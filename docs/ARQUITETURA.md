# Arquitetura

## Por que a ponte existe

Nenhum navegador consegue falar com uma impressora térmica:

* a API **WebUSB bloqueia dispositivos de classe 7** (impressora), por decisão
  de segurança dos navegadores — não é contornável;
* no Windows, o `usbprint.sys` já reivindicou o aparelho, e um driver exclusivo
  não empresta;
* `window.print()` manda a página **renderizada**, não ESC/POS — a térmica não
  entende;
* numa fila **raw** do CUPS, como quase toda 58 mm é instalada no Linux, é
  ainda pior: não há filtro, então o PDF do navegador vai cru para a bobina e
  saem metros de lixo.

A ponte resolve sendo um programa local que expõe HTTP:

```
navegador --HTTP--> ponte (127.0.0.1:9100) --> impressora
```

E ela roda **na máquina do balcão**, não no servidor, porque um servidor não
alcança a USB de um computador a 500 km dele.

## O desenho completo

```
   SEU SISTEMA (servidor web, em qualquer lugar)
        |
        |  monta o TEXTO do cupom  (exemplos/php/PonteImpressao.php)
        |  já quebrado nas colunas da bobina
        v
   NAVEGADOR do balcão
        |
        |  POST http://127.0.0.1:9100/imprimir   (exemplos/js/ponte-cliente.js)
        v
   PONTE  ─────────────────────────────────────────────────────
        |  servidor.py   valida origem, teto por minuto, corpo
        |  escpos.py     texto -> bytes ESC/POS
        |  catalogo.py   resolve o identificador contra a lista real
        v
   BACKEND  (um dos cinco)
        |
        +-- sistema:   winspool RAW  /  lp -o raw
        +-- usb:       libusb, endpoint bulk-out
        +-- usbprint:  usbprint.sys do Windows
        +-- rede:      TCP RAW 9100
        +-- serial:    pyserial
        v
   IMPRESSORA
```

## Os módulos

| Arquivo | Responsabilidade |
|---|---|
| `config.py` | onde a configuração mora, e o saneamento que impede um JSON editado à mão de derrubar a ponte |
| `escpos.py` | texto → bytes: página de código, quebra de linha, avanço, corte, gaveta |
| `backends/` | os cinco caminhos até o papel, cada um isolado |
| `catalogo.py` | junta os cinco numa lista só; resolve identificadores; cache de 5 s |
| `servidor.py` | HTTP e as travas de segurança |
| `inicializacao.py` | iniciar com o sistema; atalhos na área de trabalho |
| `janela.py` | a interface, opcional |
| `registro.py` | o `ponte.log`, com rotação |
| `cli.py` | a linha de comando |

## As decisões que moldaram o código

### Zero dependência obrigatória

O caminho `sistema:` — o que a maioria usa — só depende da biblioteca padrão do
Python. `pyusb`, `pyserial` e `tkinter` são opcionais, e **cada um que falta
some do catálogo sem derrubar o resto**. Um balcão sem `tkinter` roda a ponte
no terminal; um sem `pyusb` não oferece USB direta e imprime pelo spooler
normalmente.

Por isso nenhum desses módulos é importado no topo de arquivo nenhum: o import
está sempre dentro da função.

### `ctypes` em vez de `pywin32`

O executável precisa rodar num balcão sem nada instalado. Uma dependência a
menos é uma chance a menos de o instalador falhar. `EnumPrintersW`,
`GetDefaultPrinterW`, `OpenPrinterW`, `StartDocPrinterW` e `WritePrinter`
resolvem tudo pelo `ctypes`, que já vem no Python.

### Cinco backends, não um

A maioria das pontes cobre USB direta e ignora o resto. Mas a maioria dos
clientes tem a impressora **instalada** no sistema, e esse caminho é melhor:
usa a infraestrutura que já existe, respeita permissão e fila. Os outros três
existem para os casos que sobram — Windows ARM, impressora de rede, equipamento
serial antigo.

Todos obedecem ao mesmo contrato (`disponivel`, `listar`, `imprimir`,
`alvo_de`), e nenhum pode levantar exceção para fora: um backend quebrado some
do catálogo, não derruba a ponte.

### Cache de 5 segundos no catálogo

Listar impressoras custa: no Linux são dois processos `lpstat`; no USB, uma
varredura do barramento. O agente do sistema sonda a ponte a cada 3 segundos —
sem cache isso vira uma tempestade de processos num computador de balcão que já
é fraco. Cinco segundos é curto o bastante para uma impressora recém-ligada
aparecer quase na hora.

### Servidor com threads

Uma impressão pode levar segundos: o CUPS responde quando quer. Com um servidor
de uma thread só, a sondagem de status ficaria na fila atrás da impressão, e a
tela do balcão pareceria travada.

### A janela numa thread, o servidor em outra

Só a thread da interface pode tocar em widget do tkinter. Mexer de outra thread
não dá erro — congela. Por isso o callback de impressão apenas **enfileira** o
evento, e a interface o consome com `raiz.after(...)`.

### A configuração no perfil do usuário

O executável pode acabar em `Program Files` ou em `/usr/lib`, onde escrever
exige administrador. O perfil do usuário sempre é gravável, e é onde o Windows
e o Linux esperam encontrar configuração de aplicativo. Isso também é o que
permite instalar e configurar **sem administrador nenhum**.

### Gravação atômica

A configuração é escrita num arquivo temporário e renomeada. Se faltar energia
no meio da gravação — coisa banal num balcão — o arquivo antigo continua
íntegro, em vez de virar um JSON pela metade que impede a ponte de subir no
próximo login.

## O que a ponte deliberadamente NÃO faz

* **Não tem acesso a dado de negócio.** Sem banco, sem leitura de arquivo do
  sistema, sem rota que devolva informação de venda. O que entra é texto para
  imprimir; o que sai é "deu certo" ou o motivo da falha.
* **Não varre a rede.** Impressora de rede é declarada pelo operador.
  Varredura é lenta, assusta antivírus e adivinha errado.
* **Não roda comando por shell.** `subprocess` sempre com lista de argumentos,
  e a API do Windows por `ctypes`. `Termica; rm -rf /` é só um nome que não
  existe.
* **Não escuta fora de `127.0.0.1`.**

## Relação com a ferramenta de linha de comando

`ferramenta_cli/imprime_termica.py` continua no projeto. Ela é a ferramenta de
diagnóstico de baixo nível e carrega a engenharia reversa da GS-JP58H —
descoberta de endpoint, detach do driver do kernel, páginas de código,
tratamento dos erros de libusb. O backend `usb_direta.py` herdou essas
decisões; a ferramenta continua sendo o lugar de investigar uma impressora nova.
