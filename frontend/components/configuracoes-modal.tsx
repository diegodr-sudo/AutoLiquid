"use client";

import { useEffect, useMemo, useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  ArrowDownToLine,
  Bug,
  FileDown,
  CalendarDays,
  Check,
  CheckCircle2,
  Chrome,
  Database,
  ExternalLink,
  Eye,
  EyeOff,
  Copy,
  Github,
  Globe,
  Loader2,
  Mail,
  MessageCircle,
  Monitor,
  Moon,
  Plus,
  RefreshCw,
  Save,
  Settings,
  Settings2,
  Sun,
  Tag,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { GlassButton, GlassCard } from "./glass-card";
import {
  fetchAppSettings,
  fetchAuthUsuarios,
  fetchBugReports,
  fetchDatasGlobais,
  loginAutoLiquid,
  fetchRocketChatNotifications,
  fetchServidoresConfig,
  openChromeSession,
  recarregarModulos,
  resolverBugReport,
  deletarBugReport,
  saveAppSettings,
  saveDatasGlobais,
  upsertServidorConfig,
  updateAuthUsuario,
  verificarAtualizacao,
  instalarAtualizacaoTauri,
  isDevRuntime,
  isTauriRuntime,
  abrirUrl,
  AUTO_LIQUID_REPO,
  AUTO_LIQUID_REPO_URL,
  deletarServidorConfig,
  type AppSettings,
  type AtualizacaoTauriInfo,
  type AtualizacaoTauriProgresso,
  type BugReport,
  type AuthUsuario,
  type ProcessDates,
  type ServidorConfigRemoto,
  type VersaoInfo,
} from "@/lib/data";
import { useAuth } from "@/lib/auth-context";
import { parseDbTimestamp } from "@/lib/utils";
import { SimpleTooltip } from "@/components/ui/simple-tooltip";

interface ConfiguracoesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (settings: AppSettings) => void;
  onChromeOpened?: () => void;
}

const DEFAULT_SETTINGS: AppSettings = {
  chromePorta: 9222,
  navegador: "chrome",
  fecharAbaFila: false,
  perguntarLimparMes: true,
  temaWeb: "light",
  nivelLog: "desenvolvedor",
  tursoDatabaseUrl: "",
  tursoAuthToken: "",
  nomeUsuario: "",
  nfServicoAlertaDiasUteis: 3,
  tiposDocumentoLf: ["NF Serviço", "Fatura", "Boleto"],
  rocketChatUrl: "https://chat.ufsc.br",
  rocketChatUserId: "",
  rocketChatAuthToken: "",
  rocketChatContar: "tudo",
};

const TURSO_DASHBOARD_URL = "https://app.turso.tech";

type Aba = "basico" | "avancado" | "sistema";

const DEFAULT_DATAS_GLOBAIS: ProcessDates = {
  apuracao: "",
  vencimento: "",
};

type UpdateProgressTone = "info" | "success" | "error";

interface UpdateProgressState {
  title: string;
  detail: string;
  percent?: number;
  tone: UpdateProgressTone;
}

/** Converte DD/MM/AAAA → YYYY-MM-DD para uso no <input type="date"> */
function dateToISO(value: string): string {
  if (!value) return value;
  const trimmed = value.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return trimmed;
  const br = trimmed.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (br) return `${br[3]}-${br[2]}-${br[1]}`;
  return trimmed;
}

function canonicalEquipeName(...values: Array<string | undefined>): string {
  const joined = values.join(" ").trim().toLowerCase();
  if (!joined) return "";
  if (joined.includes("diego")) return "diego";
  return joined.split(/\s+/)[0] || joined;
}

function firstName(value: string): string {
  return value.trim().split(/\s+/)[0] || value.trim();
}

function formatUpdateBytes(bytes?: number): string | null {
  if (!bytes || bytes <= 0) return null;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function progressoAtualizacaoParaEstado(
  progresso: AtualizacaoTauriProgresso
): UpdateProgressState {
  if (progresso.etapa === "baixando") {
    const baixado = formatUpdateBytes(progresso.baixadoBytes);
    const total = formatUpdateBytes(progresso.totalBytes);
    return {
      title: "Baixando atualização",
      detail: baixado && total ? `${baixado} de ${total}` : progresso.mensagem,
      percent: progresso.percentual,
      tone: "info",
    };
  }

  if (progresso.etapa === "instalando") {
    return {
      title: "Instalando atualização",
      detail: progresso.mensagem,
      percent: progresso.percentual,
      tone: "info",
    };
  }

  if (progresso.etapa === "reiniciando") {
    return {
      title: "Reiniciando o AutoLiquid",
      detail: progresso.mensagem,
      percent: progresso.percentual,
      tone: "info",
    };
  }

  if (progresso.etapa === "atualizado") {
    return {
      title: "Você está na versão mais recente",
      detail: progresso.mensagem,
      percent: 100,
      tone: "success",
    };
  }

  return {
    title: progresso.etapa === "disponivel" ? "Atualização encontrada" : "Verificando atualização",
    detail: progresso.mensagem,
    percent: progresso.percentual,
    tone: "info",
  };
}

export function ConfiguracoesModal({
  isOpen,
  onClose,
  onSaved,
  onChromeOpened,
}: ConfiguracoesModalProps) {
  const router = useRouter();
  const { isModerator } = useAuth();
  const { setTheme } = useTheme();
  const [abaAtiva, setAbaAtiva] = useState<Aba>("basico");
  const [sistemaDesbloqueado, setSistemaDesbloqueado] = useState(false);
  const [cliquesSistema, setCliquesSistema] = useState(0);
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState("");
  const [abrindoNavegador, setAbrindoNavegador] = useState(false);
  const [recarregando, setRecarregando] = useState(false);
  const [msgRecarregar, setMsgRecarregar] = useState("");

  // Debug avançado
  const [detectando, setDetectando] = useState(false);
  const [relatorioCopiado, setRelatorioCopiado] = useState(false);
  const [erroDeteccao, setErroDeteccao] = useState("");
  const [relatorioTexto, setRelatorioTexto] = useState("");

  // Atualização
  const [verificandoUpdate, setVerificandoUpdate] = useState(false);
  const [infoUpdate, setInfoUpdate] = useState<VersaoInfo | null>(null);
  const [resultadoUpdate, setResultadoUpdate] = useState<AtualizacaoTauriInfo | null>(null);
  const [progressoUpdate, setProgressoUpdate] = useState<UpdateProgressState | null>(null);
  const [baixando, setBaixando] = useState(false);
  const [showTursoToken, setShowTursoToken] = useState(false);
  const [showRocketToken, setShowRocketToken] = useState(false);
  const [testandoRocket, setTestandoRocket] = useState(false);
  const [resultadoRocket, setResultadoRocket] = useState("");
  const [novoTipoLf, setNovoTipoLf] = useState("");
  const [servidoresSistema, setServidoresSistema] = useState<ServidorConfigRemoto[]>([]);
  const [usuariosAuth, setUsuariosAuth] = useState<AuthUsuario[]>([]);
  const [datasGlobais, setDatasGlobais] = useState<ProcessDates>(DEFAULT_DATAS_GLOBAIS);
  const [carregandoServidores, setCarregandoServidores] = useState(false);
  const [carregandoUsuarios, setCarregandoUsuarios] = useState(false);
  const [carregandoDatasGlobais, setCarregandoDatasGlobais] = useState(false);
  const [salvandoDatasGlobais, setSalvandoDatasGlobais] = useState(false);
  const [validandoUsuario, setValidandoUsuario] = useState("");
  const [validacaoUsuarios, setValidacaoUsuarios] = useState<Record<string, "ok" | "erro">>({});
  const [bugReports, setBugReports] = useState<BugReport[]>([]);
  const [carregandoBugs, setCarregandoBugs] = useState(false);
  const [erroBugs, setErroBugs] = useState("");
  const [resolvendo, setResolvendo] = useState<number | null>(null);
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [novoServidorNome, setNovoServidorNome] = useState("");
  const [erroServidores, setErroServidores] = useState("");
  const [erroUsuarios, setErroUsuarios] = useState("");
  const [erroDatasGlobais, setErroDatasGlobais] = useState("");
  const [mensagemDatasGlobais, setMensagemDatasGlobais] = useState("");
  const modoDesenvolvedor = isDevRuntime();
  const atualizacaoAutomaticaDisponivel = isTauriRuntime() && !modoDesenvolvedor;

  useEffect(() => {
    if (!isOpen) return;

    let ativo = true;
    setAbaAtiva("basico");
    if (!isModerator) {
      setSistemaDesbloqueado(false);
    }
    setCliquesSistema(0);
    setInfoUpdate(null);
    setResultadoUpdate(null);
    setProgressoUpdate(null);

    const carregar = async () => {
      setLoading(true);
      setErro("");
      try {
        const data = await fetchAppSettings();
        if (!ativo) return;
        const nextSettings = { ...DEFAULT_SETTINGS, ...data };
        setSettings(nextSettings);
        // NÃO aplicar setTheme aqui: o tema já foi sincronizado pelo
        // AppThemeSync na inicialização. Chamar setTheme durante o carregamento
        // do modal cria uma race condition — se o usuário clicar em "Escuro"
        // antes desta chamada async terminar, o tema reverteria para o valor
        // salvo, causando o "flash". O setTheme só deve ser chamado em
        // handleTemaWebChange (preview ao clicar) e em handleSave (persistência).
      } catch (error) {
        if (!ativo) return;
        setErro(
          error instanceof Error
            ? error.message
            : "Não foi possível carregar as configurações."
        );
      } finally {
        if (ativo) setLoading(false);
      }
    };

    carregar();
    return () => { ativo = false; };
  }, [isOpen, isModerator]);

  useEffect(() => {
    if (isModerator) return;
    setSistemaDesbloqueado(false);
    setCliquesSistema(0);
    if (abaAtiva === "sistema") {
      setAbaAtiva("basico");
    }
  }, [abaAtiva, isModerator]);

  useEffect(() => {
    if (!isOpen || abaAtiva !== "sistema" || !isModerator) return;
    let ativo = true;
    setCarregandoServidores(true);
    setCarregandoUsuarios(true);
    setCarregandoDatasGlobais(true);
    setErroServidores("");
    setErroUsuarios("");
    setErroDatasGlobais("");
    setMensagemDatasGlobais("");
    fetchServidoresConfig()
      .then((rows) => {
        if (ativo) setServidoresSistema(rows);
      })
      .catch((error) => {
        if (ativo) {
          setErroServidores(error instanceof Error ? error.message : "Não foi possível carregar os servidores.");
        }
      })
      .finally(() => {
        if (ativo) setCarregandoServidores(false);
      });
    fetchAuthUsuarios()
      .then((rows) => {
        if (ativo) setUsuariosAuth(rows);
      })
      .catch((error) => {
        if (ativo) {
          setErroUsuarios(error instanceof Error ? error.message : "Não foi possível carregar usuários.");
        }
      })
      .finally(() => {
        if (ativo) setCarregandoUsuarios(false);
      });
    fetchDatasGlobais()
      .then((dates) => {
        if (ativo) setDatasGlobais({ apuracao: dateToISO(dates.apuracao), vencimento: dateToISO(dates.vencimento) });
      })
      .catch((error) => {
        if (ativo) {
          setErroDatasGlobais(error instanceof Error ? error.message : "Não foi possível carregar as datas globais.");
        }
      })
      .finally(() => {
        if (ativo) setCarregandoDatasGlobais(false);
      });
    setCarregandoBugs(true);
    setErroBugs("");
    fetchBugReports("abertos")
      .then((rows) => {
        if (ativo) setBugReports(rows);
      })
      .catch((err) => {
        if (ativo) setErroBugs(err instanceof Error ? err.message : "Erro ao carregar bugs.");
      })
      .finally(() => {
        // Não guarda por `ativo`: se o efeito foi limpo antes da request terminar,
        // setCarregandoBugs(true) já tinha sido chamado e o spinner ficaria preso.
        setCarregandoBugs(false);
      });
    return () => { ativo = false; };
  }, [isOpen, abaAtiva, isModerator]);

  const handleRecarregarBugs = () => {
    setCarregandoBugs(true);
    setErroBugs("");
    fetchBugReports("abertos")
      .then((rows) => setBugReports(rows))
      .catch((err) => setErroBugs(err instanceof Error ? err.message : "Erro ao carregar bugs."))
      .finally(() => setCarregandoBugs(false));
  };

  const [exportandoBugs, setExportandoBugs] = useState(false);

  const handleExportarBugs = async () => {
    setExportandoBugs(true);
    try {
      // Busca todos os bugs (abertos + resolvidos)
      const [abertos, resolvidos] = await Promise.all([
        fetchBugReports("abertos"),
        fetchBugReports("resolvidos"),
      ]);
      const todos = [...abertos, ...resolvidos].sort(
        (a, b) => new Date(b.criadoEm).getTime() - new Date(a.criadoEm).getTime()
      );

      if (todos.length === 0) {
        return;
      }

      // ── Formata contexto e campos DOM como texto legível ──
      const fmtObj = (obj: Record<string, unknown> | Record<string, string>): string => {
        if (!obj || Object.keys(obj).length === 0) return "";
        return Object.entries(obj)
          .filter(([, v]) => v !== null && v !== undefined && v !== "")
          .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
          .join(" | ");
      };

      const fmtTs = (ts: string) => {
        const d = parseDbTimestamp(ts);
        if (!d) return ts;
        return d.toLocaleString("pt-BR", {
          day: "2-digit", month: "2-digit", year: "numeric",
          hour: "2-digit", minute: "2-digit", second: "2-digit",
        });
      };

      // ── CSV ──
      const escCsv = (v: string) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const colunas = [
        "ID", "Status", "Descrição", "Página", "Servidor", "Versão",
        "Criado em", "Resolvido em", "Contexto do app", "Campos do formulário", "Erros de console",
      ];
      const linhas = todos.map((b) => [
        b.id,
        b.resolvido ? "Resolvido" : "Aberto",
        b.descricao,
        b.pagina,
        b.servidorNome,
        b.versaoApp,
        fmtTs(b.criadoEm),
        b.resolvidoEm ? fmtTs(b.resolvidoEm) : "",
        fmtObj(b.contexto),
        fmtObj(b.camposDom),
        (b.errosConsole ?? []).join(" | "),
      ].map((c) => escCsv(String(c ?? ""))).join(";"));

      const csv = [colunas.map((c) => escCsv(c)).join(";"), ...linhas].join("\r\n");
      const bom = "﻿"; // BOM para Excel reconhecer UTF-8
      const blob = new Blob([bom + csv], { type: "text/csv;charset=utf-8;" });

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const dataHoje = new Date().toISOString().slice(0, 10);
      a.href = url;
      a.download = `bugs_autoliquid_${dataHoje}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // silencioso — falha de exportação não bloqueia a tela
    } finally {
      setExportandoBugs(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setErro("");
    try {
      const saved = await saveAppSettings(settings);
      setSettings(saved);
      setTheme(saved.temaWeb);
      onSaved?.(saved);
      onClose();
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Não foi possível salvar as configurações."
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTemaWebChange = (temaWeb: AppSettings["temaWeb"]) => {
    setSettings((current) => ({ ...current, temaWeb }));
    setTheme(temaWeb);
  };

  const normalizarTipoLf = (value: string) => value.trim().replace(/\s+/g, " ").slice(0, 60);

  const handleAdicionarTipoLf = () => {
    const tipo = normalizarTipoLf(novoTipoLf);
    if (!tipo) return;
    setSettings((current) => {
      const atuais = current.tiposDocumentoLf ?? [];
      if (atuais.some((item) => item.localeCompare(tipo, "pt-BR", { sensitivity: "base" }) === 0)) {
        return current;
      }
      return { ...current, tiposDocumentoLf: [...atuais, tipo] };
    });
    setNovoTipoLf("");
  };

  const handleRemoverTipoLf = (tipo: string) => {
    setSettings((current) => ({
      ...current,
      tiposDocumentoLf: (current.tiposDocumentoLf ?? []).filter((item) => item !== tipo),
    }));
  };

  const handleRecarregar = async () => {
    setRecarregando(true);
    setMsgRecarregar("");
    setErro("");
    try {
      const res = await recarregarModulos();
      setMsgRecarregar(res.mensagem);
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Não foi possível recarregar os módulos."
      );
    } finally {
      setRecarregando(false);
    }
  };

  const copiarTexto = (texto: string) => {
    // Tenta clipboard moderno; fallback via textarea + execCommand
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(texto).catch(() => copiarViaExecCommand(texto));
    } else {
      copiarViaExecCommand(texto);
    }
  };

  const copiarViaExecCommand = (texto: string) => {
    const ta = document.createElement("textarea");
    ta.value = texto;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try { document.execCommand("copy"); } catch (_) { /* silencia */ }
    document.body.removeChild(ta);
  };

  const handleDetectarPaginacao = async () => {
    setDetectando(true);
    setErroDeteccao("");
    setRelatorioCopiado(false);
    setRelatorioTexto("");
    try {
      const res = await fetch("http://127.0.0.1:8000/api/debug/detectar-paginacao", {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Erro desconhecido");
      }
      const data = await res.json();
      const texto = JSON.stringify(data.relatorio ?? data, null, 2);
      setRelatorioTexto(texto);
      copiarTexto(texto);
      setRelatorioCopiado(true);
      setTimeout(() => setRelatorioCopiado(false), 3000);
    } catch (error) {
      setErroDeteccao(
        error instanceof Error ? error.message : "Falha ao detectar campos."
      );
    } finally {
      setDetectando(false);
    }
  };

  const handleAbrirNavegador = async () => {
    setAbrindoNavegador(true);
    setErro("");
    try {
      await openChromeSession();
      await onChromeOpened?.();
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Não foi possível abrir o navegador."
      );
    } finally {
      setAbrindoNavegador(false);
    }
  };

  const handleVerificarUpdate = async () => {
    if (modoDesenvolvedor) {
      setErro("");
      setInfoUpdate(null);
      setResultadoUpdate(null);
      setProgressoUpdate({
        title: "Modo desenvolvedor",
        detail: "A verificação automática fica desligada no dev para não comparar a tag publicada com a versão local.",
        percent: 100,
        tone: "info",
      });
      return;
    }

    setVerificandoUpdate(true);
    setErro("");
    setResultadoUpdate(null);
    setProgressoUpdate({
      title: "Verificando atualização",
      detail: atualizacaoAutomaticaDisponivel
        ? "Consultando o pacote mais recente para o app instalado."
        : "Consultando a versão mais recente disponível.",
      percent: 8,
      tone: "info",
    });
    try {
      if (isTauriRuntime()) {
        const resultado = await instalarAtualizacaoTauri((progresso) => {
          setProgressoUpdate(progressoAtualizacaoParaEstado(progresso));
        });
        setResultadoUpdate(resultado);
        setInfoUpdate(null);
        setProgressoUpdate({
          title: resultado.temAtualizacao
            ? "Atualização instalada"
            : "Você está na versão mais recente",
          detail: resultado.mensagem,
          percent: 100,
          tone: "success",
        });
        return;
      }
      const info = await verificarAtualizacao();
      setInfoUpdate(info);
      setProgressoUpdate({
        title: info.erro
          ? "Não foi possível verificar"
          : info.tem_atualizacao
            ? "Atualização encontrada"
            : "Você está na versão mais recente",
        detail: info.erro
          ? info.erro
          : info.tem_atualizacao
            ? `A versão v${info.versao_nova} está disponível para download.`
            : `Versão instalada: v${info.versao_atual}.`,
        percent: 100,
        tone: info.erro ? "error" : info.tem_atualizacao ? "info" : "success",
      });
    } catch (error) {
      setProgressoUpdate({
        title: "Não foi possível atualizar",
        detail: error instanceof Error
          ? error.message
          : "Não foi possível verificar atualizações.",
        percent: 100,
        tone: "error",
      });
      setErro(
        error instanceof Error
          ? error.message
          : "Não foi possível verificar atualizações."
      );
    } finally {
      setVerificandoUpdate(false);
    }
  };

  const handleTestarRocketChat = async () => {
    setTestandoRocket(true);
    setResultadoRocket("");
    setErro("");
    try {
      const saved = await saveAppSettings(settings);
      setSettings(saved);
      onSaved?.(saved);
      const resultado = await fetchRocketChatNotifications();
      if (!resultado.configured) {
        setResultadoRocket("Rocket.Chat ainda não está configurado. Informe User ID e token.");
      } else {
        setResultadoRocket(
          `Conectado. ${resultado.unread} não lida(s), ${resultado.mentions} menção(ões). Badge atual: ${resultado.count}.`
        );
      }
    } catch (error) {
      setResultadoRocket(
        error instanceof Error
          ? error.message
          : "Não foi possível testar o Rocket.Chat."
      );
    } finally {
      setTestandoRocket(false);
    }
  };

  const handleSalvarDatasGlobais = async () => {
    setSalvandoDatasGlobais(true);
    setErroDatasGlobais("");
    setMensagemDatasGlobais("");
    try {
      const saved = await saveDatasGlobais(datasGlobais);
      setDatasGlobais(saved);
      setMensagemDatasGlobais("Datas globais atualizadas para todos os usuários.");
    } catch (error) {
      setErroDatasGlobais(error instanceof Error ? error.message : "Não foi possível salvar as datas globais.");
    } finally {
      setSalvandoDatasGlobais(false);
    }
  };

  const handleAdicionarServidorSistema = async () => {
    const nome = novoServidorNome.trim();
    if (!nome) return;
    const nomeKey = canonicalEquipeName(nome);
    if (
      servidoresSistema.some((s) => canonicalEquipeName(s.nome, s.nomeCompleto) === nomeKey)
      || usuariosAuth.some((u) => canonicalEquipeName(u.nome, u.username) === nomeKey)
    ) {
      setErroServidores("Servidor já cadastrado.");
      return;
    }
    const novo: ServidorConfigRemoto = {
      nome: firstName(nome),
      nomeCompleto: nome,
      cor: "#6366f1",
    };
    setErroServidores("");
    setServidoresSistema((current) => [...current, novo]);
    setNovoServidorNome("");
    try {
      await upsertServidorConfig(nome, "#6366f1");
      const [servidoresAtualizados, usuariosAtualizados] = await Promise.all([
        fetchServidoresConfig(),
        fetchAuthUsuarios(),
      ]);
      setServidoresSistema(servidoresAtualizados);
      setUsuariosAuth(usuariosAtualizados);
    } catch (error) {
      setServidoresSistema((current) => current.filter((s) => s !== novo));
      setErroServidores(error instanceof Error ? error.message : "Não foi possível adicionar o servidor.");
    }
  };

  const handleRemoverServidorSistema = async (servidor: ServidorConfigRemoto) => {
    const snapshot = servidoresSistema;
    setErroServidores("");
    setServidoresSistema((current) => current.filter((s) => s.nome !== servidor.nome));
    try {
      await deletarServidorConfig(servidor.nome);
      const [servidoresAtualizados, usuariosAtualizados] = await Promise.all([
        fetchServidoresConfig(),
        fetchAuthUsuarios(),
      ]);
      setServidoresSistema(servidoresAtualizados);
      setUsuariosAuth(usuariosAtualizados);
    } catch (error) {
      setServidoresSistema(snapshot);
      setErroServidores(error instanceof Error ? error.message : "Não foi possível remover o servidor.");
    }
  };

  const handleAtualizarUsuario = async (
    usuario: AuthUsuario,
    patch: { role?: "user" | "moderator"; senha?: string | null }
  ) => {
    const snapshot = usuariosAuth;
    setErroUsuarios("");
    setUsuariosAuth((current) =>
      current.map((item) => item.username === usuario.username ? { ...item, ...patch, senha: patch.senha ?? item.senha } : item)
    );
    try {
      const saved = await updateAuthUsuario(usuario.username, patch);
      setUsuariosAuth((current) => current.map((item) => item.username === usuario.username ? saved : item));
    } catch (error) {
      setUsuariosAuth(snapshot);
      setErroUsuarios(error instanceof Error ? error.message : "Não foi possível atualizar o usuário.");
    }
  };

  const handleValidarUsuario = async (usuario: AuthUsuario) => {
    const username = usuario.username.trim();
    const senha = usuario.senha.trim();
    if (!username || !senha) {
      setValidacaoUsuarios((current) => ({ ...current, [usuario.username]: "erro" }));
      setErroUsuarios("Informe usuário e senha para validar o acesso.");
      return;
    }
    setErroUsuarios("");
    setValidandoUsuario(usuario.username);
    setValidacaoUsuarios((current) => {
      const next = { ...current };
      delete next[usuario.username];
      return next;
    });
    try {
      await updateAuthUsuario(usuario.username, { senha });
      const session = await loginAutoLiquid(username, senha);
      setUsuariosAuth((current) =>
        current.map((item) =>
          item.username === usuario.username
            ? { ...item, nome: session.nome || item.nome, role: session.role, senha }
            : item
        )
      );
      setValidacaoUsuarios((current) => ({ ...current, [usuario.username]: "ok" }));
    } catch (error) {
      setValidacaoUsuarios((current) => ({ ...current, [usuario.username]: "erro" }));
      setErroUsuarios(error instanceof Error ? error.message : "Não foi possível validar o acesso.");
    } finally {
      setValidandoUsuario("");
    }
  };

  const nomeNavegador = settings.navegador === "edge" ? "Edge" : "Chrome";
  const equipeAcesso = useMemo(() => {
    const usuariosPorNome = new Map<string, AuthUsuario>();
    for (const usuario of usuariosAuth) {
      const key = canonicalEquipeName(usuario.nome, usuario.username);
      if (!key || usuariosPorNome.has(key)) continue;
      usuariosPorNome.set(key, usuario);
    }

    const rows = servidoresSistema.map((servidor) => {
      const key = canonicalEquipeName(servidor.nome, servidor.nomeCompleto);
      return { key, servidor, usuario: usuariosPorNome.get(key) ?? null };
    });

    for (const usuario of usuariosAuth) {
      const key = canonicalEquipeName(usuario.nome, usuario.username);
      if (!key || rows.some((row) => row.key === key)) continue;
      rows.push({
        key,
        servidor: {
          nome: firstName(usuario.nome || usuario.username),
          nomeCompleto: usuario.nome,
          cor: "#6366f1",
        },
        usuario,
      });
    }

    return rows;
  }, [servidoresSistema, usuariosAuth]);

  const handleTituloClick = () => {
    if (!isModerator) return;
    if (sistemaDesbloqueado) return;
    setCliquesSistema((valor) => {
      const proximo = valor + 1;
      if (proximo >= 5) {
        setSistemaDesbloqueado(true);
        setAbaAtiva("sistema");
        return 0;
      }
      return proximo;
    });
  };

  const versaoAtualUpdate = resultadoUpdate?.versaoAtual ?? infoUpdate?.versao_atual;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[200] overflow-y-auto">
      <div
        className="absolute inset-0 bg-background/90"
        onClick={onClose}
      />

      <div className="relative flex min-h-full items-start justify-center p-2 sm:p-3">
        <GlassCard
          className="relative z-10 pointer-events-auto w-full max-w-3xl overflow-hidden border-white/50 shadow-[0_28px_90px_-40px_rgba(15,23,42,0.35)]"
          contentClassName="flex max-h-[calc(100dvh-16px)] min-h-0 flex-col sm:max-h-[calc(100dvh-24px)]"
        >
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between border-b border-glass-border px-5 py-4">
            <div>
              <button
                type="button"
                onClick={handleTituloClick}
                className="text-left text-lg font-semibold text-foreground outline-none"
              >
                Configurações
              </button>
              <p className="mt-1 text-sm text-muted-foreground">
                Organize preferências, integrações e ajustes técnicos do AutoLiquid.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-secondary/80 hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Abas */}
          <div className="shrink-0 flex gap-1 border-b border-glass-border px-5 pt-2 pb-0">
            {(
              [
                { id: "basico" as Aba, label: "Básico", icon: Settings },
                { id: "avancado" as Aba, label: "Integrações", icon: Settings2 },
                ...(isModerator && sistemaDesbloqueado
                  ? [{ id: "sistema" as Aba, label: "Sistema", icon: Database }]
                  : []),
              ] as const
            ).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setAbaAtiva(id)}
                className={[
                  "flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-xl border-b-2 transition-all",
                  abaAtiva === id
                    ? "border-primary text-primary bg-primary/5"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted",
                ].join(" ")}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>

          {/* Conteúdo */}
          <div className="scrollable-surface min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4 [touch-action:pan-y]">
            {loading ? (
              <div className="rounded-xl border border-glass-border bg-secondary/40 px-4 py-8 text-center text-sm text-muted-foreground">
                Carregando configurações...
              </div>
            ) : (
              <div className="space-y-6">

                {/* ── ABA BÁSICO ── */}
                {abaAtiva === "basico" && (
                  <>
                    {/* Aparência */}
                    <section className="space-y-3">
                      <div>
                        <h3 className="text-sm font-semibold text-foreground">Aparência</h3>
                        <p className="text-sm text-muted-foreground">
                          O tema claro é o padrão da interface web.
                        </p>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-3">
                        {[
                          { value: "light" as const, title: "Claro", description: "Superfície clara e leitura direta.", icon: Sun },
                          { value: "dark" as const, title: "Escuro", description: "Versão noturna para pouca luz.", icon: Moon },
                          { value: "system" as const, title: "Sistema", description: "Segue o tema do sistema operacional.", icon: Monitor },
                        ].map((option) => {
                          const Icon = option.icon;
                          const active = settings.temaWeb === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => handleTemaWebChange(option.value)}
                              className={[
                                "rounded-2xl border px-4 py-4 text-left transition-all",
                                active
                                  ? "border-primary bg-primary/10 shadow-[0_12px_30px_-24px_rgba(79,70,229,0.8)]"
                                  : "border-glass-border bg-secondary/30 hover:border-primary/40 hover:bg-secondary/55",
                              ].join(" ")}
                            >
                              <div className="flex items-center gap-3">
                                <div className={["flex h-10 w-10 items-center justify-center rounded-xl border", active ? "border-primary/30 bg-primary/15 text-primary" : "border-glass-border bg-background/70 text-muted-foreground"].join(" ")}>
                                  <Icon className="h-5 w-5" />
                                </div>
                                <div>
                                  <p className="font-medium text-foreground">{option.title}</p>
                                  <p className="mt-1 text-sm text-muted-foreground">{option.description}</p>
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </section>

                    {/* Navegador */}
                    <section className="space-y-3">
                      <div>
                        <h3 className="text-sm font-semibold text-foreground">Navegador</h3>
                        <p className="text-sm text-muted-foreground">
                          Escolha o navegador usado pela automação para acessar o Comprasnet.
                        </p>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {[
                          {
                            value: "chrome" as const,
                            title: "Google Chrome",
                            description: "Recomendado. Ampla compatibilidade com o Comprasnet.",
                            icon: Chrome,
                          },
                          {
                            value: "edge" as const,
                            title: "Microsoft Edge",
                            description: "Baseado no Chromium. Boa opção em ambientes corporativos.",
                            icon: Globe,
                          },
                        ].map((option) => {
                          const Icon = option.icon;
                          const active = settings.navegador === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => setSettings((c) => ({ ...c, navegador: option.value }))}
                              className={[
                                "rounded-2xl border px-4 py-4 text-left transition-all",
                                active
                                  ? "border-primary bg-primary/10 shadow-[0_12px_30px_-24px_rgba(79,70,229,0.8)]"
                                  : "border-glass-border bg-secondary/30 hover:border-primary/40 hover:bg-secondary/55",
                              ].join(" ")}
                            >
                              <div className="flex items-center gap-3">
                                <div className={["flex h-10 w-10 items-center justify-center rounded-xl border", active ? "border-primary/30 bg-primary/15 text-primary" : "border-glass-border bg-background/70 text-muted-foreground"].join(" ")}>
                                  <Icon className="h-5 w-5" />
                                </div>
                                <div>
                                  <p className="font-medium text-foreground">{option.title}</p>
                                  <p className="mt-1 text-sm text-muted-foreground">{option.description}</p>
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                      <div className="flex flex-col gap-3 rounded-2xl border border-glass-border bg-secondary/25 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-glass-border bg-background/80 text-muted-foreground">
                            <Settings2 className="h-4 w-4" />
                          </span>
                          <div>
                            <p className="text-sm font-medium text-foreground">Porta do {nomeNavegador}</p>
                            <p className="text-xs text-muted-foreground">
                              Use a mesma porta aberta na sessão de automação.
                            </p>
                          </div>
                        </div>
                        <input
                          id="chrome-porta"
                          type="number"
                          min={1}
                          max={65535}
                          value={settings.chromePorta}
                          onChange={(e) =>
                            setSettings((c) => ({ ...c, chromePorta: Number(e.target.value || 0) }))
                          }
                          className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2 text-sm text-foreground shadow-inner outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 sm:w-32"
                        />
                      </div>

                    </section>

                    {/* Perguntar sobre datas */}
                    <section className="rounded-2xl border border-glass-border bg-secondary/25 px-4 py-4">
                      <label className="flex cursor-pointer items-start gap-3">
                        <input
                          type="checkbox"
                          checked={settings.perguntarLimparMes}
                          onChange={(e) =>
                            setSettings((c) => ({ ...c, perguntarLimparMes: e.target.checked }))
                          }
                          className="mt-1 h-4 w-4 rounded border-glass-border text-primary focus:ring-primary/30"
                        />
                        <span>
                          <span className="block font-medium text-foreground">
                            Conferir datas antigas no início do mês
                          </span>
                          <span className="mt-1 block text-sm text-muted-foreground">
                            Pergunta antes de usar datas salvas que possam gerar processamento incorreto.
                          </span>
                        </span>
                      </label>
                    </section>

                    {/* Ajustes do registro */}
                    <section className="space-y-3 rounded-2xl border border-glass-border bg-secondary/25 px-4 py-4">
                      <div>
                        <h3 className="text-sm font-semibold text-foreground">Ajustes do registro</h3>
                        <p className="text-sm text-muted-foreground">
                          Tipos de documento que exibem a opção de LF na conferência.
                        </p>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {(settings.tiposDocumentoLf ?? []).map((tipo) => (
                          <span
                            key={tipo}
                            className="inline-flex items-center gap-2 rounded-full border border-glass-border bg-background/80 px-3 py-1.5 text-sm text-foreground"
                          >
                            {tipo}
                            <button
                              type="button"
                              onClick={() => handleRemoverTipoLf(tipo)}
                              className="rounded-full p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                              aria-label={`Remover ${tipo}`}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </span>
                        ))}
                      </div>

                      <form
                        className="flex flex-col gap-2 sm:flex-row"
                        onSubmit={(event) => {
                          event.preventDefault();
                          handleAdicionarTipoLf();
                        }}
                      >
                        <input
                          value={novoTipoLf}
                          onChange={(event) => setNovoTipoLf(event.target.value)}
                          placeholder="Ex.: Recibo"
                          className="min-w-0 flex-1 rounded-xl border border-glass-border bg-background/80 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                        />
                        <GlassButton
                          type="submit"
                          size="sm"
                          className="justify-center"
                          disabled={!novoTipoLf.trim()}
                        >
                          <Plus className="h-4 w-4" />
                          Adicionar
                        </GlassButton>
                      </form>
                    </section>

                    {/* Atualização */}
                    <section className="rounded-2xl border border-violet-500/20 bg-violet-500/10 px-4 py-4">
                      <div className="flex items-start gap-3">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-violet-500/20 bg-background/80 text-violet-700 shadow-[0_16px_30px_-24px_rgba(124,58,237,0.7)]">
                          <ArrowDownToLine className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <h3 className="text-sm font-semibold text-foreground">Atualização</h3>
                              <p className="mt-1 text-sm text-muted-foreground">
                                {modoDesenvolvedor
                                  ? "Atualizações ficam desligadas no modo desenvolvedor."
                                  : atualizacaoAutomaticaDisponivel
                                    ? "Instala novas versões automaticamente pelo app instalado."
                                    : "Verifique se há uma nova versão disponível."}
                              </p>
                            </div>
                            <GlassButton
                              variant="ghost"
                              size="sm"
                              onClick={handleVerificarUpdate}
                              disabled={verificandoUpdate}
                              className="border border-violet-500/20 bg-background/80 text-foreground hover:bg-background shrink-0"
                            >
                              {verificandoUpdate ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="h-4 w-4" />
                              )}
                              {verificandoUpdate
                                ? atualizacaoAutomaticaDisponivel
                                  ? "Atualizando..."
                                  : "Verificando..."
                                : modoDesenvolvedor
                                  ? "Modo dev"
                                  : atualizacaoAutomaticaDisponivel
                                    ? "Verificar e instalar"
                                    : "Verificar"}
                            </GlassButton>
                          </div>

                          {versaoAtualUpdate && (
                            <div className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                              <Tag className="h-3.5 w-3.5" />
                              Versão instalada:{" "}
                              <span className="font-semibold text-foreground">
                                v{versaoAtualUpdate}
                              </span>
                            </div>
                          )}

                          {progressoUpdate && (
                            <div
                              className={`mt-3 rounded-xl border px-3 py-3 ${
                                progressoUpdate.tone === "error"
                                  ? "border-destructive/25 bg-destructive/10"
                                  : progressoUpdate.tone === "success"
                                    ? "border-emerald-500/20 bg-emerald-500/10"
                                    : "border-violet-500/25 bg-background/75"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <p
                                    className={`text-sm font-medium ${
                                      progressoUpdate.tone === "error"
                                        ? "text-destructive"
                                        : progressoUpdate.tone === "success"
                                          ? "text-emerald-700"
                                          : "text-violet-700"
                                    }`}
                                  >
                                    {progressoUpdate.title}
                                  </p>
                                  <p className="mt-1 break-words text-xs text-muted-foreground">
                                    {progressoUpdate.detail}
                                  </p>
                                </div>
                                {verificandoUpdate && (
                                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-violet-700" />
                                )}
                              </div>
                              <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
                                <div
                                  className={`h-full rounded-full transition-all duration-300 ${
                                    progressoUpdate.tone === "error"
                                      ? "bg-destructive"
                                      : progressoUpdate.tone === "success"
                                        ? "bg-emerald-500"
                                        : "bg-violet-600"
                                  } ${progressoUpdate.percent === undefined ? "animate-pulse" : ""}`}
                                  style={{
                                    width: `${progressoUpdate.percent ?? 36}%`,
                                  }}
                                />
                              </div>
                              {progressoUpdate.percent !== undefined && (
                                <p className="mt-1 text-right text-[11px] font-medium text-muted-foreground">
                                  {Math.round(progressoUpdate.percent)}%
                                </p>
                              )}
                            </div>
                          )}

                          {/* Resultado da verificação */}
                          {resultadoUpdate && (
                            <div
                              className={`mt-3 flex items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
                                resultadoUpdate.instalada || !resultadoUpdate.temAtualizacao
                                  ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                                  : "border-violet-500/30 bg-background/75 text-violet-700"
                              }`}
                            >
                              <CheckCircle2 className="h-4 w-4 shrink-0" />
                              {resultadoUpdate.mensagem}
                            </div>
                          )}
                          {infoUpdate && (
                            <div className="mt-3 space-y-2">
                              {infoUpdate.erro ? (
                                <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-3 space-y-2">
                                  <p className="text-sm font-medium text-destructive">
                                    Não foi possível consultar as releases do repositório.
                                  </p>
                                  <p className="text-xs text-destructive/90 break-words">
                                    {infoUpdate.erro}
                                  </p>
                                  <button
                                    onClick={() => abrirUrl(infoUpdate.url_download)}
                                    className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-background/80 px-3 py-1.5 text-sm font-medium text-destructive transition-colors hover:bg-background"
                                  >
                                    <ArrowDownToLine className="h-3.5 w-3.5" />
                                    Abrir página de releases
                                  </button>
                                </div>
                              ) : infoUpdate.tem_atualizacao ? (
                                <div className="rounded-xl border border-violet-500/30 bg-background/75 px-3 py-3 space-y-2">
                                  <p className="text-sm font-medium text-violet-700">
                                    Nova versão disponível: v{infoUpdate.versao_nova}
                                  </p>
                                  <button
                                    disabled={baixando}
                                    onClick={async () => {
                                      setBaixando(true);
                                      try {
                                        await abrirUrl(infoUpdate.url_download);
                                      } finally {
                                        setBaixando(false);
                                      }
                                    }}
                                    className="inline-flex items-center gap-2 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-sm font-medium text-violet-700 transition-colors hover:bg-violet-500/20 disabled:opacity-60 disabled:cursor-not-allowed"
                                  >
                                    {baixando ? (
                                      <>
                                        <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z" />
                                        </svg>
                                        Abrindo…
                                      </>
                                    ) : (
                                      <>
                                        <ArrowDownToLine className="h-3.5 w-3.5" />
                                        Baixar v{infoUpdate.versao_nova}
                                      </>
                                    )}
                                  </button>
                                </div>
                              ) : (
                                <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">
                                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                                  Você está usando a versão mais recente (v{infoUpdate.versao_atual}).
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </section>

                    {/* Contato */}
                    <section className="rounded-2xl border border-glass-border bg-secondary/25 px-4 py-5">
                      <div className="flex flex-col gap-4">
                        <div>
                          <h3 className="text-sm font-semibold text-foreground">Contato</h3>
                          <p className="mt-1 text-sm text-muted-foreground">
                            Dúvidas ou sugestões — fale com o desenvolvedor.
                          </p>
                        </div>
                        <div className="flex flex-col gap-2">
                          <button
                            type="button"
                            onClick={() => abrirUrl("mailto:diegodutraramos@gmail.com")}
                            className="group flex items-center gap-3 rounded-xl border border-glass-border bg-background/70 px-3 py-2.5 text-sm transition hover:border-primary/40 hover:bg-background text-left"
                          >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-glass-border bg-secondary/60 text-muted-foreground transition group-hover:border-primary/30 group-hover:text-primary">
                              <Mail className="h-4 w-4" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-xs font-medium text-muted-foreground">E-mail</span>
                              <span className="block truncate text-sm text-foreground">diegodutraramos@gmail.com</span>
                            </span>
                            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition group-hover:text-muted-foreground" />
                          </button>
                          <button
                            type="button"
                            onClick={() => abrirUrl(AUTO_LIQUID_REPO_URL)}
                            className="group flex items-center gap-3 rounded-xl border border-glass-border bg-background/70 px-3 py-2.5 text-sm transition hover:border-primary/40 hover:bg-background text-left"
                          >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-glass-border bg-secondary/60 text-muted-foreground transition group-hover:border-primary/30 group-hover:text-primary">
                              <Github className="h-4 w-4" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-xs font-medium text-muted-foreground">GitHub</span>
                              <span className="block truncate text-sm text-foreground">{AUTO_LIQUID_REPO}</span>
                            </span>
                            <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50 transition group-hover:text-muted-foreground" />
                          </button>
                        </div>
                      </div>
                    </section>
                  </>
                )}

                {/* ── ABA AVANÇADO ── */}
                {abaAtiva === "avancado" && (
                  <>
                    {/* Rocket.Chat */}
                    <section className="rounded-2xl border border-red-500/15 bg-red-500/5 px-4 py-4">
                      <div className="flex items-start gap-3">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-red-500/20 bg-background/80 text-red-600 shadow-[0_16px_30px_-24px_rgba(239,68,68,0.75)]">
                          <MessageCircle className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1 space-y-3">
                          <div>
                            <p className="text-sm font-semibold text-foreground">Rocket.Chat</p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              Conecta o contador de mensagens não lidas ao badge vermelho do topo.
                            </p>
                          </div>
                          <div className="space-y-1.5">
                            <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                              Contador
                            </span>
                            <div className="grid gap-2 rounded-2xl border border-glass-border bg-background/70 p-1.5 sm:grid-cols-2">
                              {[
                                {
                                  value: "tudo" as const,
                                  title: "Todas não lidas",
                                  description: "Canais, grupos e DMs.",
                                },
                                {
                                  value: "mencoes" as const,
                                  title: "Somente menções",
                                  description: "Quando chamarem você.",
                                },
                              ].map((option) => {
                                const active = settings.rocketChatContar === option.value;
                                return (
                                  <button
                                    key={option.value}
                                    type="button"
                                    onClick={() =>
                                      setSettings((current) => ({
                                        ...current,
                                        rocketChatContar: option.value,
                                      }))
                                    }
                                    className={[
                                      "rounded-xl px-3 py-2 text-left transition",
                                      active
                                        ? "border border-red-500/25 bg-red-500/10 text-red-700 shadow-sm"
                                        : "border border-transparent text-muted-foreground hover:bg-secondary/55 hover:text-foreground",
                                    ].join(" ")}
                                  >
                                    <span className="block text-sm font-semibold leading-5">{option.title}</span>
                                    <span className="mt-0.5 block truncate text-[11px] leading-4 opacity-75">
                                      {option.description}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                          <div className="space-y-3">
                            <label className="space-y-1.5 sm:col-span-2">
                              <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                URL
                              </span>
                              <input
                                type="url"
                                value={settings.rocketChatUrl}
                                onChange={(e) =>
                                  setSettings((c) => ({ ...c, rocketChatUrl: e.target.value }))
                                }
                                onBlur={() =>
                                  setSettings((current) => {
                                    const url = current.rocketChatUrl.trim();
                                    if (!url || url.startsWith("http://") || url.startsWith("https://")) {
                                      return { ...current, rocketChatUrl: url };
                                    }
                                    return { ...current, rocketChatUrl: `https://${url}` };
                                  })
                                }
                                placeholder="https://chat.ufsc.br"
                                className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2.5 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                              />
                            </label>
                            <label className="space-y-1.5 sm:col-span-2">
                              <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                User ID
                              </span>
                              <input
                                type="text"
                                value={settings.rocketChatUserId}
                                onChange={(e) =>
                                  setSettings((c) => ({ ...c, rocketChatUserId: e.target.value }))
                                }
                                placeholder="Seu X-User-Id"
                                className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2.5 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                              />
                            </label>
                            <label className="space-y-1.5 sm:col-span-2">
                              <span className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                                Token pessoal
                              </span>
                              <div className="relative">
                                <input
                                  type={showRocketToken ? "text" : "password"}
                                  value={settings.rocketChatAuthToken}
                                  onChange={(e) =>
                                    setSettings((c) => ({ ...c, rocketChatAuthToken: e.target.value }))
                                  }
                                  placeholder="X-Auth-Token ou Personal Access Token"
                                  className="w-full rounded-xl border border-glass-border bg-background/80 py-2.5 pl-3 pr-10 text-sm text-foreground font-mono outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowRocketToken((v) => !v)}
                                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                                  tabIndex={-1}
                                  aria-label={showRocketToken ? "Ocultar token" : "Mostrar token"}
                                >
                                  {showRocketToken
                                    ? <EyeOff className="h-4 w-4" />
                                    : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </label>
                          </div>
                          <p className="text-xs leading-5 text-muted-foreground">
                            Dica: no Rocket.Chat, gere um Personal Access Token nas preferências da sua conta. O AutoLiquid usa apenas leitura das suas inscrições para contar mensagens.
                          </p>
                          <div className="flex flex-col gap-2 rounded-xl border border-glass-border bg-background/70 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                            <p className="text-xs leading-5 text-muted-foreground">
                              Use o teste para confirmar se o token foi salvo e se a API retornou mensagens não lidas.
                            </p>
                            <GlassButton
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={handleTestarRocketChat}
                              disabled={testandoRocket}
                              className="shrink-0 border border-red-500/20 bg-background/80 text-foreground hover:bg-background"
                            >
                              {testandoRocket ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="h-4 w-4" />
                              )}
                              {testandoRocket ? "Testando..." : "Testar conexão"}
                            </GlassButton>
                          </div>
                          {resultadoRocket ? (
                            <div
                              className={[
                                "rounded-xl border px-3 py-2 text-sm",
                                resultadoRocket.toLowerCase().includes("conectado")
                                  ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700"
                                  : "border-amber-500/25 bg-amber-500/10 text-amber-800",
                              ].join(" ")}
                            >
                              {resultadoRocket}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </section>
                  </>
                )}

                {/* ── ABA SISTEMA ── */}
                {isModerator && abaAtiva === "sistema" && (
                  <>
                    <section className="rounded-2xl border border-sky-500/20 bg-sky-500/10 px-4 py-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-start gap-3">
                          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-sky-500/20 bg-background/80 text-sky-700">
                            <Database className="h-5 w-5" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-foreground">Sala de máquinas</p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              Ajustes que afetam automação, banco de dados e diagnósticos do sistema.
                            </p>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => abrirUrl(TURSO_DASHBOARD_URL)}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-500/20 bg-background/80 px-3 py-2 text-sm font-medium text-foreground transition hover:border-emerald-500/35 hover:bg-background"
                          >
                            <Globe className="h-4 w-4 text-emerald-700" />
                            Turso
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </button>
                        </div>
                      </div>
                    </section>

                    <section className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="flex items-start gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-emerald-500/20 bg-background/80 text-emerald-700">
                            <CalendarDays className="h-5 w-5" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-foreground">Datas globais</p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              Atualiza as datas globais no Turso e sincroniza as telas abertas.
                            </p>
                          </div>
                        </div>
                        {carregandoDatasGlobais ? (
                          <span className="inline-flex items-center gap-2 rounded-full border border-glass-border bg-background/70 px-3 py-1.5 text-xs text-muted-foreground">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Carregando
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Apuração</span>
                          <input
                            type="date"
                            value={datasGlobais.apuracao}
                            onChange={(event) => {
                              setMensagemDatasGlobais("");
                              setDatasGlobais((current) => ({ ...current, apuracao: event.target.value }));
                            }}
                            className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2.5 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                          />
                        </label>
                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Vencimento</span>
                          <input
                            type="date"
                            value={datasGlobais.vencimento}
                            onChange={(event) => {
                              setMensagemDatasGlobais("");
                              setDatasGlobais((current) => ({ ...current, vencimento: event.target.value }));
                            }}
                            className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2.5 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                          />
                        </label>
                        <GlassButton
                          type="button"
                          size="sm"
                          onClick={() => void handleSalvarDatasGlobais()}
                          disabled={carregandoDatasGlobais || salvandoDatasGlobais}
                          className="shrink-0"
                        >
                          {salvandoDatasGlobais ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                          {salvandoDatasGlobais ? "Salvando..." : "Salvar datas"}
                        </GlassButton>
                      </div>

                      {mensagemDatasGlobais ? (
                        <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700">
                          {mensagemDatasGlobais}
                        </div>
                      ) : null}
                      {erroDatasGlobais ? (
                        <div className="mt-3 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                          {erroDatasGlobais}
                        </div>
                      ) : null}
                    </section>

                    <section className="rounded-2xl border border-glass-border bg-secondary/25 px-4 py-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div className="flex items-start gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-glass-border bg-background/80 text-primary">
                            <Users className="h-5 w-5" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-foreground">Equipe e acesso</p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              Cadastro único para identificação, sorteio, ausências, senha e perfil. Diego é mantido como moderator.
                            </p>
                          </div>
                        </div>
                        {carregandoServidores || carregandoUsuarios ? (
                          <span className="inline-flex items-center gap-2 rounded-full border border-glass-border bg-background/70 px-3 py-1.5 text-xs text-muted-foreground">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            Carregando
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-4 overflow-hidden rounded-2xl border border-glass-border bg-background/70">
                        {equipeAcesso.length === 0 ? (
                          <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                            Nenhum servidor cadastrado.
                          </div>
                        ) : (
                          <div className="divide-y divide-glass-border">
                            {equipeAcesso.map(({ key, servidor, usuario }) => (
                              <div key={key} className="grid gap-3 px-3 py-3 lg:grid-cols-[minmax(0,1fr)_130px_210px_96px_auto] lg:items-center">
                                <div className="flex min-w-0 items-center gap-3">
                                  <span
                                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-glass-border bg-secondary/60 text-xs font-bold text-muted-foreground"
                                  >
                                    {servidor.nome.slice(0, 1).toUpperCase()}
                                  </span>
                                  <div className="min-w-0">
                                    <p className="truncate text-sm font-medium text-foreground">{servidor.nome}</p>
                                    {servidor.nomeCompleto && servidor.nomeCompleto !== servidor.nome ? (
                                      <p className="truncate text-xs text-muted-foreground">{servidor.nomeCompleto}</p>
                                    ) : null}
                                  </div>
                                </div>
                                {usuario ? (
                                  <>
                                    <select
                                      value={usuario.role}
                                      onChange={(event) =>
                                        void handleAtualizarUsuario(usuario, { role: event.target.value as "user" | "moderator" })
                                      }
                                      className="rounded-xl border border-glass-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary"
                                    >
                                      <option value="user">user</option>
                                      <option value="moderator">moderator</option>
                                    </select>
                                    <div className="flex items-center gap-2">
                                      <input
                                        value={usuario.senha}
                                        onChange={(event) => {
                                          setUsuariosAuth((current) =>
                                            current.map((item) => item.username === usuario.username ? { ...item, senha: event.target.value } : item)
                                          );
                                          setValidacaoUsuarios((current) => {
                                            const next = { ...current };
                                            delete next[usuario.username];
                                            return next;
                                          });
                                        }}
                                        onBlur={(event) => void handleAtualizarUsuario(usuario, { senha: event.currentTarget.value })}
                                        className="min-w-0 flex-1 rounded-xl border border-glass-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary"
                                        placeholder="Senha"
                                      />
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <button
                                            type="button"
                                            onClick={() => void handleAtualizarUsuario(usuario, { senha: null })}
                                            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-glass-border text-muted-foreground transition hover:text-foreground"
                                          >
                                            <RefreshCw className="h-4 w-4" />
                                          </button>
                                        </TooltipTrigger>
                                        <TooltipContent className="z-[210]">Gerar nova senha</TooltipContent>
                                      </Tooltip>
                                    </div>
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <button
                                          type="button"
                                          onClick={() => void handleValidarUsuario(usuario)}
                                          disabled={validandoUsuario === usuario.username}
                                          className={`inline-flex h-9 items-center justify-center gap-2 rounded-xl border px-3 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${
                                            validacaoUsuarios[usuario.username] === "ok"
                                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700"
                                              : validacaoUsuarios[usuario.username] === "erro"
                                                ? "border-destructive/30 bg-destructive/10 text-destructive"
                                                : "border-glass-border text-muted-foreground hover:text-foreground"
                                          }`}
                                        >
                                          {validandoUsuario === usuario.username ? (
                                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                          ) : (
                                            <CheckCircle2 className="h-3.5 w-3.5" />
                                          )}
                                          {validacaoUsuarios[usuario.username] === "ok" ? "Validado" : "Validar"}
                                        </button>
                                      </TooltipTrigger>
                                      <TooltipContent className="z-[210]">Validar autenticação</TooltipContent>
                                    </Tooltip>
                                  </>
                                ) : (
                                  <>
                                    <span className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-700">
                                      Sem acesso
                                    </span>
                                    <span />
                                    <span />
                                  </>
                                )}
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <button
                                      type="button"
                                      onClick={() => handleRemoverServidorSistema(servidor)}
                                      className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-glass-border text-muted-foreground transition hover:border-destructive/30 hover:text-destructive"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </button>
                                  </TooltipTrigger>
                                  <TooltipContent className="z-[210]">Remover servidor</TooltipContent>
                                </Tooltip>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="mt-4 grid gap-3 rounded-2xl border border-dashed border-glass-border bg-background/55 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Novo servidor</span>
                          <input
                            value={novoServidorNome}
                            onChange={(event) => setNovoServidorNome(event.target.value)}
                            onKeyDown={(event) => { if (event.key === "Enter") void handleAdicionarServidorSistema(); }}
                            placeholder="Nome usado no app"
                            className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2.5 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                          />
                        </label>
                        <GlassButton
                          type="button"
                          variant="secondary"
                          size="sm"
                          onClick={() => void handleAdicionarServidorSistema()}
                          disabled={!novoServidorNome.trim()}
                        >
                          <Plus className="h-4 w-4" />
                          Adicionar
                        </GlassButton>
                      </div>
                      {erroServidores ? (
                        <div className="mt-3 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                          {erroServidores}
                        </div>
                      ) : null}
                      {erroUsuarios ? (
                        <div className="mt-3 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                          {erroUsuarios}
                        </div>
                      ) : null}
                    </section>


                    <section className="rounded-2xl border border-glass-border bg-secondary/25 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-foreground">Tabelas no Turso</p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            22 tabelas ativas — migração completa. Todas as leituras e gravações usam o banco remoto Turso.
                          </p>
                        </div>
                        <span className="shrink-0 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                          100% Turso
                        </span>
                      </div>
                      <div className="mt-4 grid gap-2 sm:grid-cols-2">
                        {(
                          [
                            { group: "Fila", tables: ["fila_processos_atual", "fila_processos_alertas", "fila_processos_historico"] },
                            { group: "Equipe / Gestão", tables: ["servidores_config", "servidores", "ausencias"] },
                            { group: "Config", tables: ["tabelas_operacionais", "regras_operacionais", "datas_globais"] },
                            { group: "Histórico", tables: ["processos", "execucoes", "execucao_etapas", "execucao_pendencias", "notas_fiscais_execucao", "deducoes_execucao", "empenhos", "liquidacao_registros"] },
                            { group: "Cache / Interno", tables: ["cache_snapshots", "documentos_processados", "contrato_ic_de_para", "vpd_de_para", "uorg_de_para"] },
                          ] as const
                        ).map(({ group, tables }) => (
                          <div key={group} className="rounded-xl border border-glass-border bg-background/70 p-3">
                            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                              {group}
                              <span className="ml-1.5 rounded-full bg-secondary/80 px-1.5 py-0.5 text-[9px]">{tables.length}</span>
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {tables.map((t) => (
                                <span key={t} className="rounded-full bg-secondary/70 px-2 py-0.5 font-mono text-[10px] text-foreground/75">{t}</span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                      <p className="mt-3 text-xs leading-5 text-muted-foreground">
                        O schema é criado automaticamente na primeira conexão. As tabelas de cache e de/para são derivadas das tabelas operacionais e não precisam de manutenção manual.
                      </p>
                    </section>


                    {/* Turso */}
                    <section className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-4">
                      <div className="flex flex-col gap-4">
                        <div>
                          <div>
                            <p className="text-sm font-semibold text-foreground">
                              Turso / libSQL
                            </p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              Banco rápido para fila, alertas, servidores, ausências e tabelas operacionais, com cache local para abertura imediata.
                            </p>
                          </div>
                        </div>
                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                            Database URL
                          </span>
                          <input
                            value={settings.tursoDatabaseUrl}
                            onChange={(e) =>
                              setSettings((c) => ({ ...c, tursoDatabaseUrl: e.target.value }))
                            }
                            onBlur={() =>
                              setSettings((current) => {
                                const url = current.tursoDatabaseUrl.trim();
                                if (!url || url.includes("://")) {
                                  return { ...current, tursoDatabaseUrl: url };
                                }
                                return { ...current, tursoDatabaseUrl: `libsql://${url}` };
                              })
                            }
                            placeholder="libsql://seu-banco-usuario.turso.io"
                            className="w-full rounded-xl border border-glass-border bg-background/80 px-3 py-2.5 font-mono text-sm text-foreground outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15"
                          />
                        </label>
                        <label className="grid gap-1.5">
                          <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                            Auth token
                          </span>
                          <div className="relative">
                            <input
                              type={showTursoToken ? "text" : "password"}
                              value={settings.tursoAuthToken}
                              onChange={(e) =>
                                setSettings((c) => ({ ...c, tursoAuthToken: e.target.value }))
                              }
                              placeholder="Token gerado no Turso"
                              className="w-full rounded-xl border border-glass-border bg-background/80 py-2.5 pl-3 pr-10 font-mono text-sm text-foreground outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/15"
                            />
                            <button
                              type="button"
                              onClick={() => setShowTursoToken((v) => !v)}
                              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                              tabIndex={-1}
                              aria-label={showTursoToken ? "Ocultar token do Turso" : "Mostrar token do Turso"}
                            >
                              {showTursoToken
                                ? <EyeOff className="h-4 w-4" />
                                : <Eye className="h-4 w-4" />}
                            </button>
                          </div>
                        </label>
                      </div>
                    </section>

                    {/* Recarregar automação */}
                    <section className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-4">
                      <div className="flex items-start gap-3">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-emerald-500/20 bg-background/80 text-emerald-700 shadow-[0_16px_30px_-24px_rgba(16,185,129,0.8)]">
                          <RefreshCw className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <h3 className="text-sm font-semibold text-foreground">Recarregar automação</h3>
                              <p className="mt-1 text-sm text-muted-foreground">
                                Aplica alterações nos arquivos Python sem reiniciar o servidor.
                              </p>
                            </div>
                            <GlassButton
                              variant="ghost"
                              size="sm"
                              onClick={handleRecarregar}
                              disabled={recarregando}
                              className="border border-emerald-500/20 bg-background/80 text-foreground hover:bg-background shrink-0"
                            >
                              <RefreshCw className={`h-4 w-4 ${recarregando ? "animate-spin" : ""}`} />
                              {recarregando ? "Recarregando..." : "Recarregar"}
                            </GlassButton>
                          </div>
                          {msgRecarregar && (
                            <div className="mt-3 rounded-xl border border-emerald-500/20 bg-background/75 px-3 py-2 text-sm text-emerald-700">
                              {msgRecarregar}
                            </div>
                          )}
                        </div>
                      </div>
                    </section>
                  </>
                )}

                {abaAtiva === "avancado" && (
                  <>
                    {/* ── Debug: Detectar campos de paginação ── */}
                    <section className="rounded-2xl border border-violet-500/20 bg-violet-500/8 px-4 py-4">
                      <div className="flex items-start gap-3">
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-violet-500/20 bg-background/80 text-violet-600 shadow-[0_16px_30px_-24px_rgba(139,92,246,0.7)]">
                          {/* Ícone de aranha inline */}
                          <svg
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.6"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            className="h-5 w-5"
                          >
                            {/* corpo */}
                            <ellipse cx="12" cy="13" rx="3" ry="3.5" />
                            {/* cabeça */}
                            <circle cx="12" cy="8.5" r="1.8" />
                            {/* pernas esquerdas */}
                            <path d="M9 11.5 L5 9" />
                            <path d="M9 13 L4 13" />
                            <path d="M9 14.5 L5 17" />
                            {/* pernas direitas */}
                            <path d="M15 11.5 L19 9" />
                            <path d="M15 13 L20 13" />
                            <path d="M15 14.5 L19 17" />
                            {/* fio */}
                            <line x1="12" y1="6.7" x2="12" y2="3" />
                          </svg>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <h3 className="text-sm font-semibold text-foreground">
                                Diagnóstico de paginação
                              </h3>
                              <p className="mt-1 text-sm text-muted-foreground">
                                Inspeciona a página de apropriação no Chrome e copia o relatório de campos detectados para a área de transferência.
                              </p>
                            </div>
                            <GlassButton
                              variant="ghost"
                              size="sm"
                              onClick={handleDetectarPaginacao}
                              disabled={detectando}
                              className="shrink-0 border border-violet-500/20 bg-background/80 text-foreground hover:bg-background"
                            >
                              {detectando ? (
                                <>
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                  Detectando...
                                </>
                              ) : relatorioCopiado ? (
                                <>
                                  <Check className="h-4 w-4 text-emerald-600" />
                                  Copiado!
                                </>
                              ) : (
                                <>
                                  <Copy className="h-4 w-4" />
                                  Detectar e copiar
                                </>
                              )}
                            </GlassButton>
                          </div>
                          {erroDeteccao && (
                            <div className="mt-3 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                              {erroDeteccao}
                            </div>
                          )}
                          {relatorioTexto && (
                            <div className="mt-3 space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="text-xs text-muted-foreground">
                                  Relatório detectado — selecione tudo e copie (Ctrl+A → Ctrl+C)
                                </span>
                                <GlassButton
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 px-2 text-xs"
                                  onClick={() => { copiarTexto(relatorioTexto); setRelatorioCopiado(true); setTimeout(() => setRelatorioCopiado(false), 2000); }}
                                >
                                  <Copy className="h-3 w-3" />
                                  {relatorioCopiado ? "Copiado!" : "Copiar"}
                                </GlassButton>
                              </div>
                              <textarea
                                readOnly
                                value={relatorioTexto}
                                rows={8}
                                onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                                className="w-full rounded-xl border border-glass-border bg-zinc-950/80 px-3 py-2 font-mono text-[11px] text-emerald-400 outline-none resize-none"
                              />
                            </div>
                          )}
                        </div>
                      </div>
                    </section>

                    {/* ── Central de Bugs ── */}
                    <section className="rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-4">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-start gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-red-500/20 bg-background/80 text-red-600">
                            <Bug className="h-5 w-5" />
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-foreground">Central de bugs</p>
                            <p className="mt-1 text-sm text-muted-foreground">
                              Relatórios enviados pelos usuários. Marque como resolvido após corrigir.
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          {(carregandoBugs || exportandoBugs) && (
                            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                          )}
                          <SimpleTooltip content="Exportar relatório CSV" side="top">
                            <button
                              type="button"
                              onClick={() => void handleExportarBugs()}
                              disabled={exportandoBugs || carregandoBugs}
                              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground disabled:opacity-40"
                            >
                              <FileDown className="h-3.5 w-3.5" />
                            </button>
                          </SimpleTooltip>
                          <SimpleTooltip content="Recarregar" side="top">
                            <button
                              type="button"
                              onClick={handleRecarregarBugs}
                              disabled={carregandoBugs}
                              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground disabled:opacity-40"
                            >
                              <RefreshCw className="h-3.5 w-3.5" />
                            </button>
                          </SimpleTooltip>
                        </div>
                      </div>

                      {erroBugs && (
                        <p className="text-xs text-destructive px-1 pb-2">{erroBugs}</p>
                      )}

                      {!carregandoBugs && !erroBugs && bugReports.length === 0 && (
                        <p className="text-sm text-muted-foreground text-center py-4">
                          Nenhum bug em aberto.
                        </p>
                      )}

                      {bugReports.length > 0 && (
                        <div className="flex flex-col gap-2">
                          {bugReports.map((bug) => (
                            <div
                              key={bug.id}
                              className="rounded-xl border border-glass-border bg-background/70 px-3 py-3 flex flex-col gap-1.5"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="flex flex-col gap-0.5 min-w-0">
                                  <p className="text-sm text-foreground break-words">{bug.descricao}</p>
                                  <div className="flex flex-wrap gap-2 mt-1">
                                    {bug.pagina && (
                                      <span className="inline-flex items-center rounded-full border border-glass-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground font-mono">
                                        {bug.pagina}
                                      </span>
                                    )}
                                    {bug.servidorNome && (
                                      <span className="inline-flex items-center rounded-full border border-glass-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                                        {bug.servidorNome}
                                      </span>
                                    )}
                                    <span className="inline-flex items-center rounded-full border border-glass-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                                      {(parseDbTimestamp(bug.criadoEm) ?? new Date(bug.criadoEm)).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                                    </span>
                                  </div>
                                </div>
                                <div className="flex shrink-0 gap-1">
                                  <GlassButton
                                    variant="ghost"
                                    size="sm"
                                    className="text-emerald-600 hover:text-emerald-700 hover:bg-emerald-500/10"
                                    disabled={resolvendo === bug.id || excluindo === bug.id}
                                    onClick={() => {
                                      setResolvendo(bug.id);
                                      resolverBugReport(bug.id)
                                        .then(() => setBugReports((current) => current.filter((b) => b.id !== bug.id)))
                                        .catch(() => {/* silencioso */})
                                        .finally(() => setResolvendo(null));
                                    }}
                                  >
                                    {resolvendo === bug.id ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <Check className="h-3.5 w-3.5" />
                                    )}
                                    Resolvido
                                  </GlassButton>
                                  <SimpleTooltip content="Excluir" side="top">
                                  <GlassButton
                                    variant="ghost"
                                    size="sm"
                                    className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                                    disabled={excluindo === bug.id || resolvendo === bug.id}
                                    onClick={() => {
                                      setExcluindo(bug.id);
                                      deletarBugReport(bug.id)
                                        .then(() => setBugReports((current) => current.filter((b) => b.id !== bug.id)))
                                        .catch(() => {/* silencioso */})
                                        .finally(() => setExcluindo(null));
                                    }}
                                  >
                                    {excluindo === bug.id ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                      <Trash2 className="h-3.5 w-3.5" />
                                    )}
                                  </GlassButton>
                                  </SimpleTooltip>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </section>
                  </>
                )}

                {/* Erro */}
                {erro && (
                  <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {erro.includes("127.0.0.1:8000")
                      ? "A API web não respondeu. Inicie com ./iniciar_web.sh ou suba o uvicorn em 127.0.0.1:8000."
                      : erro}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="shrink-0 flex items-center justify-end gap-3 border-t border-glass-border px-5 py-3">
            <GlassButton variant="ghost" onClick={onClose} disabled={saving}>
              Cancelar
            </GlassButton>
            <GlassButton variant="primary" onClick={handleSave} disabled={loading || saving}>
              <Save className="h-4 w-4" />
              {saving ? "Salvando..." : "Salvar"}
            </GlassButton>
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
