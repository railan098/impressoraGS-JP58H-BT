#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
usbprint_win.py — Transporte ESC/POS no Windows usando o driver usbprint.sys.

Por que este módulo existe
--------------------------
O caminho principal do projeto (PyUSB + libusb + WinUSB via Zadig) esbarra num
problema no Windows sobre ARM (Snapdragon):

  - o libusb consegue *enumerar* qualquer dispositivo, mas ``libusb_open()`` só
    funciona se o driver anexado for WinUSB/libusbK;
  - trocar o driver exige o Zadig, que é um binário x86 rodando sob emulação,
    pede privilégio de administrador e faz a impressora sumir de
    "Impressoras e Scanners";
  - e das três opções do Zadig, só o WinUSB tem binário ARM64 — libusb-win32 e
    libusbK não têm.

Só que o ``usbprint.sys`` — o driver que o Windows já anexa sozinho e que é
justamente o que bloqueia o libusb — expõe um *device interface*
(``GUID_DEVINTERFACE_USBPRINT``). Esse caminho pode ser aberto com
``CreateFileW`` e receber bytes crus com ``WriteFile``.

Ou seja: o driver que atrapalhava vira o transporte. E como tudo aqui é API
nativa do Windows (setupapi + kernel32), funciona em ARM64 sem emulação de
driver, sem Zadig, sem administrador e sem fila de impressão.

Limitação: este caminho é só de escrita (ESC/POS é um protocolo de mão única
para impressão). Ler status da impressora exigiria o caminho WinUSB.
"""

from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from typing import List, Optional

# --------------------------------------------------------------------------- #
# Constantes do Win32
# --------------------------------------------------------------------------- #
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10

GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = C.c_void_p(-1).value

ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259
ERROR_ACCESS_DENIED = 5
ERROR_FILE_NOT_FOUND = 2

# O SP_DEVICE_INTERFACE_DETAIL_DATA_W tem um campo de tamanho variável no fim,
# e o Windows exige que cbSize seja o tamanho do *cabeçalho* — 8 em processos
# de 64 bits e 6 em 32 bits. Não é sizeof() da struct inteira: é um valor fixo
# documentado, e errar aqui faz a chamada falhar com ERROR_INVALID_PARAMETER.
_CB_SIZE_DETALHE = 8 if C.sizeof(C.c_void_p) == 8 else 6


class _GUID(C.Structure):
    _fields_ = [
        ("Data1", W.DWORD),
        ("Data2", W.WORD),
        ("Data3", W.WORD),
        ("Data4", W.BYTE * 8),
    ]


class _SP_DEVICE_INTERFACE_DATA(C.Structure):
    _fields_ = [
        ("cbSize", W.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", W.DWORD),
        ("Reserved", C.POINTER(W.ULONG)),
    ]


def _montar_guid(d1: int, d2: int, d3: int, resto) -> _GUID:
    g = _GUID()
    g.Data1, g.Data2, g.Data3 = d1, d2, d3
    for i, octeto in enumerate(resto):
        g.Data4[i] = octeto
    return g


# {28d78fad-5a12-11d1-ae5b-0000f803a8c2}
GUID_DEVINTERFACE_USBPRINT = _montar_guid(
    0x28D78FAD, 0x5A12, 0x11D1,
    (0xAE, 0x5B, 0x00, 0x00, 0xF8, 0x03, 0xA8, 0xC2),
)


def _carregar_dlls():
    """Carrega setupapi/kernel32 e fixa os tipos de retorno que importam.

    Sem declarar ``restype`` como ``c_void_p``, o ctypes trunca os HANDLEs
    para 32 bits em processos de 64 bits — e o handle vira lixo.
    """
    setupapi = C.WinDLL("setupapi", use_last_error=True)
    kernel32 = C.WinDLL("kernel32", use_last_error=True)
    setupapi.SetupDiGetClassDevsW.restype = C.c_void_p
    kernel32.CreateFileW.restype = C.c_void_p
    return setupapi, kernel32


# --------------------------------------------------------------------------- #
# Enumeração
# --------------------------------------------------------------------------- #
def listar_impressoras() -> List[str]:
    """Lista os caminhos de device interface das impressoras USB presentes.

    Returns:
        Lista de caminhos no formato
        ``\\\\?\\usb#vid_0416&pid_5011#serial#{guid}``. Vazia se o Windows não
        tiver nenhuma impressora USB com o ``usbprint`` anexado.

    Raises:
        OSError: se a enumeração do SetupAPI falhar.
    """
    setupapi, _ = _carregar_dlls()

    conjunto = setupapi.SetupDiGetClassDevsW(
        C.byref(GUID_DEVINTERFACE_USBPRINT), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if conjunto == INVALID_HANDLE_VALUE:
        raise OSError(f"SetupDiGetClassDevsW falhou (erro {C.get_last_error()}).")

    caminhos: List[str] = []
    try:
        indice = 0
        while True:
            dados = _SP_DEVICE_INTERFACE_DATA()
            dados.cbSize = C.sizeof(_SP_DEVICE_INTERFACE_DATA)
            achou = setupapi.SetupDiEnumDeviceInterfaces(
                C.c_void_p(conjunto), None,
                C.byref(GUID_DEVINTERFACE_USBPRINT), indice, C.byref(dados))
            if not achou:
                break  # ERROR_NO_MORE_ITEMS: acabou a lista.

            # 1a chamada: descobre o tamanho necessário do buffer.
            necessario = W.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                C.c_void_p(conjunto), C.byref(dados), None, 0,
                C.byref(necessario), None)

            # 2a chamada: preenche de fato. O cbSize vai nos 4 primeiros bytes
            # e o caminho (WCHAR*) começa logo depois.
            buffer = C.create_string_buffer(necessario.value)
            C.memmove(buffer, C.byref(W.DWORD(_CB_SIZE_DETALHE)),
                      C.sizeof(W.DWORD))
            preencheu = setupapi.SetupDiGetDeviceInterfaceDetailW(
                C.c_void_p(conjunto), C.byref(dados), buffer,
                necessario.value, None, None)
            if preencheu:
                caminhos.append(
                    C.wstring_at(C.addressof(buffer) + C.sizeof(W.DWORD)))
            indice += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(C.c_void_p(conjunto))

    return caminhos


def escolher_impressora(vid: Optional[int] = None,
                        pid: Optional[int] = None) -> str:
    """Escolhe o caminho da impressora, opcionalmente filtrando por VID/PID.

    Args:
        vid, pid: se informados, só aceita o dispositivo cujo caminho casar.
            O caminho traz ``vid_XXXX&pid_YYYY`` em minúsculas.

    Returns:
        O caminho do device interface.

    Raises:
        RuntimeError: se nenhuma impressora casar com o filtro.
    """
    caminhos = listar_impressoras()
    if not caminhos:
        raise RuntimeError(
            "Nenhuma impressora USB com o driver usbprint foi encontrada.\n"
            "  Confira o cabo, e veja se ela aparece no Gerenciador de "
            "Dispositivos.\n"
            "  Se você já rodou o Zadig e trocou o driver para WinUSB, este "
            "caminho\n"
            "  deixa de existir — use o caminho normal (libusb) do projeto.")

    if vid is None and pid is None:
        return caminhos[0]

    alvo = ""
    if vid is not None:
        alvo += f"vid_{vid:04x}"
    if pid is not None:
        alvo += f"&pid_{pid:04x}" if alvo else f"pid_{pid:04x}"

    for caminho in caminhos:
        if alvo in caminho.lower():
            return caminho

    raise RuntimeError(
        f"Nenhuma impressora usbprint casa com {alvo}.\n"
        "  Encontradas:\n    " + "\n    ".join(caminhos))


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #
def imprimir(dados: bytes,
             vid: Optional[int] = None,
             pid: Optional[int] = None,
             caminho: Optional[str] = None) -> int:
    """Escreve bytes ESC/POS crus na impressora, via usbprint.sys.

    Args:
        dados: fluxo ESC/POS já montado.
        vid, pid: filtro opcional de dispositivo.
        caminho: caminho de device interface explícito (pula a escolha).

    Returns:
        Quantidade de bytes escritos.

    Raises:
        RuntimeError: nenhuma impressora encontrada, ou acesso negado.
        OSError: falha do Win32 na abertura ou na escrita.
    """
    if caminho is None:
        caminho = escolher_impressora(vid, pid)

    _, kernel32 = _carregar_dlls()

    handle = kernel32.CreateFileW(
        caminho, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None)

    if handle == INVALID_HANDLE_VALUE:
        erro = C.get_last_error()
        if erro == ERROR_ACCESS_DENIED:
            raise RuntimeError(
                "ACESSO NEGADO ao abrir a impressora.\n"
                "  Normalmente é outro programa segurando o dispositivo:\n"
                "  feche o software de PDV e a janela de impressão e repita.")
        if erro == ERROR_FILE_NOT_FOUND:
            raise RuntimeError(
                "A impressora sumiu entre a listagem e a abertura.\n"
                "  Reconecte o cabo USB e tente de novo.")
        raise OSError(f"CreateFileW falhou no caminho da impressora "
                      f"(erro {erro}): {caminho}")

    try:
        escritos = W.DWORD(0)
        ok = kernel32.WriteFile(C.c_void_p(handle), dados, len(dados),
                                C.byref(escritos), None)
        if not ok:
            raise OSError(
                f"WriteFile falhou (erro {C.get_last_error()}). "
                "A impressora pode estar sem papel, com a tampa aberta "
                "ou desligada.")
        return escritos.value
    finally:
        kernel32.CloseHandle(C.c_void_p(handle))


if __name__ == "__main__":
    encontradas = listar_impressoras()
    print(f"Impressoras USB via usbprint: {len(encontradas)}")
    for item in encontradas:
        print("   ", item)
