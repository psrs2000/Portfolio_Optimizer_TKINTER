@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Construir o executavel

rem Gera a pasta "Otimizador de Portfolio" dentro de dist\. Roda no Windows,
rem e so no Windows: o PyInstaller nao faz executavel de um sistema para outro.
rem
rem Este arquivo precisa ficar em CRLF e sem acentos. O cmd.exe le arquivo de
rem lote por deslocamento de bytes: com fim de linha do Unix ele cai no meio
rem das palavras, e o erro que aparece e "'cho' nao e reconhecido".

set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"

if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY goto :sempython

rem Todos os modulos precisam estar nesta pasta. Faltando um, o executavel
rem sai sem a fonte de dados correspondente e o erro so aparece la na frente.
if not exist "desktop_app_qt.py" goto :faltaarquivo
if not exist "optimizer.py" goto :faltaarquivo
if not exist "cvm_fundos.py" goto :faltaarquivo
if not exist "b3_series_wide_com_limpeza.py" goto :faltaarquivo
if not exist "b3_excel_rendafixa.py" goto :faltaarquivo
if not exist "requirements.txt" goto :faltaarquivo
if not exist "desktop_app_qt.spec" goto :faltaarquivo

echo.
echo   Preparando o ambiente de construcao...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if errorlevel 1 goto :falhou

".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 goto :falhou

rem Fontes de dados opcionais. Falhar aqui nao impede a construcao: o
rem aplicativo abre do mesmo jeito e so avisa o que falta naquele botao.
echo   Instalando as fontes de dados opcionais...
".venv\Scripts\python.exe" -m pip install --quiet yfinance
".venv\Scripts\python.exe" -m pip install --quiet xlwings

echo   Construindo. Isso leva alguns minutos.
echo.
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm "desktop_app_qt.spec"
if errorlevel 1 goto :falhou

echo.
echo   Pronto: dist\Otimizador de Portfolio.exe
echo.
echo   Esse arquivo sozinho ja e o programa. Basta envia-lo ao usuario:
echo   nao precisa de Python nem de mais nada instalado.
echo.
echo   Ele leva alguns segundos para abrir, toda vez. E normal: um
echo   executavel unico descompacta o proprio conteudo antes de iniciar.
echo.
pause
exit /b 0

:sempython
echo.
echo   Nao encontrei o Python neste computador.
echo.
echo   Baixe em https://www.python.org/downloads/
echo   IMPORTANTE: na primeira tela do instalador, marque a caixa
echo   "Add python.exe to PATH" antes de clicar em Install.
echo.
pause
exit /b 1

:faltaarquivo
echo.
echo   Esta faltando um arquivo do projeto nesta pasta.
echo.
echo   Devem estar todos juntos, ao lado deste .bat:
echo     desktop_app_qt.py            (o programa)
echo     optimizer.py                 (motor de calculo)
echo     cvm_fundos.py                (fonte CVM)
echo     b3_series_wide_com_limpeza.py (fonte B3)
echo     b3_excel_rendafixa.py        (fonte Excel)
echo     requirements.txt
echo     desktop_app_qt.spec
echo.
pause
exit /b 1

:falhou
echo.
echo   Algo deu errado. Veja a mensagem acima.
echo   Se insistir, apague a pasta .venv e clique aqui de novo.
echo.
pause
exit /b 1
