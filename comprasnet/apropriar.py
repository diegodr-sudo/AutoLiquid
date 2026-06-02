"""
comprasnet_apropriar.py
Etapa 0 — Pesquisa e apropriação de instrumentos de cobrança no Contratos.gov.br.

Fluxo:
  1. Navega para a página de Apropriação de instrumentos de cobrança.
  2. Aplica em uma única busca: ano de emissão único, UG do instrumento,
     situação Pendente e pesquisa por contrato quando houver, ou CNPJ.
  4. Seleciona as caixas de seleção cujo Número do Documento bate com o dado
     extraído do PDF (aceita variações com/sem zeros à esquerda).
  5. Se não encontrar, remove apenas Situação, seleciona "Todos" e tenta de novo.
  6. Clica no botão "Apropriar".
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import time
import logging

log = logging.getLogger(__name__)


class ExecucaoInterrompida(Exception):
    pass


def _verificar_interrupcao(deve_parar=None) -> None:
    if deve_parar and deve_parar():
        raise ExecucaoInterrompida("Apropriação interrompida pelo usuário.")


def _ativar_janela_navegador() -> None:
    """Traz o navegador em execução para frente no SO.

    Verifica QUAL navegador está rodando antes de ativar — nunca lança um
    app que não está aberto (osascript 'activate' abre o app se não estiver rodando).
    """
    sistema = platform.system()
    try:
        if sistema == "Darwin":
            # Mapa: nome do processo (pgrep) → nome AppleScript
            candidatos = [
                ("Google Chrome", "Google Chrome"),
                ("Microsoft Edge", "Microsoft Edge"),
            ]
            for processo, app in candidatos:
                check = subprocess.run(
                    ["pgrep", "-x", processo],
                    capture_output=True,
                    timeout=2,
                )
                if check.returncode == 0:
                    subprocess.run(
                        ["osascript", "-e", f'tell application "{app}" to activate'],
                        capture_output=True,
                        timeout=3,
                    )
                    return  # Achou e ativou — não tenta o próximo
        elif sistema == "Windows":
            for app in ("Google Chrome", "Microsoft Edge"):
                try:
                    result = subprocess.run(
                        ["powershell", "-Command",
                         f"(New-Object -ComObject WScript.Shell).AppActivate('{app}')"],
                        capture_output=True,
                        timeout=3,
                    )
                    if result.returncode == 0:
                        return
                except Exception:
                    continue
    except Exception:
        pass

# A página de Apropriação instrumentos de cobrança fica em /gescon/fatura.
_UG_INSTRUMENTO_COBRANCA = "153163"
URL_APROPRIAR = f"https://contratos.comprasnet.gov.br/gescon/fatura?ug_ic={_UG_INSTRUMENTO_COBRANCA}"

# Timeout padrão para waitFor do Playwright (ms)
_TIMEOUT = 20_000


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_numero(valor: str) -> str:
    """Remove zeros à esquerda e caracteres não-numéricos para comparação."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.lstrip("0") or "0"


def _extrair_contrato(dados: dict) -> str:
    """Retorna o número do contrato limpo (ex: '00108/2025')."""
    for campo in ("Número do Contrato", "Numero do Contrato", "Contrato"):
        valor = str(dados.get(campo, "") or "").strip()
        if valor and valor != "—":
            return valor
    return ""


def _extrair_cnpj(dados: dict) -> str:
    """Retorna apenas os dígitos do CNPJ."""
    cnpj = str(dados.get("CNPJ", "") or "").strip()
    return re.sub(r"\D", "", cnpj)


def _formatar_cnpj(cnpj_digits: str) -> str:
    """Formata 14 dígitos como XX.XXX.XXX/XXXX-XX."""
    d = re.sub(r"\D", "", cnpj_digits)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return cnpj_digits


def _montar_termo_pesquisa(contrato: str, cnpj_digits: str) -> tuple[str, str]:
    """Monta a pesquisa global: contrato tem prioridade; CNPJ é fallback."""
    contrato_limpo = str(contrato or "").strip()
    cnpj_fmt = _formatar_cnpj(cnpj_digits)
    if contrato_limpo:
        return contrato_limpo, f"contrato '{contrato_limpo}'"
    if cnpj_fmt:
        return cnpj_fmt, f"CNPJ '{cnpj_fmt}'"
    return "", ""


def _extrair_numero_documento(dados: dict) -> str:
    """
    Retorna o número do documento de cobrança (ex: '0927118').
    Tenta vários campos do PDF extraído.
    """
    for campo in ("Número do Documento de Cobrança", "Número do Documento", "Numero Documento"):
        v = str(dados.get(campo, "") or "").strip()
        if v:
            return v
    # Tenta dentro das notas fiscais
    for nota in dados.get("Notas Fiscais", []):
        numero = str(nota.get("Número da Nota", "") or "").strip()
        if numero:
            return numero
    return ""


def _extrair_numeros_documentos(dados: dict) -> list[str]:
    """Retorna todos os números de NF/fatura extraídos, sem duplicar."""
    numeros: list[str] = []

    def adicionar(valor: object) -> None:
        texto = str(valor or "").strip()
        if texto and texto not in numeros:
            numeros.append(texto)

    for campo in ("Número do Documento de Cobrança", "Número do Documento", "Numero Documento"):
        adicionar(dados.get(campo))
    for nota in dados.get("Notas Fiscais", []) or []:
        if isinstance(nota, dict):
            adicionar(nota.get("Número da Nota"))
    return numeros


def _extrair_ano_emissao_unico(dados: dict) -> str:
    """
    Retorna o ano de emissão das NFs/faturas quando todas apontam para o
    mesmo exercício. Se houver mais de um ano, retorna vazio para não filtrar.
    """
    anos: set[str] = set()
    for nota in dados.get("Notas Fiscais", []) or []:
        if not isinstance(nota, dict):
            continue
        valor = str(
            nota.get("Data de Emissão")
            or nota.get("Data de Emissao")
            or nota.get("Data de EmissÃ£o")
            or ""
        ).strip()
        match = re.search(r"(20\d{2}|19\d{2})", valor)
        if match:
            anos.add(match.group(1))

    if len(anos) == 1:
        return next(iter(anos))
    if len(anos) > 1:
        log.info("Mais de um ano de emissão nas NFs (%s); filtro por ano será ignorado.", ", ".join(sorted(anos)))
    return ""


def _aguardar_tabela(pagina, timeout_ms: int = _TIMEOUT) -> None:
    """Aguarda a tabela de instrumentos de cobrança estar visível."""
    pagina.wait_for_selector(
        "table tbody tr, .table tbody tr, [class*='table'] tbody tr",
        timeout=timeout_ms,
        state="visible",
    )


def _clicar_todos_registros(pagina) -> None:
    """
    Seleciona 'Todos' no seletor de registros por página (DataTables).

    Estratégia em 3 tentativas progressivas:
    1. select_option via seletor CSS de página (mais confiável, sem handle stale)
    2. Clique direto na opção via JavaScript (para dropdowns custom)
    3. Fallback: JS de força-bruta em todos os <select>
    """
    log.info("Selecionando 'Todos' registros por página...")

    # Seletor exato confirmado pelo diagnóstico: name="crudTable_length", id=null, value="-1"
    # O select NÃO tem id — apenas o atributo name é confiável.
    SELETOR_EXATO = 'select[name="crudTable_length"]'

    # -- Aguarda o controle de paginação estar presente na DOM --
    SELETORES_ESPERA = [
        SELETOR_EXATO,
        "select[name$='_length']",
        ".dataTables_length select",
    ]
    seletor_encontrado: str | None = None
    for seletor in SELETORES_ESPERA:
        try:
            pagina.wait_for_selector(seletor, state="visible", timeout=6_000)
            seletor_encontrado = seletor
            log.info("Select de paginação encontrado via '%s'.", seletor)
            break
        except Exception:
            continue

    # -- Tentativa 1: select_option direto com o seletor exato (valor "-1" = Todos) --
    if seletor_encontrado:
        try:
            pagina.select_option(seletor_encontrado, value="-1")
            log.info("'Todos' selecionado (value='-1') via '%s'.", seletor_encontrado)
            time.sleep(1.2)
            _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
            return
        except Exception:
            pass
        # Fallback pelo label caso o value seja diferente
        try:
            pagina.select_option(seletor_encontrado, label="Todos")
            log.info("'Todos' selecionado pelo label via '%s'.", seletor_encontrado)
            time.sleep(1.2)
            _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
            return
        except Exception:
            pass

    # -- Tentativa 2: JS direto — busca pelo name exato primeiro, depois varre todos --
    log.info("Tentando JS fallback para selecionar 'Todos'...")
    resultado = pagina.evaluate("""
        () => {
            // Prioriza o select com name="crudTable_length" (confirmado pelo diagnóstico)
            var sel = document.querySelector('select[name="crudTable_length"]');
            if (!sel) {
                // Fallback: varre todos os selects procurando a opção Todos/-1
                var all = document.querySelectorAll('select');
                for (var j = 0; j < all.length; j++) {
                    var s = all[j];
                    for (var k = 0; k < s.options.length; k++) {
                        if ((s.options[k].text || '').trim().toLowerCase() === 'todos'
                                || s.options[k].value === '-1') {
                            sel = s;
                            break;
                        }
                    }
                    if (sel) break;
                }
            }
            if (!sel) return null;
            // Encontra a opção Todos ou value -1
            for (var i = 0; i < sel.options.length; i++) {
                var opt = sel.options[i];
                if ((opt.text || '').trim().toLowerCase() === 'todos' || opt.value === '-1') {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    return opt.value;
                }
            }
            return null;
        }
    """)

    if resultado is not None:
        log.info("JS fallback: value='%s' aplicado.", resultado)
        time.sleep(1.5)
        _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
        return

    log.warning("Não foi possível selecionar 'Todos' — prosseguindo com paginação padrão.")


def _aguardar_tabela_estavel(pagina, timeout_ms: int = 60_000) -> None:
    """
    Espera inteligente: polls até a tabela estar completamente carregada.
    Considera estável quando:
      - Não há spinners/overlays de loading visíveis
      - A tabela já respondeu com dados ou mensagem de nenhum resultado
      - Dois polls consecutivos retornam o mesmo número de linhas úteis
    """
    log.info("Aguardando tabela estabilizar...")

    js_estavel = """
        () => {
            // 1. Verifica indicadores de loading específicos do DataTables/Bootstrap.
            //    Evita varrer todos os elementos — classes genéricas como 'process'
            //    aparecem em elementos permanentes do Comprasnet e causam loop infinito.
            var seletoresLoading = [
                '#crudTable_processing',
                '.dataTables_processing',
                '.spinner-border:not(.btn .spinner-border)',
                '.spinner-grow:not(.btn .spinner-grow)',
                '[data-loading="true"]',
            ];
            for (var k = 0; k < seletoresLoading.length; k++) {
                var els = document.querySelectorAll(seletoresLoading[k]);
                for (var i = 0; i < els.length; i++) {
                    var el = els[i];
                    var style = window.getComputedStyle(el);
                    var opacity = parseFloat(style.opacity || '1');
                    if (style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && opacity > 0.1) {
                        return -1;  // ainda carregando
                    }
                }
            }

            // 2. Verifica se a tabela tem linhas com conteúdo real ou vazio confirmado
            var linhas = document.querySelectorAll('table tbody tr');
            if (linhas.length === 0) return -1;

            // Ignora linhas de "nenhum resultado" / mensagem vazia
            var linhasComDados = 0;
            for (var j = 0; j < linhas.length; j++) {
                var txt = (linhas[j].textContent || '').trim();
                // Linha tem conteúdo útil (mais de 10 chars e não é só mensagem de vazio)
                if (txt.length > 10
                        && txt.toLowerCase().indexOf('nenhum') === -1
                        && txt.toLowerCase().indexOf('no data') === -1
                        && txt.toLowerCase().indexOf('sem registro') === -1) {
                    linhasComDados++;
                }
            }

            return linhasComDados;
        }
    """

    limite = time.time() + timeout_ms / 1000
    contagem_anterior = -1

    while time.time() < limite:
        try:
            contagem = pagina.evaluate(js_estavel)
        except Exception:
            contagem = -1

        if contagem >= 0 and contagem == contagem_anterior:
            # Dois polls com o mesmo resultado → tabela estável, inclusive vazia.
            log.info("Tabela estável com %d linha(s) de dados.", contagem)
            return

        contagem_anterior = contagem
        log.info("Aguardando tabela... (linhas com dados: %s)", contagem)
        time.sleep(1.5)

    log.warning("Timeout aguardando tabela estabilizar. Prosseguindo mesmo assim.")


def _aplicar_select2_por_id(pagina, select_id: str, *, valores: list[str], texto: str) -> bool:
    """Define filtro Select2/DataTables pelo select escondido e dispara change."""
    js = """
        ({ selectId, valores, texto }) => {
            const select = document.getElementById(selectId);
            if (!select) return false;

            const normalizar = (value) => (value || '')
                .toString()
                .normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '')
                .trim()
                .toLowerCase();

            const desejados = valores.map(normalizar);
            let valorFinal = '';

            for (const opt of Array.from(select.options || [])) {
                const optValue = normalizar(opt.value);
                const optText = normalizar(opt.textContent);
                if (desejados.includes(optValue) || desejados.includes(optText)) {
                    valorFinal = opt.value;
                    break;
                }
            }

            if (!valorFinal) {
                valorFinal = valores[0] || texto;
                const opt = new Option(texto || valorFinal, valorFinal, true, true);
                select.add(opt);
            }

            if (window.jQuery) {
                window.jQuery(select).val(valorFinal).trigger('change');
            } else {
                select.value = valorFinal;
                select.dispatchEvent(new Event('input', { bubbles: true }));
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
            return true;
        }
    """
    try:
        return bool(pagina.evaluate(js, {"selectId": select_id, "valores": valores, "texto": texto}))
    except Exception as exc:
        log.warning("Falha ao aplicar filtro '%s': %s", select_id, exc)
        return False


def _aplicar_filtros_iniciais(
    pagina,
    ano_emissao: str,
    *,
    aplicar_situacao: bool = True,
) -> None:
    """
    Aplica filtros após a busca textual:
    - UG do Instrumento de Cobrança.
    - Ano Emissão, quando todas as NFs têm o mesmo ano.
    - Situação = Pendente, exceto em fallback.
    """
    filtros_aplicados = []
    if _aplicar_select2_por_id(
        pagina,
        "filter_ug_ic",
        valores=[_UG_INSTRUMENTO_COBRANCA],
        texto=_UG_INSTRUMENTO_COBRANCA,
    ):
        filtros_aplicados.append(f"UG IC={_UG_INSTRUMENTO_COBRANCA}")

    if ano_emissao:
        if _aplicar_select2_por_id(
            pagina,
            "filter_emissao",
            valores=[ano_emissao],
            texto=ano_emissao,
        ):
            filtros_aplicados.append(f"Ano Emissão={ano_emissao}")

    if aplicar_situacao:
        if _aplicar_select2_por_id(
            pagina,
            "filter_situacao",
            valores=["PEN", "Pendente"],
            texto="Pendente",
        ):
            filtros_aplicados.append("Situação=Pendente")

    if filtros_aplicados:
        log.info("Filtros iniciais aplicados: %s", " | ".join(filtros_aplicados))
        time.sleep(1.2)
        _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
    else:
        log.info("Nenhum filtro inicial foi aplicado.")


def _remover_filtros(pagina) -> None:
    """Remove filtros avançados e limpa a pesquisa global."""
    log.info("Removendo filtros antes do fallback amplo...")
    js = """
        () => {
            const remover = document.querySelector('#remove_filters_button');
            if (remover) {
                remover.click();
            }

            const search = document.querySelector("input[type='search']");
            if (search) {
                search.value = '';
                search.dispatchEvent(new Event('input', { bubbles: true }));
                search.dispatchEvent(new Event('change', { bubbles: true }));
                search.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
            }

            for (const select of document.querySelectorAll('select[id^="filter_"]')) {
                if (window.jQuery) {
                    window.jQuery(select).val('').trigger('change');
                } else {
                    select.value = '';
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
            return true;
        }
    """
    try:
        pagina.evaluate(js)
        time.sleep(1.5)
        _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
    except Exception as exc:
        log.warning("Não foi possível remover filtros automaticamente: %s", exc)


def _remover_filtro_situacao(pagina) -> None:
    """Remove apenas o filtro Situação, preservando UG, ano e pesquisa textual."""
    log.info("Removendo apenas o filtro Situação para fallback...")
    js = """
        () => {
            const visivel = (el) => {
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0
                    && style.visibility !== 'hidden'
                    && style.display !== 'none';
            };
            const select = document.getElementById('filter_situacao');
            const container = select
                ? (select.nextElementSibling || select.parentElement?.querySelector('.select2'))
                : null;
            const remover = container
                ? Array.from(container.querySelectorAll('.select2-selection__choice__remove, .select2-selection__clear, [title*="Remove"], [title*="remove"]'))
                    .find(visivel)
                : null;
            if (remover) {
                remover.click();
                return 'click-x';
            }
            if (select) {
                if (window.jQuery) {
                    window.jQuery(select).val('').trigger('change');
                } else {
                    select.value = '';
                    select.dispatchEvent(new Event('input', { bubbles: true }));
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
                return 'select-clear';
            }
            return '';
        }
    """
    try:
        resultado = pagina.evaluate(js)
        log.info("Filtro Situação removido: %s", resultado or "não encontrado")
        time.sleep(1.2)
        _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
    except Exception as exc:
        log.warning("Não foi possível remover apenas a situação: %s", exc)


def _usar_campo_pesquisar(pagina, valor: str) -> None:
    """
    Usa o campo 'Pesquisar:' no topo da lista e aguarda a tabela carregar completamente.
    """
    log.info("Usando campo Pesquisar com: %s", valor)
    js = """
        (valor) => {
            var seletores = [
                "input[type='search']",
                "input[aria-label*='Search']",
                "input[aria-label*='Pesquisar']",
                "input.form-control",
                "input[type='text']"
            ];
            for (var s = 0; s < seletores.length; s++) {
                var campos = document.querySelectorAll(seletores[s]);
                for (var i = 0; i < campos.length; i++) {
                    var inp = campos[i];
                    var rect = inp.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        inp.value = valor;
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                        return true;
                    }
                }
            }
            return false;
        }
    """
    try:
        pagina.evaluate(js, valor)
        # Pequena pausa inicial para o site iniciar a requisição
        time.sleep(1.5)
        # Espera inteligente: polls até tabela estável (sem spinner, com dados)
        _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
        log.info("Pesquisa concluída e tabela estável.")
    except Exception as exc:
        log.warning("Erro ao usar campo Pesquisar: %s", exc)


def _pesquisa_contem_termo(pagina, termo: str) -> bool:
    """Confirma que o campo de busca visível contém o termo antes de expandir para Todos."""
    js = """
        (termo) => {
            const normalizar = (valor) => (valor || '').toString()
                .normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '')
                .replace(/\\s+/g, '')
                .toLowerCase();
            const alvo = normalizar(termo);
            if (!alvo) return false;
            const seletores = [
                "input[type='search']",
                "input[aria-label*='Search']",
                "input[aria-label*='Pesquisar']",
                "input.form-control",
                "input[type='text']",
            ];
            for (const seletor of seletores) {
                for (const input of Array.from(document.querySelectorAll(seletor))) {
                    const rect = input.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && normalizar(input.value).includes(alvo)) {
                        return true;
                    }
                }
            }
            return false;
        }
    """
    try:
        return bool(pagina.evaluate(js, termo))
    except Exception:
        return False


def _clicar_todos_registros_filtrados(pagina, termo_pesquisa: str) -> None:
    if not _pesquisa_contem_termo(pagina, termo_pesquisa):
        log.warning("Não selecionei 'Todos': pesquisa textual ainda não contém '%s'.", termo_pesquisa)
        return
    _clicar_todos_registros(pagina)


def _selecionar_documentos(pagina, numero_documento: str | list[str]) -> int:
    """
    Seleciona as caixas de seleção cujo número do documento bate com
    `numero_documento` (tolerando zeros à esquerda).
    Retorna a quantidade de caixas marcadas.
    """
    numeros = numero_documento if isinstance(numero_documento, list) else [numero_documento]
    numeros_norm = [
        _normalizar_numero(numero)
        for numero in numeros
        if str(numero or "").strip()
    ]

    if not numeros_norm:
        log.warning("Número do documento não disponível — selecionando todos visíveis.")
        return _selecionar_todos_checkboxes(pagina)

    log.info("Selecionando documentos com número(s): %s", ", ".join(numeros_norm))

    js = """
        (numsNorm) => {
            var count = 0;
            var alvos = new Set(numsNorm);
            var linhas = document.querySelectorAll('table tbody tr');
            for (var i = 0; i < linhas.length; i++) {
                var linha = linhas[i];
                var celulas = linha.querySelectorAll('td');
                var encontrou = false;
                for (var j = 0; j < celulas.length; j++) {
                    var txt = (celulas[j].textContent || '').trim().replace(/\\D/g, '').replace(/^0+/, '') || '0';
                    if (alvos.has(txt)) {
                        encontrou = true;
                        break;
                    }
                }
                if (encontrou) {
                    var cb = linha.querySelector('input[type="checkbox"]');
                    if (cb) {
                        if (!cb.checked) { cb.click(); }
                        count++;
                    }
                }
            }
            return count;
        }
    """
    try:
        marcados = pagina.evaluate(js, numeros_norm)
        log.info("Documentos selecionados: %d", marcados)
        return marcados
    except Exception as exc:
        log.error("Erro ao selecionar documentos: %s", exc)
        return 0


def _selecionar_todos_checkboxes(pagina) -> int:
    """Marca todas as caixas de seleção da tabela (fallback)."""
    js = """
        () => {
            var count = 0;
            var checkboxes = document.querySelectorAll('table tbody input[type="checkbox"]');
            for (var i = 0; i < checkboxes.length; i++) {
                if (!checkboxes[i].checked) { checkboxes[i].click(); }
                count++;
            }
            return count;
        }
    """
    try:
        return pagina.evaluate(js)
    except Exception as exc:
        log.error("Erro ao selecionar todos os checkboxes: %s", exc)
        return 0


def _clicar_nova_apropriacao_se_visivel(pagina) -> str | None:
    js_nova = """
        () => {
            const normalizar = (valor) => (valor || '')
                .toString()
                .normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '')
                .toLowerCase()
                .trim()
                .replace(/\\s+/g, ' ');
            const candidatos = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"], input[type="button"]'));
            for (const el of candidatos) {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                if (rect.width <= 0 || rect.height <= 0 || style.visibility === 'hidden' || style.display === 'none') continue;
                const txt = normalizar(el.textContent || el.value || el.getAttribute('aria-label') || el.title || '');
                if (txt.includes('nova apropriacao')) {
                    el.click();
                    return txt;
                }
            }
            return null;
        }
    """
    try:
        clicado = pagina.evaluate(js_nova)
        return str(clicado) if clicado else None
    except Exception:
        return None


def _aguardar_ou_clicar_nova_apropriacao(pagina, timeout_s: float = 10) -> str | None:
    limite = time.time() + timeout_s
    while time.time() < limite:
        clicado = _clicar_nova_apropriacao_se_visivel(pagina)
        if clicado:
            return clicado
        try:
            em_formulario = bool(pagina.evaluate("""
                () => {
                    const texto = document.body ? document.body.innerText.toLowerCase() : '';
                    return texto.includes('dados básicos')
                        || texto.includes('dados basicos')
                        || texto.includes('tipo dh')
                        || texto.includes('principal com orçamento')
                        || texto.includes('principal com orcamento');
                }
            """))
            if em_formulario:
                return None
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _clicar_apropriar(pagina) -> None:
    """
    Clica no botão 'Apropriar Faturas' (botão azul abaixo da tabela)
    ou em qualquer variação do texto 'Apropriar'.
    """
    log.info("Clicando em Apropriar Faturas...")

    clicado_nova_previa = _clicar_nova_apropriacao_se_visivel(pagina)
    if clicado_nova_previa:
        log.info("Modal de apropriação já estava aberto; clicado em Nova Apropriação: '%s'", clicado_nova_previa)
        _aguardar_inicio_formulario_apropriacao(pagina)
        return

    js = """
        () => {
            // Termos aceitos em ordem de prioridade
            var termos = ['apropriar faturas', 'apropriar fatura', 'apropriar'];
            var candidatos = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"], input[type="button"]'));
            for (var t = 0; t < termos.length; t++) {
                for (var i = 0; i < candidatos.length; i++) {
                    var el = candidatos[i];
                    var title = (el.title || el.getAttribute('aria-label') || '').toLowerCase().trim();
                    var txt = (el.textContent || el.value || '').toLowerCase().trim();
                    if (txt === termos[t] || title === termos[t]) {
                        el.click();
                        return txt;
                    }
                }
            }
            // Fallback: qualquer botão/link que contenha 'apropriar'
            for (var i = 0; i < candidatos.length; i++) {
                var el = candidatos[i];
                var txt = (el.textContent || el.value || '').toLowerCase().trim();
                if (txt.indexOf('apropriar') !== -1) {
                    el.click();
                    return txt;
                }
            }
            return null;
        }
    """
    clicado = pagina.evaluate(js)

    if not clicado:
        raise RuntimeError(
            "Botão 'Apropriar Faturas' não encontrado. "
            "Verifique se algum documento está selecionado e se o botão está visível na página."
        )

    log.info("Botão clicado: '%s'", clicado)

    # Se já existe apropriação anterior, o portal abre o modal "Como deseja apropriar?".
    # Sempre escolhemos NOVA APROPRIAÇÃO; copiar apropriação anterior não se aplica.
    clicado_nova = _aguardar_ou_clicar_nova_apropriacao(pagina, timeout_s=10)
    if clicado_nova:
        log.info("Clicado em Nova Apropriação: '%s'", clicado_nova)
    else:
        log.info("Modal de Nova Apropriação não apareceu; seguindo com o formulário atual.")

    _aguardar_inicio_formulario_apropriacao(pagina)


def _aguardar_inicio_formulario_apropriacao(pagina) -> None:
    # Não espera networkidle: o portal pode manter requisições abertas e atrasar
    # a transição para Dados Básicos. Basta aguardar a tela de apropriação iniciar.
    try:
        pagina.wait_for_function(
            """() => {
                const texto = document.body ? document.body.innerText.toLowerCase() : '';
                return texto.includes('dados básicos')
                    || texto.includes('dados basicos')
                    || texto.includes('tipo dh')
                    || texto.includes('principal com orçamento')
                    || texto.includes('principal com orcamento');
            }""",
            timeout=10_000,
        )
    except Exception:
        log.info("Tela pós-apropriação ainda carregando; seguindo para a próxima etapa.")


def _garantir_na_pagina_apropriar(pagina) -> None:
    """
    Garante que o navegador está na página de Apropriação instrumentos de cobrança.
    Essa página fica em /gescon/fatura. Se já estiver no domínio correto, fica.
    Se estiver fora do domínio, navega para URL_APROPRIAR.

    Sempre traz o Chrome para frente — o navegador pode ter sido aberto em modo
    oculto (ex: atualização da fila Solar) e precisa ficar visível para o usuário.
    """
    url_atual = pagina.url
    log.info("URL atual: %s", url_atual)

    dominios_validos = ("contratos.comprasnet.gov.br", "contratos.gov.br")
    if any(d in url_atual for d in dominios_validos):
        # Já estamos no domínio certo — a aba já deve estar na página correta.
        # Se estiver em outra rota do domínio, navega para /gescon/fatura.
        if "gescon/fatura" not in url_atual:
            log.info("No domínio mas em rota diferente. Navegando para %s", URL_APROPRIAR)
            pagina.goto(URL_APROPRIAR, wait_until="networkidle", timeout=30_000)
            time.sleep(1)
        else:
            log.info("Já na página correta (%s).", url_atual)
    else:
        log.info("Fora do domínio esperado. Navegando para %s", URL_APROPRIAR)
        pagina.goto(URL_APROPRIAR, wait_until="networkidle", timeout=30_000)
        time.sleep(1)

    # Traz a aba e a janela do navegador para frente (caso Chrome esteja em segundo plano)
    try:
        pagina.bring_to_front()
    except Exception:
        pass
    _ativar_janela_navegador()


# ─────────────────────────────────────────────────────────────────────────────
# FILTROS + PESQUISA EM LOTE (otimização de performance)
# ─────────────────────────────────────────────────────────────────────────────

def _aplicar_filtros_e_pesquisa_em_lote(
    pagina,
    ano_emissao: str,
    termo_pesquisa: str,
) -> bool:
    """
    Aplica de uma só vez: UG do Instrumento de Cobrança, filtro de ano,
    situação Pendente e texto de pesquisa.

    Disparar todos os valores antes de qualquer evento de change evita reloads
    intermediários da tabela — apenas um ciclo AJAX em vez de dois ou três.

    Retorna True se conseguiu acionar a tabela sem precisar do fluxo sequencial.
    """
    log.info(
        "Aplicando filtros e pesquisa em lote: ano='%s' | pesquisa='%s'",
        ano_emissao or "-",
        termo_pesquisa,
    )

    js = """
        ({ anoEmissao, termoPesquisa }) => {
            const normalizar = (v) => (v || '').toString()
                .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').trim().toLowerCase();

            const desejadosAno = anoEmissao ? [anoEmissao] : [];
            const desejadosUgIc = ['153163'];
            const desejadosSit = ['pen', 'pendente'];
            let ugIcAplicada = false;
            let situacaoAplicada = false;
            let pesquisaAplicada = false;

            // ── 1. Define filtros SEM disparar change ainda ──
            const setSelect = (id, desejados) => {
                const sel = document.getElementById(id);
                if (!sel) return false;
                const des = desejados.map(normalizar);
                for (const opt of Array.from(sel.options || [])) {
                    if (des.includes(normalizar(opt.value)) || des.includes(normalizar(opt.textContent))) {
                        sel.value = opt.value;
                        return true;
                    }
                }
                return false;
            };

            ugIcAplicada = setSelect('filter_ug_ic', desejadosUgIc);
            if (anoEmissao) setSelect('filter_emissao', desejadosAno);
            situacaoAplicada = setSelect('filter_situacao', desejadosSit);

            // ── 2. Define a pesquisa textual SEM disparar evento ──
            if (termoPesquisa) {
                const seletores = [
                    "input[type='search']",
                    "input[aria-label*='Search']",
                    "input[aria-label*='Pesquisar']",
                    "input.form-control",
                    "input[type='text']",
                ];
                for (const s of seletores) {
                    const campos = Array.from(document.querySelectorAll(s));
                    for (const inp of campos) {
                        const rect = inp.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            inp.value = termoPesquisa;
                            pesquisaAplicada = true;
                            break;
                        }
                    }
                    if (pesquisaAplicada) break;
                }
            }

            // ── 3. Dispara change/eventos em todos de uma vez ──
            const dispararElemento = (el) => {
                if (!el) return;
                if (window.jQuery) {
                    window.jQuery(el).trigger('change');
                } else {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
            };

            const dispararChange = (id) => {
                const el = document.getElementById(id);
                dispararElemento(el);
            };

            dispararChange('filter_ug_ic');
            if (anoEmissao) dispararChange('filter_emissao');
            dispararChange('filter_situacao');

            // Dispara eventos na pesquisa
            if (termoPesquisa) {
                let pesquisaDisparada = false;
                const seletores = [
                    "input[type='search']",
                    "input[aria-label*='Search']",
                    "input[aria-label*='Pesquisar']",
                    "input.form-control",
                    "input[type='text']",
                ];
                for (const s of seletores) {
                    const campos = Array.from(document.querySelectorAll(s));
                    for (const inp of campos) {
                        const rect = inp.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                            pesquisaDisparada = true;
                            break;
                        }
                    }
                    if (pesquisaDisparada) break;
                }
            }

            return ugIcAplicada || situacaoAplicada || pesquisaAplicada;
        }
    """
    try:
        ok = pagina.evaluate(js, {"anoEmissao": ano_emissao, "termoPesquisa": termo_pesquisa})
        time.sleep(1.5)  # janela inicial para o browser iniciar as requisições
        _aguardar_tabela_estavel(pagina, timeout_ms=30_000)
        pesquisa_ok = _pesquisa_contem_termo(pagina, termo_pesquisa)
        log.info("Filtros + pesquisa aplicados em lote (ok: %s | pesquisa_ok: %s).", ok, pesquisa_ok)
        return bool(ok and pesquisa_ok)
    except Exception as exc:
        log.warning("Erro ao aplicar filtros em lote: %s. Usando fluxo sequencial.", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Ponto de entrada principal
# ─────────────────────────────────────────────────────────────────────────────

def executar(dados: dict, pagina, playwright=None, deve_parar=None) -> dict:
    """
    Executa a etapa de pesquisa e apropriação de instrumento de cobrança.

    Parâmetros
    ----------
    dados : dict
        Dados extraídos do PDF (incluindo Número do Contrato, CNPJ,
        Número do Documento de Cobrança).
    pagina : playwright Page
        Página ativa do navegador.
    playwright : opcional
        Instância do Playwright (não utilizada diretamente aqui).

    Retorno
    -------
    dict com chaves: status ("ok" | "erro" | "alerta"), mensagem
    """
    try:
        _verificar_interrupcao(deve_parar)
        contrato = _extrair_contrato(dados)
        cnpj = _extrair_cnpj(dados)
        numero_doc = _extrair_numero_documento(dados)
        numeros_docs = _extrair_numeros_documentos(dados) or ([numero_doc] if numero_doc else [])
        ano_emissao = _extrair_ano_emissao_unico(dados)

        log.info("=== Etapa 0: Apropriar ===")
        log.info(
            "Contrato: %s | CNPJ: %s | Nº Doc(s): %s | Ano emissão: %s",
            contrato,
            cnpj,
            ", ".join(numeros_docs) or "-",
            ano_emissao or "sem filtro",
        )

        # 1. Garantir que estamos na página correta
        _garantir_na_pagina_apropriar(pagina)
        _verificar_interrupcao(deve_parar)

        # 2+3. Aplica a busca principal em um único ciclo:
        # ano, UG do instrumento, situação e pesquisa por contrato ou CNPJ.
        termo_pesquisa, filtro_label = _montar_termo_pesquisa(contrato, cnpj)
        if not termo_pesquisa:
            return {
                "status": "erro",
                "mensagem": "Não foi possível filtrar: contrato e CNPJ ausentes nos dados extraídos.",
            }

        if not _aplicar_filtros_e_pesquisa_em_lote(pagina, ano_emissao, termo_pesquisa):
            _usar_campo_pesquisar(pagina, termo_pesquisa)
            _verificar_interrupcao(deve_parar)
            _aplicar_filtros_iniciais(pagina, ano_emissao, aplicar_situacao=True)
            _verificar_interrupcao(deve_parar)
            if not _pesquisa_contem_termo(pagina, termo_pesquisa):
                _usar_campo_pesquisar(pagina, termo_pesquisa)
        _verificar_interrupcao(deve_parar)

        _clicar_todos_registros_filtrados(pagina, termo_pesquisa)
        _verificar_interrupcao(deve_parar)

        # 4. Aguardar tabela (geralmente já estável após _aplicar_filtros_e_pesquisa_em_lote)
        try:
            _aguardar_tabela(pagina, timeout_ms=10_000)
        except Exception:
            log.warning("Tabela pode estar vazia ou não carregada após filtro.")

        time.sleep(0.5)
        _verificar_interrupcao(deve_parar)

        # 5. Selecionar caixas de seleção pelo número do documento
        marcados = _selecionar_documentos(pagina, numeros_docs)
        _verificar_interrupcao(deve_parar)

        if marcados == 0:
            log.info(
                "Nenhum documento encontrado com %s. Fallback único: remover Situação e selecionar Todos.",
                filtro_label,
            )
            _remover_filtro_situacao(pagina)
            _verificar_interrupcao(deve_parar)
            _clicar_todos_registros_filtrados(pagina, termo_pesquisa)
            _verificar_interrupcao(deve_parar)
            try:
                _aguardar_tabela(pagina, timeout_ms=10_000)
            except Exception:
                log.warning("Tabela pode estar vazia ou não carregada após fallback sem situação.")
            time.sleep(0.5)
            _verificar_interrupcao(deve_parar)
            marcados = _selecionar_documentos(pagina, numeros_docs)
            _verificar_interrupcao(deve_parar)

        if marcados == 0:
            return {
                "status": "erro",
                "mensagem": (
                    "Nenhum documento encontrado com número(s) '{}' "
                    "após filtrar por {}. "
                    "Verifique se o instrumento de cobrança foi lançado no sistema.".format(
                        ", ".join(numeros_docs) or numero_doc,
                        filtro_label,
                    )
                ),
            }

        log.info("%d documento(s) selecionado(s).", marcados)

        # 6. Clicar em Apropriar
        _verificar_interrupcao(deve_parar)
        _clicar_apropriar(pagina)
        _verificar_interrupcao(deve_parar)

        log.info("Etapa 0 concluída com sucesso.")
        return {
            "status": "ok",
            "mensagem": "{} documento(s) apropriado(s) com sucesso.".format(marcados),
        }

    except ExecucaoInterrompida as exc:
        log.info("Apropriação interrompida pelo usuário.")
        return {"status": "interrompido", "mensagem": str(exc)}
    except Exception as exc:
        log.exception("Erro na etapa de apropriação")
        return {"status": "erro", "mensagem": str(exc)}
