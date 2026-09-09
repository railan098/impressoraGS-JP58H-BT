# -*- coding: utf-8 -*-
"""
O servidor HTTP local e as travas que o cercam.

    navegador --HTTP--> ponte (127.0.0.1:9100) --> impressora

**Por que uma ponte é necessária.** Nenhum navegador consegue falar com uma
térmica: a WebUSB bloqueia dispositivos de classe 7 (impressora) por decisão de
segurança; no Windows o ``usbprint.sys`` já reivindicou o aparelho; e
``window.print()`` manda a página *renderizada*, não ESC/POS. Numa fila raw do
CUPS é pior — sem filtro, o PDF do navegador vai cru para a bobina e saem
metros de lixo.

**Segurança — e o motivo de cada trava.**

=============================  =============================================
Medida                         O que ela impede
=============================  =============================================
Escutar só em ``127.0.0.1``    Nenhuma máquina da rede alcança a porta. Não é
                               firewall: o socket não existe fora da máquina.
Lista de origens permitidas    Sem ela, qualquer site aberto no navegador do
                               operador manda imprimir.
Teto por minuto                Um site hostil — ou um laço com defeito no
                               próprio sistema — despeja a bobina inteira.
Teto de corpo (512 KB)         Corpo gigante como negação de serviço.
Nome conferido na lista real   Erro de digitação vira mensagem clara; nome
                               forjado não chega a lugar nenhum.
Nenhum shell                   ``subprocess`` com lista de argumentos, Win32
                               por ctypes. ``Termica; rm -rf /`` é só um nome
                               que não existe.
Configuração no perfil         Não precisa de administrador, e o programa não
                               escreve na pasta de instalação.
=============================  =============================================

**O que a ponte não faz, de propósito:** ela não tem acesso a dado de negócio.
Sem banco, sem leitura de arquivo do sistema, sem rota que devolva informação
de venda. O que entra é texto para imprimir; o que sai é "deu certo" ou o
motivo da falha.

**Limite honesto:** a porta é acessível a qualquer programa rodando na mesma
máquina. Isso é inerente a qualquer ponte local; a mitigação real é o
computador do balcão não ser de uso geral.
"""

from __future__ import annotations

import base64
import json
import platform
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional

from . import NOME, VERSAO
from . import catalogo, config, escpos

LIMITE_CORPO = 512 * 1024


class Limitador:
    """Teto de trabalhos por minuto, em janela deslizante."""

    def __init__(self, por_minuto: int) -> None:
        self.por_minuto = por_minuto
        self._marcas: deque = deque()
        self._trava = threading.Lock()

    def permitir(self) -> bool:
        agora = time.time()
        with self._trava:
            while self._marcas and agora - self._marcas[0] > 60:
                self._marcas.popleft()
            if len(self._marcas) >= self.por_minuto:
                return False
            self._marcas.append(agora)
            return True


class Ponte(BaseHTTPRequestHandler):
    server_version = f"MenuxyPonte/{VERSAO}"
    protocol_version = "HTTP/1.1"

    # Estado de classe: um só servidor por processo, e assim o handler — que é
    # instanciado a cada requisição — não precisa receber nada no construtor.
    cfg: Dict[str, Any] = {}
    limitador: Optional[Limitador] = None
    ao_registrar: Optional[Callable[[bool, str, int], None]] = None

    def log_message(self, formato, *args):
        pass    # a sondagem de 3s do agente encheria o terminal

    # ------------------------------------------------------------ utilidades
    def _origem_permitida(self) -> bool:
        permitidas = self.cfg.get("origens_permitidas", ["*"])
        if "*" in permitidas:
            return True
        origem = (self.headers.get("Origin") or "").rstrip("/").lower()
        if not origem:
            # Chamada fora do navegador (curl, o verificador, um script do
            # próprio balcão). Não há origem para conferir, e bloquear aqui
            # quebraria o diagnóstico sem impedir nada: quem roda um script na
            # máquina já tem acesso à porta de qualquer jeito.
            return True
        return origem in [o.rstrip("/").lower() for o in permitidas]

    def _responder(self, dados: Dict[str, Any], codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))

        origem = self.headers.get("Origin")
        permitidas = self.cfg.get("origens_permitidas", ["*"])
        self.send_header("Access-Control-Allow-Origin",
                         "*" if "*" in permitidas else (origem or ""))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # O Chrome exige este cabeçalho quando uma página pública chama
        # 127.0.0.1 (Private Network Access). Sem ele a chamada é barrada mesmo
        # com o CORS comum liberado, e SEM erro visível no console — é o tipo de
        # falha que custa meio dia de depuração.
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(corpo)

    def _tamanho_anunciado(self) -> int:
        """O ``Content-Length``, ou -1 se ele estiver ausente ou for lixo."""
        try:
            return int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return -1

    def _descartar(self, tamanho: int) -> None:
        """
        Lê e joga fora um corpo grande demais, antes de responder.

        Sem isto, responder 413 enquanto o cliente ainda está enviando os
        600 KB faz o navegador receber um "connection reset" em vez da
        resposta — e a página mostra "a ponte não respondeu", que manda o
        operador procurar o problema no lugar errado.

        O descarte tem teto: acima dele a conexão é simplesmente fechada. Ler
        um corpo de 1 GB só para poder responder com educação seria a própria
        negação de serviço que o limite existe para impedir.
        """
        restante = min(tamanho, LIMITE_CORPO * 4)
        while restante > 0:
            pedaco = self.rfile.read(min(65536, restante))
            if not pedaco:
                break
            restante -= len(pedaco)

    def _corpo_json(self) -> Optional[Dict[str, Any]]:
        tamanho = self._tamanho_anunciado()
        if tamanho <= 0 or tamanho > LIMITE_CORPO:
            return None
        try:
            bruto = self.rfile.read(tamanho).decode("utf-8", "replace")
            dados = json.loads(bruto)
        except Exception:
            return None
        return dados if isinstance(dados, dict) else None

    def _catalogo(self):
        return catalogo.listar(self.cfg)

    # ---------------------------------------------------------------- rotas
    def do_OPTIONS(self):
        self._responder({}, 204)

    def do_GET(self):
        caminho = self.path.split("?", 1)[0].rstrip("/") or "/"

        if caminho in ("/", "/status"):
            lista, padrao = self._catalogo()
            self._responder({
                "ok": True,
                "versao": VERSAO,
                "sistema": platform.system().lower(),
                "backends": catalogo.backends_ativos(),
                # Nomes crus para as versões antigas do agente, objetos para as
                # novas. Manter os dois é o que permite atualizar o servidor sem
                # atualizar todos os balcões no mesmo dia.
                "impressoras": [item["id"] for item in lista],
                "detalhes": [_publico(item) for item in lista],
                "padrao": padrao,
                "escolhida": self.cfg.get("impressora_padrao") or "",
                "colunas": self.cfg.get("colunas", 32),
                "origens_abertas": config.origens_abertas(self.cfg),
            })
            return

        if caminho == "/impressoras":
            lista, padrao = self._catalogo()
            self._responder({
                "ok": True,
                "impressoras": [_publico(item) for item in lista],
                "padrao": padrao,
            })
            return

        if caminho == "/saude":
            # Rota mínima para o supervisor do sistema (systemd, agendador do
            # Windows) saber que o processo está de pé, sem tocar em impressora.
            self._responder({"ok": True, "versao": VERSAO})
            return

        self._responder({"ok": False, "erro": "rota desconhecida"}, 404)

    def do_POST(self):
        caminho = self.path.split("?", 1)[0].rstrip("/")

        if caminho not in ("/imprimir", "/raw", "/gaveta"):
            self._responder({"ok": False, "erro": "rota desconhecida"}, 404)
            return

        if not self._origem_permitida():
            self._responder({"ok": False, "erro": "origem não autorizada"}, 403)
            return

        if self.limitador and not self.limitador.permitir():
            self._responder({"ok": False, "erro": "muitos trabalhos por minuto"}, 429)
            return

        tamanho = self._tamanho_anunciado()
        if tamanho > LIMITE_CORPO:
            self._descartar(tamanho)
            self._responder(
                {"ok": False,
                 "erro": f"corpo de {tamanho} bytes é maior que o limite de {LIMITE_CORPO}"},
                413)
            # A conexão não é reaproveitada: o cliente pode ter parado de
            # enviar no meio, e o que sobrou no cano contaminaria o próximo
            # pedido desta mesma conexão.
            self.close_connection = True
            return

        dados = self._corpo_json()
        if dados is None:
            self._responder(
                {"ok": False, "erro": "corpo ausente, grande demais ou JSON inválido"}, 400)
            return

        impressora = str(dados.get("impressora") or "")

        try:
            bytes_cupom = self._montar(caminho, dados)
        except ValueError as erro:
            self._responder({"ok": False, "erro": str(erro)}, 400)
            return

        try:
            ok, detalhe = catalogo.imprimir(impressora, bytes_cupom, self.cfg)
        except catalogo.ImpressoraDesconhecida as erro:
            self._responder({"ok": False, "erro": str(erro)}, 404)
            return
        except Exception as erro:
            self._responder({"ok": False, "erro": f"falha inesperada: {erro}"}, 500)
            return

        if self.ao_registrar:
            try:
                self.ao_registrar(ok, detalhe, len(bytes_cupom))
            except Exception:
                pass    # a janela não pode derrubar a impressão

        if ok:
            self._responder({"ok": True, "impressora": detalhe, "bytes": len(bytes_cupom)})
        else:
            self._responder({"ok": False, "erro": detalhe}, 500)

    # ------------------------------------------------------------- montagem
    def _montar(self, caminho: str, dados: Dict[str, Any]) -> bytes:
        """Cada rota vira bytes de um jeito. Erros de entrada saem como ValueError."""
        if caminho == "/gaveta":
            # Abrir a gaveta de dinheiro sem imprimir nada.
            return escpos.comando_gaveta()

        if caminho == "/raw":
            # ESC/POS já montado por quem chamou, em base64. Existe para o que a
            # ponte não sabe montar: logotipo em bitmap, QR code, comandos de
            # modelos específicos.
            try:
                bytes_cupom = base64.b64decode(dados.get("base64") or "", validate=True)
            except Exception:
                raise ValueError("base64 inválido")
            if not bytes_cupom:
                raise ValueError("nada para imprimir")
            if len(bytes_cupom) > LIMITE_CORPO:
                raise ValueError("conteúdo grande demais")
            return bytes_cupom

        texto = dados.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("sem texto para imprimir")

        # `colunas: 0` no pedido = "já formatei, não mexa". Ausente = usa o
        # configurado nesta máquina, que é o que uma bobina de 58 mm precisa.
        colunas = dados.get("colunas", self.cfg.get("colunas", 32))
        try:
            colunas = max(0, min(96, int(colunas)))
        except (TypeError, ValueError):
            colunas = self.cfg.get("colunas", 32)

        return escpos.montar_cupom(
            texto,
            codepage=str(dados.get("codepage") or self.cfg.get("codepage", "cp850")),
            cortar=bool(dados.get("cortar", self.cfg.get("cortar_por_padrao", True))),
            avancos=int(self.cfg.get("avancos_antes_do_corte", 4)),
            colunas=colunas,
            gaveta=bool(dados.get("gaveta", self.cfg.get("abrir_gaveta_apos_imprimir", False))),
        )


def _publico(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    O que a ponte conta sobre uma impressora.

    ``nome`` repete o ``id`` de propósito: o agente do Menuxy lê ``nome``, e
    versões futuras leem ``id``. Um campo a mais custa nada e evita um dia de
    incompatibilidade.
    """
    return {
        "id": item["id"],
        "nome": item["id"],
        "rotulo": item["rotulo"],
        "tipo": item["tipo"],
        "papel": item["papel"],
        "detalhe": item.get("detalhe", ""),
    }


def criar(cfg: Dict[str, Any]) -> ThreadingHTTPServer:
    """
    Sobe o servidor em 127.0.0.1, e só nele.

    ``ThreadingHTTPServer`` porque uma impressão pode levar segundos (o CUPS
    responde quando quer) e a sondagem de status não pode ficar na fila atrás
    dela.
    """
    Ponte.cfg = cfg
    Ponte.limitador = Limitador(int(cfg.get("limite_por_minuto", 60)))
    servidor = ThreadingHTTPServer(("127.0.0.1", int(cfg["porta"])), Ponte)
    servidor.daemon_threads = True
    return servidor


def descrever(cfg: Dict[str, Any]) -> List[str]:
    """As linhas que a ponte imprime no terminal ao subir."""
    lista, padrao = catalogo.listar(cfg, forcar=True)
    linhas = [
        f"{NOME} v{VERSAO}",
        f"  escutando em   http://127.0.0.1:{cfg['porta']}",
        f"  sistema        {platform.system()} {platform.release()} ({platform.machine()})",
        f"  caminhos       {', '.join(catalogo.backends_ativos())}",
        f"  impressoras    {len(lista)}" + (f"  |  padrão do sistema: {padrao}" if padrao else "  |  sem padrão do sistema"),
    ]
    for item in lista:
        marca = "  <= escolhida" if item["id"] == cfg.get("impressora_padrao") else ""
        linhas.append(f"     - {item['id']}   ({item['rotulo']}){marca}")
    if config.origens_abertas(cfg):
        linhas.append("  ATENÇÃO: aceitando QUALQUER origem. Feche com:")
        linhas.append("           menuxy-ponte --origens https://seusistema.com.br")
    else:
        linhas.append(f"  origens        {', '.join(cfg['origens_permitidas'])}")
    linhas.append(f"  configuração   {config.caminho_config()}")
    return linhas
