/**
 * ponte-cliente.js — cliente da Ponte de Impressão, para qualquer projeto web.
 *
 * Copie este arquivo para o seu projeto. Ele não tem dependência nenhuma, não
 * usa framework e funciona em qualquer navegador com `fetch` (todos desde 2017).
 *
 * USO MÍNIMO
 * ==========
 *     const ponte = new PonteImpressao();
 *     await ponte.imprimir("MEU CUPOM\n\nItem 1 ......... 10,00\n");
 *
 * USO COMPLETO
 * ============
 *     const ponte = new PonteImpressao({
 *         base: 'http://127.0.0.1:9100',   // padrão
 *         impressora: 'sistema:Termica58', // vazio = a escolhida na ponte
 *         colunas: 32                      // 32 = 58 mm, 48 = 80 mm
 *     });
 *
 *     if (await ponte.online()) {
 *         const lista = await ponte.impressoras();
 *         await ponte.imprimir(texto, { cortar: true });
 *     }
 *
 * TRÊS COISAS QUE VOCÊ PRECISA SABER ANTES DE USAR
 * ================================================
 *
 * 1. **A ponte roda na máquina do balcão, não no seu servidor.** Um servidor
 *    não alcança a USB de um computador a 500 km dele. Por isso o endereço é
 *    sempre `127.0.0.1` — o do navegador de quem está imprimindo.
 *
 * 2. **A ponte precisa autorizar o seu endereço.** Ela recusa com HTTP 403
 *    quem não está na lista. No balcão, uma vez:
 *
 *        menuxy-ponte --origens https://seusistema.com.br
 *
 * 3. **Página em HTTPS chamando 127.0.0.1 em HTTP funciona** — o navegador
 *    trata o loopback como origem segura. Mas o Chrome exige o cabeçalho
 *    `Access-Control-Allow-Private-Network` no preflight, e a ponte já o
 *    envia. Se você escrever a sua própria ponte, não esqueça dele: sem ele a
 *    chamada é barrada SEM erro visível no console.
 */

(function (raiz) {
    'use strict';

    var PADRAO = {
        base: 'http://127.0.0.1:9100',
        impressora: '',      // vazio = a que o operador escolheu na ponte
        colunas: 32,         // 32 colunas = 58 mm; 48 = 80 mm
        cortar: true,
        tempoLimite: 8000,   // ms para uma impressão
        tempoStatus: 2500    // ms para uma consulta de status
    };

    function PonteImpressao(opcoes) {
        this.cfg = Object.assign({}, PADRAO, opcoes || {});
        this.cfg.base = String(this.cfg.base).replace(/\/+$/, '');
        this._status = null;      // memória da última consulta
    }

    /**
     * fetch com prazo. Sem isso, uma ponte travada deixa o caixa esperando
     * para sempre, com a tela parada e nenhuma explicação.
     */
    PonteImpressao.prototype._buscar = function (caminho, opcoes, prazo) {
        var corta = new AbortController();
        var relogio = setTimeout(function () { corta.abort(); }, prazo);
        return fetch(this.cfg.base + caminho,
                     Object.assign({ signal: corta.signal }, opcoes || {}))
            .then(function (r) {
                clearTimeout(relogio);
                return r.json()
                    .then(function (d) { return { http: r.status, ok: r.ok, dados: d }; })
                    .catch(function () { return { http: r.status, ok: r.ok, dados: {} }; });
            })
            .catch(function (erro) {
                clearTimeout(relogio);
                return { http: 0, ok: false, dados: {}, erro: erro };
            });
    };

    /** A ponte está no ar? Devolve o objeto de status, ou null. */
    PonteImpressao.prototype.status = function () {
        var eu = this;
        return this._buscar('/status', {}, this.cfg.tempoStatus).then(function (r) {
            eu._status = (r.ok && r.dados && r.dados.ok) ? r.dados : null;
            return eu._status;
        });
    };

    PonteImpressao.prototype.online = function () {
        return this.status().then(function (s) { return s !== null; });
    };

    /** Lista as impressoras da máquina: [{nome, rotulo, tipo, papel}]. */
    PonteImpressao.prototype.impressoras = function () {
        return this._buscar('/impressoras', {}, this.cfg.tempoStatus).then(function (r) {
            return (r.dados && r.dados.impressoras) || [];
        });
    };

    /**
     * Imprime texto.
     *
     * Devolve `{ ok, erro, impressora }` — nunca lança. Uma falha de impressão
     * não pode derrubar a tela de venda: o pedido já foi feito, e o cupom é
     * consequência, não pré-requisito.
     */
    PonteImpressao.prototype.imprimir = function (texto, opcoes) {
        opcoes = opcoes || {};
        var corpo = {
            texto: texto,
            cortar: opcoes.cortar !== undefined ? !!opcoes.cortar : this.cfg.cortar,
            impressora: opcoes.impressora || this.cfg.impressora || undefined,
            colunas: opcoes.colunas !== undefined ? opcoes.colunas : this.cfg.colunas
        };
        return this._enviar('/imprimir', corpo, opcoes.tempoLimite);
    };

    /**
     * Imprime ESC/POS já montado (base64).
     *
     * É a saída para o que a ponte não monta sozinha: logotipo em bitmap,
     * QR code, comandos específicos do seu modelo.
     */
    PonteImpressao.prototype.raw = function (bytes, opcoes) {
        opcoes = opcoes || {};
        var base64 = (bytes instanceof Uint8Array) ? PonteImpressao.paraBase64(bytes) : String(bytes);
        return this._enviar('/raw', {
            base64: base64,
            impressora: opcoes.impressora || this.cfg.impressora || undefined
        }, opcoes.tempoLimite);
    };

    /** Abre a gaveta de dinheiro, sem imprimir nada. */
    PonteImpressao.prototype.gaveta = function (opcoes) {
        opcoes = opcoes || {};
        return this._enviar('/gaveta', {
            impressora: opcoes.impressora || this.cfg.impressora || undefined
        }, opcoes.tempoLimite);
    };

    PonteImpressao.prototype._enviar = function (rota, corpo, prazo) {
        return this._buscar(rota, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(corpo)
        }, prazo || this.cfg.tempoLimite).then(function (r) {
            // HTTP 2xx sozinho não prova que imprimiu. A ponte só confirma no
            // corpo depois que o spooler ou a USB aceitaram os bytes.
            if (r.ok && r.dados && r.dados.ok === true) {
                return { ok: true, impressora: r.dados.impressora || '', bytes: r.dados.bytes || 0 };
            }
            return { ok: false, erro: PonteImpressao.explicar(r), http: r.http };
        });
    };

    /** Traduz a falha para uma frase que o operador do balcão entende. */
    PonteImpressao.explicar = function (r) {
        if (r.http === 0) {
            return 'A ponte de impressão não respondeu. Ela está aberta nesta máquina? ' +
                   'Procure o ícone da ponte na barra de tarefas.';
        }
        if (r.http === 403) {
            return 'A ponte recusou este site. No computador do balcão, rode uma vez:\n' +
                   '  menuxy-ponte --origens ' + raiz.location.origin;
        }
        if (r.http === 404) {
            return (r.dados && r.dados.erro) ||
                   'A impressora escolhida não existe nesta máquina.';
        }
        if (r.http === 429) {
            return 'Muitas impressões seguidas. Aguarde alguns segundos.';
        }
        return (r.dados && r.dados.erro) || ('Falha na impressão (HTTP ' + r.http + ').');
    };

    // ---------------------------------------------------------------- ajudantes

    /** Uint8Array -> base64, sem estourar a pilha em cupom grande. */
    PonteImpressao.paraBase64 = function (bytes) {
        var pedacos = [];
        for (var i = 0; i < bytes.length; i += 8192) {
            pedacos.push(String.fromCharCode.apply(null, bytes.subarray(i, i + 8192)));
        }
        return btoa(pedacos.join(''));
    };

    /**
     * "Produto" à esquerda, "10,00" à direita, pontos no meio.
     *
     * É a linha que todo cupom tem, e a que todo mundo reescreve errado: sem o
     * teto de largura, um nome longo empurra o valor para a linha de baixo.
     */
    PonteImpressao.linha = function (esquerda, direita, colunas, preenchimento) {
        colunas = colunas || 32;
        preenchimento = preenchimento || ' ';
        esquerda = String(esquerda);
        direita = String(direita);
        var espaco = colunas - direita.length - 1;
        if (espaco < 1) return (esquerda + ' ' + direita).slice(0, colunas);
        if (esquerda.length > espaco) esquerda = esquerda.slice(0, espaco);
        var meio = colunas - esquerda.length - direita.length;
        return esquerda + new Array(meio + 1).join(preenchimento) + direita;
    };

    /** Centraliza dentro da largura da bobina. */
    PonteImpressao.centro = function (texto, colunas) {
        colunas = colunas || 32;
        texto = String(texto).slice(0, colunas);
        var sobra = Math.max(0, Math.floor((colunas - texto.length) / 2));
        return new Array(sobra + 1).join(' ') + texto;
    };

    /** Uma régua de separação. */
    PonteImpressao.risco = function (colunas, caractere) {
        return new Array((colunas || 32) + 1).join(caractere || '-');
    };

    /**
     * Tira os acentos.
     *
     * Impressora térmica é a última fronteira onde acento ainda dá problema:
     * cada modelo tem a sua tabela, e o operador nota na hora que "Ação" saiu
     * como "A??o". A ponte já converte, mas quem manda o texto sem acento
     * elimina a variável de vez.
     */
    PonteImpressao.semAcento = function (texto) {
        return String(texto).normalize('NFD').replace(/[̀-ͯ]/g, '');
    };

    /** Publica como global, CommonJS ou AMD — funciona nos três. */
    if (typeof module === 'object' && module.exports) {
        module.exports = PonteImpressao;
    } else if (typeof define === 'function' && define.amd) {
        define([], function () { return PonteImpressao; });
    } else {
        raiz.PonteImpressao = PonteImpressao;
    }
})(typeof window !== 'undefined' ? window : this);
