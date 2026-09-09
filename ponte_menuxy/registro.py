# -*- coding: utf-8 -*-
"""
Registro em arquivo — o que a ponte fez, para quando ninguém estava olhando.

O balcão liga a máquina de manhã e descobre à tarde que "não imprimiu nada".
Sem registro, a investigação começa do zero. Com ele, a resposta costuma estar
na primeira tela: origem recusada, impressora que sumiu, CUPS parado.

Duas decisões:

* **Rotação por tamanho, sem depender do ``logging``.** Um arquivo só, trocado
  por ``.1`` quando passa do teto. O módulo ``logging`` faria isso, mas
  arrastaria configuração global que atrapalha quem embute esta ponte em outro
  programa.
* **Nunca levantar exceção.** Disco cheio ou pasta sem permissão não podem
  impedir a impressão de sair — que é o serviço que interessa.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

from .config import caminho_registro

_trava = threading.Lock()
_ligado = False
_teto_bytes = 512 * 1024


def ativar(ligado: bool, teto_kb: int = 512) -> None:
    global _ligado, _teto_bytes
    with _trava:
        _ligado = bool(ligado)
        _teto_bytes = max(32, int(teto_kb)) * 1024


def escrever(mensagem: str) -> None:
    """Uma linha, com carimbo de data e hora. Silenciosa se o registro estiver desligado."""
    if not _ligado:
        return
    linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {mensagem}\n"
    with _trava:
        try:
            caminho = caminho_registro()
            if os.path.exists(caminho) and os.path.getsize(caminho) > _teto_bytes:
                anterior = caminho + ".1"
                if os.path.exists(anterior):
                    os.remove(anterior)
                os.replace(caminho, anterior)
            with open(caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write(linha)
        except OSError:
            pass    # disco cheio ou sem permissão: nunca atrapalhar a impressão


def ler_final(linhas: int = 200) -> str:
    """As últimas linhas do registro, para a janela e o diagnóstico."""
    try:
        with open(caminho_registro(), "r", encoding="utf-8", errors="replace") as arquivo:
            return "".join(arquivo.readlines()[-linhas:])
    except OSError:
        return ""
