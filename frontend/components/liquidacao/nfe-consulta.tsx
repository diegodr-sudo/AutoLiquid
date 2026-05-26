"use client";

import { useRef, useState } from "react";
import { Bug, FileText, Key, Loader2, Paperclip, Plus, X } from "lucide-react";
import { GlassButton } from "@/components/glass-card";

const API = "http://127.0.0.1:8000";

function fmt(v: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
}
function limparChave(v: string) { return v.replace(/\D/g, "").slice(0, 44); }
function chaveResumida(c: string) { return c.length < 20 ? c : `${c.slice(0, 8)}…${c.slice(-6)}`; }

const DED_LABELS: Record<string, string> = {
  iss: "ISS", irrf: "IRRF", pis: "PIS", cofins: "COFINS", csll: "CSLL", inss: "INSS",
};

// ─── Tipos ───────────────────────────────────────────────────────────────────

interface Deducoes { iss: number; irrf: number; pis: number; cofins: number; csll: number; inss: number; }

interface ResultadoNF {
  origem: "pdf" | "xml" | "sefaz";
  cnpj: string;
  razaoSocial: string;
  optanteSimples: boolean | null;
  tipoDocumento?: string;
  numeroNota: string;
  serie?: string;
  dataEmissao: string;
  valorBruto: number;
  deducoes: Deducoes;
  totalDeducoes: number;
  valorLiquido: number;
  municipioIncidencia?: string;
  aliquotaIss?: number;
}

interface Entrada {
  id: number;
  chave: string;
  xmlFile: File | null;
  pdfFile: File | null;
  status: "pendente" | "carregando" | "ok" | "erro";
  resultado?: ResultadoNF;
  erro?: string;
}

let _id = 1;
const nova = (): Entrada => ({ id: _id++, chave: "", xmlFile: null, pdfFile: null, status: "pendente" });

// ─── Card de resultado ────────────────────────────────────────────────────────

function ResultadoCard({ r }: { r: ResultadoNF }) {
  const dedsAtivas = Object.entries(r.deducoes).filter(([, v]) => v > 0);

  const simplesLabel =
    r.optanteSimples === true  ? { t: "Simples Nacional", cls: "bg-emerald-500/10 text-emerald-700 ring-emerald-500/20" } :
    r.optanteSimples === false ? { t: "Não Simples",       cls: "bg-secondary/60 text-muted-foreground ring-glass-border" } :
    null;

  const origemLabel =
    r.origem === "pdf"   ? { t: "via PDF",   cls: "bg-blue-500/10 text-blue-700 ring-blue-500/20" } :
    r.origem === "xml"   ? { t: "via XML",   cls: "bg-violet-500/10 text-violet-700 ring-violet-500/20" } :
    { t: "via SEFAZ", cls: "bg-amber-500/10 text-amber-700 ring-amber-500/20" };

  return (
    <div className="rounded-xl border border-glass-border/60 bg-background/60 overflow-hidden text-xs">
      {/* Cabeçalho — empresa */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-glass-border/40 bg-secondary/20">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-foreground truncate">{r.razaoSocial || "—"}</p>
          <p className="font-mono text-muted-foreground">{r.cnpj}</p>
        </div>
        <div className="flex flex-wrap gap-1.5 shrink-0 items-center">
          {simplesLabel && (
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${simplesLabel.cls}`}>
              {simplesLabel.t}
            </span>
          )}
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${origemLabel.cls}`}>
            {origemLabel.t}
          </span>
          {r.tipoDocumento && (
            <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold bg-secondary/60 text-muted-foreground ring-1 ring-inset ring-glass-border">
              {r.tipoDocumento}
            </span>
          )}
        </div>
      </div>

      {/* Corpo — valores */}
      <div className="grid grid-cols-2 divide-x divide-glass-border/40">
        {/* Coluna esquerda: bruto + deduções */}
        <div className="px-3 py-2 space-y-1.5">
          <div className="flex justify-between">
            <span className="text-muted-foreground">NF {r.numeroNota}{r.serie ? `/${r.serie}` : ""}</span>
            <span className="text-muted-foreground">{r.dataEmissao || "—"}</span>
          </div>
          <div className="flex justify-between font-medium">
            <span className="text-muted-foreground">Valor bruto</span>
            <span className="text-foreground tabular-nums">{fmt(r.valorBruto)}</span>
          </div>
          {dedsAtivas.map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <span className="text-muted-foreground flex items-center gap-1">
                <span className="text-destructive/70">−</span>
                {DED_LABELS[k]}
                {k === "iss" && r.municipioIncidencia && (
                  <span className="text-[9px] font-medium text-amber-600 bg-amber-500/10 rounded px-1">
                    {r.municipioIncidencia}
                  </span>
                )}
                {k === "iss" && r.aliquotaIss ? (
                  <span className="text-[9px] text-muted-foreground">({r.aliquotaIss}%)</span>
                ) : null}
              </span>
              <span className="text-destructive/80 tabular-nums">({fmt(v)})</span>
            </div>
          ))}
          <div className="border-t border-glass-border/40 pt-1 flex justify-between font-medium text-muted-foreground">
            <span>Total deduções</span>
            <span className="tabular-nums text-destructive/80">({fmt(r.totalDeducoes)})</span>
          </div>
        </div>

        {/* Coluna direita: valor líquido em destaque */}
        <div className="px-3 py-2 flex flex-col items-center justify-center gap-1">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Valor líquido</span>
          <span className="text-lg font-bold tabular-nums text-foreground">{fmt(r.valorLiquido)}</span>
          {r.totalDeducoes > 0 && (
            <span className="text-[10px] text-muted-foreground">
              {((r.totalDeducoes / r.valorBruto) * 100).toFixed(1)}% retido
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Componente principal ────────────────────────────────────────────────────

export function NfeConsulta() {
  const [entradas, setEntradas] = useState<Entrada[]>([nova()]);
  const [consultandoTodos, setConsultandoTodos] = useState(false);
  const xmlRefs = useRef<Record<number, HTMLInputElement | null>>({});
  const pdfRefs = useRef<Record<number, HTMLInputElement | null>>({});

  const set = (id: number, patch: Partial<Entrada>) =>
    setEntradas((p) => p.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  const remover = (id: number) =>
    setEntradas((p) => (p.length > 1 ? p.filter((e) => e.id !== id) : p));

  // ── Via PDF ──
  const consultarViaPdf = async (e: Entrada) => {
    if (!e.pdfFile) return;
    set(e.id, { status: "carregando", erro: undefined, resultado: undefined });
    try {
      const form = new FormData();
      form.append("file", e.pdfFile);
      const res = await fetch(`${API}/api/pdf/analisar-nf`, { method: "POST", body: form });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || `Erro HTTP ${res.status}`);
      }
      const d = await res.json();
      const ded: Deducoes = {
        iss: d.deducoes?.iss ?? 0, irrf: d.deducoes?.irrf ?? 0,
        pis: d.deducoes?.pis ?? 0, cofins: d.deducoes?.cofins ?? 0,
        csll: d.deducoes?.csll ?? 0, inss: d.deducoes?.inss ?? 0,
      };
      const total = Object.values(ded).reduce((a, b) => a + b, 0);
      set(e.id, {
        status: "ok",
        resultado: {
          origem: "pdf",
          cnpj: d.cnpj || "", razaoSocial: d.razaoSocial || "",
          optanteSimples: d.optanteSimples ?? null,
          tipoDocumento: d.tipoDocumento,
          numeroNota: d.numeroNota || "", serie: "",
          dataEmissao: d.dataEmissao || "",
          valorBruto: d.valorBruto ?? 0,
          deducoes: ded, totalDeducoes: round2(total),
          valorLiquido: d.valorLiquido ?? round2((d.valorBruto ?? 0) - total),
          municipioIncidencia: d.municipioIncidencia || "",
          aliquotaIss: d.aliquotaIss ?? 0,
        },
      });
    } catch (err) {
      set(e.id, { status: "erro", erro: err instanceof Error ? err.message : "Erro ao processar PDF." });
    }
  };

  // ── Via XML ──
  const consultarViaXml = async (e: Entrada) => {
    if (!e.xmlFile) return;
    set(e.id, { status: "carregando", erro: undefined, resultado: undefined });
    try {
      const form = new FormData();
      form.append("files", e.xmlFile);
      const res = await fetch(`${API}/api/xml/analisar`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`Erro HTTP ${res.status}`);
      const data = await res.json();
      if (data.erros?.length && !data.notas?.length) throw new Error(data.erros[0].erro);
      const n = data.notas?.[0];
      if (!n) throw new Error("Nenhuma NF-e no XML.");
      const ded: Deducoes = { iss: n.deducoes?.iss ?? 0, irrf: n.deducoes?.irrf ?? 0, pis: n.deducoes?.pis ?? 0, cofins: n.deducoes?.cofins ?? 0, csll: n.deducoes?.csll ?? 0, inss: n.deducoes?.inss ?? 0 };
      const total = Object.values(ded).reduce((a, b) => a + b, 0);
      set(e.id, {
        status: "ok",
        resultado: {
          origem: "xml", cnpj: n.cnpjEmitente || "", razaoSocial: n.emitente || "",
          optanteSimples: null, tipoDocumento: "NF-e",
          numeroNota: n.numero || "", serie: n.serie || "", dataEmissao: n.dataEmissao || "",
          valorBruto: n.valorBruto ?? 0, deducoes: ded, totalDeducoes: round2(total),
          valorLiquido: round2((n.valorBruto ?? 0) - total),
        },
      });
    } catch (err) {
      set(e.id, { status: "erro", erro: err instanceof Error ? err.message : "Erro ao analisar XML." });
    }
  };

  // ── Via SEFAZ (certificado) ──
  const consultarViaSefaz = async (e: Entrada) => {
    const chave = limparChave(e.chave);
    if (chave.length !== 44) { set(e.id, { status: "erro", erro: "A chave deve ter 44 dígitos." }); return; }
    set(e.id, { status: "carregando", erro: undefined, resultado: undefined });
    try {
      const res = await fetch(`${API}/api/nfe/consultar-chave`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chave }),
      });
      if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || `Erro HTTP ${res.status}`); }
      const d = await res.json();
      const ded: Deducoes = { iss: d.deducoes?.iss ?? 0, irrf: d.deducoes?.irrf ?? 0, pis: d.deducoes?.pis ?? 0, cofins: d.deducoes?.cofins ?? 0, csll: d.deducoes?.csll ?? 0, inss: d.deducoes?.inss ?? 0 };
      const total = Object.values(ded).reduce((a, b) => a + b, 0);
      set(e.id, {
        status: "ok",
        resultado: {
          origem: "sefaz", cnpj: d.cnpjEmitente || "", razaoSocial: d.emitente || "",
          optanteSimples: null, numeroNota: d.numero || "", serie: d.serie || "",
          dataEmissao: d.dataEmissao || "", valorBruto: d.valorBruto ?? 0,
          deducoes: ded, totalDeducoes: round2(total), valorLiquido: round2((d.valorBruto ?? 0) - total),
        },
      });
    } catch (err) {
      const msg = err instanceof TypeError && (err as TypeError).message.includes("fetch")
        ? "Servidor indisponível." : err instanceof Error ? err.message : "Erro.";
      set(e.id, { status: "erro", erro: msg });
    }
  };

  const consultar = (e: Entrada) => {
    if (e.pdfFile) return consultarViaPdf(e);
    if (e.xmlFile) return consultarViaXml(e);
    return consultarViaSefaz(e);
  };

  const consultarTodas = async () => {
    setConsultandoTodos(true);
    const ps = entradas.filter((e) => (e.pdfFile || e.xmlFile || limparChave(e.chave).length === 44) && e.status !== "ok");
    await Promise.all(ps.map((e) => consultar(e)));
    setConsultandoTodos(false);
  };

  const algumPendente = entradas.some(
    (e) => (e.pdfFile || e.xmlFile || limparChave(e.chave).length === 44) && e.status !== "ok"
  );
  const temErroCert = entradas.some((e) => e.erro?.includes("Certificado"));

  // ── Debug: ver texto bruto extraído do PDF ──
  const [debugTexto, setDebugTexto] = useState<string | null>(null);
  const [debugPdfRef] = useState(() => ({ current: null as HTMLInputElement | null }));
  const debugarPdf = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API}/api/pdf/debug-texto`, { method: "POST", body: form });
    const d = await res.json();
    const texto = d.paginas?.map((p: any) =>
      `=== Página ${p.pagina} ===\n${p.texto}\n\nTabelas:\n${JSON.stringify(p.tabelas, null, 2)}`
    ).join("\n\n");
    setDebugTexto(texto ?? "");
  };

  return (
    <div className="rounded-2xl border border-glass-border/70 bg-background/55 p-4 space-y-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        Consulta NF-e / NFS-e
      </p>

      <div className="space-y-3">
        {entradas.map((entrada) => (
          <div key={entrada.id} className="space-y-2">
            {/* Linha de entrada */}
            <div className="flex gap-2 items-center">
              {/* Campo chave */}
              <div className="relative flex-1 min-w-0">
                <Key className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={entrada.chave}
                  onChange={(e) => set(entrada.id, { chave: limparChave(e.target.value), status: "pendente", erro: undefined, resultado: undefined })}
                  onKeyDown={(e) => e.key === "Enter" && void consultar(entrada)}
                  placeholder="Cole os 44 dígitos da chave de acesso"
                  maxLength={44}
                  className="w-full rounded-xl border border-glass-border bg-background/80 pl-9 pr-3 py-2 text-xs text-foreground font-mono tracking-wide outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-muted-foreground/60"
                />
              </div>

              {/* Botão PDF */}
              <input ref={(el) => { pdfRefs.current[entrada.id] = el; }} type="file" accept=".pdf" className="hidden"
                onChange={(e) => set(entrada.id, { pdfFile: e.target.files?.[0] ?? null, status: "pendente", erro: undefined, resultado: undefined })} />
              <button type="button" title={entrada.pdfFile ? entrada.pdfFile.name : "Anexar PDF"}
                onClick={() => pdfRefs.current[entrada.id]?.click()}
                className={`shrink-0 flex items-center gap-1 rounded-xl border px-2.5 py-2 text-xs transition-colors ${
                  entrada.pdfFile ? "border-red-400/50 bg-red-500/5 text-red-600" : "border-glass-border bg-background/60 text-muted-foreground hover:border-red-400/40 hover:text-red-600"
                }`}>
                <FileText className="h-3.5 w-3.5 shrink-0" />
                <span className="hidden sm:inline max-w-[60px] truncate">
                  {entrada.pdfFile ? entrada.pdfFile.name.replace(".pdf","") : "PDF"}
                </span>
              </button>

              {/* Botão XML */}
              <input ref={(el) => { xmlRefs.current[entrada.id] = el; }} type="file" accept=".xml" className="hidden"
                onChange={(e) => set(entrada.id, { xmlFile: e.target.files?.[0] ?? null, status: "pendente", erro: undefined, resultado: undefined })} />
              <button type="button" title={entrada.xmlFile ? entrada.xmlFile.name : "Anexar XML"}
                onClick={() => xmlRefs.current[entrada.id]?.click()}
                className={`shrink-0 flex items-center gap-1 rounded-xl border px-2.5 py-2 text-xs transition-colors ${
                  entrada.xmlFile ? "border-primary/40 bg-primary/5 text-primary" : "border-glass-border bg-background/60 text-muted-foreground hover:border-primary/40 hover:text-foreground"
                }`}>
                <Paperclip className="h-3.5 w-3.5 shrink-0" />
                <span className="hidden sm:inline max-w-[60px] truncate">
                  {entrada.xmlFile ? entrada.xmlFile.name.replace(".xml","") : "XML"}
                </span>
              </button>

              {/* Consultar */}
              <GlassButton type="button" variant="secondary" size="sm"
                onClick={() => void consultar(entrada)}
                disabled={entrada.status === "carregando" || (!entrada.pdfFile && !entrada.xmlFile && limparChave(entrada.chave).length !== 44)}
                className="shrink-0">
                {entrada.status === "carregando" && <Loader2 className="h-4 w-4 animate-spin" />}
                {entrada.status === "carregando" ? "..." : "Consultar"}
              </GlassButton>

              {entradas.length > 1 && (
                <button type="button" onClick={() => remover(entrada.id)}
                  className="shrink-0 rounded-full p-1 text-muted-foreground hover:text-foreground">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Resultado rico */}
            {entrada.status === "ok" && entrada.resultado && (
              <ResultadoCard r={entrada.resultado} />
            )}

            {entrada.status === "erro" && (
              <p className="text-xs text-destructive pl-1">{entrada.erro}</p>
            )}
          </div>
        ))}
      </div>

      {/* Botões de ação */}
      <div className="flex gap-2 flex-wrap items-center">
        <button type="button" onClick={() => setEntradas((p) => [...p, nova()])}
          className="flex items-center gap-1.5 rounded-xl border border-dashed border-glass-border bg-background/60 px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors">
          <Plus className="h-3.5 w-3.5" /> Adicionar NF-e
        </button>

        {algumPendente && entradas.length > 1 && (
          <GlassButton type="button" variant="secondary" size="sm"
            onClick={() => void consultarTodas()} disabled={consultandoTodos} className="ml-auto">
            {consultandoTodos && <Loader2 className="h-4 w-4 animate-spin" />}
            {consultandoTodos ? "Consultando..." : "Consultar todas"}
          </GlassButton>
        )}
      </div>

      {/* Aviso certificado */}
      {temErroCert && (
        <p className="text-[11px] text-muted-foreground border border-amber-500/20 bg-amber-500/5 rounded-lg px-3 py-2">
          ⚠ Sem certificado configurado — use <strong>PDF</strong> ou <strong>XML</strong> para consultar sem SEFAZ.
        </p>
      )}

      {/* Debug parser — ver texto bruto do PDF */}
      <div className="border-t border-glass-border/40 pt-3">
        <input type="file" accept=".pdf" className="hidden"
          ref={(el) => { debugPdfRef.current = el; }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void debugarPdf(f); }} />
        <button type="button"
          onClick={() => debugPdfRef.current?.click()}
          className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 hover:text-muted-foreground transition-colors">
          <Bug className="h-3 w-3" /> Debug: ver texto extraído do PDF
        </button>
        {debugTexto !== null && (
          <pre className="mt-2 max-h-60 overflow-auto rounded-lg bg-secondary/40 p-2 text-[10px] text-foreground/70 whitespace-pre-wrap break-all">
            {debugTexto}
          </pre>
        )}
      </div>
    </div>
  );
}

function round2(v: number) { return Math.round(v * 100) / 100; }
