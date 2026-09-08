@echo off
REM ============================================================================
REM  instalar_inicializacao.bat - Faz a Ponte de Impressao subir com o Windows
REM
REM  Cria um atalho na pasta Inicializar do SEU usuario (nao precisa de
REM  administrador, nao mexe em nada do sistema).
REM
REM  Para desinstalar, rode:  instalar_inicializacao.bat /remover
REM ============================================================================
setlocal
title Inicializacao automatica - Ponte de Impressao
cd /d "%~dp0"

set "ATALHO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Ponte de Impressao.lnk"

if /I "%~1"=="/remover" goto :remover

if exist ".venv\Scripts\pythonw.exe" (
    set "VPYW=%CD%\.venv\Scripts\pythonw.exe"
) else (
    set "VPYW=pythonw.exe"
)

echo.
echo  Instalando a inicializacao automatica...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%ATALHO%');" ^
  "$s.TargetPath = '%VPYW%';" ^
  "$s.Arguments = '\"%CD%\ponte_impressao.py\"';" ^
  "$s.WorkingDirectory = '%CD%';" ^
  "$s.Description = 'Ponte de Impressao - impressora termica 58mm';" ^
  "$s.Save()"

if errorlevel 1 (
    echo   [ERRO] Nao foi possivel criar o atalho.
    goto :fim
)

if exist "%ATALHO%" (
    echo   [OK] Pronto. A ponte vai subir sozinha no proximo login.
    echo.
    echo   Atalho criado em:
    echo   %ATALHO%
) else (
    echo   [ERRO] O atalho nao apareceu onde deveria.
)
goto :fim

:remover
if exist "%ATALHO%" (
    del "%ATALHO%"
    echo   [OK] Inicializacao automatica removida.
) else (
    echo   [--] Nao havia inicializacao automatica instalada.
)

:fim
echo.
pause
endlocal
