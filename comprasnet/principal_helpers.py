"""
comprasnet_principal_helpers.py
Utilitários compartilhados entre os handlers de situação do Principal Com Orçamento.
"""
import re
import time
import logging

from services.config_service import carregar_tabelas_config

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# EXCEÇÃO DE CONTROLE
# ─────────────────────────────────────────────────────────────────────────────

class ExecucaoInterrompida(Exception):
    """Interrupção cooperativa da etapa atual."""


# ─────────────────────────────────────────────────────────────────────────────
# UTILITÁRIOS DE MÁSCARA (jquery.mask.js)
# ─────────────────────────────────────────────────────────────────────────────

# Posiciona o cursor no primeiro '_' do campo mascarado (sem selecionar),
# permitindo que `press_sequentially` preencha somente a parte editável.
# Retorna true se encontrou '_'; false se o campo já está completo (sem '_').
_JS_POSICIONAR_MASCARA = """
(el) => {
    const valor = String(el.value || '');
    const primeiro = valor.indexOf('_');
    el.focus();
    if (primeiro >= 0) {
        el.setSelectionRange(primeiro, primeiro);
        return true;
    }
    el.setSelectionRange(valor.length, valor.length);
    return false;
}
"""


def _aguardar_mascara_campo(campo, timeout_s: float = 3.0) -> bool:
    """Aguarda até que o campo mascarado exiba ao menos um '_' (template pronto).

    Retorna True se a máscara ficou disponível dentro do timeout,
    False caso o campo permaneça vazio ou preenchido sem placeholder.
    """
    inicio = time.time()
    while time.time() - inicio < timeout_s:
        val = campo.input_value().strip()
        if "_" in val:
            return True
        time.sleep(0.1)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# VPD — tabela de fallback embutida
# ─────────────────────────────────────────────────────────────────────────────

# Formato de cada linha: [natureza, situação_dsp, código_vpd]
_VPD_PADRAO: list[list[str]] = [
    ["339030.01", "DSP 001", "3.3.2.3.X.04.00"],
]


# ─────────────────────────────────────────────────────────────────────────────
# VPD LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_situacao_vpd(situacao: str) -> str:
    return re.sub(r"[^A-Z0-9/]+", "", str(situacao or "").upper())


def _situacao_vpd_compativel(situacao_linha: str, situacao_alvo: str) -> bool:
    linha = _normalizar_situacao_vpd(situacao_linha)
    alvo = _normalizar_situacao_vpd(situacao_alvo)
    if not alvo:
        return True
    if not linha:
        return False
    if linha == alvo or alvo in linha or linha in alvo:
        return True
    codigos_linha = set(re.findall(r"[A-Z]{2,4}\d{3}", linha))
    codigos_alvo = set(re.findall(r"[A-Z]{2,4}\d{3}", alvo))
    if codigos_linha and codigos_alvo:
        return bool(codigos_linha & codigos_alvo)
    return False


def _buscar_vpd(natureza: str, situacao: str = "") -> str:
    """
    Retorna o código VPD para a natureza dada.
    Ordem de consulta: PostgreSQL → tabelas_config.json → _VPD_PADRAO embutido.
    Retorna '' se não encontrado.
    """
    nat = str(natureza).strip()

    vpd_lista: list = []
    try:
        from services.postgres_service import obter_tabela_operacional, postgres_habilitado
        if postgres_habilitado():
            rows = obter_tabela_operacional("vpd")
            if rows is not None:
                vpd_lista = [
                    [
                        str((row or {}).get("natureza", "")).strip(),
                        str((row or {}).get("situacaoDsp", "")).strip(),
                        str((row or {}).get("vpd", "")).strip(),
                    ]
                    for row in rows
                ]
    except Exception as e:
        log.warning("VPD: falha ao ler tabela remota no PostgreSQL: %s", e)

    if not vpd_lista:
        try:
            cfg = carregar_tabelas_config()
            vpd_lista = cfg.get("vpd_lista", [])
        except Exception as e:
            log.warning("VPD: falha ao ler tabelas_config.json: %s", e)

    if not vpd_lista:
        vpd_lista = _VPD_PADRAO

    # Busca exata por natureza priorizando a situação correspondente
    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip()
        row_situacao = str(row[1]).strip() if len(row) > 1 else ""
        row_vpd = str(row[2]).strip()
        if row_nat.upper() == nat.upper() and _situacao_vpd_compativel(row_situacao, situacao):
            return row_vpd

    # Fallback por natureza, independentemente da situação
    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip()
        row_vpd = str(row[2]).strip()
        if row_nat.upper() == nat.upper():
            return row_vpd

    nat_base = nat.split(".")[0]

    # Busca sem sub-elemento priorizando situação
    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip().split(".")[0]
        row_situacao = str(row[1]).strip() if len(row) > 1 else ""
        if row_nat == nat_base and _situacao_vpd_compativel(row_situacao, situacao):
            return str(row[2]).strip()

    # Último fallback: família da natureza sem considerar situação
    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip().split(".")[0]
        if row_nat == nat_base:
            return str(row[2]).strip()

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# CONTROLE DE INTERRUPÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def _verificar_interrupcao(deve_parar=None):
    if deve_parar and deve_parar():
        raise ExecucaoInterrompida(
            "Execução interrompida pelo usuário durante Principal com Orçamento."
        )


# ─────────────────────────────────────────────────────────────────────────────
# EXPANDIR BARRA DO EMPENHO
# ─────────────────────────────────────────────────────────────────────────────

def _empenho_expandido(pagina, num_empenho: str) -> bool:
    """Confere se o bloco do empenho foi expandido e expôs os inputs da área."""
    try:
        return bool(
            pagina.evaluate(
                r"""(numEmp) => {
                    const normalizar = (txt) => (txt || '').replace(/\s+/g, '').toUpperCase();
                    const alvo = normalizar(numEmp);
                    return Array.from(document.querySelectorAll('input')).some((el) => {
                        const valor = normalizar(el.value || '');
                        if (!valor.includes(alvo)) return false;
                        const rect = el.getBoundingClientRect();
                        const estilo = window.getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && estilo.visibility !== 'hidden'
                            && estilo.display !== 'none';
                    });
                }""",
                num_empenho,
            )
        )
    except Exception:
        return False


def _expandir_barra_empenho(pagina, num_empenho_pdf: str, erros: list) -> bool:
    """Localiza e clica na barra azul do empenho para expandi-la."""
    num_fmt = re.sub(r"^(\d{4})(\d{6})$", r"\1NE\2", num_empenho_pdf)
    candidatos_numero = [num_fmt]
    numero_bruto = str(num_empenho_pdf or "").strip()
    if numero_bruto and numero_bruto not in candidatos_numero:
        candidatos_numero.append(numero_bruto)

    try:
        pagina.wait_for_function(
            r"""(numEmp) => {
                const normalizar = (txt) => (txt || '').replace(/\s+/g, ' ').trim().toUpperCase();
                const alvo = normalizar(numEmp);
                const visivel = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const estilo = window.getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && estilo.visibility !== 'hidden'
                        && estilo.display !== 'none';
                };
                return Array.from(document.querySelectorAll('.row.pointer-hand, .box-header, .count-poo-item, [data-count-poo-item]'))
                    .some((el) => visivel(el) && normalizar(el.innerText || el.textContent).includes(alvo));
            }""",
            arg=num_fmt,
            timeout=2500,
        )
    except Exception:
        time.sleep(1.0)

    try:
        pagina.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    ultimo_erro = None
    for numero in candidatos_numero:
        try:
            handle = pagina.evaluate_handle(
                r"""(numEmp) => {
                    const normalizar = (txt) => (txt || '').replace(/\s+/g, ' ').trim().toUpperCase();
                    const alvo = normalizar(numEmp);
                    const visivel = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        const estilo = window.getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && estilo.visibility !== 'hidden'
                            && estilo.display !== 'none';
                    };

                    const roots = Array.from(document.querySelectorAll('.count-poo-item, [data-count-poo-item], .box.box-solid, .box-header, .row.pointer-hand'));
                    for (const root of roots) {
                        const txt = normalizar(root.innerText || root.textContent);
                        if (!txt || !txt.includes(alvo) || !txt.includes('EMPENHO') || !visivel(root)) {
                            continue;
                        }

                        const container =
                            root.closest('.count-poo-item, [data-count-poo-item], .box.box-solid, .box')
                            || root;
                        const alvoClique =
                            container.querySelector('.row.pointer-hand')
                            || container.querySelector('.box-header')
                            || container.querySelector('.title-item-acordion')
                            || root;

                        if (visivel(alvoClique)) {
                            return alvoClique;
                        }
                    }
                    return null;
                }""",
                numero,
            )

            elemento = handle.as_element()
            if elemento is not None:
                elemento.scroll_into_view_if_needed(timeout=2000)
                time.sleep(0.2)
                caixa = elemento.bounding_box()
                if caixa:
                    pagina.mouse.click(
                        caixa["x"] + min(max(caixa["width"] * 0.18, 32), 140),
                        caixa["y"] + (caixa["height"] / 2),
                    )
                    time.sleep(0.6)
                    if _empenho_expandido(pagina, num_fmt):
                        print(f"    Barra expandida rapidamente ({num_fmt}).")
                        return True

            handle = pagina.evaluate_handle(
                r"""(numEmp) => {
                    const normalizar = (txt) => (txt || '').replace(/\s+/g, ' ').trim().toUpperCase();
                    const alvo = normalizar(numEmp);
                    const visivel = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        const estilo = window.getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && estilo.visibility !== 'hidden'
                            && estilo.display !== 'none';
                    };
                    const pontuar = (el, txt) => {
                        let score = 0;
                        if (txt.includes('EMPENHO')) score += 4;
                        if (txt.includes('Nº DO EMPENHO') || txt.includes('N DO EMPENHO')) score += 6;
                        if (txt.includes('SUBELEMENTO')) score += 4;
                        if (txt.includes('LIQUIDADO')) score += 4;
                        if (txt.includes('R$')) score += 2;
                        if (el.matches('.row.pointer-hand, .box-header, .title-item-acordion')) score += 10;
                        if (el.matches('[data-widget="collapse"], [aria-expanded]')) score += 6;
                        const cls = String(el.className || '').toLowerCase();
                        if (/(pointer-hand|box-header|header|heading|accordion|collapse|card|panel|title|bar|custom-shadow)/.test(cls)) score += 6;
                        score -= Math.min(txt.length, 400) / 120;
                        return score;
                    };

                    const candidatos = new Map();
                    for (const el of document.querySelectorAll('div, section, article, li, tr, td, button, a, span')) {
                        const txt = normalizar(el.innerText || el.textContent);
                        if (!txt || !txt.includes(alvo) || !txt.includes('EMPENHO') || !visivel(el)) {
                            continue;
                        }

                        let alvoClique =
                            el.closest('.row.pointer-hand, .box-header, .title-item-acordion, [data-widget="collapse"], [aria-expanded], .panel-heading, .card-header, .accordion-header, .panel-title, .card-title')
                            || el.closest('div, section, article, li, tr')
                            || el;

                        if (!visivel(alvoClique)) {
                            alvoClique = el;
                        }

                        const textoAlvo = normalizar(alvoClique.innerText || alvoClique.textContent || txt);
                        const atual = candidatos.get(alvoClique);
                        const score = pontuar(alvoClique, textoAlvo);
                        if (!atual || atual.score < score) {
                            candidatos.set(alvoClique, { alvo: alvoClique, score });
                        }
                    }

                    return Array.from(candidatos.values())
                        .sort((a, b) => b.score - a.score)[0]?.alvo || null;
                }""",
                numero,
            )

            elemento = handle.as_element()
            if elemento is None:
                continue

            elemento.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.4)

            pagina.evaluate(
                """(el) => {
                    el.scrollIntoView({ block: 'center', inline: 'center' });
                }""",
                elemento,
            )

            try:
                pagina.evaluate(
                    """(el) => {
                        const alvo =
                            el.matches('.row.pointer-hand, .box-header, .title-item-acordion')
                                ? el
                                : el.querySelector('.row.pointer-hand, .title-item-acordion')
                                    || el;
                        alvo.click();
                    }""",
                    elemento,
                )
            except Exception as exc:
                ultimo_erro = exc

            time.sleep(1.0)
            if _empenho_expandido(pagina, num_fmt):
                print(f"    Barra expandida ({num_fmt}).")
                return True

            try:
                elemento.click(timeout=3000, force=True)
            except Exception as exc:
                ultimo_erro = exc

            time.sleep(1.0)
            if _empenho_expandido(pagina, num_fmt):
                print(f"    Barra expandida ({num_fmt}).")
                return True

            caixa = elemento.bounding_box()
            if caixa:
                pagina.mouse.click(
                    caixa["x"] + (caixa["width"] / 2),
                    caixa["y"] + min(caixa["height"] / 2, 24),
                )
                time.sleep(1.0)
                if _empenho_expandido(pagina, num_fmt):
                    print(f"    Barra expandida ({num_fmt}).")
                    return True

        except Exception as exc:
            ultimo_erro = exc

    erros.append(
        f"Não foi possível expandir a barra do empenho {num_fmt}: "
        f"{ultimo_erro or 'cabeçalho não encontrado ou não reagiu ao clique'}"
    )
    return False


def _formatar_numero_empenho(num: str) -> str:
    """Normaliza '2026000136' → '2026NE000136' (mantém se já vier formatado)."""
    n = str(num or "").strip().upper().replace(" ", "")
    return re.sub(r"^(\d{4})(\d{6})$", r"\1NE\2", n)


def _capturar_empenhos_web(pagina) -> list[dict]:
    """Lê as barras (azuis) de empenho da aba Principal Com Orçamento.

    Cada barra exibe algo como:
        'Nº do Empenho: 2022NE002642  Subelemento: 24  Liquidado: SIM  R$: 149,40'

    Retorna uma lista de dicts: {numero, valor, subelemento, liquidado}.
    Falha silenciosa (retorna []) — é usada apenas para enriquecer a
    conferência manual, nunca deve quebrar o fluxo.
    """
    try:
        dados = pagina.evaluate(
            r"""() => {
                const norm = (t) => String(t || '').replace(/\s+/g, ' ').trim();
                const visivel = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                        && s.visibility !== 'hidden' && s.display !== 'none';
                };
                const seletores = '.row.pointer-hand, .box-header, .count-poo-item, '
                    + '[data-count-poo-item], .title-item-acordion, .box.box-solid';
                const resultados = [];
                const vistos = new Set();
                for (const el of Array.from(document.querySelectorAll(seletores))) {
                    if (!visivel(el)) continue;
                    const txt = norm(el.innerText || el.textContent);
                    const up = txt.toUpperCase();
                    if (!up.includes('EMPENHO')) continue;
                    const mNum = up.match(/(\d{4}NE\d{6})/);
                    if (!mNum) continue;
                    const numero = mNum[1];
                    if (vistos.has(numero)) continue;
                    vistos.add(numero);
                    const mVal = txt.match(/R\$\s*:?\s*([\d.]+,\d{2})/);
                    const mSub = txt.match(/Subelemento:\s*(\d+)/i);
                    const mLiq = txt.match(/Liquidado:\s*([A-Za-zÃÇ]+)/i);
                    resultados.push({
                        numero,
                        valor: mVal ? mVal[1] : '',
                        subelemento: mSub ? mSub[1] : '',
                        liquidado: mLiq ? mLiq[1] : '',
                    });
                }
                return resultados;
            }"""
        )
        return dados or []
    except Exception as exc:
        print(f"    Aviso: não foi possível capturar empenhos da web ({exc}).")
        return []


def _comparar_empenhos_pdf_web(empenhos_pdf: list, empenhos_web: list) -> list[str]:
    """Gera linhas de comparação (PDF × IC) por empenho, no formato que o
    painel de conferência sabe renderizar.

    Linhas possíveis:
        Empenho 2026NE000136 — Valor: Web=149.40 | PDF=51683.15
        Empenho ausente no IC: 2026NE000136=51683.15
        Empenho exclusivo no IC: 2022NE002642=149.40
    Empenhos presentes nos dois lados com o mesmo valor não geram linha.
    """
    from comprasnet.base import normalizar_valor

    def _valor_cmp(valor) -> str:
        texto = re.sub(r"[^\d,.\-]+", "", str(valor or ""))
        return normalizar_valor(texto)

    linhas: list[str] = []

    pdf = []
    for e in (empenhos_pdf or []):
        numero = _formatar_numero_empenho(e.get("Empenho", ""))
        if not numero:
            continue
        pdf.append({"numero": numero, "valor": _valor_cmp(e.get("Valor", ""))})

    web = []
    for e in (empenhos_web or []):
        numero = _formatar_numero_empenho(e.get("numero", ""))
        if not numero:
            continue
        web.append({"numero": numero, "valor": _valor_cmp(e.get("valor", ""))})

    web_por_num = {e["numero"]: e for e in web}
    nums_pdf = {e["numero"] for e in pdf}

    for e in pdf:
        w = web_por_num.get(e["numero"])
        if w is None:
            linhas.append(f"Empenho ausente no IC: {e['numero']}={e['valor'] or '—'}")
            continue
        if (w["valor"] or "") != (e["valor"] or ""):
            linhas.append(
                f"Empenho {e['numero']} — Valor: "
                f"Web={w['valor'] or '—'} | PDF={e['valor'] or '—'}"
            )

    for e in web:
        if e["numero"] not in nums_pdf:
            linhas.append(f"Empenho exclusivo no IC: {e['numero']}={e['valor'] or '—'}")

    return linhas


def _verificar_empenho(pagina, num_empenho_pdf: str, erros: list):
    """Confere se o número do empenho visível bate com o do PDF."""
    num_fmt = re.sub(r"^(\d{4})(\d{6})$", r"\1NE\2", num_empenho_pdf)
    try:
        campo = pagina.locator(
            f"xpath=//input[@value='{num_fmt}' or contains(@value,'{num_fmt}')]"
        ).first
        val = campo.input_value().strip()
        print(f"    Verificação empenho → Web: {val} | PDF: {num_fmt}")
        if val != num_fmt:
            erros.append(f"Empenho divergente! Web: {val} | PDF: {num_fmt}")
    except Exception:
        print("    Aviso: não foi possível verificar o campo do empenho.")


# ─────────────────────────────────────────────────────────────────────────────
# PREENCHIMENTO DE CAMPOS COMPARTILHADOS
# ─────────────────────────────────────────────────────────────────────────────

def _preencher_contas_a_pagar(pagina, codigo: str, erros: list, desc: str = ""):
    """Preenche o campo 'Contas a Pagar' com o código informado."""
    def _normalizar_codigo(valor: str) -> str:
        return re.sub(r"\D+", "", str(valor or ""))

    def _codigo_equivalente(valor_campo: str, valor_esperado: str) -> bool:
        atual = _normalizar_codigo(valor_campo)
        esperado = _normalizar_codigo(valor_esperado)
        if not atual or not esperado:
            return False
        if atual == esperado:
            return True
        equivalencias = {
            "104": {"213110400"},
            "1104": {"213111000", "213110400"},
        }
        return atual in equivalencias.get(esperado, set())

    try:
        campo = pagina.locator(
            "xpath=//*[normalize-space(text())='Contas a Pagar']"
            "/following::input[1]"
        ).first
        codigo_str = str(codigo or "").strip()
        # Somente os dígitos são digitados na máscara
        codigo_digitos = re.sub(r"\D+", "", codigo_str)
        valor_final = campo.input_value(timeout=3000).strip()

        if _codigo_equivalente(valor_final, codigo_str):
            print(
                f"    Contas a Pagar já preenchida: '{valor_final}'"
                f"{' ' + desc if desc else ''}"
            )
            return

        for tentativa in range(1, 4):
            # 1. Foco — aguarda template da máscara aparecer (evita fill("") que corrompe)
            campo.click()
            time.sleep(0.15)
            _aguardar_mascara_campo(campo)

            # 2. Posiciona cursor no primeiro '_' (sem selecionar — a máscara avança sozinha)
            campo.evaluate(_JS_POSICIONAR_MASCARA)

            # 3. Digita somente os dígitos editáveis
            campo.press_sequentially(codigo_digitos, delay=90)
            pagina.keyboard.press("Tab")
            time.sleep(0.8)
            valor_final = campo.input_value().strip()

            if _codigo_equivalente(valor_final, codigo_str):
                print(
                    f"    Contas a Pagar: '{valor_final}'"
                    f"{' ' + desc if desc else ''}"
                )
                return
            print(
                f"    Contas a Pagar: valor ficou '{valor_final or 'vazio'}' "
                f"(esperado '{codigo_str}', tentativa {tentativa})."
            )

        erros.append(
            f"Contas a Pagar: campo terminou com '{valor_final or 'vazio'}' "
            f"em vez de '{codigo_str}'."
        )
    except Exception as e:
        erros.append(f"Erro ao preencher Contas a Pagar: {e}")


def _preencher_campo_com_retry(
    pagina,
    locator,
    valor: str,
    erros: list,
    descricao: str = "campo",
    tentativas: int = 2,
    delay_entre: float = 1.0,
):
    """
    Preenche um campo e verifica se o valor ficou depois do Tab.
    Comum em campos de código SIAFI que disparam onBlur para buscar dados.
    """
    for t in range(1, tentativas + 1):
        try:
            locator.click(click_count=3)
            locator.fill("")
            locator.press_sequentially(valor, delay=80)
            pagina.keyboard.press("Tab")
            time.sleep(delay_entre)
            val_atual = locator.input_value().strip()
            if val_atual:
                print(f"    {descricao} → '{val_atual}' (tentativa {t})")
                return val_atual
            print(f"    {descricao}: campo vazio após Tab (tentativa {t}), tentando novamente...")
        except Exception as e:
            if t == tentativas:
                erros.append(f"Erro ao preencher {descricao}: {e}")
    return ""


def _preencher_campo_mascarado_com_retry(
    pagina,
    locator,
    valor: str,
    erros: list,
    descricao: str = "campo",
    tentativas: int = 2,
    delay_entre: float = 1.0,
):
    """
    Preenche campos com máscara fixa preservando zeros à esquerda.

    A máscara do Comprasnet pode reposicionar os dígitos quando usamos fill("")
    ou seleção tripla. Para campos curtos como Conta de Contrato, o fluxo mais
    confiável é o mesmo usado no VPD: focar, esperar o template da máscara,
    posicionar no primeiro '_' e digitar somente os dígitos editáveis.
    """
    valor_str = str(valor or "").strip()
    valor_digitos = re.sub(r"\D+", "", valor_str)
    esperado = valor_digitos or valor_str

    for t in range(1, tentativas + 1):
        try:
            locator.click()
            time.sleep(0.15)
            _aguardar_mascara_campo(locator)
            locator.evaluate(_JS_POSICIONAR_MASCARA)
            locator.press_sequentially(esperado, delay=80)
            pagina.keyboard.press("Tab")
            time.sleep(delay_entre)

            val_atual = locator.input_value().strip()
            val_digitos = re.sub(r"\D+", "", val_atual)
            # A máscara pode completar segmentos APÓS os dígitos digitados
            # (ex.: "02" vira "8.1.2.3.1.02.01"), então os dígitos esperados
            # não ficam no final. Aceita se aparecerem em qualquer posição.
            if val_atual and (not esperado or esperado in val_digitos):
                print(f"    {descricao} → '{val_atual}' (tentativa {t})")
                return val_atual

            print(
                f"    {descricao}: valor ficou '{val_atual or 'vazio'}' "
                f"(esperado final '{esperado}', tentativa {t})."
            )
        except Exception as e:
            if t == tentativas:
                erros.append(f"Erro ao preencher {descricao}: {e}")

    return ""


def _preencher_vpd(pagina, vpd_codigo: str, erros: list):
    """Preenche 'Conta Variação Patrimonial Diminutiva' com o código VPD.

    Se o campo não existir (ex: tipo DH DSP 101), ignora silenciosamente.
    """
    if not vpd_codigo:
        try:
            loc_check = pagina.locator(
                "xpath=//*[contains(normalize-space(text()),'Variação Patrimonial')]"
                "/following::input[1]"
            ).first
            loc_check.wait_for(state="visible", timeout=2000)
            existe = True
        except Exception:
            existe = False
        if existe:
            erros.append("VPD não encontrado para a natureza — preencha manualmente.")
        else:
            print("    VPD: campo não presente na página (tipo DH sem VPD) — ignorado.")
        return

    if "De acordo" in vpd_codigo:
        erros.append(
            f"VPD '{vpd_codigo}' requer conferência manual (código variável ou 'De acordo c/ NF')."
        )
        return

    try:
        vpd_normalizado = re.sub(r"(?i)x", "1", str(vpd_codigo or ""))
        vpd_partes = [parte.strip() for parte in vpd_normalizado.split(".") if parte.strip()]
        if len(vpd_partes) >= 7:
            vpd_editavel = ".".join(vpd_partes[4:-1])
            vpd_digitos = "".join(vpd_partes[4:-1])
        elif len(vpd_partes) >= 6:
            vpd_editavel = ".".join(vpd_partes[4:-1])
            vpd_digitos = "".join(vpd_partes[4:-1])
        else:
            vpd_editavel = re.sub(r"\D+", "", vpd_normalizado)
            vpd_digitos = vpd_editavel

        locator_vpd = pagina.locator(
            "xpath=//*[contains(normalize-space(text()),'Variação Patrimonial')]"
            "/following::input[1]"
        ).first
        try:
            locator_vpd.wait_for(state="visible", timeout=3000)
        except Exception:
            print(f"    VPD: campo não encontrado na página — código '{vpd_codigo}' ignorado.")
            return

        campo = locator_vpd
        # Foco primeiro — só depois lemos o valor, para garantir que a máscara
        # inicializou e exibe os '_' de placeholder.
        campo.click()
        time.sleep(0.15)
        _aguardar_mascara_campo(campo)

        # Posiciona cursor no primeiro '_' (sem selecionar intervalo — a
        # máscara avança sozinha pelos separadores fixos ao digitar).
        campo.evaluate(_JS_POSICIONAR_MASCARA)
        campo.press_sequentially(vpd_digitos or re.sub(r"\D+", "", vpd_normalizado), delay=80)

        pagina.keyboard.press("Tab")
        time.sleep(0.8)
        val = campo.input_value().strip()
        print(f"    VPD preenchida: '{val}' (complemento: '{vpd_digitos or vpd_editavel or vpd_normalizado}')")
    except Exception as e:
        erros.append(f"Erro ao preencher VPD ({vpd_codigo}): {e}")
