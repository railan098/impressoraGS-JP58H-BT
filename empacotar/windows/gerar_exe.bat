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

REM ==========================================================================
REM  Assinatura digital - OPCIONAL, e a diferenca entre o cliente ver
REM  "O Windows protegeu o seu computador" ou nao ver nada.
REM
REM  Sem assinatura o build NAO falha: sai um .exe que funciona, com aviso do
REM  SmartScreen na primeira execucao. Configure quando tiver o certificado.
REM
REM  Escolha UMA das tres formas, por variavel de ambiente:
REM
REM    MENUXY_CERT_SHA1=a1b2c3...      impressao digital do certificado na loja
REM                                    do Windows. E a forma mais precisa, e a
REM                                    que funciona com token EV e HSM.
REM    MENUXY_CERT_NOME=Railan Alves   nome do titular, se so houver um.
REM    MENUXY_CERT_PFX=C:\cert.pfx     arquivo .pfx, com MENUXY_CERT_SENHA.
REM                                    So para certificado antigo: desde junho
REM                                    de 2023 os novos exigem hardware.
REM
REM  Opcional:  MENUXY_CARIMBO=http://timestamp.sectigo.com
REM ==========================================================================
set "ASSINADO=nao"
call :assinar
goto :depois_de_assinar

:assinar
if not defined MENUXY_CARIMBO set "MENUXY_CARIMBO=http://timestamp.digicert.com"

if not defined MENUXY_CERT_SHA1 if not defined MENUXY_CERT_NOME if not defined MENUXY_CERT_PFX (
    echo.
    echo [i] Sem certificado configurado - o .exe sai SEM assinatura.
    echo     O cliente vera "O Windows protegeu o seu computador" na primeira
    echo     execucao, e precisa de "Mais informacoes" e "Executar assim mesmo".
    echo     Como assinar: docs\EMPACOTAMENTO.md
    goto :eof
)

REM  Procura o signtool: no PATH, e depois no SDK do Windows. O /o:n faz a
REM  ultima iteracao ser a versao mais nova do SDK.
set "SIGNTOOL="
where signtool >nul 2>&1 && set "SIGNTOOL=signtool"

REM  ProgramFiles(x86) tem parenteses no NOME, e parentese dentro de um bloco
REM  if(...) encerra o bloco no meio. Por isso ele sai para uma variavel simples
REM  aqui fora, e la dentro so se usa !SDK!.
set "SDK=%ProgramFiles(x86)%"
if not defined SDK set "SDK=%ProgramFiles%"

if not defined SIGNTOOL (
    for /f "delims=" %%i in ('dir /b /s /o:n "!SDK!\Windows Kits\10\bin\*\x64\signtool.exe" 2^>nul') do set "SIGNTOOL=%%i"
)
if not defined SIGNTOOL (
    echo.
    echo [AVISO] Certificado configurado, mas o signtool.exe nao foi encontrado.
    REM  Parenteses escapados: dentro de um bloco if^(...^) um ^) solto
    REM  encerraria o bloco no meio da mensagem.
    echo         Instale o "Windows SDK" ^(componente "Signing Tools"^).
    echo         O executavel foi gerado, porem SEM assinatura.
    goto :eof
)
echo [i] signtool: !SIGNTOOL!

REM  /fd e /td SHA256: SHA-1 esta obsoleto e o Windows recusa.
REM  /tr (carimbo RFC 3161) NAO e opcional: sem ele a assinatura morre junto
REM  com o certificado, e os .exe ja entregues voltam a dar aviso.
if defined MENUXY_CERT_SHA1 (
    echo [i] Assinando pela impressao digital do certificado...
    "!SIGNTOOL!" sign /fd SHA256 /td SHA256 /tr "!MENUXY_CARIMBO!" /sha1 "!MENUXY_CERT_SHA1!" "dist\PonteMenuxy.exe"
) else if defined MENUXY_CERT_PFX (
    echo [i] Assinando com o arquivo .pfx...
    "!SIGNTOOL!" sign /fd SHA256 /td SHA256 /tr "!MENUXY_CARIMBO!" /f "!MENUXY_CERT_PFX!" /p "!MENUXY_CERT_SENHA!" "dist\PonteMenuxy.exe"
) else (
    echo [i] Assinando pelo nome do titular...
    "!SIGNTOOL!" sign /fd SHA256 /td SHA256 /tr "!MENUXY_CARIMBO!" /n "!MENUXY_CERT_NOME!" "dist\PonteMenuxy.exe"
)
if errorlevel 1 (
    echo.
    echo [AVISO] A assinatura falhou - a causa esta acima.
    echo         Token EV: confira se esta plugado e se o PIN foi aceito.
    echo         O executavel foi gerado, porem SEM assinatura.
    goto :eof
)

REM  Conferir vale a pena: assinar "com sucesso" e a cadeia nao fechar no
REM  cliente e um erro que so aparece la, e tarde.
echo [i] Conferindo a assinatura...
"!SIGNTOOL!" verify /pa /v "dist\PonteMenuxy.exe" >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Assinou, mas a verificacao falhou. A cadeia do certificado
    echo         pode estar incompleta - o cliente veria o aviso mesmo assim.
    goto :eof
)
set "ASSINADO=sim"
echo [ok] Executavel assinado e verificado.
goto :eof

:depois_de_assinar

echo.
echo ======================================================================
echo    Pronto:  dist\PonteMenuxy.exe
echo.
echo    Assinado digitalmente: !ASSINADO!
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
