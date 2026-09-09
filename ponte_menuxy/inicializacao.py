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


# --------------------------------------------------------------------------- #
#  Ambiente contaminado por snap
# --------------------------------------------------------------------------- #
# Um terminal aberto dentro de um snap — o VS Code do snapd é o caso comum —
# exporta o ambiente do sandbox dele para **todo** processo filho. Dois desses
# valores estragam a integração com a área de trabalho, e de um jeito
# silencioso:
#
# * ``XDG_DATA_HOME=~/snap/code/260/.local/share`` — o atalho do menu vai parar
#   dentro do sandbox, onde o GNOME nunca vai procurar. O programa diz "atalho
#   criado" e não há atalho nenhum.
# * ``GIO_MODULE_DIR=~/snap/code/common/.cache/gio-modules`` — o ``gio`` do
#   sistema passa a carregar os módulos do snap, que não têm o de metadados do
#   gvfs. ``gio set ... metadata::trusted`` então responde "not supported", a
#   marcação de confiança não acontece, e o GNOME se recusa a lançar o ícone da
#   área de trabalho. O duplo clique não faz absolutamente nada.
#
# Nenhum dos dois é problema do snap: é vazamento de ambiente. A ponte é
# instalada fora dele e tem de gravar fora dele.

_VARIAVEIS_DE_SNAP = (
    "GIO_MODULE_DIR", "GIO_EXTRA_MODULES", "GTK_PATH", "GSETTINGS_SCHEMA_DIR",
    "GDK_PIXBUF_MODULE_FILE", "LD_LIBRARY_PATH", "LOCPATH",
)


def _dentro_de_snap(caminho: str) -> bool:
    """O caminho aponta para dentro do sandbox de algum snap?"""
    return "/snap/" in (caminho or "").replace(os.sep, "/")


def ambiente_limpo() -> dict:
    """
    Uma cópia do ambiente sem o que um snap injetou.
    
    Só remove a variável que **aponta para dentro de um snap** — um valor
    legítimo do usuário fica onde está.
    """
    ambiente = dict(os.environ)
    for nome in _VARIAVEIS_DE_SNAP:
        if _dentro_de_snap(ambiente.get(nome, "")):
            ambiente.pop(nome, None)
    return ambiente


def pasta_xdg(variavel: str, *padrao: str) -> str:
    """
    A pasta XDG do usuário, ignorando o que um snap tenha redirecionado.

    ``pasta_xdg("XDG_DATA_HOME", ".local", "share")`` devolve
    ``~/.local/share`` mesmo quando o terminal veio de dentro de um snap.
    """
    base = os.environ.get(variavel) or ""
    if not base or _dentro_de_snap(base):
        base = os.path.join(os.path.expanduser("~"), *padrao)
    return base


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
                                   text=True, timeout=5,
                                   env=ambiente_limpo()).stdout.strip()
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
    pasta = os.path.join(pasta_xdg("XDG_CONFIG_HOME", ".config"), "autostart")
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

    ok, motivo = marcar_confiavel(atalho)
    if not ok:
        # Não é detalhe: sem a marcação o GNOME simplesmente não lança o ícone,
        # e o duplo clique não faz nada nem mostra erro. Dizer "atalho criado" e
        # calar isto é entregar um ícone morto.
        return True, (f"{atalho}\n     ATENÇÃO: não consegui marcar o atalho como "
                      f"confiável ({motivo}).\n     O GNOME não lança um atalho não "
                      "confiável — o duplo clique não fará nada.\n     Clique com o "
                      "botão direito no ícone e escolha 'Permitir execução'.")
    return True, atalho


def marcar_confiavel(atalho: str) -> Tuple[bool, str]:
    """
    Marca o ``.desktop`` como confiável para o GNOME poder lançá-lo.

    Desde a 42 o GNOME se recusa a executar um lançador que o usuário não
    marcou, e a recusa é muda: o ícone fica lá e o duplo clique não faz nada.

    Roda com o ambiente limpo de propósito. Com o ``GIO_MODULE_DIR`` de um snap
    no caminho, o ``gio`` do sistema carrega os módulos do sandbox, não acha o
    de metadados do gvfs e responde "Setting attribute metadata::trusted not
    supported" — que foi exatamente o que aconteceu quando o atalho foi criado
    a partir do terminal do VS Code.
    """
    if not shutil.which("gio"):
        return False, "o comando 'gio' não existe nesta máquina"
    try:
        resultado = subprocess.run(
            ["gio", "set", atalho, "metadata::trusted", "true"],
            capture_output=True, text=True, timeout=10, env=ambiente_limpo())
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"
    if resultado.returncode == 0:
        return True, ""
    return False, (resultado.stderr or resultado.stdout or "gio falhou").strip()


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
        pasta = os.path.join(pasta_xdg("XDG_DATA_HOME", ".local", "share"), "applications")
        os.makedirs(pasta, exist_ok=True)
        ok, detalhe = _linux_atalho(pasta)
        mensagens.append(("atalho no menu: " if ok else "falhou: ") + detalhe)
        # Sem atualizar o banco, o item só aparece no próximo login.
        if shutil.which("update-desktop-database"):
            try:
                subprocess.run(["update-desktop-database", pasta],
                               capture_output=True, timeout=15, env=ambiente_limpo())
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


# --------------------------------------------------------------------------- #
#  Desligar tudo
# --------------------------------------------------------------------------- #
# "Encerrar a ponte" fecha ESTA cópia. Não é a mesma coisa que desligar a
# impressão na máquina, e a diferença aparece justamente quando incomoda: o
# operador fechou a janela, o cupom continuou saindo, e ninguém entende por
# quê. As causas são banais — o autostart já subiu uma cópia sem janela no
# login, alguém abriu uma segunda em outra porta, um terminal ficou com uma
# rodando de ontem.
#
# Daí este par: descobrir as outras cópias e encerrá-las.
#
# **Nada de shell**, como no resto do projeto. No Linux a varredura é o
# ``/proc``, que é exato e não gasta processo nenhum; no macOS é um ``ps`` com
# lista de argumentos; no Windows é o ``taskkill`` filtrando pelo PID para não
# derrubar a si mesmo.

_PROGRAMAS = ("menuxy-ponte", "pontemenuxy", "pontemenuxy.exe")


def _parece_a_ponte(argumentos: List[str]) -> bool:
    """
    Esta linha de comando é uma ponte, ou só alguém com o nome na tela?

    A pergunta importa: uma busca solta por "ponte_menuxy" acerta o editor com
    o arquivo aberto, o ``tail`` no registro e o próprio ``grep``. Encerrar o
    editor de alguém para desligar uma impressora seria um estrago bem maior do
    que o problema. Por isso só duas formas contam, e são as duas que existem:
    o executável empacotado, e ``python -m ponte_menuxy``.
    """
    if not argumentos:
        return False
    programa = os.path.basename(argumentos[0]).lower()
    if programa in _PROGRAMAS:
        return True
    if "python" not in programa:
        return False
    for indice, argumento in enumerate(argumentos):
        if argumento == "-m" and argumentos[indice + 1:indice + 2] == ["ponte_menuxy"]:
            return True
    # O console_script instalado pelo pip:  /usr/bin/python3 /usr/bin/menuxy-ponte
    return any(os.path.basename(a).lower() in _PROGRAMAS for a in argumentos[1:])


def _outras_no_proc() -> List[int]:
    meu = os.getpid()
    achados: List[int] = []
    for entrada in os.listdir("/proc"):
        if not entrada.isdigit() or int(entrada) == meu:
            continue
        try:
            with open(f"/proc/{entrada}/cmdline", "rb") as arquivo:
                partes = arquivo.read().split(b"\0")
        except OSError:
            continue           # morreu no meio da varredura, ou não é nossa
        argumentos = [p.decode("utf-8", "replace") for p in partes if p]
        if _parece_a_ponte(argumentos):
            achados.append(int(entrada))
    return achados


def _outras_no_ps() -> List[int]:
    meu = os.getpid()
    achados: List[int] = []
    try:
        saida = subprocess.run(["ps", "-Ao", "pid=,args="], capture_output=True,
                               text=True, timeout=10).stdout
    except Exception:
        return achados
    for linha in saida.splitlines():
        pedaco = linha.strip().split(None, 1)
        if len(pedaco) != 2 or not pedaco[0].isdigit():
            continue
        pid = int(pedaco[0])
        if pid != meu and _parece_a_ponte(pedaco[1].split()):
            achados.append(pid)
    return achados


def outras_copias() -> List[int]:
    """PIDs das outras pontes em execução nesta máquina. Nunca inclui a nossa."""
    if os.name == "nt":
        return []              # no Windows quem enumera e encerra é o taskkill
    if os.path.isdir("/proc"):
        return _outras_no_proc()
    return _outras_no_ps()


def _encerrar_windows() -> Tuple[int, str]:
    encerradas = 0
    problemas: List[str] = []
    for imagem in ("PonteMenuxy.exe", "pythonw.exe", "python.exe"):
        # O filtro de PID poupa a nossa própria cópia; sem ele o taskkill
        # derrubaria esta janela antes de ela encerrar o servidor direito.
        try:
            resultado = subprocess.run(
                ["taskkill", "/F", "/IM", imagem, "/FI", f"PID ne {os.getpid()}"],
                capture_output=True, text=True, timeout=20)
        except Exception as erro:
            problemas.append(f"{imagem}: {erro}")
            continue
        encerradas += resultado.stdout.upper().count("SUCCESS")
    detalhe = "; ".join(problemas)
    return encerradas, detalhe


def encerrar_outras() -> Tuple[int, str]:
    """
    Encerra as outras cópias da ponte nesta máquina. Não encerra a nossa.

    Devolve ``(quantas, detalhe)``. Pede primeiro com ``SIGTERM``, que deixa a
    outra cópia devolver a porta e fechar o registro; só quem ignorar leva
    ``SIGKILL``, meio segundo depois.
    """
    if os.name == "nt":
        return _encerrar_windows()

    import signal
    import time

    alvos = outras_copias()
    if not alvos:
        return 0, ""

    problemas: List[str] = []
    for pid in alvos:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            problemas.append(f"{pid}: de outro usuário")

    time.sleep(0.5)
    for pid in alvos:
        try:
            os.kill(pid, 0)          # ainda vivo?
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass                      # já foi: é o caso normal

    vivos = [p for p in outras_copias() if p in alvos]
    if vivos:
        problemas.append("continuam de pé: " + ", ".join(str(p) for p in vivos))
    return len(alvos) - len(vivos), "; ".join(problemas)
