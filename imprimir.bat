@echo off
REM ============================================================================
REM  imprimir.bat - Menu de uso da impressora termica 58mm
REM  Duplo clique para abrir o menu, ou passe argumentos direto:
REM      imprimir.bat --texto "Meu recibo"
REM      imprimir.bat --listar
REM ============================================================================
setlocal EnableDelayedExpansion
title Impressora Termica 58mm
cd /d "%~dp0"

REM Prefere o ambiente virtual; cai para o Python global se nao houver.
if exist ".venv\Scripts\python.exe" (
    set "VPY=%CD%\.venv\Scripts\python.exe"
) else (
    set "VPY=python"
    echo [AVISO] Ambiente virtual nao encontrado. Rode instalar.bat primeiro.
    echo.
)

REM Se veio argumento na linha de comando, executa direto e sai.
if not "%~1"=="" (
    "%VPY%" imprime_termica.py %*
    echo.
    pause
    goto :eof
)

:menu
cls
echo.
echo ============================================================================
echo   IMPRESSORA TERMICA 58mm - SMX-JP58H / POS-58
echo ============================================================================
echo.
echo   1. Imprimir cupom de TESTE
echo   2. Listar dispositivos USB (descobrir VID/PID)
echo   3. Imprimir um texto que eu digitar
echo   4. Imprimir o conteudo de um arquivo .txt
echo   5. Imprimir usando a biblioteca python-escpos
echo   6. Abrir a gaveta de dinheiro (RJ11)
echo   7. Imprimir SEM o comando de corte
echo   8. Trocar a pagina de codigo (se os acentos sairem errados)
echo   9. Gerar o executavel standalone (.exe)
echo   0. Sair
echo.
set "OP="
set /p "OP=   Escolha uma opcao: "
echo.

if "%OP%"=="1" ( "%VPY%" imprime_termica.py & goto :pausa )
if "%OP%"=="2" ( "%VPY%" imprime_termica.py --listar & goto :pausa )
if "%OP%"=="3" goto :texto
if "%OP%"=="4" goto :arquivo
if "%OP%"=="5" ( "%VPY%" imprime_termica.py --usar-escpos & goto :pausa )
if "%OP%"=="6" ( "%VPY%" imprime_termica.py --abrir-gaveta --texto "Gaveta aberta" & goto :pausa )
if "%OP%"=="7" ( "%VPY%" imprime_termica.py --sem-corte & goto :pausa )
if "%OP%"=="8" goto :codepage
if "%OP%"=="9" ( call gerar_exe.bat & goto :menu )
if "%OP%"=="0" goto :eof
echo   Opcao invalida.
goto :pausa

:texto
set "TXT="
set /p "TXT=   Digite o texto: "
if "%TXT%"=="" goto :menu
"%VPY%" imprime_termica.py --texto "%TXT%"
goto :pausa

:arquivo
set "ARQ="
set /p "ARQ=   Caminho do arquivo .txt: "
if "%ARQ%"=="" goto :menu
"%VPY%" imprime_termica.py --arquivo "%ARQ%"
goto :pausa

:codepage
echo   Paginas de codigo disponiveis:
echo     cp850  - Multilingual (padrao, melhor para portugues)
echo     cp860  - Portuguese (tente esta se cp850 falhar)
echo     cp437  - Padrao de fabrica da maioria
echo     cp1252 - Windows Latin-1
echo.
set "CP="
set /p "CP=   Qual usar: "
if "%CP%"=="" goto :menu
"%VPY%" imprime_termica.py --codepage %CP%
goto :pausa

:pausa
echo.
pause
goto :menu
