"use client";

import { useState } from "react";
import { Globe2 } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface GlobalScopeIconProps {
  message?: string;
  label?: string;
  className?: string;
}

export function GlobalScopeIcon({
  message = "Alterações aqui são globais e valem para todos os usuários.",
  label,
  className = "",
}: GlobalScopeIconProps) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={message}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          className={[
            "inline-flex h-7 items-center justify-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 text-xs font-medium text-emerald-700 shadow-sm shadow-emerald-950/5 transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/15",
            label ? "min-w-0" : "w-7 px-0",
            className,
          ].join(" ")}
        >
          <Globe2 className="h-3.5 w-3.5 shrink-0" />
          {label ? <span className="truncate">{label}</span> : null}
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="center"
        sideOffset={8}
        className="z-[140] w-64 rounded-xl p-3 text-xs leading-5 text-muted-foreground shadow-xl"
      >
        {message}
      </PopoverContent>
    </Popover>
  );
}
