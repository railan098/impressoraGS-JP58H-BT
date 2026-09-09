# -*- coding: utf-8 -*-
"""
Ponto de entrada do executável (PyInstaller).

Existe separado de ``ponte_menuxy/__main__.py`` por um detalhe do PyInstaller:
o script de entrada é executado como ``__main__`` solto, sem pacote pai, e ali
``from .cli import main`` falha com "attempted relative import with no known
parent package". Aqui o import é absoluto, e o ``__main__.py`` continua
servindo ao ``python -m ponte_menuxy``.
"""

import sys

from ponte_menuxy.cli import main

if __name__ == "__main__":
    sys.exit(main())
