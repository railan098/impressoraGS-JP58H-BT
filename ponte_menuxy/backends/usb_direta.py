# -*- coding: utf-8 -*-
"""
Backend ``usb:`` — impressora plugada **sem driver**, via libusb/pyusb.

É o caminho de quem comprou uma genérica de 58 mm que o Windows não reconhece,
e o que herdou a engenharia reversa da GS-JP58H feita em
``ferramenta_cli/imprime_termica.py``. Três coisas foram descobertas ali e não
devem ser refeitas por suposição:

1. **Filtre pela classe 7 no dispositivo *e* nas interfaces.** Muitas térmicas
   declaram ``bDeviceClass = 0`` ("classe definida na interface") e só revelam
   a classe 7 (Printer) na interface. Olhar apenas o descritor do dispositivo
   perde metade dos modelos — inclusive a GS-JP58H.
2. **Solte o driver do kernel antes do claim.** No Linux o ``usblp`` costuma
   ter reivindicado o aparelho; sem soltar, o claim falha com "Resource busy".
3. **Nunca fixe o endereço do endpoint em ``0x01``.** Ele varia por fabricante.
   Descubra pelo descritor procurando o endpoint bulk de saída.

``pyusb`` é opcional. Sem ele este backend simplesmente não aparece no
catálogo, e todo o resto da ponte continua funcionando.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Tuple

TIPO = "usb"

CLASSE_IMPRESSORA = 7          # classe 7 = Printer, definida pelo usb.org
TEMPO_LIMITE_MS = 15000


def disponivel() -> bool:
    try:
        import usb.core  # noqa: F401
        return True
    except Exception:
        return False


def _texto(dispositivo, atributo: str) -> str:
    """
    Lê uma string do descritor sem deixar a leitura derrubar a listagem.

    Ler ``product`` exige uma transferência de controle, e ela falha quando
    outro processo tem o aparelho, quando falta permissão (Linux sem a regra
    udev) ou quando o firmware é simplesmente mal-educado. Nenhum desses casos
    pode impedir a impressora de aparecer na lista.
    """
    try:
        return str(getattr(dispositivo, atributo) or "").strip()
    except Exception:
        return ""


def _eh_impressora(dispositivo) -> bool:
    if dispositivo.bDeviceClass == CLASSE_IMPRESSORA:
        return True
    try:
        for configuracao in dispositivo:
            for interface in configuracao:
                if interface.bInterfaceClass == CLASSE_IMPRESSORA:
                    return True
    except Exception:
        # Sem permissão para ler a configuração. No Linux é o sintoma clássico
        # de faltar a regra udev — documentado em docs/SOLUCAO-DE-PROBLEMAS.md.
        return False
    return False


def listar(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not disponivel():
        return []
    import usb.core

    achados: List[Dict[str, Any]] = []
    try:
        for dispositivo in usb.core.find(find_all=True):
            if not _eh_impressora(dispositivo):
                continue
            rotulo = (_texto(dispositivo, "product")
                      or _texto(dispositivo, "manufacturer")
                      or f"USB {dispositivo.idVendor:04x}:{dispositivo.idProduct:04x}")
            achados.append({
                "id": f"usb:{dispositivo.idVendor:04x}:{dispositivo.idProduct:04x}",
                "rotulo": f"{rotulo} (USB direta)",
                "tipo": TIPO,
                "papel": "58mm",
                "detalhe": "libusb no endpoint bulk-out",
            })
    except Exception as erro:
        print(f"[usb] falha ao listar: {erro}", file=sys.stderr)
    return achados


def alvo_de(identificador: str) -> Tuple[int, int]:
    """``usb:0416:5011`` -> ``(0x0416, 0x5011)``."""
    _, vid, pid = identificador.split(":")
    return int(vid, 16), int(pid, 16)


def imprimir(alvo: Tuple[int, int], dados: bytes) -> Tuple[bool, str]:
    if not disponivel():
        return False, "pyusb não está instalado nesta máquina (pip install pyusb)"
    import usb.core
    import usb.util

    vid, pid = alvo
    dispositivo = usb.core.find(idVendor=vid, idProduct=pid)
    if dispositivo is None:
        return False, f"dispositivo {vid:04x}:{pid:04x} não encontrado — cabo solto ou impressora desligada?"

    interface_reivindicada = None
    try:
        # 1) Soltar o driver do kernel (Linux/macOS). No Windows a chamada não
        #    existe e a exceção é o comportamento esperado.
        try:
            if dispositivo.is_kernel_driver_active(0):
                dispositivo.detach_kernel_driver(0)
        except Exception:
            pass

        # 2) Só configure se ainda não estiver configurado. Chamar
        #    set_configuration() num aparelho já configurado reinicia o
        #    pipeline e, em algumas térmicas, come o primeiro cupom.
        try:
            configuracao = dispositivo.get_active_configuration()
        except Exception:
            dispositivo.set_configuration()
            configuracao = dispositivo.get_active_configuration()

        # 3) A interface de impressora, não a primeira que aparecer.
        interface = None
        for candidata in configuracao:
            if candidata.bInterfaceClass == CLASSE_IMPRESSORA:
                interface = candidata
                break
        if interface is None:
            interface = configuracao[(0, 0)]

        # 4) O endereço do endpoint varia por fabricante — descubra, não fixe.
        saida = usb.util.find_descriptor(
            interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        if saida is None:
            return False, "a impressora não expõe endpoint bulk de saída"

        interface_reivindicada = interface
        saida.write(dados, timeout=TEMPO_LIMITE_MS)
        return True, f"{len(dados)} bytes"

    except Exception as erro:
        return False, _explicar(erro)
    finally:
        try:
            if interface_reivindicada is not None:
                usb.util.release_interface(dispositivo, interface_reivindicada)
        except Exception:
            pass
        try:
            usb.util.dispose_resources(dispositivo)
        except Exception:
            pass


def _explicar(erro: Exception) -> str:
    """
    Traduz os erros de libusb que o operador vai encontrar de verdade.

    "USBError: [Errno 13] Access denied" não diz a ninguém que falta uma regra
    udev. A tradução aqui é a diferença entre uma ligação para o suporte e um
    problema resolvido em dois minutos.
    """
    texto = f"{erro}".lower()
    if "access" in texto or "permission" in texto or "errno 13" in texto:
        if sys.platform.startswith("win"):
            return ("acesso negado: o driver da impressora é o usbprint.sys. "
                    "Use o identificador 'usbprint:' desta mesma impressora, ou "
                    "troque o driver por WinUSB com o Zadig.")
        return ("acesso negado: falta a regra udev. Instale "
                "ferramenta_cli/99-impressora-termica.rules em /etc/udev/rules.d/ "
                "(veja docs/SOLUCAO-DE-PROBLEMAS.md)")
    if "busy" in texto or "errno 16" in texto:
        return ("o dispositivo está ocupado: outro programa — ou o driver usblp "
                "do kernel — tem a impressora. Feche o outro programa ou rode "
                "'sudo modprobe -r usblp'.")
    if "no such device" in texto or "errno 19" in texto:
        return "a impressora sumiu do barramento durante o envio (cabo ou energia)"
    if "timeout" in texto or "timed out" in texto:
        return ("a impressora não confirmou o recebimento a tempo: sem papel, "
                "tampa aberta ou cabeça superaquecida")
    return f"{type(erro).__name__}: {erro}"
