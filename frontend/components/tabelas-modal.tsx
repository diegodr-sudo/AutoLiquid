"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, Save, Search, Trash2, Upload, X } from "lucide-react";
import { GlassButton, GlassCard } from "./glass-card";
import { GlobalScopeIcon } from "./global-scope-icon";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { SimpleTooltip } from "@/components/ui/simple-tooltip";
import {
  fetchTabela,
  saveTabela,
  type TableDataset,
  type TableKey,
  type TableRow,
} from "@/lib/data";
import { cn } from "@/lib/utils";

interface TabelasModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: TableKey;
  visibleTabs?: TableKey[];
}

const DEFAULT_TABS: TableKey[] = [
  "contratos",
  "vpd",
  "vpd-especiais",
  "uorg",
  "nat-rendimento",
  "fontes-recurso",
  "ncm",
];

const TAB_LABELS: Record<TableKey, string> = {
  contratos: "Contratos",
  vpd: "VPD",
  "vpd-especiais": "VPDs Especiais",
  uorg: "UORG",
  "nat-rendimento": "Nat. Rendimento",
  "fontes-recurso": "Fontes Recurso",
  "datas-impostos": "Datas",
  ncm: "NCM",
};

function matchesSearch(row: TableRow, query: string) {
  const term = query.trim().toLowerCase();
  if (!term) return true;
  return Object.values(row).some((value) =>
    String(value ?? "")
      .toLowerCase()
      .includes(term)
  );
}

export function TabelasModal({
  isOpen,
  onClose,
  initialTab = "contratos",
  visibleTabs,
}: TabelasModalProps) {
  const tabs = visibleTabs && visibleTabs.length > 0 ? visibleTabs : DEFAULT_TABS;
  const fallbackTab = tabs[0] ?? "contratos";
  const [activeTab, setActiveTab] = useState<TableKey>(fallbackTab);
  const [searchQuery, setSearchQuery] = useState("");
  const [datasets, setDatasets] = useState<Partial<Record<TableKey, TableDataset>>>({});
  const [drafts, setDrafts] = useState<Partial<Record<TableKey, TableRow[]>>>({});
  const [selectedRows, setSelectedRows] = useState<Partial<Record<TableKey, number>>>({});
  const [loadingTabs, setLoadingTabs] = useState<Partial<Record<TableKey, boolean>>>({});
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState("");
  const [mensagem, setMensagem] = useState("");

  const currentDataset = datasets[activeTab];
  const currentRows = drafts[activeTab] ?? currentDataset?.rows ?? [];
  const isActiveTabLoading = Boolean(loadingTabs[activeTab]);

  const visibleRows = useMemo(
    () =>
      currentRows
        .map((row, index) => ({ row, index }))
        .filter(({ row }) => matchesSearch(row, searchQuery)),
    [currentRows, searchQuery]
  );

  useEffect(() => {
    if (!tabs.includes(activeTab)) {
      setActiveTab(fallbackTab);
    }
  }, [activeTab, fallbackTab, tabs]);

  useEffect(() => {
    if (!isOpen) return;
    setActiveTab(tabs.includes(initialTab) ? initialTab : fallbackTab);
    setSearchQuery("");
    setErro("");
    setMensagem("");
  }, [fallbackTab, initialTab, isOpen, tabs]);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    // Rastreia quais abas ESTA execução do efeito iniciou o carregamento,
    // para poder limpar o loadingTabs no cleanup caso sejam canceladas.
    const tabsIniciadas = new Set<TableKey>();

    const carregarTab = async (tab: TableKey, options?: { silent?: boolean }) => {
      if (datasets[tab] || loadingTabs[tab]) return;

      tabsIniciadas.add(tab);
      setLoadingTabs((current) => ({ ...current, [tab]: true }));
      if (!options?.silent && tab === activeTab) {
        setErro("");
        setMensagem("");
      }

      try {
        const data = await fetchTabela(tab);
        if (cancelled) return;
        tabsIniciadas.delete(tab); // concluiu — não precisa limpar no cleanup
        setDatasets((current) => ({ ...current, [tab]: data }));
        setDrafts((current) => ({ ...current, [tab]: data.rows }));
      } catch (error) {
        tabsIniciadas.delete(tab);
        if (cancelled || options?.silent || tab !== activeTab) return;
        setErro(
          error instanceof Error
            ? error.message
            : "Nao foi possivel carregar a tabela selecionada."
        );
      } finally {
        if (!cancelled) {
          setLoadingTabs((current) => ({ ...current, [tab]: false }));
        }
      }
    };

    void carregarTab(activeTab);

    for (const tab of tabs) {
      if (tab !== activeTab) {
        void carregarTab(tab, { silent: true });
      }
    }

    return () => {
      cancelled = true;
      // Limpa o estado de carregamento das abas que foram iniciadas mas não
      // concluíram — sem isso, loadingTabs[tab] fica preso em `true` e as
      // abas nunca carregam na próxima abertura do modal.
      if (tabsIniciadas.size > 0) {
        setLoadingTabs((current) => {
          const next = { ...current };
          for (const tab of tabsIniciadas) {
            next[tab] = false;
          }
          return next;
        });
      }
    };
  // IMPORTANTE: `datasets` foi removido intencionalmente das dependências.
  // Incluí-lo causava re-execuções em cascata que cancelavam carregamentos
  // paralelos antes de concluírem, deixando loadingTabs preso em `true`.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, isOpen, tabs]);

  if (!isOpen) return null;

  const isDatasOnly = tabs.length === 1 && tabs[0] === "datas-impostos";
  const activeTabLabel = currentDataset?.label ?? TAB_LABELS[activeTab];

  const updateDraftRow = (rowIndex: number, key: string, value: string) => {
    setDrafts((current) => ({
      ...current,
      [activeTab]: (current[activeTab] ?? []).map((row, index) =>
        index === rowIndex ? { ...row, [key]: value } : row
      ),
    }));
  };

  const handleAddRow = () => {
    if (!currentDataset || currentDataset.fixedRows) return;
    const newRow = currentDataset.columns.reduce<TableRow>((acc, column) => {
      acc[column.key] = "";
      return acc;
    }, {});

    setDrafts((current) => ({
      ...current,
      [activeTab]: [...(current[activeTab] ?? []), newRow],
    }));
    setMensagem("");
  };

  const handleRemoveRow = () => {
    if (!currentDataset || currentDataset.fixedRows) return;
    const selectedIndex = selectedRows[activeTab];
    if (selectedIndex === undefined) return;

    setDrafts((current) => ({
      ...current,
      [activeTab]: (current[activeTab] ?? []).filter((_, index) => index !== selectedIndex),
    }));
    setSelectedRows((current) => {
      const next = { ...current };
      delete next[activeTab];
      return next;
    });
    setMensagem("");
  };

  const handleSave = async () => {
    if (!currentDataset) return;
    setSaving(true);
    setErro("");
    setMensagem("");

    try {
      const saved = await saveTabela(activeTab, currentRows);
      setDatasets((current) => ({ ...current, [activeTab]: saved }));
      setDrafts((current) => ({ ...current, [activeTab]: saved.rows }));
      setMensagem(`${saved.label} salva com sucesso.`)
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Nao foi possivel salvar esta tabela."
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[200] overflow-hidden">
      <div
        className="absolute inset-0 bg-background/90"
        onClick={onClose}
      />

      <div className="relative flex min-h-full items-center justify-center p-2">
      <GlassCard
        className="relative z-10 pointer-events-auto w-full max-w-[min(1120px,calc(100vw-16px))] overflow-hidden border-white/50"
        contentClassName="flex max-h-[calc(100dvh-16px)] min-h-0 flex-col"
      >
        <div className="shrink-0 flex items-center justify-between border-b border-glass-border px-4 py-2.5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-foreground">
                {isDatasOnly ? "Regras de Datas" : "Configuracao de Tabelas"}
              </h2>
              <GlobalScopeIcon label="Global" />
            </div>
            <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground">
              {isDatasOnly
                ? "Edite as regras de vencimento, apuracao e excecoes que entram no fluxo real da automacao."
                : "Todas as tabelas operacionais da automacao estao disponiveis na web e gravam no mesmo armazenamento local."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-secondary/80 hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="shrink-0 grid gap-2 border-b border-glass-border px-4 py-2.5 lg:grid-cols-[minmax(170px,240px)_minmax(0,1fr)_auto_auto] lg:items-end">
          {tabs.length > 1 ? (
            <label className="grid gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Tabela</span>
              <select
                value={activeTab}
                onChange={(event) => {
                  setActiveTab(event.target.value as TableKey);
                  setSearchQuery("");
                  setErro("");
                  setMensagem("");
                }}
                className="select-native h-11 w-full rounded-full border border-glass-border bg-background pl-3 pr-8 text-sm font-medium text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              >
                {tabs.map((tab) => (
                  <option key={tab} value={tab}>
                    {datasets[tab]?.label ?? TAB_LABELS[tab]}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="hidden lg:block" />
          )}

          <div className="relative min-w-0">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={currentDataset?.searchPlaceholder ?? "Buscar..."}
              className="h-11 w-full rounded-full border border-glass-border bg-background/85 pl-10 pr-4 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
            />
          </div>

          <div className="whitespace-nowrap text-sm text-muted-foreground lg:text-right">
            {visibleRows.length} / {currentRows.length} registros
          </div>

          {isDatasOnly ? null : (
            <Tooltip>
              <TooltipTrigger asChild>
                <GlassButton variant="secondary" disabled>
                  <Upload className="h-4 w-4" />
                  Planilha
                </GlassButton>
              </TooltipTrigger>
              <TooltipContent className="z-[210]">Sincronização via planilha ainda não foi ligada na versão web</TooltipContent>
            </Tooltip>
          )}
        </div>

        {currentDataset?.description && activeTab === "datas-impostos" ? (
          <div className="shrink-0 border-b border-glass-border/70 px-5 py-2">
            <SimpleTooltip content={`${activeTabLabel}: ${currentDataset.description}`} side="bottom" className="text-left">
              <p className="line-clamp-2 text-sm text-muted-foreground">
                {currentDataset.description}
              </p>
            </SimpleTooltip>
              <div className="mt-2 rounded-2xl border border-sky-500/20 bg-sky-500/10 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Como editar
                </p>
                <div className="mt-2 space-y-1.5 text-sm text-foreground">
                  <p>
                    Ajuste as linhas existentes quando a regra já faz parte do fluxo atual.
                  </p>
                  <p>
                    Esta tela ja centraliza as regras atuais de <strong>INSS (DDF050)</strong>,
                    <strong> DDF055 </strong>e os municipios de ISS que entram como
                    <strong> DDR001</strong> ou <strong>DOB001</strong>.
                  </p>
                  <p>
                    Adicione uma nova linha para novos municípios, códigos DARF ou exceções de vencimento.
                  </p>
                  <p>
                    A coluna <strong>Dia de Venc.</strong> entra no cálculo automático. A coluna{" "}
                    <strong>Regra de Apuração</strong> define se a automação usa a emissão das NFs ou as datas informadas pelo usuário.
                  </p>
                  <p>
                    Em <strong>Pede LF?</strong>, use <code>Sim</code> ou <code>Não</code>.
                  </p>
                </div>
              </div>
          </div>
        ) : (
          null
        )}

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 py-2.5">
          {!currentDataset && isActiveTabLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Carregando tabela...
            </div>
          ) : erro ? (
            <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {erro}
            </div>
          ) : currentDataset ? (
            <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-glass-border bg-background/65">
              {isActiveTabLoading ? (
                <div className="pointer-events-none absolute right-3 top-3 z-20 rounded-full border border-glass-border bg-background px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
                  Atualizando...
                </div>
              ) : null}
            <div className="scrollable-surface table-scroll-surface min-h-0 flex-1 overflow-x-auto overflow-y-scroll overscroll-contain [touch-action:pan-y]">
              <table className="min-w-[1120px]">
                <thead className="sticky top-0 z-10 bg-background">
                  <tr className="border-b border-glass-border">
                    {currentDataset.columns.map((column) => (
                      <th
                        key={column.key}
                        className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground"
                      >
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {visibleRows.length > 0 ? (
                    visibleRows.map(({ row, index }) => {
                      const selected = selectedRows[activeTab] === index;
                      return (
                        <tr
                          key={`${activeTab}-${index}`}
                          onClick={() =>
                            setSelectedRows((current) => ({
                              ...current,
                              [activeTab]: index,
                            }))
                          }
                          className={cn(
                            "border-b border-glass-border/70 transition-colors",
                            selected
                              ? "bg-primary/10"
                              : "hover:bg-secondary/45"
                          )}
                        >
                          {currentDataset.columns.map((column) => {
                            const editable = column.editable;
                            const value = row[column.key] ?? "";
                            return (
                              <td key={column.key} className="px-3 py-1.5 align-top">
                                {editable ? (
                                  <input
                                    type="text"
                                    value={value}
                                    onClick={(event) => event.stopPropagation()}
                                    onChange={(event) =>
                                      updateDraftRow(index, column.key, event.target.value)
                                    }
                                    className="w-full rounded-lg border border-transparent bg-transparent px-2 py-1.5 text-sm text-foreground outline-none transition focus:border-primary focus:bg-background/85 focus:ring-2 focus:ring-primary/15"
                                  />
                                ) : (
                                  <div className="px-2 py-1.5 text-sm text-foreground">
                                    {value || "—"}
                                  </div>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td
                        colSpan={currentDataset.columns.length}
                        className="px-4 py-12 text-center text-sm text-muted-foreground"
                      >
                        Nenhum registro encontrado para o filtro atual.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            </div>
          ) : (
            <div className="rounded-xl border border-glass-border bg-secondary/30 px-4 py-10 text-center text-sm text-muted-foreground">
              Nenhuma tabela carregada.
            </div>
          )}
        </div>

        <div className="shrink-0 flex items-center justify-between gap-4 border-t border-glass-border px-4 py-2.5">
          <div className="flex gap-2">
            <GlassButton
              variant="secondary"
              size="sm"
              onClick={handleAddRow}
              disabled={!currentDataset || currentDataset.fixedRows || saving}
            >
              <Plus className="h-4 w-4" />
              Adicionar
            </GlassButton>
            <GlassButton
              variant="secondary"
              size="sm"
              onClick={handleRemoveRow}
              disabled={
                !currentDataset ||
                currentDataset.fixedRows ||
                selectedRows[activeTab] === undefined ||
                saving
              }
            >
              <Trash2 className="h-4 w-4" />
              Remover
            </GlassButton>
          </div>

          <div className="flex items-center gap-3">
            {mensagem && (
              <span className="text-sm font-medium text-success">{mensagem}</span>
            )}
            <GlassButton variant="ghost" onClick={onClose} disabled={saving}>
              Cancelar
            </GlassButton>
            <GlassButton
              variant="primary"
              onClick={handleSave}
              disabled={!currentDataset || saving}
            >
              <Save className="h-4 w-4" />
              {saving ? "Salvando..." : "Salvar"}
            </GlassButton>
          </div>
        </div>
      </GlassCard>
      </div>
    </div>
  );
}
