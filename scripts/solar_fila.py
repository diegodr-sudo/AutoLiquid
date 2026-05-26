"""
solar_fila.py
Automação para atualizar a fila de trabalho scrapeando dados do sistema UFSC Solar
e postando em Google Sheets.

WORKFLOW:
1. Conecta ao Chrome via CDP (porta configurada)
2. Abre https://solar.egestao.ufsc.br/solar/
3. Detecta página de login (se necessário, clica em "Entrar")
4. Navega em Relatórios > Relatório de Processos/Solicitações de Pagamentos
5. Filtra por "Situação: Selecione..." (todos)
6. Aguarda carregamento (panelLoadingInvs)
7. Scrape a tabela de resultados
8. Posta os dados em Google Sheets (ou salva como CSV se credenciais falharem)
"""

import os
import sys
import time
import csv
import json
import logging
from datetime import datetime

# Playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from core.runtime_config import obter_porta_chrome

# Google Sheets
try:
    import gspread
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

# Importar funções da base do comprasnet
try:
    from comprasnet.base import conectar
except ImportError:
    def conectar(porta=None, abrir_se_fechado=True):
        p = sync_playwright().start()
        if porta is None:
            porta = obter_porta_chrome()
        nav = p.chromium.connect_over_cdp(f"http://localhost:{porta}")
        pagina = nav.contexts[0].pages[0]
        return p, pagina

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1O2Ft4Ioy3_t4bKmPQ38d56UhHY2TBHfPI6kTkNkmy-4"
SHEET_NAME = "SP_RELAT"

GOOGLE_CREDS_PATH = os.path.expanduser("~/.config/solar_fila/google_creds.json")

URL_SOLAR_BASE = "https://solar.egestao.ufsc.br/solar/"

DEFAULT_TIMEOUT = 30000  # 30s
LOADING_TIMEOUT = 60000  # 60s para loading de pesquisa

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging():
    logger = logging.getLogger("solar_fila")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger

logger = setup_logging()

# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE SHEETS
# ─────────────────────────────────────────────────────────────────────────────

def carregar_credenciais_gspread():
    if not HAS_GSPREAD:
        logger.warning("gspread não está instalado")
        return None
    if not os.path.exists(GOOGLE_CREDS_PATH):
        logger.warning(f"Credenciais não encontradas: {GOOGLE_CREDS_PATH}")
        return None
    try:
        gc = gspread.service_account(filename=GOOGLE_CREDS_PATH)
        logger.info("Credenciais gspread carregadas")
        return gc
    except Exception as e:
        logger.error(f"Erro ao carregar credenciais: {e}")
        return None


def postar_sheets_via_gspread(dados):
    if not dados:
        return False, "Sem dados para postar"

    gc = carregar_credenciais_gspread()
    if not gc:
        return False, "Credenciais gspread não disponíveis"

    try:
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.sheet1

        headers = list(dados[0].keys())
        rows = [headers] + [[d.get(h, "") for h in headers] for d in dados]

        logger.info(f"Postando {len(dados)} registros em {SHEET_NAME}!A3")
        worksheet.update(rows, "A3")

        logger.info(f"{len(dados)} registros postados em Google Sheets")
        return True, f"{len(dados)} registros postados em Google Sheets"

    except Exception as e:
        logger.error(f"Erro ao postar em Google Sheets: {e}")
        return False, f"Erro Google Sheets: {str(e)}"


def salvar_como_csv(dados):
    if not dados:
        return False, "Sem dados para salvar", ""

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"/tmp/solar_fila_{timestamp}.csv"

        headers = list(dados[0].keys())
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(dados)

        logger.info(f"Dados salvos em CSV: {filename}")

        # Tenta copiar para clipboard
        try:
            import subprocess
            with open(filename, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            try:
                subprocess.run(["pbcopy"], input=conteudo.encode('utf-8'), check=True)
                logger.info("Dados copiados para clipboard (macOS)")
            except FileNotFoundError:
                try:
                    subprocess.run(["xclip", "-selection", "clipboard"],
                                   input=conteudo.encode('utf-8'), check=True)
                    logger.info("Dados copiados para clipboard (Linux)")
                except (FileNotFoundError, subprocess.CalledProcessError):
                    pass
        except Exception:
            pass

        return True, f"Dados salvos em CSV: {filename}", filename

    except Exception as e:
        logger.error(f"Erro ao salvar CSV: {e}")
        return False, f"Erro CSV: {str(e)}", ""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _encontrar_frame_principal(pagina):
    """
    O Solar usa um iframe com name='page' para o conteúdo principal.
    Retorna o frame se existir, senão retorna a própria página.
    """
    try:
        for frame in pagina.frames:
            if frame.name == "page" or "pagamentos" in (frame.url or ""):
                logger.info(f"Frame encontrado: name={frame.name}, url={frame.url}")
                return frame
        # Tenta por seletor
        iframe_el = pagina.query_selector("iframe[name='page'], iframe[target='page']")
        if iframe_el:
            frame = iframe_el.content_frame()
            if frame:
                logger.info(f"Frame 'page' encontrado via seletor")
                return frame
    except Exception as e:
        logger.warning(f"Erro ao buscar frame: {e}")
    return pagina


def _detectar_login(pagina):
    """
    Detecta se estamos na página de login do Solar.
    Procura por: form#fm1, input[type='submit'][value='Entrar'], btn-submit
    """
    try:
        login_detectado = pagina.evaluate("""
            () => {
                // Verifica form de login (CAS)
                const form = document.querySelector("form#fm1, form[action*='login']");
                if (form) return true;
                // Verifica botão Entrar
                const btn = document.querySelector(
                    "input.btn-submit[value='Entrar'], "
                    + "input[type='submit'][value='Entrar'], "
                    + "button:has-text('Entrar')"
                );
                if (btn) return true;
                // Verifica campo de CPF/usuário
                const userField = document.querySelector(
                    "input#username, input[name='username']"
                );
                if (userField) return true;
                return false;
            }
        """)
        return login_detectado
    except Exception as e:
        logger.warning(f"Erro ao detectar login: {e}")
        return False


def _clicar_entrar(pagina):
    """
    Na página de login do Solar, clica no botão 'Entrar'.
    O usuário já deve ter credenciais salvas ou estar logado.
    """
    try:
        # Tenta clicar no botão de submit "Entrar"
        pagina.evaluate("""
            () => {
                // Procura o botão Entrar
                const btn = document.querySelector(
                    "input.btn-submit[value='Entrar'], "
                    + "input[type='submit'][value='Entrar']"
                );
                if (btn) { btn.click(); return true; }

                // Procura form e submete
                const form = document.querySelector("form#fm1, form[action*='login']");
                if (form) { form.submit(); return true; }

                return false;
            }
        """)
        logger.info("Botão 'Entrar' clicado")
        time.sleep(3)
        return True
    except Exception as e:
        logger.error(f"Erro ao clicar em Entrar: {e}")
        return False


def _aguardar_loading(pagina_ou_frame, timeout=LOADING_TIMEOUT):
    """
    Aguarda o painel de loading (panelLoadingInvs) desaparecer.
    Também aguarda indicadores genéricos de carregamento.
    """
    try:
        pagina_ou_frame.wait_for_function(
            """
            () => {
                // Panel loading do Solar
                const loading = document.getElementById("panelLoadingInvs");
                if (loading) {
                    const style = window.getComputedStyle(loading);
                    if (style.display !== "none" && style.visibility !== "hidden") {
                        return false;
                    }
                }
                // Verifica outros indicadores de loading
                const spinners = document.querySelectorAll(
                    ".ui-blockui, .loading, .spinner, [class*='loading']"
                );
                for (const s of spinners) {
                    const st = window.getComputedStyle(s);
                    if (st.display !== "none" && st.visibility !== "hidden"
                        && st.opacity !== "0") {
                        return false;
                    }
                }
                return true;
            }
            """,
            timeout=timeout
        )
        logger.info("Loading desapareceu")
        return True
    except PlaywrightTimeoutError:
        logger.warning("Timeout esperando loading (continuando)")
        time.sleep(3)
        return False
    except Exception as e:
        logger.warning(f"Erro ao aguardar loading: {e}")
        time.sleep(2)
        return False


def scrape_tabela_resultados(frame):
    """
    Extrai TODOS os dados da tabela de resultados do relatório.
    - Aguarda a tabela carregar
    - Captura cabeçalhos + todas as linhas (tamanho variável)
    - Também captura o total de registros informado pelo sistema
    """
    try:
        frame.wait_for_selector("table", timeout=DEFAULT_TIMEOUT)
        logger.info("Tabela encontrada, fazendo scroll completo para carregar todas as linhas...")

        # Scroll até o final para garantir que todas as linhas estão no DOM
        # (alguns sistemas carregam linhas preguiçosamente via scroll)
        try:
            frame.evaluate("""
                () => {
                    const scrollaveis = [
                        document.querySelector(".dataTables_scrollBody"),
                        document.querySelector(".table-responsive"),
                        document.querySelector(".resultado-scroll"),
                        document.documentElement,
                        document.body,
                    ].filter(Boolean);
                    for (const el of scrollaveis) {
                        el.scrollTop = el.scrollHeight;
                    }
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            time.sleep(1)
        except Exception:
            pass

        resultado = frame.evaluate("""
            () => {
                // ── Detecta total de registros informado pelo sistema ──────────
                let totalAnunciado = null;
                for (const el of document.querySelectorAll("*")) {
                    const t = (el.innerText || el.textContent || "").trim();
                    const m = t.match(/Resultado da consulta:\\s*(\\d+)\\s*registro/i)
                           || t.match(/(\\d+)\\s*registro/i);
                    if (m && !el.querySelector("*")) {  // elemento folha
                        totalAnunciado = parseInt(m[1]);
                        break;
                    }
                }

                // ── Prioriza a tabela PrimeFaces pelo ID confirmado ────────────
                // ID confirmado via diagnóstico: resultForm:resultTable
                let bestTable = document.querySelector('[id="resultForm:resultTable"]')
                             || document.querySelector('[id*="resultTable"]');

                // Fallback: tabela com mais linhas
                if (!bestTable) {
                    const tables = Array.from(document.querySelectorAll("table"));
                    let maxRows = 0;
                    for (const table of tables) {
                        const rows = table.querySelectorAll("tbody tr");
                        if (rows.length > maxRows) {
                            maxRows = rows.length;
                            bestTable = table;
                        }
                    }
                }

                if (!bestTable) {
                    return { headers: [], rows: [], total: totalAnunciado };
                }

                // ── Cabeçalhos: ignora colunas ui-helper-hidden (PrimeFaces reflow) ──
                // Diagnóstico confirmou: colunas duplicadas têm classe ui-helper-hidden
                // Colunas visíveis: ui-sortable-column ou ui-state-default SEM ui-helper-hidden
                let headers = [];
                let colIndicesVisiveis = [];   // índices das colunas que devem ser incluídas
                const thead = bestTable.querySelector("thead");
                if (thead) {
                    const theadRows = thead.querySelectorAll("tr");
                    const headerRow = theadRows[theadRows.length - 1];
                    const allThs = Array.from(headerRow.querySelectorAll("th"));

                    allThs.forEach((th, idx) => {
                        // Pula colunas ocultas (PrimeFaces reflow duplicatas)
                        if (th.classList.contains("ui-helper-hidden")) return;

                        // Texto da coluna: preferência para .ui-column-title
                        const titleEl = th.querySelector(".ui-column-title");
                        let txt = titleEl
                            ? (titleEl.innerText || titleEl.textContent || "").trim()
                            : (th.innerText || "").split("\\n")[0].trim();

                        if (txt) {
                            headers.push(txt);
                            colIndicesVisiveis.push(idx);
                        }
                    });
                }

                // ── Linhas do corpo — só colunas visíveis ────────────────────────
                const rowsData = [];
                const trs = bestTable.querySelectorAll("tbody tr");
                for (const tr of trs) {
                    if (tr.classList.contains("separador") ||
                        tr.classList.contains("total-row") ||
                        tr.getAttribute("role") === "separator") continue;

                    const allTds = Array.from(tr.querySelectorAll("td"));
                    // Pega apenas as colunas visíveis (pelos índices)
                    const cells = colIndicesVisiveis.map(idx => {
                        const td = allTds[idx];
                        if (!td) return "";
                        const clone = td.cloneNode(true);
                        clone.querySelectorAll(".ui-column-title").forEach(s => s.remove());
                        return (clone.innerText || clone.textContent || "").trim();
                    });
                    if (cells.some(c => c !== "")) rowsData.push(cells);
                }

                return { headers, rows: rowsData, total: totalAnunciado };
            }
        """)

        headers    = resultado.get("headers", [])
        rows_data  = resultado.get("rows", [])
        total_anun = resultado.get("total")

        logger.info(f"Headers: {headers}")
        logger.info(f"{len(rows_data)} linhas extraídas"
                    + (f" (sistema anuncia {total_anun})" if total_anun else ""))

        if total_anun and len(rows_data) < total_anun:
            logger.warning(
                f"ATENÇÃO: extraídas {len(rows_data)} linhas mas o sistema "
                f"anuncia {total_anun} registros. A tabela pode ter paginação."
            )

        dados = []
        for row in rows_data:
            if row:
                linha_dict = {}
                for i, header in enumerate(headers):
                    linha_dict[header] = row[i] if i < len(row) else ""
                # Colunas extras sem cabeçalho
                for i in range(len(headers), len(row)):
                    linha_dict[f"col_{i}"] = row[i]
                dados.append(linha_dict)

        return dados

    except PlaywrightTimeoutError:
        logger.error("Timeout aguardando tabela")
        return []
    except Exception as e:
        logger.error(f"Erro ao fazer scrape: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAÇÃO / SCRAPE
# ─────────────────────────────────────────────────────────────────────────────

def _exportar_ou_scrape(frame_form, pagina):
    """
    Tenta duas estratégias para capturar os dados da tabela de resultados:

    1. Clica em "Exportar Planilha" e lê o arquivo baixado (captura 100% dos dados
       mesmo se houver paginação).
    2. Faz scrape direto do HTML da tabela (fallback).

    Retorna lista de dicts com os dados.
    """
    # ── Estratégia 1: Exportar Planilha ─────────────────────────────────────
    try:
        logger.info("Tentando 'Exportar Planilha'...")

        # "Exportar Planilha" é um ui-menuitem-link dentro de um menu PrimeFaces.
        # Precisa primeiro abrir o menu (clicar no botão que o contém),
        # depois clicar no item "Exportar Planilha".
        # Intercepta o download antes de clicar
        with pagina.expect_download(timeout=20000) as dl_info:
            clicou_export = frame_form.evaluate("""
                () => {
                    // 1. Tenta clicar direto no link (se já estiver visível)
                    const links = [...document.querySelectorAll("a.ui-menuitem-link")];
                    for (const a of links) {
                        const t = (a.textContent || a.innerText || "").trim().toLowerCase();
                        if (t.includes("export") || t.includes("planilha")) {
                            a.click();
                            return "direto";
                        }
                    }

                    // 2. Abre o menu pai primeiro (SplitButton ou Menu do PrimeFaces)
                    // Procura botão/trigger que contenha ou seja vizinho do link de export
                    const triggers = [...document.querySelectorAll(
                        ".ui-splitbutton-menubutton, " +
                        "button[id*='export'], a[id*='export'], " +
                        ".ui-button:has(+ .ui-menu)"
                    )];
                    for (const btn of triggers) {
                        btn.click();
                    }

                    // 3. Após abrir o menu, tenta clicar no item
                    const itens = [...document.querySelectorAll(
                        ".ui-menuitem-link, .ui-menu a, .ui-overlay-menu a"
                    )];
                    for (const a of itens) {
                        const t = (a.textContent || a.innerText || "").trim().toLowerCase();
                        if (t.includes("export") || t.includes("planilha")) {
                            a.click();
                            return "via_menu";
                        }
                    }

                    return false;
                }
            """)

        if clicou_export:
            download = dl_info.value
            caminho_tmp = f"/tmp/solar_export_{int(time.time())}"
            download.save_as(caminho_tmp)
            logger.info(f"Planilha exportada: {download.suggested_filename} → {caminho_tmp}")

            dados = _parse_planilha_exportada(caminho_tmp, download.suggested_filename)
            if dados:
                logger.info(f"{len(dados)} registros via exportação")
                return dados
            logger.warning("Exportação baixada mas sem dados — fazendo scrape")
        else:
            logger.info("Botão Exportar não encontrado — usando scrape")

    except PlaywrightTimeoutError:
        logger.info("Timeout no download — usando scrape")
    except Exception as e_exp:
        logger.warning(f"Exportação falhou ({e_exp}) — usando scrape")

    # ── Estratégia 2: Scrape direto do HTML ──────────────────────────────────
    return scrape_tabela_resultados(frame_form)


def _parse_planilha_exportada(caminho, nome_arquivo):
    """
    Lê o arquivo exportado (XLS/XLSX/CSV) e retorna lista de dicts.
    """
    nome_lower = (nome_arquivo or "").lower()
    try:
        if nome_lower.endswith(".csv"):
            import csv as csv_mod
            with open(caminho, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv_mod.DictReader(f)
                return [row for row in reader]

        # Excel (xls/xlsx) — tenta openpyxl depois xlrd
        try:
            import openpyxl
            wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(c or "").strip() for c in rows[0]]
            dados = []
            for row in rows[1:]:
                if any(c is not None and str(c).strip() for c in row):
                    dados.append({
                        headers[i]: str(row[i] or "").strip()
                        for i in range(len(headers))
                    })
            return dados
        except ImportError:
            pass

        try:
            import xlrd
            wb = xlrd.open_workbook(caminho)
            ws = wb.sheet_by_index(0)
            headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
            dados = []
            for r in range(1, ws.nrows):
                row = [str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)]
                if any(row):
                    dados.append(dict(zip(headers, row)))
            return dados
        except ImportError:
            pass

        logger.warning("openpyxl e xlrd não instalados — não foi possível ler planilha")
        return []

    except Exception as e:
        logger.error(f"Erro ao parsear planilha exportada: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# AUTOMAÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def executar_automacao():
    p = None
    pagina = None

    try:
        logger.info("=" * 60)
        logger.info("INICIANDO AUTOMAÇÃO SOLAR FILA")
        logger.info("=" * 60)

        # 1. Conectar ao Chrome via CDP
        logger.info("Conectando ao Chrome via CDP...")
        try:
            p, pagina = conectar(abrir_se_fechado=False)
            logger.info("Conectado ao Chrome")
        except Exception as e:
            return {"status": "erro",
                    "mensagem": f"Falha ao conectar ao Chrome: {e}", "dados_count": 0}

        # 2. Abrir URL Solar em nova aba
        logger.info(f"Abrindo {URL_SOLAR_BASE} em nova aba...")
        try:
            contexto = pagina.context
            pagina_solar = contexto.new_page()
            pagina_solar.goto(URL_SOLAR_BASE, wait_until="domcontentloaded",
                              timeout=DEFAULT_TIMEOUT)
            logger.info("Nova aba Solar aberta")
        except Exception as e:
            return {"status": "erro",
                    "mensagem": f"Falha ao abrir Solar: {e}", "dados_count": 0}

        # Aguarda renderização inicial
        time.sleep(1)

        # 3. Detectar e lidar com página de login
        for tentativa_login in range(3):
            if _detectar_login(pagina_solar):
                logger.info(f"Página de login detectada (tentativa {tentativa_login + 1})")
                _clicar_entrar(pagina_solar)
                # Aguarda redirecionamento após login (pode levar alguns segundos)
                try:
                    pagina_solar.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
                except Exception:
                    pass
                time.sleep(4)  # Extra wait — o Solar é lento após autenticação
            else:
                logger.info("Não é página de login — prosseguindo")
                break
        else:
            # Após 3 tentativas ainda está no login
            if _detectar_login(pagina_solar):
                return {"status": "erro",
                        "mensagem": "Não foi possível passar da tela de login. "
                                    "Faça login manualmente no Solar e tente novamente.",
                        "dados_count": 0}

        # Guarda referência à página solar para usar nas etapas seguintes
        pagina = pagina_solar

        # Aguarda o menu lateral estar presente
        logger.info("Aguardando menu lateral carregar...")
        _frame_menu = None
        for tentativa in range(8):
            for f in pagina.frames:
                try:
                    tem_menu = f.evaluate(
                        "() => !!document.querySelector('li.nivel, li[nomegrupo], div.arvoremenu')"
                    )
                    if tem_menu:
                        _frame_menu = f
                        logger.info(f"Frame do menu: {f.url}")
                        break
                except Exception:
                    continue
            if _frame_menu:
                break
            time.sleep(2)

        if not _frame_menu:
            if _detectar_login(pagina):
                return {"status": "erro",
                        "mensagem": "Ainda na tela de login. Faça login manualmente no Solar.",
                        "dados_count": 0}
            _frame_menu = pagina  # fallback
            logger.warning("Menu não encontrado em nenhum frame, usando página principal")

        # 4. Expandir menu Relatórios via hover + click
        # O Solar usa jQuery .hover() — precisamos despachar mouseover/mouseenter
        logger.info("Expandindo menu 'Relatórios'...")

        def _hover_e_clicar_relatorios(frame):
            """
            Dispara apenas mouseover + mouseenter no li de Relatórios.
            NÃO faz click — o Solar expande via jQuery .hover(), sem necessidade de click.
            Clicar no item de menu poderia navegar indevidamente.
            """
            try:
                resultado = frame.evaluate("""
                    () => {
                        function dispararHover(el) {
                            ['mouseover','mouseenter'].forEach(tipo => {
                                el.dispatchEvent(new MouseEvent(tipo, {
                                    bubbles: true, cancelable: true, view: window
                                }));
                            });
                            // NÃO faz el.click() — hover já expande o submenu via jQuery
                        }

                        // 1. Atributo nomegrupo="Relatórios"
                        const a1 = document.querySelector('li[nomegrupo="Relatórios"]');
                        if (a1) { dispararHover(a1); return "nomegrupo"; }

                        // 2. ID fixo do módulo SPA
                        const a2 = document.getElementById("nomeGrupo_64_1_30");
                        if (a2) { dispararHover(a2); return "id"; }

                        // 3. li.nivel cujo texto direto seja "Relatórios"
                        for (const li of document.querySelectorAll("li.nivel")) {
                            const txt = Array.from(li.childNodes)
                                .filter(n => n.nodeType === 3)
                                .map(n => n.textContent.trim())
                                .join("").trim();
                            if (txt === "Relatórios" || txt.startsWith("Relat")) {
                                dispararHover(li);
                                return "texto_direto";
                            }
                        }

                        // 4. Qualquer [nomegrupo] com prefixo Relat
                        for (const el of document.querySelectorAll("[nomegrupo]")) {
                            if (el.getAttribute("nomegrupo").startsWith("Relat")) {
                                dispararHover(el);
                                return "attr_prefixo";
                            }
                        }

                        return null;
                    }
                """)
                return resultado
            except Exception as ex:
                logger.debug(f"Erro em frame {getattr(frame,'url','?')}: {ex}")
                return None

        clicou = _hover_e_clicar_relatorios(_frame_menu)
        if not clicou:
            # Tenta nos outros frames
            for f in pagina.frames:
                if f is _frame_menu:
                    continue
                clicou = _hover_e_clicar_relatorios(f)
                if clicou:
                    logger.info(f"Relatórios encontrado em frame alternativo: {f.url}")
                    break

        if not clicou:
            return {"status": "erro",
                    "mensagem": "Menu 'Relatórios' não encontrado.\n"
                                "Verifique se está logado no Solar com módulo SPA ativo.",
                    "dados_count": 0}

        logger.info(f"Menu 'Relatórios' expandido via: {clicou}")
        time.sleep(1)  # Aguarda submenu animar

        # 5. Clicar em "Relatório de Processos/Solicitações de Pagamentos"
        logger.info("Clicando no relatório de pagamentos...")

        def _clicar_link_pagamentos(frame):
            try:
                return frame.evaluate("""
                    () => {
                        function estaVisivel(el) {
                            if (!el) return false;
                            const s = window.getComputedStyle(el);
                            return s.display !== 'none'
                                && s.visibility !== 'hidden'
                                && s.opacity !== '0';
                        }

                        // 1. ID específico (módulo SPA 64)
                        const a1 = document.getElementById("itemMenu_64_1_680");
                        if (a1) { a1.click(); return "id"; }

                        // 2. href com pagamentos/index
                        const a2 = document.querySelector("a[href*='pagamentos/index']");
                        if (a2) { a2.click(); return "href"; }

                        // 3. Link itemMenu com texto de pagamento (qualquer visibilidade)
                        for (const a of document.querySelectorAll("a[id*='itemMenu']")) {
                            const t = a.textContent.trim().toLowerCase();
                            if (t.includes("pagamento") || t.includes("solicita")) {
                                a.click(); return "texto_itemMenu";
                            }
                        }

                        // 4. Qualquer <a> visível dentro de ul expandido com "Pagamento"
                        for (const ul of document.querySelectorAll("ul[itenspai]")) {
                            // Aceita tanto style.display como computedStyle
                            if (!estaVisivel(ul)) continue;
                            for (const a of ul.querySelectorAll("a")) {
                                const t = a.textContent.trim();
                                if (t.includes("Pagamento") || t.includes("Solicita")) {
                                    a.click(); return "ul_expandido";
                                }
                            }
                        }

                        // 5. Varredura geral — qualquer link visível com "pagamento"
                        for (const a of document.querySelectorAll("a")) {
                            const t = a.textContent.trim().toLowerCase();
                            if ((t.includes("pagamento") || t.includes("solicita"))
                                    && estaVisivel(a)) {
                                a.click(); return "varredura_geral";
                            }
                        }

                        return null;
                    }
                """)
            except Exception:
                return None

        time.sleep(0.5)
        clicou_link = _clicar_link_pagamentos(_frame_menu)
        if not clicou_link:
            for f in pagina.frames:
                if f is _frame_menu:
                    continue
                clicou_link = _clicar_link_pagamentos(f)
                if clicou_link:
                    break

        if not clicou_link:
            return {"status": "erro",
                    "mensagem": "Link do relatório de pagamentos não encontrado após expandir menu.\n"
                                "O submenu pode não ter expandido corretamente.",
                    "dados_count": 0}

        logger.info(f"Relatório de Pagamentos clicado via: {clicou_link}")

        # 6. Encontrar frame do formulário — polling com intervalo curto
        logger.info("Aguardando formulário de pesquisa carregar...")
        frame_form = None
        for tentativa in range(20):   # até 20s (20 × 1s)
            for f in pagina.frames:
                url_f = f.url or ""
                if ("pagamento" in url_f.lower()
                        or "suporte.egestao" in url_f.lower()
                        or "relatorio" in url_f.lower()
                        or "relat" in url_f.lower()):
                    frame_form = f
                    logger.info(f"Frame do formulário encontrado por URL: {url_f}")
                    break
                try:
                    tem_pesq = f.evaluate(
                        "() => !!document.querySelector("
                        "  'input[value*=\"esquis\"], input[value*=\"Pesquis\"], "
                        "   form select')"
                    )
                    if tem_pesq and f is not _frame_menu and f != pagina.main_frame:
                        frame_form = f
                        logger.info(f"Frame do formulário (via form): {url_f}")
                        break
                except Exception:
                    continue
            if frame_form:
                break
            time.sleep(1)

        if not frame_form:
            frame_form = pagina
            logger.warning("Frame do formulário não encontrado, usando página principal")

        # Aguarda formulário estar pronto
        try:
            frame_form.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
        except Exception:
            pass
        time.sleep(0.5)

        # ── DIAGNÓSTICO: loga todos os selects e Select2 do frame do formulário ──
        try:
            diag = frame_form.evaluate("""
                () => {
                    const r = {};
                    document.querySelectorAll('select').forEach((s, i) => {
                        r['sel_' + i] = {
                            id: s.id, name: s.name,
                            cls: s.className.substring(0, 80),
                            opts: [...s.options].map(o =>
                                o.text.trim() + '|' + o.value).slice(0, 10)
                        };
                    });
                    document.querySelectorAll('[class*="select2"]').forEach((el, i) => {
                        r['s2_' + i] = {
                            tag: el.tagName, id: el.id,
                            cls: el.className.substring(0, 80)
                        };
                    });
                    // Conta formulários e botões
                    r['_forms'] = document.querySelectorAll('form').length;
                    r['_btns']  = [...document.querySelectorAll(
                        'input[type=button],input[type=submit],button'
                    )].map(b => (b.value || b.textContent || '').trim().substring(0,30));
                    r['_frame_url'] = window.location.href;
                    return r;
                }
            """)
            logger.info(f"DIAGNÓSTICO DO FORMULÁRIO: {json.dumps(diag, ensure_ascii=False)}")
        except Exception as e_diag:
            logger.warning(f"Diagnóstico falhou: {e_diag}")

        # 7. Ajustar filtros: Situação = "Selecione..." (todos) + radio Todos
        # O Solar usa PrimeFaces JSF — IDs confirmados via diagnóstico:
        #   select hidden: consForm:situacaoSelect_input  (valor "Selecione..." = -9999999)
        #   dropdown UI:   consForm:situacaoSelect        (clicável)
        #   painel opções: consForm:situacaoSelect_panel
        ID_SEL_SITUACAO  = "consForm:situacaoSelect_input"
        ID_DD_SITUACAO   = "consForm:situacaoSelect"
        ID_PNL_SITUACAO  = "consForm:situacaoSelect_panel"
        VAL_SELECIONE    = "-9999999"

        logger.info("Configurando filtros do formulário (PrimeFaces)...")

        # ── Estratégia 1: Clica no trigger visual do PrimeFaces e escolhe a opção ──
        # Esse é o caminho mais confiável — imita exatamente o que o usuário faz
        _situacao_ok = False
        try:
            # Abre o dropdown clicando no trigger (seta ▼) do componente PrimeFaces
            # Usamos atributo id= para escapar os dois-pontos do JSF
            trigger_loc = frame_form.locator(
                f'[id="{ID_DD_SITUACAO}"] .ui-selectonemenu-trigger, '
                f'[id="{ID_DD_SITUACAO}"]'
            ).first
            trigger_loc.click(timeout=5000)
            logger.info("Dropdown Situação aberto")
            time.sleep(0.6)  # aguarda painel animar

            # Clica na opção "Selecione..." no painel que aparece
            opcao_loc = frame_form.locator(
                f'[id="{ID_PNL_SITUACAO}"] li[data-label="Selecione..."], '
                f'[id="{ID_PNL_SITUACAO}"] li:first-child'
            ).first
            opcao_loc.click(timeout=5000)
            logger.info("Opção 'Selecione...' clicada via PrimeFaces UI")
            _situacao_ok = True
            time.sleep(0.5)
        except Exception as e_pf:
            logger.warning(f"Estratégia PrimeFaces UI falhou: {e_pf} — tentando via JS")

        # ── Estratégia 2 (fallback): seta o select hidden + notifica PrimeFaces via JS ──
        if not _situacao_ok:
            try:
                resultado_js = frame_form.evaluate(f"""
                    () => {{
                        const sel = document.getElementById('{ID_SEL_SITUACAO}');
                        if (!sel) return 'select_nao_encontrado';

                        // Define o valor
                        sel.value = '{VAL_SELECIONE}';

                        // Notifica PrimeFaces: o widget escuta 'change' no select hidden
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                        sel.dispatchEvent(new Event('input',  {{bubbles: true}}));

                        // Atualiza o label visual do PrimeFaces manualmente
                        const cont = document.getElementById('{ID_DD_SITUACAO}');
                        if (cont) {{
                            const lbl = cont.querySelector(
                                '.ui-selectonemenu-label, label.ui-inputfield'
                            );
                            if (lbl) lbl.textContent = 'Selecione...';
                        }}

                        // Tenta via PrimeFaces widget API (widgetVar desconhecido — busca)
                        try {{
                            if (window.PrimeFaces) {{
                                const wvKey = Object.keys(PrimeFaces.widgets).find(k => {{
                                    const w = PrimeFaces.widgets[k];
                                    return w && w.input && w.input.attr &&
                                        w.input.attr('id') === '{ID_SEL_SITUACAO}';
                                }});
                                if (wvKey) {{
                                    PrimeFaces.widgets[wvKey].selectValue('{VAL_SELECIONE}');
                                    return 'pf_widget_ok:' + wvKey;
                                }}
                            }}
                        }} catch(e) {{ /* widget API não disponível */ }}

                        return 'js_change_ok';
                    }}
                """)
                logger.info(f"Situação via JS: {resultado_js}")
                _situacao_ok = True
            except Exception as e_js:
                logger.warning(f"Estratégia JS também falhou: {e_js}")

        # ── Radio "Todos" ────────────────────────────────────────────────────────────
        try:
            frame_form.evaluate("""
                () => {
                    const radios = document.querySelectorAll("input[type='radio']");
                    for (const r of radios) {
                        const lab = r.closest("label")
                            || document.querySelector(`label[for="${r.id}"]`);
                        const txt = (lab ? lab.textContent : r.value).trim().toLowerCase();
                        if (txt.includes("todo") || r.value.toLowerCase().includes("todo")) {
                            r.checked = true;
                            r.dispatchEvent(new Event("change", {bubbles: true}));
                            break;
                        }
                    }
                }
            """)
            logger.info("Radio 'Todos' marcado")
        except Exception as e_r:
            logger.warning(f"Radio Todos: {e_r}")

        time.sleep(0.5)

        # 8. Clicar em "Pesquisar"
        # PrimeFaces JSF — o botão está dentro do form "consForm"
        logger.info("Clicando em 'Pesquisar'...")
        pesquisou = False
        try:
            # Tenta pelos padrões PrimeFaces mais comuns primeiro
            btn_loc = frame_form.locator(
                '[id*="pesquisar"], [id*="Pesquisar"], [id*="btnPesq"], '
                'button:has-text("Pesquisar"), input[value="Pesquisar"]'
            ).first
            btn_loc.click(timeout=6000)
            pesquisou = True
            logger.info("Botão Pesquisar clicado via locator PrimeFaces")
        except Exception:
            # Fallback: qualquer botão com texto "Pesquisar" via JS
            try:
                pesquisou = frame_form.evaluate("""
                    () => {
                        const candidatos = [...document.querySelectorAll(
                            "button, input[type='button'], input[type='submit'], a"
                        )];
                        for (const b of candidatos) {
                            const t = (b.value || b.textContent || b.innerText || "")
                                        .trim().toLowerCase();
                            if (t.includes("pesquis")) { b.click(); return true; }
                        }
                        return false;
                    }
                """)
                if pesquisou:
                    logger.info("Botão Pesquisar clicado via evaluate JS")
            except Exception as e2:
                logger.warning(f"Não foi possível clicar Pesquisar: {e2}")

        if not pesquisou:
            logger.warning("Botão Pesquisar não encontrado — continuando assim mesmo")

        # 9. Aguardar loading desaparecer + tabela renderizar
        logger.info("Aguardando resultado da pesquisa...")
        _aguardar_loading(frame_form, timeout=LOADING_TIMEOUT)
        time.sleep(1)  # buffer mínimo para renderização

        # 9b. Ordenar por Competência — ID confirmado via diagnóstico
        ID_TH_COMPETENCIA = "resultForm:resultTable:j_idt510"
        try:
            clicou_sort = frame_form.evaluate(f"""
                () => {{
                    const th = document.getElementById('{ID_TH_COMPETENCIA}');
                    if (th) {{ th.click(); return true; }}
                    // fallback: qualquer th sortável com texto Competência
                    for (const el of document.querySelectorAll('th.ui-sortable-column')) {{
                        const txt = (el.innerText || el.textContent || '').trim();
                        if (txt.startsWith('Competência') || txt.startsWith('Compet')) {{
                            el.click(); return 'fallback';
                        }}
                    }}
                    return false;
                }}
            """)
            if clicou_sort:
                time.sleep(0.8)
                logger.info(f"Tabela ordenada por Competência (via: {clicou_sort})")
            else:
                logger.warning("th Competência não encontrado para ordenar")
        except Exception as e_sort:
            logger.debug(f"Sort Competência: {e_sort}")

        # 10. Capturar dados — tenta "Exportar Planilha" primeiro (mais completo),
        #     depois faz scrape direto da tabela como fallback
        logger.info("Capturando dados da tabela...")
        dados = _exportar_ou_scrape(frame_form, pagina)

        if not dados:
            return {"status": "aviso",
                    "mensagem": "Nenhum resultado encontrado no relatório.",
                    "dados_count": 0}

        logger.info(f"{len(dados)} registros extraídos")

        # 11. Postar em Google Sheets
        logger.info("Postando dados em Google Sheets...")
        sucesso, msg = postar_sheets_via_gspread(dados)

        if not sucesso:
            logger.warning(f"Fallback para CSV: {msg}")
            sucesso_csv, msg_csv, arquivo = salvar_como_csv(dados)
            if sucesso_csv:
                return {"status": "sucesso_fallback",
                        "mensagem": f"Dados salvos em CSV ({msg}): {msg_csv}",
                        "dados_count": len(dados), "arquivo": arquivo}
            return {"status": "erro",
                    "mensagem": f"Falha em Sheets e CSV: {msg_csv}",
                    "dados_count": len(dados)}

        return {"status": "sucesso", "mensagem": msg, "dados_count": len(dados)}

    except Exception as e:
        logger.error(f"Erro geral: {e}", exc_info=True)
        return {"status": "erro",
                "mensagem": f"Erro na automação: {e}", "dados_count": 0}

    finally:
        # Não fecha a aba do Solar nem para o Chrome — deixa aberto para o usuário
        if p:
            try:
                p.stop()
            except Exception:
                pass
        logger.info("=" * 60)
        logger.info("AUTOMAÇÃO FINALIZADA")
        logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# INTERFACE PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────

def executar():
    """Ponto de entrada público."""
    return executar_automacao()

if __name__ == "__main__":
    resultado = executar()
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    sys.exit(0 if resultado["status"] != "erro" else 1)
