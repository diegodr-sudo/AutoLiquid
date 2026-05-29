"use client";

import { useRef, useState } from "react";
import { Bug, Loader2, CheckCircle2 } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { GlassButton } from "@/components/glass-card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { enviarBugReport, fetchChromeAbaAtual, type EnviarBugReportPayload } from "@/lib/data";

interface BugReportButtonProps {
  /** Contexto do app passado pela página (estado React, arquivo, datas etc.) */
  contexto?: Record<string, unknown>;
  versaoApp?: string;
  servidorNome?: string;
}

// ── Helpers de visibilidade ───────────────────────────────────────────────────

function eVisivel(el: Element): boolean {
  const rect = el.getBoundingClientRect();
  const estilo = window.getComputedStyle(el as HTMLElement);
  return (
    rect.width > 0 &&
    rect.height > 0 &&
    estilo.visibility !== "hidden" &&
    estilo.display !== "none" &&
    estilo.opacity !== "0"
  );
}

// ── Label associado a um input ────────────────────────────────────────────────

function labelDeInput(el: HTMLElement): string {
  // 1. label[for=id]
  if (el.id) {
    const lbl = document.querySelector<HTMLLabelElement>(`label[for="${el.id}"]`);
    if (lbl) return lbl.textContent?.trim() ?? "";
  }
  // 2. aria-label
  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel) return ariaLabel.trim();
  // 3. aria-labelledby
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const txt = labelledBy
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
      .filter(Boolean)
      .join(" ");
    if (txt) return txt;
  }
  // 4. label pai (wrapping)
  const parentLabel = el.closest("label");
  if (parentLabel) {
    const clone = parentLabel.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("input,select,textarea").forEach((n) => n.remove());
    const txt = clone.textContent?.trim() ?? "";
    if (txt) return txt;
  }
  // 5. Elemento irmão anterior visível (td antes do input, p antes do campo)
  let sib = el.previousElementSibling as HTMLElement | null;
  while (sib) {
    if (eVisivel(sib)) {
      const txt = sib.textContent?.trim() ?? "";
      if (txt && txt.length > 0 && txt.length < 80) return txt;
    }
    sib = sib.previousElementSibling as HTMLElement | null;
  }
  // 6. th/td antes (tabelas de formulário)
  const td = el.closest("td");
  if (td) {
    const tdAnterior = td.previousElementSibling;
    if (tdAnterior) {
      const txt = tdAnterior.textContent?.trim() ?? "";
      if (txt && txt.length < 80) return txt;
    }
  }
  // 7. Fallback: name → id → placeholder → tagName
  return (
    el.getAttribute("name") ||
    el.getAttribute("id") ||
    el.getAttribute("placeholder") ||
    el.tagName.toLowerCase()
  );
}

// ── Captura completa do estado do app (DOM local) ─────────────────────────────

function capturarEstadoApp(): Record<string, string> {
  try {
    const campos: Record<string, string> = {};

    // URL e título da página do app
    campos["__url_app"] = window.location.href;
    campos["__titulo_pagina"] = document.title;

    // Campos de formulário com label real
    const seletores =
      "input:not([type=hidden]):not([type=password]):not([type=submit]):not([type=button]):not([type=image]):not([type=reset]):not([type=checkbox]):not([type=radio])," +
      "input[type=checkbox]:checked," +
      "input[type=radio]:checked," +
      "select, textarea";

    document
      .querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(seletores)
      .forEach((el) => {
        if (!eVisivel(el)) return;

        const chave = labelDeInput(el).slice(0, 80);
        let valor = "";

        if (el instanceof HTMLSelectElement) {
          const opt = el.options[el.selectedIndex];
          valor = opt
            ? `${el.value}${opt.text && opt.text !== el.value ? ` (${opt.text})` : ""}`
            : el.value;
        } else if (el instanceof HTMLInputElement && (el.type === "checkbox" || el.type === "radio")) {
          valor = el.checked ? `[marcado] ${el.value || el.id}` : "";
        } else {
          valor = el.value ?? "";
        }

        if (chave && valor && valor.trim() !== "") {
          // Ignora se o valor é idêntico ao placeholder (campo vazio com placeholder visível)
          const placeholder = el.getAttribute("placeholder") ?? "";
          if (valor === placeholder) return;
          campos[chave] = valor.slice(0, 300);
        }
      });

    // Mensagens de status/erro visíveis no app
    document
      .querySelectorAll<HTMLElement>(
        "[data-status], [role='alert'], [aria-live='polite'], [aria-live='assertive']"
      )
      .forEach((el, i) => {
        if (!eVisivel(el)) return;
        const txt = el.textContent?.trim() ?? "";
        if (txt && txt.length > 3 && txt.length < 400) {
          campos[`__alerta_${i}`] = txt;
        }
      });

    return campos;
  } catch {
    return {};
  }
}

// ── Componente ────────────────────────────────────────────────────────────────

export function BugReportButton({ contexto, versaoApp, servidorNome }: BugReportButtonProps) {
  const [aberto, setAberto] = useState(false);
  const [descricao, setDescricao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [erro, setErro] = useState("");
  const [capturandoChrome, setCapturandoChrome] = useState(false);

  const estadoAppRef = useRef<Record<string, string>>({});
  const chromeEstadoRef = useRef<Record<string, unknown>>({});

  async function handleAbrir(open: boolean) {
    if (open) {
      setEnviado(false);
      setErro("");
      setDescricao("");

      // Captura DOM do app imediatamente (síncrono)
      estadoAppRef.current = capturarEstadoApp();

      // Captura estado do Chrome em background (não bloqueia a abertura do popover)
      setCapturandoChrome(true);
      fetchChromeAbaAtual()
        .then((resultado) => {
          chromeEstadoRef.current = resultado as Record<string, unknown>;
        })
        .catch(() => {
          chromeEstadoRef.current = { erro: "Chrome inacessível." };
        })
        .finally(() => setCapturandoChrome(false));
    }
    setAberto(open);
  }

  async function handleEnviar() {
    const descricaoTrimada = descricao.trim();
    if (!descricaoTrimada) {
      setErro("Descreva o problema antes de enviar.");
      return;
    }
    setEnviando(true);
    setErro("");
    try {
      const payload: EnviarBugReportPayload = {
        pagina: typeof window !== "undefined" ? window.location.pathname : "",
        descricao: descricaoTrimada,
        contexto: {
          // Contexto do React (passado pela página)
          ...(contexto ?? {}),
          // Estado do Chrome (URL, campos do Comprasnet, erros da página)
          chrome: chromeEstadoRef.current,
        },
        camposDom: estadoAppRef.current,
        versaoApp: versaoApp ?? "",
        servidorNome: servidorNome ?? "",
      };
      await enviarBugReport(payload);
      setEnviado(true);
      setDescricao("");
      setTimeout(() => setAberto(false), 1800);
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao enviar. Tente novamente.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Popover open={aberto} onOpenChange={(open) => void handleAbrir(open)}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <GlassButton
              variant="ghost"
              size="sm"
              aria-label="Reportar bug"
              className="text-muted-foreground hover:text-destructive"
            >
              <Bug className="h-4 w-4" />
            </GlassButton>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>Reportar um problema</TooltipContent>
      </Tooltip>

      <PopoverContent
        side="bottom"
        align="end"
        className="w-72 p-3"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        {enviado ? (
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <CheckCircle2 className="h-7 w-7 text-emerald-500" />
            <p className="text-sm font-medium text-foreground">Relatório enviado!</p>
            <p className="text-xs text-muted-foreground">Obrigado. Vamos verificar em breve.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <p className="text-sm font-semibold text-foreground">Reportar problema</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {capturandoChrome
                  ? "Capturando estado do Chrome…"
                  : "Contexto do app e do Chrome capturados automaticamente."}
              </p>
            </div>

            <textarea
              rows={4}
              value={descricao}
              onChange={(e) => {
                setDescricao(e.target.value);
                setErro("");
              }}
              placeholder="Descreva o que aconteceu..."
              className="w-full resize-none rounded-lg border border-glass-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
              disabled={enviando}
              autoFocus
            />

            {erro && (
              <p className="text-xs text-destructive">{erro}</p>
            )}

            <GlassButton
              variant="primary"
              size="sm"
              className="w-full justify-center"
              onClick={() => void handleEnviar()}
              disabled={enviando || !descricao.trim()}
            >
              {enviando ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Enviando…
                </>
              ) : (
                "Enviar relatório"
              )}
            </GlassButton>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
