"use client";

import { useRef, useState } from "react";
import { Upload, FileText, X } from "lucide-react";
import { GlassCard } from "./glass-card";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  onFileSelect?: (file: File | null, source: "drop" | "input" | "clear") => void;
  acceptedFormats?: string[];
  disabled?: boolean;
  disabledMessage?: string;
  compact?: boolean;
}

export function UploadZone({
  onFileSelect,
  acceptedFormats = [".pdf"],
  disabled = false,
  disabledMessage,
  compact = false,
}: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [erroArquivo, setErroArquivo] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const validarArquivo = (file: File | null, source: "drop" | "input") => {
    if (!file) {
      setSelectedFile(null);
      setErroArquivo("");
      onFileSelect?.(null, "clear");
      return;
    }

    const nomeValido = file.name.toLowerCase().endsWith(".pdf");
    const tipoValido = file.type === "application/pdf";
    if (!nomeValido && !tipoValido) {
      setSelectedFile(null);
      setErroArquivo("Selecione um arquivo PDF válido.");
      onFileSelect?.(null, "clear");
      return;
    }

    setErroArquivo("");
    setSelectedFile(file);
    onFileSelect?.(file, source);
  };

  const abrirSeletor = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (disabled) return;
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (disabled) return;
    const arquivos = Array.from(e.dataTransfer.files ?? []);
    const pdf = arquivos.find((file) => file.name.toLowerCase().endsWith(".pdf")) ?? arquivos[0] ?? null;
    validarArquivo(pdf, "drop");
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    validarArquivo(e.target.files?.[0] ?? null, "input");
    e.target.value = "";
  };

  const handleRemoveFile = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setSelectedFile(null);
    setErroArquivo("");
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    onFileSelect?.(null, "clear");
  };

  return (
    <GlassCard className={compact ? "p-4" : "p-6"}>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={!selectedFile ? abrirSeletor : undefined}
        onKeyDown={
          !selectedFile
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  abrirSeletor();
                }
              }
            : undefined
        }
        role={!selectedFile ? "button" : undefined}
        tabIndex={!selectedFile && !disabled ? 0 : -1}
        aria-disabled={disabled}
        className={cn(
          "relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-all duration-300",
          compact ? "min-h-[180px] p-5" : "min-h-[260px] p-8",
          !selectedFile && !disabled && "cursor-pointer",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-glass-border hover:border-primary/50",
          selectedFile && "border-success/50 bg-success/5",
          disabled && "cursor-not-allowed opacity-60 hover:border-glass-border"
        )}
      >
        {selectedFile ? (
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <div className="flex items-center gap-3 rounded-lg bg-secondary/50 px-4 py-2">
              <FileText className="h-5 w-5 text-success" />
              <span className="text-sm text-foreground">{selectedFile.name}</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={abrirSeletor}
                className="rounded-lg border border-glass-border px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-secondary/50"
              >
                Trocar arquivo
              </button>
              <button
                type="button"
                onClick={handleRemoveFile}
                className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-destructive/20 hover:text-destructive"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className={cn("rounded-full bg-secondary/50", compact ? "mb-3 p-3" : "mb-4 p-4")}>
              <Upload className={cn("text-muted-foreground", compact ? "h-5 w-5" : "h-6 w-6")} />
            </div>
            <p className={cn("text-center text-foreground", compact ? "mb-1 text-sm font-medium" : "mb-1 text-sm")}>
              Arraste o PDF da Liquidação aqui
            </p>
            <p className={cn("text-center text-muted-foreground", compact ? "mb-3 text-sm" : "mb-4 text-sm")}>
              ou clique para selecionar
            </p>
            <p className="text-xs text-muted-foreground">
              Formato aceito: {acceptedFormats.join(", ")}
            </p>
          </>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={acceptedFormats.join(",")}
          onChange={handleFileInput}
          disabled={disabled}
          className="hidden"
        />
      </div>

      {(erroArquivo || disabledMessage) && (
        <p className={cn("mt-3 text-sm", erroArquivo ? "text-destructive" : "text-muted-foreground")}>
          {erroArquivo || disabledMessage}
        </p>
      )}
    </GlassCard>
  );
}
