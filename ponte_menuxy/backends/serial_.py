# -*- coding: utf-8 -*-
"""
Backend ``serial:`` — impressora de porta serial ou conversor USB-serial.

Equipamento antigo de balcão ainda é comum, e boa parte das térmicas de 58 mm
vem com uma variante serial. O protocolo é o mesmo ESC/POS; muda só o
transporte.

``pyserial`` é opcional — sem ele o backend some do catálogo. No Windows a
porta é ``COM3``; no Linux, ``/dev/ttyUSB0`` ou ``/dev/ttyS0``.

Identificador: ``serial:COM3:9600`` ou ``serial:/dev/ttyUSB0:19200``. A
velocidade padrão de fábrica da maioria das térmicas é 9600 8N1.

O nome do módulo tem sublinhado no fim para não colidir com o ``serial`` do
pyserial na hora do import.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

TIPO = "serial"

VELOCIDADE_PADRAO = 9600
TEMPO_ESCRITA_S = 20.0


def disponivel() -> bool:
    try:
        import serial  # noqa: F401
        return True
    except Exception:
        return False


def listar(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not disponivel():
        return []
    try:
        from serial.tools import list_ports
    except Exception:
        return []

    itens: List[Dict[str, Any]] = []
    try:
        for porta in list_ports.comports():
            if not _porta_real(porta):
                continue
            itens.append({
                "id": f"serial:{porta.device}:{VELOCIDADE_PADRAO}",
                "rotulo": f"{porta.description or porta.device} (serial)",
                "tipo": TIPO,
                "papel": "58mm",
                "detalhe": f"{porta.device} a {VELOCIDADE_PADRAO} 8N1",
            })
    except Exception:
        return []
    return itens


def _porta_real(porta) -> bool:
    """
    Descarta as portas seriais fantasma do Linux.

    O kernel registra ``/dev/ttyS0`` até ``ttyS31`` exista hardware ou não, e o
    pyserial devolve as 32. Sem este filtro, a lista de impressoras do balcão
    vira 32 linhas de lixo onde a impressora de verdade se perde.

    O sinal de que a porta é real: o pyserial conseguiu descobrir alguma coisa
    sobre ela — um VID/PID (conversor USB-serial) ou um hwid que não seja
    ``n/a``. As fantasmas não têm nem um nem outro.
    """
    if getattr(porta, "vid", None) is not None:
        return True
    hwid = (getattr(porta, "hwid", "") or "").strip().lower()
    return bool(hwid) and hwid != "n/a"


def alvo_de(identificador: str) -> Tuple[str, int]:
    """
    ``serial:/dev/ttyUSB0:19200`` -> ``("/dev/ttyUSB0", 19200)``.

    Divide pela direita porque o caminho no Windows pode conter dois-pontos
    (``serial:COM3:9600`` é fácil, mas ``\\\\.\\COM12`` também aparece).
    """
    resto = identificador.split(":", 1)[1]
    if ":" in resto:
        dispositivo, velocidade = resto.rsplit(":", 1)
        try:
            return dispositivo, int(velocidade)
        except ValueError:
            return resto, VELOCIDADE_PADRAO
    return resto, VELOCIDADE_PADRAO


def aceita_identificador(identificador: str) -> bool:
    try:
        dispositivo, _ = alvo_de(identificador)
        return bool(dispositivo)
    except IndexError:
        return False


def imprimir(alvo: Tuple[str, int], dados: bytes) -> Tuple[bool, str]:
    if not disponivel():
        return False, "pyserial não está instalado nesta máquina (pip install pyserial)"
    import serial

    dispositivo, velocidade = alvo
    try:
        with serial.Serial(dispositivo, velocidade, timeout=2,
                           write_timeout=TEMPO_ESCRITA_S) as porta:
            porta.write(dados)
            # Sem o flush, fechar a porta pode descartar o que ainda está no
            # buffer do driver — e o cupom sai pela metade.
            porta.flush()
        return True, f"{len(dados)} bytes"
    except serial.SerialTimeoutException:
        return False, (f"{dispositivo} não aceitou os bytes a tempo — controle de "
                       "fluxo (XON/XOFF ou RTS/CTS) diferente do esperado?")
    except serial.SerialException as erro:
        return False, f"{dispositivo}: {erro}"
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"
