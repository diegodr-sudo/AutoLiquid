"""
Extrator headless da fila de processos no Solar (JSF/PrimeFaces).

Escolha de arquitetura: Playwright headless (mais robusto para JSF/AJAX/ViewState).

Fluxo:
1) Abre a página alvo.
2) Faz login (se tela CAS estiver presente e credenciais forem fornecidas).
3) Aplica filtros no formulário JSF.
4) Clica em "Pesquisar" e aguarda atualização AJAX.
5) Captura a tabela HTML renderizada e converte para pandas.DataFrame.
6) Opcionalmente exporta JSON (records) e Excel.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Frame, Page, sync_playwright
from core.runtime_config import obter_porta_chrome


TARGET_URL = "https://suporte.egestao.ufsc.br/pagamentos/index.xhtml"
DEFAULT_FILTERS = {
    # No Solar, "Selecione..." equivale a consultar todas as situações.
    "consForm:situacaoSelect_input": "-9999999",
}
EXPECTED_COLUMNS = [
    "Recebido Por",
    "Competência",
    "Tipo",
    "CPF/CNPJ",
    "Fornecedor/Interessado",
    "Valor",
    "Contrato",
    "IC",
    "Data Enc.",
    "Setor Origem",
    "Protocolo",
    "Número Processo",
    "Sol. Pagamento",
]


@dataclass
class SolarFilaConfig:
    headless: bool = True
    timeout_ms: int = 45000
    username: str | None = None
    password: str | None = None
    filters: dict[str, str] = field(default_factory=dict)
    close_tab: bool = False


class SolarFilaExtractor:
    def __init__(self, config: SolarFilaConfig):
        self.config = config

    def extract(self) -> pd.DataFrame:
        with sync_playwright() as playwright:
            # Estratégia preferencial sem senha: reutilizar sessão autenticada
            # de um Chrome já aberto com depuração remota.
            sem_credenciais = not self.config.username or not self.config.password
            if sem_credenciais:
                try:
                    return self._extract_via_cdp_session(playwright)
                except Exception as exc:
                    mensagem = str(exc or "").strip()
                    # Mantém explícito erro de autenticação/sessão quando for esse o caso.
                    if "Sessão do Chrome não autenticada" in mensagem:
                        raise
                    if "connect_over_cdp" in mensagem or "ECONNREFUSED" in mensagem or "127.0.0.1" in mensagem:
                        raise RuntimeError(
                            "Não foi possível conectar ao Chrome da sessão atual. "
                            "Abra o Chrome pelo AutoLiquid e tente novamente."
                        ) from exc
                    # Não mascara falhas reais de extração (tabela, seletor, parsing etc.).
                    raise RuntimeError(f"Falha ao extrair fila usando sessão do Chrome: {mensagem}") from exc

            browser = playwright.chromium.launch(headless=self.config.headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(self.config.timeout_ms)

            try:
                return self._extract_from_page(page, require_login=True)
            finally:
                context.close()
                browser.close()

    def _extract_via_cdp_session(self, playwright) -> pd.DataFrame:
        porta = obter_porta_chrome()
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        # Sempre usa uma nova aba para não interferir na navegação atual do usuário.
        page = context.new_page()
        page.set_default_timeout(self.config.timeout_ms)

        try:
            # Aqui não exigimos login automático: esperamos que a sessão já esteja autenticada.
            return self._extract_from_page(page, require_login=False)
        finally:
            if self.config.close_tab:
                try:
                    page.close()
                except Exception:
                    pass

    def _extract_from_page(self, page: Page, require_login: bool) -> pd.DataFrame:
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        if require_login:
            self._login_if_needed(page)
        else:
            if page.locator("form#fm1, form[action*='login']").count() > 0:
                self._try_resume_authenticated_session(page)
            if page.locator("form#fm1, form[action*='login']").count() > 0:
                raise RuntimeError(
                    "Sessão do Chrome não autenticada no Solar. Faça login manualmente uma vez e tente novamente."
                )
        frame = self._resolve_form_frame(page)
        self._apply_filters(frame, self._resolved_filters())
        previous_signature = self._table_signature(frame)
        self._click_search(frame)
        self._wait_for_results(frame, previous_signature)
        headers, rows = self._extract_results_table_rows(frame)
        dataframe = self._table_rows_to_dataframe(headers, rows)
        return self._normalize_dataframe(dataframe)

    def _login_if_needed(self, page: Page) -> None:
        has_login_form = page.locator("form#fm1, form[action*='login']").count() > 0
        if not has_login_form:
            return

        if not self.config.username or not self.config.password:
            raise RuntimeError(
                "Tela de login detectada, mas usuário/senha não foram informados."
            )

        username = page.locator(
            "input#username, input[name='username'], input[id*='user']"
        ).first
        password = page.locator(
            "input#password, input[name='password'], input[type='password']"
        ).first
        username.fill(self.config.username)
        password.fill(self.config.password)

        submit = page.locator(
            "input[type='submit'][value='Entrar'], button:has-text('Entrar'), #fm1 button[type='submit']"
        ).first
        submit.click()
        page.wait_for_load_state("domcontentloaded")

    def _try_resume_authenticated_session(self, page: Page) -> None:
        submit_candidates = [
            "input.btn-submit[value='Entrar']",
            "input[type='submit'][value='Entrar']",
            "button[type='submit']",
            "button:has-text('Entrar')",
        ]

        for selector in submit_candidates:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            try:
                locator.click()
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(1500)
                if page.locator("form#fm1, form[action*='login']").count() == 0:
                    return
            except Exception:
                continue

        try:
            page.locator("form#fm1, form[action*='login']").first.evaluate(
                "(form) => form.submit()"
            )
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1500)
        except Exception:
            pass

    def _resolve_form_frame(self, page: Page) -> Frame:
        if page.locator("[id='consForm'], form[id='consForm']").count() > 0:
            return page.main_frame

        for frame in page.frames:
            try:
                if frame.locator("[id='consForm'], form[id='consForm']").count() > 0:
                    return frame
            except Exception:
                continue

        # fallback: em alguns cenários a página principal já está correta
        return page.main_frame

    def _apply_filters(self, frame: Frame, filters: dict[str, str]) -> None:
        for field_id, value in filters.items():
            self._set_field_value(frame, field_id, value)

    def _resolved_filters(self) -> dict[str, str]:
        filters = dict(DEFAULT_FILTERS)
        filters.update(self.config.filters)
        return filters

    def _set_field_value(self, frame: Frame, field_id: str, value: str) -> None:
        if field_id == "consForm:situacaoSelect_input" and value == "-9999999":
            if self._select_situacao_todos_via_ui(frame):
                return

        # Caminho 1: input/select direto pelo ID JSF (com dois-pontos)
        direct_locator = frame.locator(f"[id='{field_id}']").first
        if direct_locator.count() > 0:
            tag_name = direct_locator.evaluate("el => el.tagName.toLowerCase()")
            if tag_name in {"input", "textarea"}:
                direct_locator.fill(value)
                direct_locator.dispatch_event("change")
                return
            if tag_name == "select":
                try:
                    direct_locator.select_option(value=value)
                except Exception:
                    # fallback por label visível
                    direct_locator.select_option(label=value)
                direct_locator.dispatch_event("change")
                return

        # Caminho 2: PrimeFaces selectOneMenu (_input hidden)
        if field_id.endswith("_input"):
            widget_id = field_id[: -len("_input")]
            frame.evaluate(
                """
                ({ fieldId, widgetId, selectedValue }) => {
                    const hidden = document.getElementById(fieldId);
                    if (hidden) {
                        hidden.value = selectedValue;
                        hidden.dispatchEvent(new Event("change", { bubbles: true }));
                        hidden.dispatchEvent(new Event("input", { bubbles: true }));
                    }
                    const widget = document.getElementById(widgetId);
                    if (widget) {
                        const label = widget.querySelector(".ui-selectonemenu-label");
                        if (label) label.textContent = selectedValue;
                    }
                }
                """,
                {"fieldId": field_id, "widgetId": widget_id, "selectedValue": value},
            )
            return

        raise RuntimeError(f"Não foi possível preencher o filtro '{field_id}'.")

    def _select_situacao_todos_via_ui(self, frame: Frame) -> bool:
        trigger = frame.locator(
            "[id='consForm:situacaoSelect'] .ui-selectonemenu-trigger, [id='consForm:situacaoSelect']"
        ).first
        if trigger.count() == 0:
            return False

        try:
            trigger.click()
            frame.wait_for_timeout(400)

            option = frame.locator(
                "[id='consForm:situacaoSelect_panel'] li[data-label='Selecione...'], "
                "[id='consForm:situacaoSelect_panel'] li:first-child"
            ).first
            if option.count() == 0:
                return False

            option.click()
            frame.wait_for_timeout(300)
            return True
        except Exception:
            return False

    def _click_search(self, frame: Frame) -> None:
        candidates = [
            "[id*='pesquisar']",
            "[id*='Pesquisar']",
            "button:has-text('Pesquisar')",
            "input[type='submit'][value*='Pesquis']",
            "input[type='button'][value*='Pesquis']",
        ]
        for selector in candidates:
            locator = frame.locator(selector).first
            if locator.count() > 0:
                locator.click()
                return

        raise RuntimeError("Botão 'Pesquisar' não encontrado no formulário.")

    def _wait_for_results(self, frame: Frame, previous_signature: str) -> None:
        try:
            # PrimeFaces blockUI/loading comum
            frame.wait_for_function(
                """
                () => {
                  const loading = document.getElementById("panelLoadingInvs");
                  if (!loading) return true;
                  const st = window.getComputedStyle(loading);
                  return st.display === "none" || st.visibility === "hidden" || st.opacity === "0";
                }
                """,
                timeout=self.config.timeout_ms,
            )
        except PlaywrightTimeoutError:
            # fallback para tentar seguir mesmo sem indicador explícito
            pass

        # Aguarda a tabela do resultado aparecer/renderizar. Em algumas telas do
        # Solar a tabela vem como DataTables sem id resultTable, então aceitamos
        # qualquer tabela visível que contenha cabeçalhos esperados da fila.
        frame.wait_for_function(
            """
            () => {
              const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
              const expected = ["Recebido", "Competência", "Tipo", "CPF/CNPJ", "Fornecedor", "Valor"];
              return Array.from(document.querySelectorAll("table")).some((table) => {
                const style = window.getComputedStyle(table);
                if (style.display === "none" || style.visibility === "hidden") return false;
                const text = clean(table.innerText || table.textContent);
                const rows = table.querySelectorAll("tbody tr");
                return rows.length > 0 && expected.filter((item) => text.includes(item)).length >= 4;
              });
            }
            """,
            timeout=self.config.timeout_ms,
        )

        # Aguarda a tabela realmente atualizar após o clique em "Pesquisar".
        # Em JSF/PrimeFaces a tabela já pode existir antes da busca; por isso
        # esperamos mudança de conteúdo (assinatura) OU estabilização do DOM.
        try:
            frame.wait_for_function(
                """
                (oldSignature) => {
                  const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
                  const expected = ["Recebido", "Competência", "Tipo", "CPF/CNPJ", "Fornecedor", "Valor"];
                  const tables = Array.from(document.querySelectorAll("[id='resultForm:resultTable'], [id*='resultTable'], table"));
                  const table = tables
                    .map((candidate) => {
                      const text = clean(candidate.innerText || candidate.textContent);
                      const score = expected.filter((item) => text.includes(item)).length;
                      return { table: candidate, score, rows: candidate.querySelectorAll("tbody tr").length };
                    })
                    .filter((item) => item.rows > 0 && item.score >= 4)
                    .sort((a, b) => (b.score - a.score) || (b.rows - a.rows))[0]?.table;
                  if (!table) return false;
                  const rows = table.querySelectorAll("tbody tr");
                  const preview = Array.from(rows)
                    .slice(0, 5)
                    .map((tr) => (tr.textContent || "").replace(/\\s+/g, " ").trim())
                    .join("|");
                  const current = `${rows.length}::${preview}`;
                  return current !== oldSignature;
                }
                """,
                arg=previous_signature,
                timeout=min(self.config.timeout_ms, 20000),
            )
        except PlaywrightTimeoutError:
            # Se não houve mudança detectável, aguarda um ciclo extra para
            # evitar capturar estado transitório logo após o AJAX.
            frame.wait_for_timeout(1200)

        # Pequeno debounce final para garantir renderização completa.
        frame.wait_for_timeout(500)

    def _table_signature(self, frame: Frame) -> str:
        try:
            return frame.evaluate(
                """
                () => {
                  const clean = (value) => (value || "").replace(/\\s+/g, " ").trim();
                  const expected = ["Recebido", "Competência", "Tipo", "CPF/CNPJ", "Fornecedor", "Valor"];
                  const tables = Array.from(document.querySelectorAll("[id='resultForm:resultTable'], [id*='resultTable'], table"));
                  const table = tables
                    .map((candidate) => {
                      const text = clean(candidate.innerText || candidate.textContent);
                      const score = expected.filter((item) => text.includes(item)).length;
                      return { table: candidate, score, rows: candidate.querySelectorAll("tbody tr").length };
                    })
                    .filter((item) => item.rows > 0 && item.score >= 4)
                    .sort((a, b) => (b.score - a.score) || (b.rows - a.rows))[0]?.table;
                  if (!table) return "__sem_tabela__";
                  const rows = table.querySelectorAll("tbody tr");
                  const preview = Array.from(rows)
                    .slice(0, 5)
                    .map((tr) => (tr.textContent || "").replace(/\\s+/g, " ").trim())
                    .join("|");
                  return `${rows.length}::${preview}`;
                }
                """
            )
        except Exception:
            return "__assinatura_indisponivel__"

    def _extract_results_table_rows(self, frame: Frame) -> tuple[list[str], list[list[str]]]:
        payload = frame.evaluate(
            """
            () => {
              const clean = (value) =>
                (value || "")
                  .replace(/\\u00a0/g, " ")
                  .replace(/\\s+/g, " ")
                  .trim();

              const expected = ["Recebido", "Competência", "Tipo", "CPF/CNPJ", "Fornecedor", "Valor"];
              let bestTable = null;
              let bestScore = -1;
              let bestRows = -1;
              for (const table of Array.from(document.querySelectorAll("[id='resultForm:resultTable'], [id*='resultTable'], table"))) {
                const style = window.getComputedStyle(table);
                if (style.display === "none" || style.visibility === "hidden") continue;
                const text = clean(table.innerText || table.textContent);
                const rows = table.querySelectorAll("tbody tr").length;
                const score = expected.filter((item) => text.includes(item)).length;
                if (rows > 0 && score >= 4 && (score > bestScore || (score === bestScore && rows > bestRows))) {
                  bestTable = table;
                  bestScore = score;
                  bestRows = rows;
                }
              }
              if (!bestTable) {
                return { headers: [], rows: [] };
              }

              let headers = [];
              let visibleColumnIndexes = [];
              const thead = bestTable.querySelector("thead");
              if (thead) {
                const theadRows = thead.querySelectorAll("tr");
                const headerRow = theadRows[theadRows.length - 1];
                const allThs = Array.from(headerRow.querySelectorAll("th"));

                allThs.forEach((th, idx) => {
                  if (th.classList.contains("ui-helper-hidden")) return;

                  const titleEl = th.querySelector(".ui-column-title");
                  const text = titleEl
                    ? clean(titleEl.textContent)
                    : clean((th.textContent || "").split("\\n")[0]);

                  if (text) {
                    headers.push(text);
                    visibleColumnIndexes.push(idx);
                  }
                });
              }

              const rows = Array.from(bestTable.querySelectorAll("tbody tr"))
                .filter((tr) =>
                  !tr.classList.contains("separador")
                  && !tr.classList.contains("total-row")
                  && tr.getAttribute("role") !== "separator"
                )
                .map((tr) => {
                  const allTds = Array.from(tr.querySelectorAll("td"));
                  return visibleColumnIndexes.map((idx) => {
                    const td = allTds[idx];
                    if (!td) return "";
                    const clone = td.cloneNode(true);
                    clone.querySelectorAll(".ui-column-title").forEach((node) => node.remove());
                    const explicitParts = Array.from(clone.childNodes)
                      .map((node) => {
                        if (node.nodeType === Node.TEXT_NODE) {
                          return node.textContent || "";
                        }
                        if (node.nodeType === Node.ELEMENT_NODE) {
                          return node.textContent || "";
                        }
                        return "";
                      })
                      .map((text) => clean(text))
                      .filter(Boolean);

                    if (explicitParts.length > 1) {
                      return explicitParts.join(" ");
                    }

                    return clean(clone.innerText || clone.textContent);
                  });
                })
                .filter((row) => row.some((cell) => cell));

              return { headers, rows };
            }
            """
        )
        headers = [str(item).strip() for item in (payload or {}).get("headers") or []]
        rows = [
            [str(cell).strip() for cell in row]
            for row in ((payload or {}).get("rows") or [])
            if isinstance(row, list)
        ]
        if not headers and rows:
            headers = [f"Coluna {idx + 1}" for idx in range(len(rows[0]))]
        return headers, rows

    def _table_rows_to_dataframe(self, headers: list[str], rows: list[list[str]]) -> pd.DataFrame:
        normalized_headers = self._resolve_output_headers(headers, rows)
        total_colunas = len(normalized_headers)

        if not rows:
            return pd.DataFrame(columns=normalized_headers)

        normalized_rows = []
        for row in rows:
            values = self._normalize_row_length(row, total_colunas)
            if len(values) < total_colunas:
                values.extend([""] * (total_colunas - len(values)))
            normalized_rows.append(values)

        return pd.DataFrame(normalized_rows, columns=normalized_headers)

    def _normalize_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        df = dataframe.copy()

        # Flatten de colunas MultiIndex geradas por read_html em tabelas complexas.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [
                " ".join(str(item).strip() for item in col if str(item).strip())
                for col in df.columns.to_flat_index()
            ]
        else:
            df.columns = [str(col).strip() for col in df.columns]

        df.columns = self._make_unique_columns(df.columns)

        # Remove colunas vazias/auxiliares do PrimeFaces.
        df = df.loc[:, [col for col in df.columns if col and not col.lower().startswith("unnamed")]]

        # Normaliza strings.
        for col in df.columns:
            column_data = df[col]
            if isinstance(column_data, pd.DataFrame):
                continue
            if column_data.dtype == object:
                df[col] = (
                    column_data
                    .astype(str)
                    .str.replace(r"\s+", " ", regex=True)
                    .str.strip()
                    .replace({"nan": "", "None": ""})
                )
        return df

    def _make_unique_columns(self, columns: pd.Index | list[str]) -> list[str]:
        counts: dict[str, int] = {}
        unique_columns: list[str] = []

        for raw_name in columns:
            base_name = str(raw_name or "").strip()
            if not base_name:
                base_name = f"Coluna {len(unique_columns) + 1}"
            occurrence = counts.get(base_name, 0) + 1
            counts[base_name] = occurrence
            unique_columns.append(base_name if occurrence == 1 else f"{base_name} ({occurrence})")

        return unique_columns

    def _resolve_output_headers(self, headers: list[str], rows: list[list[str]]) -> list[str]:
        observed_max = max((len(row) for row in rows), default=0)
        observed_cols = max(len(headers), observed_max)
        if observed_cols == len(EXPECTED_COLUMNS):
            return list(EXPECTED_COLUMNS)

        normalized_headers = list(headers[:observed_cols])
        while len(normalized_headers) < observed_cols:
            normalized_headers.append(f"Coluna {len(normalized_headers) + 1}")
        return normalized_headers

    def _normalize_row_length(self, row: list[str], total_colunas: int) -> list[str]:
        values = list(row)
        if total_colunas == len(EXPECTED_COLUMNS) and len(values) == total_colunas - 1:
            # "Recebido Por" pode vir vazio; nesse caso preservamos o alinhamento
            # inserindo uma célula vazia no início da linha.
            values = ["", *values]
        return values[:total_colunas]


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.to_dict(orient="records")


def _parse_filters(raw_filters: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in raw_filters:
        if "=" not in item:
            raise ValueError(
                f"Filtro inválido '{item}'. Use o formato campo_id=valor."
            )
        key, value = item.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai fila de processos do Solar (headless) e retorna DataFrame/JSON/Excel."
    )
    parser.add_argument(
        "--username",
        default=os.getenv("SOLAR_USERNAME"),
        help="Usuário para login (ou SOLAR_USERNAME).",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("SOLAR_PASSWORD"),
        help="Senha para login (ou SOLAR_PASSWORD).",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Timeout padrão em milissegundos.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Executa com browser visível (debug).",
    )
    parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        help="Filtro no formato campo_id=valor. Pode repetir a flag.",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Caminho para salvar JSON (records).",
    )
    parser.add_argument(
        "--excel-out",
        default="",
        help="Caminho para salvar Excel (.xlsx).",
    )
    args = parser.parse_args()

    filters = _parse_filters(args.filters)
    config = SolarFilaConfig(
        headless=not args.headed,
        timeout_ms=args.timeout_ms,
        username=args.username,
        password=args.password,
        filters=filters,
    )
    extractor = SolarFilaExtractor(config)
    dataframe = extractor.extract()
    records = dataframe_to_records(dataframe)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)

    if args.excel_out:
        dataframe.to_excel(args.excel_out, index=False)

    print(
        json.dumps(
            {
                "status": "ok",
                "rows": len(dataframe),
                "columns": list(dataframe.columns),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
