"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownToLine,
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
  fetchDatasGlobais,
  loginAutoLiquid,
  fetchRocketChatNotifications,
  fetchServidoresConfig,
  openChromeSession,
  recarregarModulos,
  saveAppSettings,
  saveDatasGlobais,
  upsertServidorConfig,
  updateAuthUsuario,
  verificarAtualizacao,
  instalarAtualizacaoTauri,
  isTauriRuntime,
  abrirUrl,
  AUTO_LIQUID_REPO,
  AUTO_LIQUID_REPO_URL,
  deletarServidorConfig,
  type AppSettings,
  type AtualizacaoTauriInfo,
  type AuthUsuario,
  type ProcessDates,
  type ServidorConfigRemoto,
  type VersaoInfo,
} from "@/lib/data";
import { useAuth } from "@/lib/auth-context";

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
  databaseUrl: "",
  tursoDatabaseUrl: "",
  tursoAuthToken: "",
  databaseMode: "turso",
  nomeUsuario: "",
  nfServicoAlertaDiasUteis: 3,
  rocketChatUrl: "https://chat.ufsc.br",
  rocketChatUserId: "",
  rocketChatAuthToken: "",
  rocketChatContar: "tudo",
  dataSources: {
    fila_processos_atual: { supabase: false, turso: true },
    fila_processos_alertas: { supabase: false, turso: true },
    fila_processos_edicoes: { supabase: false, turso: true },
    servidores_config: { supabase: false, turso: true },
    tabelas_operacionais: { supabase: false, turso: true },
    datas_globais: { supabase: false, turso: true },
    processos: { supabase: false, turso: true },
    execucoes: { supabase: false, turso: true },
    empenhos: { supabase: false, turso: true },
    notas_fiscais_execucao: { supabase: false, turso: true },
    deducoes_execucao: { supabase: false, turso: true },
    execucao_pendencias: { supabase: false, turso: true },
    ausencias: { supabase: false, turso: true },
  },
};

const SUPABASE_PROJECT_URL = "https://supabase.com/dashboard/project/fxffsintfysatyglcmmi";
const TURSO_DASHBOARD_URL = "https://app.turso.tech";

type Aba = "basico" | "avancado" | "sistema";

const DATA_SOURCE_TABLES = [
  { key: "fila_processos_atual", label: "Fila atual", group: "Fila" },
  { key: "fila_processos_alertas", label: "Alertas da fila", group: "Fila" },
  { key: "fila_processos_edicoes", label: "Edições da fila", group: "Fila" },
  { key: "servidores_config", label: "Servidores", group: "Equipe" },
  { key: "tabelas_operacionais", label: "Tabelas operacionais", group: "Config" },
  { key: "datas_globais", label: "Datas globais", group: "Config" },
  { key: "processos", label: "Processos", group: "Histórico" },
  { key: "execucoes", label: "Execuções", group: "Histórico" },
  { key: "empenhos", label: "Empenhos", group: "Histórico" },
  { key: "notas_fiscais_execucao", label: "Notas fiscais", group: "Histórico" },
  { key: "deducoes_execucao", label: "Deduções", group: "Histórico" },
  { key: "execucao_pendencias", label: "Pendências", group: "Histórico" },
  { key: "ausencias", label: "Ausências", group: "Gestão" },
] as const;

const DEFAULT_DATAS_GLOBAIS: ProcessDates = {
  apuracao: "",
  vencimento: "",
};

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
  const [baixando, setBaixando] = useState(false);
  const [showDbUrl, setShowDbUrl] = useState(false);
  const [showTursoToken, setShowTursoToken] = useState(false);
  const [showRocketToken, setShowRocketToken] = useState(false);
  const [testandoRocket, setTestandoRocket] = useState(false);
  const [resultadoRocket, setResultadoRocket] = useState("");
  const [mostrarGuiaTurso, setMostrarGuiaTurso] = useState(false);
  const [servidoresSistema, setServidoresSistema] = useState<ServidorConfigRemoto[]>([]);
  const [usuariosAuth, setUsuariosAuth] = useState<AuthUsuario[]>([]);
  const [datasGlobais, setDatasGlobais] = useState<ProcessDates>(DEFAULT_DATAS_GLOBAIS);
  const [carregandoServidores, setCarregandoServidores] = useState(false);
  const [carregandoUsuarios, setCarregandoUsuarios] = useState(false);
  const [carregandoDatasGlobais, setCarregandoDatasGlobais] = useState(false);
  const [salvandoDatasGlobais, setSalvandoDatasGlobais] = useState(false);
  const [validandoUsuario, setValidandoUsuario] = useState("");
  const [validacaoUsuarios, setValidacaoUsuarios] = useState<Record<string, "ok" | "erro">>({});
  const [novoServidorNome, setNovoServidorNome] = useState("");
  const [erroServidores, setErroServidores] = useState("");
  const [erroUsuarios, setErroUsuarios] = useState("");
  const [erroDatasGlobais, setErroDatasGlobais] = useState("");
  const [mensagemDatasGlobais, setMensagemDatasGlobais] = useState("");
  const atualizacaoAutomaticaDisponivel = isTauriRuntime();

  useEffect(() => {
    if (!isOpen) return;

    let ativo = true;
    setAbaAtiva("basico");
    if (!isModerator) {
      setSistemaDesbloqueado(false);
    }
    setCliquesSistema(0);
    setInfoUpdate(null);

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
    return () => { ativo = false; };
  }, [isOpen, abaAtiva, isModerator]);

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
    setVerificandoUpdate(true);
    setErro("");
    setResultadoUpdate(null);
    try {
      if (isTauriRuntime()) {
        const resultado = await instalarAtualizacaoTauri();
        setResultadoUpdate(resultado);
        setInfoUpdate(null);
        return;
      }
      const info = await verificarAtualizacao();
      setInfoUpdate(info);
    } catch (error) {
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

  const dataSourcesForMode = (mode: "turso" | "supabase") =>
    Object.fromEntries(
      DATA_SOURCE_TABLES.map((table) => [
        table.key,
        { supabase: mode === "supabase", turso: mode === "turso" },
      ])
    ) as AppSettings["dataSources"];

  const setDatabaseModeExclusive = (mode: "turso" | "supabase") => {
    setSettings((current) => ({
      ...current,
      databaseMode: mode,
      dataSources: dataSourcesForMode(mode),
    }));
  };

  const toggleDataSource = (table: string, provider: "supabase" | "turso") => {
    setSettings((current) => {
      return {
        ...current,
        dataSources: {
          ...(current.dataSources ?? {}),
          [table]: {
            supabase: provider === "supabase",
            turso: provider === "turso",
          },
        },
      };
    });
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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className="absolute inset-0 bg-background/70 backdrop-blur-sm"
        onClick={onClose}
      />

      <div className="relative flex min-h-full items-start justify-center p-4 sm:items-center">
        <GlassCard
          className="relative z-10 pointer-events-auto w-full max-w-3xl overflow-hidden border-white/50 shadow-[0_28px_90px_-40px_rgba(15,23,42,0.35)]"
          contentClassName="flex max-h-[92vh] min-h-0 flex-col"
        >
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between border-b border-glass-border px-6 py-5">
            <div>
              <button
                type="button"
                onClick={handleTituloClick}
                className="text-left text-lg font-semibold text-foreground outline-none"
                title={isModerator && sistemaDesbloqueado ? "Sistema" : undefined}
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
          <div className="shrink-0 flex gap-1 border-b border-glass-border px-6 pt-3 pb-0">
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
          <div className="min-h-0 flex-1 overflow-y-scroll overscroll-contain px-6 py-5 [touch-action:pan-y]">
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
                                {atualizacaoAutomaticaDisponivel
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
                                ? atualizacaoAutomaticaDisponivel ? "Atualizando..." : "Verificando..."
                                : atualizacaoAutomaticaDisponivel ? "Verificar e instalar" : "Verificar"}
                            </GlassButton>
                          </div>

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
                              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Tag className="h-3.5 w-3.5" />
                                Versão atual: <span className="font-semibold text-foreground">v{infoUpdate.versao_atual}</span>
                              </div>
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
                                  O aplicativo está atualizado.
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
                            onClick={() => abrirUrl(SUPABASE_PROJECT_URL)}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-sky-500/20 bg-background/80 px-3 py-2 text-sm font-medium text-foreground transition hover:border-sky-500/35 hover:bg-background"
                          >
                            <Database className="h-4 w-4 text-sky-600" />
                            Supabase
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </button>
                          <button
                            type="button"
                            onClick={() => abrirUrl(TURSO_DASHBOARD_URL)}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-500/20 bg-background/80 px-3 py-2 text-sm font-medium text-foreground transition hover:border-emerald-500/35 hover:bg-background"
                          >
                            <Globe className="h-4 w-4 text-emerald-700" />
                            Turso
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setMostrarGuiaTurso((v) => !v)}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-glass-border bg-background/80 px-3 py-2 text-sm font-medium text-foreground transition hover:border-primary/35 hover:bg-background"
                          >
                            <Tag className="h-4 w-4 text-primary" />
                            Mapa de migração
                          </button>
                        </div>
                      </div>
                      {mostrarGuiaTurso ? (
                        <div className="mt-4 grid gap-3 md:grid-cols-3">
                          <div className="rounded-2xl border border-emerald-500/20 bg-background/80 p-3">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                              Turso local-first
                            </p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">
                              Dados que precisam abrir instantaneamente e podem sincronizar em segundo plano.
                            </p>
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {[
                                "fila_processos_atual",
                                "fila_processos_alertas",
                                "fila_processos_edicoes",
                                "servidores_config",
                                "tabelas_operacionais",
                                "datas_globais",
                              ].map((tabela) => (
                                <span key={tabela} className="rounded-full border border-emerald-500/15 bg-emerald-500/10 px-2 py-1 font-mono text-[10px] text-emerald-800">
                                  {tabela}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="rounded-2xl border border-sky-500/20 bg-background/80 p-3">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
                              Supabase/Postgres
                            </p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">
                              Mantém o histórico central, colaboração e consultas pesadas enquanto validamos o Turso.
                            </p>
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {[
                                "processos",
                                "execucoes",
                                "empenhos",
                                "notas_fiscais_execucao",
                                "deducoes_execucao",
                                "execucao_pendencias",
                                "ausencias",
                              ].map((tabela) => (
                                <span key={tabela} className="rounded-full border border-sky-500/15 bg-sky-500/10 px-2 py-1 font-mono text-[10px] text-sky-800">
                                  {tabela}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div className="rounded-2xl border border-amber-500/20 bg-background/80 p-3">
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">
                              Fase piloto
                            </p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">
                              Primeiro cache local da fila. Depois abstraímos o serviço para alternar Supabase/Turso sem quebrar o app.
                            </p>
                            <ol className="mt-3 space-y-1.5 text-xs leading-5 text-muted-foreground">
                              <li>1. Criar cache SQLite/libSQL local.</li>
                              <li>2. Mostrar fila do cache ao abrir.</li>
                              <li>3. Sincronizar remoto em segundo plano.</li>
                              <li>4. Migrar histórico só se o piloto compensar.</li>
                            </ol>
                          </div>
                        </div>
                      ) : null}
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
                                        title="Senha"
                                      />
                                      <button
                                        type="button"
                                        onClick={() => void handleAtualizarUsuario(usuario, { senha: null })}
                                        className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-glass-border text-muted-foreground transition hover:text-foreground"
                                        title="Gerar nova senha"
                                      >
                                        <RefreshCw className="h-4 w-4" />
                                      </button>
                                    </div>
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
                                      title="Validar autenticação"
                                    >
                                      {validandoUsuario === usuario.username ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : (
                                        <CheckCircle2 className="h-3.5 w-3.5" />
                                      )}
                                      {validacaoUsuarios[usuario.username] === "ok" ? "Validado" : "Validar"}
                                    </button>
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
                                <button
                                  type="button"
                                  onClick={() => handleRemoverServidorSistema(servidor)}
                                  className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-glass-border text-muted-foreground transition hover:border-destructive/30 hover:text-destructive"
                                  title="Remover servidor"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
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
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-foreground">Base de dados ativa</p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            Escolha para onde o app deve ler e gravar os dados operacionais.
                          </p>
                        </div>
                        <span className="rounded-full border border-glass-border bg-background/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                          {settings.databaseMode === "turso" ? "Turso" : "Supabase"}
                        </span>
                      </div>
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        {[
                          {
                            value: "turso" as const,
                            title: "Turso",
                            description: "Ativa Turso em todas as áreas remotas e desativa Supabase.",
                            icon: Globe,
                          },
                          {
                            value: "supabase" as const,
                            title: "Supabase",
                            description: "Ativa Postgres/Supabase em todas as áreas remotas e desativa Turso.",
                            icon: Database,
                          },
                        ].map((option) => {
                          const Icon = option.icon;
                          const active = settings.databaseMode === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => setDatabaseModeExclusive(option.value)}
                              className={[
                                "flex items-start gap-3 rounded-2xl border p-4 text-left transition",
                                active
                                  ? "border-primary/45 bg-primary/10 text-foreground shadow-sm"
                                  : "border-glass-border bg-background/70 text-muted-foreground hover:border-primary/25 hover:bg-background",
                              ].join(" ")}
                            >
                              <span className={[
                                "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border",
                                active ? "border-primary/30 bg-background text-primary" : "border-glass-border bg-secondary/50",
                              ].join(" ")}>
                                <Icon className="h-4 w-4" />
                              </span>
                              <span>
                                <span className="block text-sm font-semibold text-foreground">{option.title}</span>
                                <span className="mt-1 block text-xs leading-5">{option.description}</span>
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </section>

                    <section className="rounded-2xl border border-glass-border bg-secondary/25 px-4 py-4">
                      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            Fontes por tabela
                          </p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            Escolha uma fonte por área. Ativar uma desativa a outra, sem fallback silencioso.
                          </p>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground sm:w-48">
                          <span className="text-center">Supabase</span>
                          <span className="text-center">Turso</span>
                        </div>
                      </div>
                      <div className="mt-4 divide-y divide-glass-border overflow-hidden rounded-2xl border border-glass-border bg-background/70">
                        {DATA_SOURCE_TABLES.map((table) => {
                          const row = settings.dataSources?.[table.key] ?? { supabase: false, turso: false };
                          return (
                            <div key={table.key} className="grid grid-cols-[minmax(0,1fr)_96px] gap-3 px-3 py-2.5 sm:grid-cols-[72px_minmax(0,1fr)_96px_96px] sm:items-center">
                              <span className="hidden rounded-full bg-secondary/60 px-2 py-1 text-center text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground sm:inline">
                                {table.group}
                              </span>
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium text-foreground">{table.label}</p>
                                <p className="truncate font-mono text-[10px] text-muted-foreground">{table.key}</p>
                              </div>
                              {(["supabase", "turso"] as const).map((provider) => {
                                const enabled = Boolean(row[provider]);
                                return (
                                  <button
                                    key={provider}
                                    type="button"
                                    onClick={() => toggleDataSource(table.key, provider)}
                                    className={[
                                      "inline-flex items-center justify-center rounded-full border px-3 py-1.5 text-xs font-semibold transition",
                                      enabled
                                        ? provider === "supabase"
                                          ? "border-sky-500/25 bg-sky-500/10 text-sky-700 hover:bg-sky-500/15"
                                          : "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/15"
                                        : "border-glass-border bg-secondary/40 text-muted-foreground hover:bg-secondary/60",
                                    ].join(" ")}
                                  >
                                    {enabled ? "On" : "Off"}
                                  </button>
                                );
                              })}
                            </div>
                          );
                        })}
                      </div>
                      <p className="mt-3 text-xs leading-5 text-muted-foreground">
                        Os toggles controlam leitura e gravação remota da fila, tabelas de apoio, datas globais, ausências e histórico.
                      </p>
                    </section>

                    {/* URL do banco de dados */}
                    <section className="rounded-2xl border border-glass-border bg-secondary/25 px-4 py-4">
                      <div className="flex flex-col gap-3">
                        <div>
                          <p className="text-sm font-semibold text-foreground">
                            URL do banco de dados
                          </p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            Connection string do Supabase (
                            <code className="rounded bg-secondary/60 px-1 py-0.5 text-xs">
                              DATABASE_URL
                            </code>
                            ). Use para migrar ou alternar a fonte ativa para Supabase.
                          </p>
                        </div>
                        <div className="relative">
                          <input
                            id="database-url"
                            type={showDbUrl ? "text" : "password"}
                            value={settings.databaseUrl}
                            onChange={(e) =>
                              setSettings((c) => ({ ...c, databaseUrl: e.target.value }))
                            }
                            placeholder="postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
                            className="w-full rounded-xl border border-glass-border bg-background/80 py-2.5 pl-3 pr-10 text-sm text-foreground font-mono shadow-inner outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                          />
                          <button
                            type="button"
                            onClick={() => setShowDbUrl((v) => !v)}
                            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                            tabIndex={-1}
                            aria-label={showDbUrl ? "Ocultar URL" : "Mostrar URL"}
                          >
                            {showDbUrl
                              ? <EyeOff className="h-4 w-4" />
                              : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
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
          <div className="shrink-0 flex items-center justify-end gap-3 border-t border-glass-border px-6 py-4">
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
