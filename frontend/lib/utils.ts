import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Converte timestamps do banco (SQLite `current_timestamp` = UTC, sem sufixo de fuso)
 * para objetos Date corretamente interpretados como UTC.
 *
 * Strings com espaço como separador ("2026-05-29 14:30:00") são normalizadas
 * para ISO 8601 com "Z" antes de serem parseadas, evitando que o browser
 * as trate como horário local e exiba 3h adiantado no fuso Brasil (UTC-3).
 *
 * Strings que já contêm indicação de fuso (Z, +, -) são passadas diretamente.
 */
export function parseDbTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null
  const s = value.trim()
  // Se já tem fuso horário explícito, não altera
  const jaTemFuso = s.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(s)
  const normalized = jaTemFuso
    ? s
    : s.replace(" ", "T") + "Z"
  const d = new Date(normalized)
  return Number.isNaN(d.getTime()) ? null : d
}
