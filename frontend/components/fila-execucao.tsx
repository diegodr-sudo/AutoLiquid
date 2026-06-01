"use client";

import { useState } from "react";
import {
  FileText,
  DollarSign,
  MinusCircle,
  CreditCard,
  Building,
  Play,
  Circle,
  Square,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { GlassCard, GlassButton } from "./glass-card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Deducao, EtapaExecucao } from "@/lib/data";
import { cn } from "@/lib/utils";

const EXECUTION_GREEN_BUTTON_CLASS =
  "border-[color:oklch(0.58_0.12_160)] bg-[color:oklch(0.58_0.12_160)] text-white hover:bg-[color:oklch(0.54_0.11_160)] hover:border-[color:oklch(0.54_0.11_160)]";
const EXECUTION_GREEN_BADGE_CLASS =
  "border-[color:color-mix(in_oklch,var(--success)_22%,transparent)] bg-[color:color-mix(in_oklch,var(--success)_16%,transparent)] text-[color:oklch(0.38_0.08_160)]";
const EXECUTION_ERROR_BADGE_CLASS =
  "border-destructive/30 bg-destructive/12 text-[color:oklch(0.42_0.15_25)]";
const EXECUTION_DIVERGENCIA_BADGE_CLASS =
  "border-amber-400/35 bg-amber-500/12 text-amber-700 dark:text-amber-300";
const EXECUTION_SIAFI_OUTLINE_CLASS =
  "border-[color:oklch(0.72_0.12_85)] bg-transparent text-[color:oklch(0.48_0.09_85)] hover:bg-[color:color-mix(in_oklch,oklch(0.72_0.12_85)_10%,white)]";

interface FilaExecucaoProps {
  etapas: EtapaExecucao[];
  deducoes?: Deducao[];
  onExecutarTudo?: () => void;
  onExecutarEtapa?: (etapa: EtapaExecucao) => void;
  onExecutarDeducao?: (deducao: Deducao) => void;
  onApropriarSIAFI?: () => void;
  apuracaoDate?: string;
  vencimentoDate?: string;
  isExecutando?: boolean;
  etapaAtivaId?: number | null;
  deducaoAtivaId?: number | null;
  statusMensagem?: string;
  onPararExecucao?: () => void;
  paradaSolicitada?: boolean;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  FileText,
  DollarSign,
  MinusCircle,
  CreditCard,
  Building,
};

function getStepCircleClass(status: EtapaExecucao["status"], isAtiva: boolean) {
  if (isAtiva || status === "executando") {
    return "bg-primary text-primary-foreground";
  }

  switch (status) {
    case "concluido":
      return "bg-[color:oklch(0.58_0.12_160)] text-white";
    case "divergencia":
      return "bg-amber-500 text-white";
    case "erro":
      return "bg-destructive text-white";
    default:
      return "bg-muted text-foreground";
  }
}

function getStatusLabel(status: EtapaExecucao["status"], isAtiva: boolean) {
  if (isAtiva || status === "executando") {
    return "Em execução"
  }

  switch (status) {
    case "concluido":
      return "Concluída"
    case "divergencia":
      return "Divergência"
    case "erro":
      return "Com erro"
    default:
      return "Aguardando"
  }
}

function getStatusBadgeClass(status: EtapaExecucao["status"], isAtiva: boolean) {
  if (isAtiva || status === "executando") {
    return "border-primary/30 bg-primary/12 text-primary"
  }

  switch (status) {
    case "concluido":
      return EXECUTION_GREEN_BADGE_CLASS
    case "divergencia":
      return EXECUTION_DIVERGENCIA_BADGE_CLASS
    case "erro":
      return EXECUTION_ERROR_BADGE_CLASS
    default:
      return "border-glass-border bg-background/70 text-muted-foreground"
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function DeducaoStatusIcon({ status, isAtiva }: { status: Deducao["status"]; isAtiva: boolean }) {
  if (isAtiva || status === "executando")
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />;
  if (status === "concluido")
    return <CheckCircle2 className="h-3.5 w-3.5 text-success" />;
  if (status === "erro")
    return <XCircle className="h-3.5 w-3.5 text-destructive" />;
  return null;
}

export function FilaExecucao({
  etapas,
  deducoes = [],
  onExecutarTudo,
  onExecutarEtapa,
  onExecutarDeducao,
  onApropriarSIAFI,
  apuracaoDate,
  vencimentoDate,
  isExecutando = false,
  etapaAtivaId = null,
  deducaoAtivaId = null,
  statusMensagem,
  onPararExecucao,
  paradaSolicitada = false,
}: FilaExecucaoProps) {
  const concluidos = etapas.filter((e) => e.status === "concluido").length;
  const [deducoesExpandidas, setDeducoesExpandidas] = useState(false);
  const deducoesVisiveis = Array.from(
    deducoes.reduce((acc, deducao) => {
      const siafi = String(deducao.siafi || "").toUpperCase();
      if (!acc.has(siafi)) {
        acc.set(siafi, {
          ...deducao,
          tipo: siafi,
          valor: deducoes
            .filter((item) => String(item.siafi || "").toUpperCase() === siafi)
            .reduce((total, item) => total + item.valor, 0),
        });
      }
      return acc;
    }, new Map<string, Deducao>())
  ).map(([_, item]) => item);

  return (
    <GlassCard className="flex h-full flex-col">
      <div className="p-5">
        <h3 className="mb-4 text-xs font-medium uppercase tracking-wider text-primary">
          Fila de Execução
        </h3>

        <div className="space-y-2.5">
          {etapas.map((etapa, index) => {
            const IconComponent = iconMap[etapa.icone] || FileText;
            const isAtiva = etapaAtivaId === etapa.id;
            const isClickable = Boolean(onExecutarEtapa) && !isExecutando;
            const statusLabel = getStatusLabel(etapa.status, isAtiva);

            return (
              <div key={etapa.id} className="space-y-1.5">
                <button
                  type="button"
                  onClick={() => onExecutarEtapa?.(etapa)}
                  disabled={!isClickable}
                  aria-label={`Etapa ${index + 1}: ${etapa.nome}. Status ${statusLabel}.`}
                  className={cn(
                    "grid w-full grid-cols-[2rem_minmax(0,1fr)] gap-3 rounded-xl border px-3 py-3 text-left transition-all",
                    isAtiva
                      ? "border-primary/40 bg-primary/10 shadow-[0_18px_40px_-28px_rgba(79,70,229,0.75)]"
                      : "border-transparent bg-secondary/25",
                    isClickable && "hover:border-primary/30 hover:bg-secondary/50",
                    !isClickable && "cursor-default opacity-90"
                  )}
                >
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold",
                      getStepCircleClass(etapa.status, isAtiva)
                    )}
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="flex min-w-0 items-start gap-2">
                      <IconComponent className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 text-sm font-medium leading-snug text-foreground">
                        {etapa.nome}
                      </span>
                      {etapa.id === 3 && deducoesVisiveis.length > 0 ? (
                        <span
                          role="button"
                          tabIndex={0}
                          aria-label={deducoesExpandidas ? "Recolher deduções" : "Expandir deduções"}
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            setDeducoesExpandidas((current) => !current);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              event.stopPropagation();
                              setDeducoesExpandidas((current) => !current);
                            }
                          }}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground"
                        >
                          {deducoesExpandidas ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </span>
                      ) : null}
                    </span>
                    <span
                      className={cn(
                        "mt-2 inline-flex w-fit rounded-full border px-2.5 py-1 text-[11px] font-medium",
                        getStatusBadgeClass(etapa.status, isAtiva)
                      )}
                    >
                      {statusLabel}
                    </span>
                  </span>
                </button>

                {/* Sub-lista de deduções individuais */}
                {etapa.id === 3 && deducoesVisiveis.length > 0 && deducoesExpandidas && (
                  <div className="ml-4 space-y-1.5 border-l-2 border-glass-border pl-3">
                    {deducoesVisiveis.map((ded) => {
                      const isDedAtiva = deducaoAtivaId === ded.id;
                      const dedClickable = Boolean(onExecutarDeducao) && !isExecutando;
                      return (
                        <div
                          key={ded.id}
                          className={cn(
                            "flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-all",
                            isDedAtiva
                              ? "border-primary/30 bg-primary/8"
                              : ded.status === "concluido"
                              ? "border-success/20 bg-success/5"
                              : ded.status === "erro"
                              ? "border-destructive/20 bg-destructive/5"
                              : "border-transparent bg-background/40"
                          )}
                        >
                          <DeducaoStatusIcon status={ded.status} isAtiva={isDedAtiva} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-medium text-foreground">
                              {ded.siafi}
                            </p>
                            <p className="text-[10px] text-muted-foreground">
                              Recolhido - {formatCurrency(ded.valor)}
                            </p>
                          </div>
                          <Tooltip>
                          <TooltipTrigger asChild>
                          <button
                            type="button"
                            disabled={!dedClickable}
                            onClick={() => onExecutarDeducao?.(ded)}
                            className={cn(
                              "flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors",
                              ded.status === "concluido"
                                ? "text-[color:oklch(0.38_0.08_160)] hover:bg-[color:color-mix(in_oklch,var(--success)_10%,transparent)]"
                                : ded.status === "erro"
                                ? "border border-destructive/30 bg-destructive/10 text-[color:oklch(0.42_0.15_25)] hover:bg-destructive/15"
                                : "border border-primary/25 bg-primary/10 text-primary hover:bg-primary/15",
                              !dedClickable && "cursor-default opacity-50"
                            )}
                          >
                            <Play className="h-2.5 w-2.5" />
                            {ded.status === "concluido" ? "Refazer" : "Executar"}
                          </button>
                          </TooltipTrigger>
                          <TooltipContent>Executar apenas esta dedução</TooltipContent>
                          </Tooltip>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-6 grid gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <GlassButton
                variant="secondary"
                className={cn("w-full", EXECUTION_GREEN_BUTTON_CLASS)}
                aria-label={isExecutando ? "Executando todas as etapas" : "Executar todas as etapas"}
                onClick={onExecutarTudo}
                disabled={isExecutando}
              >
                <Play className="h-4 w-4" />
                {isExecutando ? "Executando..." : "Executar Tudo"}
              </GlassButton>
            </TooltipTrigger>
            <TooltipContent>Executar todas as etapas em sequência</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <GlassButton
                variant="ghost"
                aria-label="Apropriar no SIAFI"
                onClick={onApropriarSIAFI}
                disabled={isExecutando}
                className={cn("w-full border", EXECUTION_SIAFI_OUTLINE_CLASS)}
              >
                <Circle className="h-4 w-4" />
                Apropriar SIAFI
              </GlassButton>
            </TooltipTrigger>
            <TooltipContent>Enviar o documento atual para apropriação no SIAFI</TooltipContent>
          </Tooltip>
        </div>

        {isExecutando && (
          <GlassButton
            variant="ghost"
            className="mt-3 w-full border border-destructive/25 bg-destructive/10 text-destructive hover:bg-destructive/15"
            onClick={onPararExecucao}
            disabled={!onPararExecucao || paradaSolicitada}
          >
            <Square className="h-4 w-4" />
            {paradaSolicitada ? "Parada solicitada" : "Parar após a etapa atual"}
          </GlassButton>
        )}

        <div className="mt-4 text-center text-sm">
          <span className="text-muted-foreground">
            {statusMensagem || "Aguardando execução"}
          </span>{" "}
          <span className="font-medium text-foreground">
            {concluidos} / {etapas.length}
          </span>
        </div>
      </div>
    </GlassCard>
  );
}
