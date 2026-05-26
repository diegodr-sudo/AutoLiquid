"use client";

import { ExternalLink, Loader2 } from "lucide-react";
import { useState } from "react";

const API = "http://127.0.0.1:8000";

async function abrirPortalIss(portal: string) {
  const response = await fetch(`${API}/api/iss/abrir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ portal }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Não foi possível abrir o portal.");
  }
}

const MUNICIPIOS = [
  { id: "curitibanos", nome: "Curitibanos" },
  { id: "ararangua", nome: "Araranguá" },
  { id: "barra-do-sul", nome: "Balneário Barra do Sul" },
  { id: "gov-celso-ramos", nome: "Gov. Celso Ramos" },
] as const;

export function IssPortais() {
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [erro, setErro] = useState("");

  const handleAbrir = async (portal: string) => {
    setAbrindo(portal);
    setErro("");
    try {
      await abrirPortalIss(portal);
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível abrir o portal.");
    } finally {
      setAbrindo(null);
    }
  };

  return (
    <div className="rounded-2xl border border-glass-border/70 bg-background/55 p-4">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Portais ISS Municipal
      </p>
      <div className="flex flex-wrap gap-2">
        {MUNICIPIOS.map(({ id, nome }) => (
          <button
            key={nome}
            type="button"
            onClick={() => void handleAbrir(id)}
            disabled={Boolean(abrindo)}
            className="flex items-center gap-1.5 rounded-xl border border-glass-border bg-background/60 px-3 py-2 text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
          >
            {abrindo === id ? (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
            ) : (
              <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            )}
            {nome}
          </button>
        ))}
      </div>
      {erro ? (
        <p className="mt-3 rounded-xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {erro}
        </p>
      ) : null}
    </div>
  );
}
