'use client'

import * as React from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface SimpleTooltipProps {
  /** Conteúdo exibido no tooltip. Se falsy, renderiza os filhos sem tooltip. */
  content: React.ReactNode
  children: React.ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
  className?: string
  /** Largura máxima do tooltip (padrão: max-w-xs) */
  maxWidth?: string
  /** Desativa o tooltip sem remover o componente */
  disabled?: boolean
}

/**
 * Wrapper conveniente sobre o Tooltip do shadcn/ui.
 *
 * Substitui o atributo nativo `title=` do browser pelo tooltip estilizado
 * da aplicação. Basta envolver o elemento e passar `content`:
 *
 * ```tsx
 * // Antes
 * <span title="Texto longo aqui">...</span>
 *
 * // Depois
 * <SimpleTooltip content="Texto longo aqui">
 *   <span>...</span>
 * </SimpleTooltip>
 * ```
 */
export function SimpleTooltip({
  content,
  children,
  side = 'top',
  align = 'center',
  className,
  maxWidth = 'max-w-xs',
  disabled = false,
}: SimpleTooltipProps) {
  if (!content || disabled) return <>{children}</>

  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent
        side={side}
        align={align}
        className={cn(maxWidth, 'text-center leading-snug', className)}
      >
        {content}
      </TooltipContent>
    </Tooltip>
  )
}
