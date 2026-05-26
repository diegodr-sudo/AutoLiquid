"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { GlassButton } from "@/components/glass-card";

const API = "http://127.0.0.1:8000";

function mascaraCnpj(v: string) {
  const d = v.replace(/\D/g, "").slice(0, 14);
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2}\.\d{3})(\d)/, "$1.$2")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}

type Estado =
  | { tipo: "idle" }
  | { tipo: "loading" }
  | { tipo: "pdf"; status: "preenchido" | "gerado" | "acionado"; mensagem: string; arquivo?: string }
  | { tipo: "erro"; mensagem: string };

interface CnpjCheckerProps {
  cnpjInicial?: string;
}

export function CnpjChecker({ cnpjInicial = "" }: CnpjCheckerProps) {
  const [cnpj, setCnpj] = useState("");
  const [estado, setEstado] = useState<Estado>({ tipo: "idle" });
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Limpa timer ao desmontar
  useEffect(() => () => { if (retryTimerRef.current) clearTimeout(retryTimerRef.current); }, []);

  useEffect(() => {
    const limpo = cnpjInicial.replace(/\D/g, "");
    if (limpo.length !== 14) return;
    setCnpj(mascaraCnpj(limpo));
    setEstado({ tipo: "idle" });
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, [cnpjInicial]);

  const gerarPdf = async () => {
    const limpo = cnpj.replace(/\D/g, "");
    if (limpo.length !== 14) {
      setEstado({ tipo: "erro", mensagem: "Informe os 14 dígitos do CNPJ." });
      return;
    }

    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }

    setEstado({ tipo: "loading" });

    try {
      const res = await fetch(`${API}/api/simples/gerar-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cnpj: limpo }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.detail || `Erro ao gerar PDF (HTTP ${res.status}).`);
      }
      setEstado({
        tipo: "pdf",
        status: body.status ?? "preenchido",
        mensagem: body.mensagem ?? "Solicitação enviada ao site da Receita.",
        arquivo: body.arquivo,
      });
    } catch (e) {
      const msg =
        e instanceof TypeError && e.message.includes("fetch")
          ? "Servidor indisponível — reinicie o AutoLiquid."
          : e instanceof Error
          ? e.message
          : "Erro ao gerar PDF.";
      setEstado({ tipo: "erro", mensagem: msg });
    }
  };

  const carregando = estado.tipo === "loading";

  return (
    <div className="rounded-2xl border border-glass-border/70 bg-background/55 p-4">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        PDF Receita / Simples
      </p>

      <div className="flex gap-2">
        <input
          value={cnpj}
          onChange={(e) => {
            setCnpj(mascaraCnpj(e.target.value));
            setEstado({ tipo: "idle" });
            if (retryTimerRef.current) {
              clearTimeout(retryTimerRef.current);
              retryTimerRef.current = null;
            }
          }}
          onKeyDown={(e) => e.key === "Enter" && void gerarPdf()}
          placeholder="00.000.000/0000-00"
          className="flex-1 rounded-xl border border-glass-border bg-background/80 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 font-mono tracking-wider"
          disabled={carregando}
        />
        <GlassButton
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => void gerarPdf()}
          disabled={carregando}
          className="shrink-0"
        >
          {carregando ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
          {carregando ? "Preparando…" : "Gerar PDF"}
        </GlassButton>
      </div>

      <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
        Ao clicar em um CNPJ ou credor na fila, este campo é preenchido automaticamente. O PDF baixado é o oficial da Receita, com consulta em segundo plano sempre que a Receita permitir.
      </p>

      {estado.tipo === "erro" && (
        <p className="mt-2 text-xs text-destructive">{estado.mensagem}</p>
      )}

      {estado.tipo === "pdf" && (
        <div className="mt-3 rounded-xl border border-glass-border/60 bg-secondary/20 px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-foreground">
            {estado.status === "gerado" ? "PDF gerado." : "Consulta preparada."}
          </span>{" "}
          {estado.mensagem}
        </div>
      )}
    </div>
  );
}
