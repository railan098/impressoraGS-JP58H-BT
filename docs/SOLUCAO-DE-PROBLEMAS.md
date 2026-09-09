# Solução de problemas

Comece sempre por aqui:

```bash
menuxy-ponte --diagnostico
```

Uma tela com tudo que importa: versão, sistema, caminhos ativos, impressoras,
origens, onde a configuração mora e as últimas linhas do registro. É o que
colar num pedido de suporte.

---

## O cupom não sai

Siga na ordem. Cada passo elimina uma camada.

### 1. A ponte está no ar?

```bash
menuxy-ponte --diagnostico
```

Se o comando nem existe, ela não está instalada — veja
[INSTALACAO.md](INSTALACAO.md).

### 2. A ponte enxerga a impressora?

```bash
menuxy-ponte --listar
```

Lista vazia → pule para *"Nenhuma impressora encontrada"*, abaixo.

### 3. A ponte consegue imprimir sozinha?

```bash
menuxy-ponte --testar
```

**Saiu papel?** Então a ponte está boa e o problema está entre o seu sistema e
ela — vá para o passo 4.

**Não saiu?** O problema é a impressora ou o caminho até ela. A mensagem de
erro diz qual; procure-a mais abaixo neste arquivo.

### 4. O navegador consegue falar com a ponte?

Abra `exemplos/web/exemplo.html` no navegador **da máquina do balcão**. Ela
mostra a situação e imprime sem envolver o seu sistema.

**Imprimiu ali e não pelo sistema?** É a lista de origens. Veja o passo 5.

### 5. A origem do seu sistema está autorizada?

Abra o console do navegador (F12) e procure um **HTTP 403**. Se ele estiver
lá:

```bash
menuxy-ponte --origens https://oendereco-do-seu-sistema.com.br
```

O endereço tem que bater **exatamente** — esquema, host e porta.

---

## Nenhuma impressora encontrada

### A impressora está ligada?

O cabo USB alimenta o chip, mas a impressora precisa estar **ligada no botão**
para enumerar. É a causa nº 1, e vale a pena conferir antes de qualquer outra.

### É USB sem driver? Falta o `pyusb`

```bash
pip install pyusb          # Linux/macOS
python -m pip install pyusb libusb-package    # Windows
```

O `--diagnostico` mostra em *caminhos ativos* se o `usb` está lá.

### Linux: falta permissão na USB

O sintoma é a impressora não aparecer, ou aparecer e falhar com "acesso
negado". Instale a regra udev:

```bash
sudo cp ferramenta_cli/99-impressora-termica.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG lp $USER
```

Depois **faça logout e login** — o grupo novo só vale na sessão seguinte. O
pacote `.deb` já instala a regra.

### Linux: `usblp` segurando o aparelho

Erro típico: `Resource busy`. O kernel anexou o `usblp` à impressora. A ponte
tenta soltar sozinha; quando não consegue:

```bash
sudo modprobe -r usblp
```

### Windows: `usbprint.sys` bloqueando o libusb

Erro típico: `acesso negado` no caminho `usb:`. Duas saídas:

* **A boa, e a única em ARM:** use o identificador `usbprint:` da mesma
  impressora. `menuxy-ponte --listar` mostra os dois.
* **A antiga:** trocar o driver por WinUSB com o
  [Zadig](https://zadig.akeo.ie/). Funciona em x64, mas pede administrador e
  faz a impressora sumir de "Impressoras e Scanners". Só faça se o `usbprint:`
  falhar.

### CUPS não instalado (Linux)

```bash
sudo apt install cups-client
lpstat -a          # tem que listar as filas
```

Se `lpstat -a` não mostra a impressora, o problema é anterior à ponte — instale
a impressora no sistema primeiro.

---

## Sai papel, mas errado

### Acentos como lixo: "A‡Æo" em vez de "Ação"

Cada impressora tem uma tabela de 256 caracteres. Troque a página de código:

```bash
menuxy-ponte --codepage cp860 --testar
```

Ordem de tentativa: `cp850` (padrão), `cp860` (Portuguese), `cp1252`, `cp437`.
O cupom de teste tem uma linha de acentos justamente para conferir.

### O texto quebra na borda direita, ou sobra espaço

A largura está errada. Imprima o teste e olhe a régua:

```
....+....1....+....2....+....3..
```

Coube inteira numa linha? Está certa. Quebrou? Diminua. Sobrou muito espaço?
Aumente.

```bash
menuxy-ponte --colunas 32 --testar    # 58 mm
menuxy-ponte --colunas 48 --testar    # 80 mm
```

### O corte passa por cima da última linha

A lâmina fica alguns milímetros acima da cabeça térmica. Aumente o avanço no
`ponte_config.json`:

```json
"avancos_antes_do_corte": 6
```

### A impressora não corta nada

Muitas 58 mm de serrilha manual não têm guilhotina, e o comando é ignorado pelo
firmware — inofensivo. Se preferir desligar: `"cortar_por_padrao": false`.

### Metros de lixo saindo

Alguém mandou um PDF ou uma página renderizada para uma fila **raw**. Não foi a
ponte: ela só manda ESC/POS. Cancele a fila e procure quem imprimiu por fora:

```bash
cancel -a          # Linux
```

---

## Erros específicos

### `a porta 9100 já está em uso`

Ou a ponte já está aberta — procure o ícone na barra de tarefas —, ou outro
programa ocupa a porta. Para usar outra:

```bash
menuxy-ponte --porta 9101
```

E ajuste o endereço no seu sistema. Para descobrir quem ocupa:

```bash
ss -ltnp | grep 9100        # Linux
netstat -ano | findstr 9100 # Windows
```

Se você migrou da ponte v2, a versão antiga pode ter ficado na inicialização —
veja [MIGRACAO-MENUXY.md](../exemplos/MIGRACAO-MENUXY.md).

### `origem não autorizada` (HTTP 403)

O endereço do seu sistema não está na lista. Ele tem que bater exatamente:
`https://` ≠ `http://`, e a porta faz parte.

```bash
menuxy-ponte --origens https://seusistema.com.br
```

### `muitos trabalhos por minuto` (HTTP 429)

O teto (60/min) foi atingido. Ou é um laço com defeito no sistema — que é
justamente o que o teto existe para conter —, ou o volume é real:

```json
"limite_por_minuto": 120
```

### `a impressora X não existe nesta máquina`

A mensagem lista o que existe. Copie o identificador de lá — inclusive o
prefixo: `sistema:Termica58`, não `Termica58`.

### `a impressora não confirmou o recebimento a tempo`

Sem papel, tampa aberta ou cabeça superaquecida. Confira o equipamento.

### A janela não abre (Linux)

```bash
sudo apt install python3-tk
```

Sem `tkinter` a ponte roda no terminal e **imprime normalmente** — só não tem
interface.

### `ImportError: attempted relative import` ao rodar

Você chamou `python ponte_menuxy/__main__.py` direto. O certo é:

```bash
python3 -m ponte_menuxy
```

---

## Quando nada disso resolve

```bash
menuxy-ponte --diagnostico > diagnostico.txt
```

Junte a `diagnostico.txt` e o registro
(`~/.config/menuxy-ponte/ponte.log` ou `%APPDATA%\MenuxyPonte\ponte.log`) e
descreva: o que você fez, o que esperava e o que aconteceu.

Para investigar a fundo uma impressora USB nova, a ferramenta de baixo nível
continua no projeto:

```bash
python3 ferramenta_cli/imprime_termica.py --listar
```

Ela mostra descritores, endpoints e classes de interface de todos os
dispositivos USB — é com ela que se descobre por que um modelo novo não é
reconhecido.
