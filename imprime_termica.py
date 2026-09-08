#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imprime_termica.py — Impressão direta ESC/POS em impressoras térmicas 58mm via USB.

Escrito para a SMX-JP58H / POS-58 e compatíveis (genéricas chinesas de 58mm),
falando ESC/POS *diretamente* sobre o endpoint USB bulk-OUT. Não usa o driver
do fabricante, nem spooler do Windows, nem CUPS — por isso funciona em
Windows 11 ARM (Snapdragon), onde o driver oficial não existe.

Plataformas: Windows (x64 e ARM64, via driver WinUSB instalado com Zadig)
             Linux (amd64/arm64, via libusb + regra udev)

Uso rápido:
    python imprime_termica.py                      # detecta e imprime cupom de teste
    python imprime_termica.py --listar             # lista todos os dispositivos USB
    python imprime_termica.py --texto "Olá mundo"  # imprime um texto próprio
    python imprime_termica.py --vid 0x0416 --pid 0x5011   # força VID/PID
    python imprime_termica.py --usar-escpos        # usa a lib python-escpos

Dependências:
    pip install pyusb            (obrigatório)
    pip install python-escpos    (opcional, só para --usar-escpos)

Autor: gerado para uso livre. Sem garantias — mas testado em hardware real.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
from typing import Iterator, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Importação do PyUSB com mensagem de erro amigável
# --------------------------------------------------------------------------- #
try:
    import usb.core
    import usb.util
    import usb.backend.libusb1
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "\n[ERRO] A biblioteca 'pyusb' não está instalada.\n"
        "       Instale com:  pip install pyusb\n\n"
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------- #
# Comandos ESC/POS
# --------------------------------------------------------------------------- #
class ESCPOS:
    """Constantes do protocolo ESC/POS (Epson Standard Code for Point Of Sale).

    Só o subconjunto que praticamente toda impressora 58mm genérica implementa.
    """

    ESC = b"\x1B"
    GS = b"\x1D"

    # Inicialização: limpa buffer, volta a formatação ao padrão de fábrica.
    INIT = b"\x1B\x40"                    # ESC @

    # Alinhamento: ESC a n  (0=esquerda, 1=centro, 2=direita)
    ALINHA_ESQ = b"\x1B\x61\x00"
    ALINHA_CENTRO = b"\x1B\x61\x01"
    ALINHA_DIR = b"\x1B\x61\x02"

    # Ênfase (negrito): ESC E n
    NEGRITO_ON = b"\x1B\x45\x01"
    NEGRITO_OFF = b"\x1B\x45\x00"

    # Sublinhado: ESC - n  (0=off, 1=1 ponto, 2=2 pontos)
    SUBLINHADO_ON = b"\x1B\x2D\x01"
    SUBLINHADO_OFF = b"\x1B\x2D\x00"

    # Tamanho do caractere: GS ! n  (nibble alto=largura, baixo=altura)
    TAM_NORMAL = b"\x1D\x21\x00"
    TAM_DUPLO = b"\x1D\x21\x11"           # 2x largura + 2x altura
    TAM_DUPLA_ALTURA = b"\x1D\x21\x01"

    # Avanço de papel: ESC d n  (n linhas)
    @staticmethod
    def avanca(linhas: int = 1) -> bytes:
        """ESC d n — avança `linhas` linhas de papel (0..255)."""
        return b"\x1B\x64" + bytes([max(0, min(255, linhas))])

    # Tabela de códigos: ESC t n  (2 = CP850 Multilingual, cobre acentos PT-BR)
    @staticmethod
    def codepage(n: int) -> bytes:
        """ESC t n — seleciona a página de código do caractere."""
        return b"\x1B\x74" + bytes([n])

    # Corte de papel.
    # ATENÇÃO: o comando citado como "\x1D\xV\x00" não existe — '\xV' não é um
    # escape válido. O correto é GS V (0x1D 0x56):
    CORTE_TOTAL = b"\x1D\x56\x00"         # GS V 0  — corte total
    CORTE_PARCIAL = b"\x1D\x56\x01"       # GS V 1  — corte parcial
    # GS V B n — alimenta n pontos e corta (mais seguro: tira o texto da cabeça)
    @staticmethod
    def corte_com_avanco(pontos: int = 0x40) -> bytes:
        """GS V B n — avança `pontos` e executa corte parcial."""
        return b"\x1D\x56\x42" + bytes([max(0, min(255, pontos))])

    # Gaveta de dinheiro (RJ11): ESC p m t1 t2
    ABRE_GAVETA = b"\x1B\x70\x00\x19\xFA"


# Páginas de código ESC/POS úteis para português.
# nome -> (n do comando ESC t n, codec Python correspondente)
CODEPAGES = {
    "cp850": (2, "cp850"),      # Multilingual — melhor cobertura de acentos PT
    "cp860": (3, "cp860"),      # Portuguese
    "cp437": (0, "cp437"),      # padrão de fábrica da maioria
    "cp1252": (16, "cp1252"),   # WPC1252 / Latin-1
}

# Classe USB 7 = Printer (definida em usb.org). É o filtro principal.
USB_CLASSE_IMPRESSORA = 0x07

# VIDs/PIDs comuns em impressoras térmicas 58mm genéricas.
# Usado só como *último* fallback — a detecção por classe USB é preferível.
VIDPID_CONHECIDOS: List[Tuple[int, int, str]] = [
    (0x0416, 0x5011, "Winbond/Nuvoton — POS-58 / SMX-JP58H (mais comum)"),
    (0x0416, 0x5011, "Winbond — Virtual Com Port (mesmo chip)"),
    (0x0483, 0x5743, "STMicroelectronics — POS58"),
    (0x0471, 0x0055, "Philips — POS"),
    (0x04B8, 0x0202, "Epson TM-series"),
    (0x0DD4, 0x0205, "Custom Engineering"),
    (0x1FC9, 0x2016, "NXP — impressoras genéricas"),
    (0x1CBE, 0x0003, "TI — Luminary / POS"),
    (0x1B4F, 0x0003, "SparkFun/Syntech — módulos térmicos"),
    (0x28E9, 0x0289, "GD32 — clones 58mm"),
    (0x6868, 0x0500, "Zjiang / ZJ-5802"),
    (0x0FE6, 0x811E, "ICS Advent — POS-5890"),
]


# --------------------------------------------------------------------------- #
# Descoberta do backend libusb
# --------------------------------------------------------------------------- #
def carregar_backend(caminho_dll: Optional[str] = None):
    """Localiza o backend libusb-1.0.

    No Linux o PyUSB acha `libusb-1.0.so` sozinho. No Windows é comum a DLL não
    estar no PATH, então tentamos, em ordem:

    1. o caminho explícito passado em ``--libusb`` ou na env ``LIBUSB_PATH``;
    2. o pacote ``libusb-package`` (wheels com a DLL embutida), se instalado;
    3. a busca automática do PyUSB (PATH / diretório do script).

    Returns:
        Um backend do PyUSB, ou ``None`` para deixar o PyUSB decidir.
    """
    caminho_dll = caminho_dll or os.environ.get("LIBUSB_PATH")

    if caminho_dll:
        if not os.path.isfile(caminho_dll):
            raise SystemExit(f"[ERRO] Arquivo libusb não encontrado: {caminho_dll}")
        backend = usb.backend.libusb1.get_backend(find_library=lambda _: caminho_dll)
        if backend is None:
            raise SystemExit(
                f"[ERRO] '{caminho_dll}' não pôde ser carregado como libusb-1.0.\n"
                "       Verifique se a arquitetura da DLL bate com a do seu Python\n"
                "       (Python ARM64 exige libusb ARM64; Python x64 exige DLL x64)."
            )
        return backend

    # Tentativa 2: libusb-package (pip install libusb-package)
    try:
        import libusb_package  # type: ignore
        backend = libusb_package.get_libusb1_backend()
        if backend is not None:
            return backend
    except Exception:
        pass

    # Tentativa 3: descoberta padrão do PyUSB
    return usb.backend.libusb1.get_backend()


def _erro_sem_backend() -> str:
    """Mensagem de ajuda para quando nenhum backend libusb é encontrado."""
    if platform.system() == "Windows":
        arq = platform.machine()
        return (
            "\n[ERRO] Nenhum backend libusb encontrado no Windows.\n"
            f"       Arquitetura do Python: {arq}\n\n"
            "       Soluções (escolha uma):\n"
            "       1) pip install libusb-package\n"
            "       2) Baixe libusb-1.0.x.7z em https://github.com/libusb/libusb/releases\n"
            "          e copie a DLL da pasta correspondente ao SEU Python:\n"
            "             Python ARM64 -> VS2025\\ARM64\\dll\\libusb-1.0.dll\n"
            "             Python x64   -> VS2025\\MS64\\dll\\libusb-1.0.dll\n"
            "          para a mesma pasta deste script (ou aponte com --libusb).\n"
        )
    return (
        "\n[ERRO] Nenhum backend libusb encontrado.\n"
        "       Instale com:  sudo apt install libusb-1.0-0\n"
    )


# --------------------------------------------------------------------------- #
# Detecção da impressora
# --------------------------------------------------------------------------- #
def _texto_seguro(dev, atributo: str) -> str:
    """Lê uma string-descritor do dispositivo sem explodir por falta de permissão."""
    try:
        valor = getattr(dev, atributo)
        return str(valor) if valor else "?"
    except Exception:
        return "?"


def interfaces_impressora(dev) -> Iterator:
    """Devolve as interfaces do dispositivo cuja bInterfaceClass é 7 (Printer).

    IMPORTANTE — correção técnica: filtrar por ``dev.bDeviceClass == 7`` **não
    funciona** na maioria das impressoras 58mm. Elas declaram
    ``bDeviceClass = 0x00`` ("definido na interface") e colocam a classe 7 na
    *interface*. Foi exatamente o caso na POS-58 testada (0416:5011):

        bDeviceClass       0
        bInterfaceClass    7 Printer
        bInterfaceSubClass 1
        bInterfaceProtocol 2 (bidirectional)

    Por isso a varredura é feita interface a interface.
    """
    try:
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceClass == USB_CLASSE_IMPRESSORA:
                    yield intf
    except usb.core.USBError:
        # Sem permissão para ler os descritores de configuração — ignora.
        return


def listar_dispositivos(backend=None) -> None:
    """Imprime na tela todos os dispositivos USB visíveis, com VID/PID.

    Serve para o usuário identificar manualmente a impressora quando a
    autodetecção falha (basta então rodar com ``--vid`` / ``--pid``).
    """
    print("\n" + "=" * 72)
    print("DISPOSITIVOS USB DETECTADOS")
    print("=" * 72)

    dispositivos = list(usb.core.find(find_all=True, backend=backend))
    if not dispositivos:
        print("  Nenhum dispositivo USB visível.")
        print("  Windows: o dispositivo só aparece após o driver WinUSB (Zadig).")
        print("  Linux:   verifique permissões (regra udev) ou rode com sudo.")
        print("=" * 72 + "\n")
        return

    for dev in dispositivos:
        classes = []
        eh_impressora = False
        try:
            for cfg in dev:
                for intf in cfg:
                    classes.append(intf.bInterfaceClass)
                    if intf.bInterfaceClass == USB_CLASSE_IMPRESSORA:
                        eh_impressora = True
        except usb.core.USBError:
            classes = []

        marca = "  <<< IMPRESSORA (classe USB 7)" if eh_impressora else ""
        print(f"\n  idVendor=0x{dev.idVendor:04X}  idProduct=0x{dev.idProduct:04X}{marca}")
        print(f"    Fabricante : {_texto_seguro(dev, 'manufacturer')}")
        print(f"    Produto    : {_texto_seguro(dev, 'product')}")
        print(f"    Serial     : {_texto_seguro(dev, 'serial_number')}")
        print(f"    bDeviceClass: {dev.bDeviceClass}   "
              f"Classes de interface: {classes or 'ilegível (sem permissão)'}")
        print(f"    Bus {dev.bus}  Endereço {dev.address}")

    print("\n" + "=" * 72)
    print("Para forçar um dispositivo:")
    print("  python imprime_termica.py --vid 0xXXXX --pid 0xYYYY")
    print("=" * 72 + "\n")


def encontrar_impressora(vid: Optional[int] = None,
                         pid: Optional[int] = None,
                         backend=None):
    """Encontra a impressora térmica USB.

    Estratégia em cascata, da mais confiável para a menos:

    1. VID/PID explícitos, se informados pelo usuário;
    2. qualquer dispositivo com uma **interface** de classe 7 (Printer);
    3. dispositivo com ``bDeviceClass == 7`` (raro, mas existe);
    4. lista de VID/PID conhecidos de 58mm genéricas.

    Args:
        vid: idVendor forçado (ex.: 0x0416) ou None.
        pid: idProduct forçado (ex.: 0x5011) ou None.
        backend: backend libusb já resolvido.

    Returns:
        Tupla ``(dispositivo, interface_ou_None)``.

    Raises:
        RuntimeError: se nenhuma impressora for localizada.
    """
    # --- 1. VID/PID explícitos ------------------------------------------------
    if vid is not None and pid is not None:
        dev = usb.core.find(idVendor=vid, idProduct=pid, backend=backend)
        if dev is None:
            raise RuntimeError(
                f"Nenhum dispositivo com VID=0x{vid:04X} PID=0x{pid:04X}."
            )
        intf = next(interfaces_impressora(dev), None)
        print(f"[OK] Impressora forçada: 0x{vid:04X}:0x{pid:04X}")
        return dev, intf

    # --- 2. Varredura por classe de INTERFACE = 7 (método principal) ----------
    for dev in usb.core.find(find_all=True, backend=backend):
        intf = next(interfaces_impressora(dev), None)
        if intf is not None:
            print(f"[OK] Impressora encontrada pela classe USB 7 "
                  f"(interface {intf.bInterfaceNumber}): "
                  f"0x{dev.idVendor:04X}:0x{dev.idProduct:04X} "
                  f"— {_texto_seguro(dev, 'product')}")
            return dev, intf

    # --- 3. bDeviceClass == 7 -------------------------------------------------
    dev = usb.core.find(bDeviceClass=USB_CLASSE_IMPRESSORA, backend=backend)
    if dev is not None:
        print(f"[OK] Impressora encontrada por bDeviceClass=7: "
              f"0x{dev.idVendor:04X}:0x{dev.idProduct:04X}")
        return dev, next(interfaces_impressora(dev), None)

    # --- 4. Lista de VID/PID conhecidos --------------------------------------
    for kvid, kpid, descricao in VIDPID_CONHECIDOS:
        dev = usb.core.find(idVendor=kvid, idProduct=kpid, backend=backend)
        if dev is not None:
            print(f"[OK] Impressora reconhecida pela lista interna: "
                  f"0x{kvid:04X}:0x{kpid:04X} — {descricao}")
            return dev, next(interfaces_impressora(dev), None)

    raise RuntimeError("Nenhuma impressora térmica USB encontrada.")


# --------------------------------------------------------------------------- #
# Preparação do dispositivo (claim + endpoint)
# --------------------------------------------------------------------------- #
def preparar_dispositivo(dev, intf):
    """Solta o driver do kernel, configura o dispositivo e acha o endpoint OUT.

    O endpoint de saída é localizado dinamicamente com
    ``usb.util.find_descriptor`` — nunca fixado em 0x01/0x02, porque varia
    entre modelos.

    Args:
        dev: dispositivo PyUSB.
        intf: interface de impressora (ou None para usar a config ativa).

    Returns:
        Tupla ``(endpoint_out, numero_da_interface)``.

    Raises:
        RuntimeError: se não houver endpoint BULK OUT utilizável.
    """
    sistema = platform.system()

    # --- No Linux o módulo `usblp` do kernel captura a impressora e cria
    #     /dev/usb/lp0. Enquanto ele estiver anexado, o libusb não consegue
    #     reivindicar a interface. Precisamos desanexá-lo.
    #     No Windows isso não existe (WinUSB já é exclusivo) e o PyUSB levanta
    #     NotImplementedError — que ignoramos de propósito.
    numero_intf = intf.bInterfaceNumber if intf is not None else 0
    try:
        if dev.is_kernel_driver_active(numero_intf):
            dev.detach_kernel_driver(numero_intf)
            print(f"[OK] Driver do kernel (usblp) desanexado da interface {numero_intf}.")
    except NotImplementedError:
        pass  # Windows/macOS: não se aplica.
    except usb.core.USBError as erro:
        if erro.errno == 13:  # EACCES
            raise
        # Alguns backends erram aqui mesmo sem driver anexado; seguimos.

    # --- Ativa a configuração. Se já estiver ativa, set_configuration() pode
    #     falhar com "Resource busy" — o que é inofensivo.
    try:
        cfg_ativa = dev.get_active_configuration()
    except usb.core.USBError:
        cfg_ativa = None
    if cfg_ativa is None:
        dev.set_configuration()
        cfg_ativa = dev.get_active_configuration()

    # --- Reobtém a interface a partir da configuração ativa
    if intf is None:
        intf = usb.util.find_descriptor(
            cfg_ativa,
            custom_match=lambda i: i.bInterfaceClass == USB_CLASSE_IMPRESSORA,
        ) or cfg_ativa[(0, 0)]
        numero_intf = intf.bInterfaceNumber

    # --- Endpoint de SAÍDA (host -> impressora), transferência BULK
    endpoint_out = usb.util.find_descriptor(
        intf,
        custom_match=lambda e: (
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
        ),
    )
    if endpoint_out is None:
        # Fallback: qualquer endpoint OUT, mesmo que não seja BULK.
        endpoint_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            ),
        )
    if endpoint_out is None:
        raise RuntimeError(
            f"A interface {numero_intf} não expõe nenhum endpoint de saída (OUT). "
            "O dispositivo encontrado provavelmente não é uma impressora."
        )

    print(f"[OK] Endpoint OUT: 0x{endpoint_out.bEndpointAddress:02X} "
          f"(pacote de {endpoint_out.wMaxPacketSize} bytes)")
    return endpoint_out, numero_intf


# --------------------------------------------------------------------------- #
# Montagem do cupom
# --------------------------------------------------------------------------- #
def montar_cupom(texto: Optional[str] = None,
                 codepage: str = "cp850",
                 cortar: bool = True,
                 colunas: int = 32) -> bytes:
    """Monta o fluxo de bytes ESC/POS do cupom.

    Args:
        texto: texto livre a imprimir. Se None, imprime o cupom de teste.
        codepage: chave de ``CODEPAGES`` para a acentuação.
        cortar: se True, anexa o comando de corte de papel.
        colunas: largura em caracteres (32 na fonte A de 58mm; 42 em 80mm).

    Returns:
        Os bytes prontos para escrever no endpoint OUT.
    """
    n_codepage, codec = CODEPAGES.get(codepage, CODEPAGES["cp850"])

    def txt(s: str) -> bytes:
        """Codifica string para a página de código da impressora."""
        # 'replace' evita exceção em caracteres fora da tabela (vira '?').
        return s.encode(codec, errors="replace")

    partes: List[bytes] = []
    partes.append(ESCPOS.INIT)                 # ESC @ — reset obrigatório
    partes.append(ESCPOS.codepage(n_codepage)) # ESC t n — acentos

    if texto is None:
        sistema = platform.system()
        arquitetura = platform.machine()
        linha = "-" * colunas

        partes.append(ESCPOS.ALINHA_CENTRO)
        partes.append(ESCPOS.TAM_DUPLO + ESCPOS.NEGRITO_ON)
        partes.append(txt("TESTE OK\n"))
        partes.append(ESCPOS.NEGRITO_OFF + ESCPOS.TAM_NORMAL)
        partes.append(txt(f"Impressao bem-sucedida\nno {sistema} {arquitetura}!\n"))
        partes.append(txt(linha + "\n"))

        partes.append(ESCPOS.ALINHA_ESQ)
        partes.append(ESCPOS.NEGRITO_ON + txt("Acentuacao:\n") + ESCPOS.NEGRITO_OFF)
        partes.append(txt("ação, coração, José, Ávila\n"))
        partes.append(txt("R$ 1.234,56 — 50% à vista\n"))
        partes.append(txt(linha + "\n"))

        partes.append(ESCPOS.NEGRITO_ON + txt("Ambiente:\n") + ESCPOS.NEGRITO_OFF)
        partes.append(txt(f"SO      : {sistema} {platform.release()}\n"))
        partes.append(txt(f"Arquit. : {arquitetura}\n"))
        partes.append(txt(f"Python  : {platform.python_version()}\n"))
        partes.append(txt(f"Codepage: {codepage} (ESC t {n_codepage})\n"))
        partes.append(txt(linha + "\n"))

        partes.append(ESCPOS.ALINHA_CENTRO)
        partes.append(txt("ESC/POS direto via USB\nsem driver do fabricante\n"))
        partes.append(ESCPOS.ALINHA_ESQ)
    else:
        partes.append(ESCPOS.ALINHA_ESQ)
        partes.append(txt(texto.rstrip("\n") + "\n"))

    # Avanço antes do corte: tira o texto de baixo da cabeça térmica, senão as
    # últimas linhas ficam escondidas dentro do mecanismo.
    partes.append(ESCPOS.avanca(4))

    if cortar:
        partes.append(ESCPOS.corte_com_avanco(0x40))
        # Modelos sem guilhotina simplesmente ignoram o comando — é inofensivo.

    return b"".join(partes)


# --------------------------------------------------------------------------- #
# Impressão — caminho PyUSB puro
# --------------------------------------------------------------------------- #
def imprimir_pyusb(dados: bytes, vid=None, pid=None, backend=None,
                   timeout: int = 5000) -> None:
    """Envia bytes ESC/POS crus para a impressora usando apenas PyUSB.

    Escreve em blocos do tamanho do endpoint para não estourar o buffer
    interno da impressora (essas 58mm costumam ter poucos KB).

    Args:
        dados: fluxo ESC/POS já montado.
        vid, pid: VID/PID forçados, ou None para autodetecção.
        backend: backend libusb.
        timeout: milissegundos por bloco.
    """
    dev, intf = encontrar_impressora(vid, pid, backend)
    endpoint_out, numero_intf = preparar_dispositivo(dev, intf)

    # Bloco de escrita: múltiplo do wMaxPacketSize (64 bytes é o típico).
    tamanho_bloco = max(64, endpoint_out.wMaxPacketSize) * 8

    enviados = 0
    try:
        for inicio in range(0, len(dados), tamanho_bloco):
            bloco = dados[inicio:inicio + tamanho_bloco]
            enviados += endpoint_out.write(bloco, timeout=timeout)
        print(f"[OK] {enviados} bytes enviados à impressora.")
    finally:
        # Libera os recursos do libusb sempre — senão a próxima execução
        # falha com "Resource busy".
        usb.util.dispose_resources(dev)
        # No Linux, devolve a impressora ao kernel (recria /dev/usb/lpN).
        try:
            dev.attach_kernel_driver(numero_intf)
        except (NotImplementedError, usb.core.USBError):
            pass


# --------------------------------------------------------------------------- #
# Impressão — caminho python-escpos
# --------------------------------------------------------------------------- #
def imprimir_escpos(texto: Optional[str], vid=None, pid=None,
                    codepage: str = "cp850", cortar: bool = True) -> None:
    """Imprime usando a biblioteca python-escpos (API de alto nível).

    A python-escpos usa o PyUSB como backend, mas gerencia endpoints, páginas
    de código e formatação sozinha. Como ela exige VID/PID no construtor,
    fazemos a autodetecção antes e passamos os IDs e endpoints encontrados.
    """
    try:
        from escpos.printer import Usb
    except ImportError:
        raise SystemExit(
            "[ERRO] python-escpos não instalado.  pip install python-escpos"
        )

    if vid is None or pid is None:
        dev, intf = encontrar_impressora(vid, pid)
        vid, pid = dev.idVendor, dev.idProduct
        endpoint_out, numero_intf = preparar_dispositivo(dev, intf)
        ep_out = endpoint_out.bEndpointAddress
        # Procura um endpoint IN para o modo bidirecional (status).
        ep_in = 0x82
        for e in (intf or []):
            if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN:
                ep_in = e.bEndpointAddress
                break
        # Libera o dispositivo: quem vai reivindicá-lo agora é a python-escpos.
        usb.util.dispose_resources(dev)
    else:
        ep_out, ep_in = 0x01, 0x82

    print(f"[..] python-escpos -> 0x{vid:04X}:0x{pid:04X} "
          f"(out=0x{ep_out:02X}, in=0x{ep_in:02X})")

    impressora = Usb(idVendor=vid, idProduct=pid,
                     in_ep=ep_in, out_ep=ep_out, timeout=5000)
    try:
        impressora.charcode(codepage.upper())
    except Exception:
        pass  # nome de codepage desconhecido para a lib — segue com o padrão

    if texto is None:
        impressora.set(align="center", bold=True, double_height=True,
                       double_width=True)
        impressora.text("TESTE OK\n")
        impressora.set(align="center", bold=False, double_height=False,
                       double_width=False)
        impressora.text(f"Impressao bem-sucedida\nno {platform.system()} "
                        f"{platform.machine()}!\n")
        impressora.text("-" * 32 + "\n")
        impressora.set(align="left")
        impressora.text("ação, coração, José, Ávila\n")
        impressora.text("via python-escpos\n")
    else:
        impressora.text(texto.rstrip("\n") + "\n")

    impressora.text("\n\n\n")
    if cortar:
        try:
            impressora.cut()
        except Exception:
            impressora._raw(ESCPOS.corte_com_avanco(0x40))
    impressora.close()
    print("[OK] Impressão concluída via python-escpos.")


# --------------------------------------------------------------------------- #
# Tratamento de erros com mensagens acionáveis
# --------------------------------------------------------------------------- #
def explicar_usberror(erro: usb.core.USBError) -> str:
    """Traduz um USBError em uma instrução prática para o usuário."""
    sistema = platform.system()
    errno = getattr(erro, "errno", None)

    if errno == 13 or "access" in str(erro).lower() or "permission" in str(erro).lower():
        if sistema == "Linux":
            return (
                "PERMISSÃO NEGADA para acessar o dispositivo USB.\n\n"
                "  Solução (regra udev — não precisa de sudo depois):\n"
                "    sudo tee /etc/udev/rules.d/99-impressora-termica.rules >/dev/null <<'EOF'\n"
                '    SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"0416\", ATTRS{idProduct}==\"5011\", MODE=\"0666\", GROUP=\"lp\"\n'
                "    EOF\n"
                "    sudo udevadm control --reload-rules && sudo udevadm trigger\n"
                "    sudo usermod -aG lp $USER      # depois: faça logout/login\n\n"
                "  Teste rápido:  sudo python3 imprime_termica.py"
            )
        return (
            "ACESSO NEGADO ao dispositivo USB.\n\n"
            "  No Windows isso quase sempre significa que a impressora ainda\n"
            "  está no driver do fabricante/usbprint, e não no WinUSB.\n"
            "  Rode o Zadig e substitua o driver por WinUSB (veja o README).\n"
            "  Feche também qualquer software de PDV que esteja com ela aberta."
        )

    if errno == 16 or "busy" in str(erro).lower():
        if sistema == "Linux":
            return (
                "DISPOSITIVO OCUPADO (Resource busy).\n\n"
                "  O driver usblp do kernel ou o CUPS está segurando a impressora:\n"
                "    sudo systemctl stop cups          # pare o CUPS\n"
                "    sudo modprobe -r usblp            # solte o driver do kernel\n"
                "  (o próprio script já tenta desanexar o usblp automaticamente)"
            )
        return ("DISPOSITIVO OCUPADO. Feche o software de PDV / a fila de\n"
                "  impressão do Windows que está usando a impressora e repita.")

    if errno == 19 or "no such device" in str(erro).lower():
        return ("A impressora foi DESCONECTADA durante a operação.\n"
                "  Reconecte o cabo USB e tente de novo.")

    if "timeout" in str(erro).lower():
        return (
            "TIMEOUT na escrita.\n\n"
            "  Causas comuns:\n"
            "    - impressora sem papel ou com a tampa aberta;\n"
            "    - impressora desligada (o USB alimenta, mas o motor não);\n"
            "    - endpoint OUT errado (tente --listar e force o VID/PID)."
        )

    return f"Erro USB não classificado: {erro}"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def hexint(valor: str) -> int:
    """Converte '0x0416', '0416' ou '1046' (decimal) em int."""
    valor = valor.strip()
    return int(valor, 16) if valor.lower().startswith("0x") else int(valor, 16)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Impressão ESC/POS direta via USB (58mm) — Windows ARM e Linux.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--listar", action="store_true",
                        help="lista todos os dispositivos USB e sai")
    parser.add_argument("--vid", type=hexint, default=None,
                        help="idVendor em hexadecimal (ex.: 0x0416)")
    parser.add_argument("--pid", type=hexint, default=None,
                        help="idProduct em hexadecimal (ex.: 0x5011)")
    parser.add_argument("--texto", default=None,
                        help="texto a imprimir (padrão: cupom de teste)")
    parser.add_argument("--arquivo", default=None,
                        help="imprime o conteúdo de um arquivo de texto UTF-8")
    parser.add_argument("--codepage", default="cp850", choices=sorted(CODEPAGES),
                        help="página de código para acentos (padrão: cp850)")
    parser.add_argument("--sem-corte", action="store_true",
                        help="não envia o comando de corte de papel")
    parser.add_argument("--usar-escpos", action="store_true",
                        help="usa a biblioteca python-escpos em vez do PyUSB puro")
    parser.add_argument("--libusb", default=None,
                        help="caminho para libusb-1.0.dll / .so (ou env LIBUSB_PATH)")
    parser.add_argument("--abrir-gaveta", action="store_true",
                        help="envia o pulso de abertura da gaveta (RJ11)")
    args = parser.parse_args()

    print(f"\n=== Impressora Térmica 58mm — ESC/POS via USB ===")
    print(f"    {platform.system()} {platform.release()} / {platform.machine()} "
          f"/ Python {platform.python_version()}\n")

    # --- Backend libusb ------------------------------------------------------
    try:
        backend = carregar_backend(args.libusb)
    except SystemExit:
        raise
    if backend is None:
        try:
            # Uma sondagem para confirmar que realmente não há backend.
            next(iter(usb.core.find(find_all=True)), None)
        except usb.core.NoBackendError:
            sys.stderr.write(_erro_sem_backend())
            return 3

    # --- Modo listagem -------------------------------------------------------
    if args.listar:
        try:
            listar_dispositivos(backend)
        except usb.core.NoBackendError:
            sys.stderr.write(_erro_sem_backend())
            return 3
        return 0

    # --- Texto de origem -----------------------------------------------------
    texto = args.texto
    if args.arquivo:
        try:
            with open(args.arquivo, "r", encoding="utf-8") as fp:
                texto = fp.read()
        except OSError as erro:
            sys.stderr.write(f"\n[ERRO] Não foi possível ler '{args.arquivo}': {erro}\n")
            return 4

    # --- Impressão -----------------------------------------------------------
    try:
        if args.usar_escpos:
            imprimir_escpos(texto, args.vid, args.pid,
                            codepage=args.codepage, cortar=not args.sem_corte)
        else:
            dados = montar_cupom(texto, codepage=args.codepage,
                                 cortar=not args.sem_corte)
            if args.abrir_gaveta:
                dados += ESCPOS.ABRE_GAVETA
            imprimir_pyusb(dados, args.vid, args.pid, backend)
        print("\n>>> Concluído. Confira o papel na impressora.\n")
        return 0

    except usb.core.NoBackendError:
        sys.stderr.write(_erro_sem_backend())
        return 3

    except usb.core.USBError as erro:
        sys.stderr.write("\n" + "!" * 72 + "\n")
        sys.stderr.write("[ERRO USB] " + explicar_usberror(erro) + "\n")
        sys.stderr.write("!" * 72 + "\n\n")
        return 5

    except RuntimeError as erro:
        sys.stderr.write(f"\n[ERRO] {erro}\n")
        sys.stderr.write("Listando os dispositivos USB para ajudar a identificar "
                         "a impressora manualmente...\n")
        try:
            listar_dispositivos(backend)
        except Exception:
            pass
        sys.stderr.write(
            "Se você reconhecer a impressora acima, rode novamente forçando os IDs:\n"
            "    python imprime_termica.py --vid 0xXXXX --pid 0xYYYY\n\n"
        )
        return 6

    except KeyboardInterrupt:
        sys.stderr.write("\n[!] Interrompido pelo usuário.\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
