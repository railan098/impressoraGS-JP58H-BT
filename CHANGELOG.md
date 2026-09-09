# Histórico de versões

## 3.0.1 — 2026-09-09

### Corrigido

* **`usb:` falhava com "Resource busy" em multifuncional.** O backend soltava
  o driver do kernel sempre da **interface 0**. Numa impressora simples ela é a
  de impressão e funcionava; numa multifuncional não é — na Epson L3150 a
  classe 7 (Printer) fica na interface **1**, com `usbhid` na 0. Resultado: a
  ponte soltava a interface errada, o `usblp` continuava segurando a certa, e o
  `claim` morria com `[Errno 16] Resource busy`. A mensagem então acusava "outro
  programa tem a impressora" — mandando o operador procurar um culpado que não
  existia.

  Agora a interface de impressão é descoberta pelo descritor **antes** de
  qualquer coisa, e é dela que o driver sai.

* **O driver do kernel é devolvido no fim.** Sem isso, um cupom pela USB direta
  deixava o `usblp` desanexado e a fila do sistema (`sistema:<nome>`) parava de
  imprimir até alguém desligar o cabo — o caminho de reserva virava vítima do
  caminho principal.

* **`claim` explícito antes de escrever**, para uma disputa pelo aparelho
  aparecer como disputa e não como falha de escrita.

* **A largura do papel deixou de ser chutada.** Todo aparelho de classe 7
  aparecia no catálogo como `58mm`, inclusive uma jato de tinta A4.

* **O ícone do atalho não abria nada.** Três defeitos somados, todos
  disparados por abrir a ponte de dentro do terminal do VS Code — que é um snap
  e exporta o ambiente do sandbox para os filhos:

  1. `gio set ... metadata::trusted` falhava com *"not supported"*, porque o
     `GIO_MODULE_DIR` do snap fazia o `gio` do sistema carregar os módulos do
     sandbox, sem o de metadados do gvfs. **O GNOME não lança um `.desktop` não
     confiável**, e não diz por quê: o duplo clique não fazia nada.
  2. A falha era engolida (`except Exception: pass`), então a ponte anunciava
     "atalho criado" e entregava um ícone morto. Agora ela avisa, e ensina o
     clique com o botão direito → "Permitir execução".
  3. O atalho do menu ia para `XDG_DATA_HOME`, que o snap apontava para
     `~/snap/code/260/.local/share` — dentro do sandbox. Não havia nem sequer a
     entrada no menu como reserva.

  A ponte agora ignora `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `GIO_MODULE_DIR` e
  companhia **quando apontam para dentro de um snap**, e roda `gio` e
  `update-desktop-database` com o ambiente limpo. Um valor legítimo do usuário
  continua valendo.

### Novo

* **Botão "Desligar tudo"** no rodapé da janela: encerra **todas** as pontes
  desta máquina, não só a que está na tela. Existe porque o autostart costuma
  ter subido uma cópia sem janela no login, e fechar a janela da frente não
  parava a impressão — ninguém entendia por quê. O diálogo diz quantas cópias
  encontrou, e avisa quando o início automático vai trazê-las de volta no
  próximo boot.

* **Início com o computador virou botão**, com o estado real do sistema ao
  lado. Como caixa de seleção ele só valia depois de "Salvar configuração", e
  quem marcava e fechava a janela descobria no dia seguinte que a ponte não
  tinha subido.

* **Botão "Ver diagnóstico"** — o relatório de `--diagnostico` numa janela, com
  "Copiar tudo". Quem precisa dele é justamente quem não abre terminal.

* **Botão "Restaurar padrões"**, que preserva a impressora escolhida e as de
  rede cadastradas — elas descrevem o balcão, não uma preferência — e avisa que
  a lista de origens de fábrica é aberta.

* **Tamanho do registro (KB)** agora é editável na janela; antes só existia no
  arquivo de configuração.

* **Minimizar deixa dito que minimizou.** O X da janela parecia encerrar o
  programa, e ele continuava de pé segurando a porta 9100.

### Verificação

* 115 checagens (eram 98). As dezessete novas cobrem a escolha da interface USB num
  barramento de mentira — multifuncional, térmica de uma interface só e aparelho
  sem driver do kernel — e o ambiente vazado por um snap. Rodam em qualquer
  máquina, sem impressora plugada e sem gastar papel.

## 3.0.0 — 2026-09-09

A ponte vira **aplicativo**: instalável, com janela de configuração e ícone na
área de trabalho. Antes era um script que alguém precisava lembrar de rodar.

### Novo

* **Aplicativo empacotado.** `PonteMenuxy.exe` para Windows (um arquivo, sem
  Python no destino) e `menuxy-ponte_3.0.0_all.deb` para Debian/Ubuntu — `all`,
  então o mesmo pacote serve amd64, arm64 e armhf.
* **Janela de configuração** com quatro abas: Situação, Impressoras,
  Configuração e Registro. Escolher impressora, imprimir teste, abrir gaveta,
  cadastrar impressora de rede e ligar o início automático — tudo sem terminal.
* **Iniciar junto com o computador**, em uma caixa de seleção. Registro no
  nível do usuário nos três sistemas: `HKCU\...\Run` no Windows,
  `~/.config/autostart` no Linux, LaunchAgent no macOS.
* **Atalho na área de trabalho e no menu**, criado por um botão ou por
  `--criar-atalho`. Fora da pasta do projeto, que é de onde o operador abre.
* **Três caminhos novos até o papel**, além de `sistema:` e `usb:`:
  * `usbprint:` — Windows falando pelo próprio `usbprint.sys`. **Resolve o
    Windows ARM**, onde não dá para trocar o driver pelo Zadig.
  * `rede:` — impressora com IP, protocolo RAW 9100.
  * `serial:` — impressora serial e conversor USB-serial.
* **Rotas novas:** `POST /gaveta` (aciona a gaveta sem imprimir) e
  `GET /saude` (para monitor, sem tocar na impressora).
* **`colunas` no `POST /imprimir`** — a ponte requebra o texto na largura da
  bobina. `0` significa "já formatei, não mexa".
* **`--diagnostico`** — um relatório de uma tela para colar no suporte.
* **Registro em arquivo** com rotação, ao lado da configuração.
* **Exemplos para copiar:** cliente JavaScript sem dependência, classe PHP que
  monta o cupom no servidor, cliente Python e página de diagnóstico.
* **Documentação completa** em `docs/`, oito arquivos.
* **Verificador com 98 checagens**, que não gasta papel.

### Mudou

* O código virou o pacote `ponte_menuxy/`, com os backends isolados num
  subpacote e um contrato comum entre eles.
* A ferramenta de linha de comando e a engenharia reversa da GS-JP58H foram
  para `ferramenta_cli/`. Nada foi jogado fora: ela continua sendo o lugar de
  investigar uma impressora nova.
* A configuração é gravada de forma atômica — queda de energia no balcão não
  deixa mais um JSON pela metade.
* Listagem de impressoras ganhou cache de 5 s. O agente sonda a cada 3 s, e sem
  cache isso era uma tempestade de processos `lpstat`.
* Acentos sem tabela na impressora viram a letra sem acento, não `?`.
  "Sao Bento" é legível; "S?o Bento" faz o operador achar que quebrou.
* As portas seriais fantasma do Linux (`ttyS0`–`ttyS31`) saíram da lista.
* **Uma opção de configuração agora grava e sai**, em vez de cair no servidor.
  Na v2, `--origens ...` gravava e subia a ponte, e um instalador que a
  chamasse ficava pendurado ali para sempre. Para as duas coisas: `--servir`.
* **Clicar no ícone com a ponte já aberta agora levanta a janela dela**, em vez
  de mostrar um erro. O operador que clica no ícone quer *abrir o aplicativo*;
  responder "já está aberto" é tecnicamente correto e praticamente inútil com a
  janela minimizada atrás de tudo. A segunda cópia pede a janela à primeira
  (`POST /janela`) e sai em silêncio. Só quando a instância no ar roda sem
  janela — modo serviço — é que a explicação aparece.
* **Falha ao subir deixava o ícone mudo.** Aberto pelo atalho, o aplicativo
  roda com `Terminal=false`: a mensagem de erro ia para uma saída que não
  existe, e clicar no ícone não fazia nada. Agora a falha aparece numa caixa de
  aviso. E o caso comum — porta ocupada — é diagnosticado: a ponte consulta a
  porta e, se quem está lá é outra ponte, diz a versão dela e que não é preciso
  abrir de novo.
* Corpo maior que o teto responde **413 legível** em vez de derrubar a conexão.
  A ponte drena o excesso antes de responder — respondendo com o cliente ainda
  enviando, o navegador recebia "connection reset" e a página dizia "a ponte
  não respondeu", mandando procurar o problema no lugar errado.

### Compatibilidade

**O contrato HTTP da v2 foi mantido inteiro.** Um sistema que já falava com a
ponte v2 funciona com a v3 sem alteração nenhuma, e a configuração da v2 é
lida no mesmo lugar. Ver `exemplos/MIGRACAO-MENUXY.md`.

---

## 2.0 — 2026-09-08

* Primeira ponte multiplataforma, com os caminhos `sistema:` e `usb:`.
* Contrato HTTP `/status`, `/impressoras`, `/imprimir`, `/raw`.
* `Access-Control-Allow-Private-Network`, sem o qual o Chrome barra a chamada a
  `127.0.0.1` — e sem erro visível no console.
* Lista de origens, teto por minuto e teto de corpo.

## 1.0 — 2026-09-08

* `imprime_termica.py`: ESC/POS direto no endpoint USB bulk-out, ignorando o
  driver do fabricante, o spooler e o CUPS.
* Engenharia reversa da GS-JP58H / POS-58 (`0x0416:0x5011`): a classe 7 está na
  *interface*, não no dispositivo; o endpoint não pode ser fixado em `0x01`; o
  `usblp` precisa ser solto antes do claim.
* Instaladores para Windows e Linux, regra udev e autoteste.
