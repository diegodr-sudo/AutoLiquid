"use client";

import { GlassCard, GlassInput } from "./glass-card";
import type { ProcessDates } from "@/lib/data";
import type { ReactNode } from "react";

interface DateFieldsProps {
  dates: ProcessDates;
  onDatesChange?: (dates: ProcessDates) => void;
  compact?: boolean;
  action?: ReactNode;
}

/** Máscara dd/mm/aaaa — mantém apenas dígitos e insere barras automaticamente */
function maskDate(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}

export function DateFields({ dates, onDatesChange, compact = false, action }: DateFieldsProps) {
  return (
    <GlassCard className={compact ? "p-4" : "p-6"}>
      <div className={compact ? "mb-3 flex flex-wrap items-center justify-between gap-2" : "mb-4 flex flex-wrap items-center justify-between gap-2"}>
        <h3 className={compact ? "text-[11px] font-medium uppercase tracking-wider text-primary" : "text-xs font-medium uppercase tracking-wider text-primary"}>
          Datas do Processo
        </h3>
        {action ? <div className="ml-auto">{action}</div> : null}
      </div>
      <div className={compact ? "grid gap-4 sm:grid-cols-2" : "grid gap-6 sm:grid-cols-2"}>
        <GlassInput
          label="Data de Apuração"
          type="text"
          inputMode="numeric"
          value={dates.apuracao}
          onChange={(e) =>
            onDatesChange?.({ ...dates, apuracao: maskDate(e.target.value) })
          }
          placeholder="DD/MM/AAAA"
          maxLength={10}
        />
        <GlassInput
          label="Vencimento / Pagamento"
          type="text"
          inputMode="numeric"
          value={dates.vencimento}
          onChange={(e) =>
            onDatesChange?.({ ...dates, vencimento: maskDate(e.target.value) })
          }
          placeholder="DD/MM/AAAA"
          maxLength={10}
        />
      </div>
    </GlassCard>
  );
}
