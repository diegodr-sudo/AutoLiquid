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

    # Configura download automático sem dialog nativo do SO.
    # O SIAFI baixa o hodcivws.jnlp ao clicar em "Siafi Operacional" — sem
    # esta configuração o Chrome abre o "Salvar Como" nativo e bloqueia a automação.
    _downloads_dir = str(Path.home() / "Downloads")
    _dl_prefs = preferences.setdefault("download", {})
    if (
        _dl_prefs.get("prompt_for_download") is not False
        or _dl_prefs.get("default_directory") != _downloads_dir
    ):
        _dl_prefs["prompt_for_download"] = False
        _dl_prefs["default_directory"] = _downloads_dir
        _dl_prefs["directory_upgrade"] = True
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


def _extrair_codigo_hod(pagina) -> str:
    """Extrai o Código de Acesso HOD exibido no popup do SIAFI Web."""
    try:
        pagina.wait_for_timeout(800)
    except Exception:
        pass

    script = """
    () => {
      const valores = [];
      const push = (v) => {
        const s = String(v || "").trim();
        if (s) valores.push(s);
      };
      const scan = (doc) => {
        if (!doc) return;
        for (const el of doc.querySelectorAll("textarea,input")) {
          push(el.value || el.getAttribute("value") || el.textContent);
        }
        for (const el of doc.querySelectorAll("*")) {
          const text = (el.textContent || "").replace(/\\s+/g, " ").trim();
          if (/C[oó]digo de acesso/i.test(text)) push(text);
        }
      };
      scan(document);
      for (const frame of document.querySelectorAll("iframe")) {
        try { scan(frame.contentDocument); } catch (_) {}
      }
      return valores;
    }
    """
    valores: list[str] = []
    try:
        valores = pagina.evaluate(script) or []
    except Exception:
        valores = []

    for valor in valores:
        match = re.search(r"\b(\d{8,14})\b", str(valor))
        if match:
            return match.group(1)
    return ""


def _fechar_popup_codigo_hod(pagina) -> bool:
    """Fecha o popup do Código HOD no SIAFI Web, quando ele estiver aberto."""
    seletores = [
        "button:has-text('Fechar')",
        "input[type='button'][value='Fechar']",
        "input[type='submit'][value='Fechar']",
        "a:has-text('Fechar')",
        "span.ui-button-text:has-text('Fechar')",
    ]
    for seletor in seletores:
        try:
            alvo = pagina.locator(seletor).first
            alvo.wait_for(state="visible", timeout=1200)
            alvo.click(timeout=2500)
            return True
        except Exception:
            continue

    script = """
    () => {
      const normalizar = (v) => String(v || "").replace(/\\s+/g, " ").trim().toLowerCase();
      const tentar = (doc) => {
        if (!doc) return false;
        const seletores = [
          "button",
          "input[type=button]",
          "input[type=submit]",
          "a",
          "span.ui-button-text"
        ];
        for (const el of doc.querySelectorAll(seletores.join(","))) {
          const texto = normalizar(el.innerText || el.textContent || el.value || el.title);
          if (texto !== "fechar") continue;
          const clicavel = el.closest("button,a") || el;
          clicavel.click();
          return true;
        }
        return false;
      };
      if (tentar(document)) return true;
      for (const frame of document.querySelectorAll("iframe")) {
        try {
          if (tentar(frame.contentDocument)) return true;
        } catch (_) {}
      }
      return false;
    }
    """
    try:
        return bool(pagina.evaluate(script))
    except Exception:
        return False


def _encontrar_pagina_siafi(navegador_cdp) -> tuple[object | None, str]:
    """Busca uma página do SIAFI entre os contextos visíveis ao Playwright."""
    for ctx in navegador_cdp.contexts:
        for pg in ctx.pages:
            if _SIAFI_DOMINIO in (pg.url or ""):
                return pg, pg.url or ""
    return None, ""


def _clicar_siafi_operacional(pagina_siafi) -> bool:
    """Clica no link Siafi Operacional usando seletores tolerantes à tela atual."""
    seletores = [
        "#frmMenu\\:lnkArvoreMenu",
        "a:has-text('Siafi Operacional')",
        "text=Siafi Operacional",
    ]
    for seletor in seletores:
        try:
            link = pagina_siafi.locator(seletor).first
            link.wait_for(state="visible", timeout=3500)
            link.click(timeout=5000)
            return True
        except Exception:
            continue
    return False


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
            pagina_siafi, siafi_url = _encontrar_pagina_siafi(nav_cdp)
            encontrou_target_siafi = False

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
                    encontrou_target_siafi = True
                    siafi_url = siafi_target.get("url", "")
                    _ativar_target_cdp(porta, siafi_target.get("id", ""))
                    _ativar_janela_chrome()
                    if _SIAFI_LOGIN_PATH in siafi_url:
                        return {"action": "login_required", "url": siafi_url}
                    try:
                        nav_cdp.close()
                    except Exception:
                        pass
                    nav_cdp = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
                    try:
                        nav_cdp.contexts[0].pages[0].wait_for_timeout(500)
                    except Exception:
                        pass
                    pagina_siafi, siafi_url_playwright = _encontrar_pagina_siafi(nav_cdp)
                    siafi_url = siafi_url_playwright or siafi_url

            if encontrou_target_siafi and pagina_siafi is None:
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

                codigo_hod = _extrair_codigo_hod(pagina_siafi)
                if codigo_hod:
                    _fechar_popup_codigo_hod(pagina_siafi)
                    return {"action": "tela_preta_clicado", "url": siafi_url, "codigo_acesso": codigo_hod}

                # Logado — clica em "Siafi Operacional"
                try:
                    # Antes de clicar, configura auto-download via CDP para
                    # evitar o dialog nativo "Salvar Como" do macOS/Windows.
                    # Isso não exige nenhuma permissão do sistema operacional.
                    try:
                        _dl_path = str(Path.home() / "Downloads")
                        _cdp = pagina_siafi.context.new_cdp_session(pagina_siafi)
                        _cdp.send("Page.setDownloadBehavior", {
                            "behavior": "allow",
                            "downloadPath": _dl_path,
                        })
                    except Exception:
                        pass

                    if not _clicar_siafi_operacional(pagina_siafi):
                        return {"action": "focused", "url": siafi_url}
                    codigo_hod = _extrair_codigo_hod(pagina_siafi)
                    if codigo_hod:
                        _fechar_popup_codigo_hod(pagina_siafi)
                    return {"action": "tela_preta_clicado", "url": siafi_url, "codigo_acesso": codigo_hod}
                except Exception:
                    return {"action": "focused", "url": siafi_url}

            # Nenhuma aba SIAFI: abre uma janela anônima real do navegador.
            # Contextos anônimos criados pelo Playwright são descartados quando
            # a conexão CDP é encerrada, o que fazia a janela abrir e fechar.
            pronto = abrir_chrome_incognito(url, porta=porta, aguardar=False)
            _ativar_janela_chrome()
            return {"action": "opened", "cdpReady": pronto}
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


# JavaScript executado via CDP para capturar o estado completo da página do governo
_JS_CAPTURAR_ESTADO_PAGINA = r"""
() => {
    const normalizar = (txt) => (txt || '').replace(/\s+/g, ' ').trim();

    // ── Labels associados a um elemento ──────────────────────────────────────
    function labelDe(el) {
        if (el.id) {
            const lbl = document.querySelector('label[for="' + el.id + '"]');
            if (lbl) return normalizar(lbl.textContent);
        }
        const aria = el.getAttribute('aria-label');
        if (aria) return normalizar(aria);
        const lblById = el.getAttribute('aria-labelledby');
        if (lblById) {
            const lbl = document.getElementById(lblById);
            if (lbl) return normalizar(lbl.textContent);
        }
        const parent = el.closest('label');
        if (parent) {
            const clone = parent.cloneNode(true);
            clone.querySelectorAll('input,select,textarea').forEach(n => n.remove());
            return normalizar(clone.textContent);
        }
        // Fallback: texto do elemento anterior no DOM
        let sib = el.previousElementSibling;
        while (sib) {
            const txt = normalizar(sib.textContent);
            if (txt && txt.length < 80) return txt;
            sib = sib.previousElementSibling;
        }
        return el.getAttribute('name') || el.getAttribute('id') || el.getAttribute('placeholder') || el.tagName.toLowerCase();
    }

    // ── Campos de formulário ─────────────────────────────────────────────────
    const campos = {};
    const seletores = 'input:not([type=hidden]):not([type=password]):not([type=submit]):not([type=button]):not([type=image]):not([type=reset]), select, textarea';
    document.querySelectorAll(seletores).forEach(el => {
        const rect = el.getBoundingClientRect();
        const estilo = window.getComputedStyle(el);
        const visivel = rect.width > 0 && rect.height > 0 && estilo.visibility !== 'hidden' && estilo.display !== 'none';
        if (!visivel) return;

        const chave = labelDe(el);
        let valor = '';
        if (el.tagName === 'SELECT') {
            const opt = el.options[el.selectedIndex];
            valor = opt ? (el.value + (opt.text && opt.text !== el.value ? ' (' + opt.text + ')' : '')) : el.value;
        } else {
            valor = el.value;
        }
        if (chave && valor && valor !== '' && !valor.startsWith('__')) {
            campos[chave.slice(0, 80)] = String(valor).slice(0, 300);
        }
    });

    // ── Mensagens de erro / alerta visíveis na página ────────────────────────
    const erros = [];
    document.querySelectorAll('.alert, .alert-danger, .alert-warning, .error, [class*="erro"], [class*="error"], [class*="aviso"], [class*="alert"]').forEach(el => {
        const txt = normalizar(el.textContent);
        if (txt && txt.length > 5 && txt.length < 500) erros.push(txt);
    });

    // ── Título da seção/etapa visível (h1-h4, .box-title, .panel-title) ──────
    const titulos = [];
    document.querySelectorAll('h1, h2, h3, h4, .box-title, .panel-title, .title-item-acordion').forEach(el => {
        const txt = normalizar(el.textContent);
        if (txt && txt.length > 3 && txt.length < 200) titulos.push(txt);
    });

    return JSON.stringify({
        url: window.location.href,
        titulo: document.title,
        titulos_secoes: titulos.slice(0, 8),
        campos_formulario: campos,
        mensagens_erro: erros.slice(0, 10),
        timestamp: new Date().toISOString(),
    });
}
"""


def capturar_estado_aba_chrome(porta: int | None = None) -> dict:
    """Captura URL, título, campos de formulário e mensagens de erro
    da aba ativa do Chrome (preferencialmente a do Comprasnet).

    Retorna um dicionário com as informações ou um dict com 'erro' se falhar.
    """
    import asyncio
    try:
        asyncio.set_event_loop(None)
    except Exception:
        pass

    porta_efetiva = resolver_porta_chrome(porta)
    if not chrome_esta_pronto(porta_efetiva):
        return {"erro": "Chrome não está disponível na porta esperada."}

    try:
        from playwright.sync_api import sync_playwright
        playwright = sync_playwright().start()
        try:
            nav = playwright.chromium.connect_over_cdp(f"http://localhost:{porta_efetiva}")
            # Prioriza aba do Comprasnet; senão, a primeira disponível
            paginas = [p for ctx in nav.contexts for p in ctx.pages]
            dominios_alvo = ("comprasnet", "contratos.gov", "siafi", "sof.planejamento")
            pagina = next(
                (p for p in paginas if any(d in (p.url or "") for d in dominios_alvo)),
                paginas[0] if paginas else None,
            )
            if pagina is None:
                return {"erro": "Nenhuma aba encontrada no navegador."}

            resultado_json = pagina.evaluate(_JS_CAPTURAR_ESTADO_PAGINA)
            resultado = json.loads(resultado_json)
            return resultado
        finally:
            try:
                playwright.stop()
            except Exception:
                pass
    except Exception as exc:
        return {"erro": str(exc)[:300]}
