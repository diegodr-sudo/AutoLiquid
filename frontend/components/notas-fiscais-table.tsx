"use client";

import { useState, type ReactNode } from "react";
import { Check, ChevronDown, ChevronRight, Loader2, X, AlertTriangle } from "lucide-react";
import { GlassCard, GlassButton, GlassTable, GlassTableRow, GlassTableCell, GlassPanel } from "./glass-card";
import type { Deducao, Empenho, NotaFiscal, PendenciaDocumento, ProcessDates, ResumoFinanceiro } from "@/lib/data";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { PendenciasPanel } from "@/components/pendencias-panel";

type TabType = "notas" | "empenhos" | "deducoes" | "pendencias" | "log";

interface DatasDeducao {
  apuracao: string;
  vencimento: string;
}

interface NotasFiscaisTableProps {
  notasFiscais: NotaFiscal[];
  empenhos: Empenho[];
  deducoes: Deducao[];
  resumo: ResumoFinanceiro;
  dates?: ProcessDates;
  datasDeducoes?: Record<number, DatasDeducao>;
  onDatasDeducaoChange?: (dedId: number, datas: DatasDeducao) => void;
  logs?: string[];
  logsSimples?: string[];
  nivelLog?: "simples" | "desenvolvedor";
  pendencias?: PendenciaDocumento[];
  pendenciasExtraContent?: ReactNode;
  onTogglePendenciaResolvida?: (pendencia: PendenciaDocumento, resolvida: boolean) => void;
  pendenciaToggleId?: string | null;
  onLimparLogs?: () => void;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value) + "%";
}

function formatEditableCurrency(value: number): string {
  return value.toFixed(2).replace(".", ",");
}

function parseEditableCurrency(value: string): number | null {
  const normalized = value.replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function obterBasePercentual(
  deducao: Deducao,
  resumoBruto: number,
  brutoNotas: number
): number {
  if (deducao.baseCalculo > 0) return deducao.baseCalculo;
  if (resumoBruto > 0) return resumoBruto;
  return brutoNotas;
}

function distribuirRetencaoPorNotas(notasFiscais: NotaFiscal[], valorTotalDeducao: number) {
  const brutoNotas = notasFiscais.reduce((acc, nota) => acc + nota.valor, 0);
  const percentual = brutoNotas > 0 ? valorTotalDeducao / brutoNotas : 0;
  const itens = notasFiscais.map((nota) => ({
    nota,
    percentual,
    retencao: Number((nota.valor * percentual).toFixed(2)),
  }));

  const totalRateado = itens.reduce((acc, item) => acc + item.retencao, 0);
  const diferenca = Number((valorTotalDeducao - totalRateado).toFixed(2));
  if (itens.length > 0 && diferenca !== 0) {
    itens[itens.length - 1].retencao = Number((itens[itens.length - 1].retencao + diferenca).toFixed(2));
  }

  return {
    percentual,
    brutoNotas,
    itens,
  };
}

type LogLineType = "header" | "ok" | "run" | "err" | "warn" | "info";

function normalizeLogText(value: string): string {
  return value
    .replace(/DeduÃ§Ã£o/g, "Dedução")
    .replace(/ExecuÃ§Ã£o/g, "Execução")
    .replace(/SituaÃ§Ã£o/g, "Situação")
    .replace(/ConfirmaÃ§Ã£o/g, "Confirmação")
    .replace(/revalidaÃ§Ã£o/g, "revalidação")
    .replace(/ValidaÃ§Ã£o/g, "Validação")
    .replace(/ObservaÃ§Ã£o/g, "Observação")
    .replace(/MunicÃ­pio/g, "Município")
    .replace(/CÃ³digo/g, "Código")
    .replace(/NÃ£o/g, "Não")
    .replace(/nÃ£o/g, "não")
    .replace(/estÃ¡/g, "está")
    .replace(/sÃ©rie/g, "série")
    .replace(/SÃ©rie/g, "Série")
    .replace(/lanÃ§/g, "lanç")
    .replace(/Ã¡/g, "á")
    .replace(/Ã¢/g, "â")
    .replace(/Ã£/g, "ã")
    .replace(/Ã§/g, "ç")
    .replace(/Ã©/g, "é")
    .replace(/Ãª/g, "ê")
    .replace(/Ã­/g, "í")
    .replace(/Ã³/g, "ó")
    .replace(/Ã´/g, "ô")
    .replace(/Ãµ/g, "õ")
    .replace(/Ãº/g, "ú")
    .replace(/Âº/g, "º")
    .replace(/Âª/g, "ª")
    .replace(/â€”/g, "—")
    .replace(/â€“/g, "–")
    .replace(/â€¢/g, "•")
    .replace(/â†’/g, "→")
    .replace(/âœ“/g, "✓")
    .replace(/âœ—/g, "✗")
    .replace(/âš /g, "⚠ ");
}

function parseLogLine(raw: string): { type: LogLineType; text: string } {
  const normalized = normalizeLogText(raw);

  if (normalized.startsWith("HEADER ")) return { type: "header", text: normalized.slice(7) };
  if (normalized.startsWith("OK "))     return { type: "ok",     text: normalized.slice(3) };
  if (normalized.startsWith("RUN "))    return { type: "run",    text: normalized.slice(4) };
  if (normalized.startsWith("ERR "))    return { type: "err",    text: normalized.slice(4) };
  if (normalized.startsWith("WARN "))   return { type: "warn",   text: normalized.slice(5) };
  // Dev log lines — derive type from existing prefix conventions
  if (normalized.startsWith("✓"))  return { type: "ok",   text: normalized.slice(1).trimStart() };
  if (normalized.startsWith("✗"))  return { type: "err",  text: normalized.slice(1).trimStart() };
  if (normalized.startsWith("⚠"))  return { type: "warn", text: normalized.slice(1).trimStart() };
  if (normalized.startsWith("→"))  return { type: "run",  text: normalized.slice(1).trimStart() };
  return { type: "info", text: normalized };
}

function SimpleLogLine({ raw }: { raw: string }) {
  const { type, text } = parseLogLine(raw);

  if (type === "header") {
    return (
      <div className="flex items-center gap-3 pb-1 pt-3 first:pt-0">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {text}
        </span>
        <span className="h-px flex-1 bg-glass-border" />
      </div>
    );
  }

  const dotClass =
    type === "ok"   ? "bg-success" :
    type === "run"  ? "bg-primary animate-pulse" :
    type === "err"  ? "bg-destructive" :
    type === "warn" ? "bg-warning" :
                      "bg-muted-foreground/40";

  const textClass =
    type === "err"  ? "text-destructive" :
    type === "warn" ? "text-warning" :
    type === "run"  ? "text-primary" :
                      "text-foreground";

  const Icon =
    type === "ok"   ? Check :
    type === "err"  ? X :
    type === "warn" ? AlertTriangle :
    type === "run"  ? Loader2 :
                      null;

  return (
    <div className="flex items-start gap-2.5 py-1">
      <span className="mt-[5px] flex h-4 w-4 flex-shrink-0 items-center justify-center">
        {Icon ? (
          <Icon
            className={`h-3.5 w-3.5 ${
              type === "ok"   ? "text-success" :
              type === "err"  ? "text-destructive" :
              type === "warn" ? "text-warning" :
              type === "run"  ? "text-primary animate-spin" :
                                "text-muted-foreground"
            }`}
            strokeWidth={type === "ok" ? 2.5 : 2}
          />
        ) : (
          <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
        )}
      </span>
      <span className={`text-sm leading-snug ${textClass}`}>{text}</span>
    </div>
  );
}

function DevLogLine({ raw }: { raw: string }) {
  const { type, text } = parseLogLine(raw);
  const lineClass =
    type === "ok"
      ? "border-success/20 bg-success/5"
      : type === "err"
        ? "border-destructive/20 bg-destructive/5"
        : type === "warn"
          ? "border-warning/20 bg-warning/5"
          : type === "run"
            ? "border-primary/20 bg-primary/5"
            : "border-glass-border/60 bg-background/55";
  const textClass =
    type === "err"
      ? "text-destructive"
      : type === "warn"
        ? "text-warning"
        : type === "run"
          ? "text-primary"
          : type === "ok"
            ? "text-success"
            : "text-foreground/80";

  return (
    <div className={`rounded-xl border px-3 py-2 ${lineClass}`}>
      <p className={`font-mono text-[12px] leading-6 ${textClass}`}>{text}</p>
    </div>
  );
}

export function NotasFiscaisTable({
  notasFiscais,
  empenhos,
  deducoes,
  resumo,
  dates,
  datasDeducoes = {},
  onDatasDeducaoChange,
  logs = [],
  logsSimples = [],
  nivelLog = "desenvolvedor",
  pendencias = [],
  pendenciasExtraContent,
  onTogglePendenciaResolvida,
  pendenciaToggleId,
  onLimparLogs,
}: NotasFiscaisTableProps) {
  const [activeTab, setActiveTab] = useState<TabType>("pendencias");
  const [expandedDeducoes, setExpandedDeducoes] = useState<number[]>([]);
  const [retencoesEditadas, setRetencoesEditadas] = useState<Record<string, string>>({});
  const [basesEditadas, setBasesEditadas] = useState<Record<string, string>>({});
  const totalDeducoes = deducoes.reduce((acc, deducao) => acc + deducao.valor, 0);
  const totalNotas = notasFiscais.reduce((acc, nota) => acc + nota.valor, 0);
  const basePercentualTotal = resumo.bruto > 0 ? resumo.bruto : totalNotas;
  const deducoesAgrupadas = Array.from(
    deducoes.reduce((acc, deducao) => {
      const chave = String(deducao.siafi || deducao.codigo || "OUTROS").toUpperCase();
      const grupo = acc.get(chave) ?? {
        id: chave,
        titulo: chave,
        valor: 0,
        quantidade: 0,
        codigos: new Set<string>(),
        itens: [] as Deducao[],
      };
      grupo.valor += deducao.valor;
      grupo.quantidade += 1;
      if (deducao.codigo && deducao.codigo !== "—") {
        grupo.codigos.add(deducao.codigo);
      }
      grupo.itens.push(deducao);
      acc.set(chave, grupo);
      return acc;
    }, new Map<string, { id: string; titulo: string; valor: number; quantidade: number; codigos: Set<string>; itens: Deducao[] }>())
  ).map(([_, grupo]) => grupo);

  const tabs: { id: TabType; label: string }[] = [
    { id: "pendencias", label: `Pendências (${pendencias.length})` },
    { id: "notas", label: `Documentos (${notasFiscais.length})` },
    { id: "empenhos", label: `Empenhos (${empenhos.length})` },
    { id: "deducoes", label: `Deduções (${deducoesAgrupadas.length})` },
  ];

  const alternarDeducao = (id: number) => {
    setExpandedDeducoes((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
  };

  const atualizarRetencao = (key: string, value: string) => {
    setRetencoesEditadas((current) => ({
      ...current,
      [key]: value,
    }));
  };

  const atualizarBase = (key: string, value: string) => {
    setBasesEditadas((current) => ({ ...current, [key]: value }));
  };

  const normalizarBase = (key: string, valorOriginal: number) => {
    setBasesEditadas((current) => {
      const raw = current[key];
      if (raw === undefined) return current;
      const parsed = parseEditableCurrency(raw);
      return {
        ...current,
        [key]: parsed !== null ? formatEditableCurrency(parsed) : formatEditableCurrency(valorOriginal),
      };
    });
  };

  const normalizarRetencao = (key: string, valorOriginal: number) => {
    setRetencoesEditadas((current) => {
      const raw = current[key];
      if (raw === undefined) return current;
      const parsed = parseEditableCurrency(raw);
      return {
        ...current,
        [key]: formatEditableCurrency(parsed ?? valorOriginal),
      };
    });
  };

  return (
    <GlassCard className="overflow-hidden">
      <div className="flex flex-nowrap overflow-x-auto border-b border-glass-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`shrink-0 whitespace-nowrap px-3 py-3 text-[13px] font-medium transition-colors sm:px-4 lg:px-5 ${
              activeTab === tab.id
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {activeTab === "notas" && (
          <GlassTable headers={["", "Tipo", "Nota", "Emissão", "Ateste", "Valor"]}>
            {notasFiscais.map((nota, index) => (
              <GlassTableRow key={nota.id}>
                <GlassTableCell className="w-12 text-muted-foreground">
                  {index + 1}
                </GlassTableCell>
                <GlassTableCell className="whitespace-nowrap">{nota.tipo}</GlassTableCell>
                <GlassTableCell className="whitespace-nowrap">{nota.nota}</GlassTableCell>
                <GlassTableCell className="whitespace-nowrap">{nota.emissao}</GlassTableCell>
                <GlassTableCell className="whitespace-nowrap text-primary">{nota.ateste}</GlassTableCell>
                <GlassTableCell className="whitespace-nowrap font-medium">
                  {formatCurrency(nota.valor)}
                </GlassTableCell>
              </GlassTableRow>
            ))}
          </GlassTable>
        )}

        {activeTab === "empenhos" && (
          empenhos.length > 0 ? (
            <GlassTable
              compact
              headers={["#", "Empenho", "Sit.", "Natureza", "Rec.", "Valor"]}
              headerTitles={["", "Número do Empenho", "Situação", "Natureza da Despesa", "Recurso", "Valor Liquidado"]}
              className="overflow-x-auto"
            >
              {empenhos.map((empenho, index) => {
                // Usa o valor individual extraído do PDF; se ausente, divide o bruto igualmente
                const valorEmpenho = (empenho.valor && empenho.valor > 0)
                  ? empenho.valor
                  : empenhos.length === 1
                    ? resumo.bruto
                    : resumo.bruto / empenhos.length;
                const saldoEmpenho = empenho.saldo ?? 0;
                const totalRef = valorEmpenho + saldoEmpenho;
                // Proporção usada (valor liquidado) em relação ao total do empenho
                const pctUso = totalRef > 0 ? Math.min((valorEmpenho / totalRef) * 100, 100) : 0;
                const temSaldo = totalRef > 0;
                return (
                  <GlassTableRow key={empenho.id}>
                    {/* # */}
                    <GlassTableCell compact className="w-5 text-center text-xs text-muted-foreground">
                      {index + 1}
                    </GlassTableCell>
                    {/* Empenho — tabular nums, não quebra */}
                    <GlassTableCell compact className="whitespace-nowrap font-mono text-xs font-medium">
                      {empenho.numero}
                    </GlassTableCell>
                    {/* Situação */}
                    <GlassTableCell compact className="whitespace-nowrap text-xs">
                      {empenho.situacao}
                    </GlassTableCell>
                    {/* Natureza */}
                    <GlassTableCell compact className="whitespace-nowrap text-xs tabular-nums">
                      {empenho.natureza || "—"}
                    </GlassTableCell>
                    {/* Recurso */}
                    <GlassTableCell compact className="text-center text-xs">
                      {empenho.recurso}
                    </GlassTableCell>
                    {/* Valor + barra */}
                    <GlassTableCell compact className="text-right">
                      <div className="flex flex-col items-end gap-0.5">
                        <span className="whitespace-nowrap text-xs font-semibold tabular-nums text-red-600">
                          {valorEmpenho > 0 ? formatCurrency(valorEmpenho) : "—"}
                        </span>
                        {temSaldo && (
                          <div className="group/bar relative w-full min-w-[60px]">
                            {/* Vermelho = consumido; verde = remanescente */}
                            <div className="h-[3px] w-full overflow-hidden rounded-full bg-emerald-500/45">
                              <div
                                className="h-full rounded-full bg-red-500/75 transition-all"
                                style={{ width: `${pctUso}%` }}
                              />
                            </div>
                            <div className="pointer-events-none absolute bottom-full right-0 z-10 mb-1.5 hidden whitespace-nowrap rounded-md border border-glass-border bg-background/95 px-2 py-1 text-[11px] text-muted-foreground shadow-lg group-hover/bar:block">
                              Consumido: <span className="font-semibold text-red-600">{formatCurrency(valorEmpenho)}</span>
                              {" · "}
                              Remanescente: <span className="font-semibold text-emerald-700">{formatCurrency(saldoEmpenho)}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </GlassTableCell>
                  </GlassTableRow>
                );
              })}
            </GlassTable>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              Nenhum empenho cadastrado
            </div>
          )
        )}

        {activeTab === "pendencias" && (
          <div className="space-y-4">
            {pendenciasExtraContent}
            <PendenciasPanel
              pendencias={pendencias}
              onToggleResolvida={onTogglePendenciaResolvida}
              togglingPendenciaId={pendenciaToggleId}
            />
          </div>
        )}

        {activeTab === "deducoes" && (
          deducoesAgrupadas.length > 0 ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-xl border border-glass-border/70 bg-secondary/25 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
                    Total Deduzido
                  </div>
                  <div className="mt-2 text-lg font-semibold text-foreground">
                    {formatCurrency(deducoes.reduce((acc, item) => acc + item.valor, 0))}
                  </div>
                </div>
                <div className="rounded-xl border border-glass-border/70 bg-secondary/25 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
                    Tipos Visíveis
                  </div>
                  <div className="mt-2 text-lg font-semibold text-foreground">
                    {deducoesAgrupadas.length}
                  </div>
                </div>
                <div className="rounded-xl border border-glass-border/70 bg-secondary/25 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
                    Lançamentos
                  </div>
                  <div className="mt-2 text-lg font-semibold text-foreground">
                    {deducoes.length}
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                {deducoesAgrupadas.map((grupo, index) => {
                  const deducaoPrincipal = grupo.itens[0];
                  const aberto = expandedDeducoes.includes(index + 1);
                  const grupoSiafi = String(deducaoPrincipal?.siafi || "").toUpperCase();
                  const grupoIsISS = grupoSiafi === "DDR001" || grupoSiafi === "DOB001";
                  // Para ISS o "lançamento" é por NF vinculada; para demais é por entrada no PDF
                  const nfsVinculadasGrupo = grupoIsISS
                    ? grupo.itens.reduce((acc, i) => acc + (i.notasFiscaisVinculadas?.length ?? 0), 0)
                    : 0;
                  const qtd = grupoIsISS
                    ? (nfsVinculadasGrupo > 0 ? nfsVinculadasGrupo : grupo.quantidade)
                    : grupo.quantidade;
                  const quantidadeLabel = `${qtd} lançamento${qtd !== 1 ? "s" : ""}`;

                  return (
                    <Collapsible
                      key={grupo.id}
                      open={aberto}
                      onOpenChange={() => alternarDeducao(index + 1)}
                    >
                      <div className="overflow-hidden rounded-2xl border border-glass-border/70 bg-secondary/20">
                        <CollapsibleTrigger asChild>
                          <button className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-secondary/30">
                            <div className="flex w-6 shrink-0 items-center justify-center text-muted-foreground">
                              {aberto ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              {/* Linha 1: título + badges */}
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-sm font-semibold text-foreground">
                                  {index + 1}. {grupo.titulo}
                                </span>
                                {Array.from(grupo.codigos).length > 0 && (
                                  <span className="rounded-md bg-secondary/60 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                                    Cód. {Array.from(grupo.codigos).join(", ")}
                                  </span>
                                )}
                                {(() => {
                                  const temErro = grupo.itens.some((i) => i.status === "erro");
                                  const emExec = grupo.itens.some((i) => i.status === "executando");
                                  const concluido = grupo.itens.every((i) => i.status === "concluido");
                                  return (
                                    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
                                      temErro   ? "bg-red-100 text-red-700"
                                      : emExec  ? "bg-blue-100 text-blue-700"
                                      : concluido ? "bg-green-100 text-green-700"
                                      : "bg-secondary/60 text-muted-foreground"
                                    }`}>
                                      {temErro ? "Erro" : emExec ? "Executando" : concluido ? "Concluído" : "Aguardando"}
                                    </span>
                                  );
                                })()}
                              </div>
                              {/* Linha 2: valores */}
                              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                                <span>
                                  <span className="uppercase tracking-wide">Base </span>
                                  <span className="font-medium text-foreground">{formatCurrency(deducaoPrincipal?.baseCalculo ?? 0)}</span>
                                </span>
                                <span>
                                  <span className="uppercase tracking-wide">Recolhido </span>
                                  <span className="font-semibold text-foreground">{formatCurrency(grupo.valor)}</span>
                                </span>
                                <span>{quantidadeLabel}</span>
                              </div>
                            </div>
                          </button>
                        </CollapsibleTrigger>

                        <CollapsibleContent>
                          <div className="border-t border-glass-border/70">
                            {grupo.itens.map((item, itemIndex) => {
                              const inputKey = `${grupo.id}-${item.id}`;
                              const siafi = String(item.siafi || "").toUpperCase();

                              // ISS municipal (subset sum)
                              const isISS = siafi === "DDR001" || siafi === "DOB001";
                              // Retenção federal proporcional
                              const isProporcional = siafi === "DDF055" || siafi === "DDF050";

                              // ── Distribuição proporcional (DDF055 / DDF050) ──────────────────
                              const distribuicao = isProporcional && notasFiscais.length > 0
                                ? distribuirRetencaoPorNotas(notasFiscais, item.valor)
                                : null;

                              const totalProporcionalEditado = isProporcional && distribuicao
                                ? distribuicao.itens.reduce((acc, { nota, retencao }) => {
                                    const k = `${inputKey}-nf${nota.id}`;
                                    return acc + (parseEditableCurrency(retencoesEditadas[k] ?? formatEditableCurrency(retencao)) ?? retencao);
                                  }, 0)
                                : null;

                              // ── ISS por NF vinculada (DDR001 / DOB001) ───────────────────────
                              // Usa notasFiscais (lista principal) como fonte de valor correto;
                              // nfsVinculadas apenas identifica quais NFs pertencem a este município.
                              const nfsVinculadasRaw = item.notasFiscaisVinculadas ?? [];
                              const issItens = nfsVinculadasRaw.map((nfVinc) => {
                                // Prefere o valor da lista principal (garantidamente em R$)
                                const notaCompleta = notasFiscais.find(
                                  (n) => n.id === nfVinc.id || n.nota === nfVinc.nota
                                );
                                return { nf: nfVinc, valorNf: notaCompleta?.valor ?? nfVinc.valor };
                              });

                              const somaIssBase = issItens.reduce((s, x) => s + x.valorNf, 0);
                              const issItensComRetencao = issItens.map(({ nf, valorNf }) => ({
                                nf,
                                valorNf,
                                retencaoInicial: somaIssBase > 0
                                  ? Number((item.valor * (valorNf / somaIssBase)).toFixed(2))
                                  : 0,
                              }));
                              // Ajuste de centavos no último item
                              if (issItensComRetencao.length > 0) {
                                const soma = issItensComRetencao.reduce((s, x) => s + x.retencaoInicial, 0);
                                const diff = Number((item.valor - soma).toFixed(2));
                                if (diff !== 0) {
                                  issItensComRetencao[issItensComRetencao.length - 1].retencaoInicial =
                                    Number((issItensComRetencao[issItensComRetencao.length - 1].retencaoInicial + diff).toFixed(2));
                                }
                              }

                              const totalIssEditado = isISS && issItensComRetencao.length > 0
                                ? issItensComRetencao.reduce((acc, { nf, retencaoInicial }) => {
                                    const k = `${inputKey}-nf${nf.id}`;
                                    return acc + (parseEditableCurrency(retencoesEditadas[k] ?? formatEditableCurrency(retencaoInicial)) ?? retencaoInicial);
                                  }, 0)
                                : null;

                              // ── Valor do campo "Recolhido" ────────────────────────────────────
                              const temSubNFs =
                                (isProporcional && distribuicao !== null) ||
                                (isISS && issItensComRetencao.length > 0);

                              const totalDerivado = isProporcional
                                ? totalProporcionalEditado
                                : totalIssEditado;

                              const valorEditado = temSubNFs && totalDerivado !== null
                                ? formatEditableCurrency(totalDerivado)
                                : (retencoesEditadas[inputKey] ?? formatEditableCurrency(item.valor));

                              // Para grupos com 1 lançamento, o cabeçalho já mostra código/base/valor.
                              // Mostramos a linha interna só quando há >1 lançamento ou não há sub-NFs.
                              const mostrarLinhaLancamento = grupo.itens.length > 1 || !temSubNFs;

                              // Label da seção de sub-NFs
                              const labelSubNFs = isISS ? "ISS por nota fiscal" : "Retenção por nota fiscal";

                              // Sub-NFs a renderizar
                              const subNFsItems = isProporcional && distribuicao
                                ? distribuicao.itens.map(({ nota, retencao }) => ({
                                    id: nota.id,
                                    label: `NF ${nota.nota || `#${nota.id}`}`,
                                    valorNf: nota.valor,
                                    retencaoInicial: retencao,
                                  }))
                                : issItensComRetencao.map(({ nf, valorNf, retencaoInicial }) => ({
                                    id: nf.id,
                                    label: `NF ${nf.nota || `#${nf.id}`}`,
                                    valorNf,
                                    retencaoInicial,
                                  }));

                              return (
                                <div key={inputKey} className={itemIndex > 0 ? "border-t border-glass-border/50" : ""}>

                                  {/* Linha do lançamento — só aparece quando necessário */}
                                  {mostrarLinhaLancamento && (
                                    <div className="flex items-center gap-3 px-4 py-3">
                                      {grupo.itens.length > 1 && (
                                        <p className="text-xs font-medium text-muted-foreground shrink-0">
                                          Lançamento {itemIndex + 1}
                                        </p>
                                      )}
                                      {/* Base editável */}
                                      <div className="flex shrink-0 items-center gap-1.5">
                                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Base</span>
                                        <span className="text-xs text-muted-foreground">R$</span>
                                        <input
                                          value={basesEditadas[inputKey] ?? formatEditableCurrency(item.baseCalculo || 0)}
                                          onChange={(e) => atualizarBase(inputKey, e.target.value)}
                                          onBlur={() => normalizarBase(inputKey, item.baseCalculo || 0)}
                                          className="h-8 w-[110px] rounded-lg border border-glass-border bg-background px-2.5 text-sm font-medium text-foreground text-right outline-none transition focus:border-primary"
                                          inputMode="decimal"
                                          aria-label={`Base de cálculo do lançamento ${itemIndex + 1}`}
                                        />
                                      </div>
                                      {/* Recolhido */}
                                      <div className="flex shrink-0 items-center gap-1.5 ml-auto">
                                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Recolhido</span>
                                        <span className="text-xs text-muted-foreground">R$</span>
                                        {temSubNFs ? (
                                          <div className="flex h-8 w-[110px] items-center justify-end rounded-lg border border-glass-border/50 bg-secondary/30 px-2.5">
                                            <span className="text-sm font-semibold text-foreground tabular-nums">
                                              {formatEditableCurrency(totalDerivado ?? item.valor)}
                                            </span>
                                          </div>
                                        ) : (
                                          <input
                                            value={valorEditado}
                                            onChange={(e) => atualizarRetencao(inputKey, e.target.value)}
                                            onBlur={() => normalizarRetencao(inputKey, item.valor)}
                                            className="h-8 w-[110px] rounded-lg border border-glass-border bg-background px-2.5 text-sm font-semibold text-foreground text-right outline-none transition focus:border-primary"
                                            inputMode="decimal"
                                            aria-label={`Valor recolhido do lançamento ${itemIndex + 1}`}
                                          />
                                        )}
                                      </div>
                                    </div>
                                  )}

                                  {/* Sub-NFs: ISS por NF ou retenção proporcional */}
                                  {temSubNFs && subNFsItems.length > 0 && (
                                    <div className={`px-4 pb-3 pt-2 space-y-1.5 ${mostrarLinhaLancamento ? "border-t border-glass-border/40" : ""}`}>
                                      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground mb-2">
                                        {labelSubNFs}
                                      </p>
                                      {subNFsItems.map(({ id, label, valorNf, retencaoInicial }) => {
                                        const nfKey = `${inputKey}-nf${id}`;
                                        const nfValorEditado = retencoesEditadas[nfKey] ?? formatEditableCurrency(retencaoInicial);
                                        const nfValorParsed = parseEditableCurrency(nfValorEditado) ?? retencaoInicial;
                                        const percentualNf = valorNf > 0 ? (nfValorParsed / valorNf) * 100 : 0;
                                        return (
                                          <div key={id} className="flex items-center gap-2 rounded-lg border border-glass-border/50 bg-background/40 px-3 py-2">
                                            {/* Badge NF */}
                                            <span className="shrink-0 rounded-md bg-secondary/60 px-2 py-0.5 text-[11px] font-semibold text-foreground">
                                              {label}
                                            </span>
                                            {/* Valor base da NF */}
                                            <span className="flex-1 text-xs tabular-nums text-muted-foreground">
                                              {formatCurrency(valorNf)}
                                            </span>
                                            {/* Percentual como badge sutil */}
                                            <span className="shrink-0 rounded-full bg-secondary/50 px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                                              {formatPercent(percentualNf)}
                                            </span>
                                            {/* Input de retenção */}
                                            <input
                                              value={nfValorEditado}
                                              onChange={(e) => atualizarRetencao(nfKey, e.target.value)}
                                              onBlur={() => normalizarRetencao(nfKey, retencaoInicial)}
                                              className="h-7 w-[88px] shrink-0 rounded-md border border-glass-border bg-background px-2 text-right text-sm font-semibold text-foreground outline-none transition focus:border-primary"
                                              inputMode="decimal"
                                              aria-label={`${labelSubNFs} — ${label}`}
                                            />
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}

                                  {/* ISS sem NFs vinculadas: input direto */}
                                  {isISS && issItensComRetencao.length === 0 && (
                                    <div className="flex items-center gap-3 px-4 py-3">
                                      <p className="flex-1 text-xs text-muted-foreground">
                                        Não foi possível identificar as notas pela base de cálculo — informe manualmente.
                                      </p>
                                      <div className="flex shrink-0 items-center gap-1.5">
                                        <span className="text-xs text-muted-foreground">R$</span>
                                        <input
                                          value={retencoesEditadas[inputKey] ?? formatEditableCurrency(item.valor)}
                                          onChange={(e) => atualizarRetencao(inputKey, e.target.value)}
                                          onBlur={() => normalizarRetencao(inputKey, item.valor)}
                                          className="h-8 w-[110px] rounded-lg border border-glass-border bg-background px-2.5 text-sm font-semibold text-foreground text-right outline-none transition focus:border-primary"
                                          inputMode="decimal"
                                        />
                                      </div>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </CollapsibleContent>
                      </div>
                    </Collapsible>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              Nenhuma dedução disponível para exibir
            </div>
          )
        )}
      </div>
    </GlassCard>
  );
}
