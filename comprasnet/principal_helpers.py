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


def _marcar_empenho_atual(pagina, num_empenho: str) -> bool:
    """Marca o painel expandido do empenho atual para os preenchimentos escopados."""
    num_fmt = _formatar_numero_empenho(num_empenho)
    try:
        return bool(
            pagina.evaluate(
                r"""(numEmp) => {
                    const normalizar = (txt) => (txt || '').replace(/\s+/g, '').toUpperCase();
                    const alvo = normalizar(numEmp);
                    const visivel = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        const estilo = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && estilo.visibility !== 'hidden'
                            && estilo.display !== 'none';
                    };
                    document.querySelectorAll('[data-autoliquid-empenho-atual="1"]')
                        .forEach((el) => el.removeAttribute('data-autoliquid-empenho-atual'));
                    document.body.removeAttribute('data-autoliquid-empenho-sufixo');
                    const painelDo = (el) => {
                        const preferido = el.closest('.count-poo-item, [data-count-poo-item], .box.box-solid, .box, .panel, .card, section, fieldset, form');
                        if (preferido) return preferido;
                        let atual = el;
                        while (atual && atual !== document.body) {
                            const txt = normalizar(atual.innerText || atual.textContent);
                            const inputs = atual.querySelectorAll ? atual.querySelectorAll('input').length : 0;
                            if (txt.includes(alvo) && inputs >= 3) return atual;
                            atual = atual.parentElement;
                        }
                        return el.parentElement || el;
                    };

                    const inputs = Array.from(document.querySelectorAll('input')).filter((el) => {
                        return visivel(el) && normalizar(el.value || '').includes(alvo);
                    });
                    for (const input of inputs) {
                        const painel = painelDo(input);
                        if (painel && visivel(painel)) {
                            painel.setAttribute('data-autoliquid-empenho-atual', '1');
                            const sufixo = String(input.id || '').match(/^numempe(.+)$/)?.[1] || '';
                            if (sufixo) document.body.setAttribute('data-autoliquid-empenho-sufixo', sufixo);
                            painel.scrollIntoView({ block: 'center', inline: 'nearest' });
                            return true;
                        }
                    }

                    const headers = Array.from(document.querySelectorAll('.row.pointer-hand, .box-header, .title-item-acordion, .panel-heading, .card-header, div'))
                        .filter((el) => visivel(el) && normalizar(el.innerText || el.textContent).includes(alvo));
                    for (const header of headers) {
                        const painel = painelDo(header);
                        if (painel && visivel(painel)) {
                            painel.setAttribute('data-autoliquid-empenho-atual', '1');
                            const input = Array.from(painel.querySelectorAll('input[id^="numempe"]'))
                                .find((el) => normalizar(el.value || '').includes(alvo));
                            const sufixo = String(input?.id || '').match(/^numempe(.+)$/)?.[1] || '';
                            if (sufixo) document.body.setAttribute('data-autoliquid-empenho-sufixo', sufixo);
                            painel.scrollIntoView({ block: 'center', inline: 'nearest' });
                            return true;
                        }
                    }
                    return false;
                }""",
                num_fmt,
            )
        )
    except Exception:
        return False


def _campo_empenho_atual(pagina, rotulo: str):
    """Retorna o primeiro input após um rótulo dentro do painel marcado."""
    prefixos_por_rotulo = {
        "Conta de Bens": "numclassa",
        "Conta de Estoque": "numclassa",
        "Contas a Pagar": "numclassb",
        "Variação Patrimonial": "numclassc",
    }
    prefixo = next((pref for chave, pref in prefixos_por_rotulo.items() if chave in rotulo), "")
    if prefixo:
        try:
            sufixo = pagina.evaluate("() => document.body.getAttribute('data-autoliquid-empenho-sufixo') || ''")
            if sufixo:
                return pagina.locator(f"#{prefixo}{sufixo}").first
        except Exception:
            pass

    raiz = pagina.locator("[data-autoliquid-empenho-atual='1']").first
    return raiz.locator(
        f"xpath=.//*[contains(normalize-space(text()),'{rotulo}')]"
        "/following::input[1]"
    ).first


def _sufixo_empenho_atual(pagina) -> str:
    try:
        return str(pagina.evaluate("() => document.body.getAttribute('data-autoliquid-empenho-sufixo') || ''") or "")
    except Exception:
        return ""


def _preencher_campo_empenho_por_prefixo(pagina, prefixo: str, valor: str) -> str:
    """Preenche campo do item PCO atual por ID real, mesmo se o painel estiver recolhido."""
    sufixo = _sufixo_empenho_atual(pagina)
    if not sufixo or not prefixo or not valor:
        return ""
    try:
        return str(
            pagina.evaluate(
                """([prefixo, sufixo, valor]) => {
                    const el = document.getElementById(`${prefixo}${sufixo}`);
                    if (!el) return '';
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                    el.focus();
                    if (setter) setter.call(el, valor); else el.value = valor;
                    el.defaultValue = valor;
                    el.setAttribute('value', valor);
                    el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                    return el.value || '';
                }""",
                [prefixo, sufixo, str(valor)],
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _preencher_campo_empenho_mascarado_por_prefixo(
    pagina,
    prefixo: str,
    valor_formatado: str,
    valor_digitos: str,
) -> str:
    """Preenche campo mascarado por ID real usando inputmask quando disponível."""
    sufixo = _sufixo_empenho_atual(pagina)
    if not sufixo or not prefixo:
        return ""
    try:
        return str(
            pagina.evaluate(
                """([prefixo, sufixo, formatado, digitos]) => {
                    const el = document.getElementById(`${prefixo}${sufixo}`);
                    if (!el) return '';

                    const fire = () => {
                        el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    };
                    const setNative = (val) => {
                        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                        el.focus();
                        if (setter) setter.call(el, val); else el.value = val;
                        el.defaultValue = val;
                        el.setAttribute('value', val);
                        fire();
                        return el.value || '';
                    };
                    const completo = (val) => String(val || '').replace(/\\D/g, '') === String(formatado || '').replace(/\\D/g, '');

                    if (window.$ && $(el).inputmask) {
                        try {
                            $(el).inputmask('setvalue', digitos);
                            fire();
                            if (completo(el.value)) return el.value || '';
                            $(el).inputmask('setvalue', formatado);
                            fire();
                            if (completo(el.value)) return el.value || '';
                        } catch(e) {}
                    }

                    const viaDigitos = setNative(digitos);
                    if (completo(viaDigitos)) return viaDigitos;
                    const viaFormatado = setNative(formatado);
                    if (completo(viaFormatado)) return viaFormatado;
                    return viaDigitos || el.value || '';
                }""",
                [prefixo, sufixo, str(valor_formatado), str(valor_digitos)],
            )
            or ""
        ).strip()
    except Exception:
        return ""


def _campo_empenho_por_prefixo(pagina, prefixo: str):
    sufixo = _sufixo_empenho_atual(pagina)
    if not sufixo or not prefixo:
        return None
    return pagina.locator(f"#{prefixo}{sufixo}").first


def _valor_contas_a_pagar_formatado(codigo: str) -> str:
    digitos = re.sub(r"\D+", "", str(codigo or ""))
    if digitos in {"104", "1104"}:
        return "2.1.3.1.1.04.00"
    return str(codigo or "").strip()


def _valor_conta_estoque_formatado(codigo: str) -> str:
    digitos = re.sub(r"\D+", "", str(codigo or ""))
    if digitos == "60100":
        return "1.1.5.6.1.01.00"
    return str(codigo or "").strip()


def _campo_equivalente_contas_a_pagar(valor_campo: str, valor_esperado: str) -> bool:
    atual = re.sub(r"\D+", "", str(valor_campo or ""))
    esperado = re.sub(r"\D+", "", str(valor_esperado or ""))
    if not atual or not esperado:
        return False
    if atual == esperado:
        return True
    equivalencias = {
        "104": {"213110400"},
        "1104": {"213111000", "213110400"},
    }
    return atual in equivalencias.get(esperado, set())


def _digitar_mascara_no_primeiro_placeholder(pagina, campo, digitos: str, delay_ms: int = 45) -> str:
    """Digita os dígitos no primeiro '_' preservando a máscara já pré-preenchida."""
    if campo is None:
        return ""
    campo.click()
    time.sleep(0.05)
    _aguardar_mascara_campo(campo)
    campo.evaluate(
        """(el) => {
            const valor = String(el.value || '');
            const primeiro = valor.indexOf('_');
            el.focus();
            const pos = primeiro >= 0 ? primeiro : valor.length;
            try {
                if (window.$ && $(el).caret) $(el).caret(pos);
            } catch(e) {}
            try { el.setSelectionRange(pos, pos); } catch(e) {}
        }"""
    )
    # Teclas reais disparam melhor os hooks do inputmask do SIAFI do que insert_text.
    campo.press_sequentially(str(digitos or ""), delay=delay_ms)
    pagina.keyboard.press("Tab")
    time.sleep(0.35)
    return campo.input_value().strip()


def _reparar_contas_a_pagar_empenhos(pagina, empenhos: list, codigo: str, erros: list) -> None:
    """Última passada: garante Contas a Pagar em cada empenho usando IDs numclassb."""
    codigo_digitos = re.sub(r"\D+", "", str(codigo or ""))
    if not codigo_digitos:
        return
    for emp in empenhos or []:
        numero = _formatar_numero_empenho((emp or {}).get("Empenho", ""))
        if not numero:
            continue
        try:
            _marcar_empenho_atual(pagina, numero)
            sufixo = _sufixo_empenho_atual(pagina)
            if not sufixo:
                continue
            campo = _campo_empenho_por_prefixo(pagina, "numclassb")
            if campo is None:
                continue
            valor_atual = campo.input_value(timeout=2000).strip()
            if _campo_equivalente_contas_a_pagar(valor_atual, codigo):
                continue
            valor_final = _digitar_mascara_no_primeiro_placeholder(pagina, campo, codigo_digitos, delay_ms=35)
            if _campo_equivalente_contas_a_pagar(valor_final, codigo):
                print(f"    Contas a Pagar reparada ({numero}): '{valor_final}'")
            else:
                erros.append(f"Contas a Pagar {numero}: campo terminou com '{valor_final or 'vazio'}'.")
        except Exception as exc:
            erros.append(f"Contas a Pagar {numero}: reparo final falhou ({exc}).")


def _pre_expandir_barras_empenhos(pagina, empenhos: list, erros: list | None = None) -> set[str]:
    """Abre em lote todos os painéis de empenho presentes na aba.

    O Comprasnet demora bastante quando cada handler procura e abre sua barra
    separadamente. Este passo localiza todos os números do PDF e clica nos
    cabeçalhos fechados primeiro, deixando os campos disponíveis para o
    preenchimento escopado por empenho.
    """
    numeros = []
    for emp in empenhos or []:
        numero = _formatar_numero_empenho((emp or {}).get("Empenho", ""))
        if numero and numero not in numeros:
            numeros.append(numero)
    if not numeros:
        return set()

    try:
        resultado = pagina.evaluate(
            r"""(nums) => {
                const normalizar = (txt) => (txt || '').replace(/\s+/g, ' ').trim().toUpperCase();
                const normalizarCompacto = (txt) => normalizar(txt).replace(/\s+/g, '');
                const visivel = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const estilo = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && estilo.visibility !== 'hidden'
                        && estilo.display !== 'none';
                };
                const estaExpandido = (num) => {
                    const alvo = normalizarCompacto(num);
                    return Array.from(document.querySelectorAll('input'))
                        .some((el) => visivel(el) && normalizarCompacto(el.value || '').includes(alvo));
                };
                const acharHeader = (num) => {
                    const alvo = normalizar(num);
                    const roots = Array.from(document.querySelectorAll('.count-poo-item, [data-count-poo-item], .box.box-solid, .box, .panel, .card, .row.pointer-hand, .box-header, div'));
                    const candidatos = [];
                    for (const root of roots) {
                        if (!visivel(root)) continue;
                        const txt = normalizar(root.innerText || root.textContent);
                        if (!txt.includes(alvo) || !txt.includes('EMPENHO')) continue;
                        const container = root.closest('.count-poo-item, [data-count-poo-item], .box.box-solid, .box, .panel, .card') || root;
                        const header = container.querySelector('.row.pointer-hand, .box-header, .title-item-acordion, .panel-heading, .card-header')
                            || root.closest('.row.pointer-hand, .box-header, .title-item-acordion, .panel-heading, .card-header')
                            || root;
                        if (!visivel(header)) continue;
                        let score = 0;
                        const htxt = normalizar(header.innerText || header.textContent);
                        if (htxt.includes(alvo)) score += 20;
                        if (htxt.includes('SUBELEMENTO')) score += 4;
                        if (htxt.includes('LIQUIDADO')) score += 4;
                        if (htxt.includes('R$')) score += 2;
                        if (header.matches('.row.pointer-hand, .box-header, .title-item-acordion')) score += 10;
                        score -= Math.min(htxt.length, 600) / 200;
                        candidatos.push({ header, score });
                    }
                    candidatos.sort((a, b) => b.score - a.score);
                    return candidatos[0]?.header || null;
                };

                const clicados = [];
                const jaAbertos = [];
                const naoEncontrados = [];
                for (const num of nums) {
                    if (estaExpandido(num)) {
                        jaAbertos.push(num);
                        continue;
                    }
                    const header = acharHeader(num);
                    if (!header) {
                        naoEncontrados.push(num);
                        continue;
                    }
                    header.scrollIntoView({ block: 'center', inline: 'nearest' });
                    header.click();
                    clicados.push(num);
                }
                return { clicados, jaAbertos, naoEncontrados };
            }""",
            numeros,
        ) or {}
    except Exception as exc:
        print(f"    Aviso: pré-expansão dos empenhos falhou ({exc}); usando abertura individual.")
        resultado = {"clicados": [], "jaAbertos": [], "naoEncontrados": numeros}

    abertos = set(resultado.get("jaAbertos") or [])
    limite = time.time() + (2.2 if resultado.get("clicados") else 0.3)
    while time.time() < limite:
        abertos = {numero for numero in numeros if _empenho_expandido(pagina, numero)}
        if len(abertos) == len(numeros):
            break
        time.sleep(0.15)

    for numero in numeros:
        if numero not in abertos and _empenho_expandido(pagina, numero):
            abertos.add(numero)

    nao_encontrados = (set(resultado.get("naoEncontrados") or []) | (set(numeros) - abertos)) - abertos
    print(
        "    Empenhos pré-abertos: "
        f"{len(abertos)}/{len(numeros)}"
        + (f" | não encontrados: {', '.join(sorted(nao_encontrados))}" if nao_encontrados else "")
    )
    return abertos


def _expandir_barra_empenho(pagina, num_empenho_pdf: str, erros: list) -> bool:
    """Localiza e clica na barra azul do empenho para expandi-la."""
    num_fmt = re.sub(r"^(\d{4})(\d{6})$", r"\1NE\2", num_empenho_pdf)
    if _empenho_expandido(pagina, num_fmt):
        _marcar_empenho_atual(pagina, num_fmt)
        print(f"    Barra já expandida ({num_fmt}).")
        return True
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
                        _marcar_empenho_atual(pagina, num_fmt)
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
                _marcar_empenho_atual(pagina, num_fmt)
                print(f"    Barra expandida ({num_fmt}).")
                return True

            try:
                elemento.click(timeout=3000, force=True)
            except Exception as exc:
                ultimo_erro = exc

            time.sleep(1.0)
            if _empenho_expandido(pagina, num_fmt):
                _marcar_empenho_atual(pagina, num_fmt)
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
                    _marcar_empenho_atual(pagina, num_fmt)
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
        _marcar_empenho_atual(pagina, num_fmt)
        campo = pagina.locator("[data-autoliquid-empenho-atual='1']").first.locator(
            f"xpath=.//input[@value='{num_fmt}' or contains(@value,'{num_fmt}')]"
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
    try:
        codigo_str = str(codigo or "").strip()
        codigo_digitos = re.sub(r"\D+", "", codigo_str)
        campo = _campo_empenho_atual(pagina, "Contas a Pagar")
        try:
            campo.wait_for(state="visible", timeout=1200)
        except Exception:
            campo = pagina.locator(
                "xpath=//*[normalize-space(text())='Contas a Pagar']"
                "/following::input[1]"
            ).first
        valor_final = campo.input_value(timeout=3000).strip()

        if _campo_equivalente_contas_a_pagar(valor_final, codigo_str):
            print(
                f"    Contas a Pagar já preenchida: '{valor_final}'"
                f"{' ' + desc if desc else ''}"
            )
            return

        for tentativa in range(1, 4):
            valor_final = _digitar_mascara_no_primeiro_placeholder(pagina, campo, codigo_digitos, delay_ms=45)

            if _campo_equivalente_contas_a_pagar(valor_final, codigo_str):
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
            loc_check = _campo_empenho_atual(pagina, "Variação Patrimonial")
            try:
                loc_check.wait_for(state="visible", timeout=800)
            except Exception:
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

        locator_vpd = _campo_empenho_atual(pagina, "Variação Patrimonial")
        try:
            locator_vpd.wait_for(state="visible", timeout=1200)
        except Exception:
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
