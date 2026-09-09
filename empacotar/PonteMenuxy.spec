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
* **recurso de versão no Windows**: sem ele o ``.exe`` aparece nas Propriedades
  sem nome de produto, empresa nem versão — e um executável anônimo pesa contra
  na heurística do SmartScreen e do antivírus, além de não dizer nada a quem
  abre as Propriedades para decidir se confia. É de graça; a única razão de
  não ter era ninguém ter escrito.
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

# --------------------------------------------------------------------------- #
#  Recurso de versão do Windows
# --------------------------------------------------------------------------- #
# O PyInstaller recebe isto como *caminho de arquivo*, não como objeto — então a
# receita escreve o arquivo em build/ (que é ignorado pelo git) e passa o
# caminho adiante. Assim a fonte da verdade continua sendo o VERSION do projeto:
# ninguém precisa lembrar de atualizar o número em dois lugares.

def _versao_do_projeto():
    """
    A versão, lida da fonte única: ``ponte_menuxy/__init__.py``.

    Por expressão regular, e não por ``import``: importar o pacote aqui
    executaria código do projeto dentro do processo de build, e faria a receita
    depender de o ambiente de build ter tudo importável. Ler o texto não tem
    esse risco.
    """
    import re
    try:
        with open(os.path.join(RAIZ, "ponte_menuxy", "__init__.py"),
                  "r", encoding="utf-8") as arquivo:
            achado = re.search(r'^VERSAO\s*=\s*["\']([^"\']+)["\']',
                               arquivo.read(), re.M)
        if achado:
            return achado.group(1)
    except OSError:
        pass
    try:                                    # reserva: o arquivo VERSION
        with open(os.path.join(RAIZ, "VERSION"), "r", encoding="utf-8") as arquivo:
            return arquivo.read().strip()
    except OSError:
        return "0.0.0"


def _arquivo_de_versao():
    """Escreve o recurso VSVersionInfo e devolve o caminho. None fora do Windows."""
    versao = _versao_do_projeto()
    partes = [int(p) for p in versao.split(".")[:3] if p.isdigit()]
    while len(partes) < 4:
        partes.append(0)
    quadra = tuple(partes[:4])

    conteudo = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quadra},
    prodvers={quadra},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '041604B0',
        [StringStruct('CompanyName', 'Railan Alves'),
         StringStruct('FileDescription', 'Ponte de Impressao Menuxy'),
         StringStruct('FileVersion', '{versao}'),
         StringStruct('InternalName', 'PonteMenuxy'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 Railan Alves. Licenca MIT.'),
         StringStruct('OriginalFilename', 'PonteMenuxy.exe'),
         StringStruct('ProductName', 'Ponte de Impressao Menuxy'),
         StringStruct('ProductVersion', '{versao}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
"""
    pasta = os.path.join(RAIZ, "build")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, "versao_windows.txt")
    with open(destino, "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)
    return destino


# 1046 = pt-BR, 1200 = Unicode. O par tem de bater com o '041604B0' da
# StringTable acima, senão o Windows não acha as strings e as Propriedades
# voltam a aparecer vazias.
VERSAO_RECURSO = _arquivo_de_versao() if EH_WINDOWS else None

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
    version=VERSAO_RECURSO,
)
