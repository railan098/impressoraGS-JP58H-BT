# -*- coding: utf-8 -*-
"""
Os caminhos até o papel.

Uma impressora chega ao computador de formas muito diferentes, e uma ponte que
cobre só uma delas deixa metade dos clientes de fora. Aqui existem cinco, e o
operador escolhe qual usar por impressora:

=================  =========================================================
Prefixo do id      Quando é o caminho certo
=================  =========================================================
``sistema:``       A impressora está **instalada** (spooler do Windows ou fila
                   do CUPS). Térmica, laser, jato de tinta, USB ou de rede —
                   qualquer coisa que apareça em "Impressoras" do sistema.
                   É o caminho preferido: usa a infraestrutura que já existe,
                   respeita permissão e fila.
``usb:``           Impressora **plugada sem driver** — a genérica que o Windows
                   não reconhece. Fala libusb no endpoint bulk-out.
``usbprint:``      Windows apenas: usa o próprio ``usbprint.sys`` que o Windows
                   anexou. Resolve o caso do Windows ARM, onde não dá para
                   trocar o driver pelo Zadig.
``rede:``          Impressora com placa de rede, no protocolo RAW 9100
                   (JetDirect). Declarada pelo operador, host e porta.
``serial:``        Impressora de porta serial ou conversor USB-serial —
                   equipamento antigo que ainda é comum em balcão.
=================  =========================================================

O prefixo não é enfeite: uma ``Termica58`` instalada e uma ``Termica58`` na USB
são coisas diferentes, e sem o prefixo o trabalho pode sair pelo caminho errado.

**Contrato de todo backend**

    disponivel() -> bool
    listar(cfg)  -> list[dict]  com {id, rotulo, tipo, papel, detalhe}
    imprimir(alvo, dados: bytes) -> (ok: bool, detalhe: str)

Nenhum deles pode levantar exceção para fora: um backend quebrado (pyusb
ausente, CUPS parado) precisa sumir do catálogo, não derrubar a ponte.
"""

from . import rede, serial_, sistema, usb_direta, usbprint

# A ordem importa: é a ordem em que as impressoras aparecem na lista, e
# `sistema` vem primeiro porque é o caminho certo para a maioria.
TODOS = (sistema, usb_direta, usbprint, rede, serial_)

__all__ = ["TODOS", "sistema", "usb_direta", "usbprint", "rede", "serial_"]
