#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificador da ponte de impressão.

Sobe a ponte numa porta própria e exercita rotas, resolução de impressora,
nomes hostis, validação de entrada, lista de origens e teto por minuto.

**Ele não gasta papel.** Mira uma impressora que não existe e confere a recusa.
Isso não é escrúpulo de teste: um verificador anterior mirou a térmica de
verdade ao testar o teto por minuto e imprimiu cerca de 50 cupons de um
caractere antes de alguém cancelar a fila.

Para imprimir de verdade — UM cupom, numa impressora que você nomeia::

    python3 testes/verificar_ponte.py --com-papel sistema:Termica58

Uso normal::

    python3 testes/verificar_ponte.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ponte_menuxy import (VERSAO, catalogo, config, escpos,  # noqa: E402
                          inicializacao, servidor)
from ponte_menuxy.backends import rede, serial_, sistema, usb_direta, usbprint  # noqa: E402

PORTA = 19187          # porta alta e improvável: não colide com a ponte de verdade
BASE = f"http://127.0.0.1:{PORTA}"
ORIGEM_BOA = "https://menuxy.alvesprotect.app.br"

# Uma impressora que não existe em máquina nenhuma. É ela que recebe todos os
# trabalhos deste verificador.
FANTASMA = "sistema:__impressora_que_nao_existe__"

_passou = 0
_falhou = 0
_falhas: list = []


def conferir(descricao: str, condicao: bool, detalhe: str = "") -> None:
    global _passou, _falhou
    if condicao:
        _passou += 1
        print(f"  [ok]   {descricao}")
    else:
        _falhou += 1
        _falhas.append(descricao)
        print(f"  [FALHA] {descricao}" + (f"  ({detalhe})" if detalhe else ""))


def chamar(caminho: str, corpo=None, origem: str = "", metodo: str = ""):
    """Devolve (código HTTP, dicionário da resposta)."""
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(BASE + caminho, data=dados,
                                    method=metodo or ("POST" if dados else "GET"))
    if dados:
        pedido.add_header("Content-Type", "application/json")
    if origem:
        pedido.add_header("Origin", origem)
    try:
        with urllib.request.urlopen(pedido, timeout=12) as resposta:
            return resposta.status, json.loads(resposta.read().decode() or "{}")
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read().decode() or "{}")
        except Exception:
            return erro.code, {}
    except Exception as erro:
        return 0, {"erro_local": str(erro)}


def cru(corpo: bytes, cabecalhos: dict = None, caminho: str = "/imprimir"):
    """Envia bytes crus — para JSON quebrado e corpos gigantes."""
    pedido = urllib.request.Request(BASE + caminho, data=corpo, method="POST")
    pedido.add_header("Content-Type", "application/json")
    for chave, valor in (cabecalhos or {}).items():
        pedido.add_header(chave, valor)
    try:
        with urllib.request.urlopen(pedido, timeout=12) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        return erro.code
    except Exception:
        return 0


# =========================================================================== #
#  Blocos de verificação
# =========================================================================== #

def bloco_escpos():
    print("\n[1] Montagem ESC/POS")
    cupom = escpos.montar_cupom("Teste", codepage="cp850", cortar=True, avancos=4)
    conferir("começa com ESC @ (reinicialização)", cupom.startswith(b"\x1b\x40"))
    conferir("seleciona a página de código antes do texto", b"\x1b\x74\x02" in cupom)
    conferir("termina com GS V 0 (corte total)", cupom.endswith(b"\x1d\x56\x00"))
    conferir("avança antes de cortar (a lâmina fica acima da cabeça)",
             b"\n\n\n\n\x1d\x56\x00" in cupom)

    sem_corte = escpos.montar_cupom("Teste", cortar=False)
    conferir("sem corte quando pedido", not sem_corte.endswith(b"\x1d\x56\x00"))

    acentos = escpos.montar_cupom("ação coração pão", codepage="cp850")
    conferir("acentua em cp850 sem estourar", b"\x87" in acentos)

    # cp437 não tem "ã": tem que virar "a", não "?" nem exceção.
    caido = escpos.codificar("pão", "cp437")
    conferir("acento sem tabela vira letra simples, não '?'",
             b"?" not in caido and b"pao" in caido, repr(caido))

    quebrado = escpos.quebrar("a" * 100, 32)
    conferir("quebra palavra maior que a bobina",
             all(len(l) <= 32 for l in quebrado.split("\n")))
    palavras = escpos.quebrar("um dois tres quatro cinco seis sete oito nove dez", 20)
    conferir("não parte palavra no meio ao quebrar",
             all(len(l) <= 20 for l in palavras.split("\n")) and "quatr\no" not in palavras)

    conferir("comando de gaveta é ESC p", escpos.comando_gaveta().endswith(b"\x1b\x70\x00\x19\xfa"))
    conferir("cupom de teste tem a régua da largura",
             "....+....1" in escpos.cupom_de_teste(32))


def bloco_config():
    print("\n[2] Configuração e saneamento")
    conferir("porta absurda vira algo válido",
             1 <= config.carregar_de({"porta": 999999})["porta"] <= 65535)
    conferir("porta como texto não derruba",
             config.carregar_de({"porta": "noventa"})["porta"] == config.PADRAO["porta"])
    conferir("página de código inventada volta ao padrão",
             config.carregar_de({"codepage": "cp999"})["codepage"] == "cp850")
    conferir("lista de origens vazia volta a ['*']",
             config.carregar_de({"origens_permitidas": []})["origens_permitidas"] == ["*"])
    conferir("origens como texto solto não derruba",
             isinstance(config.carregar_de({"origens_permitidas": "abc"})["origens_permitidas"], list))
    conferir("impressora de rede sem host é descartada",
             config.carregar_de({"impressoras_rede": [{"nome": "x"}, "lixo"]})["impressoras_rede"] == [])
    conferir("impressora de rede válida sobrevive",
             config.carregar_de({"impressoras_rede": [
                 {"nome": "Cozinha", "host": "10.0.0.5", "porta": "9100"}]})["impressoras_rede"][0]["porta"] == 9100)
    conferir("colunas fora da faixa são corrigidas",
             24 <= config.carregar_de({"colunas": 5})["colunas"] <= 96)
    conferir("a configuração mora no perfil do usuário",
             os.path.expanduser("~") in config.caminho_config())


def bloco_backends():
    print("\n[3] Backends")
    for modulo in (sistema, usb_direta, usbprint, rede, serial_):
        conferir(f"backend '{modulo.TIPO}' responde ao contrato",
                 all(hasattr(modulo, nome) for nome in ("disponivel", "listar", "imprimir", "alvo_de", "TIPO")))
    conferir("backend de rede está sempre disponível (só usa socket)", rede.disponivel())
    conferir("usbprint só existe no Windows",
             usbprint.disponivel() == (os.name == "nt"))
    conferir("rede: extrai host e porta do identificador",
             rede.alvo_de("rede:192.168.0.50:9100") == ("192.168.0.50", 9100))
    conferir("rede: assume a 9100 quando a porta é omitida",
             rede.alvo_de("rede:192.168.0.50") == ("192.168.0.50", 9100))
    conferir("serial: extrai dispositivo e velocidade",
             serial_.alvo_de("serial:/dev/ttyUSB0:19200") == ("/dev/ttyUSB0", 19200))
    conferir("sistema: extrai o nome da fila",
             sistema.alvo_de("sistema:Termica 58") == "Termica 58")
    conferir("usb: extrai VID e PID em hexadecimal",
             usb_direta.alvo_de("usb:0416:5011") == (0x0416, 0x5011))
    ok, detalhe = rede.imprimir(("127.0.0.1", 9), b"x")
    conferir("rede: host inalcançável falha com explicação, sem exceção",
             ok is False and isinstance(detalhe, str) and detalhe)
    _conferir_interface_usb()
    _conferir_ambiente_de_snap()


# --------------------------------------------------------------------------- #
#  Ambiente vazado por um snap
# --------------------------------------------------------------------------- #
# Regressão de outro caso real: aberta a partir do terminal do VS Code (que é um
# snap), a ponte herdava XDG_DATA_HOME e GIO_MODULE_DIR do sandbox. O atalho do
# menu ia parar dentro do snap — onde o GNOME nunca procura — e o `gio set
# metadata::trusted` falhava com "not supported", porque o gio do sistema
# carregava os módulos do sandbox. Sem a marcação, o GNOME **não lança** o ícone
# da área de trabalho: o duplo clique não faz nada e não diz nada.

def _conferir_ambiente_de_snap():
    guardado = {nome: os.environ.get(nome)
                for nome in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "GIO_MODULE_DIR",
                             "LD_LIBRARY_PATH")}
    try:
        casa = os.path.expanduser("~")

        os.environ["XDG_DATA_HOME"] = f"{casa}/snap/code/260/.local/share"
        conferir("snap: XDG_DATA_HOME do sandbox é ignorado",
                 inicializacao.pasta_xdg("XDG_DATA_HOME", ".local", "share")
                 == os.path.join(casa, ".local", "share"),
                 inicializacao.pasta_xdg("XDG_DATA_HOME", ".local", "share"))

        os.environ["XDG_DATA_HOME"] = f"{casa}/meus-dados"
        conferir("snap: um XDG_DATA_HOME legítimo é respeitado",
                 inicializacao.pasta_xdg("XDG_DATA_HOME", ".local", "share")
                 == f"{casa}/meus-dados")

        os.environ.pop("XDG_CONFIG_HOME", None)
        conferir("snap: sem a variável, cai no padrão do XDG",
                 inicializacao.pasta_xdg("XDG_CONFIG_HOME", ".config")
                 == os.path.join(casa, ".config"))

        os.environ["GIO_MODULE_DIR"] = f"{casa}/snap/code/common/.cache/gio-modules"
        os.environ["LD_LIBRARY_PATH"] = "/opt/meu-programa/lib"
        limpo = inicializacao.ambiente_limpo()
        conferir("snap: GIO_MODULE_DIR do sandbox sai do ambiente",
                 "GIO_MODULE_DIR" not in limpo)
        conferir("snap: LD_LIBRARY_PATH legítimo permanece",
                 limpo.get("LD_LIBRARY_PATH") == "/opt/meu-programa/lib")
        conferir("snap: ambiente_limpo devolve cópia, não mexe no processo",
                 os.environ.get("GIO_MODULE_DIR", "").endswith("gio-modules"))

        conferir("snap: reconhece caminho de sandbox",
                 inicializacao._dentro_de_snap(f"{casa}/snap/code/260/.local/share")
                 and inicializacao._dentro_de_snap("/snap/code/260/usr/lib"))
        conferir("snap: não confunde uma pasta que só tem 'snap' no nome",
                 not inicializacao._dentro_de_snap(f"{casa}/Documentos/snapshots"))
    finally:
        for nome, valor in guardado.items():
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor


# --------------------------------------------------------------------------- #
#  A interface certa no USB direto
# --------------------------------------------------------------------------- #
# Regressão de um caso real: numa Epson L3150 a classe 7 (Printer) mora na
# interface 1, com 'usbhid' na 0. O backend soltava o driver do kernel da
# interface 0 por hábito, o 'usblp' continuava segurando a 1, e o claim morria
# com "[Errno 16] Resource busy" — que a ponte traduzia como "outro programa
# tem a impressora", mandando o operador procurar um culpado inexistente.
#
# O teste monta um barramento de mentira, então roda em qualquer máquina,
# com ou sem pyusb, com ou sem impressora plugada — e sem gastar papel.

class _EndpointFalso:
    def __init__(self, endereco, atributos=0x02):
        self.bEndpointAddress = endereco
        self.bmAttributes = atributos


class _InterfaceFalsa:
    def __init__(self, numero, classe, endpoints):
        self.bInterfaceNumber = numero
        self.bInterfaceClass = classe
        self._endpoints = endpoints

    def __iter__(self):
        return iter(self._endpoints)


class _ConfiguracaoFalsa:
    def __init__(self, interfaces):
        self._interfaces = interfaces

    def __iter__(self):
        return iter(self._interfaces)

    def __getitem__(self, chave):
        return self._interfaces[0]


class _DispositivoFalso:
    def __init__(self, interfaces, com_driver_em):
        self.configuracao = _ConfiguracaoFalsa(interfaces)
        self.com_driver_em = set(com_driver_em)
        self.diario = []       # tudo o que o backend fez, em ordem

    def get_active_configuration(self):
        return self.configuracao

    def is_kernel_driver_active(self, numero):
        return numero in self.com_driver_em

    def detach_kernel_driver(self, numero):
        if numero not in self.com_driver_em:
            raise OSError(2, "No data available")
        self.com_driver_em.discard(numero)
        self.diario.append(("soltou", numero))

    def attach_kernel_driver(self, numero):
        self.com_driver_em.add(numero)
        self.diario.append(("devolveu", numero))


def _usb_de_mentira(dispositivo):
    """Instala um 'usb' falso em sys.modules e devolve o que remover depois."""
    import types

    escritos = []

    def claim_interface(dev, numero):
        if numero in dev.com_driver_em:
            raise OSError(16, "Resource busy")
        dev.diario.append(("reivindicou", numero))

    def release_interface(dev, numero):
        dev.diario.append(("liberou", numero))

    def find_descriptor(interface, custom_match=None):
        for endpoint in interface:
            if custom_match is None or custom_match(endpoint):
                return endpoint
        return None

    class _EscritorFalso:
        def __init__(self, endpoint, dispositivo):
            self.endpoint = endpoint
            self.dispositivo = dispositivo

    def escrever(endpoint, dados, timeout=None):
        escritos.append((endpoint.bEndpointAddress, len(dados)))
        return len(dados)

    _EndpointFalso.write = escrever

    util = types.ModuleType("usb.util")
    util.ENDPOINT_OUT = 0x00
    util.ENDPOINT_TYPE_BULK = 0x02
    util.endpoint_direction = lambda endereco: endereco & 0x80
    util.endpoint_type = lambda atributos: atributos & 0x03
    util.find_descriptor = find_descriptor
    util.claim_interface = claim_interface
    util.release_interface = release_interface
    util.dispose_resources = lambda dev: None

    core = types.ModuleType("usb.core")
    core.find = lambda **kw: dispositivo

    raiz = types.ModuleType("usb")
    raiz.core = core
    raiz.util = util

    anteriores = {nome: sys.modules.get(nome) for nome in ("usb", "usb.core", "usb.util")}
    sys.modules.update({"usb": raiz, "usb.core": core, "usb.util": util})
    return anteriores, escritos


def _rodar_com_usb_falso(interfaces, com_driver_em):
    dispositivo = _DispositivoFalso(interfaces, com_driver_em)
    anteriores, escritos = _usb_de_mentira(dispositivo)
    try:
        ok, detalhe = usb_direta.imprimir((0x04b8, 0x1143), b"CUPOM")
    finally:
        for nome, modulo in anteriores.items():
            if modulo is None:
                sys.modules.pop(nome, None)
            else:
                sys.modules[nome] = modulo
    return ok, detalhe, dispositivo.diario, escritos


def _conferir_interface_usb():
    # Multifuncional: 'usbhid' na 0, impressora (classe 7) na 1 com o 'usblp'.
    # É a Epson L3150, e o formato de toda multifuncional.
    multifuncional = [
        _InterfaceFalsa(0, 0xFF, [_EndpointFalso(0x01)]),
        _InterfaceFalsa(1, 7, [_EndpointFalso(0x04), _EndpointFalso(0x85)]),
        _InterfaceFalsa(2, 0xFF, [_EndpointFalso(0x07)]),
    ]
    ok, detalhe, diario, escritos = _rodar_com_usb_falso(multifuncional, com_driver_em={1})

    conferir("usb: multifuncional (classe 7 na interface 1) imprime",
             ok is True, detalhe)
    conferir("usb: solta o driver da interface de impressora, não da 0",
             ("soltou", 1) in diario and ("soltou", 0) not in diario, str(diario))
    conferir("usb: reivindica a interface de impressora",
             ("reivindicou", 1) in diario, str(diario))
    conferir("usb: escreve no endpoint bulk-out daquela interface (0x04)",
             escritos == [(0x04, 5)], str(escritos))
    conferir("usb: devolve o driver do kernel no fim (a fila do sistema sobrevive)",
             ("devolveu", 1) in diario, str(diario))
    conferir("usb: libera antes de devolver o driver",
             ("liberou", 1) in diario
             and diario.index(("liberou", 1)) < diario.index(("devolveu", 1)), str(diario))

    # Térmica simples: uma interface só, a 0. O caminho de sempre não regride.
    termica = [_InterfaceFalsa(0, 7, [_EndpointFalso(0x01), _EndpointFalso(0x82)])]
    ok, detalhe, diario, escritos = _rodar_com_usb_falso(termica, com_driver_em={0})
    conferir("usb: térmica de uma interface só continua imprimindo",
             ok is True, detalhe)
    conferir("usb: nela o driver solto é o da 0 mesmo",
             ("soltou", 0) in diario and ("reivindicou", 0) in diario, str(diario))

    # Sem 'usblp' segurando nada: não há o que soltar, e nada a devolver.
    ok, _, diario, _ = _rodar_com_usb_falso(
        [_InterfaceFalsa(1, 7, [_EndpointFalso(0x04)])], com_driver_em=set())
    conferir("usb: sem driver do kernel, não solta nem devolve nada",
             ok is True and not any(a in ("soltou", "devolveu") for a, _ in diario),
             str(diario))


def bloco_resolucao(cfg):
    print("\n[4] Resolução de impressora")
    lista, _ = catalogo.listar(cfg, forcar=True)
    reais = [i["id"] for i in lista]

    for hostil in ("Termica; rm -rf /", "$(whoami)", "`id`", "../../etc/passwd",
                   "sistema:; shutdown -h now", "\x00nulo", "a" * 500):
        try:
            catalogo.resolver(hostil, cfg)
            recusou = False
        except catalogo.ImpressoraDesconhecida:
            recusou = True
        except Exception:
            recusou = True
        conferir(f"nome hostil recusado: {hostil[:28]!r}", recusou)

    if reais:
        alvo = reais[0]
        backend, _, _ = catalogo.resolver(alvo, cfg)
        conferir("id completo resolve", backend.TIPO == alvo.split(":", 1)[0])
        if alvo.startswith("sistema:"):
            nome_nu = alvo.split(":", 1)[1]
            backend, _, _ = catalogo.resolver(nome_nu, cfg)
            conferir("nome nu resolve contra a lista real", backend.TIPO == "sistema")
    else:
        print("  [i]    sem impressoras nesta máquina: dois testes de resolução pulados")

    backend, alvo, _ = catalogo.resolver("rede:10.1.2.3:9100", cfg)
    conferir("endereço de rede resolve sem cadastro prévio",
             backend.TIPO == "rede" and alvo == ("10.1.2.3", 9100))

    vazio = dict(cfg)
    vazio["impressora_padrao"] = ""
    try:
        catalogo.resolver("", vazio)
        sem_padrao_ok = bool(sistema.padrao_do_sistema())
    except catalogo.ImpressoraDesconhecida:
        sem_padrao_ok = True
    conferir("identificador vazio cai na padrão do sistema, ou recusa com clareza", sem_padrao_ok)


def bloco_rotas():
    print("\n[5] Rotas HTTP")
    codigo, dados = chamar("/status")
    conferir("GET /status responde 200", codigo == 200, str(codigo))
    conferir("/status informa a versão", dados.get("versao") == VERSAO)
    conferir("/status lista os caminhos ativos", isinstance(dados.get("backends"), list))
    conferir("/status traz impressoras como texto (agente antigo)",
             isinstance(dados.get("impressoras"), list))
    conferir("/status traz detalhes como objeto (agente novo)",
             isinstance(dados.get("detalhes"), list))
    conferir("/status avisa se as origens estão abertas",
             isinstance(dados.get("origens_abertas"), bool))

    codigo, dados = chamar("/impressoras")
    conferir("GET /impressoras responde 200", codigo == 200)
    conferir("/impressoras devolve lista de objetos com nome e rótulo",
             all(("nome" in i and "rotulo" in i) for i in dados.get("impressoras", [])))

    codigo, _ = chamar("/saude")
    conferir("GET /saude responde 200 sem tocar em impressora", codigo == 200)

    codigo, _ = chamar("/")
    conferir("GET / responde como /status", codigo == 200)

    codigo, _ = chamar("/status/")
    conferir("barra no fim não muda a rota", codigo == 200)

    codigo, _ = chamar("/inventada")
    conferir("rota desconhecida responde 404", codigo == 404)

    codigo, _ = chamar("/naoexiste", corpo={"texto": "x"})
    conferir("POST em rota desconhecida responde 404", codigo == 404)


def bloco_cabecalhos():
    print("\n[6] Cabeçalhos CORS")
    pedido = urllib.request.Request(BASE + "/imprimir", method="OPTIONS")
    pedido.add_header("Origin", ORIGEM_BOA)
    try:
        with urllib.request.urlopen(pedido, timeout=8) as resposta:
            cabecalhos = {k.lower(): v for k, v in resposta.getheaders()}
            codigo = resposta.status
    except urllib.error.HTTPError as erro:
        cabecalhos = {k.lower(): v for k, v in erro.headers.items()}
        codigo = erro.code

    conferir("preflight OPTIONS responde", codigo in (200, 204), str(codigo))
    conferir("preflight libera a origem", "access-control-allow-origin" in cabecalhos)
    conferir("preflight libera POST", "POST" in cabecalhos.get("access-control-allow-methods", ""))
    # Sem este cabeçalho o Chrome barra a chamada a 127.0.0.1 mesmo com o CORS
    # comum liberado, e sem erro visível no console.
    conferir("preflight traz Allow-Private-Network (exigência do Chrome)",
             cabecalhos.get("access-control-allow-private-network") == "true")


def bloco_entrada():
    print("\n[7] Validação de entrada")
    codigo, dados = chamar("/imprimir", corpo={})
    conferir("corpo sem texto responde 400", codigo == 400, str(codigo))

    codigo, _ = chamar("/imprimir", corpo={"texto": "   "})
    conferir("texto só com espaços responde 400", codigo == 400)

    codigo, _ = chamar("/imprimir", corpo={"texto": 12345})
    conferir("texto que não é texto responde 400", codigo == 400)

    conferir("JSON quebrado responde 400", cru(b"{isto nao e json") == 400)
    conferir("corpo vazio responde 400", cru(b"") == 400)

    # 413 e não 400: o corpo é válido, só é grande demais. E a ponte precisa
    # DRENAR o excesso antes de responder — respondendo com o cliente ainda
    # enviando, o navegador recebe "connection reset" no lugar da resposta, e a
    # página mostra "a ponte não respondeu", mandando procurar no lugar errado.
    grande = b'{"texto":"' + b"A" * (600 * 1024) + b'"}'
    conferir("corpo de 600 KB é recusado com 413 legível", cru(grande) == 413)

    gigante = b'{"texto":"' + b"A" * (3 * 1024 * 1024) + b'"}'
    conferir("corpo de 3 MB não derruba nem trava a ponte", cru(gigante) in (413, 0))

    # E a ponte tem que continuar de pé depois dos dois.
    conferir("a ponte sobrevive aos corpos gigantes", chamar("/saude")[0] == 200)

    conferir("Content-Length mentindo não derruba a ponte",
             cru(b'{"texto":"x"}', {"Content-Length": "abc"}) in (400, 0))

    codigo, _ = chamar("/raw", corpo={"base64": "isto!!!nao@e#base64"})
    conferir("base64 inválido responde 400", codigo == 400)

    codigo, _ = chamar("/raw", corpo={"base64": ""})
    conferir("base64 vazio responde 400", codigo == 400)

    # Base64 válido, impressora fantasma: tem que passar da validação e falhar
    # na entrega — 404, não 400.
    codigo, _ = chamar("/raw", corpo={"base64": base64.b64encode(b"\x1b@teste").decode(),
                                      "impressora": FANTASMA})
    conferir("base64 válido passa da validação e falha na entrega (404)", codigo == 404)


def bloco_impressora_inexistente():
    print("\n[8] Impressora que não existe (nenhum papel é gasto)")
    codigo, dados = chamar("/imprimir", corpo={"texto": "teste", "impressora": FANTASMA})
    conferir("impressora inexistente responde 404", codigo == 404, str(codigo))
    conferir("a resposta diz o que existe nesta máquina",
             "disponíveis" in (dados.get("erro") or "").lower(), dados.get("erro", ""))

    for hostil in ("Termica; rm -rf /", "$(whoami)", "`id`", "../../etc/passwd"):
        codigo, _ = chamar("/imprimir", corpo={"texto": "x", "impressora": hostil})
        conferir(f"nome hostil recusado pela rota: {hostil[:24]!r}", codigo == 404)


def bloco_origens(cfg):
    print("\n[9] Lista de origens")
    from ponte_menuxy.servidor import Ponte
    original = list(Ponte.cfg["origens_permitidas"])
    Ponte.cfg["origens_permitidas"] = [ORIGEM_BOA]
    try:
        casos = [
            (ORIGEM_BOA, True, "origem exata é aceita"),
            (ORIGEM_BOA + "/", True, "barra no fim não muda a origem"),
            (ORIGEM_BOA.upper(), True, "maiúsculas não mudam a origem"),
            ("https://menuxy.alvesprotect.app.br:8443", False, "porta diferente é recusada"),
            ("http://menuxy.alvesprotect.app.br", False, "http no lugar de https é recusado"),
            ("https://loja.example.evil.com", False, "subdomínio parecido é recusado"),
            ("https://menuxy.alvesprotect.app.br.evil.com", False, "sufixo colado é recusado"),
            ("https://evil.com", False, "site qualquer é recusado"),
        ]
        for origem, deve_passar, descricao in casos:
            codigo, _ = chamar("/imprimir", corpo={"texto": "x", "impressora": FANTASMA},
                               origem=origem)
            # Passar pela trava de origem = chegar na resolução, que devolve 404
            # porque a impressora é fantasma. Barrado = 403.
            passou = codigo != 403
            conferir(descricao, passou == deve_passar, f"HTTP {codigo}")

        codigo, _ = chamar("/imprimir", corpo={"texto": "x", "impressora": FANTASMA})
        conferir("chamada sem Origin (curl, script local) não é barrada", codigo != 403)
    finally:
        Ponte.cfg["origens_permitidas"] = original


def bloco_limite():
    print("\n[10] Teto por minuto")
    from ponte_menuxy.servidor import Limitador, Ponte
    anterior = Ponte.limitador
    Ponte.limitador = Limitador(5)
    try:
        codigos = [chamar("/imprimir", corpo={"texto": "x", "impressora": FANTASMA})[0]
                   for _ in range(9)]
        conferir("as primeiras chamadas passam do limitador",
                 codigos[:5].count(404) == 5, str(codigos))
        conferir("acima do teto responde 429", 429 in codigos, str(codigos))
        conferir("o teto para de verdade (últimas todas 429)",
                 all(c == 429 for c in codigos[5:]), str(codigos))
    finally:
        Ponte.limitador = anterior


def bloco_seguranca():
    print("\n[11] Superfície de ataque")
    import socket
    externo = socket.socket()
    externo.settimeout(2)
    # A ponte escuta só em 127.0.0.1. Conectar pelo IP da máquina na LAN tem
    # que falhar — e não por firewall: o socket não existe fora do loopback.
    try:
        endereco = socket.gethostbyname(socket.gethostname())
        if endereco.startswith("127."):
            print("  [i]    esta máquina só resolve para loopback: teste de LAN pulado")
        else:
            try:
                externo.connect((endereco, PORTA))
                alcancavel = True
            except OSError:
                alcancavel = False
            conferir("a porta NÃO é alcançável pelo IP da rede local", not alcancavel)
    except Exception:
        print("  [i]    não foi possível descobrir o IP da máquina: teste pulado")
    finally:
        externo.close()

    codigo, dados = chamar("/status")
    texto = json.dumps(dados).lower()
    for proibido in ("senha", "password", "token", "cpf", "pedido", "valor", "cliente"):
        conferir(f"/status não expõe dado de negócio ('{proibido}')", proibido not in texto)


def bloco_com_papel(alvo: str, cfg):
    print(f"\n[extra] Impressão real em {alvo} — UM cupom")
    codigo, dados = chamar("/imprimir", corpo={
        "texto": escpos.cupom_de_teste(int(cfg["colunas"]), VERSAO, "verificador"),
        "impressora": alvo, "cortar": True})
    conferir("o cupom foi aceito pela impressora", codigo == 200 and dados.get("ok") is True,
             json.dumps(dados, ensure_ascii=False))


# =========================================================================== #

def main() -> int:
    parser = argparse.ArgumentParser(description="Verificador da ponte de impressão.")
    parser.add_argument("--com-papel", metavar="ID",
                        help="imprime UM cupom de verdade na impressora informada")
    args = parser.parse_args()

    cfg = config.carregar()
    cfg["porta"] = PORTA
    cfg["origens_permitidas"] = ["*"]
    cfg["limite_por_minuto"] = 600      # o bloco do teto ajusta o seu próprio

    print("=" * 66)
    print(f"  Verificador da Ponte de Impressão v{VERSAO}")
    print(f"  porta de teste: {PORTA}   |   impressora alvo: fantasma (não gasta papel)")
    print("=" * 66)

    instancia = servidor.criar(cfg)
    threading.Thread(target=instancia.serve_forever, daemon=True).start()
    time.sleep(0.4)

    try:
        bloco_escpos()
        bloco_config()
        bloco_backends()
        bloco_resolucao(cfg)
        bloco_rotas()
        bloco_cabecalhos()
        bloco_entrada()
        bloco_impressora_inexistente()
        bloco_origens(cfg)
        bloco_limite()
        bloco_seguranca()
        if args.com_papel:
            bloco_com_papel(args.com_papel, cfg)
    finally:
        instancia.shutdown()
        instancia.server_close()

    print("\n" + "=" * 66)
    total = _passou + _falhou
    print(f"  {_passou} de {total} verificações passaram")
    if _falhou:
        print(f"  {_falhou} falharam:")
        for descricao in _falhas:
            print(f"    - {descricao}")
    else:
        print("  nenhuma falha. Nenhum papel gasto.")
    print("=" * 66)
    return 1 if _falhou else 0


if __name__ == "__main__":
    sys.exit(main())
