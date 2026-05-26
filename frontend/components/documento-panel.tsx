"use client";

import { AlertTriangle, BadgeCheck, ShieldAlert } from "lucide-react";
import { GlassCard, GlassPanel } from "./glass-card";
import type { Documento, ResumoFinanceiro } from "@/lib/data";

interface DocumentoPanelProps {
  documento: Documento;
  resumo: ResumoFinanceiro;
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

export function DocumentoPanel({ documento, resumo: _resumo }: DocumentoPanelProps) {
  const alertasExibidos = (documento.alertas ?? []).filter(
    (alerta) => !String(alerta).toLowerCase().includes("simples nacional")
  );
  const processo = documento.processo?.trim() || "—";
  const cnpj = formatCnpj(documento.cnpj || "—");
  const solPagamento = documento.solPagamento?.trim() || "—";
  const contrato = documento.contrato?.trim() || "—";

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
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                documento.optanteSimples
                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
                  : "border-amber-500/25 bg-amber-500/10 text-amber-700"
              }`}
            >
              {documento.optanteSimples ? (
                <BadgeCheck className="h-3 w-3" />
              ) : (
                <ShieldAlert className="h-3 w-3" />
              )}
              {documento.optanteSimples ? "Optante" : "Não optante"}
            </span>
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
