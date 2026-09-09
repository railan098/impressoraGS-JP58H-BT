# -*- coding: utf-8 -*-
"""
Backend ``sistema:`` — impressoras instaladas (spooler do Windows / CUPS).

É o caminho preferido, e o único que não tem dependência nenhuma além da
biblioteca padrão. Vale para qualquer impressora que apareça na lista de
impressoras do sistema operacional: térmica, laser, jato de tinta, USB ou de
rede.

**Windows — o segredo é o datatype RAW.** ``StartDocPrinter`` com
``pDatatype = "RAW"`` manda o spooler entregar os bytes ao aparelho sem
processar nada. É o único jeito de ESC/POS chegar inteiro numa impressora
instalada; sem RAW, o spooler tenta renderizar e sai lixo.

**Linux/macOS — o segredo é o ``-o raw``.** Sem ele o CUPS aciona os filtros,
converte para PostScript e a térmica recebe um documento que não entende.

Usamos ``ctypes`` em vez de ``pywin32`` de propósito: o executável precisa
rodar num balcão sem nada instalado, e uma dependência a menos é uma chance a
menos de o instalador falhar.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

TIPO = "sistema"

# O nome vem do sistema operacional e volta para dentro de uma chamada de API.
# Nada de caractere de controle, e teto de tamanho.
NOME_VALIDO = re.compile(r"^[^\x00-\x1f]{1,120}$")


# --------------------------------------------------------------------------- #
#  Windows — winspool.drv
# --------------------------------------------------------------------------- #

def _windows_padrao() -> Optional[str]:
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv")
    tamanho = wintypes.DWORD(0)
    winspool.GetDefaultPrinterW(None, ctypes.byref(tamanho))
    if tamanho.value == 0:
        return None
    buffer = ctypes.create_unicode_buffer(tamanho.value)
    if winspool.GetDefaultPrinterW(buffer, ctypes.byref(tamanho)):
        return buffer.value
    return None


def _windows_listar() -> Tuple[List[str], Optional[str]]:
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv")

    class PRINTER_INFO_4(ctypes.Structure):
        _fields_ = [
            ("pPrinterName", wintypes.LPWSTR),
            ("pServerName", wintypes.LPWSTR),
            ("Attributes", wintypes.DWORD),
        ]

    PRINTER_ENUM_LOCAL = 0x00000002
    PRINTER_ENUM_CONNECTIONS = 0x00000004
    sinalizadores = PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS

    # Chamada em duas etapas: a primeira só descobre de quanto buffer o
    # Windows precisa; a segunda preenche. É o padrão de toda API Enum* do Win32.
    necessario = wintypes.DWORD(0)
    devolvidos = wintypes.DWORD(0)
    winspool.EnumPrintersW(sinalizadores, None, 4, None, 0,
                           ctypes.byref(necessario), ctypes.byref(devolvidos))
    if necessario.value == 0:
        return [], _windows_padrao()

    buffer = ctypes.create_string_buffer(necessario.value)
    if not winspool.EnumPrintersW(sinalizadores, None, 4, buffer, necessario.value,
                                  ctypes.byref(necessario), ctypes.byref(devolvidos)):
        return [], _windows_padrao()

    info = ctypes.cast(buffer, ctypes.POINTER(PRINTER_INFO_4))
    nomes = [info[i].pPrinterName for i in range(devolvidos.value) if info[i].pPrinterName]
    return [n for n in nomes if NOME_VALIDO.match(n)], _windows_padrao()


def _windows_imprimir(nome: str, dados: bytes) -> Tuple[bool, str]:
    import ctypes
    from ctypes import wintypes

    winspool = ctypes.WinDLL("winspool.drv")

    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [
            ("pDocName", wintypes.LPWSTR),
            ("pOutputFile", wintypes.LPWSTR),
            ("pDatatype", wintypes.LPWSTR),
        ]

    manipulador = wintypes.HANDLE()
    if not winspool.OpenPrinterW(nome, ctypes.byref(manipulador), None):
        return False, f"o spooler não abriu a impressora '{nome}' (erro {ctypes.get_last_error()})"

    try:
        documento = DOC_INFO_1("Cupom Menuxy", None, "RAW")
        trabalho = winspool.StartDocPrinterW(manipulador, 1, ctypes.byref(documento))
        if not trabalho:
            return False, "o spooler recusou o documento"
        try:
            if not winspool.StartPagePrinter(manipulador):
                return False, "o spooler recusou a página"
            escritos = wintypes.DWORD(0)
            ok = winspool.WritePrinter(manipulador, dados, len(dados), ctypes.byref(escritos))
            winspool.EndPagePrinter(manipulador)
            if not ok or escritos.value != len(dados):
                return False, f"enviados {escritos.value} de {len(dados)} bytes"
        finally:
            winspool.EndDocPrinter(manipulador)
    finally:
        winspool.ClosePrinter(manipulador)

    return True, f"{len(dados)} bytes"


# --------------------------------------------------------------------------- #
#  Linux e macOS — CUPS
# --------------------------------------------------------------------------- #

def _cups_listar() -> Tuple[List[str], Optional[str]]:
    """``lpstat -a`` dá uma linha por fila; o nome é o primeiro campo."""
    if not shutil.which("lpstat"):
        return [], None
    try:
        saida = subprocess.run(["lpstat", "-a"], capture_output=True,
                               text=True, timeout=5).stdout
    except Exception:
        return [], None

    nomes = [linha.split()[0] for linha in saida.splitlines() if linha.split()]
    nomes = [n for n in nomes if NOME_VALIDO.match(n)]

    padrao = None
    try:
        resposta = subprocess.run(["lpstat", "-d"], capture_output=True,
                                  text=True, timeout=5).stdout
        if ":" in resposta:
            candidato = resposta.split(":", 1)[1].strip()
            if candidato and NOME_VALIDO.match(candidato):
                padrao = candidato
    except Exception:
        pass
    return nomes, padrao


def _cups_imprimir(nome: str, dados: bytes) -> Tuple[bool, str]:
    try:
        processo = subprocess.run(
            ["lp", "-d", nome, "-o", "raw"],
            input=dados, capture_output=True, timeout=25,
        )
    except FileNotFoundError:
        return False, "o comando 'lp' não existe nesta máquina (instale o pacote cups-client)"
    except subprocess.TimeoutExpired:
        return False, "o CUPS não respondeu em 25 segundos"
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"

    if processo.returncode != 0:
        detalhe = (processo.stderr or b"").decode("utf-8", "replace").strip()
        return False, detalhe or f"o lp devolveu código {processo.returncode}"
    return True, f"{len(dados)} bytes"


# --------------------------------------------------------------------------- #
#  Contrato do backend
# --------------------------------------------------------------------------- #

def disponivel() -> bool:
    """No Windows sempre; fora dele, só se o CUPS estiver instalado."""
    if os.name == "nt":
        return True
    return bool(shutil.which("lp") and shutil.which("lpstat"))


def padrao_do_sistema() -> Optional[str]:
    try:
        _, padrao = _windows_listar() if os.name == "nt" else _cups_listar()
        return f"sistema:{padrao}" if padrao else None
    except Exception:
        return None


def listar(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        nomes, _ = _windows_listar() if os.name == "nt" else _cups_listar()
    except Exception as erro:
        print(f"[sistema] falha ao listar: {erro}", file=sys.stderr)
        return []

    return [{
        "id": f"sistema:{nome}",
        "rotulo": nome,
        "tipo": TIPO,
        "papel": "80mm",
        "detalhe": "spooler do Windows" if os.name == "nt" else "fila do CUPS",
    } for nome in nomes]


def alvo_de(identificador: str) -> str:
    """``sistema:Termica58`` -> ``Termica58``."""
    return identificador.split(":", 1)[1]


def imprimir(alvo: str, dados: bytes) -> Tuple[bool, str]:
    try:
        if os.name == "nt":
            return _windows_imprimir(alvo, dados)
        return _cups_imprimir(alvo, dados)
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"
