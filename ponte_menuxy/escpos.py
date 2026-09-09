# -*- coding: utf-8 -*-
"""
ESC/POS: texto que vem do sistema  ->  bytes que a impressora entende.

ESC/POS é o dialeto que praticamente toda impressora térmica de cupom fala,
independente de marca. Ele é *de mão única*: a ponte envia comandos e não
espera resposta. Por isso o caminho de impressão é simples — e por isso um erro
de montagem só aparece no papel.

Os três pontos que mais custam a descobrir, e que estão resolvidos aqui:

* **Página de código.** A impressora não fala UTF-8. Ela tem tabelas de 256
  caracteres e precisa ser avisada de qual usar (``ESC t n``) *antes* do texto.
  Sem isso, "ç" e "ã" saem como lixo. ``cp850`` é a que melhor cobre o
  português.
* **Avanço antes do corte.** A lâmina fica alguns milímetros acima da cabeça
  térmica. Cortar sem avançar passa a serrilha por cima da última linha.
* **Reinicialização.** ``ESC @`` no começo devolve a impressora ao estado
  conhecido. Sem ele, um negrito deixado por um cupom anterior contamina o
  próximo.
"""

from __future__ import annotations

import time
import unicodedata
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
#  Páginas de código:  nome -> (n do comando ESC t n, codec do Python)
# --------------------------------------------------------------------------- #

CODEPAGES: Dict[str, Tuple[int, str]] = {
    "cp850": (2, "cp850"),      # Multilingual — melhor cobertura do português
    "cp860": (3, "cp860"),      # Portuguese — algumas GS-JP58H preferem esta
    "cp437": (0, "cp437"),      # padrão de fábrica da maioria
    "cp1252": (16, "cp1252"),   # Windows Latin-1
    "cp858": (19, "cp858"),     # cp850 + símbolo do euro
}

# --------------------------------------------------------------------------- #
#  Comandos
# --------------------------------------------------------------------------- #

INIT = b"\x1b\x40"                  # ESC @   — reinicializa
CORTE_TOTAL = b"\x1d\x56\x00"       # GS V 0
CORTE_PARCIAL = b"\x1d\x56\x01"     # GS V 1
CORTE_COM_AVANCO = b"\x1d\x56\x42"  # GS V B n — avança n pontos e corta
GAVETA = b"\x1b\x70\x00\x19\xfa"    # ESC p 0 — pulso na gaveta de dinheiro
ALINHAR_ESQUERDA = b"\x1b\x61\x00"
ALINHAR_CENTRO = b"\x1b\x61\x01"
NEGRITO_LIGA = b"\x1b\x45\x01"
NEGRITO_DESLIGA = b"\x1b\x45\x00"
DUPLO_LIGA = b"\x1d\x21\x11"        # GS ! — dobra largura e altura
DUPLO_DESLIGA = b"\x1d\x21\x00"


def selecionar_codepage(codepage: str) -> bytes:
    n, _ = CODEPAGES.get(codepage, CODEPAGES["cp850"])
    return b"\x1b\x74" + bytes([n])


def codificar(texto: str, codepage: str = "cp850") -> bytes:
    """
    Texto para bytes na página de código da impressora.

    Acentos que a tabela não tem viram o caractere sem acento em vez de "?".
    Uma impressora antiga em cp437 imprimindo "Sao Bento" ainda é legível;
    "S?o Bento" faz o operador achar que a ponte quebrou.
    """
    _, codec = CODEPAGES.get(codepage, CODEPAGES["cp850"])
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    try:
        return texto.encode(codec)
    except UnicodeEncodeError:
        pass

    saida = []
    for caractere in texto:
        try:
            saida.append(caractere.encode(codec))
        except UnicodeEncodeError:
            simples = unicodedata.normalize("NFKD", caractere)
            simples = "".join(c for c in simples if not unicodedata.combining(c))
            try:
                saida.append((simples or " ").encode(codec))
            except UnicodeEncodeError:
                saida.append(b" ")
    return b"".join(saida)


def quebrar(texto: str, colunas: int = 32) -> str:
    """
    Quebra linhas longas na largura da bobina, sem partir palavra no meio.

    O sistema normalmente já manda o texto formatado. Isto é a rede de proteção
    para quando não manda: sem ela a impressora corta a linha na coluna 33 e o
    nome do produto some pela borda direita, silenciosamente.
    """
    if colunas < 8:
        colunas = 32
    linhas: List[str] = []
    for original in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if len(original) <= colunas:
            linhas.append(original)
            continue
        atual = ""
        for palavra in original.split(" "):
            # Palavra maior que a bobina inteira (um código de barras digitado,
            # por exemplo): parte no seco, porque não há onde quebrar.
            while len(palavra) > colunas:
                if atual:
                    linhas.append(atual)
                    atual = ""
                linhas.append(palavra[:colunas])
                palavra = palavra[colunas:]
            if not atual:
                atual = palavra
            elif len(atual) + 1 + len(palavra) <= colunas:
                atual += " " + palavra
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
    return "\n".join(linhas)


def montar_cupom(texto: str,
                 codepage: str = "cp850",
                 cortar: bool = True,
                 avancos: int = 4,
                 colunas: int = 0,
                 gaveta: bool = False) -> bytes:
    """
    Monta o cupom completo, do ``ESC @`` ao corte.

    ``colunas=0`` respeita a formatação que veio do sistema; qualquer outro
    valor manda a ponte requebrar o texto naquela largura.
    """
    corpo = INIT + selecionar_codepage(codepage)
    corpo += codificar(quebrar(texto, colunas) if colunas else texto, codepage)
    if not corpo.endswith(b"\n"):
        corpo += b"\n"
    corpo += b"\n" * max(0, avancos)
    if cortar:
        corpo += CORTE_TOTAL
    if gaveta:
        corpo += GAVETA
    return corpo


def comando_gaveta() -> bytes:
    """Pulso de abertura da gaveta de dinheiro, isolado."""
    return INIT + GAVETA


def cupom_de_teste(colunas: int = 32, versao: str = "", sistema: str = "") -> str:
    """
    Cupom de diagnóstico.

    A régua no meio é o ponto: se ela couber inteira numa linha, a largura
    configurada bate com a bobina. Se sobrar ou faltar, o operador vê na hora,
    sem precisar medir nada.
    """
    # Régua clássica: o dígito cai exatamente na coluna múltipla de 10.
    regua = ""
    dezena = 1
    while len(regua) < colunas:
        regua += "....+...." + str(dezena)[-1]
        dezena += 1
    regua = regua[:colunas]

    linhas = [
        "PONTE DE IMPRESSAO".center(colunas),
        "-" * colunas,
        f"Versao....: {versao}"[:colunas],
        f"Sistema...: {sistema}"[:colunas],
        f"Colunas...: {colunas}"[:colunas],
        f"Emitido...: {time.strftime('%d/%m/%Y %H:%M:%S')}"[:colunas],
        "-" * colunas,
        regua,
        "-" * colunas,
        "Se a regua acima coube inteira",
        "numa linha so, a largura esta",
        "correta.",
        "",
        "Acentuacao: acao, coracao, pao",
        "",
    ]
    return "\n".join(linhas)
