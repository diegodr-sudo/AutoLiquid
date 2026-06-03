"use client";

/**
 * SiafiTerminal
 *
 * Visualização em tempo real da automação SIAFI tela preta.
 * Conecta ao SSE em /api/siafi/atulc/stream/{executionId} e exibe:
 *   - Terminal 3270 (verde no preto, fonte monospace)
 *   - Indicador da ação atual com animação
 *   - Log de etapas concluídas
 *
 * Uso:
 *   <SiafiTerminal executionId={id} onConcluido={(resultado) => ...} />
 */

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, Terminal, XCircle } from "lucide-react";
import { GlassCard } from "./glass-card";
import { cn } from "@/lib/utils";
import { siafiAtulcStreamUrl } from "@/lib/data";

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface SiafiEvent {
  type: "update" | "resultado" | "ready" | "done";
  acao?: string;
  tela?: string[];
  estado?: string;
  ok?: boolean;
  mensagem?: string;
}

interface LogEntry {
  acao: string;
  estado: string;
  ts: number;
}

interface Props {
  executionId: string | null;
  onConcluido?: (resultado: { ok: boolean; mensagem: string }) => void;
  className?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Classifica o estado em um rótulo amigável para o cabeçalho do terminal */
function labelEstado(estado: string): string {
  const map: Record<string, string> = {
    conectando:       "Conectando...",
    hod_webstart_abrindo: "Abrindo HOD...",
    hod_webstart_aguardando: "Aguardando HOD",
    hod_webstart_conectado: "HOD conectado",
    codigo_acesso:    "Código de Acesso HOD",
    login:            "Login",
    menu:             "Menu Principal",
    atulc_comando_enviado: "ATULC enviado",
    atulc_form:       "Formulário ATULC",
    atulc_credores:   "Lista de Credores",
    erro:             "Erro",
    desconhecido:     "—",
    "":               "—",
  };
  return map[estado] ?? estado;
}

/** Destaca linhas da tela 3270 com cores parecidas com o terminal real */
function TerminalLine({ linha, idx }: { linha: string; idx: number }) {
  // Linhas de cabeçalho (geralmente as 2 primeiras) — cor azul suave
  // Linhas com campos de input (contém underscores) — cor âmbar
  // Linhas de menu/opção — cor verde padrão
  const hasInput = /_{3,}/.test(linha);
  const isHeader = idx <= 1;
  const isError  = /ERRO|INVALIDO|NAO ENCONTRADO/.test(linha.toUpperCase());

  return (
    <div
      className={cn(
        "font-mono text-[11px] leading-[1.45] whitespace-pre tracking-tight",
        isError  && "text-red-400",
        isHeader && !isError && "text-blue-300/80",
        hasInput && !isError && !isHeader && "text-amber-300/90",
        !isError && !isHeader && !hasInput && "text-green-400/90",
      )}
    >
      {linha || " "}
    </div>
  );
}

// ─── Componente principal ─────────────────────────────────────────────────────

export function SiafiTerminal({ executionId, onConcluido, className }: Props) {
  const [tela, setTela]         = useState<string[]>([]);
  const [acaoAtual, setAcao]    = useState<string>("Aguardando início...");
  const [estadoAtual, setEstado] = useState<string>("");
  const [log, setLog]            = useState<LogEntry[]>([]);
  const [concluido, setConcluido] = useState<{ ok: boolean; mensagem: string } | null>(null);
  const [conectado, setConectado] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const onConcluidoRef = useRef(onConcluido);

  useEffect(() => {
    onConcluidoRef.current = onConcluido;
  }, [onConcluido]);

  // Rola o log para o último item
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  // Abre/fecha o EventSource conforme o executionId
  useEffect(() => {
    if (!executionId) return;

    // Reseta estado anterior
    setTela([]);
    setAcao("Conectando ao SIAFI...");
    setEstado("conectando");
    setLog([]);
    setConcluido(null);
    setConectado(false);

    const es = new EventSource(siafiAtulcStreamUrl(executionId));
    esRef.current = es;

    es.addEventListener("ready", () => {
      setConectado(true);
    });

    es.addEventListener("siafi", (e: MessageEvent) => {
      try {
        const evt: SiafiEvent = JSON.parse(e.data);

        if (evt.type === "update") {
          const acao   = evt.acao   ?? "";
          const estado = evt.estado ?? "";
          const linhas = evt.tela   ?? [];
          setAcao(acao);
          setEstado(estado);
          if (linhas.length > 0) setTela(linhas);
          if (acao) {
            setLog((prev) => [...prev, { acao, estado, ts: Date.now() }]);
          }
        }

        if (evt.type === "resultado") {
          const res = { ok: !!evt.ok, mensagem: evt.mensagem ?? "" };
          setConcluido(res);
          onConcluidoRef.current?.(res);
          if (evt.tela && (evt.tela as string[]).length > 0) {
            setTela(evt.tela as string[]);
          }
        }
      } catch {
        // ignora JSON inválido
      }
    });

    es.addEventListener("done", () => {
      es.close();
    });

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [executionId]);

  if (!executionId) return null;

  const emExecucao = conectado && !concluido;

  return (
    <GlassCard className={cn("overflow-hidden", className)}>
      {/* ── Cabeçalho ── */}
      <div className="flex items-center gap-2.5 border-b border-glass-border px-4 py-2.5">
        <Terminal className="h-4 w-4 text-green-400 shrink-0" />
        <span className="text-xs font-semibold text-foreground/80 tracking-wide">
          SIAFI Terminal 3270
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground font-mono">
          {labelEstado(estadoAtual)}
        </span>
        {/* Indicador de conexão */}
        <span
          className={cn(
            "h-2 w-2 rounded-full shrink-0",
            emExecucao  ? "bg-green-400 animate-pulse" :
            concluido?.ok === false ? "bg-red-400" :
            concluido?.ok === true  ? "bg-green-400" :
            "bg-muted",
          )}
        />
      </div>

      {/* ── Tela 3270 ── */}
      <div
        className="bg-black px-4 py-3 overflow-x-auto overflow-y-auto"
        style={{ minHeight: 360, maxHeight: 520 }}
      >
        {tela.length === 0 ? (
          <div className="flex items-center gap-2 text-green-400/50 font-mono text-[11px] pt-2">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>Aguardando resposta do mainframe...</span>
          </div>
        ) : (
          tela.map((linha, i) => (
            <TerminalLine key={i} linha={linha} idx={i} />
          ))
        )}
      </div>

      {/* ── Ação atual ── */}
      <div className="border-t border-glass-border px-4 py-2 flex items-center gap-2 bg-black/30">
        {emExecucao ? (
          <Loader2 className="h-3.5 w-3.5 text-green-400 animate-spin shrink-0" />
        ) : concluido?.ok ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
        ) : concluido ? (
          <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
        ) : (
          <span className="h-3.5 w-3.5 shrink-0" />
        )}
        <span className="text-[11px] font-mono text-green-300/80 truncate">
          {concluido ? concluido.mensagem : acaoAtual}
        </span>
      </div>

      {/* ── Log de etapas ── */}
      {log.length > 0 && (
        <div
          className="border-t border-glass-border px-4 py-2 space-y-0.5 overflow-y-auto"
          style={{ maxHeight: 120 }}
        >
          {log.map((entry, i) => {
            const isLast = i === log.length - 1;
            return (
              <div
                key={entry.ts}
                className={cn(
                  "flex items-start gap-2 text-[10px] font-mono",
                  isLast ? "text-green-300/90" : "text-muted-foreground/60",
                )}
              >
                <span className="mt-0.5 shrink-0 text-green-500/60">›</span>
                <span className="leading-snug">{entry.acao}</span>
              </div>
            );
          })}
          <div ref={logEndRef} />
        </div>
      )}
    </GlassCard>
  );
}
