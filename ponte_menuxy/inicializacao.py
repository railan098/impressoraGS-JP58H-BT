# -*- coding: utf-8 -*-
"""
Iniciar junto com o computador, e o atalho na área de trabalho.

Duas necessidades diferentes de um balcão:

* **Ligar o PC e a ponte já estar de pé.** Ninguém no caixa vai lembrar de
  abrir um programa antes do primeiro pedido do dia — e quando lembra, já tem
  cliente esperando.
* **Um ícone na área de trabalho**, fora da pasta do projeto, para abrir a
  janela de configuração quando precisar trocar a impressora.

Cada sistema tem o seu jeito, e a escolha em todos foi a mesma: **nível de
usuário, sem administrador**.

===========  ============================================================
Sistema      Onde
===========  ============================================================
Windows      ``HKCU\\...\\CurrentVersion\\Run``. Não ``HKLM``: aquele exige
             administrador, e a ponte imprime com as permissões de quem
             está logado. Atalhos ``.lnk`` criados por PowerShell — sem
             ``pywin32``, que é mais uma dependência para falhar.
Linux        ``~/.config/autostart/*.desktop``, que é o padrão XDG e vale
             em GNOME, KDE, XFCE e Cinnamon. Opcionalmente um serviço
             ``systemd --user``, para reiniciar sozinha se cair.
macOS        ``~/Library/LaunchAgents/*.plist``.
===========  ============================================================

**Por que serviço de usuário e não de sistema:** a ponte precisa das
permissões de quem está logado, que é quem tem acesso às filas do CUPS e à
sessão gráfica. Um serviço de sistema roda como ``root`` sem sessão, não
enxerga as impressoras do usuário e não consegue abrir janela nenhuma.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from . import NOME, NOME_CURTO

_CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NOME_REGISTRO = "MenuxyPonte"


# --------------------------------------------------------------------------- #
#  Como esta ponte é executada
# --------------------------------------------------------------------------- #

def empacotado() -> bool:
    """Verdadeiro quando rodando de dentro do executável do PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def comando(sem_janela: bool = False) -> List[str]:
    """
    A linha de comando que faz esta mesma ponte subir de novo.

    Empacotado, é o próprio executável. A partir do código, é
    ``python -m ponte_menuxy`` — com ``pythonw.exe`` no Windows, porque o "w" é
    o que evita a janela preta de console piscando a cada login.
    """
    if empacotado():
        base = [sys.executable]
    else:
        interpretador = sys.executable
        if os.name == "nt":
            sem_console = os.path.join(os.path.dirname(interpretador), "pythonw.exe")
            if os.path.isfile(sem_console):
                interpretador = sem_console
        base = [interpretador, "-m", "ponte_menuxy"]

    if sem_janela:
        base.append("--sem-janela")
    return base


def _linha(argumentos: List[str]) -> str:
    """Junta os argumentos numa linha, com aspas onde há espaço."""
    return " ".join(f'"{a}"' if " " in a else a for a in argumentos)


def _pasta_do_projeto() -> str:
    """Raiz do projeto — importa para o `python -m` achar o pacote."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def caminho_icone() -> Optional[str]:
    """
    O ícone desta instalação, ou ``None`` se não houver.

    São quatro lugares porque o arquivo muda de lugar conforme a forma de
    instalação: ao lado do módulo (a partir do código), dentro do
    ``sys._MEIPASS`` do PyInstaller — onde a receita o coloca sob
    ``ponte_menuxy/recursos``, e não na raiz —, e em ``/usr/share/icons``
    quando veio do ``.deb``.
    """
    nome = "icone.ico" if os.name == "nt" else "icone.png"
    aqui = os.path.dirname(os.path.abspath(__file__))
    empacotado_em = getattr(sys, "_MEIPASS", None)

    candidatos = [os.path.join(aqui, "recursos", nome)]
    if empacotado_em:
        candidatos += [
            os.path.join(empacotado_em, "ponte_menuxy", "recursos", nome),
            os.path.join(empacotado_em, "recursos", nome),
        ]
    candidatos.append(f"/usr/share/icons/hicolor/256x256/apps/{NOME_CURTO}.png")

    for candidato in candidatos:
        if os.path.isfile(candidato):
            return candidato
    return None


# --------------------------------------------------------------------------- #
#  Windows
# --------------------------------------------------------------------------- #

def _win_ativa() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN) as chave:
            winreg.QueryValueEx(chave, _NOME_REGISTRO)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def _win_ligar() -> Tuple[bool, str]:
    import winreg
    linha = _linha(comando(sem_janela=False))
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN) as chave:
            winreg.SetValueEx(chave, _NOME_REGISTRO, 0, winreg.REG_SZ, linha)
        return True, f"registrada na inicialização do Windows: {linha}"
    except OSError as erro:
        return False, f"não foi possível gravar no registro: {erro}"


def _win_desligar() -> Tuple[bool, str]:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN, 0,
                            winreg.KEY_SET_VALUE) as chave:
            winreg.DeleteValue(chave, _NOME_REGISTRO)
        return True, "removida da inicialização do Windows"
    except FileNotFoundError:
        return True, "já não estava na inicialização"
    except OSError as erro:
        return False, f"não foi possível remover do registro: {erro}"


def _win_atalho(destino_pasta: str) -> Tuple[bool, str]:
    """
    Cria um ``.lnk`` via PowerShell.

    PowerShell e não ``pywin32``: o executável precisa rodar num balcão sem
    nada instalado, e o ``WScript.Shell`` já vem no Windows desde sempre.
    """
    argumentos = comando(sem_janela=False)
    alvo = argumentos[0]
    resto = _linha(argumentos[1:])
    icone = caminho_icone() or alvo
    atalho = os.path.join(destino_pasta, f"{NOME}.lnk")

    script = (
        "$a = New-Object -ComObject WScript.Shell; "
        f"$s = $a.CreateShortcut('{atalho}'); "
        f"$s.TargetPath = '{alvo}'; "
        f"$s.Arguments = '{resto}'; "
        f"$s.WorkingDirectory = '{_pasta_do_projeto()}'; "
        f"$s.IconLocation = '{icone}'; "
        "$s.Description = 'Ponte de impressao do Menuxy'; "
        "$s.Save()"
    )
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30)
    except Exception as erro:
        return False, f"não foi possível chamar o PowerShell: {erro}"
    if resultado.returncode != 0:
        return False, (resultado.stderr or "").strip()[:200] or "o PowerShell recusou o atalho"
    return True, atalho


# --------------------------------------------------------------------------- #
#  Linux — XDG
# --------------------------------------------------------------------------- #

def _pasta_area_de_trabalho() -> str:
    """
    A área de trabalho do usuário, no idioma dele.

    ``xdg-user-dir`` é o único jeito confiável: num sistema em português a
    pasta é "Área de Trabalho", e chutar ``~/Desktop`` cria uma pasta órfã que
    ninguém vê.
    """
    if shutil.which("xdg-user-dir"):
        try:
            saida = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True,
                                   text=True, timeout=5).stdout.strip()
            if saida and os.path.isdir(saida):
                return saida
        except Exception:
            pass
    for nome in ("Desktop", "Área de Trabalho", "Área de trabalho"):
        candidato = os.path.join(os.path.expanduser("~"), nome)
        if os.path.isdir(candidato):
            return candidato
    return os.path.expanduser("~")


def _conteudo_desktop(sem_janela: bool = False) -> str:
    icone = caminho_icone() or "printer"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NOME}\n"
        "GenericName=Ponte de impressão\n"
        "Comment=Deixa o sistema web imprimir na impressora deste computador\n"
        f"Exec={_linha(comando(sem_janela))}\n"
        f"Path={_pasta_do_projeto()}\n"
        f"Icon={icone}\n"
        "Terminal=false\n"
        "Categories=Utility;Office;Printing;\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        # Alguns ambientes sobem o autostart antes da rede e do CUPS. Dez
        # segundos evitam a ponte listar zero impressoras logo no login.
        "X-GNOME-Autostart-Delay=10\n"
    )


def _linux_arquivo_autostart() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    pasta = os.path.join(base, "autostart")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, f"{NOME_CURTO}.desktop")


def _linux_ativa() -> bool:
    return os.path.isfile(_linux_arquivo_autostart())


def _linux_ligar() -> Tuple[bool, str]:
    arquivo = _linux_arquivo_autostart()
    try:
        with open(arquivo, "w", encoding="utf-8") as saida:
            saida.write(_conteudo_desktop(sem_janela=False))
        os.chmod(arquivo, 0o755)
        return True, f"iniciará junto com a sessão: {arquivo}"
    except OSError as erro:
        return False, f"não foi possível gravar {arquivo}: {erro}"


def _linux_desligar() -> Tuple[bool, str]:
    arquivo = _linux_arquivo_autostart()
    try:
        os.remove(arquivo)
        return True, "removida da inicialização da sessão"
    except FileNotFoundError:
        return True, "já não estava na inicialização"
    except OSError as erro:
        return False, f"não foi possível remover {arquivo}: {erro}"


def _linux_atalho(destino_pasta: str) -> Tuple[bool, str]:
    atalho = os.path.join(destino_pasta, f"{NOME_CURTO}.desktop")
    try:
        with open(atalho, "w", encoding="utf-8") as saida:
            saida.write(_conteudo_desktop())
        os.chmod(atalho, 0o755)
    except OSError as erro:
        return False, f"não foi possível gravar {atalho}: {erro}"

    # O GNOME desde a 42 ignora atalhos que o usuário não marcou como
    # confiáveis, e apenas mostra "Arquivo não confiável". Esta é a marcação.
    if shutil.which("gio"):
        try:
            subprocess.run(["gio", "set", atalho, "metadata::trusted", "true"],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    return True, atalho


# --------------------------------------------------------------------------- #
#  macOS — LaunchAgent
# --------------------------------------------------------------------------- #

def _mac_arquivo() -> str:
    pasta = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, "br.app.alvesprotect.menuxy-ponte.plist")


def _mac_ativa() -> bool:
    return os.path.isfile(_mac_arquivo())


def _mac_ligar() -> Tuple[bool, str]:
    argumentos = "".join(f"    <string>{a}</string>\n" for a in comando(sem_janela=True))
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        '  <key>Label</key><string>br.app.alvesprotect.menuxy-ponte</string>\n'
        f'  <key>ProgramArguments</key>\n  <array>\n{argumentos}  </array>\n'
        '  <key>RunAtLoad</key><true/>\n'
        '  <key>KeepAlive</key><true/>\n'
        '</dict>\n</plist>\n'
    )
    arquivo = _mac_arquivo()
    try:
        with open(arquivo, "w", encoding="utf-8") as saida:
            saida.write(plist)
        subprocess.run(["launchctl", "load", "-w", arquivo],
                       capture_output=True, timeout=15)
        return True, f"iniciará junto com o login: {arquivo}"
    except Exception as erro:
        return False, f"não foi possível registrar o LaunchAgent: {erro}"


def _mac_desligar() -> Tuple[bool, str]:
    arquivo = _mac_arquivo()
    try:
        subprocess.run(["launchctl", "unload", "-w", arquivo],
                       capture_output=True, timeout=15)
        os.remove(arquivo)
        return True, "removida da inicialização do macOS"
    except FileNotFoundError:
        return True, "já não estava na inicialização"
    except Exception as erro:
        return False, f"não foi possível remover o LaunchAgent: {erro}"


# --------------------------------------------------------------------------- #
#  Interface pública — é isto que a janela e a linha de comando usam
# --------------------------------------------------------------------------- #

def ativa() -> bool:
    """A ponte está registrada para iniciar com o sistema?"""
    try:
        if os.name == "nt":
            return _win_ativa()
        if sys.platform == "darwin":
            return _mac_ativa()
        return _linux_ativa()
    except Exception:
        return False


def definir(ligado: bool) -> Tuple[bool, str]:
    """Liga ou desliga o início automático. Devolve ``(deu certo, explicação)``."""
    try:
        if os.name == "nt":
            return _win_ligar() if ligado else _win_desligar()
        if sys.platform == "darwin":
            return _mac_ligar() if ligado else _mac_desligar()
        return _linux_ligar() if ligado else _linux_desligar()
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"


def criar_atalhos(area_de_trabalho: bool = True, menu: bool = True) -> List[str]:
    """
    Cria os atalhos para abrir a ponte fora da pasta do projeto.

    Devolve a lista de mensagens — uma por atalho — para a janela ou a linha de
    comando mostrar. Um destino que falhe não impede os outros.
    """
    mensagens: List[str] = []

    if os.name == "nt":
        destinos = []
        if area_de_trabalho:
            destinos.append(os.path.join(os.path.expanduser("~"), "Desktop"))
        if menu:
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            programas = os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs")
            os.makedirs(programas, exist_ok=True)
            destinos.append(programas)
        for destino in destinos:
            ok, detalhe = _win_atalho(destino)
            mensagens.append(("atalho criado: " if ok else "falhou: ") + detalhe)
        return mensagens

    if area_de_trabalho:
        ok, detalhe = _linux_atalho(_pasta_area_de_trabalho())
        mensagens.append(("atalho criado: " if ok else "falhou: ") + detalhe)

    if menu:
        pasta = os.path.join(
            os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"),
            "applications")
        os.makedirs(pasta, exist_ok=True)
        ok, detalhe = _linux_atalho(pasta)
        mensagens.append(("atalho no menu: " if ok else "falhou: ") + detalhe)
        # Sem atualizar o banco, o item só aparece no próximo login.
        if shutil.which("update-desktop-database"):
            try:
                subprocess.run(["update-desktop-database", pasta],
                               capture_output=True, timeout=15)
            except Exception:
                pass

    return mensagens


def remover_atalhos() -> List[str]:
    """Remove os atalhos criados por :func:`criar_atalhos`."""
    mensagens: List[str] = []
    if os.name == "nt":
        base_menu = os.environ.get("APPDATA") or os.path.expanduser("~")
        candidatos = [
            os.path.join(os.path.expanduser("~"), "Desktop", f"{NOME}.lnk"),
            os.path.join(base_menu, "Microsoft", "Windows", "Start Menu",
                         "Programs", f"{NOME}.lnk"),
        ]
    else:
        candidatos = [
            os.path.join(_pasta_area_de_trabalho(), f"{NOME_CURTO}.desktop"),
            os.path.join(
                os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"),
                "applications", f"{NOME_CURTO}.desktop"),
        ]

    for arquivo in candidatos:
        try:
            os.remove(arquivo)
            mensagens.append(f"removido: {arquivo}")
        except FileNotFoundError:
            pass
        except OSError as erro:
            mensagens.append(f"não removido ({erro}): {arquivo}")
    return mensagens


def onde() -> str:
    """Uma frase dizendo onde o registro de inicialização mora nesta máquina."""
    if os.name == "nt":
        return f"HKCU\\{_CHAVE_RUN}  ->  {_NOME_REGISTRO}"
    if sys.platform == "darwin":
        return _mac_arquivo()
    return _linux_arquivo_autostart()
