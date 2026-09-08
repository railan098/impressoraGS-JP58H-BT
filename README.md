# Impressora Térmica 58mm (SMX-JP58H / POS-58) — ESC/POS direto via USB

Solução que **ignora completamente o driver do fabricante**, o spooler do Windows e o
CUPS, falando ESC/POS diretamente no endpoint USB bulk-OUT. É por isso que funciona
em **Windows 11 ARM (Snapdragon 7c Gen 2)**, onde o driver oficial não existe.

> ### ✅ Testado em hardware real
> Este código foi executado contra a impressora física durante o desenvolvimento:
> ```
> [OK] Impressora encontrada pela classe USB 7 (interface 0): 0x0416:0x5011 — POS-58 Printer
> [OK] Driver do kernel (usblp) desanexado da interface 0.
> [OK] Endpoint OUT: 0x01 (pacote de 64 bytes)
> [OK] 412 bytes enviados à impressora.
> ```

---

## 📌 Os IDs reais da sua impressora

Descobertos lendo os descritores USB do seu equipamento:

| Campo | Valor | Observação |
|---|---|---|
| `idVendor` | **`0x0416`** | Winbond/Nuvoton (chip **YICHIP3121**) |
| `idProduct` | **`0x5011`** | anunciado como "Virtual Com Port" |
| `Product` | `POS-58 Printer` | |
| `bDeviceClass` | **`0`** | ⚠️ *não* é 7 — veja abaixo |
| `bInterfaceClass` | **`7`** (Printer) | a classe fica na **interface** |
| `bInterfaceProtocol` | `2` | bidirecional |
| Endpoint **OUT** | **`0x01`** | Bulk, 64 bytes |
| Endpoint **IN** | `0x81` | Bulk, 64 bytes |

### ⚠️ Correção técnica importante

Você sugeriu filtrar por `bDeviceClass == 7`. **Isso não funciona nesta impressora** —
e nem na maioria das 58mm genéricas. Elas declaram `bDeviceClass = 0x00`
("classe definida na interface") e colocam a classe 7 na *interface*:

```
bDeviceClass         0  [unknown]      <-- seria descartada pelo filtro
  bInterfaceClass    7  Printer        <-- é aqui que está
```

O script faz a varredura **interface a interface** (`intf.bInterfaceClass == 7`),
que é o que realmente encontra o equipamento.

### ⚠️ Segunda correção: o comando de corte

O comando citado, `\x1D\xV\x00`, **não é válido** — `\xV` não é um escape hexadecimal
em Python (`\x` exige dois dígitos hex, e `V` não é dígito). Isso causaria
`SyntaxError` na importação. Os comandos corretos são:

| Comando | Bytes | Significado |
|---|---|---|
| `GS V 0` | `\x1D\x56\x00` | corte total |
| `GS V 1` | `\x1D\x56\x01` | corte parcial |
| `GS V B n` | `\x1D\x56\x42\x40` | avança `n` pontos e corta ← **usado no script** |

O script usa a terceira forma porque ela empurra o texto para fora da cabeça térmica
antes de cortar. **Se a sua SMX-JP58H não tiver guilhotina** (a maioria das 58mm de
serrilha manual não tem), o comando é simplesmente ignorado pelo firmware — inofensivo.

---

## 1. Arquivos

| Arquivo | Função |
|---|---|
| `imprime_termica.py` | o programa |
| **`instalar.bat`** | **instalador automático do Windows — duplo clique** |
| `imprimir.bat` | menu de uso no Windows |
| `gerar_exe.bat` | gera o `.exe` standalone |
| `instalar.sh` | instalador automático do Linux |
| `imprimir.sh` | atalho de uso no Linux |
| `requirements.txt` | dependências |
| `99-impressora-termica.rules` | regra udev (Linux) |

---

## 1.1 🚀 Instalação rápida (o caminho curto)

### Windows

> ### ⚠️ Onde clonar — leia antes
> **Nunca clone dentro de `C:\Windows\System32`, `SysWOW64` ou `Program Files`.**
>
> Isso acontece sem querer: o "cmd como administrador" **sempre abre em
> `C:\Windows\System32`**, e um `git clone` ali joga o projeto na pasta de sistema.
> Os sintomas são criar `.venv` exigindo admin, o Defender bloqueando arquivos, e o
> risco de um comando de limpeza mal digitado quebrar o Windows.
>
> **Clone aqui:**
> ```powershell
> cd $env:USERPROFILE\Documents
> git clone https://github.com/railan098/impressoraGS-JP58H-BT.git
> cd impressoraGS-JP58H-BT
> ```
> O `instalar.bat` detecta pasta de sistema e se recusa a continuar, oferecendo
> copiar o projeto para o lugar certo.

```
1. Clone o projeto em Documentos (NÃO em System32)
2. DUPLO CLIQUE em  instalar.bat
3. Siga as instruções na tela
4. Rode o Zadig (o instalador te avisa se for preciso)
5. DUPLO CLIQUE em  imprimir.bat
```

O `instalar.bat` faz tudo sozinho: confere o Python e a arquitetura, cria o
ambiente virtual, instala as bibliotecas, resolve a libusb (inclusive baixando a
DLL ARM64 do GitHub se você estiver no Python ARM64), testa o backend e já procura
a impressora.

### Linux

```bash
chmod +x instalar.sh imprimir.sh
./instalar.sh
```

As seções abaixo explicam o que os instaladores fazem por baixo, e servem para
quando algo dá errado.

---

## 2. 🪟 Windows 11 ARM (Snapdragon 7c Gen 2)

### 2.1 — ⚠️ LEIA ANTES: qual Python instalar

Este é **o ponto que mais trava** nesse setup, e a resposta não é óbvia:

> **Recomendação: instale o Python x64, não o ARM64.**

Motivo: o PyUSB precisa da biblioteca nativa `libusb-1.0.dll`, e a arquitetura da DLL
precisa bater com a do interpretador. Praticamente **não existem wheels prontas de
libusb para `win-arm64`**, enquanto para x64 elas são abundantes. O Windows 11 ARM
executa binários x64 sob emulação de forma transparente, e para enviar 400 bytes a uma
impressora o custo da emulação é irrelevante.

| Rota | Python | libusb | Dificuldade |
|---|---|---|---|
| **A (recomendada)** | x64 (emulado) | `pip install libusb-package` | fácil |
| B (nativa) | ARM64 | DLL ARM64 extraída à mão do release oficial | trabalhosa |

**Rota A — passo a passo:**

1. Vá em <https://www.python.org/downloads/windows/>
2. Baixe **"Windows installer (64-bit)"** — o rótulo é `amd64`, **não** o `arm64`.
   Python 3.8+ serve; 3.11 ou 3.12 é a escolha segura.
3. Na primeira tela do instalador, **marque `Add python.exe to PATH`**.
4. Conclua a instalação e confirme no PowerShell:
   ```powershell
   python --version
   ```

> **Python 3.14 funciona.** Verifiquei a disponibilidade de wheels no PyPI:
> `pyusb` e `python-escpos` são Python puro (rodam em qualquer versão/arquitetura),
> e o `Pillow` (dependência do escpos) já publica wheels `cp314` para
> `win_amd64` **e** `win_arm64`. O único pacote sem versão ARM64 é o
> `libusb-package` — que é exatamente por isso que a rota x64 é a recomendada.
> Se você insistir no ARM64, o `instalar.bat` baixa a DLL certa automaticamente.

**Rota B (só se você fizer questão do ARM64 nativo):** instale o Python ARM64, baixe
`libusb-1.0.XX.7z` em <https://github.com/libusb/libusb/releases>, extraia
`VS2025\ARM64\dll\libusb-1.0.dll` e coloque na mesma pasta do script (ou aponte com
`--libusb C:\caminho\libusb-1.0.dll`).

### 2.2 — Instalar as dependências

```powershell
python -m pip install --upgrade pip
python -m pip install pyusb python-escpos libusb-package
```

> `libusb-package` é o que dispensa você de caçar a DLL manualmente. Se preferir não
> usá-lo, o script aceita `--libusb <caminho da dll>`.

### 2.3 — 🔑 PASSO CRÍTICO: trocar o driver com o Zadig

O Windows atribui à impressora o driver `usbprint.sys`, que é **exclusivo** e bloqueia
o libusb. É preciso substituí-lo pelo **WinUSB** genérico.

**Baixe o Zadig em <https://zadig.akeo.ie/>** (é portátil, não instala nada).
O `.exe` é x86/x64 e roda sob emulação no Windows ARM sem problemas.

```
┌─────────────────────────────────────────────────────────────────────┐
│  PASSO 1  Conecte a impressora e LIGUE ela (o botão de energia).     │
│           Só o cabo USB não basta — o USB alimenta o chip, mas a     │
│           impressora precisa estar ligada para enumerar direito.     │
├─────────────────────────────────────────────────────────────────────┤
│  PASSO 2  Clique com o botão direito em zadig.exe                    │
│           → "Executar como administrador"                            │
├─────────────────────────────────────────────────────────────────────┤
│  PASSO 3  No menu superior:  Options  →  ☑ List All Devices          │
│           ▲ SEM ISSO A IMPRESSORA NÃO APARECE NA LISTA.              │
├─────────────────────────────────────────────────────────────────────┤
│  PASSO 4  Na caixa suspensa, escolha a sua impressora.               │
│           Procure por:  "POS-58 Printer"  ou  "POS58"  ou            │
│                         "Printer"  ou  "USB Printing Support"        │
│           ✔ CONFIRME pelo USB ID logo abaixo:  0416  5011            │
└─────────────────────────────────────────────────────────────────────┘

   Assim deve ficar a janela do Zadig:

   ┌───────────────────────────── Zadig ─────────────────────────────┐
   │ Device  Options  Help                                           │
   │                                                                 │
   │  ┌───────────────────────────────────────────────┐              │
   │  │ POS-58 Printer                            ▼   │  <- PASSO 4  │
   │  └───────────────────────────────────────────────┘              │
   │                                                                 │
   │   Driver     usbprint (v10.0.x)   ➜   WinUSB (v6.1.x)           │
   │              ▲ o que está lá          ▲ PASSO 5: use as setinhas│
   │                                         ◄ ► até aparecer WinUSB │
   │                                                                 │
   │   USB ID     0416   5011      <- confira se é este!             │
   │   WCID²      ✗                                                  │
   │                                                                 │
   │        ┌──────────────────────────────────┐                     │
   │        │      Replace Driver              │  <- PASSO 6: clique │
   │        └──────────────────────────────────┘                     │
   └─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  PASSO 5  No campo da DIREITA, use as setas ◄ ► até selecionar      │
│           **WinUSB**  (NÃO escolha libusb-win32 nem libusbK).       │
├─────────────────────────────────────────────────────────────────────┤
│  PASSO 6  Clique em "Replace Driver" (ou "Install Driver").         │
│           Demora de 10 a 60 segundos. NÃO cancele nem desconecte.   │
│           Aceite o aviso do Windows sobre driver não assinado.      │
├─────────────────────────────────────────────────────────────────────┤
│  PASSO 7  Ao ver "The driver was installed successfully", feche.    │
│           Desconecte e reconecte o cabo USB.                        │
└─────────────────────────────────────────────────────────────────────┘
```

**Como confirmar que deu certo:** abra o Gerenciador de Dispositivos
(`Win+X` → Gerenciador de Dispositivos). A impressora deve ter **saído** de
"Filas de impressão" e aparecido em **"Dispositivos USB universais"** como
`POS-58 Printer`.

> **⚠️ Efeito colateral esperado:** depois do Zadig, a impressora **deixa de aparecer**
> em "Impressoras e Scanners" do Windows. Isso é normal e é justamente o objetivo — ela
> passa a ser controlada só por este script. Para reverter: Gerenciador de Dispositivos
> → botão direito na impressora → Desinstalar dispositivo → marque "tentar remover o
> driver" → reconecte o cabo.

### 2.4 — Executar

```powershell
python imprime_termica.py --listar        # confirme que ela aparece
python imprime_termica.py                 # imprime o cupom de teste
python imprime_termica.py --texto "Meu recibo"
python imprime_termica.py --vid 0x0416 --pid 0x5011
```

### 2.5 — Problemas comuns no Windows

| Sintoma | Causa / solução |
|---|---|
| `NoBackendError` | libusb ausente → `pip install libusb-package`, ou `--libusb C:\...\libusb-1.0.dll` com a **mesma arquitetura do Python** |
| `Access denied (errno 13)` | Zadig não foi aplicado, ou foi aplicado no dispositivo errado. Refaça com `List All Devices` marcado |
| Não aparece no `--listar` | Impressora desligada, ou ainda em `usbprint.sys` |
| DLL "não é um aplicativo Win32 válido" | Arquiteturas trocadas: Python ARM64 com DLL x64 (ou vice-versa) |
| Erro de timeout | Sem papel, tampa aberta, ou impressora desligada |

---

## 3. 🐧 Linux (Debian / Ubuntu, amd64 e arm64)

### 3.1 — Dependências do sistema

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv libusb-1.0-0 libusb-1.0-0-dev
```

### 3.2 — Dependências Python

Distros recentes (Ubuntu 23.04+, Debian 12+) bloqueiam `pip install` global
(PEP 668). Use um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyusb python-escpos
```

<details>
<summary>Alternativa sem venv (pacotes do sistema)</summary>

```bash
sudo apt install -y python3-usb python3-escpos
```
</details>

### 3.3 — 🔑 Regra UDEV (acesso sem `sudo`)

Sem isso você recebe `USBError: [Errno 13] Access denied`.

```bash
sudo tee /etc/udev/rules.d/99-impressora-termica.rules > /dev/null <<'EOF'
# POS-58 / SMX-JP58H (Winbond 0416:5011)
SUBSYSTEM=="usb", ATTRS{idVendor}=="0416", ATTRS{idProduct}=="5011", MODE="0666", GROUP="lp", TAG+="uaccess"

# Regra genérica: qualquer dispositivo com interface de classe 7 (Printer)
SUBSYSTEM=="usb", ENV{ID_USB_INTERFACES}=="*:07*:*", MODE="0666", GROUP="lp", TAG+="uaccess"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

> O arquivo `99-impressora-termica.rules` deste repositório já traz essas regras mais
> as de outros clones comuns — se preferir: `sudo cp 99-impressora-termica.rules /etc/udev/rules.d/`

**Troque o VID/PID se a sua for diferente.** Descubra com `lsusb` ou
`python3 imprime_termica.py --listar`.

### 3.4 — Adicionar o usuário ao grupo `lp`

```bash
sudo usermod -aG lp $USER
```

⚠️ **É obrigatório fazer logout/login** (ou reiniciar) para o grupo valer.
Verifique com:

```bash
groups | grep lp        # deve listar 'lp'
id -nG                  # confirmação alternativa
```

Truque para testar sem deslogar (vale só para o shell atual):

```bash
newgrp lp
```

### 3.5 — Reconecte o cabo

As regras udev só se aplicam quando o dispositivo é enumerado. **Desconecte e
reconecte o cabo USB** depois de instalar a regra.

Verificação das permissões:

```bash
lsusb | grep -i pos            # localize bus/device
ls -l /dev/bus/usb/001/00X     # deve mostrar crw-rw-rw- ... lp
```

### 3.6 — Sobre o driver `usblp` do kernel

O Linux anexa automaticamente o módulo `usblp` à impressora, criando `/dev/usb/lp0`.
Isso normalmente impede o libusb de reivindicar a interface.

**O script já resolve isso sozinho** — ele chama `detach_kernel_driver()` antes de
imprimir e devolve a impressora ao kernel no final. Foi exatamente o que aconteceu no
teste real:

```
[OK] Driver do kernel (usblp) desanexado da interface 0.
```

Se ainda assim aparecer `Resource busy (errno 16)`, o CUPS é o culpado:

```bash
sudo systemctl stop cups cups-browsed
# ou, para soltar de vez:
sudo modprobe -r usblp
```

### 3.7 — Executar

```bash
python3 imprime_termica.py --listar
python3 imprime_termica.py
python3 imprime_termica.py --texto "Comanda 42 — Mesa 7"
python3 imprime_termica.py --arquivo cupom.txt
python3 imprime_termica.py --usar-escpos
python3 imprime_termica.py --abrir-gaveta          # pulso RJ11
```

### 3.8 — Problemas comuns no Linux

| Sintoma | Solução |
|---|---|
| `Access denied (errno 13)` | Regra udev não aplicada, ou cabo não foi reconectado, ou falta logout após `usermod` |
| `Resource busy (errno 16)` | `sudo systemctl stop cups` e/ou `sudo modprobe -r usblp` |
| `NoBackendError` | `sudo apt install libusb-1.0-0` |
| `externally-managed-environment` | Use o venv da seção 3.2 |
| Acentos saem errados | Tente `--codepage cp860` (Portuguese) ou `--codepage cp437` |

---

## 4. 📦 Gerar executáveis standalone (PyInstaller)

O usuário final não precisa instalar Python nem as bibliotecas.

```bash
pip install pyinstaller
```

### Windows (`.exe`)

```powershell
pyinstaller --onefile --console --name imprime_termica ^
            --collect-all usb ^
            --collect-all libusb_package ^
            imprime_termica.py
```

Saída: `dist\imprime_termica.exe`

> **⚠️ PyInstaller não faz cross-compilation.** O `.exe` precisa ser gerado **na
> própria máquina Windows ARM** para virar um binário ARM64 — gerar num PC x64 produz
> um `.exe` x64 (que ainda assim roda no ARM sob emulação, e é a rota mais prática
> dado o cenário de libusb descrito na seção 2.1).
>
> **⚠️ O Zadig continua sendo obrigatório** na máquina de destino. O `.exe` empacota o
> Python e as bibliotecas, mas não o driver WinUSB.

Se não usar `libusb-package`, copie a `libusb-1.0.dll` para junto do `.exe`, ou embuta:

```powershell
pyinstaller --onefile --console --add-binary "libusb-1.0.dll;." imprime_termica.py
```

### Linux (binário ELF)

```bash
pyinstaller --onefile --console --name imprime_termica \
            --collect-all usb \
            imprime_termica.py
```

Saída: `dist/imprime_termica`

```bash
chmod +x dist/imprime_termica
./dist/imprime_termica --listar
```

> **⚠️ Compile na mesma arquitetura do alvo.** Um build feito em amd64 **não roda** em
> arm64 (Raspberry Pi etc.) — gere o binário arm64 numa máquina arm64.
>
> Para máxima compatibilidade entre distros, compile na distro **mais antiga** que
> pretende suportar (a glibc é retrocompatível para a frente, não para trás).

### Comando mínimo (o que você pediu)

```bash
pyinstaller --onefile --console imprime_termica.py
```

Funciona nos dois sistemas. As flags `--collect-all` acima são recomendadas porque o
PyUSB carrega o backend dinamicamente e o PyInstaller às vezes não detecta essa
dependência sozinho.

---

## 5. Referência da linha de comando

| Flag | Efeito |
|---|---|
| *(nenhuma)* | detecta e imprime o cupom de teste |
| `--listar` | lista todos os dispositivos USB com VID/PID |
| `--vid 0x0416 --pid 0x5011` | força um dispositivo específico |
| `--texto "..."` | imprime um texto próprio |
| `--arquivo cupom.txt` | imprime o conteúdo de um arquivo UTF-8 |
| `--codepage cp850\|cp860\|cp437\|cp1252` | página de código dos acentos |
| `--sem-corte` | não envia o comando de corte |
| `--usar-escpos` | usa a biblioteca python-escpos |
| `--libusb <caminho>` | aponta a libusb manualmente |
| `--abrir-gaveta` | dispara o pulso da gaveta de dinheiro (RJ11) |

Códigos de saída: `0` sucesso · `2` pyusb ausente · `3` sem backend libusb ·
`4` erro de arquivo · `5` erro USB · `6` impressora não encontrada.

---

## 6. Usando como biblioteca

```python
from imprime_termica import montar_cupom, imprimir_pyusb, ESCPOS

# Cupom montado à mão
dados = (
    ESCPOS.INIT
    + ESCPOS.codepage(2)                  # CP850, acentos PT-BR
    + ESCPOS.ALINHA_CENTRO
    + ESCPOS.TAM_DUPLO
    + "PADARIA DO ZE\n".encode("cp850")
    + ESCPOS.TAM_NORMAL
    + ESCPOS.ALINHA_ESQ
    + "Pao frances .... R$ 12,00\n".encode("cp850")
    + "Cafe ........... R$  8,50\n".encode("cp850")
    + ESCPOS.avanca(4)
    + ESCPOS.corte_com_avanco()
)
imprimir_pyusb(dados)

# Ou o atalho:
imprimir_pyusb(montar_cupom("Comanda 42"))
```

---

## 7. 🐙 Fluxo de trabalho com o GitHub

Repositório: <https://github.com/railan098/impressoraGS-JP58H-BT>

### 7.1 — Enviar as alterações (do Linux, onde você desenvolve)

```bash
git add -A
git commit -m "Descreva o que mudou"
git push origin main
```

### 7.2 — Baixar no Windows ARM (a máquina da impressora)

Abra o **Git Bash** ou o **PowerShell** na pasta onde quer o projeto:

```bash
git clone https://github.com/railan098/impressoraGS-JP58H-BT.git
cd impressoraGS-JP58H-BT
```

Depois é só dar **duplo clique em `instalar.bat`**.

### 7.3 — Atualizar o Windows depois de mudar algo no Linux

No Windows, dentro da pasta do projeto:

```bash
git pull
```

Pronto — o `imprime_termica.py` atualizado já está lá. Não precisa reinstalar nada,
o `.venv` continua valendo. Só rode `imprimir.bat` de novo.

> Esse é o ciclo que você queria: **edita no Linux → `git push` → `git pull` no
> Windows → testa na impressora.** Sem pendrive, sem anexo de e-mail.

### 7.4 — Se você editar direto no Windows

```bash
git add -A
git commit -m "Ajuste feito no Windows"
git push
```

E no Linux, `git pull` para receber de volta.

### 7.5 — Autenticação (o GitHub não aceita mais senha)

Se o `git push` pedir usuário e senha e recusar sua senha normal, é porque o GitHub
exige **token**, não senha:

1. <https://github.com/settings/tokens> → **Generate new token (classic)**
2. Marque o escopo **`repo`**
3. Copie o token (ele só aparece uma vez)
4. No `git push`, use o **token no lugar da senha**

Para não digitar toda vez:

```bash
# Linux
git config --global credential.helper store

# Windows (já vem com o Git for Windows)
git config --global credential.helper manager
```

### 7.6 — ⚠️ Sobre o binário de 21 MB no histórico

O primeiro commit incluiu `dist/imprime_termica` (o executável Linux, 21 MB). Já
adicionei `dist/` ao `.gitignore`, então **novos commits não levam mais binários** —
mas o arquivo continua no histórico do repositório, deixando o `git clone` pesado.

Como o repositório é novo e só você o usa, dá para limpar reescrevendo o histórico:

```bash
git checkout --orphan limpo     # cria um branch sem histórico
git add -A
git commit -m "Impressora térmica 58mm ESC/POS via USB"
git branch -D main
git branch -m main
git push -f origin main         # sobrescreve o histórico remoto
```

> **Só faça isso se ninguém mais tiver clonado o repositório** — o `push -f`
> reescreve o histórico para todo mundo. Se preferir não mexer, não tem problema:
> os 21 MB só tornam o clone mais lento, nada quebra.

### 7.7 — O que **não** vai para o GitHub (por design)

O `.gitignore` exclui de propósito:

| Item | Por quê |
|---|---|
| `.venv/` | ambiente virtual — cada máquina cria o seu |
| `dist/`, `build/`, `*.spec` | binários gerados; recrie com `gerar_exe.bat` |
| `libusb-1.0.dll` | é baixada pelo instalador, e é específica da arquitetura |
| `POS58Setup.exe`, `POS-58` | drivers do fabricante (3 MB, e não funcionam em ARM) |

⚠️ **Importante sobre a `libusb-1.0.dll`:** nunca versione essa DLL. A do x64 não
roda no ARM64 e vice-versa — se ela entrar no repositório, quebra na outra máquina.
Deixe o `instalar.bat` baixar a correta para cada uma.
