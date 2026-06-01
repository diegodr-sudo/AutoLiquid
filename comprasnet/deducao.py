"""
comprasnet_deducao.py
Preenche a aba DeduÃ§Ã£o — DDR001 (ISS): um lanÃ§amento por Nota Fiscal.

Estrutura de IDs no Contratos.gov.br (descoberta por inspeÃ§Ã£o):
  sfdeducaocodsit{did}          — select SituaÃ§Ã£o
  sfdeducaodtvenc{did}          — Data de Vencimento
  sfdeducaodtpgtoreceb{did}     — Data de Pagamento
  sfdeducaovlr{did}             — Valor do Item
  txtinscra{did}                — CÃ³digo do MunicÃ­pio  (dispara AJAX â†’ popula select)
  municipioDeducao{did}         — select MunicÃ­pio     (Select2)
  txtinscrb{did}                — CÃ³digo de Receita
  sfdeducaopossui_acrescimo{did}— select Possui AcrÃ©scimo
  recolhedor{did}{rid}          — CNPJ do recolhedor   (auto-criado na linha 1)
  vlrPrincipal{did}{rid}        — Valor da Receita     (auto-criado na linha 1)
  novo-recolhedor{did}          — link "+" para novo recolhedor (nÃ£o usado — 1 por deduÃ§Ã£o)

did = sufixo numÃ©rico da deduÃ§Ã£o  (ex: 884228)
rid = sufixo numÃ©rico do recolhedor (ex: 976052)
"""
import re
import time
import logging
import unicodedata
from comprasnet.base import (
    conectar, config_situacao, extrair_codigo_situacao,
    normalizar_valor, extrair_siafi_completo,
)
from core.datas_impostos import calcular_datas

log = logging.getLogger(__name__)


class ExecucaoInterrompida(Exception):
    """InterrupÃ§Ã£o cooperativa da etapa atual."""


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# CONSTANTES
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

_MUNICIPIO_NOME = {
    "8105": "Florianópolis",
    "8047": "Blumenau",
    "8179": "Joinville",
    "8093": "Curitibanos",
    "8027": "Araranguá",
    "5549": "Barra do Sul",
    "8465": "Gov. Celso Ramos",
    "8327": "São José",
}

_MUNICIPIO_COD_RECEITA = {
    "8105": "1111",
    "8047": "0031",
}

_DOB001_TIPO_OB = {
    "8027": "OB Fatura",
    "8093": "OB Fatura",
    "8179": "OB Crédito",
    "5549": "OB Fatura",
    "8465": "OB Fatura",
}

_CODIGOS_DDR001 = {"8105", "8047"}
_CODIGOS_DOB001 = set(_DOB001_TIPO_OB.keys()) | {"8327"}

_DOB001_FAVORECIDO = {
    "OB Fatura": {
        "cnpj": "00000000000191",
        "banco_favorecido": "001",
        "agencia_favorecido": "3582",
        "conta_favorecido": "FATURA",
    },
    "OB Crédito": {
        "cnpj": "83169623000110",
        "banco_favorecido": "001",
        "agencia_favorecido": "3155",
        "conta_favorecido": "17001145",
    },
}

_UG_TOMADORA = "153163"
_COD_MUN_DEFAULT = "8105"   # FlorianÃ³polis


def _get_any(dados: dict, *chaves: str, default=""):
    for chave in chaves:
        if chave in dados:
            valor = dados.get(chave)
            if valor is not None:
                return valor
    return default


def _ded_codigo(ded: dict) -> str:
    return str(_get_any(ded, "Código", "CÃ³digo", default="") or "").strip()


def _ded_base_calculo(ded: dict) -> str:
    return str(_get_any(ded, "Base Cálculo", "Base CÃ¡lculo", default="0") or "0").strip()


def _ded_valor(ded: dict) -> str:
    return str(_get_any(ded, "Valor", default="0") or "0").strip()


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# HELPERS GERAIS
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def _formatar_cnpj(cnpj: str) -> str:
    d = re.sub(r'\D', '', str(cnpj))
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return cnpj


def _formatar_valor_br(valor_str: str) -> str:
    """Converte para formato BR com ponto como milhar e vÃ­rgula como decimal."""
    try:
        v = float(normalizar_valor(str(valor_str)))
        # Ex: 1234.56 â†’ "1.234,56"
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor_str)


def _normalizar_data(data_str: str) -> str:
    """DD-MM-YYYY ou DD/MM/YYYY â†’ DD/MM/YYYY."""
    if not data_str:
        return ""
    m = re.match(r"(\d{2})[-/](\d{2})[-/](\d{4})", data_str.strip())
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else data_str


def _referencia(data_emissao: str) -> str:
    """DD-MM-YYYY â†’ MM/YYYY."""
    if not data_emissao:
        return ""
    m = re.match(r"\d{2}[-/](\d{2})[-/](\d{4})", data_emissao.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def _codigo_municipio_deducao(ded: dict) -> str:
    codigo_raw = _ded_codigo(ded)
    if codigo_raw in ("—", "", "0"):
        return _COD_MUN_DEFAULT
    return codigo_raw.zfill(4)


def _nf_mais_antiga(notas: list) -> dict:
    if not notas:
        return {}
    from datetime import datetime
    def _dt(nf):
        for fmt in ('%d-%m-%Y', '%d/%m/%Y'):
            try:
                return datetime.strptime(nf.get('Data de EmissÃ£o', '').strip(), fmt)
            except ValueError:
                pass
        return datetime.max
    return min(notas, key=_dt)


def _get_nf_num(nf: dict) -> str:
    """Retorna o numero da NF independente do encoding da chave."""
    return (
        nf.get('Número da Nota')
        or nf.get('N\u00famero da Nota')
        or nf.get('NÃºmero da Nota')
        or ''
    ).strip()


def _get_dados_str(dados: dict, *chaves_utf8: str) -> str:
    """Busca valor em dados tentando chave UTF-8 correta e versao garbled."""
    for chave in chaves_utf8:
        v = dados.get(chave)
        if v is not None:
            return str(v).strip()
        # tenta versão garbled: re-encode UTF-8 como Latin-1
        try:
            chave_garbled = chave.encode('utf-8').decode('latin-1')
            v = dados.get(chave_garbled)
            if v is not None:
                return str(v).strip()
        except Exception:
            pass
    return ''


def _montar_observacao(dados: dict, cod_mun: str) -> str:
    notas        = dados.get('Notas Fiscais', [])
    nums         = [_get_nf_num(n) for n in notas if _get_nf_num(n)]
    tipos        = [n.get('Tipo', '').upper() for n in notas]
    tem_fatura   = any('FATURA' in t for t in tipos)
    tipo_doc     = ("Fatura" if tem_fatura else "NF") if len(nums) == 1 else \
                   ("Faturas" if tem_fatura else "NFs")
    nums_str     = ', '.join(nums) if nums else '\u2014'
    sol          = _get_dados_str(dados, 'Solicitação de Pagamento')
    tem_contrato = _get_dados_str(dados, 'Tem Contrato') or 'Não'
    num_contrato = _get_dados_str(dados, 'Número do Contrato')
    cnpj         = _formatar_cnpj(dados.get('CNPJ', ''))
    cidade       = _MUNICIPIO_NOME.get(str(cod_mun), str(cod_mun))
    partes = [f"Pagamento {tipo_doc} {nums_str}"]
    if tem_contrato == 'Sim' and num_contrato:
        partes.append(f"Contrato {num_contrato}")
    if sol:
        partes.append(f"Solicitação Pagamento {sol}")
    partes.append(f"ISS {cidade} CNPJ {cnpj}")
    return ' - '.join(partes) + '.'


def _montar_observacao_darf(dados: dict, sufixo_normativo: str) -> str:
    notas        = dados.get('Notas Fiscais', [])
    nums         = [_get_nf_num(n) for n in notas if _get_nf_num(n)]
    tipos        = [n.get('Tipo', '').upper() for n in notas]
    tem_fatura   = any('FATURA' in t for t in tipos)
    tipo_doc     = ("Fatura" if tem_fatura else "NF") if len(nums) == 1 else \
                   ("Faturas" if tem_fatura else "NFs")
    nums_str     = ', '.join(nums) if nums else '\u2014'
    sol          = _get_dados_str(dados, 'Solicitação de Pagamento')
    tem_contrato = _get_dados_str(dados, 'Tem Contrato') or 'Não'
    num_contrato = _get_dados_str(dados, 'Número do Contrato')
    partes = [f"Pagamento {tipo_doc} {nums_str}"]
    if tem_contrato == 'Sim' and num_contrato:
        partes.append(f"Contrato {num_contrato}")
    if sol:
        partes.append(f"Solicitação Pagamento {sol}")
    partes.append(sufixo_normativo)
    return ' - '.join(partes) + '.'


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# HELPERS DE CAMPO (por ID exato)
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def _js_set(pagina, fid: str, valor: str) -> bool:
    """Pure JS field setter — zero UI interaction, no sleep."""
    try:
        return bool(pagina.evaluate(
            """([id, val]) => {
                const el = document.getElementById(id);
                if (!el) return false;
                const tag = el.tagName.toLowerCase();
                const proto = tag === 'textarea' ? HTMLTextAreaElement : HTMLInputElement;
                const setter = Object.getOwnPropertyDescriptor(proto.prototype, 'value')?.set;
                el.focus();
                if (setter) setter.call(el, val); else el.value = val;
                el.defaultValue = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
                return true;
            }""",
            [fid, str(valor)],
        ))
    except Exception:
        return False


def _batch_fill(pagina, campos: dict, container_id: str = "") -> None:
    """Fills multiple fields in one JS round-trip. campos = {fieldId: value}."""
    pagina.evaluate(
        """([campos, containerId]) => {
            const setter_i = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
            const setter_t = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
            for (const [id, val] of Object.entries(campos)) {
                const el = document.getElementById(id);
                if (!el) continue;
                const tag = el.tagName.toLowerCase();
                if (tag === 'select') {
                    const norm = s => String(s||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().trim();
                    const target = norm(String(val || ''));
                    const op = Array.from(el.options).find(o =>
                        norm(o.text) === target || norm(o.value) === target || norm(o.text).includes(target)
                    );
                    if (op) el.value = op.value;
                } else {
                    const setter = tag === 'textarea' ? setter_t : setter_i;
                    el.focus();
                    if (setter) setter.call(el, val); else el.value = val;
                    el.defaultValue = val;
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
            }
        }""",
        [campos, container_id],
    )


def _fill(pagina, fid: str, valor: str, erros: list, label: str = ""):
    """Preenche input/textarea pelo id exato via JS setter; fallback para locator."""
    try:
        if _js_set(pagina, fid, str(valor)):
            return
        # fallback: interação UI
        loc = pagina.locator(f"#{fid}")
        loc.wait_for(state="visible", timeout=5000)
        loc.click(click_count=3)
        loc.fill(str(valor))
        pagina.keyboard.press("Tab")
    except Exception as e:
        erros.append(f"{label or fid}: {e}")


def _fill_money(pagina, fid: str, valor: str, erros: list, label: str = ""):
    """Preenche campo monetário mascarado e valida o valor final normalizado."""
    try:
        esperado = normalizar_valor(str(valor))

        # ── Estratégia 1: JS setter (sem UI, sem sleep) ──────────────────────
        if _js_set(pagina, fid, str(valor)):
            atual = normalizar_valor(_read_input_value(pagina, fid))
            if atual == esperado:
                return True

        # ── Estratégia 2: press_sequentially (campo mascarado) ───────────────
        loc = pagina.locator(f"#{fid}")
        loc.wait_for(state="visible", timeout=5000)
        try:
            loc.click(click_count=3)
            try:
                loc.fill("")
            except Exception:
                pass
            loc.press_sequentially(str(valor), delay=80)
            pagina.keyboard.press("Tab")
            # Poll DOM em vez de sleep fixo
            try:
                pagina.wait_for_function(
                    """(id) => {
                        const el = document.getElementById(id);
                        return !!el && String(el.value || '').replace(/[^0-9]/g, '').length > 0;
                    }""",
                    fid,
                    timeout=2000,
                )
            except Exception:
                pass
            atual = normalizar_valor(_read_input_value(pagina, fid))
            if atual == esperado:
                return True
        except Exception:
            pass

        # ── Estratégia 3: JS setter com setAttribute (campos antigos) ────────
        ok = loc.evaluate(
            """(el, valorBr) => {
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                el.focus();
                if (setter) { setter.call(el, valorBr); } else { el.value = valorBr; }
                el.defaultValue = valorBr;
                el.setAttribute('value', valorBr);
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('keyup', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
                return String(el.value || '').trim();
            }""",
            str(valor),
        )
        atual = normalizar_valor(_read_input_value(pagina, fid) or ok)
        if atual == esperado:
            return True

        raise RuntimeError(
            f"campo ficou com '{_read_input_value(pagina, fid) or 'vazio'}' após tentar preencher '{valor}'"
        )
    except Exception as e:
        erros.append(f"{label or fid}: {e}")
        return False


def _fill_date(pagina, fid: str, data_ddmmaaaa: str, erros: list, label: str = ""):
    """
    Preenche um campo de data — suporta <input type='date'> (valor interno ISO)
    e <input type='text'> com máscara DD/MM/AAAA.

    Estratégias (ordem):
    1. ISO setter via loc.evaluate() + time.sleep(0.35) — igual ao Dados Básicos.
       Browsers rejeitam valor BR ('DD/MM/AAAA') em type='date' silenciosamente.
    2. Digitar dígitos DDMMAAAA (sem barras) + Tab + sleep — igual ao preencher_data
       do base.py; o date picker formata automaticamente.
    3. ISO setter novamente (recuperação após a digitação ter corrompido o valor).
    """
    try:
        partes = re.split(r"[/\-]", data_ddmmaaaa.strip())
        if len(partes) != 3:
            raise ValueError(f"Data inválida: '{data_ddmmaaaa}'")
        dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
        iso = f"{aaaa}-{mm}-{dd}"
        br  = f"{dd}/{mm}/{aaaa}"
        digitos = dd + mm + aaaa  # DDMMAAAA sem separadores

        loc = pagina.locator(f"#{fid}")
        loc.wait_for(state="visible", timeout=5000)
        loc.scroll_into_view_if_needed()
        loc.click()

        # ── Estratégia 0: Playwright native fill (suporte nativo a type="date") ─
        try:
            loc.fill(iso)
            time.sleep(0.2)
            val = (loc.input_value() or "").strip()
            if val in (iso, br):
                return
        except Exception:
            pass

        def _iso_setter() -> str:
            resultado = loc.evaluate(
                """(el, valorIso) => {
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    el.focus();
                    if (setter) { setter.call(el, valorIso); } else { el.value = valorIso; }
                    el.setAttribute('value', valorIso);
                    el.defaultValue = valorIso;
                    el.dispatchEvent(new Event('input',  { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
                    return String(el.value || '').trim();
                }""",
                iso,
            )
            time.sleep(0.35)  # browser precisa de tempo para processar type="date"
            return (loc.input_value() or resultado or "").strip()

        # ── Estratégia 1: ISO setter (correto para type="date") ─────────────
        val = _iso_setter()
        if val in (iso, br):
            return

        # ── Estratégia 2: digitar DDMMAAAA sem barras + Tab (como preencher_data) ──
        try:
            loc.click(click_count=3)
            try:
                loc.fill("")
            except Exception:
                pass
            loc.press_sequentially(digitos, delay=60)
            pagina.keyboard.press("Tab")
            time.sleep(0.4)
            val = (loc.input_value() or _read_input_value(pagina, fid) or "").strip()
            if val in (iso, br):
                return
        except Exception:
            pass

        # ── Estratégia 3: ISO setter novamente após tentativa de digitação ───
        val = _iso_setter()
        if val in (iso, br):
            return

        raise RuntimeError(
            f"campo permaneceu com '{val or 'vazio'}' após tentar preencher '{iso}'"
        )

    except Exception as e:
        erros.append(f"{label or fid}: {e}")


def _fill_date_silente(pagina, fid: str, data_ddmmaaaa: str, erros: list, label: str = ""):
    """
    Preenche campo de data com suporte completo a type='date' E type='text' com jQuery inputmask.

    PROBLEMA RAIZ IDENTIFICADO:
    - O portal usa type="text" com jQuery inputmask (placeholder "dd/mm/aaaa" em português)
    - Passar formato ISO ("2026-05-20") em qualquer método falha pois a máscara rejeita
    - A solução é detectar o tipo e usar o formato correto: BR para text, ISO para date

    Estratégias (em cascata):
    A. jQuery inputmask.setvalue() com formato BR — API oficial do plugin
    B. loc.fill(br) para type=text, loc.fill(iso) para type=date
    C. Setter nativo (prototype) com formato correto para o tipo
    D. Keyboard: click → Ctrl+A → Delete → press_sequentially(dígitos) + Tab
    E. Keyboard com barras explícitas: press_sequentially(br) + Tab
    F. Setter silente final como último recurso
    """
    try:
        partes = re.split(r"[/\-]", str(data_ddmmaaaa).strip())
        if len(partes) != 3:
            raise ValueError(f"Data inválida: '{data_ddmmaaaa}'")
        if len(partes[0]) == 4:
            aaaa, mm, dd = partes[0], partes[1].zfill(2), partes[2].zfill(2)
        else:
            dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
        iso     = f"{aaaa}-{mm}-{dd}"          # AAAA-MM-DD  (para type="date")
        br      = f"{dd}/{mm}/{aaaa}"           # DD/MM/AAAA  (para type="text" com máscara)
        digitos = dd + mm + aaaa               # DDMMAAAA    (para press_sequentially)
        lbl     = label or fid

        def _leitura() -> str:
            try:
                return (pagina.evaluate(
                    """(id) => {
                        const el = document.getElementById(id);
                        if (!el) return '';
                        return String(el.value || '').trim();
                    }""",
                    fid,
                ) or "").strip()
            except Exception:
                return ""

        def _tipo_campo() -> str:
            try:
                return (pagina.evaluate(
                    "(id) => { const el = document.getElementById(id); return el ? el.type : 'unknown'; }",
                    fid,
                ) or "text").lower()
            except Exception:
                return "text"

        loc = pagina.locator(f"#{fid}")

        # Aguarda visibilidade antes de qualquer tentativa
        try:
            loc.wait_for(state="visible", timeout=5000)
        except Exception:
            erros.append(f"{lbl}: campo não ficou visível em 5s")
            return

        tipo = _tipo_campo()
        print(f"      [{lbl}] type={tipo!r} | alvo BR={br!r} | iso={iso!r}")

        # ── Estratégia A: jQuery inputmask.setvalue() — API oficial ──────────
        # Funciona com RobinHerbots/Inputmask; dispara handlers internos corretos
        res_a = pagina.evaluate(
            """([id, valBr]) => {
                const el = document.getElementById(id);
                if (!el) return 'NOT_FOUND';
                try {
                    // Forma 1: API objeto inputmask no elemento (versão >= 5.x)
                    if (el.inputmask && typeof el.inputmask.setValue === 'function') {
                        el.inputmask.setValue(valBr);
                        return 'A1:' + el.value;
                    }
                    // Forma 2: jQuery plugin method (versão 3.x/4.x)
                    if (window.$ && $(el).inputmask) {
                        $(el).inputmask('setvalue', valBr);
                        return 'A2:' + el.value;
                    }
                    // Forma 3: trigger 'setvalue' no jQuery
                    if (window.$) {
                        $(el).trigger('setvalue', [valBr]);
                        return 'A3:' + el.value;
                    }
                    return 'A_NO_JQUERY';
                } catch (e) {
                    return 'A_ERR:' + e.message;
                }
            }""",
            [fid, br],
        ) or "A_EVAL_ERR"
        print(f"      [{lbl}] Estratégia A: {res_a}")
        time.sleep(0.3)
        if _leitura() in (iso, br):
            print(f"      [{lbl}] ✓ preenchido via Estratégia A (inputmask.setvalue)")
            return

        # ── Estratégia B: loc.fill() com formato correto para o tipo ─────────
        # type="text" com máscara jQuery: fill(br) — aceita "DD/MM/AAAA" diretamente
        # type="date": fill(iso) — Playwright usa API nativa do browser
        fill_val = br if tipo == "text" else iso
        try:
            loc.fill(fill_val)
            time.sleep(0.3)
            val_b = _leitura()
            if val_b in (iso, br):
                print(f"      [{lbl}] ✓ preenchido via Estratégia B fill({fill_val!r})")
                return
            print(f"      [{lbl}] Estratégia B fill({fill_val!r}) → leitura='{val_b}'")
        except Exception as e_b:
            print(f"      [{lbl}] Estratégia B erro: {e_b}")

        # Tenta o outro formato (fallback)
        fill_val2 = iso if fill_val == br else br
        try:
            loc.fill(fill_val2)
            time.sleep(0.3)
            val_b2 = _leitura()
            if val_b2 in (iso, br):
                print(f"      [{lbl}] ✓ preenchido via Estratégia B2 fill({fill_val2!r})")
                return
            print(f"      [{lbl}] Estratégia B2 fill({fill_val2!r}) → leitura='{val_b2}'")
        except Exception:
            pass

        # ── Estratégia C: setter nativo (prototype) com formato correto ───────
        # Bypassa o setter patched do jQuery inputmask
        # Para type="text": usa BR; para type="date": usa ISO + valueAsDate
        res_c = pagina.evaluate(
            """([id, iso, br, tipo]) => {
                const el = document.getElementById(id);
                if (!el) return 'NOT_FOUND';
                const valToSet = (tipo === 'date' || tipo === 'datetime-local') ? iso : br;
                // Aplica valueAsDate para type="date" (API nativa do Firefox)
                if (tipo === 'date' || tipo === 'datetime-local') {
                    const [y, m, d] = iso.split('-').map(Number);
                    try { el.valueAsDate = new Date(Date.UTC(y, m - 1, d)); } catch(e) {}
                }
                // Setter da prototype (bypassa jQuery inputmask)
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, valToSet); else el.value = valToSet;
                el.defaultValue = valToSet;
                el.setAttribute('value', valToSet);
                const rawGetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.get;
                const rawVal = rawGetter ? rawGetter.call(el) : el.value;
                return 'C:tipo=' + el.type + ':set=' + valToSet + ':raw=' + rawVal + ':el.value=' + el.value;
            }""",
            [fid, iso, br, tipo],
        ) or "C_EVAL_ERR"
        print(f"      [{lbl}] Estratégia C: {res_c}")
        time.sleep(0.25)
        if _leitura() in (iso, br):
            print(f"      [{lbl}] ✓ preenchido via Estratégia C (setter nativo)")
            return

        # ── Estratégia D: keyboard simulation — dígitos apenas ───────────────
        # jQuery inputmask: ao receber keydown/keypress/keyup, insere dígito na posição
        # correta e avança o cursor. As barras "/" são inseridas automaticamente.
        # IMPORTANTE: Ctrl+A → Delete limpa sem quebrar o estado interno da máscara.
        try:
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.15)
            pagina.keyboard.press("Control+a")
            time.sleep(0.1)
            pagina.keyboard.press("Delete")
            time.sleep(0.15)
            loc.press_sequentially(digitos, delay=90)
            pagina.keyboard.press("Tab")
            time.sleep(0.5)
            val_d = _leitura()
            if val_d in (iso, br):
                print(f"      [{lbl}] ✓ preenchido via Estratégia D (dígitos+Tab)")
                return
            print(f"      [{lbl}] Estratégia D dígitos → leitura='{val_d}'")
        except Exception as e_d:
            print(f"      [{lbl}] Estratégia D erro: {e_d}")

        # ── Estratégia E: keyboard com barras explícitas (DD/MM/AAAA) ─────────
        # Alguns campos type="text" sem máscara precisam das barras digitadas
        try:
            loc.scroll_into_view_if_needed()
            loc.click()
            time.sleep(0.15)
            pagina.keyboard.press("Control+a")
            time.sleep(0.1)
            pagina.keyboard.press("Delete")
            time.sleep(0.15)
            loc.press_sequentially(br, delay=90)
            pagina.keyboard.press("Tab")
            time.sleep(0.5)
            val_e = _leitura()
            if val_e in (iso, br):
                print(f"      [{lbl}] ✓ preenchido via Estratégia E (br+Tab)")
                return
            print(f"      [{lbl}] Estratégia E br → leitura='{val_e}'")
        except Exception as e_e:
            print(f"      [{lbl}] Estratégia E erro: {e_e}")

        # ── Estratégia F: setter silente final ────────────────────────────────
        # Última tentativa: força o valor sem eventos (para evitar reset por AJAX)
        res_f = pagina.evaluate(
            """([id, iso, br, tipo]) => {
                const el = document.getElementById(id);
                if (!el) return 'NOT_FOUND';
                const valToSet = (tipo === 'date' || tipo === 'datetime-local') ? iso : br;
                if (tipo === 'date' || tipo === 'datetime-local') {
                    const [y, m, d] = iso.split('-').map(Number);
                    try { el.valueAsDate = new Date(Date.UTC(y, m - 1, d)); } catch(e) {}
                }
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, valToSet); else el.value = valToSet;
                el.defaultValue = valToSet;
                el.setAttribute('value', valToSet);
                return 'F:' + el.type + ':' + el.value;
            }""",
            [fid, iso, br, tipo],
        ) or "F_EVAL_ERR"
        time.sleep(0.25)
        val_final = _leitura()
        print(f"      [{lbl}] Estratégia F: {res_f} → leitura='{val_final}'")

        if val_final not in (iso, br):
            erros.append(
                f"{lbl}: campo ficou '{val_final or 'vazio'}' após todas as estratégias "
                f"(esperado '{iso}' ou '{br}') | tipo={tipo!r}"
            )

    except Exception as e:
        erros.append(f"{label or fid}: {e}")


def _fill_if_different(pagina, fid: str, valor: str, erros: list, label: str = ""):
    atual = _read_input_value(pagina, fid)
    if str(atual).strip() == str(valor).strip():
        return
    _fill(pagina, fid, valor, erros, label)


def _normalizar_texto(texto: str) -> str:
    base = unicodedata.normalize("NFD", str(texto or ""))
    sem_acentos = "".join(ch for ch in base if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", sem_acentos).strip().lower()


def _codigo_municipio_por_nome(nome: str, default: str = "") -> str:
    alvo = _normalizar_texto(nome)
    if not alvo:
        return str(default or "").strip()
    for codigo, nome_mapa in _MUNICIPIO_NOME.items():
        nome_norm = _normalizar_texto(nome_mapa)
        if alvo == nome_norm or alvo in nome_norm or nome_norm in alvo:
            return codigo
    return str(default or "").strip()


def _preencher_municipio_por_codigo(
    pagina,
    fid_codigo: str,
    fid_select: str,
    codigo: str,
    nome: str,
    did: str,
    alvo_busca: str,
    erros: list,
    label: str = "",
) -> bool:
    codigo = str(codigo or "").strip()
    nome = str(nome or "").strip()
    if not codigo:
        erros.append(f"{label or fid_codigo}: código do município vazio.")
        return False

    ultimo_erro = None
    for _ in range(3):
        try:
            loc = pagina.locator(f"#{fid_codigo}")
            loc.wait_for(state="visible", timeout=5000)
            loc.click(click_count=3)
            try:
                loc.fill("")
            except Exception:
                pass
            loc.fill(codigo)

            pagina.evaluate(
                """({ fieldId, codigoMunicipio, deducaoId, alvoBusca }) => {
                    const input = document.getElementById(fieldId);
                    if (!input) return false;
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                    input.focus();
                    if (setter) {
                        setter.call(input, codigoMunicipio);
                    } else {
                        input.value = codigoMunicipio;
                    }
                    input.defaultValue = codigoMunicipio;
                    input.setAttribute('value', codigoMunicipio);
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    if (typeof buscaMunicipioPorCod === 'function') {
                        buscaMunicipioPorCod(deducaoId, input, alvoBusca);
                    }
                    return true;
                }""",
                {
                    "fieldId": fid_codigo,
                    "codigoMunicipio": codigo,
                    "deducaoId": did,
                    "alvoBusca": alvo_busca,
                },
            )

            try:
                pagina.wait_for_function(
                    """({ fieldId, selectId, codigoMunicipio, nomeMunicipio }) => {
                        const normalizar = (txt) =>
                            String(txt || '')
                                .normalize('NFD')
                                .replace(/[\u0300-\u036f]/g, '')
                                .replace(/\\s+/g, ' ')
                                .trim()
                                .toLowerCase();
                        const input = document.getElementById(fieldId);
                        const select = document.getElementById(selectId);
                        if (!input) return false;
                        if (String(input.value || '').trim() !== String(codigoMunicipio || '').trim()) return false;
                        if (!select) return true;

                        const alvoCodigo = normalizar(codigoMunicipio);
                        const alvoNome = normalizar(nomeMunicipio);
                        return Array.from(select.options || []).some((option) => {
                            const texto = normalizar(option.text);
                            const valor = normalizar(option.value);
                            return (alvoCodigo && (valor === alvoCodigo || texto.includes(alvoCodigo)))
                                || (alvoNome && texto.includes(alvoNome));
                        });
                    }""",
                    arg={
                        "fieldId": fid_codigo,
                        "selectId": fid_select,
                        "codigoMunicipio": codigo,
                        "nomeMunicipio": nome,
                    },
                    timeout=5000,
                )
            except Exception:
                pass

            status = pagina.evaluate(
                """({ fieldId, selectId, codigoMunicipio, nomeMunicipio }) => {
                    const normalizar = (txt) =>
                        String(txt || '')
                            .normalize('NFD')
                            .replace(/[\u0300-\u036f]/g, '')
                            .replace(/\\s+/g, ' ')
                            .trim()
                            .toLowerCase();
                    const input = document.getElementById(fieldId);
                    const select = document.getElementById(selectId);
                    const alvoCodigo = normalizar(codigoMunicipio);
                    const alvoNome = normalizar(nomeMunicipio);

                    let selecionado = false;
                    let textoSelecionado = '';
                    if (select) {
                        const option = Array.from(select.options || []).find((item) => {
                            const texto = normalizar(item.text);
                            const valor = normalizar(item.value);
                            return (alvoCodigo && (valor === alvoCodigo || texto.includes(alvoCodigo)))
                                || (alvoNome && texto.includes(alvoNome));
                        });
                        if (option) {
                            select.value = option.value;
                            select.dispatchEvent(new Event('input', { bubbles: true }));
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                            if (typeof $ !== 'undefined') {
                                $(select).trigger('change');
                            }
                            selecionado = true;
                            textoSelecionado = String(option.text || '').trim();
                        }
                    }

                    const valorCodigo = String(input?.value || '').trim();
                    if (!textoSelecionado && select && select.selectedIndex >= 0) {
                        textoSelecionado = String(select.options[select.selectedIndex]?.text || '').trim();
                    }

                    return {
                        valorCodigo,
                        textoSelecionado,
                        ok:
                            valorCodigo === String(codigoMunicipio || '').trim()
                            && (!select || (selecionado && textoSelecionado && !/selecione/i.test(textoSelecionado))),
                    };
                }""",
                {
                    "fieldId": fid_codigo,
                    "selectId": fid_select,
                    "codigoMunicipio": codigo,
                    "nomeMunicipio": nome,
                },
            ) or {}

            if status.get("ok"):
                return True

            ultimo_erro = RuntimeError(
                f"campo ficou com código '{status.get('valorCodigo') or 'vazio'}' e município "
                f"'{status.get('textoSelecionado') or 'vazio'}'"
            )
        except Exception as exc:
            ultimo_erro = exc

    erros.append(f"{label or fid_codigo}: {ultimo_erro or 'não conseguiu preencher município.'}")
    return False


def _read_input_value(pagina, fid: str) -> str:
    try:
        return pagina.evaluate(
            """(fieldId) => {
                const el = document.getElementById(fieldId);
                return (el && el.value) ? String(el.value).trim() : '';
            }""",
            fid,
        )
    except Exception:
        return ""


def _set_input_silente(pagina, fid: str, valor: str) -> bool:
    try:
        return bool(pagina.evaluate(
            """([id, val]) => {
                const el = document.getElementById(id);
                if (!el) return false;
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                el.focus();
                if (setter) setter.call(el, val); else el.value = val;
                el.defaultValue = val;
                el.setAttribute('value', val);
                return true;
            }""",
            [fid, str(valor or "")],
        ))
    except Exception:
        return False


def _valor_campo_equivalente(atual: str, esperado: str, tolerancia: float = 0.01) -> bool:
    atual_txt = str(atual or "").strip()
    esperado_txt = str(esperado or "").strip()
    if atual_txt == esperado_txt:
        return True

    try:
        atual_num = float(normalizar_valor(atual_txt or "0") or "0")
        esperado_num = float(normalizar_valor(esperado_txt or "0") or "0")
        return abs(atual_num - esperado_num) <= tolerancia
    except Exception:
        return False


def _assert_datas_preenchidas(pagina, did: str, data_ddmmaaaa: str, erros: list) -> bool:
    """Verifica se as datas de vencimento e pagamento foram preenchidas corretamente.
    Aceita tanto o formato ISO (2026-04-16) quanto DD/MM/AAAA (16/04/2026).
    """
    partes = re.split(r"[/\-]", str(data_ddmmaaaa or "").strip())
    if len(partes) != 3:
        erros.append("Datas da dedução estão inválidas antes da confirmação.")
        return False

    dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
    iso = f"{aaaa}-{mm}-{dd}"
    br  = f"{dd}/{mm}/{aaaa}"
    aceitos = {iso, br}
    campos = [
        (f"sfdeducaodtvenc{did}", "Data de Vencimento"),
        (f"sfdeducaodtpgtoreceb{did}", "Data de Pagamento"),
    ]

    ok = True
    for fid, label in campos:
        valor = _read_input_value(pagina, fid)
        if valor not in aceitos:
            erros.append(f"{label}: campo ficou '{valor or 'vazio'}' antes da confirmação.")
            ok = False
    return ok

def _obter_bloco_deducao_vigente(pagina, did_referencia: str = "") -> dict:
    """Descobre o conjunto de IDs atual da deduÃ§Ã£o em ediÃ§Ã£o."""
    try:
        return pagina.evaluate(
            """(didRef) => {
                const visivel = (el) => !!el && (!!el.offsetParent || el.type === 'hidden');
                const extrairDid = (id, prefixo) => String(id || '').replace(prefixo, '');
                const grupos = new Map();

                const garantir = (did) => {
                    if (!grupos.has(did)) {
                        grupos.set(did, {
                            did,
                            situacaoId: '',
                            vencId: '',
                            pagamentoId: '',
                            confirmarId: '',
                            score: 0,
                        });
                    }
                    return grupos.get(did);
                };

                for (const el of document.querySelectorAll('[id^="sfdeducaocodsit"], [id^="sfdeducaodtvenc"], [id^="sfdeducaodtpgtoreceb"], [id^="confirma-dados-deducao-"]')) {
                    if (!visivel(el)) continue;
                    const id = String(el.id || '');
                    let did = '';
                    let campo = '';
                    if (id.startsWith('sfdeducaocodsit')) {
                        did = extrairDid(id, 'sfdeducaocodsit');
                        campo = 'situacaoId';
                    } else if (id.startsWith('sfdeducaodtvenc')) {
                        did = extrairDid(id, 'sfdeducaodtvenc');
                        campo = 'vencId';
                    } else if (id.startsWith('sfdeducaodtpgtoreceb')) {
                        did = extrairDid(id, 'sfdeducaodtpgtoreceb');
                        campo = 'pagamentoId';
                    } else if (id.startsWith('confirma-dados-deducao-')) {
                        did = extrairDid(id, 'confirma-dados-deducao-');
                        campo = 'confirmarId';
                    }
                    if (!did) continue;
                    const grupo = garantir(did);
                    grupo[campo] = id;
                }

                const todos = Array.from(grupos.values()).map((grupo) => ({
                    ...grupo,
                    score:
                        (grupo.vencId ? 10 : 0)
                        + (grupo.pagamentoId ? 10 : 0)
                        + (grupo.confirmarId ? 8 : 0)
                        + (grupo.situacaoId ? 4 : 0)
                        + (didRef && grupo.did === didRef ? 20 : 0)
                        + (Number.parseInt(grupo.did, 10) || 0) / 1000000,
                }));

                if (!todos.length) return {};
                todos.sort((a, b) => b.score - a.score);
                return todos[0];
            }""",
            did_referencia,
        ) or {}
    except Exception:
        return {}


def _abrir_aba_deducao(pagina) -> None:
    candidatos = [
        pagina.locator("#deducao-tab"),
        pagina.locator("a[href='#deducao'], a[data-target='#deducao']"),
        pagina.locator("button[aria-controls='deducao'], a[aria-controls='deducao']"),
        pagina.get_by_role("tab", name=re.compile(r"deduÃ§Ã£o|deducao", re.I)),
        pagina.locator("text=DeduÃ§Ã£o").first,
    ]

    ultimo_erro = None
    for loc in candidatos:
        try:
            if loc.count() == 0:
                continue
            alvo = loc.first
            alvo.wait_for(state="visible", timeout=2500)
            alvo.click()
            pagina.wait_for_function(
                """() => {
                    const visivel = (el) => !!el && !!el.offsetParent;
                    const painel = document.querySelector('#deducao');
                    if (visivel(painel)) return true;
                    return Array.from(document.querySelectorAll("[id^='sfdeducaocodsit']")).some((el) => visivel(el));
                }""",
                timeout=5000,
            )
            return
        except Exception as exc:
            ultimo_erro = exc
            continue

    raise RuntimeError(f"Aba DeduÃ§Ã£o nÃ£o encontrada ou nÃ£o abriu corretamente: {ultimo_erro}")


def _esperar_formulario_deducao_estabilizar(pagina, did: str, timeout_ms: int = 20000) -> None:
    """Espera os campos principais da deduÃ§Ã£o existirem e o botÃ£o confirmar estar disponÃ­vel."""
    try:
        pagina.wait_for_function(
            """(deducaoId) => {
                const visivel = (el) => !!el && (!!el.offsetParent || el.type === 'hidden');
                const match = (prefixo) => {
                    if (!deducaoId) return null;
                    return document.getElementById(`${prefixo}${deducaoId}`);
                };
                const editavel = (el) => visivel(el) && !el.disabled && !el.readOnly;
                const situacao = match('sfdeducaocodsit');
                const venc = match('sfdeducaodtvenc');
                const pag = match('sfdeducaodtpgtoreceb');
                const valor = match('sfdeducaovlr');
                const confirmar = document.getElementById(`confirma-dados-deducao-${deducaoId}`);
                return editavel(situacao) && editavel(venc) && editavel(pag) && editavel(valor) && visivel(confirmar);
            }""",
            arg=did,
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Formulário da dedução {did or 'sem id'} não estabilizou em {timeout_ms}ms."
        ) from exc


def _fixar_datas_deducao(pagina, did: str, data_venc: str, erros: list) -> str:
    """Preenche e reaplica as datas da deduÃ§Ã£o jÃ¡ no fim do fluxo, antes da confirmaÃ§Ã£o."""
    if not data_venc:
        erros.append("Data de vencimento calculada estÃ¡ vazia para a deduÃ§Ã£o.")
        return ""

    bloco = _obter_bloco_deducao_vigente(pagina, did)
    did_atual = str(bloco.get("did") or _resolver_did_vigente(pagina, did) or did)

    try:
        _esperar_formulario_deducao_estabilizar(pagina, did_atual)
    except Exception:
        # Segue mesmo sem a espera completa; o _fill_date ainda valida o valor final.
        pass

    for tentativa in range(1, 4):
        bloco = _obter_bloco_deducao_vigente(pagina, did_atual)
        did_atual = str(bloco.get("did") or _resolver_did_vigente(pagina, did_atual) or did_atual)
        venc_id = str(bloco.get("vencId") or f"sfdeducaodtvenc{did_atual}")
        pagamento_id = str(bloco.get("pagamentoId") or f"sfdeducaodtpgtoreceb{did_atual}")

        _rolar_para_datas_deducao(pagina, did_atual)
        _fill_date_silente(pagina, venc_id, data_venc, erros, "Data de Vencimento")
        _fill_date_silente(pagina, pagamento_id, data_venc, erros, "Data de Pagamento")

        erros_antes = len(erros)
        ok = _assert_datas_preenchidas(pagina, did_atual, data_venc, erros)
        if ok:
            print(f"    Datas da deduÃ§Ã£o estÃ¡veis na tentativa {tentativa}.")
            return did_atual

        del erros[erros_antes:]
        print(f"    Datas da deduÃ§Ã£o ainda instÃ¡veis; reaplicando (tentativa {tentativa}).")

    erros.append("Datas da deduÃ§Ã£o nÃ£o permaneceram preenchidas antes da confirmaÃ§Ã£o.")
    return ""


def _aguardar_confirmacao_deducao(pagina, did: str, timeout_ms: int = 12000) -> None:
    pagina.wait_for_function(
        """(deducaoId) => {
            const elConfirma = document.getElementById(`sfdeducaoconfirma_dados${deducaoId}`);
            // Se o elemento sumiu do DOM a dedução foi confirmada/removida
            if (!elConfirma) return true;
            const valorConfirmado = String(elConfirma.value || '').trim().toLowerCase();
            if (valorConfirmado === 'true') return true;

            const restantesNaoConfirmadas = Array.from(
                document.querySelectorAll('.sfdeducaoApropriacaoConfirmaDados, [id^="sfdeducaoconfirma_dados"]')
            )
                .map((el) => String(el.value || '').trim().toLowerCase())
                .filter((valor) => valor === 'false').length;
            if (restantesNaoConfirmadas === 0) return true;

            const botao = document.getElementById(`confirma-dados-deducao-${deducaoId}`);
            if (!botao || botao.disabled) return true;

            const textos = Array.from(document.querySelectorAll('.swal2-container, .swal2-popup, .pnotify, .ui-pnotify, .sweet-alert, .jconfirm'))
                .map((el) => String(el.textContent || '').trim().toLowerCase())
                .filter(Boolean);
            return textos.some((texto) =>
                texto.includes('dados salvo com sucesso') ||
                texto.includes('dados salvos com sucesso') ||
                texto.includes('sucesso')
            );
        }""",
        arg=did,
        timeout=timeout_ms,
    )


def _aguardar_proxima_deducao_liberada(pagina, did_confirmado: str, timeout_ms: int = 15000) -> None:
    pagina.wait_for_function(
        """(deducaoId) => {
            const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length);
            const botaoAtual = document.getElementById(`confirma-dados-deducao-${deducaoId}`);
            const elHidden = document.getElementById(`sfdeducaoconfirma_dados${deducaoId}`);
            // Elemento sumiu → dedução confirmada/removida
            if (!elHidden) return true;
            const hiddenAtual = String(elHidden.value || '').trim().toLowerCase();
            const overlayAtivo = !!document.querySelector('#nova-aba-situacao-deducao .overlay');
            const existeEmEdicao = Array.from(document.querySelectorAll('[id^="sfdeducaoconfirma_dados"]'))
                .some((el) => {
                    const valor = String(el.value || '').trim().toLowerCase();
                    const id = String(el.id || '').replace('sfdeducaoconfirma_dados', '');
                    const botao = document.getElementById(`confirma-dados-deducao-${id}`);
                    return valor !== 'true' && visivel(botao);
                });
            const botaoNovo = document.getElementById('nova-aba-situacao-deducao');

            if (overlayAtivo) return false;
            if (existeEmEdicao) return false;
            if (hiddenAtual !== 'true' && visivel(botaoAtual)) return false;
            return visivel(botaoNovo);
        }""",
        arg=did_confirmado,
        timeout=timeout_ms,
    )


def _cancelar_deducoes_abertas(pagina) -> int:
    """Tenta fechar/cancelar todas as deduções ainda abertas (não confirmadas).

    Estratégias (em ordem):
    1. Clica no botão de exclusão (lixeira / excluir / remover) de cada dedução.
    2. Tenta invocar diretamente as funções JS do portal (excluirDeducao, etc.).
    3. Preenche as datas obrigatórias e depois confirma (último recurso).
    Retorna quantas deduções foram fechadas.
    """
    # Primeiro: descobre os DIDs travados e quais funções JS estão disponíveis
    info = pagina.evaluate(
        """() => {
            const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length > 0);
            const naoConf = Array.from(document.querySelectorAll('[id^="sfdeducaoconfirma_dados"]'))
                .filter(el => {
                    const v = String(el.value || '').trim().toLowerCase();
                    const d = String(el.id || '').replace('sfdeducaoconfirma_dados', '');
                    return v !== 'true' && visivel(document.getElementById(`confirma-dados-deducao-${d}`));
                })
                .map(el => String(el.id || '').replace('sfdeducaoconfirma_dados', ''));
            // Funções globais relacionadas a excluir/remover dedução
            const fns = Object.keys(window).filter(k =>
                /excluir|remover|delete|cancel/i.test(k) && /deduc/i.test(k)
            );
            return { dids: naoConf, fns };
        }"""
    ) or {"dids": [], "fns": []}
    print(f"    [Recovery] dids travados={info.get('dids')} fns_js={info.get('fns')}")

    fechadas = 0
    for did in (info.get("dids") or []):
        # ── Tenta via função JS do portal ────────────────────────────────────
        fn_names = info.get("fns") or []
        tentou_fn = False
        for fn in fn_names:
            try:
                ok = pagina.evaluate(f"(did) => {{ if (typeof {fn} === 'function') {{ {fn}(did); return true; }} return false; }}", did)
                if ok:
                    print(f"    [Recovery] Chamou {fn}('{did}')")
                    fechadas += 1
                    tentou_fn = True
                    break
            except Exception:
                pass

        if tentou_fn:
            time.sleep(1.0)
            continue

        # ── Tenta encontrar e clicar no botão de exclusão ─────────────────────
        clicou = pagina.evaluate(
            """(did) => {
                const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length > 0);
                // Candidatos: qualquer elemento com onclick que mencione excluir/remover + did
                const todos = Array.from(document.querySelectorAll('[onclick],[href]'));
                for (const el of todos) {
                    const oc = String(el.getAttribute('onclick') || el.getAttribute('href') || '');
                    if (oc.includes(did) && /excluir|remover|delete|cancel/i.test(oc)) {
                        const alvo = el.closest('button,a,[role="button"]') || el;
                        if (visivel(alvo)) { alvo.click(); return 'onclick:' + oc.slice(0, 60); }
                    }
                }
                // Ícone lixeira próximo ao bloco da dedução
                const refEl = document.getElementById(`sfdeducaoconfirma_dados${did}`)
                           || document.getElementById(`confirma-dados-deducao-${did}`);
                if (refEl) {
                    const bloco = refEl.closest('.tab-pane, .panel, .card, [class*="deducao"], [class*="deduc"]') || refEl.parentElement?.parentElement;
                    if (bloco) {
                        const lixeira = bloco.querySelector('.fa-trash, .fa-trash-o, .glyphicon-trash, [title*="xcluir"], [title*="emov"], [aria-label*="xcluir"]');
                        if (lixeira) {
                            const btn = lixeira.closest('button,a,[role="button"]') || lixeira;
                            if (visivel(btn)) { btn.click(); return 'lixeira'; }
                        }
                    }
                }
                return null;
            }""",
            did,
        )
        if clicou:
            print(f"    [Recovery] Clicou botão de exclusão: {clicou}")
            fechadas += 1
            time.sleep(1.0)
            continue

        # ── Último recurso: preenche datas obrigatórias + confirma ────────────
        # Usa _fill_date_silente para aproveitar todas as estratégias de preenchimento
        print(f"    [Recovery] Nenhum botão encontrado para did={did}. Preenchendo datas e confirmando...")
        try:
            hoje_br = pagina.evaluate(
                "() => { const d = new Date(); "
                "return d.getDate().toString().padStart(2,'0')+'/'+(d.getMonth()+1).toString().padStart(2,'0')+'/'+d.getFullYear(); }"
            )
            erros_rec: list = []
            _fill_date_silente(pagina, f"sfdeducaodtvenc{did}", hoje_br, erros_rec, "Recovery-Venc")
            _fill_date_silente(pagina, f"sfdeducaodtpgtoreceb{did}", hoje_br, erros_rec, "Recovery-Pgto")
            if erros_rec:
                print(f"    [Recovery] Avisos ao preencher datas: {erros_rec}")
            time.sleep(0.3)
            botao = pagina.locator(f"#confirma-dados-deducao-{did}")
            botao.wait_for(state="visible", timeout=3000)
            botao.click()
            fechadas += 1
            time.sleep(1.0)
        except Exception as e_rec:
            print(f"    [Recovery] Falha ao confirmar did={did}: {e_rec}")

    return fechadas


def _garantir_sem_deducao_em_edicao(pagina, timeout_ms: int = 8000) -> None:
    try:
        pagina.wait_for_function(
            """() => {
                const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length);
                return !Array.from(document.querySelectorAll('[id^="sfdeducaoconfirma_dados"]'))
                    .some((el) => {
                        const valor = String(el.value || '').trim().toLowerCase();
                        const did = String(el.id || '').replace('sfdeducaoconfirma_dados', '');
                        const botao = document.getElementById(`confirma-dados-deducao-${did}`);
                        return valor !== 'true' && visivel(botao);
                    });
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        # Timeout: há dedução travada. Tenta fechar e aguarda mais um pouco.
        print("    [Recuperação] Dedução travada detectada — tentando fechar...")
        fechadas = _cancelar_deducoes_abertas(pagina)
        print(f"    [Recuperação] {fechadas} dedução(ões) fechada(s). Aguardando...")
        time.sleep(2.0)
        # Segunda tentativa com timeout maior
        try:
            pagina.wait_for_function(
                """() => {
                    const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length);
                    return !Array.from(document.querySelectorAll('[id^="sfdeducaoconfirma_dados"]'))
                        .some((el) => {
                            const valor = String(el.value || '').trim().toLowerCase();
                            const did = String(el.id || '').replace('sfdeducaoconfirma_dados', '');
                            const botao = document.getElementById(`confirma-dados-deducao-${did}`);
                            return valor !== 'true' && visivel(botao);
                        });
                }""",
                timeout=max(timeout_ms, 30000),
            )
            print("    [Recuperação] Dedução fechada com sucesso.")
        except Exception as e2:
            print(f"    [Recuperação] Ainda há dedução aberta após tentativa de fechar: {e2}")
            raise RuntimeError(
                f"Dedução anterior continuou aberta após recuperação ({fechadas} fechada(s))."
            ) from e2


def _verificar_interrupcao(deve_parar=None):
    if deve_parar and deve_parar():
        raise ExecucaoInterrompida("ExecuÃ§Ã£o interrompida pelo usuÃ¡rio durante DeduÃ§Ã£o.")


def _select(pagina, fid: str, texto: str, erros: list, label: str = ""):
    """
    Seleciona opção em <select> (ou Select2) pelo id exato.
    Tenta via JavaScript para garantir que o evento 'change' seja disparado.
    Aceita variantes acentuadas e sem acento (ex: 'NÃO' e 'NAO' são equivalentes).
    """
    import unicodedata as _ud

    def _normalizar(s: str) -> str:
        return _ud.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()

    texto_norm = _normalizar(texto)
    texto_lower = texto.lower().strip()
    try:
        ok = pagina.evaluate(
            """([fid, textoLower, textoNorm]) => {
                const sel = document.getElementById(fid);
                if (!sel) return false;

                const norm = (s) => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().trim();

                const op = Array.from(sel.options).find(o =>
                    o.text.toLowerCase().trim() === textoLower ||
                    o.text.toLowerCase().trim().includes(textoLower) ||
                    norm(o.text) === textoNorm ||
                    norm(o.text).includes(textoNorm) ||
                    o.value.toLowerCase().trim() === textoLower ||
                    norm(o.value) === textoNorm
                );
                if (!op) return false;
                sel.value = op.value;
                sel.dispatchEvent(new Event('change', {bubbles: true}));
                if (typeof $ !== 'undefined') $(sel).trigger('change');
                return true;
            }""",
            [fid, texto_lower, texto_norm],
        )
        if not ok:
            erros.append(f"{label or fid}: opção '{texto}' não encontrada")
    except Exception as e:
        erros.append(f"{label or fid}: {e}")


def _select_com_fallback(pagina, fid: str, opcoes: list[str], erros: list, label: str = "") -> str:
    """Seleciona a primeira opÃ§Ã£o existente em um select."""
    for opcao in opcoes:
        if not str(opcao or "").strip():
            continue
        try:
            ok = pagina.evaluate(
                """({ fieldId, texto }) => {
                    const sel = document.getElementById(fieldId);
                    if (!sel) return false;
                    const alvo = String(texto || '').trim().toLowerCase();
                    const op = Array.from(sel.options).find((item) =>
                        String(item.value || '').trim().toLowerCase() === alvo ||
                        String(item.text || '').trim().toLowerCase().includes(alvo)
                    );
                    if (!op) return false;
                    sel.value = op.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    if (typeof $ !== 'undefined') {
                        $(sel).trigger('change');
                    }
                    return true;
                }""",
                {"fieldId": fid, "texto": str(opcao)},
            )
            if ok:
                return str(opcao)
        except Exception:
            continue
    erros.append(f"{label or fid}: nenhuma das opÃ§Ãµes {opcoes} foi encontrada")
    return ""


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# DESCOBERTA DE IDs DINÃ‚MICOS
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def _obter_did(pagina) -> str:
    """
    Retorna o sufixo numÃ©rico (ex: '884228') do ÃšLTIMO DDR001 adicionado.
    Baseado no id do select de situaÃ§Ã£o: sfdeducaocodsit{did}
    """
    return pagina.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('[id^="sfdeducaocodsit"]'));
        if (!els.length) return '';
        return els[els.length - 1].id.replace('sfdeducaocodsit', '');
    }""") or ""


def _obter_rid(pagina, did: str) -> str:
    """
    Retorna o sufixo numÃ©rico (ex: '976052') do recolhedor auto-criado
    para a deduÃ§Ã£o 'did'.
    Busca: recolhedor{did}{rid}, vlrPrincipal{did}{rid} e vlrbasecalculo{did}{rid}
    (DDF055/DARF pode criar vlrbasecalculo antes de vlrPrincipal).
    """
    return pagina.evaluate(f"""() => {{
        const ids = [
            ...Array.from(document.querySelectorAll('[id^="recolhedor{did}"]')).map(el => el.id),
            ...Array.from(document.querySelectorAll('[id^="vlrPrincipal{did}"]')).map(el => el.id),
            ...Array.from(document.querySelectorAll('[id^="vlrbasecalculo{did}"]')).map(el => el.id),
        ];
        if (!ids.length) return '';
        const ultimo = ids[ids.length - 1];
        return ultimo
            .replace('recolhedor{did}', '')
            .replace('vlrPrincipal{did}', '')
            .replace('vlrbasecalculo{did}', '');
    }}""") or ""


def _aguardar_novo_recolhedor(pagina, did: str, rid_anterior: str = "", timeout_ms: int = 12000) -> str:
    """Aguarda a criação de uma nova linha de recolhedor para a dedução `did`.

    Aceita qualquer um dos três campos que o portal pode criar:
      recolhedor{did}{rid}     — CNPJ
      vlrbasecalculo{did}{rid} — Base de Cálculo (DDF055/DARF)
      vlrPrincipal{did}{rid}   — Valor da Receita
    """
    pagina.wait_for_function(
        """({ deducaoId, ridAnterior }) => {
            const ids = [
                ...Array.from(document.querySelectorAll(`[id^="recolhedor${deducaoId}"]`)).map((el) => el.id),
                ...Array.from(document.querySelectorAll(`[id^="vlrPrincipal${deducaoId}"]`)).map((el) => el.id),
                ...Array.from(document.querySelectorAll(`[id^="vlrbasecalculo${deducaoId}"]`)).map((el) => el.id),
            ];
            if (!ids.length) return false;

            const ultimo = ids[ids.length - 1]
                .replace(`recolhedor${deducaoId}`, '')
                .replace(`vlrPrincipal${deducaoId}`, '')
                .replace(`vlrbasecalculo${deducaoId}`, '');

            if (!ultimo) return false;
            if (ridAnterior && ultimo === ridAnterior) return false;

            // Aceita qualquer campo — DDF055 pode criar vlrbasecalculo antes de vlrPrincipal
            return !!document.getElementById(`recolhedor${deducaoId}${ultimo}`)
                || !!document.getElementById(`vlrPrincipal${deducaoId}${ultimo}`)
                || !!document.getElementById(`vlrbasecalculo${deducaoId}${ultimo}`);
        }""",
        arg={"deducaoId": did, "ridAnterior": rid_anterior},
        timeout=timeout_ms,
    )
    return _obter_rid(pagina, did)


def _preencher_valor_recolhedor(
    pagina, did: str, cnpj_fmt: str, valor_br: str, erros: list,
    rid_pre_aberto: str = "",
) -> bool:
    """Clica uma vez no '+' do recolhedor e preenche o campo vlrPrincipal.

    Se ``rid_pre_aberto`` for fornecido, usa esse RID diretamente sem clicar
    no '+' novamente (útil quando o recolhedor já foi expandido antes do
    preenchimento principal, para evitar que o AJAX de expansão resete campos).
    """
    try:
        if rid_pre_aberto:
            rid = rid_pre_aberto
        else:
            rid_anterior = _obter_rid(pagina, did)
            try:
                pagina.locator(f"#novo-recolhedor{did}").wait_for(state="visible", timeout=8000)
                pagina.locator(f"#novo-recolhedor{did}").click()
                rid = _aguardar_novo_recolhedor(pagina, did, rid_anterior=rid_anterior, timeout_ms=12000)
            except Exception:
                rid = _obter_rid(pagina, did)

        if rid:
            if _fill_money(pagina, f"vlrPrincipal{did}{rid}", valor_br, erros, "Valor da Receita"):
                return True
            erros.append(
                f"DDR001: campo vlrPrincipal{did}{rid} nÃ£o aceitou o valor '{valor_br}'."
            )
            return False

        erros.append(f"DDR001: nÃ£o encontrou um campo de Valor da Receita para a deduÃ§Ã£o (did={did}).")
        return False
    except Exception as e:
        erros.append(f"Valor da Receita / recolhedor: {e}")
        return False


def _preencher_recolhedor_darf(
    pagina,
    did: str,
    cnpj_fmt: str,
    base_calculo_br: str,
    valor_receita_br: str,
    erros: list,
    rid_pre_aberto: str = "",
) -> bool:
    """Preenche os campos do recolhedor DARF.

    Se ``rid_pre_aberto`` for fornecido, usa esse RID diretamente sem clicar
    no '+' novamente (útil quando o recolhedor já foi expandido antes do
    preenchimento principal, para evitar que o AJAX de expansão resete campos).
    """
    try:
        if rid_pre_aberto:
            rid = rid_pre_aberto
        else:
            rid_anterior = _obter_rid(pagina, did)
            try:
                pagina.locator(f"#novo-recolhedor{did}").wait_for(state="visible", timeout=8000)
                pagina.locator(f"#novo-recolhedor{did}").click()
                rid = _aguardar_novo_recolhedor(pagina, did, rid_anterior=rid_anterior, timeout_ms=12000)
            except Exception:
                rid = _obter_rid(pagina, did)
                if not rid:
                    # Segunda tentativa: aguarda mais e tenta de novo
                    time.sleep(1.5)
                    try:
                        pagina.locator(f"#novo-recolhedor{did}").wait_for(state="visible", timeout=5000)
                        pagina.locator(f"#novo-recolhedor{did}").click()
                        rid = _aguardar_novo_recolhedor(pagina, did, rid_anterior=rid_anterior, timeout_ms=10000)
                    except Exception:
                        rid = _obter_rid(pagina, did)

        if not rid:
            erros.append(f"DARF: nÃ£o encontrou a linha de recolhimento da deduÃ§Ã£o (did={did}).")
            return False

        cnpj_dig = re.sub(r"\D", "", str(cnpj_fmt or ""))
        recolhedor_id = f"recolhedor{did}{rid}"
        atual_recolhedor = re.sub(r"\D", "", _read_input_value(pagina, recolhedor_id))
        if cnpj_dig and atual_recolhedor != cnpj_dig:
            _fill(pagina, recolhedor_id, cnpj_dig, erros, "Recolhedor")

        if not _fill_money(pagina, f"vlrbasecalculo{did}{rid}", base_calculo_br, erros, "Base de CÃ¡lculo"):
            return False

        if not _fill_money(pagina, f"vlrPrincipal{did}{rid}", valor_receita_br, erros, "Valor da Receita"):
            return False

        return True
    except Exception as e:
        erros.append(f"Recolhedor DARF: {e}")
        return False


def _resolver_did_vigente(pagina, did_referencia: str = "") -> str:
    """
    Redescobre o DID atual da deduÃ§Ã£o ativa/mais recente.
    O portal pode recriar o bloco no DOM enquanto o prÃ©-doc Ã© preenchido.
    """
    bloco = _obter_bloco_deducao_vigente(pagina, did_referencia)
    return str(bloco.get("did") or "")


def _obter_deducao_em_edicao(pagina) -> str:
    """
    Retorna o DID de uma deduÃ§Ã£o jÃ¡ aberta e ainda nÃ£o confirmada.
    Isso evita clicar no '+' repetidamente quando o portal demora a reagir.
    """
    try:
        return pagina.evaluate(
            """() => {
                const visivel = (el) => !!el && (!!el.offsetParent || el.type === 'hidden');
                const dids = Array.from(document.querySelectorAll('[id^="sfdeducaocodsit"]'))
                    .filter((el) => visivel(el))
                    .map((el) => String(el.id).replace('sfdeducaocodsit', ''));

                const candidatos = dids.map((did) => {
                    const confirmado = document.getElementById(`sfdeducaoconfirma_dados${did}`);
                    const valorConfirmado = String(confirmado.value || '').trim().toLowerCase();
                    const situacao = document.getElementById(`sfdeducaocodsit${did}`);
                    const valorSituacao = String(situacao.value || '').trim();
                    const confirmar = document.getElementById(`confirma-dados-deducao-${did}`);
                    return {
                        did,
                        aindaAberta: valorConfirmado !== 'true' && visivel(confirmar),
                        score:
                            (valorSituacao ? 8 : 0)
                            + (confirmar && visivel(confirmar) ? 10 : 0)
                            + ((Number.parseInt(did, 10) || 0) / 1000000),
                    };
                }).filter((item) => item.did && item.aindaAberta);

                if (!candidatos.length) return '';
                candidatos.sort((a, b) => b.score - a.score);
                return candidatos[0].did;
            }"""
        ) or ""
    except Exception:
        return ""


def _rolar_para_datas_deducao(pagina, did: str) -> None:
    return None


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# BOTÃƒO "+" DA ABA DEDUÃ‡ÃƒO
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def _clicar_nova_deducao(pagina, reutilizar_existente: bool = False):
    """
    Clica no link id='nova-aba-situacao-deducao' para adicionar uma nova deduÃ§Ã£o.
    HTML real:
      <a id="nova-aba-situacao-deducao" onclick="clickBtnNovaAbaSituacaoDeducao(null,false)">
        <i class="fa fa-plus"></i>
      </a>
    """
    did_existente = _obter_deducao_em_edicao(pagina)
    if reutilizar_existente and did_existente:
        print(f"    Reaproveitando deduÃ§Ã£o em ediÃ§Ã£o (did={did_existente}).")
        return did_existente

    try:
        estado_antes = pagina.evaluate(
            """() => {
                const parseIntSafe = (valor) => {
                    const num = Number.parseInt(String(valor || ''), 10);
                    return Number.isNaN(num) ? 0 : num;
                };
                const ids = Array.from(document.querySelectorAll('[id^="sfdeducaocodsit"]'))
                    .map((el) => String(el.id).replace('sfdeducaocodsit', ''))
                    .map(parseIntSafe)
                    .filter((id) => id > 0);
                const countHost = document.querySelector('.count-situacao-deducao');
                return {
                    did: ids.length ? Math.max(...ids) : 0,
                    contador: parseIntSafe(countHost?.dataset?.countSituacaoDeducao ?? countHost?.getAttribute('data-count-situacao-deducao')),
                    html: document.getElementById('deducao').innerHTML || '',
                };
            }"""
        ) or {}
    except Exception:
        estado_antes = {"did": 0, "contador": 0, "html": ""}

    disparou = pagina.evaluate(
        """() => {
            if (typeof clickBtnNovaAbaSituacaoDeducao === 'function') {
                clickBtnNovaAbaSituacaoDeducao(null, false);
                return 'funcao-js';
            }
            const el = document.getElementById('nova-aba-situacao-deducao');
            if (!el) return '';
            el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' });
            el.click();
            return 'click-dom';
        }"""
    )
    if not disparou:
        raise RuntimeError("NÃ£o foi possÃ­vel localizar o '+' de nova deduÃ§Ã£o.")

    pagina.wait_for_function(
        """(estadoAnterior) => {
            const parseIntSafe = (valor) => {
                const num = Number.parseInt(String(valor || ''), 10);
                return Number.isNaN(num) ? 0 : num;
            };
            const ids = Array.from(document.querySelectorAll('[id^="sfdeducaocodsit"]'))
                .map((el) => String(el.id).replace('sfdeducaocodsit', ''))
                .map(parseIntSafe)
                .filter((id) => id > 0);
            const didAtual = ids.length ? Math.max(...ids) : 0;
            const countHost = document.querySelector('.count-situacao-deducao');
            const contadorAtual = parseIntSafe(
                countHost?.dataset?.countSituacaoDeducao
                ?? countHost?.getAttribute('data-count-situacao-deducao')
            );
            const htmlAtual = document.getElementById('deducao').innerHTML || '';
            const overlayAtivo = !!document.querySelector('#nova-aba-situacao-deducao .overlay');

            if (overlayAtivo) return false;
            if (didAtual > parseIntSafe(estadoAnterior.did)) return true;
            if (contadorAtual > parseIntSafe(estadoAnterior.contador)) return true;
            return htmlAtual && htmlAtual !== String(estadoAnterior.html || '');
        }""",
        arg=estado_antes,
        timeout=20000,
    )

    # Busca DID novo com retry — o portal às vezes demora a criar o elemento
    did_anterior_int = int(estado_antes.get("did") or 0)
    did_novo = ""
    for _tentativa in range(8):
        did_novo = pagina.evaluate(
            """(didAnterior) => {
                const parseIntSafe = (v) => { const n = Number.parseInt(String(v||''),10); return isNaN(n)?0:n; };
                const ids = Array.from(document.querySelectorAll('[id^="sfdeducaocodsit"]'))
                    .map((el) => parseIntSafe(String(el.id).replace('sfdeducaocodsit','')))
                    .filter((id) => id > didAnterior);
                return ids.length ? String(Math.max(...ids)) : '';
            }""",
            did_anterior_int,
        ) or ""
        if did_novo:
            break
        # Ainda não apareceu — aguarda e tenta de novo
        time.sleep(0.4)

    if not did_novo:
        # Fallback: dedução em edição (não confirmada) com DID > anterior
        did_novo = _obter_deducao_em_edicao(pagina) or ""
        if did_novo and int(did_novo or 0) <= did_anterior_int:
            did_novo = ""

    if not did_novo:
        bloco_vigente = _obter_bloco_deducao_vigente(pagina)
        cand = str(bloco_vigente.get("did") or "")
        if cand and int(cand) > did_anterior_int:
            did_novo = cand
    if not did_novo:
        # Fallback ampliado: varre qualquer elemento com sufixo numérico no painel
        did_novo = pagina.evaluate(
            """(estadoAnterior) => {
                const didAnterior = Number.parseInt(String(estadoAnterior.did || ''), 10) || 0;
                const painel = document.getElementById('deducao') || document.body;
                const prefixos = [
                    'sfdeducaocodsit', 'sfdeducaodtvenc', 'sfdeducaodtpgtoreceb',
                    'sfdeducaovlr', 'sfdeducaocodugpgto', 'sfdeducaoconfirma_dados',
                    'sfdeducaopossui_acrescimo', 'confirma-dados-deducao-',
                    'txtinscra', 'txtinscrb', 'municipioDeducao',
                ];
                const nums = new Set();
                for (const el of painel.querySelectorAll('[id]')) {
                    const id = String(el.id || '');
                    for (const pref of prefixos) {
                        if (id.startsWith(pref)) {
                            const n = Number.parseInt(id.slice(pref.length), 10);
                            if (!Number.isNaN(n) && n > didAnterior) nums.add(n);
                        }
                    }
                    const m = /(\d{5,})$/.exec(id);
                    if (m) {
                        const n = Number.parseInt(m[1], 10);
                        if (n > didAnterior) nums.add(n);
                    }
                }
                if (nums.size === 0) {
                    const amostra = Array.from(painel.querySelectorAll('[id]'))
                        .slice(0, 40).map(e => e.id).filter(Boolean).join(', ');
                    console.warn('[DEDUCAO] IDs no painel apos clique no +:', amostra || 'nenhum');
                    return '';
                }
                return String(Math.max(...nums));
            }""",
            estado_antes,
        ) or ""
    if not did_novo:
        raise RuntimeError("Nova deduÃ§Ã£o nÃ£o apareceu apÃ³s um Ãºnico clique no '+'.")

    try:
        _esperar_formulario_deducao_estabilizar(pagina, did_novo, timeout_ms=20000)
    except Exception as e:
        print(f"    Aviso: formulário de dedução não estabilizou completamente (did={did_novo}): {e}")
    print(f"    Nova deduÃ§Ã£o criada com um clique ({disparou}, did={did_novo}).")
    return did_novo


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# PRÃ‰-DOC  (IDs exatos confirmados por inspeÃ§Ã£o)
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
#
# sfpredoccodrecurso{did}      SELECT  Recurso
# sfpredocreferencia{did}      INPUT   ReferÃªncia (MM/AAAA)
# sfpredoccodugtmdrserv{did}   INPUT   UG Tomadora do ServiÃ§o
# sfpredoccodmuninf{did}       INPUT   CÃ³digo do MunicÃ­pio da NF  (AJAX â†’ popula select)
# municipioDeducaoPreDoc{did}  SELECT  MunicÃ­pio da NF            (Select2)
# sfpredocnumnf{did}           INPUT   NÃºmero da NF
# sfpredocdtemisnf{did}        INPUT   Data de EmissÃ£o da NF
# sfpredoctxtserienf{did}      INPUT   SÃ©rie (nÃ£o preencher)
# sfpredocnumsubserienf{did}   INPUT   SubsÃ©rie (nÃ£o preencher)
# sfpredocnumaliqnf{did}       INPUT   AlÃ­quota da NF
# sfpredocvlrnf{did}           INPUT   Valor da NF
# sfpredoctxtobser{did}        TEXTAREA ObservaÃ§Ã£o

def _extrair_pdid_de_ids(ids_existentes: set) -> str:
    """Extrai o pdid (sufixo numérico) de um conjunto de IDs de campos sfpredoc*.
    Retorna o maior número encontrado, ou '' se nenhum."""
    _PREFIXOS_PREDOC = [
        "sfpredoccodrecurso", "sfpredocreferencia", "sfpredocnumref",
        "sfpredoctxtprocesso", "sfpredocdtprdoapuracao", "sfpredoccodmuninf",
        "sfpredocnumnf", "sfpredocdtemisnf", "sfpredocvlrnf",
        "sfpredoctxtobser", "sfpredoccodugtmdrserv", "sfpredocnumaliqnf",
    ]
    nums = set()
    for id_str in ids_existentes:
        for pref in _PREFIXOS_PREDOC:
            if id_str.startswith(pref):
                sufixo = id_str[len(pref):]
                try:
                    nums.add(int(sufixo))
                except ValueError:
                    pass
    if nums:
        return str(max(nums))
    return ""


def _coletar_ids_predoc_do_did(pagina, did: str, apenas_visiveis: bool = False) -> list[str]:
    """Coleta IDs `sfpredoc*` pertencentes ao bloco da dedução informada.

    O portal mantém vários painéis de dedução simultaneamente no DOM. Quando
    usamos uma busca global, é fácil capturar o `pdid` da dedução anterior e
    preencher o Pré-Doc errado a partir da 4ª NF. Por isso a coleta fica
    ancorada no bloco visível do `did` atual.
    """
    try:
        return pagina.evaluate(
            """({ deducaoId, apenasVisiveis }) => {
                const prefixos = [
                    'sfpredoccodrecurso', 'sfpredocreferencia', 'sfpredocnumref',
                    'sfpredoctxtprocesso', 'sfpredocdtprdoapuracao', 'sfpredoccodmuninf',
                    'sfpredocnumnf', 'sfpredocdtemisnf', 'sfpredocvlrnf',
                    'sfpredoctxtobser', 'sfpredoccodugtmdrserv', 'sfpredocnumaliqnf',
                ];
                const visivel = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                };
                const coletar = (root) => {
                    if (!root) return [];
                    const ids = [];
                    for (const el of root.querySelectorAll('[id]')) {
                        const id = String(el.id || '');
                        if (!prefixos.some((p) => id.startsWith(p))) continue;
                        if (apenasVisiveis && !visivel(el)) continue;
                        ids.push(id);
                    }
                    return ids;
                };

                const ancora =
                    document.getElementById(`confirma-dados-deducao-${deducaoId}`)
                    || document.getElementById(`aba-deducao${deducaoId}`)
                    || document.getElementById(`sfdeducaocodsit${deducaoId}`)
                    || document.getElementById(`sfdeducaovlr${deducaoId}`);

                let nivel = ancora;
                for (let i = 0; i < 12 && nivel; i += 1) {
                    const ids = coletar(nivel);
                    if (ids.length) return ids;
                    nivel = nivel.parentElement;
                }
                return [];
            }""",
            {"deducaoId": did, "apenasVisiveis": apenas_visiveis},
        ) or []
    except Exception:
        return []


def _obter_pdid_do_did(pagina, did: str, apenas_visiveis: bool = False) -> str:
    """Extrai o `pdid` associado ao bloco da dedução atual."""
    return _extrair_pdid_de_ids(set(_coletar_ids_predoc_do_did(pagina, did, apenas_visiveis)))


def _abrir_predoc_resiliente(pagina, did: str, erros: list) -> str:
    """Abre o Pré-Doc clicando no '+', detecta o pdid real dos campos que aparecem
    e retorna-o como string.  Retorna '' em caso de falha.

    O Pré-Doc pode ter um sufixo numérico (pdid) DIFERENTE do sufixo da
    dedução pai (did), por isso não usamos did para identificar os campos do
    formulário – detectamos o pdid pelos próprios IDs que surgem no DOM.
    """
    try:
        # ── 1. Captura IDs sfpredoc* já existentes no DOM ────────────────────
        ids_antes = _coletar_ids_predoc_do_did(pagina, did, apenas_visiveis=False)
        ids_antes_set = set(ids_antes)

        # ── 2. Verifica se o Pré-Doc já está aberto (com campos VISÍVEIS) ──────
        # Para DDF055 os IDs sfpredoc* já existem no DOM desde o carregamento
        # da página (mas ficam ocultos). Só consideramos "aberto" se ao menos
        # um dos campos principais estiver visível na tela.
        pdid_existente = _obter_pdid_do_did(pagina, did, apenas_visiveis=True)
        if pdid_existente:
            log.debug("Pré-Doc já aberto e visível no bloco did=%s; pdid=%s", did, pdid_existente)
            return pdid_existente
        if ids_antes_set:
            pdid_existente = _extrair_pdid_de_ids(ids_antes_set)
        if pdid_existente:
            # IDs existem mas ocultos (DDF055) → ainda precisa clicar no "+"
            log.debug(
                "IDs sfpredoc do did=%s encontrados (pdid=%s) mas campos ocultos → clicando no '+'.",
                did,
                pdid_existente,
            )

        # ── 3. Clica no botão '+' do Pré-Doc ─────────────────────────────────
        clicou = pagina.evaluate(
            """(deducaoId) => {
                const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length > 0);
                const normalizar = (txt) =>
                    String(txt || '')
                        .normalize('NFD')
                        .replace(/[\u0300-\u036f]/g, '')
                        .replace(/\s+/g, ' ')
                        .trim()
                        .toLowerCase();

                const clicar = (el) => {
                    const alvo = el?.closest?.('button, a, [role="button"]') || el;
                    if (!alvo || !visivel(alvo)) return false;
                    alvo.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' });
                    try { alvo.click(); }
                    catch (_) {
                        alvo.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    }
                    return true;
                };

                const temCaraDePredoc = (el) => {
                    if (!el || !visivel(el)) return false;
                    const texto  = normalizar(el.textContent || el.value || '');
                    const titulo = normalizar(
                        el.getAttribute?.('title') || el.getAttribute?.('aria-label') ||
                        el.getAttribute?.('data-original-title') || ''
                    );
                    const classe  = normalizar(el.className || '');
                    const onclick = normalizar(el.getAttribute?.('onclick') || '');
                    const temIconeMais = !!el.querySelector?.('.fa-plus, .glyphicon-plus, [class*="plus"]');
                    return classe.includes('tooltipadicionarpredoc')
                        || titulo.includes('predoc')
                        || onclick.includes('predoc')
                        || texto.includes('predoc')
                        || texto === '+'
                        || temIconeMais;
                };

                const candidatos = Array.from(
                    document.querySelectorAll('button, a, span, i, [role="button"]')
                );

                // ── Estratégia 0 (mais segura): procura o botão dentro do container do did ──
                // Usa confirma-dados-deducao-{did} como âncora e sobe até 12 níveis
                // buscando o botão Pré-Doc DENTRO de cada container intermediário.
                // Mais robusto que .closest() para DOM pesado com múltiplos painéis.
                {
                    const ancora = document.getElementById(`confirma-dados-deducao-${deducaoId}`)
                        || document.getElementById(`aba-deducao${deducaoId}`);
                    if (ancora) {
                        let nivel = ancora;
                        for (let lvl = 0; lvl < 12; lvl++) {
                            nivel = nivel.parentElement;
                            if (!nivel) break;
                            const btn = Array.from(
                                nivel.querySelectorAll('button, a, span, i, [role="button"]')
                            ).find((el) => {
                                if (!visivel(el)) return false;
                                const classe  = normalizar(el.className || '');
                                const onclick = normalizar(el.getAttribute?.('onclick') || '');
                                const titulo  = normalizar(el.getAttribute?.('title') || el.getAttribute?.('aria-label') || '');
                                return classe.includes('predoc') || onclick.includes('predoc') || titulo.includes('predoc');
                            });
                            if (btn && clicar(btn)) return 'container-predoc-v2';
                        }
                    }
                }

                // ── Estratégia 1: onclick contém "predoc" (case-insensitive) ──
                const porOnclickPredoc = candidatos.find(
                    (el) => visivel(el) && normalizar(el.getAttribute('onclick') || '').includes('predoc')
                );
                if (clicar(porOnclickPredoc)) return 'onclick-predoc';

                // ── Estratégia 2: onclick contém o did exato ──
                const porOnclick = candidatos.find(
                    (el) => visivel(el) && String(el.getAttribute('onclick') || '').includes(deducaoId)
                );
                if (clicar(porOnclick)) return 'onclick-did';

                // ── Estratégia 3: cabeçalho "Pré-Doc" → botão "+" vizinho ─────
                const cabecalhosPredoc = Array.from(
                    document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span,td,th,label,strong,p,caption')
                ).filter((el) => {
                    if (!visivel(el)) return false;
                    const txt = normalizar(el.textContent || el.getAttribute('title') || '');
                    return /^pr[eé].?doc$/i.test(txt) || txt === 'pr\u00e9-doc' || txt === 'pre-doc';
                });
                for (const cab of cabecalhosPredoc.reverse()) {
                    let bloco = cab;
                    for (let i = 0; i < 4; i++) {
                        bloco = bloco.parentElement;
                        if (!bloco) break;
                        const btnMais = Array.from(
                            bloco.querySelectorAll('button, a, span, i, [role="button"]')
                        ).find((el) => {
                            const txt = normalizar(el.textContent || '');
                            return visivel(el) && (
                                txt === '+'
                                || el.querySelector?.('.fa-plus, .glyphicon-plus, [class*="plus"]')
                                || normalizar(el.getAttribute?.('onclick') || '').includes('predoc')
                                || normalizar(el.className || '').includes('predoc')
                            );
                        });
                        if (btnMais && clicar(btnMais)) return 'predoc-header';
                    }
                }

                // ── Estratégia 4 (fallback): último "+" que NÃO esteja dentro de
                //    "Lista dos Recolhedores" ou similar ──
                const botoesMais = candidatos.filter((el) => {
                    if (!visivel(el)) return false;
                    const txt = normalizar(el.textContent || '');
                    if (txt !== '+') return false;
                    // Exclui botões cujo ancestral contenha "recolhedor" no texto
                    let pai = el.parentElement;
                    for (let i = 0; i < 6 && pai; i++) {
                        const paiTxt = normalizar(pai.textContent || '');
                        if (paiTxt.includes('recolhedor') && !paiTxt.includes('predoc')) return false;
                        pai = pai.parentElement;
                    }
                    return true;
                });
                const ultimo = botoesMais.pop();
                if (clicar(ultimo)) return 'global-mais';

                return '';
            }""",
            did,
        )
        if not clicou:
            erros.append("Pré-Doc: botão '+' não encontrado.")
            return ""

        log.debug("Pré-Doc '+' clicado via estratégia: %s", clicou)

        # ── 4. Aguarda campos sfpredoc* ficarem VISÍVEIS no DOM ──────────────
        # Não esperamos novos IDs (em DDF055 os elementos já existem no DOM
        # mas ficam ocultos até o "+" ser clicado). Detectamos pela visibilidade.
        pagina.wait_for_function(
            """(deducaoId) => {
                const prefixos = [
                    'sfpredoccodrecurso', 'sfpredocreferencia', 'sfpredocnumref',
                    'sfpredoctxtprocesso', 'sfpredocdtprdoapuracao', 'sfpredoccodmuninf',
                    'sfpredocnumnf', 'sfpredocdtemisnf', 'sfpredocvlrnf',
                    'sfpredoctxtobser', 'sfpredoccodugtmdrserv', 'sfpredocnumaliqnf',
                ];
                const visivel = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                };
                const ancora =
                    document.getElementById(`confirma-dados-deducao-${deducaoId}`)
                    || document.getElementById(`aba-deducao${deducaoId}`)
                    || document.getElementById(`sfdeducaocodsit${deducaoId}`)
                    || document.getElementById(`sfdeducaovlr${deducaoId}`);
                let nivel = ancora;
                for (let i = 0; i < 12 && nivel; i += 1) {
                    const encontrados = Array.from(nivel.querySelectorAll('[id]')).filter((el) => {
                        const id = String(el.id || '');
                        return prefixos.some((p) => id.startsWith(p)) && visivel(el);
                    });
                    if (encontrados.length) return true;
                    nivel = nivel.parentElement;
                }
                return false;
            }""",
            arg=did,
            timeout=15000,
        )
        ids_depois = _coletar_ids_predoc_do_did(pagina, did, apenas_visiveis=True)

        pdid = _extrair_pdid_de_ids(set(ids_depois or []))
        if not pdid:
            # fallback: usa did caso não consiga extrair pdid dos novos elementos
            log.warning(
                "Pré-Doc abriu mas pdid não detectado em %s; usando did=%s como fallback.",
                ids_depois, did,
            )
            pdid = did

        log.debug("Pré-Doc aberto; pdid=%s  (did=%s)", pdid, did)
        return pdid

    except Exception as e:
        erros.append(f"Pré-Doc — abrir: {e}")
        return ""


def _fill_aliquota_nf(pagina, fid: str, aliquota_pct: float, erros: list):
    esperado = round(float(aliquota_pct or 0.0), 4)
    variacoes = [
        f"{esperado:.4f}".replace(".", ","),
        f"{esperado:.4f}",
        f"{esperado:.2f}".replace(".", ","),
    ]

    def _parse_aliquota(valor_raw: str) -> float | None:
        texto = str(valor_raw or "").strip()
        if not texto:
            return None
        candidatos = [texto]
        if "." in texto and "," in texto:
            candidatos.append(texto.replace(".", "").replace(",", "."))
            candidatos.append(texto.replace(",", ""))
        elif "," in texto:
            candidatos.append(texto.replace(".", "").replace(",", "."))
        for candidato in candidatos:
            try:
                valor = float(candidato)
            except Exception:
                continue
            if valor > 1000:
                valor = valor / 1000
            if valor > 100:
                valor = valor / 100
            return valor
        return None

    try:
        loc = pagina.locator(f"#{fid}")
        loc.wait_for(state="visible", timeout=15000)  # 15s para DOM pesado (4ª NF)
        ultimo_lido = ""
        for tentativa in variacoes:
            loc.click(click_count=3)
            try:
                loc.fill("")
            except Exception:
                pass
            loc.fill(tentativa)
            pagina.keyboard.press("Tab")
            ultimo_lido = _read_input_value(pagina, fid)
            valor_lido = _parse_aliquota(ultimo_lido)
            if valor_lido is not None and abs(valor_lido - esperado) <= 0.01:
                return
        raise RuntimeError(f"campo ficou com '{ultimo_lido or 'vazio'}'")
    except Exception as e:
        erros.append(f"PrÃƒÂ©-Doc/AlÃƒÂ­quota: {e}")


def _preencher_predoc(pagina, did: str, nf: dict, recurso: str,
                      cod_mun: str, municipio_nf_nome: str,
                      aliquota_pct: float, dados: dict, erros: list,
                      pdid_pre: str = ""):
    """Preenche o Pré-Doc de um DDR001.
    Abre o formulário, detecta o pdid real e preenche todos os campos.

    pdid_pre: pdid pré-detectado durante a fase de pré-expansão.
              Se fornecido e os campos ainda estiverem visíveis, evita
              uma nova chamada a _abrir_predoc_resiliente (mais robusto
              para DOM pesado com múltiplos painéis de dedução).
    """
    print("    → Pré-Doc DDR001")

    # ── Tenta reutilizar pdid da pré-expansão se campos ainda visíveis ──────
    pdid = ""
    if pdid_pre:
        try:
            campos_visiveis = pagina.evaluate(
                """(pdid) => {
                    const visivel = (el) => {
                        if (!el) return false;
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 && r.height === 0) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    };
                    const prefs = [
                        'sfpredoctxtprocesso', 'sfpredocnumref',
                        'sfpredocdtprdoapuracao', 'sfpredoctxtobser',
                        'sfpredoccodrecurso',
                    ];
                    return prefs.some(p => visivel(document.getElementById(p + pdid)));
                }""",
                pdid_pre,
            )
            if campos_visiveis:
                pdid = pdid_pre
                print(f"      [Predoc] reutilizando pdid pré-expansão: {pdid}")
        except Exception:
            pass

    # ── Abre Pré-Doc se necessário (campos não visíveis ou sem pdid_pre) ────
    if not pdid:
        pdid = _abrir_predoc_resiliente(pagina, did, erros)

    if not pdid:
        erros.append(
            f"DDR001 (did={did}): Pré-Doc não pôde ser aberto — "
            "confirmação pode falhar por falta de dados do pré-doc."
        )
        return

    print(f"      pdid={pdid}")

    # ── Dados da NF ─────────────────────────────────────────────────────────
    data_emissao = _normalizar_data(nf.get('Data de Emissão', '') or nf.get('Data de Emissao', ''))
    num_nf       = nf.get('Número da Nota', '') or nf.get('Numero da Nota', '')
    nf_val_br    = _formatar_valor_br(nf.get('Valor', ''))
    referencia   = _referencia(nf.get('Data de Emissão', '') or nf.get('Data de Emissao', ''))
    municipio_nf_nome = str(municipio_nf_nome or "").strip()
    cod_mun_nf = _codigo_municipio_por_nome(municipio_nf_nome, default=cod_mun)
    obs          = _montar_observacao(dados, cod_mun)

    # ── Recurso (SELECT: "1", "2" ou "3") ───────────────────────────────────
    _select_com_fallback(
        pagina,
        f"sfpredoccodrecurso{pdid}",
        [str(recurso), "0", "1"],
        erros,
        "Pré-Doc/Recurso",
    )

    # ── Município PRIMEIRO — o AJAX do município pode resetar campos de NF ───
    # Chamamos ANTES do batch fill para que o retorno do servidor não desfaça
    # os valores que preencheremos logo a seguir.
    _preencher_municipio_por_codigo(
        pagina,
        f"sfpredoccodmuninf{pdid}",
        f"municipioDeducaoPreDoc{pdid}",
        cod_mun_nf,
        municipio_nf_nome,
        pdid,
        "municipioDeducaoPreDoc",
        erros,
        "Pré-Doc/Município NF",
    )

    # ── Batch fill: Referência, UG Tomadora, Número NF, Série, Valor NF, Obs ─
    # Executado DEPOIS do AJAX do município para evitar reset dos campos de NF.
    campos_batch: dict = {
        f"sfpredocreferencia{pdid}": referencia,
        f"sfpredoccodugtmdrserv{pdid}": _UG_TOMADORA,
        f"sfpredocnumnf{pdid}": num_nf,
        f"sfpredoctxtserienf{pdid}": "1",
        f"sfpredocvlrnf{pdid}": nf_val_br,
        f"sfpredoctxtobser{pdid}": obs,
    }
    try:
        _batch_fill(pagina, campos_batch)
    except Exception as e:
        erros.append(f"Pré-Doc/batch: {e}")

    # ── Data de Emissão da NF (campo de data, requer helper dedicado) ────────
    if data_emissao:
        _fill_date(pagina, f"sfpredocdtemisnf{pdid}", data_emissao, erros, "Pré-Doc/Data Emissão NF")

    # ── Alíquota da NF (campo mascarado, requer helper dedicado) ─────────────
    _fill_aliquota_nf(pagina, f"sfpredocnumaliqnf{pdid}", aliquota_pct, erros)


def _preencher_predoc_darf(
    pagina,
    did: str,
    apuracao: str,
    processo: str,
    observacao: str,
    erros: list,
    recurso: str = "0",
    vinculacao: str = "400",
) -> bool:
    """Preenche o Pré-Doc para DDF050/DDF055.
    Abre o formulário, detecta o pdid real e preenche todos os campos.
    Retorna True se conseguiu preencher os campos obrigatórios (Observação),
    False caso contrário.
    """
    print("    → Pré-Doc DARF")

    # ── Abre Pré-Doc e obtém o pdid real ────────────────────────────────────
    pdid = _abrir_predoc_resiliente(pagina, did, erros)
    if not pdid:
        erros.append("Pré-Doc DARF: não foi possível abrir o formulário (pdid vazio).")
        return False

    print(f"      pdid={pdid}  apuracao='{apuracao}'  processo='{processo}'")

    # ── Diagnóstico: quais IDs sfpredoc existem e quais estão visíveis ──────
    _dbg = pagina.evaluate(
        """(pdid) => {
            const prefixos = [
                'sfpredoccodrecurso', 'sfpredocdtprdoapuracao', 'sfpredoctxtprocesso',
                'sfpredocnumref', 'sfpredoctxtobser',
            ];
            const visivel = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return false;
                const s = window.getComputedStyle(el);
                return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            };
            return prefixos.map(p => {
                const id = p + pdid;
                const el = document.getElementById(id);
                return id + ':' + (el ? (visivel(el) ? 'visível' : 'oculto') : 'não-existe');
            }).join(' | ');
        }""",
        pdid,
    )
    print(f"      campos: {_dbg}")

    erros_antes = len(erros)

    # ── Recurso ──────────────────────────────────────────────────────────────
    _select_com_fallback(
        pagina,
        f"sfpredoccodrecurso{pdid}",
        [str(recurso), "0", "1"],
        erros,
        "Pré-Doc/Recurso",
    )

    # ── Batch fill: Processo, Vinculação, Observação ──────────────────────────
    campos_darf: dict = {}
    if processo:
        campos_darf[f"sfpredoctxtprocesso{pdid}"] = processo
    campos_darf[f"sfpredocnumref{pdid}"] = vinculacao
    campos_darf[f"sfpredoctxtobser{pdid}"] = observacao
    obs_ok = False
    try:
        _batch_fill(pagina, campos_darf)
        obs_ok = bool(observacao)
    except Exception as e:
        erros.append(f"Pré-Doc/batch DARF: {e}")

    # ── Período de Apuração — setado em SILÊNCIO, sem eventos ────────────────
    # Qualquer método que dispare change/input/blur neste campo (loc.fill, ISO
    # setter com eventos, press_sequentially+Tab) aciona um handler jQuery que
    # reseta o formulário inteiro (Recurso→"0", Processo/Vinc/Obs somem).
    # Solução: setar el.value diretamente sem nenhum evento, exatamente como
    # fizemos para txtinscra{did}. O valor fica no DOM e é enviado no submit.
    if apuracao:
        try:
            partes = re.split(r"[/\-]", str(apuracao).strip())
            if len(partes) == 3:
                dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
                iso_ap = f"{aaaa}-{mm}-{dd}"
                pagina.evaluate(
                    """([id, val]) => {
                        const el = document.getElementById(id);
                        if (!el) return false;
                        const setter = Object.getOwnPropertyDescriptor(
                            HTMLInputElement.prototype, 'value')?.set;
                        if (setter) setter.call(el, val); else el.value = val;
                        el.defaultValue = val;
                        el.setAttribute('value', val);
                        // SEM eventos — evita reset do formulário pelo handler jQuery
                        return true;
                    }""",
                    [f"sfpredocdtprdoapuracao{pdid}", iso_ap],
                )
        except Exception as e:
            erros.append(f"Pré-Doc/Período de Apuração: {e}")

    novos_erros = erros[erros_antes:]
    if novos_erros:
        print(f"      ⚠ erros no Pré-Doc: {'; '.join(str(e) for e in novos_erros)}")

    return obs_ok


def _revalidar_ddr001_antes_confirmar(
    pagina,
    did: str,
    nf: dict,
    cod_mun: str,
    nome_mun: str,
    cod_receita: str,
    iss_br: str,
    aliquota_nf_pct: float,
    rid_pre: str,
    pdid_pre: str,
    erros: list,
) -> None:
    """Reaplica campos críticos do DDR001 quando o portal reseta algo no fim.

    O problema aparece com mais frequência a partir da 4ª NF, quando o DOM fica
    mais pesado e alguns AJAX tardios limpam parcialmente campos já preenchidos.
    """
    try:
        ug_id = f"sfdeducaocodugpgto{did}"
        if _read_input_value(pagina, ug_id) != _UG_TOMADORA:
            print(f"    [Revalidacao DDR001] UG divergente em {ug_id} — repreenchendo.")
            _fill(pagina, ug_id, _UG_TOMADORA, erros, "UG Pagadora na revalidacao")
    except Exception as e:
        erros.append(f"Revalidacao DDR001/UG Pagadora: {e}")

    try:
        valor_id = f"sfdeducaovlr{did}"
        if not _valor_campo_equivalente(_read_input_value(pagina, valor_id), iss_br):
            print(f"    [Revalidacao DDR001] Valor do Item divergente em {valor_id} — repreenchendo.")
            _fill_money(pagina, valor_id, iss_br, erros, "Valor do Item na revalidacao")
    except Exception as e:
        erros.append(f"Revalidacao DDR001/Valor do Item: {e}")

    try:
        receita_id = f"txtinscrb{did}"
        if cod_receita and _read_input_value(pagina, receita_id).strip() != str(cod_receita).strip():
            print(f"    [Revalidacao DDR001] Codigo de Receita divergente em {receita_id} — repreenchendo.")
            _fill(pagina, receita_id, cod_receita, erros, "Codigo de Receita na revalidacao")
    except Exception as e:
        erros.append(f"Revalidacao DDR001/Codigo de Receita: {e}")

    try:
        rid = rid_pre or _obter_rid(pagina, did)
        if rid:
            receita_recolh_id = f"vlrPrincipal{did}{rid}"
            if not _valor_campo_equivalente(_read_input_value(pagina, receita_recolh_id), iss_br):
                print(
                    f"    [Revalidacao DDR001] Valor da Receita divergente em {receita_recolh_id} — repreenchendo."
                )
                _fill_money(
                    pagina,
                    receita_recolh_id,
                    iss_br,
                    erros,
                    "Valor da Receita na revalidacao",
                )
    except Exception as e:
        erros.append(f"Revalidacao DDR001/Recolhedor: {e}")

    try:
        pdid = pdid_pre or _obter_pdid_do_did(pagina, did, apenas_visiveis=True)
        if pdid:
            num_nf = str(
                nf.get("Número da Nota", "")
                or nf.get("Numero da Nota", "")
                or ""
            ).strip()
            valor_nf = _formatar_valor_br(nf.get("Valor", "0"))
            nf_id = f"sfpredocnumnf{pdid}"
            valor_nf_id = f"sfpredocvlrnf{pdid}"
            aliquota_nf_id = f"sfpredocnumaliqnf{pdid}"
            mun_nf_id = f"sfpredoccodmuninf{pdid}"

            if num_nf and _read_input_value(pagina, nf_id).strip() != num_nf:
                print(f"    [Revalidacao DDR001] Numero da NF divergente em {nf_id} — repreenchendo.")
                _fill(pagina, nf_id, num_nf, erros, "Pre-Doc/NF na revalidacao")

            if not _valor_campo_equivalente(_read_input_value(pagina, valor_nf_id), valor_nf):
                print(f"    [Revalidacao DDR001] Valor da NF divergente em {valor_nf_id} — repreenchendo.")
                _fill_money(
                    pagina,
                    valor_nf_id,
                    valor_nf,
                    erros,
                    "Pre-Doc/Valor NF na revalidacao",
                )

            if str(_read_input_value(pagina, mun_nf_id) or "").strip() != str(cod_mun).strip():
                print(f"    [Revalidacao DDR001] Municipio da NF divergente em {mun_nf_id} — repreenchendo.")
                _preencher_municipio_por_codigo(
                    pagina,
                    mun_nf_id,
                    f"municipioDeducaoPreDoc{pdid}",
                    cod_mun,
                    nome_mun,
                    pdid,
                    "municipioDeducaoPreDoc",
                    erros,
                    "Pre-Doc/Municipio NF na revalidacao",
                )

            valor_aliquota = _read_input_value(pagina, aliquota_nf_id)
            try:
                atual = float(str(valor_aliquota or "0").replace(".", "").replace(",", "."))
            except Exception:
                atual = None
            if atual is None or abs(atual - float(aliquota_nf_pct or 0.0)) > 0.01:
                print(f"    [Revalidacao DDR001] Aliquota da NF divergente em {aliquota_nf_id} — repreenchendo.")
                _fill_aliquota_nf(
                    pagina,
                    aliquota_nf_id,
                    aliquota_nf_pct,
                    erros,
                )
    except Exception as e:
        erros.append(f"Revalidacao DDR001/Pre-Doc: {e}")


def _preencher_ddr001_nf(pagina, nf: dict, idx: int, total: int,
                          cod_mun: str, nome_mun: str, cod_receita: str,
                          data_venc: str, recurso: str, aliquota_pct: float,
                          iss_nf: float, cnpj_fmt: str,
                          dados: dict, erros: list, deve_parar=None):
    """Cria e preenche uma entrada DDR001 para uma Nota Fiscal especÃ­fica."""

    iss_br  = _formatar_valor_br(f"{iss_nf:.2f}")
    num_nf = (
        nf.get("Número da Nota", "")
        or nf.get("Numero da Nota", "")
        or nf.get("NÃºmero da Nota", "")
    )
    print(f"  â†’ DDR001 NF {num_nf} [{idx+1}/{total}]  ISS={iss_br}  Venc={data_venc}")
    _verificar_interrupcao(deve_parar)
    _garantir_sem_deducao_em_edicao(pagina, timeout_ms=30000)

    # â"€â"€ 1. Cria nova deduÃ§Ã£o â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    did = _clicar_nova_deducao(pagina)
    _verificar_interrupcao(deve_parar)

    # â"€â"€ 2. ObtÃ©m ID dinÃ¢mico da deduÃ§Ã£o â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    did = did or _obter_did(pagina)
    if not did:
        erros.append(f"DDR001 NF {num_nf}: nÃ£o obteve ID da deduÃ§Ã£o — abortando esta entrada.")
        return False
    print(f"    did={did}")

    # ── 3. Situação → DDR001 (com retry — AJAX pode resetar o select) ───────────
    try:
        _esperar_formulario_deducao_estabilizar(pagina, did, timeout_ms=30000)
    except Exception:
        pass

    _situacao_ok = False
    for _tent_sit in range(3):
        _select(pagina, f"sfdeducaocodsit{did}", "DDR001", erros, "Situação")
        time.sleep(0.8)
        try:
            # Verifica pelo TEXTO da opção selecionada (value é código numérico)
            _texto_sit = pagina.evaluate(
                f"() => {{ const el = document.getElementById('sfdeducaocodsit{did}'); "
                f"if (!el) return ''; "
                f"const op = el.options[el.selectedIndex]; "
                f"return op ? op.text.trim() : ''; }}"
            )
            if "DDR001" in str(_texto_sit or "").upper():
                _situacao_ok = True
                break
            print(f"    [DDR001] Situação ainda ‘{_texto_sit}’ — retry {_tent_sit+1}/3")
        except Exception:
            _situacao_ok = True  # se não conseguiu verificar, assume ok
            break
    if not _situacao_ok:
        erros.append(f"DDR001 NF {num_nf}: portal não aceitou situação DDR001 — abortando.")
        return False

    try:
        _esperar_formulario_deducao_estabilizar(pagina, did, timeout_ms=30000)
    except Exception:
        pass
    _verificar_interrupcao(deve_parar)

    # â"€â"€ PRÉ-EXPANSÃO: abre recolhedor E pré-doc ANTES de preencher qualquer campo ─
    print(f"    [Pré-expansão DDR001] Abrindo recolhedor e pré-doc...")
    rid_expandido: str = ""
    try:
        pagina.locator(f"#novo-recolhedor{did}").wait_for(state="visible", timeout=30000)
    except Exception as ex_wait_rid:
        print(f"      [Aviso] novo-recolhedor{did} não visível em 30s: {ex_wait_rid}")
    for _tent_rid in range(3):  # 3 tentativas para dom mais pesado
        try:
            rid_ant = _obter_rid(pagina, did)
            pagina.locator(f"#novo-recolhedor{did}").click()
            rid_expandido = _aguardar_novo_recolhedor(pagina, did, rid_anterior=rid_ant, timeout_ms=30000)
            print(f"      recolhedor aberto: rid={rid_expandido}")
            break
        except Exception as ex_rid:
            rid_expandido = _obter_rid(pagina, did)
            print(f"      recolhedor: rid fallback={rid_expandido} (tentativa {_tent_rid+1}: {ex_rid})")
            if rid_expandido:
                break
            time.sleep(2.0)  # wait entre tentativas

    predoc_pdid_pre: str = ""
    try:
        predoc_pdid_pre = _abrir_predoc_resiliente(pagina, did, erros)
        print(f"      pré-doc aberto: pdid={predoc_pdid_pre}")
    except Exception as ex_pdid:
        print(f"      pré-doc: falhou ao pré-abrir ({ex_pdid})")

    # Aguarda o AJAX de expansao terminar antes de preencher (buffer maior para dom pesado)
    time.sleep(1.5)
    _verificar_interrupcao(deve_parar)

    # â"€â"€ 4. UG pagadora e valor â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    _fill(pagina, f"sfdeducaocodugpgto{did}", _UG_TOMADORA, erros, "UG Pagadora")

    # â"€â"€ 5. Valor do Item (ISS desta NF) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    _fill(pagina, f"sfdeducaovlr{did}", iss_br, erros, "Valor do Item")

    # â"€â"€ 7. CÃ³digo do MunicÃ­pio — preenche campo e chama buscaMunicipioPorCod()
    if _preencher_municipio_por_codigo(
        pagina,
        f"txtinscra{did}",
        f"municipioDeducao{did}",
        cod_mun,
        nome_mun,
        did,
        "municipioDeducao",
        erros,
        "CÃ³digo do MunicÃ­pio",
    ):
        print(f"    MunicÃ­pio selecionado: {nome_mun}")

    # â"€â"€ 9. CÃ³digo de Receita â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    # Codigo de Receita: aguarda campo estabilizar apos AJAX do municipio,
    # depois preenche com retry para sobreviver a qualquer reset residual do portal.
    if cod_receita:
        fid_receita = f"txtinscrb{did}"
        # Aguarda o campo existir e estar editavel (AJAX do municipio pode demorar)
        try:
            pagina.wait_for_function(
                """(fid) => {
                    const el = document.getElementById(fid);
                    return !!el && !el.disabled && !el.readOnly && el.offsetParent !== null;
                }""",
                fid_receita,
                timeout=6000,
            )
        except Exception:
            pass  # campo pode nao existir -- _fill vai tratar

        preenchido_receita = False
        for _tent_rec in range(3):
            _fill(pagina, fid_receita, cod_receita, erros if _tent_rec == 2 else [], "Codigo de Receita")
            time.sleep(0.35)
            valor_atual = _read_input_value(pagina, fid_receita)
            if str(valor_atual or "").strip() == str(cod_receita).strip():
                preenchido_receita = True
                break
            print(f"    [Receita] tentativa {_tent_rec+1}: esperado={cod_receita!r} atual={valor_atual!r} - repreenchendo...")
        if preenchido_receita:
            print(f"    Codigo de Receita preenchido: {cod_receita}")
        else:
            erros.append(f"Codigo de Receita (txtinscrb{did}): nao fixou apos 3 tentativas (ultimo valor: {valor_atual!r})")

    # â"€â"€ 10. Possui AcrÃ©scimo = NÃƒO â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    _select(pagina, f"sfdeducaopossui_acrescimo{did}", "NÃƒO", erros, "Possui AcrÃ©scimo")

    # â"€â"€ 11. Recolhedor (rid já obtido — SEM clicar no ‘+’ de novo) ────────────
    print(f"    [11] Recolhedor / Valor da Receita={iss_br}")
    if _preencher_valor_recolhedor(pagina, did, cnpj_fmt, iss_br, erros, rid_pre_aberto=rid_expandido):
        print(f"    Valor da Receita preenchido ({iss_br})")
    else:
        erros.append(f"DDR001 NF {num_nf}: nÃ£o conseguiu preencher o Valor da Receita do recolhedor (did={did}).")
        return False

    # â"€â"€ 12. PrÃ©-Doc (seção já aberta — _abrir_predoc_resiliente não reclica) ──
    municipio_nf_nome = nome_mun
    # Aliquota efetiva por NF = ISS_NF / Valor_NF x 100 (ex: 1706,07 / 68242,70 = 2,50%).
    # NAO usa aliquota_pct global (ISS_total / Base_Calculo_PDF) que reflete a taxa
    # municipal sobre a parcela de servicos (ex: 15,50%), gerando percentual errado.
    try:
        _nf_val_float = float(normalizar_valor(str(nf.get("Valor", "0") or "0")) or "0")
        aliquota_predoc = round(iss_nf / _nf_val_float * 100, 4) if _nf_val_float else aliquota_pct
    except Exception:
        aliquota_predoc = aliquota_pct
    print(f"    [Predoc] aliquota efetiva: {aliquota_predoc:.4f}% (iss={iss_nf:.2f} / nf={_nf_val_float:.2f})")
    _preencher_predoc(pagina, did, nf, recurso,
                      cod_mun, municipio_nf_nome,
                      aliquota_predoc, dados, erros,
                      pdid_pre=predoc_pdid_pre)
    _verificar_interrupcao(deve_parar)

    # â"€â"€ Datas — SILENTES, absolutamente por último (após pré-doc) ─────────────
    # Garantimos aqui que nenhum AJAX posterior apague as datas.
    _fill_date_silente(pagina, f"sfdeducaodtvenc{did}", data_venc, erros, "Data de Vencimento")
    _fill_date_silente(pagina, f"sfdeducaodtpgtoreceb{did}", data_venc, erros, "Data de Pagamento")

    # â"€â"€ 12b. ValidaÃ§Ã£o final do topo antes da confirmaÃ§Ã£o â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    try:
        codigo_mun_atual = _read_input_value(pagina, f"txtinscra{did}")
        if str(codigo_mun_atual or "").strip() != str(cod_mun):
            print(
                f"    CÃ³digo do MunicÃ­pio divergente antes da confirmaÃ§Ã£o "
                f"(atual: '{codigo_mun_atual or 'vazio'}', esperado: '{cod_mun}'). Repreenchendo..."
            )
            _preencher_municipio_por_codigo(
                pagina,
                f"txtinscra{did}",
                f"municipioDeducao{did}",
                cod_mun,
                nome_mun,
                did,
                "municipioDeducao",
                erros,
                "MunicÃ­pio na revalidaÃ§Ã£o",
            )
    except Exception as e:
        erros.append(f"RevalidaÃ§Ã£o do CÃ³digo do MunicÃ­pio: {e}")

    _revalidar_ddr001_antes_confirmar(
        pagina,
        did,
        nf,
        cod_mun,
        nome_mun,
        cod_receita,
        iss_br,
        aliquota_predoc,
        rid_expandido,
        predoc_pdid_pre,
        erros,
    )

    _verificar_interrupcao(deve_parar)
    # ── 13. Confirmar (atômico: seta datas + clica no mesmo tick JS) ─────────
    print(f"    [13] Confirmando dedução (did={did})")
    return _confirmar_com_datas_atomico(pagina, did, data_venc, erros)


def _confirmar_com_datas_atomico(pagina, did: str, data_ddmmaaaa: str, erros: list) -> bool:
    """
    Seta as datas de vencimento/pagamento via JS (sem eventos) e imediatamente
    clica o botão Confirmar via Playwright (clique trusted — isTrusted=true).

    Estratégia em dois passos:
    1. JS: setter via prototype → seta campo type='date' com ISO sem disparar eventos
    2. Playwright: loc.click() → clique real, trusted, que o portal aceita
    O intervalo entre os dois é mínimo (apenas a chamada Python ao btn.click),
    sem janela para AJAX ou JS do portal resetar os valores.
    """
    partes = re.split(r"[/\-]", str(data_ddmmaaaa).strip())
    if len(partes) != 3:
        erros.append(f"Data inválida para confirm atômico: '{data_ddmmaaaa}'")
        return False
    if len(partes[0]) == 4:
        aaaa, mm, dd = partes[0], partes[1].zfill(2), partes[2].zfill(2)
    else:
        dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
    iso = f"{aaaa}-{mm}-{dd}"

    ultimo_resultado = "SEM_TENTATIVA"
    ultimo_erro_click = None
    ultimo_erro_aguardo = None

    for tentativa in range(1, 4):
        # Passo 0 — aguarda o botão Confirmar ficar habilitado (portal valida assíncrono)
        # A partir da 4ª DDR001 o DOM fica mais pesado e o portal pode levar mais tempo.
        try:
            pagina.wait_for_function(
                """(did) => {
                    const btn = document.getElementById('confirma-dados-deducao-' + did);
                    return !!btn && !btn.disabled;
                }""",
                did,
                timeout=20000,
            )
        except Exception:
            pass  # O evaluate abaixo registra o estado real do botão

        # Passo 1 — seta as duas datas silenciosamente (sem eventos)
        try:
            resultado = pagina.evaluate(
                """([did, iso]) => {
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                    const setData = (id) => {
                        const el = document.getElementById(id);
                        if (!el) return 'NAO_ENCONTRADO:' + id;
                        if (setter) setter.call(el, iso); else el.value = iso;
                        el.defaultValue = iso;
                        el.setAttribute('value', iso);
                        return el.value;
                    };
                    const vencVal = setData('sfdeducaodtvenc' + did);
                    const pgtoVal = setData('sfdeducaodtpgtoreceb' + did);
                    const btn = document.getElementById('confirma-dados-deducao-' + did);
                    if (!btn) return 'SEM_BTN:venc=' + vencVal + ':pgto=' + pgtoVal;
                    if (btn.disabled) return 'BTN_DISABLED:venc=' + vencVal + ':pgto=' + pgtoVal;
                    btn.scrollIntoView({ block: 'center' });
                    return 'OK:venc=' + vencVal + ':pgto=' + pgtoVal;
                }""",
                [did, iso],
            ) or "EVAL_ERRO"
        except Exception as e_eval:
            resultado = f"EVAL_ERRO:{e_eval}"

        ultimo_resultado = resultado
        print(f"    [Confirmar] tentativa {tentativa}/3 did={did} iso={iso} | datas setadas → {resultado}")

        if not resultado.startswith("OK"):
            if tentativa < 3:
                time.sleep(1.2)
                continue
            erros.append(f"Confirmar dedução (did={did}): {resultado}")
            return False

        # Passo 2 — clica via Playwright (trusted, aceito pelo portal)
        try:
            btn_loc = pagina.locator(f"#confirma-dados-deducao-{did}")
            btn_loc.wait_for(state="visible", timeout=5000)
            btn_loc.click()
        except Exception as e_click:
            ultimo_erro_click = e_click
            try:
                pagina.locator("[name='confirma-dados-deducao']:visible").last.click()
                ultimo_erro_click = None
            except Exception:
                if tentativa < 3:
                    time.sleep(1.2)
                    continue
                erros.append(f"Confirmar dedução (did={did}): não conseguiu clicar — {e_click}")
                return False

        # Passo 3 — aguarda confirmação
        try:
            _aguardar_confirmacao_deducao(pagina, did, timeout_ms=20000)
            _aguardar_proxima_deducao_liberada(pagina, did, timeout_ms=20000)
            print("    Dedução confirmada.")
            return True
        except Exception as e_aw:
            ultimo_erro_aguardo = e_aw
            print(f"    [Confirmar] tentativa {tentativa}/3 aguardando confirmação falhou: {e_aw}")
            if tentativa < 3:
                time.sleep(1.5)
                continue

    detalhe = ultimo_resultado
    if ultimo_erro_click:
        detalhe += f" | clique={ultimo_erro_click}"
    if ultimo_erro_aguardo:
        detalhe += f" | aguardo={ultimo_erro_aguardo}"
    erros.append(f"Confirmar dedução (did={did}): {detalhe}")
    return False


def _preencher_deducao_darf_total(
    pagina,
    ded: dict,
    idx: int,
    total: int,
    siafi: str,
    data_venc: str,
    data_apuracao: str,
    processo: str,
    cnpj_fmt: str,
    dados: dict,
    erros: list,
    recurso: str = "0",
    deve_parar=None,
):
    valor_item_br = _formatar_valor_br(_ded_valor(ded))
    base_calculo_br = _formatar_valor_br(_ded_base_calculo(ded))
    codigo_pdf = _ded_codigo(ded)
    codigo_darf = "1162" if siafi == "DDF050" else codigo_pdf
    natureza = str(ded.get("Rendimento", "") or "").strip()
    observacao = _montar_observacao_darf(
        dados,
        "IN 2110/22" if siafi == "DDF050" else "IN 1234/12",
    )

    detalhe_codigo = f"  Código={codigo_darf}" if codigo_darf else ""
    detalhe_rendimento = f"  Rendimento={natureza}" if siafi != "DDF050" and natureza and natureza != "—" else ""
    print(
        f"  â†’ {siafi} [{idx+1}/{total}]"
        f"{detalhe_codigo}{detalhe_rendimento}  Valor={valor_item_br}  Venc={data_venc}"
    )
    _verificar_interrupcao(deve_parar)
    _garantir_sem_deducao_em_edicao(pagina, timeout_ms=8000)

    did = _clicar_nova_deducao(pagina)
    _verificar_interrupcao(deve_parar)
    if not did:
        erros.append(f"{siafi}: não obteve ID da nova dedução após clicar no '+'. "
                     "O portal pode não ter criado um novo formulário.")
        return False
    print(f"    did={did}")

    # Espera o formulário estabilizar ANTES de selecionar — sem isso, quando
    # DDF055 é o único tipo de dedução, o AJAX ainda não carregou as opções
    # do select e o _select falha silenciosamente (igual ao padrão DDR001).
    try:
        _esperar_formulario_deducao_estabilizar(pagina, did, timeout_ms=15000)
    except Exception:
        pass

    # Seleciona Situação com retry — AJAX pode resetar o select (igual DDR001)
    _situacao_ok = False
    for _tent_sit in range(3):
        _select(pagina, f"sfdeducaocodsit{did}", siafi, erros, f"Situação ({siafi})")
        time.sleep(0.8)
        try:
            _texto_sit = pagina.evaluate(
                f"() => {{ const el = document.getElementById('sfdeducaocodsit{did}'); "
                f"if (!el) return ''; "
                f"const op = el.options[el.selectedIndex]; "
                f"return op ? op.text.trim() : ''; }}"
            )
            if siafi.upper() in str(_texto_sit or "").upper():
                _situacao_ok = True
                break
            print(f"    [{siafi}] Situação ainda '{_texto_sit}' — retry {_tent_sit+1}/3")
        except Exception:
            _situacao_ok = True  # não conseguiu verificar, assume ok
            break
    if not _situacao_ok:
        erros.append(f"{siafi}: portal não aceitou situação {siafi} após 3 tentativas.")
        return False

    try:
        _esperar_formulario_deducao_estabilizar(pagina, did, timeout_ms=15000)
    except Exception:
        pass
    _verificar_interrupcao(deve_parar)

    # ── PRÉ-EXPANSÃO: abre recolhedor E pré-doc ANTES de preencher qualquer campo ─
    # Estratégia: todo AJAX de expansão ("+") dispara aqui; depois preenchemos
    # tudo de uma vez sem que nenhum clique de "+" resete o que já foi preenchido.
    print(f"    [Pré-expansão] Abrindo recolhedor e pré-doc antes de preencher...")
    rid_expandido: str = ""
    # Aguarda o botão '+' do recolhedor estar visível — DDF055 pode demorar mais
    # no Windows; usa 25s igual ao DDR001 para máxima compatibilidade.
    try:
        pagina.locator(f"#novo-recolhedor{did}").wait_for(state="visible", timeout=25000)
    except Exception as ex_wait_rid:
        print(f"      [Aviso] novo-recolhedor{did} nao ficou visivel em 25s: {ex_wait_rid}")
    for _tent_rid in range(3):
        try:
            rid_ant = _obter_rid(pagina, did)
            pagina.locator(f"#novo-recolhedor{did}").click()
            rid_expandido = _aguardar_novo_recolhedor(pagina, did, rid_anterior=rid_ant, timeout_ms=20000)
            print(f"      recolhedor aberto: rid={rid_expandido}")
            break
        except Exception as ex_rid:
            rid_expandido = _obter_rid(pagina, did)
            print(f"      recolhedor: rid fallback={rid_expandido} (tentativa {_tent_rid+1}: {ex_rid})")
            if rid_expandido:
                break
            time.sleep(2.0)  # aguarda AJAX e tenta de novo

    pdid_expandido: str = ""
    try:
        pdid_expandido = _abrir_predoc_resiliente(pagina, did, erros)
        print(f"      pre-doc aberto: pdid={pdid_expandido}")
    except Exception as ex_pdid:
        print(f"      pre-doc: falhou ao pre-abrir ({ex_pdid})")

    # Aguarda o AJAX de expansão terminar antes de preencher os campos
    time.sleep(1.5)
    _verificar_interrupcao(deve_parar)

    # ── Campos principais (formulário de dedução) ─────────────────────────────
    _fill(pagina, f"sfdeducaocodugpgto{did}", _UG_TOMADORA, erros, "UG Pagadora")
    _fill_money(pagina, f"sfdeducaovlr{did}", valor_item_br, erros, "Valor do Item")

    if siafi != "DDF050" and natureza and natureza != "—":
        # Aguarda o campo Natureza de Rendimento ficar visível antes de preencher.
        # O AJAX do DDF055 pode demorar mais no Windows; espera até 12s.
        try:
            pagina.locator(f"#txtinscrb{did}").wait_for(state="visible", timeout=12000)
        except Exception:
            pass
        _fill(pagina, f"txtinscrb{did}", natureza, erros, "Natureza de Rendimento")

    _select(pagina, f"sfdeducaopossui_acrescimo{did}", "NÃƒO", erros, "Possui AcrÃ©scimo")

    # ── Recolhedor (usa rid já obtido — SEM clicar no '+' de novo) ───────────
    print(f"    [Recolhedor] Base={base_calculo_br} Receita={valor_item_br}")
    if not _preencher_recolhedor_darf(
        pagina, did, cnpj_fmt, base_calculo_br, valor_item_br, erros,
        rid_pre_aberto=rid_expandido,
    ):
        erros.append(f"{siafi}: nÃ£o conseguiu preencher o recolhedor/valores (did={did}).")
        return False

    # ── Pré-Doc (seção já aberta — _abrir_predoc_resiliente detecta e não reclica) ─
    predoc_ok = _preencher_predoc_darf(
        pagina,
        did,
        apuracao=data_apuracao,
        processo=processo,
        observacao=observacao,
        erros=erros,
        recurso=recurso,
        vinculacao="400",
    )
    if not predoc_ok:
        erros.append(
            f"{siafi}: Pré-Doc não preenchido (campos obrigatórios vazios) — "
            "confirmação bloqueada para evitar erro de validação."
        )
        return False
    _verificar_interrupcao(deve_parar)

    # ── Datas e Código DARF — absolutamente por último (após pré-doc) ─────────
    # Diagnóstico: inspeciona os campos antes de tentar preencher
    diag_datas = pagina.evaluate(
        """([idVenc, idPgto]) => {
            const info = (id) => {
                const el = document.getElementById(id);
                if (!el) return id + ':NAO_ENCONTRADO';
                const r = el.getBoundingClientRect();
                return id + ':type=' + el.type
                    + ':value=' + (el.value || 'vazio')
                    + ':visible=' + (r.width > 0 && r.height > 0)
                    + ':disabled=' + el.disabled
                    + ':readonly=' + el.readOnly;
            };
            return [info(idVenc), info(idPgto)];
        }""",
        [f"sfdeducaodtvenc{did}", f"sfdeducaodtpgtoreceb{did}"],
    )
    print(f"    [Diagnóstico datas] {diag_datas}")
    _fill_date_silente(pagina, f"sfdeducaodtvenc{did}", data_venc, erros, "Data de Vencimento")
    _fill_date_silente(pagina, f"sfdeducaodtpgtoreceb{did}", data_venc, erros, "Data de Pagamento")

    # txtinscra{did} tem onkeyup="buscaMunicipioPorCod" que faz AJAX ao receber
    # Tab/blur; "1162" não é município → AJAX limpa o campo. Setter silente.
    if codigo_darf:
        try:
            if not _set_input_silente(pagina, f"txtinscra{did}", str(codigo_darf)):
                erros.append(f"Código de Recolhimento DARF: campo txtinscra{did} não encontrado.")
        except Exception as e:
            erros.append(f"Código de Recolhimento DARF: {e}")

    if siafi != "DDF050" and natureza and natureza != "—":
        natureza_id = f"txtinscrb{did}"
        if not _set_input_silente(pagina, natureza_id, natureza):
            erros.append(f"Natureza de Rendimento: campo {natureza_id} não encontrado.")
        else:
            natureza_atual = _read_input_value(pagina, natureza_id)
            if str(natureza_atual or "").strip() != str(natureza).strip():
                erros.append(
                    f"Natureza de Rendimento ({natureza_id}): esperado {natureza}, ficou {natureza_atual or 'vazio'}."
                )
            else:
                print(f"    Natureza de Rendimento final: {natureza}")

    # ── Confirmar (atômico: seta datas + clica no mesmo tick JS) ─────────────
    print(f"    Confirmando {siafi} (did={did})")
    return _confirmar_com_datas_atomico(pagina, did, data_venc, erros)



# ─────────────────────────────────────────────────────────────────────────────
# LOCALIZADOR COMPARTILHADO DO BOTÃO "+" DO PRÉ-DOC
# ─────────────────────────────────────────────────────────────────────────────
# Mesma estratégia (0–4) usada inline por _abrir_predoc_resiliente
# (DDR001/DDF050/DDF055). Extraída como constante para que o DOB001 use o MESMO
# localizador comprovado, em vez de uma reimplementação divergente baseada em
# texto "+" — que NÃO encontra o ícone CSS (<i class="fa fa-plus">) do portal.
# Retorna a string da estratégia vencedora, ou '' se nenhum botão foi clicado.
# OBS: espelha o JS inline de _abrir_predoc_resiliente; mantenha os dois em sincronia.
_JS_CLICAR_MAIS_PREDOC = r"""(deducaoId) => {
    const visivel = (el) => !!el && (!!el.offsetParent || el.getClientRects().length > 0);
    const normalizar = (txt) =>
        String(txt || '')
            .normalize('NFD')
            .replace(/[̀-ͯ]/g, '')
            .replace(/\s+/g, ' ')
            .trim()
            .toLowerCase();

    const clicar = (el) => {
        const alvo = el?.closest?.('button, a, [role="button"]') || el;
        if (!alvo || !visivel(alvo)) return false;
        alvo.scrollIntoView({ block: 'center', inline: 'center', behavior: 'auto' });
        try { alvo.click(); }
        catch (_) {
            alvo.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }
        return true;
    };

    const candidatos = Array.from(
        document.querySelectorAll('button, a, span, i, [role="button"]')
    );

    // Estratégia 0 (mais segura): botão Pré-Doc DENTRO do container do did.
    {
        const ancora = document.getElementById(`confirma-dados-deducao-${deducaoId}`)
            || document.getElementById(`aba-deducao${deducaoId}`);
        if (ancora) {
            let nivel = ancora;
            for (let lvl = 0; lvl < 12; lvl++) {
                nivel = nivel.parentElement;
                if (!nivel) break;
                const btn = Array.from(
                    nivel.querySelectorAll('button, a, span, i, [role="button"]')
                ).find((el) => {
                    if (!visivel(el)) return false;
                    const classe  = normalizar(el.className || '');
                    const onclick = normalizar(el.getAttribute?.('onclick') || '');
                    const titulo  = normalizar(el.getAttribute?.('title') || el.getAttribute?.('aria-label') || '');
                    return classe.includes('predoc') || onclick.includes('predoc') || titulo.includes('predoc');
                });
                if (btn && clicar(btn)) return 'container-predoc-v2';
            }
        }
    }

    // Estratégia 1: onclick contém "predoc"
    const porOnclickPredoc = candidatos.find(
        (el) => visivel(el) && normalizar(el.getAttribute('onclick') || '').includes('predoc')
    );
    if (clicar(porOnclickPredoc)) return 'onclick-predoc';

    // Estratégia 2: onclick contém o did exato
    const porOnclick = candidatos.find(
        (el) => visivel(el) && String(el.getAttribute('onclick') || '').includes(deducaoId)
    );
    if (clicar(porOnclick)) return 'onclick-did';

    // Estratégia 3: cabeçalho "Pré-Doc" -> botão "+" vizinho
    const cabecalhosPredoc = Array.from(
        document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span,td,th,label,strong,p,caption')
    ).filter((el) => {
        if (!visivel(el)) return false;
        const txt = normalizar(el.textContent || el.getAttribute('title') || '');
        return /^pr[eé].?doc$/i.test(txt) || txt === 'pré-doc' || txt === 'pre-doc';
    });
    for (const cab of cabecalhosPredoc.reverse()) {
        let bloco = cab;
        for (let i = 0; i < 4; i++) {
            bloco = bloco.parentElement;
            if (!bloco) break;
            const btnMais = Array.from(
                bloco.querySelectorAll('button, a, span, i, [role="button"]')
            ).find((el) => {
                const txt = normalizar(el.textContent || '');
                return visivel(el) && (
                    txt === '+'
                    || el.querySelector?.('.fa-plus, .glyphicon-plus, [class*="plus"]')
                    || normalizar(el.getAttribute?.('onclick') || '').includes('predoc')
                    || normalizar(el.className || '').includes('predoc')
                );
            });
            if (btnMais && clicar(btnMais)) return 'predoc-header';
        }
    }

    // Estratégia 4 (fallback): último "+" que NÃO esteja dentro de "recolhedor"
    const botoesMais = candidatos.filter((el) => {
        if (!visivel(el)) return false;
        const txt = normalizar(el.textContent || '');
        if (txt !== '+') return false;
        let pai = el.parentElement;
        for (let i = 0; i < 6 && pai; i++) {
            const paiTxt = normalizar(pai.textContent || '');
            if (paiTxt.includes('recolhedor') && !paiTxt.includes('predoc')) return false;
            pai = pai.parentElement;
        }
        return true;
    });
    const ultimo = botoesMais.pop();
    if (clicar(ultimo)) return 'global-mais';

    return '';
}"""


# Localizador PRINCIPAL do '+' do Pré-Doc do DOB001: sobe a partir da âncora do
# did e clica no botão que tenha atributo "predoc" OU ícone de "+" (fa-plus etc.)
# OU seja um <a href="#"> anônimo (padrão do Contratos.gov.br: ícone CSS/jQuery,
# sem texto e sem onclick). Exclui botões de outras ações (nova dedução, confirmar,
# recolhedor, acréscimo, apropriar, preencher). É o que abre o DOB001 de forma
# confiável — por isso é tentado ANTES dos demais localizadores.
_JS_PREDOC_DOB001_CONTAINER = r"""(did) => {
    const v = (el) => !!el && (!!el.offsetParent || el.getClientRects().length > 0);
    const n = (t) => String(t || '').normalize('NFD')
        .replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
    const click = (el) => {
        if (!el || !v(el)) return false;
        el.scrollIntoView({ block: 'center', behavior: 'auto' });
        try { el.click(); }
        catch (_) { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); }
        return true;
    };
    const ancora = document.getElementById('confirma-dados-deducao-' + did)
        || document.getElementById('aba-deducao' + did);
    if (!ancora) return '';
    let nivel = ancora;
    for (let i = 0; i < 12; i++) {
        nivel = nivel.parentElement;
        if (!nivel) break;
        const els = Array.from(nivel.querySelectorAll('button,a,span,i,[role="button"]'));
        for (const el of els) {
            if (!v(el)) continue;
            const id = el.id || '';
            const cls = n(el.className || '');
            const onc = n(el.getAttribute('onclick') || '');
            const tit = n(el.getAttribute('title') || el.getAttribute('aria-label') || '');
            const txt = n(el.textContent || '');
            const href = (el.getAttribute('href') || '').toLowerCase();
            const ico = !!el.querySelector('.fa-plus,.glyphicon-plus,[class*="plus"],[class*="add"]');
            if (id.startsWith('nova-aba-situacao-deducao')) continue;
            if (id.startsWith('confirma-dados-deducao')) continue;
            if (id.startsWith('novo-acrescimo')) continue;
            if (id.startsWith('novo-recolhedor')) continue;
            if (id.startsWith('btnPreencher')) continue;
            if (txt.includes('relacionamento')) continue;
            if (txt.includes('confirmar')) continue;
            if (txt.includes('apropriar')) continue;
            if (txt.includes('preencher')) continue;
            if (cls.includes('predoc') || onc.includes('predoc') || tit.includes('predoc'))
                return click(el) ? 'predoc-attr' : '';
            if (ico) return click(el) ? 'icon-plus' : '';
            if (txt === '+') return click(el) ? 'text-plus' : '';
            if (txt === '' && el.tagName === 'A' && !id && (href === '#' || href.endsWith('#')))
                return click(el) ? 'anon-href-hash' : '';
        }
    }
    return '';
}"""


def _dob001_predoc_aberto(pagina, did: str) -> bool:
    """True se algum campo específico do Pré-Doc DOB001 já está VISÍVEL.

    Evita reclicar no '+' quando a seção já foi expandida (um segundo clique
    poderia colapsar ou duplicar o Pré-Doc).
    """
    try:
        return bool(pagina.evaluate(
            r"""(did) => {
                const v = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return false;
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                };
                return ['codcredordevedorpredoc','codnumlista','codtipoob',
                        'bancoFavorecido','agenciaFavorecido','contaFavorecido',
                        'txtprocesso','obser'].some((p) => v(document.getElementById(p + did)));
            }""",
            did,
        ))
    except Exception:
        return False


def _abrir_predoc_dob001(pagina, did: str, erros: list) -> bool:
    """Abre o Pré-Doc de uma dedução DOB001 clicando no '+' e aguarda os
    campos específicos do DOB001 ficarem visíveis.

    Usa múltiplas estratégias Playwright nativas antes de cair no evaluate JS.
    """
    import re as _re

    def _aguardar_campos(timeout_ms: int = 15000) -> bool:
        try:
            pagina.wait_for_function(
                """(did) => {
                    const v = el => {
                        if (!el) return false;
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 && r.height === 0) return false;
                        const s = window.getComputedStyle(el);
                        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
                    };
                    return ['codcredordevedorpredoc','codnumlista','codtipoob',
                            'bancoFavorecido','agenciaFavorecido','contaFavorecido',
                            'txtprocesso','obser'].some(p => v(document.getElementById(p + did)));
                }""",
                arg=did,
                timeout=timeout_ms,
            )
            print(f"      pré-doc DOB001 aberto ✓")
            return True
        except Exception:
            return False

    def _tentar(loc, desc: str) -> bool:
        try:
            if loc.count() == 0:
                return False
            el = loc.first
            if not el.is_visible(timeout=800):
                return False
            el.scroll_into_view_if_needed(timeout=2000)
            el.click(timeout=3000)
            if _aguardar_campos(3000):
                print(f"      [DOB001] Pré-Doc clicado: {desc}")
                return True
        except Exception:
            pass
        return False

    def _tentar_js(js: str, desc: str, verify_ms: int) -> bool:
        """Executa um localizador JS do '+' do Pré-Doc e confirma a abertura
        pelos campos do DOB001. Retorna True só se os campos aparecerem."""
        try:
            est = pagina.evaluate(js, did)
        except Exception as e:
            print(f"      [DOB001] {desc} erro: {e}")
            return False
        if not est:
            return False
        print(f"      [DOB001] Pré-Doc '+' clicado ({desc}: {est})")
        return _aguardar_campos(verify_ms)

    # ── 0. Já aberto? não reclica (evita colapsar/duplicar a seção) ──────
    if _dob001_predoc_aberto(pagina, did):
        print("      pré-doc DOB001 já aberto ✓ (sem reclicar)")
        return True

    # ── 1 (PREFERENCIAL): botão Pré-Doc no container do did ──────────────
    # No Contratos.gov.br o '+' é um ícone CSS / <a href="#"> anônimo, SEM
    # texto. Este localizador é o que abre o DOB001 de forma confiável, então
    # roda PRIMEIRO — antes era a última estratégia (B), e só era alcançado
    # depois de ~25 s de timeouts dos localizadores que não acham ícone.
    if _tentar_js(_JS_PREDOC_DOB001_CONTAINER, "container", 10000):
        return True

    # ── 2 (fallback): localizador resiliente (mesmo das demais deduções) ─
    if _tentar_js(_JS_CLICAR_MAIS_PREDOC, "resiliente", 4000):
        return True

    # ── A: botão com texto exato "+" (mais comum) ────────────────────────
    if _tentar(
        pagina.locator("button, a").filter(has_text=_re.compile(r"^\s*\+\s*$")).last,
        "button/a com texto +"
    ):
        return True

    # ── B: dentro do container da dedução — qualquer <a href="...#"> anônimo ──
    # (padrão do Contratos.gov.br: ícone CSS + jQuery, sem onclick/texto)
    try:
        confirmar = pagina.locator(f"#confirma-dados-deducao-{did}")
        if confirmar.count() > 0 and confirmar.is_visible(timeout=500):
            # Sobe pelo DOM via JS e clica no <a href="#"> anônimo da seção Pré-Doc
            clicou_b = pagina.evaluate(
                """(did) => {
                    const v = el => !!el && (!!el.offsetParent || el.getClientRects().length > 0);
                    const n = t => String(t||'').normalize('NFD')
                        .replace(/[̀-ͯ]/g,'').replace(/\s+/g,' ').trim().toLowerCase();
                    const click = el => {
                        if (!el || !v(el)) return false;
                        el.scrollIntoView({ block:'center', behavior:'auto' });
                        try { el.click(); }
                        catch(_) { el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window})); }
                        return true;
                    };

                    const ancora = document.getElementById('confirma-dados-deducao-' + did)
                                || document.getElementById('aba-deducao' + did);
                    if (!ancora) return '';

                    let nivel = ancora;
                    for (let i = 0; i < 12; i++) {
                        nivel = nivel.parentElement;
                        if (!nivel) break;

                        const els = Array.from(nivel.querySelectorAll('button,a,span,i,[role="button"]'));
                        for (const el of els) {
                            if (!v(el)) continue;
                            const id   = el.id || '';
                            const cls  = n(el.className||'');
                            const onc  = n(el.getAttribute('onclick')||'');
                            const tit  = n(el.getAttribute('title')||el.getAttribute('aria-label')||'');
                            const txt  = n(el.textContent||'');
                            const href = (el.getAttribute('href')||'').toLowerCase();
                            const ico  = !!el.querySelector('.fa-plus,.glyphicon-plus,[class*="plus"],[class*="add"]');

                            // Exclusões
                            if (id.startsWith('nova-aba-situacao-deducao')) continue;
                            if (id.startsWith('confirma-dados-deducao'))    continue;
                            if (id.startsWith('novo-acrescimo'))             continue;
                            if (id.startsWith('btnPreencher'))               continue;
                            if (txt.includes('relacionamento'))              continue;
                            if (txt.includes('confirmar'))                   continue;
                            if (txt.includes('apropriar'))                   continue;
                            if (txt.includes('preencher'))                   continue;

                            // Condições positivas
                            if (cls.includes('predoc') || onc.includes('predoc') || tit.includes('predoc'))
                                return click(el) ? 'predoc-attr' : '';
                            if (ico)
                                return click(el) ? 'icon-plus' : '';
                            if (txt === '+')
                                return click(el) ? 'text-plus' : '';
                            // Link anônimo href="#" (ícone CSS, jQuery)
                            if (txt === '' && el.tagName === 'A' && !id
                                && (href === '#' || href.endsWith('#')))
                                return click(el) ? 'anon-href-hash' : '';
                        }
                    }
                    return '';
                }""",
                did,
            )
            if clicou_b:
                print(f"      [DOB001] Pré-Doc clicado via JS container: {clicou_b}")
                if _aguardar_campos(4000):
                    return True
    except Exception as e:
        print(f"      [DOB001] Estratégia B erro: {e}")

    # ── C: cabeçalho "Pré-Doc" → primeiro botão/link no mesmo bloco ─────
    try:
        import re as _re2
        cabs = pagina.locator(
            "caption, th, td, div, span, h1, h2, h3, h4, h5, h6, strong, p"
        ).filter(has_text=_re2.compile(r"^pré-?doc$", _re2.IGNORECASE))
        n_cabs = cabs.count()
        for idx in range(n_cabs - 1, -1, -1):
            cab = cabs.nth(idx)
            if not cab.is_visible(timeout=400):
                continue
            for xp in ["../..", "../../..", "../../../..", "../../../../.."]:
                bloco = cab.locator(f"xpath={xp}")
                if bloco.count() == 0:
                    continue
                btn = bloco.locator("button, a").filter(
                    has_text=_re2.compile(r"^\s*\+\s*$")
                ).first
                if _tentar(btn, f"predoc-heading-idx{idx}"):
                    return True
            break
    except Exception as e:
        print(f"      [DOB001] Estratégia C erro: {e}")

    erros.append("DOB001/Pré-Doc: botão '+' não encontrado após todas as estratégias.")
    return False


def calcular_dv_nup(base15: str) -> str:
    """Calcula os 2 dígitos verificadores do NUP-17 (Número Único de Protocolo),
    conforme a Portaria Interministerial MJSP/ME nº 11/2019.

    Módulo 11 com pesos da direita para a esquerda, progressão de razão 1
    começando em 2: DV1 sobre os 15 dígitos da base (pesos 2..16) e DV2 sobre os
    16 dígitos já com o DV1 (pesos 2..17). Para cada dígito verificador, usa a
    unidade do resultado de 11 - (soma % 11): resto 0 vira 1, resto 1 vira 0.

    Recebe os 15 dígitos da base (com ou sem pontuação) e retorna 'DD'.
    Ex.: '23080.017645/2026' -> '81'  (NUP completo: 23080.017645/2026-81)
    """
    import re as _re_nup
    d = _re_nup.sub(r"\D", "", str(base15 or ""))
    if len(d) != 15:
        raise ValueError(f"NUP base deve ter 15 dígitos; recebido {len(d)}")
    s1 = sum(int(d[i]) * (16 - i) for i in range(15))
    r1 = s1 % 11
    dv1 = (11 - r1) % 10
    d2 = d + str(dv1)
    s2 = sum(int(d2[i]) * (17 - i) for i in range(16))
    r2 = s2 % 11
    dv2 = (11 - r2) % 10
    return f"{dv1}{dv2}"


def _formatar_processo_nup(processo: str) -> str:
    """Normaliza o nº do processo para o NUP-17 exigido pela máscara do portal:
    NNNNN.NNNNNN/AAAA-DD.

    O PDF traz o NUP SEM os 2 dígitos verificadores (15 dígitos), mas a máscara
    do campo Processo exige os 17 — por isso o campo ficava com '-__' em branco.
    Aqui calculamos o DV e devolvemos o número completo e pontuado. Se já vierem
    17 dígitos, usa como está. Em qualquer outro caso (formato fora do padrão
    NUP), devolve o valor original sem alterar — nunca inventa dígitos.
    """
    import re as _re_nup
    bruto = str(processo or "").strip()
    d = _re_nup.sub(r"\D", "", bruto)
    if len(d) == 15:
        try:
            processo_historico = _buscar_processo_completo_no_historico_fila(d)
            if processo_historico:
                return processo_historico
            d = d + calcular_dv_nup(d)
        except Exception:
            return bruto
    if len(d) != 17:
        return bruto  # formato inesperado — não mexe
    return f"{d[0:5]}.{d[5:11]}/{d[11:15]}-{d[15:17]}"


def _buscar_processo_completo_no_historico_fila(base15: str) -> str:
    """Tenta resolver o NUP completo usando o Protocolo da fila/histórico.

    A coluna "Número Processo" da fila pode guardar só o sequencial curto
    (ex.: 025771), enquanto o JSON "Protocolo" traz o processo oficial completo.
    Quando o PDF vem sem DV, o Protocolo registrado é uma fonte melhor que
    recalcular, principalmente para processos que não seguem a base esperada.
    """
    import re as _re_nup

    base = _re_nup.sub(r"\D", "", str(base15 or ""))
    if len(base) != 15:
        return ""

    def _formatar_candidato(valor: object) -> str:
        texto = str(valor or "").strip()
        digitos = _re_nup.sub(r"\D", "", texto)
        if len(digitos) >= 17 and digitos[:15] == base:
            d = digitos[:17]
            return f"{d[0:5]}.{d[5:11]}/{d[11:15]}-{d[15:17]}"
        return ""

    # 1) Snapshot local da fila atual: rápido e sem rede.
    try:
        from services import local_cache_service as _local_cache

        snapshot = _local_cache.obter_fila_processos_snapshot()
        for row in snapshot.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for chave in ("Protocolo", "protocolo", "processoSolar", "Processo"):
                achado = _formatar_candidato(row.get(chave))
                if achado:
                    return achado
    except Exception:
        pass

    # 2) Histórico remoto/local persistido no Turso, quando configurado.
    try:
        from services import turso_service as _turso

        if not _turso.turso_configurado():
            return ""
        like_prefix = f"{base}%"
        sql = """
            select protocolo
            from (
              select json_extract(dados, '$.Protocolo') as protocolo, atualizado_em as ordem
              from fila_processos_atual
              union all
              select json_extract(dados, '$.Protocolo') as protocolo, ultimo_visto_em as ordem
              from fila_processos_historico
              union all
              select numero_processo as protocolo, atualizado_em as ordem
              from processos
            )
            where protocolo is not null
              and replace(replace(replace(protocolo, '.', ''), '/', ''), '-', '') like ?
            order by ordem desc
            limit 1
        """
        result = _turso.executar(sql, [like_prefix], timeout=3)
        for row in _turso._rows(result):
            achado = _formatar_candidato(row.get("protocolo"))
            if achado:
                return achado
    except Exception:
        pass

    return ""


def _preencher_dob001_total(
    pagina,
    ded: dict,
    idx: int,
    total: int,
    cod_mun: str,
    data_venc: str,
    processo: str,
    cnpj_fmt: str,
    lf_numero: str,
    dados: dict,
    erros: list,
    deve_parar=None,
):
    valor_item_br = _formatar_valor_br(ded.get("Valor", "0"))
    nome_mun = _MUNICIPIO_NOME.get(cod_mun, cod_mun)
    tipo_ob = _DOB001_TIPO_OB.get(cod_mun, "OB Fatura")
    favorecido = _DOB001_FAVORECIDO[tipo_ob]
    observacao = _montar_observacao(dados, cod_mun)

    print(
        f"  â†’ DOB001 {nome_mun} [{idx+1}/{total}]  "
        f"Valor={valor_item_br}  Tipo={tipo_ob}  Venc={data_venc}"
    )
    _verificar_interrupcao(deve_parar)
    _garantir_sem_deducao_em_edicao(pagina, timeout_ms=8000)

    did = _clicar_nova_deducao(pagina)
    _verificar_interrupcao(deve_parar)
    if not did:
        erros.append(f"DOB001 {nome_mun}: não obteve ID da nova dedução após clicar no '+'.")
        return False
    print(f"    did={did}")

    # ── Aguarda o formulário estabilizar ANTES de selecionar DOB001 ──────
    # O select sfdeducaocodsit{did} aparece no DOM imediatamente mas as
    # opções AJAX só chegam depois — selecionar antes disso sempre falha.
    try:
        _esperar_formulario_deducao_estabilizar(pagina, did, timeout_ms=15000)
    except Exception:
        pass

    # Espera adicional para as opções do select de Situação carregarem
    try:
        pagina.wait_for_function(
            """(did) => {
                const sel = document.getElementById('sfdeducaocodsit' + did);
                return sel && sel.options.length > 1;
            }""",
            arg=did,
            timeout=10000,
        )
    except Exception:
        pass  # Tenta selecionar mesmo assim

    # Seleciona DOB001 com retry caso o primeiro `_select` falhe por timing
    for _tentativa_sel in range(3):
        ok = pagina.evaluate(
            """([fid, texto]) => {
                const sel = document.getElementById(fid);
                if (!sel || sel.options.length <= 1) return false;
                const norm = (s) => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().trim();
                const op = Array.from(sel.options).find(o =>
                    norm(o.value) === norm(texto) ||
                    norm(o.text).includes(norm(texto))
                );
                if (!op) return false;
                sel.value = op.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                if (typeof $ !== 'undefined') $(sel).trigger('change');
                return true;
            }""",
            [f"sfdeducaocodsit{did}", "DOB001"],
        )
        if ok:
            print(f"    [DOB001] Situação selecionada ✓ (tentativa {_tentativa_sel + 1})")
            break
        time.sleep(0.6)
    else:
        erros.append(f"DOB001: opção 'DOB001' não encontrada no select Situação após 3 tentativas.")

    # Aguarda o formulário re-estabilizar após a seleção de DOB001 (dispara AJAX)
    try:
        _esperar_formulario_deducao_estabilizar(pagina, did, timeout_ms=15000)
    except Exception:
        pass
    _verificar_interrupcao(deve_parar)

    # ── Abre o Pré-Doc DOB001 clicando no '+' ───────────────────────────
    # _abrir_predoc_dob001 aguarda campos DOB001-específicos (não sfpredoc*),
    # evitando o timeout de 15 s que causava falha silenciosa da dedução DOB001.
    print(f"    [DOB001] Abrindo pré-doc...")
    predoc_aberto = _abrir_predoc_dob001(pagina, did, erros)
    if not predoc_aberto:
        print(f"    [DOB001] Aviso: pré-doc pode não ter aberto corretamente; tentando preencher assim mesmo.")
    time.sleep(0.8)

    _fill_if_different(pagina, f"sfdeducaocodugpgto{did}", _UG_TOMADORA, erros, "UG Pagadora")
    _fill_money(pagina, f"sfdeducaovlr{did}", valor_item_br, erros, "Valor do Item")
    _select(pagina, f"sfdeducaopossui_acrescimo{did}", "NÃO", erros, "Possui Acréscimo")

    # Diagnóstico: mostra as opções reais do select Tipo de OB
    try:
        opcoes_reais = pagina.evaluate(
            "(id) => { const s = document.getElementById(id); "
            "return s ? Array.from(s.options).map(o => o.value + '|' + o.text) : ['NAO_ENCONTRADO']; }",
            f"codtipoob{did}",
        )
        print(f"    [Tipo de OB] opções disponíveis: {opcoes_reais}")
    except Exception as ex_opts:
        print(f"    [Tipo de OB] diagnóstico falhou: {ex_opts}")

    _select_com_fallback(
        pagina,
        f"codtipoob{did}",
        [tipo_ob, "OB Fatura", "OB Crédito", "fatura", "credito", "crédito"],
        erros,
        "Pré-Doc/Tipo de OB",
    )

    # Processo: o PDF traz o NUP sem os 2 dígitos verificadores; a máscara do
    # campo exige os 17. Completa com o DV (módulo 11) antes de preencher.
    processo_fmt = _formatar_processo_nup(processo)
    if processo_fmt != processo:
        print(f"    [DOB001] Processo NUP completado com DV: {processo} -> {processo_fmt}")

    # ── Batch fill: todos os campos de texto do Pré-Doc DOB001 (1 round-trip) ─
    campos_dob001 = {
        f"codcredordevedorpredoc{did}": favorecido["cnpj"],
        f"txtprocesso{did}": processo_fmt,
        f"taxacambio{did}": "0",
        f"codnumlista{did}": lf_numero,
        f"bancoFavorecido{did}": favorecido["banco_favorecido"],
        f"agenciaFavorecido{did}": favorecido["agencia_favorecido"],
        f"contaFavorecido{did}": favorecido["conta_favorecido"],
        f"bancoPagador{did}": "001",
        f"obser{did}": observacao,
    }
    try:
        _batch_fill(pagina, campos_dob001)
    except Exception as e:
        erros.append(f"Pré-Doc DOB001/batch: {e}")

    # ── Confirmar (atômico: seta datas + clica no mesmo tick JS) ─────────────
    print(f"    Confirmando DOB001 (did={did})")
    try:
        return _confirmar_com_datas_atomico(pagina, did, data_venc, erros)
    except Exception as e:
        erros.append(f"DOB001: erro ao confirmar dedução (did={did}): {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# BARREIRA DE TRANSIÇÃO ENTRE TIPOS DE DEDUÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def _aguardar_portal_limpo_entre_tipos(pagina, timeout_ms: int = 20000) -> None:
    """
    Barreira de sincronização obrigatória entre tipos de dedução.

    Garante que, antes de iniciar o próximo tipo (ex: DDF055 após DDF050):
      1. Nenhuma dedução está em estado não-confirmado com botão Confirmar visível
      2. Não há overlay ativo sobre o botão '+'
      3. O botão 'nova-aba-situacao-deducao' está visível e disponível
      4. Um buffer extra permite que qualquer AJAX residual complete

    Esta função é a solução definitiva para o bug de "DDF055 preenchendo em cima
    do DDF050": enquanto o portal não liberar explicitamente o botão '+', o próximo
    tipo não recebe permissão para chamar _clicar_nova_deducao().
    """
    print("    [Transição] Aguardando portal limpo antes do próximo tipo...")
    try:
        pagina.wait_for_function(
            """() => {
                const visivel = (el) =>
                    !!el && (!!el.offsetParent || el.getClientRects().length > 0);

                // ① Nenhuma dedução em edição (sem botão Confirmar visível não-confirmado)
                const emEdicao = Array.from(
                    document.querySelectorAll('[id^="sfdeducaoconfirma_dados"]')
                ).some((el) => {
                    const v   = String(el.value || '').trim().toLowerCase();
                    const did = String(el.id || '').replace('sfdeducaoconfirma_dados', '');
                    const btn = document.getElementById('confirma-dados-deducao-' + did);
                    return v !== 'true' && visivel(btn);
                });
                if (emEdicao) return false;

                // ② Sem overlay ativo sobre o botão '+'
                const overlay = document.querySelector(
                    '#nova-aba-situacao-deducao .overlay'
                );
                if (overlay && visivel(overlay)) return false;

                // ③ Botão '+' visível e disponível
                const btnNova = document.getElementById('nova-aba-situacao-deducao');
                return visivel(btnNova);
            }""",
            timeout=timeout_ms,
        )
        print("    [Transição] Portal limpo ✓")
    except Exception as e:
        log.warning("[Transição] Portal não ficou limpo em %dms: %s", timeout_ms, e)
        print(f"    [Transição] Aviso: portal não confirmou limpeza em {timeout_ms}ms — tentando recuperação.")
        _garantir_sem_deducao_em_edicao(pagina, timeout_ms=max(timeout_ms, 30000))
        pagina.wait_for_function(
            """() => {
                const visivel = (el) =>
                    !!el && (!!el.offsetParent || el.getClientRects().length > 0);
                const overlay = document.querySelector('#nova-aba-situacao-deducao .overlay');
                const btnNova = document.getElementById('nova-aba-situacao-deducao');
                return (!overlay || !visivel(overlay)) && visivel(btnNova);
            }""",
            timeout=max(timeout_ms, 30000),
        )
        print("    [Transição] Portal recuperado após espera extra ✓")

    # Buffer extra para AJAX residual (animações, re-render do portal)
    time.sleep(1.5)


# ─────────────────────────────────────────────────────────────────────────────
# PONTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────

def executar(
    dados_extraidos,
    data_vencimento_processo="",
    apuracao_usuario="",
    lf_numero="",
    deve_parar=None,
    *,
    pagina=None,
    playwright=None,
    pular_confirmar_aba=False,
):
    """
    Orquestrador principal da etapa de Dedução.

    Executa os tipos na ordem:
      DDR001 → (transição) → DDF050 → (transição) → DDF055 → (transição) → DOB001

    Cada tipo é processado por um módulo dedicado:
      comprasnet_deducao_ddr001  · comprasnet_deducao_ddf050
      comprasnet_deducao_ddf055  · comprasnet_deducao_dob001

    pular_confirmar_aba=True: não clica o botão global "Confirmar" da aba Dedução
    ao final — usado quando um único tipo é executado individualmente (o tipo já
    faz seu próprio confirmar interno; o botão global só é necessário no fluxo
    completo, após todos os tipos serem processados).

    A "transição" (_aguardar_portal_limpo_entre_tipos) é a barreira que impede o
    próximo tipo de começar antes do portal estar completamente livre.
    """
    deducoes = dados_extraidos.get("Deduções", [])
    notas    = dados_extraidos.get("Notas Fiscais", [])

    if not deducoes:
        print("=== DEDUÇÃO === [PULADA — nenhuma dedução no PDF]")
        return {"status": "pulado", "mensagem": "Nenhuma dedução encontrada no PDF."}

    # ── Classifica as deduções por tipo ──────────────────────────────────────
    def _siafi_deducao(d: dict) -> str:
        return str(
            d.get("Situação SIAFI", "")
            or extrair_siafi_completo(d.get("Situação", ""))
            or ""
        ).upper()

    ddr001_list: list = []
    ddf050_list: list = []
    ddf055_list: list = []
    dob001_list: list = []
    outras_list: list = []

    for ded in deducoes:
        cod_mun = _codigo_municipio_deducao(ded)
        siafi   = _siafi_deducao(ded)

        if cod_mun in _CODIGOS_DDR001 or siafi == "DDR001":
            ddr001_list.append(ded)
        elif cod_mun in _CODIGOS_DOB001 or siafi == "DOB001":
            dob001_list.append(ded)
        elif siafi == "DDF050":
            ddf050_list.append(ded)
        elif siafi == "DDF055" or (siafi.startswith("DDF") and siafi != "DDF050"):
            ddf055_list.append(ded)
        else:
            outras_list.append(ded)

    outras_restantes = [
        d for d in outras_list
        if d not in ddf050_list
        and d not in ddf055_list
        and d not in dob001_list
        and d not in ddr001_list
    ]

    print(
        f"=== DEDUÇÃO ===\n"
        f"  DDR001 (ISS):           {len(ddr001_list)} retenção(ões)\n"
        f"  DDF050 (IRRF IN2110):   {len(ddf050_list)} retenção(ões)\n"
        f"  DDF055 (IRRF IN1234):   {len(ddf055_list)} retenção(ões)\n"
        f"  DOB001 (Ordem Bancária):{len(dob001_list)} retenção(ões)"
    )

    if not ddr001_list and not ddf050_list and not ddf055_list and not dob001_list:
        return {"status": "pulado", "mensagem": "Nenhuma retenção reconhecida para lançar."}

    sessao_propria = pagina is None
    if sessao_propria:
        playwright, pagina = conectar()

    try:
        erros: list = []

        cnpj_fmt      = _formatar_cnpj(dados_extraidos.get("CNPJ", ""))
        datas_emissao = [_normalizar_data(n.get("Data de Emissão", "")) for n in notas]
        processo      = str(dados_extraidos.get("Processo", "") or "")
        emps          = dados_extraidos.get("Empenhos", [])
        recurso_darf  = str((emps[0].get("Recurso") if emps else "1") or "1").strip()

        _abrir_aba_deducao(pagina)

        # No modo individual (pular_confirmar_aba=True) a aba pode estar sendo
        # re-aberta com AJAX ainda em andamento de uma dedução anterior.
        # _aguardar_portal_limpo_entre_tipos garante que o botão '+' esteja
        # disponível e não há overlay antes de qualquer preenchimento.
        if pular_confirmar_aba:
            _aguardar_portal_limpo_entre_tipos(pagina)

        # ══════════════════════════════════════════════════════════════════════
        # ① DDR001 — ISS (uma entrada por Nota Fiscal)
        # ══════════════════════════════════════════════════════════════════════
        if ddr001_list:
            from comprasnet.deducao_ddr001 import executar_ddr001
            executar_ddr001(
                pagina,
                ddr001_list,
                notas,
                cnpj_fmt=cnpj_fmt,
                dados_extraidos=dados_extraidos,
                data_vencimento_processo=data_vencimento_processo,
                erros=erros,
                deve_parar=deve_parar,
            )

        # ══════════════════════════════════════════════════════════════════════
        # ② DDF050 — IRRF IN 2110/22
        # ══════════════════════════════════════════════════════════════════════
        if ddf050_list:
            _verificar_interrupcao(deve_parar)
            if ddr001_list:
                # Garante que todas as DDR001s terminaram antes de começar DDF050
                _aguardar_portal_limpo_entre_tipos(pagina)
            from comprasnet.deducao_ddf050 import executar_ddf050
            executar_ddf050(
                pagina,
                ddf050_list,
                datas_emissao=datas_emissao,
                data_vencimento_processo=data_vencimento_processo,
                apuracao_usuario=apuracao_usuario,
                processo=processo,
                cnpj_fmt=cnpj_fmt,
                dados_extraidos=dados_extraidos,
                erros=erros,
                recurso_darf=recurso_darf,
                deve_parar=deve_parar,
            )

        # ══════════════════════════════════════════════════════════════════════
        # ③ DDF055 — IRRF IN 1234/12
        #    TRANSIÇÃO OBRIGATÓRIA: espera portal limpo antes de continuar.
        #    Sem esta barreira, o DDF055 começa a preencher em cima do DDF050.
        # ══════════════════════════════════════════════════════════════════════
        if ddf055_list:
            _verificar_interrupcao(deve_parar)
            if ddf050_list or ddr001_list:
                # ← CORREÇÃO DEFINITIVA DA TRANSIÇÃO DDF050 → DDF055
                _aguardar_portal_limpo_entre_tipos(pagina)
            from comprasnet.deducao_ddf055 import executar_ddf055
            executar_ddf055(
                pagina,
                ddf055_list,
                data_vencimento_processo=data_vencimento_processo,
                apuracao_usuario=apuracao_usuario,
                processo=processo,
                cnpj_fmt=cnpj_fmt,
                dados_extraidos=dados_extraidos,
                erros=erros,
                recurso_darf=recurso_darf,
                deve_parar=deve_parar,
            )

        # ══════════════════════════════════════════════════════════════════════
        # ④ DOB001 — Ordem Bancária
        # ══════════════════════════════════════════════════════════════════════
        if dob001_list:
            _verificar_interrupcao(deve_parar)
            if ddf055_list or ddf050_list or ddr001_list:
                _aguardar_portal_limpo_entre_tipos(pagina)
            from comprasnet.deducao_dob001 import executar_dob001
            executar_dob001(
                pagina,
                dob001_list,
                lf_numero=str(lf_numero or "").strip(),
                datas_emissao=datas_emissao,
                data_vencimento_processo=data_vencimento_processo,
                processo=processo,
                cnpj_fmt=cnpj_fmt,
                dados_extraidos=dados_extraidos,
                erros=erros,
                deve_parar=deve_parar,
            )

        # ── Verificação de outras deduções não classificadas ──────────────────
        if outras_restantes:
            print(f"\n  Verificando {len(outras_restantes)} deduções não classificadas...")
            try:
                total_pdf = dados_extraidos.get("Resumo", {}).get("Total Deduções", "")
                if total_pdf:
                    for linha in pagina.locator("table tbody tr").all():
                        if "TOTAL" in linha.inner_text().upper():
                            for cel in linha.locator("td").all():
                                val = cel.inner_text().strip()
                                if val and normalizar_valor(val) == normalizar_valor(total_pdf):
                                    print(f"  Total deduções confere: R$ {total_pdf} ✅")
            except Exception as e:
                log.warning("Verificação tabela deduções: %s", e)

        # ── Confirma a aba (botão global Confirmar da aba Dedução) ────────────
        if not erros and not pular_confirmar_aba:
            print("\n  Confirmando aba Dedução...")
            try:
                _verificar_interrupcao(deve_parar)
                btn = pagina.evaluate_handle("""() => {
                    return Array.from(document.querySelectorAll('button[type="submit"],button'))
                        .filter(b => /confirmar/i.test((b.textContent || '').trim()) && b.offsetParent)
                        .find(b => !(b.id || '').startsWith('confirma-dados-deducao-'))
                        || null;
                }""")
                if pagina.evaluate("el => el ? el.tagName : null", btn):
                    pagina.evaluate("el => el.click()", btn)
                else:
                    (
                        pagina.locator("button:visible")
                        .filter(has_not=pagina.locator("[id^='confirma-dados-deducao-']"))
                        .filter(has_text="Confirmar")
                        .last
                        .click()
                    )
                print("  Dedução confirmada ✓")
            except Exception as e:
                erros.append(f"Confirmar aba Dedução: {e}")

        if erros:
            return {"status": "alerta", "mensagem": "\n".join(erros)}
        return {"status": "sucesso", "mensagem": "Dedução preenchida e confirmada!"}

    except ExecucaoInterrompida as e:
        log.info("Dedução interrompida: %s", e)
        return {"status": "interrompido", "mensagem": str(e)}
    except Exception as e:
        log.error("Erro geral em Dedução: %s", e)
        return {"status": "erro", "mensagem": str(e)}
    finally:
        if sessao_propria and playwright is not None:
            playwright.stop()
