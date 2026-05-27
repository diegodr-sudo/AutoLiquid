"use client";

import { useState } from "react";
import { Chrome, Loader2 } from "lucide-react";
import { GlassButton } from "@/components/glass-card";
import { UploadZone } from "@/components/upload-zone";
import { openSiafiIncognito } from "@/lib/data";

interface SiafiPreenchimentoPanelProps {
  apiDisponivel: boolean;
}

export function SiafiPreenchimentoPanel({ apiDisponivel }: SiafiPreenchimentoPanelProps) {
  const [abrindoSiafi, setAbrindoSiafi] = useState(false);
  const [erro, setErro] = useState("");

  const handleAbrirSiafi = async () => {
    setAbrindoSiafi(true);
    setErro("");
    try {
      await openSiafiIncognito();
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível abrir o SIAFI.");
    } finally {
      setAbrindoSiafi(false);
    }
  };

  return (
    <>
      <UploadZone
        onFileSelect={() => setErro("")}
        acceptedFormats={[".pdf", ".xlsx", ".xls", ".csv"]}
        title="Arraste o PDF ou planilha para SIAFI aqui"
        description="ou clique para selecionar"
        compact
        disabled={!apiDisponivel}
        disabledMessage={
          !apiDisponivel
            ? "A seleção foi desativada porque a API web não está respondendo."
            : undefined
        }
      />

      <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="min-h-5 min-w-0">
          {erro ? (
            <p className="max-w-xl text-sm text-destructive">{erro}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              A extração para SIAFI será configurada depois; por enquanto use o atalho para abrir o SIAFI.
            </p>
          )}
        </div>

        <GlassButton
          variant="secondary"
          size="lg"
          onClick={() => void handleAbrirSiafi()}
          disabled={abrindoSiafi || !apiDisponivel}
          className="w-full md:w-auto"
          title="Abrir SIAFI em aba anônima do Chrome"
        >
          {abrindoSiafi ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Chrome className="h-5 w-5" />
          )}
          {abrindoSiafi ? "Abrindo..." : "Abrir SIAFI"}
        </GlassButton>
      </div>
    </>
  );
}
