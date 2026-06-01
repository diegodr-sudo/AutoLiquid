"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Building2,
  CalendarDays,
  FileText,
  RefreshCw,
  Search,
  TrendingUp,
  X,
  type LucideIcon,
} from "lucide-react";
import { fetchDashboardHistorico, type HistoricoDashboardData } from "@/lib/data";
import { SimpleTooltip } from "@/components/ui/simple-tooltip";

function fmtBRL(value: number): string {
  return value.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: value >= 1_000_000 ? 1 : 2,
  });
}

function fmtCompactBRL(value: number): string {
  if (value >= 1_000_000) return `R$ ${(value / 1_000_000).toFixed(2).replace(".", ",")} mi`;
  if (value >= 1_000) return `R$ ${(value / 1_000).toFixed(1).replace(".", ",")} mil`;
  return fmtBRL(value);
}

function fmtMes(mes: string): string {
  const [year, month] = mes.split("-");
  const names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  return `${names[Number(month) - 1] ?? month}/${year?.slice(2) ?? ""}`;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="min-w-[180px] flex-1">
      <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <span className="relative block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/45" />
        <input
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="h-10 w-full rounded-xl border border-glass-border bg-background/80 pl-9 pr-9 text-sm text-foreground outline-none transition focus:border-primary/45 focus:ring-2 focus:ring-primary/15"
        />
        {value ? (
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground/55 transition hover:bg-secondary hover:text-foreground"
            aria-label={`Limpar ${label}`}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </span>
    </label>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = "neutral",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail?: string;
  tone?: "neutral" | "blue" | "green" | "amber";
}) {
  const toneClass = {
    neutral: "border-glass-border bg-background/72 text-foreground",
    blue: "border-sky-500/18 bg-sky-500/[0.06] text-sky-700",
    green: "border-emerald-500/18 bg-emerald-500/[0.07] text-emerald-700",
    amber: "border-amber-500/18 bg-amber-500/[0.07] text-amber-700",
  }[tone];

  return (
    <div className={cx("rounded-2xl border p-4 shadow-sm", toneClass)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {label}
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
            {value}
          </p>
          {detail ? <p className="mt-1 text-xs text-muted-foreground">{detail}</p> : null}
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-current/10 bg-background/70">
          <Icon className="h-4 w-4" />
        </span>
      </div>
    </div>
  );
}

function DistributionList({
  title,
  subtitle,
  icon: Icon,
  items,
  max,
  empty,
}: {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  items: Array<{ key: string; label: string; value: number; count: number; helper?: string }>;
  max: number;
  empty: string;
}) {
  return (
    <section className="rounded-2xl border border-glass-border bg-background/72 p-4 shadow-sm">
      <div className="mb-4 flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-glass-border bg-secondary/45 text-primary">
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
        </div>
      </div>

      {items.length ? (
        <div className="space-y-3">
          {items.map((item) => {
            const pct = max > 0 ? Math.max(3, (item.value / max) * 100) : 3;
            return (
              <div key={item.key} className="group">
                <div className="mb-1.5 flex items-baseline justify-between gap-3">
                  <div className="min-w-0">
                    <SimpleTooltip content={item.label} side="top" className="text-left">
                      <p className="truncate text-sm font-medium text-foreground">
                        {item.label || "Sem identificação"}
                      </p>
                    </SimpleTooltip>
                    <p className="text-[11px] text-muted-foreground">
                      {item.count} processo(s){item.helper ? ` · ${item.helper}` : ""}
                    </p>
                  </div>
                  <p className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
                    {fmtCompactBRL(item.value)}
                  </p>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary/45">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-slate-700 via-slate-500 to-slate-400 transition-all duration-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-glass-border bg-secondary/20 px-4 py-8 text-center text-sm text-muted-foreground">
          {empty}
        </div>
      )}
    </section>
  );
}

function MonthlyBars({ data }: { data: HistoricoDashboardData["porMes"] }) {
  if (data.length < 2) return null;
  const max = Math.max(...data.map((item) => item.valor), 1);

  return (
    <section className="rounded-2xl border border-glass-border bg-background/72 p-4 shadow-sm">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-glass-border bg-secondary/45 text-primary">
            <BarChart3 className="h-4 w-4" />
          </span>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Evolução mensal</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Consulta por competência de execução registrada no histórico.
            </p>
          </div>
        </div>
        <p className="rounded-full border border-glass-border bg-secondary/30 px-3 py-1 text-xs text-muted-foreground">
          Média: {fmtCompactBRL(data.reduce((sum, item) => sum + item.valor, 0) / data.length)}
        </p>
      </div>

      <div className="flex h-44 items-end gap-2 overflow-x-auto pb-1">
        {data.map((item) => {
          const height = Math.max(8, (item.valor / max) * 100);
          return (
            <div key={item.mes} className="flex min-w-12 flex-1 flex-col items-center gap-2">
              <div className="flex h-32 w-full items-end rounded-xl bg-secondary/28 px-1.5">
                <SimpleTooltip content={`${fmtMes(item.mes)} · ${fmtBRL(item.valor)} · ${item.count} processo(s)`} side="top">
                  <div
                    className="w-full rounded-t-lg bg-gradient-to-t from-primary/75 to-primary/35 transition-all duration-500 hover:from-primary hover:to-primary/55"
                    style={{ height: `${height}%` }}
                  />
                </SimpleTooltip>
              </div>
              <span className="text-[10px] text-muted-foreground">{fmtMes(item.mes)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

const PERIODOS = [
  { key: "semana", label: "Esta semana" },
  { key: "mes", label: "30 dias" },
  { key: "trimestre", label: "90 dias" },
  { key: "semestre", label: "6 meses" },
  { key: "ano", label: "Ano" },
  { key: "tudo", label: "Tudo" },
];

export function DashboardHistorico({ visible }: { visible: boolean }) {
  const [empresa, setEmpresa] = useState("");
  const [contrato, setContrato] = useState("");
  const [servidor, setServidor] = useState("");
  const [periodo, setPeriodo] = useState("semana");
  const [data, setData] = useState<HistoricoDashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const buscar = useCallback((emp: string, cont: string, serv: string, per: string) => {
    setLoading(true);
    setErro("");
    fetchDashboardHistorico({ empresa: emp, contrato: cont, servidor: serv, periodo: per })
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((error) => {
        setErro(error instanceof Error ? error.message : "Erro ao carregar o dashboard.");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (visible && !data && !loading) buscar(empresa, contrato, servidor, periodo);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => buscar(empresa, contrato, servidor, periodo), 450);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresa, contrato, servidor, periodo]);

  const hasActiveFilter = Boolean(empresa || contrato || servidor);
  const periodLabel = PERIODOS.find((item) => item.key === periodo)?.label ?? "Todos";

  const prepared = useMemo(() => {
    if (!data) return null;
    const contratos = data.porContrato.filter((item) => item.contrato !== "(sem contrato)");
    const maxEmpresa = Math.max(...data.porEmpresa.map((item) => item.valor), 1);
    const maxContrato = Math.max(...contratos.map((item) => item.valor), 1);

    return {
      contratos,
      maxEmpresa,
      maxContrato,
      mediaProcesso: data.total > 0 ? data.totalValor / data.total : 0,
      maiorMes: data.porMes.length ? Math.max(...data.porMes.map((item) => item.valor)) : 0,
    };
  }, [data]);

  if (!visible) return null;

  return (
    <div className="space-y-5 pb-8">
      <section className="overflow-hidden rounded-[26px] border border-glass-border bg-[linear-gradient(135deg,rgba(248,250,252,0.92),rgba(241,245,249,0.72))] p-5 shadow-sm">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">
              Histórico
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
              Consulta de valores liquidados
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Use os filtros para conferir montantes por fornecedor, contrato ou servidor, sem gerar nova tabela.
            </p>
          </div>
          <button
            type="button"
            onClick={() => buscar(empresa, contrato, servidor, periodo)}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-glass-border bg-background/80 px-3.5 py-2 text-sm font-medium text-foreground shadow-sm transition hover:border-primary/30 hover:text-primary disabled:opacity-55"
          >
            <RefreshCw className={cx("h-4 w-4", loading && "animate-spin")} />
            Atualizar
          </button>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <FilterInput label="Fornecedor" value={empresa} onChange={setEmpresa} placeholder="Nome do fornecedor" />
          <FilterInput label="Contrato" value={contrato} onChange={setContrato} placeholder="Número do contrato" />
          <FilterInput label="Servidor" value={servidor} onChange={setServidor} placeholder="Nome do servidor" />

          <div className="max-w-full">
            <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Período
            </span>
            <div className="inline-flex max-w-full flex-wrap gap-1.5 rounded-2xl border border-glass-border bg-background/60 p-1.5 shadow-inner">
              {PERIODOS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setPeriodo(item.key)}
                  className={cx(
                    "h-8 shrink-0 rounded-xl px-3 text-xs font-semibold transition",
                    periodo === item.key
                      ? "bg-foreground text-background shadow-sm"
                      : "text-muted-foreground hover:bg-secondary/70 hover:text-foreground"
                  )}
                  aria-pressed={periodo === item.key}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {hasActiveFilter ? (
            <button
              type="button"
              onClick={() => {
                setEmpresa("");
                setContrato("");
                setServidor("");
              }}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-glass-border bg-background/55 px-3 text-sm text-muted-foreground transition hover:bg-background hover:text-foreground"
            >
              <X className="h-4 w-4" />
              Limpar
            </button>
          ) : null}
        </div>
      </section>

      {erro ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {erro}
        </div>
      ) : null}

      {loading && !data ? (
        <div className="flex items-center justify-center rounded-2xl border border-glass-border bg-background/60 py-20 text-sm text-muted-foreground">
          <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
          Consultando histórico...
        </div>
      ) : null}

      {data && data.total === 0 ? (
        <div className="rounded-2xl border border-dashed border-glass-border bg-background/60 py-16 text-center text-sm text-muted-foreground">
          <Search className="mx-auto mb-3 h-9 w-9 opacity-25" />
          Nenhum valor encontrado para os filtros aplicados.
        </div>
      ) : null}

      {data && prepared && data.total > 0 ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={TrendingUp}
              label="Valor localizado"
              value={fmtCompactBRL(data.totalValor)}
              detail={fmtBRL(data.totalValor)}
              tone="blue"
            />
            <MetricCard
              icon={FileText}
              label="Processos"
              value={String(data.total)}
              detail={`Média ${fmtCompactBRL(prepared.mediaProcesso)} por processo`}
              tone="green"
            />
            <MetricCard
              icon={CalendarDays}
              label="Recorte"
              value={periodLabel}
              detail={hasActiveFilter ? "Filtros ativos" : "Sem filtros adicionais"}
              tone="neutral"
            />
            <MetricCard
              icon={BarChart3}
              label="Maior mês"
              value={prepared.maiorMes ? fmtCompactBRL(prepared.maiorMes) : "—"}
              detail={data.porMes.length ? `${data.porMes.length} mês(es) no gráfico` : "Sem série mensal"}
              tone="amber"
            />
          </div>

          <MonthlyBars data={data.porMes} />

          <div className="grid gap-4 xl:grid-cols-2">
            <DistributionList
              title="Por contrato"
              subtitle="Valores agregados por contrato informado."
              icon={FileText}
              max={prepared.maxContrato}
              empty="Nenhum contrato informado no recorte."
              items={prepared.contratos.map((item, index) => ({
                key: `${item.contrato}-${index}`,
                label: item.contrato,
                value: item.valor,
                count: item.count,
              }))}
            />
            <DistributionList
              title="Por fornecedor"
              subtitle="Fornecedores com maior valor liquidado."
              icon={Building2}
              max={prepared.maxEmpresa}
              empty="Sem fornecedor para exibir."
              items={data.porEmpresa.map((item, index) => ({
                key: `${item.cnpj || item.nome || "fornecedor"}-${index}`,
                label: item.nome,
                helper: item.cnpj,
                value: item.valor,
                count: item.count,
              }))}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
