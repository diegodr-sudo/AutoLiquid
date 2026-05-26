"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  Loader2,
  X,
} from "lucide-react";
import { GlassButton, GlassCard } from "./glass-card";

type LogLineType = "header" | "ok" | "run" | "err" | "warn" | "info";

function normalizeLogText(value: string): string {
  return String(value || "")
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
    .replace(/â€"/g, "—")
    .replace(/â€"/g, "–")
    .replace(/â€¢/g, "•")
    .replace(/â†'/g, "→")
    .replace(/âœ"/g, "✓")
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
  if (normalized.startsWith("✓"))  return { type: "ok",   text: normalized.slice(1).trimStart() };
  if (normalized.startsWith("✗"))  return { type: "err",  text: normalized.slice(1).trimStart() };
  if (normalized.startsWith("⚠"))  return { type: "warn", text: normalized.slice(1).trimStart() };
  if (normalized.startsWith("→"))  return { type: "run",  text: normalized.slice(1).trimStart() };
  return { type: "info", text: normalized };
}

function LogRow({ raw, index, finished }: { raw: string; index: number; finished: boolean }) {
  const { type, text } = parseLogLine(raw);

  if (type === "header") {
    return (
      <div className="flex items-center gap-2 pb-1 pt-3 first:pt-0">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-white/30">
          {text}
        </span>
        <span className="h-px flex-1 bg-white/10" />
      </div>
    );
  }

  // "run" lines só giram enquanto o log não terminou; se encerrou com erro ficam estáticos
  const isSpinning = type === "run" && !finished;

  const Icon =
    type === "ok"              ? Check :
    type === "err"             ? X :
    type === "warn"            ? AlertTriangle :
    (type === "run" && !finished) ? Loader2 :
    type === "run"             ? null :   // run encerrado → ponto
                                  null;

  const iconClass =
    type === "ok"   ? "text-emerald-400" :
    type === "err"  ? "text-red-400" :
    type === "warn" ? "text-amber-400" :
    (type === "run" && !finished) ? "text-sky-400" :
    type === "run"  ? "text-white/25" :
                      "text-white/20";

  const textClass =
    type === "err"             ? "text-red-300" :
    type === "warn"            ? "text-amber-300" :
    (type === "run" && !finished) ? "text-sky-300" :
    type === "run"             ? "text-white/40" :   // run encerrado → esmaecido
    type === "ok"              ? "text-emerald-300" :
                                  "text-white/65";

  const lineNum = String(index + 1).padStart(3, " ");

  return (
    <div className="group flex items-start gap-2 rounded-md px-2 py-[3px] transition-colors hover:bg-white/5">
      <span className="mt-[2px] w-6 shrink-0 select-none text-right font-mono text-[10px] text-white/20">
        {lineNum}
      </span>
      <span className="mt-[2px] flex h-3.5 w-3.5 shrink-0 items-center justify-center">
        {Icon ? (
          <Icon
            className={`h-3 w-3 ${iconClass} ${isSpinning ? "animate-spin" : ""}`}
            strokeWidth={type === "ok" ? 2.5 : 2}
          />
        ) : (
          <span className={`h-1 w-1 rounded-full ${type === "run" ? "bg-white/20" : "bg-white/15"}`} />
        )}
      </span>
      <span className={`min-w-0 flex-1 break-words font-mono text-[12px] leading-5 ${textClass}`}>
        {text}
      </span>
    </div>
  );
}

interface LogExecucaoPanelProps {
  logs: string[];
  onLimpar?: () => void;
}

export function LogExecucaoPanel({ logs, onLimpar }: LogExecucaoPanelProps) {
  const [expanded, setExpanded] = useState(false);

  const stats = useMemo(() => {
    let erros = 0;
    let avisos = 0;
    let ultimo: { type: LogLineType; text: string } | null = null;
    for (const raw of logs) {
      const parsed = parseLogLine(raw);
      if (parsed.type === "err")  erros++;
      if (parsed.type === "warn") avisos++;
      if (parsed.type !== "header") ultimo = parsed;
    }
    // Considera encerrado se a última linha relevante é ok ou err
    const finished = ultimo !== null && (ultimo.type === "ok" || ultimo.type === "err");
    return { erros, avisos, ultimo, total: logs.length, finished };
  }, [logs]);

  const statusColor =
    stats.erros > 0   ? "text-red-400" :
    stats.avisos > 0  ? "text-amber-400" :
    stats.total > 0   ? "text-emerald-400" :
                        "text-muted-foreground";

  const StatusIcon =
    stats.erros > 0  ? X :
    stats.avisos > 0 ? AlertTriangle :
    stats.total > 0  ? Check :
                       Code2;

  return (
    <GlassCard className="overflow-hidden">
      {/* ── Header ── */}
      <div className="px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <StatusIcon className={`h-4 w-4 shrink-0 ${statusColor}`} />
          <span className="min-w-0 truncate text-sm font-semibold text-foreground">
            Log de Execução
          </span>

          {stats.erros > 0 && (
            <span className="shrink-0 rounded-full bg-red-500/12 px-2 py-0.5 text-[11px] font-semibold text-red-500 ring-1 ring-inset ring-red-500/20">
              {stats.erros}e
            </span>
          )}
          {stats.avisos > 0 && (
            <span className="shrink-0 rounded-full bg-amber-500/12 px-2 py-0.5 text-[11px] font-semibold text-amber-600 ring-1 ring-inset ring-amber-500/20">
              {stats.avisos}a
            </span>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="whitespace-nowrap rounded-full border border-glass-border bg-background/70 px-2.5 py-0.5 text-xs text-muted-foreground">
            {stats.total} {stats.total === 1 ? "linha" : "linhas"}
          </span>
          {onLimpar && (
            <GlassButton
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 px-2.5 text-xs text-muted-foreground"
              onClick={onLimpar}
              disabled={stats.total === 0}
            >
              Limpar
            </GlassButton>
          )}
          <button
            type="button"
            onClick={() => setExpanded((c) => !c)}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-glass-border bg-background/80 text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            aria-label={expanded ? "Recolher log" : "Expandir log"}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* ── Preview da última mensagem (recolhido) ── */}
      {!expanded && stats.ultimo && (
        <div className="border-t border-glass-border/50 px-4 py-2">
          <p className={`line-clamp-1 font-mono text-xs ${
            stats.ultimo.type === "err"  ? "text-red-500" :
            stats.ultimo.type === "warn" ? "text-amber-600" :
            stats.ultimo.type === "ok"   ? "text-emerald-600" :
                                           "text-muted-foreground"
          }`}>
            {stats.ultimo.text}
          </p>
        </div>
      )}

      {/* ── Log expandido: terminal escuro ── */}
      {expanded && (
        <div className="border-t border-glass-border/50">
          {stats.total === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">
              Nenhum log disponível.
            </p>
          ) : (
            <div className="max-h-96 overflow-y-auto rounded-b-2xl bg-zinc-950/90 px-2 py-2">
              {logs.map((linha, i) => (
                <LogRow key={i} raw={linha} index={i} finished={stats.finished} />
              ))}
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}
