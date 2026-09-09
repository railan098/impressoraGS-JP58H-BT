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

**Assinatura digital.** O executável não é assinado, e o SmartScreen vai avisar
o cliente na primeira execução ("Windows protegeu o computador" → *Mais
informações* → *Executar assim mesmo*). Para eliminar o aviso é preciso um
certificado de assinatura de código, que é pago e nominal — vale a pena quando
a base de clientes cresce.

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
4. Gere os pacotes dos três destinos.
5. Confira cada um numa máquina limpa, com `--diagnostico`.
6. Marque a versão no git: `git tag -a v3.0.1 -m "..."`.

## Reprodutibilidade

O `.deb` é determinístico exceto pela data no manual e no `copyright`. O `.exe`
não é — o PyInstaller embute caminhos e carimbos da máquina de build. Se um dia
isso importar, o caminho é construir dentro de um container fixo.
