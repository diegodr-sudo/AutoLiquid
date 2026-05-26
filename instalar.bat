@echo off
echo ============================================
echo  DCF - Instalacao de Dependencias
echo ============================================
echo.

echo [1/3] Instalando pacotes Python...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo ERRO: Falha ao instalar pacotes. Verifique se o Python esta instalado.
    pause
    exit /b 1
)

echo.
echo [2/3] Instalando navegador Playwright (Chromium)...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo.
    echo AVISO: Falha ao instalar o Chromium via Playwright.
    echo Execute manualmente: python -m playwright install chromium
)

echo.
echo [3/3] Verificando instalacao...
python -c "import PyQt6; import playwright; import pdfplumber; import requests; print('OK - Todas as dependencias instaladas com sucesso!')"
if %errorlevel% neq 0 (
    echo ERRO: Alguma dependencia nao foi instalada corretamente.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Instalacao concluida!
echo  Execute: python interface.py
echo ============================================
echo.
pause
