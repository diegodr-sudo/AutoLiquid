"use client";

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  hover?: boolean;
}

export function GlassCard({
  children,
  className,
  contentClassName,
  hover = false,
}: GlassCardProps) {
  return (
    <div
      className={cn(
        "relative rounded-2xl border border-glass-border bg-glass-bg shadow-[0_28px_80px_-48px_rgba(15,23,42,0.4)] backdrop-blur-xl",
        "before:absolute before:inset-0 before:rounded-2xl before:bg-gradient-to-br before:from-glass-highlight before:to-transparent before:pointer-events-none",
        hover && "transition-all duration-300 hover:border-primary/30 hover:shadow-[0_30px_90px_-50px_rgba(79,70,229,0.45)]",
        className
      )}
    >
      <div className={cn("relative z-10", contentClassName)}>{children}</div>
    </div>
  );
}

interface GlassPanelProps {
  children: ReactNode;
  className?: string;
}

export function GlassPanel({ children, className }: GlassPanelProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-glass-border/50 bg-secondary/30 backdrop-blur-sm p-4",
        className
      )}
    >
      {children}
    </div>
  );
}

interface GlassInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function GlassInput({ label, className, ...props }: GlassInputProps) {
  return (
    <div className="space-y-2">
      {label && (
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </label>
      )}
      <input
        className={cn(
          "w-full rounded-lg border border-glass-border bg-input px-4 py-3 text-foreground",
          "placeholder:text-muted-foreground/50",
          "focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/50",
          "transition-all duration-200",
          className
        )}
        {...props}
      />
    </div>
  );
}

interface GlassButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "success" | "warning";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

export function GlassButton({
  variant = "secondary",
  size = "md",
  children,
  className,
  ...props
}: GlassButtonProps) {
  const variants = {
    primary: "bg-primary text-primary-foreground hover:bg-primary/90 border-primary/50",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80 border-glass-border",
    ghost: "bg-transparent text-foreground hover:bg-secondary/50 border-transparent",
    success: "bg-success text-primary-foreground hover:bg-success/90 border-success/50",
    warning: "bg-warning text-primary-foreground hover:bg-warning/90 border-warning/50",
  };

  const sizes = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3 text-base",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg border font-medium",
        "transition-all duration-200 backdrop-blur-sm",
        "focus:outline-none focus:ring-2 focus:ring-ring/50",
        "disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

interface GlassTableProps {
  headers: string[];
  headerTitles?: string[];
  children: ReactNode;
  className?: string;
  compact?: boolean;
}

export function GlassTable({ headers, headerTitles, children, className, compact }: GlassTableProps) {
  const thPad = compact ? "px-2 py-2" : "px-4 py-3";
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full">
        <thead>
          <tr className="border-b border-glass-border">
            {headers.map((header, index) => (
              <th
                key={index}
                title={headerTitles?.[index]}
                className={cn(thPad, "text-left text-xs font-medium uppercase tracking-wider text-muted-foreground", headerTitles?.[index] ? "cursor-default" : "")}
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-glass-border/50">{children}</tbody>
      </table>
    </div>
  );
}

export function GlassTableRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <tr className={cn("transition-colors hover:bg-secondary/30", className)}>
      {children}
    </tr>
  );
}

export function GlassTableCell({ children, className, compact }: { children: ReactNode; className?: string; compact?: boolean }) {
  return (
    <td className={cn(compact ? "px-2 py-2" : "px-4 py-3", "text-sm text-foreground", className)}>
      {children}
    </td>
  );
}
