<?php
/**
 * PonteImpressao.php — monta o texto do cupom no servidor.
 *
 * Copie para o seu projeto. Não tem dependência: PHP 7.4 ou mais novo, só isso.
 *
 * ONDE ESTA CLASSE ENTRA
 * ======================
 * A ponte roda na máquina do balcão; o seu servidor não alcança a impressora
 * dela. Então a divisão de trabalho é esta:
 *
 *     servidor (esta classe)   monta o TEXTO do cupom, já quebrado nas colunas
 *                              da bobina e sem acento
 *              |
 *              v  (o texto viaja no JSON da sua API)
 *     navegador (ponte-cliente.js)   entrega à ponte
 *              |
 *              v
 *     ponte (127.0.0.1:9100)   vira ESC/POS e escreve na impressora
 *
 * Montar no servidor e não no navegador é de propósito: o preço, o desconto e
 * o total precisam sair do mesmo lugar que gravou a venda. Cupom recalculado
 * no navegador é cupom que um dia vai divergir do banco.
 *
 * EXEMPLO
 * =======
 *     $cupom = new PonteImpressao(32);          // 32 = 58 mm; 48 = 80 mm
 *     $cupom->centro('MINHA LOJA')
 *           ->centro('Rua Exemplo, 100')
 *           ->risco()
 *           ->esquerdaDireita('Pedido', '#1234')
 *           ->esquerdaDireita('Data', date('d/m/Y H:i'))
 *           ->risco()
 *           ->item('Coca-Cola 2L', 2, 12.50)
 *           ->item('Pizza Calabresa Grande', 1, 59.90)
 *           ->risco()
 *           ->esquerdaDireita('TOTAL', 'R$ ' . number_format(84.90, 2, ',', '.'))
 *           ->linha('')
 *           ->centro('Obrigado pela preferencia!');
 *
 *     echo json_encode(['texto' => $cupom->texto()]);
 */
class PonteImpressao
{
    /** @var int Largura da bobina em colunas: 32 para 58 mm, 48 para 80 mm. */
    private int $colunas;

    /** @var string[] */
    private array $linhas = [];

    public function __construct(int $colunas = 32)
    {
        // Fora dessa faixa não existe bobina de cupom; um valor absurdo aqui
        // vira um cupom ilegível que só se descobre no papel.
        $this->colunas = max(24, min(96, $colunas));
    }

    /*
     * Sobre strlen() e substr() em vez de mb_strlen()/mb_substr(): todo texto
     * passa por limpar() antes de ser medido, e de lá sai ASCII puro — um byte
     * por caractere, que é exatamente o que a impressora conta como coluna.
     * A mbstring nem sempre está instalada em hospedagem compartilhada, e
     * depender dela quebraria o cupom justamente no cliente mais simples.
     */

    /** Uma linha crua. Texto maior que a bobina é quebrado, não cortado. */
    public function linha(string $texto = ''): self
    {
        foreach (explode("\n", $this->quebrar($texto)) as $parte) {
            $this->linhas[] = $parte;
        }
        return $this;
    }

    /** Centraliza na largura da bobina. */
    public function centro(string $texto): self
    {
        $texto = $this->limpar($texto);
        foreach (explode("\n", $this->quebrar($texto)) as $parte) {
            $sobra = max(0, intdiv($this->colunas - strlen($parte), 2));
            $this->linhas[] = str_repeat(' ', $sobra) . $parte;
        }
        return $this;
    }

    /**
     * Rótulo à esquerda, valor à direita, preenchimento no meio.
     *
     * O valor é sagrado: quem é truncado quando não cabe é o rótulo. Um total
     * cortado pela metade no cupom é um problema com o cliente na hora.
     */
    public function esquerdaDireita(string $esquerda, string $direita, string $preenchimento = ' '): self
    {
        $esquerda = $this->limpar($esquerda);
        $direita  = $this->limpar($direita);

        $espaco = $this->colunas - strlen($direita) - 1;
        if ($espaco < 1) {
            $this->linhas[] = substr($esquerda . ' ' . $direita, 0, $this->colunas);
            return $this;
        }
        if (strlen($esquerda) > $espaco) {
            $esquerda = substr($esquerda, 0, $espaco);
        }
        $meio = $this->colunas - strlen($esquerda) - strlen($direita);
        $this->linhas[] = $esquerda . str_repeat($preenchimento, max(0, $meio)) . $direita;
        return $this;
    }

    /**
     * Um item da venda, em duas linhas quando o nome é longo.
     *
     * Duas linhas e não uma truncada porque "Pizza Calabresa Gran" no cupom
     * gera dúvida no cliente; o nome inteiro em cima e a conta embaixo, não.
     */
    public function item(string $descricao, float $quantidade, float $unitario): self
    {
        $descricao = $this->limpar($descricao);
        $total = $this->dinheiro($quantidade * $unitario);
        $conta = $this->numero($quantidade) . ' x ' . $this->dinheiro($unitario);

        if (strlen($descricao) + strlen($total) + 1 <= $this->colunas
            && strlen($conta) + strlen($total) + 1 <= $this->colunas
            && strlen($descricao) <= $this->colunas - strlen($total) - 1) {
            // Cabe no formato compacto: nome + total numa linha, conta na outra.
            $this->esquerdaDireita($descricao, $total);
            $this->linhas[] = '  ' . $conta;
            return $this;
        }

        $this->linha($descricao);
        $this->esquerdaDireita('  ' . $conta, $total);
        return $this;
    }

    /** Uma régua de separação. */
    public function risco(string $caractere = '-'): self
    {
        $this->linhas[] = str_repeat($caractere, $this->colunas);
        return $this;
    }

    /** Linhas em branco. */
    public function pular(int $quantas = 1): self
    {
        for ($i = 0; $i < $quantas; $i++) {
            $this->linhas[] = '';
        }
        return $this;
    }

    /** O texto final, pronto para o campo `texto` do POST /imprimir. */
    public function texto(): string
    {
        return implode("\n", $this->linhas) . "\n";
    }

    public function __toString(): string
    {
        return $this->texto();
    }

    // ----------------------------------------------------------- ajudantes

    /**
     * Tira o acento e o que a impressora não imprime.
     *
     * A ponte já converte acentos para a tabela da impressora, mas cada modelo
     * tem a sua — e o cliente nota na hora quando "Ação" sai como "A??o".
     * Mandar sem acento elimina a variável de vez.
     *
     * Caracteres de controle também saem: eles seriam interpretados como
     * COMANDO pela impressora, e um 0x1D no meio do nome de um produto pode
     * disparar um corte no lugar errado.
     */
    private function limpar(string $texto): string
    {
        $sem = @iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $texto);
        if ($sem === false) {
            $sem = $texto;
        }
        $sem = str_replace(['"', "'", '`', '^', '~'], ['', '', '', '', ''], $sem);
        return preg_replace('/[\x00-\x1F\x7F]/', '', $sem) ?? '';
    }

    /** Quebra na largura da bobina sem partir palavra. */
    private function quebrar(string $texto): string
    {
        $texto = $this->limpar($texto);
        return wordwrap($texto, $this->colunas, "\n", true);
    }

    private function dinheiro(float $valor): string
    {
        return number_format($valor, 2, ',', '.');
    }

    /** Quantidade inteira sai sem casas: "2 x", não "2,00 x". */
    private function numero(float $valor): string
    {
        return (floor($valor) == $valor)
            ? (string) (int) $valor
            : number_format($valor, 3, ',', '');
    }
}
