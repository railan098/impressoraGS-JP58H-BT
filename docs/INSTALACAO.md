# Instalação

A ponte roda **na máquina do balcão**, junto da impressora. Não é ela que vai
no seu servidor: um servidor não alcança a USB de um computador a 500 km dele.

Escolha o caminho pela máquina de destino:

| Situação da máquina | Use |
|---|---|
| Windows, sem Python | [`PonteMenuxy.exe`](#windows--o-executável-recomendado) |
| Windows, com Python | [`instalar_windows.bat`](#windows--a-partir-do-código) |
| Linux (Debian, Ubuntu, Mint, Pop!_OS) | [o `.deb`](#linux--o-pacote-deb-recomendado) |
| Linux, outra distribuição | [`instalar_linux.sh`](#linux--a-partir-do-código) |
| macOS | [`instalar_linux.sh`](#macos) (o caminho é o mesmo) |

---

## Windows — o executável (recomendado)

Um arquivo só, sem Python no destino.

**Você, uma vez por versão:**

```
empacotar\windows\gerar_exe.bat
```

Sai `dist\PonteMenuxy.exe`.

**O cliente:**

1. Copia o `.exe` para uma pasta dele — `Documentos`, a área de trabalho, onde
   quiser. **Nunca em `C:\Windows\System32` nem em `Program Files`**: a
   primeira é a pasta do sistema, e a segunda exige administrador para
   escrever.
2. Duplo clique.
3. Na aba **Configuração**: marca *Iniciar automaticamente ao ligar o
   computador*, preenche as *Origens permitidas* com o endereço do sistema e
   clica em **Salvar**.
4. Na aba **Impressoras**: escolhe a impressora, clica em **Usar esta** e em
   **Imprimir teste**.

O botão *Criar atalho na área de trabalho* põe o ícone fora da pasta do
programa, que é de onde o operador vai abrir todo dia.

## Windows — a partir do código

Para a máquina que já tem Python:

```
empacotar\windows\instalar_windows.bat
```

Ele confere o Python, copia o programa para `%LOCALAPPDATA%\MenuxyPonte`,
instala os opcionais, **pergunta o endereço do seu sistema**, cria os atalhos e
oferece registrar na inicialização.

> **Por que `%LOCALAPPDATA%` e não `Program Files`:** escrever em Program Files
> exige administrador, e a ponte precisa imprimir com as permissões de quem
> está logado — que é quem tem acesso às impressoras do usuário.

---

## Linux — o pacote `.deb` (recomendado)

```bash
# gerar (uma vez, na sua máquina)
./empacotar/linux/gerar_deb.sh

# instalar (na máquina do balcão)
sudo apt install ./dist/menuxy-ponte_3.0.1_all.deb
```

O pacote é `all` — o mesmo arquivo serve amd64, arm64 e armhf, inclusive
Raspberry Pi de balcão. Ele instala:

* `/usr/bin/menuxy-ponte` — o comando;
* o item no menu de aplicativos, com ícone;
* a regra udev que dá acesso à impressora USB sem `sudo`;
* o manual (`man menuxy-ponte`) e a documentação em
  `/usr/share/doc/menuxy-ponte/`.

Depois de instalar:

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br   # feche a lista
menuxy-ponte --iniciar-com-sistema sim                      # inicie com o PC
menuxy-ponte --criar-atalho                                 # ícone na área de trabalho
menuxy-ponte --listar                                       # confira
```

Para imprimir por **USB direta** sem `sudo`, entre no grupo `lp` e refaça o
login:

```bash
sudo usermod -aG lp $USER
```

**Desinstalar:** `sudo apt remove menuxy-ponte`. A configuração fica no perfil
do usuário e não é apagada — desinstalar para atualizar não pode perder a
impressora escolhida no balcão. Para limpar de vez:
`rm -rf ~/.config/menuxy-ponte`.

## Linux — a partir do código

Para distribuições sem `apt` (Fedora, Arch, openSUSE):

```bash
./empacotar/linux/instalar_linux.sh
```

Instala em `~/.local` — **sem `sudo`**, de propósito: a ponte imprime com as
permissões de quem está logado, e um serviço rodando como `root` não enxergaria
as filas do CUPS do usuário.

**Binário único** para máquina sem Python:

```bash
./empacotar/linux/gerar_binario.sh
```

> Gere na distribuição **mais antiga** que os seus clientes usam: o binário do
> PyInstaller carrega a glibc da máquina onde foi construído. Um feito no
> Ubuntu 24.04 não roda no 20.04; o contrário funciona. Na dúvida, prefira o
> `.deb`, que é Python puro e não tem esse problema.

---

## macOS

O caminho do Linux serve — o macOS também usa CUPS:

```bash
./empacotar/linux/instalar_linux.sh
```

O início automático vira um LaunchAgent em
`~/Library/LaunchAgents/br.app.alvesprotect.menuxy-ponte.plist`.

---

## O que é obrigatório e o que é opcional

**Obrigatório:** Python 3.8 ou mais novo. Só isso. O caminho `sistema:` — o que
a maioria usa — não tem nenhuma outra dependência.

| Opcional | O que acrescenta | Instalar |
|---|---|---|
| `python3-tk` | a janela de configuração | `sudo apt install python3-tk` |
| `cups-client` | as impressoras instaladas no Linux | `sudo apt install cups-client` |
| `pyusb` | o caminho `usb:` (impressora sem driver) | `pip install pyusb` |
| `pyserial` | o caminho `serial:` | `pip install pyserial` |

Faltando qualquer um deles, o caminho correspondente some do catálogo e **todo
o resto continua funcionando**. Confira o que a sua máquina tem:

```bash
menuxy-ponte --diagnostico
```

---

## Conferir se deu certo

```bash
menuxy-ponte --diagnostico   # o que a ponte enxerga de si mesma
menuxy-ponte --listar        # as impressoras
menuxy-ponte --testar        # imprime UM cupom de teste
```

E, no navegador da mesma máquina, abra `exemplos/web/exemplo.html`: ela mostra
a situação da ponte e imprime sem envolver o seu sistema. Quando o cupom não
sai, é essa página que diz se o problema é a ponte ou o sistema que fala com ela.
