"""
comprasnet_dados_pagamento.py
Preenche a aba Dados de Pagamento.
"""

from __future__ import annotations

import re
import time

from comprasnet.base import conectar, preencher_data, normalizar_valor, clicar_aba_generica, aguardar_aba_ativa


def _documentos_para_observacao(dados_extraidos: dict) -> list[tuple[str, str]]:
    documentos: list[tuple[str, str]] = []
    for nota in dados_extraidos.get("Notas Fiscais", []):
        numero = str(nota.get("Número da Nota", "") or "").strip()
        if not numero:
            continue
        tipo = str(nota.get("Tipo", "") or "").upper()
        categoria = "FATURA" if "FATURA" in tipo else "NF"
        documentos.append((categoria, numero))
    return documentos


def _montar_observacao(dados_extraidos: dict) -> str:
    documentos = _documentos_para_observacao(dados_extraidos)
    nfs = [numero for categoria, numero in documentos if categoria == "NF"]
    faturas = [numero for categoria, numero in documentos if categoria == "FATURA"]
    sol = str(dados_extraidos.get("Solicitação de Pagamento", "") or "").strip()
    tem_contrato = dados_extraidos.get("Tem Contrato?", dados_extraidos.get("Tem Contrato", "Não")) == "Sim"
    num_contrato = str(dados_extraidos.get("Número do Contrato", "") or "").strip()

    partes: list[str] = []
    if nfs:
        partes.append(f"Pagamento {'NF' if len(nfs) == 1 else 'NFs'} {', '.join(nfs)}")
    if faturas:
        partes.append(f"{'Fatura' if len(faturas) == 1 else 'Faturas'} {', '.join(faturas)}")
    if not partes:
        partes.append("Pagamento NF —")
    if tem_contrato and num_contrato:
        partes.append(f"Contrato {num_contrato}")
    if sol:
        partes.append(f"Solicitação Pagamento {sol}")
    return " - ".join(partes) + "."


def _clicar_aba_dados_pagamento(pagina) -> None:
    """Navega para a aba Dados de Pagamento de forma resiliente."""

    seletores_conteudo = [
        "#dados-pagamento",
        "input[name='dtpagamento'], input[name='dtvencimento']",
        "button[name='confirma-dados-pagamento']",
    ]

    # Verifica se já está na aba
    if aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=800):
        return

    # Tenta seletores CSS diretos
    css_candidatos = [
        "#dados-pagamento-tab",
        "a[href='#dados-pagamento']",
        "a[data-target='#dados-pagamento']",
        "button[aria-controls='dados-pagamento']",
        "a[aria-controls='dados-pagamento']",
    ]
    clicou = pagina.evaluate(
        """(candidatos) => {
            const visivel = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
            };
            for (const sel of candidatos) {
                try {
                    const el = document.querySelector(sel);
                    if (visivel(el)) { el.click(); return sel; }
                } catch {}
            }
            return '';
        }""",
        css_candidatos,
    )
    if clicou and aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=5000):
        return

    # Tenta get_by_role
    try:
        loc = pagina.get_by_role("tab", name=re.compile("dados de pagamento", re.I))
        if loc.count() > 0:
            loc.first.click(timeout=3000)
            if aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=5000):
                return
    except Exception:
        pass

    # Fallback genérico por texto
    for texto in ("Dados de Pagamento", "Dados de pagamento", "Pagamento"):
        if clicar_aba_generica(pagina, texto, timeout_ms=3000):
            time.sleep(0.3)
            if aguardar_aba_ativa(pagina, seletores_conteudo, timeout_ms=5000):
                return

    # Último recurso: wait_for_function mais amplo
    try:
        pagina.wait_for_function(
            """() => {
                const visivel = (el) => !!el && el.offsetParent !== null;
                const painel = document.querySelector("#dados-pagamento");
                if (visivel(painel)) return true;
                return Array.from(document.querySelectorAll("input, textarea, button"))
                    .some((el) => visivel(el) && /dados.de.pagamento/i.test(
                        (el.parentElement?.innerText || el.textContent || "")
                    ));
            }""",
            timeout=3000,
        )
        return
    except Exception as exc:
        raise RuntimeError(f"Aba Dados de Pagamento não encontrada: {exc}")

def _esperar_dados_pagamento_prontos(pagina, timeout_ms: int = 15000) -> None:
    """Aguarda a aba Dados de Pagamento estar pronta para interação.
    Condição: botão 'Confirmar Dados de Pagamento' visível OU botão Pré-Doc visível.
    Evita buscar pelo ID do campo de data (varia entre portais).
    """
    pagina.wait_for_function(
        """() => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            // Confirmar Dados de Pagamento
            const temConfirmar = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'))
                .some((el) => visivel(el) && /confirmar.*pagamento/i.test(String(el.textContent || el.value || '').trim()));
            // Pré-Doc
            const temPredoc = Array.from(document.querySelectorAll('button, a, span, div, input'))
                .some((el) => visivel(el) && /pr[eé].?doc/i.test(String(el.textContent || el.value || '').trim()));
            return temConfirmar || temPredoc;
        }""",
        timeout=timeout_ms,
    )


def _achar_botao_confirmar_pagamento(pagina):
    return pagina.evaluate_handle(
        """() => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            const seletores = [
                "button[name='confirma-dados-pagamento']",
                "input[name='confirma-dados-pagamento']",
                "#btnSubmitFormSfDadosPagamento",
                "button, input[type='submit'], input[type='button'], a, span"
            ];
            const botoes = [];
            for (const seletor of seletores) {
                for (const el of document.querySelectorAll(seletor)) {
                    if (!botoes.includes(el)) botoes.push(el);
                }
            }
            return botoes.find((el) => {
                if (!visivel(el)) return false;
                const texto = String(el.textContent || el.value || '').trim().toLowerCase();
                const idName = String(el.id || '') + ' ' + String(el.name || '');
                return (
                    texto.includes('confirmar') && texto.includes('pagamento')
                ) || /confirma.*pagamento/i.test(idName);
            }) || null;
        }"""
    )


def _achar_botao_predoc(pagina):
    return pagina.evaluate_handle(
        """() => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            const seletores = 'button, a, input, div, span, td';
            const els = Array.from(document.querySelectorAll(seletores));
            return els.find((el) => {
                if (!visivel(el)) return false;
                const txt = String(el.textContent || el.value || '').trim();
                return txt.length < 40 && /pr[eé].doc/i.test(txt);
            }) || null;
        }"""
    )


def _clicar_handle(pagina, handle, descricao: str) -> None:
    tipo = pagina.evaluate("el => el ? el.tagName : null", handle)
    if not tipo:
        raise RuntimeError(f"{descricao} nao encontrado.")
    pagina.evaluate(
        """(el) => {
            el.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
            el.click();
        }""",
        handle,
    )


def _preencher_campo_visivel_por_ids(pagina, ids: list[str], valor: str) -> bool:
    for fid in ids:
        try:
            loc = pagina.locator(f"#{fid}:visible").first
            if loc.count() == 0:
                continue
            loc.wait_for(state="visible", timeout=4000)
            loc.click(click_count=3)
            try:
                loc.fill("")
            except Exception:
                pass
            loc.fill(str(valor))
            pagina.keyboard.press("Tab")
            time.sleep(0.2)
            return True
        except Exception:
            continue
    return False


def _esperar_modal_predoc(pagina, timeout_ms: int = 20000) -> None:
    pagina.wait_for_function(
        """() => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            const temTextarea = Array.from(document.querySelectorAll('textarea')).some(visivel);
            const temProcesso = Array.from(document.querySelectorAll('input'))
                .some((el) => visivel(el) && /processo/i.test(`${el.id || ''} ${el.name || ''}`));
            const temLupa = visivel(document.querySelector('#buttonContasFavorecido'));
            return temTextarea || temProcesso || temLupa;
        }""",
        timeout=timeout_ms,
    )


def _selecionar_tipo_ob_modal(pagina, tipo_ob: str) -> bool:
    if not tipo_ob:
        return False
    try:
        return bool(
            pagina.evaluate(
                """(tipo) => {
                    const visivel = (el) => !!el && el.offsetParent !== null;
                    const normalizar = (txt) => String(txt || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    for (const select of document.querySelectorAll('select')) {
                        if (!visivel(select)) continue;
                        const options = Array.from(select.options || []);
                        const alvo = options.find((option) => normalizar(option.text).includes(normalizar(tipo)));
                        if (!alvo) continue;
                        select.value = alvo.value;
                        select.dispatchEvent(new Event('input', { bubbles: true }));
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""",
                tipo_ob,
            )
        )
    except Exception:
        return False


def _preencher_lf_modal(pagina, lf_numero: str) -> bool:
    if not lf_numero:
        return False
    try:
        return bool(
            pagina.evaluate(
                """(lf) => {
                    const visivel = (el) => !!el && el.offsetParent !== null;
                    const candidatos = Array.from(document.querySelectorAll('input, textarea')).filter((el) => {
                        if (!visivel(el)) return false;
                        const idName = `${el.id || ''} ${el.name || ''}`.toLowerCase();
                        const contexto = `${el.parentElement.innerText || ''}`.toLowerCase();
                        return idName.includes('lf') || idName.includes('lista') || contexto.includes('lf') || contexto.includes('lista');
                    });
                    const campo = candidatos[0];
                    if (!campo) return false;
                    campo.focus();
                    campo.value = lf;
                    campo.dispatchEvent(new Event('input', { bubbles: true }));
                    campo.dispatchEvent(new Event('change', { bubbles: true }));
                    campo.blur();
                    return true;
                }""",
                lf_numero,
            )
        )
    except Exception:
        return False


def _preencher_observacao_modal(pagina, obs: str) -> bool:
    try:
        loc = pagina.locator("textarea:visible").last
        loc.wait_for(state="visible", timeout=5000)
        loc.fill(obs)
        return True
    except Exception:
        return False


def _confirmar_dados_pagamento(pagina, descricao: str, obrigatorio: bool = True) -> bool:
    ultimo_erro = None

    for _ in range(3):
        try:
            _esperar_dados_pagamento_prontos(pagina, timeout_ms=5000)
        except Exception:
            pass

        handle = _achar_botao_confirmar_pagamento(pagina)
        try:
            _clicar_handle(pagina, handle, descricao)
            pagina.wait_for_timeout(250)
            return True
        except Exception as exc:
            ultimo_erro = exc
            time.sleep(0.6)

    if obrigatorio:
        raise RuntimeError(f"{descricao} nao encontrado.") from ultimo_erro

    print(f"  [Aviso] {descricao} não apareceu novamente; seguindo sem erro.")
    return False


def _clicar_predoc(pagina) -> None:
    handle = _achar_botao_predoc(pagina)
    _clicar_handle(pagina, handle, "BotÃ£o PrÃ©-Doc")
    _esperar_modal_predoc(pagina)


def _preencher_dados_bancarios(pagina, banco: str, agencia: str, conta: str) -> None:
    """Preenche Banco, Agência e Conta do Domicílio Bancário do Favorecido no modal Pré-Doc.

    Estratégia:
    1. Tenta IDs conhecidos do portal (sfpredoc*, banco, agencia, conta).
    2. Fallback: localiza o bloco "Favorecido" no DOM e preenche os inputs seguintes por rótulo
       de célula adjacente — evitando confundir com o bloco "Pagador".
    3. Para a Conta, além do evaluate, usa Playwright fill() como reforço (lookup field).
    """
    resultado = pagina.evaluate(
        """([banco, agencia, conta]) => {
            const visivel = (el) => !!el && el.offsetParent !== null;
            const setVal = (inp, val) => {
                if (!inp || !visivel(inp) || !val) return false;
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                inp.focus();
                if (setter) setter.call(inp, val); else inp.value = val;
                inp.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                inp.blur();
                return true;
            };

            const preenchido = { banco: false, agencia: false, conta: false };

            // ── Estratégia 1: IDs específicos do portal ────────────────────────
            const idsBanco   = ['sfpredocbanco', 'bancoFavorecido', 'banco', 'codbanco', 'sfpredoccodbanco'];
            const idsAgencia = ['sfpredocagencia', 'agenciaFavorecido', 'agencia', 'sfpredoccodagencia', 'numAgencia'];
            const idsConta   = ['sfpredocconta', 'contaFavorecido', 'numconta', 'sfpredocnumconta', 'numeroConta'];

            for (const id of idsBanco)   { const el = document.getElementById(id); if (el && setVal(el, banco))   { preenchido.banco   = true; break; } }
            for (const id of idsAgencia) { const el = document.getElementById(id); if (el && setVal(el, agencia)) { preenchido.agencia = true; break; } }
            for (const id of idsConta)   { const el = document.getElementById(id); if (el && setVal(el, conta))   { preenchido.conta   = true; break; } }

            // ── Estratégia 2: DOM contextual (bloco "Favorecido") ──────────────
            if (!preenchido.banco || !preenchido.agencia || !preenchido.conta) {
                // Encontra o nó de texto "Favorecido" mais próximo de um formulário
                const candidatos = Array.from(document.querySelectorAll(
                    'td, th, label, span, div, h4, h5, strong'
                )).filter(el => visivel(el) && /favorecido/i.test(el.textContent.trim())
                                            && !/pagador/i.test(el.textContent.trim()));

                let raizFavorecido = candidatos.length > 0
                    ? (candidatos[0].closest('table, fieldset, div.row, div.form-group') || candidatos[0].parentElement)
                    : null;

                if (raizFavorecido) {
                    const inputs = Array.from(raizFavorecido.querySelectorAll(
                        'input[type="text"], input:not([type])'
                    )).filter(visivel);

                    const rotulos = [
                        { campo: 'banco',   termos: ['banco'],    valor: banco },
                        { campo: 'agencia', termos: ['ag', 'agência', 'agencia'], valor: agencia },
                        { campo: 'conta',   termos: ['conta'],    valor: conta },
                    ];

                    for (const inp of inputs) {
                        const td = inp.closest('td');
                        const prevTd = td ? td.previousElementSibling : null;
                        const labelEl = inp.labels && inp.labels[0] ? inp.labels[0] : null;
                        const ctx = [
                            labelEl ? labelEl.textContent : '',
                            prevTd ? prevTd.textContent : '',
                            inp.id || '',
                            inp.name || '',
                            inp.placeholder || '',
                        ].join(' ').toLowerCase();

                        for (const r of rotulos) {
                            if (!preenchido[r.campo] && r.termos.some(t => ctx.includes(t))) {
                                if (setVal(inp, r.valor)) preenchido[r.campo] = true;
                            }
                        }
                    }
                }
            }

            return preenchido;
        }""",
        [banco, agencia, conta],
    )
    print(f"  [Domicílio Bancário Favorecido] banco={banco} ag={agencia} conta={conta} → {resultado}")

    # Reforço Playwright para a Conta (campo de lookup — fill() é mais confiável)
    if conta:
        try:
            # Tenta pelo botão de lupa associado (buttonContasFavorecido)
            btn_lupa = pagina.locator("#buttonContasFavorecido:visible").first
            if btn_lupa.count() > 0:
                # Campo de texto que precede a lupa
                inp_conta = btn_lupa.locator("xpath=preceding::input[1]")
                if inp_conta.count() > 0:
                    inp_conta.click(click_count=3)
                    inp_conta.fill(conta)
                    inp_conta.press("Tab")
            else:
                # Fallback: inputs visíveis com "conta" no contexto
                for loc in pagina.locator("input:visible").all():
                    try:
                        ctx = pagina.evaluate(
                            """(el) => {
                                const td = el.closest('td');
                                const prev = td && td.previousElementSibling;
                                return ((prev ? prev.textContent : '') + ' ' + (el.id || '') + ' ' + (el.name || '')).toLowerCase();
                            }""",
                            loc.element_handle(),
                        )
                        if ctx and "conta" in ctx and "pagador" not in ctx:
                            loc.click(click_count=3)
                            loc.fill(conta)
                            loc.press("Tab")
                            break
                    except Exception:
                        continue
        except Exception as e_conta:
            print(f"  [Aviso] Reforço Playwright Conta: {e_conta}")


def _salvar_modal_predoc(pagina) -> None:
    botao_salvar = pagina.locator("#btnSalvar:visible").first
    botao_salvar.wait_for(state="visible", timeout=8000)
    botao_salvar.click()
    pagina.wait_for_function(
        """() => {
            const botao = document.querySelector('#btnSalvar');
            return !botao || botao.offsetParent === null;
        }""",
        timeout=12000,
    )


def _preencher_data_pagamento(pagina, data_ddmmaaaa: str) -> None:
    """Preenche a Data de Pagamento via JS setter — sem press_sequentially, sem delays.

    Estratégia:
    1. Converte para ISO (AAAA-MM-DD) e BR (DD/MM/AAAA).
    2. JS: encontra o campo pelo name (dtpagamento / dtvencimento) ou por label
       adjacente, e usa o prototype setter para type='date' (ISO) ou
       inputmask.setvalue para type='text' mascarado (BR).
    3. Playwright fill() como fallback rápido.
    4. preencher_data() (press_sequentially) como último recurso.
    """
    data_ddmmaaaa = str(data_ddmmaaaa or "").strip()
    if not data_ddmmaaaa:
        raise ValueError("Data de Pagamento vazia.")

    partes = re.split(r"[/\-]", data_ddmmaaaa)
    if len(partes) != 3:
        raise ValueError(f"Formato de data inválido: '{data_ddmmaaaa}'")
    if len(partes[0]) == 4:
        aaaa, mm, dd = partes[0], partes[1].zfill(2), partes[2].zfill(2)
    else:
        dd, mm, aaaa = partes[0].zfill(2), partes[1].zfill(2), partes[2]
    iso = f"{aaaa}-{mm}-{dd}"
    br  = f"{dd}/{mm}/{aaaa}"

    # ── Estratégia 1: JS puro ─────────────────────────────────────────────────
    resultado = pagina.evaluate(
        """([iso, br]) => {
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;

            const setField = (el, iso, br) => {
                if (!el) return false;
                const tipo = (el.type || 'text').toLowerCase();
                const val  = (tipo === 'date' || tipo === 'datetime-local') ? iso : br;

                // valueAsDate para type=date (API nativa)
                if (tipo === 'date') {
                    try {
                        const [y, m, d] = iso.split('-').map(Number);
                        el.valueAsDate = new Date(Date.UTC(y, m - 1, d));
                    } catch(e) {}
                }
                // Setter prototype (bypassa inputmask)
                if (setter) setter.call(el, val); else el.value = val;
                el.defaultValue = val;
                el.setAttribute('value', val);
                el.dispatchEvent(new Event('input',  { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));

                // inputmask.setvalue (opcional, para type=text mascarado)
                if (tipo !== 'date' && window.$ && $(el).inputmask) {
                    try { $(el).inputmask('setvalue', br); } catch(e) {}
                }
                return true;
            };

            // Candidatos por name (ordem de prioridade)
            const nomes = ['dtpagamento', 'dtvencimento', 'datapagamento', 'data_pagamento'];
            for (const nome of nomes) {
                const el = document.querySelector(`input[name='${nome}']`);
                if (el && el.offsetParent !== null && setField(el, iso, br)) {
                    return 'OK:name=' + nome + ':val=' + el.value;
                }
            }

            // Fallback: busca por label "Data de Pagamento" adjacente
            const labels = Array.from(document.querySelectorAll('label, td, th, span, div'));
            for (const lbl of labels) {
                if (!/data.de.pagamento/i.test(lbl.textContent || '')) continue;
                const inp = lbl.control
                    || lbl.nextElementSibling?.querySelector?.('input')
                    || lbl.closest('tr, div.form-group, div.row')
                        ?.querySelector?.('input[type="date"], input[type="text"]');
                if (inp && inp.offsetParent !== null && setField(inp, iso, br)) {
                    return 'OK:label=' + (inp.name || inp.id) + ':val=' + inp.value;
                }
            }
            return 'NOT_FOUND';
        }""",
        [iso, br],
    ) or "EVAL_ERR"
    print(f"  [Data Pagamento] JS setter → {resultado}")
    if resultado.startswith("OK"):
        return

    # ── Estratégia 2: Playwright fill() pelo seletor de name ─────────────────
    for nome in ("dtpagamento", "dtvencimento"):
        try:
            loc = pagina.locator(f"input[name='{nome}']:visible").first
            if loc.count() == 0:
                continue
            tipo = loc.get_attribute("type") or "text"
            loc.fill(iso if tipo == "date" else br)
            print(f"  [Data Pagamento] Playwright fill({nome}) OK")
            return
        except Exception:
            continue

    # ── Estratégia 3: preencher_data original (press_sequentially) ───────────
    print("  [Data Pagamento] fallback → preencher_data (lento)")
    preencher_data(pagina, "Data de Pagamento:", data_ddmmaaaa)


def executar(dados_extraidos, data_vencimento_usuario, *, usar_conta_pdf=True, conta_banco="", conta_agencia="", conta_conta="", pagina=None, playwright=None):
    sessao_propria = pagina is None
    if sessao_propria:
        playwright, pagina = conectar()
    try:
        print("=== DADOS DE PAGAMENTO ===")
        erros = []
        data_pagamento = str(
            dados_extraidos.get("_vencimento_documento", "") or data_vencimento_usuario or ""
        ).strip()
        lf_numero = str(dados_extraidos.get("_lf_numero", "") or "").strip()

        _clicar_aba_dados_pagamento(pagina)
        _esperar_dados_pagamento_prontos(pagina)

        print(f"[1] Data de Pagamento: {data_pagamento}")
        try:
            _preencher_data_pagamento(pagina, data_pagamento)
        except Exception as e:
            erros.append(f"Erro ao preencher Data de Pagamento: {e}")

        print("[2] Validando favorecido e valor...")
        cnpj_pdf = re.sub(r"\D", "", str(dados_extraidos.get("CNPJ", "") or ""))

        # Valor liquido esperado = soma das NFs - soma das deducoes
        # O portal exibe o valor liquido na Lista de Favorecidos, nunca o bruto da NF.
        try:
            total_nf = sum(
                float(normalizar_valor(str(n.get("Valor", "0") or "0")) or "0")
                for n in dados_extraidos.get("Notas Fiscais", [])
            )
            total_ded = sum(
                float(normalizar_valor(str(d.get("Valor", "0") or "0")) or "0")
                for d in (dados_extraidos.get("Deduções") or dados_extraidos.get("Deducoes") or [])
            )
            valor_liquido_esperado = round(total_nf - total_ded, 2)
        except Exception:
            total_nf = total_ded = 0.0
            valor_liquido_esperado = None

        try:
            campo_cnpj = pagina.locator(
                "input:visible, td:visible"
            ).filter(has_text=re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")).first
            try:
                cnpj_web_raw = campo_cnpj.input_value().strip()
            except Exception:
                cnpj_web_raw = campo_cnpj.inner_text().strip()
            cnpj_web = re.sub(r"\D", "", cnpj_web_raw)
            print(f"  CNPJ  -> Web: {cnpj_web} | PDF: {cnpj_pdf}")
            if cnpj_web and cnpj_pdf and cnpj_web != cnpj_pdf:
                erros.append(f"CNPJ divergente! Web: {cnpj_web_raw} | PDF: {cnpj_pdf}")
        except Exception as e:
            print(f"  Aviso: nao foi possivel verificar CNPJ do favorecido: {e}")

        # Validacao de valor - apenas informativa (nao bloqueia a execucao)
        # Regex especifica para valores monetarios BR: digitos + separadores, sem barras/letras
        _REGEX_MOEDA = re.compile(r"^-?\s*\d{1,3}(?:[.,]\d{3})*[.,]\d{2}$")
        try:
            celulas = pagina.locator("table td").all()
            valor_web_raw = next(
                (
                    c.inner_text().strip()
                    for c in celulas
                    if _REGEX_MOEDA.match(c.inner_text().strip())
                ),
                "",
            )
            if valor_web_raw and valor_liquido_esperado is not None:
                try:
                    valor_web_float = float(normalizar_valor(valor_web_raw) or "0")
                    diff = abs(valor_web_float - valor_liquido_esperado)
                    if diff < 0.10:
                        print(f"  Valor -> Web: {valor_web_raw} | Liquido esperado: {valor_liquido_esperado:.2f} OK")
                    else:
                        print(
                            f"  [AVISO] Valor divergente - Web: {valor_web_raw} "
                            f"| Liquido esperado: {valor_liquido_esperado:.2f} "
                            f"(NFs={total_nf:.2f} - Ded={total_ded:.2f}) "
                            f"- continuando mesmo assim"
                        )
                except Exception:
                    pass
            elif valor_web_raw:
                print(f"  Valor Web: {valor_web_raw}")
        except Exception as e:
            print(f"  Aviso: nao foi possivel verificar Valor: {e}")

        if erros:
            return {"status": "alerta", "mensagem": "\n".join(erros)}

        print("[3] 1Âº Confirmar Dados de Pagamento...")
        try:
            _confirmar_dados_pagamento(pagina, "Confirmar Dados de Pagamento")
            print("  1Âº save concluÃ­do.")
        except Exception as e:
            print(f"  Aviso ao 1Âº confirmar: {e}")

        print("[4] Abrindo PrÃ©-Doc...")
        _clicar_predoc(pagina)
        print("  Modal PrÃ©-Doc aberto.")

        print("[5] Atualizando Processo...")
        proc_pdf = str(dados_extraidos.get("Processo", "") or "")
        if proc_pdf and not _preencher_campo_visivel_por_ids(
            pagina,
            ["txtprocesso", "sfpredoctxtprocesso", "txtprocesso0"],
            proc_pdf,
        ):
            print("  Aviso: campo Processo do modal nÃ£o foi localizado.")

        if lf_numero:
            print(f"[6] LF informada: {lf_numero}")
            _selecionar_tipo_ob_modal(pagina, "OB Fatura")
            _preencher_lf_modal(pagina, lf_numero)

        # Domicílio Bancário do Favorecido — sempre preenche:
        #   usar_conta_pdf=True  → usa valores do PDF (Banco/Agência/Conta extraídos)
        #   usar_conta_pdf=False → usa valores informados pelo usuário
        # O portal não pré-preenche esses campos; deixá-los vazios causa erro de validação.
        usar_conta_pdf_ativo = bool(usar_conta_pdf)

        if usar_conta_pdf_ativo:
            banco_fav   = str(dados_extraidos.get("Banco",   "") or "").strip()
            agencia_fav = str(dados_extraidos.get("Agência", dados_extraidos.get("AgÃªncia", "")) or "").strip()
            conta_fav   = str(dados_extraidos.get("Conta",   "") or "").strip()
            print(f"[7] Preenchendo domicílio bancário do favorecido (PDF): "
                  f"banco={banco_fav} ag={agencia_fav} conta={conta_fav}")
        elif usar_conta_pdf:
            banco_fav = agencia_fav = conta_fav = ""
            print("[7] Domicílio bancário do PDF ignorado: regra operacional desativada.")
        else:
            banco_fav   = str(conta_banco   or "").strip()
            agencia_fav = str(conta_agencia or "").strip()
            conta_fav   = str(conta_conta   or "").strip()
            print(f"[7] Preenchendo domicílio bancário do favorecido (usuário): "
                  f"banco={banco_fav} ag={agencia_fav} conta={conta_fav}")

        if banco_fav or agencia_fav or conta_fav:
            try:
                _preencher_dados_bancarios(pagina, banco_fav, agencia_fav, conta_fav)
            except Exception as e:
                erros.append(f"Erro ao preencher dados bancários do favorecido: {e}")
        else:
            print("[7] Sem dados bancários disponíveis para preencher.")

        print("[8] Preenchendo ObservaÃ§Ã£o...")
        obs = _montar_observacao(dados_extraidos)
        if not _preencher_observacao_modal(pagina, obs):
            erros.append("Campo ObservaÃ§Ã£o nÃ£o encontrado no modal.")

        print("[9] Salvando modal...")
        try:
            _salvar_modal_predoc(pagina)
            print("  Modal salvo com sucesso.")
        except Exception as e:
            erros.append(f"Erro ao salvar o modal: {e}")

        print("[10] 2Âº Confirmar Dados de Pagamento...")
        try:
            confirmou_segunda_vez = _confirmar_dados_pagamento(
                pagina,
                "2Âº Confirmar Dados de Pagamento",
                obrigatorio=False,
            )
            if confirmou_segunda_vez:
                print("  2Âº save concluÃ­do.")
            else:
                print("  2Âº confirmar não foi necessário.")
        except Exception as e:
            erros.append(f"Erro ao confirmar Dados de Pagamento: {e}")

        if erros:
            return {"status": "alerta", "mensagem": "\n".join(erros)}
        return {"status": "sucesso", "mensagem": "Dados de Pagamento preenchidos e confirmados!"}
    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}
    finally:
        if sessao_propria and playwright is not None:
            playwright.stop()
