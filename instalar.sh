#!/usr/bin/env bash
# =============================================================================
#  instalar.sh - Instalador da Impressora Termica 58mm (ESC/POS USB) no Linux
#  Debian / Ubuntu e derivados, amd64 e arm64
#
#  Uso:  chmod +x instalar.sh && ./instalar.sh
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"

VERDE='\033[0;32m'; VERM='\033[0;31m'; AMAR='\033[1;33m'; NEG='\033[1m'; FIM='\033[0m'
ok()   { echo -e "      ${VERDE}$1${FIM}"; }
aviso(){ echo -e "      ${AMAR}[AVISO] $1${FIM}"; }
erro() { echo -e "      ${VERM}[ERRO] $1${FIM}"; }

echo
echo "============================================================================"
echo -e "  ${NEG}INSTALADOR - IMPRESSORA TERMICA 58mm (SMX-JP58H / POS-58)${FIM}"
echo "  Comunicacao ESC/POS direta via USB - sem driver do fabricante"
echo "============================================================================"
echo
echo "  Sistema: $(uname -s) $(uname -r) / $(uname -m)"
echo

# ---------------------------------------------------------------- [1/6]
echo "[1/6] Instalando dependencias do sistema (pede a senha do sudo)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip python3-venv libusb-1.0-0 usbutils
    ok "libusb e Python instalados."
else
    aviso "Nao e um sistema apt. Instale manualmente: python3, python3-venv, libusb-1.0"
fi

# ---------------------------------------------------------------- [2/6]
echo
echo "[2/6] Criando o ambiente virtual (.venv)..."
if [ -x ".venv/bin/python" ]; then
    ok "Ja existe - reaproveitando."
else
    python3 -m venv .venv || { erro "Falha ao criar o venv."; exit 1; }
    ok "Criado."
fi
VPY="$PWD/.venv/bin/python"

# ---------------------------------------------------------------- [3/6]
echo
echo "[3/6] Instalando pyusb e python-escpos..."
"$VPY" -m pip install --quiet --upgrade pip
if "$VPY" -m pip install --quiet pyusb python-escpos; then
    ok "Instalados."
else
    erro "Falha ao instalar as dependencias Python."; exit 1
fi

# ---------------------------------------------------------------- [4/6]
echo
echo "[4/6] Instalando a regra udev (acesso sem sudo)..."
REGRA=/etc/udev/rules.d/99-impressora-termica.rules
if [ -f "99-impressora-termica.rules" ]; then
    sudo cp 99-impressora-termica.rules "$REGRA"
else
    sudo tee "$REGRA" >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5011", MODE="0666", GROUP="lp", TAG+="uaccess"
SUBSYSTEM=="usb", ENV{ID_USB_INTERFACES}=="*:07*:*", MODE="0666", GROUP="lp", TAG+="uaccess"
EOF
fi
sudo udevadm control --reload-rules && sudo udevadm trigger
ok "Regra instalada em $REGRA"

# ---------------------------------------------------------------- [5/6]
echo
echo "[5/6] Adicionando '$USER' ao grupo lp..."
if id -nG "$USER" | tr ' ' '\n' | grep -qx lp; then
    ok "Ja esta no grupo lp."
else
    sudo usermod -aG lp "$USER"
    aviso "Adicionado ao grupo lp - FACA LOGOUT/LOGIN para valer."
    aviso "Para testar agora sem deslogar, use: newgrp lp"
fi

# ---------------------------------------------------------------- [6/6]
echo
echo "[6/6] Procurando a impressora..."
echo
"$VPY" imprime_termica.py --listar

echo "============================================================================"
echo -e "  ${VERDE}${NEG}INSTALACAO CONCLUIDA.${FIM}"
echo "============================================================================"
echo
echo "  IMPORTANTE: desconecte e reconecte o cabo USB agora, para a regra"
echo "  udev ser aplicada ao dispositivo."
echo
echo "  Como usar:"
echo "    ./imprimir.sh                      # cupom de teste"
echo "    ./imprimir.sh --listar             # lista dispositivos"
echo "    ./imprimir.sh --texto 'Meu recibo'"
echo
read -rp "  Quer imprimir o cupom de teste agora? [s/N]: " RESP
if [[ "${RESP,,}" == "s" ]]; then
    echo
    "$VPY" imprime_termica.py
fi
echo
