const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
const DEFAULT_API_TIMEOUT_MS = 10000
const SAVE_PREENCHIMENTO_TIMEOUT_MS = 30000
const EXECUTION_API_TIMEOUT_MS = 5 * 60 * 1000
const PDF_PROCESS_TIMEOUT_MS = 2 * 60 * 1000
const DEFAULT_API_STARTUP_TIMEOUT_MS = 60000
const DEFAULT_API_STARTUP_RETRY_MS = 1000
export const AUTO_LIQUID_REPO =
  process.env.NEXT_PUBLIC_AUTO_LIQUID_REPO ?? "diegodr-sudo/AutoLiquid"
export const AUTO_LIQUID_REPO_URL = `https://github.com/${AUTO_LIQUID_REPO}`

export type ChromeStatus = "pronto" | "carregando" | "erro"

export interface ProcessDates {
  apuracao: string
  vencimento: string
}

export interface Documento {
  cnpj: string
  nomeCredor?: string
  processo: string
  solPagamento: string
  convenio: string
  natureza: string
  ateste: string
  contrato: string
  codigoIG: string
  tipoLiquidacao: string
  tipoOperacional?: "comprasnet" | "bolsa" | string
  bolsas?: BolsaLiquidacao[]
  optanteSimples?: boolean
  alertas?: string[]
  bancoPdf?: string
  agenciaPdf?: string
  contaPdf?: string
}

export interface BolsaLiquidacao {
  numeroRemessa: string
  emissao: string
  ateste: string
  valor: number
}

export interface BolsistaRemessa {
  nome: string
  cpf: string
  banco: string
  agencia: string
  conta: string
  valor: string
  valorNumerico: number
  situacaoLc: string
  lc: string
}

export interface RemessaBolsaTotais {
  quantidade: number
  valor: string
  valorNumerico: number
  aceitosQuantidade: number
  aceitosValor: string
  rejeitadosQuantidade: number
  rejeitadosValor: string
  canceladosQuantidade: number
  canceladosValor: string
  pendentesQuantidade: number
  pendentesValor: string
}

export interface RemessaBolsa {
  numeroRemessa: string
  bolsa: string
  codigoBolsa: string
  mesAno: string
  data: string
  solicitacaoPagamento: string
  processo: string
  nomeArquivo: string
  bolsistas: BolsistaRemessa[]
  totais: RemessaBolsaTotais
  alertas?: string[]
}

export interface ResumoFinanceiro {
  bruto: number
  deducoes: number
  liquido: number
}

export interface NotaFiscal {
  id: number
  tipo: string
  nota: string
  emissao: string
  ateste: string
  valor: number
}

export interface Empenho {
  id: number
  numero: string
  situacao: string
  recurso: string
  natureza?: string
  valor?: number
  saldo?: number
}

export interface NotaFiscalVinculada {
  id: number
  nota: string
  valor: number
}

export interface Deducao {
  id: number
  tipo: string
  codigo: string
  siafi: string
  baseCalculo: number
  valor: number
  status: "aguardando" | "executando" | "concluido" | "erro"
  datasCalculadas?: { apuracao: string; vencimento: string }
  notasFiscaisVinculadas?: NotaFiscalVinculada[]
}

export interface EtapaExecucao {
  id: number
  nome: string
  status: "aguardando" | "executando" | "concluido" | "erro"
  icone: string
}

export interface PendenciaDocumento {
  id: string
  tipo: "bloqueio" | "divergencia" | "atencao"
  titulo: string
  descricao: string
  origem?: "pdf" | "portal" | "configuracao" | "automacao"
  resolvida?: boolean
}

export interface StatusGeralDocumento {
  tipo: "pronto" | "atencao" | "bloqueado" | "em_execucao"
  titulo: string
  descricao: string
}

export type TableKey =
  | "contratos"
  | "vpd"
  | "vpd-especiais"
  | "uorg"
  | "nat-rendimento"
  | "fontes-recurso"
  | "datas-impostos"

export interface TableColumn {
  key: string
  label: string
  editable: boolean
}

export type TableRow = Record<string, string>

export interface TableDataset {
  key: TableKey
  label: string
  description: string
  searchPlaceholder: string
  columns: TableColumn[]
  rows: TableRow[]
  totalRows: number
  fixedRows: boolean
}

export interface AppSettings {
  chromePorta: number
  navegador: "chrome" | "edge"
  fecharAbaFila: boolean
  perguntarLimparMes: boolean
  temaWeb: "light" | "dark" | "system"
  nivelLog: "simples" | "desenvolvedor"
  tursoDatabaseUrl: string
  tursoAuthToken: string
  nomeUsuario: string
  nfServicoAlertaDiasUteis: number
  rocketChatUrl: string
  rocketChatUserId: string
  rocketChatAuthToken: string
  rocketChatContar: "tudo" | "mencoes"
}

export interface RocketChatNotifications {
  configured: boolean
  unread: number
  mentions: number
  count: number
  rooms: Array<{
    id: string
    name: string
    type: string
    unread: number
    mentions: number
  }>
  message?: string
}

export interface DocumentoProcessado {
  id: string
  lfNumero: string
  ugrNumero: string
  vencimentoDocumento: string
  usarContaPdf?: boolean
  contaBanco?: string
  contaAgencia?: string
  contaConta?: string
  vpd?: string
  requiresCentroCusto: boolean
  dates: ProcessDates
  documento: Documento
  resumo: ResumoFinanceiro
  notasFiscais: NotaFiscal[]
  empenhos: Empenho[]
  deducoes: Deducao[]
  etapas: EtapaExecucao[]
  pendencias: PendenciaDocumento[]
  statusGeral: StatusGeralDocumento
  remessasBolsa?: RemessaBolsa[]
  logs: string[]
  logsSimples: string[]
  isRunning: boolean
  cancelRequested: boolean
}

export interface StopExecutionResponse extends DocumentoProcessado {
  success: boolean
  mensagem: string
}

export interface BackendStatus {
  chromeStatus: ChromeStatus
  chromePorta: number
}

export type BackendStartupPhase =
  | "booting-ui"
  | "starting-api"
  | "restoring-data"
  | "ready"
  | "error"

export interface BackendStartupProgress {
  phase: BackendStartupPhase
  title: string
  detail: string
  progress: number
  attempt: number
  elapsedMs: number
}

export interface OpenChromeResponse {
  success: boolean
  chromeStatus: ChromeStatus
  chromePorta: number
  url: string
  mensagem: string
  /** Status específico do SIAFI retornado pelo endpoint /api/siafi/abrir */
  siafiStatus?: "pronto" | "login_required" | "abrindo" | "tela_preta_clicado"
}

export interface OpenSolarProcessResponse {
  success: boolean
  chromeStatus: ChromeStatus
  chromePorta: number
  processo: string
  chaveProcesso?: string
  url?: string
  mensagem: string
}

export interface DashboardProcessoRecente {
  numeroProcesso: string
  fornecedor?: string
  bruto?: number
  dataExecucao?: string | null
  status?: "aguardando" | "concluido" | string
}

export interface DashboardInfo {
  habilitado: boolean
  periodo: string
  valorBruto: number
  quantidadeProcessos: number
  ultimosProcessos: DashboardProcessoRecente[]
}

export interface FilaProcessosInfo {
  total: number
  columns: string[]
  rows: Record<string, string | number | null>[]
  updatedAt?: string | null
  source?: string
  erro?: string
}

export interface SaveFilaResponsavelPayload {
  numeroProcesso: string
  solPagamento: string
  responsavel: string
}

export interface SaveFilaConclusaoPayload {
  numeroProcesso: string
  solPagamento: string
  concluido: boolean
}

export type QueueServerMode = "ativo" | "metade" | "fora"

export interface QueueServerConfig {
  id: string
  nome: string
  modo: QueueServerMode
}

export type AlertaServicoAcaoVencimento =
  | "IGNORAR"
  | "DIA_FIXO_MES_SEGUINTE"
  | "DATA_PERSONALIZADA"

export interface AlertaServicoRule {
  id: string
  active: boolean
  tipoDocumento: string
  cnpj: string
  setor: string
  acaoVencimento: AlertaServicoAcaoVencimento
  valorAcao: string
}

export interface AlertaServicoConfig {
  diasUteisPadrao: number
  regras: AlertaServicoRule[]
  source?: string
}

export interface FilaSetoresHistoricoResponse {
  setores: string[]
  source?: string
  errors?: string[]
}

export type MesVencimentoDeducao = "atual" | "seguinte" | "usuario"
export type ApuracaoDeducao = "emissao_mais_antiga" | "usuario"
export type AjusteDiaNaoUtilDeducao = "antecipar" | "prorrogar" | "manter"

export interface RegraDataDeducao {
  id: string
  nome: string
  codigos: string[]
  siafi: "DDF050" | "DDF055" | "DDR001" | "DOB001" | string
  diaVencimento: number | null
  mesVencimento: MesVencimentoDeducao
  apuracao: ApuracaoDeducao
  pagamento: "igual_vencimento"
  ajusteDiaNaoUtil: AjusteDiaNaoUtilDeducao
  precisaLf: boolean
  observacao: string
}

export interface RegrasDatasDeducoesConfig {
  versao: number
  regras: RegraDataDeducao[]
  source?: string
}

export interface SimulacaoRegraDataDeducao {
  regraId: string
  dataEmissao: string
  apuracao: string
  vencimento: string
  pagamento: string
  observacao: string
}

export interface FilaAlerta {
  id: number
  mensagem: string
  autor: string
  criadoEm?: string | null
}

export interface SaveFilaAlertaPayload {
  numeroProcesso: string
  solPagamento: string
  mensagem: string
}

export type AuthRole = "user" | "moderator"

export interface AuthSession {
  token: string
  username: string
  nome?: string
  role: AuthRole
  authSource?: "turso" | "local"
  authWarning?: string
}

export interface AuthUsuario {
  id: number
  nome: string
  username: string
  role: AuthRole
  senha: string
}

export interface AuthDiagnostico {
  versao?: string
  configLocalExiste: boolean
  configEmbutidaExiste: boolean
  tursoUrlPresente: boolean
  tursoUrlTipo?: string
  tursoHost?: string
  tursoTokenPresente: boolean
  tursoTokenPareceJwt: boolean
  tursoTokenTamanho: number
  envTursoUrlPresente?: boolean
  envTursoTokenPresente?: boolean
  consultaTursoOk: boolean
  erroTipo?: string
  erroResumo?: string
}

export type RegistroLiquidacaoTipoDocumento = "NP" | "RP" | "LF"

export interface RegistroLiquidacaoPayload {
  documentoId: string
  numeroProcesso: string
  finalizada: boolean
  tipoDocumento?: RegistroLiquidacaoTipoDocumento | ""
  numeroDocumento?: string
  dificuldade?: number
  servidorNome?: string
  servidorUsername?: string
}

export interface RegistroLiquidacaoPendente {
  documentoId: string
  numeroProcesso: string
  criadoEm?: string
}

export const MOCK_PROCESS_DATES: ProcessDates = {
  apuracao: "",
  vencimento: "",
}

export const MOCK_DOCUMENTO: Documento = {
  cnpj: "—",
  processo: "—",
  solPagamento: "—",
  convenio: "—",
  natureza: "—",
  ateste: "—",
  contrato: "—",
  codigoIG: "—",
  tipoLiquidacao: "Aguardando processamento",
  optanteSimples: false,
  alertas: [],
}

export const MOCK_RESUMO_FINANCEIRO: ResumoFinanceiro = {
  bruto: 0,
  deducoes: 0,
  liquido: 0,
}

export const MOCK_NOTAS_FISCAIS: NotaFiscal[] = []
export const MOCK_EMPENHOS: Empenho[] = []
export const MOCK_DEDUCOES: Deducao[] = []

export const MOCK_ETAPAS_EXECUCAO: EtapaExecucao[] = [
  { id: 1, nome: "Dados Básicos", status: "aguardando", icone: "FileText" },
  { id: 2, nome: "Principal com Orçamento", status: "aguardando", icone: "DollarSign" },
  { id: 3, nome: "Dedução", status: "aguardando", icone: "MinusCircle" },
  { id: 4, nome: "Dados de Pagamento", status: "aguardando", icone: "CreditCard" },
  { id: 5, nome: "Centro de Custo", status: "aguardando", icone: "Building" },
]

interface ApiFetchOptions {
  timeoutMs?: number
  signal?: AbortSignal
}

export const delay = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms)
  })

function getNetworkErrorMessage(
  path: string,
  error: unknown,
  abortedByCaller = false
): string {
  if (abortedByCaller) {
    return "A requisição foi interrompida antes da conclusão."
  }

  if (error instanceof DOMException && error.name === "AbortError") {
    return `A API não respondeu a tempo em ${API_BASE_URL}${path}. Verifique se o backend interno/web terminou de iniciar.`
  }

  if (error instanceof TypeError) {
    return `Não foi possível conectar à API em ${API_BASE_URL}. Aguarde alguns segundos; se persistir, reinicie o backend interno ou o backend web.`
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return `Falha ao acessar ${API_BASE_URL}${path}.`
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  options: ApiFetchOptions = {}
): Promise<T> {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? DEFAULT_API_TIMEOUT_MS
  let abortedByCaller = false
  let removeAbortListener: (() => void) | undefined

  if (options.signal) {
    if (options.signal.aborted) {
      abortedByCaller = true
      controller.abort()
    } else {
      const handleAbort = () => {
        abortedByCaller = true
        controller.abort()
      }
      options.signal.addEventListener("abort", handleAbort, { once: true })
      removeAbortListener = () =>
        options.signal?.removeEventListener("abort", handleAbort)
    }
  }

  const timeoutId =
    timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : undefined

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
    })

    if (!response.ok) {
      let message = `Erro HTTP ${response.status}`
      try {
        const data = await response.json()
        message = data.detail || data.mensagem || message
      } catch {
        // sem corpo JSON
      }
      throw new Error(message)
    }

    try {
      return (await response.json()) as T
    } catch {
      throw new Error("A API respondeu sem um JSON válido.")
    }
  } catch (error) {
    throw new Error(getNetworkErrorMessage(path, error, abortedByCaller), {
      cause: error,
    })
  } finally {
    if (timeoutId !== undefined) {
      clearTimeout(timeoutId)
    }
    removeAbortListener?.()
  }
}

export async function fetchBackendStatus(): Promise<BackendStatus> {
  try {
    return await apiFetch<BackendStatus>("/api/status", undefined, { timeoutMs: 2000 })
  } catch (error) {
    const message = error instanceof Error ? error.message : ""
    if (message.includes("/api/status") && message.includes("não respondeu a tempo")) {
      return {
        chromeStatus: "erro",
        chromePorta: 9222,
      }
    }
    throw error
  }
}

export async function fetchBackendHealth(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/health", undefined, { timeoutMs: 4000 })
}

export async function loginAutoLiquid(
  username: string,
  password: string
): Promise<AuthSession> {
  return apiFetch<AuthSession>("/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  }, {
    timeoutMs: 15000,
  })
}

export async function fetchAuthDiagnostico(): Promise<AuthDiagnostico> {
  return apiFetch<AuthDiagnostico>("/api/auth/diagnostico", undefined, {
    timeoutMs: 10000,
  })
}

export async function fetchAuthUsuarios(): Promise<AuthUsuario[]> {
  const data = await apiFetch<{ usuarios: AuthUsuario[] }>("/api/auth/usuarios", undefined, {
    timeoutMs: 15000,
  })
  return data.usuarios ?? []
}

export async function updateAuthUsuario(
  username: string,
  payload: { role?: AuthRole; senha?: string | null }
): Promise<AuthUsuario> {
  const data = await apiFetch<{ success: boolean; usuario: AuthUsuario }>("/api/auth/usuarios", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, ...payload }),
  }, {
    timeoutMs: 15000,
  })
  return data.usuario
}

export async function fetchDashboard(
  periodo: "dia" | "semana" | "mes" | "este-mes" = "semana",
  servidorNome?: string,
  limite = 5
): Promise<DashboardInfo> {
  const params = new URLSearchParams({ periodo })
  if (servidorNome) params.set("servidor_nome", servidorNome)
  params.set("limite", String(Math.max(1, Math.min(100, Math.trunc(Number(limite) || 5)))))
  return apiFetch<DashboardInfo>(`/api/dashboard?${params.toString()}`)
}

export async function fetchFilaProcessos(
  refresh = false
): Promise<FilaProcessosInfo> {
  const params = new URLSearchParams()
  if (refresh) params.set("refresh", "true")
  const suffix = params.toString() ? `?${params.toString()}` : ""
  try {
    return await apiFetch<FilaProcessosInfo>(`/api/fila-processos${suffix}`, undefined, {
      timeoutMs: refresh ? 120000 : 30000,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : ""
    if (message.includes("404") || message.toLowerCase().includes("not found")) {
      throw new Error(
        "O backend em execução ainda não possui o endpoint da fila. Reinicie a API para carregar a nova rota /api/fila-processos.",
        { cause: error }
      )
    }
    throw error
  }
}

export async function saveFilaResponsavel(
  payload: SaveFilaResponsavelPayload
): Promise<{ success: boolean; responsavel: string; alteradoPor: string; alteradoEm?: string | null }> {
  return apiFetch<{ success: boolean; responsavel: string; alteradoPor: string; alteradoEm?: string | null }>("/api/fila-processos/responsavel", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  })
}

export async function saveFilaAlerta(
  payload: SaveFilaAlertaPayload
): Promise<{ success: boolean; alerta: FilaAlerta | null }> {
  return apiFetch<{ success: boolean; alerta: FilaAlerta | null }>("/api/fila-processos/alertas", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  })
}

export async function deleteFilaAlerta(
  alertaId: number,
  contexto: {
    numeroProcesso?: string
    solPagamento?: string
    mensagem?: string
  } = {}
): Promise<{ success: boolean; alertaId: number }> {
  const params = new URLSearchParams()
  if (contexto.numeroProcesso) params.set("numero_processo", contexto.numeroProcesso)
  if (contexto.solPagamento) params.set("sol_pagamento", contexto.solPagamento)
  if (contexto.mensagem) params.set("mensagem", contexto.mensagem)
  const suffix = params.toString() ? `?${params.toString()}` : ""
  return apiFetch<{ success: boolean; alertaId: number }>(`/api/fila-processos/alertas/${alertaId}${suffix}`, {
    method: "DELETE",
  })
}

export async function saveFilaConclusao(
  payload: SaveFilaConclusaoPayload
): Promise<{ success: boolean; concluido: boolean; concluidoPor?: string; concluidoEm?: string | null }> {
  return apiFetch<{ success: boolean; concluido: boolean; concluidoPor?: string; concluidoEm?: string | null }>("/api/fila-processos/conclusao", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  })
}

export async function openSolarProcess(
  numeroProcesso: string
): Promise<OpenSolarProcessResponse> {
  return apiFetch<OpenSolarProcessResponse>("/api/solar/processo/abrir", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ numeroProcesso }),
  }, {
    timeoutMs: 150000,
  })
}

export async function fetchQueueServersConfig(): Promise<{ servidores: QueueServerConfig[]; source?: string }> {
  return apiFetch<{ servidores: QueueServerConfig[]; source?: string }>("/api/fila-processos/servidores-sorteio", undefined, {
    timeoutMs: 6000,
  })
}

export async function saveQueueServersConfig(
  servidores: QueueServerConfig[]
): Promise<{ success: boolean; servidores: QueueServerConfig[] }> {
  return apiFetch<{ success: boolean; servidores: QueueServerConfig[] }>("/api/fila-processos/servidores-sorteio", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ servidores }),
  }, {
    timeoutMs: 10000,
  })
}

export async function fetchAlertaServicoConfig(): Promise<AlertaServicoConfig> {
  return apiFetch<AlertaServicoConfig>("/api/fila-processos/alerta-servico-regras", undefined, {
    timeoutMs: 10000,
  })
}

export async function fetchFilaSetoresHistorico(): Promise<FilaSetoresHistoricoResponse> {
  return apiFetch<FilaSetoresHistoricoResponse>("/api/fila-processos/setores-historico", undefined, {
    timeoutMs: 10000,
  })
}

export async function saveAlertaServicoConfig(
  config: AlertaServicoConfig
): Promise<{ success: boolean; config: AlertaServicoConfig }> {
  return apiFetch<{ success: boolean; config: AlertaServicoConfig }>("/api/fila-processos/alerta-servico-regras", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(config),
  }, {
    timeoutMs: 15000,
  })
}

export async function fetchRegrasDatasDeducoes(): Promise<RegrasDatasDeducoesConfig> {
  return apiFetch<RegrasDatasDeducoesConfig>("/api/deducoes/regras-datas", undefined, {
    timeoutMs: 10000,
  })
}

export async function saveRegrasDatasDeducoes(
  config: RegrasDatasDeducoesConfig
): Promise<{ success: boolean; config: RegrasDatasDeducoesConfig }> {
  return apiFetch<{ success: boolean; config: RegrasDatasDeducoesConfig }>("/api/deducoes/regras-datas", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(config),
  }, {
    timeoutMs: 15000,
  })
}

export async function simularRegraDataDeducao(
  payload: { regraId: string; dataEmissao: string }
): Promise<SimulacaoRegraDataDeducao> {
  return apiFetch<SimulacaoRegraDataDeducao>("/api/deducoes/regras-datas/simular", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }, {
    timeoutMs: 10000,
  })
}

export function createFilaProcessosEventSource(): EventSource {
  return new EventSource(`${API_BASE_URL}/api/fila-processos/stream`)
}

export async function waitForBackendReady(
  {
    timeoutMs = DEFAULT_API_STARTUP_TIMEOUT_MS,
    retryDelayMs = DEFAULT_API_STARTUP_RETRY_MS,
    onProgress,
  }: {
    timeoutMs?: number
    retryDelayMs?: number
    onProgress?: (progress: BackendStartupProgress) => void
  } = {}
): Promise<BackendStatus> {
  const deadline = Date.now() + timeoutMs
  const startedAt = Date.now()
  let lastError: unknown
  let attempt = 0

  onProgress?.({
    phase: "starting-api",
    title: "Abrindo o AutoLiquid",
    detail: "Preparando os serviços locais para iniciar a automação.",
    progress: 18,
    attempt,
    elapsedMs: 0,
  })

  while (Date.now() <= deadline) {
    attempt += 1
    const elapsedMs = Date.now() - startedAt
    const progress = Math.min(
      82,
      22 + Math.round((elapsedMs / Math.max(timeoutMs, 1)) * 54)
    )

    onProgress?.({
      phase: "starting-api",
      title: "Conectando os serviços",
      detail: "Aguardando os serviços locais ficarem prontos para liberar a tela inicial.",
      progress,
      attempt,
      elapsedMs,
    })

    try {
      await fetchBackendHealth()
      let status: BackendStatus
      try {
        status = await fetchBackendStatus()
      } catch {
        status = {
          chromeStatus: "erro",
          chromePorta: 9222,
          }
      }
      onProgress?.({
        phase: "starting-api",
        title: "Serviços conectados",
        detail: "Tudo certo. A interface principal já pode ser preparada.",
        progress: 86,
        attempt,
        elapsedMs: Date.now() - startedAt,
      })
      return status
    } catch (error) {
      lastError = error
      if (Date.now() + retryDelayMs > deadline) {
        break
      }
      await delay(retryDelayMs)
    }
  }

  if (lastError instanceof Error) {
    throw lastError
  }

  throw new Error(
    `A API não ficou disponível em ${API_BASE_URL} dentro de ${Math.round(
      timeoutMs / 1000
    )} segundos.`
  )
}

export async function openChromeSession(): Promise<OpenChromeResponse> {
  return apiFetch<OpenChromeResponse>("/api/chrome/abrir", {
    method: "POST",
  })
}

export async function openSiafiIncognito(): Promise<OpenChromeResponse> {
  return apiFetch<OpenChromeResponse>("/api/siafi/abrir", {
    method: "POST",
  })
}

export async function fetchDatasGlobais(): Promise<ProcessDates> {
  return apiFetch<ProcessDates>("/api/datas-globais", undefined, { timeoutMs: 20000 })
}

export async function saveDatasGlobais(
  dates: ProcessDates
): Promise<ProcessDates> {
  return apiFetch<ProcessDates>("/api/datas-globais", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(dates),
  }, {
    timeoutMs: 15000,
  })
}

export async function fetchSimplesBatch(
  cnpjs: string[]
): Promise<Record<string, boolean | null>> {
  if (cnpjs.length === 0) return {}
  try {
    const data = await apiFetch<{ resultado: Record<string, boolean | null> }>(
      "/api/cnpj/simples-batch",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cnpjs }),
      },
      { timeoutMs: 75000 }
    )
    return data.resultado ?? {}
  } catch {
    return {}
  }
}

export async function fetchProcessDates(): Promise<ProcessDates> {
  return apiFetch<ProcessDates>("/api/process-dates")
}

export async function saveProcessDates(
  dates: ProcessDates
): Promise<ProcessDates> {
  return apiFetch<ProcessDates>("/api/process-dates", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(dates),
  })
}

export async function fetchDocumentoProcessado(
  id: string
): Promise<DocumentoProcessado> {
  return apiFetch<DocumentoProcessado>(`/api/documentos/${id}`)
}

export async function fetchTabela(
  tableKey: TableKey,
  search?: string
): Promise<TableDataset> {
  const query = search ? `?search=${encodeURIComponent(search)}` : ""
  return apiFetch<TableDataset>(`/api/tabelas/${tableKey}${query}`)
}

export async function saveTabela(
  tableKey: TableKey,
  rows: TableRow[]
): Promise<TableDataset> {
  return apiFetch<TableDataset>(`/api/tabelas/${tableKey}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ rows }),
  })
}

export interface HistoricoDashboardData {
  habilitado: boolean
  total: number
  totalValor: number
  porServidor: { nome: string; count: number; valor: number }[]
  porEmpresa: { nome: string; cnpj: string; count: number; valor: number }[]
  porContrato: { contrato: string; count: number; valor: number }[]
  porMes: { mes: string; count: number; valor: number }[]
}

export async function fetchDashboardHistorico(filters: {
  empresa?: string
  contrato?: string
  servidor?: string
  periodo?: string
}): Promise<HistoricoDashboardData> {
  const params = new URLSearchParams()
  if (filters.empresa)  params.set("empresa",   filters.empresa)
  if (filters.contrato) params.set("contrato",  filters.contrato)
  if (filters.servidor) params.set("servidor",  filters.servidor)
  if (filters.periodo)  params.set("periodo",   filters.periodo)
  return apiFetch<HistoricoDashboardData>(`/api/dashboard/historico?${params.toString()}`)
}

/**
 * Dado uma lista de números de contrato (SARF), retorna o IC (IG) correspondente
 * de cada um a partir da tabela de contratos cadastrada.
 * Contratos não encontrados terão valor null no mapa resultante.
 */
export async function fetchContratosIcLookup(
  sarfs: string[]
): Promise<Record<string, string | null>> {
  if (sarfs.length === 0) return {}
  try {
    const data = await apiFetch<{ resultado: Record<string, string | null> }>(
      "/api/contratos/lookup-ic",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sarfs }),
      }
    )
    return data.resultado ?? {}
  } catch {
    return {}
  }
}

// ── Ausências / Servidores Config ─────────────────────────────────────────────

export interface AusenciaRemota {
  id: string
  servidor: string
  tipo: "ferias" | "afastamento" | "licenca"
  inicio: string // YYYY-MM-DD
  fim: string    // YYYY-MM-DD
  obs?: string | null
}

export interface ServidorConfigRemoto {
  nome: string
  nomeCompleto?: string
  cor: string
}

export async function fetchAusencias(): Promise<AusenciaRemota[]> {
  const data = await apiFetch<{ ausencias: AusenciaRemota[] }>("/api/ausencias")
  return data.ausencias ?? []
}

export async function criarAusencia(ausencia: AusenciaRemota): Promise<AusenciaRemota> {
  return apiFetch<AusenciaRemota>("/api/ausencias", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ausencia),
  })
}

export async function deletarAusencia(id: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/ausencias/${encodeURIComponent(id)}`, {
    method: "DELETE",
  })
}

export async function fetchServidoresConfig(): Promise<ServidorConfigRemoto[]> {
  const data = await apiFetch<{ servidores: ServidorConfigRemoto[] }>("/api/servidores-config")
  return data.servidores ?? []
}

export async function upsertServidorConfig(nome: string, cor: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/servidores-config/${encodeURIComponent(nome)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cor }),
  })
}

export async function deletarServidorConfig(nome: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(`/api/servidores-config/${encodeURIComponent(nome)}`, {
    method: "DELETE",
  })
}

export async function fetchAppSettings(): Promise<AppSettings> {
  return apiFetch<AppSettings>("/api/configuracoes")
}

export async function fetchRocketChatNotifications(): Promise<RocketChatNotifications> {
  return apiFetch<RocketChatNotifications>("/api/rocketchat/notificacoes", undefined, {
    timeoutMs: 6000,
  })
}

export async function testTursoConnection(): Promise<{
  configured: boolean
  ok: boolean
  durationMs?: number
  rowsRead?: number
  rowsWritten?: number
  mensagem?: string
}> {
  return apiFetch("/api/turso/testar", {
    method: "POST",
  }, {
    timeoutMs: 15000,
  })
}

export async function migrateTursoData(): Promise<{
  ok: boolean
  fila: number
  servidores: number
  ausencias: number
  historico?: {
    processos?: number
    execucoes?: number
    empenhos?: number
    notas?: number
    deducoes?: number
    pendencias?: number
  }
  datasGlobais?: boolean
  tabelas: Array<{ chave: string; linhas: number }>
  avisos: string[]
}> {
  return apiFetch("/api/turso/migrar", {
    method: "POST",
  }, {
    timeoutMs: 120000,
  })
}

export async function saveAppSettings(
  settings: AppSettings
): Promise<AppSettings> {
  return apiFetch<AppSettings>("/api/configuracoes", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(settings),
  })
}

export async function recarregarModulos(): Promise<{
  recarregados: string[]
  erros: Record<string, string>
  mensagem: string
}> {
  return apiFetch("/api/recarregar", { method: "POST" })
}

export async function uploadPDF(
  file: File,
  dates: ProcessDates
): Promise<{ success: boolean; documentoId?: string; mensagem?: string }> {
  const formData = new FormData()
  formData.append("file", file)
  formData.append("apuracao", dates.apuracao)
  formData.append("vencimento", dates.vencimento)

  return apiFetch<{ success: boolean; documentoId?: string; mensagem?: string }>(
    "/api/processar",
    {
      method: "POST",
      body: formData,
    },
    {
      timeoutMs: PDF_PROCESS_TIMEOUT_MS,
    }
  )
}

export async function uploadRemessaBolsa(
  documentoId: string,
  file: File
): Promise<DocumentoProcessado> {
  const formData = new FormData()
  formData.append("file", file)

  return apiFetch<DocumentoProcessado>(
    `/api/documentos/${encodeURIComponent(documentoId)}/remessas-bolsa`,
    {
      method: "POST",
      body: formData,
    },
    {
      timeoutMs: PDF_PROCESS_TIMEOUT_MS,
    }
  )
}

export async function executarTodas(
  documentoId: string,
  options: {
    signal?: AbortSignal
    lfNumero?: string
    ugrNumero?: string
    vencimentoDocumento?: string
    usarContaPdf?: boolean
    contaBanco?: string
    contaAgencia?: string
    contaConta?: string
    vpd?: string
  } = {}
): Promise<DocumentoProcessado> {
  return apiFetch<DocumentoProcessado>(
    `/api/documentos/${documentoId}/executar-todas`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        lfNumero: options.lfNumero ?? "",
        ugrNumero: options.ugrNumero ?? "",
        vencimentoDocumento: options.vencimentoDocumento ?? "",
        usarContaPdf: options.usarContaPdf ?? true,
        contaBanco: options.contaBanco ?? "",
        contaAgencia: options.contaAgencia ?? "",
        contaConta: options.contaConta ?? "",
        vpd: options.vpd ?? "",
      }),
    },
    {
      timeoutMs: EXECUTION_API_TIMEOUT_MS,
      signal: options.signal,
    }
  )
}

export async function executarEtapa(
  documentoId: string,
  etapaId: number,
  options: {
    signal?: AbortSignal
    lfNumero?: string
    ugrNumero?: string
    vencimentoDocumento?: string
    usarContaPdf?: boolean
    contaBanco?: string
    contaAgencia?: string
    contaConta?: string
    vpd?: string
  } = {}
): Promise<DocumentoProcessado> {
  return apiFetch<DocumentoProcessado>(
    `/api/documentos/${documentoId}/executar-etapa/${etapaId}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        lfNumero: options.lfNumero ?? "",
        ugrNumero: options.ugrNumero ?? "",
        vencimentoDocumento: options.vencimentoDocumento ?? "",
        usarContaPdf: options.usarContaPdf ?? true,
        contaBanco: options.contaBanco ?? "",
        contaAgencia: options.contaAgencia ?? "",
        contaConta: options.contaConta ?? "",
        vpd: options.vpd ?? "",
      }),
    },
    {
      timeoutMs: EXECUTION_API_TIMEOUT_MS,
      signal: options.signal,
    }
  )
}

export async function apropriarSIAFI(
  documentoId: string,
  options: { signal?: AbortSignal } = {}
): Promise<{ success: boolean; mensagem: string; logs: string[] }> {
  return apiFetch<{ success: boolean; mensagem: string; logs: string[] }>(
    `/api/documentos/${documentoId}/apropriar-siafi`,
    {
      method: "POST",
    },
    {
      timeoutMs: EXECUTION_API_TIMEOUT_MS,
      signal: options.signal,
    }
  )
}

export async function executarDeducao(
  documentoId: string,
  dedId: number,
  options: {
    signal?: AbortSignal
    lfNumero?: string
    ugrNumero?: string
    vencimentoDocumento?: string
    dataApuracao?: string
    dataVencimento?: string
  } = {}
): Promise<DocumentoProcessado> {
  return apiFetch<DocumentoProcessado>(
    `/api/documentos/${documentoId}/executar-deducao/${dedId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lfNumero: options.lfNumero ?? "",
        ugrNumero: options.ugrNumero ?? "",
        vencimentoDocumento: options.vencimentoDocumento ?? "",
        usarContaPdf: true,
        contaBanco: "",
        contaAgencia: "",
        contaConta: "",
        dataApuracao: options.dataApuracao ?? "",
        dataVencimento: options.dataVencimento ?? "",
      }),
    },
    {
      timeoutMs: EXECUTION_API_TIMEOUT_MS,
      signal: options.signal,
    }
  )
}

export async function salvarPreenchimentoDocumento(
  documentoId: string,
  options: {
    lfNumero?: string
    ugrNumero?: string
    vencimentoDocumento?: string
    usarContaPdf?: boolean
    contaBanco?: string
    contaAgencia?: string
    contaConta?: string
    vpd?: string
  } = {}
): Promise<DocumentoProcessado> {
  return apiFetch<DocumentoProcessado>(
    `/api/documentos/${documentoId}/salvar-preenchimento`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lfNumero: options.lfNumero ?? "",
        ugrNumero: options.ugrNumero ?? "",
        vencimentoDocumento: options.vencimentoDocumento ?? "",
        usarContaPdf: options.usarContaPdf ?? true,
        contaBanco: options.contaBanco ?? "",
        contaAgencia: options.contaAgencia ?? "",
        contaConta: options.contaConta ?? "",
        vpd: options.vpd ?? "",
      }),
    },
    { timeoutMs: SAVE_PREENCHIMENTO_TIMEOUT_MS }
  )
}

export async function atualizarPendenciaDocumento(
  documentoId: string,
  pendenciaId: string,
  resolvida = true
): Promise<DocumentoProcessado> {
  return apiFetch<DocumentoProcessado>(
    `/api/documentos/${documentoId}/pendencias/${pendenciaId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolvida }),
    },
    { timeoutMs: SAVE_PREENCHIMENTO_TIMEOUT_MS }
  )
}

export async function pararExecucao(
  documentoId: string
): Promise<StopExecutionResponse> {
  return apiFetch<StopExecutionResponse>(
    `/api/documentos/${documentoId}/parar-execucao`,
    {
      method: "POST",
    }
  )
}

export async function registrarLiquidacao(
  payload: RegistroLiquidacaoPayload
): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>("/api/registros-liquidacao", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, {
    timeoutMs: 15000,
  })
}

export async function fetchRegistroLiquidacaoPendente(options: {
  servidorNome?: string
  servidorUsername?: string
} = {}): Promise<RegistroLiquidacaoPendente | null> {
  const params = new URLSearchParams()
  if (options.servidorNome) params.set("servidor_nome", options.servidorNome)
  if (options.servidorUsername) params.set("servidor_username", options.servidorUsername)
  const suffix = params.toString() ? `?${params.toString()}` : ""
  const data = await apiFetch<{ pendente: RegistroLiquidacaoPendente | null }>(
    `/api/registros-liquidacao/pendente${suffix}`,
    undefined,
    { timeoutMs: 15000 }
  )
  return data.pendente
}

export async function descartarRegistroLiquidacaoPendente(
  documentoId: string
): Promise<{ success: boolean }> {
  return apiFetch<{ success: boolean }>(
    `/api/registros-liquidacao/pendente/${encodeURIComponent(documentoId)}`,
    { method: "DELETE" },
    { timeoutMs: 15000 }
  )
}

// ── Versão / Atualização ──────────────────────────────────────────────────

export interface VersaoInfo {
  versao_atual: string
  versao_nova: string
  url_download: string
  tem_atualizacao: boolean
  erro?: string
}

export interface AtualizacaoTauriInfo {
  suportado: boolean
  temAtualizacao: boolean
  instalada: boolean
  versaoAtual?: string
  versaoNova?: string
  mensagem: string
}

export type AtualizacaoTauriEtapa =
  | "verificando"
  | "disponivel"
  | "baixando"
  | "instalando"
  | "reiniciando"
  | "atualizado"

export interface AtualizacaoTauriProgresso {
  etapa: AtualizacaoTauriEtapa
  percentual?: number
  baixadoBytes?: number
  totalBytes?: number
  versaoAtual?: string
  versaoNova?: string
  mensagem: string
}

export type AtualizacaoTauriProgressoCallback = (
  progresso: AtualizacaoTauriProgresso
) => void

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window
}

export function isDevRuntime(): boolean {
  return typeof process !== "undefined" && process.env.NODE_ENV !== "production"
}

export async function obterVersao(): Promise<{ versao: string }> {
  return apiFetch<{ versao: string }>("/versao")
}

async function obterVersaoAppInstalado(): Promise<string | undefined> {
  if (!isTauriRuntime()) return undefined
  try {
    const { getVersion } = await import("@tauri-apps/api/app")
    return await getVersion()
  } catch {
    return undefined
  }
}

export async function verificarAtualizacao(): Promise<VersaoInfo> {
  return apiFetch<VersaoInfo>("/versao/verificar", {}, { timeoutMs: 8000 })
}

/**
 * Só verifica se há atualização disponível, sem baixar nem instalar.
 * Usado no startup para mostrar o banner sem interromper o usuário.
 */
export async function checarAtualizacaoTauri(): Promise<AtualizacaoTauriInfo> {
  if (!isTauriRuntime()) {
    return { suportado: false, temAtualizacao: false, instalada: false, mensagem: "" }
  }
  try {
    const [{ check }, versaoAtual] = await Promise.all([
      import("@tauri-apps/plugin-updater"),
      obterVersaoAppInstalado(),
    ])
    const update = await check({ timeout: 30_000 })
    if (!update) {
      return {
        suportado: true,
        temAtualizacao: false,
        instalada: false,
        versaoAtual,
        mensagem: versaoAtual
          ? `Você está usando a versão mais recente (v${versaoAtual}).`
          : "Você está usando a versão mais recente.",
      }
    }
    return {
      suportado: true,
      temAtualizacao: true,
      instalada: false,
      versaoAtual: update.currentVersion || versaoAtual,
      versaoNova: update.version,
      mensagem: `Nova versão disponível: ${update.version}`,
    }
  } catch {
    return { suportado: true, temAtualizacao: false, instalada: false, mensagem: "" }
  }
}

/**
 * Baixa, instala e relança o app. Usado apenas quando o usuário clica
 * "Verificar e instalar" nas Configurações.
 */
export async function instalarAtualizacaoTauri(
  onProgresso?: AtualizacaoTauriProgressoCallback
): Promise<AtualizacaoTauriInfo> {
  if (!isTauriRuntime()) {
    return {
      suportado: false,
      temAtualizacao: false,
      instalada: false,
      mensagem: "Atualização automática disponível apenas no aplicativo instalado.",
    }
  }

  onProgresso?.({
    etapa: "verificando",
    percentual: 8,
    mensagem: "Verificando se há uma nova versão disponível.",
  })

  const [{ check }, { relaunch }, versaoApp] = await Promise.all([
    import("@tauri-apps/plugin-updater"),
    import("@tauri-apps/plugin-process"),
    obterVersaoAppInstalado(),
  ])

  const update = await check({ timeout: 30_000 })
  if (!update) {
    onProgresso?.({
      etapa: "atualizado",
      percentual: 100,
      versaoAtual: versaoApp,
      mensagem: versaoApp
        ? `Você está usando a versão mais recente (v${versaoApp}).`
        : "Você está usando a versão mais recente.",
    })
    return {
      suportado: true,
      temAtualizacao: false,
      instalada: false,
      versaoAtual: versaoApp,
      mensagem: versaoApp
        ? `Você está usando a versão mais recente (v${versaoApp}).`
        : "Você está usando a versão mais recente.",
    }
  }

  const versaoAtual = update.currentVersion || versaoApp
  let totalBytes = 0
  let baixadoBytes = 0

  onProgresso?.({
    etapa: "disponivel",
    percentual: 12,
    versaoAtual,
    versaoNova: update.version,
    mensagem: `Nova versão v${update.version} encontrada. Iniciando download.`,
  })

  await update.downloadAndInstall((evento) => {
    if (evento.event === "Started") {
      totalBytes = evento.data.contentLength ?? 0
      baixadoBytes = 0
      onProgresso?.({
        etapa: "baixando",
        percentual: totalBytes > 0 ? 15 : undefined,
        totalBytes,
        baixadoBytes,
        versaoAtual,
        versaoNova: update.version,
        mensagem: "Baixando a atualização.",
      })
      return
    }

    if (evento.event === "Progress") {
      baixadoBytes += evento.data.chunkLength
      const percentual =
        totalBytes > 0
          ? Math.min(90, 15 + Math.round((baixadoBytes / totalBytes) * 75))
          : undefined
      onProgresso?.({
        etapa: "baixando",
        percentual,
        totalBytes,
        baixadoBytes,
        versaoAtual,
        versaoNova: update.version,
        mensagem: "Baixando a atualização.",
      })
      return
    }

    onProgresso?.({
      etapa: "instalando",
      percentual: 94,
      totalBytes,
      baixadoBytes,
      versaoAtual,
      versaoNova: update.version,
      mensagem: "Download concluído. Instalando a atualização.",
    })
  })

  onProgresso?.({
    etapa: "reiniciando",
    percentual: 98,
    versaoAtual,
    versaoNova: update.version,
    mensagem: "Atualização instalada. Reiniciando o AutoLiquid.",
  })

  try {
    await relaunch()
  } catch {
    // No Windows o instalador pode encerrar o app antes do relaunch completar.
  }

  // Se chegou aqui, relaunch() falhou silenciosamente — avisa o usuário.
  return {
    suportado: true,
    temAtualizacao: true,
    instalada: true,
    versaoAtual,
    versaoNova: update.version,
    mensagem: `Versão ${update.version} instalada. Feche e reabra o AutoLiquid para aplicar.`,
  }
}


export async function abrirUrl(url: string): Promise<void> {
  await apiFetch<{ ok: boolean }>("/api/abrir-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  })
}
