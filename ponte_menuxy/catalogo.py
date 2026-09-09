# -*- coding: utf-8 -*-
"""
O catálogo: junta os cinco backends numa lista só e resolve identificadores.

Um identificador é ``<prefixo>:<alvo>`` — ``sistema:Termica58``,
``usb:0416:5011``, ``rede:192.168.0.50:9100``. O prefixo diz por qual caminho o
trabalho vai sair, e é ele que o sistema guarda no cadastro da estação.

**A resolução aceita três formas**, porque as três chegam de verdade:

* o id completo (``sistema:Termica58``) — o que o Menuxy manda;
* o nome nu (``Termica58``) — o que alguém digita à mão ou o que veio de uma
  versão antiga do sistema, resolvido contra a lista real;
* vazio — usa a configurada nesta máquina; não havendo, a padrão do sistema.

E ela **confere contra a lista real** antes de qualquer uso. Isso transforma um
erro de digitação em mensagem clara e faz um nome forjado não chegar a lugar
nenhum: ``Termica; rm -rf /`` é só um nome que não existe.
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional, Tuple

from .backends import TODOS, rede, serial_, sistema, usb_direta, usbprint

# Prefixo -> módulo do backend
POR_PREFIXO = {
    "sistema": sistema,
    "usb": usb_direta,
    "usbprint": usbprint,
    "rede": rede,
    "serial": serial_,
}

# --------------------------------------------------------------------------- #
#  Cache curto
# --------------------------------------------------------------------------- #
# Listar impressoras custa: no Linux são dois `lpstat` (processos externos), e
# no USB é uma varredura do barramento. O agente do Menuxy sonda a ponte a cada
# 3 segundos; sem cache isso vira uma tempestade de processos num computador de
# balcão que já é fraco. Cinco segundos é curto o bastante para uma impressora
# recém-ligada aparecer quase na hora.
_VALIDADE_S = 5.0
_cache: Optional[Tuple[float, List[Dict[str, Any]], Optional[str]]] = None
_trava = threading.Lock()


def invalidar() -> None:
    """Força a próxima consulta a ir ao sistema. Usado pelo botão 'Procurar'."""
    global _cache
    with _trava:
        _cache = None


def listar(cfg: Dict[str, Any], forcar: bool = False) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Todas as impressoras visíveis, dos cinco caminhos, e qual é a padrão.

    Um backend que quebre é registrado e ignorado — nunca derruba a listagem
    inteira. Uma máquina sem CUPS ainda precisa enxergar as impressoras de rede.
    """
    global _cache
    agora = time.monotonic()
    with _trava:
        if _cache and not forcar and (agora - _cache[0]) < _VALIDADE_S:
            return _cache[1], _cache[2]

    encontradas: List[Dict[str, Any]] = []
    for backend in TODOS:
        try:
            if backend.disponivel():
                encontradas.extend(backend.listar(cfg))
        except Exception as erro:
            print(f"[catalogo] backend {backend.TIPO} falhou ao listar: {erro}")

    padrao = None
    try:
        padrao = sistema.padrao_do_sistema()
    except Exception:
        pass

    with _trava:
        _cache = (agora, encontradas, padrao)
    return encontradas, padrao


def backends_ativos() -> List[str]:
    return [b.TIPO for b in TODOS if b.disponivel()]


# --------------------------------------------------------------------------- #
#  Resolução
# --------------------------------------------------------------------------- #

class ImpressoraDesconhecida(ValueError):
    """O identificador não corresponde a nada nesta máquina."""


def resolver(identificador: str, cfg: Dict[str, Any]) -> Tuple[Any, Any, str]:
    """
    Descobre a qual impressora um identificador se refere.

    Devolve ``(modulo_do_backend, alvo, rotulo)``, ou levanta
    ``ImpressoraDesconhecida`` com uma frase que o operador entende — "não
    existe nesta máquina, disponíveis: ..." ajuda mais do que um código de erro.
    """
    lista, padrao = listar(cfg)
    por_id = {item["id"]: item for item in lista}

    escolhido = ((identificador or "").strip()
                 or str(cfg.get("impressora_padrao") or "").strip()
                 or (padrao or ""))
    if not escolhido:
        raise ImpressoraDesconhecida(
            "nenhuma impressora escolhida e o sistema não tem uma padrão. "
            "Escolha uma na janela da ponte ou rode: menuxy-ponte --impressora <id>")

    if escolhido in por_id:
        item = por_id[escolhido]
        backend = POR_PREFIXO[item["tipo"]]
        return backend, backend.alvo_de(escolhido), item["rotulo"]

    # Endereço direto, sem cadastro: rede: e serial: aceitam alvos que não
    # estão na lista, porque não há como listá-los sem varrer a rede.
    prefixo = escolhido.split(":", 1)[0] if ":" in escolhido else ""
    for modulo in (rede, serial_):
        if prefixo == modulo.TIPO and modulo.aceita_identificador(escolhido):
            return modulo, modulo.alvo_de(escolhido), escolhido

    # Nome nu: procura entre as do sistema antes de desistir.
    candidato = f"sistema:{escolhido}"
    if candidato in por_id:
        item = por_id[candidato]
        return sistema, sistema.alvo_de(candidato), item["rotulo"]

    disponiveis = ", ".join(item["id"] for item in lista) or "nenhuma"
    raise ImpressoraDesconhecida(
        f"a impressora '{escolhido}' não existe nesta máquina. Disponíveis: {disponiveis}")


def imprimir(identificador: str, dados: bytes, cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Resolve e envia. Devolve ``(ok, rótulo da impressora)`` ou ``(False, motivo)``.

    Levanta ``ImpressoraDesconhecida`` — e só ela — quando o identificador não
    resolve; o servidor transforma isso em 404, que é diferente de "a impressora
    existe mas falhou" (500).
    """
    backend, alvo, rotulo = resolver(identificador, cfg)
    try:
        ok, detalhe = backend.imprimir(alvo, dados)
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"
    return ok, (rotulo if ok else detalhe)
