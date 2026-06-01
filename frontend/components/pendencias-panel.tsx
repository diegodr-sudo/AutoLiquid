"use client";

import { CheckCircle2, ExternalLink, Loader2 } from "lucide-react";
import { useState } from "react";
import { SimpleTooltip } from "@/components/ui/simple-tooltip";

import { GlassCard } from "@/components/glass-card";
import type { PendenciaDocumento } from "@/lib/data";

interface PendenciasPanelProps {
  pendencias: PendenciaDocumento[];
  onToggleResolvida?: (pendencia: PendenciaDocumento, resolvida: boolean) => void;
  togglingPendenciaId?: string | null;
}

const API = "http://127.0.0.1:8000";

interface PortalConfigLF { id: string; nome: string; codigo?: string }

function extrairCodigosMunicipais(descricao: string): string[] {
  const m = descricao.match(/Códigos municipais:\s*([0-9, ]+)\./i);
  if (!m) return [];
  return m[1].split(",").map((c) => c.trim()).filter(Boolean);
}

function PortaisLFPendencia({ descricao }: { descricao: string }) {
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  const [portaisConfig, setPortaisConfig] = useState<PortalConfigLF[]>([]);

  // Carrega portais do backend (uma vez por montagem)
  useState(() => {
    fetch(`${API}/api/iss/portais`)
      .then((r) => r.json())
      .then((d) => setPortaisConfig((d.portais ?? []) as PortalConfigLF[]))
      .catch(() => {});
  });

  const codigos = extrairCodigosMunicipais(descricao);
  const portais = portaisConfig.filter(
    (p) => p.codigo && codigos.includes(p.codigo)
  );

  if (portais.length === 0) return null;

  const handleAbrir = async (portalId: string) => {
    setAbrindo(portalId);
    setErro("");
    try {
      const res = await fetch(`${API}/api/iss/abrir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portal: portalId }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error((data as { detail?: string }).detail || "Não foi possível abrir o portal.");
      }
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível abrir o portal.");
    } finally {
      setAbrindo(null);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {portais.map(({ id, nome }) => (
        <SimpleTooltip
          key={id}
          content={`Abrir portal ISS de ${nome} — login automático será aplicado`}
          side="top"
        >
          <button
            type="button"
            onClick={() => void handleAbrir(id)}
            disabled={Boolean(abrindo)}
            className="flex items-center gap-1.5 rounded-xl border border-glass-border bg-background/60 px-3 py-2 text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary disabled:opacity-60"
          >
            {abrindo === id ? (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
            ) : (
              <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            {nome}
          </button>
        </SimpleTooltip>
      ))}
      {erro && (
        <p className="mt-2 w-full rounded-xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {erro}
        </p>
      )}
    </div>
  );
}

const PRIORIDADE_TIPO: Record<PendenciaDocumento["tipo"], number> = {
  bloqueio: 0,
  divergencia: 1,
  atencao: 2,
};

function itemClass(_tipo: PendenciaDocumento["tipo"]) {
  // Cartões neutros — a cor fica apenas na tag de tipo (BLOQUEIO/DIVERGÊNCIA/ATENÇÃO).
  return "border-glass-border bg-background/55";
}

function badgeClass(tipo: PendenciaDocumento["tipo"]) {
  switch (tipo) {
    case "bloqueio":
      return "border-destructive/25 bg-destructive/10 text-destructive";
    case "divergencia":
      return "border-amber-500/25 bg-amber-500/10 text-amber-700";
    default:
      return "border-sky-500/20 bg-sky-500/10 text-sky-700";
  }
}

function labelTipoPendencia(tipo: PendenciaDocumento["tipo"]) {
  if (tipo === "bloqueio") return "BLOQUEIO";
  if (tipo === "divergencia") return "DIVERGÊNCIA";
  return "ATENÇÃO";
}

type DivRow = { label: string; pdf: string | null; ic: string | null; type: "match" | "diff" | "pdf_only" | "ic_only" };

function formatBRL(valor: string | null | undefined): string | null {
  if (!valor) return null;
  // Aceita "1417.10", "51683.15", "4.250,00", etc.
  const limpo = valor.replace(/[^\d.,]/g, "");
  if (!limpo) return null;
  let num: number;
  if (limpo.includes(",")) {
    num = parseFloat(limpo.replace(/\./g, "").replace(",", "."));
  } else {
    num = parseFloat(limpo);
  }
  if (isNaN(num)) return valor;
  return `R$ ${num.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Paleta única (tons amenos) compartilhada pelas tabelas de conferência —
// dados básicos e principal com orçamento — para manter o mesmo padrão.
const DIV_STATUS_CONFIG: Record<DivRow["type"], { rowCls: string; badgeCls: string; label: string }> = {
  match:    { rowCls: "bg-emerald-500/[0.05]", badgeCls: "border border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300", label: "✓ Igual" },
  diff:     { rowCls: "bg-rose-500/[0.05]",    badgeCls: "border border-rose-400/30 bg-rose-500/10 text-rose-600 dark:text-rose-300",          label: "✗ Divergente" },
  pdf_only: { rowCls: "bg-amber-500/[0.05]",   badgeCls: "border border-amber-400/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",      label: "⚠ Ausente no IC" },
  ic_only:  { rowCls: "bg-violet-500/[0.05]",  badgeCls: "border border-violet-400/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",  label: "⚠ Exclusiva no IC" },
};

function DivergenciaTabela({ rows, titulo }: { rows: DivRow[]; titulo: string }) {
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-glass-border bg-background/55">
      <table className="w-full border-separate border-spacing-0 text-left text-xs">
        <thead className="bg-muted/40 text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
          <tr>
            <th className="w-px whitespace-nowrap px-2.5 py-2 font-semibold">{titulo}</th>
            <th className="whitespace-nowrap px-2.5 py-2 font-semibold text-center">PDF</th>
            <th className="whitespace-nowrap px-2.5 py-2 font-semibold text-center">IC</th>
            <th className="whitespace-nowrap px-2.5 py-2 font-semibold text-center">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const cfg = DIV_STATUS_CONFIG[row.type];
            return (
              <tr key={i} className={cfg.rowCls}>
                <td className="w-px whitespace-nowrap px-2.5 py-2 font-medium text-foreground/90">{row.label}</td>
                <td className="whitespace-nowrap px-2.5 py-2 font-mono text-[11px] text-center text-muted-foreground">
                  {row.pdf ?? <span className="opacity-40">—</span>}
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 font-mono text-[11px] text-center text-muted-foreground">
                  {row.ic ?? <span className="opacity-40">—</span>}
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 text-center">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${cfg.badgeCls}`}>
                    {cfg.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function renderDivergenciaDadosBasicos(linhas: string[]) {
  const rows: DivRow[] = [];

  for (const linha of linhas) {
    // Código do Credor: Web=XXX | PDF=YYY
    const mCredor = linha.match(/^Código do Credor:\s*Web=([^\s|]+)\s*\|\s*PDF=([^\s.|]+)\.?$/i);
    if (mCredor) {
      rows.push({ label: "CNPJ", pdf: mCredor[2], ic: mCredor[1], type: "diff" });
      continue;
    }
    // Ateste: Web=X | PDF=Y
    const mAteste = linha.match(/^Ateste:\s*Web=([^\s|]+)\s*\|\s*PDF=([^\s.|]+)\.?$/i);
    if (mAteste) {
      rows.push({ label: "Ateste", pdf: mAteste[2], ic: mAteste[1], type: "diff" });
      continue;
    }
    // NF(s) ausente(s) nos documentos de origem da Web: 6919=4250.00, 1234=8100.50
    const mAusente = linha.match(/^NF\(s\) ausente\(s\) nos documentos de origem da Web:\s*(.+)/i);
    if (mAusente) {
      for (const part of mAusente[1].split(/,\s*/)) {
        const [nf, val] = part.trim().split("=");
        if (nf) rows.push({ label: `NF ${nf.trim()}`, pdf: formatBRL(val) ?? "presente", ic: null, type: "pdf_only" });
      }
      continue;
    }
    // NF(s) inesperada(s) nos documentos de origem da Web: 1314=990.00, 5678=780.00
    const mInesperada = linha.match(/^NF\(s\) inesperada\(s\) nos documentos de origem da Web:\s*(.+)/i);
    if (mInesperada) {
      for (const part of mInesperada[1].split(/,\s*/)) {
        const [nf, val] = part.trim().split("=");
        if (nf) rows.push({ label: `NF ${nf.trim()}`, pdf: null, ic: formatBRL(val) ?? "presente", type: "ic_only" });
      }
      continue;
    }
    // NF XXXX — Emissão: Web=YY | PDF=ZZ
    const mNFEmissao = linha.match(/^NF\s+(\S+)\s+—\s+Emiss[aã]o:\s*Web=([^\s|]+)\s*\|\s*PDF=([^\s.|]+)\.?$/i);
    if (mNFEmissao) {
      rows.push({ label: `NF ${mNFEmissao[1]} — Emissão`, pdf: mNFEmissao[3], ic: mNFEmissao[2], type: "diff" });
      continue;
    }
    // NF XXXX — Valor: Web=X | PDF=Y
    const mNFValor = linha.match(/^NF\s+(\S+)\s+—\s+Valor:\s*Web=([^\s|]+)\s*\|\s*PDF=([^\s.|]+)\.?$/i);
    if (mNFValor) {
      rows.push({ label: `NF ${mNFValor[1]} — Valor`, pdf: formatBRL(mNFValor[3]), ic: formatBRL(mNFValor[2]), type: "diff" });
      continue;
    }
    // Valor total dos documentos de origem divergente: Web=1417.10 | PDF=51683.15.
    const mValorTotal = linha.match(/^Valor total dos documentos de origem divergente:\s*Web=([\d.]+)\s*\|\s*PDF=([\d.]+)\.?$/i);
    if (mValorTotal) {
      rows.push({ label: "Valor total", pdf: formatBRL(mValorTotal[2]), ic: formatBRL(mValorTotal[1]), type: "diff" });
      continue;
    }
    // Quantidade de documentos de origem divergente: Web=X | PDF=Y
    const mQtd = linha.match(/^Quantidade de documentos de origem divergente:\s*Web=(\d+)\s*\|\s*PDF=(\d+)\.?$/i);
    if (mQtd) {
      rows.push({ label: "Quantidade de NFs", pdf: mQtd[2], ic: mQtd[1], type: "diff" });
      continue;
    }
  }

  if (rows.length === 0) return null;
  return <DivergenciaTabela rows={rows} titulo="Item" />;
}

function parseNum(valor: string | null | undefined): number | null {
  if (!valor) return null;
  const limpo = valor.replace(/[^\d.,]/g, "");
  if (!limpo) return null;
  const num = limpo.includes(",")
    ? parseFloat(limpo.replace(/\./g, "").replace(",", "."))
    : parseFloat(limpo);
  return isNaN(num) ? null : num;
}

function renderDivergenciaEmpenhos(linhas: string[]) {
  const rows: DivRow[] = [];

  for (const linha of linhas) {
    // Empenho 2026NE000136 — Valor: Web=149.40 | PDF=51683.15
    const mValor = linha.match(/^Empenho\s+(\S+)\s+—\s+Valor:\s*Web=([^|]+?)\s*\|\s*PDF=([^|]+?)\.?$/i);
    if (mValor) {
      const ic = mValor[2].trim();
      const pdf = mValor[3].trim();
      const nIc = parseNum(ic);
      const nPdf = parseNum(pdf);
      const igual = nIc !== null && nPdf !== null && Math.abs(nIc - nPdf) < 0.005;
      rows.push({
        label: mValor[1],
        pdf: formatBRL(pdf),
        ic: formatBRL(ic),
        type: igual ? "match" : "diff",
      });
      continue;
    }
    // Empenho ausente no IC: 2026NE000136=51683.15
    const mAusente = linha.match(/^Empenho ausente no IC:\s*(\S+?)=(.+?)\.?$/i);
    if (mAusente) {
      rows.push({ label: mAusente[1], pdf: formatBRL(mAusente[2]) ?? "presente", ic: null, type: "pdf_only" });
      continue;
    }
    // Empenho exclusivo no IC: 2022NE002642=149.40
    const mExclusivo = linha.match(/^Empenho exclusivo no IC:\s*(\S+?)=(.+?)\.?$/i);
    if (mExclusivo) {
      rows.push({ label: mExclusivo[1], pdf: null, ic: formatBRL(mExclusivo[2]) ?? "presente", type: "ic_only" });
      continue;
    }
  }

  if (rows.length === 0) return null;
  return <DivergenciaTabela rows={rows} titulo="Empenho" />;
}

function renderPendenciaDescricao(descricao: string) {
  const textoLimpo = descricao
    .replace(/^⚠\s*/, "")
    .replace(/^[^:]+ requer confer[êe]ncia manual:\s*/i, "")
    .replace(/\s*Códigos municipais:\s*[0-9, ]+\./i, "")
    .trim();

  // ── Divergência Principal com Orçamento (tabela de empenhos PDF × IC) ────
  const linhasDivergencia = textoLimpo.split("\n").map((l) => l.trim()).filter(Boolean);
  const ehDivergenciaEmpenhos = linhasDivergencia.some((l) =>
    /^Empenho\b.*(Web=.*\|\s*PDF=|ausente no IC|exclusivo no IC)/i.test(l)
  );
  if (ehDivergenciaEmpenhos) {
    const tabela = renderDivergenciaEmpenhos(linhasDivergencia);
    if (tabela) return tabela;
  }

  // ── Divergência Dados Básicos (tabela PDF × IC) ──────────────────────────
  const ehDivergenciaDadosBasicos = linhasDivergencia.some((l) =>
    /(Web=.*\|\s*PDF=|ausente\(s\) nos documentos|inesperada\(s\) nos documentos)/i.test(l)
  );
  if (ehDivergenciaDadosBasicos) {
    const tabela = renderDivergenciaDadosBasicos(linhasDivergencia);
    if (tabela) return tabela;
  }

  if (/Outros Lançamentos|Situação:\s*IMB050/i.test(textoLimpo)) {
    const segmentos = Array.from(
      textoLimpo.matchAll(/([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .()/-]+):\s*([^:]+?)(?=(?:\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .()/-]+:)|$)/g)
    );
    if (segmentos.length > 0) {
      const valorPorLabel = new Map(
        segmentos.map((segmento) => [
          segmento[1].trim().toLowerCase(),
          segmento[2].replace(/\.$/, "").trim(),
        ])
      );
      const situacao = valorPorLabel.get("situação") || "IMB050";
      const subitem = valorPorLabel.get("subitem") || valorPorLabel.get("subitem da despesa") || "—";
      const bensUso = valorPorLabel.get("bens móveis em uso") || "—";
      const bensAlmox = valorPorLabel.get("bens móveis em almoxarifado") || "—";
      const valor = valorPorLabel.get("valor") || "—";

      return (
        <div className="mt-3 overflow-x-auto rounded-xl border border-glass-border bg-background/55">
          <table className="min-w-[480px] w-full border-separate border-spacing-0 text-left text-xs">
            <thead className="bg-muted/40 text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
              <tr>
                <th className="whitespace-nowrap px-3 py-2 font-semibold">Situação (IMB050)</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold">Subitem</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold">Bens móveis em uso</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold">Bens móveis em almoxarifado</th>
                <th className="whitespace-nowrap px-3 py-2 font-semibold">Valor</th>
              </tr>
            </thead>
            <tbody className="text-muted-foreground">
              <tr>
                <td className="whitespace-nowrap px-3 py-3 font-medium text-foreground">{situacao}</td>
                <td className="whitespace-nowrap px-3 py-3">{subitem}</td>
                <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px]">{bensUso}</td>
                <td className="whitespace-nowrap px-3 py-3 font-mono text-[11px]">{bensAlmox}</td>
                <td className="whitespace-nowrap px-3 py-3 text-[11px] font-semibold tabular-nums text-foreground">{valor}</td>
              </tr>
            </tbody>
          </table>
        </div>
      );
    }
  }

  const segmentos = Array.from(
    textoLimpo.matchAll(/([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .()/-]+:)\s*([^:]+?)(?=(?:\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .()/-]+:)|$)/g)
  );

  if (segmentos.length === 0) {
    return <p className="mt-2 text-sm leading-6 text-muted-foreground">{descricao}</p>;
  }

  return (
    <div className="mt-2 space-y-1.5">
      {segmentos.map((segmento, index) => (
        <p key={`${segmento[1]}-${index}`} className="text-sm leading-6 text-muted-foreground">
          <strong className="font-semibold text-foreground">{segmento[1]}</strong>{" "}
          {segmento[2].trim()}
        </p>
      ))}
    </div>
  );
}

export function PendenciasPanel({
  pendencias,
  onToggleResolvida,
  togglingPendenciaId,
}: PendenciasPanelProps) {
  const pendenciasOrdenadas = [...pendencias].sort((a, b) => {
    const resolvidaA = a.resolvida ? 1 : 0;
    const resolvidaB = b.resolvida ? 1 : 0;
    if (resolvidaA !== resolvidaB) return resolvidaA - resolvidaB;

    const prioridadeA = PRIORIDADE_TIPO[a.tipo] ?? 3;
    const prioridadeB = PRIORIDADE_TIPO[b.tipo] ?? 3;
    if (prioridadeA !== prioridadeB) return prioridadeA - prioridadeB;

    return a.titulo.localeCompare(b.titulo, "pt-BR");
  });
  const totalPendentes = pendencias.filter((pendencia) => !pendencia.resolvida).length;

  return (
    <GlassCard className="p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Pendências e Divergências
          </p>
        </div>
        <span className="inline-flex w-fit shrink-0 self-start whitespace-nowrap rounded-full border border-glass-border bg-background/70 px-3 py-1 text-xs font-medium text-muted-foreground">
          {totalPendentes} pendente(s)
        </span>
      </div>

      {pendencias.length === 0 ? (
        <div className="mt-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-4 text-sm text-emerald-700">
          Nenhuma pendência relevante foi detectada até aqui. O documento está em condição boa para seguir.
        </div>
      ) : (
        <div className="mt-5 space-y-3">
          {pendenciasOrdenadas.map((pendencia) => {
            const podeConcluir = Boolean(onToggleResolvida) && !pendencia.id.startsWith("local-");
            const estaSalvando = togglingPendenciaId === pendencia.id;
            return (
            <div
              key={pendencia.id}
              className={`rounded-2xl border px-4 py-4 ${itemClass(pendencia.tipo)} ${pendencia.resolvida ? "opacity-70" : ""}`}
            >
              {/* Cabeçalho: título à esquerda; tag + botão fixos no topo à direita */}
              <div className="flex items-start justify-between gap-3">
                <p className="min-w-0 flex-1 pt-1 text-sm font-semibold text-foreground">{pendencia.titulo}</p>
                <div className="flex shrink-0 items-center gap-2">
                  <span
                    className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.16em] ${badgeClass(pendencia.tipo)}`}
                  >
                    {pendencia.resolvida ? "CONCLUÍDA" : labelTipoPendencia(pendencia.tipo)}
                  </span>
                  <button
                    type="button"
                    onClick={() => podeConcluir && !estaSalvando && onToggleResolvida?.(pendencia, !pendencia.resolvida)}
                    disabled={!podeConcluir || estaSalvando}
                    className={`inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl border px-3 text-xs font-semibold transition-all ${
                      pendencia.resolvida
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/15"
                        : "border-sky-500/25 bg-background/80 text-sky-800 shadow-sm hover:-translate-y-0.5 hover:border-sky-500/45 hover:bg-sky-500/10 hover:shadow-md"
                    } ${!podeConcluir || estaSalvando ? "cursor-not-allowed opacity-45" : ""} ${estaSalvando ? "ring-2 ring-primary/15" : ""}`}
                    aria-label={pendencia.resolvida ? "Reabrir pendência" : "Concluir pendência"}
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    {estaSalvando ? "Salvando…" : pendencia.resolvida ? "Concluída" : "Concluir"}
                  </button>
                </div>
              </div>
              {/* Descrição / tabela abaixo, ocupa largura total */}
              {renderPendenciaDescricao(
                pendencia.descricao.replace(/\s*Códigos municipais:\s*[0-9, ]+\.?/i, "").trim()
              )}
              {/* Atalho portal ISS para pendência de LF (usa descricao original para extrair códigos) */}
              {pendencia.titulo === "LF obrigatória para a OB" && (
                <PortaisLFPendencia descricao={pendencia.descricao} />
              )}
            </div>
          )})}
        </div>
      )}
    </GlassCard>
  );
}
