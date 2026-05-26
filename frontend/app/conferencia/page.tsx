"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CheckCircle2, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { Header } from "@/components/header";
import { DocumentoPanel } from "@/components/documento-panel";
import { NotasFiscaisTable } from "@/components/notas-fiscais-table";
import { FilaExecucao } from "@/components/fila-execucao";
import { LogExecucaoPanel } from "@/components/log-execucao-panel";
import { StatusOverview } from "@/components/status-overview";
import { TabelasModal } from "@/components/tabelas-modal";
import { ConfiguracoesModal } from "@/components/configuracoes-modal";
import { GlassButton } from "@/components/glass-card";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  pararExecucao,
  type Documento,
  type Deducao,
  type DocumentoProcessado,
  type Empenho,
  type PendenciaDocumento,
  type ResumoFinanceiro,
  type NotaFiscal,
  type EtapaExecucao,
  type ProcessDates,
  type StatusGeralDocumento,
  type TableKey,
  executarTodas,
  executarEtapa,
  executarDeducao,
  apropriarSIAFI,
  salvarPreenchimentoDocumento,
  atualizarPendenciaDocumento,
  registrarLiquidacao,
  descartarRegistroLiquidacaoPendente,
} from "@/lib/data";
import { readStoredAuthSession } from "@/lib/auth-store";
import { useAuth } from "@/lib/auth-context";

const FILA_TRABALHO_URL =
  "https://docs.google.com/spreadsheets/d/1O2Ft4Ioy3_t4bKmPQ38d56UhHY2TBHfPI6kTkNkmy-4/edit?gid=0#gid=0";
const REGISTRO_LIQUIDACAO_PENDENTE_KEY = "autoliquid_registro_liquidacao_pendente";
const IGNORAR_RETORNO_PENDENCIA_SESSION_KEY = "autoliquid_ignorar_retorno_pendencia_sessao";
const RETORNO_PENDENCIA_DISPENSADO_KEY = "autoliquid_retorno_pendencia_dispensado";

function ConferenciaPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const documentoId = searchParams.get("id");
  const execucaoAbortControllerRef = useRef<AbortController | null>(null);
  const registroPendenteRemotoRef = useRef("");
  // Ref para proteger polling: não sobrescreve pendências enquanto um toggle está em voo
  const pendenciaToggleInFlightRef = useRef(false);
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
  const [isTabelasOpen, setIsTabelasOpen] = useState(false);
  const [tabelasInitialTab, setTabelasInitialTab] = useState<TableKey>("contratos");
  const [tabelasVisibleTabs, setTabelasVisibleTabs] = useState<TableKey[] | undefined>(undefined);
  const [isConfiguracoesOpen, setIsConfiguracoesOpen] = useState(false);
  const [isExecutando, setIsExecutando] = useState(false);
  const [paradaSolicitada, setParadaSolicitada] = useState(false);
  const [etapaAtivaId, setEtapaAtivaId] = useState<number | null>(null);
  const [deducaoAtivaId, setDeducaoAtivaId] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const [statusMensagem, setStatusMensagem] = useState("");
  const [chromeStatus, setChromeStatus] = useState<"pronto" | "carregando" | "erro">("carregando");
  const [browserName, setBrowserName] = useState("Chrome");
  const [nomeUsuario, setNomeUsuario] = useState<string | null>(null);
  const [pendencias, setPendencias] = useState<PendenciaDocumento[]>([]);
  const [statusGeral, setStatusGeral] = useState<StatusGeralDocumento>({
    tipo: "atencao",
    titulo: "Carregando documento",
    descricao: "O resumo operacional do documento será exibido em instantes.",
  });
  const [abrindoChrome, setAbrindoChrome] = useState(false);
  const [lfNumero, setLfNumero] = useState("");
  const [ugrNumero, setUgrNumero] = useState("");
  const [vencimentoDocumento, setVencimentoDocumento] = useState("");
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
  const [salvandoPendencias, setSalvandoPendencias] = useState(false);
  const [pendenciaToggleId, setPendenciaToggleId] = useState<string | null>(null);
  const [pendenciasExpanded, setPendenciasExpanded] = useState(true);
  const [conclusaoOpen, setConclusaoOpen] = useState(false);
  const [conclusaoNumeroNp, setConclusaoNumeroNp] = useState("");
  const [conclusaoDificuldade, setConclusaoDificuldade] = useState(3);
  const [conclusaoDificuldadeInteragida, setConclusaoDificuldadeInteragida] = useState(false);
  const [conclusaoSaving, setConclusaoSaving] = useState(false);
  const [conclusaoErro, setConclusaoErro] = useState("");
  const precisaLF = deducoes.some((deducao) => deducao.siafi === "DOB001");
  const precisaUGR = requiresCentroCusto;
  const _temPendenciaVpd = pendencias.some(
    (p) => p.titulo.toLowerCase().includes("vpd não encontrado")
  );
  // Campo VPD deve ser exibido enquanto há pendência OU enquanto o usuário
  // estiver preenchendo (tocouVpd=true), mesmo que o valor já não esteja vazio.
  const precisaVpd = _temPendenciaVpd && !vpd.trim();
  const mostrarVpd = _temPendenciaVpd || tocouVpd;
  const temFatura = notasFiscais.some((nota) =>
    nota.tipo.toLowerCase().includes("fatura")
  );
  const mostraBlocoLf = precisaLF || temFatura;
  const contaPdfDisponivel = Boolean(documento.bancoPdf || documento.agenciaPdf || documento.contaPdf);
  const contaManualCompleta = Boolean(
    contaBanco.trim() && contaAgencia.trim() && contaConta.trim()
  );
  const dadosBancariosResolvidos = usarContaPdf ? contaPdfDisponivel : contaManualCompleta;

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
    setLfNumero(payload.lfNumero ?? "");
    setUgrNumero(payload.ugrNumero ?? "");
    setVencimentoDocumento(payload.vencimentoDocumento ?? "");
    setVpd(payload.vpd ?? "");
    setRequiresCentroCusto(Boolean(payload.requiresCentroCusto));
    setIsExecutando(Boolean(payload.isRunning));
    setParadaSolicitada(Boolean(payload.cancelRequested));
    setEtapaAtivaId(
      payload.etapas.find((etapa) => etapa.status === "executando")?.id ?? null
    );

    if (payload.isRunning) {
      const etapaEmExecucao = payload.etapas.find(
        (etapa) => etapa.status === "executando"
      );
      setStatusMensagem(
        payload.cancelRequested
          ? "Parada solicitada. A etapa atual será concluída antes da interrupção."
          : etapaEmExecucao
            ? `Executando ${etapaEmExecucao.nome}...`
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
    setConclusaoErro("");
    setConclusaoOpen(true);
  };

  const finalizarProcesso = async () => {
    if (!documentoId || conclusaoSaving) return;
    const numeroNp = conclusaoNumeroNp.trim();
    if (!numeroNp) {
      setConclusaoErro("Informe o número da NP.");
      return;
    }
    if (!conclusaoDificuldadeInteragida) {
      setConclusaoErro("Informe o nível de dificuldade do processo.");
      return;
    }

    setConclusaoErro("");
    setConclusaoSaving(true);
    // Marca como finalizado antes da chamada para bloquear qualquer
    // void registrarLiquidacaoPendente(finalizada=false) ainda em voo.
    liquidacaoFinalizadaRef.current = true;
    try {
      await registrarLiquidacao({
        documentoId,
        numeroProcesso: documento.processo && documento.processo !== "—" ? documento.processo : "",
        finalizada: true,
        tipoDocumento: "NP",
        numeroDocumento: numeroNp,
        dificuldade: conclusaoDificuldade,
        servidorNome: auth.session?.nome || nomeUsuario || "",
        servidorUsername: auth.session?.username || "",
      });
      if (typeof window !== "undefined") {
        window.localStorage.removeItem(REGISTRO_LIQUIDACAO_PENDENTE_KEY);
        window.dispatchEvent(new CustomEvent("autoliquid:liquidacao-registrada", {
          detail: {
            documentoId,
            numeroProcesso: documento.processo,
            finalizada: true,
            tipoDocumento: "NP",
            numeroDocumento: numeroNp,
            dificuldade: conclusaoDificuldade,
          },
        }));
      }
      setConclusaoOpen(false);
      router.push("/");
    } catch (error) {
      // Permite nova tentativa se a chamada falhar
      liquidacaoFinalizadaRef.current = false;
      setConclusaoErro(error instanceof Error ? error.message : "Não foi possível concluir o processo agora.");
    } finally {
      setConclusaoSaving(false);
    }
  };

  const handleTogglePendenciaResolvida = async (pendencia: PendenciaDocumento, resolvida: boolean) => {
    if (!documentoId) return;
    // Guard: bloqueia duplo-clique e cliques enquanto outro toggle está em progresso
    if (pendenciaToggleId !== null) return;
    if (pendencia.id.startsWith("local-")) {
      setErro("Essa pendência é concluída preenchendo o campo correspondente no próprio painel.");
      setPendenciasExpanded(true);
      return;
    }

    setErro("");
    setPendenciaToggleId(pendencia.id);
    pendenciaToggleInFlightRef.current = true;
    // Deep copy para rollback correto em caso de erro
    const pendenciasAntes = pendencias.map((p) => ({ ...p }));
    // Atualização otimista: reflete visualmente antes da resposta do servidor
    setPendencias((current) =>
      current.map((item) =>
        item.id === pendencia.id ? { ...item, resolvida } : item
      )
    );
    try {
      const payload = await atualizarPendenciaDocumento(documentoId, pendencia.id, resolvida);
      // Atualização cirúrgica: aplica só a pendência alterada do servidor,
      // sem sobrescrever todo o estado (evita race condition com o polling).
      const pendenciaServidor = payload.pendencias?.find((p) => p.id === pendencia.id);
      setPendencias((current) =>
        current.map((item) =>
          item.id === pendencia.id
            ? (pendenciaServidor ?? { ...item, resolvida })
            : item
        )
      );
      // Atualiza statusGeral e resumo que podem ter mudado com a resolução da pendência
      if (payload.statusGeral) setStatusGeral(payload.statusGeral);
      if (payload.resumo !== undefined) setResumo(payload.resumo);
    } catch (error) {
      setPendencias(pendenciasAntes);
      setErro(error instanceof Error ? error.message : "Não foi possível atualizar a pendência agora.");
    } finally {
      pendenciaToggleInFlightRef.current = false;
      setPendenciaToggleId(null);
    }
  };

  const resumirExecucao = (
    payload: DocumentoProcessado,
    mensagemSucesso: string
  ) => {
    const ultimoLog = payload.logs.at(-1)?.toLowerCase() ?? "";

    if (ultimoLog.includes("parada solicitada")) {
      return "Execução interrompida após a etapa atual.";
    }

    if (payload.etapas.some((etapa) => etapa.status === "erro")) {
      return "Execução interrompida com erro.";
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
    setLfNumero("");
    setVencimentoDocumento("");
    setUsarContaPdf(true);
    setContaBanco("");
    setContaAgencia("");
    setContaConta("");
    setTocouLf(false);
    setTocouUgr(false);
    setTocouConta(false);
    setTocouFatura(false);
  }, [documentoId]);

  useEffect(() => {
    if (precisaUGR || precisaLF || precisaVpd || temFatura || !dadosBancariosResolvidos) {
      setPendenciasExpanded(true);
    }
  }, [precisaUGR, precisaLF, precisaVpd, temFatura, dadosBancariosResolvidos]);

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
    }, 2500);

    return () => {
      ativo = false;
      window.clearInterval(intervalId);
    };
  }, [documentoId, isExecutando]);

  const executeAll = async (
    lfInformada = lfNumero,
    ugrInformada = ugrNumero,
    vencimentoInformado = vencimentoDocumento,
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
        lfNumero: lfInformada,
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
        setStatusMensagem("Parada solicitada. Atualizando andamento da automação...");
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
    lfInformada = lfNumero,
    ugrInformada = ugrNumero,
    vencimentoInformado = vencimentoDocumento,
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
        lfNumero: lfInformada,
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
        setStatusMensagem("Parada solicitada. Atualizando andamento da automação...");
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

    if ((contexto === "todas" || etapa?.id === 3) && precisaLF && !lfNumero.trim()) {
      faltas.push("LF");
      if (!mensagemSemClique && !tocouLf) {
        mensagemSemClique = "Preencha a LF na aba Pendências antes de continuar.";
      }
    }

    if (contexto === "todas" || etapa?.id === 4) {
      if (temFatura && !vencimentoDocumento.trim()) {
        faltas.push("vencimento da fatura");
        if (!mensagemSemClique && !tocouFatura) {
          mensagemSemClique = "Revise os dados de fatura na aba Pendências antes de executar.";
        }
      }

      if (!dadosBancariosResolvidos) {
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
      const payload = await executarDeducao(documentoId, deducao.id, {
        signal: controller.signal,
        lfNumero,
        ugrNumero,
        vencimentoDocumento,
        dataApuracao: datasOverride?.apuracao || "",
        dataVencimento: datasOverride?.vencimento || "",
      });
      aplicarPayload(payload);
      setStatusMensagem(`Dedução ${deducao.tipo || deducao.siafi} concluída.`);
    } catch (error) {
      console.error("Erro ao executar dedução:", error);
      if (controller.signal.aborted) {
        setStatusMensagem("Parada solicitada.");
      } else {
        setErro(
          error instanceof Error ? error.message : "Erro ao executar a dedução."
        );
        setStatusMensagem(`Falha na dedução ${deducao.tipo || deducao.siafi}.`);
      }
    } finally {
      if (execucaoAbortControllerRef.current === controller) {
        execucaoAbortControllerRef.current = null;
      }
      if (!controller.signal.aborted) {
        setIsExecutando(false);
        setDeducaoAtivaId(null);
      }
    }
  };

  const handlePararExecucao = async () => {
    if (!documentoId || !isExecutando) return;

    try {
      const payload = await pararExecucao(documentoId);
      execucaoAbortControllerRef.current?.abort();
      aplicarPayload(payload);
      setErro("");
      setStatusMensagem(payload.mensagem);
    } catch (error) {
      console.error("Erro ao solicitar parada:", error);
      setErro(
        error instanceof Error
          ? error.message
          : "Erro ao solicitar a interrupção da execução."
      );
    }
  };

  const handleSalvarPreenchimento = async () => {
    if (!documentoId) return;
    setSalvandoPendencias(true);
    setErro("");

    try {
      const payload = await salvarPreenchimentoDocumento(documentoId, {
        lfNumero,
        ugrNumero,
        vencimentoDocumento,
        usarContaPdf,
        contaBanco,
        contaAgencia,
        contaConta,
        vpd,
      });
      setPendencias(payload.pendencias ?? []);
      setPendenciasExpanded(false);
      setStatusMensagem("Preenchimento operacional salvo.");
    } catch (error) {
      console.error("Erro ao salvar preenchimento:", error);
      setPendenciasExpanded(true);
      setErro(
        error instanceof Error
          ? error.message
          : "Não foi possível salvar os campos de pendência."
      );
    } finally {
      setSalvandoPendencias(false);
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

  const pendenciasBaseVisiveis = pendencias.filter((pendencia) => {
    const titulo = String(pendencia.titulo ?? "").toLowerCase();

    if (titulo.includes("ugr obrigatória") && ugrNumero.trim()) {
      return false;
    }

    if (titulo.includes("lf obrigatória") && lfNumero.trim()) {
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

  if (precisaLF && !lfNumero.trim()) {
    pendenciasLocais.push({
      id: "local-lf",
      tipo: "bloqueio",
      titulo: "LF pendente",
      descricao: "Preencha a LF para permitir a execução das deduções que dependem dela.",
      origem: "configuracao",
    });
  }

  if (temFatura && !vencimentoDocumento.trim()) {
    pendenciasLocais.push({
      id: "local-fatura-vencimento",
      tipo: "atencao",
      titulo: "Vencimento da fatura não informado",
      descricao: "Se este documento usa vencimento específico de fatura, informe-o antes de executar os dados de pagamento.",
      origem: "configuracao",
    });
  }

  if (!dadosBancariosResolvidos) {
    pendenciasLocais.push({
      id: "local-banco",
      tipo: "bloqueio",
      titulo: "Dados bancários pendentes",
      descricao: usarContaPdf
        ? "Selecione uma conta válida do PDF ou troque para preenchimento manual."
        : "Preencha banco, agência e conta para concluir Dados de Pagamento.",
      origem: "configuracao",
    });
  }

  const pendenciasVisiveis = [...pendenciasBaseVisiveis, ...pendenciasLocais];

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
          />
        </div>

        {/* Main Grid Layout */}
        <div className="grid items-start gap-5 min-[1180px]:grid-cols-[minmax(180px,220px)_minmax(0,2.45fr)_minmax(220px,270px)]">
          {/* Left Column - Documento */}
          <div className="space-y-6">
            <DocumentoPanel documento={documento} resumo={resumo} />
          </div>

          {/* Center Column - Notas Fiscais */}
          <div className="min-w-0 space-y-6">
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
                  {/* ── Header ── */}
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">
                      Preenchimento Operacional
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setPendenciasExpanded((current) => !current)}
                        className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-glass-border bg-background/75 text-muted-foreground transition-colors hover:text-foreground"
                        aria-label={pendenciasExpanded ? "Recolher preenchimento operacional" : "Expandir preenchimento operacional"}
                      >
                        {pendenciasExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                      <GlassButton
                        variant="secondary"
                        size="sm"
                        onClick={() => void handleSalvarPreenchimento()}
                        disabled={salvandoPendencias || isExecutando}
                        className="shrink-0"
                      >
                        {salvandoPendencias ? "Salvando..." : "Salvar"}
                      </GlassButton>
                    </div>
                  </div>

                  {pendenciasExpanded ? (
                    <div className="mt-5 divide-y divide-glass-border/40 [&>*]:pt-5 [&>*:first-child]:pt-0">

                      {/* ── Grid de campos pequenos (LF, UGR, VPD) ── */}
                      {(mostraBlocoLf || precisaUGR || mostrarVpd) && (
                        <div className="grid gap-x-6 gap-y-5 lg:grid-cols-2">

                          {mostraBlocoLf && (
                            <div className="space-y-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">LF e Fatura</p>
                              <div className="space-y-2">
                                <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                  LF
                                </label>
                                <Input
                                  value={lfNumero}
                                  maxLength={12}
                                  placeholder="Ex.: 2026LF00123"
                                  onFocus={() => setTocouLf(true)}
                                  onChange={(event) => {
                                    setTocouLf(true);
                                    setLfNumero(event.target.value);
                                  }}
                                />
                              </div>
                              {temFatura && (
                                <div className="space-y-2">
                                  <label className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
                                    Vencimento da fatura
                                  </label>
                                  <Input
                                    value={vencimentoDocumento}
                                    placeholder="dd/mm/aaaa"
                                    onFocus={() => setTocouFatura(true)}
                                    onChange={(event) => {
                                      setTocouFatura(true);
                                      setVencimentoDocumento(event.target.value);
                                    }}
                                  />
                                </div>
                              )}
                            </div>
                          )}

                          {precisaUGR && (
                            <div className="space-y-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Centro de Custo</p>
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
                          )}

                          {mostrarVpd && (
                            <div className="space-y-3">
                              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">VPD</p>
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
                            </div>
                          )}

                        </div>
                      )}

                      {/* ── Dados Bancários ── */}
                      <div className="space-y-3">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Dados Bancários</p>
                          <div className="flex gap-2">
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
                              Preencher manualmente
                            </button>
                          </div>
                        </div>

                        {usarContaPdf ? (
                          <div className="rounded-xl border border-glass-border/50 bg-secondary/10 px-3 py-3 text-sm text-muted-foreground">
                            {contaPdfDisponivel
                              ? [documento.bancoPdf && `Banco ${documento.bancoPdf}`, documento.agenciaPdf && `Ag. ${documento.agenciaPdf}`, documento.contaPdf && `Conta ${documento.contaPdf}`].filter(Boolean).join(" · ")
                              : "Nenhuma conta foi identificada no PDF. Troque para preenchimento manual."}
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

                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-muted-foreground">
                      As definições operacionais estão recolhidas. Expanda se quiser revisar ou alterar os campos antes da execução.
                    </p>
                  )}
                </div>
              }
              onLimparLogs={() => {
                setLogs([]);
                setLogsSimples([]);
                setStatusMensagem("Logs limpos.");
              }}
            />
          </div>

          {/* Right Column - Fila de Execução */}
          <div className="space-y-6 min-[1180px]:min-w-[270px]">
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
            disabled={isExecutando || conclusaoSaving}
            className="shrink-0"
          >
            <CheckCircle2 className="h-4 w-4" />
            Concluir processo
          </GlassButton>
        </div>
      </main>

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

      <Dialog open={conclusaoOpen} onOpenChange={(open) => {
        if (!conclusaoSaving) {
          setConclusaoOpen(open);
          setConclusaoErro("");
        }
      }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Concluir processo</DialogTitle>
            <DialogDescription>
              Registre a NP e a dificuldade para fechar a liquidação deste processo.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5">
            <label className="space-y-1.5">
              <span className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
                Número da NP
              </span>
              <Input
                value={conclusaoNumeroNp}
                onChange={(event) => setConclusaoNumeroNp(event.target.value)}
                placeholder="Ex.: 2026NP000123"
                disabled={conclusaoSaving}
              />
            </label>

            <div className="rounded-2xl border border-glass-border bg-muted/20 px-4 py-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Dificuldade
                </span>
                <span className="rounded-full border border-glass-border bg-background px-3 py-1 text-sm font-semibold text-foreground">
                  {conclusaoDificuldade}/5
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={5}
                step={1}
                value={conclusaoDificuldade}
                onChange={(event) => {
                  setConclusaoDificuldade(Number(event.target.value));
                  setConclusaoDificuldadeInteragida(true);
                }}
                disabled={conclusaoSaving}
                className="h-8 w-full accent-primary"
                aria-label="Dificuldade do processo"
              />
              <div className="mt-1 flex justify-between text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                <span>1</span>
                <span>5</span>
              </div>
            </div>
          </div>

          {conclusaoErro ? (
            <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {conclusaoErro}
            </div>
          ) : null}

          <DialogFooter>
            <GlassButton
              variant="ghost"
              onClick={() => setConclusaoOpen(false)}
              disabled={conclusaoSaving}
            >
              Cancelar
            </GlassButton>
            <GlassButton
              variant="success"
              onClick={() => void finalizarProcesso()}
              disabled={conclusaoSaving}
            >
              {conclusaoSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              Salvar conclusão
            </GlassButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
