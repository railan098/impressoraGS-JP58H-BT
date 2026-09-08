@echo off
REM ============================================================================
REM  gerar_exe.bat - Compila o executavel standalone com PyInstaller
REM
REM  O .exe gerado roda em maquinas SEM Python instalado.
REM  ATENCAO: o driver WinUSB (Zadig) continua sendo necessario na maquina
REM  de destino - o .exe empacota o Python, nao o driver.
REM ============================================================================
setlocal
title Gerando executavel - Impressora Termica
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "VPY=%CD%\.venv\Scripts\python.exe"
) else (
    set "VPY=python"
)

echo.
echo ============================================================================
echo   GERANDO O EXECUTAVEL STANDALONE
echo ============================================================================
echo.

echo [1/3] Instalando o PyInstaller...
"%VPY%" -m pip install --quiet --disable-pip-version-check pyinstaller
if errorlevel 1 (
    echo   [ERRO] Falha ao instalar o PyInstaller.
    goto :fim
)
echo       OK.

echo.
echo [2/3] Compilando... isso demora de 1 a 3 minutos.
echo.

REM Se a DLL da libusb estiver solta na pasta, embute ela no .exe.
if exist "libusb-1.0.dll" (
    echo       Embutindo libusb-1.0.dll no executavel.
    "%VPY%" -m PyInstaller --onefile --console --name imprime_termica ^
        --collect-all usb ^
        --add-binary "libusb-1.0.dll;." ^
        --noconfirm --clean imprime_termica.py
) else (
    "%VPY%" -m PyInstaller --onefile --console --name imprime_termica ^
        --collect-all usb ^
        --collect-all libusb_package ^
        --noconfirm --clean imprime_termica.py
)

if errorlevel 1 (
    echo.
    echo   [ERRO] A compilacao falhou. Leia as mensagens acima.
    goto :fim
)

echo.
echo [3/3] Limpando arquivos temporarios...
if exist "build" rmdir /s /q "build" >nul 2>&1
echo       OK.

echo.
echo ============================================================================
echo   PRONTO: dist\imprime_termica.exe
echo ============================================================================
echo.
echo   Para distribuir, leve junto:
echo     - dist\imprime_termica.exe
echo     - README.md  (instrucoes do Zadig)
echo.
echo   Lembre-se: na maquina de destino ainda e preciso rodar o Zadig
echo   e trocar o driver da impressora para WinUSB.
echo.

:fim
pause
endlocal
