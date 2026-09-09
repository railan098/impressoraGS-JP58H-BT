# Legado — a ponte v2

Estes arquivos foram a **primeira ponte de impressão** do Menuxy, de setembro de
2026. A v3 (`ponte_menuxy/`) os substituiu, mas nada aqui foi jogado fora: cada
ideia que valia a pena está viva no código novo, e este é o registro de onde
ela nasceu.

**Nada aqui é executado pela v3.** É material de consulta.

| Arquivo | O que era | Onde a ideia foi parar |
|---|---|---|
| `ponte_impressao.py` | a ponte v2 inteira: servidor HTTP, caminhos `sistema:` e `usb:`, lista de origens, teto por minuto | dividida em `ponte_menuxy/servidor.py`, `catalogo.py`, `escpos.py` e `backends/` |
| `usbprint_win.py` | transporte pelo `usbprint.sys` do Windows — o achado que resolveu o Windows ARM sem Zadig | virou `ponte_menuxy/backends/usbprint.py`, com o mesmo `GUID_DEVINTERFACE_USBPRINT` e o mesmo cuidado com o `cbSize` do cabeçalho |
| `exemplo_web.html` | página de exemplo do navegador | `exemplos/web/exemplo.html`, agora usando o cliente reutilizável |
| `ponte.bat` | atalho para subir a ponte no Windows | `empacotar/windows/instalar_windows.bat` e o atalho `.lnk` criado por `--criar-atalho` |
| `instalar_inicializacao.bat` | registrava a ponte na inicialização do Windows | `ponte_menuxy/inicializacao.py`, que faz isso nos três sistemas |

## O que a v3 aprendeu com esta versão

Três coisas descobertas aqui custaram caro e não devem ser refeitas por
suposição:

1. **`Access-Control-Allow-Private-Network: true`.** Sem esse cabeçalho no
   preflight, o Chrome barra a chamada a `127.0.0.1` mesmo com o CORS comum
   liberado — e **sem erro visível no console**.
2. **RAW é o ponto no Windows, `-o raw` é o ponto no CUPS.** Sem eles o
   trabalho é convertido e a térmica recebe PostScript.
3. **O `usbprint.sys` pode ser o transporte, não só o obstáculo.** É o que
   torna o Windows ARM viável sem Zadig e sem administrador.

## Se você precisar de algo daqui

O histórico do git tem tudo: `git log --follow legado/<arquivo>`. A versão
original, antes da reorganização, está no commit `3702710`.
