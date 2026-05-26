#!/bin/bash
# ─────────────────────────────────────────────────────────────
# DCF · Automação de Liquidação — Script de inicialização macOS
# ─────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   DCF · Automação de Liquidação          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

VENV_DIR=".venv"

resolver_python_sistema() {
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return
    fi
    if command -v python >/dev/null 2>&1; then
        command -v python
        return
    fi

    echo "❌ Python não encontrado no sistema."
    read -p "Pressione Enter para fechar..."
    exit 1
}

recriar_venv() {
    local python_sistema
    python_sistema="$(resolver_python_sistema)"

    echo "📦 Recriando ambiente virtual..."
    "$python_sistema" -m venv --clear "$VENV_DIR"
}

# ── Cria o ambiente virtual se não existir ────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Criando ambiente virtual (só na primeira vez)..."
    recriar_venv
    if [ $? -ne 0 ]; then
        echo "❌ Falha ao criar ambiente virtual."
        read -p "Pressione Enter para fechar..."
        exit 1
    fi
    echo "✓ Ambiente virtual criado"
elif [ ! -x "$VENV_DIR/bin/python3" ] || ! "$VENV_DIR/bin/python3" -c "import sys" >/dev/null 2>&1; then
    echo "📦 Ambiente virtual inválido ou movido. Vou recriar a .venv..."
    recriar_venv
    if [ $? -ne 0 ]; then
        echo "❌ Falha ao recriar o ambiente virtual."
        read -p "Pressione Enter para fechar..."
        exit 1
    fi
    echo "✓ Ambiente virtual recriado"
fi

# ── Ativa o ambiente virtual ──────────────────────────────────
source "$VENV_DIR/bin/activate"
PYTHON="$VENV_DIR/bin/python3"

# ── Instala dependências se necessário ───────────────────────
if ! $PYTHON -c "import PyQt6" 2>/dev/null; then
    echo "📦 Instalando dependências (só na primeira vez)..."
    $PYTHON -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ Falha ao instalar dependências."
        read -p "Pressione Enter para fechar..."
        exit 1
    fi
    echo "✓ Dependências instaladas"
else
    echo "✓ Dependências OK"
fi

# ── Playwright: instala browser se necessário ─────────────────
if [ ! -d "$HOME/Library/Caches/ms-playwright" ]; then
    echo "🌐 Configurando navegador (só na primeira vez)..."
    $PYTHON -m playwright install chromium
fi

# ── Abre o app ───────────────────────────────────────────────
echo ""
echo "🚀 Abrindo o app..."
echo ""
$PYTHON interface.py
