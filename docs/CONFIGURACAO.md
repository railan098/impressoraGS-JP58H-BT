# Configuração

Tudo pode ser feito de três jeitos: pela **janela** (aba Configuração), pela
**linha de comando**, ou editando o **arquivo JSON**. Os três mexem no mesmo
lugar.

## Onde o arquivo mora

| Sistema | Caminho |
|---|---|
| Windows | `%APPDATA%\MenuxyPonte\ponte_config.json` |
| Linux | `~/.config/menuxy-ponte/ponte_config.json` |
| macOS | `~/Library/Application Support/MenuxyPonte/ponte_config.json` |

No perfil do usuário, nunca ao lado do programa: o executável pode acabar numa
pasta onde escrever exige administrador, e o perfil sempre é gravável.

Para descobrir o caminho exato nesta máquina: `menuxy-ponte --diagnostico`.

## Os campos

| Campo | Padrão | O que faz |
|---|---|---|
| `porta` | `9100` | Porta HTTP local. Mudar exige avisar o seu sistema. |
| `origens_permitidas` | `["*"]` | Quem pode mandar imprimir. **Feche isto.** |
| `limite_por_minuto` | `60` | Teto de trabalhos por minuto. |
| `impressora_padrao` | `""` | Usada quando o pedido não diz qual. Vazio = a padrão do sistema. |
| `codepage` | `"cp850"` | Tabela de acentos. `cp850` cobre o português; se sair lixo, tente `cp860`. |
| `cortar_por_padrao` | `true` | Desligue se a impressora não tem guilhotina. |
| `colunas` | `32` | Largura da bobina: 32 para 58 mm, 48 para 80 mm. |
| `avancos_antes_do_corte` | `4` | Linhas em branco antes de cortar. |
| `abrir_gaveta_apos_imprimir` | `false` | Pulso na gaveta ao fim de cada cupom. |
| `impressoras_rede` | `[]` | Impressoras com IP, declaradas pelo operador. |
| `iniciar_com_sistema` | `false` | Registrado de verdade no sistema, não só aqui. |
| `abrir_janela` | `true` | Abrir a janela ao iniciar. |
| `fechar_minimiza` | `true` | Fechar a janela minimiza em vez de encerrar. |
| `registrar_em_arquivo` | `true` | Grava `ponte.log` ao lado da configuração. |
| `registro_kb` | `512` | Tamanho do registro antes de rotacionar. |

**O arquivo é saneado na leitura.** Uma porta escrita como `"noventa"` ou uma
página de código inventada viram o padrão, com aviso — nunca uma ponte que não
sobe no login do balcão.

## Pela linha de comando

```bash
menuxy-ponte --porta 9101
menuxy-ponte --origens https://menuxy.alvesprotect.app.br
menuxy-ponte --impressora sistema:Termica58
menuxy-ponte --colunas 48
menuxy-ponte --codepage cp860
menuxy-ponte --iniciar-com-sistema sim
menuxy-ponte --criar-atalho
```

Todas **gravam e saem** — nenhuma sobe o servidor. É o que permite um
instalador chamá-las em sequência sem travar o script esperando um servidor que
nunca termina. Combine à vontade:

```bash
menuxy-ponte --origens https://minhaloja.com.br --impressora sistema:Termica58 --colunas 32
```

Para configurar **e já subir** na mesma chamada, some `--servir`:

```bash
menuxy-ponte --porta 9101 --servir
```

---

## Os quatro ajustes que resolvem quase tudo

### 1. Origens — o único que não pode esperar

Com `["*"]`, **qualquer site que o operador visitar consegue gastar a sua
bobina**. Ler, não consegue — a ponte não tem acesso a dado nenhum — mas
imprimir, sim.

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br
```

A comparação é exata. `https://` e `http://` são origens diferentes, e a porta
faz parte: `https://loja.com.br` não autoriza `https://loja.com.br:8443`.
Vários endereços, separados por espaço:

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br http://192.168.18.31:8080
```

### 2. Largura do papel

Imprima o cupom de teste (`menuxy-ponte --testar`) e olhe a régua:

```
....+....1....+....2....+....3..
```

Se ela couber inteira **numa linha só**, a largura está certa. Se quebrar, o
valor é alto demais; se sobrar muito espaço à direita, é baixo demais. Bobina
de 58 mm quer `32`; a de 80 mm, `48`.

### 3. Acentos saindo como lixo

Cada impressora tem a sua tabela de 256 caracteres, e o comando `ESC t n` diz
qual usar. `cp850` funciona na grande maioria. Se "ção" sair como "‡Æo":

```bash
menuxy-ponte --codepage cp860 --testar
```

O cupom de teste tem uma linha de acentos justamente para conferir isso.

### 4. O corte passando por cima da última linha

A lâmina fica alguns milímetros **acima** da cabeça térmica. Aumente o avanço
no JSON:

```json
"avancos_antes_do_corte": 6
```

Se a impressora não tem guilhotina, o comando de corte é ignorado pelo firmware
— inofensivo. Mas você pode desligá-lo: `"cortar_por_padrao": false`.

---

## Impressora de rede

A ponte **não varre a rede**: varredura é lenta, assusta antivírus e adivinha
errado. Declare o endereço.

Pela janela: aba **Impressoras** → *Adicionar impressora de rede* → o botão
testa o alcance antes de cadastrar.

Pelo JSON:

```json
"impressoras_rede": [
  {"nome": "Cozinha", "host": "192.168.0.50", "porta": 9100},
  {"nome": "Balcao",  "host": "192.168.0.51", "porta": 9100}
]
```

Sem cadastrar, dá para imprimir direto pelo identificador:

```bash
menuxy-ponte --impressora rede:192.168.0.50:9100 --testar
```

A porta 9100 é o protocolo RAW (JetDirect), que praticamente toda impressora de
rede aceita.

---

## Iniciar com o computador

Pela janela: aba **Configuração** → *Iniciar automaticamente ao ligar o
computador*.

Pela linha de comando:

```bash
menuxy-ponte --iniciar-com-sistema sim
menuxy-ponte --iniciar-com-sistema nao
```

Onde isso é gravado:

| Sistema | Onde |
|---|---|
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |
| Linux | `~/.config/autostart/menuxy-ponte.desktop` |
| macOS | `~/Library/LaunchAgents/br.app.alvesprotect.menuxy-ponte.plist` |

Sempre no nível do **usuário**, nunca do sistema. A ponte precisa das
permissões de quem está logado — é quem tem acesso às filas do CUPS e à sessão
gráfica. Um serviço de sistema rodando como `root` não enxergaria nem uma nem
outra.

No Linux, a entrada leva `X-GNOME-Autostart-Delay=10`: alguns ambientes sobem o
autostart antes da rede e do CUPS, e sem a folga a ponte listaria zero
impressoras logo no login.
