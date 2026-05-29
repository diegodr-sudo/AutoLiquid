"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  X, ChevronLeft, ChevronRight, Calendar, Plus, Trash2,
  AlertCircle, Check, Clipboard, MessageCircle, Pencil, RefreshCw,
} from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "@/hooks/use-toast";
import {
  fetchAusencias, criarAusencia, deletarAusencia,
  fetchServidoresConfig, upsertServidorConfig,
  type AusenciaRemota, type ServidorConfigRemoto,
} from "@/lib/data";

// ── Tipos locais ──────────────────────────────────────────────────────────────

type Ausencia = AusenciaRemota;
type ServidorConfig = ServidorConfigRemoto;

// ── Helpers de data ───────────────────────────────────────────────────────────

/** Máscara dd/mm/aaaa */
function maskDate(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`;
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`;
}

/** "26/04/2026" → "2026-04-26" ou "" se inválido */
function dmyToYMD(dmy: string): string {
  const parts = dmy.split("/");
  if (parts.length !== 3 || parts[2].length !== 4) return "";
  return `${parts[2]}-${parts[1].padStart(2, "0")}-${parts[0].padStart(2, "0")}`;
}

interface AusenciasModalProps {
  open: boolean;
  onClose: () => void;
  servidoresSugeridos?: string[];
}

const PALETTE = [
  "#0ea5e9", "#6366f1", "#8b5cf6", "#a855f7", "#ec4899",
  "#ef4444", "#f97316", "#f59e0b", "#84cc16", "#10b981",
  "#14b8a6", "#06b6d4",
];

// ── Feriados ─────────────────────────────────────────────────────────────────

function calcularPascoa(ano: number): Date {
  const a = ano % 19, b = Math.floor(ano / 100), c = ano % 100;
  const d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(ano, month - 1, day);
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d); r.setDate(r.getDate() + n); return r;
}

function toYMD(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function getFeriados(ano: number): Record<string, { nome: string }> {
  const pascoa = calcularPascoa(ano);
  const f: Record<string, { nome: string }> = {};
  const add = (d: Date | [number, number], nome: string) => {
    const date = Array.isArray(d) ? new Date(ano, d[0] - 1, d[1]) : d;
    f[toYMD(date)] = { nome };
  };
  add([1, 1],  "Confraternização Universal");
  add([4, 21], "Tiradentes");
  add([5, 1],  "Dia do Trabalho");
  add([9, 7],  "Independência do Brasil");
  add([10, 12],"Nossa Sra. Aparecida");
  add([11, 2], "Finados");
  add([11, 15],"Proclamação da República");
  add([11, 20],"Consciência Negra");
  add([12, 25],"Natal");
  add(addDays(pascoa, -47), "Carnaval");
  add(addDays(pascoa, -48), "Carnaval (segunda)");
  add(addDays(pascoa, -2),  "Sexta-feira Santa");
  add(pascoa,              "Páscoa");
  add(addDays(pascoa, 60), "Corpus Christi");
  add([1, 20], "São Sebastião (Florianópolis)");
  add([3, 23], "Aniversário de Florianópolis");
  add([8, 15], "Nossa Sra. do Desterro (Florianópolis)");
  return f;
}

// ── Tipo config ───────────────────────────────────────────────────────────────

const TIPO_CONFIG = {
  ferias:      { label: "Férias",      color: "bg-teal-500/20 text-teal-700 border-teal-500/30" },
  afastamento: { label: "Afastamento", color: "bg-amber-500/20 text-amber-700 border-amber-500/30" },
  licenca:     { label: "Licença",     color: "bg-violet-500/20 text-violet-700 border-violet-500/30" },
};

function isBetween(ymd: string, inicio: string, fim: string) {
  return ymd >= inicio && ymd <= fim;
}

function initials(nome: string): string {
  const parts = nome.trim().split(/\s+/);
  return parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : nome.slice(0, 2).toUpperCase();
}

// ── Calendário ────────────────────────────────────────────────────────────────

const DIAS  = ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];
const MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho",
               "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];

// ── Componente ────────────────────────────────────────────────────────────────

export function FeriasModal({ open, onClose }: AusenciasModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);
  const today = new Date();

  const [viewYear,  setViewYear]  = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [ausencias,  setAusencias]  = useState<Ausencia[]>([]);
  const [servidores, setServidores] = useState<ServidorConfig[]>([]);
  const [tab, setTab] = useState<"calendario" | "cores">("calendario");
  const [loadingData, setLoadingData] = useState(false);
  const [editServIdx, setEditServIdx] = useState<number | null>(null);

  // Picker de mês/ano
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(today.getFullYear());

  // Formulário de ausência
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ servidor: "", tipo: "ferias" as Ausencia["tipo"], inicio: "", fim: "", obs: "" });
  const [formErro, setFormErro] = useState("");
  const [rocketMenuOpen, setRocketMenuOpen] = useState(false);

  // ── Erro inline não-bloqueante ────────────────────────────────────────────
  const [erroInline, setErroInline] = useState("");
  const showErro = (msg: string) => {
    setErroInline(msg);
    setTimeout(() => setErroInline(""), 4000);
  };

  // ── Carga de dados ────────────────────────────────────────────────────────

  const carregarDados = useCallback(async () => {
    setLoadingData(true);
    try {
      const [aus, servs] = await Promise.all([
        fetchAusencias(),
        fetchServidoresConfig(),
      ]);
      setAusencias(aus);
      setServidores(servs);
    } catch {
      // se a API falhar, mantém estado anterior silenciosamente
    } finally {
      setLoadingData(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (open) carregarDados();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;

  const feriados = getFeriados(viewYear);

  const corMap: Record<string, string> = Object.fromEntries(
    servidores.map((s) => [s.nome, s.cor])
  );

  const firstDay  = new Date(viewYear, viewMonth, 1);
  const lastDay   = new Date(viewYear, viewMonth + 1, 0);
  const startPad  = firstDay.getDay();
  const cells: (number | null)[] = [
    ...Array(startPad).fill(null),
    ...Array.from({ length: lastDay.getDate() }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const prevMonth = () => viewMonth === 0
    ? (setViewMonth(11), setViewYear(y => y - 1))
    : setViewMonth(m => m - 1);
  const nextMonth = () => viewMonth === 11
    ? (setViewMonth(0), setViewYear(y => y + 1))
    : setViewMonth(m => m + 1);
  const goToToday = () => { setViewYear(today.getFullYear()); setViewMonth(today.getMonth()); setPickerOpen(false); };

  const todayYMD = toYMD(today);

  // ── Handlers ausência — optimistic UI ────────────────────────────────────

  const handleAddAusencia = () => {
    setFormErro("");
    if (!form.servidor.trim()) { setFormErro("Informe o servidor."); return; }
    if (!servidores.some((s) => s.nome.toLowerCase() === form.servidor.trim().toLowerCase())) {
      setFormErro("Servidor não cadastrado.");
      return;
    }
    const inicioYMD = dmyToYMD(form.inicio);
    const fimYMD   = dmyToYMD(form.fim);
    if (!inicioYMD) { setFormErro("Início inválido. Use DD/MM/AAAA."); return; }
    if (!fimYMD)    { setFormErro("Fim inválido. Use DD/MM/AAAA.");    return; }
    if (inicioYMD > fimYMD) { setFormErro("Início deve ser anterior ao fim."); return; }

    const tempId = `temp-${Date.now()}`;
    const nova: Ausencia = {
      id: tempId,
      servidor: form.servidor.trim(),
      tipo: form.tipo,
      inicio: inicioYMD,
      fim: fimYMD,
      obs: form.obs.trim() || undefined,
    };

    // ① Atualiza UI imediatamente
    setAusencias((prev) => [...prev, nova]);
    setForm({ servidor: "", tipo: "ferias", inicio: "", fim: "", obs: "" });
    setShowForm(false);

    // ② Persiste em background — reverte em caso de falha
    criarAusencia(nova)
      .then((salva) => {
        // Substitui temp ID pelo ID real do servidor
        setAusencias((prev) => prev.map((a) => a.id === tempId ? salva : a));
      })
      .catch(() => {
        setAusencias((prev) => prev.filter((a) => a.id !== tempId));
        showErro("Não foi possível salvar a ausência. Tente novamente.");
      });
  };

  const handleDeleteAusencia = (id: string) => {
    // ① Remove imediatamente
    const snapshot = ausencias.find((a) => a.id === id);
    setAusencias((prev) => prev.filter((a) => a.id !== id));

    // ② Persiste em background — restaura em caso de falha
    deletarAusencia(id).catch(() => {
      if (snapshot) setAusencias((prev) => [...prev, snapshot]);
      showErro("Não foi possível remover a ausência. Tente novamente.");
    });
  };

  const handleUpdateServCor = (idx: number, cor: string) => {
    const snapshot = servidores[idx];
    setServidores((prev) => prev.map((sv, i) => i === idx ? { ...sv, cor } : sv));
    setEditServIdx(null);

    upsertServidorConfig(snapshot.nomeCompleto || snapshot.nome, cor).catch(() => {
      setServidores((prev) => prev.map((sv, i) => i === idx ? snapshot : sv));
      showErro("Não foi possível atualizar a cor. Tente novamente.");
    });
  };

  const rocketOutCommand = "/out-of-office out";
  const rocketInCommand = "/out-of-office in";

  const handleCopyCommand = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      setRocketMenuOpen(false);
      toast({ title: "Comando copiado!", duration: 1800 });
    } catch {
      showErro("Não foi possível copiar o comando.");
    }
  };

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-[200] flex items-center justify-center overflow-hidden bg-black/45 px-2 py-2"
      onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}
    >
      <div className="flex max-h-[calc(100dvh-16px)] w-full max-w-[580px] flex-col overflow-hidden rounded-2xl border border-glass-border bg-background shadow-2xl">

        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-glass-border px-5 py-3">
          <div className="flex items-center gap-3">
            <Calendar className="h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold text-foreground">Ausências da Equipe</h2>
            {loadingData && <RefreshCw className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex rounded-lg border border-glass-border bg-secondary/30 p-0.5 text-[11px] font-semibold">
              {([
                ["calendario", "Calendário"],
                ["cores", "Cores"],
              ] as const).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  className={`rounded-md px-3 py-1 transition-colors ${tab === id ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={carregarDados}
                  disabled={loadingData}
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary/60 hover:text-foreground disabled:opacity-40"
                >
                  <RefreshCw className={`h-4 w-4 ${loadingData ? "animate-spin" : ""}`} />
                </button>
              </TooltipTrigger>
              <TooltipContent className="z-[210]">Recarregar dados</TooltipContent>
            </Tooltip>
            <Tooltip>
              <Popover open={rocketMenuOpen} onOpenChange={setRocketMenuOpen}>
                <TooltipTrigger asChild>
                  <PopoverTrigger asChild>
                    <button
                      type="button"
                      className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                      aria-label="Comandos Rocket.Chat"
                    >
                      <MessageCircle className="h-4 w-4" />
                    </button>
                  </PopoverTrigger>
                </TooltipTrigger>
                <PopoverContent align="end" sideOffset={8} className="z-[210] w-64 p-1.5">
                <button
                  type="button"
                  onClick={() => void handleCopyCommand(rocketOutCommand)}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-secondary/70"
                >
                  <Clipboard className="h-4 w-4 text-muted-foreground" />
                  Copiar comando de Saída
                </button>
                <button
                  type="button"
                  onClick={() => void handleCopyCommand(rocketInCommand)}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-secondary/70"
                >
                  <Clipboard className="h-4 w-4 text-muted-foreground" />
                  Copiar comando de Retorno
                </button>
              </PopoverContent>
              </Popover>
              <TooltipContent className="z-[210]">Comandos Rocket.Chat</TooltipContent>
            </Tooltip>
            <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary/60 hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Erro inline — aparece/desaparece sem bloquear nada */}
        {erroInline && (
          <div className="mx-5 mt-3 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/8 px-3 py-2 text-[11px] text-destructive">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            {erroInline}
          </div>
        )}

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {tab === "calendario" ? (
            <>
              <div className="rounded-xl border border-glass-border bg-background/50 p-3">
                {/* Navegação */}
                <div className="mb-2 flex items-center justify-between gap-2">
                  <button type="button" onClick={prevMonth} className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary/60">
                    <ChevronLeft className="h-4 w-4" />
                  </button>

                  <div className="relative flex-1 text-center">
                    <button
                      type="button"
                      onClick={() => { setPickerYear(viewYear); setPickerOpen(v => !v); }}
                      className="rounded-lg px-3 py-1 text-sm font-semibold text-foreground hover:bg-secondary/60 transition-colors"
                    >
                      {MESES[viewMonth]} {viewYear} <span className="ml-0.5 text-[10px] text-muted-foreground">▾</span>
                    </button>

                    {pickerOpen && (
                      <div className="absolute left-1/2 top-full z-20 mt-1 -translate-x-1/2 rounded-xl border border-glass-border bg-background p-3 shadow-xl" style={{ minWidth: 220 }}>
                        <div className="mb-2 flex items-center justify-between">
                          <button type="button" onClick={() => setPickerYear(y => y - 1)} className="rounded p-1 text-muted-foreground hover:bg-secondary/60">
                            <ChevronLeft className="h-3.5 w-3.5" />
                          </button>
                          <span className="text-[13px] font-semibold text-foreground">{pickerYear}</span>
                          <button type="button" onClick={() => setPickerYear(y => y + 1)} className="rounded p-1 text-muted-foreground hover:bg-secondary/60">
                            <ChevronRight className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        <div className="grid grid-cols-3 gap-1">
                          {MESES.map((m, idx) => {
                            const isSelected = idx === viewMonth && pickerYear === viewYear;
                            const isCurrentMonth = idx === today.getMonth() && pickerYear === today.getFullYear();
                            return (
                              <button
                                key={m}
                                type="button"
                                onClick={() => { setViewMonth(idx); setViewYear(pickerYear); setPickerOpen(false); }}
                                className={`rounded-lg py-1.5 text-[11px] font-medium transition-colors ${
                                  isSelected
                                    ? "bg-primary text-primary-foreground"
                                    : isCurrentMonth
                                      ? "bg-primary/10 text-primary"
                                      : "text-foreground hover:bg-secondary/60"
                                }`}
                              >
                                {m.slice(0, 3)}
                              </button>
                            );
                          })}
                        </div>
                        <button
                          type="button"
                          onClick={goToToday}
                          className="mt-2 w-full rounded-lg border border-glass-border py-1.5 text-[11px] font-medium text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors"
                        >
                          Ir para hoje
                        </button>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-1">
                    {(viewMonth !== today.getMonth() || viewYear !== today.getFullYear()) && (
                      <button
                        type="button"
                        onClick={goToToday}
                        className="rounded-lg border border-glass-border px-2 py-1 text-[10px] font-semibold text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors"
                        title="Voltar para o mês atual"
                      >
                        Hoje
                      </button>
                    )}
                    <button type="button" onClick={nextMonth} className="rounded-lg p-1.5 text-muted-foreground hover:bg-secondary/60">
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Legenda */}
                <div className="mb-2 flex flex-wrap gap-x-2 gap-y-1 text-[9px] text-muted-foreground">
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500/70" />Feriado</span>
                  {servidores.map((s) => (
                    <span key={s.nome} className="flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full" style={{ background: s.cor }} />
                      {s.nome.split(" ")[0]}
                    </span>
                  ))}
                </div>

                {/* Cabeçalho */}
                <div className="mb-1 grid grid-cols-7">
                  {DIAS.map((d) => (
                    <div key={d} className="py-0.5 text-center text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">{d}</div>
                  ))}
                </div>

                {/* Dias */}
                <div className="grid grid-cols-7 gap-0.5">
                  {cells.map((day, idx) => {
                    if (day === null) return <div key={`pad-${idx}`} />;
                    const ymd = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                    const feriado  = feriados[ymd];
                    const isToday  = ymd === todayYMD;
                    const isWeekend = idx % 7 === 0 || idx % 7 === 6;
                    const ausDia   = ausencias.filter((a) => isBetween(ymd, a.inicio, a.fim));

                    const tooltip = [
                      feriado?.nome,
                      ...ausDia.map((a) => `${a.servidor} (${TIPO_CONFIG[a.tipo].label})`),
                    ].filter(Boolean).join(" · ");

                    return (
                      <div
                        key={ymd}
                        title={tooltip}
                        className={`relative flex flex-col items-center rounded-lg py-1 transition-colors ${isToday ? "bg-primary/15 ring-1 ring-primary/40" : feriado ? "bg-red-500/6" : ""}`}
                        style={{ minHeight: 40 }}
                      >
                        <span className={`text-[11px] font-medium leading-none ${
                          isToday   ? "font-bold text-primary"
                          : feriado ? "text-red-600"
                          : isWeekend ? "text-muted-foreground/60"
                          : "text-foreground"
                        }`}>
                          {day}
                        </span>

                        {feriado && <span className="mt-0.5 h-1 w-1 rounded-full bg-red-500" />}

                        {ausDia.length > 0 && (
                          <div className="mt-0.5 flex flex-wrap justify-center gap-0.5 px-0.5">
                            {ausDia.slice(0, 4).map((a) => {
                              const cor = corMap[a.servidor] ?? "#94a3b8";
                              return (
                                <span
                                  key={a.id}
                                  className="flex items-center justify-center rounded-full font-bold text-white"
                                  style={{ width: 13, height: 13, fontSize: 6, background: cor, opacity: 0.92 }}
                                  title={`${a.servidor} · ${TIPO_CONFIG[a.tipo].label}`}
                                >
                                  {initials(a.servidor).slice(0, 1)}
                                </span>
                              );
                            })}
                            {ausDia.length > 4 && (
                              <span
                                className="flex items-center justify-center rounded-full bg-muted font-bold text-muted-foreground"
                                style={{ width: 13, height: 13, fontSize: 6 }}
                              >
                                +{ausDia.length - 4}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                    Ausências cadastradas
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowForm((v) => !v)}
                    className="flex items-center gap-1.5 rounded-lg border border-glass-border bg-background/60 px-3 py-1.5 text-[11px] font-medium transition-colors hover:bg-secondary/60"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Adicionar
                  </button>
                </div>

                {showForm && (
                  <div className="mb-3 space-y-3 rounded-xl border border-glass-border bg-background/70 p-4">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="col-span-2">
                        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Servidor</label>
                        <input
                          list="servidores-list"
                          value={form.servidor}
                          onChange={(e) => setForm((f) => ({ ...f, servidor: e.target.value }))}
                          placeholder="Nome do servidor"
                          className="w-full rounded-lg border border-glass-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50"
                        />
                        <datalist id="servidores-list">
                          {servidores.map((s) => <option key={s.nome} value={s.nome} />)}
                        </datalist>
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Tipo</label>
                        <select
                          value={form.tipo}
                          onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value as Ausencia["tipo"] }))}
                          className="select-native h-11 w-full rounded-full border border-glass-border bg-background pl-3 pr-8 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                        >
                          <option value="ferias">Férias</option>
                          <option value="afastamento">Afastamento</option>
                          <option value="licenca">Licença</option>
                        </select>
                      </div>
                      <div />
                      <div>
                        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Início</label>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={form.inicio}
                          onChange={(e) => setForm((f) => ({ ...f, inicio: maskDate(e.target.value) }))}
                          placeholder="DD/MM/AAAA"
                          maxLength={10}
                          className="w-full rounded-lg border border-glass-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/50"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Fim</label>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={form.fim}
                          onChange={(e) => setForm((f) => ({ ...f, fim: maskDate(e.target.value) }))}
                          placeholder="DD/MM/AAAA"
                          maxLength={10}
                          className="w-full rounded-lg border border-glass-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/50"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Observação (opcional)</label>
                        <input
                          value={form.obs}
                          onChange={(e) => setForm((f) => ({ ...f, obs: e.target.value }))}
                          placeholder="Ex: Licença médica, portaria nº…"
                          className="w-full rounded-lg border border-glass-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/50"
                        />
                      </div>
                    </div>
                    {formErro && (
                      <p className="flex items-center gap-1.5 text-[11px] text-destructive">
                        <AlertCircle className="h-3.5 w-3.5 shrink-0" />{formErro}
                      </p>
                    )}
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => { setShowForm(false); setFormErro(""); }}
                        className="rounded-lg border border-glass-border px-4 py-1.5 text-sm text-muted-foreground hover:bg-secondary/60">
                        Cancelar
                      </button>
                      <button type="button" onClick={handleAddAusencia}
                        className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                        Salvar
                      </button>
                    </div>
                  </div>
                )}

                {ausencias.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-glass-border py-5 text-center text-sm text-muted-foreground">
                    <Calendar className="mx-auto mb-2 h-7 w-7 opacity-25" />
                    Nenhuma ausência cadastrada.
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {ausencias.slice().sort((a, b) => a.inicio.localeCompare(b.inicio)).map((a) => {
                      const cfg = TIPO_CONFIG[a.tipo];
                      const cor = corMap[a.servidor] ?? "#94a3b8";
                      const ini = new Date(a.inicio + "T00:00:00");
                      const fim = new Date(a.fim    + "T00:00:00");
                      const dias = Math.round((fim.getTime() - ini.getTime()) / 86_400_000) + 1;
                      return (
                          <div key={a.id} className="flex items-center gap-3 rounded-xl border border-glass-border bg-background/50 px-3 py-2"
                            style={{ borderLeft: `3px solid ${cor}` }}>
                          <div className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                            style={{ background: cor }}>
                            {initials(a.servidor)}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-[13px] font-semibold text-foreground">{a.servidor}</span>
                              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${cfg.color}`}>{cfg.label}</span>
                            </div>
                            <p className="mt-0.5 text-[11px] text-muted-foreground">
                              {ini.toLocaleDateString("pt-BR")} → {fim.toLocaleDateString("pt-BR")}
                              <span className="ml-2 text-muted-foreground/60">({dias} dia{dias !== 1 ? "s" : ""})</span>
                              {a.obs && <span className="ml-2 italic">· {a.obs}</span>}
                            </p>
                          </div>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button type="button" onClick={() => handleDeleteAusencia(a.id)}
                                className="shrink-0 rounded-lg p-1.5 text-muted-foreground/40 hover:bg-destructive/10 hover:text-destructive">
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent className="z-[210]">Remover ausência</TooltipContent>
                          </Tooltip>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <div>
                <p className="text-sm font-semibold text-foreground">Cores do calendário</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Ajuste apenas como cada servidor aparece nos afastamentos.
                </p>
              </div>

              <div className="space-y-2">
                {servidores.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-glass-border py-5 text-center text-sm text-muted-foreground">
                    Nenhum servidor cadastrado.
                  </div>
                ) : null}
                {servidores.map((s, idx) => (
                  <div key={s.nome} className="relative flex items-center gap-3 rounded-xl border border-glass-border bg-background/50 px-3 py-2">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                      style={{ background: s.cor }}>
                      {initials(s.nome)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-foreground">{s.nome}</span>
                      {s.nomeCompleto && s.nomeCompleto !== s.nome ? (
                        <span className="block truncate text-[11px] text-muted-foreground">{s.nomeCompleto}</span>
                      ) : null}
                    </div>
                    <Tooltip>
                    <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => setEditServIdx(editServIdx === idx ? null : idx)}
                      className="flex items-center gap-1.5 rounded-lg border border-glass-border px-2.5 py-1 text-[11px] text-muted-foreground hover:bg-secondary/60"
                    >
                      <span className="h-3 w-3 rounded-full border border-white/30" style={{ background: s.cor }} />
                      <Pencil className="h-3 w-3" />
                    </button>
                    </TooltipTrigger>
                    <TooltipContent className="z-[210]">Trocar cor</TooltipContent>
                    </Tooltip>
                    {editServIdx === idx && (
                      <div className="absolute right-4 top-12 z-10 rounded-xl border border-glass-border bg-background p-3 shadow-xl">
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                          Cor de {s.nome.split(" ")[0]}
                        </p>
                        <div className="flex flex-wrap gap-1.5" style={{ maxWidth: 160 }}>
                          {PALETTE.map((cor) => (
                            <button
                              key={cor}
                              type="button"
                              onClick={() => handleUpdateServCor(idx, cor)}
                              className="relative h-6 w-6 rounded-full border-2 transition-transform hover:scale-110"
                              style={{
                                background: cor,
                                borderColor: s.cor === cor ? "white" : "transparent",
                                boxShadow: s.cor === cor ? `0 0 0 2px ${cor}` : "none",
                              }}
                            >
                              {s.cor === cor && <Check className="absolute inset-0 m-auto h-3 w-3 text-white" />}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
