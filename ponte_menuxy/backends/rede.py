# -*- coding: utf-8 -*-
"""
Backend ``rede:`` — impressora com placa de rede, protocolo RAW 9100.

Praticamente toda impressora de rede — térmica, matricial ou laser — aceita
bytes crus numa conexão TCP na porta 9100. O protocolo é o "JetDirect" da HP,
que virou padrão de fato: abre o socket, escreve, fecha. Não há resposta, e é
por isso que ele é tão universal.

**A ponte não varre a rede.** Varredura é lenta, dispara alarme de antivírus e
adivinha errado. As impressoras de rede são declaradas pelo operador na aba
Impressoras da janela, ou direto no ``ponte_config.json``::

    "impressoras_rede": [
      {"nome": "Cozinha", "host": "192.168.0.50", "porta": 9100}
    ]

Elas também podem ser usadas sem cadastro, pelo identificador direto::

    rede:192.168.0.50:9100
"""

from __future__ import annotations

import socket
from typing import Any, Dict, List, Tuple

TIPO = "rede"

TEMPO_CONEXAO_S = 4.0
TEMPO_ENVIO_S = 20.0
PORTA_RAW = 9100


def disponivel() -> bool:
    """Sempre: só precisa de socket, que é da biblioteca padrão."""
    return True


def listar(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    itens: List[Dict[str, Any]] = []
    for declarada in cfg.get("impressoras_rede") or []:
        host = declarada.get("host")
        porta = int(declarada.get("porta", PORTA_RAW))
        nome = declarada.get("nome") or host
        itens.append({
            "id": f"rede:{host}:{porta}",
            "rotulo": f"{nome} ({host}:{porta})",
            "tipo": TIPO,
            "papel": "80mm",
            "detalhe": "TCP RAW 9100 (JetDirect)",
        })
    return itens


def alvo_de(identificador: str) -> Tuple[str, int]:
    """``rede:192.168.0.50:9100`` -> ``("192.168.0.50", 9100)``."""
    partes = identificador.split(":")
    host = partes[1]
    porta = int(partes[2]) if len(partes) > 2 and partes[2] else PORTA_RAW
    return host, porta


def aceita_identificador(identificador: str) -> bool:
    """
    Aceita ``rede:host[:porta]`` mesmo sem cadastro prévio.

    Sem isto, imprimir numa impressora de rede exigiria cadastrá-la antes —
    o que atrapalha justamente o teste rápido de "essa aqui responde?".
    """
    try:
        host, porta = alvo_de(identificador)
        return bool(host) and 1 <= porta <= 65535
    except (IndexError, ValueError):
        return False


def imprimir(alvo: Tuple[str, int], dados: bytes) -> Tuple[bool, str]:
    host, porta = alvo
    try:
        with socket.create_connection((host, porta), timeout=TEMPO_CONEXAO_S) as conexao:
            conexao.settimeout(TEMPO_ENVIO_S)
            conexao.sendall(dados)
            # Meio segundo antes de fechar. Fechar o socket no mesmo instante do
            # último byte faz algumas placas de rede descartarem o fim do buffer,
            # e o cupom sai truncado no corte.
            conexao.settimeout(0.5)
            try:
                conexao.recv(1)
            except (socket.timeout, OSError):
                pass
        return True, f"{len(dados)} bytes"
    except socket.timeout:
        return False, f"{host}:{porta} não respondeu a tempo"
    except ConnectionRefusedError:
        return False, (f"{host}:{porta} recusou a conexão — a impressora está ligada "
                       "e o RAW 9100 habilitado?")
    except socket.gaierror:
        return False, f"não foi possível resolver o endereço '{host}'"
    except OSError as erro:
        return False, f"falha de rede até {host}:{porta} — {erro}"


def testar_alcance(host: str, porta: int = PORTA_RAW) -> Tuple[bool, str]:
    """Abre e fecha a conexão sem imprimir. É o botão 'Testar' do cadastro."""
    try:
        with socket.create_connection((host, porta), timeout=TEMPO_CONEXAO_S):
            return True, f"{host}:{porta} respondeu"
    except Exception as erro:
        return False, f"{host}:{porta} — {erro}"
