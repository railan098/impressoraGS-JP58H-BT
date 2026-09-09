#!/usr/bin/env bash
#
# Gera o pacote .deb da Ponte de Impressão Menuxy.
#
# O pacote é "all" (independente de arquitetura) porque tudo aqui é Python
# puro — o mesmo .deb serve amd64, arm64 e armhf. É a diferença entre um
# arquivo e três, e entre funcionar num Raspberry Pi de balcão ou não.
#
# Uso:
#     ./empacotar/linux/gerar_deb.sh
#
# Sai em:  dist/menuxy-ponte_<versao>_all.deb
#
# Instalar:      sudo apt install ./dist/menuxy-ponte_*_all.deb
# Desinstalar:   sudo apt remove menuxy-ponte
#
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"

VERSAO="$(python3 -c "import sys; sys.path.insert(0,'.'); from ponte_menuxy import VERSAO; print(VERSAO)")"
PACOTE="menuxy-ponte"
ARQ="dist/${PACOTE}_${VERSAO}_all.deb"
MONTAGEM="$(mktemp -d)"
trap 'rm -rf "$MONTAGEM"' EXIT

echo "==> Montando ${PACOTE} ${VERSAO}"

# --------------------------------------------------------------------------
# Árvore de arquivos
# --------------------------------------------------------------------------
install -d "$MONTAGEM/DEBIAN"
install -d "$MONTAGEM/usr/lib/$PACOTE"
install -d "$MONTAGEM/usr/bin"
install -d "$MONTAGEM/usr/share/applications"
install -d "$MONTAGEM/usr/share/doc/$PACOTE"
install -d "$MONTAGEM/usr/share/man/man1"
install -d "$MONTAGEM/lib/udev/rules.d"

# O pacote Python, sem __pycache__ (bytecode da máquina de build não serve
# para a de destino, e ainda quebraria a soma de verificação do dpkg).
cp -r ponte_menuxy "$MONTAGEM/usr/lib/$PACOTE/"
find "$MONTAGEM/usr/lib/$PACOTE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$MONTAGEM/usr/lib/$PACOTE" -name '*.pyc' -delete 2>/dev/null || true

# Ícones nos tamanhos que os ambientes gráficos procuram.
for tam in 32 48 64 128 256; do
    install -d "$MONTAGEM/usr/share/icons/hicolor/${tam}x${tam}/apps"
    install -m 644 "ponte_menuxy/recursos/icone-${tam}.png" \
        "$MONTAGEM/usr/share/icons/hicolor/${tam}x${tam}/apps/${PACOTE}.png"
done

# Regra udev: dá acesso à impressora USB sem sudo. Vai em /lib/udev porque é
# regra fornecida por pacote; /etc fica reservado ao que o administrador edita.
install -m 644 ferramenta_cli/99-impressora-termica.rules \
    "$MONTAGEM/lib/udev/rules.d/99-impressora-termica.rules"

install -m 644 README.md "$MONTAGEM/usr/share/doc/$PACOTE/"
cp -r docs "$MONTAGEM/usr/share/doc/$PACOTE/"
cp -r exemplos "$MONTAGEM/usr/share/doc/$PACOTE/"

# --------------------------------------------------------------------------
# Executável
# --------------------------------------------------------------------------
cat > "$MONTAGEM/usr/bin/$PACOTE" <<'EOF'
#!/bin/sh
# Ponte de Impressão Menuxy — invólucro do pacote.
# PYTHONPATH em vez de instalar em dist-packages: o pacote fica contido em
# /usr/lib/menuxy-ponte e não polui o Python do sistema.
PYTHONPATH="/usr/lib/menuxy-ponte${PYTHONPATH:+:$PYTHONPATH}" \
    exec python3 -m ponte_menuxy "$@"
EOF
chmod 755 "$MONTAGEM/usr/bin/$PACOTE"

# --------------------------------------------------------------------------
# Atalho no menu de aplicativos
# --------------------------------------------------------------------------
cat > "$MONTAGEM/usr/share/applications/$PACOTE.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Ponte de Impressão Menuxy
GenericName=Ponte de impressão
Comment=Deixa o seu sistema web imprimir na impressora deste computador
Exec=$PACOTE
Icon=$PACOTE
Terminal=false
Categories=Utility;Office;Printing;
Keywords=impressora;cupom;termica;menuxy;escpos;pdv;
StartupNotify=false
EOF
chmod 644 "$MONTAGEM/usr/share/applications/$PACOTE.desktop"

# --------------------------------------------------------------------------
# Manual
# --------------------------------------------------------------------------
cat > "$MONTAGEM/usr/share/man/man1/$PACOTE.1" <<EOF
.TH MENUXY-PONTE 1 "$(LC_ALL=C date '+%d %B %Y')" "$VERSAO" "Ponte de Impressão Menuxy"
.SH NOME
menuxy\\-ponte \\- ponte de impressão local para sistemas web
.SH SINOPSE
.B menuxy-ponte
.RI [ opções ]
.SH DESCRIÇÃO
Sobe um servidor HTTP em 127.0.0.1 que aceita texto e o entrega à impressora
desta máquina, em ESC/POS. Existe porque nenhum navegador consegue falar com
uma impressora térmica.
.SH OPÇÕES
.TP
.B \\-\\-listar
Lista as impressoras que a ponte enxerga e sai.
.TP
.B \\-\\-testar
Imprime um cupom de teste e sai.
.TP
.B \\-\\-diagnostico
Relatório completo para o suporte. Não imprime nada.
.TP
.BI \\-\\-origens " URL..."
Endereços que podem mandar imprimir.
.TP
.BI \\-\\-impressora " ID"
Impressora desta máquina, ex.\\& sistema:Termica58.
.TP
.BI \\-\\-iniciar\\-com\\-sistema " sim|nao"
Liga ou desliga o início automático.
.TP
.B \\-\\-sem\\-janela
Só o servidor, sem interface. É o modo serviço.
.SH ARQUIVOS
.TP
.I ~/.config/menuxy-ponte/ponte_config.json
Configuração.
.TP
.I ~/.config/menuxy-ponte/ponte.log
Registro.
.SH VEJA TAMBÉM
/usr/share/doc/menuxy-ponte/docs/
EOF
gzip -9n "$MONTAGEM/usr/share/man/man1/$PACOTE.1"

# --------------------------------------------------------------------------
# Metadados
# --------------------------------------------------------------------------
TAMANHO="$(du -sk "$MONTAGEM" | cut -f1)"

cat > "$MONTAGEM/DEBIAN/control" <<EOF
Package: $PACOTE
Version: $VERSAO
Section: utils
Priority: optional
Architecture: all
Maintainer: Railan Alves <Saobentomaqsbm@gmail.com>
Installed-Size: $TAMANHO
Depends: python3 (>= 3.8), python3-tk
Recommends: cups-client, python3-usb
Suggests: python3-serial
Homepage: https://github.com/railan098/impressoraGS-JP58H-BT
Description: Ponte de impressão local para sistemas web (ESC/POS)
 Servidor HTTP local que permite a um sistema web imprimir na impressora
 térmica deste computador. Nenhum navegador consegue fazer isso sozinho: a
 WebUSB bloqueia dispositivos de classe 7 e window.print() manda a página
 renderizada, não ESC/POS.
 .
 Cobre cinco caminhos até o papel: impressora instalada no CUPS, USB direta
 sem driver, USB pelo driver do Windows, impressora de rede RAW 9100 e porta
 serial.
 .
 Escuta apenas em 127.0.0.1, com lista de origens permitidas e teto de
 trabalhos por minuto. Não tem acesso a dado de negócio: o que entra é texto
 para imprimir, o que sai é o resultado.
EOF

cat > "$MONTAGEM/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

if [ "$1" = "configure" ]; then
    # Recarrega as regras para a impressora USB já valer sem religar a máquina.
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules >/dev/null 2>&1 || true
        udevadm trigger --subsystem-match=usb >/dev/null 2>&1 || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
    fi

    cat <<'FIM'

  Ponte de Impressão Menuxy instalada.

    menuxy-ponte --listar        veja as impressoras que ela enxerga
    menuxy-ponte                 abra a janela de configuração

  Antes de usar em produção, feche a lista de origens:

    menuxy-ponte --origens https://menuxy.alvesprotect.app.br

  Para imprimir por USB direta sem sudo, entre no grupo lp e refaça o login:

    sudo usermod -aG lp $USER

FIM
fi
exit 0
EOF
chmod 755 "$MONTAGEM/DEBIAN/postinst"

cat > "$MONTAGEM/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
# A configuração e o registro ficam no perfil do usuário e NÃO são removidos:
# desinstalar para reinstalar uma versão nova não pode apagar a impressora
# escolhida no balcão. Para limpar de fato:
#   rm -rf ~/.config/menuxy-ponte
exit 0
EOF
chmod 755 "$MONTAGEM/DEBIAN/prerm"

cat > "$MONTAGEM/usr/share/doc/$PACOTE/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: menuxy-ponte
Source: https://github.com/railan098/impressoraGS-JP58H-BT

Files: *
Copyright: $(date +%Y) Railan Alves
License: MIT
EOF

# --------------------------------------------------------------------------
# Empacotar
# --------------------------------------------------------------------------
mkdir -p dist
find "$MONTAGEM" -type d -exec chmod 755 {} +
find "$MONTAGEM/usr/lib" -type f -exec chmod 644 {} +

# Soma de verificação de tudo que não é metadado — o dpkg usa para detectar
# arquivo alterado à mão depois da instalação.
( cd "$MONTAGEM" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
    | xargs -0 md5sum > DEBIAN/md5sums )

fakeroot dpkg-deb --build --root-owner-group "$MONTAGEM" "$ARQ" >/dev/null

echo "==> $ARQ"
dpkg-deb --info "$ARQ" | sed -n '2,12p'
echo
echo "Instalar:     sudo apt install ./$ARQ"
echo "Desinstalar:  sudo apt remove menuxy-ponte"
