@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 goto pasta_erro
echo ========================================
echo       ESTACAO RADIO - GATEWAY
echo ========================================
if not exist ".env" goto sem_env
if exist ".venv\Scripts\python.exe" goto executar_venv
python --version >nul 2>&1
if errorlevel 1 goto sem_python
python "tools\iniciar.py" %*
goto resultado
:executar_venv
".venv\Scripts\python.exe" "tools\iniciar.py" %*
:resultado
set "resultado=%errorlevel%"
if not "%resultado%"=="0" (
    echo [ERRO] Inicializacao ou execucao interrompida. Confira as instrucoes acima.
    pause
)
popd
exit /b %resultado%
:sem_env
echo [ERRO] Arquivo .env nao encontrado.
echo Copie .env.example para .env e configure MICROSERIAL_GATEWAY_TOKEN.
goto falha
:sem_python
echo [ERRO] Python nao encontrado. Instale Python 3.10 ou superior.
echo Na instalacao, habilite Add Python to PATH e tente novamente.
goto falha
:pasta_erro
echo [ERRO] Nao foi possivel abrir a pasta do projeto.
pause
exit /b 1
:falha
pause
popd
exit /b 1
