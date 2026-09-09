# -*- coding: utf-8 -*-
"""
Configuração da ponte: onde ela mora, como é lida e como é saneada.

Duas decisões que valem a explicação:

1. **O arquivo fica no perfil do usuário**, nunca ao lado do programa. O
   executável pode acabar em ``C:\\Program Files`` ou em ``/usr/lib``, onde
   escrever exige administrador. O perfil do usuário sempre é gravável, e é
   onde o Windows e o Linux esperam encontrar configuração de aplicativo.

2. **Tudo é saneado na leitura.** O arquivo é JSON e o operador vai editar à
   mão mais cedo ou mais tarde. Uma porta escrita como ``"noventa e um"`` não
   pode derrubar a ponte no login do balcão — vira o padrão, com aviso.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from . import NOME_CURTO

# --------------------------------------------------------------------------- #
#  Valores padrão — a documentação de cada campo está em docs/CONFIGURACAO.md
# --------------------------------------------------------------------------- #

PADRAO: Dict[str, Any] = {
    # ---- rede local -------------------------------------------------------
    "porta": 9100,
    # Quem pode mandar imprimir. "*" aceita qualquer site aberto no navegador
    # desta máquina — prático no primeiro dia, aberto para sempre. O instalador
    # pergunta o endereço do sistema e grava aqui.
    "origens_permitidas": ["*"],
    "limite_por_minuto": 60,

    # ---- impressão --------------------------------------------------------
    # Identificador completo, com prefixo de backend: "sistema:Termica58",
    # "usb:0416:5011", "rede:192.168.0.50:9100". Vazio = padrão do sistema.
    "impressora_padrao": "",
    "codepage": "cp850",
    "cortar_por_padrao": True,
    # Largura da bobina em colunas: 32 para 58 mm, 48 para 80 mm. Serve para a
    # ponte quebrar linhas quando o sistema manda texto não formatado.
    "colunas": 32,
    # Linhas em branco antes do corte. Não é decoração: a lâmina fica alguns
    # milímetros acima da cabeça térmica, e sem o avanço a serrilha passa por
    # cima da última linha impressa.
    "avancos_antes_do_corte": 4,
    "abrir_gaveta_apos_imprimir": False,

    # ---- impressoras de rede declaradas pelo operador ---------------------
    # A ponte não varre a rede sozinha (varredura é lenta e assusta antivírus).
    # Cada item: {"nome": "Balcao", "host": "192.168.0.50", "porta": 9100}
    "impressoras_rede": [],

    # ---- comportamento do aplicativo --------------------------------------
    "iniciar_com_sistema": False,
    "abrir_janela": True,
    # Minimizar para a bandeja ao fechar a janela, em vez de encerrar a ponte.
    # O balcão fecha a janela sem querer o tempo todo.
    "fechar_minimiza": True,
    "registrar_em_arquivo": True,
    # Tamanho máximo do registro antes de ser rotacionado, em KB.
    "registro_kb": 512,
}

# Campos que são lista de texto e precisam de saneamento próprio.
_LISTAS_DE_TEXTO = ("origens_permitidas",)


# --------------------------------------------------------------------------- #
#  Localização
# --------------------------------------------------------------------------- #

def pasta_dados() -> str:
    """
    Pasta do perfil do usuário onde a ponte guarda configuração e registro.

    Windows:  %APPDATA%\\MenuxyPonte
    macOS:    ~/Library/Application Support/MenuxyPonte
    Linux:    $XDG_CONFIG_HOME/menuxy-ponte  (ou ~/.config/menuxy-ponte)
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        pasta = os.path.join(base, "MenuxyPonte")
    elif sys.platform == "darwin":
        pasta = os.path.join(os.path.expanduser("~"), "Library",
                             "Application Support", "MenuxyPonte")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        pasta = os.path.join(base, NOME_CURTO)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def caminho_config() -> str:
    return os.path.join(pasta_dados(), "ponte_config.json")


def caminho_registro() -> str:
    return os.path.join(pasta_dados(), "ponte.log")


# --------------------------------------------------------------------------- #
#  Leitura e escrita
# --------------------------------------------------------------------------- #

def _sanear(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Devolve uma configuração que não derruba a ponte, custe o que custar."""
    from .escpos import CODEPAGES        # importado aqui para evitar ciclo

    def inteiro(campo: str, minimo: int, maximo: int) -> None:
        try:
            cfg[campo] = max(minimo, min(maximo, int(cfg[campo])))
        except (TypeError, ValueError):
            cfg[campo] = PADRAO[campo]

    inteiro("porta", 1, 65535)
    inteiro("limite_por_minuto", 1, 600)
    inteiro("colunas", 24, 96)
    inteiro("avancos_antes_do_corte", 0, 12)
    inteiro("registro_kb", 32, 32768)

    for campo in _LISTAS_DE_TEXTO:
        valor = cfg.get(campo)
        if not isinstance(valor, list) or not valor:
            cfg[campo] = list(PADRAO[campo])
        else:
            cfg[campo] = [str(v) for v in valor if str(v).strip()] or list(PADRAO[campo])

    if cfg.get("codepage") not in CODEPAGES:
        cfg["codepage"] = PADRAO["codepage"]

    if not isinstance(cfg.get("impressora_padrao"), str):
        cfg["impressora_padrao"] = ""

    # Impressoras de rede: descarta qualquer item malformado em vez de estourar
    # depois, na hora de imprimir, quando o cliente já está esperando o cupom.
    limpas: List[Dict[str, Any]] = []
    for item in cfg.get("impressoras_rede") or []:
        if not isinstance(item, dict):
            continue
        host = str(item.get("host") or "").strip()
        if not host:
            continue
        try:
            porta = max(1, min(65535, int(item.get("porta", 9100))))
        except (TypeError, ValueError):
            porta = 9100
        limpas.append({
            "nome": str(item.get("nome") or host).strip()[:60],
            "host": host[:120],
            "porta": porta,
        })
    cfg["impressoras_rede"] = limpas

    for campo in ("cortar_por_padrao", "abrir_gaveta_apos_imprimir",
                  "iniciar_com_sistema", "abrir_janela", "fechar_minimiza",
                  "registrar_em_arquivo"):
        cfg[campo] = bool(cfg.get(campo, PADRAO[campo]))

    return cfg


def carregar() -> Dict[str, Any]:
    """Lê a configuração do disco, completando o que faltar com os padrões."""
    cfg: Dict[str, Any] = json.loads(json.dumps(PADRAO))   # cópia profunda barata
    try:
        with open(caminho_config(), "r", encoding="utf-8") as arquivo:
            gravado = json.load(arquivo)
        if isinstance(gravado, dict):
            cfg.update({k: v for k, v in gravado.items() if k in PADRAO})
    except FileNotFoundError:
        pass
    except Exception as erro:
        print(f"[config] arquivo ignorado por erro de leitura: {erro}", file=sys.stderr)
    return _sanear(cfg)


def carregar_de(cru: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sane uma configuração que já está na memória, sem tocar no disco.

    É o que a janela usa depois de o operador digitar: uma porta 70000 ou uma
    página de código inventada viram o padrão ali mesmo, antes de serem
    gravadas — em vez de derrubarem a ponte no próximo login.
    """
    cfg: Dict[str, Any] = json.loads(json.dumps(PADRAO))
    cfg.update({k: v for k, v in cru.items() if k in PADRAO})
    return _sanear(cfg)


def salvar(cfg: Dict[str, Any]) -> str:
    """
    Grava a configuração e devolve o caminho.

    Escreve num temporário e renomeia: se faltar energia no meio da gravação —
    coisa banal num balcão — o arquivo antigo continua íntegro, em vez de virar
    um JSON pela metade que impede a ponte de subir no próximo login.
    """
    destino = caminho_config()
    temporario = destino + ".tmp"
    dados = {chave: cfg.get(chave, PADRAO[chave]) for chave in PADRAO}
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.flush()
        os.fsync(arquivo.fileno())
    os.replace(temporario, destino)
    return destino


def origens_abertas(cfg: Dict[str, Any]) -> bool:
    return "*" in cfg.get("origens_permitidas", [])
