"use client";

import { CheckCircle2 } from "lucide-react";

import { GlassCard } from "@/components/glass-card";
import type { PendenciaDocumento } from "@/lib/data";

interface PendenciasPanelProps {
  pendencias: PendenciaDocumento[];
  onToggleResolvida?: (pendencia: PendenciaDocumento, resolvida: boolean) => void;
  togglingPendenciaId?: string | null;
}

const PRIORIDADE_TIPO: Record<PendenciaDocumento["tipo"], number> = {
  bloqueio: 0,
  divergencia: 1,
  atencao: 2,
};

function itemClass(tipo: PendenciaDocumento["tipo"]) {
  switch (tipo) {
    case "bloqueio":
      return "border-destructive/25 bg-destructive/10";
    case "divergencia":
      return "border-amber-500/25 bg-amber-500/10";
    default:
      return "border-sky-500/20 bg-sky-500/8";
  }
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

function renderPendenciaDescricao(descricao: string) {
  const textoLimpo = descricao
    .replace(/^⚠\s*/, "")
    .replace(/^[^:]+ requer confer[êe]ncia manual:\s*/i, "")
    .trim();

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
        <div className="mt-3 overflow-x-auto rounded-xl border border-sky-500/20 bg-background/55">
          <table className="min-w-[480px] w-full border-separate border-spacing-0 text-left text-xs">
            <thead className="bg-sky-500/10 text-[9px] uppercase tracking-[0.14em] text-sky-800">
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
          <p className="mt-2 text-sm text-muted-foreground">
            Este resumo mostra o que bloqueia, o que diverge e o que merece conferência antes da execução.
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
              {/* Cabeçalho: título + badge + botão na mesma linha */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-foreground">{pendencia.titulo}</p>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.16em] ${badgeClass(pendencia.tipo)}`}
                  >
                    {pendencia.resolvida ? "CONCLUÍDA" : labelTipoPendencia(pendencia.tipo)}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => podeConcluir && onToggleResolvida?.(pendencia, !pendencia.resolvida)}
                  disabled={!podeConcluir}
                  className={`inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl border px-3 text-xs font-semibold transition-all ${
                    pendencia.resolvida
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/15"
                      : "border-sky-500/25 bg-background/80 text-sky-800 shadow-sm hover:-translate-y-0.5 hover:border-sky-500/45 hover:bg-sky-500/10 hover:shadow-md"
                  } ${!podeConcluir ? "cursor-not-allowed opacity-45" : ""} ${estaSalvando ? "ring-2 ring-primary/15" : ""}`}
                  aria-label={pendencia.resolvida ? "Reabrir pendência" : "Concluir pendência"}
                >
                  <CheckCircle2 className="h-4 w-4" />
                  {pendencia.resolvida ? "Concluída" : "Concluir"}
                </button>
              </div>
              {/* Descrição / tabela abaixo, ocupa largura total */}
              {renderPendenciaDescricao(pendencia.descricao)}
            </div>
          )})}
        </div>
      )}
    </GlassCard>
  );
}
