#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autoteste.py — Diagnóstico e bateria de testes do projeto da impressora 58mm.

Roda com ou sem a impressora conectada:
  - sem hardware: valida toda a lógica (comandos ESC/POS, montagem do cupom,
    tratamento de erros) e diagnostica o ambiente;
  - com hardware: soma os testes de comunicação real e a impressão.

Uso:
    python autoteste.py              # tudo, menos imprimir de verdade
    python autoteste.py --imprimir   # inclui a impressão física
"""

from __future__ import annotations

import os
import platform
import sys
import traceback

TOTAL = 0
PASSOU = 0
FALHOU = 0
PULOU = 0


def secao(titulo: str) -> None:
    print()
    print("=" * 74)
    print(f"  {titulo}")
    print("=" * 74)


def checa(descricao: str, condicao, detalhe: str = "") -> bool:
    """Registra o resultado de uma verificação."""
    global TOTAL, PASSOU, FALHOU
    TOTAL += 1
    if condicao:
        PASSOU += 1
        print(f"  [ OK ] {descricao}")
        if detalhe:
            print(f"         {detalhe}")
        return True
    FALHOU += 1
    print(f"  [FALHA] {descricao}")
    if detalhe:
        print(f"         {detalhe}")
    return False


def pula(descricao: str, motivo: str) -> None:
    global TOTAL, PULOU
    TOTAL += 1
    PULOU += 1
    print(f"  [PULA] {descricao}")
    print(f"         motivo: {motivo}")


def hexdump(dados: bytes, limite: int = 48) -> str:
    """Representação hex legível de um trecho de bytes."""
    trecho = dados[:limite]
    saida = " ".join(f"{b:02X}" for b in trecho)
    return saida + (" ..." if len(dados) > limite else "")


# ===========================================================================
def main() -> int:
    imprimir_de_verdade = "--imprimir" in sys.argv

    print()
    print("#" * 74)
    print("#  AUTOTESTE - IMPRESSORA TERMICA 58mm (ESC/POS via USB)")
    print("#" * 74)

    # -------------------------------------------------------------- AMBIENTE
    secao("1. AMBIENTE")
    print(f"  Sistema      : {platform.system()} {platform.release()}")
    print(f"  Arquitetura  : {platform.machine()}")
    print(f"  Python       : {platform.python_version()}")
    print(f"  Executavel   : {sys.executable}")
    print(f"  Diretorio    : {os.getcwd()}")
    print()

    checa("Python >= 3.8", sys.version_info >= (3, 8),
          f"versao detectada: {platform.python_version()}")

    if platform.system() == "Windows":
        pasta = os.getcwd().lower()
        ruim = any(x in pasta for x in ("\\windows\\system32",
                                        "\\windows\\syswow64",
                                        "\\program files"))
        checa("Projeto NAO esta em pasta de sistema", not ruim,
              "mova para %USERPROFILE%\\Documents" if ruim else "")

    # ------------------------------------------------------------ DEPENDENCIAS
    secao("2. DEPENDENCIAS")

    try:
        import usb
        import usb.core
        import usb.util
        ver = getattr(usb, "__version__", "?")
        checa("pyusb importado", True, f"versao {ver}")
        tem_pyusb = True
    except ImportError as e:
        checa("pyusb importado", False, str(e))
        tem_pyusb = False

    try:
        import escpos
        checa("python-escpos importado", True,
              f"versao {getattr(escpos, '__version__', '?')}")
    except ImportError:
        pula("python-escpos importado", "opcional - so para --usar-escpos")

    if not tem_pyusb:
        print("\n  Sem pyusb nao da para continuar. Rode o instalador.")
        return 1

    # --------------------------------------------------------------- BACKEND
    secao("3. BACKEND LIBUSB")

    import usb.backend.libusb1
    from imprime_termica import carregar_backend

    dll_local = os.path.abspath("libusb-1.0.dll")
    if os.path.isfile(dll_local):
        print(f"  DLL local encontrada: {dll_local}")

    try:
        backend = carregar_backend()
        checa("Backend libusb carregado", backend is not None,
              f"{type(backend).__name__}" if backend else
              "instale libusb (Linux: apt install libusb-1.0-0)")
    except SystemExit as e:
        checa("Backend libusb carregado", False, f"SystemExit: {e}")
        backend = None

    # ------------------------------------------------------- COMANDOS ESC/POS
    secao("4. COMANDOS ESC/POS (logica pura, nao precisa de impressora)")

    from imprime_termica import ESCPOS, CODEPAGES, montar_cupom

    checa("INIT = ESC @ (1B 40)", ESCPOS.INIT == b"\x1B\x40",
          hexdump(ESCPOS.INIT))
    checa("Corte total = GS V 0 (1D 56 00)",
          ESCPOS.CORTE_TOTAL == b"\x1D\x56\x00", hexdump(ESCPOS.CORTE_TOTAL))
    checa("Corte parcial = GS V 1 (1D 56 01)",
          ESCPOS.CORTE_PARCIAL == b"\x1D\x56\x01", hexdump(ESCPOS.CORTE_PARCIAL))
    checa("Corte com avanco = GS V B n (1D 56 42 40)",
          ESCPOS.corte_com_avanco(0x40) == b"\x1D\x56\x42\x40",
          hexdump(ESCPOS.corte_com_avanco(0x40)))
    checa("Avanco 4 linhas = ESC d 4 (1B 64 04)",
          ESCPOS.avanca(4) == b"\x1B\x64\x04", hexdump(ESCPOS.avanca(4)))
    checa("Avanco satura em 255 (nao estoura o byte)",
          ESCPOS.avanca(9999) == b"\x1B\x64\xFF", hexdump(ESCPOS.avanca(9999)))
    checa("Avanco negativo vira 0",
          ESCPOS.avanca(-5) == b"\x1B\x64\x00", hexdump(ESCPOS.avanca(-5)))
    checa("Codepage CP850 = ESC t 2 (1B 74 02)",
          ESCPOS.codepage(2) == b"\x1B\x74\x02", hexdump(ESCPOS.codepage(2)))
    checa("Alinhamento centro = ESC a 1 (1B 61 01)",
          ESCPOS.ALINHA_CENTRO == b"\x1B\x61\x01", hexdump(ESCPOS.ALINHA_CENTRO))
    checa("Negrito ON = ESC E 1 (1B 45 01)",
          ESCPOS.NEGRITO_ON == b"\x1B\x45\x01", hexdump(ESCPOS.NEGRITO_ON))
    checa("Gaveta = ESC p 0 25 250 (1B 70 00 19 FA)",
          ESCPOS.ABRE_GAVETA == b"\x1B\x70\x00\x19\xFA",
          hexdump(ESCPOS.ABRE_GAVETA))

    # ------------------------------------------------------ MONTAGEM DO CUPOM
    secao("5. MONTAGEM DO CUPOM")

    cupom = montar_cupom()
    checa("Cupom de teste gerado", len(cupom) > 100, f"{len(cupom)} bytes")
    checa("Comeca com ESC @ (reset)", cupom.startswith(b"\x1B\x40"),
          hexdump(cupom, 16))
    checa("Contem o comando de corte", b"\x1D\x56" in cupom)
    checa("Contem avanco de papel antes do corte", b"\x1B\x64" in cupom)

    sem_corte = montar_cupom(cortar=False)
    checa("--sem-corte realmente remove o corte", b"\x1D\x56" not in sem_corte)

    texto = montar_cupom("Comanda 42")
    checa("Texto proprio entra no cupom", b"Comanda 42" in texto,
          hexdump(texto, 32))

    # Acentuacao: 'ção' em CP850
    acento = montar_cupom("ação")
    esperado = "ação".encode("cp850")
    checa("Acentos codificados em CP850", esperado in acento,
          f"'ação' -> {hexdump(esperado)}")

    for nome, (n, codec) in CODEPAGES.items():
        c = montar_cupom("teste", codepage=nome)
        ok = bytes([0x1B, 0x74, n]) in c
        checa(f"Codepage {nome} emite ESC t {n}", ok)

    # Caractere impossivel nao pode explodir
    try:
        emoji = montar_cupom("emoji: \U0001F600 chines: 中")
        checa("Caractere fora da tabela nao quebra (usa '?')",
              len(emoji) > 0, f"{len(emoji)} bytes gerados")
    except Exception as e:
        checa("Caractere fora da tabela nao quebra", False, repr(e))

    # ---------------------------------------------------------- ENUMERACAO USB
    secao("6. ENUMERACAO USB")

    import usb.core
    from imprime_termica import (interfaces_impressora, encontrar_impressora,
                                 USB_CLASSE_IMPRESSORA)

    try:
        dispositivos = list(usb.core.find(find_all=True, backend=backend))
        checa("Enumeracao USB funcionou", True,
              f"{len(dispositivos)} dispositivo(s) visivel(is)")
    except usb.core.NoBackendError as e:
        checa("Enumeracao USB funcionou", False, f"NoBackendError: {e}")
        dispositivos = []

    impressoras = []
    for dev in dispositivos:
        intfs = list(interfaces_impressora(dev))
        if intfs:
            impressoras.append((dev, intfs[0]))
        classes = []
        try:
            for cfg in dev:
                for i in cfg:
                    classes.append(i.bInterfaceClass)
        except usb.core.USBError:
            classes = ["ilegivel"]
        marca = "  <-- IMPRESSORA" if intfs else ""
        print(f"    0x{dev.idVendor:04X}:0x{dev.idProduct:04X}  "
              f"devClass={dev.bDeviceClass:<3} intfClass={classes}{marca}")

    tem_impressora = len(impressoras) > 0
    if tem_impressora:
        dev, intf = impressoras[0]
        checa("Impressora detectada pela classe de INTERFACE 7", True,
              f"0x{dev.idVendor:04X}:0x{dev.idProduct:04X}")
        checa("Confirma que bDeviceClass NAO e 7 (por isso o filtro por "
              "interface)", dev.bDeviceClass != USB_CLASSE_IMPRESSORA,
              f"bDeviceClass={dev.bDeviceClass}, bInterfaceClass="
              f"{intf.bInterfaceClass}")

        import usb.util
        ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        checa("Endpoint OUT localizado dinamicamente", ep_out is not None,
              f"0x{ep_out.bEndpointAddress:02X}, {ep_out.wMaxPacketSize} bytes"
              if ep_out else "nenhum endpoint de saida")
    else:
        pula("Impressora detectada", "nenhum dispositivo com interface classe 7")
        if platform.system() == "Windows":
            print("         >>> No Windows isso quase sempre significa que")
            print("             falta rodar o Zadig e trocar o driver da")
            print("             impressora para WinUSB.")
        else:
            print("         >>> Verifique se o cabo USB esta conectado e a")
            print("             impressora ligada no botao de energia.")

    # --------------------------------------------------- TRATAMENTO DE ERROS
    secao("7. TRATAMENTO DE ERROS")

    try:
        encontrar_impressora(0xDEAD, 0xBEEF, backend)
        checa("VID/PID inexistente levanta RuntimeError", False,
              "nao levantou excecao")
    except RuntimeError as e:
        checa("VID/PID inexistente levanta RuntimeError", True, str(e)[:60])
    except Exception as e:
        checa("VID/PID inexistente levanta RuntimeError", False, repr(e))

    from imprime_termica import explicar_usberror

    class ErroFalso(usb.core.USBError):
        pass

    for errno, palavra in ((13, "NEGAD"), (16, "OCUPADO"), (19, "DESCONECT")):
        try:
            e = usb.core.USBError("simulado", errno=errno)
            msg = explicar_usberror(e)
            checa(f"errno {errno} vira mensagem acionavel",
                  palavra in msg.upper(), msg.splitlines()[0][:60])
        except Exception as exc:
            checa(f"errno {errno} vira mensagem acionavel", False, repr(exc))

    msg_timeout = explicar_usberror(usb.core.USBError("Operation timed out"))
    checa("timeout vira mensagem acionavel", "TIMEOUT" in msg_timeout.upper(),
          msg_timeout.splitlines()[0][:60])

    from imprime_termica import hexint
    checa("hexint aceita '0x0416'", hexint("0x0416") == 0x0416)
    checa("hexint aceita '0416'", hexint("0416") == 0x0416)

    # ----------------------------------------------------- IMPRESSAO REAL
    secao("8. IMPRESSAO FISICA")

    if not tem_impressora:
        pula("Impressao real", "impressora nao conectada")
    elif not imprimir_de_verdade:
        pula("Impressao real", "rode com --imprimir para gastar papel")
    else:
        from imprime_termica import imprimir_pyusb
        try:
            dados = montar_cupom(
                f"AUTOTESTE OK\n{platform.system()} {platform.machine()}\n"
                f"Python {platform.python_version()}")
            imprimir_pyusb(dados, backend=backend)
            checa("Impressao fisica concluida", True,
                  f"{len(dados)} bytes enviados")
        except NotImplementedError:
            # libusb enxerga mas nao abre: o usbprint.sys ainda esta anexado.
            # Em vez de exigir o Zadig, tenta o transporte nativo do Windows -
            # o mesmo fallback que o imprime_termica.py usa sozinho.
            if platform.system() != "Windows":
                raise
            try:
                from imprime_termica import _imprimir_via_usbprint
                _imprimir_via_usbprint(dados)
                checa("Impressao fisica concluida (via usbprint)", True,
                      f"{len(dados)} bytes - sem Zadig")
            except Exception as e2:
                from imprime_termica import _erro_driver_incompativel
                checa("Impressao fisica concluida", False, repr(e2))
                print(_erro_driver_incompativel())
        except Exception as e:
            checa("Impressao fisica concluida", False, repr(e))
            traceback.print_exc()

    # -------------------------------------------------------------- RESUMO
    secao("RESUMO")
    print(f"  Total de verificacoes : {TOTAL}")
    print(f"  Passou                : {PASSOU}")
    print(f"  Falhou                : {FALHOU}")
    print(f"  Pulou                 : {PULOU}")
    print()

    if FALHOU == 0 and tem_impressora:
        print("  >>> TUDO CERTO. A impressora esta acessivel e o codigo esta ok.")
        if not imprimir_de_verdade:
            print("  >>> Rode 'python autoteste.py --imprimir' para imprimir.")
    elif FALHOU == 0:
        print("  >>> O CODIGO ESTA OK, mas a impressora nao foi encontrada.")
        print("      Resolva a conexao/driver e rode este autoteste de novo.")
    else:
        print(f"  >>> {FALHOU} verificacao(oes) falharam - veja os detalhes acima.")
    print()
    return 0 if FALHOU == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
