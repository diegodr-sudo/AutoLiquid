"""Integração com navegadores (Chrome e Edge) usados pela automação."""

import json
import os
import platform
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.app_paths import DIR_PERFIL, PORTA_CHROME, URL_INICIAL
from core.runtime_config import obter_porta_chrome


def obter_navegador_configurado() -> str:
    """Retorna o navegador configurado ('chrome' ou 'edge')."""
    try:
        from services.config_service import carregar_config_app
        config = carregar_config_app()
        return str(config.get("navegador") or "chrome").lower().strip()
    except Exception:
        return "chrome"


def resolver_porta_chrome(porta=None) -> int:
    if porta is None:
        return obter_porta_chrome()
    try:
        porta_int = int(str(porta).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Porta inválida: {porta!r}") from exc
    if not 1 <= porta_int <= 65535:
        raise ValueError(f"Porta fora do intervalo válido: {porta_int}")
    return porta_int


def chrome_esta_aberto(porta=None):
    porta = resolver_porta_chrome(porta)
    try:
        with socket.create_connection(("localhost", porta), timeout=0.5):
            return True
    except OSError:
        return False


def chrome_cdp_esta_pronto(porta=None, timeout_s: float = 1.5) -> bool:
    porta = resolver_porta_chrome(porta)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/json/version",
            timeout=max(timeout_s, 0.2),
        ) as response:
            if getattr(response, "status", 200) >= 400:
                return False
            payload = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
            return bool(payload.get("Browser") or payload.get("webSocketDebuggerUrl"))
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return False


def chrome_esta_pronto(porta=None, timeout_s: float = 1.5) -> bool:
    return chrome_esta_aberto(porta) and chrome_cdp_esta_pronto(porta, timeout_s=timeout_s)


def _spawn_detached(cmd: list[str]) -> None:
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        # No Windows, start_new_session e creationflags são mutuamente exclusivos.
        # Usar apenas creationflags com DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP.
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
        kwargs["close_fds"] = True
    subprocess.Popen(cmd, **kwargs)


def _resolver_executavel_chrome(sistema: str) -> str:
    """Retorna o executável do Google Chrome conforme o sistema operacional."""
    if sistema == "Darwin":
        return "Google Chrome"  # usado via 'open -na'
    if sistema == "Windows":
        candidatos = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
        ]
        return next((c for c in candidatos if Path(c).exists()), "chrome.exe")
    # Linux
    for candidato in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
        if subprocess.run(["which", candidato], capture_output=True).returncode == 0:
            return candidato
    return "google-chrome"


def _resolver_executavel_edge(sistema: str) -> str:
    """Retorna o executável do Microsoft Edge conforme o sistema operacional."""
    if sistema == "Darwin":
        return "Microsoft Edge"  # usado via 'open -na'
    if sistema == "Windows":
        candidatos = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            str(Path.home() / "AppData/Local/Microsoft/Edge/Application/msedge.exe"),
        ]
        return next((c for c in candidatos if Path(c).exists()), "msedge.exe")
    # Linux
    for candidato in ("microsoft-edge", "microsoft-edge-stable", "msedge"):
        if subprocess.run(["which", candidato], capture_output=True).returncode == 0:
            return candidato
    return "microsoft-edge"


def abrir_chrome(
    porta=None,
    aguardar=False,
    timeout_s=10,
    navegador: str | None = None,
    oculto: bool = False,
    url_inicial: str | None = None,
):
    """
    Abre o navegador configurado (Chrome ou Edge) com depuração remota ativa.

    Parâmetros
    ----------
    porta : int, opcional
        Porta de depuração remota. Usa a configurada se omitida.
    aguardar : bool
        Se True, aguarda o navegador responder na porta antes de retornar.
    timeout_s : int
        Tempo máximo de espera (segundos) quando aguardar=True.
    navegador : str, opcional
        'chrome' ou 'edge'. Se omitido, usa a configuração salva.
    oculto : bool
        No macOS, abre o aplicativo sem ativar a janela. Útil para automações
        de apoio que não devem roubar o foco do usuário.
    url_inicial : str, opcional
        URL aberta na inicialização. Se omitida, usa a URL padrão do app.
    """
    porta = resolver_porta_chrome(porta)
    if navegador is None:
        navegador = obter_navegador_configurado()

    args = [
        f"--remote-debugging-port={porta}",
        f"--user-data-dir={DIR_PERFIL}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        url_inicial or URL_INICIAL,
    ]

    sistema = platform.system()

    if navegador == "edge":
        if sistema == "Darwin":
            exe = _resolver_executavel_edge(sistema)
            cmd = ["open", "-j", "-na", exe, "--args", *args] if oculto else ["open", "-na", exe, "--args", *args]
        else:
            exe = _resolver_executavel_edge(sistema)
            cmd = [exe, *args]
    else:
        # Chrome (padrão)
        if sistema == "Darwin":
            exe = _resolver_executavel_chrome(sistema)
            cmd = ["open", "-j", "-na", exe, "--args", *args] if oculto else ["open", "-na", exe, "--args", *args]
        else:
            exe = _resolver_executavel_chrome(sistema)
            cmd = [exe, *args]

    _spawn_detached(cmd)

    if aguardar:
        limite = time.time() + max(timeout_s, 1)
        while time.time() < limite:
            if chrome_esta_pronto(porta):
                return porta
            time.sleep(0.5)
        nav_nome = "Edge" if navegador == "edge" else "Chrome"
        raise RuntimeError(
            f"{nav_nome} não ficou pronto para automação na porta {porta} após {timeout_s} segundos."
        )
    return porta


def abrir_chrome_incognito(url: str) -> None:
    """Abre uma nova janela anônima do Google Chrome na URL informada."""
    url = str(url or "").strip()
    if not url:
        raise ValueError("URL inicial não informada.")

    sistema = platform.system()
    exe = _resolver_executavel_chrome(sistema)
    args = ["--incognito", "--new-window", url]
    if sistema == "Darwin":
        cmd = ["open", "-na", exe, "--args", *args]
    else:
        cmd = [exe, *args]

    _spawn_detached(cmd)


def conectar_chrome_cdp(porta=None, abrir_se_fechado=True):
    import asyncio
    from playwright.sync_api import sync_playwright

    # Garante que esta thread não tem um loop asyncio ativo, evitando o erro:
    # "It looks like you are using Playwright Sync API inside the asyncio loop."
    # Quando o FastAPI roda endpoints síncronos via run_in_executor, a thread
    # herdada pode detectar o loop do uvicorn. Desvincular aqui resolve isso.
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass

    porta = resolver_porta_chrome(porta)
    if not chrome_esta_pronto(porta):
        if abrir_se_fechado:
            abrir_chrome(porta, aguardar=True)
        else:
            navegador = obter_navegador_configurado()
            nav_nome = "Edge" if navegador == "edge" else "Chrome"
            raise RuntimeError(
                f"{nav_nome} não está aberto na porta {porta}.\n"
                "Abra o navegador pelas Configurações antes de executar."
            )

    playwright = sync_playwright().start()
    navegador_cdp = playwright.chromium.connect_over_cdp(f"http://localhost:{porta}")

    # Tenta encontrar a aba do Comprasnet/contratos aberta no navegador.
    # Se não encontrar, usa a primeira aba disponível.
    todas_paginas = navegador_cdp.contexts[0].pages
    _dominios_alvo = ("comprasnet", "contratos.gov")
    pagina = next(
        (p for p in todas_paginas if any(d in p.url for d in _dominios_alvo)),
        todas_paginas[0] if todas_paginas else None,
    )
    if pagina is None:
        raise RuntimeError(
            "Nenhuma aba encontrada no navegador. "
            "Abra a página do Comprasnet antes de executar."
        )

    return playwright, pagina
