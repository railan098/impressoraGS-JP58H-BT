# -*- mode: python ; coding: utf-8 -*-
"""
Receita do PyInstaller — serve para Windows e Linux.

    pyinstaller --clean --noconfirm empacotar/PonteMenuxy.spec

Decisões que importam:

* **onefile**: um arquivo só. O cliente baixa e dá duplo clique; não há pasta
  para alguém mover pela metade.
* **console=False**: sem a janela preta atrás do aplicativo. O diagnóstico
  continua saindo por ``--diagnostico`` e pelo registro em arquivo.
* **tkinter incluído explicitamente**: o PyInstaller às vezes não o detecta,
  porque a ponte só o importa dentro de funções — de propósito, para funcionar
  em Linux sem ele.
* **pyusb e pyserial em ``hiddenimports``, mas não obrigatórios**: se
  estiverem no ambiente de build, vão junto e o executável cobre USB e serial;
  se não, o executável sai menor e esses caminhos simplesmente não aparecem.
"""

import os
import sys

# SPECPATH é injetado pelo PyInstaller e aponta para a pasta deste arquivo.
# Usá-lo em vez de os.getcwd() faz a receita funcionar seja qual for a pasta de
# onde o build foi chamado.
RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
EH_WINDOWS = sys.platform.startswith("win")
EH_MAC = sys.platform == "darwin"

# O ícone só é aplicado onde o formato do executável tem onde guardá-lo. No
# Linux o ELF não tem: quem carrega o ícone lá é o arquivo .desktop.
ICONE = None
if EH_WINDOWS:
    ICONE = os.path.join(RAIZ, "ponte_menuxy", "recursos", "icone.ico")
elif EH_MAC:
    ICONE = os.path.join(RAIZ, "ponte_menuxy", "recursos", "icone.png")

# Opcionais: só entram na lista se existirem no ambiente de build.
opcionais = []
for modulo in ("usb", "usb.core", "usb.util", "usb.backend.libusb1",
               "serial", "serial.tools.list_ports"):
    try:
        __import__(modulo)
        opcionais.append(modulo)
    except Exception:
        pass

analise = Analysis(
    [os.path.join(SPECPATH, "executavel.py")],
    pathex=[RAIZ],
    binaries=[],
    datas=[(os.path.join(RAIZ, "ponte_menuxy", "recursos"), "ponte_menuxy/recursos")],
    hiddenimports=[
        "ponte_menuxy",
        "ponte_menuxy.cli",
        "ponte_menuxy.janela",
        "ponte_menuxy.servidor",
        "ponte_menuxy.catalogo",
        "ponte_menuxy.registro",
        "ponte_menuxy.backends.sistema",
        "ponte_menuxy.backends.usb_direta",
        "ponte_menuxy.backends.usbprint",
        "ponte_menuxy.backends.rede",
        "ponte_menuxy.backends.serial_",
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
    ] + opcionais,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Matplotlib e companhia entrariam por dependência transitiva do Pillow e
    # dobrariam o tamanho do executável sem que nada aqui os use.
    excludes=["matplotlib", "numpy", "scipy", "pandas", "PyQt5", "PySide2",
              "IPython", "pytest", "setuptools", "pip"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analise.pure)

exe = EXE(
    pyz,
    analise.scripts,
    analise.binaries,
    analise.datas,
    [],
    name="PonteMenuxy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX desligado: ele encolhe o arquivo, mas antivírus de balcão tratam
    # executável comprimido como suspeito — e um falso positivo no cliente
    # custa mais caro do que 8 MB a mais.
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=ICONE,
    version=None,
)
