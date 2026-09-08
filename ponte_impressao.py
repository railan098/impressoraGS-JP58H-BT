#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ponte_impressao.py — Ponte HTTP local entre o navegador e a impressora térmica.

O problema
----------
Um software rodando no navegador não consegue falar com a impressora USB:

  - a API WebUSB **bloqueia** dispositivos de classe 7 (impressora) por padrão;
  - e mesmo que não bloqueasse, o ``usbprint.sys`` do Windows já reivindicou o
    aparelho, então o navegador não conseguiria reivindicá-lo também;
  - ``window.print()`` abre a caixa de diálogo do Windows e renderiza a página
    como imagem — não é ESC/POS, e a impressora térmica não entende.

A solução
---------
Este app roda na máquina onde a impressora está e expõe um servidor HTTP em
``127.0.0.1``. O software web imprime com um ``fetch()`` comum::

    fetch("http://127.0.0.1:9100/imprimir", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({texto: "Meu cupom"})
    });

O caminho até o papel é o do ``usbprint_win.py``: bytes ESC/POS crus no device
interface do usbprint.sys. Nenhum driver trocado, nenhum Zadig, nada de
administrador — e funciona em Windows sobre ARM (Snapdragon).

Segurança
---------
O servidor escuta **somente em 127.0.0.1**, então nada da rede externa alcança
a impressora. Quem pode chamar é controlado por ``origens_permitidas`` no
arquivo ``ponte_config.json``: com ``"*"`` qualquer site aberto no navegador
consegue imprimir. Para travar, troque por uma lista de origens, por exemplo::

    "origens_permitidas": ["https://meusistema.com.br"]
"""

from __future__ import annotations

import base64
import json
import os
import platform
import queue
import sys
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

PASTA = os.path.dirname(os.path.abspath(__file__))
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)

import usbprint_win  # noqa: E402  (precisa do sys.path acima)

# O montar_cupom vive no imprime_termica, que importa pyusb no topo. A ponte em
# si não precisa de pyusb, então uma falha aqui não pode derrubar o app: sem ele
# o endpoint /raw continua funcionando.
try:
    from imprime_termica import ESCPOS, montar_cupom
    TEM_MONTADOR = True
except Exception:  # pragma: no cover - depende do ambiente
    TEM_MONTADOR = False
    ESCPOS = None  # type: ignore
    montar_cupom = None  # type: ignore

VERSAO = "1.0"
ARQUIVO_CONFIG = os.path.join(PASTA, "ponte_config.json")

CONFIG_PADRAO: Dict[str, Any] = {
    "porta": 9100,
    "origens_permitidas": ["*"],
    "codepage_padrao": "cp850",
    "cortar_padrao": True,
}


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
def carregar_config() -> Dict[str, Any]:
    """Lê ponte_config.json, criando-o com os padrões se não existir."""
    config = dict(CONFIG_PADRAO)
    try:
        with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as fp:
            config.update(json.load(fp))
    except FileNotFoundError:
        try:
            with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as fp:
                json.dump(config, fp, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Pasta somente-leitura: seguimos com os padrões.
    except (OSError, json.JSONDecodeError):
        pass  # Config corrompida: melhor subir com o padrão do que não subir.
    return config


# --------------------------------------------------------------------------- #
# Estado compartilhado entre o servidor e a interface
# --------------------------------------------------------------------------- #
class Estado:
    """Estado da ponte, compartilhado entre as threads do servidor e da GUI."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.trava = threading.Lock()
        self.caminho_escolhido: Optional[str] = None   # None = automático
        self.eventos: "queue.Queue[str]" = queue.Queue()
        self.impressos = 0
        self.erros = 0

    def registrar(self, mensagem: str) -> None:
        """Enfileira uma linha de log para a interface mostrar."""
        agora = datetime.now().strftime("%H:%M:%S")
        self.eventos.put(f"[{agora}] {mensagem}")

    def origem_permitida(self, origem: str) -> bool:
        """Diz se a origem do navegador pode usar a ponte."""
        permitidas: List[str] = self.config.get("origens_permitidas", ["*"])
        if "*" in permitidas:
            return True
        if not origem:
            return True  # curl / chamada sem navegador
        return origem.rstrip("/") in [p.rstrip("/") for p in permitidas]


ESTADO: Optional[Estado] = None


# --------------------------------------------------------------------------- #
# Impressão
# --------------------------------------------------------------------------- #
def imprimir_bytes(dados: bytes) -> int:
    """Manda os bytes para a impressora, respeitando a escolha manual.

    Args:
        dados: fluxo ESC/POS pronto.

    Returns:
        Bytes efetivamente escritos.
    """
    assert ESTADO is not None
    with ESTADO.trava:
        caminho = ESTADO.caminho_escolhido
    return usbprint_win.imprimir(dados, caminho=caminho)


# --------------------------------------------------------------------------- #
# Servidor HTTP
# --------------------------------------------------------------------------- #
class Manipulador(BaseHTTPRequestHandler):
    """Trata as rotas da ponte. Uma instância por requisição."""

    server_version = f"PonteImpressao/{VERSAO}"

    # -- infraestrutura ----------------------------------------------------- #
    def log_message(self, formato: str, *args: Any) -> None:
        """Silencia o log do BaseHTTPRequestHandler (ele escreve em stderr).

        Rodando com pythonw.exe não existe stderr, e a escrita pode falhar.
        O log útil vai para a janela do app.
        """
        return

    def _cabecalhos_cors(self) -> None:
        """Emite os cabeçalhos de CORS, inclusive o de Private Network Access.

        O Chrome exige ``Access-Control-Allow-Private-Network`` quando uma
        página pública chama um endereço privado como o 127.0.0.1. Sem ele o
        navegador barra a chamada mesmo com o CORS comum liberado.
        """
        assert ESTADO is not None
        origem = self.headers.get("Origin", "")
        permitidas = ESTADO.config.get("origens_permitidas", ["*"])
        if "*" in permitidas:
            self.send_header("Access-Control-Allow-Origin", origem or "*")
        elif origem:
            self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def _responder(self, codigo: int, corpo: Dict[str, Any]) -> None:
        """Responde em JSON, sempre com os cabeçalhos de CORS."""
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self._cabecalhos_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _ler_json(self) -> Dict[str, Any]:
        """Lê e decodifica o corpo JSON da requisição."""
        try:
            tamanho = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            tamanho = 0
        if tamanho <= 0:
            return {}
        if tamanho > 4 * 1024 * 1024:
            raise ValueError("Corpo grande demais (limite de 4 MB).")
        return json.loads(self.rfile.read(tamanho).decode("utf-8"))

    # -- rotas -------------------------------------------------------------- #
    def do_OPTIONS(self) -> None:  # noqa: N802 (nome exigido pela stdlib)
        self.send_response(204)
        self._cabecalhos_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        assert ESTADO is not None
        rota = self.path.split("?")[0].rstrip("/") or "/"

        if rota in ("/", "/status"):
            try:
                encontradas = usbprint_win.listar_impressoras()
            except OSError as erro:
                encontradas = []
                ESTADO.registrar(f"Falha ao listar impressoras: {erro}")
            with ESTADO.trava:
                escolhida = ESTADO.caminho_escolhido
            self._responder(200, {
                "ok": True,
                "versao": VERSAO,
                "sistema": f"{platform.system()} {platform.machine()}",
                "impressora_presente": bool(encontradas),
                "impressoras": encontradas,
                "impressora_ativa": escolhida or (encontradas[0] if encontradas
                                                  else None),
                "modo": "manual" if escolhida else "automatico",
                "impressos": ESTADO.impressos,
            })
            return

        self._responder(404, {"ok": False, "erro": f"Rota '{rota}' não existe.",
                              "rotas": ["/status", "/imprimir", "/raw"]})

    def do_POST(self) -> None:  # noqa: N802
        assert ESTADO is not None
        rota = self.path.split("?")[0].rstrip("/") or "/"
        origem = self.headers.get("Origin", "")

        if not ESTADO.origem_permitida(origem):
            ESTADO.registrar(f"BLOQUEADO: origem não autorizada -> {origem}")
            self._responder(403, {
                "ok": False,
                "erro": "Origem não autorizada.",
                "dica": "Adicione esta origem em origens_permitidas no "
                        "ponte_config.json.",
                "origem": origem,
            })
            return

        try:
            corpo = self._ler_json()
        except (ValueError, json.JSONDecodeError) as erro:
            self._responder(400, {"ok": False, "erro": f"JSON inválido: {erro}"})
            return

        try:
            if rota == "/imprimir":
                dados = self._montar(corpo)
            elif rota == "/raw":
                dados = self._decodificar_raw(corpo)
            else:
                self._responder(404, {"ok": False,
                                      "erro": f"Rota '{rota}' não existe."})
                return
        except ValueError as erro:
            self._responder(400, {"ok": False, "erro": str(erro)})
            return

        try:
            escritos = imprimir_bytes(dados)
        except RuntimeError as erro:
            ESTADO.erros += 1
            ESTADO.registrar(f"ERRO: {erro}")
            self._responder(503, {"ok": False, "erro": str(erro)})
            return
        except OSError as erro:
            ESTADO.erros += 1
            ESTADO.registrar(f"ERRO de escrita: {erro}")
            self._responder(502, {"ok": False, "erro": str(erro)})
            return

        ESTADO.impressos += 1
        ESTADO.registrar(f"Impresso: {escritos} bytes "
                         f"(origem: {origem or 'sem origem'})")
        self._responder(200, {"ok": True, "bytes": escritos})

    # -- montagem do conteúdo ---------------------------------------------- #
    def _montar(self, corpo: Dict[str, Any]) -> bytes:
        """Monta o cupom ESC/POS a partir do JSON recebido."""
        assert ESTADO is not None
        if not TEM_MONTADOR:
            raise ValueError(
                "O montador de cupom não está disponível (pyusb ausente). "
                "Use a rota /raw enviando os bytes ESC/POS em base64.")

        texto = corpo.get("texto")
        if texto is not None and not isinstance(texto, str):
            raise ValueError("O campo 'texto' precisa ser uma string.")

        codepage = corpo.get("codepage") or ESTADO.config["codepage_padrao"]
        cortar = corpo.get("cortar", ESTADO.config["cortar_padrao"])

        try:
            dados = montar_cupom(texto, codepage=codepage, cortar=bool(cortar))
        except KeyError:
            raise ValueError(f"Codepage '{codepage}' não é suportada.")

        if corpo.get("abrir_gaveta"):
            dados += ESCPOS.ABRE_GAVETA
        return dados

    def _decodificar_raw(self, corpo: Dict[str, Any]) -> bytes:
        """Extrai bytes ESC/POS crus enviados em base64."""
        bruto = corpo.get("base64")
        if not isinstance(bruto, str) or not bruto:
            raise ValueError("Envie os bytes ESC/POS no campo 'base64'.")
        try:
            return base64.b64decode(bruto, validate=True)
        except Exception as erro:
            raise ValueError(f"base64 inválido: {erro}")


def iniciar_servidor(estado: Estado) -> ThreadingHTTPServer:
    """Sobe o servidor HTTP numa thread daemon.

    Escuta só em 127.0.0.1 de propósito: assim nenhuma outra máquina da rede
    alcança a impressora.
    """
    porta = int(estado.config.get("porta", 9100))
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
    servidor.daemon_threads = True
    thread = threading.Thread(target=servidor.serve_forever,
                              name="servidor-http", daemon=True)
    thread.start()
    estado.registrar(f"Servidor no ar em http://127.0.0.1:{porta}")
    return servidor


# --------------------------------------------------------------------------- #
# Interface desktop (tkinter — vem junto com o Python, sem dependência extra)
# --------------------------------------------------------------------------- #
def abrir_janela(estado: Estado, servidor: ThreadingHTTPServer) -> None:
    """Abre a janela de status da ponte."""
    import tkinter as tk
    from tkinter import ttk

    porta = int(estado.config.get("porta", 9100))

    raiz = tk.Tk()
    raiz.title("Ponte de Impressão — Térmica 58mm")
    raiz.geometry("620x430")
    raiz.minsize(560, 380)

    moldura = ttk.Frame(raiz, padding=12)
    moldura.pack(fill="both", expand=True)

    ttk.Label(moldura, text="Ponte de Impressão",
              font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(moldura, text=f"Servidor: http://127.0.0.1:{porta}",
              foreground="#0a6").pack(anchor="w")

    # --- Situação da impressora
    caixa = ttk.LabelFrame(moldura, text="Impressora", padding=10)
    caixa.pack(fill="x", pady=(12, 8))

    rotulo_status = ttk.Label(caixa, text="procurando...",
                              font=("Segoe UI", 10, "bold"))
    rotulo_status.pack(anchor="w")

    ttk.Label(caixa, text="Conexão:").pack(anchor="w", pady=(8, 2))
    combo = ttk.Combobox(caixa, state="readonly", width=70)
    combo.pack(fill="x")

    linha = ttk.Frame(caixa)
    linha.pack(fill="x", pady=(10, 0))

    # --- Log
    caixa_log = ttk.LabelFrame(moldura, text="Atividade", padding=6)
    caixa_log.pack(fill="both", expand=True, pady=(4, 0))
    texto_log = tk.Text(caixa_log, height=9, wrap="word",
                        font=("Consolas", 9), state="disabled")
    barra = ttk.Scrollbar(caixa_log, command=texto_log.yview)
    texto_log.configure(yscrollcommand=barra.set)
    barra.pack(side="right", fill="y")
    texto_log.pack(side="left", fill="both", expand=True)

    def escrever_log(linha_texto: str) -> None:
        texto_log.configure(state="normal")
        texto_log.insert("end", linha_texto + "\n")
        texto_log.see("end")
        texto_log.configure(state="disabled")

    # --- Ações
    def ao_escolher(_evento: Any = None) -> None:
        """Fixa a impressora escolhida à mão (ou volta ao automático)."""
        escolha = combo.get()
        with estado.trava:
            estado.caminho_escolhido = None if escolha.startswith("Automático") \
                else escolha
        estado.registrar(f"Conexão definida: {escolha}")

    combo.bind("<<ComboboxSelected>>", ao_escolher)

    def imprimir_teste() -> None:
        try:
            if TEM_MONTADOR:
                dados = montar_cupom(
                    "TESTE DA PONTE\n"
                    f"{platform.system()} {platform.machine()}\n"
                    f"http://127.0.0.1:{porta}")
            else:
                dados = b"\x1B\x40TESTE DA PONTE\n\n\n"
            escritos = imprimir_bytes(dados)
            estado.registrar(f"Teste impresso: {escritos} bytes")
        except Exception as erro:
            estado.registrar(f"Falha no teste: {erro}")

    ttk.Button(linha, text="Imprimir teste",
               command=imprimir_teste).pack(side="left")
    ttk.Button(linha, text="Procurar de novo",
               command=lambda: atualizar(forcar=True)).pack(side="left",
                                                            padx=(8, 0))

    def copiar_exemplo() -> None:
        """Coloca na área de transferência o fetch() pronto para colar no site."""
        trecho = (
            f'fetch("http://127.0.0.1:{porta}/imprimir", {{\n'
            '  method: "POST",\n'
            '  headers: { "Content-Type": "application/json" },\n'
            '  body: JSON.stringify({ texto: "Meu cupom" })\n'
            '});'
        )
        raiz.clipboard_clear()
        raiz.clipboard_append(trecho)
        estado.registrar("Exemplo de código copiado para a área de transferência.")

    ttk.Button(linha, text="Copiar exemplo JS",
               command=copiar_exemplo).pack(side="left", padx=(8, 0))

    # --- Atualização periódica
    ultimo = {"lista": None}

    def atualizar(forcar: bool = False) -> None:
        """Reavalia a presença da impressora e drena o log."""
        try:
            encontradas = usbprint_win.listar_impressoras()
        except OSError:
            encontradas = []

        if forcar or encontradas != ultimo["lista"]:
            ultimo["lista"] = encontradas
            opcoes = ["Automático (primeira encontrada)"] + encontradas
            combo["values"] = opcoes
            if not combo.get() or combo.get() not in opcoes:
                combo.current(0)
            if encontradas:
                rotulo_status.configure(
                    text=f"CONECTADA — {len(encontradas)} impressora(s)",
                    foreground="#0a6")
            else:
                rotulo_status.configure(
                    text="NÃO ENCONTRADA — confira o cabo USB",
                    foreground="#c33")
            if forcar:
                estado.registrar(f"Busca manual: {len(encontradas)} encontrada(s)")

        while True:
            try:
                escrever_log(estado.eventos.get_nowait())
            except queue.Empty:
                break

        raiz.after(1500, atualizar)

    def ao_fechar() -> None:
        servidor.shutdown()
        raiz.destroy()

    raiz.protocol("WM_DELETE_WINDOW", ao_fechar)
    atualizar(forcar=True)
    raiz.mainloop()


# --------------------------------------------------------------------------- #
def main() -> int:
    global ESTADO
    config = carregar_config()
    ESTADO = Estado(config)

    if "*" in config.get("origens_permitidas", []):
        ESTADO.registrar("Atenção: qualquer site pode imprimir "
                         "(origens_permitidas = *).")

    try:
        servidor = iniciar_servidor(ESTADO)
    except OSError as erro:
        porta = config.get("porta", 9100)
        mensagem = (f"Não foi possível abrir a porta {porta}: {erro}\n\n"
                    "Provavelmente a ponte já está rodando, ou outro programa "
                    "ocupou a porta.\nTroque 'porta' no ponte_config.json.")
        try:
            import tkinter.messagebox as mb
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            mb.showerror("Ponte de Impressão", mensagem)
            r.destroy()
        except Exception:
            sys.stderr.write(mensagem + "\n")
        return 1

    if "--sem-janela" in sys.argv:
        # Modo servidor puro: útil para depurar no console.
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            servidor.shutdown()
        return 0

    try:
        abrir_janela(ESTADO, servidor)
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
