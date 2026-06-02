"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Banknote, CheckCircle2, FileUp, Loader2, Play, Upload, Users, X } from "lucide-react";
import { Header } from "@/components/header";
import { DocumentoPanel } from "@/components/documento-panel";
import { NotasFiscaisTable } from "@/components/notas-fiscais-table";
import { FilaExecucao } from "@/components/fila-execucao";
import { LogExecucaoPanel } from "@/components/log-execucao-panel";
import { StatusOverview } from "@/components/status-overview";
import { ConfiguracoesModal } from "@/components/configuracoes-modal";
import { TabelasModal } from "@/components/tabelas-modal";
import { FeriasModal } from "@/components/ferias-modal";
import { PendenciasPanel } from "@/components/pendencias-panel";
import { GlassButton } from "@/components/glass-card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  abrirUrl,
  MOCK_DOCUMENTO,
  MOCK_DEDUCOES,
  MOCK_EMPENHOS,
  MOCK_RESUMO_FINANCEIRO,
  MOCK_NOTAS_FISCAIS,
  MOCK_ETAPAS_EXECUCAO,
  MOCK_PROCESS_DATES,
  fetchBackendStatus,
  fetchDocumentoProcessado,
  fetchAppSettings,
  openChromeSession,
  openSiafiIncognito,
  pararExecucao,
  type Documento,
  type Deducao,
  type DocumentoProcessado,
  type Empenho,
  type PendenciaDocumento,
  type ResumoFinanceiro,
  type NotaFiscal,
  type RemessaBolsa,
  type EtapaExecucao,
  type ProcessDates,
  type StatusGeralDocumento,
  type TableKey,
  executarTodas,
  executarEtapa,
  executarDeducao,
  apropriarSIAFI,
  atualizarPendenciaDocumento,
  registrarLiquidacao,
  descartarRegistroLiquidacaoPendente,
  uploadRemessaBolsa,
  type RegistroLiquidacaoTipoDocumento,
} from "@/lib/data";
import { readStoredAuthSession } from "@/lib/auth-store";
import { useAuth } from "@/lib/auth-context";
import { SimpleTooltip } from "@/components/ui/simple-tooltip";

// ── Pontuação de Dificuldade ─────────────────────────────────────────────────

const DIFFICULTY_OPTIONS: { value: number; label: string; short: string; color: string; bg: string; ring: string }[] = [
  { value: 1, label: "Rotineiro",  short: "1", color: "text-emerald-700", bg: "bg-emerald-500/10 hover:bg-emerald-500/20", ring: "ring-emerald-500/40" },
  { value: 2, label: "Simples",    short: "2", color: "text-teal-700",    bg: "bg-teal-500/10 hover:bg-teal-500/20",     ring: "ring-teal-500/40" },
  { value: 3, label: "Moderado",   short: "3", color: "text-amber-700",   bg: "bg-amber-500/10 hover:bg-amber-500/20",   ring: "ring-amber-500/40" },
  { value: 4, label: "Trabalhoso", short: "4", color: "text-orange-700",  bg: "bg-orange-500/10 hover:bg-orange-500/20", ring: "ring-orange-500/40" },
  { value: 5, label: "Complexo",   short: "5", color: "text-rose-700",    bg: "bg-rose-500/10 hover:bg-rose-500/20",     ring: "ring-rose-500/40" },
];

function formatarDataComBarras(valor: string) {
  const texto = String(valor || "").trim();
  const iso = texto.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;

  const comSeparador = texto.match(/^(\d{2})[-/.](\d{2})[-/.](\d{4})$/);
  if (comSeparador) return `${comSeparador[1]}/${comSeparador[2]}/${comSeparador[3]}`;

  const digitos = texto.replace(/\D/g, "").slice(0, 8);
  if (digitos.length <= 2) return digitos;
  if (digitos.length <= 4) return `${digitos.slice(0, 2)}/${digitos.slice(2)}`;
  return `${digitos.slice(0, 2)}/${digitos.slice(2, 4)}/${digitos.slice(4)}`;
}

function DifficultyPicker({
  value,
  onChange,
  disabled,
}: {
  value: number | null;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        Dificuldade
      </span>
      <div className="grid grid-cols-5 gap-1.5">
        {DIFFICULTY_OPTIONS.map((opt) => {
          const selected = value === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange(opt.value)}
              className={`flex flex-col items-center gap-1 rounded-xl border py-2.5 px-1 text-center transition-all disabled:cursor-not-allowed disabled:opacity-50
                ${selected
                  ? `ring-2 ${opt.ring} border-transparent ${opt.bg} ${opt.color} font-semibold`
                  : `border-glass-border bg-background/60 text-muted-foreground hover:border-transparent ${opt.bg} ${opt.color}`
                }`}
            >
              <span className="text-base font-bold leading-none">{opt.short}</span>
              <span className="text-[10px] leading-tight font-medium">{opt.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

const FILA_TRABALHO_URL =
  "https://docs.google.com/spreadsheets/d/1O2Ft4Ioy3_t4bKmPQ38d56UhHY2TBHfPI6kTkNkmy-4/edit?gid=0#gid=0";
const REGISTRO_LIQUIDACAO_PENDENTE_KEY = "autoliquid_registro_liquidacao_pendente";
const IGNORAR_RETORNO_PENDENCIA_SESSION_KEY = "autoliquid_ignorar_retorno_pendencia_sessao";
const RETORNO_PENDENCIA_DISPENSADO_KEY = "autoliquid_retorno_pendencia_dispensado";
const DEFAULT_TIPOS_DOCUMENTO_LF = ["NF Serviço", "Fatura", "Boleto"];
const MUNICIPIOS_DOB001: Record<string, string> = {
  "8179": "Joinville",
  "8093": "Curitibanos",
  "8027": "Araranguá",
  "5549": "Barra do Sul",
  "8465": "Gov. Celso Ramos",
  "8327": "São José",
};

function normalizarTipoDocumentoLf(valor: string) {
  return valor.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value || 0);
}

function ConferenciaPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const documentoId = searchParams.get("id");
  const execucaoAbortControllerRef = useRef<AbortController | null>(null);
  const remessaInputRef = useRef<HTMLInputElement | null>(null);
  const registroPendenteRemotoRef = useRef("");
  const conclusaoNoticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const conclusaoEncaminhamentoCopiadoKeyRef = useRef("");
  const conclusaoEncaminhamentoCopyingRef = useRef(false);
  // Ref para proteger polling: não sobrescreve pendências enquanto um toggle está em voo
  const pendenciaToggleInFlightRef = useRef(false);
  const pendenciaTogglePendingRef = useRef<Map<string, { latest: boolean; saving: boolean }>>(new Map());
  // Ref para bloquear chamadas tardias de registrarLiquidacaoPendente após a finalização
  const liquidacaoFinalizadaRef = useRef(false);
  const [documento, setDocumento] = useState<Documento>(MOCK_DOCUMENTO);
  const [resumo, setResumo] = useState<ResumoFinanceiro>(MOCK_RESUMO_FINANCEIRO);
  const [notasFiscais, setNotasFiscais] = useState<NotaFiscal[]>(MOCK_NOTAS_FISCAIS);
  const [empenhos, setEmpenhos] = useState<Empenho[]>(MOCK_EMPENHOS);
  const [deducoes, setDeducoes] = useState<Deducao[]>(MOCK_DEDUCOES);
  const [etapas, setEtapas] = useState<EtapaExecucao[]>(MOCK_ETAPAS_EXECUCAO);
  const [dates, setDates] = useState<ProcessDates>(MOCK_PROCESS_DATES);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsSimples, setLogsSimples] = useState<string[]>([]);
  const [remessasBolsa, setRemessasBolsa] = useState<RemessaBolsa[]>([]);
  const [uploadingRemessa, setUploadingRemessa] = useState(false);
  /** Código operacional da bolsa: 01 = Outros, 03 = Pesquisa e/ou Extensão */
  const [codigoOperacional, setCodigoOperacional] = useState<"01" | "03">("01");
  const [bolsaTabAtiva, setBolsaTabAtiva] = useState<"pendencias" | "remessas" | "empenhos">("pendencias");
  const [remessaAbertaNumero, setRemessaAbertaNumero] = useState<string | null>(null);
  const [isConfiguracoesOpen, setIsConfiguracoesOpen] = useState(false);
  const [isTabelasOpen, setIsTabelasOpen] = useState(false);
  const [tabelasInitialTab, setTabelasInitialTab] = useState<TableKey>("contratos");
  const [tabelasVisibleTabs, setTabelasVisibleTabs] = useState<TableKey[] | undefined>(undefined);
  const [isFeriasOpen, setIsFeriasOpen] = useState(false);
  const [isExecutando, setIsExecutando] = useState(false);
  const [paradaSolicitada, setParadaSolicitada] = useState(false);
  const [etapaAtivaId, setEtapaAtivaId] = useState<number | null>(null);
  const [deducaoAtivaId, setDeducaoAtivaId] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const [statusMensagem, setStatusMensagem] = useState("");
  const [chromeStatus, setChromeStatus] = useState<"pronto" | "carregando" | "erro">("carregando");
  const [browserName, setBrowserName] = useState("Chrome");
  const [nomeUsuario, setNomeUsuario] = useState<string | null>(null);
  const [tiposDocumentoLf, setTiposDocumentoLf] = useState<string[]>(DEFAULT_TIPOS_DOCUMENTO_LF);
  const [pendencias, setPendencias] = useState<PendenciaDocumento[]>([]);
  const [pendenciasLocaisResolvidas, setPendenciasLocaisResolvidas] = useState<Record<string, boolean>>({});
  const [statusGeral, setStatusGeral] = useState<StatusGeralDocumento>({
    tipo: "atencao",
    titulo: "Carregando documento",
    descricao: "O resumo operacional do documento será exibido em instantes.",
  });
  const [abrindoChrome, setAbrindoChrome] = useState(false);
  const [lfPagamentoNumero, setLfPagamentoNumero] = useState("");
  const [lfDob001Numero, setLfDob001Numero] = useState("");
  const [ugrNumero, setUgrNumero] = useState("");
  const [vencimentoDocumento, setVencimentoDocumento] = useState("");
  /** Quando false, o documento opcional não tem LF/vencimento e segue como nota fiscal comum. */
  const [documentoTemLf, setDocumentoTemLf] = useState(false);
  const [requiresCentroCusto, setRequiresCentroCusto] = useState(false);
  const [usarContaPdf, setUsarContaPdf] = useState(true);
  const [contaBanco, setContaBanco] = useState("");
  const [contaAgencia, setContaAgencia] = useState("");
  const [contaConta, setContaConta] = useState("");
  const [vpd, setVpd] = useState("");
  const [datasDeducoes, setDatasDeducoes] = useState<Record<number, { apuracao: string; vencimento: string }>>({});
  const [tocouLf, setTocouLf] = useState(false);
  const [tocouUgr, setTocouUgr] = useState(false);
  const [tocouConta, setTocouConta] = useState(false);
  const [tocouFatura, setTocouFatura] = useState(false);
  const [tocouVpd, setTocouVpd] = useState(false);
  const [pendenciaToggleId, setPendenciaToggleId] = useState<string | null>(null);
  const [, setPendenciasExpanded] = useState(true);
  // ── Dialog de conclusão (NP + dificuldade) ──
  const [conclusaoAberta, setConclusaoAberta] = useState(false);
  const [conclusaoTipo, setConclusaoTipo] = useState<RegistroLiquidacaoTipoDocumento>("NP");
  const [conclusaoNumero, setConclusaoNumero] = useState("");
  const [conclusaoDificuldade, setConclusaoDificuldade] = useState<number | null>(null);
  const [conclusaoSaving, setConclusaoSaving] = useState(false);
  const [conclusaoErro, setConclusaoErro] = useState("");
  const [conclusaoNotice, setConclusaoNotice] = useState("");
  const precisaLfDob001 = deducoes.some((deducao) => deducao.siafi === "DOB001");
  const precisaUGR = requiresCentroCusto;
  const _temPendenciaVpd = pendencias.some(
    (p) => p.titulo.toLowerCase().includes("vpd não encontrado")
  );
  // Campo VPD deve ser exibido enquanto há pendência OU enquanto o usuário
  // estiver preenchendo (tocouVpd=true), mesmo que o valor já não esteja vazio.
  const precisaVpd = _temPendenciaVpd && !vpd.trim();
  const mostrarVpd = _temPendenciaVpd || tocouVpd;
  const tiposLfNormalizados = tiposDocumentoLf.map(normalizarTipoDocumentoLf).filter(Boolean);
  const temFatura = notasFiscais.some((nota) =>
    normalizarTipoDocumentoLf(nota.tipo).includes("fatura")
  );
  const tipoLfEncontrado = notasFiscais.find((nota) => {
    const tipoNota = normalizarTipoDocumentoLf(nota.tipo);
    return tiposLfNormalizados.some((tipoConfig) => tipoNota.includes(tipoConfig));
  });
  const documentoTemLfOpcional = Boolean(tipoLfEncontrado);
  const documentoComLfPagamentoAtivo = documentoTemLfOpcional && documentoTemLf;
  const documentoUsaLfComVencimento = documentoTemLfOpcional && documentoComLfPagamentoAtivo;
  const municipiosDob001 = Array.from(new Set(
    deducoes
      .filter((deducao) => deducao.siafi === "DOB001")
      .map((deducao) => {
        const codigo = String(deducao.codigo || "").trim().replace(/^0+/, "");
        return deducao.municipio || MUNICIPIOS_DOB001[codigo] || "";
      })
      .filter(Boolean)
  ));
  const labelLfDob001 = `LF da DOB001${municipiosDob001.length > 0 ? ` - ${municipiosDob001.join(", ")}` : ""}`;
  const contaPdfDisponivel = Boolean(documento.bancoPdf || documento.agenciaPdf || documento.contaPdf);
  const contaManualCompleta = Boolean(
    contaBanco.trim() && contaAgencia.trim() && contaConta.trim()
  );
  const dadosBancariosResolvidos = usarContaPdf ? contaPdfDisponivel : contaManualCompleta;
  const precisaDadosBancariosPagamento = !documentoComLfPagamentoAtivo && !dadosBancariosResolvidos;

  useEffect(() => {
    return () => {
      if (conclusaoNoticeTimerRef.current) {
        clearTimeout(conclusaoNoticeTimerRef.current);
      }
    };
  }, []);

  const aplicarPayload = (payload: DocumentoProcessado) => {
    setDocumento(payload.documento);
    setResumo(payload.resumo);
    setNotasFiscais(payload.notasFiscais);
    setEmpenhos(payload.empenhos);
    setDeducoes(payload.deducoes);
    setEtapas(payload.etapas);
    setDates(payload.dates);
    setLogs(payload.logs);
    setLogsSimples(payload.logsSimples ?? []);
    setRemessasBolsa(payload.remessasBolsa ?? []);
    // Não sobrescreve pendências se um toggle está em andamento (evita race condition)
    if (!pendenciaToggleInFlightRef.current) {
      setPendencias(payload.pendencias ?? []);
    }
    setStatusGeral(
      payload.statusGeral ?? {
        tipo: "atencao",
        titulo: "Resumo indisponível",
        descricao: "Não foi possível montar o resumo operacional deste documento.",
      }
    );
    setLfPagamentoNumero(payload.lfPagamentoNumero ?? payload.lfNumero ?? "");
    setLfDob001Numero(payload.lfDob001Numero ?? payload.lfNumero ?? "");
    setUgrNumero(payload.ugrNumero ?? "");
    setVencimentoDocumento(formatarDataComBarras(payload.vencimentoDocumento ?? ""));
    setVpd(payload.vpd ?? "");
    setRequiresCentroCusto(Boolean(payload.requiresCentroCusto));
    if (payload.documento.codigoOperacional === "01" || payload.documento.codigoOperacional === "03") {
      setCodigoOperacional(payload.documento.codigoOperacional);
    }
    setIsExecutando(Boolean(payload.isRunning));
    setParadaSolicitada(Boolean(payload.cancelRequested));
    // Só atualiza etapaAtivaId se o backend já confirmou qual etapa está rodando,
    // ou se a execução terminou. Evita flickering quando o backend ainda não
    // marcou o status como "executando" no primeiro polling após o click.
    const etapaEmExecucaoId =
      payload.etapas.find((etapa) => etapa.status === "executando")?.id ?? null;
    if (etapaEmExecucaoId !== null || !payload.isRunning) {
      setEtapaAtivaId(etapaEmExecucaoId);
    }

    const deducaoEmExecucaoId =
      payload.deducoes.find((deducao) => deducao.status === "executando")?.id ?? null;
    if (deducaoEmExecucaoId !== null || !payload.isRunning) {
      setDeducaoAtivaId(deducaoEmExecucaoId);
    }

    if (payload.isRunning) {
      const etapaEmExecucao = payload.etapas.find(
        (etapa) => etapa.status === "executando"
      );
      const deducaoEmExecucao = payload.deducoes.find(
        (deducao) => deducao.status === "executando"
      );
      setStatusMensagem(
        payload.cancelRequested
          ? "Automação pausada."
          : etapaEmExecucao
            ? `Executando ${etapaEmExecucao.nome}...`
            : deducaoEmExecucao
              ? `Executando dedução ${deducaoEmExecucao.tipo || deducaoEmExecucao.siafi}...`
            : "Execução em andamento..."
      );
    }
  };

  const registrarLiquidacaoPendente = () => {
    if (typeof window === "undefined" || !documentoId) return;
    let criadoEm = new Date().toISOString();
    let numeroProcessoAnterior = "";
    try {
      const atual = JSON.parse(window.localStorage.getItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY) || "null");
      if (atual?.documentoId === documentoId) {
        criadoEm = atual.criadoEm || criadoEm;
        numeroProcessoAnterior = atual.numeroProcesso || "";
      }
    } catch {
      // Mantém um novo registro limpo quando o conteúdo anterior está inválido.
    }
    const numeroProcesso = documento.processo && documento.processo !== "—"
      ? documento.processo
      : numeroProcessoAnterior;
    try {
      const dispensados = JSON.parse(window.localStorage.getItem(RETORNO_PENDENCIA_DISPENSADO_KEY) || "[]");
      if (Array.isArray(dispensados)) {
        window.localStorage.setItem(
          RETORNO_PENDENCIA_DISPENSADO_KEY,
          JSON.stringify(dispensados.map(String).filter((item) => item !== documentoId))
        );
      }
    } catch {
      window.localStorage.removeItem(RETORNO_PENDENCIA_DISPENSADO_KEY);
    }
    window.localStorage.setItem(
      REGISTRO_LIQUIDACAO_PENDENTE_KEY,
      JSON.stringify({
        documentoId,
        numeroProcesso,
        criadoEm,
      }),
    );
    const chaveRemota = `${documentoId}:${numeroProcesso}`;
    if (registroPendenteRemotoRef.current !== chaveRemota && !liquidacaoFinalizadaRef.current) {
      registroPendenteRemotoRef.current = chaveRemota;
      void registrarLiquidacao({
        documentoId,
        numeroProcesso,
        finalizada: false,
        servidorNome: auth.session?.nome || nomeUsuario || "",
        servidorUsername: auth.session?.username || "",
      }).catch(() => {
        registroPendenteRemotoRef.current = "";
      });
    }
  };

  const voltarParaInicio = () => {
    if (typeof window !== "undefined" && documentoId) {
      window.sessionStorage.setItem(IGNORAR_RETORNO_PENDENCIA_SESSION_KEY, documentoId);
      try {
        const dispensados = JSON.parse(window.localStorage.getItem(RETORNO_PENDENCIA_DISPENSADO_KEY) || "[]");
        const nextDispensados = Array.isArray(dispensados) ? new Set(dispensados.map(String)) : new Set<string>();
        nextDispensados.add(documentoId);
        window.localStorage.setItem(RETORNO_PENDENCIA_DISPENSADO_KEY, JSON.stringify([...nextDispensados].slice(-50)));
      } catch {
        window.localStorage.setItem(RETORNO_PENDENCIA_DISPENSADO_KEY, JSON.stringify([documentoId]));
      }
      window.localStorage.removeItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
      void descartarRegistroLiquidacaoPendente(documentoId).catch((error) => {
        console.warn("Não foi possível descartar retorno pendente.", error);
      });
    }
    router.push("/");
  };

  const abrirConclusaoProcesso = () => {
    const pendenciasNaoResolvidas = pendenciasVisiveis.filter((pendencia) => !pendencia.resolvida);
    if (pendenciasNaoResolvidas.length > 0) {
      setErro("Conclua todas as pendências antes de concluir o processo.");
      setPendenciasExpanded(true);
      return;
    }
    setErro("");
    setConclusaoNumero("");
    setConclusaoTipo("NP");
    setConclusaoDificuldade(null);
    setConclusaoErro("");
    setConclusaoNotice("");
    conclusaoEncaminhamentoCopiadoKeyRef.current = "";
    setConclusaoAberta(true);
  };

  const montarTextoEncaminhamentoConclusao = () =>
    `Para conformidade, ${conclusaoTipo} ${conclusaoNumero.trim()}.`;

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
    const copiado = document.execCommand("copy");
    document.body.removeChild(textarea);
    if (!copiado) {
      throw new Error("O navegador recusou a cópia automática.");
    }
  };

  const mostrarConclusaoNotice = (mensagem: string, durationMs = 1500) => {
    setConclusaoNotice(mensagem);
    if (conclusaoNoticeTimerRef.current) {
      clearTimeout(conclusaoNoticeTimerRef.current);
    }
    conclusaoNoticeTimerRef.current = setTimeout(() => {
      setConclusaoNotice("");
      conclusaoNoticeTimerRef.current = null;
    }, durationMs);
  };

  useEffect(() => {
    if (!conclusaoAberta || conclusaoSaving) return;
    const numero = conclusaoNumero.trim();
    if (!numero || !conclusaoDificuldade) return;

    const copyKey = `${conclusaoTipo}:${numero}:${conclusaoDificuldade}`;
    if (
      conclusaoEncaminhamentoCopiadoKeyRef.current === copyKey
      || conclusaoEncaminhamentoCopyingRef.current
    ) {
      return;
    }

    conclusaoEncaminhamentoCopyingRef.current = true;
    copiarTextoParaAreaTransferencia(montarTextoEncaminhamentoConclusao())
      .then(() => {
        conclusaoEncaminhamentoCopiadoKeyRef.current = copyKey;
        mostrarConclusaoNotice("Encaminhamento copiado", 1500);
      })
      .catch((error) => {
        console.warn("Não foi possível copiar o encaminhamento automaticamente.", error);
      })
      .finally(() => {
        conclusaoEncaminhamentoCopyingRef.current = false;
      });
  }, [
    conclusaoAberta,
    conclusaoSaving,
    conclusaoTipo,
    conclusaoNumero,
    conclusaoDificuldade,
  ]);

  const handleConcluirComRegistro = async (finalizada: boolean) => {
    if (conclusaoSaving) return;
    if (finalizada && !conclusaoNumero.trim()) {
      setConclusaoErro("Informe o número do documento.");
      return;
    }
    if (finalizada && !conclusaoDificuldade) {
      setConclusaoErro("Selecione a dificuldade do processo.");
      return;
    }
    setConclusaoErro("");
    setConclusaoSaving(true);
    const encaminhamentoKey = `${conclusaoTipo}:${conclusaoNumero.trim()}:${conclusaoDificuldade ?? ""}`;
    try {
      if (finalizada && conclusaoEncaminhamentoCopiadoKeyRef.current !== encaminhamentoKey) {
        try {
          await copiarTextoParaAreaTransferencia(montarTextoEncaminhamentoConclusao());
          conclusaoEncaminhamentoCopiadoKeyRef.current = encaminhamentoKey;
          mostrarConclusaoNotice("Encaminhamento copiado", 1500);
        } catch (error) {
          console.warn("Não foi possível copiar o encaminhamento automaticamente.", error);
        }
      }
      await registrarLiquidacao({
        documentoId: documentoId ?? "",
        numeroProcesso: documento.processo ?? "",
        finalizada,
        tipoDocumento: finalizada ? conclusaoTipo : "",
        numeroDocumento: finalizada ? conclusaoNumero.trim() : "",
        dificuldade: finalizada ? (conclusaoDificuldade ?? undefined) : undefined,
        servidorNome: auth.session?.nome || nomeUsuario || "",
        servidorUsername: auth.session?.username || "",
      });
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
      }
      liquidacaoFinalizadaRef.current = true;
      // Sinaliza para page.tsx que o registro já foi feito aqui
      if (typeof window !== "undefined") {
        window.sessionStorage.removeItem("autoliquid_vem_de_concluir");
      }
      router.push("/");
    } catch (error) {
      setConclusaoErro(error instanceof Error ? error.message : "Erro ao registrar. Tente novamente.");
    } finally {
      setConclusaoSaving(false);
    }
  };

  const handleTogglePendenciaResolvida = async (pendencia: PendenciaDocumento, resolvida: boolean) => {
    if (!documentoId) return;
    if (pendencia.id.startsWith("local-")) {
      setErro("");
      setPendenciasLocaisResolvidas((current) => ({
        ...current,
        [pendencia.id]: resolvida,
      }));
      return;
    }

    setErro("");
    pendenciaToggleInFlightRef.current = true;
    setPendencias((current) =>
      current.map((item) =>
        item.id === pendencia.id ? { ...item, resolvida } : item
      )
    );

    const pending = pendenciaTogglePendingRef.current;
    const existing = pending.get(pendencia.id);
    pending.set(pendencia.id, { latest: resolvida, saving: existing?.saving ?? false });
    if (existing?.saving) return;

    pending.set(pendencia.id, { latest: resolvida, saving: true });
    setPendenciaToggleId(pendencia.id);

    let intent = resolvida;
    while (true) {
      try {
        const payload = await atualizarPendenciaDocumento(documentoId, pendencia.id, intent);
        const currentPending = pending.get(pendencia.id);
        if (!currentPending || currentPending.latest === intent) {
          const pendenciaServidor = payload.pendencias?.find((p) => p.id === pendencia.id);
          setPendencias((current) =>
            current.map((item) =>
              item.id === pendencia.id
                ? (pendenciaServidor ?? { ...item, resolvida: intent })
                : item
            )
          );
          if (payload.statusGeral) setStatusGeral(payload.statusGeral);
          if (payload.resumo !== undefined) setResumo(payload.resumo);
          pending.delete(pendencia.id);
          break;
        }
        intent = currentPending.latest;
        pending.set(pendencia.id, { latest: intent, saving: true });
      } catch (error) {
        const currentPending = pending.get(pendencia.id);
        if (!currentPending || currentPending.latest === intent) {
          setPendencias((current) =>
            current.map((item) =>
              item.id === pendencia.id ? { ...item, resolvida: pendencia.resolvida } : item
            )
          );
          pending.delete(pendencia.id);
          setErro(error instanceof Error ? error.message : "Não foi possível atualizar a pendência agora.");
          break;
        }
        intent = currentPending.latest;
        pending.set(pendencia.id, { latest: intent, saving: true });
      }
    }

    if (pending.size === 0) {
      pendenciaToggleInFlightRef.current = false;
      setPendenciaToggleId(null);
    } else {
      setPendenciaToggleId(null);
    }
  };

  const resumirExecucao = (
    payload: DocumentoProcessado,
    mensagemSucesso: string
  ) => {
    const ultimoLog = payload.logs.at(-1)?.toLowerCase() ?? "";

    if (ultimoLog.includes("parada solicitada")) {
      return "Execução interrompida.";
    }

    if (payload.etapas.some((etapa) => etapa.status === "erro")) {
      return "Execução interrompida com erro.";
    }

    if (payload.etapas.some((etapa) => etapa.status === "divergencia")) {
      return "Execução concluída — há divergências a conferir.";
    }

    return mensagemSucesso;
  };

  useEffect(() => {
    registrarLiquidacaoPendente();
  }, [documentoId, documento.processo]);

  useEffect(() => {
    let ativo = true;
    let documentoCarregado = false;
    let recarregandoDocumento = false;

    const atualizarChrome = async () => {
      try {
        const status = await fetchBackendStatus();
        if (!ativo) return;
        setChromeStatus(status.chromeStatus);

        if (!documentoCarregado && !recarregandoDocumento && documentoId) {
          recarregandoDocumento = true;
          try {
            const [payloadResult, settingsResult] = await Promise.allSettled([
              fetchDocumentoProcessado(documentoId),
              fetchAppSettings(),
            ]);

            if (payloadResult.status === "fulfilled") {
              if (!ativo) return;
              aplicarPayload(payloadResult.value);
              documentoCarregado = true;
              setErro("");
            }

            if (settingsResult.status === "fulfilled" && ativo) {
              setBrowserName(settingsResult.value.navegador === "edge" ? "Edge" : "Chrome");
              setTiposDocumentoLf(settingsResult.value.tiposDocumentoLf ?? DEFAULT_TIPOS_DOCUMENTO_LF);
              const storedSession = await readStoredAuthSession();
              const nomeSessao = auth.session?.nome || auth.session?.username || storedSession?.nome || storedSession?.username || "";
              setNomeUsuario((current) => nomeSessao || current || settingsResult.value.nomeUsuario || "");
            }
          } finally {
            recarregandoDocumento = false;
          }
        }
      } catch (error) {
        if (!ativo) return;
        console.error("Erro ao consultar status do Chrome:", error);
        setChromeStatus("erro");
      }
    };

    const loadData = async () => {
      if (!documentoId) {
        setErro("Nenhum documento foi informado para conferência.");
        return;
      }

      const [statusResult, payloadResult, settingsResult] = await Promise.allSettled([
        fetchBackendStatus(),
        fetchDocumentoProcessado(documentoId),
        fetchAppSettings(),
      ]);

      if (statusResult.status === "fulfilled") {
        if (!ativo) return;
        setChromeStatus(statusResult.value.chromeStatus);
      } else {
        console.error("Erro ao consultar status do Chrome:", statusResult.reason);
        if (ativo) {
          setChromeStatus("erro");
        }
      }

      if (payloadResult.status === "fulfilled") {
        if (!ativo) return;
        aplicarPayload(payloadResult.value);
        documentoCarregado = true;
        setErro("");
      } else {
        console.error("Erro ao carregar documento processado:", payloadResult.reason);
        if (ativo) {
          setErro(
            payloadResult.reason instanceof Error
              ? payloadResult.reason.message
              : "Erro ao carregar os dados do documento."
          );
        }
      }

      if (settingsResult.status === "fulfilled" && ativo) {
        setBrowserName(settingsResult.value.navegador === "edge" ? "Edge" : "Chrome");
        setTiposDocumentoLf(settingsResult.value.tiposDocumentoLf ?? DEFAULT_TIPOS_DOCUMENTO_LF);
        const storedSession = await readStoredAuthSession();
        const nomeSessao = auth.session?.nome || auth.session?.username || storedSession?.nome || storedSession?.username || "";
        setNomeUsuario((current) => nomeSessao || current || settingsResult.value.nomeUsuario || "");
      }
    };

    const handleFocus = () => {
      void atualizarChrome();
    };

    const handleVisibility = () => {
      if (!document.hidden) {
        void atualizarChrome();
      }
    };

    const intervalId = window.setInterval(() => {
      void atualizarChrome();
    }, 5000);

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    loadData();

    return () => {
      ativo = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [documentoId]);

  useEffect(() => {
    setUgrNumero("");
    setLfPagamentoNumero("");
    setLfDob001Numero("");
    setVencimentoDocumento("");
    setUsarContaPdf(true);
    setContaBanco("");
    setContaAgencia("");
    setContaConta("");
    setTocouLf(false);
    setTocouUgr(false);
    setTocouConta(false);
    setTocouFatura(false);
    setDocumentoTemLf(false);
  }, [documentoId]);

  useEffect(() => {
    if (precisaUGR || precisaLfDob001 || precisaVpd || documentoComLfPagamentoAtivo || precisaDadosBancariosPagamento) {
      setPendenciasExpanded(true);
    }
  }, [precisaUGR, precisaLfDob001, precisaVpd, documentoComLfPagamentoAtivo, precisaDadosBancariosPagamento]);

  useEffect(() => {
    if (!documentoId || !isExecutando) return;

    let ativo = true;
    const intervalId = window.setInterval(async () => {
      try {
        const payload = await fetchDocumentoProcessado(documentoId);
        if (!ativo) return;
        aplicarPayload(payload);
        if (!payload.isRunning) {
          setStatusMensagem(resumirExecucao(payload, "Execução concluída."));
        }
      } catch (error) {
        if (!ativo) return;
        console.error("Erro ao atualizar andamento da execução:", error);
      }
    }, 1500);

    return () => {
      ativo = false;
      window.clearInterval(intervalId);
    };
  }, [documentoId, isExecutando]);

  const executeAll = async (
    lfPagamentoInformada = documentoComLfPagamentoAtivo ? lfPagamentoNumero : "",
    lfDob001Informada = lfDob001Numero,
    ugrInformada = ugrNumero,
    vencimentoInformado = documentoComLfPagamentoAtivo ? vencimentoDocumento : "",
    usarPdf = usarContaPdf,
    banco = contaBanco,
    agencia = contaAgencia,
    conta = contaConta,
    vpdInformado = vpd,
  ) => {
    if (!documentoId) return;
    execucaoAbortControllerRef.current?.abort();
    const controller = new AbortController();
    execucaoAbortControllerRef.current = controller;
    setIsExecutando(true);
    setParadaSolicitada(false);
    setEtapaAtivaId(null);
    setStatusMensagem("Executando automação...");
    setErro("");
    try {
      // O endpoint retorna imediatamente (background task). Não chamamos
      // aplicarPayload aqui para não sobrescrever o estado com a resposta
      // estale. O polling (useEffect abaixo) detecta a conclusão real.
      await executarTodas(documentoId, {
        signal: controller.signal,
        lfNumero: lfDob001Informada || lfPagamentoInformada,
        lfPagamentoNumero: lfPagamentoInformada,
        lfDob001Numero: lfDob001Informada,
        ugrNumero: ugrInformada,
        vencimentoDocumento: vencimentoInformado,
        usarContaPdf: usarPdf,
        contaBanco: banco,
        contaAgencia: agencia,
        contaConta: conta,
        vpd: vpdInformado,
      });
    } catch (error) {
      console.error("Erro ao executar:", error);
      if (controller.signal.aborted) {
        setStatusMensagem("Automação pausada.");
      } else {
        // Falha na própria chamada HTTP — encerra imediatamente.
        setErro(
          error instanceof Error ? error.message : "Erro ao executar automação."
        );
        setStatusMensagem("Execução interrompida.");
        setIsExecutando(false);
      }
    } finally {
      if (execucaoAbortControllerRef.current === controller) {
        execucaoAbortControllerRef.current = null;
      }
      // NÃO reseta isExecutando aqui — o polling detecta quando
      // isRunning=false no backend e chama setIsExecutando(false) via aplicarPayload.
    }
  };

  const executeEtapa = async (
    etapa: EtapaExecucao,
    lfPagamentoInformada = documentoComLfPagamentoAtivo ? lfPagamentoNumero : "",
    lfDob001Informada = lfDob001Numero,
    ugrInformada = ugrNumero,
    vencimentoInformado = documentoComLfPagamentoAtivo ? vencimentoDocumento : "",
    usarPdf = usarContaPdf,
    banco = contaBanco,
    agencia = contaAgencia,
    conta = contaConta,
    vpdInformado = vpd,
  ) => {
    if (!documentoId) return;
    execucaoAbortControllerRef.current?.abort();
    const controller = new AbortController();
    execucaoAbortControllerRef.current = controller;
    setIsExecutando(true);
    setParadaSolicitada(false);
    setEtapaAtivaId(etapa.id);
    setStatusMensagem(`Executando ${etapa.nome}...`);
    setErro("");

    try {
      // O endpoint retorna imediatamente (background task). Não chamamos
      // aplicarPayload aqui — isso sobrescreveria etapaAtivaId com null
      // antes do backend setar o status como "executando", fazendo a etapa
      // voltar a mostrar "Com erro". O polling (useEffect abaixo) cuida de
      // atualizar o estado real a cada 2,5 s e detecta a conclusão.
      await executarEtapa(documentoId, etapa.id, {
        signal: controller.signal,
        lfNumero: lfDob001Informada || lfPagamentoInformada,
        lfPagamentoNumero: lfPagamentoInformada,
        lfDob001Numero: lfDob001Informada,
        ugrNumero: ugrInformada,
        vencimentoDocumento: vencimentoInformado,
        usarContaPdf: usarPdf,
        contaBanco: banco,
        contaAgencia: agencia,
        contaConta: conta,
        vpd: vpdInformado,
      });
    } catch (error) {
      console.error("Erro ao executar etapa:", error);
      if (controller.signal.aborted) {
        setStatusMensagem("Automação pausada.");
      } else {
        // Falha na própria chamada HTTP — encerra imediatamente.
        setErro(
          error instanceof Error
            ? error.message
            : "Erro ao executar a etapa selecionada."
        );
        setStatusMensagem(`Falha na etapa ${etapa.nome}.`);
        setIsExecutando(false);
        setEtapaAtivaId(null);
      }
    } finally {
      if (execucaoAbortControllerRef.current === controller) {
        execucaoAbortControllerRef.current = null;
      }
      // NÃO reseta isExecutando / etapaAtivaId aqui — o polling detecta
      // quando isRunning=false e atualiza o estado via aplicarPayload.
    }
  };

  const validarPendenciasPreenchimento = (contexto: "todas" | "etapa", etapa?: EtapaExecucao) => {
    const faltas: string[] = [];
    let mensagemSemClique = "";

    if ((contexto === "todas" || etapa?.id === 5) && precisaUGR && !ugrNumero.trim()) {
      faltas.push("UGR");
      if (!tocouUgr) {
        mensagemSemClique = "Preencha a UGR na aba Pendências antes de continuar.";
      }
    }

    if ((contexto === "todas" || etapa?.id === 3) && precisaLfDob001 && !lfDob001Numero.trim()) {
      faltas.push("LF da dedução DOB001");
      if (!mensagemSemClique && !tocouLf) {
        mensagemSemClique = "Preencha a LF da dedução DOB001 na aba Pendências antes de continuar.";
      }
    }

    if (contexto === "todas" || etapa?.id === 4) {
      if (documentoComLfPagamentoAtivo && !lfPagamentoNumero.trim()) {
        faltas.push("LF dos Dados de Pagamento");
        if (!mensagemSemClique && !tocouLf) {
          mensagemSemClique = "Preencha a LF dos Dados de Pagamento na aba Pendências antes de executar.";
        }
      }

      if (documentoUsaLfComVencimento && !vencimentoDocumento.trim()) {
        faltas.push(temFatura ? "vencimento da fatura nos Dados de Pagamento" : "vencimento da LF dos Dados de Pagamento");
        if (!mensagemSemClique && !tocouFatura) {
          mensagemSemClique = "Revise os dados da LF de Dados de Pagamento na aba Pendências antes de executar.";
        }
      }

      if (precisaDadosBancariosPagamento) {
        faltas.push("dados bancários");
        if (!mensagemSemClique && !tocouConta) {
          mensagemSemClique = "Escolha ou preencha os dados bancários na aba Pendências antes de executar.";
        }
      }
    }

    if (faltas.length === 0) {
      return true;
    }

    setErro(mensagemSemClique || `Ainda há pendências de preenchimento: ${faltas.join(", ")}.`);
    setStatusMensagem("Preencha as lacunas destacadas na aba Pendências antes de executar.");
    return false;
  };

  const handleExecutarTudo = async () => {
    if (!validarPendenciasPreenchimento("todas")) {
      return;
    }
    await executeAll();
  };

  const handleExecutarEtapa = async (etapa: EtapaExecucao) => {
    if (!validarPendenciasPreenchimento("etapa", etapa)) {
      return;
    }
    await executeEtapa(etapa);
  };

  const handleExecutarDeducao = async (deducao: Deducao) => {
    if (!documentoId) return;
    if (deducao.siafi === "DOB001" && !lfDob001Numero.trim()) {
      setErro("Preencha a LF da dedução DOB001 na aba Pendências antes de executar esta dedução.");
      setPendenciasExpanded(true);
      return;
    }
    execucaoAbortControllerRef.current?.abort();
    const controller = new AbortController();
    execucaoAbortControllerRef.current = controller;
    setIsExecutando(true);
    setParadaSolicitada(false);
    setDeducaoAtivaId(deducao.id);
    setStatusMensagem(`Executando dedução ${deducao.tipo || deducao.siafi}...`);
    setErro("");
    try {
      const datasOverride = datasDeducoes[deducao.id];
      await executarDeducao(documentoId, deducao.id, {
        signal: controller.signal,
        lfNumero: lfDob001Numero,
        lfDob001Numero,
        ugrNumero,
        vencimentoDocumento,
        dataApuracao: datasOverride?.apuracao || "",
        dataVencimento: datasOverride?.vencimento || "",
      });
    } catch (error) {
      console.error("Erro ao executar dedução:", error);
      if (controller.signal.aborted) {
        setStatusMensagem("Automação pausada.");
      } else {
        setErro(
          error instanceof Error ? error.message : "Erro ao executar a dedução."
        );
        setStatusMensagem(`Falha na dedução ${deducao.tipo || deducao.siafi}.`);
        setIsExecutando(false);
        setDeducaoAtivaId(null);
      }
    } finally {
      if (execucaoAbortControllerRef.current === controller) {
        execucaoAbortControllerRef.current = null;
      }
    }
  };

  const handlePararExecucao = async () => {
    if (!documentoId || !isExecutando) return;

    execucaoAbortControllerRef.current?.abort();
    setIsExecutando(false);
    setParadaSolicitada(true);
    setEtapaAtivaId(null);
    setDeducaoAtivaId(null);
    setStatusMensagem("Automação pausada.");
    setErro("");

    try {
      const payload = await pararExecucao(documentoId);
      aplicarPayload(payload);
      setStatusMensagem(payload.mensagem || "Automação pausada.");
    } catch (error) {
      console.error("Erro ao solicitar parada:", error);
      setParadaSolicitada(false);
      setErro(
        error instanceof Error
          ? error.message
          : "Erro ao solicitar a interrupção da execução."
      );
    }
  };

  const handleApropriarSIAFI = async () => {
    if (!documentoId) return;
    registrarLiquidacaoPendente();
    setEtapaAtivaId(null);
    setStatusMensagem("Enviando apropriação ao SIAFI...");
    setErro("");
    try {
      const resultado = await apropriarSIAFI(documentoId);
      setLogs(resultado.logs);
      setLogsSimples([]);
      setStatusMensagem(resultado.mensagem);
    } catch (error) {
      console.error("Erro ao apropriar SIAFI:", error);
      setErro(
        error instanceof Error
          ? error.message
          : "Erro ao apropriar no SIAFI."
      );
      setStatusMensagem("Falha ao apropriar no SIAFI.");
    }
  };

  const handleRemessaBolsaInput = async (file: File | null) => {
    if (!documentoId || !file || uploadingRemessa) return;
    setUploadingRemessa(true);
    setErro("");
    try {
      const payload = await uploadRemessaBolsa(documentoId, file);
      aplicarPayload(payload);
      setStatusMensagem("Remessa de bolsa extraída e vinculada à liquidação.");
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível extrair a remessa de bolsa.");
    } finally {
      setUploadingRemessa(false);
      if (remessaInputRef.current) {
        remessaInputRef.current.value = "";
      }
    }
  };

  const handleAbrirChrome = async () => {
    setAbrindoChrome(true);
    setErro("");
    try {
      const status = await openChromeSession();
      setChromeStatus(status.chromeStatus);
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Não foi possível abrir o Chrome."
      );
      setChromeStatus("erro");
    } finally {
      setAbrindoChrome(false);
    }
  };

  const handleAbrirSiafi = async () => {
    setAbrindoChrome(true);
    setErro("");
    setStatusMensagem("");
    try {
      const result = await openSiafiIncognito();
      setChromeStatus(result.chromeStatus);
      if (result.siafiStatus === "login_required") {
        setErro("O SIAFI está aberto mas aguardando login. Faça login na janela do SIAFI e clique em Executar novamente.");
      } else if (result.siafiStatus === "tela_preta_clicado") {
        setStatusMensagem("Clicado em Siafi Operacional — aguarde o download do aplicativo iniciar.");
      } else if (result.siafiStatus === "pronto") {
        setStatusMensagem("Aba do SIAFI já estava aberta — janela trazida para frente.");
      }
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível abrir o SIAFI.");
      setChromeStatus("erro");
    } finally {
      setAbrindoChrome(false);
    }
  };

  const documentoBolsa = documento.tipoOperacional === "bolsa"
    || Boolean(documento.bolsas?.length)
    || notasFiscais.some((nota) => nota.tipo.toLowerCase().includes("bolsa"));

  const pendenciasBaseVisiveis = pendencias.filter((pendencia) => {
    const titulo = String(pendencia.titulo ?? "").toLowerCase();

    if (titulo.startsWith("etapa com erro:") || titulo.startsWith("dedução com erro:")) {
      return false;
    }

    if (titulo.includes("ugr obrigatória") && ugrNumero.trim()) {
      return false;
    }

    if (
      (titulo.includes("lf obrigatória") || titulo.includes("lf da dedução dob001"))
      && lfDob001Numero.trim()
    ) {
      return false;
    }

    if (titulo.includes("vpd não encontrado") && vpd.trim()) {
      return false;
    }

    // Oculta pendência de UGR quando o campo já está preenchido
    if (titulo.toLowerCase().includes("ugr não informada") && ugrNumero.trim()) {
      return false;
    }

    return true;
  });

  const pendenciasLocais: PendenciaDocumento[] = [];

  // Bolsa não tem deduções nem dados bancários — essas pendências não se aplicam.
  if (!documentoBolsa) {
    if (documentoUsaLfComVencimento && !vencimentoDocumento.trim()) {
      pendenciasLocais.push({
        id: "local-lf-vencimento",
        tipo: "atencao",
        titulo: "Vencimento da LF dos Dados de Pagamento não informado",
        descricao: "Como os Dados de Pagamento usarão LF, informe o vencimento antes de executar essa etapa.",
        origem: "configuracao",
        resolvida: Boolean(pendenciasLocaisResolvidas["local-lf-vencimento"]),
      });
    }

    if (precisaDadosBancariosPagamento) {
      pendenciasLocais.push({
        id: "local-banco",
        tipo: "bloqueio",
        titulo: "Dados bancários pendentes",
        descricao: usarContaPdf
          ? "Selecione uma conta válida do PDF ou troque para preenchimento manual."
          : "Preencha banco, agência e conta para concluir Dados de Pagamento.",
        origem: "configuracao",
        resolvida: Boolean(pendenciasLocaisResolvidas["local-banco"]),
      });
    }
  }

  const pendenciasVisiveis = [...pendenciasBaseVisiveis, ...pendenciasLocais];

  // Entidades federais (universidades, institutos, autarquias) nunca são optantes por Simples.
  const isFederalEntity = /federal|universidade|instituto\s+fed|autarquia/i.test(
    documento.nomeCredor ?? ""
  );
  const bolsasLiquidacao = documento.bolsas ?? [];
  const totalBolsistas = remessasBolsa.reduce((total, remessa) => total + (remessa.bolsistas?.length ?? 0), 0);
  const totalRemessas = remessasBolsa.reduce((total, remessa) => total + (remessa.totais?.valorNumerico ?? 0), 0);
  const remessasEsperadas = new Set(bolsasLiquidacao.map((bolsa) => bolsa.numeroRemessa).filter(Boolean));
  const remessasRecebidas = new Set(remessasBolsa.map((remessa) => remessa.numeroRemessa).filter(Boolean));
  const remessasPendentes = [...remessasEsperadas].filter((numero) => !remessasRecebidas.has(numero));
  const remessasPorNumero = new Map(remessasBolsa.map((remessa) => [remessa.numeroRemessa, remessa]));
  const remessasDocumentos = [
    ...bolsasLiquidacao.map((bolsa) => {
      const remessa = remessasPorNumero.get(bolsa.numeroRemessa);
      return {
        numero: bolsa.numeroRemessa,
        nome: `Remessa ${bolsa.numeroRemessa}`,
        detalhe: `Ateste ${bolsa.ateste || "—"}`,
        valor: remessa?.totais.valorNumerico ?? bolsa.valor,
        carregada: Boolean(remessa),
        remessa,
      };
    }),
    ...remessasBolsa
      .filter((remessa) => !remessasEsperadas.has(remessa.numeroRemessa))
      .map((remessa) => ({
        numero: remessa.numeroRemessa,
        nome: `Remessa ${remessa.numeroRemessa}`,
        detalhe: remessa.nomeArquivo,
        valor: remessa.totais.valorNumerico,
        carregada: true,
        remessa,
      })),
  ];

  const pendenciasAtivasVisiveis = pendenciasVisiveis.filter((pendencia) => !pendencia.resolvida);
  const bloqueiosAtivos = pendenciasAtivasVisiveis.filter((pendencia) => pendencia.tipo === "bloqueio");
  const pontosAtencao = pendenciasVisiveis.filter((pendencia) =>
    !pendencia.resolvida && ["atencao", "divergencia"].includes(pendencia.tipo)
  );

  const statusGeralVisivel: StatusGeralDocumento = isExecutando
    ? {
        tipo: "em_execucao",
        titulo: statusGeral.titulo,
        descricao: statusMensagem || statusGeral.descricao,
      }
    : bloqueiosAtivos.length > 0
      ? {
          tipo: "bloqueado",
          titulo: "Documento com bloqueios",
          descricao: `${bloqueiosAtivos.length} item(ns) exigem ação antes de seguir com segurança.`,
        }
      : pontosAtencao.length > 0
        ? {
            tipo: "atencao",
            titulo: "Documento requer conferência",
            descricao: `${pontosAtencao.length} ponto(s) merecem revisão antes da execução completa.`,
          }
        : {
            tipo: "pronto",
            titulo: "Documento pronto para seguir",
            descricao: "Nenhuma pendência ativa foi identificada neste momento.",
          };

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
        onOpenTabelas={() => {
          setTabelasInitialTab("contratos");
          setTabelasVisibleTabs(undefined);
          setIsTabelasOpen(true);
        }}
        onOpenConfiguracoes={() => setIsConfiguracoesOpen(true)}
        onOpenChrome={handleAbrirChrome}
        chromeActionDisabled={abrindoChrome}
        onOpenFilaTrabalho={() => void abrirUrl(FILA_TRABALHO_URL)}
        onOpenFerias={() => setIsFeriasOpen(true)}
        bugReportContexto={{
          processo: documento.processo,
          solPagamento: documento.solPagamento,
          fornecedor: documento.nomeCredor,
          cnpj: documento.cnpj,
          contrato: documento.contrato,
          natureza: documento.natureza,
          tipoLiquidacao: documento.tipoLiquidacao,
          optanteSimples: documento.optanteSimples,
          valorBruto: resumo.bruto,
          valorLiquido: resumo.liquido,
          etapaAtiva: etapaAtivaId !== null
            ? (etapas.find((e) => e.id === etapaAtivaId)?.nome ?? etapaAtivaId)
            : null,
          deducaoAtiva: deducaoAtivaId !== null
            ? (deducoes.find((d) => d.id === deducaoAtivaId)?.siafi ?? deducaoAtivaId)
            : null,
          deducoes: deducoes.map((d) => ({ siafi: d.siafi, tipo: d.tipo, status: d.status })),
          pendencias: pendencias.map((p) => ({ id: p.id, tipo: p.tipo, titulo: p.titulo })),
          lfPagamentoNumero: lfPagamentoNumero || null,
          lfDob001Numero: lfDob001Numero || null,
          ugrNumero: ugrNumero || null,
          vencimentoDocumento: vencimentoDocumento || null,
          contaBanco: contaBanco || null,
          contaAgencia: contaAgencia || null,
          contaConta: contaConta || null,
          vpd: vpd || null,
          isExecutando,
          chromeStatus,
          apuracao: dates.apuracao,
          vencimento: dates.vencimento,
          statusMensagem: statusMensagem || null,
        }}
        bugReportServidor={nomeUsuario ?? ""}
      />

      <main className="relative mx-auto max-w-[1600px] px-4 py-8 sm:px-6 xl:px-8">
        {erro && (
          <div className="mb-6 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {erro}
          </div>
        )}

        <div className="mb-6">
          <StatusOverview
            statusGeral={statusGeralVisivel}
            resumo={resumo}
            optanteSimples={Boolean(documento.optanteSimples)}
            hasDdf055={deducoes.some((deducao) => deducao.siafi === "DDF055")}
            apuracaoDate={dates.apuracao}
            vencimentoDate={dates.vencimento}
            onBack={voltarParaInicio}
            isFederalEntity={isFederalEntity}
            onConcluir={abrirConclusaoProcesso}
          />
        </div>

        {/* Main Grid Layout */}
        <div className="grid items-start gap-5 min-[1180px]:grid-cols-[minmax(180px,220px)_minmax(0,2.45fr)_minmax(220px,270px)]">
          {/* Left Column - Documento */}
          <div className="space-y-6">
            <DocumentoPanel documento={documento} resumo={resumo} hideOptanteSimples={isFederalEntity || documentoBolsa} />
          </div>

          {/* Center Column - Notas Fiscais */}
          <div className="min-w-0 space-y-6">
            {documentoBolsa ? (
              <div className="space-y-5">
                <div className="overflow-hidden rounded-2xl border border-glass-border/70 bg-background/65">
                  <div className="flex overflow-x-auto border-b border-glass-border">
                    {([
                      { id: "pendencias", label: `Pendências (${pendenciasVisiveis.length})` },
                      { id: "remessas", label: `Remessas (${Math.max(bolsasLiquidacao.length, remessasBolsa.length)})` },
                      { id: "empenhos", label: `Empenhos (${empenhos.length})` },
                    ] as const).map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setBolsaTabAtiva(tab.id)}
                        className={`shrink-0 border-b-2 px-5 py-3 text-sm font-medium transition-colors ${
                          bolsaTabAtiva === tab.id
                            ? "border-primary text-foreground"
                            : "border-transparent text-muted-foreground hover:bg-secondary/35 hover:text-foreground"
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  <div className="p-4">
                    {bolsaTabAtiva === "pendencias" && (
                      <div className="space-y-4">
                        <div className="rounded-2xl border border-glass-border/70 bg-background/55 px-5 py-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                            Preenchimento Operacional
                          </p>

                          <div className="mt-5 space-y-5">
                              <div className="grid gap-x-6 gap-y-5 lg:grid-cols-2">
                                <div className="space-y-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                  Centro de Custo
                                </p>
                                <div className="space-y-2">
                                  <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                    UGR
                                  </label>
                                  <Input
                                    value={ugrNumero}
                                    maxLength={6}
                                    placeholder="Ex.: 153424"
                                    onFocus={() => setTocouUgr(true)}
                                    onChange={(event) => {
                                      setTocouUgr(true);
                                      setUgrNumero(event.target.value);
                                    }}
                                  />
                                </div>
                                </div>

                                <div className="space-y-3">
                                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                  Código Operacional
                                </p>
                                <div className="grid min-h-11 grid-cols-2 overflow-hidden rounded-xl border border-glass-border bg-secondary/20 p-1">
                                  <button
                                    type="button"
                                    onClick={() => setCodigoOperacional("01")}
                                    className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                                      codigoOperacional === "01"
                                        ? "bg-background text-foreground shadow-sm"
                                        : "text-muted-foreground hover:bg-background/45 hover:text-foreground"
                                    }`}
                                  >
                                    Outros (01)
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setCodigoOperacional("03")}
                                    className={`rounded-lg px-3 py-2 text-sm font-semibold leading-snug transition-colors ${
                                      codigoOperacional === "03"
                                        ? "bg-background text-primary shadow-sm"
                                        : "text-muted-foreground hover:bg-background/45 hover:text-foreground"
                                    }`}
                                  >
                                    Pesquisa/Extensão (03)
                                  </button>
                                </div>
                                </div>
                              </div>

                              <div
                                className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-7 text-center transition-colors ${
                                  uploadingRemessa
                                    ? "border-primary/40 bg-primary/5"
                                    : "border-glass-border bg-background/60 hover:border-primary/40 hover:bg-primary/5"
                                }`}
                                onClick={() => !uploadingRemessa && remessaInputRef.current?.click()}
                                onDragOver={(e) => { e.preventDefault(); }}
                                onDrop={(e) => {
                                  e.preventDefault();
                                  const file = e.dataTransfer.files?.[0] ?? null;
                                  if (file) void handleRemessaBolsaInput(file);
                                }}
                              >
                                <input
                                  ref={remessaInputRef}
                                  type="file"
                                  accept=".pdf,application/pdf"
                                  className="hidden"
                                  onChange={(event) => void handleRemessaBolsaInput(event.target.files?.[0] ?? null)}
                                />
                                {uploadingRemessa ? (
                                  <Loader2 className="h-7 w-7 animate-spin text-primary" />
                                ) : (
                                  <Upload className="h-7 w-7 text-muted-foreground" />
                                )}
                                <p className="text-sm font-medium text-foreground">
                                  {uploadingRemessa ? "Extraindo remessa..." : "Arraste o PDF da remessa aqui"}
                                </p>
                                {!uploadingRemessa && (
                                  <p className="text-xs text-muted-foreground">ou clique para selecionar</p>
                                )}
                              </div>

                              <div className="space-y-2">
                                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                                  Remessas esperadas
                                </p>
                                <div className="space-y-1.5">
                                  {remessasDocumentos.map((doc) => (
                                    <button
                                      key={doc.numero}
                                      type="button"
                                      disabled={!doc.carregada}
                                      onClick={() => {
                                        if (!doc.carregada) return;
                                        setRemessaAbertaNumero(doc.numero);
                                        setBolsaTabAtiva("remessas");
                                      }}
                                      className={`grid w-full grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 rounded-xl border px-3 py-2.5 text-left text-sm transition-colors ${
                                        doc.carregada
                                          ? "border-glass-border bg-background/70 hover:border-primary/35 hover:bg-primary/5"
                                          : "cursor-default border-glass-border/60 bg-secondary/20 text-muted-foreground opacity-70"
                                      }`}
                                    >
                                      <span className="min-w-0">
                                        <span className={`block truncate font-semibold ${doc.carregada ? "text-foreground" : "text-muted-foreground"}`}>{doc.nome}</span>
                                        <span className="block truncate text-xs text-muted-foreground">{doc.detalhe}</span>
                                      </span>
                                      <span className={`whitespace-nowrap text-xs font-semibold tabular-nums ${doc.carregada ? "text-foreground" : "text-muted-foreground"}`}>
                                        {formatCurrency(doc.valor)}
                                      </span>
                                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                                        doc.carregada
                                          ? "bg-emerald-500/10 text-emerald-700"
                                          : "bg-secondary/60 text-muted-foreground"
                                      }`}>
                                        {doc.carregada ? "Carregada" : "Pendente"}
                                      </span>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            </div>
                        </div>

                        <PendenciasPanel
                          pendencias={pendenciasVisiveis}
                          onToggleResolvida={handleTogglePendenciaResolvida}
                          togglingPendenciaId={pendenciaToggleId}
                        />
                      </div>
                    )}

                    {bolsaTabAtiva === "remessas" && (
                      <div className="space-y-5">
                        <section className="overflow-hidden rounded-2xl border border-glass-border/70 bg-background/65">
                          <div className="border-b border-glass-border bg-secondary/25 px-5 py-4">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                              Documentos
                            </p>
                            <h2 className="mt-1 text-lg font-semibold text-foreground">
                              Remessas
                            </h2>
                          </div>

                          {remessasDocumentos.length > 0 ? (
                            <div className="divide-y divide-glass-border/60">
                              {remessasDocumentos.map((doc) => {
                                const aberto = remessaAbertaNumero === doc.numero;
                                return (
                                  <div key={doc.numero}>
                                    <button
                                      type="button"
                                      disabled={!doc.carregada}
                                      onClick={() => {
                                        if (!doc.carregada) return;
                                        setRemessaAbertaNumero(aberto ? null : doc.numero);
                                      }}
                                      className={`grid w-full gap-3 px-5 py-4 text-left transition-colors sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center ${
                                        doc.carregada
                                          ? "hover:bg-secondary/25"
                                          : "cursor-default bg-secondary/10 text-muted-foreground opacity-75"
                                      }`}
                                    >
                                      <span className="min-w-0">
                                        <span className={`block truncate text-sm font-semibold ${doc.carregada ? "text-foreground" : "text-muted-foreground"}`}>{doc.nome}</span>
                                        <span className="block truncate text-xs text-muted-foreground">{doc.detalhe}</span>
                                      </span>
                                      <span className={`whitespace-nowrap text-sm font-semibold tabular-nums ${doc.carregada ? "text-foreground" : "text-muted-foreground"}`}>
                                        {formatCurrency(doc.valor)}
                                      </span>
                                      <span className={`w-fit rounded-full px-2.5 py-1 text-xs font-semibold ${
                                        doc.carregada
                                          ? "bg-emerald-500/10 text-emerald-700"
                                          : "bg-secondary/60 text-muted-foreground"
                                      }`}>
                                        {doc.carregada ? "Carregada" : "Pendente"}
                                      </span>
                                    </button>

                                    {aberto && doc.remessa ? (
                                      <div className="border-t border-glass-border/60 bg-background/45 px-5 pb-5 pt-4">
                                        <div className="mb-3 flex flex-wrap gap-2 text-sm">
                                          <span className="inline-flex items-center gap-1.5 rounded-lg border border-glass-border bg-background px-2.5 py-1.5 font-semibold text-foreground">
                                            <Users className="h-3.5 w-3.5 text-muted-foreground" />
                                            {doc.remessa.totais.quantidade} bolsistas
                                          </span>
                                          <span className="inline-flex items-center gap-1.5 rounded-lg border border-glass-border bg-background px-2.5 py-1.5 font-semibold text-emerald-700">
                                            <Banknote className="h-3.5 w-3.5" />
                                            {formatCurrency(doc.remessa.totais.valorNumerico)}
                                          </span>
                                        </div>

                                        <div className="table-scroll-surface max-h-[420px] overflow-auto rounded-xl border border-glass-border/70">
                                          <table className="min-w-[900px] w-full text-sm">
                                            <thead className="sticky top-0 z-10 bg-muted">
                                              <tr className="border-b border-glass-border text-left text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                                                <th className="px-4 py-3">Nome</th>
                                                <th className="px-4 py-3">CPF</th>
                                                <th className="px-4 py-3">Banco</th>
                                                <th className="px-4 py-3">Agência</th>
                                                <th className="px-4 py-3">Conta</th>
                                                <th className="px-4 py-3 text-right">Valor</th>
                                                <th className="px-4 py-3">LC</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {doc.remessa.bolsistas.map((bolsista) => (
                                                <tr key={`${doc.remessa?.numeroRemessa}-${bolsista.cpf}`} className="border-b border-glass-border/60 last:border-0 odd:bg-background/35 even:bg-background/10">
                                                  <td className="max-w-[320px] truncate px-4 py-3 font-medium text-foreground">
                                                    <SimpleTooltip content={bolsista.nome} side="top">
                                                      <span className="block truncate">{bolsista.nome}</span>
                                                    </SimpleTooltip>
                                                  </td>
                                                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{bolsista.cpf}</td>
                                                  <td className="px-4 py-3">{bolsista.banco}</td>
                                                  <td className="px-4 py-3">{bolsista.agencia}</td>
                                                  <td className="px-4 py-3 font-mono text-xs">{bolsista.conta}</td>
                                                  <td className="px-4 py-3 text-right font-semibold text-foreground">{formatCurrency(bolsista.valorNumerico)}</td>
                                                  <td className="px-4 py-3 text-muted-foreground">{[bolsista.situacaoLc, bolsista.lc].filter(Boolean).join(" ") || "—"}</td>
                                                </tr>
                                              ))}
                                            </tbody>
                                          </table>
                                        </div>
                                      </div>
                                    ) : null}
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="flex h-32 items-center justify-center px-5 text-sm text-muted-foreground">
                              Nenhuma remessa prevista.
                            </div>
                          )}
                        </section>
                        {false && (
                          <>
                <section className="rounded-2xl border border-glass-border/70 bg-background/65 p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                        Documentos
                      </p>
                      <h2 className="mt-1 text-xl font-semibold text-foreground">
                        Remessas de bolsistas
                      </h2>
                    </div>
                    <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3">
                      <div className="rounded-xl border border-glass-border bg-background px-3 py-2">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Remessas</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{remessasBolsa.length}</p>
                      </div>
                      <div className="rounded-xl border border-glass-border bg-background px-3 py-2">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Bolsistas</p>
                        <p className="mt-1 text-lg font-semibold text-foreground">{totalBolsistas}</p>
                      </div>
                      <div className="rounded-xl border border-glass-border bg-background px-3 py-2">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Total</p>
                        <p className="mt-1 text-lg font-semibold text-emerald-700">{formatCurrency(totalRemessas)}</p>
                      </div>
                    </div>
                  </div>

                  {bolsasLiquidacao.length > 0 ? (
                    <div className="mt-5 rounded-xl border border-glass-border bg-secondary/20">
                      <div className="border-b border-glass-border px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                          Remessas previstas na liquidação
                        </p>
                      </div>
                      <div className="divide-y divide-glass-border/60">
                        {bolsasLiquidacao.map((bolsa) => (
                          <div key={bolsa.numeroRemessa} className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-[1fr_auto_auto] sm:items-center">
                            <div className="min-w-0">
                              <p className="font-semibold text-foreground">Remessa {bolsa.numeroRemessa}</p>
                              <p className="text-muted-foreground">Ateste {bolsa.ateste || "—"}</p>
                            </div>
                            <p className="font-semibold text-foreground">{formatCurrency(bolsa.valor)}</p>
                            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${
                              remessasRecebidas.has(bolsa.numeroRemessa)
                                ? "bg-emerald-500/10 text-emerald-700"
                                : "bg-amber-500/10 text-amber-700"
                            }`}>
                              {remessasRecebidas.has(bolsa.numeroRemessa) ? "Carregada" : "Pendente"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {/* Drop zone */}
                  <div
                    className={`mt-5 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
                      uploadingRemessa
                        ? "border-primary/40 bg-primary/5"
                        : "border-glass-border bg-background/60 hover:border-primary/40 hover:bg-primary/5"
                    }`}
                    onClick={() => !uploadingRemessa && remessaInputRef.current?.click()}
                    onDragOver={(e) => { e.preventDefault(); }}
                    onDrop={(e) => {
                      e.preventDefault();
                      const file = e.dataTransfer.files?.[0] ?? null;
                      if (file) void handleRemessaBolsaInput(file);
                    }}
                  >
                    <input
                      ref={remessaInputRef}
                      type="file"
                      accept=".pdf,application/pdf"
                      className="hidden"
                      onChange={(event) => void handleRemessaBolsaInput(event.target.files?.[0] ?? null)}
                    />
                    {uploadingRemessa ? (
                      <Loader2 className="h-7 w-7 animate-spin text-primary" />
                    ) : (
                      <Upload className="h-7 w-7 text-muted-foreground" />
                    )}
                    <p className="text-sm font-medium text-foreground">
                      {uploadingRemessa ? "Extraindo remessa..." : "Arraste o PDF da remessa aqui"}
                    </p>
                    {!uploadingRemessa && (
                      <p className="text-xs text-muted-foreground">ou clique para selecionar</p>
                    )}
                  </div>
                  {remessasPendentes.length > 0 ? (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-700">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>Remessa(s) ainda pendente(s): {remessasPendentes.join(", ")}.</span>
                    </div>
                  ) : null}
                </section>

                {remessasBolsa.length === 0 ? (
                  <div className="rounded-2xl border border-glass-border/70 bg-background/60 px-5 py-10 text-center">
                    <FileUp className="mx-auto h-8 w-8 text-muted-foreground" />
                    <p className="mt-3 text-sm font-semibold text-foreground">Nenhuma remessa carregada</p>
                    <p className="mt-1 text-sm text-muted-foreground">Anexe a remessa da bolsa para visualizar os bolsistas.</p>
                  </div>
                ) : (
                  <div className="space-y-5">
                    {remessasBolsa.map((remessa) => (
                      <section key={remessa.numeroRemessa} className="overflow-hidden rounded-2xl border border-glass-border/70 bg-background/65">
                        <div className="border-b border-glass-border bg-secondary/25 px-5 py-4">
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0">
                              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                                Remessa {remessa.numeroRemessa}
                              </p>
                              <h3 className="mt-1 text-lg font-semibold text-foreground">
                                {remessa.bolsa || "Bolsa"} {remessa.codigoBolsa ? `(${remessa.codigoBolsa})` : ""}
                              </h3>
                              <p className="mt-1 text-sm text-muted-foreground">
                                {remessa.data || "—"} · {remessa.mesAno || "—"} · {remessa.nomeArquivo}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2 text-sm">
                              <span className="inline-flex items-center gap-1.5 rounded-lg border border-glass-border bg-background px-2.5 py-1.5 font-semibold text-foreground">
                                <Users className="h-3.5 w-3.5 text-muted-foreground" />
                                {remessa.totais.quantidade} bolsistas
                              </span>
                              <span className="inline-flex items-center gap-1.5 rounded-lg border border-glass-border bg-background px-2.5 py-1.5 font-semibold text-emerald-700">
                                <Banknote className="h-3.5 w-3.5" />
                                {formatCurrency(remessa.totais.valorNumerico)}
                              </span>
                            </div>
                          </div>
                          {remessa.alertas?.length ? (
                            <div className="mt-3 space-y-2">
                              {remessa.alertas.map((alerta) => (
                                <div key={alerta} className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-700">
                                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                                  <span>{alerta}</span>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>

                        <div className="table-scroll-surface max-h-[520px] overflow-auto">
                          <table className="min-w-[980px] w-full text-sm">
                            <thead className="sticky top-0 z-10 bg-muted">
                              <tr className="border-b border-glass-border text-left text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                                <th className="px-4 py-3">Nome</th>
                                <th className="px-4 py-3">CPF</th>
                                <th className="px-4 py-3">Banco</th>
                                <th className="px-4 py-3">Agência</th>
                                <th className="px-4 py-3">Conta</th>
                                <th className="px-4 py-3 text-right">Valor</th>
                                <th className="px-4 py-3">LC</th>
                              </tr>
                            </thead>
                            <tbody>
                              {remessa.bolsistas.map((bolsista) => (
                                <tr key={`${remessa.numeroRemessa}-${bolsista.cpf}`} className="border-b border-glass-border/60 last:border-0 odd:bg-background/35 even:bg-background/10">
                                  <td className="max-w-[320px] truncate px-4 py-3 font-medium text-foreground">
                                    <SimpleTooltip content={bolsista.nome} side="top">
                                      <span className="block truncate">{bolsista.nome}</span>
                                    </SimpleTooltip>
                                  </td>
                                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{bolsista.cpf}</td>
                                  <td className="px-4 py-3">{bolsista.banco}</td>
                                  <td className="px-4 py-3">{bolsista.agencia}</td>
                                  <td className="px-4 py-3 font-mono text-xs">{bolsista.conta}</td>
                                  <td className="px-4 py-3 text-right font-semibold text-foreground">{formatCurrency(bolsista.valorNumerico)}</td>
                                  <td className="px-4 py-3 text-muted-foreground">{[bolsista.situacaoLc, bolsista.lc].filter(Boolean).join(" ") || "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </section>
                    ))}
                  </div>
                )}

                          </>
                        )}
                      </div>
                    )}

                    {bolsaTabAtiva === "empenhos" && (
                <section className="overflow-hidden rounded-2xl border border-glass-border/70 bg-background/65">
                  <div className="border-b border-glass-border bg-secondary/25 px-5 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                      Empenhos
                    </p>
                    <h2 className="mt-1 text-lg font-semibold text-foreground">
                      Documentos de orçamento
                    </h2>
                  </div>

                  {empenhos.length > 0 ? (
                    <div className="table-scroll-surface overflow-auto">
                      <table className="w-full table-fixed text-sm">
                        <colgroup>
                          <col className="w-[150px]" />
                          <col className="w-[90px]" />
                          <col className="w-[115px]" />
                          <col className="w-[64px]" />
                          <col />
                        </colgroup>
                        <thead className="bg-muted">
                          <tr className="border-b border-glass-border text-left text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                            <th className="px-3 py-3">Empenho</th>
                            <th className="px-3 py-3">Sit.</th>
                            <th className="px-3 py-3">Natureza</th>
                            <th className="px-2 py-3 text-center">Rec.</th>
                            <th className="px-3 py-3 text-right">Valor</th>
                          </tr>
                        </thead>
                        <tbody>
                          {empenhos.map((empenho) => {
                            const valorEmpenho = empenho.valor && empenho.valor > 0
                              ? empenho.valor
                              : empenhos.length === 1
                                ? resumo.bruto
                                : resumo.bruto / empenhos.length;
                            const saldoEmpenho = empenho.saldo ?? 0;
                            const totalRef = valorEmpenho + saldoEmpenho;
                            const pctUso = totalRef > 0 ? Math.min((valorEmpenho / totalRef) * 100, 100) : 0;
                            const temSaldo = totalRef > 0;

                            return (
                              <tr key={empenho.id} className="border-b border-glass-border/60 last:border-0 odd:bg-background/35 even:bg-background/10">
                                <td className="truncate px-3 py-3 font-mono text-xs font-medium text-foreground">{empenho.numero}</td>
                                <td className="truncate px-3 py-3 text-xs text-muted-foreground">{empenho.situacao}</td>
                                <td className="truncate px-3 py-3 text-xs tabular-nums text-muted-foreground">{empenho.natureza || "—"}</td>
                                <td className="px-2 py-3 text-center text-xs text-muted-foreground">{empenho.recurso}</td>
                                <td className="px-3 py-3 text-right">
                                  <div className="flex flex-col items-end gap-0.5">
                                    <span className="whitespace-nowrap text-xs font-semibold tabular-nums text-red-600">
                                      {valorEmpenho > 0 ? formatCurrency(valorEmpenho) : "—"}
                                    </span>
                                    {temSaldo && (
                                      <div className="group/bar relative w-full min-w-[60px]">
                                        <div className="h-[3px] w-full overflow-hidden rounded-full bg-emerald-500/45">
                                          <div
                                            className="h-full rounded-full bg-red-500/75 transition-all"
                                            style={{ width: `${pctUso}%` }}
                                          />
                                        </div>
                                        <div className="pointer-events-none absolute bottom-full right-0 z-10 mb-1.5 hidden whitespace-nowrap rounded-md border border-glass-border bg-background/95 px-2 py-1 text-[11px] text-muted-foreground shadow-lg group-hover/bar:block">
                                          Consumido: <span className="font-semibold text-red-600">{formatCurrency(valorEmpenho)}</span>
                                          {" · "}
                                          Remanescente: <span className="font-semibold text-emerald-700">{formatCurrency(saldoEmpenho)}</span>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="flex h-32 items-center justify-center px-5 text-sm text-muted-foreground">
                      Nenhum empenho cadastrado
                    </div>
                  )}
                </section>
                    )}
                  </div>
                </div>
              </div>
            ) : (
            <NotasFiscaisTable
              notasFiscais={notasFiscais}
              empenhos={empenhos}
              deducoes={deducoes}
              resumo={resumo}
              dates={dates}
              datasDeducoes={datasDeducoes}
              onDatasDeducaoChange={(dedId, datas) =>
                setDatasDeducoes((prev) => ({ ...prev, [dedId]: datas }))
              }
              logs={logs}
              logsSimples={logsSimples}
              pendencias={pendenciasVisiveis}
              onTogglePendenciaResolvida={handleTogglePendenciaResolvida}
              pendenciaToggleId={pendenciaToggleId}
              pendenciasExtraContent={
                <div className="rounded-2xl border border-glass-border/70 bg-background/55 px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                    Preenchimento Operacional
                  </p>

                  <div className="mt-5 divide-y divide-glass-border/40 [&>*]:pt-5 [&>*:first-child]:pt-0">

                      <div className="space-y-6">
                        {(precisaLfDob001 || mostrarVpd) && (
                          <section className="space-y-3">
                            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Dedução</p>
                            <div className="grid gap-3 lg:grid-cols-2">
                              {precisaLfDob001 && (
                                <div className="space-y-2">
                                  <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                    {labelLfDob001}
                                  </label>
                                  <Input
                                    value={lfDob001Numero}
                                    maxLength={12}
                                    placeholder="Ex.: 2026LF00123"
                                    onFocus={() => setTocouLf(true)}
                                    onChange={(event) => {
                                      setTocouLf(true);
                                      setLfDob001Numero(event.target.value);
                                    }}
                                  />
                                </div>
                              )}

                              {mostrarVpd && (
                                <div className="space-y-2">
                                  <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                    Conta VPD
                                  </label>
                                  <Input
                                    value={vpd}
                                    placeholder="Ex.: 311130200"
                                    onFocus={() => setTocouVpd(true)}
                                    onChange={(event) => {
                                      setTocouVpd(true);
                                      setVpd(event.target.value);
                                    }}
                                  />
                                </div>
                              )}
                            </div>
                          </section>
                        )}

                        <section className="space-y-3 border-t border-glass-border/40 pt-5">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Dados de Pagamento</p>
                            {documentoTemLfOpcional && (
                              <label className="flex w-fit cursor-pointer items-center gap-2 rounded-full border border-glass-border bg-background/70 px-3 py-1.5">
                                <span className="text-xs font-medium text-muted-foreground">Usar LF</span>
                                <Switch
                                  checked={documentoTemLf}
                                  onCheckedChange={(checked) => {
                                    setDocumentoTemLf(checked);
                                    if (!checked) {
                                      setLfPagamentoNumero("");
                                      setVencimentoDocumento("");
                                    }
                                  }}
                                />
                              </label>
                            )}
                          </div>

                          {documentoComLfPagamentoAtivo ? (
                            <div className="grid gap-3 lg:grid-cols-2">
                              <div className="space-y-2">
                                <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                  LF dos Dados de Pagamento
                                </label>
                                <Input
                                  value={lfPagamentoNumero}
                                  maxLength={12}
                                  placeholder="Ex.: 2026LF00123"
                                  onFocus={() => setTocouLf(true)}
                                  onChange={(event) => {
                                    setTocouLf(true);
                                    setLfPagamentoNumero(event.target.value);
                                  }}
                                />
                              </div>

                              <div className="space-y-2">
                                <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                  {temFatura ? "Vencimento da fatura" : "Vencimento da LF"}
                                </label>
                                <Input
                                  value={vencimentoDocumento}
                                  placeholder="dd/mm/aaaa"
                                  onFocus={() => setTocouFatura(true)}
                                  onChange={(event) => {
                                    setTocouFatura(true);
                                    setVencimentoDocumento(formatarDataComBarras(event.target.value));
                                  }}
                                />
                              </div>

                              <p className="text-xs text-muted-foreground lg:col-span-2">
                                Favorecido: Banco do Brasil (00.000.000/0001-91).
                              </p>
                            </div>
                          ) : (
                            <div className="space-y-3">
                              <div className="flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setTocouConta(true);
                                    setUsarContaPdf(true);
                                  }}
                                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                                    usarContaPdf
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-glass-border bg-background text-muted-foreground hover:bg-secondary/50"
                                  }`}
                                >
                                  Conta do PDF
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setTocouConta(true);
                                    setUsarContaPdf(false);
                                    if (!contaBanco && documento.bancoPdf) setContaBanco(documento.bancoPdf);
                                    if (!contaAgencia && documento.agenciaPdf) setContaAgencia(documento.agenciaPdf);
                                    if (!contaConta && documento.contaPdf) setContaConta(documento.contaPdf);
                                  }}
                                  className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                                    !usarContaPdf
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-glass-border bg-background text-muted-foreground hover:bg-secondary/50"
                                  }`}
                                >
                                  Manual
                                </button>
                              </div>

                              {usarContaPdf ? (
                                <div className="rounded-xl border border-glass-border/50 bg-secondary/10 px-3 py-3 text-sm text-muted-foreground">
                                  {contaPdfDisponivel
                                    ? [documento.bancoPdf && `Banco ${documento.bancoPdf}`, documento.agenciaPdf && `Ag. ${documento.agenciaPdf}`, documento.contaPdf && `Conta ${documento.contaPdf}`].filter(Boolean).join(" · ")
                                    : "Conta não identificada no PDF."}
                                </div>
                              ) : (
                                <div className="grid gap-3 md:grid-cols-3">
                                  <div className="space-y-2">
                                    <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                      Banco
                                    </label>
                                    <Input
                                      value={contaBanco}
                                      placeholder={documento.bancoPdf || "Ex.: 001"}
                                      onFocus={() => setTocouConta(true)}
                                      onChange={(e) => {
                                        setTocouConta(true);
                                        setContaBanco(e.target.value);
                                      }}
                                    />
                                  </div>
                                  <div className="space-y-2">
                                    <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                      Agência
                                    </label>
                                    <Input
                                      value={contaAgencia}
                                      placeholder={documento.agenciaPdf || "Ex.: 0001-9"}
                                      onFocus={() => setTocouConta(true)}
                                      onChange={(e) => {
                                        setTocouConta(true);
                                        setContaAgencia(e.target.value);
                                      }}
                                    />
                                  </div>
                                  <div className="space-y-2">
                                    <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                      Conta
                                    </label>
                                    <Input
                                      value={contaConta}
                                      placeholder={documento.contaPdf || "Ex.: 12345-6"}
                                      onFocus={() => setTocouConta(true)}
                                      onChange={(e) => {
                                        setTocouConta(true);
                                        setContaConta(e.target.value);
                                      }}
                                    />
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </section>

                        {precisaUGR && (
                          <section className="space-y-3 border-t border-glass-border/40 pt-5">
                            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Centro de Custo</p>
                            <div className="max-w-md space-y-2">
                              <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                UGR
                              </label>
                              <Input
                                value={ugrNumero}
                                maxLength={6}
                                placeholder="Ex.: 153424"
                                onFocus={() => setTocouUgr(true)}
                                onChange={(event) => {
                                  setTocouUgr(true);
                                  setUgrNumero(event.target.value);
                                }}
                              />
                            </div>
                          </section>
                        )}
                      </div>

                  </div>
                </div>
              }
              onLimparLogs={() => {
                setLogs([]);
                setLogsSimples([]);
                setStatusMensagem("Logs limpos.");
              }}
            />
            )}
          </div>

          {/* Right Column - Fila de Execução */}
          <div className="space-y-6 min-[1180px]:min-w-[270px]">
            {documentoBolsa ? (
              <section className="overflow-hidden rounded-2xl border border-glass-border/70 bg-background/65">
                {/* Header */}
                <div className="border-b border-glass-border bg-secondary/25 px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Etapas</p>
                  <h3 className="mt-1 text-base font-semibold text-foreground">Lançamento SIAFI</h3>
                </div>

                {/* Step cards */}
                <div className="space-y-2 p-4">
                  {/* Step 1: Gerar LC(s) */}
                  <div className="grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 px-3 py-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">1</div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-foreground">
                          {remessasBolsa.length > 1 ? "Gerar LCs" : "Gerar LC"}
                        </p>
                        <span className="inline-flex rounded-full border border-glass-border bg-background/70 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                          Aguardando
                        </span>
                      </div>
                      <GlassButton
                        size="sm"
                        variant="secondary"
                        className="mt-2"
                        onClick={() => void handleAbrirSiafi()}
                        disabled={abrindoChrome}
                      >
                        {abrindoChrome ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                        {abrindoChrome ? "Abrindo..." : "Executar"}
                      </GlassButton>
                    </div>
                  </div>

                  {/* Step 2: Registro no SIAFI */}
                  <div className="grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-3 rounded-xl border border-glass-border/50 bg-background/40 px-3 py-3 opacity-60">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground">2</div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-sm font-semibold text-muted-foreground">Registro no SIAFI</p>
                        <span className="inline-flex rounded-full border border-glass-border bg-background/70 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                          Aguardando
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Footer */}
                <div className="border-t border-glass-border px-4 pb-4 pt-3">
                  <GlassButton
                    variant="success"
                    size="lg"
                    className="w-full"
                    onClick={() => void handleAbrirSiafi()}
                    disabled={abrindoChrome}
                  >
                    {abrindoChrome ? <Loader2 className="h-5 w-5 animate-spin" /> : <Play className="h-5 w-5" />}
                    {abrindoChrome ? "Abrindo..." : "Executar tudo"}
                  </GlassButton>
                  <div className="mt-3 space-y-1.5 rounded-xl border border-glass-border bg-secondary/20 px-3 py-2.5 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Remessas</span>
                      <span className="font-semibold text-foreground">{remessasBolsa.length}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Bolsistas</span>
                      <span className="font-semibold text-foreground">{totalBolsistas}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Valor total</span>
                      <span className="font-semibold text-emerald-700">{formatCurrency(totalRemessas)}</span>
                    </div>
                  </div>
                </div>
              </section>
            ) : (
              <FilaExecucao
                etapas={etapas}
                deducoes={deducoes}
                apuracaoDate={dates.apuracao}
                vencimentoDate={dates.vencimento}
                isExecutando={isExecutando}
                etapaAtivaId={etapaAtivaId}
                deducaoAtivaId={deducaoAtivaId}
                paradaSolicitada={paradaSolicitada}
                statusMensagem={statusMensagem}
                onExecutarEtapa={handleExecutarEtapa}
                onExecutarDeducao={handleExecutarDeducao}
                onExecutarTudo={handleExecutarTudo}
                onApropriarSIAFI={handleApropriarSIAFI}
                onPararExecucao={handlePararExecucao}
              />
            )}
            <LogExecucaoPanel
              logs={logs}
              onLimpar={() => {
                setLogs([]);
                setLogsSimples([]);
                setStatusMensagem("Logs limpos.");
              }}
            />
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-3 rounded-2xl border border-glass-border/70 bg-background/65 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
              Fechamento
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {pendenciasAtivasVisiveis.length > 0
                ? `${pendenciasAtivasVisiveis.length} pendência(s) ainda precisam ser concluídas.`
                : "Pendências concluídas. O processo pode ser finalizado."}
            </p>
          </div>
          <GlassButton
            variant="success"
            size="lg"
            onClick={abrirConclusaoProcesso}
            disabled={isExecutando}
            className="shrink-0"
          >
            <CheckCircle2 className="h-4 w-4" />
            Concluir processo
          </GlassButton>
        </div>
      </main>

      {/* ── Dialog de conclusão: NP + dificuldade ── */}
      {conclusaoAberta && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-background/70 px-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-glass-border bg-background shadow-[0_28px_90px_-30px_rgba(15,23,42,0.3)]">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-glass-border px-5 py-4">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600">
                  <CheckCircle2 className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-foreground">Registrar conclusão</p>
                  <p className="text-xs text-muted-foreground font-mono">{documento.processo || "Processo"}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setConclusaoAberta(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="flex flex-col gap-5 px-5 py-5">
              {/* Tipo + número */}
              <div className="grid grid-cols-[110px_1fr] gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Tipo</span>
                  <select
                    value={conclusaoTipo}
                    onChange={(e) => setConclusaoTipo(e.target.value as RegistroLiquidacaoTipoDocumento)}
                    disabled={conclusaoSaving}
                    className="h-10 rounded-lg border border-glass-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary/50"
                  >
                    <option value="NP">NP</option>
                    <option value="RP">RP</option>
                    <option value="LF">LF</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Número</span>
                  <input
                    value={conclusaoNumero}
                    onChange={(e) => { setConclusaoNumero(e.target.value); setConclusaoErro(""); }}
                    disabled={conclusaoSaving}
                    placeholder="Ex.: 2026NP001234"
                    className="h-10 rounded-lg border border-glass-border bg-background px-3 text-sm text-foreground outline-none focus:border-primary/50 placeholder:text-muted-foreground/50"
                    autoFocus
                  />
                </label>
              </div>

              {/* Dificuldade */}
              <DifficultyPicker
                value={conclusaoDificuldade}
                onChange={(v) => { setConclusaoDificuldade(v); setConclusaoErro(""); }}
                disabled={conclusaoSaving}
              />

              {conclusaoErro && (
                <p className="rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {conclusaoErro}
                </p>
              )}

              {conclusaoNotice && (
                <div
                  role="status"
                  aria-live="polite"
                  className="inline-flex w-fit items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-700 shadow-sm"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {conclusaoNotice}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between gap-2 border-t border-glass-border px-5 py-4">
              <button
                type="button"
                onClick={() => void handleConcluirComRegistro(false)}
                disabled={conclusaoSaving}
                className="h-10 rounded-xl border border-glass-border bg-background px-4 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground disabled:opacity-50"
              >
                Ainda não finalizei
              </button>
              <button
                type="button"
                onClick={() => void handleConcluirComRegistro(true)}
                disabled={conclusaoSaving || !conclusaoNumero.trim() || !conclusaoDificuldade}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-600 px-5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none"
              >
                {conclusaoSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                Registrar e concluir
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfiguracoesModal
        isOpen={isConfiguracoesOpen}
        onClose={() => setIsConfiguracoesOpen(false)}
        onSaved={async (saved) => {
          try {
            const status = await fetchBackendStatus();
            setChromeStatus(status.chromeStatus);
          } catch {
            setChromeStatus("erro");
          }
          if (saved?.navegador) {
            setBrowserName(saved.navegador === "edge" ? "Edge" : "Chrome");
          }
          if (saved?.nomeUsuario !== undefined) {
            setNomeUsuario((current) => auth.session?.nome || auth.session?.username || current || saved.nomeUsuario || "");
          }
        }}
        onChromeOpened={async () => {
          try {
            const status = await fetchBackendStatus();
            setChromeStatus(status.chromeStatus);
          } catch {
            setChromeStatus("erro");
          }
        }}
      />

      <TabelasModal
        isOpen={isTabelasOpen}
        onClose={() => {
          setIsTabelasOpen(false);
          setTabelasVisibleTabs(undefined);
        }}
        initialTab={tabelasInitialTab}
        visibleTabs={tabelasVisibleTabs}
      />

      <FeriasModal
        open={isFeriasOpen}
        onClose={() => setIsFeriasOpen(false)}
      />

    </div>
  );
}

export default function ConferenciaPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
          Carregando conferência...
        </div>
      }
    >
      <ConferenciaPageContent />
    </Suspense>
  );
}
