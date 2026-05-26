"use client";

import { useEffect, useRef, useState } from "react";
import { X, TrendingUp, Users, Building2, CheckCircle2, Clock, Award, BarChart3 } from "lucide-react";

// ── Tipos ────────────────────────────────────────────────────────────────────

interface FilaRow {
  responsavel: string;
  valor: string;
  credor: string;
  tipo: string;
  concluido: boolean;
  competencia: string;
  cpfCnpj: string;
}

interface DashboardModalProps {
  open: boolean;
  onClose: () => void;
  rows: FilaRow[];
}

// ── Utilitários ───────────────────────────────────────────────────────────────

function parseValor(v: string): number {
  const n = parseFloat(v.replace(/[R$\s.]/g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

function fmtBRL(n: number): string {
  if (n >= 1_000_000) return `R$ ${(n / 1_000_000).toFixed(1).replace(".", ",")}M`;
  if (n >= 1_000) return `R$ ${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function firstName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts[0] ?? name;
}

const TIPO_COLORS: Record<string, string> = {
  "NF Serviço":  "#8b5cf6",
  "NF Material": "#0ea5e9",
  "Fatura":      "#6366f1",
  "Boleto":      "#f59e0b",
  "Proc. Origem":"#ef4444",
  "Bolsa":       "#14b8a6",
};

function parseTipoSimples(tipo: string): string {
  if (/nf\s*servi/i.test(tipo)) return "NF Serviço";
  if (/nf\s*mat/i.test(tipo)) return "NF Material";
  if (/fatura/i.test(tipo)) return "Fatura";
  if (/boleto/i.test(tipo)) return "Boleto";
  if (/proc.*origem/i.test(tipo)) return "Proc. Origem";
  if (/bolsa/i.test(tipo)) return "Bolsa";
  return tipo || "Outros";
}

// ── Subcomponentes ────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: React.ElementType; label: string; value: string; sub?: string; color: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-glass-border bg-background/60 p-4">
      <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${color}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className="mt-0.5 text-xl font-bold tabular-nums text-foreground">{value}</p>
        {sub && <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>}
      </div>
    </div>
  );
}

function HBar({ label, value, max, color, sub }: {
  label: string; value: number; max: number; color: string; sub?: string;
}) {
  const pct = max > 0 ? Math.max(4, (value / max) * 100) : 4;
  return (
    <div className="group flex items-center gap-3">
      <div className="w-24 shrink-0 truncate text-right text-[11px] text-muted-foreground" title={label}>
        {label}
      </div>
      <div className="relative flex-1 overflow-hidden rounded-full bg-secondary/40" style={{ height: 8 }}>
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <div className="w-28 shrink-0 text-right text-[11px] font-semibold tabular-nums text-foreground">
        {sub ?? fmtBRL(value)}
      </div>
    </div>
  );
}

function TipoDonut({ data }: { data: { label: string; value: number; color: string }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return null;
  let cumulative = 0;
  const size = 80;
  const r = 28;
  const cx = size / 2;
  const cy = size / 2;
  const segments = data.map((d) => {
    const fraction = d.value / total;
    const startAngle = cumulative * 2 * Math.PI - Math.PI / 2;
    cumulative += fraction;
    const endAngle = cumulative * 2 * Math.PI - Math.PI / 2;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const largeArc = fraction > 0.5 ? 1 : 0;
    return { ...d, path: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`, fraction };
  });
  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {segments.map((s) => (
          <path key={s.label} d={s.path} fill={s.color} opacity={0.85} />
        ))}
        <circle cx={cx} cy={cy} r={16} fill="var(--background)" />
        <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle" fontSize={9} fill="var(--muted-foreground)" fontWeight={600}>
          {total}
        </text>
      </svg>
      <div className="flex flex-col gap-1">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-1.5 text-[11px]">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.color }} />
            <span className="text-muted-foreground">{s.label}</span>
            <span className="ml-auto pl-2 font-semibold tabular-nums text-foreground">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────

export function DashboardModal({ open, onClose, rows }: DashboardModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  // Fechar com Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // ── Cálculos (memoizados via useMemo-like pattern) ────────────────────────
  const [computed, setComputed] = useState<ReturnType<typeof computeDashboard> | null>(null);

  useEffect(() => {
    if (open && rows.length > 0) setComputed(computeDashboard(rows));
  }, [open, rows]);

  if (!open) return null;

  const c = computed ?? computeDashboard(rows);

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-blur-sm"
      onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}
    >
      <div className="w-full max-w-3xl rounded-2xl border border-glass-border bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass-border px-6 py-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold text-foreground">Dashboard · Fila de Processos</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard icon={BarChart3} label="Total em fila" value={fmtBRL(c.totalValor)} sub={`${c.total} processos`} color="bg-primary/10 text-primary" />
            <StatCard icon={CheckCircle2} label="Concluídos" value={`${c.pctConcluido}%`} sub={`${c.concluidos} de ${c.total}`} color="bg-emerald-500/10 text-emerald-600" />
            <StatCard icon={Clock} label="Pendentes" value={String(c.pendentes)} sub={fmtBRL(c.valorPendente)} color="bg-amber-500/10 text-amber-600" />
            <StatCard icon={Award} label="Ticket médio" value={fmtBRL(c.ticketMedio)} sub="por processo" color="bg-violet-500/10 text-violet-600" />
          </div>

          {/* Por responsável */}
          <div className="rounded-xl border border-glass-border bg-background/50 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" />
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Valor por Responsável</p>
            </div>
            <div className="space-y-2.5">
              {c.porResponsavel.slice(0, 8).map((r) => (
                <HBar
                  key={r.name}
                  label={firstName(r.name)}
                  value={r.valor}
                  max={c.porResponsavel[0]?.valor ?? 1}
                  color="#6366f1"
                  sub={`${fmtBRL(r.valor)} (${r.count})`}
                />
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Processos por responsável */}
            <div className="rounded-xl border border-glass-border bg-background/50 p-4">
              <div className="mb-3 flex items-center gap-2">
                <Users className="h-4 w-4 text-muted-foreground" />
                <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Processos por Responsável</p>
              </div>
              <div className="space-y-2.5">
                {c.porResponsavel.slice(0, 6).map((r) => (
                  <HBar
                    key={r.name}
                    label={firstName(r.name)}
                    value={r.count}
                    max={c.porResponsavel[0]?.count ?? 1}
                    color="#0ea5e9"
                    sub={`${r.count} proc.`}
                  />
                ))}
              </div>
            </div>

            {/* Distribuição por tipo */}
            <div className="rounded-xl border border-glass-border bg-background/50 p-4">
              <div className="mb-3 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
                <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Distribuição por Tipo</p>
              </div>
              <TipoDonut data={c.porTipo} />
            </div>
          </div>

          {/* Top credores */}
          <div className="rounded-xl border border-glass-border bg-background/50 p-4">
            <div className="mb-3 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Top Credores por Valor</p>
            </div>
            <div className="space-y-2.5">
              {c.topCredores.map((cr, i) => (
                <div key={cr.name} className="flex items-center gap-3">
                  <span className="w-4 shrink-0 text-center text-[10px] font-bold text-muted-foreground/50">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[12px] text-foreground" title={cr.name}>{cr.name}</span>
                      <span className="shrink-0 text-[11px] font-semibold tabular-nums text-foreground">{fmtBRL(cr.valor)}</span>
                    </div>
                    <div className="mt-1 overflow-hidden rounded-full bg-secondary/40" style={{ height: 4 }}>
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${Math.max(4, (cr.valor / (c.topCredores[0]?.valor ?? 1)) * 100)}%`,
                          background: `hsl(${(i * 47) % 360}, 65%, 55%)`,
                        }}
                      />
                    </div>
                  </div>
                  <span className="w-10 shrink-0 text-right text-[10px] text-muted-foreground">{cr.count}×</span>
                </div>
              ))}
            </div>
          </div>

          {/* Minimap competências */}
          {c.porCompetencia.length > 0 && (
            <div className="rounded-xl border border-glass-border bg-background/50 p-4">
              <div className="mb-3 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
                <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Volume por Competência</p>
              </div>
              <div className="flex items-end gap-1" style={{ height: 56 }}>
                {c.porCompetencia.map((comp) => {
                  const pct = c.maxCompValor > 0 ? (comp.valor / c.maxCompValor) * 100 : 0;
                  return (
                    <div key={comp.label} className="group relative flex flex-1 flex-col items-center" style={{ height: "100%" }}>
                      <div className="flex flex-1 items-end w-full">
                        <div
                          className="w-full rounded-t-sm bg-primary/40 transition-all duration-700 group-hover:bg-primary/70"
                          style={{ height: `${Math.max(4, pct)}%` }}
                          title={`${comp.label}: ${fmtBRL(comp.valor)}`}
                        />
                      </div>
                      <span className="mt-1 text-[9px] text-muted-foreground/70 truncate w-full text-center">
                        {comp.label.slice(-5)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Cálculos ──────────────────────────────────────────────────────────────────

function computeDashboard(rows: FilaRow[]) {
  const total = rows.length;
  const concluidos = rows.filter((r) => r.concluido).length;
  const pendentes = total - concluidos;
  const totalValor = rows.reduce((s, r) => s + parseValor(r.valor), 0);
  const valorPendente = rows.filter((r) => !r.concluido).reduce((s, r) => s + parseValor(r.valor), 0);
  const pctConcluido = total > 0 ? Math.round((concluidos / total) * 100) : 0;
  const ticketMedio = total > 0 ? totalValor / total : 0;

  // Por responsável
  const respMap = new Map<string, { valor: number; count: number }>();
  for (const r of rows) {
    const name = r.responsavel || "Sem responsável";
    const cur = respMap.get(name) ?? { valor: 0, count: 0 };
    cur.valor += parseValor(r.valor);
    cur.count += 1;
    respMap.set(name, cur);
  }
  const porResponsavel = [...respMap.entries()]
    .map(([name, d]) => ({ name, ...d }))
    .sort((a, b) => b.valor - a.valor);

  // Por tipo
  const tipoMap = new Map<string, number>();
  for (const r of rows) {
    const tipo = parseTipoSimples(r.tipo);
    tipoMap.set(tipo, (tipoMap.get(tipo) ?? 0) + 1);
  }
  const porTipo = [...tipoMap.entries()]
    .map(([label, value]) => ({ label, value, color: TIPO_COLORS[label] ?? "#94a3b8" }))
    .sort((a, b) => b.value - a.value);

  // Top credores
  const credorMap = new Map<string, { valor: number; count: number }>();
  for (const r of rows) {
    const name = r.credor || "—";
    const cur = credorMap.get(name) ?? { valor: 0, count: 0 };
    cur.valor += parseValor(r.valor);
    cur.count += 1;
    credorMap.set(name, cur);
  }
  const topCredores = [...credorMap.entries()]
    .map(([name, d]) => ({ name, ...d }))
    .sort((a, b) => b.valor - a.valor)
    .slice(0, 8);

  // Por competência
  const compMap = new Map<string, number>();
  for (const r of rows) {
    if (!r.competencia) continue;
    compMap.set(r.competencia, (compMap.get(r.competencia) ?? 0) + parseValor(r.valor));
  }
  const porCompetencia = [...compMap.entries()]
    .map(([label, valor]) => ({ label, valor }))
    .sort((a, b) => a.label.localeCompare(b.label))
    .slice(-12);
  const maxCompValor = Math.max(...porCompetencia.map((c) => c.valor), 1);

  return {
    total, concluidos, pendentes, totalValor, valorPendente,
    pctConcluido, ticketMedio, porResponsavel, porTipo, topCredores,
    porCompetencia, maxCompValor,
  };
}
