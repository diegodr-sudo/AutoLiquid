"use client";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface GlobalScopeIconProps {
  message?: string;
  label?: string;
  className?: string;
}

export function GlobalScopeIcon({
  message = "Global: esta configuração é compartilhada e vale para todos os usuários.",
  label,
  className = "",
}: GlobalScopeIconProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={message}
          title={message}
          className={[
            "inline-flex h-7 items-center justify-center gap-1.5 rounded-full border border-teal-500/25 bg-teal-500/10 px-2 text-xs font-medium text-teal-700 shadow-sm shadow-teal-950/5 transition-colors hover:border-teal-500/40 hover:bg-teal-500/15",
            label ? "min-w-0 pr-2.5" : "w-7 px-0",
            className,
          ].join(" ")}
        >
          <span className="relative inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-current/45 bg-background/55">
            <svg
              viewBox="0 0 16 16"
              aria-hidden="true"
              className="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="1.35"
            >
              <circle cx="8" cy="8" r="5.25" />
              <path d="M2.9 8h10.2" />
              <path d="M8 2.75c1.35 1.35 2.05 3.1 2.05 5.25S9.35 11.9 8 13.25" />
              <path d="M8 2.75C6.65 4.1 5.95 5.85 5.95 8s.7 3.9 2.05 5.25" />
            </svg>
          </span>
          {label ? <span className="truncate">{label}</span> : null}
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="top"
        align="center"
        sideOffset={8}
        className="z-[200] max-w-72 rounded-xl px-3 py-2 text-xs leading-5"
      >
        {message}
      </TooltipContent>
    </Tooltip>
  );
}
