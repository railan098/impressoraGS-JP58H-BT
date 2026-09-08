@echo off
REM ============================================================================
REM  ponte.bat - Abre a Ponte de Impressao (servidor local + janela de status)
REM
REM  Duplo clique para deixar a impressora disponivel para o navegador.
REM  O software web imprime com um fetch() em http://127.0.0.1:9100
REM ============================================================================
setlocal
title Ponte de Impressao - Termica 58mm
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    set "VPYW=%CD%\.venv\Scripts\pythonw.exe"
) else (
    set "VPYW=pythonw"
)

REM pythonw.exe roda sem abrir janela preta de console: so a janela do app.
start "" "%VPYW%" "%CD%\ponte_impressao.py"
endlocal
