"use client";

import { useState } from "react";
import { Chrome, FileUp, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { GlassButton } from "@/components/glass-card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { UploadZone } from "@/components/upload-zone";
import { openSiafiIncognito, uploadPDF, type ProcessDates } from "@/lib/data";

interface SiafiPreenchimentoPanelProps {
  apiDisponivel: boolean;
  dates: ProcessDates;
}

export function SiafiPreenchimentoPanel({ apiDisponivel, dates }: SiafiPreenchimentoPanelProps) {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [processando, setProcessando] = useState(false);
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

  const handleProcessar = async (fileOverride?: File | null) => {
    const arquivo = fileOverride ?? selectedFile;
    if (!arquivo || processando) return;

    setProcessando(true);
    setErro("");
    try {
      const result = await uploadPDF(arquivo, dates);
      if (result.success && result.documentoId) {
        router.push(`/conferencia?id=${encodeURIComponent(result.documentoId)}`);
        return;
      }
      setErro(result.mensagem || "Não foi possível processar o documento.");
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Erro ao processar o documento.");
    } finally {
      setProcessando(false);
    }
  };

  return (
    <>
      <UploadZone
        onFileSelect={(file, source) => {
          setErro("");
          setSelectedFile(file);
          if (file && source !== "clear") {
            void handleProcessar(file);
          }
        }}
        acceptedFormats={[".pdf"]}
        title="Arraste o PDF da liquidação SIAFI aqui"
        description="para bolsa, a próxima tela recebe as remessas"
        compact
        disabled={!apiDisponivel || processando}
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
              Envie a liquidação; se for bolsa, confira as remessas e bolsistas na próxima tela.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2 sm:flex-row md:justify-end">
          <GlassButton
            variant="secondary"
            size="lg"
            onClick={() => void handleProcessar()}
            disabled={!selectedFile || processando || !apiDisponivel}
            className="w-full md:w-auto"
          >
            {processando ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <FileUp className="h-5 w-5" />
            )}
            {processando ? "Processando..." : "Processar"}
          </GlassButton>
          <Tooltip>
            <TooltipTrigger asChild>
              <GlassButton
                variant="secondary"
                size="lg"
                onClick={() => void handleAbrirSiafi()}
                disabled={abrindoSiafi || !apiDisponivel}
                className="w-full md:w-auto"
              >
                {abrindoSiafi ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Chrome className="h-5 w-5" />
                )}
                {abrindoSiafi ? "Abrindo..." : "Abrir SIAFI"}
              </GlassButton>
            </TooltipTrigger>
            <TooltipContent>Abrir SIAFI em aba anônima do Chrome</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </>
  );
}
