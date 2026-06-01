"use client";

import { AlertTriangle, BadgeCheck, Loader2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { GlassCard, GlassPanel } from "./glass-card";
import { SimpleTooltip } from "@/components/ui/simple-tooltip";
import type { Documento, ResumoFinanceiro } from "@/lib/data";

const API = "http://127.0.0.1:8000";

async function gerarPdfSimples(cnpjLimpo: string): Promise<void> {
  const res = await fetch(`${API}/api/simples/gerar-pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cnpj: cnpjLimpo, downloadOnly: false }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || "Erro ao gerar PDF.");
  }
}

interface DocumentoPanelProps {
  documento: Documento;
  resumo: ResumoFinanceiro;
  /** Suprime o badge "Optante/Não optante" quando não é relevante (bolsa, entidade federal). */
  hideOptanteSimples?: boolean;
}

function formatCnpj(cnpj: string): string {
  const digits = String(cnpj || "").replace(/\D/g, "");
  if (digits.length >= 14) {
    const d = digits.slice(0, 14);
    return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
  }
  return cnpj;
}

function InfoRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="min-w-0 space-y-0.5">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <p className={highlight ? "break-words font-medium text-primary" : "break-words text-sm text-foreground"}>{value}</p>
    </div>
  );
}

export function DocumentoPanel({ documento, resumo: _resumo, hideOptanteSimples = false }: DocumentoPanelProps) {
  const [gerandoPdf, setGerandoPdf] = useState(false);
  const [pdfErro, setPdfErro] = useState("");

  const alertasExibidos = (documento.alertas ?? []).filter(
    (alerta) => !String(alerta).toLowerCase().includes("simples nacional")
  );
  const processo = documento.processo?.trim() || "—";
  const cnpj = formatCnpj(documento.cnpj || "—");
  const cnpjLimpo = String(documento.cnpj || "").replace(/\D/g, "");
  const solPagamento = documento.solPagamento?.trim() || "—";
  const contrato = documento.contrato?.trim() || "—";

  const handleGerarPdf = async () => {
    if (cnpjLimpo.length !== 14 || gerandoPdf) return;
    setGerandoPdf(true);
    setPdfErro("");
    try {
      await gerarPdfSimples(cnpjLimpo);
    } catch (e) {
      setPdfErro(e instanceof Error ? e.message : "Erro ao gerar PDF.");
    } finally {
      setGerandoPdf(false);
    }
  };

  return (
    <GlassCard className="p-6 md:p-7">
      <h3 className="mb-5 text-xs font-medium uppercase tracking-wider text-primary">
        Documento
      </h3>

      <div className="grid gap-5">
        <InfoRow label="Processo" value={processo} />
        <div className="min-w-0 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wider text-muted-foreground">CNPJ</span>
            {!hideOptanteSimples && (
              <SimpleTooltip
                content={
                  documento.optanteSimples
                    ? "Optante pelo Simples Nacional"
                    : "Não optante pelo Simples Nacional — clique para gerar PDF da Receita"
                }
                side="top"
              >
                <button
                  type="button"
                  onClick={() => void handleGerarPdf()}
                  disabled={gerandoPdf || cnpjLimpo.length !== 14}
                  className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-60 ${
                    documento.optanteSimples
                      ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
                      : "border-amber-500/25 bg-amber-500/10 text-amber-700"
                  }`}
                >
                  {gerandoPdf ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : documento.optanteSimples ? (
                    <BadgeCheck className="h-3 w-3" />
                  ) : (
                    <ShieldAlert className="h-3 w-3" />
                  )}
                  {documento.optanteSimples ? "Optante" : "Não optante"}
                </button>
              </SimpleTooltip>
            )}
            {pdfErro && (
              <span className="text-[10px] text-destructive">{pdfErro}</span>
            )}
          </div>
          <p className="mt-1 break-all text-sm leading-6 text-foreground">{cnpj}</p>
          {documento.nomeCredor ? (
            <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">{documento.nomeCredor}</p>
          ) : null}
        </div>
        <InfoRow label="Sol. Pagamento" value={solPagamento} />
        <InfoRow label="Contrato" value={contrato} />

        {alertasExibidos.length > 0 && (
          <GlassPanel className="border-warning/30 bg-warning/10">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-warning" />
              <div className="space-y-1">
                {alertasExibidos.map((alerta, i) => (
                  <p key={i} className="text-xs text-warning">
                    {alerta}
                  </p>
                ))}
              </div>
            </div>
          </GlassPanel>
        )}
      </div>
    </GlassCard>
  );
}
