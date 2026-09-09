# Contrato HTTP

A ponte escuta em **`http://127.0.0.1:9100`** — e só em `127.0.0.1`. Nenhuma
máquina da rede alcança essa porta; não por firewall, mas porque o socket não
existe fora do loopback.

Todas as respostas são JSON UTF-8.

```
GET  /status        situação, impressoras, versão
GET  /impressoras   só as impressoras
GET  /saude         { ok, versao } — não toca na impressora
POST /imprimir      { texto, cortar?, impressora?, colunas?, codepage?, gaveta? }
POST /raw           { base64, impressora? }
POST /gaveta        { impressora? }
```

---

## `GET /status`

```json
{
  "ok": true,
  "versao": "3.0.0",
  "sistema": "linux",
  "backends": ["sistema", "usb", "rede"],
  "impressoras": ["sistema:Termica58", "usb:0416:5011"],
  "detalhes": [
    {
      "id": "sistema:Termica58",
      "nome": "sistema:Termica58",
      "rotulo": "Termica58",
      "tipo": "sistema",
      "papel": "80mm",
      "detalhe": "fila do CUPS"
    }
  ],
  "padrao": "sistema:Termica58",
  "escolhida": "",
  "colunas": 32,
  "origens_abertas": false
}
```

`impressoras` (lista de texto) e `detalhes` (lista de objetos) carregam a mesma
informação. Os dois existem para que atualizar o servidor não obrigue a
atualizar todos os balcões no mesmo dia: cliente antigo lê `impressoras`,
cliente novo lê `detalhes`.

Dentro de `detalhes`, `nome` repete `id` pelo mesmo motivo.

---

## `POST /imprimir`

```json
{
  "texto": "MINHA LOJA\n--------\nTOTAL   R$ 10,00\n",
  "cortar": true,
  "impressora": "sistema:Termica58",
  "colunas": 0,
  "codepage": "cp850",
  "gaveta": false
}
```

| Campo | Obrigatório | Padrão | Observação |
|---|---|---|---|
| `texto` | sim | — | Texto puro. `\n` separa linhas. |
| `cortar` | não | do config | Corta ao fim. |
| `impressora` | não | a configurada | Ver *Identificadores*. |
| `colunas` | não | do config | **`0` = "já formatei, não mexa"**. |
| `codepage` | não | do config | `cp850`, `cp860`, `cp437`, `cp1252`, `cp858`. |
| `gaveta` | não | do config | Pulso na gaveta após o cupom. |

**Sucesso** — HTTP 200:

```json
{ "ok": true, "impressora": "Termica58", "bytes": 412 }
```

**Falha:**

| HTTP | Quando | Corpo |
|---|---|---|
| 400 | corpo ausente, JSON inválido, sem texto, base64 inválido | `{"ok":false,"erro":"..."}` |
| 413 | corpo maior que 512 KB | `{"ok":false,"erro":"corpo de N bytes é maior..."}` |
| 403 | a origem não está na lista permitida | `{"ok":false,"erro":"origem não autorizada"}` |
| 404 | a impressora não existe nesta máquina | `{"ok":false,"erro":"... Disponíveis: ..."}` |
| 429 | passou do teto por minuto | `{"ok":false,"erro":"muitos trabalhos por minuto"}` |
| 500 | a impressora existe mas recusou | `{"ok":false,"erro":"sem papel..."}` |

> **HTTP 200 sozinho não prova que imprimiu.** Confira `ok === true` no corpo:
> a ponte só o marca depois que o spooler, a USB ou a rede aceitaram os bytes.
> É a diferença entre "a requisição chegou" e "o papel saiu".

---

## `POST /raw`

ESC/POS já montado por você, em base64. Existe para o que a ponte não monta
sozinha: logotipo em bitmap, QR code, comandos específicos do seu modelo.

```json
{ "base64": "G0BUZXN0ZQoKCgodVgA=", "impressora": "sistema:Termica58" }
```

Os bytes vão **como estão**, sem `ESC @` na frente e sem corte no fim — o
controle é todo seu.

## `POST /gaveta`

Aciona a gaveta de dinheiro sem imprimir. `{ "impressora": "..." }`, tudo
opcional.

---

## Identificadores de impressora

O campo `impressora` aceita três formas:

1. **Id completo** — `sistema:Termica58`, `usb:0416:5011`,
   `rede:192.168.0.50:9100`. É o que o `/status` devolve e o que você deve
   guardar.
2. **Nome nu** — `Termica58`, resolvido contra a lista real de impressoras do
   sistema. Serve para o que veio digitado à mão.
3. **Vazio ou ausente** — usa a que o operador escolheu na ponte; não havendo,
   a padrão do sistema operacional.

O prefixo não é enfeite: uma `Termica58` instalada e uma `Termica58` na USB são
coisas diferentes, e sem ele o trabalho poderia sair pelo caminho errado.

| Prefixo | Caminho |
|---|---|
| `sistema:` | spooler do Windows / fila do CUPS |
| `usb:` | libusb no endpoint bulk-out (sem driver) |
| `usbprint:` | driver do Windows (funciona em ARM sem Zadig) |
| `rede:` | TCP RAW 9100 |
| `serial:` | porta serial ou conversor USB-serial |

Um identificador que não existe nesta máquina devolve **404 com a lista do que
existe** — é o que transforma erro de digitação em problema resolvido em dois
minutos.

---

## CORS e o cabeçalho que o Chrome exige

Toda resposta traz:

```
Access-Control-Allow-Origin: <a origem, ou * se a lista estiver aberta>
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Private-Network: true
```

O último é obrigatório. Quando uma página pública chama `127.0.0.1`, o Chrome
aplica o *Private Network Access* e **barra a chamada sem esse cabeçalho** —
mesmo com o CORS comum liberado, e **sem erro visível no console**. Se você
escrever a sua própria ponte um dia, não esqueça dele: é o tipo de falha que
custa meio dia.

Página em HTTPS chamando `http://127.0.0.1` funciona: o navegador trata o
loopback como origem segura.

---

## Exemplo mínimo

```js
const r = await fetch('http://127.0.0.1:9100/imprimir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto: 'Ola mundo\n', cortar: true })
}).then(r => r.json());

if (!r.ok) console.error(r.erro);
```

Cliente completo, com prazo, mensagens de erro traduzidas e ajudantes de
formatação: [`exemplos/js/ponte-cliente.js`](../exemplos/js/ponte-cliente.js).
