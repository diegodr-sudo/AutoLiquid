"""Integração com navegadores (Chrome e Edge) usados pela automação."""

import json
import os
import platform
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.app_paths import DIR_PERFIL, PORTA_CHROME, URL_INICIAL, caminho_recurso
from core.runtime_config import obter_porta_chrome

AUTOLIQUID_EXTRACTOR_BOOKMARK_NAME = "Captar informacoes da pagina"
AUTOLIQUID_EXTRACTOR_BOOKMARK_ALIASES = {
    AUTOLIQUID_EXTRACTOR_BOOKMARK_NAME,
    "AutoLiquid Extrair Pagina",
}
AUTOLIQUID_EXTRACTOR_BOOKMARK_VERSION = "captar-informacoes-v2"


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


def _chrome_timestamp() -> str:
    # Chrome armazena datas como microssegundos desde 1601-01-01 UTC.
    return str(int((time.time() + 11644473600) * 1_000_000))


def _compactar_bookmarklet(source: str) -> str:
    source = source.strip()
    source = re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)
    return " ".join(line.strip() for line in source.splitlines() if line.strip())


def _bookmarklet_extrator_pagina() -> str:
    caminho = caminho_recurso("scripts/browser_page_extractor_bookmarklet.js")
    source = caminho.read_text(encoding="utf-8")
    return "javascript:" + _compactar_bookmarklet(source)


def _novo_no_pasta(nome: str) -> dict:
    agora = _chrome_timestamp()
    return {
        "children": [],
        "date_added": agora,
        "date_last_used": "0",
        "date_modified": agora,
        "guid": "",
        "id": "1",
        "name": nome,
        "type": "folder",
    }


def _proximo_bookmark_id(node: dict) -> int:
    maior = 0
    pilha = [node]
    while pilha:
        atual = pilha.pop()
        try:
            maior = max(maior, int(str(atual.get("id") or "0")))
        except ValueError:
            pass
        pilha.extend(atual.get("children") or [])
        roots = atual.get("roots")
        if isinstance(roots, dict):
            pilha.extend(item for item in roots.values() if isinstance(item, dict))
    return maior + 1


def garantir_bookmarklets_autoliquid() -> tuple[bool, bool]:
    """Garante o bookmarklet de extração no perfil dedicado do navegador.

    Retorna (sucesso, alterado). Quando o perfil já está aberto, alterações no
    arquivo Bookmarks só aparecem depois que o Chrome recarrega o perfil.
    """
    try:
        bookmarklet_url = _bookmarklet_extrator_pagina()
    except Exception:
        return False, False

    perfil = Path(DIR_PERFIL)
    default_dir = perfil / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    bookmarks_path = default_dir / "Bookmarks"

    if bookmarks_path.exists():
        try:
            bookmarks = json.loads(bookmarks_path.read_text(encoding="utf-8"))
        except Exception:
            bookmarks = {}
    else:
        bookmarks = {}

    roots = bookmarks.setdefault("roots", {})
    bookmark_bar = roots.setdefault("bookmark_bar", _novo_no_pasta("Bookmarks bar"))
    roots.setdefault("other", _novo_no_pasta("Other bookmarks"))
    roots.setdefault("synced", _novo_no_pasta("Mobile bookmarks"))
    bookmark_bar.setdefault("children", [])

    children = bookmark_bar["children"]
    changed = False
    bookmark_item = None
    for item in list(children):
        if item.get("name") in AUTOLIQUID_EXTRACTOR_BOOKMARK_ALIASES:
            if bookmark_item is not None:
                children.remove(item)
                changed = True
                continue
            bookmark_item = item
            if item.get("name") != AUTOLIQUID_EXTRACTOR_BOOKMARK_NAME:
                item["name"] = AUTOLIQUID_EXTRACTOR_BOOKMARK_NAME
                item["date_modified"] = _chrome_timestamp()
                changed = True
            if item.get("url") != bookmarklet_url:
                item["url"] = bookmarklet_url
                item["date_modified"] = _chrome_timestamp()
                changed = True
    if bookmark_item is None:
        children.append({
            "date_added": _chrome_timestamp(),
            "date_last_used": "0",
            "guid": "",
            "id": str(_proximo_bookmark_id(bookmarks)),
            "name": AUTOLIQUID_EXTRACTOR_BOOKMARK_NAME,
            "type": "url",
            "url": bookmarklet_url,
        })
        changed = True

    bookmarks.setdefault("version", 1)
    bookmarks.pop("checksum", None)
    if changed or not bookmarks_path.exists():
        bookmarks_path.write_text(json.dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = _garantir_barra_favoritos_visivel() or changed
    return True, changed


def instalar_bookmarklets_autoliquid() -> bool:
    """Compatibilidade: retorna apenas sucesso da garantia do bookmarklet."""
    sucesso, _changed = garantir_bookmarklets_autoliquid()
    return sucesso


def fechar_navegador_automacao(porta=None, timeout_s: float = 5.0) -> bool:
    """Fecha o navegador dedicado da automação via CDP."""
    porta = resolver_porta_chrome(porta)
    if not chrome_esta_pronto(porta):
        return True

    playwright = None
    navegador_cdp = None
    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        navegador_cdp = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        navegador_cdp.close()
    except Exception:
        return False
    finally:
        try:
            if playwright is not None:
                playwright.stop()
        except Exception:
            pass

    limite = time.time() + max(timeout_s, 0.5)
    while time.time() < limite:
        if not chrome_esta_aberto(porta):
            return True
        time.sleep(0.2)
    return not chrome_esta_aberto(porta)


def _garantir_barra_favoritos_visivel() -> bool:
    preferences_path = Path(DIR_PERFIL) / "Default" / "Preferences"
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    if preferences_path.exists():
        try:
            preferences = json.loads(preferences_path.read_text(encoding="utf-8"))
        except Exception:
            preferences = {}
    else:
        preferences = {}
    bookmark_bar = preferences.setdefault("bookmark_bar", {})
    autoliquid = preferences.setdefault("autoliquid", {})
    changed = False
    if bookmark_bar.get("show_on_all_tabs") is not True:
        bookmark_bar["show_on_all_tabs"] = True
        changed = True
    if autoliquid.get("extractor_bookmark_version") != AUTOLIQUID_EXTRACTOR_BOOKMARK_VERSION:
        autoliquid["extractor_bookmark_version"] = AUTOLIQUID_EXTRACTOR_BOOKMARK_VERSION
        changed = True
    if changed:
        preferences_path.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


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
    instalar_bookmarklets_autoliquid()

    args = [
        f"--remote-debugging-port={porta}",
        f"--user-data-dir={DIR_PERFIL}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--show-bookmark-bar",
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


def abrir_chrome_incognito(url: str, porta=None, aguardar: bool = False, timeout_s: float = 10.0) -> bool:
    """Abre uma nova janela anônima do Google Chrome na URL informada.

    Quando ``porta`` é informada, a janela também sobe com CDP ativo. Isso é
    necessário para fluxos que precisam reencontrar/focar a aba depois.
    """
    url = str(url or "").strip()
    if not url:
        raise ValueError("URL inicial não informada.")
    porta_resolvida = resolver_porta_chrome(porta) if porta is not None else None

    sistema = platform.system()
    exe = _resolver_executavel_chrome(sistema)
    instalar_bookmarklets_autoliquid()
    args = [
        f"--user-data-dir={DIR_PERFIL}",
        *([f"--remote-debugging-port={porta_resolvida}"] if porta_resolvida is not None else []),
        "--incognito",
        "--new-window",
        "--show-bookmark-bar",
        url,
    ]
    if sistema == "Darwin":
        cmd = ["open", "-na", exe, "--args", *args]
    else:
        cmd = [exe, *args]

    _spawn_detached(cmd)
    if not aguardar or porta_resolvida is None:
        return True

    limite = time.time() + max(timeout_s, 1.0)
    while time.time() < limite:
        if chrome_esta_pronto(porta_resolvida):
            return True
        time.sleep(0.5)
    return chrome_esta_pronto(porta_resolvida)


_SIAFI_DOMINIO = "siafi.tesouro.gov.br"
_SIAFI_LOGIN_PATH = "login.jsf"


def _listar_targets_cdp(porta: int) -> list[dict]:
    """Lista todas as abas abertas via endpoint HTTP do CDP.

    Inclui contextos incógnito que Playwright pode não expor via contexts[].
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/json/list", timeout=2
        ) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return []


def _ativar_target_cdp(porta: int, target_id: str) -> None:
    """Traz uma aba para frente via endpoint HTTP do CDP."""
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{porta}/json/activate/{target_id}", timeout=2
        )
    except Exception:
        pass


def _ativar_janela_chrome() -> None:
    """Tenta trazer a janela do Chrome para frente no sistema operacional."""
    sistema = platform.system()
    try:
        if sistema == "Darwin":
            subprocess.run(
                ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                capture_output=True,
            )
        elif sistema == "Windows":
            subprocess.run(
                ["powershell", "-Command",
                 "(New-Object -ComObject WScript.Shell).AppActivate('Google Chrome')"],
                capture_output=True,
            )
    except Exception:
        pass


def abrir_ou_focar_siafi(url: str) -> dict:
    """Verifica se já existe uma aba do SIAFI Web.

    Comportamentos:
    - Aba encontrada e logada  → foca, clica 'Siafi Operacional', retorna action='tela_preta_clicado'
    - Aba encontrada no login  → foca, retorna action='login_required'
    - Aba não encontrada       → abre nova janela anônima, retorna action='opened'

    A detecção usa o endpoint HTTP /json/list do CDP para garantir que abas
    incógnito criadas externamente também sejam encontradas.
    """
    porta = obter_porta_chrome()

    if not chrome_esta_pronto(porta):
        pronto = abrir_chrome_incognito(url, porta=porta, aguardar=True, timeout_s=15)
        return {"action": "opened", "cdpReady": pronto}

    try:
        import asyncio
        try:
            asyncio.set_event_loop(None)
        except Exception:
            pass
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            nav_cdp = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")

            # Busca aba SIAFI em todos os contextos existentes
            pagina_siafi = None
            siafi_url = ""
            for ctx in nav_cdp.contexts:
                for pg in ctx.pages:
                    if _SIAFI_DOMINIO in (pg.url or ""):
                        pagina_siafi = pg
                        siafi_url = pg.url
                        break
                if pagina_siafi:
                    break

            # Fallback: verifica via HTTP /json/list (captura abas de
            # processos externos que Playwright pode não enxergar)
            if pagina_siafi is None:
                targets = _listar_targets_cdp(porta)
                siafi_target = next(
                    (t for t in targets
                     if t.get("type") == "page" and _SIAFI_DOMINIO in (t.get("url") or "")),
                    None,
                )
                if siafi_target:
                    siafi_url = siafi_target.get("url", "")
                    _ativar_target_cdp(porta, siafi_target.get("id", ""))
                    _ativar_janela_chrome()
                    if _SIAFI_LOGIN_PATH in siafi_url:
                        return {"action": "login_required", "url": siafi_url}
                    return {"action": "focused", "url": siafi_url}

            if pagina_siafi is not None:
                # Aba encontrada via Playwright — traz para frente
                try:
                    pagina_siafi.bring_to_front()
                except Exception:
                    pass
                _ativar_janela_chrome()

                if _SIAFI_LOGIN_PATH in siafi_url:
                    return {"action": "login_required", "url": siafi_url}

                # Logado — clica em "Siafi Operacional"
                try:
                    link = pagina_siafi.locator(
                        "#frmMenu\\:lnkArvoreMenu, a:text('Siafi Operacional')"
                    ).first
                    link.wait_for(state="visible", timeout=3000)
                    link.click(timeout=5000)
                    return {"action": "tela_preta_clicado", "url": siafi_url}
                except Exception:
                    return {"action": "focused", "url": siafi_url}

            # Nenhuma aba SIAFI — cria contexto incógnito via CDP para que
            # fique acessível em chamadas futuras (sem processo separado).
            ctx_incognito = nav_cdp.new_context()
            nova_pagina = ctx_incognito.new_page()
            nova_pagina.goto(url, timeout=15000, wait_until="domcontentloaded")
            try:
                nova_pagina.bring_to_front()
            except Exception:
                pass
            _ativar_janela_chrome()
            return {"action": "opened"}
        finally:
            try:
                playwright.stop()
            except Exception:
                pass
    except Exception:
        # Se Playwright falhar por qualquer motivo, abre normalmente
        pronto = abrir_chrome_incognito(url, porta=porta, aguardar=True, timeout_s=15)
        return {"action": "opened", "cdpReady": pronto}


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
