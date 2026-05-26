"use client";

import Link from "next/link";
import { MessageCircle, Table2, Settings, Circle, Palmtree } from "lucide-react";
import { GlassButton } from "./glass-card";

interface HeaderProps {
  chromeStatus?: "pronto" | "carregando" | "erro";
  browserName?: string;
  onOpenTabelas?: () => void;
  onOpenConfiguracoes?: () => void;
  onOpenChrome?: () => void;
  chromeActionDisabled?: boolean;
  onGoHome?: () => void;
  onOpenFilaTrabalho?: () => void;
  onOpenDashboard?: () => void;
  onOpenFerias?: () => void;
  rocketChatUnreadCount?: number | null;
}

export function Header({
  chromeStatus = "pronto",
  browserName = "Chrome",
  onOpenTabelas,
  onOpenConfiguracoes,
  onOpenChrome,
  chromeActionDisabled = false,
  onGoHome,
  onOpenFilaTrabalho: _onOpenFilaTrabalho,
  onOpenDashboard,
  onOpenFerias,
  rocketChatUnreadCount = null,
}: HeaderProps) {
  const statusColor = {
    pronto: "text-success",
    carregando: "text-warning",
    erro: "text-destructive",
  };

  const statusText = {
    pronto: `${browserName} disponível`,
    carregando: `Verificando ${browserName}...`,
    erro: `${browserName} indisponível`,
  };
  const rocketChatBadge =
    typeof rocketChatUnreadCount === "number" && rocketChatUnreadCount > 0
      ? rocketChatUnreadCount > 99
        ? "99+"
        : String(rocketChatUnreadCount)
      : "";

  return (
    <header className="sticky top-0 z-50 border-b border-glass-border bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <div className="flex items-center gap-2">
          <Link
            href="/"
            onClick={onGoHome}
            className="group inline-flex items-baseline rounded-md px-1 py-0.5 transition-colors hover:bg-secondary/45"
            aria-label="Ir para o painel inicial"
          >
            <h1 className="text-lg font-semibold text-foreground tracking-tight transition-colors group-hover:text-primary">
              AutoLiquid
              <span className="ml-2 text-xs font-normal text-muted-foreground tracking-normal">
                · DCF / Liquidação
              </span>
            </h1>
          </Link>

          <a
            href="https://chat.ufsc.br"
            target="_blank"
            rel="noreferrer"
            title={
              rocketChatBadge
                ? `${rocketChatBadge} notificação(ões) no Rocket.Chat`
                : "Abrir Rocket.Chat"
            }
            className="relative inline-flex h-8 items-center gap-1.5 rounded-full border border-glass-border bg-background px-3 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
          >
            <MessageCircle className="h-3.5 w-3.5" />
            Rocket.Chat
            {rocketChatBadge ? (
              <span
                aria-label={`${rocketChatBadge} notificação(ões) no Rocket.Chat`}
                className="absolute -right-1.5 -top-2 inline-flex min-w-5 items-center justify-center rounded-full border-2 border-background bg-red-500 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white shadow-[0_4px_12px_rgba(239,68,68,0.35)]"
              >
                {rocketChatBadge}
              </span>
            ) : null}
          </a>
        </div>

        <nav className="flex items-center gap-2">
          <GlassButton
            variant="ghost"
            size="sm"
            onClick={onOpenFerias}
            title="Férias, Afastamentos e Licenças"
          >
            <Palmtree className="h-4 w-4" />
            Ausências
          </GlassButton>

          <GlassButton
            variant="ghost"
            size="sm"
            onClick={onOpenTabelas}
            disabled={!onOpenTabelas}
            title={onOpenTabelas ? undefined : "Ação ainda não disponível nesta tela"}
          >
            <Table2 className="h-4 w-4" />
            Tabelas
          </GlassButton>

          <GlassButton
            variant="ghost"
            size="sm"
            onClick={onOpenChrome}
            disabled={!onOpenChrome || chromeActionDisabled}
            title={
              onOpenChrome
                ? `Abrir ou reconectar o ${browserName} na página inicial da automação`
                : "Ação indisponível nesta tela"
            }
          >
            <Circle className={`h-3 w-3 fill-current ${statusColor[chromeStatus]}`} />
            <span className={statusColor[chromeStatus]}>{statusText[chromeStatus]}</span>
          </GlassButton>

          <GlassButton
            variant="ghost"
            size="sm"
            onClick={onOpenConfiguracoes}
            disabled={!onOpenConfiguracoes}
            title={onOpenConfiguracoes ? undefined : "Configurações web ainda não implementadas"}
          >
            <Settings className="h-4 w-4" />
            Configurações
          </GlassButton>
        </nav>
      </div>
    </header>
  );
}
