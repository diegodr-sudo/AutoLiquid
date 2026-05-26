"use client";

import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowDownToLine, ArrowUp, CalendarDays, CheckCircle2, ChevronDown, ChevronRight, FileUp, Info, Loader2, MessageSquare, Minus, Pencil, Plus, RefreshCw, Settings2, Trash2, X } from "lucide-react";
import { Header } from "@/components/header";
import { DateFields } from "@/components/date-fields";
import { UploadZone } from "@/components/upload-zone";
import { TabelasModal } from "@/components/tabelas-modal";
import { ConfiguracoesModal } from "@/components/configuracoes-modal";
import { DashboardModal } from "@/components/dashboard-modal";
import { FeriasModal } from "@/components/ferias-modal";
import { DashboardHistorico } from "@/components/dashboard-historico";
import { GlassButton } from "@/components/glass-card";
import { GlobalScopeIcon } from "@/components/global-scope-icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CnpjChecker, NfeConsulta, IssPortais, HistoricoBusca } from "@/components/liquidacao";
import {
  abrirUrl,
  createFilaProcessosEventSource,
  delay,
  fetchDashboard,
  fetchDocumentoProcessado,
  fetchRegistroLiquidacaoPendente,
  fetchFilaProcessos,
  fetchAlertaServicoConfig,
  fetchFilaSetoresHistorico,
  fetchRegrasDatasDeducoes,
  fetchAuthDiagnostico,
  loginAutoLiquid,
  fetchQueueServersConfig,
  fetchRocketChatNotifications,
  type BackendStartupProgress,
  type DashboardInfo,
  type FilaProcessosInfo,
  MOCK_PROCESS_DATES,
  fetchBackendStatus,
  fetchAppSettings,
  saveAppSettings,
  fetchProcessDates,
  fetchDatasGlobais,
  fetchSimplesBatch,
  fetchContratosIcLookup,
  deleteFilaAlerta,
  openChromeSession,
  openSolarProcess,
  registrarLiquidacao,
  saveProcessDates,
  saveFilaAlerta,
  saveFilaConclusao,
  saveFilaResponsavel,
  saveAlertaServicoConfig,
  saveRegrasDatasDeducoes,
  saveQueueServersConfig,
  waitForBackendReady,
  verificarAtualizacao,
  type AlertaServicoConfig,
  type AlertaServicoRule,
  type AuthSession,
  type AuthDiagnostico,
  type RegistroLiquidacaoTipoDocumento,
  type FilaAlerta,
  type RegraDataDeducao,
  type RegrasDatasDeducoesConfig,
  type QueueServerConfig,
  type QueueServerMode,
  type TableKey,
  type ProcessDates,
  type VersaoInfo,
  uploadPDF,
} from "@/lib/data";
import { readStoredAuthSession } from "@/lib/auth-store";
import { useAuth } from "@/lib/auth-context";

const INITIAL_STARTUP_STATE: BackendStartupProgress = {
  phase: "booting-ui",
  title: "Identificação",
  detail: "Escolha como deseja entrar no AutoLiquid.",
  progress: 12,
  attempt: 0,
  elapsedMs: 0,
};

const LOADING_PULSES = [
  "Confirmando seu acesso salvo...",
  "Acordando os serviços locais...",
  "Checando o navegador de apoio...",
  "Lendo preferências da sua estação...",
  "Buscando datas globais do processo...",
  "Sincronizando regras da fila...",
  "Separando contratos e vínculos recentes...",
  "Carregando responsáveis e alertas...",
  "Organizando a fila por prioridade...",
  "Quase lá: abrindo o painel no ponto certo...",
];

const LOADING_STEPS = [
  "Acesso",
  "Navegador",
  "Serviços",
  "Preferências",
  "Dados",
  "Fila",
];
const REGISTRO_LIQUIDACAO_PENDENTE_KEY = "autoliquid_registro_liquidacao_pendente";
const IGNORAR_RETORNO_PENDENCIA_SESSION_KEY = "autoliquid_ignorar_retorno_pendencia_sessao";
const RETORNO_PENDENCIA_DISPENSADO_KEY = "autoliquid_retorno_pendencia_dispensado";
const DASHBOARD_LIMIT_OPTIONS = [5, 10, 25, 50, 100] as const;

function formatAuthDiagnostico(diagnostico: AuthDiagnostico): string {
  if (!diagnostico.tursoUrlPresente || !diagnostico.tursoTokenPresente) {
    return "Diagnóstico: este pacote não encontrou URL/token do Turso embutidos. Gere a instalação pelo workflow de release com os secrets configurados.";
  }
  if (!diagnostico.configEmbutidaExiste && !diagnostico.envTursoUrlPresente && !diagnostico.envTursoTokenPresente) {
    return "Diagnóstico: a configuração embutida da release não foi encontrada no app instalado.";
  }
  if (!diagnostico.consultaTursoOk) {
    const host = diagnostico.tursoHost ? ` Host: ${diagnostico.tursoHost}.` : "";
    const erro = diagnostico.erroResumo ? ` Erro: ${diagnostico.erroResumo}` : "";
    return `Diagnóstico: o app encontrou a configuração do Turso, mas não conseguiu consultar o banco.${host}${erro}`;
  }
  return "";
}

const DASHBOARD_LABELS = {
  dia: "Hoje",
  semana: "Semana",
  mes: "30 dias",
  "este-mes": "Este mês",
} as const;

type MainTab = "dashboard" | "painel" | "liquidacao" | "registro";

interface QueueDisplayColumn {
  key: keyof QueueDisplayRow;
  label: string;
  defaultWidth: number;
}

interface QueueDisplayRow {
  rowKey: string;
  responsavel: string;
  responsavelAlterado: boolean;
  responsavelAlteradoPor: string;
  responsavelAlteradoEm: string;
  concluido: boolean;
  concluidoPor: string;
  concluidoEm: string;
  alertas: FilaAlerta[];
  nfServicoAlerta: boolean;
  nfServicoAlertaTooltip: string;
  competencia: string;
  tipo: string;
  cpfCnpj: string;
  credor: string;
  valor: string;
  contrato: string;
  ic: string;
  dataEnc: string;
  setorOrigem: string;
  numeroProcesso: string;
  processoSolar: string;
  solPagamento: string;
}

interface RegistroLiquidacaoPendente {
  documentoId: string;
  numeroProcesso: string;
  criadoEm?: string;
}

const QUEUE_SERVER_STORAGE_KEY = "painel_queue_servers_v1";
const QUEUE_VISIBLE_COLUMNS_STORAGE_KEY = "painel_queue_columns_v1";
const QUEUE_COMPACT_COLUMNS_STORAGE_KEY = "painel_queue_compact_columns_v1";
const QUEUE_COLUMN_WIDTHS_STORAGE_KEY = "painel_queue_column_widths_v1";
const QUEUE_MOSTRAR_TIPO_BADGES_KEY = "painel_mostrar_tipo_badges_v1";
const QUEUE_MOSTRAR_SIMPLES_KEY = "painel_mostrar_simples_v1";
const MIN_QUEUE_COLUMN_WIDTH = 44;
const DEFAULT_QUEUE_SERVERS: QueueServerConfig[] = [
  { id: "diego", nome: "Diego", modo: "ativo" },
  { id: "rubens", nome: "Rubens", modo: "ativo" },
  { id: "gabriel", nome: "Gabriel", modo: "ativo" },
  { id: "karine", nome: "Karine", modo: "ativo" },
  { id: "ramone", nome: "Ramone", modo: "metade" },
];
const ALERTA_SERVICO_TIPO_TODOS = "__TODOS__";
const ALERTA_SERVICO_REGRA_PADRAO_ID = "alerta-servico-padrao";
const ALERTA_SERVICO_BASE_TIPOS = [
  "NF Serviço",
  "NF Material",
  "Boleto",
  "Proc. Origem",
  "Fatura",
  "Recibo",
] as const;
const ALERTA_SERVICO_REGRA_PADRAO: AlertaServicoRule = {
  id: ALERTA_SERVICO_REGRA_PADRAO_ID,
  active: true,
  tipoDocumento: "NF Serviço",
  cnpj: "",
  setor: "",
  acaoVencimento: "DIA_FIXO_MES_SEGUINTE",
  valorAcao: "20",
};
const DEFAULT_ALERTA_SERVICO_CONFIG: AlertaServicoConfig = {
  diasUteisPadrao: 3,
  regras: [ALERTA_SERVICO_REGRA_PADRAO],
};
const DEFAULT_ALERTA_SERVICO_RULE: AlertaServicoRule = {
  id: "",
  active: true,
  tipoDocumento: ALERTA_SERVICO_TIPO_TODOS,
  cnpj: "",
  setor: "",
  acaoVencimento: "IGNORAR",
  valorAcao: "",
};
const DEFAULT_REGRAS_DATAS_DEDUCOES: RegrasDatasDeducoesConfig = {
  versao: 1,
  regras: [],
};
const LEGACY_DISTRIBUTION_NAMES = [
  "Diego", "Rubens", "Karine", "Gabriel", "Ramone", "Diego", "Karine", "Ramone", "Rubens", "Gabriel",
  "Karine", "Gabriel", "Diego", "Ramone", "Rubens", "Karine", "Rubens", "Gabriel", "Ramone", "Diego",
  "Gabriel", "Karine", "Ramone", "Rubens", "Diego", "Gabriel", "Diego", "Ramone", "Karine", "Rubens",
  "Rubens", "Diego", "Gabriel", "Karine", "Ramone", "Rubens", "Ramone", "Karine", "Diego", "Gabriel",
  "Ramone", "Rubens", "Karine", "Diego", "Gabriel", "Ramone", "Gabriel", "Rubens", "Karine", "Diego",
  "Diego", "Ramone", "Rubens", "Gabriel", "Karine", "Diego", "Ramone", "Gabriel", "Karine", "Rubens",
  "Karine", "Diego", "Ramone", "Rubens", "Gabriel", "Karine", "Gabriel", "Ramone", "Diego", "Rubens",
  "Gabriel", "Ramone", "Diego", "Karine", "Rubens", "Gabriel", "Rubens", "Diego", "Ramone", "Karine",
  "Rubens", "Karine", "Gabriel", "Ramone", "Diego", "Rubens", "Ramone", "Karine", "Gabriel", "Diego",
  "Ramone", "Gabriel", "Rubens", "Diego", "Karine", "Ramone", "Diego", "Rubens", "Gabriel", "Karine",
] as const;
const QUEUE_DISPLAY_COLUMNS: QueueDisplayColumn[] = [
  { key: "responsavel", label: "Responsável", defaultWidth: 182 },
  { key: "competencia", label: "Competência", defaultWidth: 100 },
  { key: "tipo", label: "Tipo", defaultWidth: 140 },
  { key: "cpfCnpj", label: "CPF/CNPJ", defaultWidth: 132 },
  { key: "credor", label: "Credor", defaultWidth: 280 },
  { key: "valor", label: "Valor", defaultWidth: 110 },
  { key: "contrato", label: "Contrato", defaultWidth: 110 },
  { key: "ic", label: "IC", defaultWidth: 110 },
  { key: "dataEnc", label: "Data Enc.", defaultWidth: 102 },
  { key: "setorOrigem", label: "Setor Origem", defaultWidth: 112 },
  { key: "numeroProcesso", label: "Nº Processo", defaultWidth: 88 },
  { key: "solPagamento", label: "Sol. Pag.", defaultWidth: 108 },
];

const QUEUE_COMPACT_COLUMN_CLASSES: Partial<Record<keyof QueueDisplayRow, string>> = {
  responsavel: "min-w-[120px] max-w-[150px]",
  competencia: "min-w-[82px] max-w-[96px]",
  tipo: "min-w-[96px] max-w-[120px]",
  cpfCnpj: "min-w-[112px] max-w-[128px]",
  credor: "min-w-[220px] max-w-[280px]",
  valor: "min-w-[90px] max-w-[108px]",
  contrato: "min-w-[92px] max-w-[110px]",
  ic: "min-w-[82px] max-w-[100px]",
  dataEnc: "min-w-[88px] max-w-[100px]",
  setorOrigem: "min-w-[86px] max-w-[106px]",
  numeroProcesso: "min-w-[74px] max-w-[92px]",
  solPagamento: "min-w-[92px] max-w-[110px]",
};

function normalizeQueueCell(value: string | number | null | undefined): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function extractSolarProcessNumber(...values: Array<string | number | null | undefined>): string {
  for (const value of values) {
    const normalized = normalizeQueueCell(value);
    const match = normalized.match(/\b\d{5}\.\d{5,6}\/\d{4}(?:-\d{2})?\b/);
    if (match) return match[0];
  }
  return "";
}

function formatFilaProcessoCurto(value: string | number | null | undefined): string {
  const text = normalizeQueueCell(value);
  const match = text.match(/\b23080\.(\d{1,6})\/(\d{4})(?:-\d{2})?\b/);
  if (!match) return text;
  const numero = match[1].replace(/^0+/, "") || "0";
  return `${numero}/${match[2].slice(-2)}`;
}

function normalizeCnpj(value: string | number | null | undefined): string {
  return String(value ?? "").replace(/\D+/g, "");
}

function normalizeTipoDocumento(value: string | number | null | undefined): string {
  const normalized = normalizeQueueCell(value);
  return normalized === ALERTA_SERVICO_TIPO_TODOS ? "" : normalized;
}

function formatRuleScope(value: string): string {
  return normalizeQueueCell(value) || "Todos";
}

function formatMesVencimentoDeducao(value: RegraDataDeducao["mesVencimento"]): string {
  if (value === "atual") return "Mesmo mês";
  if (value === "usuario") return "Usuário informa";
  return "Mês seguinte";
}

function formatApuracaoDeducao(value: RegraDataDeducao["apuracao"]): string {
  return value === "usuario" ? "usuário informa" : "emissão mais antiga";
}

function formatAjusteDiaNaoUtilDeducao(value: RegraDataDeducao["ajusteDiaNaoUtil"]): string {
  if (value === "prorrogar") return "Prorrogar para próximo dia útil";
  if (value === "manter") return "Manter data";
  return "Antecipar para dia útil anterior";
}

function normalizeCodigoDeducao(value: string): string {
  return value.replace(/\D+/g, "");
}

function padDeducaoDatePart(value: number): string {
  return String(value).padStart(2, "0");
}

function formatDeducaoDateShortBR(value: Date): string {
  return `${padDeducaoDatePart(value.getDate())}/${padDeducaoDatePart(value.getMonth() + 1)}`;
}

function formatDeducaoDateBR(value: Date): string {
  return `${formatDeducaoDateShortBR(value)}/${value.getFullYear()}`;
}

function weekdayDeducaoBR(value: Date): string {
  return ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado"][value.getDay()];
}

function deducaoMonthDateWithDay(base: Date, monthOffset: number, day: number): Date {
  const year = base.getFullYear();
  const month = base.getMonth() + monthOffset;
  const lastDay = new Date(year, month + 1, 0).getDate();
  return new Date(year, month, Math.min(Math.max(1, day), lastDay));
}

function isDeducaoBusinessDay(value: Date): boolean {
  return value.getDay() !== 0 && value.getDay() !== 6;
}

function adjustDeducaoNonBusinessDate(value: Date, mode: RegraDataDeducao["ajusteDiaNaoUtil"]): Date {
  const adjusted = new Date(value);
  if (mode === "manter") return adjusted;
  if (mode === "prorrogar") {
    while (!isDeducaoBusinessDay(adjusted)) adjusted.setDate(adjusted.getDate() + 1);
    return adjusted;
  }
  while (!isDeducaoBusinessDay(adjusted)) adjusted.setDate(adjusted.getDate() - 1);
  return adjusted;
}

function buildDeducaoRulePreview(rule: RegraDataDeducao): string {
  const today = new Date();
  const emissao = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (rule.mesVencimento === "usuario") {
    return `Simulação: se a nota for emitida em ${formatDeducaoDateShortBR(emissao)}, o vencimento será informado pelo usuário no processo.`;
  }

  const dia = Math.max(1, Math.min(31, Number(rule.diaVencimento || 20)));
  const alvo = rule.mesVencimento === "atual"
    ? deducaoMonthDateWithDay(emissao, 0, dia)
    : deducaoMonthDateWithDay(emissao, 1, dia);
  const ajuste = rule.ajusteDiaNaoUtil || "antecipar";
  const vencimento = adjustDeducaoNonBusinessDate(alvo, ajuste);
  const apuracao = rule.apuracao === "usuario" ? "com apuração informada pelo usuário" : `com apuração em ${formatDeducaoDateShortBR(emissao)}`;

  let ajusteTexto = "";
  if (vencimento.getTime() !== alvo.getTime()) {
    ajusteTexto = vencimento < alvo
      ? `, antecipado do dia ${formatDeducaoDateShortBR(alvo)}`
      : `, prorrogado do dia ${formatDeducaoDateShortBR(alvo)}`;
  } else if (ajuste === "manter" && !isDeducaoBusinessDay(alvo)) {
    ajusteTexto = ", mantendo a data mesmo não útil";
  }

  return `Simulação: se a nota for emitida em ${formatDeducaoDateShortBR(emissao)}, ${apuracao}, o vencimento será em ${formatDeducaoDateBR(vencimento)} (${weekdayDeducaoBR(vencimento)}${ajusteTexto}).`;
}

function buildDeducaoRuleSummary(rule: RegraDataDeducao): string {
  if (rule.mesVencimento === "usuario") return "Datas informadas pelo usuário";
  const dia = rule.diaVencimento ? `dia ${rule.diaVencimento}` : "dia não definido";
  return `${formatApuracaoDeducao(rule.apuracao)} · vencimento no ${dia} do ${formatMesVencimentoDeducao(rule.mesVencimento).toLowerCase()}`;
}

function formatAlertaServicoAcao(rule: AlertaServicoRule): string {
  if (rule.acaoVencimento === "IGNORAR") return "Não participa";
  if (rule.acaoVencimento === "DATA_PERSONALIZADA") {
    return rule.valorAcao ? `Vence em ${rule.valorAcao}` : "Data personalizada";
  }
  return `Dia ${rule.valorAcao || "20"} do mês seguinte`;
}

function normalizeAlertaServicoConfig(config: Partial<AlertaServicoConfig> | null | undefined): AlertaServicoConfig {
  const rawRules = Array.isArray(config?.regras) ? config.regras : [];
  const defaultRule = rawRules.find((rule) => rule.id === ALERTA_SERVICO_REGRA_PADRAO_ID);
  const customRules = rawRules.filter((rule) => rule.id !== ALERTA_SERVICO_REGRA_PADRAO_ID);
  return {
    ...DEFAULT_ALERTA_SERVICO_CONFIG,
    ...config,
    diasUteisPadrao: Math.max(0, Math.min(60, Number(config?.diasUteisPadrao ?? DEFAULT_ALERTA_SERVICO_CONFIG.diasUteisPadrao) || 0)),
    regras: [
      { ...ALERTA_SERVICO_REGRA_PADRAO, ...(defaultRule ?? {}) },
      ...customRules,
    ],
  };
}

function matchesAlertaServicoRule(
  rule: AlertaServicoRule,
  tipo: string,
  cnpj: string,
  setor: string,
): boolean {
  if (!rule.active) return false;
  const ruleTipo = normalizeTipoDocumento(rule.tipoDocumento).toLocaleLowerCase("pt-BR");
  const ruleCnpj = normalizeCnpj(rule.cnpj);
  const ruleSetor = normalizeQueueCell(rule.setor).toLocaleLowerCase("pt-BR");
  if (ruleTipo && ruleTipo !== tipo) return false;
  if (ruleCnpj && ruleCnpj !== cnpj) return false;
  if (ruleSetor && ruleSetor !== setor) return false;
  return true;
}

function getAlertaServicoRuleScore(rule: AlertaServicoRule): number {
  return (
    (normalizeTipoDocumento(rule.tipoDocumento) ? 1 : 0)
    + (normalizeCnpj(rule.cnpj) ? 2 : 0)
    + (normalizeQueueCell(rule.setor) ? 4 : 0)
  );
}

function parseValorBRL(valor: string): number {
  // "R$ 1.274,59" → 1274.59
  const n = parseFloat(valor.replace(/[R$\s.]/g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

function formatValorCompact(valor: number): string {
  if (valor >= 1_000_000) return `R$ ${(valor / 1_000_000).toFixed(1).replace(".", ",")}M`;
  if (valor >= 1_000) return `R$ ${(valor / 1_000).toFixed(1).replace(".", ",")}K`;
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valor);
}

interface TipoEntry {
  label: string;  // nome completo (para tooltip)
  abbr: string;   // versão curta (exibida na badge)
  style: string;
  priority: boolean;
}

// Each pattern captures a known tipo; order matters — more specific first.
const TIPO_PATTERNS: Array<{ regex: RegExp; label: string; abbr: string; style: string; priority?: boolean }> = [
  { regex: /proc\.?\s*origem/i,  label: "Proc. Origem", abbr: "P. Orig.", style: "border-rose-500/35 bg-rose-500/10 text-rose-700",     priority: true },
  { regex: /nf\s*servi[çc]o/i,   label: "NF Serviço",   abbr: "NF Srv.",  style: "border-violet-500/35 bg-violet-500/10 text-violet-700" },
  { regex: /nf\s*material/i,     label: "NF Material",  abbr: "NF Mat.",  style: "border-sky-500/35 bg-sky-500/10 text-sky-700" },
  { regex: /fatura/i,            label: "Fatura",       abbr: "Fatura",   style: "border-indigo-500/35 bg-indigo-500/10 text-indigo-700" },
  { regex: /boleto/i,            label: "Boleto",       abbr: "Boleto",   style: "border-amber-500/35 bg-amber-500/10 text-amber-700" },
  { regex: /bolsa/i,             label: "Bolsa",        abbr: "Bolsa",    style: "border-teal-500/35 bg-teal-500/10 text-teal-700" },
];

const TIPO_DEFAULT_STYLE = "border-glass-border bg-muted/40 text-muted-foreground";

function _extractTipos(raw: string, out: TipoEntry[]): void {
  let remaining = raw.trim();
  if (!remaining) return;

  let anyMatch = false;
  while (remaining.length > 0) {
    let found = false;
    for (const p of TIPO_PATTERNS) {
      const m = remaining.match(p.regex);
      if (m && m.index !== undefined) {
        out.push({ label: p.label, abbr: p.abbr, style: p.style, priority: Boolean(p.priority) });
        remaining = (remaining.slice(0, m.index) + remaining.slice(m.index + m[0].length)).trim();
        anyMatch = true;
        found = true;
        break;
      }
    }
    if (!found) {
      // No pattern matched — keep literal remainder
      if (remaining) out.push({ label: remaining, abbr: remaining, style: TIPO_DEFAULT_STYLE, priority: false });
      break;
    }
  }
  void anyMatch; // used only for intent clarity
}

function parseTipos(tipo: string): TipoEntry[] {
  if (!tipo) return [];
  // Try hard-delimiter split first (/, +, ;, |, comma); space is intentionally NOT here
  // because known types like "NF Serviço" or "NF Material" contain spaces.
  const parts = tipo.split(/[\/+;|,]/).map((p) => p.trim()).filter(Boolean);
  const entries: TipoEntry[] = [];
  if (parts.length > 1) {
    // Delimiter-separated — but still run pattern extraction on each part
    // to normalise labels (e.g. "Proc.Origem" → "Proc. Origem")
    for (const part of parts) _extractTipos(part, entries);
  } else {
    // Single string — extract all known types greedy (handles "Fatura NF Serviço")
    _extractTipos(tipo, entries);
  }
  // Proc. Origem always first
  return entries.sort((a, b) => {
    if (a.priority && !b.priority) return -1;
    if (!a.priority && b.priority) return 1;
    return 0;
  });
}

function loadQueueMostrarTipoBadges(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const v = window.localStorage.getItem(QUEUE_MOSTRAR_TIPO_BADGES_KEY);
    return v === null ? true : v === "1";
  } catch { return true; }
}

function loadQueueMostrarSimples(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const v = window.localStorage.getItem(QUEUE_MOSTRAR_SIMPLES_KEY);
    return v === null ? true : v === "1";
  } catch { return true; }
}

function firstNameOf(value: string): string {
  return normalizeQueueCell(value).split(" ")[0]?.toLocaleLowerCase("pt-BR") ?? "";
}

function formatFirstNameLabel(value: string): string {
  if (!value) return "";
  return value.charAt(0).toLocaleUpperCase("pt-BR") + value.slice(1);
}

function formatResponsavelTooltip(autor: string, alteradoEm: string): string {
  const parts: string[] = [];
  if (autor) parts.push(`Alterado por ${autor}`);
  const parsed = alteradoEm ? new Date(alteradoEm) : null;
  if (parsed && !Number.isNaN(parsed.getTime())) {
    parts.push(
      `em ${parsed.toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
      })} às ${parsed.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit",
      })}`
    );
  }
  return parts.join(" ") || "Responsável alterado manualmente";
}

function parseFilaAlertas(value: string | number | null | undefined): FilaAlerta[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(String(value));
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => ({
        id: Number(item?.id ?? 0),
        mensagem: normalizeQueueCell(item?.mensagem),
        autor: normalizeQueueCell(item?.autor),
        criadoEm: normalizeQueueCell(item?.criadoEm) || null,
      }))
      .filter((item) => item.id && item.mensagem);
  } catch {
    return [];
  }
}

function getQueueRawRowKey(row: Record<string, unknown>): string {
  return `${normalizeQueueCell(row["Número Processo"] as string | number | null | undefined)}::${normalizeQueueCell(row["Sol. Pagamento"] as string | number | null | undefined)}`;
}

function formatAlertaCriadoEm(value?: string | null): string {
  const parsed = value ? new Date(value) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function normalizeDashboardStatus(status?: string | null): "concluido" | "aguardando" {
  return String(status || "").toLocaleLowerCase("pt-BR").includes("concl")
    ? "concluido"
    : "aguardando";
}

function normalizeDataEnc(value: string | number | null | undefined): string {
  const text = normalizeQueueCell(value);
  const match = text.match(/^(\d{1,2}\/\d{1,2}\/\d{4})/);
  return match ? match[1] : text;
}

function parseCompetenciaToTimestamp(value: string): number {
  const match = normalizeQueueCell(value).match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return Number.MAX_SAFE_INTEGER;
  const [, day, month, year] = match;
  return new Date(Number(year), Number(month) - 1, Number(day)).getTime();
}

function parseDateBR(value: string): Date | null {
  const match = normalizeQueueCell(value).match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;
  const [, day, month, year] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateBR(date: Date): string {
  return date.toLocaleDateString("pt-BR");
}

function isBusinessDay(date: Date): boolean {
  const day = date.getDay();
  return day !== 0 && day !== 6;
}

function getNfServicoDeadline(competencia: Date): Date {
  const prazo = new Date(competencia.getFullYear(), competencia.getMonth() + 1, 20);
  while (!isBusinessDay(prazo)) {
    prazo.setDate(prazo.getDate() - 1);
  }
  return prazo;
}

function getFixedDayNextMonthDeadline(competencia: Date, day: string): Date {
  const parsedDay = Math.max(1, Math.min(31, Number(day) || 20));
  const lastDay = new Date(competencia.getFullYear(), competencia.getMonth() + 2, 0).getDate();
  const prazo = new Date(competencia.getFullYear(), competencia.getMonth() + 1, Math.min(parsedDay, lastDay));
  while (!isBusinessDay(prazo)) {
    prazo.setDate(prazo.getDate() - 1);
  }
  return prazo;
}

function businessDaysUntil(target: Date, now: Date = new Date()): number {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const end = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  if (start.getTime() === end.getTime()) return 0;

  const step = start < end ? 1 : -1;
  const cursor = new Date(start);
  let count = 0;

  while (cursor.getTime() !== end.getTime()) {
    cursor.setDate(cursor.getDate() + step);
    if (isBusinessDay(cursor)) {
      count += step;
    }
  }

  return count;
}

function buildNfServicoAlert(
  tipo: string,
  competencia: string,
  cpfCnpj: string,
  setorOrigem: string,
  regras: AlertaServicoConfig,
): {
  ativo: boolean;
  tooltip: string;
} {
  const normalizedTipo = normalizeQueueCell(tipo).toLocaleLowerCase("pt-BR");
  const cnpj = normalizeCnpj(cpfCnpj);
  const setor = normalizeQueueCell(setorOrigem).toLocaleLowerCase("pt-BR");
  const competenciaDate = parseDateBR(competencia);
  if (!competenciaDate) {
    return { ativo: false, tooltip: "" };
  }

  const normalizedRegras = normalizeAlertaServicoConfig(regras);
  const defaultRule = normalizedRegras.regras.find((rule) => rule.id === ALERTA_SERVICO_REGRA_PADRAO_ID);
  const isNfServico = normalizedTipo.includes("serviço") || normalizedTipo.includes("servico");

  const matchingRule = (normalizedRegras.regras || []).reduce<{
    rule: AlertaServicoRule;
    score: number;
    index: number;
  } | null>((best, rule, index) => {
    if (!matchesAlertaServicoRule(rule, normalizedTipo, cnpj, setor)) return best;
    const score = getAlertaServicoRuleScore(rule);
    if (!best || score > best.score || (score === best.score && index > best.index)) {
      return { rule, score, index };
    }
    return best;
  }, null)?.rule;

  if (!matchingRule && isNfServico && defaultRule && !defaultRule.active) {
    return { ativo: false, tooltip: "" };
  }

  if (matchingRule?.acaoVencimento === "IGNORAR") {
    return { ativo: false, tooltip: "" };
  }

  if (!isNfServico && !matchingRule) {
    return { ativo: false, tooltip: "" };
  }

  const prazo = matchingRule?.acaoVencimento === "DATA_PERSONALIZADA" && matchingRule.valorAcao
    ? new Date(`${matchingRule.valorAcao}T00:00:00`)
    : getFixedDayNextMonthDeadline(
        competenciaDate,
        matchingRule?.acaoVencimento === "DIA_FIXO_MES_SEGUINTE" ? matchingRule.valorAcao : "20",
      );
  if (Number.isNaN(prazo.getTime())) {
    return { ativo: false, tooltip: "" };
  }
  const diasRestantes = businessDaysUntil(prazo);
  const limite = Math.max(0, normalizedRegras.diasUteisPadrao);
  const ativo = diasRestantes <= limite;
  const regraLabel = matchingRule?.id === ALERTA_SERVICO_REGRA_PADRAO_ID || !matchingRule
    ? "Alerta de serviço"
    : "Exceção do alerta de serviço";

  if (!ativo) {
    return { ativo: false, tooltip: "" };
  }

  if (diasRestantes < 0) {
    return {
      ativo: true,
      tooltip: `${regraLabel}: competência ${competencia} tem prazo em ${formatDateBR(prazo)} e está vencida há ${Math.abs(diasRestantes)} dia(s) útil(eis).`,
    };
  }

  return {
    ativo: true,
    tooltip: `${regraLabel}: competência ${competencia} tem prazo em ${formatDateBR(prazo)}. Faltam ${diasRestantes} dia(s) útil(eis).`,
  };
}

function loadQueueServerConfigs(): QueueServerConfig[] {
  if (typeof window === "undefined") {
    return DEFAULT_QUEUE_SERVERS;
  }

  try {
    const raw = window.localStorage.getItem(QUEUE_SERVER_STORAGE_KEY);
    if (!raw) return DEFAULT_QUEUE_SERVERS;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_QUEUE_SERVERS;

    const configs = parsed
      .filter((item): item is QueueServerConfig =>
        Boolean(item)
        && typeof item.id === "string"
        && typeof item.nome === "string"
        && ["ativo", "metade", "fora"].includes(String(item.modo))
      )
      .map((item) => ({
        id: item.id,
        nome: item.nome,
        modo: item.modo,
      }));

    return configs.length > 0 ? configs : DEFAULT_QUEUE_SERVERS;
  } catch {
    return DEFAULT_QUEUE_SERVERS;
  }
}

function loadVisibleQueueColumns(): Array<keyof QueueDisplayRow> {
  const validKeys = QUEUE_DISPLAY_COLUMNS.map((column) => column.key);
  if (typeof window === "undefined") {
    return validKeys;
  }

  try {
    const raw = window.localStorage.getItem(QUEUE_VISIBLE_COLUMNS_STORAGE_KEY);
    if (!raw) return validKeys;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return validKeys;
    const filtered = parsed.filter((key): key is keyof QueueDisplayRow => validKeys.includes(key));
    const missing = validKeys.filter((key) => !filtered.includes(key));
    const ordered = [...filtered, ...missing];
    return ordered.length > 0 ? ordered : validKeys;
  } catch {
    return validKeys;
  }
}

function loadCompactQueueColumns(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(QUEUE_COMPACT_COLUMNS_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function loadQueueColumnWidths(): Partial<Record<keyof QueueDisplayRow, number>> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(QUEUE_COLUMN_WIDTHS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const validKeys = new Set(QUEUE_DISPLAY_COLUMNS.map((column) => column.key));
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([key, value]) => validKeys.has(key as keyof QueueDisplayRow) && typeof value === "number")
        .map(([key, value]) => [key, Math.max(MIN_QUEUE_COLUMN_WIDTH, Math.min(520, Number(value)))])
    ) as Partial<Record<keyof QueueDisplayRow, number>>;
  } catch {
    return {};
  }
}

function hashProcessIdentifier(seed: string): number {
  let hash = 2166136261;
  for (const char of seed) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function normalizeServerKey(name: string): string {
  return name.trim().toLocaleLowerCase("pt-BR");
}

function shouldUseHalfSlot(
  _slotName: string,
  _slotIndex: number,
  occurrenceIndex: number,
): boolean {
  // Extensão da fórmula original: qualquer servidor em modo 1/2
  // participa somente nas ocorrências ímpares da sua sequência dentro
  // da lista-base de 100 posições, replicando o padrão do "Ramone 1/2".
  return occurrenceIndex % 2 === 0;
}

function buildDistributionSlots(queueServers: QueueServerConfig[]) {
  const slots: Array<{ name: string; key: string; halfEligible: boolean }> = [];
  const occurrenceByName = new Map<string, number>();

  for (let index = 0; index < LEGACY_DISTRIBUTION_NAMES.length; index += 1) {
    const name = LEGACY_DISTRIBUTION_NAMES[index];
    const key = normalizeServerKey(name);
    const occurrence = occurrenceByName.get(key) ?? 0;
    occurrenceByName.set(key, occurrence + 1);
    slots.push({
      name,
      key,
      halfEligible: shouldUseHalfSlot(name, index, occurrence),
    });
  }

  const legacyNames = new Set(Array.from(LEGACY_DISTRIBUTION_NAMES, normalizeServerKey));
  const extraServers = queueServers.filter((server) => {
    const nome = server.nome.trim();
    return nome && !legacyNames.has(normalizeServerKey(nome));
  });

  for (const server of extraServers) {
    const nome = server.nome.trim();
    const key = normalizeServerKey(nome);
    for (let index = 0; index < 20; index += 1) {
      slots.push({
        name: nome,
        key,
        halfEligible: index % 2 === 0,
      });
    }
  }

  return slots;
}

function sortearResponsavel(
  numeroProcesso: string,
  queueServers: QueueServerConfig[],
): string {
  const serverMap = new Map(
    queueServers
      .filter((server) => server.nome.trim())
      .map((server) => [normalizeServerKey(server.nome), { ...server, nome: server.nome.trim() }]),
  );
  const slots = buildDistributionSlots(queueServers);
  const activeSlots = slots.filter((slot) => {
    const server = serverMap.get(slot.key);
    if (!server || server.modo === "fora") return false;
    if (server.modo === "metade") return slot.halfEligible;
    return true;
  });

  if (activeSlots.length === 0) {
    return "Ninguém ativo";
  }

  const idCalculo = Number(numeroProcesso.replace(/\D+/g, "") || "0");
  const totalSlots = slots.length;
  const posBase = ((Math.floor(idCalculo * 7919) % totalSlots) + totalSlots) % totalSlots;

  let bestWeight = -1;
  let bestName = activeSlots[0]?.name ?? "Ninguém ativo";

  for (let index = 0; index < slots.length; index += 1) {
    const slot = slots[index];
    const server = serverMap.get(slot.key);
    if (!server || server.modo === "fora") continue;
    if (server.modo === "metade" && !slot.halfEligible) continue;

    const sequenceIndex = index + 1;
    const weightBase = Math.floor(idCalculo * (sequenceIndex * 104729 + 13));
    const weight = ((weightBase % 10000) + 10000) % 10000
      + (index === posBase ? 1000000 : 0);

    if (weight > bestWeight) {
      bestWeight = weight;
      bestName = slot.name;
    }
  }

  return bestName;
}

function buildFilaDistribuida(
  filaProcessos: FilaProcessosInfo | null,
  queueServers: QueueServerConfig[],
  alertaServicoConfig: AlertaServicoConfig,
): QueueDisplayRow[] {
  if (!filaProcessos?.rows?.length) return [];

  return filaProcessos.rows.map((row) => {
    const numeroProcesso = normalizeQueueCell(row["Número Processo"]);
    const processoSolar = extractSolarProcessNumber(
      row["Número Processo"],
      row["Protocolo"],
      row["protocolo"],
    );
    const solPagamento = normalizeQueueCell(row["Sol. Pagamento"]);
    const recebidoPor = normalizeQueueCell(row["Recebido Por"]);
    const responsavelManual = normalizeQueueCell(row["__responsavel_manual"]);
    const responsavelSorteado = normalizeQueueCell(row["__responsavel_sorteado"]);
    const responsavelAlterado = Boolean(row["__responsavel_alterado"]) && Boolean(responsavelManual);
    const responsavelAlteradoPor = normalizeQueueCell(row["__responsavel_alterado_por"]);
    const responsavelAlteradoEm = normalizeQueueCell(row["__responsavel_alterado_em"]);
    const concluido = Boolean(row["__concluido"]);
    const concluidoPor = normalizeQueueCell(row["__concluido_por"]);
    const concluidoEm = normalizeQueueCell(row["__concluido_em"]);
    const alertas = parseFilaAlertas(row["__alertas_json"]);
    const tipo = normalizeQueueCell(row["Tipo"]);
    const competencia = normalizeQueueCell(row["Competência"]);
    const cpfCnpj = normalizeQueueCell(row["CPF/CNPJ"]);
    const setorOrigem = normalizeQueueCell(row["Setor Origem"]);
    const nfServicoAlert = buildNfServicoAlert(tipo, competencia, cpfCnpj, setorOrigem, alertaServicoConfig);

    return {
      rowKey: `${numeroProcesso}::${solPagamento}`,
      responsavel: responsavelManual || recebidoPor || responsavelSorteado || sortearResponsavel(numeroProcesso || processoSolar, queueServers),
      responsavelAlterado,
      responsavelAlteradoPor,
      responsavelAlteradoEm,
      concluido,
      concluidoPor,
      concluidoEm,
      alertas,
      nfServicoAlerta: nfServicoAlert.ativo,
      nfServicoAlertaTooltip: nfServicoAlert.tooltip,
      competencia,
      tipo,
      cpfCnpj,
      credor: normalizeQueueCell(row["Fornecedor/Interessado"]),
      valor: normalizeQueueCell(row["Valor"]),
      contrato: normalizeQueueCell(row["Contrato"]),
      ic: normalizeQueueCell(row["IC"]),
      dataEnc: normalizeDataEnc(row["Data Enc."]),
      setorOrigem,
      numeroProcesso,
      processoSolar,
      solPagamento,
    };
  }).sort((a, b) => {
    const byCompetencia = parseCompetenciaToTimestamp(a.competencia) - parseCompetenciaToTimestamp(b.competencia);
    if (byCompetencia !== 0) return byCompetencia;
    return (a.numeroProcesso || a.processoSolar).localeCompare(
      b.numeroProcesso || b.processoSolar,
      "pt-BR",
      { numeric: true },
    );
  });
}

function buildQueueProcessCounts(rows: QueueDisplayRow[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = normalizeServerKey(row.responsavel);
    if (!key || key === normalizeServerKey("Ninguém ativo")) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

function getFilaUpdatedAtTime(data: FilaProcessosInfo | null): number {
  if (!data?.updatedAt) return 0;
  const raw = String(data.updatedAt).trim();
  const normalized = /^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/.test(raw)
    ? `${raw.replace(" ", "T")}Z`
    : raw;
  const parsed = new Date(normalized).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

function isFilaSnapshotFresh(next: FilaProcessosInfo, current: FilaProcessosInfo | null): boolean {
  if (!current) return true;
  const nextTime = getFilaUpdatedAtTime(next);
  const currentTime = getFilaUpdatedAtTime(current);
  if (nextTime && currentTime && nextTime < currentTime) return false;
  return true;
}

function getDifficultyTone(value: number) {
  if (value <= 3) {
    return {
      color: "#10b981",
      bg: "bg-emerald-500",
      text: "text-emerald-700",
      ring: "ring-emerald-500/20",
      label: "Rotineiro",
    };
  }
  if (value <= 6) {
    return {
      color: "#f59e0b",
      bg: "bg-amber-500",
      text: "text-amber-700",
      ring: "ring-amber-500/20",
      label: "Atenção Média",
    };
  }
  if (value <= 8) {
    return {
      color: "#f43f5e",
      bg: "bg-rose-500",
      text: "text-rose-700",
      ring: "ring-rose-500/20",
      label: "Trabalhoso",
    };
  }
  return {
    color: "#e11d48",
    bg: "bg-rose-600",
    text: "text-rose-800",
    ring: "ring-rose-500/25",
    label: "Alta Complexidade",
  };
}

function formatDifficultyValue(value: number): string {
  return Number.isInteger(value)
    ? String(value)
    : value.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function DifficultySlider({
  value,
  onChange,
  onInteract,
  disabled,
}: {
  value: number;
  onChange: (value: number) => void;
  onInteract?: () => void;
  disabled?: boolean;
}) {
  const tone = getDifficultyTone(value);
  const progress = ((value - 1) / 9) * 100;
  const ticks = Array.from({ length: 10 }, (_, index) => index + 1);
  const tooltipOffset = value === 1 ? 14 : value === 10 ? -14 : 0;

  const handleChange = (nextValue: number) => {
    onInteract?.();
    onChange(Math.round(nextValue));
  };

  return (
    <div className="rounded-2xl border border-glass-border bg-muted/20 px-4 pb-5 pt-4">
      <div className="mb-7 flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          Dificuldade
        </span>
        <span className={`rounded-full bg-background px-3 py-1 text-xs font-semibold ring-1 ring-inset ${tone.text} ${tone.ring}`}>
          {tone.label}
        </span>
      </div>

      <div
        className="relative mx-4 h-16 overflow-visible"
        style={{ "--difficulty-color": tone.color } as CSSProperties}
      >
        <div
          className={`difficulty-tooltip pointer-events-none absolute top-0 z-30 -translate-x-1/2 rounded-full px-3 py-1 text-sm font-bold text-white shadow-md transition-[left,background-color,transform,opacity] duration-300 ${tone.bg}`}
          style={{
            left: `${progress}%`,
            "--tooltip-offset": `${tooltipOffset}px`,
          } as CSSProperties}
        >
          {formatDifficultyValue(value)}
          <span className={`absolute left-1/2 top-full h-2 w-2 -translate-x-1/2 -translate-y-1/2 rotate-45 ${tone.bg}`} />
        </div>

        <div className="absolute left-0 right-0 top-10 h-3 overflow-hidden rounded-full bg-slate-200">
          <div
            className={`h-full rounded-full transition-[width,background-color] duration-300 ${tone.bg}`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="pointer-events-none absolute left-0 right-0 top-10 z-10 flex h-3 items-center justify-between px-1">
          {ticks.map((tick) => (
            <span
              key={tick}
              className={`h-1.5 w-1.5 rounded-full transition-colors duration-300 ${
                tick <= value ? "bg-white/70" : "bg-slate-400/45"
              }`}
            />
          ))}
        </div>

        <input
          type="range"
          min={1}
          max={10}
          step={1}
          value={value}
          onChange={(event) => handleChange(Number(event.target.value))}
          disabled={disabled}
          className="difficulty-range absolute left-0 right-0 top-6 z-20 h-11 w-full cursor-pointer bg-transparent disabled:cursor-not-allowed disabled:opacity-60"
          aria-label="Dificuldade da liquidação"
          aria-valuetext={`${formatDifficultyValue(value)} de 10, ${tone.label}`}
        />
      </div>

      <style jsx>{`
        .difficulty-range {
          -webkit-appearance: none;
          appearance: none;
        }

        .difficulty-range:focus {
          outline: none;
        }

        .difficulty-range::-webkit-slider-runnable-track {
          height: 12px;
          background: transparent;
          border-radius: 9999px;
        }

        .difficulty-range::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 28px;
          height: 28px;
          margin-top: -8px;
          border-radius: 9999px;
          border: 4px solid white;
          background: var(--difficulty-color);
          box-shadow: 0 10px 20px rgba(15, 23, 42, 0.18);
          transition: transform 160ms ease, background-color 240ms ease, box-shadow 160ms ease;
        }

        .difficulty-range:hover::-webkit-slider-thumb {
          transform: scale(1.1);
          box-shadow: 0 14px 28px rgba(15, 23, 42, 0.22);
        }

        .difficulty-range:active::-webkit-slider-thumb {
          transform: scale(1.16);
          box-shadow: 0 18px 34px rgba(15, 23, 42, 0.28);
        }

        .difficulty-range:focus-visible::-webkit-slider-thumb {
          box-shadow: 0 0 0 5px color-mix(in srgb, var(--difficulty-color) 22%, transparent), 0 12px 24px rgba(15, 23, 42, 0.2);
        }

        .difficulty-range::-moz-range-track {
          height: 12px;
          background: transparent;
          border-radius: 9999px;
        }

        .difficulty-range::-moz-range-thumb {
          width: 28px;
          height: 28px;
          border-radius: 9999px;
          border: 4px solid white;
          background: var(--difficulty-color);
          box-shadow: 0 10px 20px rgba(15, 23, 42, 0.18);
          transition: transform 160ms ease, background-color 240ms ease, box-shadow 160ms ease;
        }

        .difficulty-range:hover::-moz-range-thumb {
          transform: scale(1.1);
          box-shadow: 0 14px 28px rgba(15, 23, 42, 0.22);
        }

        .difficulty-range:active::-moz-range-thumb {
          transform: scale(1.16);
          box-shadow: 0 18px 34px rgba(15, 23, 42, 0.28);
        }

        .difficulty-tooltip {
          animation: difficulty-tooltip-in 180ms ease-out;
          transform: translateX(calc(-50% + var(--tooltip-offset))) translateY(0) scale(1);
        }

        @keyframes difficulty-tooltip-in {
          from {
            opacity: 0;
            transform: translateX(calc(-50% + var(--tooltip-offset))) translateY(3px) scale(0.94);
          }
          to {
            opacity: 1;
            transform: translateX(calc(-50% + var(--tooltip-offset))) translateY(0) scale(1);
          }
        }
      `}</style>
    </div>
  );
}

/** Normaliza datas vindas do Turso/SSE (que podem estar em YYYY-MM-DD) para DD/MM/AAAA */
function normalizeDateToBR(value: string): string {
  if (!value) return value;
  const trimmed = value.trim();
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(trimmed)) return trimmed;
  const iso = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
  return trimmed;
}

function normalizeDatesForDisplay(dates: ProcessDates): ProcessDates {
  return {
    apuracao: normalizeDateToBR(dates.apuracao),
    vencimento: normalizeDateToBR(dates.vencimento),
  };
}

export default function HomePage() {
  const router = useRouter();
  const auth = useAuth();
  const [activeMainTab, setActiveMainTab] = useState<MainTab>("painel");
  const [dates, setDates] = useState<ProcessDates>(MOCK_PROCESS_DATES);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isTabelasOpen, setIsTabelasOpen] = useState(false);
  const [tabelasInitialTab, setTabelasInitialTab] = useState<TableKey>("contratos");
  const [tabelasVisibleTabs, setTabelasVisibleTabs] = useState<TableKey[] | undefined>(undefined);
  const [isConfiguracoesOpen, setIsConfiguracoesOpen] = useState(false);
  const [erro, setErro] = useState("");
  const [erroInicializacao, setErroInicializacao] = useState("");
  const [apiDisponivel, setApiDisponivel] = useState(true);
  const [chromeStatus, setChromeStatus] = useState<"pronto" | "carregando" | "erro">("carregando");
  const [abrindoChrome, setAbrindoChrome] = useState(false);
  const [bannerUpdate, setBannerUpdate] = useState<VersaoInfo | null>(null);
  const [browserName, setBrowserName] = useState("Chrome");
  const [nomeUsuario, setNomeUsuario] = useState<string | null>(null); // null = ainda carregando
  const [startupState, setStartupState] =
    useState<BackendStartupProgress>(INITIAL_STARTUP_STATE);
  const [startupError, setStartupError] = useState("");
  // Persiste o startup entre navegações dentro da mesma sessão do app
  const [startupConcluido, setStartupConcluido] = useState(false);
  const [authGateReady, setAuthGateReady] = useState(true);
  const [storedAuthSession, setStoredAuthSession] = useState<AuthSession | null>(null);
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [showManualLogin, setShowManualLogin] = useState(false);
  const [loadingPulseIndex, setLoadingPulseIndex] = useState(0);
  const [registroPendente, setRegistroPendente] = useState<RegistroLiquidacaoPendente | null>(null);
  const [registroTipoDocumento, setRegistroTipoDocumento] = useState<RegistroLiquidacaoTipoDocumento>("NP");
  const [registroNumeroDocumento, setRegistroNumeroDocumento] = useState("");
  const [registroDificuldade, setRegistroDificuldade] = useState(5);
  const [registroDificuldadeInteragida, setRegistroDificuldadeInteragida] = useState(false);
  const [registroSaving, setRegistroSaving] = useState(false);
  const [registroError, setRegistroError] = useState("");
  const [registroNotice, setRegistroNotice] = useState("");
  const registroNoticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [startupRunId, setStartupRunId] = useState(0);
  const [dashboardPeriodo, setDashboardPeriodo] =
    useState<keyof typeof DASHBOARD_LABELS>("semana");
  const [dashboardProcessLimit, setDashboardProcessLimit] = useState(5);
  const [dashboard, setDashboard] = useState<DashboardInfo | null>(null);
  const [carregandoDashboard, setCarregandoDashboard] = useState(false);
  const [dashboardRefreshSeq, setDashboardRefreshSeq] = useState(0);
  const [filaProcessos, setFilaProcessos] = useState<FilaProcessosInfo | null>(null);
  const [carregandoFila, setCarregandoFila] = useState(false);
  const [erroFila, setErroFila] = useState("");
  const [queueServers, setQueueServers] = useState<QueueServerConfig[]>(() => loadQueueServerConfigs());
  const [visibleQueueColumns, setVisibleQueueColumns] = useState<Array<keyof QueueDisplayRow>>(() => loadVisibleQueueColumns());
  const [compactQueueColumns, setCompactQueueColumns] = useState(() => loadCompactQueueColumns());
  const [queueColumnWidths, setQueueColumnWidths] = useState<Partial<Record<keyof QueueDisplayRow, number>>>(() => loadQueueColumnWidths());
  const [queueSettingsOpen, setQueueSettingsOpen] = useState(false);
  const [mostrarTipoBadges, setMostrarTipoBadges] = useState(() => loadQueueMostrarTipoBadges());
  const [mostrarSimples, setMostrarSimples] = useState(() => loadQueueMostrarSimples());
  const [queueSimplesMap, setQueueSimplesMap] = useState<Record<string, boolean | null>>({});
  const [isLoadingSimples, setIsLoadingSimples] = useState(false);
  // IC lookup: contrato (SARF) → IC (IG) da tabela de contratos; null = não cadastrado
  const [queueIcOverrides, setQueueIcOverrides] = useState<Record<string, string | null>>({});
  const [responsavelFilter, setResponsavelFilter] = useState("todos");
  const [queueResponsavelDrafts, setQueueResponsavelDrafts] = useState<Record<string, string>>({});
  const [savingResponsavelKey, setSavingResponsavelKey] = useState<string | null>(null);
  const [openingSolarProcessKey, setOpeningSolarProcessKey] = useState<string | null>(null);
  const [queueAlertDrafts, setQueueAlertDrafts] = useState<Record<string, string>>({});
  const [savingAlertKey, setSavingAlertKey] = useState<string | null>(null);
  const [deletingAlertId, setDeletingAlertId] = useState<number | null>(null);
  const conclusaoPendingRef = useRef<Map<string, { latest: boolean; saving: boolean }>>(new Map());
  const queueLocalPatchesRef = useRef<Map<string, { patch: Record<string, string | number | null>; expiresAt: number }>>(new Map());
  const removedOptimisticAlertIdsRef = useRef<Set<number>>(new Set());
  const [queueConclusaoOverrides, setQueueConclusaoOverrides] = useState<
    Record<string, { concluido: boolean; concluidoPor: string; concluidoEm: string }>
  >({});
  const [nfServicoAlertaDiasUteis, setNfServicoAlertaDiasUteis] = useState(3);
  const [alertaServicoConfig, setAlertaServicoConfig] = useState<AlertaServicoConfig>(DEFAULT_ALERTA_SERVICO_CONFIG);
  const [alertaServicoSetoresHistorico, setAlertaServicoSetoresHistorico] = useState<string[]>([]);
  const [savingAlertaServicoConfig, setSavingAlertaServicoConfig] = useState(false);
  const [alertaServicoDialogOpen, setAlertaServicoDialogOpen] = useState(false);
  const [editingAlertaServicoRuleId, setEditingAlertaServicoRuleId] = useState<string | null>(null);
  const [alertaServicoRuleDraft, setAlertaServicoRuleDraft] = useState<AlertaServicoRule>(DEFAULT_ALERTA_SERVICO_RULE);
  const [regrasDatasDeducoes, setRegrasDatasDeducoes] = useState<RegrasDatasDeducoesConfig>(DEFAULT_REGRAS_DATAS_DEDUCOES);
  const [carregandoRegrasDatasDeducoes, setCarregandoRegrasDatasDeducoes] = useState(false);
  const [savingRegrasDatasDeducoes, setSavingRegrasDatasDeducoes] = useState(false);
  const [erroRegrasDatasDeducoes, setErroRegrasDatasDeducoes] = useState("");
  const [deducoesRulesDialogOpen, setDeducoesRulesDialogOpen] = useState(false);
  const [codigoDeducaoDrafts, setCodigoDeducaoDrafts] = useState<Record<string, string>>({});
  const [expandedDeducaoRuleIds, setExpandedDeducaoRuleIds] = useState<Record<string, boolean>>({});
  const [fecharAbaFila, setFecharAbaFila] = useState(false);
  const [rocketChatUnreadCount, setRocketChatUnreadCount] = useState<number | null>(null);
  const [uploadResetKey, setUploadResetKey] = useState(0);
  const [buscaProcesso, setBuscaProcesso] = useState<string | null>(null);
  const [buscaHistorico, setBuscaHistorico] = useState<{ cnpj: string; contrato?: string; contratos?: string[] } | null>(null);
  const [isDashboardOpen, setIsDashboardOpen] = useState(false);
  const [isFeriasOpen, setIsFeriasOpen] = useState(false);
  const lastSavedDatesRef = useRef(JSON.stringify(MOCK_PROCESS_DATES));
  const queueServersSyncedRef = useRef(false);
  const skipNextQueueServersSaveRef = useRef(false);
  const queueServersDirtyRef = useRef(false);
  const queueServersVersionRef = useRef(0);
  const apiStatusFailuresRef = useRef(0);
  const filaLoadPromiseRef = useRef<Promise<FilaProcessosInfo> | null>(null);

  // ── Cálculos memoizados — evita recalcular em renders causados por outros estados ──
  const filaDistribuidaBase = useMemo(
    () => buildFilaDistribuida(filaProcessos, queueServers, alertaServicoConfig),
    [filaProcessos, queueServers, alertaServicoConfig],
  );
  const filaDistribuida = useMemo(
    () => filaDistribuidaBase.map((row) => {
      const override = queueConclusaoOverrides[row.rowKey];
      return override ? { ...row, ...override } : row;
    }),
    [filaDistribuidaBase, queueConclusaoOverrides],
  );
  const queueColumnsToRender = useMemo(
    () => QUEUE_DISPLAY_COLUMNS
      .filter((column) => visibleQueueColumns.includes(column.key))
      .sort((a, b) => visibleQueueColumns.indexOf(a.key) - visibleQueueColumns.indexOf(b.key)),
    [visibleQueueColumns],
  );
  const queueColumnsByKey = useMemo(
    () => new Map(QUEUE_DISPLAY_COLUMNS.map((column) => [column.key, column])),
    [],
  );
  const inactiveQueueColumns = useMemo(
    () => QUEUE_DISPLAY_COLUMNS.filter((column) => !visibleQueueColumns.includes(column.key)),
    [visibleQueueColumns],
  );
  const queueTableMinWidth = compactQueueColumns ? "min-w-[1180px]" : "min-w-[1480px]";
  const hasManualQueueWidths = Object.keys(queueColumnWidths).length > 0;
  useEffect(() => {
    return () => {
      if (registroNoticeTimerRef.current) {
        clearTimeout(registroNoticeTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!startupConcluido || !apiDisponivel) return;

    let ativo = true;
    const carregarNotificacoes = async () => {
      try {
        const data = await fetchRocketChatNotifications();
        if (!ativo) return;
        setRocketChatUnreadCount(data.configured ? data.count : null);
      } catch {
        if (ativo) setRocketChatUnreadCount(null);
      }
    };

    void carregarNotificacoes();
    const intervalId = window.setInterval(() => {
      void carregarNotificacoes();
    }, 45_000);

    return () => {
      ativo = false;
      window.clearInterval(intervalId);
    };
  }, [startupConcluido, apiDisponivel]);
  const queueProcessCounts = useMemo(
    () => buildQueueProcessCounts(filaDistribuida),
    [filaDistribuida],
  );
  const responsavelOptions = useMemo(
    () => Array.from(
      new Set(filaDistribuida.map((row) => firstNameOf(row.responsavel)).filter(Boolean))
    ).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [filaDistribuida],
  );
  const filaFiltrada = useMemo(
    () => responsavelFilter === "todos"
      ? filaDistribuida
      : filaDistribuida.filter((row) => firstNameOf(row.responsavel) === responsavelFilter),
    [filaDistribuida, responsavelFilter],
  );
  const alertaServicoTipoOptions = useMemo(
    () => Array.from(new Set([
      ...ALERTA_SERVICO_BASE_TIPOS,
      ...filaDistribuida.map((row) => normalizeQueueCell(row.tipo)).filter(Boolean),
    ])).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [filaDistribuida],
  );
  const alertaServicoSetorOptions = useMemo(
    () => Array.from(new Set([
      ...alertaServicoSetoresHistorico.map(normalizeQueueCell).filter(Boolean),
      ...filaDistribuida.map((row) => normalizeQueueCell(row.setorOrigem)).filter(Boolean),
    ])).sort((a, b) => a.localeCompare(b, "pt-BR")),
    [alertaServicoSetoresHistorico, filaDistribuida],
  );

  // Conjunto estável de contratos sem IC — muda só quando a fila é recarregada do servidor.
  // Usado como dependência do lookup de IC para evitar re-consulta a cada check/responsável.
  const filaContratosKey = filaProcessos
    ? JSON.stringify(
        Array.from(new Set(
          filaProcessos.rows
            .filter((r) => {
              const contrato = String(r["Contrato"] ?? "").trim();
              const ic = String(r["IC"] ?? "").trim();
              return contrato && !ic;
            })
            .map((r) => String(r["Contrato"] ?? "").trim())
        )).sort()
      )
    : "";

  const abrirHistoricoDaFila = (row: QueueDisplayRow) => {
    const cnpj = row.cpfCnpj.replace(/\D/g, "");
    if (cnpj.length !== 14) return;

    const contratos = Array.from(new Set([
      row.contrato,
      row.ic,
      row.contrato ? queueIcOverrides[row.contrato] ?? "" : "",
    ].map((item) => item.trim()).filter(Boolean)));

    setBuscaProcesso(null);
    setBuscaHistorico({
      cnpj,
      contrato: contratos[0],
      contratos,
    });
    setActiveMainTab("liquidacao");
  };

  const abrirProcessoSolarDaFila = async (row: QueueDisplayRow) => {
    const numeroProcesso = normalizeQueueCell(row.processoSolar || row.numeroProcesso);
    if (!numeroProcesso) return;

    setOpeningSolarProcessKey(row.rowKey);
    setErroFila("");
    setChromeStatus("carregando");
    try {
      const result = await openSolarProcess(numeroProcesso);
      setChromeStatus(result.chromeStatus);
      setApiDisponivel(true);
    } catch (error) {
      setChromeStatus("erro");
      setErroFila(
        error instanceof Error
          ? error.message
          : "Não foi possível abrir o processo no Solar."
      );
    } finally {
      setOpeningSolarProcessKey(null);
    }
  };

  // Conjunto estável de CNPJs — muda só quando a fila é recarregada do servidor,
  // não quando metadados locais (check, responsável) são atualizados.
  const filaCnpjsKey = filaProcessos
    ? JSON.stringify(
        Array.from(new Set(
          filaProcessos.rows
            .map((r) => String(r["CPF/CNPJ"] ?? "").replace(/\D/g, ""))
            .filter((c) => c.length === 14)
        )).sort()
      )
    : "";

  const formatCurrency = (value: number) =>
    new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);

  const resetUploadArea = () => {
    setSelectedFile(null);
    setIsUploading(false);
    setErro("");
    setUploadResetKey((current) => current + 1);
  };

  // Ref para distinguir edição de nome (debounce longo) de ação discreta (debounce curto)
  const queueServerActionRef = useRef<"typing" | "action">("action");

  const updateQueueServer = (serverId: string, patch: Partial<QueueServerConfig>) => {
    queueServerActionRef.current = "nome" in patch ? "typing" : "action";
    queueServersSyncedRef.current = true;
    queueServersDirtyRef.current = true;
    queueServersVersionRef.current += 1;
    setQueueServers((current) =>
      current.map((server) =>
        server.id === serverId ? { ...server, ...patch } : server
      )
    );
  };

  const loadRemoteQueueServers = async () => {
    const data = await fetchQueueServersConfig();
    if (queueServersDirtyRef.current) {
      queueServersSyncedRef.current = true;
      return;
    }
    if (data.servidores.length > 0) {
      skipNextQueueServersSaveRef.current = true;
      setQueueServers(data.servidores);
    }
    queueServersSyncedRef.current = true;
  };

  const loadRemoteAlertaServicoConfig = async () => {
    const data = await fetchAlertaServicoConfig();
    const nextConfig = normalizeAlertaServicoConfig(data);
    setAlertaServicoConfig(nextConfig);
    setNfServicoAlertaDiasUteis(nextConfig.diasUteisPadrao);
  };

  const loadAlertaServicoSetoresHistorico = async () => {
    const data = await fetchFilaSetoresHistorico();
    setAlertaServicoSetoresHistorico((data.setores ?? []).map(normalizeQueueCell).filter(Boolean));
  };

  const loadRemoteRegrasDatasDeducoes = async () => {
    setCarregandoRegrasDatasDeducoes(true);
    setErroRegrasDatasDeducoes("");
    try {
      const data = await fetchRegrasDatasDeducoes();
      setRegrasDatasDeducoes({
        ...DEFAULT_REGRAS_DATAS_DEDUCOES,
        ...data,
        regras: (data.regras ?? []).map((rule) => ({ ...rule, ajusteDiaNaoUtil: rule.ajusteDiaNaoUtil || "antecipar" })),
      });
    } catch (error) {
      setErroRegrasDatasDeducoes(error instanceof Error ? error.message : "Não foi possível carregar regras de deduções.");
    } finally {
      setCarregandoRegrasDatasDeducoes(false);
    }
  };

  const loadFilaProcessosOnce = (refresh = false) => {
    if (refresh) return fetchFilaProcessos(true);
    if (!filaLoadPromiseRef.current) {
      filaLoadPromiseRef.current = fetchFilaProcessos(false).finally(() => {
        filaLoadPromiseRef.current = null;
      });
    }
    return filaLoadPromiseRef.current;
  };

  const setQueueLocalPatch = (
    rowKey: string,
    patch: Record<string, string | number | null>,
    ttlMs = 15_000,
  ) => {
    queueLocalPatchesRef.current.set(rowKey, {
      patch,
      expiresAt: Date.now() + ttlMs,
    });
  };

  const clearQueueLocalPatch = (rowKey: string) => {
    queueLocalPatchesRef.current.delete(rowKey);
  };

  const applyQueueLocalPatches = (data: FilaProcessosInfo): FilaProcessosInfo => {
    if (queueLocalPatchesRef.current.size === 0) return data;
    const now = Date.now();
    for (const [rowKey, entry] of queueLocalPatchesRef.current.entries()) {
      if (entry.expiresAt <= now) {
        queueLocalPatchesRef.current.delete(rowKey);
      }
    }
    if (queueLocalPatchesRef.current.size === 0) return data;
    return {
      ...data,
      rows: data.rows.map((row) => {
        const patch = queueLocalPatchesRef.current.get(getQueueRawRowKey(row))?.patch;
        return patch ? { ...row, ...patch } : row;
      }),
    };
  };

  const applyFilaProcessos = (data: FilaProcessosInfo, options: { force?: boolean } = {}) => {
    const nextData = applyQueueLocalPatches(data);
    setFilaProcessos((current) => {
      if (options.force || isFilaSnapshotFresh(nextData, current)) {
        return nextData;
      }
      return current;
    });
  };

  const prepararAmbienteInicial = async () => {
    let ultimoStartup: BackendStartupProgress = {
      phase: "starting-api",
      title: "Abrindo o AutoLiquid",
      detail: LOADING_PULSES[0],
      progress: 14,
      attempt: 0,
      elapsedMs: 0,
    };

    setStartupError("");
    setErroInicializacao("");
    setApiDisponivel(false);
    setChromeStatus("carregando");
    setStartupState(ultimoStartup);

    const backendStatus = await waitForBackendReady({
      timeoutMs: 60000,
      retryDelayMs: 1000,
      onProgress: (progress) => {
        ultimoStartup = {
          ...progress,
          title: progress.attempt <= 1 ? "Ligando motores" : "Conectando serviços",
          detail: LOADING_PULSES[Math.min(progress.attempt, LOADING_PULSES.length - 1)],
          progress: Math.min(46, Math.max(18, progress.progress)),
        };
        setStartupState(ultimoStartup);
      },
    });

    setChromeStatus(backendStatus.chromeStatus);
    setApiDisponivel(true);
    setErroInicializacao("");

    setStartupState({
      phase: "restoring-data",
      title: "Sincronizando contexto",
      detail: LOADING_PULSES[4],
      progress: 52,
      attempt: ultimoStartup.attempt,
      elapsedMs: ultimoStartup.elapsedMs,
    });

    const [datesGlobaisResult, settingsResult] = await Promise.allSettled([
      fetchDatasGlobais(),
      fetchAppSettings(),
    ]);

    if (datesGlobaisResult.status === "fulfilled") {
      const datesGlobais = normalizeDatesForDisplay(datesGlobaisResult.value);
      if (datesGlobais.vencimento || datesGlobais.apuracao) {
        setDates(datesGlobais);
        lastSavedDatesRef.current = JSON.stringify(datesGlobais);
      } else {
        try {
          const localDates = normalizeDatesForDisplay(await fetchProcessDates());
          setDates(localDates);
          lastSavedDatesRef.current = JSON.stringify(localDates);
        } catch {
          // fallback silencioso para manter a entrada fluida
        }
      }
    } else {
      console.warn("Datas globais indisponíveis; usando config local:", datesGlobaisResult.reason);
      try {
        const localDates = normalizeDatesForDisplay(await fetchProcessDates());
        setDates(localDates);
        lastSavedDatesRef.current = JSON.stringify(localDates);
      } catch {
        // fallback silencioso para manter a entrada fluida
      }
    }

    if (settingsResult.status === "fulfilled") {
      setBrowserName(settingsResult.value.navegador === "edge" ? "Edge" : "Chrome");
      setNomeUsuario((current) => current || settingsResult.value.nomeUsuario || "");
      setNfServicoAlertaDiasUteis(settingsResult.value.nfServicoAlertaDiasUteis ?? 3);
      setAlertaServicoConfig((current) => ({
        ...current,
        diasUteisPadrao: current.diasUteisPadrao || settingsResult.value.nfServicoAlertaDiasUteis || 3,
      }));
      setFecharAbaFila(Boolean(settingsResult.value.fecharAbaFila));
    }

    setStartupState((current) => ({
      ...current,
      title: "Ajustando preferências",
      detail: LOADING_PULSES[5],
      progress: Math.max(current.progress, 60),
    }));
    await delay(450);
  };

  const carregarFilaInicial = async () => {
    const mensagens = [
      LOADING_PULSES[6],
      "Trazendo a fila de pagamentos para perto...",
      "Aplicando sorteio, responsáveis e marcações locais...",
      LOADING_PULSES[7],
      LOADING_PULSES[8],
      LOADING_PULSES[9],
    ];
    let index = 0;
    const startedAt = Date.now();
    setStartupState({
      phase: "restoring-data",
      title: "Preparando sua área",
      detail: mensagens[index],
      progress: 64,
      attempt: 1,
      elapsedMs: 0,
    });
    const intervalId = window.setInterval(() => {
      index = Math.min(index + 1, mensagens.length - 1);
      setStartupState((current) => ({
        ...current,
        detail: mensagens[index],
        progress: Math.min(92, current.progress + 3),
      }));
    }, 900);
    try {
      const data = await loadFilaProcessosOnce(false);
      applyFilaProcessos(data, { force: true });
      const elapsed = Date.now() - startedAt;
      await delay(Math.max(0, 2800 - elapsed));
      setStartupState((current) => ({
        ...current,
        detail: "Painel pronto. Abrindo a fila de trabalho...",
        progress: Math.max(current.progress, 96),
      }));
      await delay(650);
    } finally {
      window.clearInterval(intervalId);
    }
  };

  const concluirEntrada = async (session: AuthSession, ambientePreparado = false) => {
    setAuthLoading(true);
    setAuthError("");
    try {
      if (!ambientePreparado) {
        await prepararAmbienteInicial();
      }
      await auth.setSession(session);
      const sessionName = session.nome || session.username;
      setNomeUsuario(sessionName);
      try {
        const settings = await fetchAppSettings();
        if (settings.nomeUsuario !== sessionName) {
          await saveAppSettings({ ...settings, nomeUsuario: sessionName });
        }
      } catch {
        // A identificação visual já vem da sessão; a persistência local é apenas compatibilidade.
      }
      await carregarFilaInicial();
      setStartupState({
        phase: "ready",
        title: "Tudo pronto",
        detail: "Abrindo a fila de trabalho...",
        progress: 100,
        attempt: 1,
        elapsedMs: 0,
      });
      setActiveMainTab("painel");
      setStartupConcluido(true);
    } catch (error) {
      const mensagem = error instanceof Error ? error.message : "Não foi possível concluir a entrada.";
      setAuthError(mensagem);
      setStartupError(mensagem);
      setStartupState((current) => ({
        ...current,
        phase: "error",
        title: "Entrada interrompida",
        detail: "Não conseguimos concluir a preparação agora.",
        progress: 100,
      }));
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLoginSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthLoading(true);
    setAuthError("");
    try {
      await prepararAmbienteInicial();
      const session = await loginAutoLiquid(loginUsername.trim(), loginPassword);
      await concluirEntrada(session, true);
    } catch (error) {
      let mensagem = error instanceof Error ? error.message : "Usuário ou senha inválidos.";
      if (!mensagem.includes("Usuário ou senha inválidos")) {
        try {
          const diagnostico = await fetchAuthDiagnostico();
          const detalhe = formatAuthDiagnostico(diagnostico);
          if (detalhe) {
            mensagem = `${mensagem} ${detalhe}`;
          }
        } catch {
          // Se o diagnóstico também falhar, mantemos o erro original do login.
        }
      }
      setAuthError(mensagem);
      setStartupError(mensagem);
      setStartupState((current) => ({
        ...current,
        phase: "error",
        title: "Entrada interrompida",
        detail: "Confira os dados e tente novamente.",
        progress: 100,
      }));
    } finally {
      setAuthLoading(false);
    }
  };

  const updateResponsavelDraft = (rowKey: string, value: string) => {
    setQueueResponsavelDrafts((current) => ({
      ...current,
      [rowKey]: value,
    }));
  };

  const updateAlertDraft = (rowKey: string, value: string) => {
    setQueueAlertDrafts((current) => ({
      ...current,
      [rowKey]: value,
    }));
  };

  const updateRowMeta = (rowKey: string, patch: Record<string, string | number | null>) => {
    setFilaProcessos((current) => {
      if (!current) return current;
      return {
        ...current,
        rows: current.rows.map((item) => {
          const currentKey = getQueueRawRowKey(item);
          return currentKey === rowKey ? { ...item, ...patch } : item;
        }),
      };
    });
  };

  const isApiUnavailableError = (error: unknown) => {
    const message = error instanceof Error ? error.message : "";
    return (
      message.includes("Não foi possível conectar à API") ||
      message.includes("A API não respondeu a tempo") ||
      message.includes("A API não ficou disponível")
    );
  };

  const toggleQueueConclusao = async (row: QueueDisplayRow) => {
    const nextConcluido = !row.concluido;

    // Capture rollback state from the current row (before any optimistic update)
    const rollbackMeta = {
      __concluido: row.concluido ? "1" : "",
      __concluido_por: row.concluidoPor,
      __concluido_em: row.concluidoEm,
    };
    const rollbackOverride = queueConclusaoOverrides[row.rowKey];

    // Apply optimistic update immediately — no delay, no grey flash
    const applyOptimistic = (concluido: boolean) => {
      setQueueConclusaoOverrides((current) => ({
        ...current,
        [row.rowKey]: {
          concluido,
          concluidoPor: concluido ? (nomeUsuario || "Você") : "",
          concluidoEm: concluido ? new Date().toISOString() : "",
        },
      }));
      updateRowMeta(row.rowKey, {
        __concluido: concluido ? "1" : "",
        __concluido_por: concluido ? (nomeUsuario || "Você") : "",
        __concluido_em: concluido ? new Date().toISOString() : "",
      });
      setQueueLocalPatch(row.rowKey, {
        __concluido: concluido ? "1" : "",
        __concluido_por: concluido ? (nomeUsuario || "Você") : "",
        __concluido_em: concluido ? new Date().toISOString() : "",
      });
    };

    applyOptimistic(nextConcluido);

    const pending = conclusaoPendingRef.current;
    const existing = pending.get(row.rowKey);

    // Record latest intent; if a save is already in flight it will pick this up
    pending.set(row.rowKey, { latest: nextConcluido, saving: existing?.saving ?? false });
    if (existing?.saving) return;

    // Start save loop — handles rapid clicks by always sending the last intent
    pending.set(row.rowKey, { latest: nextConcluido, saving: true });
    let intent = nextConcluido;

    while (true) {
      try {
        let result: Awaited<ReturnType<typeof saveFilaConclusao>> | null = null;
        let lastError: unknown = null;
        for (let attempt = 0; attempt < 4; attempt += 1) {
          try {
            result = await saveFilaConclusao({
              numeroProcesso: row.numeroProcesso,
              solPagamento: row.solPagamento,
              concluido: intent,
            });
            setApiDisponivel(true);
            break;
          } catch (error) {
            lastError = error;
            if (!isApiUnavailableError(error) || attempt === 3) {
              throw error;
            }
            // Só avisa o usuário na 2ª falha — uma oscilação passageira
            // não precisa de mensagem; só falhas repetidas justificam o alerta.
            if (attempt >= 1) {
              setErroFila("A API local oscilou. Mantive sua marcação na tela e estou tentando salvar de novo.");
            }
            await delay(700 * (attempt + 1));
          }
        }
        if (!result) {
          throw lastError instanceof Error ? lastError : new Error("Não foi possível marcar o processo como concluído.");
        }
        // Sync with server-confirmed values
        updateRowMeta(row.rowKey, {
          __concluido: result.concluido ? "1" : "",
          __concluido_por: result.concluidoPor || "",
          __concluido_em: result.concluidoEm || "",
        });
        setQueueLocalPatch(row.rowKey, {
          __concluido: result.concluido ? "1" : "",
          __concluido_por: result.concluidoPor || "",
          __concluido_em: result.concluidoEm || "",
        }, 20_000);
        setQueueConclusaoOverrides((current) => ({
          ...current,
          [row.rowKey]: {
            concluido: result.concluido,
            concluidoPor: result.concluidoPor || "",
            concluidoEm: result.concluidoEm || "",
          },
        }));
      } catch (error) {
        if (isApiUnavailableError(error)) {
          setApiDisponivel(false);
          setQueueLocalPatch(row.rowKey, {
            __concluido: intent ? "1" : "",
            __concluido_por: intent ? (nomeUsuario || "Você") : "",
            __concluido_em: intent ? new Date().toISOString() : "",
          }, 60_000);
          setErroFila(
            "A API local caiu antes de confirmar. A marcação ficou na tela, mas ainda não foi salva no Turso; reinicie o app para a API subir e marque novamente se precisar."
          );
          pending.delete(row.rowKey);
          return;
        }

        // Roll back to the state before the first click in this chain
        clearQueueLocalPatch(row.rowKey);
        updateRowMeta(row.rowKey, rollbackMeta);
        setQueueConclusaoOverrides((current) => {
          const next = { ...current };
          if (rollbackOverride) {
            next[row.rowKey] = rollbackOverride;
          } else {
            delete next[row.rowKey];
          }
          return next;
        });
        setErroFila(error instanceof Error ? error.message : "Não foi possível marcar o processo como concluído.");
        pending.delete(row.rowKey);
        return;
      }

      // Check if a new intent arrived while we were saving
      const current = pending.get(row.rowKey);
      if (!current || current.latest === intent) {
        pending.delete(row.rowKey);
        return;
      }
      // New intent — loop again with the updated value and apply optimistic immediately
      intent = current.latest;
      pending.set(row.rowKey, { latest: intent, saving: true });
      applyOptimistic(intent);
    }
  };

  const persistQueueAlert = async (row: QueueDisplayRow) => {
    const mensagem = normalizeQueueCell(queueAlertDrafts[row.rowKey]);
    if (!mensagem) return;

    const optimisticAlert: FilaAlerta = {
      id: -Date.now(),
      mensagem,
      autor: nomeUsuario || "Você",
      criadoEm: new Date().toISOString(),
    };

    setQueueAlertDrafts((current) => ({
      ...current,
      [row.rowKey]: "",
    }));
    setQueueLocalPatch(row.rowKey, {
      __alertas_json: JSON.stringify([optimisticAlert, ...row.alertas]),
    });
    setFilaProcessos((current) => {
      if (!current) return current;
      return {
        ...current,
        rows: current.rows.map((item) => {
          const currentKey = getQueueRawRowKey(item);
          if (currentKey !== row.rowKey) return item;
          const alertas = parseFilaAlertas(item["__alertas_json"]);
          setQueueLocalPatch(row.rowKey, {
            __alertas_json: JSON.stringify([optimisticAlert, ...alertas]),
          });
          return {
            ...item,
            __alertas_json: JSON.stringify([optimisticAlert, ...alertas]),
          };
        }),
      };
    });

    setSavingAlertKey(row.rowKey);
    try {
      const result = await saveFilaAlerta({
        numeroProcesso: row.numeroProcesso,
        solPagamento: row.solPagamento,
        mensagem,
      });
      if (removedOptimisticAlertIdsRef.current.has(optimisticAlert.id)) {
        removedOptimisticAlertIdsRef.current.delete(optimisticAlert.id);
        if (result.alerta?.id) {
          void deleteFilaAlerta(result.alerta.id, {
            numeroProcesso: row.numeroProcesso,
            solPagamento: row.solPagamento,
            mensagem,
          }).catch(() => {});
        }
        return;
      }
      setFilaProcessos((current) => {
        if (!current || !result.alerta) return current;
        return {
          ...current,
          rows: current.rows.map((item) => {
            const currentKey = getQueueRawRowKey(item);
            if (currentKey !== row.rowKey) return item;
            const alertas = parseFilaAlertas(item["__alertas_json"]);
            const withoutOptimistic = alertas.filter((alerta) => alerta.id !== optimisticAlert.id);
            setQueueLocalPatch(row.rowKey, {
              __alertas_json: JSON.stringify([result.alerta, ...withoutOptimistic]),
            }, 20_000);
            return {
              ...item,
              __alertas_json: JSON.stringify([result.alerta, ...withoutOptimistic]),
            };
          }),
        };
      });
    } catch (error) {
      setFilaProcessos((current) => {
        if (!current) return current;
        return {
          ...current,
          rows: current.rows.map((item) => {
            const currentKey = getQueueRawRowKey(item);
            if (currentKey !== row.rowKey) return item;
            const alertas = parseFilaAlertas(item["__alertas_json"]).filter(
              (alerta) => alerta.id !== optimisticAlert.id
            );
            clearQueueLocalPatch(row.rowKey);
            return {
              ...item,
              __alertas_json: JSON.stringify(alertas),
            };
          }),
        };
      });
      setQueueAlertDrafts((current) => ({
        ...current,
        [row.rowKey]: mensagem,
      }));
      setErroFila(error instanceof Error ? error.message : "Não foi possível salvar a mensagem.");
    } finally {
      setSavingAlertKey(null);
    }
  };

  const removeQueueAlert = async (row: QueueDisplayRow, alerta: FilaAlerta) => {
    const previousAlertas = row.alertas;
    const nextAlertas = previousAlertas.filter((item) => item.id !== alerta.id);
    setDeletingAlertId(alerta.id);
    setQueueLocalPatch(row.rowKey, {
      __alertas_json: JSON.stringify(nextAlertas),
    });
    updateRowMeta(row.rowKey, {
      __alertas_json: JSON.stringify(nextAlertas),
    });
    if (alerta.id <= 0) {
      removedOptimisticAlertIdsRef.current.add(alerta.id);
      setDeletingAlertId(null);
      return;
    }
    try {
      await deleteFilaAlerta(alerta.id, {
        numeroProcesso: row.numeroProcesso,
        solPagamento: row.solPagamento,
        mensagem: alerta.mensagem,
      });
      setQueueLocalPatch(row.rowKey, {
        __alertas_json: JSON.stringify(nextAlertas),
      }, 20_000);
    } catch (error) {
      setQueueLocalPatch(row.rowKey, {
        __alertas_json: JSON.stringify(previousAlertas),
      }, 5_000);
      updateRowMeta(row.rowKey, {
        __alertas_json: JSON.stringify(previousAlertas),
      });
      setErroFila(error instanceof Error ? error.message : "Não foi possível remover a mensagem.");
    } finally {
      setDeletingAlertId(null);
    }
  };

  const persistResponsavel = async (row: QueueDisplayRow) => {
    const nextResponsavel = (queueResponsavelDrafts[row.rowKey] ?? row.responsavel).trim();
    if (nextResponsavel === row.responsavel && !queueResponsavelDrafts[row.rowKey]) return;

    const previous = {
      __responsavel_manual: row.responsavel,
      __responsavel_alterado: row.responsavelAlterado ? "1" : "",
      __responsavel_alterado_por: row.responsavelAlteradoPor,
      __responsavel_alterado_em: row.responsavelAlteradoEm,
    };
    updateRowMeta(row.rowKey, {
      __responsavel_manual: nextResponsavel,
      __responsavel_alterado: nextResponsavel ? "1" : "",
      __responsavel_alterado_por: nextResponsavel ? (nomeUsuario || "Você") : "",
      __responsavel_alterado_em: nextResponsavel ? new Date().toISOString() : "",
    });
    setSavingResponsavelKey(row.rowKey);
    try {
      const result = await saveFilaResponsavel({
        numeroProcesso: row.numeroProcesso,
        solPagamento: row.solPagamento,
        responsavel: nextResponsavel,
      });
      setFilaProcessos((current) => {
        if (!current) return current;
        return {
          ...current,
          rows: current.rows.map((item) => {
            const currentKey = `${normalizeQueueCell(item["Número Processo"])}::${normalizeQueueCell(item["Sol. Pagamento"])}`;
            if (currentKey !== row.rowKey) return item;
            return {
              ...item,
              __responsavel_manual: nextResponsavel,
              __responsavel_alterado: nextResponsavel ? "1" : "",
              __responsavel_alterado_por: nextResponsavel ? result.alteradoPor : "",
              __responsavel_alterado_em: nextResponsavel ? result.alteradoEm ?? "" : "",
            };
          }),
        };
      });
    } catch (error) {
      updateRowMeta(row.rowKey, previous);
      setErroFila(
        error instanceof Error ? error.message : "Não foi possível salvar o responsável."
      );
    } finally {
      setSavingResponsavelKey(null);
    }
  };

  const persistNfServicoAlertSetting = async () => {
    const nextConfig = normalizeAlertaServicoConfig({
      ...alertaServicoConfig,
      diasUteisPadrao: nfServicoAlertaDiasUteis,
    });
    setAlertaServicoConfig(nextConfig);
    setSavingAlertaServicoConfig(true);
    try {
      const result = await saveAlertaServicoConfig(nextConfig);
      const saved = normalizeAlertaServicoConfig(result.config);
      setAlertaServicoConfig(saved);
      setNfServicoAlertaDiasUteis(saved.diasUteisPadrao);
    } catch (error) {
      setErroFila(error instanceof Error ? error.message : "Não foi possível salvar o alerta de NF Serviço.");
    } finally {
      setSavingAlertaServicoConfig(false);
    }
  };

  const persistAlertaServicoConfig = async (nextConfig: AlertaServicoConfig) => {
    const normalized = normalizeAlertaServicoConfig({
      ...nextConfig,
    });
    setAlertaServicoConfig(normalized);
    setNfServicoAlertaDiasUteis(normalized.diasUteisPadrao);
    setSavingAlertaServicoConfig(true);
    try {
      const result = await saveAlertaServicoConfig(normalized);
      const saved = normalizeAlertaServicoConfig(result.config);
      setAlertaServicoConfig(saved);
      setNfServicoAlertaDiasUteis(saved.diasUteisPadrao);
    } catch (error) {
      setErroFila(error instanceof Error ? error.message : "Não foi possível salvar as regras do alerta de serviço.");
    } finally {
    setSavingAlertaServicoConfig(false);
    }
  };

  const openNewAlertaServicoRule = () => {
    setEditingAlertaServicoRuleId(null);
    setAlertaServicoRuleDraft({
      ...DEFAULT_ALERTA_SERVICO_RULE,
      id: `regra-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      valorAcao: "",
    });
    setAlertaServicoDialogOpen(true);
  };

  const openEditAlertaServicoRule = (rule: AlertaServicoRule) => {
    setEditingAlertaServicoRuleId(rule.id);
    setAlertaServicoRuleDraft({ ...DEFAULT_ALERTA_SERVICO_RULE, ...rule });
    setAlertaServicoDialogOpen(true);
  };

  const saveAlertaServicoRuleDraft = () => {
    const draft: AlertaServicoRule = {
      ...alertaServicoRuleDraft,
      tipoDocumento: alertaServicoRuleDraft.tipoDocumento || ALERTA_SERVICO_TIPO_TODOS,
      cnpj: normalizeCnpj(alertaServicoRuleDraft.cnpj),
      setor: normalizeQueueCell(alertaServicoRuleDraft.setor),
      valorAcao:
        alertaServicoRuleDraft.acaoVencimento === "IGNORAR"
          ? ""
          : normalizeQueueCell(alertaServicoRuleDraft.valorAcao),
    };
    if (draft.cnpj && draft.cnpj.length !== 14) {
      setErroFila("Informe um CNPJ com 14 dígitos ou deixe vazio para todos.");
      return;
    }
    if (draft.acaoVencimento === "DIA_FIXO_MES_SEGUINTE") {
      const dia = Number(draft.valorAcao);
      if (!Number.isInteger(dia) || dia < 1 || dia > 31) {
        setErroFila("Informe um dia do mês entre 1 e 31.");
        return;
      }
    }
    if (draft.acaoVencimento === "DATA_PERSONALIZADA" && !draft.valorAcao) {
      setErroFila("Informe a data personalizada da exceção.");
      return;
    }

    const currentRules = normalizeAlertaServicoConfig(alertaServicoConfig).regras;
    const nextRules = editingAlertaServicoRuleId
      ? currentRules.some((rule) => rule.id === editingAlertaServicoRuleId)
        ? currentRules.map((rule) => rule.id === editingAlertaServicoRuleId ? draft : rule)
        : [draft, ...currentRules]
      : [...currentRules, draft];
    setAlertaServicoDialogOpen(false);
    setEditingAlertaServicoRuleId(null);
    void persistAlertaServicoConfig({
      ...alertaServicoConfig,
      regras: nextRules,
    });
  };

  const toggleAlertaServicoRule = (ruleId: string, active: boolean) => {
    void persistAlertaServicoConfig({
      ...alertaServicoConfig,
      regras: alertaServicoConfig.regras.map((rule) => rule.id === ruleId ? { ...rule, active } : rule),
    });
  };

  const removeAlertaServicoRule = (ruleId: string) => {
    void persistAlertaServicoConfig({
      ...alertaServicoConfig,
      regras: alertaServicoConfig.regras.filter((rule) => rule.id !== ruleId),
    });
  };

  const patchRegraDataDeducao = (ruleId: string, patch: Partial<RegraDataDeducao>) => {
    if (!auth.isModerator) return;
    setErroRegrasDatasDeducoes("");
    setRegrasDatasDeducoes((current) => ({
      ...current,
      regras: current.regras.map((rule) => rule.id === ruleId ? { ...rule, ...patch } : rule),
    }));
  };

  const addCodigoRegraDataDeducao = (ruleId: string) => {
    if (!auth.isModerator) return;
    const codigo = normalizeCodigoDeducao(codigoDeducaoDrafts[ruleId] ?? "");
    if (!codigo) return;
    setErroRegrasDatasDeducoes("");
    setRegrasDatasDeducoes((current) => ({
      ...current,
      regras: current.regras.map((rule) => {
        if (rule.id !== ruleId || rule.codigos.includes(codigo)) return rule;
        return { ...rule, codigos: [...rule.codigos, codigo] };
      }),
    }));
    setCodigoDeducaoDrafts((current) => ({ ...current, [ruleId]: "" }));
  };

  const removeCodigoRegraDataDeducao = (ruleId: string, codigo: string) => {
    if (!auth.isModerator) return;
    setErroRegrasDatasDeducoes("");
    setRegrasDatasDeducoes((current) => ({
      ...current,
      regras: current.regras.map((rule) =>
        rule.id === ruleId ? { ...rule, codigos: rule.codigos.filter((item) => item !== codigo) } : rule
      ),
    }));
  };

  const toggleRegraDataDeducaoExpanded = (ruleId: string) => {
    setExpandedDeducaoRuleIds((current) => ({ ...current, [ruleId]: !current[ruleId] }));
  };

  const addRegraDataDeducao = () => {
    if (!auth.isModerator) return;
    const ruleId = `deducao-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setErroRegrasDatasDeducoes("");
    setRegrasDatasDeducoes((current) => ({
      ...current,
      regras: [
        ...current.regras,
        {
          id: ruleId,
          nome: "Nova dedução",
          codigos: [],
          siafi: "DDF055",
          diaVencimento: null,
          mesVencimento: "usuario",
          apuracao: "usuario",
          pagamento: "igual_vencimento",
          ajusteDiaNaoUtil: "antecipar",
          precisaLf: false,
          observacao: "",
        },
      ],
    }));
    setCodigoDeducaoDrafts((current) => ({ ...current, [ruleId]: "" }));
    setExpandedDeducaoRuleIds((current) => ({ ...current, [ruleId]: true }));
  };

  const removeRegraDataDeducao = (ruleId: string) => {
    if (!auth.isModerator) return;
    setErroRegrasDatasDeducoes("");
    setRegrasDatasDeducoes((current) => ({
      ...current,
      regras: current.regras.filter((rule) => rule.id !== ruleId),
    }));
    setCodigoDeducaoDrafts((current) => {
      const next = { ...current };
      delete next[ruleId];
      return next;
    });
    setExpandedDeducaoRuleIds((current) => {
      const next = { ...current };
      delete next[ruleId];
      return next;
    });
  };

  const openDeducoesRulesDialog = () => {
    setDeducoesRulesDialogOpen(true);
    if (!regrasDatasDeducoes.regras.length) {
      void loadRemoteRegrasDatasDeducoes();
    }
  };

  const persistRegrasDatasDeducoes = async () => {
    if (!auth.isModerator) return;
    const regraInvalida = regrasDatasDeducoes.regras.find((rule) =>
      !/^[A-Z]{3}\d{3}$/.test(rule.siafi)
      || !rule.codigos.length
      || !normalizeQueueCell(rule.nome)
      || (rule.mesVencimento !== "usuario" && !rule.diaVencimento)
    );
    if (regraInvalida) {
      setErroRegrasDatasDeducoes(`Revise ${regraInvalida.nome || regraInvalida.id}: informe nome, SIAFI no formato DDF055, códigos e dia quando a data for calculada.`);
      return;
    }
    setSavingRegrasDatasDeducoes(true);
    setErroRegrasDatasDeducoes("");
    try {
      const result = await saveRegrasDatasDeducoes(regrasDatasDeducoes);
      setRegrasDatasDeducoes({
        ...DEFAULT_REGRAS_DATAS_DEDUCOES,
        ...result.config,
        regras: (result.config.regras ?? []).map((rule) => ({ ...rule, ajusteDiaNaoUtil: rule.ajusteDiaNaoUtil || "antecipar" })),
      });
    } catch (error) {
      setErroRegrasDatasDeducoes(error instanceof Error ? error.message : "Não foi possível salvar as regras de deduções.");
    } finally {
      setSavingRegrasDatasDeducoes(false);
    }
  };

  const persistFecharAbaFilaSetting = async (value: boolean) => {
    setFecharAbaFila(value);
    try {
      const current = await fetchAppSettings();
      await saveAppSettings({
        ...current,
        fecharAbaFila: value,
      });
    } catch (error) {
      setFecharAbaFila((current) => !current);
      setErroFila(error instanceof Error ? error.message : "Não foi possível salvar a preferência de fechar aba.");
    }
  };

  const beginResizeQueueColumn = (
    columnKey: keyof QueueDisplayRow,
    event: React.MouseEvent<HTMLSpanElement>
  ) => {
    event.preventDefault();
    const startX = event.clientX;
    const th = event.currentTarget.closest("th");
    const startWidth = queueColumnWidths[columnKey] ?? th?.getBoundingClientRect().width ?? 120;

    const handleMove = (moveEvent: MouseEvent) => {
      const nextWidth = Math.max(MIN_QUEUE_COLUMN_WIDTH, Math.min(520, Math.round(startWidth + moveEvent.clientX - startX)));
      setQueueColumnWidths((current) => ({
        ...current,
        [columnKey]: nextWidth,
      }));
    };

    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  };

  const handleQueueColumnDragStart = (
    event: React.DragEvent<HTMLDivElement>,
    columnKey: keyof QueueDisplayRow
  ) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(columnKey));
  };

  const handleQueueColumnDrop = (
    event: React.DragEvent<HTMLDivElement>,
    targetKey: keyof QueueDisplayRow
  ) => {
    event.preventDefault();
    const sourceKey = event.dataTransfer.getData("text/plain") as keyof QueueDisplayRow;
    if (!sourceKey || sourceKey === targetKey) return;
    setVisibleQueueColumns((current) => {
      if (!current.includes(sourceKey) || !current.includes(targetKey)) return current;
      const withoutSource = current.filter((key) => key !== sourceKey);
      const targetIndex = withoutSource.indexOf(targetKey);
      const next = [...withoutSource];
      next.splice(targetIndex, 0, sourceKey);
      return next;
    });
  };

  const resetQueueColumnWidths = () => {
    setQueueColumnWidths({});
  };

  const toggleQueueColumn = (columnKey: keyof QueueDisplayRow) => {
    setVisibleQueueColumns((current) => {
      if (current.includes(columnKey)) {
        return current.length > 1 ? current.filter((key) => key !== columnKey) : current;
      }
      return [...current, columnKey];
    });
  };

  const moveQueueColumn = (columnKey: keyof QueueDisplayRow, direction: -1 | 1) => {
    setVisibleQueueColumns((current) => {
      const index = current.indexOf(columnKey);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  };

  const resetQueueColumnOrder = () => {
    setVisibleQueueColumns(QUEUE_DISPLAY_COLUMNS.map((column) => column.key));
  };

  const activateQueueColumn = (columnKey: keyof QueueDisplayRow) => {
    setVisibleQueueColumns((current) => current.includes(columnKey) ? current : [...current, columnKey]);
  };

  // Verificação de versão na inicialização (só quando API estiver disponível)
  useEffect(() => {
    if (!startupConcluido || !apiDisponivel) {
      return;
    }

    let ativo = true;
    const checarVersao = async () => {
      // Aguarda API ficar disponível antes de consultar
      await new Promise(r => setTimeout(r, 3000));
      if (!ativo) return;
      try {
        const info = await verificarAtualizacao();
        if (ativo && info.tem_atualizacao) setBannerUpdate(info);
      } catch {
        // silencia erros de rede na checagem automática
      }
    };
    checarVersao();
    return () => { ativo = false; };
  }, [startupConcluido, apiDisponivel]);

  useEffect(() => {
    if (!startupConcluido || !apiDisponivel) return;
    let ativo = true;
    loadRemoteQueueServers().catch(() => {
      if (ativo) {
        queueServersSyncedRef.current = true;
      }
    });
    loadRemoteAlertaServicoConfig().catch(() => {
      // Mantém a configuração carregada localmente como fallback visual.
    });
    loadAlertaServicoSetoresHistorico().catch(() => {
      // A fila atual continua alimentando o datalist se o histórico remoto falhar.
    });
    loadRemoteRegrasDatasDeducoes().catch(() => {
      // O próprio loader já mostra a falha no controle de deduções.
    });
    return () => {
      ativo = false;
    };
  }, [startupConcluido, apiDisponivel]);

  useEffect(() => {
    if (!startupConcluido || !apiDisponivel || filaProcessos) {
      return;
    }

    let ativo = true;
    loadFilaProcessosOnce(false)
      .then((data) => {
        if (ativo) applyFilaProcessos(data);
      })
      .catch(() => {
        // O painel mostra o erro se o usuário abrir a fila e a nova tentativa falhar.
      });

    return () => {
      ativo = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startupConcluido, apiDisponivel, filaProcessos]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(QUEUE_SERVER_STORAGE_KEY, JSON.stringify(queueServers));

    if (!apiDisponivel || !queueServersSyncedRef.current) return;
    if (skipNextQueueServersSaveRef.current) {
      skipNextQueueServersSaveRef.current = false;
      return;
    }

    // Ações discretas (mudar modo, remover) salvam quase imediatamente.
    // Edição de nome usa debounce maior para evitar spam enquanto o usuário digita.
    const debounce = queueServerActionRef.current === "typing" ? 700 : 80;
    const versionAtSave = queueServersVersionRef.current;

    const timeoutId = window.setTimeout(() => {
      void saveQueueServersConfig(queueServers)
        .then(() => {
          if (queueServersVersionRef.current === versionAtSave) {
            queueServersDirtyRef.current = false;
          }
        })
        .catch((error) => {
          setErroFila(error instanceof Error ? error.message : "Não foi possível sincronizar servidores do sorteio.");
        });
    }, debounce);

    return () => window.clearTimeout(timeoutId);
  }, [queueServers, apiDisponivel]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(QUEUE_VISIBLE_COLUMNS_STORAGE_KEY, JSON.stringify(visibleQueueColumns));
  }, [visibleQueueColumns]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(QUEUE_COMPACT_COLUMNS_STORAGE_KEY, compactQueueColumns ? "1" : "0");
  }, [compactQueueColumns]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(QUEUE_COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(queueColumnWidths));
  }, [queueColumnWidths]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(QUEUE_MOSTRAR_TIPO_BADGES_KEY, mostrarTipoBadges ? "1" : "0");
  }, [mostrarTipoBadges]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(QUEUE_MOSTRAR_SIMPLES_KEY, mostrarSimples ? "1" : "0");
  }, [mostrarSimples]);

  useEffect(() => {
    if (!mostrarSimples || !filaCnpjsKey) {
      setQueueSimplesMap({});
      setIsLoadingSimples(false);
      return;
    }
    const cnpjs: string[] = JSON.parse(filaCnpjsKey);
    if (cnpjs.length === 0) return;
    let ativo = true;
    setIsLoadingSimples(true);
    setQueueSimplesMap({});
    fetchSimplesBatch(cnpjs).then((result) => {
      if (ativo) {
        setQueueSimplesMap(result);
        setIsLoadingSimples(false);
      }
    }).catch(() => {
      if (ativo) setIsLoadingSimples(false);
    });
    return () => { ativo = false; };
  // filaCnpjsKey muda apenas quando os CNPJs da fila mudam — não quando metadados locais são atualizados.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filaCnpjsKey, mostrarSimples]);

  // Lookup de IC para linhas com contrato mas sem IC cadastrado na fila.
  // filaContratosKey muda apenas quando os contratos-sem-IC da fila mudam.
  useEffect(() => {
    if (!filaContratosKey) {
      setQueueIcOverrides({});
      return;
    }
    const sarfs: string[] = JSON.parse(filaContratosKey);
    if (sarfs.length === 0) {
      setQueueIcOverrides({});
      return;
    }
    let ativo = true;
    fetchContratosIcLookup(sarfs).then((resultado) => {
      if (ativo) setQueueIcOverrides(resultado);
    });
    return () => { ativo = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filaContratosKey]);

  useEffect(() => {
    let ativo = true;

    const carregarTela = async () => {
      if (auth.isAuthenticated && auth.session && !authLoading) {
        const sessionName = auth.session.nome || auth.session.username;
        setStoredAuthSession(auth.session);
        setLoginUsername(auth.session.username || "");
        setNomeUsuario(sessionName);
        try {
          const settings = await fetchAppSettings();
          if (settings.nomeUsuario !== sessionName) {
            await saveAppSettings({ ...settings, nomeUsuario: sessionName });
          }
        } catch {
          // Compatibilidade com APIs antigas; a sessão continua sendo a fonte da verdade.
        }
        setApiDisponivel(true);
        setChromeStatus("pronto");
        setAuthGateReady(false);
        setStartupError("");
        setErroInicializacao("");
        setStartupState({
          phase: "ready",
          title: "Tudo pronto",
          detail: "Abrindo a fila de trabalho...",
          progress: 100,
          attempt: 1,
          elapsedMs: 0,
        });
        setStartupConcluido(true);
        return;
      }

      setStartupConcluido(false);
      setStartupError("");
      setErroInicializacao("");
      setStartupState(INITIAL_STARTUP_STATE);
      setAuthGateReady(true);
      try {
        const savedSession = await readStoredAuthSession();
        if (!ativo) return;
        setStoredAuthSession(savedSession);
        setLoginUsername(savedSession?.username || "");
        if (savedSession && temRegistroLiquidacaoPendente()) {
          setAuthGateReady(false);
          setActiveMainTab("liquidacao");
          await auth.setSession(savedSession);
        }
      } catch {
        if (!ativo) return;
        setStoredAuthSession(null);
      }
    };

    carregarTela();

    return () => {
      ativo = false;
    };
  }, [startupRunId, auth.isAuthenticated, auth.session, authLoading]);

  // Datas vêm do Supabase (datas_globais) e são somente leitura para o servidor.
  // Edições do usuário ficam em memória apenas (não são persistidas).
  // O useEffect de auto-save foi intencionalmente removido.

  useEffect(() => {
    if (!authLoading) {
      setLoadingPulseIndex(0);
      return;
    }

    const intervalId = window.setInterval(() => {
      setLoadingPulseIndex((current) => (current + 1) % LOADING_PULSES.length);
    }, 1050);

    return () => window.clearInterval(intervalId);
  }, [authLoading]);

  useEffect(() => {
    if (!startupConcluido) {
      return;
    }

    let ativo = true;

    const atualizarChrome = async () => {
      try {
        const backendStatus = await fetchBackendStatus();
        if (!ativo) return false;
        setChromeStatus(backendStatus.chromeStatus);
        setApiDisponivel(true);
        setErroInicializacao("");
        apiStatusFailuresRef.current = 0;
        return true;
      } catch (error) {
        if (!ativo) return false;
        console.error("Erro ao consultar status do backend:", error);
        apiStatusFailuresRef.current += 1;
        if (apiStatusFailuresRef.current >= 3) {
          setChromeStatus("erro");
          setApiDisponivel(false);
          setErroInicializacao(
            error instanceof Error
              ? error.message
              : "Não foi possível consultar o status do Chrome."
          );
        }
        return false;
      }
    };

    const handleFocus = () => {
      window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
      void atualizarChrome();
    };

    const handleVisibility = () => {
      if (!document.hidden) {
        void atualizarChrome();
      }
    };

    const handlePageShow = () => {
      window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
      void atualizarChrome();
    };

    const intervalId = window.setInterval(() => {
      void atualizarChrome();
    }, 5000);

    window.addEventListener("focus", handleFocus);
    window.addEventListener("pageshow", handlePageShow);
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      ativo = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("pageshow", handlePageShow);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [startupConcluido]);

  useEffect(() => {
    if (!startupConcluido || !apiDisponivel) {
      return;
    }

    let ativo = true;
    const carregarDashboard = async () => {
      setCarregandoDashboard(true);
      try {
        const data = await fetchDashboard(dashboardPeriodo, nomeUsuario || undefined, dashboardProcessLimit);
        if (!ativo) return;
        setDashboard(data);
      } catch (error) {
        if (!ativo) return;
        console.error("Erro ao carregar dashboard:", error);
      } finally {
        if (ativo) {
          setCarregandoDashboard(false);
        }
      }
    };

    void carregarDashboard();
    return () => {
      ativo = false;
    };
  }, [apiDisponivel, dashboardPeriodo, dashboardProcessLimit, nomeUsuario, startupConcluido, dashboardRefreshSeq]);

  useEffect(() => {
    if (!startupConcluido || typeof window === "undefined") return;
    let ativo = true;

    const aplicarRegistroPendente = async (registro: RegistroLiquidacaoPendente) => {
      const ignorarDocumentoNestaSessao = window.sessionStorage.getItem(IGNORAR_RETORNO_PENDENCIA_SESSION_KEY);
      if (registro.documentoId && ignorarDocumentoNestaSessao === registro.documentoId) {
        return;
      }
      try {
        const dispensados = JSON.parse(window.localStorage.getItem(RETORNO_PENDENCIA_DISPENSADO_KEY) || "[]");
        if (registro.documentoId && Array.isArray(dispensados) && dispensados.map(String).includes(registro.documentoId)) {
          window.localStorage.removeItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
          return;
        }
      } catch {
        window.localStorage.removeItem(RETORNO_PENDENCIA_DISPENSADO_KEY);
      }

      if (registro.documentoId) {
        try {
          const documento = await fetchDocumentoProcessado(registro.documentoId);
          if (!ativo) return;
          const temPendenciasAbertas = (documento.pendencias ?? []).some((pendencia) => !pendencia.resolvida);
          if (temPendenciasAbertas) {
            router.push(`/conferencia?id=${encodeURIComponent(registro.documentoId)}`);
            return;
          }
        } catch (error) {
          console.warn("Não foi possível conferir pendências do documento salvo.", error);
        }
      }
      if (!ativo) return;
      setRegistroPendente(registro);
      setActiveMainTab("liquidacao");
      setRegistroError("");
      setRegistroDificuldadeInteragida(false);
    };

    const raw = window.localStorage.getItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as RegistroLiquidacaoPendente;
        if (parsed?.documentoId || parsed?.numeroProcesso) {
          void aplicarRegistroPendente(parsed);
          return () => {
            ativo = false;
          };
        }
      } catch {
        window.localStorage.removeItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
      }
    }

    if (!apiDisponivel || !auth.session) {
      return () => {
        ativo = false;
      };
    }

    const carregarPendenteRemoto = async () => {
      try {
        const pendente = await fetchRegistroLiquidacaoPendente({
          servidorNome: auth.session?.nome || "",
          servidorUsername: auth.session?.username || "",
        });
        if (!ativo || !(pendente?.documentoId || pendente?.numeroProcesso)) return;
        window.localStorage.setItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY, JSON.stringify(pendente));
        await aplicarRegistroPendente(pendente);
      } catch (error) {
        console.warn("Não foi possível consultar liquidação pendente remota.", error);
      }
    };

    void carregarPendenteRemoto();
    return () => {
      ativo = false;
    };
  }, [apiDisponivel, auth.session, router, startupConcluido]);

  useEffect(() => {
    if (!startupConcluido || !apiDisponivel || activeMainTab !== "painel") {
      return;
    }
    if (filaProcessos) {
      setCarregandoFila(false);
      return;
    }

    let ativo = true;
    const carregarFila = async (refresh = false) => {
      setCarregandoFila(true);
      setErroFila("");
      try {
        const data = await loadFilaProcessosOnce(refresh);
        if (!ativo) return;
        applyFilaProcessos(data);
        if (!refresh && data.source === "postgres-loading") {
          window.setTimeout(() => {
            if (ativo) void carregarFila(false);
          }, 1800);
        }
      } catch (error) {
        if (!ativo) return;
        setErroFila(error instanceof Error ? error.message : "Falha ao carregar fila.");
      } finally {
        if (ativo) setCarregandoFila(false);
      }
    };

    void carregarFila(false);
    return () => {
      ativo = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startupConcluido, apiDisponivel, activeMainTab, filaProcessos]);

  useEffect(() => {
    if (!startupConcluido || !apiDisponivel || activeMainTab !== "painel") {
      return;
    }

    let cancelled = false;
    let refreshTimeout: ReturnType<typeof setTimeout> | null = null;
    let lastErrorRefreshAt = 0;
    const source = createFilaProcessosEventSource();

    const scheduleRefresh = () => {
      if (refreshTimeout) {
        clearTimeout(refreshTimeout);
      }
      refreshTimeout = setTimeout(async () => {
        try {
          const data = await fetchFilaProcessos(false);
          if (!cancelled) {
            applyFilaProcessos(data);
            setErroFila("");
          }
        } catch (error) {
          if (!cancelled) {
            setErroFila(error instanceof Error ? error.message : "Falha ao sincronizar fila.");
          }
        }
      }, 250);
    };

    const handleFilaEvent = (event: Event) => {
      const data = (() => {
        try {
          return JSON.parse((event as MessageEvent<string>).data || "{}");
        } catch {
          return {};
        }
      })();
      if (data?.type === "servidores-sorteio-atualizados") {
        void loadRemoteQueueServers();
        scheduleRefresh();
        return;
      }
      if (data?.type === "alerta-servico-regras-atualizadas") {
        void loadRemoteAlertaServicoConfig();
        return;
      }
      if (data?.type === "datas-deducoes-regras-atualizadas") {
        void loadRemoteRegrasDatasDeducoes();
        return;
      }
      if (data?.type === "conclusao-alterada" && data.rowKey) {
        // O evento já carrega os valores confirmados pelo servidor —
        // atualiza a linha diretamente sem precisar de um refetch completo.
        // Isso elimina a janela de dado stale e torna a atualização instantânea.
        if (typeof data.concluido === "boolean") {
          const patch = {
            __concluido: data.concluido ? "1" : "",
            __concluido_por: String(data.concluidoPor || ""),
            __concluido_em: String(data.concluidoEm || ""),
          };
          updateRowMeta(data.rowKey as string, patch);
          setQueueLocalPatch(data.rowKey as string, patch, 20_000);
          setQueueConclusaoOverrides((current) => ({
            ...current,
            [data.rowKey as string]: {
              concluido: data.concluido as boolean,
              concluidoPor: String(data.concluidoPor || ""),
              concluidoEm: String(data.concluidoEm || ""),
            },
          }));
        } else {
          // Evento antigo sem payload — fallback para refetch
          scheduleRefresh();
        }
        return;
      }
      if (data?.type === "datas-globais-atualizadas") {
        const nextDates = data.dates;
        if (
          nextDates
          && typeof nextDates.apuracao === "string"
          && typeof nextDates.vencimento === "string"
        ) {
          const normalized = normalizeDatesForDisplay(nextDates);
          setDates(normalized);
          lastSavedDatesRef.current = JSON.stringify(normalized);
        } else {
          void fetchDatasGlobais().then((remoteDates) => {
            const normalized = normalizeDatesForDisplay(remoteDates);
            setDates(normalized);
            lastSavedDatesRef.current = JSON.stringify(normalized);
          });
        }
        return;
      }
      void loadAlertaServicoSetoresHistorico();
      scheduleRefresh();
    };

    source.addEventListener("fila", handleFilaEvent);
    source.onerror = () => {
      const now = Date.now();
      if (!cancelled && now - lastErrorRefreshAt >= 15_000) {
        lastErrorRefreshAt = now;
        scheduleRefresh();
      }
    };
    const pollId = window.setInterval(() => {
      if (!document.hidden) {
        scheduleRefresh();
      }
    }, 30000);

    return () => {
      cancelled = true;
      if (refreshTimeout) {
        clearTimeout(refreshTimeout);
      }
      window.clearInterval(pollId);
      source.removeEventListener("fila", handleFilaEvent);
      source.close();
    };
  }, [startupConcluido, apiDisponivel, activeMainTab]);

  const handleFileSelect = (file: File | null, source: "drop" | "input" | "clear") => {
    setErro("");
    setSelectedFile(file);
    if (file && source !== "clear") {
      void handleProcessar(file);
    }
  };

  const handleProcessar = async (fileOverride?: File) => {
    const arquivoParaProcessar = fileOverride ?? selectedFile;
    if (!arquivoParaProcessar) {
      setErro("Selecione um PDF antes de processar.");
      return;
    }
    if (isUploading) {
      return;
    }

    setIsUploading(true);
    setErro("");
    try {
      const result = await uploadPDF(arquivoParaProcessar, dates);
      if (result.success) {
        router.push(`/conferencia?id=${result.documentoId}`);
        return;
      }
      setErro(result.mensagem || "Não foi possível processar o documento.");
    } catch (error) {
      console.error("Erro ao processar:", error);
      setErro(
        error instanceof Error
          ? error.message
          : "Erro inesperado ao processar o documento."
      );
    } finally {
      setIsUploading(false);
    }
  };

  const handleAbrirChrome = async () => {
    setAbrindoChrome(true);
    setErro("");
    try {
      const status = await openChromeSession();
      setChromeStatus(status.chromeStatus);
      setApiDisponivel(true);
      setErroInicializacao("");
    } catch (error) {
      setErroInicializacao(
        error instanceof Error
          ? error.message
          : "Nao foi possivel abrir o Chrome."
      );
      setChromeStatus("erro");
      setApiDisponivel(false);
    } finally {
      setAbrindoChrome(false);
    }
  };

  const garantirChromeAbertoParaFila = async () => {
    let statusAtual = chromeStatus;
    try {
      const backendStatus = await fetchBackendStatus();
      statusAtual = backendStatus.chromeStatus;
      setChromeStatus(backendStatus.chromeStatus);
      setApiDisponivel(true);
    } catch {
      statusAtual = "erro";
    }

    if (statusAtual === "pronto") {
      return;
    }

    setAbrindoChrome(true);
    setChromeStatus("carregando");
    try {
      const status = await openChromeSession();
      setChromeStatus(status.chromeStatus);
      setApiDisponivel(true);
      setErroInicializacao("");
      if (status.chromeStatus !== "pronto") {
        throw new Error(status.mensagem || "Chrome não ficou pronto para atualizar a fila.");
      }
    } finally {
      setAbrindoChrome(false);
    }
  };

  const mostrarRegistroNotice = (mensagem: string) => {
    setRegistroNotice(mensagem);
    if (registroNoticeTimerRef.current) {
      clearTimeout(registroNoticeTimerRef.current);
    }
    registroNoticeTimerRef.current = setTimeout(() => {
      setRegistroNotice("");
      registroNoticeTimerRef.current = null;
    }, 2200);
  };

  const temRegistroLiquidacaoPendente = () => {
    if (typeof window === "undefined") return false;
    try {
      const parsed = JSON.parse(window.localStorage.getItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY) || "null") as RegistroLiquidacaoPendente | null;
      return Boolean(parsed?.documentoId || parsed?.numeroProcesso);
    } catch {
      return false;
    }
  };

  const copiarTextoParaAreaTransferencia = async (texto: string) => {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(texto);
      return;
    }
    if (typeof document === "undefined") return;
    const textarea = document.createElement("textarea");
    textarea.value = texto;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  };

  const concluirRegistroLiquidacao = async (finalizada: boolean) => {
    if (!registroPendente) return;
    if (registroSaving) return;
    if (finalizada && !registroNumeroDocumento.trim()) {
      setRegistroError("Informe o número do documento para registrar a liquidação como finalizada.");
      return;
    }
    setRegistroError("");
    setRegistroSaving(true);

    const payload: Parameters<typeof registrarLiquidacao>[0] = {
      documentoId: registroPendente.documentoId,
      numeroProcesso: registroPendente.numeroProcesso,
      finalizada,
      tipoDocumento: finalizada ? registroTipoDocumento : "",
      numeroDocumento: finalizada ? registroNumeroDocumento.trim() : "",
      dificuldade: finalizada ? registroDificuldade : undefined,
      servidorNome: auth.session?.nome || "",
      servidorUsername: auth.session?.username || "",
    };

    try {
      if (finalizada) {
        await copiarTextoParaAreaTransferencia(
          `Para conformidade, ${registroTipoDocumento} ${registroNumeroDocumento.trim()}.`
        );
      }
    } catch (error) {
      console.warn("Não foi possível copiar o despacho automaticamente.", error);
    }

    try {
      await registrarLiquidacao(payload);
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
      }
      setRegistroPendente(null);
      setRegistroNumeroDocumento("");
      setRegistroDificuldade(5);
      setRegistroDificuldadeInteragida(false);
      setDashboardRefreshSeq((seq) => seq + 1);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("autoliquid:liquidacao-registrada", { detail: payload }));
      }
      if (finalizada) {
        mostrarRegistroNotice("Despacho copiado!");
      }
    } catch (error) {
      setRegistroError(error instanceof Error ? error.message : "Não foi possível registrar a liquidação.");
    } finally {
      setRegistroSaving(false);
    }
  };

  const renderAlertaServicoRuleBuilder = () => {
    const normalizedConfig = normalizeAlertaServicoConfig(alertaServicoConfig);
    const defaultRule = normalizedConfig.regras.find((rule) => rule.id === ALERTA_SERVICO_REGRA_PADRAO_ID) ?? ALERTA_SERVICO_REGRA_PADRAO;
    const customRules = normalizedConfig.regras.filter((rule) => rule.id !== ALERTA_SERVICO_REGRA_PADRAO_ID);
    const renderRuleContent = (rule: AlertaServicoRule, label: string) => (
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <label className="inline-flex h-7 items-center gap-2 rounded-full border border-glass-border bg-muted/20 px-2.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={rule.active}
              onChange={(event) => toggleAlertaServicoRule(rule.id, event.target.checked)}
              className="h-3.5 w-3.5 accent-primary"
            />
            {rule.active ? "Ativa" : "Inativa"}
          </label>
          <span
            className={`inline-flex max-w-full rounded-full border px-2.5 py-1 text-xs font-medium ${
              rule.acaoVencimento === "IGNORAR"
                ? "border-zinc-300 bg-zinc-100 text-zinc-700"
                : "border-red-500/25 bg-red-500/10 text-red-700"
            }`}
          >
            <span className="truncate">{formatAlertaServicoAcao(rule)}</span>
          </span>
          <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            {label}
          </span>
        </div>
        <div className="mt-2 grid min-w-0 gap-2 text-sm sm:grid-cols-3">
          <span className="min-w-0 truncate text-foreground">
            <span className="mr-1 text-xs text-muted-foreground">Tipo</span>
            {rule.tipoDocumento === ALERTA_SERVICO_TIPO_TODOS ? "Todos" : rule.tipoDocumento}
          </span>
          <span className="min-w-0 truncate text-muted-foreground">
            <span className="mr-1 text-xs">CNPJ</span>
            {formatRuleScope(rule.cnpj)}
          </span>
          <span className="min-w-0 truncate text-muted-foreground">
            <span className="mr-1 text-xs">Setor</span>
            {formatRuleScope(rule.setor)}
          </span>
        </div>
      </div>
    );

    return (
      <div className="rounded-2xl border border-red-500/15 bg-red-500/5 p-3 text-sm text-foreground">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="block font-medium">Alerta</span>
            <GlobalScopeIcon message="Alterações neste alerta são globais e valem para todos os usuários." />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {savingAlertaServicoConfig ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : null}
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              Antecedência
              <input
                type="number"
                min={0}
                max={60}
                value={nfServicoAlertaDiasUteis}
                onChange={(event) =>
                  setNfServicoAlertaDiasUteis(Number(event.target.value || 0))
                }
                onBlur={() => void persistNfServicoAlertSetting()}
                className="w-20 rounded-xl border border-glass-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary"
                title="Dias úteis padrão"
              />
            </label>
            <GlassButton type="button" size="sm" onClick={openNewAlertaServicoRule}>
              <Plus className="h-4 w-4" />
              Nova Exceção
            </GlassButton>
          </div>
        </div>

        <div className="mt-3 overflow-hidden rounded-2xl border border-glass-border bg-background">
          <div className="divide-y divide-glass-border">
            <div
              className="grid min-w-0 gap-3 px-3 py-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center"
            >
              {renderRuleContent(defaultRule, "padrão")}
              <div className="flex items-center gap-1 lg:justify-end">
                <button
                  type="button"
                  onClick={() => openEditAlertaServicoRule(defaultRule)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-glass-border text-muted-foreground transition-colors hover:text-foreground"
                  title="Editar alerta padrão"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {customRules.map((rule) => (
              <div
                key={rule.id}
                className="grid min-w-0 gap-3 px-3 py-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center"
              >
                {renderRuleContent(rule, "exceção")}
                <div className="flex items-center gap-1 lg:justify-end">
                <button
                  type="button"
                  onClick={() => openEditAlertaServicoRule(rule)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-glass-border text-muted-foreground transition-colors hover:text-foreground"
                  title="Editar exceção"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => removeAlertaServicoRule(rule.id)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-glass-border text-muted-foreground transition-colors hover:border-red-500/40 hover:text-red-600"
                  title="Excluir exceção"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  const renderDeducoesRuleLauncher = () => (
    <section className="min-w-0 rounded-2xl border border-glass-border bg-background/55 p-4 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.4)]">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Controle de deduções</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Regras globais de SIAFI, códigos, vencimento, apuração e LF usadas na etapa de dedução.
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="rounded-full border border-glass-border bg-background px-2.5 py-1">
              {regrasDatasDeducoes.regras.length || "—"} regras
            </span>
            <span className="rounded-full border border-glass-border bg-background px-2.5 py-1">
              {auth.isModerator ? "Edição liberada" : "Somente leitura"}
            </span>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 md:justify-end">
          <GlassButton
            type="button"
            size="sm"
            onClick={openDeducoesRulesDialog}
          >
            <Settings2 className="h-4 w-4" />
            Abrir regras
          </GlassButton>
        </div>
      </div>
    </section>
  );

  if (!startupConcluido) {
    const showLogin = authGateReady && !authLoading;
    const hideCredentialFields = Boolean(storedAuthSession) && !showManualLogin;
    const loadingDetail = authLoading ? LOADING_PULSES[loadingPulseIndex] : startupState.detail;
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-2xl rounded-[32px] border border-glass-border bg-background/95 p-8 shadow-[0_34px_120px_-58px_rgba(15,23,42,0.5)] sm:p-10">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-3xl border border-primary/20 bg-primary/10 text-primary">
              {showLogin ? <Settings2 className="h-8 w-8" /> : <Loader2 className="h-8 w-8 animate-spin" />}
            </div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">AutoLiquid</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-foreground">
              {showLogin ? "Identificação" : startupState.title}
            </h1>
            <p className="mx-auto mt-3 max-w-md text-base leading-7 text-muted-foreground">
              {showLogin ? "Acesse com a conta salva ou escolha outro usuário." : loadingDetail}
            </p>
          </div>

          {!showLogin ? (
            <div className="space-y-6">
              <div className="h-3 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-sky-500 via-primary to-emerald-500 transition-[width] duration-[1400ms] ease-out"
                  style={{ width: `${Math.max(8, startupState.progress)}%` }}
                />
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {LOADING_STEPS.map((step, index) => {
                  const active = startupState.progress >= 14 + index * 14;
                  return (
                    <div
                      key={step}
                      className={`rounded-2xl border px-3 py-3 text-center text-sm font-medium transition-colors ${
                        active
                          ? "border-primary/25 bg-primary/10 text-primary"
                          : "border-glass-border bg-muted/20 text-muted-foreground"
                      }`}
                    >
                      {step}
                    </div>
                  );
                })}
              </div>
              <p className="rounded-2xl border border-glass-border bg-muted/20 px-5 py-4 text-center text-sm leading-6 text-muted-foreground">
                {LOADING_PULSES[(loadingPulseIndex + 2) % LOADING_PULSES.length]}
              </p>
              {startupError ? (
                <GlassButton
                  type="button"
                  variant="secondary"
                  size="md"
                  onClick={() => setStartupRunId((current) => current + 1)}
                  className="w-full justify-center"
                >
                  <RefreshCw className="h-4 w-4" />
                  Tentar novamente
                </GlassButton>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4">
              {storedAuthSession ? (
                <button
                  type="button"
                  onClick={() => void concluirEntrada(storedAuthSession)}
                  className="flex w-full items-center justify-between rounded-2xl border border-primary/25 bg-primary/10 px-4 py-3 text-left text-sm transition-colors hover:bg-primary/15"
                >
                  <span>
                    <span className="block font-semibold text-foreground">Auto-login</span>
                    <span className="text-xs text-muted-foreground">
                      Entrar como {storedAuthSession.nome || storedAuthSession.username}
                    </span>
                  </span>
                  <span className="rounded-full border border-primary/25 bg-background px-2.5 py-1 text-xs font-medium text-primary">
                    {storedAuthSession.role === "moderator" ? "moderator" : "user"}
                  </span>
                </button>
              ) : null}

              {authError && hideCredentialFields ? (
                <p className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {authError}
                </p>
              ) : null}

              {hideCredentialFields ? (
                <GlassButton
                  type="button"
                  variant="secondary"
                  size="md"
                  onClick={() => {
                    setShowManualLogin(true);
                    setLoginUsername("");
                    setLoginPassword("");
                    setAuthError("");
                  }}
                  className="w-full justify-center"
                >
                  Outra conta
                </GlassButton>
              ) : (
                <form onSubmit={handleLoginSubmit} className="space-y-3">
                  <input
                    value={loginUsername}
                    onChange={(event) => setLoginUsername(event.target.value)}
                    placeholder="Usuário"
                    className="w-full rounded-2xl border border-glass-border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary"
                  />
                  <input
                    type="password"
                    value={loginPassword}
                    onChange={(event) => setLoginPassword(event.target.value)}
                    placeholder="Senha"
                    className="w-full rounded-2xl border border-glass-border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary"
                  />
                  {authError ? (
                    <p className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                      {authError}
                    </p>
                  ) : null}
                  <GlassButton type="submit" size="md" className="w-full justify-center" disabled={authLoading}>
                    {authLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    Entrar
                  </GlassButton>
                  {storedAuthSession ? (
                    <button
                      type="button"
                      onClick={() => {
                        setShowManualLogin(false);
                        setLoginUsername(storedAuthSession.username);
                        setLoginPassword("");
                        setAuthError("");
                      }}
                      className="w-full text-center text-xs font-medium text-muted-foreground transition-colors hover:text-primary"
                    >
                      Usar auto-login
                    </button>
                  ) : null}
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Background decoration */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -left-1/4 -top-1/4 h-1/2 w-1/2 rounded-full bg-primary/5 blur-3xl" />
        <div className="absolute -bottom-1/4 -right-1/4 h-1/2 w-1/2 rounded-full bg-accent/5 blur-3xl" />
      </div>

      <Header
        chromeStatus={chromeStatus}
        browserName={browserName}
        onGoHome={() => setActiveMainTab("dashboard")}
        onOpenTabelas={() => {
          setTabelasInitialTab("contratos");
          setTabelasVisibleTabs(undefined);
          setIsTabelasOpen(true);
        }}
        onOpenConfiguracoes={() => setIsConfiguracoesOpen(true)}
        onOpenChrome={handleAbrirChrome}
        chromeActionDisabled={abrindoChrome || !apiDisponivel}
        onOpenDashboard={() => setIsDashboardOpen(true)}
        onOpenFerias={() => setIsFeriasOpen(true)}
        rocketChatUnreadCount={rocketChatUnreadCount}
      />

      <DashboardModal
        open={isDashboardOpen}
        onClose={() => setIsDashboardOpen(false)}
        rows={filaDistribuida}
      />
      <FeriasModal
        open={isFeriasOpen}
        onClose={() => setIsFeriasOpen(false)}
        servidoresSugeridos={[...new Set(filaDistribuida.map((r) => r.responsavel).filter(Boolean))].sort()}
      />

      <main className="relative mx-auto w-full max-w-[96vw] px-4 py-6 sm:px-5 sm:py-8 2xl:max-w-[1700px]">
        <section className="mb-5 rounded-[28px] border border-glass-border bg-glass-bg px-5 py-5 shadow-[0_28px_80px_-48px_rgba(15,23,42,0.4)] backdrop-blur-xl sm:px-6">

          {/* ── Cabeçalho + Abas ── */}
          <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary/80">
                AutoLiquid
              </p>
              <h1 className="mt-2 text-balance text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                {activeMainTab === "dashboard"
                  ? "Dashboard"
                  : activeMainTab === "painel"
                    ? "Fila de Processos"
                    : activeMainTab === "liquidacao"
                      ? "Liquidação"
                      : "Registro"}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {activeMainTab === "dashboard"
                  ? "Análise histórica de todos os processos executados."
                  : activeMainTab === "painel"
                    ? "Acompanhe a fila consolidada de processos do Solar."
                    : activeMainTab === "liquidacao"
                      ? "Acesse os portais municipais e execute a liquidação no SIAFI."
                      : "Envie o PDF da liquidação para extrair e conferir os dados antes de executar."}
              </p>
            </div>

            {/* Seletor de abas */}
            <div className="flex shrink-0 gap-1 rounded-xl border border-glass-border bg-background/60 p-1">
              {(["painel", "liquidacao", "registro"] as MainTab[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveMainTab(tab)}
                  className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
                    activeMainTab === tab
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab === "painel" ? "Fila de Processos" : tab === "liquidacao" ? "Liquidação" : "Registro"}
                </button>
              ))}
            </div>
          </div>

          {bannerUpdate && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-violet-500/30 bg-violet-500/10 px-4 py-3">
            <div className="flex items-center gap-3 min-w-0">
              <ArrowDownToLine className="h-4 w-4 shrink-0 text-violet-700" />
              <p className="text-sm text-violet-700">
                <span className="font-semibold">Nova versão disponível:</span>{" "}
                v{bannerUpdate.versao_nova}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <a
                href={bannerUpdate.url_download}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-violet-500/30 bg-background/80 px-3 py-1.5 text-xs font-medium text-violet-700 transition-colors hover:bg-background"
              >
                Baixar
              </a>
              <button
                type="button"
                onClick={() => setBannerUpdate(null)}
                className="rounded-full p-1 text-violet-500 transition-colors hover:bg-violet-500/10"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            </div>
          )}

          {erroInicializacao && (
            <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {erroInicializacao}
            </div>
          )}

          {!startupConcluido && (
            <div className="mb-4 flex flex-col gap-3 rounded-2xl border border-glass-border/70 bg-background/60 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-foreground">{startupState.title}</p>
                <p className="mt-1 text-sm text-muted-foreground">{startupState.detail}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full border border-glass-border bg-background/70 px-3 py-1 text-xs text-muted-foreground">
                  {startupState.progress}%
                </span>
                {startupError ? (
                  <GlassButton
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setStartupRunId((current) => current + 1)}
                  >
                    Tentar novamente
                  </GlassButton>
                ) : null}
              </div>
            </div>
          )}

          {/* ── Aba: Dashboard histórico ── */}
          {activeMainTab === "dashboard" && (
            <DashboardHistorico visible={activeMainTab === "dashboard"} />
          )}

          {/* ── Aba: Painel (Fila de Processos) ── */}
          {activeMainTab === "painel" && (
            <div className="space-y-4">
              <section className="rounded-2xl border border-glass-border bg-background/55 p-4 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.4)]">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-foreground">Fila de Processos (Solar)</h3>
                      <Popover>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            className="rounded-full border border-glass-border bg-background px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
                          >
                            {filaFiltrada.length} processos
                          </button>
                        </PopoverTrigger>
                        <PopoverContent align="start" className="w-80 p-0 shadow-xl">
                          {(() => {
                            const totalValor = filaFiltrada.reduce((s, r) => s + parseValorBRL(r.valor), 0);
                            const totalConcluidos = filaFiltrada.filter((r) => r.concluido).length;

                            // Agrupa por primeiro nome do responsável
                            const byResp = new Map<string, { count: number; valor: number; concluidos: number }>();
                            for (const row of filaFiltrada) {
                              const nome = formatFirstNameLabel(firstNameOf(row.responsavel)) || "—";
                              const cur = byResp.get(nome) ?? { count: 0, valor: 0, concluidos: 0 };
                              byResp.set(nome, {
                                count: cur.count + 1,
                                valor: cur.valor + parseValorBRL(row.valor),
                                concluidos: cur.concluidos + (row.concluido ? 1 : 0),
                              });
                            }
                            const sorted = Array.from(byResp.entries()).sort((a, b) => b[1].count - a[1].count);
                            const maxCount = sorted[0]?.[1]?.count ?? 1;

                            return (
                              <>
                                {/* Totais */}
                                <div className="border-b border-glass-border px-4 py-3">
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-primary/70">
                                    Resumo da fila
                                  </p>
                                  <div className="mt-2 grid grid-cols-3 gap-2">
                                    <div className="rounded-xl border border-glass-border bg-muted/30 px-2.5 py-2 text-center">
                                      <p className="text-base font-bold text-foreground">{filaFiltrada.length}</p>
                                      <p className="text-[10px] text-muted-foreground">processos</p>
                                    </div>
                                    <div className="rounded-xl border border-glass-border bg-muted/30 px-2.5 py-2 text-center">
                                      <p className="text-base font-bold text-foreground">{formatValorCompact(totalValor)}</p>
                                      <p className="text-[10px] text-muted-foreground">valor total</p>
                                    </div>
                                    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/8 px-2.5 py-2 text-center">
                                      <p className="text-base font-bold text-emerald-700">{totalConcluidos}</p>
                                      <p className="text-[10px] text-emerald-600/70">concluídos</p>
                                    </div>
                                  </div>
                                </div>

                                {/* Por responsável */}
                                <div className="px-4 py-3">
                                  <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                                    Por responsável
                                  </p>
                                  <div className="space-y-2.5">
                                    {sorted.map(([nome, stats]) => (
                                      <div key={nome}>
                                        <div className="mb-1 flex items-center justify-between gap-2">
                                          <span className="text-xs font-medium text-foreground">{nome}</span>
                                          <div className="flex items-center gap-2">
                                            {stats.concluidos > 0 && (
                                              <span className="text-[10px] font-medium text-emerald-600">
                                                {stats.concluidos} ✓
                                              </span>
                                            )}
                                            <span className="text-[10px] text-muted-foreground">
                                              {formatValorCompact(stats.valor)}
                                            </span>
                                            <span className="w-5 text-right text-xs font-semibold text-foreground">
                                              {stats.count}
                                            </span>
                                          </div>
                                        </div>
                                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted/50">
                                          <div
                                            className="h-full rounded-full bg-primary/50 transition-all"
                                            style={{ width: `${(stats.count / maxCount) * 100}%` }}
                                          />
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </>
                            );
                          })()}
                        </PopoverContent>
                      </Popover>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {filaProcessos?.updatedAt
                        ? `Última atualização: ${new Date(filaProcessos.updatedAt).toLocaleString("pt-BR", {
                            day: "2-digit",
                            month: "2-digit",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}`
                        : "Tabela consolidada carregada do Solar."}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2 rounded-lg border border-glass-border bg-background px-3 py-1.5 text-sm text-foreground">
                      <span className="text-xs text-muted-foreground">Responsável</span>
                      <select
                        value={responsavelFilter}
                        onChange={(event) => setResponsavelFilter(event.target.value)}
                        className="bg-transparent text-sm outline-none"
                      >
                        <option value="todos">Todos</option>
                        {responsavelOptions.map((nome) => (
                          <option key={nome} value={nome}>
                            {formatFirstNameLabel(nome)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={() => setQueueSettingsOpen(true)}
                      className="inline-flex items-center gap-2 rounded-lg border border-glass-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-background/80"
                    >
                      <Settings2 className="h-4 w-4" />
                      Ajustes
                    </button>
                    <GlassButton
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={async () => {
                        setCarregandoFila(true);
                        setErroFila("");
                        try {
                          await garantirChromeAbertoParaFila();
                          const data = await fetchFilaProcessos(true);
                          filaLoadPromiseRef.current = null;
                          setQueueConclusaoOverrides({});
                          applyFilaProcessos(data, { force: true });
                        } catch (error) {
                          setErroFila(error instanceof Error ? error.message : "Falha ao atualizar fila.");
                        } finally {
                          setCarregandoFila(false);
                        }
                      }}
                      disabled={carregandoFila || !apiDisponivel}
                    >
                      <RefreshCw className={`h-4 w-4 ${carregandoFila ? "animate-spin" : ""}`} />
                      {carregandoFila ? "Atualizando..." : "Atualizar fila"}
                    </GlassButton>
                  </div>
                </div>

                {erroFila && (
                  <div className="mb-3 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {erroFila}
                  </div>
                )}

                {carregandoFila && !filaProcessos ? (
                  <div className="rounded-xl border border-glass-border bg-background/70 px-4 py-8 text-center text-sm text-muted-foreground">
                    Carregando fila de processos...
                  </div>
                ) : filaFiltrada.length > 0 ? (
                  <div className="overflow-x-auto rounded-xl border border-glass-border bg-background/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.45)]">
                    <table className={`${queueTableMinWidth} table-fixed text-sm leading-5`}>
                      <thead className="bg-muted/65">
                        <tr>
                          {queueColumnsToRender.map((column) => (
                            <th
                              key={column.key}
                              style={{ width: queueColumnWidths[column.key] ?? column.defaultWidth }}
                              className={`group relative select-none whitespace-nowrap border-b border-glass-border text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground ${compactQueueColumns ? "px-2 py-2" : "px-3 py-2.5"}`}
                            >
                              {column.label}
                              <span
                                role="separator"
                                aria-orientation="vertical"
                                title="Arraste para redimensionar"
                                onMouseDown={(event) => beginResizeQueueColumn(column.key, event)}
                                className="absolute right-0 top-0 h-full w-3 cursor-col-resize opacity-0 group-hover:opacity-100 after:absolute after:right-1 after:top-1/2 after:h-4 after:w-0.5 after:-translate-y-1/2 after:rounded-full after:bg-primary/40 after:content-['']"
                              />
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {filaFiltrada.map((row, idx) => (
                          <tr
                            key={`fila-${idx}`}
                            className={[
                              "border-b border-glass-border/60 last:border-0",
                              row.concluido
                                ? "bg-emerald-500/10 hover:bg-emerald-500/15"
                                : "odd:bg-background/35 even:bg-background/10 hover:bg-primary/5",
                            ].join(" ")}
                          >
                            {queueColumnsToRender.map((column) => (
                              <td
                                key={`${idx}-${column.key}`}
                                style={{ width: queueColumnWidths[column.key] ?? column.defaultWidth, maxWidth: queueColumnWidths[column.key] ?? column.defaultWidth }}
                                className={`overflow-hidden whitespace-nowrap align-top text-foreground ${compactQueueColumns ? "px-2 py-2 text-[13px]" : "px-3 py-2.5"}`}
                              >
                                {column.key === "responsavel" ? (
                                  <div className={queueColumnWidths[column.key] ? "w-full min-w-0 overflow-hidden" : compactQueueColumns ? "min-w-[132px]" : "min-w-[180px]"}>
                                    <div className="flex min-w-0 items-center gap-2">
                                      <button
                                        type="button"
                                        onClick={() => void toggleQueueConclusao(row)}
                                        title={
                                          row.concluido
                                            ? `Concluído${row.concluidoPor ? ` por ${row.concluidoPor}` : ""}`
                                            : "Marcar processo como concluído"
                                        }
                                        className={[
                                          "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-50",
                                          row.concluido
                                            ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-700"
                                            : "border-glass-border bg-transparent text-muted-foreground hover:border-emerald-500/40 hover:text-emerald-700",
                                        ].join(" ")}
                                      >
                                        <CheckCircle2 className="h-3.5 w-3.5" />
                                      </button>
                                      <input
                                        type="text"
                                        value={queueResponsavelDrafts[row.rowKey] ?? row.responsavel}
                                        onChange={(event) =>
                                          updateResponsavelDraft(row.rowKey, event.target.value)
                                        }
                                        onBlur={() => void persistResponsavel(row)}
                                        onKeyDown={(event) => {
                                          if (event.key === "Enter") {
                                            event.currentTarget.blur();
                                          }
                                        }}
                                        className="min-w-0 flex-1 truncate rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm text-foreground outline-none transition-colors focus:border-primary focus:bg-background/80"
                                      />
                                      {row.responsavelAlterado ? (
                                        <span
                                          title={formatResponsavelTooltip(
                                            row.responsavelAlteradoPor,
                                            row.responsavelAlteradoEm,
                                          )}
                                          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/10 text-[11px] font-semibold text-amber-700"
                                        >
                                          !
                                        </span>
                                      ) : null}
                                      <Popover>
                                        <PopoverTrigger asChild>
                                          <button
                                            type="button"
                                            title={row.alertas.length ? "Ver mensagens" : "Adicionar mensagem"}
                                            className={[
                                              "inline-flex h-5 shrink-0 items-center justify-center rounded-full border text-[11px] transition-colors",
                                              row.alertas.length
                                                ? "min-w-5 border-sky-500/35 bg-sky-500/10 px-1.5 text-sky-700 hover:bg-sky-500/15"
                                                : "w-5 border-glass-border bg-transparent text-muted-foreground hover:border-sky-500/35 hover:text-sky-700",
                                            ].join(" ")}
                                          >
                                            {row.alertas.length ? (
                                              <>
                                                <MessageSquare className="h-3 w-3" />
                                                <span className="ml-1">{row.alertas.length}</span>
                                              </>
                                            ) : (
                                              <Plus className="h-3 w-3" />
                                            )}
                                          </button>
                                        </PopoverTrigger>
                                        <PopoverContent align="start" className="w-80 p-3">
                                          <div className="space-y-3">
                                            {row.alertas.length > 0 ? (
                                              <div className="max-h-44 space-y-2 overflow-y-auto pr-1">
                                                {row.alertas.map((alerta) => (
                                                  <div
                                                    key={alerta.id}
                                                    className="rounded-lg border border-sky-500/20 bg-sky-500/10 px-3 py-2"
                                                  >
                                                    <div className="flex items-start gap-2">
                                                      <div className="min-w-0 flex-1">
                                                        <p className="whitespace-pre-wrap text-sm leading-5 text-foreground">
                                                          {alerta.mensagem}
                                                        </p>
                                                        <p className="mt-1 text-[11px] text-muted-foreground">
                                                          {[alerta.autor, formatAlertaCriadoEm(alerta.criadoEm)]
                                                            .filter(Boolean)
                                                            .join(" • ")}
                                                        </p>
                                                      </div>
                                                      <button
                                                        type="button"
                                                        onClick={() => void removeQueueAlert(row, alerta)}
                                                        disabled={deletingAlertId === alerta.id}
                                                        title="Remover mensagem"
                                                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-sky-500/20 text-sky-700 transition-colors hover:bg-sky-500/15 disabled:cursor-not-allowed disabled:opacity-50"
                                                      >
                                                        <X className="h-3.5 w-3.5" />
                                                      </button>
                                                    </div>
                                                  </div>
                                                ))}
                                              </div>
                                            ) : null}
                                            <div className="space-y-2">
                                              <textarea
                                                value={queueAlertDrafts[row.rowKey] ?? ""}
                                                onChange={(event) =>
                                                  updateAlertDraft(row.rowKey, event.target.value)
                                                }
                                                placeholder="Adicionar mensagem..."
                                                rows={3}
                                                className="w-full resize-none rounded-lg border border-glass-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-sky-500"
                                              />
                                              <div className="flex justify-end">
                                                <button
                                                  type="button"
                                                  onClick={() => void persistQueueAlert(row)}
                                                  disabled={
                                                    savingAlertKey === row.rowKey ||
                                                    !normalizeQueueCell(queueAlertDrafts[row.rowKey])
                                                  }
                                                  className="inline-flex items-center gap-1.5 rounded-lg border border-sky-500/25 bg-sky-500/10 px-2.5 py-1.5 text-xs font-medium text-sky-700 transition-colors hover:bg-sky-500/15 disabled:cursor-not-allowed disabled:opacity-50"
                                                >
                                                  <Plus className="h-3.5 w-3.5" />
                                                  Adicionar
                                                </button>
                                              </div>
                                            </div>
                                          </div>
                                        </PopoverContent>
                                      </Popover>
                                    </div>
                                  </div>
                                ) : column.key === "competencia" ? (
                                  <div className="flex w-full min-w-0 items-center overflow-hidden">
                                    {row.nfServicoAlerta ? (
                                      <span
                                        title={row.nfServicoAlertaTooltip}
                                        className="min-w-0 truncate rounded border border-red-500/40 bg-red-500/8 px-1.5 py-0.5 text-[12px] font-medium text-red-700"
                                      >
                                        {row.competencia}
                                      </span>
                                    ) : (
                                      <span className="min-w-0 truncate">{row.competencia}</span>
                                    )}
                                  </div>
                                ) : column.key === "numeroProcesso" ? (
                                  (() => {
                                    const processoSolar = row.processoSolar || row.numeroProcesso;
                                    const processoExibicao = formatFilaProcessoCurto(processoSolar);
                                    return processoSolar ? (
                                      <button
                                        type="button"
                                        disabled={openingSolarProcessKey === row.rowKey || !apiDisponivel}
                                        onClick={() => void abrirProcessoSolarDaFila(row)}
                                        className="inline-flex max-w-full items-center gap-1.5 truncate text-left font-mono text-foreground underline-offset-2 hover:text-primary hover:underline disabled:cursor-wait disabled:opacity-60"
                                        title={`${processoSolar} — abrir processo no Solar`}
                                      >
                                        {openingSolarProcessKey === row.rowKey ? (
                                          <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                                        ) : null}
                                        <span className="min-w-0 truncate">{processoExibicao}</span>
                                      </button>
                                    ) : (
                                      <span className="block min-w-0 truncate text-muted-foreground/40">—</span>
                                    );
                                  })()
                                ) : column.key === "tipo" ? (
                                  <div className="flex w-full min-w-0 flex-nowrap items-center gap-1 overflow-hidden">
                                    {mostrarTipoBadges && row.tipo ? (() => {
                                      const tipos = parseTipos(row.tipo);
                                      return tipos.map((entry, i) => (
                                        <span
                                          key={i}
                                          title={entry.label}
                                          className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-none ${entry.style}`}
                                        >
                                          {entry.abbr}
                                        </span>
                                      ));
                                    })() : (
                                      <span className="min-w-0 truncate text-foreground" title={row.tipo}>
                                        {row.tipo}
                                      </span>
                                    )}
                                    {mostrarSimples && (() => {
                                      const cnpjLimpo = row.cpfCnpj.replace(/\D/g, "");
                                      if (cnpjLimpo.length !== 14) return null;
                                      if (isLoadingSimples && !(cnpjLimpo in queueSimplesMap)) {
                                        return <span className="h-2 w-2 animate-pulse rounded-full bg-muted-foreground/30" />;
                                      }
                                      const status = queueSimplesMap[cnpjLimpo];
                                      if (status === true) return (
                                        <span title="Optante pelo Simples Nacional" className="inline-flex shrink-0 items-center rounded-full border border-emerald-500/35 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold leading-none text-emerald-700">
                                          SN
                                        </span>
                                      );
                                      if (status === false) return (
                                        <span title="Não optante pelo Simples Nacional" className="inline-flex shrink-0 items-center rounded-full border border-orange-500/30 bg-orange-500/8 px-2 py-0.5 text-[10px] font-semibold leading-none text-orange-700">
                                          NS
                                        </span>
                                      );
                                      return null;
                                    })()}
                                  </div>
                                ) : column.key === "cpfCnpj" ? (() => {
                                  const cnpjLimpo = row.cpfCnpj.replace(/\D/g, "");
                                  const clicavel = cnpjLimpo.length === 14;
                                  return clicavel ? (
                                    <button
                                      type="button"
                                      className="block w-full min-w-0 truncate text-left underline-offset-2 hover:text-primary hover:underline"
	                                      title={`${row.cpfCnpj} — clique para ver histórico`}
	                                      onClick={() => {
	                                        abrirHistoricoDaFila(row);
	                                      }}
                                    >
                                      {row.cpfCnpj}
                                    </button>
                                  ) : (
                                    <span className="block min-w-0 truncate">{row.cpfCnpj}</span>
                                  );
                                })() : column.key === "credor" ? (
                                  <button
                                    type="button"
                                    className="block w-full min-w-0 truncate text-left text-foreground underline-offset-2 hover:text-primary hover:underline"
	                                    title={`${row.credor} — clique para ver histórico`}
	                                    onClick={() => {
	                                      abrirHistoricoDaFila(row);
	                                    }}
                                  >
                                    {row.credor}
                                  </button>
                                ) : column.key === "valor" ? (
                                  <span className="block w-full min-w-0 truncate text-right tabular-nums" title={row.valor}>
                                    {row.valor}
                                  </span>
                                ) : column.key === "ic" ? (() => {
                                  // Se já tem IC na fila, exibe normalmente
                                  if (row.ic) {
                                    return (
                                      <span className="block min-w-0 truncate" title={row.ic}>
                                        {row.ic}
                                      </span>
                                    );
                                  }
                                  // Se tem contrato, tenta o lookup na tabela de contratos
                                  if (row.contrato) {
                                    const icLookup = queueIcOverrides[row.contrato];
                                    if (icLookup === null) {
                                      // Cadastrado na tabela mas sem IC, ou não encontrado
                                      return (
                                        <span className="block min-w-0 truncate text-[11px] italic text-muted-foreground/60" title="Não cadastrado na tabela de contratos">
                                          Não cadastrado
                                        </span>
                                      );
                                    }
                                    if (icLookup) {
                                      return (
                                        <span className="block min-w-0 truncate" title={icLookup}>
                                          {icLookup}
                                        </span>
                                      );
                                    }
                                  }
                                  return <span className="block min-w-0 truncate text-muted-foreground/40">—</span>;
                                })() : (
                                  <span className="block min-w-0 truncate" title={String(row[column.key] ?? "")}>
                                    {String(row[column.key] ?? "")}
                                  </span>
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="rounded-xl border border-glass-border bg-background/70 px-4 py-8 text-center text-sm text-muted-foreground">
                    Nenhum processo na fila para exibir.
                  </div>
                )}
              </section>
            </div>
          )}

          {/* ── Aba: Liquidação ── */}
          {activeMainTab === "liquidacao" && (
            <div className="space-y-4">
              <IssPortais />
              <CnpjChecker cnpjInicial={buscaHistorico?.cnpj ?? ""} />
              <NfeConsulta />
              <HistoricoBusca buscaInicial={buscaProcesso} buscaInicialCnpj={buscaHistorico} />
            </div>
          )}

          {/* ── Aba: Registro ── */}
          {activeMainTab === "registro" && (
          <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)] xl:items-start">
            {/* Coluna esquerda: datas + upload (cards separados) */}
            <div className="flex min-w-0 flex-col gap-4">
              <DateFields dates={dates} onDatesChange={setDates} compact />

              <div className="min-w-0 rounded-2xl border border-glass-border bg-background/55 p-4 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.4)]">
                <UploadZone
                  key={uploadResetKey}
                  onFileSelect={handleFileSelect}
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
                        Envie o PDF e siga direto para a conferência.
                      </p>
                    )}
                  </div>

                  <GlassButton
                    variant="secondary"
                    size="lg"
                    onClick={() => handleProcessar()}
                    disabled={!selectedFile || isUploading || !apiDisponivel}
                    className="w-full md:w-auto"
                  >
                    {isUploading ? (
                      <Loader2 className="h-5 w-5 animate-spin" />
                    ) : (
                      <FileUp className="h-5 w-5" />
                    )}
                    {isUploading ? "Processando PDF..." : "Processar Documento"}
                  </GlassButton>
                </div>
              </div>

              {renderDeducoesRuleLauncher()}
            </div>

            {/* Coluna direita: dashboard */}
            <div className="flex min-w-0 flex-col gap-4 rounded-2xl border border-glass-border bg-background/55 p-5 shadow-[0_18px_50px_-36px_rgba(15,23,42,0.4)] xl:sticky xl:top-4">
              {/* Cabeçalho do dashboard */}
              <div className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                      Meus processos
                    </p>
                    <p className="mt-0.5 text-sm text-muted-foreground">
                      {nomeUsuario || "Servidor"}
                    </p>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex rounded-lg border border-glass-border bg-secondary/30 p-0.5 text-[11px] font-semibold">
                    {Object.entries(DASHBOARD_LABELS).map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setDashboardPeriodo(value as keyof typeof DASHBOARD_LABELS)}
                        className={`rounded-md px-2.5 py-1.5 transition-colors ${
                          dashboardPeriodo === value
                            ? "bg-background text-foreground shadow-sm"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <label className="flex h-9 items-center gap-2 rounded-lg border border-glass-border bg-secondary/30 px-2.5 text-[11px] font-semibold text-muted-foreground">
                    Máx.
                    <select
                      value={dashboardProcessLimit}
                      onChange={(event) => setDashboardProcessLimit(Math.max(1, Math.min(100, Number(event.target.value) || 5)))}
                      className="h-7 rounded-md border border-glass-border bg-background px-2 text-xs font-semibold text-foreground outline-none transition focus:border-primary"
                    >
                      {DASHBOARD_LIMIT_OPTIONS.map((value) => (
                        <option key={value} value={value}>{value}</option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>

              {/* Métricas */}
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
                <div className="rounded-2xl border border-glass-border/70 bg-background/70 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Bruto</p>
                  <p className="mt-1 whitespace-nowrap text-base font-bold tabular-nums text-foreground sm:text-lg">
                    {carregandoDashboard ? "—" : formatCurrency(dashboard?.valorBruto ?? 0)}
                  </p>
                </div>
                <div className="rounded-2xl border border-glass-border/70 bg-background/70 px-4 py-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Processos</p>
                  <p className="mt-1 text-xl font-bold text-foreground">
                    {carregandoDashboard ? "—" : dashboard?.quantidadeProcessos ?? 0}
                  </p>
                </div>
              </div>

              {/* Lista de processos recentes */}
              <div className="flex flex-col gap-1 flex-1">
                <div className="flex items-center justify-between mb-1">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Recentes
                  </p>
                  {dashboard?.habilitado === false && (
                    <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                      BD indisponível
                    </span>
                  )}
                </div>

                {carregandoDashboard ? (
                  <p className="text-sm text-muted-foreground py-2">Carregando...</p>
                ) : (dashboard?.ultimosProcessos?.length ?? 0) > 0 ? (
                  dashboard!.ultimosProcessos.map((processo, index) => {
                    const status = normalizeDashboardStatus(processo.status);
                    return (
                      <button
                        key={processo.numeroProcesso || `processo-${index}`}
                        type="button"
                        onClick={() => {
                          setBuscaProcesso(processo.numeroProcesso);
                          setActiveMainTab("liquidacao");
                        }}
                        className="group grid w-full grid-cols-[auto_minmax(0,1fr)] gap-3 rounded-xl border border-glass-border/50 bg-secondary/20 px-3 py-2.5 text-left transition-all hover:border-primary/30 hover:bg-primary/5"
                      >
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-foreground group-hover:bg-primary/15 group-hover:text-primary">
                          {index + 1}
                        </span>
                        <div className="min-w-0">
                          <div className="flex min-w-0 flex-wrap items-center gap-2">
                            <span className="truncate font-mono text-xs font-semibold text-foreground">
                              {processo.numeroProcesso}
                            </span>
                            <span
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                                status === "concluido"
                                  ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-700"
                                  : "border-amber-500/25 bg-amber-500/10 text-amber-700"
                              }`}
                            >
                              {status === "concluido" ? "Concluído" : "Aguardando"}
                            </span>
                          </div>
                          <div className="mt-1 flex min-w-0 items-center justify-between gap-2">
                            {processo.fornecedor ? (
                              <p className="min-w-0 truncate text-[11px] text-muted-foreground">
                                {processo.fornecedor}
                              </p>
                            ) : (
                              <span className="min-w-0" />
                            )}
                            {processo.bruto != null && processo.bruto > 0 && (
                              <span className="shrink-0 text-[11px] font-semibold tabular-nums text-foreground">
                                {formatCurrency(processo.bruto)}
                              </span>
                            )}
                          </div>
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    {nomeUsuario
                      ? "Nenhum processo registrado ainda."
                      : "Nenhum processo registrado ainda."}
                  </p>
                )}
              </div>
            </div>
          </div>
          )}
        </section>
      </main>

      {queueSettingsOpen ? (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-2 sm:p-4">
          <button
            type="button"
            aria-label="Fechar ajustes"
            className="absolute inset-0 bg-background/65 backdrop-blur-sm"
            onClick={() => setQueueSettingsOpen(false)}
          />
          <div className="relative z-10 flex max-h-[calc(100dvh-1rem)] w-full max-w-[min(1180px,calc(100vw-1rem))] flex-col overflow-hidden rounded-2xl border border-glass-border bg-background/95 shadow-[0_30px_100px_-45px_rgba(15,23,42,0.45)]">
            <div className="grid gap-3 border-b border-glass-border px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-5">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-primary/80">
                  Ajustes da Fila
                </p>
                <h2 className="mt-1.5 text-xl font-semibold text-foreground">
                  Preferências da fila
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Controle atualização, visualização, colunas e sorteio sem ocupar a tela inteira.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setQueueSettingsOpen(false)}
                className="rounded-full border border-glass-border bg-background p-2 text-muted-foreground transition-colors hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
              <div className="grid min-w-0 gap-4 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <div className="min-w-0 space-y-4">
                  <section className="min-w-0 rounded-2xl border border-glass-border bg-muted/20 p-4">
                    <div className="mb-3">
                      <div>
                        <h3 className="text-base font-semibold text-foreground">Atualização</h3>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Defina como a coleta no Solar se comporta e ajuste alertas operacionais.
                        </p>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <label className="grid gap-3 rounded-2xl border border-glass-border bg-background px-3 py-2.5 text-sm text-foreground sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                        <span className="min-w-0">
                          <span className="block font-medium">Fechar aba após atualizar fila</span>
                          <span className="text-xs text-muted-foreground">
                            Fecha somente a aba do Solar criada para coletar a tabela; mantém o navegador aberto.
                          </span>
                        </span>
                        <input
                          type="checkbox"
                          checked={fecharAbaFila}
                          onChange={(event) => void persistFecharAbaFilaSetting(event.target.checked)}
                        />
                      </label>
                      {renderAlertaServicoRuleBuilder()}
                    </div>
                  </section>

                  <section className="min-w-0 rounded-2xl border border-glass-border bg-muted/20 p-4">
                    <div className="mb-3">
                      <h3 className="text-base font-semibold text-foreground">Visualização</h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Ajustes locais de leitura da tabela no painel.
                      </p>
                    </div>
                    <div className="space-y-3">
                      <label className="grid gap-3 rounded-2xl border border-glass-border bg-background px-3 py-2.5 text-sm text-foreground sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                        <span className="min-w-0">
                          <span className="block font-medium">Colunas compactas</span>
                          <span className="text-xs text-muted-foreground">
                            Reduz larguras e espaçamentos apenas neste computador.
                          </span>
                        </span>
                        <input
                          type="checkbox"
                          checked={compactQueueColumns}
                          onChange={(event) => setCompactQueueColumns(event.target.checked)}
                        />
                      </label>
                      <label className="grid gap-3 rounded-2xl border border-glass-border bg-background px-3 py-2.5 text-sm text-foreground sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                        <span className="min-w-0">
                          <span className="block font-medium">Badges de tipo</span>
                          <span className="text-xs text-muted-foreground">
                            Exibe etiquetas coloridas por tipo (NF Serviço, Boleto, Proc. Origem…) na coluna Tipo.
                          </span>
                        </span>
                        <input
                          type="checkbox"
                          checked={mostrarTipoBadges}
                          onChange={(event) => setMostrarTipoBadges(event.target.checked)}
                        />
                      </label>
                      <label className="grid gap-3 rounded-2xl border border-glass-border bg-background px-3 py-2.5 text-sm text-foreground sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                        <span className="min-w-0">
                          <span className="block font-medium">Indicador Simples Nacional</span>
                          <span className="text-xs text-muted-foreground">
                            Exibe badge "SN" no credor quando a consulta da API identificar o CNPJ como optante.
                          </span>
                        </span>
                        <input
                          type="checkbox"
                          checked={mostrarSimples}
                          onChange={(event) => setMostrarSimples(event.target.checked)}
                        />
                      </label>
                    </div>
                  </section>

                  <section className="min-w-0 rounded-2xl border border-glass-border bg-muted/20 p-4">
                    <div className="mb-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                      <div className="min-w-0">
                        <h3 className="text-base font-semibold text-foreground">Colunas</h3>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Oculte colunas, reorganize a ordem e ajuste larguras no cabeçalho da fila.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={resetQueueColumnWidths}
                        className="rounded-lg border border-glass-border bg-background px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                      >
                        Resetar larguras
                      </button>
                    </div>
                    <div className="mb-2 flex justify-end">
                      <button
                        type="button"
                        onClick={resetQueueColumnOrder}
                        className="rounded-lg border border-glass-border bg-background px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                      >
                        Ordem padrão
                      </button>
                    </div>
                    <div className="space-y-2">
                      {visibleQueueColumns.map((columnKey, index) => {
                        const column = queueColumnsByKey.get(columnKey);
                        if (!column) return null;
                        return (
                          <div
                            key={column.key}
                            draggable
                            onDragStart={(event) => handleQueueColumnDragStart(event, column.key)}
                            onDragOver={(event) => event.preventDefault()}
                            onDrop={(event) => handleQueueColumnDrop(event, column.key)}
                            className="grid cursor-grab grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-2xl border border-glass-border bg-background px-3 py-2 text-sm text-foreground active:cursor-grabbing"
                          >
                            <button
                              type="button"
                              onClick={() => toggleQueueColumn(column.key)}
                              disabled={visibleQueueColumns.length === 1}
                              className="inline-flex h-5 w-5 items-center justify-center rounded-md border border-primary/30 bg-primary/10 text-[11px] font-bold text-primary disabled:opacity-40"
                              title="Desativar coluna"
                            >
                              ✓
                            </button>
                            <span className="min-w-0 truncate">{column.label}</span>
                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => moveQueueColumn(column.key, -1)}
                                disabled={index === 0}
                                title="Mover para a esquerda"
                                className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-glass-border text-muted-foreground transition-colors hover:text-foreground disabled:opacity-35"
                              >
                                <ArrowUp className="h-3.5 w-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => moveQueueColumn(column.key, 1)}
                                disabled={index === visibleQueueColumns.length - 1}
                                title="Mover para a direita"
                                className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-glass-border text-muted-foreground transition-colors hover:text-foreground disabled:opacity-35"
                              >
                                <ArrowDown className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-4 rounded-2xl border border-dashed border-glass-border bg-background/60 p-3">
                      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Colunas desativadas
                      </p>
                      {inactiveQueueColumns.length ? (
                        <div className="flex flex-wrap gap-2">
                          {inactiveQueueColumns.map((column) => (
                            <button
                              key={column.key}
                              type="button"
                              onClick={() => activateQueueColumn(column.key)}
                              className="rounded-full border border-glass-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                            >
                              + {column.label}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">Todas as colunas estão ativas.</p>
                      )}
                    </div>
                  </section>
                </div>
                <section className="min-w-0 rounded-2xl border border-glass-border bg-muted/20 p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-semibold text-foreground">Servidores no sorteio</h3>
                        <GlobalScopeIcon
                          label="Global"
                          message="Alterações nos servidores do sorteio são globais e valem para todos os usuários."
                        />
                        <Popover>
                          <PopoverTrigger asChild>
                            <button
                              type="button"
                              aria-label="Sobre o sorteio"
                              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-glass-border bg-background text-muted-foreground transition-colors hover:text-foreground"
                            >
                              <Info className="h-3.5 w-3.5" />
                            </button>
                          </PopoverTrigger>
                          <PopoverContent align="start" sideOffset={8} className="z-[140] w-96 max-w-[calc(100vw-2rem)] rounded-xl p-3 text-sm leading-5 text-muted-foreground shadow-xl">
                            <div className="space-y-2">
                              <p>
                                O sorteio é determinístico: o backend lê do Turso a fila e o status dos servidores, roda em memória a mesma fórmula da planilha e devolve o responsável calculado para cada processo.
                              </p>
                              <p>
                                A fórmula usa o número do processo como id de cálculo, a lista-base de 100 posições e os pesos de cada slot. Servidor ativo usa todos os slots, 1/2 usa apenas metade das ocorrências, e fora não participa.
                              </p>
                              <p>
                                O resultado é estável: com o mesmo processo e os mesmos status, o responsável será sempre o mesmo. Alterações manuais continuam tendo prioridade sobre o sorteio.
                              </p>
                            </div>
                          </PopoverContent>
                        </Popover>
                      </div>
                      <p className="mt-1 text-sm text-muted-foreground">
                        Defina a participação de cada servidor cadastrado no sorteio.
                      </p>
                    </div>
                  </div>

                  <div className="overflow-hidden rounded-2xl border border-glass-border bg-background">
                    <div className="hidden grid-cols-[minmax(0,1fr)_120px_140px] gap-3 border-b border-glass-border bg-muted/30 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground md:grid">
                      <span>Servidor</span>
                      <span className="text-center">Fila</span>
                      <span>Status</span>
                    </div>
                    <div className="divide-y divide-glass-border">
                      {queueServers.map((server) => (
                        <div
                          key={server.id}
                          className="grid gap-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_120px_140px] md:items-center md:gap-3"
                        >
                          <div className="min-w-0 rounded-xl border border-glass-border bg-muted/20 px-3 py-2 text-sm font-medium text-foreground">
                            {server.nome || "Servidor sem nome"}
                          </div>
                          <div className="flex md:justify-center">
                            <span className="inline-flex rounded-full border border-glass-border bg-muted/30 px-2.5 py-1 text-xs font-medium text-foreground">
                              {queueProcessCounts.get(normalizeServerKey(server.nome)) ?? 0} processos
                            </span>
                          </div>
                          <select
                            value={server.modo}
                            onChange={(event) =>
                              updateQueueServer(server.id, {
                                modo: event.target.value as QueueServerMode,
                              })
                            }
                            className="rounded-xl border border-glass-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-primary"
                          >
                            <option value="ativo">1</option>
                            <option value="metade">1/2</option>
                            <option value="fora">Fora</option>
                          </select>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {registroPendente ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 px-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-glass-border bg-background p-5 shadow-[0_28px_90px_-45px_rgba(15,23,42,0.55)]">
            <div className="mb-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-primary">Registro da liquidação</p>
              <h2 className="mt-2 text-xl font-semibold text-foreground">
                Você terminou a liquidação do processo {registroPendente.numeroProcesso || "informado"}?
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Se ainda não terminou, marque como não finalizada agora. Quando finalizar, volte com o documento gerado e registre os dados abaixo.
              </p>
            </div>

            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-[130px_minmax(0,1fr)]">
                <label className="space-y-1.5">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Tipo</span>
                  <select
                    value={registroTipoDocumento}
                    onChange={(event) => setRegistroTipoDocumento(event.target.value as RegistroLiquidacaoTipoDocumento)}
                    className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm font-medium text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                    disabled={registroSaving}
                  >
                    <option value="NP">NP</option>
                    <option value="RP">RP</option>
                    <option value="LF">LF</option>
                  </select>
                </label>
                <label className="space-y-1.5">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">Número do documento</span>
                  <input
                    value={registroNumeroDocumento}
                    onChange={(event) => setRegistroNumeroDocumento(event.target.value)}
                    className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                    disabled={registroSaving}
                  />
                </label>
              </div>

              <DifficultySlider
                value={registroDificuldade}
                onChange={(nextValue) => {
                  setRegistroDificuldade(nextValue);
                }}
                onInteract={() => setRegistroDificuldadeInteragida(true)}
                disabled={registroSaving}
              />
            </div>

            {registroError ? (
              <div className="mt-4 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {registroError}
              </div>
            ) : null}

            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
              <button
                type="button"
                onClick={() => void concluirRegistroLiquidacao(false)}
                disabled={registroSaving}
                className="inline-flex h-11 items-center justify-center rounded-2xl border border-slate-300 bg-transparent px-4 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Não, ainda não finalizei
              </button>
              <button
                type="button"
                onClick={() => void concluirRegistroLiquidacao(true)}
                disabled={registroSaving || !registroNumeroDocumento.trim() || !registroDificuldadeInteragida}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 text-sm font-semibold text-slate-50 shadow-md shadow-slate-900/20 transition-all hover:-translate-y-0.5 hover:bg-slate-800 hover:shadow-lg disabled:translate-y-0 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none"
                title={!registroDificuldadeInteragida ? "Mova a barra de dificuldade para habilitar o registro." : undefined}
              >
                {registroSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Registrar conclusão
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {registroNotice ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/35 px-6 backdrop-blur-sm">
          <div
            role="status"
            aria-live="polite"
            className="registro-notice rounded-3xl border border-emerald-500/25 bg-background/95 px-6 py-5 text-center text-base font-semibold text-emerald-800 shadow-[0_28px_90px_-45px_rgba(15,23,42,0.65)]"
          >
            {registroNotice}
          </div>
        </div>
      ) : null}

      <style jsx>{`
        .registro-notice {
          animation: registro-notice-in 180ms ease-out;
        }

        @keyframes registro-notice-in {
          from {
            opacity: 0;
            transform: translateY(6px) scale(0.96);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
      `}</style>

      <Dialog open={deducoesRulesDialogOpen} onOpenChange={setDeducoesRulesDialogOpen}>
        <DialogContent className="flex max-h-[calc(100vh-2rem)] min-h-0 flex-col overflow-hidden p-0 sm:max-w-5xl">
          <DialogHeader className="shrink-0 border-b border-glass-border px-5 py-4 pr-12">
            <DialogTitle>Regras de deduções</DialogTitle>
            <DialogDescription>
              Consulte as regras globais usadas para classificar códigos, calcular datas e exigir LF nas deduções.
            </DialogDescription>
          </DialogHeader>

          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden px-5 py-4">
            <div className="grid gap-3 rounded-2xl border border-glass-border bg-muted/20 p-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
              <div className="min-w-0 text-sm text-muted-foreground">
                {auth.isModerator ? (
                  <span>Modo moderador: alterações salvas passam a impactar extração, datas e execução das deduções.</span>
                ) : (
                  <span>Somente moderadores podem alterar estas regras. Você pode consultar todas as configurações.</span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 md:justify-end">
                <button
                  type="button"
                  onClick={() => void loadRemoteRegrasDatasDeducoes()}
                  disabled={carregandoRegrasDatasDeducoes || savingRegrasDatasDeducoes}
                  className="inline-flex h-9 items-center gap-2 rounded-xl border border-glass-border bg-background px-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${carregandoRegrasDatasDeducoes ? "animate-spin" : ""}`} />
                  Recarregar
                </button>
                <button
                  type="button"
                  onClick={addRegraDataDeducao}
                  disabled={!auth.isModerator}
                  className="inline-flex h-9 items-center gap-2 rounded-xl border border-glass-border bg-background px-3 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <Plus className="h-4 w-4" />
                  Nova regra
                </button>
                <GlassButton
                  type="button"
                  size="sm"
                  onClick={() => void persistRegrasDatasDeducoes()}
                  disabled={!auth.isModerator || carregandoRegrasDatasDeducoes || savingRegrasDatasDeducoes || !regrasDatasDeducoes.regras.length}
                  title={!auth.isModerator ? "Apenas moderadores podem salvar regras de deduções." : undefined}
                >
                  {savingRegrasDatasDeducoes ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  {savingRegrasDatasDeducoes ? "Salvando..." : "Salvar"}
                </GlassButton>
              </div>
            </div>

            {erroRegrasDatasDeducoes ? (
              <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {erroRegrasDatasDeducoes}
              </div>
            ) : null}

            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              {carregandoRegrasDatasDeducoes ? (
                <div className="flex items-center gap-2 rounded-2xl border border-glass-border bg-background px-4 py-6 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Carregando regras...
                </div>
              ) : regrasDatasDeducoes.regras.length ? (
                <div className="space-y-3">
                  {regrasDatasDeducoes.regras.map((rule, index) => {
                    const usaDataUsuario = rule.mesVencimento === "usuario";
                    const codigoDraft = codigoDeducaoDrafts[rule.id] ?? "";
                    const ajusteDiaNaoUtil = rule.ajusteDiaNaoUtil || "antecipar";
                    const previewDeducao = buildDeducaoRulePreview({ ...rule, ajusteDiaNaoUtil });
                    const isExpanded = Boolean(expandedDeducaoRuleIds[rule.id]);
                    return (
                      <section key={rule.id} className="overflow-hidden rounded-2xl border border-glass-border bg-background/95 shadow-sm">
                        <div className="grid gap-2 px-4 py-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                          <button
                            type="button"
                            onClick={() => toggleRegraDataDeducaoExpanded(rule.id)}
                            className="grid min-w-0 gap-2 text-left sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center"
                            aria-expanded={isExpanded}
                          >
                            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-glass-border bg-muted/20 text-muted-foreground">
                              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                            </span>
                            <span className="min-w-0">
                              <span className="flex min-w-0 flex-wrap items-center gap-2">
                                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                                  Regra {index + 1}
                                </span>
                                <span className="rounded-full border border-glass-border bg-muted/20 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                                  {rule.siafi || "SIAFI"}
                                </span>
                                {rule.precisaLf ? (
                                  <span className="rounded-full border border-violet-500/20 bg-violet-500/10 px-2 py-0.5 text-[11px] font-medium text-violet-700">
                                    LF
                                  </span>
                                ) : null}
                              </span>
                              <span className="mt-1 block truncate text-sm font-semibold text-foreground" title={rule.nome}>
                                {rule.nome || "Regra sem nome"}
                              </span>
                              <span className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                <span className="inline-flex min-w-0 items-center gap-1">
                                  <CalendarDays className="h-3.5 w-3.5 shrink-0" />
                                  <span className="truncate">{buildDeducaoRuleSummary(rule)}</span>
                                </span>
                                <span className="truncate font-mono">
                                  {rule.codigos.length ? rule.codigos.join(", ") : "sem códigos"}
                                </span>
                              </span>
                            </span>
                          </button>
                          <button
                            type="button"
                            onClick={() => removeRegraDataDeducao(rule.id)}
                            disabled={!auth.isModerator}
                            className="inline-flex h-9 items-center justify-center gap-2 rounded-xl border border-glass-border px-3 text-xs font-medium text-muted-foreground transition-colors hover:border-red-500/40 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Trash2 className="h-4 w-4" />
                            Remover
                          </button>
                        </div>

                        {isExpanded ? (
                          <div className="border-t border-glass-border p-4">
                            <div className="space-y-3 rounded-2xl border border-glass-border bg-muted/10 p-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Identidade da regra</p>
                          </div>
                          <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_120px]">
                            <label className="space-y-1.5">
                              <span className="text-xs font-medium text-muted-foreground">Nome da regra</span>
                              <input
                                value={rule.nome}
                                disabled={!auth.isModerator}
                                onChange={(event) => patchRegraDataDeducao(rule.id, { nome: event.target.value })}
                                className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                              />
                            </label>
                            <label className="space-y-1.5">
                              <span className="text-xs font-medium text-muted-foreground">SIAFI</span>
                              <input
                                value={rule.siafi}
                                disabled={!auth.isModerator}
                                maxLength={6}
                                onChange={(event) => patchRegraDataDeducao(rule.id, { siafi: event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })}
                                className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 font-mono text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                                placeholder="DDF055"
                              />
                            </label>
                          </div>

                          <div className="space-y-1.5">
                            <span className="text-xs font-medium text-muted-foreground">Códigos</span>
                            <div className="rounded-xl border border-glass-border bg-background p-2">
                              <div className="flex min-h-9 flex-wrap items-center gap-2">
                                {rule.codigos.length ? (
                                  rule.codigos.map((codigo) => (
                                    <span
                                      key={codigo}
                                      className="inline-flex h-8 items-center gap-1 rounded-lg border border-glass-border bg-muted/20 px-2 font-mono text-xs text-foreground"
                                    >
                                      {codigo}
                                      <button
                                        type="button"
                                        onClick={() => removeCodigoRegraDataDeducao(rule.id, codigo)}
                                        disabled={!auth.isModerator}
                                        className="inline-flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                                        aria-label={`Remover código ${codigo}`}
                                        title={`Remover código ${codigo}`}
                                      >
                                        <Minus className="h-3.5 w-3.5" />
                                      </button>
                                    </span>
                                  ))
                                ) : (
                                  <span className="px-1 text-xs text-muted-foreground">Nenhum código adicionado.</span>
                                )}
                              </div>
                              <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                                <input
                                  value={codigoDraft}
                                  disabled={!auth.isModerator}
                                  inputMode="numeric"
                                  onChange={(event) =>
                                    setCodigoDeducaoDrafts((current) => ({
                                      ...current,
                                      [rule.id]: normalizeCodigoDeducao(event.target.value),
                                    }))
                                  }
                                  onKeyDown={(event) => {
                                    if (event.key !== "Enter") return;
                                    event.preventDefault();
                                    addCodigoRegraDataDeducao(rule.id);
                                  }}
                                  className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 font-mono text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                                  placeholder="Digite um código"
                                />
                                <button
                                  type="button"
                                  onClick={() => addCodigoRegraDataDeducao(rule.id)}
                                  disabled={!auth.isModerator || !codigoDraft}
                                  className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-glass-border bg-background px-3 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-45"
                                >
                                  <Plus className="h-4 w-4" />
                                  Adicionar
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="mt-3 space-y-3 rounded-2xl border border-glass-border bg-muted/10 p-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Lógica de apuração e vencimento</p>
                          <div className="flex flex-wrap items-end gap-2 text-sm text-muted-foreground">
                            <label className="min-w-[240px] space-y-1.5">
                              <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Apuração</span>
                              <select
                                value={rule.apuracao}
                                disabled={!auth.isModerator || usaDataUsuario}
                                onChange={(event) =>
                                  patchRegraDataDeducao(rule.id, {
                                    apuracao: event.target.value as RegraDataDeducao["apuracao"],
                                  })
                                }
                                className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                              >
                                <option value="emissao_mais_antiga">Emissão mais antiga das NFs</option>
                                <option value="usuario">Usuário informa</option>
                              </select>
                            </label>
                            <span className="pb-2">→</span>
                            <span className="pb-2">Vencimento no</span>
                            {!usaDataUsuario ? (
                              <label className="w-36 space-y-1.5">
                                <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Dia</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={31}
                                  disabled={!auth.isModerator}
                                  value={rule.diaVencimento ?? ""}
                                  onChange={(event) =>
                                    patchRegraDataDeducao(rule.id, {
                                      diaVencimento: Math.max(1, Math.min(31, Number(event.target.value || 20))),
                                    })
                                  }
                                  className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                                  aria-label="Dia do vencimento"
                                />
                              </label>
                            ) : (
                              <label className="space-y-1.5">
                                <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Dia</span>
                                <span className="inline-flex h-10 items-center rounded-xl border border-dashed border-glass-border bg-muted/30 px-3 text-sm text-muted-foreground">
                                  informado pelo usuário
                                </span>
                              </label>
                            )}
                            <span className="pb-2">do</span>
                            <label className="min-w-[170px] space-y-1.5">
                              <span className="block text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Mês do vencimento</span>
                              <select
                                value={rule.mesVencimento}
                                disabled={!auth.isModerator}
                                onChange={(event) => {
                                  const mesVencimento = event.target.value as RegraDataDeducao["mesVencimento"];
                                  patchRegraDataDeducao(rule.id, {
                                    mesVencimento,
                                    apuracao: mesVencimento === "usuario" ? "usuario" : rule.apuracao,
                                    diaVencimento: mesVencimento === "usuario" ? null : rule.diaVencimento ?? 20,
                                  });
                                }}
                                className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                              >
                                <option value="seguinte">Mês seguinte</option>
                                <option value="atual">Mesmo mês</option>
                                <option value="usuario">Usuário informa</option>
                              </select>
                            </label>
                          </div>

                          {!usaDataUsuario ? (
                            <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_160px]">
                              <label className="space-y-1.5">
                                <span className="text-xs font-medium text-muted-foreground">Dias não úteis</span>
                                <select
                                  value={ajusteDiaNaoUtil}
                                  disabled={!auth.isModerator}
                                  onChange={(event) =>
                                    patchRegraDataDeducao(rule.id, {
                                      ajusteDiaNaoUtil: event.target.value as RegraDataDeducao["ajusteDiaNaoUtil"],
                                    })
                                  }
                                  className="h-10 w-full rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                                >
                                  <option value="antecipar">Antecipar para dia útil anterior</option>
                                  <option value="prorrogar">Prorrogar para próximo dia útil</option>
                                  <option value="manter">Manter data</option>
                                </select>
                              </label>
                              <label className="flex h-10 items-center gap-2 self-end rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground">
                                <input
                                  type="checkbox"
                                  checked={rule.precisaLf}
                                  disabled={!auth.isModerator}
                                  onChange={(event) => patchRegraDataDeducao(rule.id, { precisaLf: event.target.checked })}
                                />
                                Precisa LF
                              </label>
                            </div>
                          ) : (
                            <label className="flex h-10 w-fit items-center gap-2 rounded-xl border border-glass-border bg-background px-3 text-sm text-foreground">
                              <input
                                type="checkbox"
                                checked={rule.precisaLf}
                                disabled={!auth.isModerator}
                                onChange={(event) => patchRegraDataDeducao(rule.id, { precisaLf: event.target.checked })}
                              />
                              Precisa LF
                            </label>
                          )}

                          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
                            {previewDeducao}
                          </div>
                        </div>

                        <label className="mt-3 block space-y-1.5">
                          <span className="text-xs font-medium text-muted-foreground">Observação livre</span>
                          <textarea
                            value={rule.observacao}
                            disabled={!auth.isModerator}
                            onChange={(event) => patchRegraDataDeducao(rule.id, { observacao: event.target.value })}
                            className="min-h-20 w-full resize-y rounded-xl border border-glass-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:bg-muted/40 disabled:text-muted-foreground"
                          />
                        </label>

                        <p className="mt-3 text-xs text-muted-foreground">
                          {formatMesVencimentoDeducao(rule.mesVencimento)} · Apuração: {formatApuracaoDeducao(rule.apuracao)} · Dias não úteis: {formatAjusteDiaNaoUtilDeducao(ajusteDiaNaoUtil)}
                        </p>
                          </div>
                        ) : null}
                      </section>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-2xl border border-glass-border bg-background px-4 py-8 text-center text-sm text-muted-foreground">
                  Nenhuma regra de dedução carregada.
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="shrink-0 border-t border-glass-border px-5 py-4">
            <button
              type="button"
              onClick={() => setDeducoesRulesDialogOpen(false)}
              className="inline-flex h-10 items-center justify-center rounded-xl border border-glass-border bg-background px-4 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              Fechar
            </button>
            <GlassButton
              type="button"
              onClick={() => void persistRegrasDatasDeducoes()}
              disabled={!auth.isModerator || carregandoRegrasDatasDeducoes || savingRegrasDatasDeducoes || !regrasDatasDeducoes.regras.length}
            >
              {savingRegrasDatasDeducoes ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              {savingRegrasDatasDeducoes ? "Salvando..." : "Salvar regras"}
            </GlassButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={alertaServicoDialogOpen}
        onOpenChange={(open) => {
          setAlertaServicoDialogOpen(open);
          if (!open) setEditingAlertaServicoRuleId(null);
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {editingAlertaServicoRuleId === ALERTA_SERVICO_REGRA_PADRAO_ID
                ? "Editar alerta padrão"
                : editingAlertaServicoRuleId
                  ? "Editar exceção"
                  : "Nova exceção"}
            </DialogTitle>
            <DialogDescription>
              Monte uma regra combinando tipo, CNPJ e setor. Campos vazios valem como Todos.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            <section className="rounded-2xl border border-glass-border bg-muted/20 p-4">
              <h3 className="text-sm font-semibold text-foreground">Quando se aplica?</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-[1.08fr_1fr_1fr]">
                <label className="space-y-1.5 text-sm">
                  <span className="text-xs font-medium text-muted-foreground">Tipo</span>
                  <select
                    value={alertaServicoRuleDraft.tipoDocumento}
                    onChange={(event) =>
                      setAlertaServicoRuleDraft((current) => ({
                        ...current,
                        tipoDocumento: event.target.value,
                      }))
                    }
                    className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                  >
                    <option value={ALERTA_SERVICO_TIPO_TODOS}>Todos os tipos</option>
                    {alertaServicoTipoOptions.map((tipo) => (
                      <option key={tipo} value={tipo}>{tipo}</option>
                    ))}
                  </select>
                </label>

                <label className="space-y-1.5 text-sm">
                  <span className="text-xs font-medium text-muted-foreground">CNPJ</span>
                  <input
                    value={alertaServicoRuleDraft.cnpj}
                    onChange={(event) =>
                      setAlertaServicoRuleDraft((current) => ({
                        ...current,
                        cnpj: event.target.value,
                      }))
                    }
                    placeholder="Vazio = Todos"
                    className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                  />
                </label>

                <label className="space-y-1.5 text-sm">
                  <span className="text-xs font-medium text-muted-foreground">Setor</span>
                  <input
                    list="alerta-servico-setores"
                    value={alertaServicoRuleDraft.setor}
                    onChange={(event) =>
                      setAlertaServicoRuleDraft((current) => ({
                        ...current,
                        setor: event.target.value,
                      }))
                    }
                    placeholder="Vazio = Todos"
                    className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                  />
                  <datalist id="alerta-servico-setores">
                    {alertaServicoSetorOptions.map((setor) => (
                      <option key={setor} value={setor} />
                    ))}
                  </datalist>
                </label>
              </div>
            </section>

            <section className="rounded-2xl border border-glass-border bg-muted/20 p-4">
              <h3 className="text-sm font-semibold text-foreground">O que acontece?</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-[1.25fr_1fr]">
                <label className="space-y-1.5 text-sm">
                  <span className="text-xs font-medium text-muted-foreground">Ação</span>
                  <select
                    value={alertaServicoRuleDraft.acaoVencimento}
                    onChange={(event) =>
                      setAlertaServicoRuleDraft((current) => ({
                        ...current,
                        acaoVencimento: event.target.value as AlertaServicoRule["acaoVencimento"],
                        valorAcao: event.target.value === "DIA_FIXO_MES_SEGUINTE" ? "20" : "",
                      }))
                    }
                    className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                  >
                    <option value="IGNORAR">Ignorar</option>
                    <option value="DIA_FIXO_MES_SEGUINTE">Dia fixo do mês seguinte</option>
                    <option value="DATA_PERSONALIZADA">Data personalizada</option>
                  </select>
                </label>

                {alertaServicoRuleDraft.acaoVencimento === "DIA_FIXO_MES_SEGUINTE" ? (
                  <label className="space-y-1.5 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">Dia</span>
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={alertaServicoRuleDraft.valorAcao}
                      onChange={(event) =>
                        setAlertaServicoRuleDraft((current) => ({
                          ...current,
                          valorAcao: event.target.value,
                        }))
                      }
                      className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                    />
                  </label>
                ) : null}

                {alertaServicoRuleDraft.acaoVencimento === "DATA_PERSONALIZADA" ? (
                  <label className="space-y-1.5 text-sm">
                    <span className="text-xs font-medium text-muted-foreground">Data</span>
                    <input
                      type="date"
                      value={alertaServicoRuleDraft.valorAcao}
                      onChange={(event) =>
                        setAlertaServicoRuleDraft((current) => ({
                          ...current,
                          valorAcao: event.target.value,
                        }))
                      }
                      className="h-11 w-full rounded-2xl border border-glass-border bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
                    />
                  </label>
                ) : null}
              </div>
              {alertaServicoRuleDraft.acaoVencimento !== "IGNORAR" ? (
                <div className="mt-3 rounded-xl border border-sky-500/15 bg-sky-500/10 px-3 py-2 text-xs leading-5 text-sky-800">
                  O AutoLiquid considera o dia útil correspondente; se a data escolhida cair em fim de semana ou feriado operacional, usa o dia útil anterior.
                </div>
              ) : null}
            </section>
          </div>

          <DialogFooter>
            <GlassButton
              type="button"
              variant="secondary"
              onClick={() => setAlertaServicoDialogOpen(false)}
            >
              Cancelar
            </GlassButton>
            <GlassButton type="button" onClick={saveAlertaServicoRuleDraft}>
              Salvar exceção
            </GlassButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tabelas Modal */}
      <TabelasModal
        isOpen={isTabelasOpen}
        onClose={() => {
          setIsTabelasOpen(false);
          setTabelasVisibleTabs(undefined);
        }}
        initialTab={tabelasInitialTab}
        visibleTabs={tabelasVisibleTabs}
      />

      <ConfiguracoesModal
        isOpen={isConfiguracoesOpen}
        onClose={() => setIsConfiguracoesOpen(false)}
        onSaved={async () => {
          try {
            const settings = await fetchAppSettings();
            setBrowserName(settings.navegador === "edge" ? "Edge" : "Chrome");
            setNomeUsuario((current) => auth.session?.nome || auth.session?.username || current || settings.nomeUsuario || "");
            setNfServicoAlertaDiasUteis(settings.nfServicoAlertaDiasUteis ?? 3);
            setFecharAbaFila(Boolean(settings.fecharAbaFila));
            void loadRemoteAlertaServicoConfig();
            try {
              const rocket = await fetchRocketChatNotifications();
              setRocketChatUnreadCount(rocket.configured ? rocket.count : null);
            } catch {
              setRocketChatUnreadCount(null);
            }
            const status = await fetchBackendStatus();
            setChromeStatus(status.chromeStatus);
          } catch {
            setChromeStatus("erro");
          }
        }}
        onChromeOpened={async () => {
          try {
            const status = await fetchBackendStatus();
            setChromeStatus(status.chromeStatus);
            setApiDisponivel(true);
            setErroInicializacao("");
          } catch {
            setChromeStatus("erro");
            setApiDisponivel(false);
          }
        }}
      />

    </div>
  );
}
