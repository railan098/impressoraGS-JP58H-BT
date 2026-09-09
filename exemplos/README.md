# Exemplos — para o Menuxy e para os próximos projetos

Código pronto para copiar. Nenhum depende do resto do projeto: são arquivos
soltos que você leva para onde precisar.

| Arquivo | Para quê |
|---|---|
| [`js/ponte-cliente.js`](js/ponte-cliente.js) | **Cliente JavaScript.** Sem dependência, funciona em qualquer projeto web. É por onde começar. |
| [`php/PonteImpressao.php`](php/PonteImpressao.php) | **Monta o texto do cupom no servidor.** PHP 7.4+, sem extensão nenhuma. |
| [`python/cliente.py`](python/cliente.py) | **Cliente Python.** Para o que não é web: PDV de mesa, script de fechamento, robô de WhatsApp. |
| [`web/exemplo.html`](web/exemplo.html) | **Página de diagnóstico.** Prova que a ponte imprime, sem envolver o seu sistema. |
| [`MIGRACAO-MENUXY.md`](MIGRACAO-MENUXY.md) | **Migração do Menuxy** da ponte v2 para a v3, com os `diff` prontos. |

---

## Como um projeto novo se liga à ponte

Três passos, e o terceiro é o único que muda de projeto para projeto.

### 1. Copie o cliente

```html
<script src="/assets/js/ponte-cliente.js"></script>
```

### 2. Autorize o seu endereço, no balcão

```bash
menuxy-ponte --origens https://seuprojeto.com.br
```

Sem isso a ponte responde **403**. É a trava que impede qualquer site aberto no
navegador do operador de gastar a bobina.

### 3. Monte o cupom e mande

```js
const ponte = new PonteImpressao({ colunas: 32 });   // 32 = 58 mm, 48 = 80 mm

if (!await ponte.online()) {
    alert('A ponte de impressão não está aberta nesta máquina.');
    return;
}

const L = PonteImpressao;
const cupom = [
    L.centro('MINHA LOJA', 32),
    L.risco(32),
    L.linha('Coca-Cola 2L', '25,00', 32),
    '  2 x 12,50',
    L.risco(32),
    L.linha('TOTAL', 'R$ 84,90', 32),
    '',
    L.centro('Obrigado!', 32),
    ''
].join('\n');

const r = await ponte.imprimir(cupom, { cortar: true });
if (!r.ok) alert(r.erro);     // `erro` já vem em português, pronto para mostrar
```

---

## Onde montar o cupom: servidor ou navegador?

**No servidor**, quando os valores importam. O preço, o desconto e o total têm
que sair do mesmo lugar que gravou a venda; cupom recalculado no navegador é
cupom que um dia vai divergir do banco. É para isso que serve o
`PonteImpressao.php`: ele monta o texto, e o navegador só entrega.

```php
$cupom = new PonteImpressao(32);
$cupom->centro('MINHA LOJA')
      ->risco()
      ->item('Coca-Cola 2L', 2, 12.50)
      ->risco()
      ->esquerdaDireita('TOTAL', 'R$ ' . number_format($total, 2, ',', '.'));

echo json_encode(['texto' => $cupom->texto()]);
```

E no navegador, mandando `colunas: 0` para dizer "já está formatado, não mexa":

```js
await ponte.imprimir(resposta.texto, { colunas: 0 });
```

**No navegador**, para o que é só apresentação — um cupom de teste, uma
segunda via sem valor fiscal.

---

## Quatro coisas que economizam meio dia

**1. A ponte roda na máquina do balcão, não no seu servidor.** Por isso o
endereço é sempre `127.0.0.1` — o do navegador de quem está imprimindo. Um
servidor não alcança a USB de um computador a 500 km dele.

**2. `HTTP 200` não prova que imprimiu.** Confira `ok === true` no corpo: a
ponte só o marca depois que o spooler, a USB ou a rede aceitaram os bytes.

**3. Mande o texto sem acento.** A ponte converte para a tabela da impressora,
mas cada modelo tem a sua, e o cliente nota na hora quando "Ação" sai como
"A??o". `PonteImpressao.semAcento()` e o `limpar()` do PHP resolvem.

**4. Falha de impressão não pode derrubar a tela de venda.** O pedido já foi
feito; o cupom é consequência, não pré-requisito. Por isso nenhum método do
cliente lança exceção — todos devolvem `{ok, erro}`.

---

## Testar sem gastar papel

Mire uma impressora que não existe: a ponte recusa com 404 e a lista do que
existe de verdade.

```js
await ponte.imprimir('teste', { impressora: 'sistema:__fantasma__' });
// { ok: false, erro: "a impressora ... não existe nesta máquina. Disponíveis: ..." }
```

É o que o [verificador](../testes/verificar_ponte.py) faz nas 98 checagens dele.
