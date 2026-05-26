"""
comprasnet_base.py
Utilitários compartilhados + mapeamento de situações.
"""
import re
import time

from services.chrome_service import conectar_chrome_cdp

# ─────────────────────────────────────────────────────────────────────────────
# MAPEAMENTO DE SITUAÇÕES
# Defina aqui quais abas cada situação utiliza e seus parâmetros específicos.
# ─────────────────────────────────────────────────────────────────────────────
SITUACOES = {
    # ── Situações numéricas (legado / fallback) ────────────────────────────
    "201": {
        "descricao":         "Material Permanente (Bens Móveis)",
        "contas_a_pagar":    "104",          # → 2.1.3.1.1.04.00
        "usa_deducao":       False,
        "usa_centro_custo":  False,
    },
    "101": {
        "descricao":         "Material de Consumo (Almoxarifado)",
        "contas_a_pagar":    "104",          # → 2.1.3.1.1.04.00
        "usa_deducao":       False,
        "usa_centro_custo":  True,
        "centro_custo_auto": True,
    },
    "102": {
        "descricao":         "Material de Consumo (Entrega Direta)",
        "contas_a_pagar":    "104",          # → 2.1.3.1.1.04.00
        "usa_deducao":       False,
        "usa_centro_custo":  True,
        "centro_custo_auto": True,
    },
    "001": {
        "descricao":         "Serviços de Terceiros (BPV001)",
        "contas_a_pagar":    "104",          # → 2.1.3.1.1.04.00
        "usa_deducao":       True,
        "usa_centro_custo":  False,
    },
    # ── Situações com código SIAFI completo ───────────────────────────────
    "DSP001": {
        "descricao":         "Aquisição de Serviços — Pessoas Jurídicas",
        "contas_a_pagar":    "1104",         # → 2.1.3.1.1.04.00 (digita 1104)
        "usa_deducao":       True,
        "usa_centro_custo":  False,
        "tem_contrato":      True,           # campos Tem Contrato / Conta Contrato / Favorecido
        "conta_contrato":    "02",           # valor padrão para Conta de Contrato
    },
    "BPV001": {
        "descricao":         "Pagamento de Obrigações Liquidadas — CPR",
        "contas_a_pagar":    "104",          # → 2.1.3.1.1.04.00
        "usa_deducao":       True,
        "usa_centro_custo":  False,
        "tem_contrato":      False,
    },
    "DSP101": {
        "descricao":         "Material de Consumo — Almoxarifado (DSP)",
        "contas_a_pagar":    "1104",         # → 2.1.3.1.1.04.00
        "usa_deducao":       False,
        "usa_centro_custo":  True,
        "conta_estoque":     "60100",        # → 1.1.5.6.1.01.00
    },
    "DSP102": {
        "descricao":         "Material de Consumo — Entrega Direta (DSP)",
        "contas_a_pagar":    "1104",         # → 2.1.3.1.1.04.00
        "usa_deducao":       False,
        "usa_centro_custo":  True,
        "conta_estoque":     "60100",        # → 1.1.5.6.1.01.00
    },
    "DSP201": {
        "descricao":         "Material Permanente — Bens Móveis (DSP)",
        "contas_a_pagar":    "1104",         # → 2.1.3.1.1.04.00 (DSP usa 1104, não 104)
        "usa_deducao":       False,
        "usa_centro_custo":  False,
        # Campos para preencher manualmente no SIAFI caso a automação não consiga:
        # IMB050: Conta de Bens Móveis (auto-preenchida pelo portal)
        # IMB050: Contas a Pagar = 2.1.3.1.1.04.00
        # IMB050: VPD = conforme natureza de despesa
    },
}

# Alias: código numérico → código SIAFI completo preferido
# Quando o dropdown tiver múltiplas opções com o mesmo número (ex: BPV001 e DSP001),
# usa este mapa para saber qual selecionar por padrão se o código completo não for
# extraível do PDF.
_PREFERENCIA_SITUACAO = {
    "001": "BPV001",   # fallback numérico → prefer BPV001 se não souber qual dos "001"
}


def extrair_siafi_completo(raw: str) -> str:
    """
    Tenta extrair o código SIAFI completo (ex: 'DSP001', 'BPV001', 'DSP201')
    de uma string que pode conter texto adicional.
    Suporta formatos:
        'DSP001', 'DSP 001', 'BPV001', '001 - DSP001 - Serviços...'
    Retorna o código normalizado SEM espaço (ex: 'DSP001') ou '' se não encontrado.
    """
    upper = raw.upper().strip()
    # Formato colado: DSP001, BPV001
    m = re.search(r'\b([A-Z]{2,4})\s*(\d{3})\b', upper)
    if m:
        return m.group(1) + m.group(2)   # sem espaço
    return ""


def config_situacao(codigo: str):
    """
    Retorna a config da situação.
    Tenta código SIAFI completo primeiro (DSP001), depois numérico (001).
    """
    cod = str(codigo).strip().upper()
    cfg = SITUACOES.get(cod)
    if cfg:
        return cfg
    # Fallback: extrai número e busca
    m = re.search(r"\d+", cod)
    if m:
        cfg = SITUACOES.get(m.group(0))
        if cfg:
            return cfg
    return None


def conectar(porta=None, abrir_se_fechado=True):
    """
    Conecta ao Chrome via CDP.
    Se o Chrome não estiver aberto e abrir_se_fechado=True, abre automaticamente.
    """
    return conectar_chrome_cdp(porta=porta, abrir_se_fechado=abrir_se_fechado)


# ─────────────────────────────────────────────────────────────────────────────
# SELETOR UNIVERSAL
# ─────────────────────────────────────────────────────────────────────────────
JS_ACHAR_INPUT = """
(textoLabel) => {
    // Considera apenas elementos VISÍVEIS (bounding rect > 0) para evitar
    // coletar campos de outras abas/seções que estão ocultas no DOM.
    const visivel = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const inputVisivel = (el) => el && visivel(el) && !el.disabled;
    const q = (r) => {
        if (!r) return null;
        const inp = r.querySelector('input,select,textarea');
        return inputVisivel(inp) ? inp : null;
    };
    const todos = Array.from(document.querySelectorAll('*'));
    for (const el of todos) {
        if (!visivel(el)) continue;
        if (el.textContent.trim() !== textoLabel) continue;
        let inp = q(el.nextElementSibling);
        if (inp) return inp;
        inp = q(el.parentElement?.nextElementSibling);
        if (inp) return inp;
        const avo = el.parentElement?.parentElement;
        if (avo) {
            const f = Array.from(avo.querySelectorAll('input,select,textarea'))
                .filter(inputVisivel);
            if (f.length) return f[0];
        }
    }
    return null;
}
"""

_TIMEOUT_UI_MS = 20000


def _esperar_locator_interagivel(locator, timeout_ms: int = _TIMEOUT_UI_MS):
    locator.wait_for(state="visible", timeout=timeout_ms)
    # Usa polling Python em vez de busy-wait JS (que bloqueava o browser por até 20s)
    deadline = time.time() + min(timeout_ms / 1000, 10.0)
    while time.time() < deadline:
        interagivel = locator.evaluate(
            """(el) => {
                const rect = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0
                    && s.visibility !== 'hidden' && s.display !== 'none'
                    && !el.disabled && !el.readOnly;
            }"""
        )
        if interagivel:
            return locator
        time.sleep(0.15)
    return locator  # devolve mesmo assim; o fill vai tentar


def _ler_valor_locator(locator) -> str:
    try:
        return locator.input_value().strip()
    except Exception:
        try:
            return locator.inner_text().strip()
        except Exception:
            return ""

def achar_elemento(pagina, label):
    h = pagina.evaluate_handle(JS_ACHAR_INPUT, label)
    if not pagina.evaluate("el => el ? el.tagName : null", h):
        raise RuntimeError(f"Campo não encontrado: '{label}'")
    id_  = pagina.evaluate("el => el.id || ''",   h)
    name = pagina.evaluate("el => el.name || ''", h)
    if id_:   return pagina.locator(f"#{id_}")
    if name:  return pagina.locator(f"[name='{name}']")
    todos = pagina.locator("input:visible,select:visible,textarea:visible").all()
    for i, inp in enumerate(todos):
        if pagina.evaluate("(a,b)=>a===b", h, inp.element_handle()):
            return pagina.locator(f"(input:visible,select:visible,textarea:visible)[{i+1}]")
    raise RuntimeError(f"Campo '{label}' não mapeável para Locator.")

def _achar_elemento_resiliente(pagina, label, tentativas: int = 3):
    ultimo_erro = None
    for _ in range(tentativas):
        try:
            return achar_elemento(pagina, label)
        except Exception as exc:
            ultimo_erro = exc
            time.sleep(0.4)
    raise RuntimeError(str(ultimo_erro or f"Campo nÃ£o encontrado: '{label}'"))


def preencher_data(pagina, label, data_ddmmaaaa):
    partes = re.split(r"[/\-]", data_ddmmaaaa.strip())
    if len(partes) != 3:
        raise ValueError(f"Data inválida: '{data_ddmmaaaa}'")
    dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
    esperado = f"{dd}/{mm}/{aaaa}"
    ultimo_erro = None
    for _ in range(3):
        try:
            campo = _esperar_locator_interagivel(_achar_elemento_resiliente(pagina, label))
            campo.click(click_count=3)
            try:
                campo.fill("")
            except Exception:
                pass
            campo.press_sequentially(dd + mm + aaaa, delay=60)
            pagina.keyboard.press("Tab")
            time.sleep(0.4)
            valor_final = normalizar_data(_ler_valor_locator(campo))
            if valor_final == esperado:
                return
            ultimo_erro = RuntimeError(f"campo ficou com '{valor_final or 'vazio'}'")
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.5)
    raise RuntimeError(f"{label}: {ultimo_erro}")

def preencher_texto(pagina, label, valor):
    valor_str = str(valor)
    ultimo_erro = None
    for _ in range(3):
        try:
            campo = _esperar_locator_interagivel(_achar_elemento_resiliente(pagina, label))
            campo.click(click_count=3)
            try:
                campo.fill("")
            except Exception:
                pass
            campo.fill(valor_str)
            pagina.keyboard.press("Tab")
            time.sleep(0.3)
            valor_final = _ler_valor_locator(campo)
            if not valor_str or valor_final == valor_str:
                return
            ultimo_erro = RuntimeError(f"campo ficou com '{valor_final or 'vazio'}'")
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.5)
    raise RuntimeError(f"{label}: {ultimo_erro}")

def selecionar_opcao(pagina, label, contem_texto):
    """
    Seleciona opção de um <select> cujo texto contém 'contem_texto'.
    Estratégia 1: acha o select pelo label e busca a opção via JS.
    Estratégia 2 (fallback): varre todos os <select> visíveis procurando
                              aquele que tenha uma opção com o texto desejado.
    """
    def _achar_valor(handle):
        return pagina.evaluate(
            """([el, txt]) => {
                if (!el) return null;
                const alvo = String(txt || '').trim().toLowerCase();
                const op = Array.from(el.options || []).find((o) =>
                    String(o.text || '').trim().toLowerCase().includes(alvo)
                );
                return op ? op.value : null;
            }""",
            [handle, contem_texto]
        )

    ultimo_erro = None

    # Estratégia 1 — pelo label, com retry e validação do valor final
    for _ in range(4):
        try:
            sel = _esperar_locator_interagivel(_achar_elemento_resiliente(pagina, label, tentativas=4))
            handle = sel.element_handle()
            valor = _achar_valor(handle)
            if valor:
                sel.select_option(value=valor)
                time.sleep(0.3)
                valor_final = sel.input_value().strip()
                if valor_final == str(valor):
                    return valor
                ultimo_erro = RuntimeError(f"select ficou com '{valor_final or 'vazio'}'")
            else:
                ultimo_erro = RuntimeError(f"opção '{contem_texto}' ainda não apareceu no select '{label}'")
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.5)

    # Estratégia 2 — varre todos os selects visíveis e espera opções carregarem
    for _ in range(4):
        try:
            selects = pagina.locator("select:visible").all()
            for sel in selects:
                try:
                    _esperar_locator_interagivel(sel)
                    handle = sel.element_handle()
                    valor = _achar_valor(handle)
                    if not valor:
                        continue
                    sel.select_option(value=valor)
                    time.sleep(0.3)
                    valor_final = sel.input_value().strip()
                    if valor_final == str(valor):
                        return valor
                    ultimo_erro = RuntimeError(f"select genérico ficou com '{valor_final or 'vazio'}'")
                except Exception as exc:
                    ultimo_erro = exc
        except Exception as exc:
            ultimo_erro = exc
        time.sleep(0.5)

    raise RuntimeError(f"{label}: {ultimo_erro or f'Opção {contem_texto!r} não encontrada em nenhum select da página.'}")

def ler_campo_data(pagina, label):
    return normalizar_data(achar_elemento(pagina, label).input_value().strip())

def ler_celula_tabela(pagina, linha, coluna):
    linhas = [l for l in pagina.locator("table tbody tr").all()
              if "TOTAL" not in l.inner_text().upper() and l.inner_text().strip()]
    if linha >= len(linhas): return None
    celulas = linhas[linha].locator("td").all()
    if coluna >= len(celulas): return None
    return celulas[coluna].inner_text().strip()

def normalizar_data(s):
    if not s: return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s.strip())
    if m: return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m2 = re.match(r"(\d{2})-(\d{2})-(\d{4})", s.strip())
    if m2: return f"{m2.group(1)}/{m2.group(2)}/{m2.group(3)}"
    return s.strip()

def normalizar_valor(v):
    if not v: return ""
    s = re.sub(r"\s", "", str(v)).strip()
    if re.search(r",\d{2}$", s):     s = s.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{2}$", s):  s = s.replace(",", "")
    else:                             s = s.replace(".", "").replace(",", "")
    try:    return f"{float(s):.2f}"
    except: return s

def extrair_codigo_situacao(raw):
    m = re.search(r"\d+", raw)
    return m.group(0) if m else raw


# ─────────────────────────────────────────────────────────────────────────────
# NAVEGAÇÃO GENÉRICA DE ABAS
# ─────────────────────────────────────────────────────────────────────────────

def clicar_aba_generica(pagina, texto_aba: str, timeout_ms: int = 8000) -> bool:
    """
    Clica em uma aba do portal pelo texto visível, usando busca JS resiliente.

    Normaliza acentos, espaços e capitalização para localizar qualquer elemento
    clicável (a, button, li, [role=tab]) cujo texto contenha `texto_aba`.

    Retorna True se a aba foi clicada, False caso não encontrada.
    """
    import unicodedata

    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFD", str(s or ""))
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        return s.lower().strip()

    alvo_norm = _norm(texto_aba)

    clicou = pagina.evaluate(
        """(alvo) => {
            const normalizar = (txt) =>
                String(txt || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ')
                    .trim()
                    .toLowerCase();

            const visivel = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0
                    && s.visibility !== 'hidden' && s.display !== 'none'
                    && s.opacity !== '0';
            };

            const candidatos = Array.from(document.querySelectorAll(
                'a, button, [role="tab"], li > a, li > button, .nav-link, .tab-link'
            ));

            // Busca exata primeiro
            let alvo_el = candidatos.find(
                (el) => visivel(el) && normalizar(el.textContent) === alvo
            );

            // Busca por inclusão (alvo dentro do texto do elemento)
            if (!alvo_el) {
                alvo_el = candidatos.find(
                    (el) => visivel(el) && normalizar(el.textContent).includes(alvo)
                );
            }

            // Busca inversa (texto do elemento dentro do alvo — para abreviações)
            if (!alvo_el) {
                alvo_el = candidatos.find((el) => {
                    if (!visivel(el)) return false;
                    const t = normalizar(el.textContent);
                    return t.length >= 4 && alvo.includes(t);
                });
            }

            if (!alvo_el) return false;

            alvo_el.scrollIntoView({ block: 'center', behavior: 'auto' });
            alvo_el.click();
            return true;
        }""",
        alvo_norm,
    )

    return bool(clicou)


def aguardar_aba_ativa(pagina, seletores_conteudo: list[str], timeout_ms: int = 8000) -> bool:
    """
    Aguarda que pelo menos um dos `seletores_conteudo` fique visível na página.
    Útil para confirmar que uma aba abriu corretamente.

    Retorna True se encontrou algum elemento, False se esgotou o timeout.
    """
    import json
    try:
        pagina.wait_for_function(
            """(seletores) => {
                const visivel = (el) => !!el && el.offsetParent !== null && el.getBoundingClientRect().width > 0;
                return seletores.some((sel) => {
                    try { return visivel(document.querySelector(sel)); }
                    catch { return false; }
                });
            }""",
            arg=seletores_conteudo,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False
