"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Server,
  Sparkles,
} from "lucide-react";

import { GlassButton, GlassCard } from "@/components/glass-card";
import type { BackendStartupPhase } from "@/lib/data";

type StepStatus = "pending" | "active" | "done" | "error";

interface StartupScreenProps {
  phase: BackendStartupPhase;
  progress: number;
  title: string;
  detail: string;
  error?: string;
  onRetry?: () => void;
}

function getStepStatuses(phase: BackendStartupPhase): StepStatus[] {
  if (phase === "error") {
    return ["done", "error", "pending"];
  }

  const ordem: BackendStartupPhase[] = [
    "booting-ui",
    "starting-api",
    "restoring-data",
    "ready",
  ];
  const indiceAtual = ordem.indexOf(phase);

  return [0, 1, 2].map((indice) => {
    if (phase === "ready") {
      return "done";
    }
    if (indice < indiceAtual) {
      return "done";
    }
    if (indice === indiceAtual) {
      return "active";
    }
    return "pending";
  });
}

function StepIndicator({
  label,
  description,
  status,
}: {
  label: string;
  description: string;
  status: StepStatus;
}) {
  const palette =
    status === "done"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
      : status === "active"
        ? "border-sky-500/30 bg-sky-500/10 text-sky-700"
        : status === "error"
          ? "border-destructive/30 bg-destructive/10 text-destructive"
          : "border-glass-border/70 bg-background/60 text-muted-foreground";

  return (
    <div className={`rounded-2xl border px-4 py-3 transition-colors ${palette}`}>
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full border border-current/20 bg-background/70">
          {status === "done" ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : status === "active" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : status === "error" ? (
            <AlertTriangle className="h-4 w-4" />
          ) : (
            <span className="h-2.5 w-2.5 rounded-full bg-current/45" />
          )}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{label}</p>
          <p className="text-xs opacity-80">{description}</p>
        </div>
      </div>
    </div>
  );
}

export function StartupScreen({
  phase,
  progress,
  title,
  detail,
  error,
  onRetry,
}: StartupScreenProps) {
  const steps = getStepStatuses(phase);
  const safeProgress = Math.max(0, Math.min(100, progress));

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-6 py-10">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-[-12%] top-[-18%] h-72 w-72 rounded-full bg-sky-500/12 blur-3xl" />
        <div className="absolute bottom-[-12%] right-[-10%] h-80 w-80 rounded-full bg-primary/14 blur-3xl" />
        <div className="absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-white/55 to-transparent" />
      </div>

      <GlassCard className="relative w-full max-w-3xl overflow-hidden border-white/55 shadow-[0_34px_110px_-52px_rgba(15,23,42,0.42)]">
        <div className="relative px-6 py-7 sm:px-8 sm:py-8">
          <div className="mb-8 flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-sky-500/20 bg-background/85 text-sky-700 shadow-[0_18px_40px_-28px_rgba(14,116,144,0.85)]">
                {phase === "error" ? (
                  <AlertTriangle className="h-7 w-7" />
                ) : (
                  <Sparkles className="h-7 w-7" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-sky-700/80">
                  Ambiente local
                </p>
                <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                  {title}
                </h1>
                <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground sm:text-base">
                  {detail}
                </p>
              </div>
            </div>

            <div className="hidden rounded-2xl border border-glass-border/70 bg-background/70 px-4 py-3 text-right sm:block">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Progresso
              </p>
              <p className="mt-1 text-2xl font-semibold text-foreground">{safeProgress}%</p>
            </div>
          </div>

          <div className="mb-7">
            <div className="h-3 overflow-hidden rounded-full bg-secondary/80">
              <div
                className="h-full rounded-full bg-gradient-to-r from-sky-500 via-primary to-accent transition-[width] duration-500 ease-out"
                style={{ width: `${safeProgress}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
              <div className="inline-flex items-center gap-2">
                <Server className="h-4 w-4" />
                <span>
                  {phase === "starting-api"
                    ? "Conectando os serviços internos"
                    : phase === "restoring-data"
                      ? "Recuperando dados iniciais"
                      : phase === "ready"
                        ? "Tudo pronto para começar"
                        : phase === "error"
                          ? "Abertura interrompida"
                          : "Preparando o painel inicial"}
                </span>
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <StepIndicator
              label="Painel"
              description="Montando a interface inicial"
              status={steps[0]}
            />
            <StepIndicator
              label="Serviços"
              description="Ligando a API local do AutoLiquid"
              status={steps[1]}
            />
            <StepIndicator
              label="Contexto"
              description="Carregando datas e preferências salvas"
              status={steps[2]}
            />
          </div>

          {error && (
            <div className="mt-6 rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-destructive">
                    O AutoLiquid ainda nao conseguiu concluir a abertura.
                  </p>
                  <p className="mt-1 text-sm leading-6 text-destructive/90">{error}</p>
                </div>
              </div>
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <p className="max-w-xl text-sm text-muted-foreground">
              A tela principal será exibida assim que os serviços locais estiverem prontos.
            </p>

            {error && onRetry ? (
              <GlassButton
                type="button"
                variant="secondary"
                size="md"
                onClick={onRetry}
                className="border-destructive/20 bg-background/80"
              >
                <RefreshCw className="h-4 w-4" />
                Tentar novamente
              </GlassButton>
            ) : null}
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
