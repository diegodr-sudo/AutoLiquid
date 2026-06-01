"use client";

import { ExternalLink, Loader2, Settings2, X, Eye, EyeOff, Save, Trash2, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { GlobalScopeIcon } from "@/components/global-scope-icon";

const API = "http://127.0.0.1:8000";

export interface PortalConfig {
  id: string;
  nome: string;
  url: string;
  login: string;
  senha: string;
  codigo: string; // código DOB001 associado (ex: "8093")
}

async function fetchPortais(): Promise<PortalConfig[]> {
  const res = await fetch(`${API}/api/iss/portais`);
  if (!res.ok) throw new Error("Não foi possível carregar os portais.");
  const data = await res.json();
  return (data.portais as PortalConfig[]).filter((p) => p.id !== "global");
}

async function savePortais(portais: PortalConfig[]): Promise<void> {
  const res = await fetch(`${API}/api/iss/portais`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ portais }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || "Não foi possível salvar.");
  }
}

async function abrirPortal(portalId: string): Promise<void> {
  const res = await fetch(`${API}/api/iss/abrir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ portal: portalId }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail || "Não foi possível abrir o portal.");
  }
}

function gerarId(): string {
  return "portal-" + Math.random().toString(36).slice(2, 9);
}

// ─── Modal de configurações ────────────────────────────────────────────────

function SettingsModal({
  portais,
  onClose,
  onSaved,
}: {
  portais: PortalConfig[];
  onClose: () => void;
  onSaved: (updated: PortalConfig[]) => void;
}) {
  const [draft, setDraft] = useState<PortalConfig[]>(portais.map((p) => ({ ...p })));
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState("");
  const [senhasVisiveis, setSenhasVisiveis] = useState<Record<string, boolean>>({});
  const overlayRef = useRef<HTMLDivElement>(null);

  const toggleSenha = (id: string) =>
    setSenhasVisiveis((prev) => ({ ...prev, [id]: !prev[id] }));

  const updateField = (id: string, field: keyof PortalConfig, value: string) =>
    setDraft((prev) => prev.map((p) => (p.id === id ? { ...p, [field]: value } : p)));

  const remover = (id: string) =>
    setDraft((prev) => prev.filter((p) => p.id !== id));

  const adicionar = () =>
    setDraft((prev) => [
      ...prev,
      { id: gerarId(), nome: "", url: "", login: "", senha: "", codigo: "" },
    ]);

  const handleSave = async () => {
    setSaving(true);
    setErro("");
    try {
      await savePortais(draft);
      onSaved(draft);
      onClose();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao salvar.");
    } finally {
      setSaving(false);
    }
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === overlayRef.current) onClose();
  };

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    >
      <div className="relative mx-4 w-full max-w-3xl rounded-2xl border border-glass-border bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-glass-border px-6 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-foreground">Portais ISS Municipal</h2>
              <GlobalScopeIcon label="Global" />
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-4 shrink-0 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tabela */}
        <div className="overflow-x-auto px-6 py-4">
          <table className="w-full border-separate border-spacing-y-2 text-sm">
            <thead>
              <tr className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                <th className="pb-1 text-left">Portal</th>
                <th className="pb-1 pl-3 text-left">URL</th>
                <th className="pb-1 pl-3 text-left">Login</th>
                <th className="pb-1 pl-3 text-left">Senha</th>
                <th className="pb-1 pl-3 text-left">Cód. DOB001</th>
                <th className="pb-1 pl-3" />
              </tr>
            </thead>
            <tbody>
              {draft.map((portal) => (
                <tr key={portal.id}>
                  <td className="pr-2">
                    <input
                      type="text"
                      value={portal.nome}
                      onChange={(e) => updateField(portal.id, "nome", e.target.value)}
                      placeholder="Nome"
                      className="w-full min-w-[110px] rounded-lg border border-glass-border bg-background/60 px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/50 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/20"
                    />
                  </td>
                  <td className="pl-3">
                    <input
                      type="url"
                      value={portal.url}
                      onChange={(e) => updateField(portal.id, "url", e.target.value)}
                      placeholder="https://..."
                      className="w-full min-w-[150px] rounded-lg border border-glass-border bg-background/60 px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/50 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/20"
                    />
                  </td>
                  <td className="pl-3">
                    <input
                      type="text"
                      value={portal.login}
                      onChange={(e) => updateField(portal.id, "login", e.target.value)}
                      placeholder="usuário / CNPJ"
                      className="w-full min-w-[110px] rounded-lg border border-glass-border bg-background/60 px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/50 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/20"
                    />
                  </td>
                  <td className="pl-3">
                    <div className="relative flex items-center">
                      <input
                        type={senhasVisiveis[portal.id] ? "text" : "password"}
                        value={portal.senha}
                        onChange={(e) => updateField(portal.id, "senha", e.target.value)}
                        placeholder="••••••••"
                        className="w-full min-w-[110px] rounded-lg border border-glass-border bg-background/60 py-1.5 pl-2.5 pr-8 text-xs text-foreground placeholder:text-muted-foreground/50 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/20"
                      />
                      <button
                        type="button"
                        onClick={() => toggleSenha(portal.id)}
                        className="absolute right-2 text-muted-foreground/60 hover:text-muted-foreground"
                      >
                        {senhasVisiveis[portal.id] ? (
                          <EyeOff className="h-3.5 w-3.5" />
                        ) : (
                          <Eye className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </td>
                  <td className="pl-3">
                    <input
                      type="text"
                      value={portal.codigo}
                      onChange={(e) => updateField(portal.id, "codigo", e.target.value)}
                      placeholder="ex: 8093"
                      className="w-full min-w-[80px] rounded-lg border border-glass-border bg-background/60 px-2.5 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/20"
                    />
                  </td>
                  <td className="pl-2">
                    <button
                      type="button"
                      onClick={() => remover(portal.id)}
                      className="rounded-lg p-1.5 text-muted-foreground/50 transition-colors hover:bg-destructive/10 hover:text-destructive"
                      title="Remover portal"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <button
            type="button"
            onClick={adicionar}
            className="mt-1 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
            Adicionar portal
          </button>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-glass-border px-6 py-4">
          {erro ? (
            <p className="text-xs text-destructive">{erro}</p>
          ) : (
            <p className="text-xs text-muted-foreground">
              O código DOB001 vincula o portal ao bloqueio "LF obrigatória" nas pendências do Registro automaticamente.
            </p>
          )}
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-4 py-2 text-xs font-semibold text-primary transition-colors hover:bg-primary/15 disabled:opacity-60"
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" />
            )}
            {saving ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Componente principal ──────────────────────────────────────────────────

export function IssPortais() {
  const [portais, setPortais] = useState<PortalConfig[]>([]);
  const [abrindo, setAbrindo] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  const [modalAberto, setModalAberto] = useState(false);

  const carregarPortais = useCallback(async () => {
    try {
      const data = await fetchPortais();
      setPortais(data);
    } catch {
      // silencioso
    }
  }, []);

  useEffect(() => {
    void carregarPortais();
  }, [carregarPortais]);

  const handleAbrir = async (portalId: string) => {
    setAbrindo(portalId);
    setErro("");
    try {
      await abrirPortal(portalId);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível abrir o portal.");
    } finally {
      setAbrindo(null);
    }
  };

  const portaisVisiveis = portais.filter((p) => p.url.trim() !== "");

  return (
    <>
      <div className="rounded-2xl border border-glass-border/70 bg-background/55 p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Portais ISS Municipal
          </p>
          <button
            type="button"
            onClick={() => setModalAberto(true)}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            title="Configurar portais"
          >
            <Settings2 className="h-3.5 w-3.5" />
            Ajustes
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          {portaisVisiveis.map(({ id, nome }) => (
            <button
              key={id}
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

          {portaisVisiveis.length === 0 && (
            <p className="text-xs text-muted-foreground">
              Nenhum portal configurado. Clique em Ajustes para adicionar.
            </p>
          )}
        </div>

        {erro ? (
          <p className="mt-3 rounded-xl border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {erro}
          </p>
        ) : null}
      </div>

      {modalAberto && (
        <SettingsModal
          portais={portais}
          onClose={() => setModalAberto(false)}
          onSaved={(updated) => setPortais(updated)}
        />
      )}
    </>
  );
}
