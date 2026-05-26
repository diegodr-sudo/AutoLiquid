"""
construir.py — Gera o executável do DCF Automação de Liquidação.

USO (rode a partir da pasta Automocao):
    cd Automocao
    python construir.py

RESULTADO:
    macOS  → dist/DCFLiquidacao.app    (basta dar dois cliques para abrir)
    Windows → dist/DCFLiquidacao/DCFLiquidacao.exe

REQUISITOS (instale antes):
    pip install pyinstaller pyqt6 pdfplumber playwright requests
"""
import os
import platform
import shutil
import subprocess
import sys

# ─── Configuração ────────────────────────────────────────────────────────────
NOME_APP = "DCFLiquidacao"          # sem espaços — evita problemas no macOS
ENTRY    = "interface.py"
ICON_MAC = None                     # caminho para .icns (ex: "assets/icon.icns")
ICON_WIN = None                     # caminho para .ico  (ex: "assets/icon.ico")

MODULOS_OCULTOS = [
    "extrator",
    "consulta_cnpj",
    "comprasnet_base",
    "comprasnet_bot",
    "comprasnet_dados_basicos",
    "comprasnet_principal_orcamento",
    "comprasnet_deducao",
    "comprasnet_centro_custo",
    "comprasnet_dados_pagamento",
    "comprasnet_finalizar",
    # PyQt6 essenciais usados diretamente pelo app
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtSvg",
]

# Arquivos de dados a embutir no executável
DADOS_EXTRAS = [
    "configuracoes.json",
    "tabelas_config.json",
]


def _instalar_pyinstaller():
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  Instalando PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _build_mac():
    """Build para macOS — gera um .app clicável."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", NOME_APP,
        "--windowed",                    # cria .app bundle
        "--onedir",                      # mais rápido para abrir que --onefile
        "--osx-bundle-identifier", "br.gov.dcf.liquidacao",
    ]

    # Ícone
    if ICON_MAC and os.path.exists(ICON_MAC):
        cmd += ["--icon", ICON_MAC]

    # Hidden imports
    for mod in MODULOS_OCULTOS:
        cmd += ["--hidden-import", mod]

    # Coleta apenas os submódulos necessários para reduzir o tamanho do bundle.
    cmd += ["--collect-submodules", "PyQt6"]

    # Dados extras
    for src in DADOS_EXTRAS:
        if os.path.exists(src):
            cmd += ["--add-data", f"{src}:."]

    cmd.append(ENTRY)
    return cmd


def _build_win():
    """Build para Windows — gera um .exe."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", NOME_APP,
        "--windowed",                    # sem janela de console
        "--onedir",
    ]

    if ICON_WIN and os.path.exists(ICON_WIN):
        cmd += ["--icon", ICON_WIN]

    for mod in MODULOS_OCULTOS:
        cmd += ["--hidden-import", mod]

    cmd += ["--collect-submodules", "PyQt6"]

    for src in DADOS_EXTRAS:
        if os.path.exists(src):
            cmd += ["--add-data", f"{src};."]

    cmd.append(ENTRY)
    return cmd


def construir():
    print("=" * 60)
    print("  DCF Automação de Liquidação — Build")
    print("=" * 60)

    sistema = platform.system()
    print(f"\n  Plataforma: {sistema}")
    print(f"  Python: {sys.version.split()[0]}")

    if not os.path.exists(ENTRY):
        print(f"\n  ERRO: '{ENTRY}' não encontrado.")
        print(f"  Execute este script na pasta Automocao/.")
        sys.exit(1)

    _instalar_pyinstaller()

    if sistema == "Darwin":
        cmd = _build_mac()
    elif sistema == "Windows":
        cmd = _build_win()
    else:
        print(f"\n  Sistema '{sistema}' — usando build genérico (Linux).")
        cmd = _build_win()  # Funciona para Linux também (sem .app)
        # Troca ; por : nos --add-data
        cmd = [c.replace(";", ":") if "--add-data" not in c and ";" in c else c for c in cmd]
        # Refaz com separador correto
        cmd_fixed = []
        for i, c in enumerate(cmd):
            if i > 0 and cmd[i-1] == "--add-data" and ";" in c:
                cmd_fixed.append(c.replace(";", ":"))
            else:
                cmd_fixed.append(c)
        cmd = cmd_fixed

    print(f"\n  Comando: {' '.join(cmd)}")
    print(f"\n  Construindo... (1-3 min)\n")

    resultado = subprocess.run(cmd)

    if resultado.returncode != 0:
        print("\n  ERRO no build. Verifique as mensagens acima.")
        sys.exit(1)

    # ── Pós-build ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  BUILD CONCLUÍDO!")
    print("=" * 60)

    # Copia configs para dentro do dist se existirem
    dist_app = os.path.join("dist", NOME_APP)

    if sistema == "Darwin":
        # No macOS com --windowed --onedir, o .app fica em dist/NomeApp.app
        # OU em dist/NomeApp/NomeApp.app dependendo da versão do PyInstaller
        app_bundle = os.path.join("dist", f"{NOME_APP}.app")
        app_alt    = os.path.join("dist", NOME_APP, f"{NOME_APP}.app")

        if os.path.exists(app_bundle):
            destino = app_bundle
            # Configs vão para dentro do bundle: .app/Contents/MacOS/
            macos_dir = os.path.join(app_bundle, "Contents", "MacOS")
        elif os.path.exists(app_alt):
            destino = app_alt
            macos_dir = os.path.join(app_alt, "Contents", "MacOS")
        elif os.path.isdir(dist_app):
            destino = dist_app
            macos_dir = dist_app
        else:
            destino = "dist/"
            macos_dir = None

        if macos_dir and os.path.isdir(macos_dir):
            for src in DADOS_EXTRAS:
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(macos_dir, src))

        print(f"\n  Resultado: {destino}")
        if destino.endswith(".app"):
            print(f"\n  Para abrir: dois cliques em '{destino}'")
            print(f"  Ou no terminal: open '{destino}'")
        else:
            print(f"\n  Execute: ./{destino}/{NOME_APP}")

        # Remove o .pkg que confunde (artefato do PyInstaller, não é instalador)
        pkg = os.path.join("dist", f"{NOME_APP}.pkg")
        if os.path.exists(pkg):
            os.remove(pkg)
            print(f"\n  (Removido artefato {NOME_APP}.pkg — não é necessário)")

    elif sistema == "Windows":
        for src in DADOS_EXTRAS:
            if os.path.exists(src) and os.path.isdir(dist_app):
                shutil.copy2(src, os.path.join(dist_app, src))

        exe = os.path.join(dist_app, f"{NOME_APP}.exe")
        print(f"\n  Resultado: {exe}")
        print(f"\n  Copie a pasta inteira 'dist/{NOME_APP}/' para o PC de destino.")
        print(f"  Dentro dela, execute {NOME_APP}.exe")

    else:
        print(f"\n  Resultado em: dist/{NOME_APP}/")

    print(f"\n  Os warnings de 'missing module' são normais (módulos opcionais).")
    print(f"  O que importa é se o app abre e funciona corretamente.\n")


if __name__ == "__main__":
    construir()
