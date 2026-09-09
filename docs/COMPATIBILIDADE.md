# Compatibilidade

## A pergunta que importa

**"A minha impressora funciona?"** Quase certamente sim — e por um motivo
estrutural: a ponte cobre cinco caminhos diferentes até o papel, e toda
impressora chega ao computador por pelo menos um deles.

Descubra em dez segundos:

```bash
menuxy-ponte --listar
```

O que aparecer nessa lista, imprime.

---

## Os cinco caminhos

| Prefixo | Cobre | Precisa de |
|---|---|---|
| `sistema:` | **qualquer impressora instalada** no sistema — térmica, laser, jato de tinta, USB, de rede, compartilhada | nada (só o Python) |
| `usb:` | térmica genérica **sem driver**, plugada na USB | `pyusb` + libusb |
| `usbprint:` | USB no Windows, **inclusive ARM**, usando o driver que o próprio Windows anexou | nada (só Windows) |
| `rede:` | impressora com IP, protocolo RAW 9100 | nada |
| `serial:` | impressora serial ou conversor USB-serial | `pyserial` |

O caminho `sistema:` sozinho já cobre a grande maioria dos balcões, e é o
preferido: usa a infraestrutura que já existe, respeita permissão e fila.

---

## Sistemas operacionais

| Sistema | Situação | Observação |
|---|---|---|
| Windows 10 / 11 (x64) | testado | caminho principal |
| Windows 11 **ARM** (Snapdragon) | testado | use `usbprint:` — o `usb:` esbarra no libusb, veja abaixo |
| Windows 7 / 8.1 | deve funcionar | limitado ao Python 3.8, que é o último que roda lá |
| Ubuntu / Debian / Mint / Pop!_OS | testado | `.deb` pronto |
| Fedora / Arch / openSUSE | deve funcionar | use `instalar_linux.sh` |
| Raspberry Pi OS | deve funcionar | o `.deb` é `all` — serve arm64 e armhf |
| macOS 11+ | deve funcionar | mesmo caminho do Linux (CUPS) |

**Python:** 3.8 ou mais novo. Testado até o 3.14.

**Arquiteturas:** x86-64, ARM64 e ARMv7. Tudo é Python puro; não há binário
compilado no pacote.

---

## Windows ARM — o caso que merece explicação

No Windows sobre ARM (Snapdragon), o caminho `usb:` (libusb) esbarra num
problema real: o libusb *enumera* qualquer dispositivo, mas só consegue *abrir*
aquele cujo driver anexado seja WinUSB ou libusbK. Trocar o driver exige o
Zadig, que pede administrador e faz a impressora sumir de "Impressoras e
Scanners" — e das três opções do Zadig, só o WinUSB tem binário ARM64.

**A ponte resolve isso com o caminho `usbprint:`.** O `usbprint.sys` — o driver
que o Windows já anexa sozinho, e que é justamente o que bloqueia o libusb —
expõe uma *device interface* que pode ser aberta com `CreateFileW` e receber
bytes crus com `WriteFile`. O driver que atrapalhava vira o transporte.

Resultado: **em Windows ARM, não instale o Zadig.** Rode `menuxy-ponte
--listar`, escolha o identificador que começa com `usbprint:` e pronto — sem
administrador, sem trocar driver, sem emulação.

---

## Impressoras conhecidas

### Térmicas 58 mm

| Modelo | Caminho testado | Observação |
|---|---|---|
| GS-JP58H / SMX-JP58H / POS-58 | `usb:0416:5011`, `usbprint:` | Winbond/Nuvoton YICHIP3121. É a impressora sobre a qual este projeto foi construído. |
| Clones genéricos 58 mm | `usb:` | quase todos declaram classe 7 na *interface*, não no dispositivo — a ponte filtra nos dois níveis |
| Epson TM-T20 e família | `sistema:` | tem driver oficial; instale e use o `sistema:` |
| Elgin i9 / i7 | `sistema:` | idem |
| Bematech MP-4200 | `sistema:` | idem |
| Daruma DR800 | `sistema:` | idem |

### Térmicas 80 mm

Todas funcionam pelo `sistema:`. Ajuste `colunas` para **48**.

### Laser e jato de tinta

Funcionam pelo `sistema:`, mas o resultado é uma página inteira com o texto do
cupom no alto — ESC/POS não é linguagem de impressora de página. Serve para
teste; não serve para cupom.

---

## Uma impressora que não aparece na lista

Em ordem de probabilidade:

1. **Está desligada.** O cabo USB alimenta o chip, mas a impressora precisa
   estar **ligada no botão** para enumerar. É a causa nº 1.
2. **É USB sem driver e falta o `pyusb`.** `pip install pyusb`, depois
   `menuxy-ponte --listar` de novo.
3. **É USB no Linux e falta permissão.** Instale a regra udev
   (`ferramenta_cli/99-impressora-termica.rules`) e entre no grupo `lp`. O
   `.deb` faz a primeira parte sozinho.
4. **É de rede.** A ponte não varre a rede — cadastre o IP.
   Veja [CONFIGURACAO.md](CONFIGURACAO.md#impressora-de-rede).
5. **Está instalada mas o CUPS não a mostra.** Confira com `lpstat -a`; se ela
   não aparece ali, o problema é anterior à ponte.

O diagnóstico responde a maioria disso de uma vez:

```bash
menuxy-ponte --diagnostico
```

---

## Navegadores

| Navegador | Situação |
|---|---|
| Chrome / Edge / Brave (89+) | testado — o `Access-Control-Allow-Private-Network` que a ponte envia é exigência deles |
| Firefox | testado |
| Safari | deve funcionar |

Página em **HTTPS** chamando `http://127.0.0.1` funciona: o navegador trata o
loopback como origem segura.
