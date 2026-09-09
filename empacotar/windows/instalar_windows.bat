@echo off
REM ==========================================================================
REM  Instalador da Ponte de Impressao Menuxy no Windows, A PARTIR DO CODIGO.
REM
REM  Use este se a maquina TEM Python. Se nao tiver, entregue o
REM  PonteMenuxy.exe gerado por empacotar\windows\gerar_exe.bat.
REM
REM  Instala em %LOCALAPPDATA% e NAO em Program Files: la escrever exige
REM  administrador, e a ponte imprime com as permissoes de quem esta logado.
REM ==========================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0..\.."
set "ORIGEM=%CD%"
set "DESTINO=%LOCALAPPDATA%\MenuxyPonte"

echo.
echo ======================================================================
echo    Ponte de Impressao Menuxy - instalacao no Windows
echo ======================================================================
echo.

REM ---- Trava de pasta de sistema -------------------------------------------
REM  O "cmd como administrador" sempre abre em C:\Windows\System32, e um
REM  git clone ali joga o projeto dentro da pasta do sistema. Ja aconteceu.
echo %ORIGEM% | findstr /I /C:"\\Windows\\System32" /C:"\\Windows\\SysWOW64" >nul
if not errorlevel 1 (
    echo [ERRO] Este projeto esta dentro de uma pasta do SISTEMA:
    echo        %ORIGEM%
    echo.
    echo        Mova para os seus Documentos e rode de novo:
    echo          cd %%USERPROFILE%%\Documents
    echo          git clone ^<url do projeto^>
    pause & exit /b 1
)

REM ---- Python ---------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Baixe o "Windows installer (64-bit)" em
    echo        https://www.python.org/downloads/windows/
    echo        e marque "Add python.exe to PATH".
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%v
echo [ok] Python !PYVER!

python -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [!]  tkinter ausente: a ponte vai rodar sem janela.
) else (
    echo [ok] tkinter - a janela de configuracao vai abrir
)

REM ---- Copiar ---------------------------------------------------------------
echo [i]  Instalando em %DESTINO%
if exist "%DESTINO%\ponte_menuxy" rmdir /S /Q "%DESTINO%\ponte_menuxy"
mkdir "%DESTINO%" 2>nul
xcopy /E /I /Y /Q "%ORIGEM%\ponte_menuxy" "%DESTINO%\ponte_menuxy" >nul
if errorlevel 1 (
    echo [ERRO] Nao foi possivel copiar para %DESTINO%.
    pause & exit /b 1
)
echo [ok] arquivos copiados

REM ---- Opcionais ------------------------------------------------------------
echo [i]  Instalando os opcionais (USB e serial)...
python -m pip install --quiet --disable-pip-version-check pyusb pyserial libusb-package 2>nul
if errorlevel 1 (
    echo [!]  os opcionais falharam - a ponte funciona so com o caminho 'sistema:'
) else (
    echo [ok] pyusb e pyserial instalados
)

REM ---- Atalho de linha de comando -------------------------------------------
> "%DESTINO%\menuxy-ponte.bat" echo @echo off
>> "%DESTINO%\menuxy-ponte.bat" echo set PYTHONPATH=%DESTINO%
>> "%DESTINO%\menuxy-ponte.bat" echo python -m ponte_menuxy %%*

REM ---- Origem ---------------------------------------------------------------
echo.
echo  A ponte so aceita ordens dos enderecos que voce autorizar. Deixar
echo  aberto significa que qualquer site nesta maquina consegue gastar a
echo  sua bobina - nao ler nada, mas gastar.
echo.
set "ORIGEM_SISTEMA="
set /p ORIGEM_SISTEMA="  Endereco do seu sistema [https://menuxy.alvesprotect.app.br]: "
if "!ORIGEM_SISTEMA!"=="" set "ORIGEM_SISTEMA=https://menuxy.alvesprotect.app.br"
call "%DESTINO%\menuxy-ponte.bat" --origens "!ORIGEM_SISTEMA!" >nul
echo [ok] somente !ORIGEM_SISTEMA! pode mandar imprimir

REM ---- Atalhos e inicializacao ----------------------------------------------
echo.
call "%DESTINO%\menuxy-ponte.bat" --criar-atalho
set "AUTO="
set /p AUTO="  Iniciar a ponte junto com o Windows? [S/n]: "
if /I not "!AUTO!"=="n" call "%DESTINO%\menuxy-ponte.bat" --iniciar-com-sistema sim

REM ---- Impressoras ----------------------------------------------------------
echo.
echo  Impressoras que a ponte enxerga:
call "%DESTINO%\menuxy-ponte.bat" --listar

echo.
echo ======================================================================
echo    Instalada em %DESTINO%
echo.
echo    O atalho esta na area de trabalho e no menu Iniciar.
echo    Duplo clique nele para abrir a janela de configuracao.
echo ======================================================================
echo.
pause
