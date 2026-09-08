@echo off
REM ============================================================================
REM  instalar.bat - Instalador completo da Impressora Termica 58mm (ESC/POS USB)
REM  Windows 10/11 - x64 e ARM64 (Snapdragon)
REM
REM  Basta dar DUPLO CLIQUE neste arquivo. Ele faz tudo:
REM    - confere o Python e a arquitetura
REM    - cria o ambiente virtual .venv
REM    - instala pyusb + python-escpos
REM    - resolve a libusb (automatico no x64, download no ARM64)
REM    - testa o backend e procura a impressora
REM
REM  Sem acentos de proposito: evita problemas de encoding do cmd.exe.
REM ============================================================================
setlocal EnableDelayedExpansion
title Instalador - Impressora Termica 58mm ESC/POS
cd /d "%~dp0"

set "PY=python"
set "VENV=.venv"
set "ERROS=0"

echo.
echo ============================================================================
echo   INSTALADOR - IMPRESSORA TERMICA 58mm (SMX-JP58H / POS-58)
echo   Comunicacao ESC/POS direta via USB - sem driver do fabricante
echo ============================================================================
echo.

REM ---------------------------------------------------------------- [1/7]
echo [1/7] Procurando o Python...
where %PY% >nul 2>&1
if errorlevel 1 (
    set "PY=py"
    where py >nul 2>&1
    if errorlevel 1 (
        echo.
        echo   [ERRO] Python nao encontrado no PATH.
        echo.
        echo   Voce disse que ja instalou o Python 3.14.7. O problema entao e
        echo   que ele nao foi adicionado ao PATH. Duas saidas:
        echo.
        echo     A) Reinstale marcando a caixa "Add python.exe to PATH"
        echo        na PRIMEIRA tela do instalador; ou
        echo     B) Painel de Controle ^> Aplicativos ^> Python ^> Modificar
        echo        ^> Next ^> marque "Add Python to environment variables"
        echo.
        goto :falhou
    )
)
for /f "delims=" %%v in ('%PY% -c "import sys;print(sys.version.split()[0])" 2^>nul') do set "PYVER=%%v"
for /f "delims=" %%a in ('%PY% -c "import platform;print(platform.machine())" 2^>nul') do set "PYARCH=%%a"
for /f "delims=" %%e in ('%PY% -c "import sys;print(sys.executable)" 2^>nul') do set "PYEXE=%%e"

if "%PYVER%"=="" (
    echo   [ERRO] O comando "%PY%" existe mas nao respondeu.
    echo   Provavelmente e o atalho falso da Microsoft Store.
    echo   Desative em: Configuracoes ^> Aplicativos ^> Aliases de execucao.
    goto :falhou
)

echo       Versao      : Python %PYVER%
echo       Arquitetura : %PYARCH%
echo       Executavel  : %PYEXE%

REM ---- Aviso critico sobre ARM64 -----------------------------------------
set "EH_ARM=0"
if /i "%PYARCH%"=="ARM64" set "EH_ARM=1"

if "%EH_ARM%"=="1" (
    echo.
    echo   ##########################################################################
    echo   #  ATENCAO: voce instalou o Python ARM64 nativo.                         #
    echo   #                                                                        #
    echo   #  Isso FUNCIONA, mas da mais trabalho: o pacote libusb-package NAO tem  #
    echo   #  versao para win_arm64, entao este script vai precisar baixar a DLL    #
    echo   #  ARM64 da libusb direto do GitHub (faco isso automaticamente no        #
    echo   #  passo 5).                                                             #
    echo   #                                                                        #
    echo   #  Se algo falhar, a rota mais simples e desinstalar este Python e       #
    echo   #  instalar o "Windows installer (64-bit)" / amd64. O Windows 11 ARM     #
    echo   #  roda x64 por emulacao, e para imprimir um cupom isso e irrelevante.   #
    echo   ##########################################################################
    echo.
    timeout /t 5 >nul
)

REM ---------------------------------------------------------------- [2/7]
echo.
echo [2/7] Criando o ambiente virtual (%VENV%)...
if exist "%VENV%\Scripts\python.exe" (
    echo       Ja existe - reaproveitando.
) else (
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo   [ERRO] Falha ao criar o ambiente virtual.
        echo   Tente:  %PY% -m pip install --upgrade virtualenv
        goto :falhou
    )
    echo       Criado com sucesso.
)
set "VPY=%CD%\%VENV%\Scripts\python.exe"

REM ---------------------------------------------------------------- [3/7]
echo.
echo [3/7] Atualizando o pip...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 (
    echo       [AVISO] Nao consegui atualizar o pip. Seguindo mesmo assim.
) else (
    echo       pip atualizado.
)

REM ---------------------------------------------------------------- [4/7]
echo.
echo [4/7] Instalando pyusb e python-escpos...
echo       ^(pode demorar 1-2 minutos^)
"%VPY%" -m pip install --quiet --disable-pip-version-check pyusb python-escpos
if errorlevel 1 (
    echo   [ERRO] Falha ao instalar as dependencias.
    echo   Verifique sua conexao com a internet, ou rode manualmente:
    echo       "%VPY%" -m pip install pyusb python-escpos
    goto :falhou
)
echo       pyusb + python-escpos instalados.

REM ---------------------------------------------------------------- [5/7]
echo.
echo [5/7] Resolvendo a biblioteca libusb...

if "%EH_ARM%"=="1" goto :libusb_arm

REM ---- Caminho x64/x86: o pacote resolve sozinho -------------------------
echo       Python x64/x86 detectado - usando libusb-package.
"%VPY%" -m pip install --quiet --disable-pip-version-check libusb-package
if errorlevel 1 (
    echo       [AVISO] libusb-package falhou. Vou baixar a DLL manualmente.
    goto :libusb_arm
)
echo       libusb-package instalado.
goto :libusb_ok

REM ---- Caminho ARM64 (ou fallback): baixar a DLL do release oficial ------
:libusb_arm
if exist "libusb-1.0.dll" (
    echo       libusb-1.0.dll ja esta na pasta - reaproveitando.
    goto :libusb_ok
)

set "LIBUSB_VER=1.0.30"
set "LIBUSB_URL=https://github.com/libusb/libusb/releases/download/v%LIBUSB_VER%/libusb-%LIBUSB_VER%.7z"
if "%EH_ARM%"=="1" (
    set "DLL_PATH=VS2025/ARM64/dll/libusb-1.0.dll"
) else (
    set "DLL_PATH=VS2025/MS64/dll/libusb-1.0.dll"
)

echo       Baixando libusb %LIBUSB_VER% do GitHub...
echo       ^(cerca de 7 MB^)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%LIBUSB_URL%' -OutFile 'libusb_tmp.7z' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    echo       [AVISO] Download falhou.
    goto :libusb_manual
)

echo       Extraindo %DLL_PATH% ...
REM O tar do Windows 10/11 (bsdtar/libarchive) le arquivos .7z.
tar -xf libusb_tmp.7z "%DLL_PATH%" 2>nul
if errorlevel 1 (
    echo       [AVISO] O tar do Windows nao conseguiu abrir o .7z.
    goto :libusb_manual
)

for %%F in ("%DLL_PATH:/=\%") do copy /y "%%~fF" "libusb-1.0.dll" >nul 2>&1
if not exist "libusb-1.0.dll" (
    echo       [AVISO] A DLL nao apareceu apos a extracao.
    goto :libusb_manual
)

REM Limpeza dos temporarios
del /q libusb_tmp.7z >nul 2>&1
if exist "VS2025" rmdir /s /q "VS2025" >nul 2>&1
echo       libusb-1.0.dll instalada na pasta do projeto.
goto :libusb_ok

:libusb_manual
echo.
echo       ----------------------------------------------------------------
echo       NAO CONSEGUI INSTALAR A LIBUSB AUTOMATICAMENTE.
echo       Faca manualmente (leva 2 minutos):
echo.
echo         1. Abra: https://github.com/libusb/libusb/releases
echo         2. Baixe: libusb-%LIBUSB_VER%.7z
echo         3. Extraia com o 7-Zip ou WinRAR
echo         4. Copie o arquivo:
echo              %DLL_PATH:/=\%
echo            para esta pasta:
echo              %CD%
echo         5. Renomeie para: libusb-1.0.dll  (se ja nao for)
echo         6. Rode este instalador de novo.
echo       ----------------------------------------------------------------
echo.
set /a ERROS+=1
start "" "https://github.com/libusb/libusb/releases"

:libusb_ok

REM ---------------------------------------------------------------- [6/7]
echo.
echo [6/7] Testando o backend USB...
"%VPY%" -c "import usb.core,usb.backend.libusb1,os,sys; d=os.path.abspath('libusb-1.0.dll'); b=usb.backend.libusb1.get_backend(find_library=lambda x:d) if os.path.isfile(d) else usb.backend.libusb1.get_backend(); print('   backend OK' if b else '   SEM BACKEND'); sys.exit(0 if b else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo       [ERRO] Nenhum backend libusb utilizavel.
    echo       Sem isso o Python nao consegue falar com a USB.
    echo       Volte ao passo 5 e resolva a libusb.
    set /a ERROS+=1
) else (
    echo       Backend libusb funcionando.
)

REM ---------------------------------------------------------------- [7/7]
echo.
echo [7/7] Procurando a impressora...
echo.
"%VPY%" imprime_termica.py --listar
echo.

REM ---------------------------------------------------------------- Final
echo ============================================================================
if "%ERROS%"=="0" (
    echo   INSTALACAO CONCLUIDA.
) else (
    echo   INSTALACAO CONCLUIDA COM %ERROS% PENDENCIA^(S^) - veja os avisos acima.
)
echo ============================================================================
echo.
echo   PROXIMO PASSO OBRIGATORIO - O DRIVER WinUSB:
echo.
echo   Se a impressora NAO apareceu marcada com "IMPRESSORA (classe USB 7)"
echo   na lista acima, o Windows ainda esta com o driver usbprint.sys nela,
echo   que bloqueia o acesso direto. Voce PRECISA troca-lo pelo WinUSB:
echo.
echo     1. Baixe o Zadig em https://zadig.akeo.ie/  (nao instala nada)
echo     2. Ligue a impressora (botao de energia, nao so o cabo)
echo     3. Botao direito no zadig.exe ^> Executar como administrador
echo     4. Menu Options ^> marque "List All Devices"     ^<-- ESSENCIAL
echo     5. Escolha "POS-58 Printer" na lista
echo        Confira o USB ID:  0416  5011
echo     6. No campo da direita use as setas ate aparecer  WinUSB
echo     7. Clique em "Replace Driver" e aguarde
echo     8. Desconecte e reconecte o cabo USB
echo     9. Rode este instalador de novo para confirmar
echo.
echo   Detalhes completos e solucao de problemas: README.md
echo.
echo ============================================================================
echo.
echo   COMO USAR A PARTIR DE AGORA:
echo     imprimir.bat        - menu com todas as opcoes
echo     gerar_exe.bat       - cria o executavel standalone
echo.

choice /c SN /n /m "   Quer imprimir o cupom de teste agora? [S/N]: "
if errorlevel 2 goto :fim
echo.
echo   Enviando cupom de teste...
"%VPY%" imprime_termica.py
goto :fim

:falhou
echo.
echo ============================================================================
echo   INSTALACAO INTERROMPIDA - resolva o erro acima e rode de novo.
echo ============================================================================

:fim
echo.
pause
endlocal
