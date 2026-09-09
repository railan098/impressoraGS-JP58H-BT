# Empacotamento

Como sair do código e chegar num arquivo que o cliente instala.

| Destino | Comando | Sai |
|---|---|---|
| Windows, sem Python | `empacotar\windows\gerar_exe.bat` | `dist\PonteMenuxy.exe` |
| Debian/Ubuntu | `./empacotar/linux/gerar_deb.sh` | `dist/menuxy-ponte_3.0.1_all.deb` |
| Linux, sem Python | `./empacotar/linux/gerar_binario.sh` | `dist/menuxy-ponte-3.0.1-linux-x86_64` |

---

## Windows — o `.exe`

```
empacotar\windows\gerar_exe.bat
```

Ele instala o PyInstaller, tenta instalar os opcionais (`pyusb`, `pyserial`,
`libusb-package`) e empacota com `empacotar\PonteMenuxy.spec`.

**Decisões da receita, e por quê:**

* **`--onefile`** — um arquivo só. O cliente baixa e dá duplo clique; não há
  pasta para alguém mover pela metade.
* **`console=False`** — sem a janela preta atrás do aplicativo. O diagnóstico
  continua saindo por `--diagnostico` e pelo `ponte.log`.
* **UPX desligado** — ele encolheria o arquivo, mas antivírus de balcão tratam
  executável comprimido como suspeito, e um falso positivo no cliente custa
  mais caro que 8 MB.
* **`tkinter` em `hiddenimports`** — a ponte só o importa dentro de funções (de
  propósito, para funcionar em Linux sem ele), e o PyInstaller às vezes não
  detecta isso sozinho.
* **`matplotlib`, `numpy` e afins em `excludes`** — entrariam por dependência
  transitiva do Pillow e dobrariam o tamanho sem que nada aqui os use.
* **`empacotar/executavel.py` como ponto de entrada** — o script de entrada do
  PyInstaller roda como `__main__` solto, sem pacote pai, e ali
  `from .cli import main` falha. Esse arquivo faz o import absoluto;
  `ponte_menuxy/__main__.py` continua servindo ao `python -m`.

**Antes de entregar, confira numa máquina sem Python:**

```
PonteMenuxy.exe --listar
PonteMenuxy.exe --diagnostico
```

O diagnóstico tem que dizer `empacotado : sim (PyInstaller)`.

---

## Assinatura digital

Não existe como "pular" o SmartScreen: ele é **reputação**, não antivírus.
O caminho é deixar de ser desconhecido — assinando. Sem assinatura o build não
falha; sai um `.exe` que funciona, com aviso na primeira execução (o passo a
passo para o operador está em [INSTALACAO.md](INSTALACAO.md)).

**São três controles diferentes**, e confundi-los faz perder tempo:

| Controle | O que é | Como sai |
|---|---|---|
| **Mark of the Web** | marca de "veio da internet" no arquivo baixado | entregar por pendrive, ou *Propriedades → Desbloquear* |
| **SmartScreen** | reputação do binário e do editor | assinar; enquanto isso, *Mais informações → Executar assim mesmo* |
| **Controle de Aplicativo Inteligente** | Windows 11, só em instalação limpa | **não tem "executar assim mesmo"** — só assinatura resolve |

### Que certificado

| | Custo/ano | Efeito |
|---|---|---|
| **OV** (organização) | ~US$ 200–400 | assina; a reputação ainda se acumula com os downloads |
| **EV** (validação estendida) | ~US$ 300–600 | caminho mais rápido para reputação |
| **Certum Open Source** | dezenas de euros | para projeto de código aberto — **este é MIT, então se qualifica** |

Dois detalhes que pegam de surpresa:

* Desde **junho de 2023** a chave privada precisa morar em hardware (token
  FIPS 140-2) ou HSM na nuvem. Não se recebe mais um `.pfx` por e-mail.
* **Sempre carimbe a hora** (`/tr`). Sem o carimbo, a assinatura morre junto
  com o certificado e os executáveis já entregues voltam a dar aviso.

### Como usar no build

O `gerar_exe.bat` assina sozinho quando encontra a configuração, e apenas avisa
quando não encontra. Escolha **uma** das três formas:

```bat
REM  Token EV ou HSM — a forma precisa, pela impressao digital do certificado
set MENUXY_CERT_SHA1=a1b2c3d4e5f6...

REM  ou pelo nome do titular, se so houver um certificado na loja
set MENUXY_CERT_NOME=Railan Alves

REM  ou arquivo .pfx (so certificado antigo; os novos exigem hardware)
set MENUXY_CERT_PFX=C:\caminho\cert.pfx
set MENUXY_CERT_SENHA=...

REM  opcional: outro carimbador
set MENUXY_CARIMBO=http://timestamp.sectigo.com

empacotar\windows\gerar_exe.bat
```

Para achar a impressão digital do que está instalado:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Format-List Subject, Thumbprint, NotAfter
```

O script procura o `signtool.exe` no PATH e no Windows SDK, assina com SHA-256,
carimba a hora e **confere a assinatura depois** — assinar "com sucesso" e a
cadeia não fechar na máquina do cliente é um erro que só apareceria lá, e tarde.
Ao final ele diz `Assinado digitalmente: sim` ou `nao`.

### O que já é de graça

* **Recurso de versão** no `.exe`: nome do produto, empresa, versão e copyright
  aparecem nas Propriedades. É gerado a partir do arquivo `VERSION`, então o
  número não precisa ser mantido em dois lugares. Executável anônimo pesa
  contra na heurística e não diz nada a quem abre as Propriedades para decidir
  se confia.
* **UPX desligado** — comprimido levanta mais suspeita do que os 8 MB poupados.
* **Falso positivo do Defender** é comum com `--onefile`, porque o executável
  se descompacta no temp. Submeta em `microsoft.com/wdsi/filesubmission`:
  costuma sair em poucos dias e vale para todos os clientes de uma vez.

> **O que não fazer:** desligar o SmartScreen por registro ou GPO na máquina do
> cliente. Funciona, e derruba a proteção do balcão inteiro para resolver um
> aviso que aparece uma vez. Se a frota é gerenciada, a decisão é do
> administrador dela — não algo que o seu instalador deva fazer sozinho.

---

## Linux — o `.deb`

```bash
./empacotar/linux/gerar_deb.sh
sudo apt install ./dist/menuxy-ponte_3.0.1_all.deb
```

**`Architecture: all`** — tudo é Python puro, então o mesmo arquivo serve
amd64, arm64 e armhf, inclusive Raspberry Pi de balcão. É a diferença entre um
arquivo e três.

O que o pacote coloca:

```
/usr/bin/menuxy-ponte                              invólucro
/usr/lib/menuxy-ponte/ponte_menuxy/                o pacote Python
/usr/share/applications/menuxy-ponte.desktop       item do menu
/usr/share/icons/hicolor/*/apps/menuxy-ponte.png   ícones
/usr/share/man/man1/menuxy-ponte.1.gz              manual
/usr/share/doc/menuxy-ponte/                       README, docs e exemplos
/lib/udev/rules.d/99-impressora-termica.rules      acesso à USB sem sudo
```

**`PYTHONPATH` em vez de `dist-packages`:** o pacote fica contido em
`/usr/lib/menuxy-ponte` e não polui o Python do sistema. Desinstalar remove
tudo, sem sobra.

**Dependências:** `python3 (>= 3.8)` e `python3-tk`. `cups-client` e
`python3-usb` são `Recommends` — o `apt` os instala por padrão, mas a ponte
funciona sem.

**O `postinst`** recarrega as regras udev, atualiza o banco de aplicativos e o
cache de ícones, e imprime os próximos passos. **O `prerm` não apaga a
configuração**: desinstalar para atualizar não pode perder a impressora
escolhida no balcão.

Conferir o pacote antes de distribuir:

```bash
dpkg-deb --info dist/menuxy-ponte_*.deb
dpkg-deb -c    dist/menuxy-ponte_*.deb
lintian        dist/menuxy-ponte_*.deb    # se tiver o lintian instalado
```

---

## Linux — o binário único

```bash
./empacotar/linux/gerar_binario.sh
```

Para máquina sem Python. **O binário carrega a glibc da máquina onde foi
construído**: gere na distribuição mais antiga que os seus clientes usam. Um
feito no Ubuntu 24.04 não roda no 20.04; o contrário funciona.

Na dúvida, prefira o `.deb` — Python puro não tem esse problema.

---

## Publicar uma versão

1. Suba `VERSAO` em `ponte_menuxy/__init__.py`. Ele é a fonte única: o `.deb`,
   o `--versao` e o `/status` leem de lá.
2. Anote a mudança em `CHANGELOG.md`.
3. Rode o verificador: `python3 testes/verificar_ponte.py`.
4. Espelhe o número no arquivo `VERSION` (o `.deb` lê dele).
5. Gere os pacotes dos três destinos.
6. **Confira que o `.exe` saiu assinado** — o `gerar_exe.bat` diz
   `Assinado digitalmente: sim` ao final. Saindo `nao`, o cliente vai ver o
   aviso do SmartScreen.
7. Confira cada um numa máquina limpa, com `--diagnostico`. No Windows, olhe
   também *Propriedades → Detalhes*: nome, versão e empresa têm de aparecer.
8. Marque a versão no git: `git tag -a v3.0.1 -m "..."`.

## Reprodutibilidade

O `.deb` é determinístico exceto pela data no manual e no `copyright`. O `.exe`
não é — o PyInstaller embute caminhos e carimbos da máquina de build. Se um dia
isso importar, o caminho é construir dentro de um container fixo.
