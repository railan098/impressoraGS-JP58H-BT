# -*- coding: utf-8 -*-
"""
Backend ``usbprint:`` — Windows falando pelo próprio ``usbprint.sys``.

**Por que este caminho existe.** O caminho ``usb:`` (libusb) esbarra num
problema no Windows sobre ARM (Snapdragon): o libusb *enumera* qualquer
dispositivo, mas só consegue *abrir* aquele cujo driver anexado seja
WinUSB/libusbK. Trocar o driver exige o Zadig, que pede administrador e faz a
impressora sumir de "Impressoras e Scanners" — e das três opções do Zadig, só o
WinUSB tem binário ARM64.

Só que o ``usbprint.sys`` — o driver que o Windows já anexa sozinho, e que é
justamente o que bloqueia o libusb — expõe um *device interface*
(``GUID_DEVINTERFACE_USBPRINT``) que pode ser aberto com ``CreateFileW`` e
receber bytes crus com ``WriteFile``.

O driver que atrapalhava vira o transporte. E como é tudo API nativa do Windows
(setupapi + kernel32), funciona em ARM64 sem emulação, sem Zadig, sem
administrador e sem passar pela fila de impressão.

**Limitação:** só escrita. Ler status da impressora exigiria o caminho WinUSB.

Este módulo é uma adaptação de ``usbprint_win.py``, escrito e testado no
projeto irmão ``impressoraGS-JP58H-BT``.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

TIPO = "usbprint"

# --------------------------------------------------------------------------- #
#  Constantes do Win32
# --------------------------------------------------------------------------- #
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
ERROR_ACCESS_DENIED = 5
ERROR_FILE_NOT_FOUND = 2

# vid_0416&pid_5011 dentro do caminho do device interface
_VID_PID = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", re.IGNORECASE)


def disponivel() -> bool:
    return os.name == "nt"


def _estruturas():
    """Monta as estruturas do SetupAPI. Só é chamado no Windows."""
    import ctypes as C
    from ctypes import wintypes as W

    class GUID(C.Structure):
        _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD),
                    ("Data3", W.WORD), ("Data4", W.BYTE * 8)]

    class SP_DEVICE_INTERFACE_DATA(C.Structure):
        _fields_ = [("cbSize", W.DWORD), ("InterfaceClassGuid", GUID),
                    ("Flags", W.DWORD), ("Reserved", C.POINTER(W.ULONG))]

    # {28d78fad-5a12-11d1-ae5b-0000f803a8c2}
    guid = GUID()
    guid.Data1, guid.Data2, guid.Data3 = 0x28D78FAD, 0x5A12, 0x11D1
    for i, octeto in enumerate((0xAE, 0x5B, 0x00, 0x00, 0xF8, 0x03, 0xA8, 0xC2)):
        guid.Data4[i] = octeto

    setupapi = C.WinDLL("setupapi", use_last_error=True)
    kernel32 = C.WinDLL("kernel32", use_last_error=True)
    # Sem fixar restype como c_void_p, o ctypes trunca os HANDLEs para 32 bits
    # num processo de 64 bits — e o handle vira lixo.
    setupapi.SetupDiGetClassDevsW.restype = C.c_void_p
    kernel32.CreateFileW.restype = C.c_void_p

    # O SP_DEVICE_INTERFACE_DETAIL_DATA_W tem campo de tamanho variável no fim,
    # e o Windows exige que cbSize seja o tamanho do *cabeçalho*: 8 em processos
    # de 64 bits, 6 em 32 bits. Não é sizeof() da struct inteira, e errar aqui
    # faz a chamada falhar com ERROR_INVALID_PARAMETER.
    cb_detalhe = 8 if C.sizeof(C.c_void_p) == 8 else 6
    return C, W, setupapi, kernel32, guid, SP_DEVICE_INTERFACE_DATA, cb_detalhe


def _caminhos() -> List[str]:
    """Caminhos de device interface das impressoras USB com o usbprint anexado."""
    if not disponivel():
        return []
    C, W, setupapi, _, guid, SP_DEVICE_INTERFACE_DATA, cb_detalhe = _estruturas()

    invalido = C.c_void_p(-1).value
    conjunto = setupapi.SetupDiGetClassDevsW(
        C.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if conjunto == invalido:
        return []

    encontrados: List[str] = []
    try:
        indice = 0
        while True:
            dados = SP_DEVICE_INTERFACE_DATA()
            dados.cbSize = C.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                    C.c_void_p(conjunto), None, C.byref(guid), indice, C.byref(dados)):
                break                       # ERROR_NO_MORE_ITEMS: acabou

            necessario = W.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                C.c_void_p(conjunto), C.byref(dados), None, 0,
                C.byref(necessario), None)

            buffer = C.create_string_buffer(necessario.value)
            C.memmove(buffer, C.byref(W.DWORD(cb_detalhe)), C.sizeof(W.DWORD))
            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                    C.c_void_p(conjunto), C.byref(dados), buffer,
                    necessario.value, None, None):
                encontrados.append(C.wstring_at(C.addressof(buffer) + C.sizeof(W.DWORD)))
            indice += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(C.c_void_p(conjunto))
    return encontrados


def listar(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not disponivel():
        return []
    itens: List[Dict[str, Any]] = []
    try:
        for caminho in _caminhos():
            achado = _VID_PID.search(caminho)
            if achado:
                vid, pid = achado.group(1).lower(), achado.group(2).lower()
                identificador = f"usbprint:{vid}:{pid}"
                rotulo = f"USB {vid}:{pid} (driver do Windows)"
            else:
                # Sem VID/PID no caminho não há como montar um id estável; o
                # índice serve, e é o que o Windows garante dentro da sessão.
                identificador = f"usbprint:#{len(itens)}"
                rotulo = "Impressora USB (driver do Windows)"
            itens.append({
                "id": identificador,
                "rotulo": rotulo,
                "tipo": TIPO,
                "papel": "58mm",
                "detalhe": "usbprint.sys — funciona em Windows ARM sem Zadig",
            })
    except Exception:
        return []
    return itens


def alvo_de(identificador: str) -> Optional[Tuple[int, int]]:
    """``usbprint:0416:5011`` -> ``(0x0416, 0x5011)``; ``usbprint:#0`` -> ``None``."""
    resto = identificador.split(":", 1)[1]
    if resto.startswith("#"):
        return None
    vid, pid = resto.split(":")
    return int(vid, 16), int(pid, 16)


def _escolher(alvo: Optional[Tuple[int, int]]) -> Optional[str]:
    caminhos = _caminhos()
    if not caminhos:
        return None
    if alvo is None:
        return caminhos[0]
    marca = f"vid_{alvo[0]:04x}&pid_{alvo[1]:04x}"
    for caminho in caminhos:
        if marca in caminho.lower():
            return caminho
    return None


def imprimir(alvo: Optional[Tuple[int, int]], dados: bytes) -> Tuple[bool, str]:
    if not disponivel():
        return False, "este caminho só existe no Windows"

    caminho = _escolher(alvo)
    if caminho is None:
        return False, ("nenhuma impressora USB com o driver usbprint foi encontrada. "
                       "Se você trocou o driver por WinUSB no Zadig, este caminho deixa "
                       "de existir — use o identificador 'usb:' desta impressora.")

    C, W, _, kernel32, _, _, _ = _estruturas()
    invalido = C.c_void_p(-1).value

    manipulador = kernel32.CreateFileW(
        caminho, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None)

    if manipulador == invalido:
        erro = C.get_last_error()
        if erro == ERROR_ACCESS_DENIED:
            return False, ("acesso negado: outro programa está segurando a impressora. "
                           "Feche o software de PDV e a janela de impressão e repita.")
        if erro == ERROR_FILE_NOT_FOUND:
            return False, "a impressora sumiu entre a listagem e a abertura — reconecte o cabo"
        return False, f"CreateFileW falhou (erro {erro})"

    try:
        escritos = W.DWORD(0)
        ok = kernel32.WriteFile(C.c_void_p(manipulador), dados, len(dados),
                                C.byref(escritos), None)
        if not ok:
            return False, (f"WriteFile falhou (erro {C.get_last_error()}): sem papel, "
                           "tampa aberta ou impressora desligada")
        if escritos.value != len(dados):
            return False, f"enviados {escritos.value} de {len(dados)} bytes"
        return True, f"{escritos.value} bytes"
    finally:
        kernel32.CloseHandle(C.c_void_p(manipulador))
