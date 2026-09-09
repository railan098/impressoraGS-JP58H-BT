# Migração do Menuxy para a ponte v3

Guia para levar o Menuxy (`menuxy.alvesprotect.app.br`) da ponte v2 para esta.

**Resumo:** o contrato HTTP não mudou. Se a v2 já funciona no seu balcão, a v3
funciona sem nenhuma alteração no Menuxy — a migração é trocar o programa da
máquina. Tudo abaixo da seção 2 é ganho opcional.

---

## 1. O que muda na máquina do balcão

| | ponte v2 | ponte v3 |
|---|---|---|
| Instalação | copiar `ponte.py` e rodar à mão | `.deb` no Linux, `.exe` no Windows |
| Caminhos até o papel | `sistema:`, `usb:` | mais `usbprint:`, `rede:`, `serial:` |
| Início com o computador | script à parte | caixa de seleção na janela |
| Configuração | editar JSON | janela com quatro abas |
| Atalho | nenhum | área de trabalho e menu |

### Migrar

```bash
# 1. pare a v2
pkill -f ponte.py

# 2. instale a v3
sudo apt install ./dist/menuxy-ponte_3.0.0_all.deb

# 3. confirme que ela vê a mesma impressora de antes
menuxy-ponte --listar
```

**A configuração da v2 é aproveitada.** As duas leem o mesmo
`~/.config/menuxy-ponte/ponte_config.json` (`%APPDATA%\MenuxyPonte\` no
Windows), e os campos novos entram com o padrão. A impressora escolhida, a
porta e a lista de origens continuam valendo — não há o que redigitar.

No Windows, se a v2 estava registrada na inicialização, remova a entrada antiga
antes de ligar a nova, ou as duas vão brigar pela porta 9100:

```
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v PonteImpressao /f
```

---

## 2. O que o Menuxy já faz certo — e não precisa mexer

O agente em `assets/js/impressao-agente.js` foi escrito contra o contrato v2, e
a v3 o mantém inteiro:

| O que o agente faz | Estado na v3 |
|---|---|
| `GET /impressoras`, caindo para `/status` | continua |
| `impressoras` como lista de texto | continua, para não quebrar balcão desatualizado |
| `POST /imprimir {texto, cortar, impressora}` | continua |
| Só confia em `d.ok === true`, não no HTTP 2xx | continua sendo o certo |
| `impressora` vazia = a escolhida na ponte | continua |
| `sistema:Termica58` com dois-pontos | continua |

O default de `ponte_url` em `includes/impressao.php` (`http://127.0.0.1:9100`)
segue correto.

---

## 3. Os ganhos opcionais

### 3.1 — `colunas` no pedido de impressão

A v3 aceita `colunas` no corpo do `POST /imprimir` e requebra o texto naquela
largura. Serve para o balcão que trocou a bobina de 58 mm por 80 mm sem avisar
ninguém: o servidor manda a largura junto e o cupom sai certo.

Em `assets/js/impressao-agente.js`, na função `imprimirNaPonte`:

```diff
 function imprimirNaPonte(base, texto, cortar, impressora) {
     var corta = new AbortController();
     var relogio = setTimeout(function () { corta.abort(); }, 8000);

     return fetch(String(base || CFG.ponte || '').replace(/\/+$/, '') + '/imprimir', {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({
             texto: texto,
             cortar: !!cortar,
-            impressora: impressora || undefined
+            impressora: impressora || undefined,
+            // A ponte v3 requebra o texto nesta largura. Mande 0 para dizer
+            // "já formatei, não mexa" — que é o caso quando o cupom veio
+            // pronto de includes/impressao_texto.php.
+            colunas: 0
         }),
         signal: corta.signal
     })
```

> Mandar `colunas: 0` preserva exatamente o comportamento de hoje. Só troque
> por `32` ou `48` se você **não** estiver formatando no servidor.

### 3.2 — Gravar o tipo de caminho da impressora

O `/status` da v3 devolve, em `detalhes[]`, os campos `tipo` (`sistema`, `usb`,
`rede`, `serial`, `usbprint`), `papel` e `detalhe`. Guardando o `tipo` no
cadastro da estação, a tela de gerenciamento passa a distinguir "a térmica do
balcão" de "a laser do escritório" sem o dono precisar adivinhar pelo nome.

Em `normalizarLista`, dentro de `assets/js/impressao-agente.js`:

```diff
         return bruto.map(function (item) {
             if (typeof item === 'string') return { nome: item, rotulo: '', papel: '80mm' };
             return {
                 nome:   item.nome || item.name || '',
                 rotulo: item.rotulo || item.descricao || item.description || '',
-                papel:  item.papel || item.paper || '80mm'
+                papel:  item.papel || item.paper || '80mm',
+                // Novidade da ponte v3. Ausente nas anteriores — por isso o ''.
+                tipo:   item.tipo || ''
             };
         }).filter(function (p) { return p.nome; });
```

O campo chega em `ajax/impressao_api.php` na ação `estacao_anunciar`, junto do
resto do JSON de `impressoras`. Se a coluna ainda não existe no banco, ele é
simplesmente ignorado — nada quebra por adicioná-lo antes.

### 3.3 — Gaveta de dinheiro

Rota nova: `POST /gaveta` com `{impressora}` aciona a gaveta sem imprimir. Hoje
o Menuxy não tem esse botão; quando tiver, é uma linha:

```js
fetch(CFG.ponte + '/gaveta', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ impressora: impressoraDaEstacao })
});
```

### 3.4 — `GET /saude`

Responde `{ok, versao}` sem tocar na impressora. É a rota para um monitor
perguntar "o processo está de pé?" sem acordar o spooler a cada minuto.

---

## 4. Fechar a lista de origens

Este é o passo que não pode ficar para depois. Com a lista aberta, qualquer site
que o operador visitar consegue gastar a bobina do balcão.

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br
```

Vários endereços, quando o balcão também usa uma instalação local:

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br http://192.168.18.31:8080
```

A comparação é exata: `https://` e `http://` são origens diferentes, e a porta
faz parte. `https://menuxy.alvesprotect.app.br` **não** autoriza
`https://menuxy.alvesprotect.app.br:8443`.

---

## 5. Roteiro de conferência

Depois de migrar um balcão, em ordem:

```bash
menuxy-ponte --diagnostico     # 1. a ponte se enxerga?
menuxy-ponte --listar          # 2. a impressora aparece?
menuxy-ponte --testar          # 3. o papel sai? (gasta UM cupom)
```

E no Menuxy, no navegador do balcão:

4. Abra qualquer tela logada e confira no painel de estações que a máquina
   aparece com a lista de impressoras.
5. Emita um pedido de teste e veja o cupom sair.
6. Confira o registro: `~/.config/menuxy-ponte/ponte.log`.

Se o passo 3 imprime e o passo 5 não, o problema não é a ponte — é a lista de
origens ou o roteamento da estação no cadastro do Menuxy.
