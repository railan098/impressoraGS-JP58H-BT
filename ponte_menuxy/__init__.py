# -*- coding: utf-8 -*-
"""
Ponte de Impressão Menuxy — servidor local que dá à web acesso à impressora.

O pacote está dividido assim:

    config.py        onde a configuração mora e como ela é saneada
    escpos.py        texto  ->  bytes que a impressora térmica entende
    backends/        os cinco caminhos até o papel (ver backends/__init__.py)
    catalogo.py      junta os cinco num catálogo só e resolve identificadores
    servidor.py      o HTTP local, com as travas de segurança
    inicializacao.py iniciar junto com o sistema e atalhos na área de trabalho
    janela.py        a janela de configuração (opcional; tkinter)
    cli.py           a linha de comando

Nada aqui importa `tkinter`, `usb` ou `serial` no topo do módulo: são todos
opcionais, e a ponte precisa subir numa máquina que não tenha nenhum deles.
"""

VERSAO = "3.0.0"
NOME = "Ponte de Impressão Menuxy"
NOME_CURTO = "menuxy-ponte"

# Endereço padrão do sistema que usa esta ponte. O instalador pergunta e grava
# na lista de origens permitidas; deixar aberto é o erro fácil deste projeto.
SISTEMA_PADRAO = "https://menuxy.alvesprotect.app.br"

__all__ = ["VERSAO", "NOME", "NOME_CURTO", "SISTEMA_PADRAO"]
