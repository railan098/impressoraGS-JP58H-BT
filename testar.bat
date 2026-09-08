@echo off
REM ============================================================================
REM  testar.bat - Roda a bateria de autotestes no Windows
REM
REM  Duplo clique para diagnosticar tudo:
REM    - ambiente (Python, arquitetura, pasta)
REM    - dependencias (pyusb, python-escpos)
REM    - backend libusb
REM    - comandos ESC/POS e montagem do cupom
REM    - enumeracao USB e deteccao da impressora
REM    - tratamento de erros
REM
REM  Passe --imprimir para incluir a impressao fisica:
REM      testar.bat --imprimir
REM ============================================================================
setlocal
title Autoteste - Impressora Termica 58mm
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "VPY=%CD%\.venv\Scripts\python.exe"
) else (
    set "VPY=python"
    echo [AVISO] Ambiente virtual nao encontrado - rode instalar.bat primeiro.
    echo.
)

"%VPY%" autoteste.py %*

echo.
echo ============================================================================
echo   Copie TODO o texto acima e mande para quem for te ajudar.
echo   Para selecionar: botao direito na janela ^> Marcar ^> arraste ^> Enter
echo ============================================================================
echo.
pause
endlocal
