<div align="center">

<img src="ponte_menuxy/recursos/icone-128.png" width="96" alt="">

# Ponte de Impressão Menuxy

**Deixa um sistema web imprimir na impressora térmica do balcão.**
Windows e Linux, um código só, cinco caminhos até o papel.

`.exe` para Windows &nbsp;·&nbsp; `.deb` para Linux &nbsp;·&nbsp; sem dependência obrigatória

</div>

---

## O problema

Nenhum navegador consegue falar com uma impressora térmica:

* a API **WebUSB bloqueia dispositivos de classe 7** (impressora), por decisão
  de segurança dos navegadores;
* no Windows, o `usbprint.sys` já reivindicou o aparelho;
* `window.print()` manda a página **renderizada**, não ESC/POS — a térmica não
  entende;
* numa fila **raw** do CUPS é pior: sem filtro, o PDF do navegador vai cru para
  a bobina e saem metros de lixo.

E o seu servidor não resolve: ele não alcança a USB de um balcão a 500 km dele.

## A solução

Um programa que roda **na máquina do balcão** e expõe HTTP local:

```
navegador --HTTP--> ponte (127.0.0.1:9100) --> impressora
```

```js
await fetch('http://127.0.0.1:9100/imprimir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: 'MEU CUPOM\n', cortar: true })
});
```

---

## Começar em três minutos

**Linux**

```bash
./empacotar/linux/gerar_deb.sh
sudo apt install ./dist/menuxy-ponte_3.0.0_all.deb
menuxy-ponte --origens https://menuxy.alvesprotect.app.br
menuxy-ponte --testar
```

**Windows**

```
empacotar\windows\gerar_exe.bat     (uma vez, na sua máquina)
```

Entregue `dist\PonteMenuxy.exe` ao cliente. Duplo clique, e a janela abre.

**A partir do código, em qualquer sistema**

```bash
python3 -m ponte_menuxy --listar
python3 -m ponte_menuxy
```

Instalação detalhada: [`docs/INSTALACAO.md`](docs/INSTALACAO.md).

---

## O aplicativo

Uma janela com quatro abas, para o operador não precisar de terminal nem de
editor de texto:

| Aba | O que resolve |
|---|---|
| **Situação** | a ponte está no ar? quantos cupons saíram? quem pode mandar imprimir? |
| **Impressoras** | escolher a impressora, imprimir teste, abrir a gaveta, cadastrar impressora de rede |
| **Configuração** | porta, origens permitidas, acentos, largura do papel, corte — e **iniciar junto com o computador** |
| **Registro** | o que passou por aqui, com hora |

Mais o **atalho na área de trabalho e no menu**, criado por um botão — fora da
pasta do projeto, que é de onde o operador vai abrir todo dia.

Sem `tkinter` a janela não abre e a ponte **continua imprimindo**, no terminal.

---

## Cinco caminhos até o papel

Uma impressora chega ao computador de formas muito diferentes, e uma ponte que
cobre só uma delas deixa metade dos clientes de fora.

| Identificador | Quando é o caminho certo | Precisa de |
|---|---|---|
| `sistema:<nome>` | a impressora está **instalada** (spooler do Windows / fila do CUPS). Térmica, laser, jato, USB ou de rede | nada |
| `usb:VID:PID` | impressora **plugada sem driver** — a genérica que o Windows não reconhece | `pyusb` |
| `usbprint:VID:PID` | Windows, **inclusive ARM**: usa o driver que o próprio Windows anexou, sem Zadig | nada |
| `rede:host:porta` | impressora com IP, protocolo RAW 9100 | nada |
| `serial:porta:vel` | impressora serial ou conversor USB-serial | `pyserial` |

O prefixo não é enfeite: uma `Termica58` instalada e uma `Termica58` na USB são
coisas diferentes, e sem ele o trabalho poderia sair pelo caminho errado.

**O caminho `sistema:` não tem dependência nenhuma além da biblioteca padrão do
Python** — e é o que a maioria dos balcões usa. Os opcionais que faltarem
somem do catálogo sem derrubar o resto.

Detalhes e lista de modelos: [`docs/COMPATIBILIDADE.md`](docs/COMPATIBILIDADE.md).

---

## Contrato HTTP

```
GET  /status        situação, versão, impressoras
GET  /impressoras   só as impressoras
GET  /saude         { ok, versao } — não toca na impressora
POST /imprimir      { texto, cortar?, impressora?, colunas? }
POST /raw           { base64, impressora? }        ESC/POS já montado
POST /gaveta        { impressora? }
```

> **HTTP 200 sozinho não prova que imprimiu.** Confira `ok === true` no corpo:
> a ponte só o marca depois que o spooler, a USB ou a rede aceitaram os bytes.

Contrato completo: [`docs/API.md`](docs/API.md).

---

## Segurança

| Medida | O que impede |
|---|---|
| Escuta **só em `127.0.0.1`** | Nenhuma máquina da rede alcança a porta. Não é firewall: o socket não existe fora do loopback. |
| **Lista de origens** | Sem ela, qualquer site aberto no navegador do operador manda imprimir. |
| **Teto por minuto** (60) | Um site hostil, ou um laço com defeito no sistema, despeja a bobina inteira. |
| **Teto de corpo** (512 KB) | Corpo gigante como negação de serviço. |
| Nome conferido na **lista real** | Erro de digitação vira mensagem clara; nome forjado não chega a lugar nenhum. |
| **Nenhum shell** | `subprocess` com lista de argumentos, Win32 por `ctypes`. `Termica; rm -rf /` é só um nome que não existe. |
| **Nenhum acesso a dado** | Sem banco, sem leitura de arquivo, sem rota que devolva informação de venda. |

**O limite, dito sem rodeio:** com a lista de origens aberta (`["*"]`), qualquer
site que o operador visitar consegue gastar a sua bobina. Ler, não consegue —
não há o que ler. Feche assim que souber o endereço:

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br
```

O resto, inclusive o que ela **não** protege:
[`docs/SEGURANCA.md`](docs/SEGURANCA.md).

---

## Verificação

```bash
python3 testes/verificar_ponte.py
```

98 checagens: montagem ESC/POS, saneamento da configuração, contrato dos cinco
backends, resolução de identificadores, rotas, CORS, validação de entrada,
nomes hostis, lista de origens, teto por minuto e superfície de ataque.

**Não gasta papel** — mira uma impressora que não existe e confere a recusa.
Para imprimir de verdade, um cupom só:

```bash
python3 testes/verificar_ponte.py --com-papel sistema:Termica58
```

---

## Estrutura

```
ponte_menuxy/        o aplicativo
  config.py          onde a configuração mora, e o saneamento dela
  escpos.py          texto -> bytes que a impressora entende
  backends/          os cinco caminhos até o papel
  catalogo.py        junta os cinco; resolve identificadores
  servidor.py        o HTTP e as travas
  inicializacao.py   iniciar com o sistema; atalhos
  janela.py          a interface (opcional)
  cli.py             a linha de comando

exemplos/            código para copiar em projetos novos
  js/ponte-cliente.js      cliente JavaScript, sem dependência
  php/PonteImpressao.php   monta o cupom no servidor
  python/cliente.py        cliente para o que não é web
  web/exemplo.html         página de diagnóstico
  MIGRACAO-MENUXY.md       migração da ponte v2, com os diff prontos

empacotar/           .exe, .deb e binário único
docs/                a documentação
testes/              o verificador
ferramenta_cli/      a ferramenta de baixo nível e a engenharia reversa da GS-JP58H
```

---

## Documentação

| | |
|---|---|
| [INSTALACAO.md](docs/INSTALACAO.md) | instalar em cada sistema |
| [CONFIGURACAO.md](docs/CONFIGURACAO.md) | todos os campos, e os quatro ajustes que resolvem quase tudo |
| [API.md](docs/API.md) | o contrato HTTP |
| [ARQUITETURA.md](docs/ARQUITETURA.md) | como é por dentro, e por que foi assim |
| [COMPATIBILIDADE.md](docs/COMPATIBILIDADE.md) | sistemas, impressoras e o caso do Windows ARM |
| [SEGURANCA.md](docs/SEGURANCA.md) | as travas, e o que elas não protegem |
| [EMPACOTAMENTO.md](docs/EMPACOTAMENTO.md) | gerar o `.exe` e o `.deb` |
| [SOLUCAO-DE-PROBLEMAS.md](docs/SOLUCAO-DE-PROBLEMAS.md) | quando o cupom não sai |
| [exemplos/README.md](exemplos/README.md) | ligar um projeto novo à ponte |
| [ferramenta_cli/README.md](ferramenta_cli/README.md) | a engenharia reversa da GS-JP58H |

---

## A ferramenta de linha de comando

`ferramenta_cli/imprime_termica.py` continua no projeto. Ela é a ferramenta de
diagnóstico de baixo nível e carrega o trabalho de engenharia reversa da
GS-JP58H — descoberta de endpoint, detach do driver do kernel, páginas de
código, tradução dos erros de libusb. É com ela que se investiga por que uma
impressora nova não é reconhecida:

```bash
python3 ferramenta_cli/imprime_termica.py --listar
```

O backend `usb:` da ponte herdou essas decisões; elas custaram caro para
descobrir e não devem ser refeitas por suposição.

---

<div align="center">
<sub>

Feito para o [Menuxy](https://menuxy.alvesprotect.app.br) — e para qualquer
projeto que precise imprimir. Veja [`exemplos/`](exemplos/).

</sub>
</div>
