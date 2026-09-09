@echo off
REM ==========================================================================
REM  Gera o PonteMenuxy.exe — rode na SUA maquina, uma vez por versao.
REM
REM  O que sai:  dist\PonteMenuxy.exe  — um arquivo unico, que roda em maquina
REM  SEM Python instalado. E esse arquivo que voce entrega ao cliente.
REM ==========================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0..\.."

echo.
echo ======================================================================
echo    Ponte de Impressao Menuxy - gerador do executavel do Windows
echo ======================================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale de https://www.python.org/downloads/windows/
    echo        e marque "Add python.exe to PATH" na primeira tela.
    pause & exit /b 1
)

for /f "tokens=*" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%v
echo [i] Python !PYVER!

echo [i] Instalando o PyInstaller e os opcionais...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller
REM  pyusb e pyserial sao opcionais: entram no .exe se instalarem, e ampliam
REM  os caminhos que ele cobre. Se a instalacao falhar, seguimos assim mesmo.
python -m pip install --quiet pyusb pyserial libusb-package 2>nul

echo [i] Empacotando (isso leva um ou dois minutos)...
python -m PyInstaller --clean --noconfirm empacotar\PonteMenuxy.spec
if errorlevel 1 (
    echo.
    echo [ERRO] O PyInstaller falhou. A causa costuma aparecer acima.
    pause & exit /b 1
)

if not exist "dist\PonteMenuxy.exe" (
    echo [ERRO] O executavel nao foi gerado.
    pause & exit /b 1
)

echo.
echo ======================================================================
echo    Pronto:  dist\PonteMenuxy.exe
echo.
echo    Confira antes de entregar:
echo      dist\PonteMenuxy.exe --listar
echo      dist\PonteMenuxy.exe --diagnostico
echo.
echo    No cliente: copie o .exe para uma pasta dele (NAO para System32),
echo    de um duplo clique e use a aba Configuracao para ligar o inicio
echo    automatico e escolher a impressora.
echo ======================================================================
echo.
pause
