# -*- coding: utf-8 -*-
"""
A linha de comando.

Sem argumento nenhum a ponte abre a janela e serve — é o que o atalho da área
de trabalho faz, e o que acontece no duplo clique. Os argumentos existem para
o instalador, para o modo serviço e para o diagnóstico::

    menuxy-ponte                       janela + servidor
    menuxy-ponte --sem-janela          só o servidor (modo serviço)
    menuxy-ponte --listar              o que ela enxerga, e sai
    menuxy-ponte --testar              imprime UM cupom de teste, e sai
    menuxy-ponte --origens https://menuxy.alvesprotect.app.br
    menuxy-ponte --impressora sistema:Termica58
    menuxy-ponte --iniciar-com-sistema sim
    menuxy-ponte --criar-atalho
    menuxy-ponte --diagnostico         relatório para colar no suporte

Uma opção de configuração **grava e sai** — ela não sobe o servidor. É o que
permite um instalador chamar ``--origens`` e ``--iniciar-com-sistema`` em
sequência sem travar o script esperando um servidor que nunca termina. Para
configurar e já subir, some ``--servir``::

    menuxy-ponte --porta 9101 --servir
"""

from __future__ import annotations

import argparse
import errno
import platform
import sys
from typing import Any, Dict, List, Optional

from . import NOME, SISTEMA_PADRAO, VERSAO
from . import catalogo, config, escpos, inicializacao, janela, registro, servidor


def _tabela(lista: List[Dict[str, Any]], padrao, escolhida: str) -> str:
    if not lista:
        return ("Nenhuma impressora encontrada.\n"
                "  - instalada no sistema? confira em Impressoras do sistema operacional\n"
                "  - USB sem driver? instale o pyusb:  pip install pyusb\n"
                "  - de rede? cadastre o IP na aba Impressoras da janela")
    linhas = [f"{'IDENTIFICADOR':40} {'CAMINHO':10} DESCRIÇÃO"]
    for item in lista:
        marca = ""
        if item["id"] == escolhida:
            marca = "  <= escolhida nesta máquina"
        elif item["id"] == padrao:
            marca = "  (padrão do sistema)"
        linhas.append(f"{item['id']:40} {item['tipo']:10} {item['rotulo']}{marca}")
    return "\n".join(linhas)


def _diagnostico(cfg: Dict[str, Any]) -> str:
    """Relatório de uma tela para colar no suporte. Não imprime nada."""
    lista, padrao = catalogo.listar(cfg, forcar=True)
    linhas = [
        f"{NOME} — diagnóstico",
        "=" * 60,
        f"versão da ponte  : {VERSAO}",
        f"Python           : {sys.version.split()[0]} ({platform.python_implementation()})",
        f"sistema          : {platform.system()} {platform.release()} {platform.machine()}",
        f"executável       : {sys.executable}",
        f"empacotado       : {'sim (PyInstaller)' if inicializacao.empacotado() else 'não'}",
        "",
        f"caminhos ativos  : {', '.join(catalogo.backends_ativos())}",
        f"tkinter (janela) : {'disponível' if janela.disponivel() else 'AUSENTE — instale python3-tk'}",
        "",
        f"configuração     : {config.caminho_config()}",
        f"registro         : {config.caminho_registro()}",
        f"porta            : {cfg['porta']}",
        f"origens          : {', '.join(cfg['origens_permitidas'])}"
        + ("   <= ABERTA, feche com --origens" if config.origens_abertas(cfg) else ""),
        f"impressora fixada: {cfg.get('impressora_padrao') or '(nenhuma; usa a padrão do sistema)'}",
        f"padrão do sistema: {padrao or '(nenhuma)'}",
        f"papel            : {cfg['colunas']} colunas, página {cfg['codepage']}, "
        f"corte {'ligado' if cfg['cortar_por_padrao'] else 'desligado'}",
        f"inicia com o SO  : {'sim' if inicializacao.ativa() else 'não'}  ({inicializacao.onde()})",
        "",
        _tabela(lista, padrao, cfg.get("impressora_padrao", "")),
    ]
    final = registro.ler_final(15)
    if final:
        linhas += ["", "últimas linhas do registro:", final.rstrip()]
    return "\n".join(linhas)


def _sim_nao(valor: str) -> bool:
    return str(valor).strip().lower() in ("sim", "s", "1", "true", "on", "yes")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="menuxy-ponte",
        description=f"{NOME} v{VERSAO} — deixa o seu sistema web imprimir na impressora "
                    "deste computador.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Documentação completa em docs/ — comece por docs/INSTALACAO.md",
    )
    parser.add_argument("--versao", action="version", version=f"{NOME} {VERSAO}")

    grupo = parser.add_argument_group("configuração (grava e sai; some --servir para subir junto)")
    grupo.add_argument("--porta", type=int, metavar="N", help="porta HTTP local (padrão 9100)")
    grupo.add_argument("--origens", nargs="*", metavar="URL",
                       help=f"endereços que podem mandar imprimir; ex.: {SISTEMA_PADRAO}")
    grupo.add_argument("--impressora", metavar="ID",
                       help="identificador da impressora desta máquina (ex.: sistema:Termica58)")
    grupo.add_argument("--colunas", type=int, metavar="N",
                       help="largura da bobina: 32 para 58 mm, 48 para 80 mm")
    grupo.add_argument("--codepage", metavar="NOME", choices=sorted(escpos.CODEPAGES),
                       help="página de código dos acentos (padrão cp850)")
    grupo.add_argument("--iniciar-com-sistema", metavar="sim|nao",
                       help="liga ou desliga o início automático ao ligar o computador")

    acoes = parser.add_argument_group("ações (fazem e saem)")
    acoes.add_argument("--listar", action="store_true", help="lista as impressoras e sai")
    acoes.add_argument("--testar", action="store_true",
                       help="imprime UM cupom de teste e sai")
    acoes.add_argument("--gaveta", action="store_true",
                       help="abre a gaveta de dinheiro e sai")
    acoes.add_argument("--diagnostico", action="store_true",
                       help="relatório completo para o suporte; não imprime nada")
    acoes.add_argument("--criar-atalho", action="store_true",
                       help="cria o atalho na área de trabalho e no menu")
    acoes.add_argument("--remover-atalho", action="store_true",
                       help="remove os atalhos criados")

    modo = parser.add_argument_group("modo de execução")
    modo.add_argument("--sem-janela", action="store_true",
                      help="não abre a janela; só o servidor (é o modo serviço)")
    modo.add_argument("--com-janela", action="store_true",
                      help="força a janela, mesmo com 'abrir_janela' desligado")
    modo.add_argument("--servir", action="store_true",
                      help="sobe o servidor depois de gravar a configuração "
                           "(sem isto, uma opção de configuração grava e sai)")
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    cfg = config.carregar()

    # ---- o que grava configuração ----------------------------------------
    mudou = False
    for campo, valor in (("porta", args.porta), ("impressora_padrao", args.impressora),
                         ("colunas", args.colunas), ("codepage", args.codepage)):
        if valor is not None:
            cfg[campo] = valor
            mudou = True
    if args.origens is not None:
        cfg["origens_permitidas"] = args.origens or ["*"]
        mudou = True
    if args.iniciar_com_sistema is not None:
        desejado = _sim_nao(args.iniciar_com_sistema)
        cfg["iniciar_com_sistema"] = desejado
        ok, detalhe = inicializacao.definir(desejado)
        print(("[ok] " if ok else "[erro] ") + detalhe)
        mudou = True
        if not ok:
            return 1

    if mudou:
        cfg = config.carregar_de(cfg)
        print(f"[ok] configuração gravada em {config.salvar(cfg)}")

    registro.ativar(bool(cfg["registrar_em_arquivo"]), int(cfg["registro_kb"]))

    # Configurar e servir são intenções diferentes. Um instalador que chama
    # `--origens ...` espera o comando TERMINAR; se ele subisse o servidor, o
    # script travaria ali para sempre, esperando algo que nunca acaba. Quem
    # quer as duas coisas pede as duas, com `--servir`.
    acoes = (args.criar_atalho or args.remover_atalho or args.diagnostico
             or args.listar or args.testar or args.gaveta)
    if mudou and not acoes and not args.servir:
        print("     para subir a ponte agora:  menuxy-ponte")
        return 0

    # ---- ações que fazem e saem ------------------------------------------
    if args.criar_atalho:
        for mensagem in inicializacao.criar_atalhos():
            print("[ok] " + mensagem)
        return 0

    if args.remover_atalho:
        mensagens = inicializacao.remover_atalhos()
        print("\n".join("[ok] " + m for m in mensagens) or "[ok] nenhum atalho encontrado")
        return 0

    if args.diagnostico:
        print(_diagnostico(cfg))
        return 0

    if args.listar:
        lista, padrao = catalogo.listar(cfg, forcar=True)
        print(_tabela(lista, padrao, cfg.get("impressora_padrao", "")))
        return 0 if lista else 1

    if args.gaveta:
        try:
            ok, detalhe = catalogo.imprimir(cfg.get("impressora_padrao", ""),
                                            escpos.comando_gaveta(), cfg)
        except catalogo.ImpressoraDesconhecida as erro:
            print(f"[erro] {erro}")
            return 1
        print(("[ok] gaveta acionada em " if ok else "[erro] ") + detalhe)
        return 0 if ok else 1

    if args.testar:
        cupom = escpos.montar_cupom(
            escpos.cupom_de_teste(int(cfg["colunas"]), VERSAO, platform.system()),
            codepage=cfg["codepage"],
            cortar=bool(cfg["cortar_por_padrao"]),
            avancos=int(cfg["avancos_antes_do_corte"]),
        )
        try:
            ok, detalhe = catalogo.imprimir(cfg.get("impressora_padrao", ""), cupom, cfg)
        except catalogo.ImpressoraDesconhecida as erro:
            print(f"[erro] {erro}")
            return 1
        print(("[ok] cupom de teste impresso em " if ok else "[erro] ") + detalhe)
        return 0 if ok else 1

    # ---- servir ------------------------------------------------------------
    return servir(cfg, args)


def quem_ocupa(porta: int) -> Optional[Dict[str, Any]]:
    """
    Descobre se quem já está na porta é outra ponte.

    Faz diferença enorme na mensagem: "já existe uma ponte no ar" manda o
    operador procurar o ícone na barra de tarefas, enquanto "a porta está
    ocupada" o manda investigar o computador inteiro.
    """
    import json as _json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/status", timeout=2) as resposta:
            dados = _json.loads(resposta.read().decode("utf-8") or "{}")
        return dados if isinstance(dados, dict) and dados.get("ok") else None
    except Exception:
        return None


def _explicar_porta_ocupada(porta: int) -> str:
    outra = quem_ocupa(porta)
    if outra:
        return (
            f"Já existe uma ponte de impressão no ar na porta {porta} "
            f"(versão {outra.get('versao', 'desconhecida')}).\n\n"
            "Não é preciso abrir de novo — ela já está funcionando. Procure o "
            "ícone na barra de tarefas.\n\n"
            "Se for uma versão antiga que você quer substituir, encerre-a "
            "primeiro:\n"
            "    pkill -f ponte.py          (Linux/macOS)\n"
            "    taskkill /IM pythonw.exe   (Windows)\n\n"
            f"Ou use outra porta:  menuxy-ponte --porta {porta + 1}\n"
            "(lembrando de ajustar o endereço no seu sistema)."
        )
    return (
        f"A porta {porta} está ocupada por outro programa.\n\n"
        f"Para a ponte usar outra:  menuxy-ponte --porta {porta + 1}\n"
        "Lembre de ajustar o endereço no seu sistema depois.\n\n"
        "Para descobrir quem ocupa:\n"
        f"    ss -ltnp | grep {porta}          (Linux)\n"
        f"    netstat -ano | findstr {porta}   (Windows)"
    )


def servir(cfg: Dict[str, Any], args) -> int:
    com_janela = args.com_janela or (cfg.get("abrir_janela", True) and not args.sem_janela)

    try:
        instancia = servidor.criar(cfg)
    except OSError as erro:
        if erro.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)):
            mensagem = _explicar_porta_ocupada(int(cfg["porta"]))
        else:
            mensagem = f"Não foi possível abrir a porta {cfg['porta']}:\n\n{erro}"

        print("[erro] " + mensagem, file=sys.stderr)
        registro.escrever(f"falha ao subir: {mensagem.splitlines()[0]}")
        # Aberto pelo atalho não há terminal nenhum: sem esta caixa, o ícone
        # simplesmente não faz nada e o operador fica sem pista alguma.
        if com_janela:
            janela.avisar(mensagem)
        return 2

    for linha in servidor.descrever(cfg):
        print(linha)
    registro.escrever(f"ponte iniciada na porta {cfg['porta']}")

    if com_janela and janela.disponivel():
        try:
            return janela.abrir(instancia, cfg)
        except Exception as erro:
            # A janela falhou (servidor gráfico ausente, sessão remota sem X).
            # Servir no terminal é melhor do que não servir.
            print(f"[aviso] a janela não abriu ({erro}); seguindo no terminal.", file=sys.stderr)
    elif com_janela:
        print("[aviso] tkinter não está instalado — seguindo no terminal.")
        if sys.platform.startswith("linux"):
            print("        Para ter a janela:  sudo apt install python3-tk")

    print("  Ctrl+C para parar.")
    try:
        instancia.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrada.")
        registro.escrever("ponte encerrada pelo operador")
    finally:
        instancia.server_close()
    return 0
