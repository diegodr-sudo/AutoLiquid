import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Converte timestamps do banco para objetos Date.
 *
 * O banco armazena timestamps no horário local de Brasília (sem sufixo de fuso).
 * Strings sem fuso são normalizadas apenas trocando o espaço por "T", para que
 * o browser as interprete como horário local — sem adicionar "Z" (que causaria
 * a subtração de 3h pelo toLocaleString em pt-BR).
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
    : s.replace(" ", "T") // sem "Z" → browser interpreta como horário local
  const d = new Date(normalized)
  return Number.isNaN(d.getTime()) ? null : d
}
