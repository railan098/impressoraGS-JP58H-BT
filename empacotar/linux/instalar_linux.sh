#!/usr/bin/env bash
#
# Instalador da Ponte de Impressão Menuxy no Linux, a partir do código.
#
# Instala em ~/.local — SEM sudo. É de propósito: a ponte imprime com as
# permissões de quem está logado, que é quem tem acesso às filas do CUPS. Um
# serviço de sistema rodando como root não enxergaria essas filas.
#
# Se você prefere um pacote de verdade:  ./empacotar/linux/gerar_deb.sh
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESTINO="$HOME/.local/lib/menuxy-ponte"
BIN="$HOME/.local/bin"
AZUL='\033[1;34m'; VERDE='\033[1;32m'; AMARELO='\033[1;33m'; NADA='\033[0m'

titulo() { echo -e "\n${AZUL}==> $1${NADA}"; }
ok()     { echo -e "  ${VERDE}[ok]${NADA} $1"; }
aviso()  { echo -e "  ${AMARELO}[!]${NADA} $1"; }

echo "======================================================================"
echo "   Ponte de Impressão Menuxy — instalação no Linux"
echo "======================================================================"

# ---------------------------------------------------------------- 1. Python
titulo "Conferindo o Python"
if ! command -v python3 >/dev/null 2>&1; then
    echo "  Python 3 não encontrado. Instale com:  sudo apt install python3"
    exit 1
fi
VERSAO_PY="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
ok "Python $VERSAO_PY em $(command -v python3)"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)' || {
    echo "  A ponte precisa de Python 3.8 ou mais novo."; exit 1; }

# ------------------------------------------------------------- 2. Opcionais
titulo "Conferindo o que é opcional"
python3 -c 'import tkinter' 2>/dev/null \
    && ok "tkinter — a janela de configuração vai abrir" \
    || aviso "tkinter ausente: a ponte roda no terminal. Para a janela:  sudo apt install python3-tk"
command -v lp >/dev/null 2>&1 \
    && ok "CUPS (lp) — impressoras instaladas vão aparecer" \
    || aviso "CUPS ausente: sem ele só sobram os caminhos usb:, rede: e serial:. Instale:  sudo apt install cups-client"
python3 -c 'import usb.core' 2>/dev/null \
    && ok "pyusb — impressora USB sem driver vai aparecer" \
    || aviso "pyusb ausente (opcional): para USB direta,  pip3 install --user pyusb"

# ------------------------------------------------------------- 3. Copiar
titulo "Instalando em $DESTINO"
mkdir -p "$DESTINO" "$BIN"
rm -rf "$DESTINO/ponte_menuxy"
cp -r "$RAIZ/ponte_menuxy" "$DESTINO/"
find "$DESTINO" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
ok "pacote copiado"

cat > "$BIN/menuxy-ponte" <<EOF
#!/bin/sh
PYTHONPATH="$DESTINO\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m ponte_menuxy "\$@"
EOF
chmod +x "$BIN/menuxy-ponte"
ok "comando criado: $BIN/menuxy-ponte"

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) aviso "$BIN não está no seu PATH. Acrescente ao ~/.bashrc:"
       echo "        export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ------------------------------------------------------- 4. Regra udev (USB)
titulo "Acesso à impressora USB"
if [ -w /etc/udev/rules.d ] 2>/dev/null; then
    cp "$RAIZ/ferramenta_cli/99-impressora-termica.rules" /etc/udev/rules.d/
    udevadm control --reload-rules && udevadm trigger || true
    ok "regra udev instalada"
else
    aviso "para imprimir por USB direta sem sudo, rode uma vez:"
    echo "        sudo cp $RAIZ/ferramenta_cli/99-impressora-termica.rules /etc/udev/rules.d/"
    echo "        sudo udevadm control --reload-rules && sudo udevadm trigger"
    echo "        sudo usermod -aG lp \$USER    # depois faça logout e login"
fi

# ------------------------------------------------------------ 5. Origem
titulo "Quem pode mandar imprimir"
echo "  A ponte só aceita ordens dos endereços que você autorizar. Deixar"
echo "  aberto significa que qualquer site nesta máquina consegue gastar a sua"
echo "  bobina — não ler nada, a ponte não tem acesso a dado nenhum, mas gastar."
echo
read -r -p "  Endereço do seu sistema [https://menuxy.alvesprotect.app.br]: " ORIGEM
ORIGEM="${ORIGEM:-https://menuxy.alvesprotect.app.br}"
"$BIN/menuxy-ponte" --origens "$ORIGEM" >/dev/null
ok "somente $ORIGEM pode mandar imprimir"

# --------------------------------------------------------- 6. Início e atalho
titulo "Atalho e início automático"
"$BIN/menuxy-ponte" --criar-atalho | sed 's/^/  /'

read -r -p "  Iniciar a ponte junto com o computador? [S/n] " AUTO
if [ "${AUTO:-s}" != "n" ] && [ "${AUTO:-s}" != "N" ]; then
    "$BIN/menuxy-ponte" --iniciar-com-sistema sim | sed 's/^/  /'
fi

# ---------------------------------------------------------- 7. Impressoras
titulo "Impressoras que a ponte enxerga"
"$BIN/menuxy-ponte" --listar | sed 's/^/  /' || aviso "nenhuma impressora ainda — ligue-a e rode 'menuxy-ponte --listar'"

echo
echo "======================================================================"
echo -e "   ${VERDE}Instalada.${NADA}"
echo
echo "   menuxy-ponte               abre a janela e começa a servir"
echo "   menuxy-ponte --testar      imprime um cupom de teste"
echo "   menuxy-ponte --diagnostico relatório para o suporte"
echo
echo "   O atalho também está no menu de aplicativos e na área de trabalho."
echo "======================================================================"
