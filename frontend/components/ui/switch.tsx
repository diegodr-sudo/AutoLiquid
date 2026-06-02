'use client'

import * as React from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'

import { cn } from '@/lib/utils'

function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'peer inline-flex h-[1.15rem] w-8 shrink-0 items-center rounded-full border shadow-xs transition-all outline-none data-[state=checked]:border-primary/40 data-[state=checked]:bg-primary data-[state=unchecked]:border-slate-300 data-[state=unchecked]:bg-slate-200 hover:data-[state=unchecked]:bg-slate-300/70 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:data-[state=unchecked]:border-slate-500 dark:data-[state=unchecked]:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-4 rounded-full border bg-background shadow-sm ring-0 transition-transform data-[state=checked]:translate-x-[calc(100%-2px)] data-[state=checked]:border-primary-foreground/40 data-[state=checked]:bg-primary-foreground data-[state=unchecked]:translate-x-0 data-[state=unchecked]:border-slate-400 data-[state=unchecked]:bg-white dark:data-[state=unchecked]:border-slate-500 dark:data-[state=unchecked]:bg-slate-100"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
