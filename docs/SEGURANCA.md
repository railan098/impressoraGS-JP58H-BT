# Segurança

## O modelo de ameaça, em uma frase

A ponte abre uma porta HTTP na máquina do balcão. **Qualquer aba que o operador
tiver aberta pode tentar falar com ela.** Todo o desenho de segurança parte
disso.

## As travas, e o que cada uma impede

| Medida | O que impede |
|---|---|
| Escuta **só em `127.0.0.1`** | Nenhuma máquina da rede alcança a porta. Não é firewall: o socket não existe fora do loopback. |
| **Lista de origens permitidas** | Sem ela, qualquer site aberto no navegador do operador manda imprimir. |
| **Teto por minuto** (60) | Um site hostil — ou um laço com defeito no próprio sistema — despeja a bobina inteira antes de alguém perceber. |
| **Teto de corpo** (512 KB) | Corpo gigante como negação de serviço. |
| Nome conferido contra a **lista real** | Erro de digitação vira mensagem clara; nome forjado não chega a lugar nenhum. |
| **Nenhum shell** | `subprocess` com lista de argumentos, Win32 por `ctypes`. `Termica; rm -rf /` é só um nome que não existe. |
| **Nenhum acesso a dado** | Sem banco, sem leitura de arquivo, sem rota que devolva informação de venda. |
| Configuração no **perfil do usuário** | Não precisa de administrador, e o programa não escreve na pasta de instalação. |
| Gravação **atômica** | Queda de energia não deixa um JSON pela metade que impeça a ponte de subir. |

## O que ela NÃO protege — sendo direto

**1. Com `origens_permitidas: ["*"]`, qualquer site que o operador visitar
consegue gastar a sua bobina.** Ler, não consegue — não há o que ler. Mas
imprimir, sim. Feche a lista assim que souber o endereço do sistema:

```bash
menuxy-ponte --origens https://menuxy.alvesprotect.app.br
```

O `--diagnostico` e a janela avisam em amarelo enquanto a lista estiver aberta.

**2. A porta é acessível a qualquer programa rodando na mesma máquina.** Isso é
inerente a qualquer ponte local — um programa local pode falar com outro
programa local, e nenhum cabeçalho HTTP muda isso. A mitigação real é o
computador do balcão não ser de uso geral.

**3. A lista de origens depende do cabeçalho `Origin`, que o navegador
preenche.** Um programa fora do navegador pode omiti-lo, e a ponte então
aceita: bloquear ali quebraria `curl`, scripts do próprio balcão e o
diagnóstico, sem impedir nada — quem roda um programa na máquina já alcança a
porta de qualquer jeito.

**4. Não há autenticação.** Um segredo compartilhado precisaria ser distribuído
para cada balcão e apareceria no código da página, que é público por natureza.
A trava real é a que já está: só o loopback, só as origens da lista, e nenhum
dado atrás dela.

## Como a comparação de origem funciona

Exata, depois de normalizar barra final e maiúsculas. Estes **não** são a mesma
origem:

| Autorizado | Recusado | Por quê |
|---|---|---|
| `https://loja.com.br` | `http://loja.com.br` | esquema diferente |
| `https://loja.com.br` | `https://loja.com.br:8443` | porta faz parte |
| `https://loja.com.br` | `https://sub.loja.com.br` | host diferente |
| `https://loja.com.br` | `https://loja.com.br.evil.com` | host diferente |

`https://loja.com.br/` e `https://LOJA.com.br` **são** aceitos — barra final e
caixa não mudam a origem.

## Nomes hostis

Todo identificador de impressora é conferido contra a lista real antes de
qualquer uso. Estes chegam à ponte e não vão a lugar nenhum:

```
Termica; rm -rf /        $(whoami)        `id`
../../etc/passwd         sistema:; shutdown -h now
```

Todos devolvem **404 com a lista de impressoras que existem**. E, mesmo que
passassem, não há shell no caminho: o CUPS é chamado com
`["lp", "-d", nome, "-o", "raw"]` como lista de argumentos, e o Windows pela
API `ctypes`.

O verificador exercita cada um deles:

```bash
python3 testes/verificar_ponte.py
```

## Autorização e privilégio

A ponte **nunca pede administrador**:

* instala em `%LOCALAPPDATA%` ou `~/.local`, não em `Program Files` nem `/usr`
  (o `.deb` é a exceção, e aí quem instala é o `apt`);
* registra o início automático em `HKCU`, não em `HKLM`;
* no Linux usa serviço/autostart **de usuário**, não de sistema.

Isso não é só conveniência. A ponte precisa das permissões de quem está logado:
é esse usuário que tem acesso às filas do CUPS e à sessão gráfica. Um serviço
rodando como `root` não enxergaria nem uma nem outra.

O único passo que pede `sudo` é a regra udev para USB direta — uma vez, na
instalação, e o `.deb` já a traz.

## Relatar um problema

Achou uma falha? `Saobentomaqsbm@gmail.com`. Descreva o que acontece e como
reproduzir; se envolver a rede local ou outra máquina, diga a topologia.
