#!/usr/bin/env bash
#
# Gera um binário único do Linux com PyInstaller — para máquinas SEM Python.
#
# ATENÇÃO: o binário carrega a glibc da máquina onde foi construído. Gere na
# distribuição MAIS ANTIGA que os seus clientes usam; um binário feito no
# Ubuntu 24.04 não roda no 20.04, mas o contrário funciona.
#
# Na dúvida, prefira o .deb (./gerar_deb.sh): ele é Python puro, roda em
# qualquer arquitetura e não tem esse problema.
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

command -v pyinstaller >/dev/null 2>&1 || {
    echo "PyInstaller não encontrado.  pip3 install --user pyinstaller"; exit 1; }

VERSAO="$(python3 -c "import sys; sys.path.insert(0,'.'); from ponte_menuxy import VERSAO; print(VERSAO)")"
echo "==> Gerando binário da ponte $VERSAO"

pyinstaller --clean --noconfirm empacotar/PonteMenuxy.spec

SAIDA="dist/PonteMenuxy"
if [ -f "$SAIDA" ]; then
    mv "$SAIDA" "dist/menuxy-ponte-${VERSAO}-linux-$(uname -m)"
    SAIDA="dist/menuxy-ponte-${VERSAO}-linux-$(uname -m)"
fi

echo "==> $SAIDA  ($(du -h "$SAIDA" | cut -f1))"
echo "    Confira numa máquina sem Python:  ./$(basename "$SAIDA") --listar"
