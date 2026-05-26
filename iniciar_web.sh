#!/bin/bash
# Inicializacao do frontend web + API FastAPI em ambiente local.

set -euo pipefail

cd "$(dirname "$0")"

ROOT_DIR="$(pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
NEXT_BIN_JS="$FRONTEND_DIR/node_modules/next/dist/bin/next"
PACKAGE_LOCK="$FRONTEND_DIR/package-lock.json"
PNPM_LOCK="$FRONTEND_DIR/pnpm-lock.yaml"
PNPM_LOCK_BACKUP="$FRONTEND_DIR/pnpm-lock.yaml.disabled-by-npm"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3000}"

API_LOG="${TMPDIR:-/tmp}/automocao-api.log"

API_PID=""

banner() {
    echo ""
    echo "=========================================="
    echo " DCF - Automacao de Liquidacao (Web)"
    echo "=========================================="
    echo ""
}

porta_em_uso() {
    local porta="$1"
    lsof -iTCP:"$porta" -sTCP:LISTEN -n -P >/dev/null 2>&1
}

cleanup() {
    local status=$?

    if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
        echo ""
        echo "Encerrando API..."
        kill "$API_PID" 2>/dev/null || true
        wait "$API_PID" 2>/dev/null || true
    fi

    if [ -f "$PNPM_LOCK_BACKUP" ] && [ ! -f "$PNPM_LOCK" ]; then
        mv "$PNPM_LOCK_BACKUP" "$PNPM_LOCK"
    fi

    exit "$status"
}

trap cleanup EXIT INT TERM

resolver_python_sistema() {
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return
    fi
    if command -v python >/dev/null 2>&1; then
        command -v python
        return
    fi

    echo "[py] Python nao encontrado no sistema."
    exit 1
}

recriar_venv() {
    local python_sistema
    python_sistema="$(resolver_python_sistema)"

    echo "[py] Recriando ambiente virtual em $VENV_DIR..."
    "$python_sistema" -m venv --clear "$VENV_DIR"
}

reinstalar_frontend() {
    echo "[web] Reinstalando dependencias do frontend..."
    (
        cd "$FRONTEND_DIR"
        npm ci --include=optional
    )
}

garantir_python() {
    if [ ! -d "$VENV_DIR" ]; then
        echo "[py] Criando ambiente virtual..."
        recriar_venv
    elif [ ! -x "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c "import sys" >/dev/null 2>&1; then
        echo "[py] Ambiente virtual invalido ou movido. Vou recriar a .venv."
        recriar_venv
    fi

    if [ ! -x "$PYTHON_BIN" ]; then
        echo "[py] Nao encontrei o Python da venv em $PYTHON_BIN"
        exit 1
    fi

    if ! "$PYTHON_BIN" -c "import fastapi, uvicorn, multipart, pandas" >/dev/null 2>&1; then
        echo "[py] Instalando dependencias Python..."
        "$PYTHON_BIN" -m pip install -r requirements.txt
    else
        echo "[py] Dependencias Python OK"
    fi

    if [ ! -d "$HOME/Library/Caches/ms-playwright" ]; then
        echo "[py] Instalando browsers do Playwright..."
        "$PYTHON_BIN" -m playwright install chromium
    fi
}

garantir_node() {
    if ! command -v npm >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
        echo "[web] Node.js/npm nao encontrados. Instale Node.js antes de continuar."
        exit 1
    fi

    if [ ! -d "$FRONTEND_DIR" ]; then
        echo "[web] Pasta do frontend nao encontrada em $FRONTEND_DIR"
        exit 1
    fi

    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        reinstalar_frontend
    else
        echo "[web] Dependencias do frontend OK"
    fi

    if [ ! -f "$NEXT_BIN_JS" ]; then
        echo "[web] Next.js nao encontrado em $NEXT_BIN_JS"
        echo "[web] Vou reinstalar as dependencias do frontend..."
        rm -rf "$FRONTEND_DIR/node_modules"
        reinstalar_frontend
    fi

    if [ -f "$PACKAGE_LOCK" ] && [ -f "$PNPM_LOCK" ]; then
        echo "[web] Detectei package-lock.json e pnpm-lock.yaml juntos."
        echo "[web] Vou desativar temporariamente o pnpm-lock para o Next usar npm."
        rm -f "$PNPM_LOCK_BACKUP"
        mv "$PNPM_LOCK" "$PNPM_LOCK_BACKUP"
    fi

    if ! (
        cd "$FRONTEND_DIR"
        node -e "require('lightningcss/node')"
    ) >/dev/null 2>&1; then
        echo "[web] Dependencia nativa do lightningcss nao encontrada."
        echo "[web] Vou reinstalar o frontend com dependencias opcionais da plataforma."
        rm -rf "$FRONTEND_DIR/node_modules"
        reinstalar_frontend
    fi
}

validar_portas() {
    if porta_em_uso "$API_PORT"; then
        echo "[api] Porta $API_PORT ja esta em uso."
        exit 1
    fi

    if porta_em_uso "$WEB_PORT"; then
        echo "[web] Porta $WEB_PORT ja esta em uso."
        exit 1
    fi
}

subir_api() {
    echo "[api] Iniciando FastAPI em http://$API_HOST:$API_PORT"
    : > "$API_LOG"

    "$PYTHON_BIN" -m uvicorn api:app --host "$API_HOST" --port "$API_PORT" >"$API_LOG" 2>&1 &
    API_PID=$!

    for tentativa in $(seq 1 20); do
        if curl -fsS "http://$API_HOST:$API_PORT/api/health" >/dev/null 2>&1; then
            echo "[api] API pronta"
            return
        fi

        if ! kill -0 "$API_PID" 2>/dev/null; then
            echo "[api] A API encerrou logo apos iniciar. Ultimas linhas do log:"
            tail -n 40 "$API_LOG" || true
            exit 1
        fi

        sleep 0.5
    done

    echo "[api] Timeout aguardando a API responder em /api/health"
    tail -n 40 "$API_LOG" || true
    exit 1
}

subir_frontend() {
    echo "[web] Iniciando Next.js em http://$WEB_HOST:$WEB_PORT"
    echo "[web] API configurada em http://$API_HOST:$API_PORT"
    echo "[web] Log da API: $API_LOG"
    echo ""
    echo "Pressione Ctrl+C para encerrar tudo."
    echo ""

    (
        cd "$FRONTEND_DIR"
        NEXT_PUBLIC_API_BASE_URL="http://$API_HOST:$API_PORT" \
            node "$NEXT_BIN_JS" dev --webpack --hostname "$WEB_HOST" --port "$WEB_PORT"
    )
}

banner
garantir_python
garantir_node
validar_portas
subir_api
subir_frontend
