# -*- coding: utf-8 -*-
"""
A janela do aplicativo: situação, impressoras, configuração e registro.

O servidor funciona sem ela — ``--sem-janela`` é o modo serviço. Esta janela
existe porque alguém no balcão precisa conseguir olhar a tela e responder "a
impressão está de pé?" sem abrir terminal, e trocar a impressora sem editar
JSON.

``tkinter`` vem junto com o Python no Windows e no macOS. No Linux costuma ser
um pacote à parte (``python3-tk``) — por isso **todo import fica dentro das
funções**: faltando, a ponte cai no modo terminal em vez de quebrar.

A janela roda na thread principal e o servidor numa thread própria. Toda
atualização vinda do servidor passa por ``raiz.after(0, ...)``, porque só a
thread da interface pode tocar em widget — mexer direto trava a janela de um
jeito que não dá erro, só congela.
"""

from __future__ import annotations

import os
import platform
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import NOME, VERSAO
from . import catalogo, config, escpos, inicializacao, registro

LARGURA = 720
ALTURA = 560

COR_OK = "#15803d"
COR_ALERTA = "#b45309"
COR_ERRO = "#b91c1c"
COR_SUAVE = "#555555"


def disponivel() -> bool:
    """Há tkinter nesta máquina?"""
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def avisar(mensagem: str, titulo: str = NOME, erro: bool = True) -> bool:
    """
    Mostra uma caixa de aviso, sem abrir a janela inteira.

    Existe por um defeito real: aberto pelo atalho da área de trabalho, o
    aplicativo roda com ``Terminal=false``. Se ele falha ao subir — porta
    ocupada é o caso comum — a mensagem vai para a saída de erro, que nesse
    modo **não existe**, e o operador vê o ícone não fazer absolutamente nada.

    Devolve ``True`` se conseguiu mostrar. Numa sessão sem servidor gráfico
    (SSH, modo serviço) devolve ``False``, e quem chamou continua imprimindo a
    mensagem no terminal.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()          # só a caixa, sem a janela vazia atrás
        icone = inicializacao.caminho_icone()
        if icone and icone.endswith(".png"):
            try:
                raiz.iconphoto(True, tk.PhotoImage(file=icone))
            except Exception:
                pass
        if erro:
            messagebox.showerror(titulo, mensagem)
        else:
            messagebox.showinfo(titulo, mensagem)
        raiz.destroy()
        return True
    except Exception:
        return False


def abrir(servidor, cfg: Dict[str, Any]) -> int:
    """
    Abre a janela e roda até o operador encerrar.

    O servidor recebido já está criado, mas ainda não está servindo: quem o
    coloca no ar é a thread daqui. Assim, se a janela não puder abrir, quem
    chamou ainda pode servir no terminal com o mesmo objeto.
    """
    import tkinter as tk
    from tkinter import messagebox, ttk

    from .servidor import Ponte

    raiz = tk.Tk()
    raiz.title(f"{NOME} — v{VERSAO}")
    raiz.geometry(f"{LARGURA}x{ALTURA}")
    raiz.minsize(660, 520)

    icone = inicializacao.caminho_icone()
    if icone and icone.endswith(".png"):
        try:
            raiz.iconphoto(True, tk.PhotoImage(file=icone))
        except Exception:
            pass
    elif icone and os.name == "nt":
        try:
            raiz.iconbitmap(icone)
        except Exception:
            pass

    # O servidor numa thread própria: a janela precisa continuar respondendo a
    # cliques enquanto um cupom está sendo enviado — e o CUPS demora o que quer.
    threading.Thread(target=servidor.serve_forever, daemon=True, name="ponte-http").start()

    # Fila entre a thread do servidor e a da interface. Sem ela, o callback de
    # impressão tocaria no widget de dentro da thread errada.
    eventos: "queue.Queue[str]" = queue.Queue()

    # ---------------------------------------------------------------- layout
    abas = ttk.Notebook(raiz)
    abas.pack(fill="both", expand=True, padx=10, pady=(10, 4))

    aba_situacao = ttk.Frame(abas, padding=14)
    aba_impressoras = ttk.Frame(abas, padding=14)
    aba_config = ttk.Frame(abas, padding=14)
    aba_registro = ttk.Frame(abas, padding=14)
    abas.add(aba_situacao, text="  Situação  ")
    abas.add(aba_impressoras, text="  Impressoras  ")
    abas.add(aba_config, text="  Configuração  ")
    abas.add(aba_registro, text="  Registro  ")

    # =========================================================== SITUAÇÃO ===
    ttk.Label(aba_situacao, text=NOME, font=("", 16, "bold")).pack(anchor="w")
    ttk.Label(aba_situacao, text=f"versão {VERSAO}", foreground=COR_SUAVE).pack(anchor="w")

    quadro_estado = ttk.LabelFrame(aba_situacao, text=" Estado ", padding=12)
    quadro_estado.pack(fill="x", pady=(14, 10))

    rotulo_ar = ttk.Label(quadro_estado, text="● no ar", foreground=COR_OK,
                          font=("", 12, "bold"))
    rotulo_ar.grid(row=0, column=0, sticky="w", columnspan=2)

    def linha_info(linha: int, chave: str, valor: str):
        ttk.Label(quadro_estado, text=chave, foreground=COR_SUAVE).grid(
            row=linha, column=0, sticky="w", pady=1)
        rotulo = ttk.Label(quadro_estado, text=valor)
        rotulo.grid(row=linha, column=1, sticky="w", padx=(14, 0), pady=1)
        return rotulo

    linha_info(1, "Endereço", f"http://127.0.0.1:{cfg['porta']}")
    linha_info(2, "Sistema", f"{platform.system()} {platform.release()} ({platform.machine()})")
    linha_info(3, "Caminhos", ", ".join(catalogo.backends_ativos()))
    rotulo_impressora = linha_info(4, "Impressora", cfg.get("impressora_padrao") or "(a padrão do sistema)")
    rotulo_contagem = linha_info(5, "Impressões", "0 nesta sessão")

    quadro_origem = ttk.LabelFrame(aba_situacao, text=" Quem pode mandar imprimir ", padding=12)
    quadro_origem.pack(fill="x")
    rotulo_origem = ttk.Label(quadro_origem, text="", wraplength=620, justify="left")
    rotulo_origem.pack(anchor="w")

    def pintar_origem():
        if config.origens_abertas(cfg):
            rotulo_origem.configure(
                text=("ATENÇÃO: qualquer site aberto neste navegador consegue mandar "
                      "imprimir. Ele não lê nada — a ponte não tem acesso a dado "
                      "nenhum — mas gasta a sua bobina. Feche a lista na aba "
                      "Configuração, informando o endereço do seu sistema."),
                foreground=COR_ALERTA)
        else:
            rotulo_origem.configure(
                text="Somente: " + ", ".join(cfg["origens_permitidas"]),
                foreground=COR_OK)

    pintar_origem()

    # ======================================================== IMPRESSORAS ===
    ttk.Label(aba_impressoras, text="Impressora desta máquina",
              font=("", 11, "bold")).pack(anchor="w")
    ttk.Label(
        aba_impressoras, wraplength=640, justify="left", foreground=COR_SUAVE,
        text=("'sistema:' usa a impressora instalada (spooler do Windows ou fila do "
              "CUPS) — é o caminho certo para a maioria. 'usb:' fala direto com a "
              "USB, para as que não têm driver. 'rede:' é impressora com IP. "
              "'usbprint:' é o caminho do Windows ARM.")
    ).pack(anchor="w", pady=(2, 10))

    lista_widget = ttk.Treeview(aba_impressoras, columns=("tipo", "detalhe"),
                                show="tree headings", height=8)
    lista_widget.heading("#0", text="Identificador")
    lista_widget.heading("tipo", text="Caminho")
    lista_widget.heading("detalhe", text="Como funciona")
    lista_widget.column("#0", width=250)
    lista_widget.column("tipo", width=80, anchor="center")
    lista_widget.column("detalhe", width=280)
    lista_widget.pack(fill="both", expand=True)

    encontradas: List[Dict[str, Any]] = []

    def recarregar():
        nonlocal encontradas
        for item in lista_widget.get_children():
            lista_widget.delete(item)
        encontradas, padrao = catalogo.listar(cfg, forcar=True)
        for item in encontradas:
            marca = "  ← escolhida" if item["id"] == cfg.get("impressora_padrao") else (
                "  (padrão do sistema)" if item["id"] == padrao else "")
            lista_widget.insert("", "end", iid=item["id"],
                                text=item["id"] + marca,
                                values=(item["tipo"], item.get("detalhe", "")))
        escolhida = cfg.get("impressora_padrao")
        if escolhida and escolhida in [i["id"] for i in encontradas]:
            lista_widget.selection_set(escolhida)
        anotar(f"{len(encontradas)} impressora(s) encontrada(s)")

    def selecionada() -> str:
        escolha = lista_widget.selection()
        return escolha[0] if escolha else ""

    def usar_esta():
        escolha = selecionada()
        if not escolha:
            messagebox.showinfo(NOME, "Escolha uma impressora na lista primeiro.")
            return
        cfg["impressora_padrao"] = escolha
        config.salvar(cfg)
        rotulo_impressora.configure(text=escolha)
        recarregar()
        anotar(f"impressora fixada: {escolha}")

    def imprimir_teste():
        alvo = selecionada() or cfg.get("impressora_padrao", "")
        dados = escpos.montar_cupom(
            escpos.cupom_de_teste(int(cfg.get("colunas", 32)), VERSAO, platform.system()),
            codepage=cfg["codepage"],
            cortar=bool(cfg["cortar_por_padrao"]),
            avancos=int(cfg["avancos_antes_do_corte"]),
        )
        try:
            ok, detalhe = catalogo.imprimir(alvo, dados, cfg)
        except catalogo.ImpressoraDesconhecida as erro:
            anotar(f"FALHA: {erro}")
            messagebox.showerror(NOME, str(erro))
            return
        anotar(("teste impresso em " if ok else "teste FALHOU: ") + detalhe)
        if not ok:
            messagebox.showerror(NOME, detalhe)

    def abrir_gaveta():
        alvo = selecionada() or cfg.get("impressora_padrao", "")
        try:
            ok, detalhe = catalogo.imprimir(alvo, escpos.comando_gaveta(), cfg)
        except catalogo.ImpressoraDesconhecida as erro:
            messagebox.showerror(NOME, str(erro))
            return
        anotar(("gaveta acionada em " if ok else "gaveta FALHOU: ") + detalhe)

    botoes = ttk.Frame(aba_impressoras)
    botoes.pack(fill="x", pady=(10, 6))
    ttk.Button(botoes, text="Procurar de novo", command=recarregar).pack(side="left")
    ttk.Button(botoes, text="Usar esta", command=usar_esta).pack(side="left", padx=6)
    ttk.Button(botoes, text="Imprimir teste", command=imprimir_teste).pack(side="left")
    ttk.Button(botoes, text="Abrir gaveta", command=abrir_gaveta).pack(side="left", padx=6)

    # ---- impressora de rede ------------------------------------------------
    quadro_rede = ttk.LabelFrame(aba_impressoras, text=" Adicionar impressora de rede ", padding=10)
    quadro_rede.pack(fill="x", pady=(8, 0))
    ttk.Label(quadro_rede, text="A ponte não varre a rede — varredura é lenta e assusta "
                                "antivírus. Informe o endereço:",
              foreground=COR_SUAVE, wraplength=620, justify="left").grid(
        row=0, column=0, columnspan=6, sticky="w", pady=(0, 6))

    nome_rede = tk.StringVar()
    host_rede = tk.StringVar()
    porta_rede = tk.StringVar(value="9100")
    ttk.Label(quadro_rede, text="Nome").grid(row=1, column=0, sticky="w")
    ttk.Entry(quadro_rede, textvariable=nome_rede, width=14).grid(row=1, column=1, padx=(4, 10))
    ttk.Label(quadro_rede, text="IP").grid(row=1, column=2, sticky="w")
    ttk.Entry(quadro_rede, textvariable=host_rede, width=16).grid(row=1, column=3, padx=(4, 10))
    ttk.Label(quadro_rede, text="Porta").grid(row=1, column=4, sticky="w")
    ttk.Entry(quadro_rede, textvariable=porta_rede, width=7).grid(row=1, column=5, padx=(4, 10))

    def adicionar_rede():
        from .backends import rede as backend_rede
        host = host_rede.get().strip()
        if not host:
            messagebox.showinfo(NOME, "Informe o IP da impressora.")
            return
        try:
            porta = int(porta_rede.get())
        except ValueError:
            porta = 9100
        alcancou, detalhe = backend_rede.testar_alcance(host, porta)
        if not alcancou and not messagebox.askyesno(
                NOME, f"{detalhe}\n\nCadastrar mesmo assim?"):
            return
        cfg["impressoras_rede"] = list(cfg.get("impressoras_rede") or []) + [
            {"nome": nome_rede.get().strip() or host, "host": host, "porta": porta}]
        config.salvar(cfg)
        catalogo.invalidar()
        recarregar()
        anotar(f"impressora de rede cadastrada: {host}:{porta}")

    ttk.Button(quadro_rede, text="Testar e adicionar", command=adicionar_rede).grid(
        row=1, column=6, padx=(4, 0))

    # ======================================================= CONFIGURAÇÃO ===
    campos = ttk.Frame(aba_config)
    campos.pack(fill="both", expand=True)
    campos.columnconfigure(1, weight=1)

    var_porta = tk.StringVar(value=str(cfg["porta"]))
    var_origens = tk.StringVar(value=", ".join(cfg["origens_permitidas"]))
    var_codepage = tk.StringVar(value=cfg["codepage"])
    var_colunas = tk.StringVar(value=str(cfg["colunas"]))
    var_avancos = tk.StringVar(value=str(cfg["avancos_antes_do_corte"]))
    var_limite = tk.StringVar(value=str(cfg["limite_por_minuto"]))
    var_registro_kb = tk.StringVar(value=str(cfg["registro_kb"]))
    var_cortar = tk.BooleanVar(value=cfg["cortar_por_padrao"])
    var_gaveta = tk.BooleanVar(value=cfg["abrir_gaveta_apos_imprimir"])
    var_janela = tk.BooleanVar(value=cfg["abrir_janela"])
    var_minimiza = tk.BooleanVar(value=cfg["fechar_minimiza"])
    var_registro = tk.BooleanVar(value=cfg["registrar_em_arquivo"])

    def campo(linha: int, rotulo: str, variavel, ajuda: str, largura: int = 22, opcoes=None):
        ttk.Label(campos, text=rotulo).grid(row=linha * 2, column=0, sticky="w", pady=(6, 0))
        if opcoes:
            widget = ttk.Combobox(campos, textvariable=variavel, values=opcoes,
                                  state="readonly", width=largura)
        else:
            widget = ttk.Entry(campos, textvariable=variavel, width=largura)
        widget.grid(row=linha * 2, column=1, sticky="w", padx=(12, 0), pady=(6, 0))
        ttk.Label(campos, text=ajuda, foreground=COR_SUAVE, wraplength=660,
                  justify="left").grid(row=linha * 2 + 1, column=0, columnspan=2,
                                       sticky="w", pady=(0, 2))

    campo(0, "Porta", var_porta,
          "Porta HTTP local. Só mude se outro programa já usar a 9100 — o sistema "
          "precisa saber o novo número.")
    campo(1, "Origens permitidas", var_origens,
          "Endereços que podem mandar imprimir, separados por vírgula. Deixe "
          "'*' apenas enquanto testa: ele aceita qualquer site aberto no navegador.",
          largura=48)
    campo(2, "Página de código", var_codepage,
          "Como os acentos são codificados. cp850 cobre o português na maioria das "
          "impressoras; se sair lixo no lugar de 'ç', tente cp860.",
          opcoes=sorted(escpos.CODEPAGES))
    campo(3, "Colunas do papel", var_colunas,
          "32 para bobina de 58 mm, 48 para 80 mm. Use o cupom de teste: se a régua "
          "couber inteira numa linha, está certo.")
    campo(4, "Avanços antes do corte", var_avancos,
          "Linhas em branco antes de acionar a guilhotina. A lâmina fica acima da "
          "cabeça térmica; sem avanço, o corte passa por cima da última linha.")
    campo(5, "Limite por minuto", var_limite,
          "Teto de trabalhos por minuto. Existe para um site hostil, ou um laço com "
          "defeito, não despejar a bobina inteira.")
    campo(6, "Tamanho do registro (KB)", var_registro_kb,
          "Quanto o arquivo de registro pode crescer antes de ser rotacionado. Um "
          "balcão movimentado enche 512 KB em algumas semanas; aumentar só vale se "
          "você precisa de histórico longo para conferência.")

    marcadores = ttk.Frame(campos)
    marcadores.grid(row=14, column=0, columnspan=2, sticky="w", pady=(12, 0))
    ttk.Checkbutton(marcadores, text="Cortar o papel ao fim de cada cupom",
                    variable=var_cortar).pack(anchor="w")
    ttk.Checkbutton(marcadores, text="Abrir a gaveta de dinheiro após imprimir",
                    variable=var_gaveta).pack(anchor="w")
    ttk.Separator(marcadores, orient="horizontal").pack(fill="x", pady=8)

    # Início com o computador: botão, não marcador.
    #
    # Como marcador ele só valia depois de "Salvar configuração", e quem marcava
    # e fechava a janela descobria no dia seguinte que a ponte não tinha subido.
    # Ligar o início automático é uma ação, não uma preferência a confirmar
    # depois — então acontece no clique. E o rótulo ao lado diz o estado **real**
    # do sistema, lido na hora: é a resposta para "eu marquei isso ou não?".
    inicio = ttk.Frame(marcadores)
    inicio.pack(anchor="w", fill="x", pady=(2, 2))

    botao_inicio = ttk.Button(inicio, text="", width=34)
    botao_inicio.pack(side="left")
    rotulo_inicio = ttk.Label(inicio, text="")
    rotulo_inicio.pack(side="left", padx=(10, 0))

    def pintar_inicio():
        ligado = inicializacao.ativa()
        botao_inicio.configure(
            text="Desativar início com o computador" if ligado
            else "Iniciar junto com o computador")
        rotulo_inicio.configure(
            text=("● ligado — a ponte sobe sozinha no login" if ligado
                  else "● desligado — alguém precisa abrir a ponte todo dia"),
            foreground=COR_OK if ligado else COR_ALERTA)

    def alternar_inicio():
        desejado = not inicializacao.ativa()
        ok, detalhe = inicializacao.definir(desejado)
        pintar_inicio()
        if ok:
            cfg["iniciar_com_sistema"] = desejado
            config.salvar(cfg)
        anotar(detalhe if ok else f"FALHA: {detalhe}")
        if not ok:
            messagebox.showerror(NOME, detalhe)

    botao_inicio.configure(command=alternar_inicio)
    pintar_inicio()

    ttk.Label(marcadores, text=f"registro em: {inicializacao.onde()}",
              foreground=COR_SUAVE).pack(anchor="w", padx=(4, 0))
    ttk.Checkbutton(marcadores, text="Abrir esta janela ao iniciar",
                    variable=var_janela).pack(anchor="w")
    ttk.Checkbutton(marcadores, text="Fechar a janela apenas minimiza (a ponte continua imprimindo)",
                    variable=var_minimiza).pack(anchor="w")
    ttk.Checkbutton(marcadores, text="Gravar registro em arquivo",
                    variable=var_registro).pack(anchor="w")

    def salvar_configuracao():
        anterior_porta = cfg["porta"]
        try:
            cfg["porta"] = int(var_porta.get())
            cfg["colunas"] = int(var_colunas.get())
            cfg["avancos_antes_do_corte"] = int(var_avancos.get())
            cfg["limite_por_minuto"] = int(var_limite.get())
            cfg["registro_kb"] = int(var_registro_kb.get())
        except ValueError:
            messagebox.showerror(
                NOME, "Porta, colunas, avanços, limite e tamanho do registro "
                      "precisam ser números.")
            return

        origens = [o.strip() for o in var_origens.get().split(",") if o.strip()]
        cfg["origens_permitidas"] = origens or ["*"]
        cfg["codepage"] = var_codepage.get()
        cfg["cortar_por_padrao"] = var_cortar.get()
        cfg["abrir_gaveta_apos_imprimir"] = var_gaveta.get()
        cfg["abrir_janela"] = var_janela.get()
        cfg["fechar_minimiza"] = var_minimiza.get()
        cfg["registrar_em_arquivo"] = var_registro.get()

        # Reler pelo saneamento: é ele que impede uma porta 70000 digitada por
        # engano de virar uma ponte que não sobe no próximo login.
        cfg.update(config.carregar_de(cfg))
        config.salvar(cfg)
        registro.ativar(bool(cfg["registrar_em_arquivo"]), int(cfg["registro_kb"]))

        # O saneamento pode ter corrigido o que foi digitado (uma porta 70000,
        # um registro de 4 KB). Reescrever os campos com o que ficou de fato
        # evita a tela mentir sobre o que está gravado.
        var_porta.set(str(cfg["porta"]))
        var_colunas.set(str(cfg["colunas"]))
        var_avancos.set(str(cfg["avancos_antes_do_corte"]))
        var_limite.set(str(cfg["limite_por_minuto"]))
        var_registro_kb.set(str(cfg["registro_kb"]))
        var_origens.set(", ".join(cfg["origens_permitidas"]))

        pintar_origem()
        anotar("configuração gravada em " + config.caminho_config())

        if cfg["porta"] != anterior_porta:
            messagebox.showinfo(
                NOME,
                f"A porta mudou de {anterior_porta} para {cfg['porta']}.\n\n"
                "Feche e abra a ponte para a mudança valer — e lembre de ajustar o "
                "endereço no seu sistema.")

    rodape_config = ttk.Frame(aba_config)
    rodape_config.pack(fill="x", pady=(12, 0))
    ttk.Button(rodape_config, text="Salvar configuração",
               command=salvar_configuracao).pack(side="left")

    def criar_atalho():
        mensagens = inicializacao.criar_atalhos()
        for mensagem in mensagens:
            anotar(mensagem)
        messagebox.showinfo(NOME, "\n".join(mensagens) or "nada a fazer")

    ttk.Button(rodape_config, text="Criar atalho na área de trabalho",
               command=criar_atalho).pack(side="left", padx=6)

    def abrir_pasta():
        pasta = config.pasta_dados()
        try:
            if os.name == "nt":
                os.startfile(pasta)                       # noqa: S606
            elif platform.system() == "Darwin":
                os.system(f'open "{pasta}"')
            else:
                os.system(f'xdg-open "{pasta}" >/dev/null 2>&1 &')
        except Exception:
            messagebox.showinfo(NOME, pasta)

    ttk.Button(rodape_config, text="Abrir pasta da configuração",
               command=abrir_pasta).pack(side="left")

    def ver_diagnostico():
        """
        O relatório de suporte numa janela, com botão de copiar.

        É o mesmo de ``menuxy-ponte --diagnostico``. Existe aqui porque quem
        precisa dele é justamente quem não abre terminal: na hora em que o
        cupom não sai, o suporte pede "me manda o diagnóstico" e o operador
        precisa conseguir produzir isso sozinho.
        """
        from .cli import _diagnostico          # tardio: cli importa esta janela

        try:
            relatorio = _diagnostico(cfg)
        except Exception as erro:
            messagebox.showerror(NOME, f"não foi possível montar o relatório: {erro}")
            return

        vista = tk.Toplevel(raiz)
        vista.title(f"{NOME} — diagnóstico")
        vista.geometry("760x520")
        vista.transient(raiz)

        area = tk.Text(vista, wrap="none", font=("Consolas", 9))
        rolagem = ttk.Scrollbar(vista, orient="vertical", command=area.yview)
        area.configure(yscrollcommand=rolagem.set)
        area.insert("1.0", relatorio)
        area.configure(state="disabled")
        rolagem.pack(side="right", fill="y")
        area.pack(side="top", fill="both", expand=True, padx=(10, 0), pady=10)

        pe = ttk.Frame(vista)
        pe.pack(fill="x", padx=10, pady=(0, 10))

        def copiar():
            raiz.clipboard_clear()
            raiz.clipboard_append(relatorio)
            anotar("diagnóstico copiado para a área de transferência")

        ttk.Button(pe, text="Copiar tudo", command=copiar).pack(side="left")
        ttk.Button(pe, text="Fechar", command=vista.destroy).pack(side="right")

    ttk.Button(rodape_config, text="Ver diagnóstico",
               command=ver_diagnostico).pack(side="left", padx=6)

    def restaurar_padroes():
        """
        Volta a configuração ao estado de fábrica, menos as impressoras.

        A impressora escolhida e as de rede cadastradas ficam: elas descrevem o
        **balcão**, não a preferência de ninguém, e redescobrir o IP da
        impressora da cozinha é justamente o trabalho que ninguém quer refazer.
        """
        if not messagebox.askyesno(
                NOME,
                "Voltar porta, origens permitidas, acentos, largura do papel, corte "
                "e limites aos valores de fábrica?\n\n"
                "ATENÇÃO: de fábrica a lista de origens é '*', ou seja, ABERTA — "
                "qualquer site que o operador visitar poderá gastar a bobina. "
                "Feche-a de novo com o endereço do seu sistema.\n\n"
                "A impressora escolhida e as impressoras de rede cadastradas são "
                "mantidas.\n\n"
                "O início automático não é alterado — ele tem botão próprio."):
            return

        guardadas = {
            "impressora_padrao": cfg.get("impressora_padrao", ""),
            "impressoras_rede": list(cfg.get("impressoras_rede") or []),
            "iniciar_com_sistema": inicializacao.ativa(),
        }
        cfg.update(config.carregar_de(dict(guardadas)))
        config.salvar(cfg)
        registro.ativar(bool(cfg["registrar_em_arquivo"]), int(cfg["registro_kb"]))

        var_porta.set(str(cfg["porta"]))
        var_origens.set(", ".join(cfg["origens_permitidas"]))
        var_codepage.set(cfg["codepage"])
        var_colunas.set(str(cfg["colunas"]))
        var_avancos.set(str(cfg["avancos_antes_do_corte"]))
        var_limite.set(str(cfg["limite_por_minuto"]))
        var_registro_kb.set(str(cfg["registro_kb"]))
        var_cortar.set(cfg["cortar_por_padrao"])
        var_gaveta.set(cfg["abrir_gaveta_apos_imprimir"])
        var_janela.set(cfg["abrir_janela"])
        var_minimiza.set(cfg["fechar_minimiza"])
        var_registro.set(cfg["registrar_em_arquivo"])

        pintar_origem()
        anotar("configuração restaurada aos padrões de fábrica")
        if cfg["porta"] != servidor.server_address[1]:
            messagebox.showinfo(
                NOME, f"A porta voltou para {cfg['porta']}. Feche e abra a ponte "
                      "para a mudança valer.")

    ttk.Button(rodape_config, text="Restaurar padrões",
               command=restaurar_padroes).pack(side="left")

    # =========================================================== REGISTRO ===
    ttk.Label(aba_registro, text="O que passou por aqui", font=("", 11, "bold")).pack(anchor="w")
    texto = tk.Text(aba_registro, height=18, wrap="word", font=("Consolas", 9))
    barra = ttk.Scrollbar(aba_registro, orient="vertical", command=texto.yview)
    texto.configure(yscrollcommand=barra.set, state="disabled")
    texto.pack(side="left", fill="both", expand=True, pady=(6, 0))
    barra.pack(side="right", fill="y", pady=(6, 0))

    impressos = 0

    def anotar(mensagem: str) -> None:
        """Escreve uma linha no registro da janela (e no arquivo, se ligado)."""
        registro.escrever(mensagem)
        texto.configure(state="normal")
        texto.insert("end", f"[{time.strftime('%H:%M:%S')}] {mensagem}\n")
        # Teto de linhas: uma janela aberta por semana num balcão movimentado
        # acumularia dezenas de milhares de linhas e comeria a memória.
        if int(texto.index("end-1c").split(".")[0]) > 500:
            texto.delete("1.0", "200.0")
        texto.see("end")
        texto.configure(state="disabled")

    # ------------------------------------------------ ponte entre as threads
    def ao_imprimir(ok: bool, detalhe: str, tamanho: int) -> None:
        """Chamado pela thread do servidor. Só enfileira — quem desenha é a interface."""
        eventos.put(f"{'1' if ok else '0'}|{tamanho}|{detalhe}")

    Ponte.ao_registrar = staticmethod(ao_imprimir)

    def ao_pedir_janela() -> None:
        """Outra cópia do aplicativo pediu a janela. Chamado pela thread HTTP."""
        eventos.put("MOSTRAR||")

    Ponte.ao_mostrar_janela = staticmethod(ao_pedir_janela)

    def trazer_para_frente() -> None:
        raiz.deiconify()
        raiz.lift()
        # O -topmost momentâneo é o que realmente funciona: sem ele, GNOME e
        # Windows costumam apenas piscar o botão na barra em vez de levantar a
        # janela, porque o pedido não veio de uma interação do usuário com ELA.
        try:
            raiz.attributes("-topmost", True)
            raiz.after(400, lambda: raiz.attributes("-topmost", False))
        except Exception:
            pass
        try:
            raiz.focus_force()
        except Exception:
            pass

    def drenar():
        nonlocal impressos
        try:
            while True:
                evento = eventos.get_nowait()
                marca, tamanho, detalhe = evento.split("|", 2)
                if marca == "MOSTRAR":
                    trazer_para_frente()
                    anotar("outra cópia do aplicativo foi aberta; janela trazida à frente")
                elif marca == "1":
                    impressos += 1
                    rotulo_contagem.configure(text=f"{impressos} nesta sessão")
                    anotar(f"impresso em {detalhe} ({tamanho} bytes)")
                else:
                    anotar(f"FALHA: {detalhe}")
        except queue.Empty:
            pass
        raiz.after(400, drenar)

    # ---------------------------------------------------------------- fechar
    def ao_fechar():
        if cfg.get("fechar_minimiza", True):
            # Minimiza, não esconde: sem ícone de bandeja, esconder a janela a
            # tornaria impossível de reabrir sem matar o processo.
            #
            # E deixa dito que minimizou. Sem esta linha o X da janela parece
            # ter encerrado o programa, e ele continua de pé: o terminal que o
            # abriu nunca devolve o prompt, a porta 9100 segue ocupada e a
            # próxima tentativa de abrir esbarra numa ponte que "não existe".
            raiz.iconify()
            anotar("janela minimizada — a ponte CONTINUA no ar e imprimindo. "
                   "Para encerrar de verdade use 'Encerrar esta cópia', ou "
                   "'Desligar tudo' se houver mais de uma.")
            return
        encerrar()

    def encerrar():
        anotar("encerrando a ponte")
        try:
            servidor.shutdown()
        except Exception:
            pass
        raiz.destroy()

    def desligar_tudo():
        """
        Encerra a impressão nesta máquina inteira, não só esta janela.

        "Encerrar esta cópia" fecha o que está na frente do operador, e isso
        engana: o autostart costuma ter subido uma cópia sem janela no login,
        e às vezes há uma terceira num terminal esquecido. O cupom continua
        saindo depois de fechar a janela, e ninguém entende por quê. Este botão
        é a resposta para "para de imprimir, agora".
        """
        outras = inicializacao.outras_copias()
        if os.name == "nt":
            resumo = "esta ponte e qualquer outra cópia aberta nesta máquina"
        elif outras:
            resumo = (f"esta ponte e mais {len(outras)} cópia(s) em execução "
                      f"(PID {', '.join(str(p) for p in outras)})")
        else:
            resumo = "esta ponte — é a única em execução nesta máquina"

        aviso = (f"Encerrar {resumo}.\n\n"
                 "Nada mais será impresso até alguém abrir a ponte de novo.")
        if inicializacao.ativa():
            aviso += ("\n\nO início automático continua ligado: ela volta sozinha "
                      "quando o computador for ligado. Para impedir isso, desligue-o "
                      "antes, na aba Configuração.")
        if not messagebox.askyesno(NOME, aviso + "\n\nDesligar tudo agora?"):
            return

        encerradas, detalhe = inicializacao.encerrar_outras()
        if encerradas:
            anotar(f"desligar tudo: {encerradas} outra(s) cópia(s) encerrada(s)")
        if detalhe:
            anotar(f"desligar tudo: {detalhe}")
            messagebox.showwarning(
                NOME, "Nem todas as cópias foram encerradas:\n\n" + detalhe)
        encerrar()

    rodape = ttk.Frame(raiz)
    rodape.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Label(rodape, text=f"configuração: {config.caminho_config()}",
              foreground=COR_SUAVE).pack(side="left")
    # Os rótulos precisam dizer o alcance de cada um: lado a lado, "Encerrar a
    # ponte" e "Desligar tudo" pareceriam o mesmo botão escrito duas vezes.
    ttk.Button(rodape, text="Encerrar esta cópia", command=encerrar).pack(side="right")
    ttk.Button(rodape, text="Minimizar", command=raiz.iconify).pack(side="right", padx=6)
    ttk.Button(rodape, text="Desligar tudo", command=desligar_tudo).pack(side="right")

    raiz.protocol("WM_DELETE_WINDOW", ao_fechar)

    recarregar()
    anotar(f"ponte no ar em http://127.0.0.1:{cfg['porta']}")
    drenar()

    raiz.mainloop()
    # shutdown() para o laço; server_close() devolve a porta. Sem o segundo, a
    # porta fica presa ao processo e reabrir a ponte falha com "já está em uso".
    for encerrar_algo in (servidor.shutdown, servidor.server_close):
        try:
            encerrar_algo()
        except Exception:
            pass
    return 0
