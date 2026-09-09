#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cliente.py — como falar com a ponte a partir de Python.

Serve para um PDV de mesa, um script de fechamento de caixa, um robô que
imprime a comanda quando chega um pedido no WhatsApp — qualquer coisa que não
seja uma página web.

Só usa a biblioteca padrão. Copie o arquivo e use.

    python3 exemplos/python/cliente.py --status
    python3 exemplos/python/cliente.py --exemplo
    python3 exemplos/python/cliente.py --texto "Ola" --impressora sistema:Termica58
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class Ponte:
    """Cliente da Ponte de Impressão. Nenhum método levanta exceção de rede."""

    def __init__(self, base: str = "http://127.0.0.1:9100",
                 impressora: str = "", colunas: int = 32, prazo: float = 8.0) -> None:
        self.base = base.rstrip("/")
        self.impressora = impressora
        self.colunas = colunas
        self.prazo = prazo

    # ------------------------------------------------------------ transporte
    def _chamar(self, caminho: str, corpo: Optional[Dict[str, Any]] = None,
                prazo: Optional[float] = None) -> Dict[str, Any]:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        pedido = urllib.request.Request(self.base + caminho, data=dados,
                                        method="POST" if dados else "GET")
        if dados:
            pedido.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(pedido, timeout=prazo or self.prazo) as resposta:
                return json.loads(resposta.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as erro:
            try:
                return json.loads(erro.read().decode("utf-8") or "{}")
            except Exception:
                return {"ok": False, "erro": f"HTTP {erro.code}"}
        except Exception as erro:
            return {"ok": False, "erro": f"a ponte não respondeu: {erro}"}

    # ----------------------------------------------------------------- rotas
    def status(self) -> Dict[str, Any]:
        return self._chamar("/status", prazo=3.0)

    def online(self) -> bool:
        return self.status().get("ok") is True

    def impressoras(self) -> List[Dict[str, Any]]:
        return self._chamar("/impressoras", prazo=3.0).get("impressoras", [])

    def imprimir(self, texto: str, cortar: bool = True,
                 impressora: str = "") -> Dict[str, Any]:
        return self._chamar("/imprimir", {
            "texto": texto,
            "cortar": cortar,
            "colunas": self.colunas,
            "impressora": impressora or self.impressora or None,
        })

    def raw(self, dados: bytes, impressora: str = "") -> Dict[str, Any]:
        """ESC/POS já montado — logotipo, QR code, comandos do seu modelo."""
        return self._chamar("/raw", {
            "base64": base64.b64encode(dados).decode("ascii"),
            "impressora": impressora or self.impressora or None,
        })

    def gaveta(self, impressora: str = "") -> Dict[str, Any]:
        return self._chamar("/gaveta", {"impressora": impressora or self.impressora or None})

    # ------------------------------------------------------------- ajudantes
    def linha(self, esquerda: str, direita: str, preenchimento: str = " ") -> str:
        """'Produto' à esquerda, '10,00' à direita. Quem é cortado é o rótulo."""
        espaco = self.colunas - len(direita) - 1
        if espaco < 1:
            return (esquerda + " " + direita)[:self.colunas]
        esquerda = esquerda[:espaco]
        meio = self.colunas - len(esquerda) - len(direita)
        return esquerda + preenchimento * max(0, meio) + direita

    def centro(self, texto: str) -> str:
        return texto[:self.colunas].center(self.colunas).rstrip()

    def risco(self, caractere: str = "-") -> str:
        return caractere * self.colunas


def cupom_de_exemplo(ponte: Ponte) -> str:
    """O cupom que o ``--exemplo`` imprime. Copie e adapte."""
    linhas = [
        ponte.centro("MINHA LOJA"),
        ponte.centro("Rua Exemplo, 100"),
        ponte.centro("(11) 90000-0000"),
        ponte.risco(),
        ponte.linha("Pedido", "#1234"),
        ponte.linha("Data", "09/09/2026 09:41"),
        ponte.risco(),
        ponte.linha("Coca-Cola 2L", "25,00"),
        "  2 x 12,50",
        ponte.linha("Pizza Calabresa", "59,90"),
        "  1 x 59,90",
        ponte.risco(),
        ponte.linha("TOTAL", "R$ 84,90"),
        ponte.risco("="),
        "",
        ponte.centro("Obrigado pela preferencia!"),
        "",
    ]
    return "\n".join(linhas)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente de exemplo da Ponte de Impressão.")
    parser.add_argument("--base", default="http://127.0.0.1:9100")
    parser.add_argument("--impressora", default="", help="ex.: sistema:Termica58")
    parser.add_argument("--colunas", type=int, default=32, help="32 para 58 mm, 48 para 80 mm")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--texto", help="imprime este texto")
    parser.add_argument("--exemplo", action="store_true", help="imprime um cupom de exemplo")
    parser.add_argument("--gaveta", action="store_true")
    args = parser.parse_args()

    ponte = Ponte(args.base, args.impressora, args.colunas)

    if args.status or not any((args.listar, args.texto, args.exemplo, args.gaveta)):
        situacao = ponte.status()
        if not situacao.get("ok"):
            print(f"a ponte não respondeu em {args.base}")
            print("  ela está aberta na máquina? procure o ícone na barra de tarefas")
            return 1
        print(json.dumps(situacao, ensure_ascii=False, indent=2))
        return 0

    if args.listar:
        for item in ponte.impressoras():
            print(f"{item['nome']:40} {item.get('tipo',''):9} {item.get('rotulo','')}")
        return 0

    if args.gaveta:
        resultado = ponte.gaveta()
    else:
        texto = cupom_de_exemplo(ponte) if args.exemplo else (args.texto or "")
        resultado = ponte.imprimir(texto)

    if resultado.get("ok"):
        print(f"impresso em {resultado.get('impressora','')} ({resultado.get('bytes',0)} bytes)")
        return 0
    print(f"falhou: {resultado.get('erro','motivo desconhecido')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
