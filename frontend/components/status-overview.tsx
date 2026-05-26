"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CalendarDays,
  Landmark,
  Loader2,
  Receipt,
  ShieldAlert,
  Wallet,
} from "lucide-react";

import { GlassCard } from "@/components/glass-card";
import type { ResumoFinanceiro, StatusGeralDocumento } from "@/lib/data";
import Link from "next/link";
import { GlassButton } from "@/components/glass-card";

interface StatusOverviewProps {
  statusGeral: StatusGeralDocumento;
  resumo: ResumoFinanceiro;
  optanteSimples: boolean;
  hasDdf055: boolean;
  apuracaoDate?: string;
  vencimentoDate?: string;
  onBack?: () => void;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function statusBadgeClass(tipo: StatusGeralDocumento["tipo"]) {
  switch (tipo) {
    case "pronto":
      return "border-emerald-500/25 bg-emerald-500/10 text-emerald-700";
    case "bloqueado":
      return "border-destructive/25 bg-destructive/10 text-destructive";
    case "em_execucao":
      return "border-sky-500/25 bg-sky-500/10 text-sky-700";
    default:
      return "border-amber-500/25 bg-amber-500/10 text-amber-700";
  }
}

export function StatusOverview({
  statusGeral,
  resumo,
  optanteSimples,
  hasDdf055,
  apuracaoDate,
  vencimentoDate,
  onBack,
}: StatusOverviewProps) {
  const simplesStatus =
    optanteSimples === hasDdf055
      ? optanteSimples
        ? {
            tone: "border-amber-500/25 bg-amber-500/10 text-amber-700",
            title: "Optante com DDF055 presente",
            description:
              "A retenção federal DDF055 (IR, CSLL, COFINS, PIS) foi identificada em empresa optante pelo Simples Nacional.",
          }
        : {
            tone: "border-amber-500/25 bg-amber-500/10 text-amber-700",
            title: "Não optante e sem DDF055",
            description:
              "A empresa não consta como optante pelo Simples e nenhuma retenção federal DDF055 foi identificada.",
          }
      : null;

  return (
    <GlassCard className="px-5 py-4">
      {/* Linha 1: Voltar + título + status + datas */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {onBack ? (
          <GlassButton variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </GlassButton>
        ) : (
          <Link href="/">
            <GlassButton variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4" />
              Voltar
            </GlassButton>
          </Link>
        )}

        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <h1 className="text-base font-semibold text-foreground">Conferência e Automação</h1>

          <span
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${statusBadgeClass(statusGeral.tipo)}`}
          >
            {statusGeral.tipo === "pronto" ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : statusGeral.tipo === "em_execucao" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5" />
            )}
            {statusGeral.titulo}
          </span>

          {simplesStatus && (
            <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${simplesStatus.tone}`}>
              <AlertTriangle className="h-3.5 w-3.5" />
              {simplesStatus.title}
            </span>
          )}
        </div>

        {(apuracaoDate || vencimentoDate) && (
          <div className="flex shrink-0 flex-wrap gap-1.5">
            {apuracaoDate && (
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-glass-border bg-background/70 px-2.5 py-1 text-xs font-medium text-foreground">
                <CalendarDays className="h-3 w-3 text-muted-foreground" />
                Apuração: {apuracaoDate}
              </span>
            )}
            {vencimentoDate && (
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-glass-border bg-background/70 px-2.5 py-1 text-xs font-medium text-foreground">
                <CalendarDays className="h-3 w-3 text-muted-foreground" />
                Vencimento: {vencimentoDate}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Linha 2: descrição do status + resumo financeiro inline */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{statusGeral.descricao}</p>

        <div className="flex shrink-0 items-center divide-x divide-glass-border rounded-xl border border-glass-border bg-background/70">
          <div className="flex items-center gap-2 px-4 py-2">
            <Landmark className="h-3.5 w-3.5 text-muted-foreground" />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Bruto</p>
              <p className="text-sm font-semibold text-foreground">{formatCurrency(resumo.bruto)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-4 py-2">
            <Receipt className="h-3.5 w-3.5 text-muted-foreground" />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Deduções</p>
              <p className="text-sm font-semibold text-foreground">- {formatCurrency(resumo.deducoes)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-4 py-2">
            <Wallet className="h-3.5 w-3.5 text-muted-foreground" />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Líquido</p>
              <p className="text-sm font-semibold text-emerald-700">{formatCurrency(resumo.liquido)}</p>
            </div>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
