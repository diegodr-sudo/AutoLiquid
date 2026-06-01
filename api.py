"""API FastAPI para integrar o frontend Next.js com a automacao Python."""

from __future__ import annotations

import sys

# Garante UTF-8 no stdout/stderr no Windows (evita UnicodeEncodeError com → ⚠ etc.)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import importlib
import asyncio
import base64
import hashlib
import html
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import inspect
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

# ── Carrega variáveis de ambiente do arquivo .env ─────────────────────────────
try:
    from dotenv import load_dotenv
    _env_candidates =[
        Path.home() / ".autoliquid" / ".env",
        Path(sys.executable).parent / ".env",
        Path(".env"),
    ]
    for _env_path in _env_candidates:
        if _env_path.exists():
            load_dotenv(_env_path)
            break
except Exception:
    pass

import requests
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.app_paths import CAMINHO_CONFIG, URL_INICIAL, caminho_recurso
from core.runtime_config import obter_datas_salvas, obter_porta_chrome, salvar_datas_processo

log = logging.getLogger(__name__)

# ── Injeta variáveis de config no ambiente (desenvolvimento local) ─────────────
try:
    from services.config_service import carregar_config_app as _carregar_cfg
    _cfg = _carregar_cfg() or {}
    if not os.getenv("TURSO_DATABASE_URL"):
        _turso_url = str(_cfg.get("turso_database_url") or "").strip()
        if _turso_url:
            os.environ["TURSO_DATABASE_URL"] = _turso_url
    if not os.getenv("TURSO_AUTH_TOKEN"):
        _turso_token = str(_cfg.get("turso_auth_token") or "").strip()
        if _turso_token:
            os.environ["TURSO_AUTH_TOKEN"] = _turso_token
    if not os.getenv("AUTO_LIQUID_NOME"):
        _nome = str(_cfg.get("nome_usuario") or "").strip()
        if _nome:
            os.environ["AUTO_LIQUID_NOME"] = _nome
except Exception:
    pass

DEFAULT_APP_VERSION = "0.0.0"


def _normalizar_app_version(valor: Any) -> str:
    return str(valor or "").strip().lstrip("v")


def _candidatos_version_file() -> list[Path]:
    base_dir = Path(__file__).resolve().parent
    candidatos = [base_dir / "VERSION"]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidatos.append(Path(meipass) / "VERSION")
    return candidatos


def _candidatos_tauri_conf() -> list[Path]:
    base_dir = Path(__file__).resolve().parent
    candidatos =[
        base_dir / "src-tauri" / "tauri.conf.json",
        base_dir / "tauri.conf.json",
    ]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        bundle_dir = Path(meipass)
        candidatos.extend([
                bundle_dir / "src-tauri" / "tauri.conf.json",
                bundle_dir / "tauri.conf.json",
            ]
        )
    return candidatos


def _obter_app_version() -> str:
    versao_env = _normalizar_app_version(os.getenv("AUTO_LIQUID_VERSION"))
    if versao_env:
        return versao_env
    for caminho in _candidatos_version_file():
        try:
            if caminho.exists():
                versao = _normalizar_app_version(caminho.read_text(encoding="utf-8"))
                if versao:
                    return versao
        except Exception:
            continue
    for caminho in _candidatos_tauri_conf():
        try:
            if not caminho.exists():
                continue
            config = json.loads(caminho.read_text(encoding="utf-8"))
            versao = _normalizar_app_version(config.get("version", ""))
            if versao:
                return versao
        except Exception:
            continue
    return DEFAULT_APP_VERSION


APP_VERSION = _obter_app_version()
app = FastAPI(title="Automacao DCF API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ETAPAS_BASE =[
    {"id": 0, "nome": "Apropriar Instrumento", "status": "aguardando", "icone": "ClipboardCheck"},
    {"id": 1, "nome": "Dados Básicos", "status": "aguardando", "icone": "FileText"},
    {"id": 2, "nome": "Principal com Orçamento", "status": "aguardando", "icone": "DollarSign"},
    {"id": 3, "nome": "Dedução", "status": "aguardando", "icone": "MinusCircle"},
    {"id": 4, "nome": "Dados de Pagamento", "status": "aguardando", "icone": "CreditCard"},
    {"id": 5, "nome": "Centro de Custo", "status": "aguardando", "icone": "Building"},
]

FILA_PROCESSOS_CACHE: dict[str, Any] = {
    "rows": [],
    "columns":[],
    "updatedAt": None,
}
SOLAR_FILA_TARGET_URL = "https://suporte.egestao.ufsc.br/pagamentos/index.xhtml"
FILA_EVENT_SUBSCRIBERS: set[Queue[str]] = set()
FILA_EVENT_SUBSCRIBERS_LOCK = Lock()
FILA_EVENT_LISTENER_LOCK = Lock()
FILA_EVENT_LISTENER_STARTED = False
FILA_REMOTE_WATCHER_LOCK = Lock()
FILA_REMOTE_WATCHER_STARTED = False
FILA_SNAPSHOT_DB_RETRY_AFTER = 0.0
FILA_SNAPSHOT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fila-snapshot")
FILA_SNAPSHOT_FUTURE = None
FILA_SNAPSHOT_FUTURE_LOCK = Lock()
SERVIDORES_SORTEIO_CACHE: dict[str, Any] = {
    "rows": None,
    "source": "empty",
    "updatedAt": 0.0,
}
SERVIDORES_SORTEIO_CACHE_LOCK = Lock()
SERVIDORES_SORTEIO_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="servidores-sorteio")
SERVIDORES_SORTEIO_FUTURE = None
SERVIDORES_SORTEIO_FUTURE_LOCK = Lock()


def _chrome_service():
    from services import chrome_service
    return chrome_service


def _web_config_service():
    from services import web_config_service
    return web_config_service


def _postgres_service():
    from services import postgres_service
    return postgres_service


def _local_cache_service():
    from services import local_cache_service
    return local_cache_service


def _turso_service():
    from services import turso_service
    return turso_service


def _fila_sorteio_service():
    from services import fila_sorteio_service
    return fila_sorteio_service


ISS_PORTAIS_CONFIG: dict[str, dict[str, str]] = {
    "curitibanos": {
        "nome": "Curitibanos",
        "url": "https://e-gov.betha.com.br/livroeletronico2/02022-064/login.faces?lastUrl=/contribuinte/main.faces",
        "login": "g.santana",
        "senha": "ufsc2025",
        "codigo": "8093",
    },
    "ararangua": {
        "nome": "Araranguá",
        "url": "https://ararangua.atende.net/autoatendimento/servicos/nfse",
        "login": "83899526000182",
        "senha": "dcf*UFSC2025",
        "codigo": "8027",
    },
    "barra-do-sul": {
        "nome": "Balneário Barra do Sul",
        "url": "https://nfse-balneariobarradosul.atende.net/autoatendimento/servicos/nfse?redirected=1",
        "login": "83899526000182",
        "senha": "Ufsc*2025",
        "codigo": "5549",
    },
    "gov-celso-ramos": {
        "nome": "Gov. Celso Ramos",
        "url": "https://www.prefeituramoderna.com.br/",
        "login": "1009",
        "senha": "dcfufsc1009",
        "codigo": "8465",
    },
}

_ISS_PORTAIS_CONFIG_KEY = "iss-portais-config"


def _carregar_portais_iss_config() -> dict[str, dict[str, str]]:
    """Carrega a configuração dos portais ISS do Turso; cai de volta para o padrão se não houver dados."""
    try:
        turso = _turso_service()
        rows = turso.obter_tabela_operacional(_ISS_PORTAIS_CONFIG_KEY)
        if rows:
            config = {
                item["id"]: {k: v for k, v in item.items() if k != "id"}
                for item in rows
                if item.get("id") and item.get("id") != "global"
            }
            # Preenche o campo 'codigo' a partir dos defaults para portais que ainda não o têm
            for pid, dados in config.items():
                if not str(dados.get("codigo", "") or "").strip():
                    default_codigo = ISS_PORTAIS_CONFIG.get(pid, {}).get("codigo", "")
                    if default_codigo:
                        dados["codigo"] = default_codigo
            return config
    except Exception:
        pass
    return {k: dict(v) for k, v in ISS_PORTAIS_CONFIG.items()}


def _salvar_portais_iss_config(config: dict[str, dict[str, str]]) -> None:
    """Persiste a configuração dos portais ISS no Turso."""
    turso = _turso_service()
    rows = [{"id": k, **v} for k, v in config.items()]
    turso.salvar_tabela_operacional(_ISS_PORTAIS_CONFIG_KEY, rows)


def _fonte_dados_habilitada(tabela: str, provedor: str) -> bool:
    try:
        return bool(_web_config_service().fonte_dados_habilitada(tabela, provedor))
    except Exception:
        return provedor == "turso"


def _fila_row_key_api(row: dict[str, Any]) -> str:
    numero_processo = str(row.get("Número Processo") or "").strip()
    sol_pagamento = str(row.get("Sol. Pagamento") or "").strip()
    return f"{numero_processo}::{sol_pagamento}"


def _mesclar_metadados_cache_fila(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata_keys = {
        "__responsavel_manual",
        "__responsavel_alterado",
        "__responsavel_alterado_por",
        "__responsavel_alterado_em",
        "__alertas_json",
        "__concluido",
        "__concluido_por",
        "__concluido_em",
    }
    cache_rows = FILA_PROCESSOS_CACHE.get("rows") or []
    metadata_by_key = {
        _fila_row_key_api(row): {key: row.get(key) for key in metadata_keys if key in row}
        for row in cache_rows
        if isinstance(row, dict)
    }
    merged: list[dict[str, Any]] = []
    for row in rows or []:
        next_row = dict(row)
        next_row.update(metadata_by_key.get(_fila_row_key_api(next_row), {}))
        merged.append(next_row)
    return merged


def _sincronizar_fila_postgres_async(rows: list[dict[str, Any]], updated_at: str | None, origem: str = "solar-headless") -> None:
    if not _fonte_dados_habilitada("fila_processos_atual", "supabase"):
        return

    snapshot_rows = [dict(row) for row in rows or []]

    def _run() -> None:
        global FILA_PROCESSOS_CACHE
        try:
            synced_rows = _postgres_service().salvar_snapshot_fila_processos(
                snapshot_rows,
                updated_at=updated_at,
                origem=origem,
            )
            synced_rows = _aplicar_sorteio_fila(synced_rows)
            columns = _colunas_fila(synced_rows)
            current_updated_at = str(FILA_PROCESSOS_CACHE.get("updatedAt") or "")
            if updated_at and current_updated_at and current_updated_at > updated_at:
                return
            FILA_PROCESSOS_CACHE = {
                "rows": synced_rows,
                "columns": columns,
                "updatedAt": updated_at,
            }
            try:
                _local_cache_service().salvar_fila_processos_snapshot(synced_rows, updated_at)
            except Exception:
                log.debug("Falha ao atualizar cache local após sincronizar Supabase", exc_info=True)
            _broadcast_fila_event({"type": "fila-atualizada", "updatedAt": updated_at, "source": "supabase-background"})
        except Exception:
            log.debug("Falha ao sincronizar cache da fila no Supabase", exc_info=True)

    Thread(target=_run, name="postgres-fila-sync", daemon=True).start()


def _sincronizar_fila_turso_async(rows: list[dict[str, Any]], updated_at: str | None) -> None:
    if not _fonte_dados_habilitada("fila_processos_atual", "turso"):
        return

    def _run() -> None:
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                turso.salvar_snapshot_fila(rows, updated_at)
        except Exception:
            log.debug("Falha ao sincronizar cache da fila no Turso", exc_info=True)

    Thread(target=_run, name="turso-fila-sync", daemon=True).start()


def _broadcast_fila_event(payload: dict[str, Any]) -> None:
    mensagem = json.dumps(payload, ensure_ascii=False)
    with FILA_EVENT_SUBSCRIBERS_LOCK:
        subscribers = list(FILA_EVENT_SUBSCRIBERS)
    for subscriber in subscribers:
        try:
            subscriber.put_nowait(mensagem)
        except Exception:
            continue


def _fila_event_listener_loop() -> None:
    while True:
        try:
            if not _fonte_dados_habilitada("fila_processos_atual", "supabase"):
                time.sleep(30)
                continue

            postgres_service = _postgres_service()
            if not postgres_service.postgres_habilitado():
                time.sleep(5)
                continue

            conn = postgres_service._get_connection(reuse=False)
            conn.autocommit = True
            with conn:
                with conn.cursor() as cur:
                    cur.execute("listen autoliquid_fila_updates")
                    for notify in conn.notifies(timeout=30):
                        try:
                            payload = json.loads(notify.payload or "{}")
                        except Exception:
                            payload = {"type": "fila-atualizada"}
                        _broadcast_fila_event(payload)
        except Exception:
            log.exception("Falha no listener em tempo real da fila")
            time.sleep(3)


def _ensure_fila_event_listener() -> None:
    global FILA_EVENT_LISTENER_STARTED
    if FILA_EVENT_LISTENER_STARTED:
        return
    with FILA_EVENT_LISTENER_LOCK:
        if FILA_EVENT_LISTENER_STARTED:
            return
        thread = Thread(target=_fila_event_listener_loop, name="fila-event-listener", daemon=True)
        thread.start()
        FILA_EVENT_LISTENER_STARTED = True


def _fila_remote_token() -> str | None:
    if _fonte_dados_habilitada("fila_processos_atual", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                return turso.obter_token_tempo_real_fila(timeout=2)
        except Exception:
            log.debug("Falha ao obter token de tempo real da fila no Turso", exc_info=True)
    if _fonte_dados_habilitada("fila_processos_atual", "supabase"):
        try:
            postgres = _postgres_service()
            if postgres.postgres_habilitado():
                return postgres.obter_token_tempo_real_fila()
        except Exception:
            log.debug("Falha ao obter token de tempo real da fila no PostgreSQL", exc_info=True)
    return None


def _refresh_fila_cache_remoto() -> dict[str, Any] | None:
    if _fonte_dados_habilitada("fila_processos_atual", "turso"):
        snapshot = _carregar_snapshot_fila_turso()
        if snapshot:
            return snapshot
    if _fonte_dados_habilitada("fila_processos_atual", "supabase"):
        return _carregar_snapshot_fila_postgres()
    return None


def _fila_remote_watcher_loop() -> None:
    last_token: str | None = None
    while True:
        try:
            token = _fila_remote_token()
            if token and last_token is None:
                last_token = token
                snapshot = _refresh_fila_cache_remoto()
                if snapshot:
                    _broadcast_fila_event({
                        "type": "fila-remota-atualizada",
                        "token": token,
                        "updatedAt": snapshot.get("updatedAt"),
                        "total": snapshot.get("total"),
                    })
            elif token and token != last_token:
                last_token = token
                snapshot = _refresh_fila_cache_remoto()
                _broadcast_fila_event({
                    "type": "fila-remota-atualizada",
                    "token": token,
                    "updatedAt": (snapshot or {}).get("updatedAt"),
                    "total": (snapshot or {}).get("total"),
                })
        except Exception:
            log.debug("Falha no watcher remoto da fila", exc_info=True)
        time.sleep(2)


def _ensure_fila_remote_watcher() -> None:
    global FILA_REMOTE_WATCHER_STARTED
    if FILA_REMOTE_WATCHER_STARTED:
        return
    with FILA_REMOTE_WATCHER_LOCK:
        if FILA_REMOTE_WATCHER_STARTED:
            return
        thread = Thread(target=_fila_remote_watcher_loop, name="fila-remote-watcher", daemon=True)
        thread.start()
        FILA_REMOTE_WATCHER_STARTED = True


def _carregar_snapshot_fila_postgres() -> dict[str, Any]:
    global FILA_PROCESSOS_CACHE

    if not _fonte_dados_habilitada("fila_processos_atual", "supabase"):
        return {
            "total": 0,
            "columns": [],
            "rows":[],
            "updatedAt": None,
            "source": "supabase-disabled",
        }

    snapshot_db = _postgres_service().obter_fila_processos_snapshot_atual()
    rows_db = _aplicar_sorteio_fila(_aplicar_de_para_contrato_ic(snapshot_db["rows"]))
    columns_db = _colunas_fila(rows_db)
    try:
        _local_cache_service().salvar_fila_processos_snapshot(rows_db, snapshot_db.get("updatedAt"))
    except Exception:
        log.debug("Falha ao atualizar cache local da fila", exc_info=True)
    _sincronizar_fila_turso_async(rows_db, snapshot_db.get("updatedAt"))
    FILA_PROCESSOS_CACHE = {
        "rows": rows_db,
        "columns": columns_db,
        "updatedAt": snapshot_db.get("updatedAt"),
    }
    _broadcast_fila_event(
        {
            "type": "fila-cache-atualizada",
            "updatedAt": snapshot_db.get("updatedAt"),
            "total": len(rows_db),
            "origem": "postgres",
        }
    )
    return {
        "total": len(rows_db),
        "columns": columns_db,
        "rows": rows_db,
        "updatedAt": snapshot_db.get("updatedAt"),
        "source": "postgres",
    }


def _carregar_snapshot_fila_turso() -> dict[str, Any] | None:
    global FILA_PROCESSOS_CACHE

    started_at = time.monotonic()
    try:
        turso = _turso_service()
        if not _fonte_dados_habilitada("fila_processos_atual", "turso") or not turso.turso_configurado():
            return None
        snapshot = turso.obter_snapshot_fila(timeout=2.5)
    except Exception as exc:
        log.warning("Falha ao carregar snapshot da fila no Turso: %s", exc)
        return None

    rows = _aplicar_sorteio_fila(_aplicar_de_para_contrato_ic(snapshot.get("rows") or[]))
    log.info(
        "Snapshot da fila no Turso carregado em %.0fms (%d linhas).",
        (time.monotonic() - started_at) * 1000,
        len(rows),
    )

    updated_at = snapshot.get("updatedAt")
    columns = _colunas_fila(rows)
    FILA_PROCESSOS_CACHE = {
        "rows": rows,
        "columns": columns,
        "updatedAt": updated_at,
    }
    try:
        _local_cache_service().salvar_fila_processos_snapshot(rows, updated_at)
    except Exception:
        log.debug("Falha ao atualizar cache local com snapshot do Turso", exc_info=True)

    _broadcast_fila_event({
        "type": "fila-cache-atualizada",
        "updatedAt": updated_at,
        "total": len(rows),
        "source": "turso",
    })

    return {
        "total": len(rows),
        "columns": columns,
        "rows": rows,
        "updatedAt": updated_at,
        "source": "turso",
    }


def _snapshot_fila_future():
    global FILA_SNAPSHOT_FUTURE
    with FILA_SNAPSHOT_FUTURE_LOCK:
        if FILA_SNAPSHOT_FUTURE is None or FILA_SNAPSHOT_FUTURE.done():
            FILA_SNAPSHOT_FUTURE = FILA_SNAPSHOT_EXECUTOR.submit(_carregar_snapshot_fila_turso)
        return FILA_SNAPSHOT_FUTURE


def _atualizar_fila_turso_background() -> None:
    if not _fonte_dados_habilitada("fila_processos_atual", "turso"):
        return
    Thread(target=_carregar_snapshot_fila_turso, name="turso-fila-refresh", daemon=True).start()


def _normalizar_servidores_sorteio(rows: list[Any]) -> list[dict[str, str]]:
    servidores: list[dict[str, str]] =[]
    for index, item in enumerate(rows or[]):
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        nome = str(item.get("nome") or "").strip()
        modo = str(item.get("modo") or "ativo").strip().lower()
        if modo not in {"ativo", "metade", "fora"}:
            modo = "ativo"
        servidor_id = str(item.get("id") or "").strip()
        if not servidor_id:
            servidor_id = f"server-{index + 1}"
        servidores.append({"id": servidor_id, "nome": nome, "modo": modo})
    return servidores


def _normalizar_cnpj(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _normalizar_regras_alerta_servico(config: Any) -> dict[str, Any]:
    if isinstance(config, BaseModel):
        config = config.model_dump()
    if not isinstance(config, dict):
        config = {}
    try:
        dias = int(config.get("diasUteisPadrao", config.get("dias_uteis_padrao", 3)) or 0)
    except (TypeError, ValueError):
        dias = 3
    dias = max(0, min(60, dias))

    def _normalizar_acao(value: Any) -> str:
        acao = str(value or "IGNORAR").strip().upper()
        return acao if acao in {"IGNORAR", "DIA_FIXO_MES_SEGUINTE", "DATA_PERSONALIZADA"} else "IGNORAR"

    def _normalizar_tipo(value: Any) -> str:
        tipo = str(value or "__TODOS__").strip()
        return tipo or "__TODOS__"

    def _rule(
        *,
        index: int,
        origem: str,
        item: dict[str, Any],
        acao: str,
        valor: str = "",
        setor_key: str = "setor",
    ) -> dict[str, Any] | None:
        cnpj = _normalizar_cnpj(item.get("cnpj"))
        setor = str(item.get(setor_key) or item.get("setorOrigem") or item.get("setor_origem") or "").strip()
        tipo = _normalizar_tipo(item.get("tipoDocumento") or item.get("tipo_documento"))
        regra_id = str(item.get("id") or f"{origem}-{index + 1}-{cnpj or 'todos'}-{setor.casefold() or 'todos'}").strip()
        normalized_acao = _normalizar_acao(item.get("acaoVencimento") or item.get("acao_vencimento") or acao)
        valor_acao = str(item.get("valorAcao") or item.get("valor_acao") or valor).strip()
        if normalized_acao == "IGNORAR":
            valor_acao = ""
        elif normalized_acao == "DIA_FIXO_MES_SEGUINTE":
            try:
                valor_acao = str(max(1, min(31, int(valor_acao or 20))))
            except (TypeError, ValueError):
                valor_acao = "20"
        elif normalized_acao == "DATA_PERSONALIZADA" and not valor_acao:
            return None
        return {
            "id": regra_id,
            "active": bool(item.get("active", item.get("ativo", True))),
            "tipoDocumento": tipo,
            "cnpj": cnpj,
            "setor": setor,
            "acaoVencimento": normalized_acao,
            "valorAcao": valor_acao,
        }

    def _lista_regras() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        raw_rules = config.get("regras")
        if isinstance(raw_rules, list):
            for index, item in enumerate(raw_rules):
                if isinstance(item, BaseModel):
                    item = item.model_dump()
                if not isinstance(item, dict):
                    continue
                rule = _rule(index=index, origem="regra", item=item, acao="IGNORAR")
                if not rule:
                    continue
                key = (
                    str(rule["tipoDocumento"]).casefold(),
                    str(rule["cnpj"]),
                    str(rule["setor"]).casefold(),
                    str(rule["acaoVencimento"]),
                    str(rule["valorAcao"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                out.append(rule)
            return out

        legacy_specs = [
            ("cnpjsExcluidos", "IGNORAR", ""),
            ("cnpjsIncluidos", "DIA_FIXO_MES_SEGUINTE", "20"),
            ("cnpjSetor10Dias", "DIA_FIXO_MES_SEGUINTE", "10"),
        ]
        for chave, acao, valor in legacy_specs:
            for index, item in enumerate(config.get(chave) or []):
                if isinstance(item, BaseModel):
                    item = item.model_dump()
                if not isinstance(item, dict):
                    continue
                cnpj = _normalizar_cnpj(item.get("cnpj"))
                if len(cnpj) != 14:
                    continue
                if chave == "cnpjSetor10Dias" and not str(item.get("setorOrigem") or "").strip():
                    continue
                rule = _rule(index=index, origem=chave, item=item, acao=acao, valor=valor, setor_key="setorOrigem")
                if rule:
                    out.append(rule)
        return out

    alertas_setor_raw = config.get("alertasSetor") or config.get("alertas_setor") or []
    alertas_setor: list[dict[str, Any]] = []
    seen_setores: set[str] = set()
    if isinstance(alertas_setor_raw, list):
        for index, item in enumerate(alertas_setor_raw):
            if isinstance(item, BaseModel):
                item = item.model_dump()
            if isinstance(item, str):
                item = {"setor": item}
            if not isinstance(item, dict):
                continue
            setor = str(item.get("setor") or "").strip()
            key = setor.casefold()
            if not setor or key in seen_setores:
                continue
            seen_setores.add(key)
            alertas_setor.append({
                "id": str(item.get("id") or f"setor-{index + 1}-{key}").strip(),
                "active": bool(item.get("active", item.get("ativo", True))),
                "setor": setor,
                "mensagem": str(item.get("mensagem") or "").strip(),
            })

    setores_raw = config.get("setoresAlerta") or config.get("setores_alerta") or []
    if isinstance(setores_raw, list):
        for item in setores_raw:
            setor = str(item or "").strip()
            key = setor.casefold()
            if setor and key not in seen_setores:
                seen_setores.add(key)
                alertas_setor.append({
                    "id": f"setor-{len(alertas_setor) + 1}-{key}",
                    "active": True,
                    "setor": setor,
                    "mensagem": "",
                })

    return {
        "diasUteisPadrao": dias,
        "regras": _lista_regras(),
        "alertasSetor": alertas_setor,
    }


def _carregar_regras_alerta_servico() -> tuple[dict[str, Any], str]:
    if _fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                rows = turso.obter_tabela_operacional("fila_alerta_servico_regras")
                if rows and isinstance(rows[0], dict):
                    return _normalizar_regras_alerta_servico(rows[0]), "turso"
        except Exception as exc:
            log.warning("Falha ao carregar regras do alerta de serviço no Turso: %s", exc)
    if _fonte_dados_habilitada("tabelas_operacionais", "supabase"):
        try:
            rows = _postgres_service().obter_tabela_operacional("fila_alerta_servico_regras")
            if rows and isinstance(rows[0], dict):
                return _normalizar_regras_alerta_servico(rows[0]), "postgres"
        except Exception as exc:
            log.warning("Falha ao carregar regras do alerta de serviço no PostgreSQL: %s", exc)
    try:
        dias = int(_web_config_service().carregar_configuracoes_web().get("nfServicoAlertaDiasUteis", 3) or 3)
    except Exception:
        dias = 3
    return _normalizar_regras_alerta_servico({"diasUteisPadrao": dias}), "default"


def _salvar_regras_alerta_servico(config: dict[str, Any]) -> str:
    errors: list[str] = []
    saved_sources: list[str] = []
    rows = [config]
    if _fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                turso.salvar_tabela_operacional("fila_alerta_servico_regras", rows)
                saved_sources.append("turso")
            else:
                errors.append("Turso: credenciais não configuradas")
        except Exception as exc:
            errors.append(f"Turso: {exc}")
    if _fonte_dados_habilitada("tabelas_operacionais", "supabase"):
        try:
            _postgres_service().salvar_tabela_operacional("fila_alerta_servico_regras", rows)
            saved_sources.append("postgres")
        except Exception as exc:
            errors.append(f"Supabase: {exc}")
    if saved_sources:
        return "+".join(saved_sources)
    if errors:
        raise RuntimeError("; ".join(errors))
    raise RuntimeError("Nenhuma fonte compartilhada está habilitada para salvar os alertas.")


DEDUCOES_DATAS_GRUPOS_PADRAO: list[dict[str, Any]] = [
    {
        "id": "ddf050-inss",
        "nome": "INSS",
        "codigos": ["1162", "1164"],
        "siafi": "DDF050",
        "diaVencimento": 20,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": False,
        "observacao": "DDF050 1162/1164: vencimento e pagamento no dia 20 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "ddf055-retencoes",
        "nome": "Retenções DDF055",
        "codigos": ["6147", "9060", "8739", "8767", "6175", "8850", "8863", "6188", "6190"],
        "siafi": "DDF055",
        "diaVencimento": None,
        "mesVencimento": "usuario",
        "apuracao": "usuario",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": False,
        "observacao": "DDF055: vencimento e apuração são informados pelo usuário no processo.",
    },
    {
        "id": "iss-florianopolis",
        "nome": "ISS Florianópolis",
        "codigos": ["8105"],
        "siafi": "DDR001",
        "diaVencimento": 20,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": False,
        "observacao": "DDR001 8105: dia 20 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "iss-blumenau",
        "nome": "ISS Blumenau",
        "codigos": ["8047"],
        "siafi": "DDR001",
        "diaVencimento": 10,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": False,
        "observacao": "DDR001 8047: dia 10 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "iss-joinville",
        "nome": "ISS Joinville",
        "codigos": ["8179"],
        "siafi": "DOB001",
        "diaVencimento": 20,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": False,
        "observacao": "DOB001 8179: dia 20 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "iss-curitibanos",
        "nome": "ISS Curitibanos",
        "codigos": ["8093"],
        "siafi": "DOB001",
        "diaVencimento": 20,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": True,
        "observacao": "DOB001 8093: dia 20 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "iss-ararangua",
        "nome": "ISS Araranguá",
        "codigos": ["8027"],
        "siafi": "DOB001",
        "diaVencimento": 20,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": True,
        "observacao": "DOB001 8027: dia 20 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "iss-barra-do-sul",
        "nome": "ISS Barra do Sul",
        "codigos": ["5549"],
        "siafi": "DOB001",
        "diaVencimento": 10,
        "mesVencimento": "seguinte",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": True,
        "observacao": "DOB001 5549: dia 10 do mês seguinte, seguindo o ajuste de dia não útil configurado.",
    },
    {
        "id": "iss-gov-celso-ramos",
        "nome": "ISS Gov. Celso Ramos",
        "codigos": ["8465"],
        "siafi": "DOB001",
        "diaVencimento": 20,
        "mesVencimento": "atual",
        "apuracao": "emissao_mais_antiga",
        "pagamento": "igual_vencimento",
        "ajusteDiaNaoUtil": "antecipar",
        "precisaLf": True,
        "observacao": "DOB001 8465: dia 20 do mesmo mês da NF, seguindo o ajuste de dia não útil configurado.",
    },
]

DEDUCOES_SIAFI_LEGADO_PARA_ATUAL = {
    "DDF021": "DDF050",
    "DDF025": "DDF055",
}

DEDUCOES_REGRAS_IDS_LEGADO_PARA_ATUAL = {
    "ddf021-inss": "ddf050-inss",
    "ddf025-retencoes": "ddf055-retencoes",
}


def _normalizar_siafi_deducao(value: Any) -> str:
    siafi = re.sub(r"[^A-Z0-9]", "", str(value or "").strip().upper())
    return DEDUCOES_SIAFI_LEGADO_PARA_ATUAL.get(siafi, siafi)


def _normalizar_texto_siafi_deducao(value: Any) -> str:
    text = str(value or "").strip()
    for legado, atual in DEDUCOES_SIAFI_LEGADO_PARA_ATUAL.items():
        text = re.sub(legado, atual, text, flags=re.IGNORECASE)
    return text


def _normalizar_deducao_extraida(deducao: dict[str, Any]) -> dict[str, Any]:
    next_deducao = dict(deducao or {})
    siafi_atual = _normalizar_siafi_deducao(next_deducao.get("Situação SIAFI") or next_deducao.get("Situação"))
    if siafi_atual:
        next_deducao["Situação SIAFI"] = siafi_atual
    next_deducao["Situação"] = _normalizar_texto_siafi_deducao(next_deducao.get("Situação"))
    return next_deducao


def _tem_siafi_deducao_legado(config: Any) -> bool:
    try:
        serialized = json.dumps(config, ensure_ascii=False, default=str).upper()
    except TypeError:
        serialized = str(config).upper()
    return any(legado in serialized for legado in DEDUCOES_SIAFI_LEGADO_PARA_ATUAL)


def _normalizar_regras_datas_deducoes(config: Any) -> dict[str, Any]:
    if isinstance(config, BaseModel):
        config = config.model_dump()
    if not isinstance(config, dict):
        config = {}

    raw_regras = config.get("regras")
    if not isinstance(raw_regras, list):
        raw_regras = DEDUCOES_DATAS_GRUPOS_PADRAO

    default_by_id = {str(item["id"]): item for item in DEDUCOES_DATAS_GRUPOS_PADRAO}
    regras: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_regras):
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        raw_rule_id = str(item.get("id") or f"regra-{index + 1}").strip()
        rule_id = DEDUCOES_REGRAS_IDS_LEGADO_PARA_ATUAL.get(raw_rule_id.lower(), raw_rule_id)
        base = default_by_id.get(rule_id, {})
        rule_id = str(rule_id or base.get("id") or f"regra-{index + 1}").strip()
        if not rule_id or rule_id in seen:
            continue
        seen.add(rule_id)
        codigos = [
            "".join(ch for ch in str(codigo or "") if ch.isdigit())
            for codigo in (item.get("codigos") or base.get("codigos") or [])
        ]
        codigos = [codigo for codigo in codigos if codigo]
        if not codigos:
            continue
        siafi = _normalizar_siafi_deducao(item.get("siafi") or base.get("siafi") or "")
        if not re.fullmatch(r"[A-Z]{3}[0-9]{3}", siafi):
            continue
        mes = str(item.get("mesVencimento") or item.get("mes") or base.get("mesVencimento") or "seguinte").strip().lower()
        if mes not in {"atual", "seguinte", "usuario"}:
            mes = "seguinte"
        try:
            dia = int(item.get("diaVencimento") if item.get("diaVencimento") not in {"", None} else base.get("diaVencimento") or 0)
        except (TypeError, ValueError):
            dia = 0
        dia_vencimento = None if mes == "usuario" else max(1, min(31, dia or 20))
        apuracao = str(item.get("apuracao") or base.get("apuracao") or "emissao_mais_antiga").strip()
        if apuracao not in {"emissao_mais_antiga", "usuario"}:
            apuracao = "emissao_mais_antiga"
        pagamento = str(item.get("pagamento") or base.get("pagamento") or "igual_vencimento").strip()
        if pagamento != "igual_vencimento":
            pagamento = "igual_vencimento"
        ajuste_dia_nao_util = str(item.get("ajusteDiaNaoUtil") or base.get("ajusteDiaNaoUtil") or "antecipar").strip().lower()
        if ajuste_dia_nao_util not in {"antecipar", "prorrogar", "manter"}:
            ajuste_dia_nao_util = "antecipar"
        regras.append({
            "id": rule_id,
            "nome": _normalizar_texto_siafi_deducao(item.get("nome") or base.get("nome") or rule_id),
            "codigos": codigos,
            "siafi": siafi,
            "diaVencimento": dia_vencimento,
            "mesVencimento": mes,
            "apuracao": apuracao,
            "pagamento": pagamento,
            "ajusteDiaNaoUtil": ajuste_dia_nao_util,
            "precisaLf": bool(item.get("precisaLf", base.get("precisaLf", False))),
            "observacao": _normalizar_texto_siafi_deducao(item.get("observacao") or base.get("observacao") or ""),
        })

    if not regras:
        return {"versao": 1, "regras": deepcopy(DEDUCOES_DATAS_GRUPOS_PADRAO)}
    return {"versao": 1, "regras": regras}


def _datas_deducoes_para_rows_datas_impostos(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for regra in config.get("regras") or []:
        apuracao = "Informado pelo usuário" if regra.get("apuracao") == "usuario" else "Data de emissão mais antiga das NFs"
        for codigo in regra.get("codigos") or []:
            rows.append({
                "imposto": regra.get("nome") or "",
                "codigo": codigo,
                "siafi": regra.get("siafi") or "",
                "dia": "" if regra.get("mesVencimento") == "usuario" else str(regra.get("diaVencimento") or ""),
                "mes": regra.get("mesVencimento") or "seguinte",
                "apuracao": apuracao,
                "ajusteDiaNaoUtil": regra.get("ajusteDiaNaoUtil") or "antecipar",
                "lf": "Sim" if regra.get("precisaLf") else "Não",
            })
    return rows


def _carregar_regras_datas_deducoes() -> tuple[dict[str, Any], str]:
    if _fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                rows = turso.obter_tabela_operacional("datas-deducoes-regras")
                if rows and isinstance(rows[0], dict):
                    source = "turso-legacy" if _tem_siafi_deducao_legado(rows[0]) else "turso"
                    return _normalizar_regras_datas_deducoes(rows[0]), source
        except Exception as exc:
            log.warning("Falha ao carregar regras de datas das deduções no Turso: %s", exc)
    return _normalizar_regras_datas_deducoes({"regras": DEDUCOES_DATAS_GRUPOS_PADRAO}), "default"


def _salvar_regras_datas_deducoes(config: dict[str, Any]) -> None:
    errors: list[str] = []
    rows = [config]
    expanded_rows = _datas_deducoes_para_rows_datas_impostos(config)
    if _fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                turso.salvar_tabela_operacional("datas-deducoes-regras", rows)
                turso.salvar_tabela_operacional("datas-impostos", expanded_rows)
        except Exception as exc:
            errors.append(f"Turso: {exc}")
    if _fonte_dados_habilitada("tabelas_operacionais", "supabase"):
        try:
            postgres = _postgres_service()
            postgres.salvar_tabela_operacional("datas-deducoes-regras", rows)
            postgres.salvar_tabela_operacional("datas-impostos", expanded_rows)
        except Exception as exc:
            errors.append(f"Supabase: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))


def _parse_data_iso_or_br(value: str) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _cache_servidores_sorteio(rows: list[dict[str, Any]], source: str) -> None:
    servidores = _normalizar_servidores_sorteio(rows)
    if not servidores:
        return
    with SERVIDORES_SORTEIO_CACHE_LOCK:
        SERVIDORES_SORTEIO_CACHE["rows"] = servidores
        SERVIDORES_SORTEIO_CACHE["source"] = source
        SERVIDORES_SORTEIO_CACHE["updatedAt"] = time.time()


def _obter_cache_servidores_sorteio() -> tuple[list[dict[str, Any]] | None, str]:
    with SERVIDORES_SORTEIO_CACHE_LOCK:
        rows = SERVIDORES_SORTEIO_CACHE.get("rows")
        source = str(SERVIDORES_SORTEIO_CACHE.get("source") or "cache")
    if isinstance(rows, list) and rows:
        return [dict(item) for item in rows if isinstance(item, dict)], f"{source}-cache"
    return None, "empty"


def _carregar_servidores_sorteio_remoto() -> tuple[list[dict[str, Any]] | None, str]:
    if _fonte_dados_habilitada("servidores_config", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                config = turso.obter_tabela_operacional("fila_servidores_sorteio") or []
                modos = {
                    str(item.get("nome") or "").casefold(): str(item.get("modo") or "fora")
                    for item in config
                    if isinstance(item, dict)
                }
                ids = {
                    str(item.get("nome") or "").casefold(): str(item.get("id") or f"server-{item.get('nome')}")
                    for item in config
                    if isinstance(item, dict)
                }
                rows = [
                    {
                        "id": ids.get(str(servidor.get("nome") or "").casefold(), f"server-{servidor.get('nome')}"),
                        "nome": str(servidor.get("nome") or "").strip(),
                        "modo": modos.get(str(servidor.get("nome") or "").casefold(), "fora"),
                    }
                    for servidor in turso.listar_servidores_config()
                    if str(servidor.get("nome") or "").strip()
                ]
                if not rows and config:
                    rows = [dict(item) for item in config if isinstance(item, dict)]
                return rows, "turso"
        except Exception as exc:
            log.warning("Falha ao carregar servidores do sorteio no Turso: %s", exc)
    if _fonte_dados_habilitada("servidores_config", "supabase"):
        try:
            return _postgres_service().obter_servidores_sorteio(), "postgres"
        except Exception as exc:
            log.warning("Falha ao carregar servidores do sorteio no PostgreSQL: %s", exc)
    return None, "empty"


def _refresh_servidores_sorteio_background() -> None:
    global SERVIDORES_SORTEIO_FUTURE
    started_at = time.time()

    def _done(future) -> None:
        global SERVIDORES_SORTEIO_FUTURE
        try:
            rows, source = future.result()
            if rows:
                with SERVIDORES_SORTEIO_CACHE_LOCK:
                    cache_updated_at = float(SERVIDORES_SORTEIO_CACHE.get("updatedAt") or 0)
                if cache_updated_at > started_at:
                    return
                _cache_servidores_sorteio(rows, source)
                _broadcast_fila_event({"type": "servidores-sorteio-atualizados"})
        except Exception:
            log.debug("Falha ao atualizar cache de servidores do sorteio", exc_info=True)
        finally:
            with SERVIDORES_SORTEIO_FUTURE_LOCK:
                if SERVIDORES_SORTEIO_FUTURE is future:
                    SERVIDORES_SORTEIO_FUTURE = None

    with SERVIDORES_SORTEIO_FUTURE_LOCK:
        if SERVIDORES_SORTEIO_FUTURE is not None and not SERVIDORES_SORTEIO_FUTURE.done():
            return
        SERVIDORES_SORTEIO_FUTURE = SERVIDORES_SORTEIO_EXECUTOR.submit(_carregar_servidores_sorteio_remoto)
        SERVIDORES_SORTEIO_FUTURE.add_done_callback(_done)


def _servidores_sorteio_raw() -> list[dict[str, Any]]:
    cached, _source = _obter_cache_servidores_sorteio()
    if cached:
        return cached
    _refresh_servidores_sorteio_background()
    return []


def _aplicar_sorteio_fila(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        return _fila_sorteio_service().aplicar_sorteio_rows(rows, _servidores_sorteio_raw())
    except Exception:
        log.debug("Falha ao aplicar sorteio da fila no backend", exc_info=True)
        return rows


def _salvar_alerta_fila_background(
    numero_processo: str,
    sol_pagamento: str,
    mensagem: str,
) -> None:
    try:
        _postgres_service().salvar_alerta_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            mensagem=mensagem,
        )
    except Exception:
        log.exception("Falha ao salvar alerta da fila em segundo plano")


def _comprasnet_base():
    import comprasnet.base as comprasnet_base
    return comprasnet_base


def _consulta_cnpj():
    import core.consulta_cnpj as consulta_cnpj
    return consulta_cnpj


def _extrator():
    import core.extrator as extrator
    return extrator


def _datas_impostos():
    import core.datas_impostos as datas_impostos
    return datas_impostos


def _jwt_secret() -> bytes:
    cfg_secret = ""
    try:
        cfg = _web_config_service().carregar_configuracoes_web()
        cfg_secret = str(cfg.get("tursoAuthToken") or "").strip()
    except Exception:
        cfg_secret = ""
    secret = cfg_secret or os.getenv("TURSO_AUTH_TOKEN") or os.getenv("AUTO_LIQUID_JWT_SECRET") or "autoliquid-local"
    return secret.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _jwt_encode(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(_jwt_secret(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


class ExecucaoInterrompida(Exception):
    """Sinaliza interrupção cooperativa de uma etapa em andamento."""


class TableSaveRequest(BaseModel):
    rows: list[dict[str, Any]]


class WebConfigPayload(BaseModel):
    chromePorta: int
    navegador: str = "chrome"
    fecharAbaFila: bool = False
    perguntarLimparMes: bool
    temaWeb: str = "light"
    nivelLog: str = "desenvolvedor"
    tursoDatabaseUrl: str = ""
    tursoAuthToken: str = ""
    nomeUsuario: str = ""
    nfServicoAlertaDiasUteis: int = 3
    tiposDocumentoLf: list[str] = Field(default_factory=lambda: ["NF Serviço", "Fatura", "Boleto"])
    rocketChatUrl: str = "https://chat.ufsc.br"
    rocketChatUserId: str = ""
    rocketChatAuthToken: str = ""
    rocketChatContar: str = "tudo"


class ChromeOpenResponse(BaseModel):
    success: bool
    chromeStatus: str
    chromePorta: int
    url: str
    mensagem: str


class ExecucaoPayload(BaseModel):
    lfNumero: str = ""
    ugrNumero: str = ""
    vencimentoDocumento: str = ""
    usarContaPdf: bool = True
    contaBanco: str = ""
    contaAgencia: str = ""
    contaConta: str = ""
    vpd: str = ""
    dataApuracao: str = ""
    dataVencimento: str = ""
    codigoOperacional: str = ""


class PendenciaResolvidaPayload(BaseModel):
    resolvida: bool = True


class ProcessDatesPayload(BaseModel):
    apuracao: str = ""
    vencimento: str = ""


class RegistroLiquidacaoPayload(BaseModel):
    documentoId: str = ""
    numeroProcesso: str = ""
    finalizada: bool = False
    tipoDocumento: str = ""
    numeroDocumento: str = ""
    dificuldade: float = 1
    servidorNome: str = ""
    servidorUsername: str = ""


class HistoricoSearchPayload(BaseModel):
    cnpj: str = ""
    contrato: str = ""
    contratos: list[str] = []
    numero_processo: str = ""
    empenho: str = ""


class FilaProcessosResponse(BaseModel):
    total: int
    columns: list[str]
    rows: list[dict[str, Any]]
    updatedAt: str | None = None
    source: str = "solar-headless"


class FilaResponsavelPayload(BaseModel):
    numeroProcesso: str = ""
    solPagamento: str = ""
    responsavel: str = ""


class FilaAlertaPayload(BaseModel):
    numeroProcesso: str = ""
    solPagamento: str = ""
    mensagem: str = ""


class FilaConclusaoPayload(BaseModel):
    numeroProcesso: str = ""
    solPagamento: str = ""
    concluido: bool = False


class AbrirProcessoSolarPayload(BaseModel):
    numeroProcesso: str = ""


class QueueServerPayload(BaseModel):
    id: str = ""
    nome: str = ""
    modo: str = "ativo"


class QueueServersPayload(BaseModel):
    servidores: list[QueueServerPayload] =[]


class AlertaServicoRulePayload(BaseModel):
    id: str = ""
    active: bool = True
    tipoDocumento: str = "__TODOS__"
    cnpj: str = ""
    setor: str = ""
    acaoVencimento: str = "IGNORAR"
    valorAcao: str = ""


class AlertaSetorRulePayload(BaseModel):
    id: str = ""
    active: bool = True
    setor: str = ""
    mensagem: str = ""


class AlertaServicoConfigPayload(BaseModel):
    diasUteisPadrao: int = 3
    regras: list[AlertaServicoRulePayload] = []
    alertasSetor: list[AlertaSetorRulePayload] = []
    setoresAlerta: list[str] = []


class RegraDataDeducaoPayload(BaseModel):
    id: str = ""
    nome: str = ""
    codigos: list[str] = []
    siafi: str = ""
    diaVencimento: int | None = None
    mesVencimento: str = "seguinte"
    apuracao: str = "emissao_mais_antiga"
    pagamento: str = "igual_vencimento"
    ajusteDiaNaoUtil: str = "antecipar"
    precisaLf: bool = False
    observacao: str = ""


class RegrasDatasDeducoesPayload(BaseModel):
    versao: int = 1
    regras: list[RegraDataDeducaoPayload] = []


class SimularRegraDataDeducaoPayload(BaseModel):
    regraId: str = ""
    dataEmissao: str = ""


class LoginPayload(BaseModel):
    username: str = ""
    password: str = ""


class UsuarioAuthPayload(BaseModel):
    username: str = ""
    role: str | None = None
    senha: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _brl_para_float(s: str) -> float:
    try:
        txt = str(s or "0").strip()
        if not txt or txt in ("-", "—"):
            return 0.0
        last_dot   = txt.rfind(".")
        last_comma = txt.rfind(",")
        if last_comma > last_dot:
            return float(txt.replace(".", "").replace(",", "."))
        elif last_dot > last_comma:
            return float(txt.replace(",", ""))
        else:
            return float(txt.replace(".", "").replace(",", "."))
    except Exception:
        return 0.0


def _colunas_fila(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    first_row = rows[0]
    return[str(key) for key in first_row.keys() if not str(key).startswith("__")]


def _normalizar_sarf_fila(contrato: str) -> str:
    texto = str(contrato or "").strip()
    match = re.match(r"^(\d+)/(\d{4})$", texto)
    if match:
        return f"{match.group(2)}{match.group(1).zfill(5)}"
    return texto.upper()


def _aplicar_de_para_contrato_ic(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    try:
        mapa_ic = _web_config_service().carregar_contratos_ic_de_para(somente_local=True)
    except Exception:
        log.debug("Falha ao carregar de/para Contrato → IC da fila", exc_info=True)
        return rows
    if not mapa_ic:
        return rows

    enriquecidas: list[dict[str, Any]] =[]
    for row in rows:
        next_row = dict(row)
        contrato = str(next_row.get("Contrato") or "").strip()
        ic_atual = str(next_row.get("IC") or "").strip()
        if contrato and not ic_atual:
            ig = mapa_ic.get(_normalizar_sarf_fila(contrato))
            if ig:
                next_row["IC"] = ig
                next_row["__ic_origem"] = "de_para"
        enriquecidas.append(next_row)
    return enriquecidas


def _atualizar_etapa(doc_id: str, etapa_id: int, status: str) -> None:
    doc = _local_cache_service().obter_documento(doc_id)
    if not doc: return
    for etapa in doc["etapas"]:
        if str(etapa["id"]) == str(etapa_id):
            etapa["status"] = status
            break
    _local_cache_service().salvar_documento(doc_id, doc)


def _log(doc_id: str, mensagem: str) -> None:
    doc = _local_cache_service().obter_documento(doc_id)
    if not doc: return
    doc["logs"].append(mensagem)
    _local_cache_service().salvar_documento(doc_id, doc)


def _log_s(doc_id: str, mensagem: str) -> None:
    doc = _local_cache_service().obter_documento(doc_id)
    if not doc: return
    doc["logs_simples"].append(mensagem)
    _local_cache_service().salvar_documento(doc_id, doc)


def _s_campo(dados: dict, *chaves: str) -> str:
    for chave in chaves:
        v = dados.get(chave)
        if v is not None:
            return str(v).strip()
        try:
            garbled = chave.encode("utf-8").decode("latin-1")
            v = dados.get(garbled)
            if v is not None:
                return str(v).strip()
        except Exception:
            pass
    return ""


def _valor_ou_traco(valor: Any) -> str:
    texto = str(valor or "").strip()
    if not texto or texto.lower() == "não encontrado":
        return "—"
    return texto


def _normalizar_texto_legivel(valor: str) -> str:
    return (
        str(valor or "")
        .replace("DeduÃ§Ã£o", "Dedução")
        .replace("ExecuÃ§Ã£o", "Execução")
        .replace("ConfirmaÃ§Ã£o", "Confirmação")
        .replace("SituaÃ§Ã£o", "Situação")
        .replace("nÃ£o", "não")
        .replace("NÃ£o", "Não")
        .replace("estÃ¡", "está")
        .replace("CÃ³digo", "Código")
        .replace("MunicÃ­pio", "Município")
        .replace("Ã¡", "á")
        .replace("Ã¢", "â")
        .replace("Ã£", "ã")
        .replace("Ã§", "ç")
        .replace("Ã©", "é")
        .replace("Ãª", "ê")
        .replace("Ã­", "í")
        .replace("Ã³", "ó")
        .replace("Ã´", "ô")
        .replace("Ãµ", "õ")
        .replace("Ãº", "ú")
        .replace("Âº", "º")
        .replace("Âª", "ª")
        .strip()
    )


def _detalhar_erro_execucao(nome: str, exc: Exception | str) -> str:
    bruto = _normalizar_texto_legivel(str(exc or "")).strip()
    normalizado = _normalizar_texto_status(bruto)

    if not bruto:
        return f"{nome}: erro sem detalhe retornado pela automação."

    # Mensagens de conferência manual já vêm formatadas com as linhas de
    # comparação PDF × IC que o painel sabe renderizar. Não reescrever (mesmo
    # que o "motivo técnico" contenha expressões como "não encontrado").
    if "requer conferencia manual" in normalizado:
        return f"{nome}: {bruto}"

    if "confirmar dados de pagamento" in normalizado and "nao encontrado" in normalizado:
        return (
            f"{nome}: o botão de confirmação final dos dados de pagamento não apareceu na tela. "
            f"Detalhe: {bruto}"
        )

    if "timeout" in normalizado or "exceeded" in normalizado:
        return (
            f"{nome}: o portal demorou mais do que o esperado para responder. "
            f"Detalhe: {bruto}"
        )

    if "nao encontrado" in normalizado or "não encontrado" in bruto.lower():
        return (
            f"{nome}: um campo, botão ou bloco esperado não foi localizado na página. "
            f"Detalhe: {bruto}"
        )

    if "falha ao coletar documentos de origem" in normalizado:
        return (
            f"{nome}: os documentos de origem não puderam ser lidos corretamente no portal. "
            f"Detalhe: {bruto}"
        )

    return f"{nome}: {bruto}"


def _gerar_logs_simples_conferencia(dados: dict) -> list:
    return[]


def _gerar_logs_etapa_sucesso(dados: dict, etapa_id: int, venc: str = "") -> list:
    msgs: list =[]

    if etapa_id == 0:
        msgs.append("HEADER Apropriar Instrumento")
        msgs.append("OK Instrumento de cobrança pesquisado e apropriado com sucesso")

    elif etapa_id == 1:
        msgs.append("HEADER Dados Básicos")

        ateste = _s_campo(dados, "Data de Ateste")
        if ateste:
            msgs.append(f"OK Data de ateste conferida — {ateste}")

        cnpj = _s_campo(dados, "CNPJ")
        if cnpj:
            msgs.append(f"OK CNPJ {cnpj} conferido")

        processo = _s_campo(dados, "Processo")
        if processo:
            msgs.append(f"OK Processo {processo} conferido")

        for nf in dados.get("Notas Fiscais",[]):
            num    = _s_campo(nf, "Número da Nota", "Nº", "N.Nota", "Numero da Nota")
            valor  = _s_campo(nf, "Valor")
            emissao = _s_campo(nf, "Data de Emissão", "Emissão")
            tipo   = _s_campo(nf, "Tipo") or "NF"
            label  = f"{tipo} {num}".strip() if num else tipo
            if valor and valor not in ("0", "0,00"):
                linha = f"{label} — {valor}" + (f" — emissão {emissao}" if emissao else "")
            elif emissao:
                linha = f"{label} — emissão {emissao}"
            else:
                linha = label
            msgs.append(f"OK {linha} conferida")

    elif etapa_id == 2:
        msgs.append("HEADER Principal com Orçamento")
        resumo = dados.get("Resumo", {})
        bruto = _s_campo(resumo, "Valor Bruto")
        if bruto and bruto not in ("0", "0,00"):
            msgs.append(f"OK Crédito {bruto} registrado")
        else:
            msgs.append("OK Crédito principal registrado")

    elif etapa_id == 3:
        msgs.append("HEADER Deduções")
        deducoes = dados.get("Deduções",[])
        if not deducoes:
            msgs.append("OK Deduções registradas")
        for ded in deducoes:
            siafi    = _s_campo(ded, "Situação SIAFI")
            tipo_ded = _s_campo(ded, "Situação") or "Dedução"
            valor_ded = _s_campo(ded, "Valor")
            label = f"{siafi} — {tipo_ded}" if siafi else tipo_ded
            if valor_ded and valor_ded not in ("0", "0,00"):
                msgs.append(f"OK {label} — {valor_ded} registrada")
            else:
                msgs.append(f"OK {label} registrada")

    elif etapa_id == 4:
        msgs.append("HEADER Dados de Pagamento")
        if venc:
            msgs.append(f"OK Vencimento {venc} preenchido")
        msgs.append("OK Dados de pagamento preenchidos")

    elif etapa_id == 5:
        msgs.append("HEADER Centro de Custo")
        msgs.append("OK Centro de custo preenchido")

    return msgs


def _normalizar_texto_status(valor: str) -> str:
    return (
        unicodedata.normalize("NFD", str(valor or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


def _montar_pendencias_documento(
    dados: dict,
    dados_extraidos: dict,
    deducoes: list[dict[str, Any]],
    etapas: list[dict[str, Any]],
    tipo_operacional: str = "",
) -> list[dict[str, Any]]:
    pendencias: list[dict[str, Any]] =[]
    vistos: set[tuple[str, str]] = set()
    pendencias_resolvidas = {
        str(item or "").strip()
        for item in (dados.get("pendencias_resolvidas") or [])
        if str(item or "").strip()
    }

    def adicionar(tipo: str, titulo: str, descricao: str, origem: str = "automacao") -> None:
        chave = (tipo, titulo.strip())
        if not titulo.strip() or chave in vistos:
            return
        vistos.add(chave)
        pendencia_id = "p-" + hashlib.sha1(
            f"{tipo}|{origem}|{titulo.strip()}|{descricao.strip()}".encode("utf-8")
        ).hexdigest()[:16]
        pendencias.append(
            {
                "id": pendencia_id,
                "tipo": tipo,
                "titulo": titulo.strip(),
                "descricao": descricao.strip(),
                "origem": origem,
                "resolvida": pendencia_id in pendencias_resolvidas,
            }
        )

    if dados.get("requires_centro_custo") and not str(dados.get("ugr_numero", "") or "").strip():
        adicionar(
            "bloqueio",
            "UGR não informada",
            "Necessário para preencher o Centro de Custo. O número da UGR está na solicitação de pagamento.",
            "configuracao",
        )

    if any(str(ded.get("siafi", "") or "") == "DOB001" for ded in deducoes) and not str(
        dados.get("lf_numero", "") or ""
    ).strip():
        _dob001_codes = sorted({
            str(ded.get("codigo", "") or "").strip()
            for ded in deducoes
            if str(ded.get("siafi", "") or "") == "DOB001"
            and str(ded.get("codigo", "") or "").strip() not in ("", "—", "0")
        })
        _codes_str = f" Códigos municipais: {', '.join(_dob001_codes)}." if _dob001_codes else ""
        adicionar(
            "bloqueio",
            "LF obrigatória para a OB",
            f"Há dedução DOB001 no documento e o número da LF ainda não foi preenchido.{_codes_str}",
            "configuracao",
        )

    empenhos_raw = dados_extraidos.get("Empenhos",[]) or[]
    if empenhos_raw:
        situacao_empenho = str(empenhos_raw[0].get("Situação", "") or "")
        try:
            base = _comprasnet_base()
            tipo_liquidacao = (
                base.extrair_siafi_completo(situacao_empenho)
                or base.extrair_codigo_situacao(situacao_empenho)
                or ""
            )
        except Exception:
            tipo_liquidacao = situacao_empenho
        tipo_liquidacao_norm = _normalizar_texto_status(tipo_liquidacao).upper()
        if tipo_liquidacao_norm in {"DSP201", "201"}:
            _natureza = str(dados_extraidos.get("Natureza", "") or "").strip()
            _subitem = _natureza.split(".")[-1] if "." in _natureza else "??"
            _bens_almox = "1.2.3.1.1.08.01"
            try:
                from services.config_service import carregar_tabelas_config as _ctc
                _tabelas = _ctc()
                _nat_bens = _tabelas.get("natureza_bens_moveis", {})
                _NATUREZA_PADRAO_IMB = {
                    "449052.04": "1.2.3.1.1.01.01", "449052.06": "1.2.3.1.1.01.02",
                    "449052.08": "1.2.3.1.1.01.03", "449052.10": "1.2.3.1.1.01.04",
                    "449052.12": "1.2.3.1.1.03.01", "449052.18": "1.2.3.1.1.04.02",
                    "449052.20": "1.2.3.1.1.05.06", "449052.24": "1.2.3.1.1.01.05",
                    "449052.28": "1.2.3.1.1.01.06", "449052.30": "1.2.3.1.1.01.07",
                    "449052.32": "1.2.3.1.1.01.08", "449052.33": "1.2.3.1.1.04.05",
                    "449052.34": "1.2.3.1.1.01.25", "449052.35": "1.2.3.1.1.02.01",
                    "449052.36": "1.2.3.1.1.03.02", "449052.38": "1.2.3.1.1.01.09",
                    "449052.39": "1.2.3.1.1.01.21", "449052.40": "1.2.3.1.1.01.20",
                    "449052.41": "1.2.3.1.1.02.01", "449052.42": "1.2.3.1.1.03.03",
                    "449052.44": "1.2.3.1.1.04.06", "449052.46": "1.2.3.1.1.01.10",
                    "449052.48": "1.2.3.1.1.05.01", "449052.49": "1.2.3.1.1.01.11",
                    "449052.51": "1.2.3.1.1.99.09", "449052.52": "1.2.3.1.1.05.03",
                    "449052.54": "1.2.3.1.1.01.14", "449052.57": "1.2.3.1.1.01.12",
                    "449052.60": "1.2.3.1.1.01.13", "449052.96": "1.2.3.1.1.07.03",
                }
                _nat_bens = _nat_bens or _NATUREZA_PADRAO_IMB
                _bens_uso = _nat_bens.get(_natureza, "")
            except Exception:
                _bens_uso = ""
            _bens_nao_mapeado = not _bens_uso
            _bens_uso = _bens_uso or "Não mapeado — consulte Configurações → Tabelas"

            try:
                _total_nfs = sum(
                    _brl_para_float(n.get("Valor", "0"))
                    for n in dados_extraidos.get("Notas Fiscais",[])
                )
                _valor_str = f"R$ {_total_nfs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except Exception:
                _valor_str = "—"

            _aviso_nat = (
                f" ⚠ Natureza '{_natureza}' não encontrada na tabela — verifique em Configurações → Tabelas."
                if _bens_nao_mapeado else ""
            )

            adicionar(
                "atencao",
                "Preenchimento Outros Lançamentos (SIAFI)",
                f"Orientação: acesse o SIAFI e lance manualmente em Outros Lançamentos. "
                f"Situação: IMB050. "
                f"Subitem: {_subitem}. "
                f"Bens Móveis em Uso: {_bens_uso}. "
                f"Bens Móveis em Almoxarifado: {_bens_almox}. "
                f"Valor: {_valor_str}."
                + _aviso_nat,
                "automacao",
            )

        _DSP_SITUACOES_VPD = {"DSP001", "DSP102"}  # DSP101 e DSP201 não possuem campo VPD
        if tipo_liquidacao_norm in _DSP_SITUACOES_VPD:
            vpd_manual = str(dados.get("vpd_manual", "") or "").strip()
            if not vpd_manual:
                natureza_vpd = str(dados_extraidos.get("Natureza", "") or "").strip()
                vpd_tabela = ""
                try:
                    from services import turso_service as _ts_vpd
                    if _ts_vpd.turso_configurado():
                        vpd_tabela = _ts_vpd._buscar_vpd(natureza_vpd, tipo_liquidacao_norm)
                except Exception:
                    pass
                if not vpd_tabela:
                    try:
                        from comprasnet.principal_helpers import _buscar_vpd as _ph_buscar_vpd
                        vpd_tabela = _ph_buscar_vpd(natureza_vpd, tipo_liquidacao_norm)
                    except Exception:
                        pass
                if not vpd_tabela:
                    nat_label = f" para a natureza '{natureza_vpd}'" if natureza_vpd else ""
                    adicionar(
                        "atencao",
                        "VPD não encontrado — informar manualmente",
                        f"A situação {tipo_liquidacao_norm} requer VPD, mas nenhum foi localizado{nat_label}. "
                        "Informe o código VPD no painel de preenchimento antes de executar.",
                        "automacao",
                    )

    for etapa in etapas:
        if str(etapa.get("status", "") or "") == "erro":
            adicionar(
                "bloqueio",
                f"Etapa com erro: {etapa.get('nome', 'Automação')}",
                "A automação registrou erro nesta etapa e precisa de revisão antes de prosseguir.",
                "automacao",
            )

    for ded in deducoes:
        if str(ded.get("status", "") or "") == "erro":
            rotulo = str(ded.get("siafi", "") or ded.get("tipo", "") or "Dedução").strip()
            adicionar(
                "bloqueio",
                f"Dedução com erro: {rotulo}",
                "Uma dedução falhou durante a execução e deve ser refeita ou conferida manualmente.",
                "automacao",
            )

    for alerta in dados.get("alertas", []) or[]:
        alerta_txt = str(alerta or "").strip()
        if alerta_txt:
            adicionar(
                "atencao",
                "Atenção na análise inicial",
                alerta_txt,
                "pdf",
            )

    # Verificação de Simples Nacional / DDF055 não se aplica a bolsas nem a
    # entidades federais (universidades, institutos, autarquias), que são isentas
    # de retenção federal independentemente de optante.
    _nome_credor = str(dados_extraidos.get("Nome do Credor", "") or dados.get("nome_credor", "") or "").strip()
    _is_bolsa = tipo_operacional == "bolsa"
    _is_federal = bool(
        __import__("re").search(
            r"federal|universidade|instituto\s+fed|autarquia"
            r"|fund\w*\s+(?:de\s+)?ensino|fund\w*\s+(?:de\s+)?pesquisa"
            r"|feesc|fepese|funjab|funpesquisa|feaufsc",
            _nome_credor,
            __import__("re").IGNORECASE,
        )
    )
    if _is_bolsa or _is_federal:
        return pendencias

    _optante = bool(dados.get("optante_simples", False))
    try:
        regras_deducoes, _ = _carregar_regras_datas_deducoes()
        regra_retencoes = next(
            (
                regra for regra in regras_deducoes.get("regras", [])
                if str(regra.get("id") or "") == "ddf055-retencoes"
            ),
            {},
        )
        codigos_retencoes = {
            str(codigo or "").strip()
            for codigo in (regra_retencoes.get("codigos") or [])
            if str(codigo or "").strip()
        }
        siafis_retencoes = {
            str(regra_retencoes.get("siafi") or "DDF055").strip().upper()
        }
    except Exception:
        codigos_retencoes = {"6147", "9060", "8739", "8767", "6175", "8850", "8863", "6188", "6190"}
        siafis_retencoes = {"DDF055"}
    label_retencao_federal = sorted(siafis_retencoes)[0] if siafis_retencoes else "DDF055"
    _tem_retencao_federal = any(
        str(d.get("codigo", "") or "").strip() in codigos_retencoes
        or str(d.get("siafi", "") or "").strip().upper() in siafis_retencoes
        for d in deducoes
    )
    if _optante and _tem_retencao_federal:
        adicionar(
            "bloqueio",
            f"Optante pelo Simples com {label_retencao_federal} identificada",
            f"A empresa consta como optante pelo Simples Nacional, mas a dedução {label_retencao_federal} (retenção federal: IR, CSLL, COFINS, PIS) foi identificada no documento. "
            "Empresas optantes pelo Simples geralmente são isentas dessas retenções federais — verifique se a retenção é devida.",
            "pdf",
        )
    elif not _optante and not _tem_retencao_federal:
        adicionar(
            "bloqueio",
            f"Não optante sem {label_retencao_federal}",
            f"A empresa não consta como optante pelo Simples Nacional e nenhuma dedução {label_retencao_federal} (retenção federal: IR, CSLL, COFINS, PIS) foi identificada. "
            "Verifique se a retenção federal deveria estar presente neste documento.",
            "pdf",
        )

    mensagens =[*dados.get("logs", []), *dados.get("logs_simples",[])]
    for mensagem in mensagens:
        mensagem_txt = str(mensagem or "").strip()
        mensagem_norm = _normalizar_texto_status(mensagem_txt)
        if not mensagem_txt:
            continue
        if "requer conferencia manual" in mensagem_norm:
            # Extrai a etapa (ex.: "Dados Básicos", "Principal com Orçamento")
            # para que divergências de etapas diferentes não colidam no mesmo
            # título e sejam descartadas pela deduplicação (tipo, título).
            m_etapa = re.match(r"^[⚠✗✓\s]*([^:]+?):", mensagem_txt)
            etapa_nome = m_etapa.group(1).strip() if m_etapa else ""
            titulo = (
                f"Conferência manual necessária — {etapa_nome}"
                if etapa_nome
                else "Conferência manual necessária"
            )
            adicionar(
                "divergencia",
                titulo,
                mensagem_txt,
                "portal",
            )
        elif "diverg" in mensagem_norm:
            adicionar(
                "divergencia",
                "Divergência detectada",
                mensagem_txt,
                "portal",
            )

    return pendencias


def _montar_status_geral(
    dados: dict,
    pendencias: list[dict[str, Any]],
) -> dict[str, str]:
    if bool(dados.get("is_running", False)):
        return {
            "tipo": "em_execucao",
            "titulo": "Automação em andamento",
            "descricao": "O AutoLiquid está executando etapas neste documento agora.",
        }

    pendencias_ativas = [item for item in pendencias if not item.get("resolvida")]
    bloqueios =[item for item in pendencias_ativas if item.get("tipo") == "bloqueio"]
    divergencias =[item for item in pendencias_ativas if item.get("tipo") == "divergencia"]
    atencoes =[item for item in pendencias_ativas if item.get("tipo") == "atencao"]

    if bloqueios:
        return {
            "tipo": "bloqueado",
            "titulo": "Documento com bloqueios",
            "descricao": f"{len(bloqueios)} item(ns) exigem ação antes de seguir com segurança.",
        }
    if divergencias:
        return {
            "tipo": "atencao",
            "titulo": "Documento com divergências",
            "descricao": f"{len(divergencias)} divergência(s) foram detectadas e devem ser conferidas.",
        }
    if atencoes:
        return {
            "tipo": "atencao",
            "titulo": "Documento com atenções",
            "descricao": f"{len(atencoes)} observação(ões) merecem revisão, embora não bloqueiem a execução.",
        }
    return {
        "tipo": "pronto",
        "titulo": "Documento pronto para execução",
        "descricao": "Nenhum bloqueio ou divergência relevante foi identificado até aqui.",
    }

def _vincular_iss_notas(deducoes: list[dict], notas: list[dict], tolerancia: float = 0.02) -> None:
    from itertools import combinations

    iss_entries =[d for d in deducoes if str(d.get("siafi", "")).upper() in {"DDR001", "DOB001"}]
    if not iss_entries or not notas:
        return

    nf_pool = [(nf["id"], str(nf.get("nota", "")), float(nf.get("valor", 0))) for nf in notas if float(nf.get("valor", 0)) > 0]

    for ded in iss_entries:
        base = float(ded.get("baseCalculo", 0))
        if base <= 0:
            continue

        vinculadas: list[dict] =[]
        for r in range(1, len(nf_pool) + 1):
            for combo in combinations(nf_pool, r):
                if abs(sum(v for _, _, v in combo) - base) <= tolerancia:
                    vinculadas =[{"id": id_, "nota": nota, "valor": round(v, 2)} for id_, nota, v in combo]
                    break
            if vinculadas:
                break

        ded["notasFiscaisVinculadas"] = vinculadas


def _montar_documento_processado(doc_id: str, dados: dict) -> dict[str, Any]:
    d = dados.get("dados_extraidos", {})
    resumo_raw = d.get("Resumo", {})

    notas =[
        {
            "id": i + 1,
            "tipo": n.get("Tipo", ""),
            "nota": n.get("Número da Nota", ""),
            "emissao": n.get("Data de Emissão", ""),
            "ateste": n.get("Data de Ateste", ""),
            "valor": _brl_para_float(n.get("Valor", "0")),
        }
        for i, n in enumerate(d.get("Notas Fiscais", []))
    ]

    empenhos =[
        {
            "id": i + 1,
            "numero": e.get("Empenho", ""),
            "situacao": e.get("Situação", ""),
            "recurso": e.get("Recurso", ""),
            "natureza": e.get("Natureza", "") or d.get("Natureza", ""),
            "valor": _brl_para_float(e.get("Valor", "0") or "0"),
            "saldo": _brl_para_float(e.get("Saldo", "0") or "0"),
        }
        for i, e in enumerate(d.get("Empenhos", []))
    ]

    _ded_status_map: dict = dados.get("deducoes_status", {})

    try:
        _datas_calc = _datas_impostos().calcular_datas_documento(
            d,
            vencimento_usuario=str(dados.get("dates", {}).get("vencimento", "") or ""),
            apuracao_usuario=str(dados.get("dates", {}).get("apuracao", "") or ""),
        )
    except Exception:
        _datas_calc = {}

    def _normalizar_codigo(codigo: str) -> str:
        c = str(codigo or "").strip()
        return c.lstrip("0") or c

    deducoes =[
        {
            "id": i + 1,
            "tipo": ded.get("Situação", ""),
            "codigo": ded.get("Código", ""),
            "siafi": ded.get("Situação SIAFI", ""),
            "rendimento": ded.get("Rendimento", ""),
            "baseCalculo": _brl_para_float(ded.get("Base Cálculo", "0")),
            "valor": _brl_para_float(ded.get("Valor", "0")),
            "status": _ded_status_map.get(str(i + 1), _ded_status_map.get(i + 1, "aguardando")),
            "datasCalculadas": (lambda c: {
                "apuracao": _datas_calc.get(c, {}).get("apuracao", ""),
                "vencimento": _datas_calc.get(c, {}).get("vencimento", ""),
            })(_normalizar_codigo(ded.get("Código", ""))),
            "notasFiscaisVinculadas": [],
        }
        for i, ded in enumerate(_normalizar_deducao_extraida(item) for item in d.get("Deduções",[]))
    ]

    _vincular_iss_notas(deducoes, notas)

    tipo_liquidacao = ""
    empenhos_raw = d.get("Empenhos",[])
    if empenhos_raw:
        sit_raw = empenhos_raw[0].get("Situação", "")
        base = _comprasnet_base()
        tipo_liquidacao = base.extrair_siafi_completo(sit_raw) or base.extrair_codigo_situacao(sit_raw)

    bolsas_liquidacao = [
        {
            "numeroRemessa": str(item.get("Número da Remessa", "") or "").strip(),
            "emissao": str(item.get("Data de Emissão", "") or "").strip(),
            "ateste": str(item.get("Data de Ateste", "") or "").strip(),
            "valor": _brl_para_float(item.get("Valor", "0")),
        }
        for item in d.get("Bolsas", [])
    ]
    remessas_bolsa = dados.get("remessas_bolsa", [])
    if not isinstance(remessas_bolsa, list):
        remessas_bolsa = []
    tipo_operacional = str(d.get("Tipo Operacional") or "").strip().lower()
    if not tipo_operacional:
        tipo_operacional = "bolsa" if bolsas_liquidacao else "comprasnet"

    etapas = deepcopy(dados.get("etapas", ETAPAS_BASE))
    pendencias = _montar_pendencias_documento(dados, d, deducoes, etapas, tipo_operacional)
    status_geral = _montar_status_geral(dados, pendencias)

    return {
        "id": doc_id,
        "lfNumero": dados.get("lf_numero", ""),
        "ugrNumero": dados.get("ugr_numero", ""),
        "vencimentoDocumento": dados.get("vencimento_documento", ""),
        "usarContaPdf": bool(dados.get("usar_conta_pdf", True)),
        "contaBanco": dados.get("conta_banco", ""),
        "contaAgencia": dados.get("conta_agencia", ""),
        "contaConta": dados.get("conta_conta", ""),
        "requiresCentroCusto": bool(dados.get("requires_centro_custo", False)),
        "vpd": dados.get("vpd_manual", ""),
        "dates": dados.get("dates", {"apuracao": "", "vencimento": ""}),
        "documento": {
            "cnpj": _valor_ou_traco(d.get("CNPJ", "")),
            "nomeCredor": _valor_ou_traco(d.get("Nome do Credor", "") or d.get("Nome Credor", "")),
            "processo": _valor_ou_traco(d.get("Processo", "")),
            "solPagamento": _valor_ou_traco(d.get("Solicitação de Pagamento", "")),
            "convenio": _valor_ou_traco(d.get("Tem Convênio", "")),
            "natureza": _valor_ou_traco(d.get("Natureza", "")),
            "ateste": _valor_ou_traco(d.get("Data de Ateste", "")),
            "contrato": _valor_ou_traco(d.get("Número do Contrato", "")),
            "codigoIG": _valor_ou_traco(d.get("IG", "")),
            "tipoLiquidacao": tipo_liquidacao,
            "tipoOperacional": tipo_operacional,
            "codigoOperacional": str(dados.get("codigo_operacional", "") or "01"),
            "bolsas": bolsas_liquidacao,
            "optanteSimples": bool(dados.get("optante_simples", False)),
            "alertas": dados.get("alertas",[]),
            "bancoPdf": d.get("Banco", ""),
            "agenciaPdf": d.get("Agência", ""),
            "contaPdf": d.get("Conta", ""),
        },
        "resumo": {
            "bruto": _brl_para_float(resumo_raw.get("Valor Bruto", "0")),
            "deducoes": _brl_para_float(resumo_raw.get("Total Deduções", "0")),
            "liquido": _brl_para_float(resumo_raw.get("Valor Líquido", "0")),
        },
        "notasFiscais": notas,
        "empenhos": empenhos,
        "deducoes": deducoes,
        "etapas": etapas,
        "pendencias": pendencias,
        "statusGeral": status_geral,
        "remessasBolsa": remessas_bolsa,
        "logs": dados.get("logs",[]),
        "logsSimples": dados.get("logs_simples",[]),
        "isRunning": dados.get("is_running", False),
        "cancelRequested": dados.get("cancel_requested", False),
    }


def _sincronizar_documento_remoto(doc_id: str, dados: dict) -> None:
    snapshot = _montar_documento_processado(doc_id, dados)
    if _fonte_dados_habilitada("execucoes", "turso"):
        turso = _turso_service()
        if turso.turso_configurado():
            turso.salvar_documento(doc_id, dados)
            execucao_id = turso.persistir_documento_com_log(snapshot)
            if execucao_id is not None:
                dados["turso_execucao_id"] = execucao_id
        return

    if _fonte_dados_habilitada("execucoes", "supabase"):
        try:
            execucao_id = _postgres_service().persistir_documento_com_log(snapshot)
            if execucao_id is not None:
                dados["postgres_execucao_id"] = execucao_id
        except Exception:
            pass


def _obter_documento_cache_ou_turso(doc_id: str) -> dict | None:
    doc = _local_cache_service().obter_documento(doc_id)
    if doc:
        return doc
    if not _fonte_dados_habilitada("execucoes", "turso"):
        return None
    try:
        turso = _turso_service()
        if not turso.turso_configurado():
            return None
        doc = turso.obter_documento(doc_id)
        if doc:
            _local_cache_service().salvar_documento(doc_id, doc)
        return doc
    except Exception:
        log.warning("Falha ao recuperar documento %s do Turso.", doc_id, exc_info=True)
        return None


def _executar_uma_etapa(
    doc_id: str,
    etapa_id: int,
    playwright_obj: Any,
    pagina: Any,
) -> None:
    """Executa UMA etapa de automação, atualizando status e logs no dict doc."""
    import comprasnet.apropriar as comprasnet_apropriar
    import comprasnet.dados_basicos as comprasnet_dados_basicos
    import comprasnet.principal_orcamento as comprasnet_principal_orcamento
    import comprasnet.deducao as comprasnet_deducao
    import comprasnet.dados_pagamento as comprasnet_dados_pagamento
    import comprasnet.centro_custo as comprasnet_centro_custo

    doc = _local_cache_service().obter_documento(doc_id)
    if not doc: return

    dados = doc["dados_extraidos"]
    venc = str(doc.get("vencimento_documento") or doc["dates"].get("vencimento", "") or "")
    venc_deducao = str(doc["dates"].get("vencimento", "") or "")
    apuracao = str(doc["dates"].get("apuracao", "") or "")
    lf_numero = str(doc.get("lf_numero", "") or "")
    ugr_numero = str(doc.get("ugr_numero", "") or "")
    usar_conta_pdf = bool(doc.get("usar_conta_pdf", True))
    conta_banco = str(doc.get("conta_banco", "") or "")
    conta_agencia = str(doc.get("conta_agencia", "") or "")
    conta_conta = str(doc.get("conta_conta", "") or "")
    
    def deve_parar():
        current = _local_cache_service().obter_documento(doc_id)
        return bool(current.get("cancel_requested", False)) if current else False

    houve_divergencia = False

    def _verificar_resultado(resultado: Any, nome: str) -> None:
        nonlocal houve_divergencia
        if not isinstance(resultado, dict):
            return
        status = resultado.get("status", "")
        mensagem = resultado.get("mensagem", "")
        if status == "erro":
            raise RuntimeError(_detalhar_erro_execucao(nome, mensagem or "erro não detalhado"))
        if status == "interrompido":
            raise ExecucaoInterrompida(mensagem or f"{nome} interrompido.")
        if status == "alerta" and mensagem:
            # Divergência: sinaliza mas NÃO interrompe a automação.
            houve_divergencia = True
            _log(doc_id, f"⚠ {_detalhar_erro_execucao(nome, mensagem)}")

    _ETAPAS_NOMES = {
        0: "Apropriar Instrumento",
        1: "Dados Básicos",
        2: "Principal com Orçamento",
        3: "Deduções",
        4: "Dados de Pagamento",
        5: "Centro de Custo",
    }

    _atualizar_etapa(doc_id, etapa_id, "executando")
    _log_s(doc_id, f"RUN {_ETAPAS_NOMES.get(etapa_id, f'Etapa {etapa_id}')}")

    try:
        if etapa_id == 0:
            _log(doc_id, "→ Pesquisando e apropriando instrumento de cobrança...")
            resultado = comprasnet_apropriar.executar(
                dados, pagina=pagina, playwright=playwright_obj
            )
            _verificar_resultado(resultado, "Apropriar Instrumento")
        elif etapa_id == 1:
            _log(doc_id, "→ Iniciando Dados Básicos...")
            resultado = comprasnet_dados_basicos.executar(
                dados, venc, pagina=pagina, playwright=playwright_obj
            )
            _verificar_resultado(resultado, "Dados Básicos")
        elif etapa_id == 2:
            _log(doc_id, "→ Iniciando Principal com Orçamento...")
            vpd_manual = str(doc.get("vpd_manual", "") or "").strip()
            if vpd_manual:
                dados["VPD_MANUAL"] = vpd_manual
            resultado = comprasnet_principal_orcamento.executar(
                dados, deve_parar=deve_parar, pagina=pagina, playwright=playwright_obj
            )
            _verificar_resultado(resultado, "Principal com Orçamento")
        elif etapa_id == 3:
            _log(doc_id, "→ Iniciando Dedução...")
            resultado = comprasnet_deducao.executar(
                dados, venc_deducao, apuracao, lf_numero,
                deve_parar=deve_parar, pagina=pagina, playwright=playwright_obj,
            )
            _verificar_resultado(resultado, "Dedução")
        elif etapa_id == 4:
            _log(doc_id, "→ Iniciando Dados de Pagamento...")
            dados_pagamento = {
                **dados,
                "_lf_numero": lf_numero,
                "_vencimento_documento": venc,
                "_tipos_documento_lf": _web_config_service().carregar_configuracoes_web().get("tiposDocumentoLf", []),
            }
            resultado = comprasnet_dados_pagamento.executar(
                dados_pagamento, venc,
                usar_conta_pdf=usar_conta_pdf,
                conta_banco=conta_banco,
                conta_agencia=conta_agencia,
                conta_conta=conta_conta,
                pagina=pagina, playwright=playwright_obj
            )
            _verificar_resultado(resultado, "Dados de Pagamento")
        elif etapa_id == 5:
            _log(doc_id, "→ Iniciando Centro de Custo...")
            resultado = comprasnet_centro_custo.executar(
                dados, ugr_numero, deve_parar=deve_parar,
                pagina=pagina, playwright=playwright_obj,
            )
            _verificar_resultado(resultado, "Centro de Custo")
        else:
            raise ValueError(f"Etapa desconhecida: {etapa_id}")

        # "divergencia": etapa terminou (não para a automação) porém com
        # divergências a conferir. Caso contrário, "concluido" normal.
        _atualizar_etapa(doc_id, etapa_id, "divergencia" if houve_divergencia else "concluido")
        if houve_divergencia:
            # Evita as palavras "diverg"/"requer conferência manual" para não
            # gerar um card de pendência genérico — as tabelas já cobrem isso.
            _log(doc_id, f"⚠ Etapa {etapa_id} concluída — confira as pendências.")
        else:
            _log(doc_id, f"✓ Etapa {etapa_id} concluída.")
        for msg in _gerar_logs_etapa_sucesso(dados, etapa_id, venc):
            _log_s(doc_id, msg)

    except Exception as exc:
        _atualizar_etapa(doc_id, etapa_id, "erro")
        mensagem = _detalhar_erro_execucao(
            _ETAPAS_NOMES.get(etapa_id, f"Etapa {etapa_id}"),
            exc,
        )
        _log(doc_id, f"✗ {mensagem}")
        _log_s(doc_id, f"ERR {mensagem}")
        raise


def _auto_concluir_na_fila(doc_id: str) -> None:
    """Marca automaticamente o processo como concluído na fila ao terminar todas as etapas."""
    try:
        doc = _local_cache_service().obter_documento(doc_id)
        if not doc:
            return
        d = doc.get("dados_extraidos") or {}
        numero_processo = str(d.get("Processo") or "").strip()
        sol_pagamento = str(d.get("Solicitação de Pagamento") or "").strip()
        if not numero_processo and not sol_pagamento:
            return

        autor = str(os.getenv("AUTO_LIQUID_NOME") or os.getenv("USER") or os.getenv("USERNAME") or "").strip()
        result = {
            "concluido": True,
            "concluidoPor": autor,
            "concluidoEm": datetime.now().isoformat(timespec="seconds"),
        }

        if _fonte_dados_habilitada("fila_processos_edicoes", "turso"):
            turso = _turso_service()
            if turso.turso_configurado():
                result = turso.salvar_conclusao_fila(
                    numero_processo=numero_processo,
                    sol_pagamento=sol_pagamento,
                    concluido=True,
                    autor=autor,
                )
        elif _fonte_dados_habilitada("fila_processos_edicoes", "supabase"):
            result = _postgres_service().salvar_conclusao_fila(
                numero_processo=numero_processo,
                sol_pagamento=sol_pagamento,
                concluido=True,
            )

        row_key = f"{numero_processo}::{sol_pagamento}"
        updated_rows: list[dict[str, Any]] = []
        for row in FILA_PROCESSOS_CACHE.get("rows", []) or []:
            current_key = f"{str(row.get('Número Processo') or '').strip()}::{str(row.get('Sol. Pagamento') or '').strip()}"
            if current_key == row_key:
                next_row = dict(row)
                next_row["__concluido"] = "1"
                next_row["__concluido_por"] = str(result.get("concluidoPor") or autor)
                next_row["__concluido_em"] = str(result.get("concluidoEm") or "")
                updated_rows.append(next_row)
            else:
                updated_rows.append(row)

        if updated_rows:
            FILA_PROCESSOS_CACHE["rows"] = updated_rows
            FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(updated_rows)
            try:
                _local_cache_service().salvar_fila_processos_snapshot(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))
            except Exception:
                pass
            _sincronizar_fila_turso_async(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))

        _broadcast_fila_event({
            "type": "conclusao-alterada",
            "rowKey": row_key,
            "concluido": True,
            "concluidoPor": str(result.get("concluidoPor") or autor),
            "concluidoEm": str(result.get("concluidoEm") or ""),
        })
        _log(doc_id, f"✓ Processo {numero_processo or sol_pagamento} marcado como concluído na fila.")
    except Exception:
        log.debug("Falha ao marcar processo como concluído na fila.", exc_info=True)


def _task_executar_todas(doc_id: str):
    playwright_obj = None
    concluiu_todas = False
    try:
        playwright_obj, pagina = _comprasnet_base().conectar()
        for etapa_id in range(0, 6):
            doc = _local_cache_service().obter_documento(doc_id)
            if not doc: break
            if doc.get("cancel_requested"):
                raise ExecucaoInterrompida("Cancelado pelo usuário.")
            _executar_uma_etapa(doc_id, etapa_id, playwright_obj, pagina)
        concluiu_todas = True
    except ExecucaoInterrompida:
        _log(doc_id, "Execução interrompida pelo usuário.")
    except Exception as exc:
        _log(doc_id, _detalhar_erro_execucao("Execução completa", exc))
        log.exception("Erro na execução de todas as etapas")
    finally:
        doc = _local_cache_service().obter_documento(doc_id)
        if doc:
            doc["is_running"] = False
            _local_cache_service().salvar_documento(doc_id, doc)
            _sincronizar_documento_remoto(doc_id, doc)
        if playwright_obj is not None:
            try:
                playwright_obj.stop()
            except Exception:
                pass
    if concluiu_todas:
        _auto_concluir_na_fila(doc_id)


def _task_executar_etapa(doc_id: str, etapa_id: int):
    playwright_obj = None
    try:
        playwright_obj, pagina = _comprasnet_base().conectar()
        _executar_uma_etapa(doc_id, etapa_id, playwright_obj, pagina)
    except Exception as exc:
        _log(doc_id, _detalhar_erro_execucao(f"Etapa {etapa_id}", exc))
        log.exception("Erro na execução da etapa %s", etapa_id)
    finally:
        doc = _local_cache_service().obter_documento(doc_id)
        if doc:
            doc["is_running"] = False
            _local_cache_service().salvar_documento(doc_id, doc)
            _sincronizar_documento_remoto(doc_id, doc)
        if playwright_obj is not None:
            try:
                playwright_obj.stop()
            except Exception:
                pass


def _task_executar_deducao(doc_id: str, ded_id: int, payload_dict: dict):
    playwright_obj = None
    try:
        doc = _local_cache_service().obter_documento(doc_id)
        if not doc: return

        deducoes_raw = doc["dados_extraidos"].get("Deduções",[])
        ded = _normalizar_deducao_extraida(deducoes_raw[ded_id - 1])
        dados = doc["dados_extraidos"]

        if payload_dict.get("dataVencimento") or payload_dict.get("dataApuracao"):
            venc_deducao = str(payload_dict.get("dataVencimento") or "")
            apuracao     = str(payload_dict.get("dataApuracao") or "")
        else:
            try:
                _datas_calc = _datas_impostos().calcular_datas_documento(
                    dados,
                    vencimento_usuario=str(doc["dates"].get("vencimento", "") or ""),
                    apuracao_usuario=str(doc["dates"].get("apuracao", "") or ""),
                )
                cod = str(ded.get("Código", "") or "").strip().lstrip("0") or str(ded.get("Código", "") or "").strip()
                _d = _datas_calc.get(cod, {})
                venc_deducao = str(_d.get("vencimento", "") or doc["dates"].get("vencimento", "") or "")
                apuracao     = str(_d.get("apuracao", "") or doc["dates"].get("apuracao", "") or "")
            except Exception:
                venc_deducao = str(doc["dates"].get("vencimento", "") or "")
                apuracao     = str(doc["dates"].get("apuracao", "") or "")

        lf_numero = str(doc.get("lf_numero", "") or "")
        def deve_parar():
            current = _local_cache_service().obter_documento(doc_id)
            return bool(current.get("cancel_requested", False)) if current else False

        dados_fake = {**dados, "Deduções": [ded]}

        if "deducoes_status" not in doc:
            doc["deducoes_status"] = {}
        doc["deducoes_status"][str(ded_id)] = "executando"
        _local_cache_service().salvar_documento(doc_id, doc)

        _log(doc_id, f"→ Executando dedução {ded_id}: {ded.get('Situação', '')} ({ded.get('Situação SIAFI', '')})")

        playwright_obj, pagina = _comprasnet_base().conectar()
        import comprasnet.deducao as comprasnet_deducao
        resultado = comprasnet_deducao.executar(
            dados_fake, venc_deducao, apuracao, lf_numero,
            deve_parar=deve_parar, pagina=pagina, playwright=playwright_obj,
            pular_confirmar_aba=True,
        )

        status_res = resultado.get("status", "") if isinstance(resultado, dict) else ""
        mensagem_res = resultado.get("mensagem", "") if isinstance(resultado, dict) else ""

        doc = _local_cache_service().obter_documento(doc_id)
        if not doc: return

        if status_res == "erro":
            doc["deducoes_status"][str(ded_id)] = "erro"
            _local_cache_service().salvar_documento(doc_id, doc)
            _log(doc_id, f"✗ {_detalhar_erro_execucao(f'Dedução {ded_id}', mensagem_res or 'erro desconhecido')}")
        elif status_res == "pulado":
            doc["deducoes_status"][str(ded_id)] = "erro"
            _local_cache_service().salvar_documento(doc_id, doc)
            _log(doc_id, f"✗ Dedução {ded_id}: tipo não reconhecido pelo classificador. Mensagem: {mensagem_res}")
        elif status_res == "interrompido":
            doc["deducoes_status"][str(ded_id)] = "aguardando"
            _local_cache_service().salvar_documento(doc_id, doc)
            _log(doc_id, f"⏸ Dedução {ded_id} interrompida.")
        elif status_res == "alerta":
            doc["deducoes_status"][str(ded_id)] = "concluido"
            _local_cache_service().salvar_documento(doc_id, doc)
            _log(doc_id, f"⚠ {_detalhar_erro_execucao(f'Dedução {ded_id}', mensagem_res)}")
            _log_s(doc_id, f"OK Dedução {ded_id} — {ded.get('Situação', '')} registrada (com alertas)")
        else:
            doc["deducoes_status"][str(ded_id)] = "concluido"
            _local_cache_service().salvar_documento(doc_id, doc)
            _log(doc_id, f"✓ Dedução {ded_id} concluída.")
            _log_s(doc_id, f"OK Dedução {ded_id} — {ded.get('Situação', '')} registrada")

    except Exception as exc:
        doc = _local_cache_service().obter_documento(doc_id)
        if doc:
            if "deducoes_status" not in doc:
                doc["deducoes_status"] = {}
            doc["deducoes_status"][str(ded_id)] = "erro"
            _local_cache_service().salvar_documento(doc_id, doc)
        _log(doc_id, _detalhar_erro_execucao(f"Dedução {ded_id}", exc))
        log.exception("Erro ao executar dedução individual %s", ded_id)
    finally:
        doc = _local_cache_service().obter_documento(doc_id)
        if doc:
            doc["is_running"] = False
            _local_cache_service().salvar_documento(doc_id, doc)
            _sincronizar_documento_remoto(doc_id, doc)
        if playwright_obj is not None:
            try:
                playwright_obj.stop()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/auth/diagnostico")
def diagnostico_auth() -> dict[str, Any]:
    """Diagnostico seguro do caminho de login, sem expor secrets."""
    cfg = _carregar_cfg() or {}
    turso_url = str(cfg.get("turso_database_url") or "").strip()
    turso_token = str(cfg.get("turso_auth_token") or "").strip()
    recurso_config = caminho_recurso(CAMINHO_CONFIG.name)
    host = ""
    if turso_url:
        try:
            parsed = requests.utils.urlparse(
                "https://" + turso_url.removeprefix("libsql://")
                if turso_url.startswith("libsql://")
                else turso_url
            )
            host = parsed.netloc
        except Exception:
            host = "invalido"

    turso_url_tipo = ""
    if turso_url.startswith("libsql://"):
        turso_url_tipo = "libsql"
    elif turso_url.startswith("https://"):
        turso_url_tipo = "https"

    resultado: dict[str, Any] = {
        "versao": APP_VERSION,
        "configLocalPath": str(CAMINHO_CONFIG),
        "configEmbutidaPath": str(recurso_config),
        "configLocalExiste": CAMINHO_CONFIG.exists(),
        "configEmbutidaExiste": recurso_config.exists() and recurso_config != CAMINHO_CONFIG,
        "tursoUrlPresente": bool(turso_url),
        "tursoUrlTipo": turso_url_tipo,
        "tursoHost": host,
        "tursoTokenPresente": bool(turso_token),
        "tursoTokenPareceJwt": turso_token.startswith("ey"),
        "tursoTokenTamanho": len(turso_token),
        "envTursoUrlPresente": bool(os.getenv("TURSO_DATABASE_URL")),
        "envTursoTokenPresente": bool(os.getenv("TURSO_AUTH_TOKEN")),
        "consultaTursoOk": False,
    }
    try:
        _turso_service().executar("select 1 as ok", timeout=8)
        resultado["consultaTursoOk"] = True
    except Exception as exc:
        resultado["erroTipo"] = type(exc).__name__
        resultado["erroResumo"] = str(exc)[:240]
    return resultado


@app.post("/login")
def login(payload: LoginPayload) -> dict[str, Any]:
    try:
        usuario = _turso_service().autenticar_usuario(payload.username, payload.password)
    except Exception as exc:
        log.warning("Falha ao autenticar usuário no Turso: %s", exc)
        detalhe = str(exc)
        if "Turso" in detalhe and "configurado" in detalhe:
            raise HTTPException(
                status_code=503,
                detail="Banco Turso não configurado neste app. Atualize a instalação com uma release válida.",
            ) from exc
        if "HTTP 401" in detalhe or "HTTP 403" in detalhe:
            raise HTTPException(
                status_code=503,
                detail="Banco Turso recusou a autenticação do app. Confira o token usado na release.",
            ) from exc
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)) or any(
            trecho in detalhe
            for trecho in (
                "Read timed out",
                "ConnectionError",
                "Failed to establish",
                "Max retries exceeded",
                "NameResolutionError",
                "Temporary failure in name resolution",
                "SSLError",
            )
        ):
            raise HTTPException(
                status_code=503,
                detail="Não foi possível conectar ao Turso para validar o usuário. Verifique internet/VPN/firewall e tente novamente.",
            ) from exc
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível validar o usuário no Turso: {detalhe[:220]}",
        ) from exc
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
    nome_usuario = str(usuario.get("nome") or usuario.get("username") or "").strip()
    if nome_usuario:
        os.environ["AUTO_LIQUID_NOME"] = nome_usuario
    token = _jwt_encode({
        "sub": usuario["username"],
        "name": nome_usuario,
        "role": usuario["role"],
        "iat": int(time.time()),
    })
    return {
        "token": token,
        "username": usuario["username"],
        "nome": nome_usuario,
        "role": usuario["role"],
    }


@app.get("/api/auth/usuarios")
def listar_usuarios_auth() -> dict[str, Any]:
    try:
        return {"usuarios": _turso_service().listar_usuarios_auth()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível carregar usuários: {exc}") from exc


@app.put("/api/auth/usuarios")
def atualizar_usuario_auth(payload: UsuarioAuthPayload) -> dict[str, Any]:
    try:
        usuario = _turso_service().atualizar_usuario_auth(
            payload.username,
            role=payload.role,
            senha=payload.senha,
        )
        return {"success": True, "usuario": usuario}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível salvar usuário: {exc}") from exc


@app.get("/api/status")
async def status_backend() -> dict[str, Any]:
    porta = obter_porta_chrome()
    try:
        chrome_pronto = _chrome_service().chrome_esta_pronto(porta, timeout_s=0.5)
    except Exception:
        chrome_pronto = False

    return {
        "chromeStatus": "pronto" if chrome_pronto else "erro",
        "chromePorta": porta,
    }


@app.get("/api/dashboard")
def dashboard(
    periodo: str = Query(default="semana"),
    servidor_nome: str = Query(default=""),
    limite: int = Query(default=5, ge=1, le=100),
) -> dict[str, Any]:
    def _status_concluido(status: Any) -> bool:
        return "concl" in str(status or "").casefold()

    def _mesclar_registros_locais(base: dict[str, Any]) -> dict[str, Any]:
        try:
            local = _local_cache_service().obter_dashboard_registros_liquidacao(periodo, servidor_nome)
        except Exception:
            log.debug("Falha ao carregar registros locais para o dashboard", exc_info=True)
            return base

        # Deduplica ultimos_base por numeroProcesso, mantendo o mais recente
        seen: dict[str, dict[str, Any]] = {}
        for item in (base.get("ultimosProcessos") or []):
            if not isinstance(item, dict):
                continue
            num = str(item.get("numeroProcesso") or "").strip()
            if not num:
                continue
            anterior = seen.get(num)
            if not anterior or str(item.get("dataExecucao") or "") >= str(anterior.get("dataExecucao") or ""):
                seen[num] = item
        ultimos_base = list(seen.values())
        processos_base = set(seen.keys())
        changed_by_local_status = False
        local_by_num: dict[str, dict[str, Any]] = {}
        for item in (local.get("ultimosProcessos") or []):
            if not isinstance(item, dict):
                continue
            num = str(item.get("numeroProcesso") or "").strip()
            if not num:
                continue
            anterior = local_by_num.get(num)
            if not anterior or str(item.get("dataExecucao") or "") >= str(anterior.get("dataExecucao") or ""):
                local_by_num[num] = item

        for num, item in seen.items():
            local_item = local_by_num.get(num)
            if not local_item:
                continue
            if _status_concluido(local_item.get("status")) and not _status_concluido(item.get("status")):
                item["status"] = "concluido"
                changed_by_local_status = True

        # Adiciona registros locais que ainda não estão no Turso
        extras = [
            item
            for item in local_by_num.values()
            if isinstance(item, dict)
            and str(item.get("numeroProcesso") or "").strip()
            and str(item.get("numeroProcesso") or "").strip() not in processos_base
        ]
        if not extras and not changed_by_local_status and len(ultimos_base) == len(list(base.get("ultimosProcessos") or [])):
            return base

        combinados = sorted(
            [*ultimos_base, *extras],
            key=lambda item: str(item.get("dataExecucao") or ""),
            reverse=True,
        )[:limite]
        # Recalcula valorBruto a partir dos itens já deduplicados,
        # evitando que processos duplicados (mesmo numeroProcesso) inflem o total.
        valor_bruto_dedup = (
            sum(float(item.get("bruto") or 0) for item in ultimos_base)
            + sum(float(item.get("bruto") or 0) for item in extras)
        )
        return {
            **base,
            "valorBruto": valor_bruto_dedup,
            "quantidadeProcessos": len(seen) + len(extras),
            "ultimosProcessos": combinados,
        }

    if _fonte_dados_habilitada("execucoes", "turso"):
        turso = _turso_service()
        if not turso.turso_configurado():
            raise HTTPException(status_code=503, detail="Turso não configurado.")
        return _mesclar_registros_locais(turso.obter_dashboard(periodo, servidor_nome=servidor_nome, limite=limite))
    if not _fonte_dados_habilitada("execucoes", "supabase"):
        return _mesclar_registros_locais({"habilitado": False, "periodo": periodo, "valorBruto": 0, "quantidadeProcessos": 0, "ultimosProcessos": []})
    return _mesclar_registros_locais(_postgres_service().obter_dashboard(periodo, servidor_nome=servidor_nome, limite=limite))


@app.get("/api/dashboard/historico")
def dashboard_historico(
    empresa: str = Query(default=""),
    contrato: str = Query(default=""),
    servidor: str = Query(default=""),
    periodo: str = Query(default="semana"),
) -> dict[str, Any]:
    if _fonte_dados_habilitada("execucoes", "turso"):
        turso = _turso_service()
        if not turso.turso_configurado():
            raise HTTPException(status_code=503, detail="Turso não configurado.")
        return turso.obter_dashboard_historico(
            empresa=empresa,
            contrato=contrato,
            servidor=servidor,
            periodo=periodo,
        )
    if not _fonte_dados_habilitada("execucoes", "supabase"):
        return {"habilitado": False, "total": 0, "totalValor": 0, "porServidor": [], "porEmpresa": [], "porContrato": [], "porMes": []}
    return _postgres_service().obter_dashboard_historico(
        empresa=empresa,
        contrato=contrato,
        servidor=servidor,
        periodo=periodo,
    )


@app.get("/api/fila-processos")
def fila_processos(refresh: bool = Query(default=False)) -> dict[str, Any]:
    global FILA_PROCESSOS_CACHE, FILA_SNAPSHOT_DB_RETRY_AFTER

    if not refresh:
        if FILA_PROCESSOS_CACHE["rows"]:
            rows_cache = _aplicar_sorteio_fila(FILA_PROCESSOS_CACHE["rows"])
            FILA_PROCESSOS_CACHE["rows"] = rows_cache
            FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(rows_cache)
            return {
                "total": len(rows_cache),
                "columns": FILA_PROCESSOS_CACHE["columns"],
                "rows": rows_cache,
                "updatedAt": FILA_PROCESSOS_CACHE["updatedAt"],
                "source": "cache",
            }

        snapshot_local = _local_cache_service().obter_fila_processos_snapshot()
        rows_local = _aplicar_sorteio_fila(_aplicar_de_para_contrato_ic(snapshot_local.get("rows") or[]))
        if rows_local:
            columns_local = _colunas_fila(rows_local)
            FILA_PROCESSOS_CACHE = {
                "rows": rows_local,
                "columns": columns_local,
                "updatedAt": snapshot_local.get("updatedAt"),
            }
            # Serve o cache local imediatamente para o startup ser rápido,
            # mas dispara um refresh do Turso em background para garantir que
            # outros usuários que atualizaram a fila sejam refletidos logo.
            _atualizar_fila_turso_background()
            return {
                "total": len(rows_local),
                "columns": columns_local,
                "rows": rows_local,
                "updatedAt": snapshot_local.get("updatedAt"),
                "source": "local-cache",
            }

        if _fonte_dados_habilitada("fila_processos_atual", "turso"):
            snapshot_turso = _carregar_snapshot_fila_turso()
            if snapshot_turso:
                return snapshot_turso
            return {
                "total": 0,
                "columns": [],
                "rows":[],
                "updatedAt": None,
                "source": "turso-empty",
            }

        if _fonte_dados_habilitada("fila_processos_atual", "supabase"):
            try:
                return _snapshot_fila_future().result(timeout=2)
            except TimeoutError:
                return {
                    "total": 0,
                    "columns": [],
                    "rows":[],
                    "updatedAt": None,
                    "source": "supabase-loading",
                }

        return {
            "total": 0,
            "columns":[],
            "rows":[],
            "updatedAt": None,
            "source": "empty",
        }

    try:
        chrome_service = _chrome_service()
        porta = obter_porta_chrome()
        if not chrome_service.chrome_esta_pronto(porta):
            chrome_service.abrir_chrome(
                porta,
                aguardar=True,
                timeout_s=20,
                oculto=True,
                url_inicial=SOLAR_FILA_TARGET_URL,
            )

        from scripts.solar_fila_headless import SolarFilaConfig, SolarFilaExtractor

        config = SolarFilaConfig(
            headless=True,
            timeout_ms=60000,
            username=os.getenv("SOLAR_USERNAME"),
            password=os.getenv("SOLAR_PASSWORD"),
            filters={},
            close_tab=bool(_web_config_service().carregar_configuracoes_web().get("fecharAbaFila")),
        )
        dataframe = SolarFilaExtractor(config).extract()
        if dataframe.empty:
            raise RuntimeError("A tabela do Solar foi encontrada, mas nenhuma linha de processo foi extraída.")
        updated_at = datetime.now().isoformat(timespec="seconds")
        rows_extraidas = _aplicar_de_para_contrato_ic(dataframe.to_dict(orient="records"))
        rows = _mesclar_metadados_cache_fila(rows_extraidas)
        aviso_sincronizacao = ""
        if _fonte_dados_habilitada("fila_processos_atual", "supabase"):
            _sincronizar_fila_postgres_async(rows_extraidas, updated_at, origem="solar-headless")
            aviso_sincronizacao = "Fila extraída do Solar. Sincronização com Supabase em segundo plano."
            if _fonte_dados_habilitada("fila_processos_atual", "turso"):
                _sincronizar_fila_turso_async(rows_extraidas, updated_at)
        elif _fonte_dados_habilitada("fila_processos_atual", "turso"):
            turso = _turso_service()
            if not turso.turso_configurado():
                aviso_sincronizacao = "Fila extraída do Solar, mas o Turso não está configurado."
            else:
                _sincronizar_fila_turso_async(rows_extraidas, updated_at)
                aviso_sincronizacao = "Fila extraída do Solar. Sincronização com Turso em segundo plano."
        rows = _aplicar_sorteio_fila(rows)
        try:
            _local_cache_service().salvar_fila_processos_snapshot(rows, updated_at)
        except Exception:
            log.debug("Falha ao atualizar cache local da fila", exc_info=True)
        columns = _colunas_fila(rows)

        FILA_PROCESSOS_CACHE = {
            "rows": rows,
            "columns": columns,
            "updatedAt": updated_at,
        }

        return {
            "total": len(rows),
            "columns": columns,
            "rows": rows,
            "updatedAt": updated_at,
            "source": "solar-headless",
            "erro": aviso_sincronizacao or None,
        }
    except Exception as exc:
        if FILA_PROCESSOS_CACHE["rows"]:
            rows_cache = _aplicar_sorteio_fila(FILA_PROCESSOS_CACHE["rows"])
            FILA_PROCESSOS_CACHE["rows"] = rows_cache
            FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(rows_cache)
            return {
                "total": len(rows_cache),
                "columns": FILA_PROCESSOS_CACHE["columns"],
                "rows": rows_cache,
                "updatedAt": FILA_PROCESSOS_CACHE["updatedAt"],
                "source": "cache-local",
                "erro": str(exc),
            }
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível carregar a fila de processos no momento: {exc}",
        ) from exc


@app.get("/api/fila-processos/servidores-sorteio")
def obter_servidores_sorteio() -> dict[str, Any]:
    rows, source = _obter_cache_servidores_sorteio()
    if rows is None:
        started_at = time.time()
        future = SERVIDORES_SORTEIO_EXECUTOR.submit(_carregar_servidores_sorteio_remoto)
        try:
            rows, source = future.result(timeout=3.5)
            if rows:
                _cache_servidores_sorteio(rows, source)
        except TimeoutError:
            def _late_done(done_future) -> None:
                try:
                    late_rows, late_source = done_future.result()
                    if late_rows:
                        with SERVIDORES_SORTEIO_CACHE_LOCK:
                            cache_updated_at = float(SERVIDORES_SORTEIO_CACHE.get("updatedAt") or 0)
                        if cache_updated_at > started_at:
                            return
                        _cache_servidores_sorteio(late_rows, late_source)
                        _broadcast_fila_event({"type": "servidores-sorteio-atualizados"})
                except Exception:
                    log.debug("Falha ao concluir carga tardia de servidores do sorteio", exc_info=True)

            future.add_done_callback(_late_done)
            _refresh_servidores_sorteio_background()
            rows = []
            source = "carregando"
        except Exception as exc:
            log.warning("Falha ao carregar servidores do sorteio: %s", exc)
            rows = []
            source = "erro"
    else:
        _refresh_servidores_sorteio_background()
    servidores = _normalizar_servidores_sorteio(rows or[])
    return {
        "servidores": servidores,
        "source": source if rows is not None else "empty",
    }


@app.get("/api/fila-processos/alerta-servico-regras")
def obter_regras_alerta_servico() -> dict[str, Any]:
    config, source = _carregar_regras_alerta_servico()
    return {**config, "source": source}


@app.get("/api/fila-processos/setores-historico")
def obter_setores_historico_fila(limite: int = Query(default=300, ge=1, le=1000)) -> dict[str, Any]:
    errors: list[str] = []
    fontes: list[str] = []
    setores: list[str] = []

    if _fonte_dados_habilitada("fila_processos_atual", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                setores.extend(turso.obter_setores_fila_historico(limite=limite))
                fontes.append("turso")
        except Exception as exc:
            errors.append(f"Turso: {exc}")
            log.warning("Falha ao carregar setores historicos da fila no Turso: %s", exc)

    if _fonte_dados_habilitada("fila_processos_atual", "supabase"):
        try:
            setores.extend(_postgres_service().obter_setores_fila_historico(limite=limite))
            fontes.append("postgres")
        except Exception as exc:
            errors.append(f"PostgreSQL: {exc}")
            log.warning("Falha ao carregar setores historicos da fila no PostgreSQL: %s", exc)

    setores_unicos = sorted(
        {str(setor or "").strip() for setor in setores if str(setor or "").strip()},
        key=lambda item: item.casefold(),
    )
    return {
        "setores": setores_unicos[:limite],
        "source": "+".join(fontes) if fontes else "empty",
        "errors": errors,
    }


@app.put("/api/fila-processos/alerta-servico-regras")
def salvar_regras_alerta_servico(payload: AlertaServicoConfigPayload) -> dict[str, Any]:
    config = _normalizar_regras_alerta_servico(payload)
    try:
        source = _salvar_regras_alerta_servico(config)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível salvar as regras do alerta de serviço: {exc}",
        ) from exc
    try:
        _web_config_service().salvar_configuracoes_web({
            **_web_config_service().carregar_configuracoes_web(),
            "nfServicoAlertaDiasUteis": config["diasUteisPadrao"],
        })
    except Exception:
        log.debug("Falha ao espelhar dias úteis do alerta na configuração local", exc_info=True)
    _broadcast_fila_event({"type": "alerta-servico-regras-atualizadas"})
    return {
        "success": True,
        "config": {**config, "source": source},
    }


@app.get("/api/deducoes/regras-datas")
def obter_regras_datas_deducoes() -> dict[str, Any]:
    config, source = _carregar_regras_datas_deducoes()
    if source in {"default", "turso-legacy"}:
        try:
            _salvar_regras_datas_deducoes(config)
            source = "turso"
        except Exception:
            log.debug("Falha ao materializar regras padrão de datas das deduções", exc_info=True)
    return {**config, "source": source}


@app.put("/api/deducoes/regras-datas")
def salvar_regras_datas_deducoes(payload: RegrasDatasDeducoesPayload) -> dict[str, Any]:
    config = _normalizar_regras_datas_deducoes(payload)
    try:
        _salvar_regras_datas_deducoes(config)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível salvar as regras de datas das deduções: {exc}",
        ) from exc
    _broadcast_fila_event({"type": "datas-deducoes-regras-atualizadas"})
    return {"success": True, "config": config}


@app.post("/api/deducoes/regras-datas/simular")
def simular_regra_data_deducao(payload: SimularRegraDataDeducaoPayload) -> dict[str, Any]:
    config, _source = _carregar_regras_datas_deducoes()
    regra = next((item for item in config.get("regras", []) if str(item.get("id") or "") == payload.regraId), None)
    if not regra:
        raise HTTPException(status_code=404, detail="Regra não encontrada.")
    emissao = _parse_data_iso_or_br(payload.dataEmissao)
    if not emissao:
        raise HTTPException(status_code=422, detail="Informe uma data de emissão válida.")
    emissao_br = emissao.strftime("%d/%m/%Y")
    if regra.get("mesVencimento") == "usuario" or regra.get("apuracao") == "usuario":
        return {
            "regraId": regra.get("id"),
            "dataEmissao": emissao_br,
            "apuracao": "Informada pelo usuário",
            "vencimento": "Informado pelo usuário",
            "pagamento": "Informado pelo usuário",
            "observacao": "Esta dedução usa datas informadas manualmente no processo.",
        }
    try:
        from core.datas_impostos import calcular_datas
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Motor de datas indisponível: {exc}") from exc
    codigo = str((regra.get("codigos") or [""])[0] or "").strip()
    regra_calculo = {
        "imposto": regra.get("nome") or "",
        "codigo": codigo,
        "siafi": regra.get("siafi") or "",
        "dia": str(regra.get("diaVencimento") or ""),
        "mes": regra.get("mesVencimento") or "seguinte",
        "apuracao": "Data de emissão mais antiga das NFs",
        "ajusteDiaNaoUtil": regra.get("ajusteDiaNaoUtil") or "antecipar",
        "lf": "Sim" if regra.get("precisaLf") else "Não",
    }
    result = calcular_datas(codigo, [emissao_br], regra=regra_calculo)
    vencimento = str(result.get("vencimento") or "")
    observacao = str(result.get("ajuste_observacao") or "")
    return {
        "regraId": regra.get("id"),
        "dataEmissao": emissao_br,
        "apuracao": str(result.get("apuracao") or ""),
        "vencimento": vencimento,
        "pagamento": vencimento,
        "observacao": observacao or "Datas de vencimento/pagamento calculadas conforme a regra.",
    }


@app.put("/api/fila-processos/servidores-sorteio")
def salvar_servidores_sorteio(payload: QueueServersPayload) -> dict[str, Any]:
    servidores = _normalizar_servidores_sorteio(payload.servidores)
    errors: list[str] =[]
    if _fonte_dados_habilitada("servidores_config", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                turso.salvar_tabela_operacional("fila_servidores_sorteio", servidores)
        except Exception as exc:
            errors.append(f"Turso: {exc}")
    if _fonte_dados_habilitada("servidores_config", "supabase"):
        try:
            _postgres_service().salvar_servidores_sorteio(servidores)
        except Exception as exc:
            errors.append(f"Supabase: {exc}")
    if errors:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível salvar os servidores do sorteio: {'; '.join(errors)}",
        )
    _cache_servidores_sorteio(servidores, "local")
    _broadcast_fila_event({"type": "servidores-sorteio-atualizados"})
    return {
        "success": True,
        "servidores": servidores,
    }


@app.get("/api/fila-processos/stream")
async def fila_processos_stream(request: Request):
    _ensure_fila_remote_watcher()

    subscriber: Queue[str] = Queue()
    with FILA_EVENT_SUBSCRIBERS_LOCK:
        FILA_EVENT_SUBSCRIBERS.add(subscriber)

    async def event_generator():
        ultimo_keepalive = time.monotonic()
        try:
            yield "event: ready\ndata: {\"type\":\"ready\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    mensagem = subscriber.get_nowait()
                    yield f"event: fila\ndata: {mensagem}\n\n"
                except Empty:
                    if time.monotonic() - ultimo_keepalive >= 15:
                        ultimo_keepalive = time.monotonic()
                        yield ": keepalive\n\n"
                    await asyncio.sleep(0.5)
        finally:
            with FILA_EVENT_SUBSCRIBERS_LOCK:
                FILA_EVENT_SUBSCRIBERS.discard(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.put("/api/fila-processos/responsavel")
def atualizar_responsavel_fila(payload: FilaResponsavelPayload) -> dict[str, Any]:
    global FILA_PROCESSOS_CACHE

    numero_processo = str(payload.numeroProcesso or "").strip()
    sol_pagamento = str(payload.solPagamento or "").strip()
    responsavel = str(payload.responsavel or "").strip()
    if not numero_processo and not sol_pagamento:
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos o número do processo ou a solicitação de pagamento.",
        )

    autor = str(os.getenv("AUTO_LIQUID_NOME") or os.getenv("USER") or os.getenv("USERNAME") or "").strip()
    if _fonte_dados_habilitada("fila_processos_edicoes", "turso"):
        turso = _turso_service()
        if not turso.turso_configurado():
            raise HTTPException(status_code=503, detail="Turso não configurado.")
        alterado_em = turso.salvar_responsavel_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            responsavel=responsavel,
            autor=autor,
        )
    elif _fonte_dados_habilitada("fila_processos_edicoes", "supabase"):
        alterado_em = _postgres_service().salvar_responsavel_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            responsavel=responsavel,
        )
    else:
        alterado_em = datetime.now().isoformat(timespec="seconds")

    row_key = f"{numero_processo}::{sol_pagamento}"
    updated_rows: list[dict[str, Any]] = []
    for row in FILA_PROCESSOS_CACHE.get("rows", []) or[]:
        current_key = f"{str(row.get('Número Processo') or '').strip()}::{str(row.get('Sol. Pagamento') or '').strip()}"
        if current_key == row_key:
            next_row = dict(row)
            next_row["__responsavel_manual"] = responsavel
            next_row["__responsavel_alterado"] = "1" if responsavel else ""
            next_row["__responsavel_alterado_por"] = autor if responsavel else ""
            next_row["__responsavel_alterado_em"] = alterado_em if responsavel else ""
            updated_rows.append(next_row)
        else:
            updated_rows.append(row)

    if updated_rows:
        FILA_PROCESSOS_CACHE["rows"] = updated_rows
        FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(updated_rows)
        try:
            _local_cache_service().salvar_fila_processos_snapshot(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))
        except Exception:
            log.debug("Falha ao atualizar cache local da fila", exc_info=True)
        _sincronizar_fila_turso_async(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))

    _broadcast_fila_event({"type": "responsavel-alterado", "rowKey": row_key})
    return {
        "success": True,
        "responsavel": responsavel,
        "alteradoPor": autor,
        "alteradoEm": alterado_em,
    }


@app.post("/api/fila-processos/alertas")
def adicionar_alerta_fila(payload: FilaAlertaPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    global FILA_PROCESSOS_CACHE

    numero_processo = str(payload.numeroProcesso or "").strip()
    sol_pagamento = str(payload.solPagamento or "").strip()
    mensagem = str(payload.mensagem or "").strip()
    if not numero_processo and not sol_pagamento:
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos o número do processo ou a solicitação de pagamento.",
        )
    if not mensagem:
        raise HTTPException(status_code=422, detail="Informe uma mensagem.")

    autor = str(os.getenv("AUTO_LIQUID_NOME") or os.getenv("USER") or os.getenv("USERNAME") or "").strip()
    alerta = {
        "id": -int(time.time() * 1000),
        "mensagem": mensagem,
        "autor": autor,
        "criadoEm": datetime.now().isoformat(timespec="minutes"),
    }
    if _fonte_dados_habilitada("fila_processos_alertas", "turso"):
        turso = _turso_service()
        if not turso.turso_configurado():
            raise HTTPException(status_code=503, detail="Turso não configurado.")
        alerta = turso.salvar_alerta_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            mensagem=mensagem,
            autor=autor,
        )
    elif _fonte_dados_habilitada("fila_processos_alertas", "supabase"):
        alerta = _postgres_service().salvar_alerta_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            mensagem=mensagem,
        )

    row_key = f"{numero_processo}::{sol_pagamento}"
    updated_rows: list[dict[str, Any]] =[]
    for row in FILA_PROCESSOS_CACHE.get("rows", []) or[]:
        current_key = f"{str(row.get('Número Processo') or '').strip()}::{str(row.get('Sol. Pagamento') or '').strip()}"
        if current_key == row_key:
            next_row = dict(row)
            try:
                alertas = json.loads(str(next_row.get("__alertas_json") or "[]"))
            except Exception:
                alertas = []
            alertas =[alerta, *alertas]
            next_row["__alertas_json"] = json.dumps(alertas, ensure_ascii=False)
            updated_rows.append(next_row)
        else:
            updated_rows.append(row)

    if updated_rows:
        FILA_PROCESSOS_CACHE["rows"] = updated_rows
        FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(updated_rows)
        try:
            _local_cache_service().salvar_fila_processos_snapshot(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))
        except Exception:
            log.debug("Falha ao atualizar cache local da fila", exc_info=True)
        _sincronizar_fila_turso_async(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))
    _broadcast_fila_event({"type": "alerta-adicionado", "rowKey": row_key, "alerta": alerta})

    return {
        "success": True,
        "alerta": alerta,
    }


@app.delete("/api/fila-processos/alertas/{alerta_id}")
def remover_alerta_fila(
    alerta_id: int,
    numero_processo: str = Query(default=""),
    sol_pagamento: str = Query(default=""),
    mensagem: str = Query(default=""),
) -> dict[str, Any]:
    global FILA_PROCESSOS_CACHE

    if alerta_id <= 0:
        raise HTTPException(status_code=422, detail="Identificador da mensagem inválido.")

    errors: list[str] = []
    saved_anywhere = False
    if _fonte_dados_habilitada("fila_processos_alertas", "turso"):
        try:
            turso = _turso_service()
            if not turso.turso_configurado():
                raise RuntimeError("Turso não configurado.")
            turso.remover_alerta_fila(
                alerta_id=alerta_id,
                numero_processo=numero_processo,
                sol_pagamento=sol_pagamento,
                mensagem=mensagem,
            )
            saved_anywhere = True
        except Exception as exc:
            errors.append(f"Turso: {exc}")
    if _fonte_dados_habilitada("fila_processos_alertas", "supabase"):
        try:
            _postgres_service().remover_alerta_fila(alerta_id=alerta_id)
            saved_anywhere = True
        except Exception as exc:
            errors.append(f"Supabase: {exc}")
    if errors and not saved_anywhere:
        raise HTTPException(status_code=503, detail=f"Não foi possível remover a mensagem: {'; '.join(errors)}")

    updated_rows: list[dict[str, Any]] = []
    row_key = f"{str(numero_processo or '').strip()}::{str(sol_pagamento or '').strip()}"
    for row in FILA_PROCESSOS_CACHE.get("rows", []) or []:
        next_row = dict(row)
        current_key = f"{str(row.get('Número Processo') or '').strip()}::{str(row.get('Sol. Pagamento') or '').strip()}"
        try:
            alertas = json.loads(str(next_row.get("__alertas_json") or "[]"))
        except Exception:
            alertas = []
        filtered = [
            alerta
            for alerta in alertas
            if isinstance(alerta, dict)
            and int(alerta.get("id") or 0) != alerta_id
            and not (
                row_key == current_key
                and bool(mensagem)
                and str(alerta.get("mensagem") or "").strip() == mensagem.strip()
            )
        ]
        next_row["__alertas_json"] = json.dumps(filtered, ensure_ascii=False)
        updated_rows.append(next_row)

    if updated_rows:
        FILA_PROCESSOS_CACHE["rows"] = updated_rows
        FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(updated_rows)
        try:
            _local_cache_service().salvar_fila_processos_snapshot(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))
        except Exception:
            log.debug("Falha ao atualizar cache local da fila", exc_info=True)
        _sincronizar_fila_turso_async(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))

    _broadcast_fila_event({"type": "alerta-removido", "alertaId": alerta_id})
    return {"success": True, "alertaId": alerta_id}


@app.put("/api/fila-processos/conclusao")
def atualizar_conclusao_fila(payload: FilaConclusaoPayload) -> dict[str, Any]:
    global FILA_PROCESSOS_CACHE

    numero_processo = str(payload.numeroProcesso or "").strip()
    sol_pagamento = str(payload.solPagamento or "").strip()
    if not numero_processo and not sol_pagamento:
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos o número do processo ou a solicitação de pagamento.",
        )

    if _fonte_dados_habilitada("fila_processos_edicoes", "turso"):
        autor_turso = str(os.getenv("AUTO_LIQUID_NOME") or os.getenv("USER") or os.getenv("USERNAME") or "").strip()
        turso = _turso_service()
        if not turso.turso_configurado():
            raise HTTPException(status_code=503, detail="Turso não configurado.")
        result = turso.salvar_conclusao_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            concluido=bool(payload.concluido),
            autor=autor_turso,
        )
    elif _fonte_dados_habilitada("fila_processos_edicoes", "supabase"):
        result = _postgres_service().salvar_conclusao_fila(
            numero_processo=numero_processo,
            sol_pagamento=sol_pagamento,
            concluido=bool(payload.concluido),
        )
    else:
        autor = str(os.getenv("AUTO_LIQUID_NOME") or os.getenv("USER") or os.getenv("USERNAME") or "").strip()
        result = {
            "concluido": bool(payload.concluido),
            "concluidoPor": autor if payload.concluido else "",
            "concluidoEm": datetime.now().isoformat(timespec="seconds") if payload.concluido else "",
        }

    row_key = f"{numero_processo}::{sol_pagamento}"
    updated_rows: list[dict[str, Any]] =[]
    numero_digits = re.sub(r"\D+", "", numero_processo)
    numero_solar_match = re.search(r"\b23080\.(\d{1,6})/\d{4}", numero_processo)
    numero_solar_seq = numero_solar_match.group(1) if numero_solar_match else ""
    numero_keys = {item for item in (numero_digits, numero_solar_seq, numero_solar_seq.lstrip("0")) if item}
    for row in FILA_PROCESSOS_CACHE.get("rows", []) or[]:
        current_key = f"{str(row.get('Número Processo') or '').strip()}::{str(row.get('Sol. Pagamento') or '').strip()}"
        current_numero = str(row.get("Número Processo") or "").strip()
        current_digits = re.sub(r"\D+", "", current_numero)
        current_solar_match = re.search(r"\b23080\.(\d{1,6})/\d{4}", current_numero)
        current_solar_seq = current_solar_match.group(1) if current_solar_match else ""
        current_keys = {item for item in (current_digits, current_solar_seq, current_solar_seq.lstrip("0")) if item}
        same_row = current_key == row_key or (
            bool(numero_processo)
            and not sol_pagamento
            and (
                current_numero == numero_processo
                or bool(numero_keys.intersection(current_keys))
            )
        )
        if same_row:
            next_row = dict(row)
            next_row["__concluido"] = "1" if result.get("concluido") else ""
            next_row["__concluido_por"] = str(result.get("concluidoPor") or "")
            next_row["__concluido_em"] = str(result.get("concluidoEm") or "")
            updated_rows.append(next_row)
        else:
            updated_rows.append(row)

    if updated_rows:
        FILA_PROCESSOS_CACHE["rows"] = updated_rows
        FILA_PROCESSOS_CACHE["columns"] = _colunas_fila(updated_rows)
        try:
            _local_cache_service().salvar_fila_processos_snapshot(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))
        except Exception:
            log.debug("Falha ao atualizar cache local da fila", exc_info=True)
        _sincronizar_fila_turso_async(updated_rows, FILA_PROCESSOS_CACHE.get("updatedAt"))

    # Inclui os valores confirmados no evento para que clientes SSE
    # possam atualizar a linha diretamente, sem precisar de um refetch completo.
    _broadcast_fila_event({
        "type": "conclusao-alterada",
        "rowKey": row_key,
        "concluido": bool(result.get("concluido")),
        "concluidoPor": str(result.get("concluidoPor") or ""),
        "concluidoEm": str(result.get("concluidoEm") or ""),
    })
    return {"success": True, **result}


@app.post("/api/chrome/abrir")
def abrir_chrome_endpoint() -> dict[str, Any]:
    chrome_service = _chrome_service()
    porta = obter_porta_chrome()
    try:
        bookmark_ok, bookmark_changed = chrome_service.garantir_bookmarklets_autoliquid()
        estava_aberto = chrome_service.chrome_esta_pronto(porta)
        if bookmark_ok and bookmark_changed and estava_aberto:
            chrome_service.fechar_navegador_automacao(porta, timeout_s=5)
        if not chrome_service.chrome_esta_pronto(porta):
            chrome_service.abrir_chrome(porta, aguardar=True, timeout_s=15)
        aberto = chrome_service.chrome_esta_pronto(porta)
        return {
            "success": aberto,
            "chromeStatus": "pronto" if aberto else "erro",
            "chromePorta": porta,
            "url": URL_INICIAL,
            "mensagem": "Chrome pronto." if aberto else "Chrome não ficou pronto para automação na porta esperada.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/chrome/aba-atual")
def chrome_aba_atual_endpoint() -> dict[str, Any]:
    """Captura o estado completo da aba ativa do Chrome: URL, título,
    campos de formulário com labels, mensagens de erro e títulos de seção.
    Usado pelo relatório de bugs para capturar o contexto do Playwright.
    """
    chrome_service = _chrome_service()
    porta = obter_porta_chrome()
    try:
        return chrome_service.capturar_estado_aba_chrome(porta)
    except Exception as exc:
        return {"erro": str(exc)[:300]}


_SIAFI_WEB_URL = "https://siafi.tesouro.gov.br/"


@app.post("/api/siafi/abrir")
def abrir_siafi_endpoint() -> dict[str, Any]:
    chrome_service = _chrome_service()
    porta = obter_porta_chrome()
    try:
        resultado = chrome_service.abrir_ou_focar_siafi(_SIAFI_WEB_URL)
        action = resultado.get("action", "opened")

        if action == "login_required":
            return {
                "success": True,
                "chromeStatus": "pronto",
                "chromePorta": porta,
                "url": resultado.get("url", _SIAFI_WEB_URL),
                "siafiStatus": "login_required",
                "mensagem": "O SIAFI está aberto mas aguardando login. Faça login na janela do SIAFI e clique em Executar novamente.",
            }
        if action == "tela_preta_clicado":
            return {
                "success": True,
                "chromeStatus": "pronto",
                "chromePorta": porta,
                "url": resultado.get("url", _SIAFI_WEB_URL),
                "siafiStatus": "tela_preta_clicado",
                "mensagem": "Clicado em Siafi Operacional — aguarde o download do aplicativo iniciar.",
            }
        if action == "focused":
            return {
                "success": True,
                "chromeStatus": "pronto",
                "chromePorta": porta,
                "url": resultado.get("url", _SIAFI_WEB_URL),
                "siafiStatus": "pronto",
                "mensagem": "Aba do SIAFI já estava aberta — janela trazida para frente.",
            }
        # action == "opened"
        cdp_ready = bool(resultado.get("cdpReady", True))
        return {
            "success": cdp_ready,
            "chromeStatus": "pronto" if cdp_ready else "erro",
            "chromePorta": porta,
            "url": _SIAFI_WEB_URL,
            "siafiStatus": "abrindo",
            "mensagem": (
                "SIAFI aberto em nova aba anônima do Chrome."
                if cdp_ready
                else "SIAFI foi solicitado, mas o Chrome não ficou pronto para automação na porta esperada."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_SOLAR_BASE_URL = "https://solar.egestao.ufsc.br/solar/"
_SOLAR_CONSULTA_PROCESSO_URL = (
    "https://solar.egestao.ufsc.br/cpav/abrirConsultaProcesso.do"
    "?tipoConsulta=N&visualizacaoResultado=T&visualizacaoProcesso=D"
)


def _quebrar_processo_solar(numero_processo: str) -> dict[str, str]:
    texto = str(numero_processo or "").strip()
    match = re.search(r"\b(\d{5})\.(\d{5,6})/(\d{4})(?:-(\d{2}))?\b", texto)
    if match:
        orgao, numero, ano, dv = match.groups()
    else:
        match_curto = re.search(r"\b(\d{1,6})/(\d{2}|\d{4})(?:-(\d{2}))?\b", texto)
        if not match_curto:
            return {}
        numero, ano, dv = match_curto.groups()
        orgao = "23080"
        if len(ano) == 2:
            ano = f"20{ano}"
    numero = numero.zfill(6)
    return {
        "orgao": orgao,
        "numero": numero,
        "numero_sem_zero": str(int(numero)) if numero.isdigit() else numero,
        "ano": ano,
        "dv": dv or "",
        "formatado": f"{orgao}.{numero}/{ano}" + (f"-{dv}" if dv else ""),
    }


def _frame_por_nome(pagina: Any, nome: str) -> Any | None:
    for frame in getattr(pagina, "frames", []) or []:
        if getattr(frame, "name", "") == nome:
            return frame
    return None


def _frame_conteudo_solar(pagina: Any) -> Any | None:
    """Encontra o frame de conteúdo principal do Solar (não menu, não cabeçalho).

    Tenta primeiro pelos nomes comuns do frameset do Solar; se não encontrar,
    usa a URL de cada frame para identificar o frame de conteúdo.
    """
    # Tenta pelos nomes conhecidos no frameset do Solar
    for nome in ("page", "framePage", "framePrincipal", "principal", "conteudo", "main", "content"):
        frame = _frame_por_nome(pagina, nome)
        if frame is not None:
            return frame

    # Fallback: identifica o frame de conteúdo pela URL
    url_principal = str(getattr(pagina, "url", "") or "")
    frames = list(getattr(pagina, "frames", []) or [])
    candidatos: list[Any] = []
    for frame in frames:
        url = str(getattr(frame, "url", "") or "")
        nome_frame = (str(getattr(frame, "name", "") or "")).lower()
        if not url or url == url_principal or url == "about:blank":
            continue
        if "solar.egestao.ufsc.br" not in url:
            continue
        # Exclui frames de menu e cabeçalho pelos padrões conhecidos
        if any(p in nome_frame for p in ("menu", "header", "top", "topo")):
            continue
        if any(p in url.lower() for p in ("menu", "header", "frameset", "topo", "top")):
            continue
        candidatos.append(frame)

    if not candidatos:
        return None

    # Prefere frame cujo URL seja de uma tela de conteúdo conhecida do Solar
    for frame in candidatos:
        url = (str(getattr(frame, "url", "") or "")).lower()
        if any(p in url for p in ("consultarprocessos", "visualizarprocesso", "abrirconsulta", "cpav")):
            return frame

    return candidatos[0]


def _pagina_parece_solar(pagina: Any) -> bool:
    try:
        assinatura = f"{pagina.url or ''} {pagina.title() or ''}".lower()
    except Exception:
        assinatura = str(getattr(pagina, "url", "") or "").lower()
    return any(chave in assinatura for chave in ("solar.egestao", "spa", "universidade federal de santa catarina"))


def _localizar_pagina_solar(contexto: Any) -> Any | None:
    candidatas = [pagina for pagina in contexto.pages if _pagina_parece_solar(pagina)]
    return candidatas[-1] if candidatas else None


def _alvos_solar(pagina: Any) -> list[Any]:
    return [pagina, *list(getattr(pagina, "frames", []) or [])]


def _target_consulta_solar(pagina: Any) -> Any | None:
    seletores = (
        "#procDocCorrespDTO\\.flTipoprocesso",
        "[name='procDocCorrespDTO.flTipoprocesso']",
        "#procDocCorrespDTO\\.nuProcessooficial",
        "[name='procDocCorrespDTO.nuProcessooficial']",
        "input[name='btnConsultar']",
    )
    for alvo in _alvos_solar(pagina):
        try:
            if any(alvo.locator(seletor).count() > 0 for seletor in seletores):
                return alvo
        except Exception:
            continue
    return None


def _selecionar_modulo_spa_solar(pagina: Any) -> bool:
    script = """
    () => {
      const normalizar = (valor) => String(valor || "")
        .normalize("NFD")
        .replace(/[\\u0300-\\u036f]/g, "")
        .toLowerCase();
      for (const select of document.querySelectorAll("select")) {
        const contexto = normalizar(`${select.id || ""} ${select.name || ""} ${select.closest("td,div,body")?.textContent || ""}`);
        const pareceModulo = contexto.includes("modulo") || contexto.includes("sistema") || Array.from(select.options).some((opt) => normalizar(opt.textContent).includes("spa"));
        if (!pareceModulo) continue;
        const opcao = Array.from(select.options).find((opt) => normalizar(opt.textContent).trim() === "spa" || normalizar(opt.value).trim() === "spa");
        if (!opcao) continue;
        if (select.value !== opcao.value) {
          select.value = opcao.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
        }
        return true;
      }
      return false;
    }
    """
    selecionou = False
    for alvo in _alvos_solar(pagina):
        try:
            selecionou = bool(alvo.evaluate(script)) or selecionou
        except Exception:
            continue
    if selecionou:
        time.sleep(0.8)
    return selecionou


def _clicar_menu_consulta_processo_solar(pagina: Any) -> bool:
    script = """
    () => {
      const normalizar = (valor) => String(valor || "")
        .normalize("NFD")
        .replace(/[\\u0300-\\u036f]/g, "")
        .replace(/\\s+/g, " ")
        .trim()
        .toLowerCase();
      const visivel = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && rect.width >= 0 && rect.height >= 0;
      };
      const links = Array.from(document.querySelectorAll("a, button, input[type='button'], input[type='submit']"));
      const candidatos = links.map((el) => {
        const texto = normalizar(el.textContent || el.value || el.title || el.getAttribute("aria-label") || "");
        const href = normalizar(el.getAttribute("href") || "");
        const idName = normalizar(`${el.id || ""} ${el.name || ""}`);
        return { el, texto, href, idName };
      });
      const matchers = [
        (item) => item.texto.includes("consulta de processo digital"),
        (item) => item.texto.includes("consulta de processo/solicitacoes"),
        (item) => item.texto.includes("consulta de processos/solicitacoes"),
        (item) => item.texto.includes("consulta") && item.texto.includes("processo"),
        (item) => item.href.includes("abrirconsultaprocesso") || item.href.includes("consultaprocesso"),
        (item) => item.idName.includes("consultaprocesso"),
      ];
      for (const matcher of matchers) {
        const item = candidatos.find((candidato) => matcher(candidato) && visivel(candidato.el));
        if (item) {
          item.el.click();
          return `${item.el.tagName}:${item.texto || item.href || item.idName}`;
        }
      }
      const invisivel = candidatos.find((candidato) => matchers.some((matcher) => matcher(candidato)));
      if (invisivel) {
        invisivel.el.click();
        return `${invisivel.el.tagName}:invisivel`;
      }
      return "";
    }
    """
    _selecionar_modulo_spa_solar(pagina)
    for alvo in _alvos_solar(pagina):
        try:
            if alvo.evaluate(script):
                time.sleep(1.2)
                return True
        except Exception:
            continue
    return False


def _navegar_consulta_processo_solar(pagina: Any) -> None:
    # Encontra o frame de conteúdo pelo nome ou pela URL (mais robusto)
    frame_conteudo = _frame_conteudo_solar(pagina)
    if frame_conteudo is not None:
        try:
            frame_conteudo.evaluate("(url) => { window.location.href = url; }", _SOLAR_CONSULTA_PROCESSO_URL)
            return
        except Exception:
            pass
        try:
            frame_conteudo.goto(_SOLAR_CONSULTA_PROCESSO_URL, wait_until="domcontentloaded", timeout=20000)
            return
        except Exception:
            pass
    try:
        pagina.evaluate("(url) => { window.location.href = url; }", _SOLAR_CONSULTA_PROCESSO_URL)
        return
    except Exception:
        pass
    pagina.goto(_SOLAR_CONSULTA_PROCESSO_URL, wait_until="domcontentloaded", timeout=40000)


def _selecionar_dados_do_processo_solar(alvo: Any) -> None:
    script = """
    () => {
      const normalize = (value) => String(value || "")
        .normalize("NFD")
        .replace(/[\\u0300-\\u036f]/g, "")
        .toLowerCase();
      const selects = Array.from(document.querySelectorAll("select"));
      const select = selects.find((item) => {
        const idName = `${item.id || ""} ${item.name || ""}`.toLowerCase();
        return idName.includes("visualizacao");
      });
      if (!select) return false;
      const option = Array.from(select.options).find((item) => {
        const text = normalize(item.textContent);
        return text.includes("dados") && text.includes("processo");
      });
      if (!option) return false;
      select.value = option.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    """
    try:
        if alvo.evaluate(script):
            return
    except Exception:
        pass
    for value in ("D", "DP", "DADOS"):
        try:
            alvo.select_option("#visualizacaoProcesso", value)
            return
        except Exception:
            continue


def _abrir_consulta_processos_solar(pagina: Any) -> Any:
    # Verifica se o formulário de consulta já está visível (evita navegação desnecessária)
    alvo_imediato = _target_consulta_solar(pagina)
    if alvo_imediato is not None:
        return alvo_imediato

    # Tenta navegar o frame de conteúdo diretamente (funciona mesmo com processo já aberto)
    frame_conteudo = _frame_conteudo_solar(pagina)
    if frame_conteudo is not None:
        try:
            frame_conteudo.evaluate("(url) => { window.location.href = url; }", _SOLAR_CONSULTA_PROCESSO_URL)
            fim_direto = time.time() + 10
            while time.time() < fim_direto:
                alvo = _target_consulta_solar(pagina)
                if alvo is not None:
                    return alvo
                time.sleep(0.25)
        except Exception:
            pass

    _clicar_menu_consulta_processo_solar(pagina)
    fim_menu = time.time() + 8
    while time.time() < fim_menu:
        alvo = _target_consulta_solar(pagina)
        if alvo is not None:
            return alvo
        time.sleep(0.25)

    try:
        _navegar_consulta_processo_solar(pagina)
    except Exception:
        pagina.goto(_SOLAR_BASE_URL, wait_until="domcontentloaded", timeout=30000)
        _clicar_menu_consulta_processo_solar(pagina)

    fim = time.time() + 15
    while time.time() < fim:
        alvo = _target_consulta_solar(pagina)
        if alvo is not None:
            return alvo
        time.sleep(0.25)
    raise RuntimeError(
        "Não encontrei a tela de consulta de processo do Solar. "
        "Se apareceu a página de login, entre no Solar e clique novamente no processo."
    )


def _chave_processo_solar(alvo: Any) -> str:
    try:
        conteudo = alvo.content()
    except Exception:
        return ""
    match = re.search(r"chaveProcesso=([^&\"']+)", html.unescape(conteudo))
    return match.group(1) if match else ""


def _alvo_contem_dados_processo_solar(alvo: Any, processo: dict[str, str]) -> bool:
    try:
        texto = alvo.locator("body").inner_text(timeout=1000)
    except Exception:
        return False
    texto_normalizado = re.sub(r"\s+", " ", texto).lower()
    numero = processo.get("numero", "")
    numero_sem_zero = processo.get("numero_sem_zero", "")
    ano = processo.get("ano", "")
    dv = processo.get("dv", "")
    tem_tela_dados = "dados do processo digital" in texto_normalizado or "processo digital" in texto_normalizado
    tem_numero = (
        processo.get("formatado", "") in texto
        or (numero and numero in texto and ano in texto)
        or (numero_sem_zero and numero_sem_zero in texto and ano in texto)
    )
    if dv:
        tem_numero = tem_numero and (dv in texto or processo.get("formatado", "") in texto)
    return tem_tela_dados and tem_numero


def _fill_primeiro_seletor(alvo: Any, seletores: tuple[str, ...], valor: str) -> bool:
    for seletor in seletores:
        try:
            locator = alvo.locator(seletor)
            if locator.count() > 0:
                locator.first.fill(valor)
                return True
        except Exception:
            continue
    return False


def _select_primeiro_seletor(alvo: Any, seletores: tuple[str, ...], valor: str) -> bool:
    for seletor in seletores:
        try:
            locator = alvo.locator(seletor)
            if locator.count() > 0:
                locator.first.select_option(valor)
                return True
        except Exception:
            continue
    return False


def _clicar_botao_consultar_solar(alvo: Any) -> None:
    seletores = (
        "input[name='btnConsultar']",
        "input[value*='Consultar']",
        "button:has-text('Consultar')",
        "input[type='submit']",
    )
    for seletor in seletores:
        try:
            locator = alvo.locator(seletor)
            if locator.count() > 0:
                locator.first.click(timeout=5000)
                return
        except Exception:
            continue
    raise RuntimeError("Botão Consultar não encontrado no Solar.")


def _clicar_resultado_processo_solar(alvo: Any, processo: dict[str, str]) -> bool:
    script = """
    (processo) => {
      const normalizar = (valor) => String(valor || "")
        .normalize("NFD")
        .replace(/[\\u0300-\\u036f]/g, "")
        .replace(/\\s+/g, " ")
        .trim()
        .toLowerCase();
      const numero = String(processo.numero || "");
      const numeroSemZero = String(processo.numero_sem_zero || "");
      const ano = String(processo.ano || "");
      const formatado = String(processo.formatado || "");
      const combina = (texto) => {
        const raw = String(texto || "");
        const norm = normalizar(raw);
        return (formatado && raw.includes(formatado))
          || (ano && numero && raw.includes(numero) && raw.includes(ano))
          || (ano && numeroSemZero && raw.includes(numeroSemZero) && raw.includes(ano))
          || (norm.includes("processo digital") && ano && norm.includes(ano));
      };
      const clicaveis = Array.from(document.querySelectorAll("a, button, input[type='button'], input[type='submit'], img[onclick], span[onclick]"));
      for (const el of clicaveis) {
        const texto = `${el.textContent || ""} ${el.value || ""} ${el.title || ""} ${el.getAttribute("href") || ""} ${el.getAttribute("onclick") || ""}`;
        if (combina(texto) || /chaveProcesso=/i.test(texto)) {
          el.click();
          return true;
        }
      }
      const linhas = Array.from(document.querySelectorAll("tr, li, div"));
      for (const linha of linhas) {
        if (!combina(linha.textContent || "")) continue;
        const link = linha.querySelector("a, button, input[type='button'], input[type='submit'], img[onclick], span[onclick]");
        if (link) {
          link.click();
          return true;
        }
      }
      return false;
    }
    """
    try:
        return bool(alvo.evaluate(script, processo))
    except Exception:
        return False


def _abrir_processo_solar_na_pagina(pagina: Any, numero_processo: str) -> dict[str, Any]:
    processo = _quebrar_processo_solar(numero_processo)
    if not processo:
        raise HTTPException(status_code=422, detail="Número do processo inválido para consulta no Solar.")

    alvo = _abrir_consulta_processos_solar(pagina)
    numero = processo["numero"]
    ano = processo["ano"]
    processo_formatado = processo["formatado"]

    _selecionar_dados_do_processo_solar(alvo)
    _select_primeiro_seletor(alvo, ("#procDocCorrespDTO\\.flTipoprocesso", "[name='procDocCorrespDTO.flTipoprocesso']"), "P")
    if not _fill_primeiro_seletor(alvo, ("#procDocCorrespDTO\\.nuProcessooficial", "[name='procDocCorrespDTO.nuProcessooficial']"), numero):
        raise RuntimeError("Campo do número do processo não encontrado no Solar.")
    if not _fill_primeiro_seletor(alvo, ("#procDocCorrespDTO\\.nuAno", "[name='procDocCorrespDTO.nuAno']"), ano):
        raise RuntimeError("Campo do ano do processo não encontrado no Solar.")
    _fill_primeiro_seletor(alvo, ("#procDocCorrespDTO\\.nuDigitoVerificador", "[name='procDocCorrespDTO.nuDigitoVerificador']"), "")
    _clicar_botao_consultar_solar(alvo)

    fim = time.time() + 45
    chave_encontrada = ""
    chave_encontrada_em: float | None = None
    resultado_clicado = False
    while time.time() < fim:
        for alvo_dados in [pagina, *list(getattr(pagina, "frames", []) or [])]:
            if _alvo_contem_dados_processo_solar(alvo_dados, processo):
                return {"chaveProcesso": chave_encontrada, "url": pagina.url, "processo": processo_formatado}
            if not resultado_clicado and _clicar_resultado_processo_solar(alvo_dados, processo):
                resultado_clicado = True
                time.sleep(1.0)

        frame_pasta = _frame_por_nome(pagina, "frameNPasta")
        if frame_pasta:
            try:
                texto = frame_pasta.locator("body").inner_text(timeout=1200)
                match_url = re.search(r"chaveProcesso=([^&]+)", frame_pasta.url)
                chave = match_url.group(1) if match_url else ""
                if processo_formatado in texto or (numero.lstrip("0") in texto and ano in texto):
                    return {"chaveProcesso": chave, "url": pagina.url, "processo": processo_formatado}
                if chave_encontrada and chave_encontrada in frame_pasta.url:
                    return {"chaveProcesso": chave_encontrada, "url": pagina.url, "processo": processo_formatado}
            except Exception:
                pass

        alvo_atual = _target_consulta_solar(pagina)
        if alvo_atual is not None:
            chave = _chave_processo_solar(alvo_atual)
            if chave and chave != chave_encontrada:
                chave_encontrada = chave
                chave_encontrada_em = time.time()

        # Retorna logo que o link do processo apareceu na busca e o navegador
        # já começou a abrir o detalhe — o usuário vê o restante no próprio browser.
        if chave_encontrada and chave_encontrada_em and (time.time() - chave_encontrada_em) >= 1.5:
            return {"chaveProcesso": chave_encontrada, "url": pagina.url, "processo": processo_formatado}

        time.sleep(0.5)

    if chave_encontrada:
        return {"chaveProcesso": chave_encontrada, "url": pagina.url, "processo": processo_formatado}
    raise RuntimeError(f"Não consegui abrir o processo no Solar: {processo_formatado}.")


@app.post("/api/solar/processo/abrir")
def abrir_processo_solar_endpoint(payload: AbrirProcessoSolarPayload) -> dict[str, Any]:
    numero_processo = str(payload.numeroProcesso or "").strip()
    if not numero_processo:
        raise HTTPException(status_code=422, detail="Informe o número do processo.")

    chrome_service = _chrome_service()
    porta = obter_porta_chrome()
    playwright = None
    try:
        chrome_service.instalar_bookmarklets_autoliquid()
        if not chrome_service.chrome_esta_pronto(porta):
            chrome_service.abrir_chrome(
                porta,
                aguardar=True,
                timeout_s=20,
                url_inicial=_SOLAR_BASE_URL,
            )
        playwright, pagina_base = chrome_service.conectar_chrome_cdp(porta, abrir_se_fechado=True)
        contexto = pagina_base.context
        pagina = _localizar_pagina_solar(contexto)
        if pagina is None:
            pagina = contexto.new_page()
            pagina.goto(_SOLAR_BASE_URL, wait_until="domcontentloaded", timeout=45000)

        resultado = _abrir_processo_solar_na_pagina(pagina, numero_processo)
        try:
            pagina.bring_to_front()
        except Exception:
            pass
        return {
            "success": True,
            "chromeStatus": "pronto",
            "chromePorta": porta,
            "mensagem": f"Processo {resultado['processo']} aberto no Solar.",
            **resultado,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


def _preencher_login_iss_pagina(pagina: Any, login: str, senha: str) -> dict[str, Any]:
    script = """
    ({ login, senha }) => {
      const norm = (value) => String(value || "")
        .normalize("NFD")
        .replace(/[\\u0300-\\u036f]/g, "")
        .toLowerCase();
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.visibility !== "hidden"
          && style.display !== "none"
          && rect.width > 0
          && rect.height > 0
          && !el.disabled
          && !el.readOnly;
      };
      const setValue = (el, value, dispatchBlur) => {
        const proto = el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (setter) setter.call(el, value);
        else el.value = value;
        el.dispatchEvent(new Event("input",  { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        if (dispatchBlur) el.dispatchEvent(new Event("blur", { bubbles: true }));
      };
      const inputs = Array.from(document.querySelectorAll("input, textarea"))
        .filter((el) => visible(el));
      const fieldText = (el) => norm([
        el.name,
        el.id,
        el.placeholder,
        el.getAttribute("aria-label"),
        el.getAttribute("title"),
        document.querySelector(`label[for="${CSS.escape(el.id || "")}"]`)?.textContent,
        el.closest("label")?.textContent,
      ].join(" "));
      const password = inputs.find((el) => norm(el.getAttribute("type")) === "password")
        || inputs.find((el) => /senha|password/.test(fieldText(el)));
      const loginTypes = new Set(["", "text", "email", "tel", "search", "number"]);
      const loginCandidates = inputs.filter((el) => {
        const type = norm(el.getAttribute("type"));
        return el !== password && loginTypes.has(type);
      });
      const scoreLogin = (el) => {
        const text = fieldText(el);
        let score = 0;
        if (/login|usuario|user|cnpj|cpf|inscricao|codigo|matricula|email/.test(text)) score += 20;
        if (/senha|password|buscar|pesquisar|captcha/.test(text)) score -= 40;
        if (el.value) score -= 2;
        return score;
      };
      const username = loginCandidates
        .map((el) => ({ el, score: scoreLogin(el) }))
        .sort((a, b) => b.score - a.score)[0]?.el;

      const buttons = Array.from(document.querySelectorAll("button, input[type='submit'], input[type='button'], a"))
        .filter((el) => visible(el));
      const submit = buttons.find((el) => /entrar|acessar|login|logar|conectar|prosseguir/.test(norm(`${el.textContent || ""} ${el.value || ""} ${el.title || ""} ${el.id || ""} ${el.className || ""}`)));

      // Preenche usuário SEM blur para evitar re-render JSF antes de preencher a senha
      if (username) {
        username.focus();
        setValue(username, login, false);
      }

      // Preenche senha após breve delay (aguarda possível atualização JSF do usuário)
      // e clica em submeter logo após
      setTimeout(() => {
        if (password) {
          password.focus();
          setValue(password, senha, true);
        }
        setTimeout(() => {
          if (submit) {
            submit.click();
          } else if (password) {
            password.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
          }
        }, 300);
      }, 400);

      return {
        loginPreenchido: Boolean(username),
        senhaPreenchida: Boolean(password),
        submitClicado: Boolean(submit),
      };
    }
    """
    melhor = {"loginPreenchido": False, "senhaPreenchida": False, "submitClicado": False}
    for frame in pagina.frames:
        try:
            result = frame.evaluate(script, {"login": login, "senha": senha})
        except Exception:
            continue
        if result.get("loginPreenchido") or result.get("senhaPreenchida"):
            melhor = result
        if result.get("loginPreenchido") and result.get("senhaPreenchida"):
            return result
    return melhor


@app.get("/api/iss/portais")
def obter_portais_iss() -> dict[str, Any]:
    config = _carregar_portais_iss_config()
    # Materializa no Turso caso ainda seja o padrão
    try:
        turso = _turso_service()
        if not turso.obter_tabela_operacional(_ISS_PORTAIS_CONFIG_KEY):
            _salvar_portais_iss_config(config)
    except Exception:
        pass
    portais = [{"id": k, **v} for k, v in config.items()]
    return {"portais": portais}


@app.put("/api/iss/portais")
def salvar_portais_iss(body: dict[str, Any]) -> dict[str, Any]:
    portais_raw = body.get("portais") or []
    config: dict[str, dict[str, str]] = {}
    for item in portais_raw:
        pid = str(item.get("id", "") or "").strip()
        if not pid:
            continue
        config[pid] = {
            "nome": str(item.get("nome", "") or "").strip(),
            "url": str(item.get("url", "") or "").strip(),
            "login": str(item.get("login", "") or "").strip(),
            "senha": str(item.get("senha", "") or "").strip(),
        }
    try:
        _salvar_portais_iss_config(config)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível salvar as configurações dos portais ISS: {exc}",
        ) from exc
    return {"success": True}


@app.post("/api/iss/abrir")
def abrir_portal_iss(body: dict[str, Any]) -> dict[str, Any]:
    portal_id = str(body.get("portal") or "").strip()
    config = _carregar_portais_iss_config()
    portal = config.get(portal_id)
    if not portal:
        raise HTTPException(status_code=404, detail="Portal ISS não cadastrado.")

    chrome_service = _chrome_service()
    porta = obter_porta_chrome()
    playwright_obj = None
    try:
        if not chrome_service.chrome_esta_pronto(porta):
            chrome_service.abrir_chrome(porta, aguardar=True, timeout_s=20)
        playwright_obj, pagina_base = chrome_service.conectar_chrome_cdp(porta, abrir_se_fechado=True)
        contexto = pagina_base.context
        pagina = contexto.new_page()
        pagina.goto(portal["url"], wait_until="domcontentloaded", timeout=45000)
        try:
            pagina.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        time.sleep(0.8)

        # Primeira passagem: JS preenche campos genéricos (funciona bem para usuário
        # em portais como Betha/JSF; senha pode não ser preenchida em portais com
        # teclado virtual — a segunda passagem cobre isso via keystrokes).
        _preencher_login_iss_pagina(pagina, portal["login"], portal["senha"])
        time.sleep(1.0)

        login_valor = portal["login"]
        senha_valor = portal["senha"]
        senha_preenchida = False
        submit_clicado   = False

        _SENHA_SELS = [
            'input[type="password"]:visible',
            'input[type="password"]',
        ]
        _LOGIN_SELS = [
            'input[type="text"]:visible',
            'input[type="email"]:visible',
            'input[type="number"]:visible',
        ]
        _SUBMIT_SELS = [
            'input[type="submit"]:visible',
            'button[type="submit"]:visible',
            'button:visible',
            'input[type="submit"]',
        ]

        def _clicar_submit() -> bool:
            for sel in _SUBMIT_SELS:
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=1000):
                        loc.click(timeout=3000)
                        return True
                except Exception:
                    continue
            return False

        def _tentar_fill_nativo() -> tuple[bool, bool]:
            """Preenche login+senha via keystrokes reais e clica submit.
            Se os campos já estiverem preenchidos (autofill), vai direto ao submit.
            Retorna (senha_ok, submit_ok)."""
            _s_ok = False

            # Verifica se a senha já está preenchida (autofill ou passagem anterior)
            _senha_ja_preenchida = False
            for sel in _SENHA_SELS:
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=500):
                        val = loc.input_value(timeout=500)
                        if val:
                            _senha_ja_preenchida = True
                        break
                except Exception:
                    continue

            if _senha_ja_preenchida:
                # Campos já preenchidos — apenas clica submit
                time.sleep(0.2)
                return True, _clicar_submit()

            # Campos vazios — preenche login via keystrokes
            for sel in _LOGIN_SELS:
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=500):
                        loc.triple_click(timeout=2000)
                        pagina.keyboard.type(login_valor, delay=30)
                        break
                except Exception:
                    continue

            # Preenche senha via keystrokes
            for sel in _SENHA_SELS:
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=1000):
                        loc.triple_click(timeout=2000)
                        pagina.keyboard.type(senha_valor, delay=40)
                        _s_ok = True
                        break
                except Exception:
                    continue

            if _s_ok:
                time.sleep(0.3)
                return True, _clicar_submit()

            return _s_ok, False

        senha_preenchida, submit_clicado = _tentar_fill_nativo()

        # Alguns portais (ex: Prefeitura Moderna / Gov. Celso Ramos) fazem redirect
        # após o primeiro submit e recarregam o formulário limpo — é necessário
        # preencher e submeter uma segunda vez.
        if submit_clicado:
            try:
                pagina.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            time.sleep(0.8)

            # Verifica se ainda há formulário de login visível (campo senha vazio = reset)
            _ainda_no_login = False
            for sel in _SENHA_SELS:
                try:
                    loc = pagina.locator(sel).first
                    if loc.count() and loc.is_visible(timeout=1000):
                        val = loc.input_value(timeout=1000)
                        if val == "":
                            _ainda_no_login = True
                        break
                except Exception:
                    continue

            if _ainda_no_login:
                # Preenche também o campo de login (pode ter sido limpo)
                for sel in _LOGIN_SELS:
                    try:
                        loc = pagina.locator(sel).first
                        if loc.count() and loc.is_visible(timeout=1000):
                            cur = loc.input_value(timeout=500)
                            if cur == "":
                                loc.fill(login_valor, timeout=3000)
                            break
                    except Exception:
                        continue
                time.sleep(0.3)
                s2, sub2 = _tentar_fill_nativo()
                senha_preenchida = senha_preenchida or s2
                submit_clicado   = submit_clicado   or sub2

        return {
            "ok": True,
            "portal": portal["nome"],
            "loginPreenchido": True,
            "senhaPreenchida": senha_preenchida,
            "submitClicado": submit_clicado,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Não foi possível abrir o portal ISS: {exc}") from exc
    finally:
        if playwright_obj:
            try:
                playwright_obj.stop()
            except Exception:
                pass


@app.post("/api/processar")
async def processar_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    apuracao: str = Form(default=""),
    vencimento: str = Form(default=""),
) -> dict[str, Any]:
    tmp_path = None
    try:
        sufixo = os.path.splitext(file.filename or ".pdf")[1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
            tmp_path = tmp.name
            conteudo = await file.read()
            tmp.write(conteudo)

        dados_extraidos = _extrator().extrair_dados_pdf(tmp_path, nome_arquivo=file.filename)
        if not dados_extraidos:
            # Verifica se é uma Remessa de bolsa enviada pelo lugar errado.
            # Tenta detectar "REMESSA NNNNNN" na primeira página do PDF.
            _é_remessa = bool(re.search(r"\bremessa\b", str(file.filename or ""), re.IGNORECASE))
            if not _é_remessa:
                try:
                    import pdfplumber as _pdfplumber
                    with _pdfplumber.open(tmp_path) as _pdf_chk:
                        _pg0 = (_pdf_chk.pages[0].extract_text() or "") if _pdf_chk.pages else ""
                    _é_remessa = bool(re.search(r"\bREMESSA\s+\d+", _pg0, re.IGNORECASE))
                except Exception:
                    pass
            if _é_remessa:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Este arquivo parece ser uma Remessa de bolsa, não uma Liquidação. "
                        "Carregue primeiro o PDF de Liquidação (DAL) e depois vincule a remessa "
                        "pelo botão 'Remessa' dentro do documento."
                    ),
                )
            raise HTTPException(
                status_code=422,
                detail="Não foi possível extrair dados do PDF. Verifique se é um documento LF válido.",
            )

        from comprasnet.centro_custo import requer_centro_custo

        doc_id = str(uuid4())
        alertas: list[str] =[]
        simples = False

        cnpj_limpo = "".join(c for c in str(dados_extraidos.get("CNPJ", "")) if c.isdigit())
        if cnpj_limpo:
            try:
                empresa = _consulta_cnpj().obter_dados_empresa(cnpj_limpo)
                optante = empresa.get("optante_simples")
                simples = bool(optante) if optante is not None else False
                nome_pdf = str(dados_extraidos.get("Nome do Credor", "") or "").strip()
                if not nome_pdf:
                    razao = empresa.get("razao_social", "")
                    if razao:
                        dados_extraidos["Nome do Credor"] = razao
            except Exception:
                pass

        novo_doc = {
            "dados_extraidos": dados_extraidos,
            "lf_numero": "",
            "ugr_numero": "",
            "vencimento_documento": "",
            "optante_simples": bool(simples) if cnpj_limpo else False,
            "requires_centro_custo": requer_centro_custo(dados_extraidos),
            "dates": {"apuracao": apuracao, "vencimento": vencimento},
            "etapas": deepcopy(ETAPAS_BASE),
            "logs":[],
            "logs_simples": _gerar_logs_simples_conferencia(dados_extraidos),
            "alertas": alertas,
            "is_running": False,
            "cancel_requested": False,
        }
        _local_cache_service().salvar_documento(doc_id, novo_doc)
        
        # Sincroniza em background para não travar a resposta
        background_tasks.add_task(_sincronizar_documento_remoto, doc_id, novo_doc)

        return {"success": True, "documentoId": doc_id}

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Erro ao processar PDF")
        raise HTTPException(
            status_code=500,
            detail=_detalhar_erro_execucao("Processamento do PDF", exc),
        ) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.get("/api/documentos/{doc_id}")
def obter_documento(doc_id: str) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return _montar_documento_processado(doc_id, doc)


@app.post("/api/documentos/{doc_id}/remessas-bolsa")
async def processar_remessa_bolsa(
    doc_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    tmp_path = None
    try:
        sufixo = os.path.splitext(file.filename or ".pdf")[1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
            tmp_path = tmp.name
            conteudo = await file.read()
            tmp.write(conteudo)

        remessa = _extrator().extrair_remessa_bolsa_pdf(tmp_path, nome_arquivo=file.filename)
        if not remessa or not remessa.get("numeroRemessa") or not remessa.get("bolsistas"):
            raise HTTPException(
                status_code=422,
                detail="Não foi possível extrair a remessa de bolsa. Verifique se é um PDF de remessa válido.",
            )

        dados_extraidos = doc.get("dados_extraidos", {}) if isinstance(doc.get("dados_extraidos"), dict) else {}
        alertas: list[str] = []
        processo_doc = str(dados_extraidos.get("Processo", "") or "").strip()
        sol_doc = str(dados_extraidos.get("Solicitação de Pagamento", "") or "").strip()
        remessas_esperadas = {
            str(item.get("Número da Remessa", "") or "").strip()
            for item in dados_extraidos.get("Bolsas", [])
            if isinstance(item, dict)
        }

        if processo_doc and remessa.get("processo") and remessa["processo"] != processo_doc:
            alertas.append(f"Processo da remessa ({remessa['processo']}) difere da liquidação ({processo_doc}).")
        if sol_doc and remessa.get("solicitacaoPagamento") and remessa["solicitacaoPagamento"] != sol_doc:
            alertas.append(f"Solicitação da remessa ({remessa['solicitacaoPagamento']}) difere da liquidação ({sol_doc}).")
        if remessas_esperadas and remessa["numeroRemessa"] not in remessas_esperadas:
            alertas.append(f"Remessa {remessa['numeroRemessa']} não aparece na lista de bolsas da liquidação.")
        remessa["alertas"] = alertas

        remessas_existentes = doc.get("remessas_bolsa", [])
        if not isinstance(remessas_existentes, list):
            remessas_existentes = []
        remessas_filtradas = [
            item for item in remessas_existentes
            if str(item.get("numeroRemessa", "") or "") != str(remessa["numeroRemessa"])
        ]
        remessas_filtradas.append(remessa)
        remessas_filtradas.sort(key=lambda item: str(item.get("numeroRemessa", "")))
        doc["remessas_bolsa"] = remessas_filtradas

        _local_cache_service().salvar_documento(doc_id, doc)
        background_tasks.add_task(_sincronizar_documento_remoto, doc_id, doc)

        return _montar_documento_processado(doc_id, doc)

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Erro ao processar remessa de bolsa")
        raise HTTPException(
            status_code=500,
            detail=_detalhar_erro_execucao("Processamento da remessa", exc),
        ) from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.post("/api/documentos/{doc_id}/salvar-preenchimento")
def salvar_preenchimento_documento(doc_id: str, payload: ExecucaoPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    if doc.get("is_running"):
        raise HTTPException(status_code=409, detail="Não é possível salvar durante uma execução em andamento.")

    doc["lf_numero"] = payload.lfNumero
    doc["ugr_numero"] = payload.ugrNumero
    doc["vencimento_documento"] = payload.vencimentoDocumento
    doc["usar_conta_pdf"] = payload.usarContaPdf
    doc["conta_banco"] = payload.contaBanco
    doc["conta_agencia"] = payload.contaAgencia
    doc["conta_conta"] = payload.contaConta
    doc["vpd_manual"] = payload.vpd
    if payload.codigoOperacional:
        doc["codigo_operacional"] = payload.codigoOperacional
    
    _local_cache_service().salvar_documento(doc_id, doc)
    background_tasks.add_task(_sincronizar_documento_remoto, doc_id, doc)
    return _montar_documento_processado(doc_id, doc)


@app.post("/api/documentos/{doc_id}/pendencias/{pendencia_id}")
def atualizar_pendencia_documento(
    doc_id: str,
    pendencia_id: str,
    payload: PendenciaResolvidaPayload,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    pendencia_id = str(pendencia_id or "").strip()
    if not pendencia_id:
        raise HTTPException(status_code=400, detail="Pendência inválida.")

    resolvidas = {
        str(item or "").strip()
        for item in (doc.get("pendencias_resolvidas") or [])
        if str(item or "").strip()
    }
    if payload.resolvida:
        resolvidas.add(pendencia_id)
    else:
        resolvidas.discard(pendencia_id)

    doc["pendencias_resolvidas"] = sorted(resolvidas)
    _local_cache_service().salvar_documento(doc_id, doc)
    background_tasks.add_task(_sincronizar_documento_remoto, doc_id, doc)
    return _montar_documento_processado(doc_id, doc)


@app.post("/api/documentos/{doc_id}/executar-todas")
def executar_todas(doc_id: str, payload: ExecucaoPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    if doc.get("is_running"):
        raise HTTPException(status_code=409, detail="Execução já em andamento.")

    doc["is_running"] = True
    doc["cancel_requested"] = False
    doc["lf_numero"] = payload.lfNumero
    doc["ugr_numero"] = payload.ugrNumero
    doc["vencimento_documento"] = payload.vencimentoDocumento
    doc["usar_conta_pdf"] = payload.usarContaPdf
    doc["conta_banco"] = payload.contaBanco
    doc["conta_agencia"] = payload.contaAgencia
    doc["conta_conta"] = payload.contaConta
    doc["vpd_manual"] = payload.vpd
    doc["etapas"] = deepcopy(ETAPAS_BASE)
    doc["logs"] =[]
    doc["logs_simples"] = _gerar_logs_simples_conferencia(doc["dados_extraidos"])
    
    _local_cache_service().salvar_documento(doc_id, doc)

    background_tasks.add_task(_task_executar_todas, doc_id)

    return _montar_documento_processado(doc_id, doc)


@app.post("/api/documentos/{doc_id}/executar-etapa/{etapa_id}")
def executar_etapa(doc_id: str, etapa_id: int, payload: ExecucaoPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if etapa_id not in range(0, 6):
        raise HTTPException(status_code=400, detail=f"Etapa inválida: {etapa_id}")

    if doc.get("is_running"):
        raise HTTPException(status_code=409, detail="Execução já em andamento.")

    doc["is_running"] = True
    doc["cancel_requested"] = False
    if payload.lfNumero:
        doc["lf_numero"] = payload.lfNumero
    if payload.ugrNumero:
        doc["ugr_numero"] = payload.ugrNumero
    if payload.vencimentoDocumento:
        doc["vencimento_documento"] = payload.vencimentoDocumento
    doc["usar_conta_pdf"] = payload.usarContaPdf
    if payload.contaBanco:
        doc["conta_banco"] = payload.contaBanco
    if payload.contaAgencia:
        doc["conta_agencia"] = payload.contaAgencia
    if payload.contaConta:
        doc["conta_conta"] = payload.contaConta
    if payload.vpd:
        doc["vpd_manual"] = payload.vpd

    _local_cache_service().salvar_documento(doc_id, doc)

    background_tasks.add_task(_task_executar_etapa, doc_id, etapa_id)

    return _montar_documento_processado(doc_id, doc)


@app.post("/api/documentos/{doc_id}/executar-deducao/{ded_id}")
def executar_deducao_individual(doc_id: str, ded_id: int, payload: ExecucaoPayload, background_tasks: BackgroundTasks) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    deducoes_raw = doc["dados_extraidos"].get("Deduções",[])

    if ded_id < 1 or ded_id > len(deducoes_raw):
        raise HTTPException(status_code=404, detail=f"Dedução {ded_id} não encontrada.")

    if doc.get("is_running"):
        raise HTTPException(status_code=409, detail="Execução já em andamento.")

    doc["is_running"] = True
    doc["cancel_requested"] = False
    if payload.lfNumero:
        doc["lf_numero"] = payload.lfNumero
    if payload.ugrNumero:
        doc["ugr_numero"] = payload.ugrNumero
    if payload.vencimentoDocumento:
        doc["vencimento_documento"] = payload.vencimentoDocumento

    _local_cache_service().salvar_documento(doc_id, doc)

    background_tasks.add_task(_task_executar_deducao, doc_id, ded_id, payload.model_dump())

    return _montar_documento_processado(doc_id, doc)


@app.post("/api/documentos/{doc_id}/apropriar-siafi")
def apropriar_siafi(doc_id: str) -> dict[str, Any]:
    doc = _local_cache_service().obter_documento(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    logs: list[str] =[]
    try:
        import comprasnet.finalizar as comprasnet_finalizar
        comprasnet_finalizar.executar()
        logs.append("✓ Apropriação SIAFI concluída.")
        return {"success": True, "mensagem": "Apropriação SIAFI concluída com sucesso.", "logs": logs}
    except Exception as exc:
        logs.append(f"✗ {_detalhar_erro_execucao('Apropriação SIAFI', exc)}")
        log.exception("Erro ao apropriar SIAFI")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/documentos/{doc_id}/parar-execucao")
def parar_execucao(doc_id: str) -> dict[str, Any]:
    doc = _obter_documento_cache_ou_turso(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    doc["cancel_requested"] = True
    _local_cache_service().salvar_documento(doc_id, doc)
    _sincronizar_documento_remoto(doc_id, doc)
    resultado = _montar_documento_processado(doc_id, doc)
    return {**resultado, "success": True, "mensagem": "Solicitação de parada enviada."}


@app.post("/api/registros-liquidacao")
def registrar_liquidacao(payload: RegistroLiquidacaoPayload) -> dict[str, Any]:
    payload_local = {
        "documentoId": payload.documentoId,
        "numeroProcesso": payload.numeroProcesso,
        "finalizada": payload.finalizada,
        "tipoDocumento": payload.tipoDocumento,
        "numeroDocumento": payload.numeroDocumento,
        "dificuldade": payload.dificuldade,
        "servidorNome": payload.servidorNome,
        "servidorUsername": payload.servidorUsername,
    }
    try:
        _local_cache_service().salvar_registro_liquidacao(payload_local, sincronizado=False)
    except Exception:
        log.debug("Falha ao salvar registro de liquidação no cache local", exc_info=True)

    def _sincronizar_registro() -> bool:
        try:
            _turso_service().registrar_liquidacao(
                documento_id=payload.documentoId,
                numero_processo=payload.numeroProcesso,
                finalizada=payload.finalizada,
                tipo_documento=payload.tipoDocumento,
                numero_documento=payload.numeroDocumento,
                dificuldade=payload.dificuldade,
                servidor_nome=payload.servidorNome,
                servidor_username=payload.servidorUsername,
            )
            if payload.finalizada and payload.numeroProcesso:
                _turso_service().salvar_conclusao_fila(
                    numero_processo=payload.numeroProcesso,
                    sol_pagamento="",
                    concluido=True,
                    autor=payload.servidorNome or payload.servidorUsername,
                )
            try:
                _local_cache_service().salvar_registro_liquidacao(payload_local, sincronizado=True)
            except Exception:
                log.debug("Falha ao marcar registro de liquidação como sincronizado", exc_info=True)
            return True
        except Exception:
            log.warning("Registro de liquidação salvo localmente; sincronização com Turso falhou.", exc_info=True)
            return False

    # Turso sempre em background — o dado já está salvo no cache local acima,
    # então não há risco de perda. Retornar imediatamente elimina os ~15-30s
    # de espera que vinham da chamada síncrona à rede.
    Thread(target=_sincronizar_registro, name="liquidacao-registro-sync", daemon=True).start()

    return {"success": True, "local": True, "sincronizado": False}


@app.get("/api/registros-liquidacao/pendente")
def obter_registro_liquidacao_pendente(
    servidor_nome: str = Query(default=""),
    servidor_username: str = Query(default=""),
) -> dict[str, Any]:
    try:
        pendente = _turso_service().obter_liquidacao_pendente(
            servidor_nome=servidor_nome,
            servidor_username=servidor_username,
        )
        return {"pendente": pendente}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível consultar liquidação pendente: {exc}") from exc


@app.delete("/api/registros-liquidacao/pendente/{documento_id}")
def descartar_registro_liquidacao_pendente(documento_id: str) -> dict[str, Any]:
    try:
        _turso_service().descartar_liquidacao_pendente(documento_id)
        return {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível descartar o retorno pendente: {exc}") from exc


def _registrar_liquidacao_sincrono(payload: RegistroLiquidacaoPayload) -> dict[str, Any]:
    try:
        _turso_service().registrar_liquidacao(
            documento_id=payload.documentoId,
            numero_processo=payload.numeroProcesso,
            finalizada=payload.finalizada,
            tipo_documento=payload.tipoDocumento,
            numero_documento=payload.numeroDocumento,
            dificuldade=payload.dificuldade,
            servidor_nome=payload.servidorNome,
            servidor_username=payload.servidorUsername,
        )
        return {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível registrar a liquidação: {exc}") from exc


@app.get("/api/datas-globais")
def datas_globais_get() -> dict[str, str]:
    if _fonte_dados_habilitada("datas_globais", "turso"):
        turso = _turso_service()
        if turso.turso_configurado():
            try:
                datas = turso.obter_datas_globais()
                if datas.get("vencimento") or datas.get("apuracao"):
                    return datas
            except Exception:
                log.debug("Falha ao obter datas globais do Turso; usando fallback local.", exc_info=True)
        locais = obter_datas_salvas()
        return {
            "apuracao": str(locais.get("apuracao", "")),
            "vencimento": str(locais.get("vencimento", "")),
        }
    if not _fonte_dados_habilitada("datas_globais", "supabase"):
        return {"vencimento": "", "apuracao": ""}
    try:
        return _postgres_service().obter_datas_globais()
    except Exception:
        log.debug("Falha ao obter datas globais do Supabase.", exc_info=True)
        return {"vencimento": "", "apuracao": ""}


def _salvar_datas_globais(payload: ProcessDatesPayload, *, exigir_turso: bool = False) -> dict[str, str]:
    dados = salvar_datas_processo(payload.apuracao, payload.vencimento)
    errors: list[str] = []
    if _fonte_dados_habilitada("datas_globais", "turso"):
        try:
            turso = _turso_service()
            if not turso.turso_configurado():
                raise RuntimeError("Turso não configurado.")
            turso.salvar_datas_globais(dados)
        except Exception as exc:
            if exigir_turso:
                errors.append(str(exc))
            log.warning("Falha ao salvar datas globais no Turso.", exc_info=True)
    elif exigir_turso:
        errors.append("datas_globais não está habilitado para Turso.")
    if errors:
        raise HTTPException(status_code=503, detail=f"Não foi possível salvar datas globais no Turso: {'; '.join(errors)}")
    result = {
        "apuracao": str(dados.get("apuracao", "")),
        "vencimento": str(dados.get("vencimento", "")),
    }
    _broadcast_fila_event({"type": "datas-globais-atualizadas", "dates": result})
    return result


@app.put("/api/datas-globais")
def datas_globais_put(payload: ProcessDatesPayload) -> dict[str, str]:
    return _salvar_datas_globais(payload, exigir_turso=True)


@app.get("/api/process-dates")
def process_dates() -> dict[str, str]:
    dados = obter_datas_salvas()
    return {
        "apuracao": str(dados.get("apuracao", "")),
        "vencimento": str(dados.get("vencimento", "")),
    }


@app.put("/api/process-dates")
def salvar_process_dates(payload: ProcessDatesPayload) -> dict[str, str]:
    return _salvar_datas_globais(payload)


@app.post("/api/historico/buscar")
def buscar_historico(payload: HistoricoSearchPayload) -> dict[str, Any]:
    def _buscar(service: Any) -> list[dict[str, Any]]:
        if payload.cnpj:
            contratos = payload.contratos or ([payload.contrato] if payload.contrato else [])
            return service.buscar_historico_por_cnpj(payload.cnpj, contratos, limite=40)
        if payload.numero_processo:
            return service.buscar_historico_por_numero_processo(payload.numero_processo, limite=40)
        if payload.contrato:
            return service.buscar_historico_por_contrato(payload.contrato, limite=40)
        if payload.empenho:
            return service.buscar_historico_por_empenho(payload.empenho, limite=40)
        raise HTTPException(status_code=422, detail="Informe CNPJ, processo, contrato ou empenho.")

    errors: list[str] = []
    if _fonte_dados_habilitada("execucoes", "turso"):
        turso = _turso_service()
        if not turso.turso_configurado():
            raise HTTPException(status_code=503, detail="Turso não configurado.")
        processos = _buscar(turso)
        return {"processos": processos, "total": len(processos), "source": "turso"}

    if _fonte_dados_habilitada("execucoes", "supabase"):
        try:
            processos = _buscar(_postgres_service())
            return {"processos": processos, "total": len(processos), "source": "supabase"}
        except Exception as exc:
            errors.append(f"Supabase: {exc}")

    raise HTTPException(status_code=500, detail="; ".join(errors) or "Nenhuma fonte de historico habilitada.")


@app.get("/api/configuracoes")
def configuracoes_web() -> dict[str, Any]:
    return _web_config_service().carregar_configuracoes_web()


@app.put("/api/configuracoes")
def salvar_configuracoes(payload: WebConfigPayload) -> dict[str, Any]:
    try:
        return _web_config_service().salvar_configuracoes_web(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/rocketchat/notificacoes")
def notificacoes_rocket_chat() -> dict[str, Any]:
    cfg = _web_config_service().carregar_configuracoes_web()
    base_url = str(cfg.get("rocketChatUrl") or "").strip().rstrip("/")
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    user_id = str(cfg.get("rocketChatUserId") or "").strip()
    auth_token = str(cfg.get("rocketChatAuthToken") or "").strip()
    contar = str(cfg.get("rocketChatContar") or "tudo").strip().lower()

    if not base_url or not user_id or not auth_token:
        return {
            "configured": False,
            "unread": 0,
            "mentions": 0,
            "count": 0,
            "rooms":[],
            "message": "Rocket.Chat não configurado.",
        }

    try:
        url = f"{base_url}/api/v1/subscriptions.get"
        response = requests.get(
            url,
            headers={
                "X-User-Id": user_id,
                "X-Auth-Token": auth_token,
            },
            timeout=4,
        )
        if response.status_code in {401, 403}:
            raise HTTPException(status_code=401, detail="Token do Rocket.Chat inválido ou expirado.")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Endpoint do Rocket.Chat não encontrado: {url}")
        response.raise_for_status()
        payload = response.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar Rocket.Chat: {exc}") from exc

    subscriptions = payload.get("update") or payload.get("subscriptions") or []
    if not isinstance(subscriptions, list):
        subscriptions =[]

    rooms: list[dict[str, Any]] =[]
    total_unread = 0
    total_mentions = 0

    def _as_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    for item in subscriptions:
        if not isinstance(item, dict):
            continue
        unread = _as_int(item.get("unread"))
        mentions = _as_int(item.get("userMentions"))
        if unread <= 0 and mentions <= 0:
            continue
        total_unread += max(unread, 0)
        total_mentions += max(mentions, 0)
        rooms.append(
            {
                "id": item.get("rid") or item.get("_id") or "",
                "name": item.get("name") or item.get("fname") or "",
                "type": item.get("t") or "",
                "unread": unread,
                "mentions": mentions,
            }
        )

    count = total_mentions if contar == "mencoes" else total_unread
    return {
        "configured": True,
        "unread": total_unread,
        "mentions": total_mentions,
        "count": count,
        "rooms": rooms[:20],
    }


# Módulos de entrada da automação (nomes "dotted" reais, como estão em
# sys.modules). São reimportados explicitamente para que erros de sintaxe
# apareçam na resposta do botão.
_MODULOS_AUTOMACAO =[
    "comprasnet.base",
    "comprasnet.apropriar",
    "comprasnet.principal_helpers",
    "comprasnet.dados_basicos",
    "comprasnet.dados_pagamento",
    "comprasnet.principal_orcamento",
    "comprasnet.deducao",
    "comprasnet.centro_custo",
    "comprasnet.finalizar",
    "core.datas_impostos",
    "core.extrator",
]

# Prefixos cujos submódulos são todos purgados do cache antes de reimportar.
# Cobre comprasnet.situacoes.*, comprasnet.deducao_*, core.*, etc., para que
# os 'from x import y' nos handlers passem a enxergar o código novo.
_PREFIXOS_RECARREGAVEIS = ("comprasnet.", "core.")


@app.post("/api/recarregar")
def recarregar_modulos() -> dict[str, Any]:
    recarregados: list[str] = []
    erros: dict[str, str] = {}

    # 1) Purga TODO submódulo recarregável do cache de importação.
    for nome in list(sys.modules):
        if nome.startswith(_PREFIXOS_RECARREGAVEIS):
            sys.modules.pop(nome, None)

    # 2) Reimporta os módulos de entrada (e, por consequência, suas dependências).
    for nome in _MODULOS_AUTOMACAO:
        try:
            importlib.import_module(nome)
            recarregados.append(nome)
        except Exception as exc:
            erros[nome] = str(exc)

    # Importante: este endpoint NÃO recarrega o próprio api.py (o servidor em
    # execução). Mudanças no api.py exigem reiniciar o backend — o que o modo
    # de recarga automática (AUTO_LIQUID_RELOAD=1) faz sozinho ao salvar.
    nota_api = " Mudanças no api.py exigem reiniciar o backend."
    return {
        "recarregados": recarregados,
        "erros": erros,
        "mensagem": (
            f"{len(recarregados)} módulo(s) de automação recarregado(s) com sucesso." + nota_api
            if not erros
            else f"{len(recarregados)} recarregado(s), {len(erros)} com erro." + nota_api
        ),
    }


@app.get("/api/tabelas/{table_key}")
def obter_tabela_web(table_key: str, search: str = Query(default="")) -> dict[str, Any]:
    if table_key not in _web_config_service().TABLE_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Tabela não encontrada.")
    return _web_config_service().carregar_tabela_web(table_key, search)


@app.put("/api/tabelas/{table_key}")
def atualizar_tabela_web(table_key: str, payload: TableSaveRequest) -> dict[str, Any]:
    if table_key not in _web_config_service().TABLE_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Tabela não encontrada.")
    return _web_config_service().salvar_tabela_web(table_key, payload.rows)


@app.post("/api/contratos/lookup-ic")
def lookup_ic_por_sarf(body: dict[str, Any]) -> dict[str, Any]:
    sarfs: list[str] =[str(s).strip() for s in (body.get("sarfs") or []) if str(s).strip()]
    if not sarfs:
        return {"resultado": {}}

    indice = _web_config_service().carregar_contratos_ic_de_para()

    resultado: dict[str, str | None] = {}
    for sarf in sarfs:
        ig = indice.get(_normalizar_sarf_fila(sarf))
        resultado[sarf] = ig if ig else None

    return {"resultado": resultado}


# ─────────────────────────────────────────────────────────────────────────────
# AUSÊNCIAS / SERVIDORES CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/ausencias")
def listar_ausencias() -> dict[str, Any]:
    errors: list[str] =[]
    if _fonte_dados_habilitada("ausencias", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                return {"ausencias": turso.listar_ausencias(), "source": "turso"}
        except Exception as e:
            errors.append(f"Turso: {e}")
    if _fonte_dados_habilitada("ausencias", "supabase"):
        try:
            rows = _postgres_service().listar_ausencias()
            return {"ausencias": rows, "source": "supabase"}
        except Exception as e:
            errors.append(f"Supabase: {e}")
    raise HTTPException(status_code=500, detail="; ".join(errors) or "Nenhuma fonte de ausências habilitada.")


@app.post("/api/ausencias")
def criar_ausencia(body: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "servidor", "tipo", "inicio", "fim"}
    missing = required - set(body.keys())
    if missing:
        raise HTTPException(status_code=422, detail=f"Campos obrigatórios: {missing}")
    try:
        result = None
        if _fonte_dados_habilitada("ausencias", "turso"):
            turso = _turso_service()
            if turso.turso_configurado():
                result = turso.criar_ausencia(body)
        if _fonte_dados_habilitada("ausencias", "supabase"):
            result = _postgres_service().criar_ausencia(body)
        if result is None:
            raise RuntimeError("Nenhuma fonte de ausências habilitada.")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/ausencias/{ausencia_id}")
def deletar_ausencia(ausencia_id: str) -> dict[str, Any]:
    try:
        ok = False
        if _fonte_dados_habilitada("ausencias", "turso"):
            turso = _turso_service()
            if turso.turso_configurado():
                ok = turso.deletar_ausencia(ausencia_id) or ok
        if _fonte_dados_habilitada("ausencias", "supabase"):
            ok = _postgres_service().deletar_ausencia(ausencia_id) or ok
        if not ok:
            raise HTTPException(status_code=404, detail="Ausência não encontrada.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/servidores-config")
def listar_servidores_config() -> dict[str, Any]:
    errors: list[str] =[]
    if _fonte_dados_habilitada("servidores_config", "turso"):
        try:
            turso = _turso_service()
            if turso.turso_configurado():
                return {"servidores": turso.listar_servidores_config(), "source": "turso"}
        except Exception as e:
            errors.append(f"Turso: {e}")
    if _fonte_dados_habilitada("servidores_config", "supabase"):
        try:
            rows = _postgres_service().listar_servidores_config()
            return {"servidores": rows, "source": "supabase"}
        except Exception as e:
            errors.append(f"Supabase: {e}")
    raise HTTPException(status_code=500, detail="; ".join(errors) or "Nenhuma fonte de servidores habilitada.")


@app.put("/api/servidores-config/{nome}")
def upsert_servidor_config(nome: str, body: dict[str, Any]) -> dict[str, Any]:
    cor = str(body.get("cor") or "#6366f1").strip()
    try:
        if _fonte_dados_habilitada("servidores_config", "turso"):
            turso = _turso_service()
            if turso.turso_configurado():
                turso.salvar_servidor_config(nome, cor)
        if _fonte_dados_habilitada("servidores_config", "supabase"):
            _postgres_service().salvar_servidor_config(nome, cor)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/servidores-config/{nome}")
def deletar_servidor_config(nome: str) -> dict[str, Any]:
    try:
        if _fonte_dados_habilitada("servidores_config", "turso"):
            turso = _turso_service()
            if turso.turso_configurado():
                turso.deletar_servidor_config(nome)
        if _fonte_dados_habilitada("servidores_config", "supabase"):
            _postgres_service().deletar_servidor_config(nome)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# VERSÃO / ATUALIZAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

_GITHUB_REPO_PADRAO = "diegodr-sudo/AutoLiquid"


def _normalizar_github_repo(valor: str) -> str:
    texto = str(valor or "").strip()
    texto = texto.removesuffix(".git")
    if "github.com/" in texto:
        texto = texto.split("github.com/", 1)[1]
    texto = texto.strip("/")
    partes = [parte for parte in texto.split("/") if parte]
    if len(partes) >= 2:
        return f"{partes[0]}/{partes[1]}"
    return ""


def _obter_github_repo() -> str:
    repo = _normalizar_github_repo(os.getenv("AUTO_LIQUID_GITHUB_REPO", ""))
    if repo:
        return repo
    try:
        from services.config_service import carregar_config_app

        repo = _normalizar_github_repo(str(carregar_config_app().get("github_repo") or ""))
        if repo:
            return repo
    except Exception:
        pass
    return _GITHUB_REPO_PADRAO


_GITHUB_REPO  = _obter_github_repo()
_GITHUB_API   = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
_RELEASES_URL = f"https://github.com/{_GITHUB_REPO}/releases/latest"


def _comparar_versao(a: str, b: str) -> int:
    def _partes(v: str):
        partes = []
        for parte in v.lstrip("v").split("+", 1)[0].split("-", 1)[0].split("."):
            if parte.isdigit():
                partes.append(int(parte))
        while len(partes) < 3:
            partes.append(0)
        return tuple(partes[:3])
    pa, pb = _partes(a), _partes(b)
    return (pa > pb) - (pa < pb)


@app.get("/versao")
def obter_versao() -> dict[str, Any]:
    return {"versao": APP_VERSION}


@app.get("/versao/verificar")
def verificar_atualizacao() -> dict[str, Any]:
    try:
        r = requests.get(_GITHUB_API, timeout=6,
                         headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        data = r.json()
        versao_nova = data.get("tag_name", "").lstrip("v")
        url_download = data.get("html_url", _RELEASES_URL)
        tem_atualizacao = bool(versao_nova) and _comparar_versao(versao_nova, APP_VERSION) > 0
        return {
            "versao_atual": APP_VERSION,
            "versao_nova": versao_nova,
            "url_download": url_download,
            "tem_atualizacao": tem_atualizacao,
        }
    except Exception as exc:
        return {
            "versao_atual": APP_VERSION,
            "versao_nova": "",
            "url_download": _RELEASES_URL,
            "tem_atualizacao": False,
            "erro": str(exc),
        }


@app.post("/api/debug/detectar-paginacao")
def debug_detectar_paginacao() -> dict[str, Any]:
    playwright_obj, pagina = _comprasnet_base().conectar()
    try:
        resultado = pagina.evaluate("""
            () => {
                var relatorio = {
                    url: window.location.href,
                    titulo: document.title,
                    selects: [],
                    botoes_todos:[],
                    datatables_length: null,
                    tabela_existe: false,
                    linhas_tabela: 0
                };

                var selects = document.querySelectorAll('select');
                for (var i = 0; i < selects.length; i++) {
                    var sel = selects[i];
                    var rect = sel.getBoundingClientRect();
                    var opts =[];
                    for (var j = 0; j < sel.options.length; j++) {
                        opts.push({ value: sel.options[j].value, text: sel.options[j].text.trim() });
                    }
                    relatorio.selects.push({
                        index: i,
                        name: sel.name || null,
                        id: sel.id || null,
                        className: sel.className || null,
                        value_atual: sel.value,
                        visivel: rect.width > 0 && rect.height > 0,
                        options: opts,
                        parent_classes: sel.parentElement ? sel.parentElement.className : null
                    });
                }

                var todos_els = Array.from(document.querySelectorAll('button, a, li, span, option'));
                for (var k = 0; k < todos_els.length; k++) {
                    var el = todos_els[k];
                    var txt = (el.textContent || '').trim();
                    if (txt.toLowerCase() === 'todos' || txt.toLowerCase() === 'all') {
                        var r = el.getBoundingClientRect();
                        relatorio.botoes_todos.push({
                            tag: el.tagName,
                            text: txt,
                            className: el.className || null,
                            id: el.id || null,
                            visivel: r.width > 0 && r.height > 0,
                            value: el.value || null
                        });
                    }
                }

                var dtLen = document.querySelector('.dataTables_length');
                if (dtLen) {
                    relatorio.datatables_length = {
                        html: dtLen.innerHTML.substring(0, 500),
                        className: dtLen.className
                    };
                }

                var linhas = document.querySelectorAll('table tbody tr');
                relatorio.tabela_existe = linhas.length > 0;
                relatorio.linhas_tabela = linhas.length;

                return relatorio;
            }
        """)

        return {"ok": True, "relatorio": resultado}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            playwright_obj.stop()
        except Exception:
            pass


@app.post("/api/abrir-url")
def abrir_url(body: dict[str, Any]) -> dict[str, Any]:
    import webbrowser
    url = str(body.get("url", "")).strip()
    if url:
        webbrowser.open(url)
    return {"ok": True}


@app.post("/api/turso/testar")
def testar_turso() -> dict[str, Any]:
    turso = _turso_service()
    if not turso.turso_configurado():
        return {"configured": False, "ok": False, "mensagem": "Turso ainda não está configurado."}
    try:
        return turso.testar_conexao()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/turso/migrar")
def migrar_turso() -> dict[str, Any]:
    turso = _turso_service()
    if not turso.turso_configurado():
        raise HTTPException(status_code=400, detail="Turso não configurado.")

    resultado: dict[str, Any] = {
        "ok": True,
        "fila": 0,
        "servidores": 0,
        "ausencias": 0,
        "historico": {},
        "tabelas": [],
        "avisos":[],
    }
    try:
        turso.garantir_schema_cache(timeout=20)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Não foi possível preparar o schema do Turso: {exc}") from exc

    try:
        snapshot = _postgres_service().obter_fila_processos_snapshot_atual()
        rows = snapshot.get("rows") or[]
        if rows:
            turso.salvar_snapshot_fila(rows, snapshot.get("updatedAt"))
            resultado["fila"] = len(rows)
    except Exception as exc:
        resultado["avisos"].append(f"Fila não migrada: {exc}")

    try:
        servidores = _postgres_service().listar_servidores_config()
        for servidor in servidores:
            turso.salvar_servidor_config(
                str(servidor.get("nomeCompleto") or servidor.get("nome") or ""),
                str(servidor.get("cor") or "#6366f1"),
            )
        resultado["servidores"] = len(servidores)
    except Exception as exc:
        resultado["avisos"].append(f"Servidores não migrados: {exc}")

    try:
        sorteio = _postgres_service().obter_servidores_sorteio() or[]
        turso.salvar_tabela_operacional("fila_servidores_sorteio", sorteio)
    except Exception as exc:
        resultado["avisos"].append(f"Sorteio não migrado: {exc}")

    try:
        ausencias = _postgres_service().listar_ausencias()
        for ausencia in ausencias:
            turso.criar_ausencia(ausencia)
        resultado["ausencias"] = len(ausencias)
    except Exception as exc:
        resultado["avisos"].append(f"Ausências não migradas: {exc}")

    try:
        datas = _postgres_service().obter_datas_globais()
        turso.salvar_datas_globais(datas)
        resultado["datasGlobais"] = bool(datas.get("apuracao") or datas.get("vencimento"))
    except Exception as exc:
        resultado["avisos"].append(f"Datas globais não migradas: {exc}")

    try:
        resultado["historico"] = turso.importar_historico_postgres(_postgres_service())
    except Exception as exc:
        resultado["avisos"].append(f"Histórico não migrado: {exc}")

    for table_key in ("contratos", "vpd", "vpd-especiais", "uorg", "nat-rendimento", "datas-impostos", "ncm"):
        try:
            rows = _postgres_service().obter_tabela_operacional(table_key)
            if rows is None:
                table = _web_config_service().carregar_tabela_web(table_key)
                rows = table.get("rows") or[]
            turso.salvar_tabela_operacional(table_key, rows)
            if table_key == "contratos":
                turso.salvar_contratos_ic_de_para(rows)
            resultado["tabelas"].append({"chave": table_key, "linhas": len(rows)})
        except Exception as exc:
            resultado["avisos"].append(f"Tabela {table_key} não migrada: {exc}")

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# CNPJ / SIMPLES NACIONAL
# ─────────────────────────────────────────────────────────────────────────────

def _formatar_cnpj(cnpj_limpo: str) -> str:
    return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"


def _texto_pdf_escape(texto: str) -> str:
    return str(texto).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _quebrar_linha_pdf(texto: str, limite: int = 84) -> list[str]:
    palavras = str(texto or "").split()
    if not palavras:
        return [""]
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        candidato = f"{atual} {palavra}".strip()
        if len(candidato) <= limite:
            atual = candidato
            continue
        if atual:
            linhas.append(atual)
        atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _gerar_pdf_texto(linhas: list[str]) -> bytes:
    y = 790
    comandos = ["BT", "/F1 12 Tf", "50 790 Td", "14 TL"]
    for i, linha in enumerate(linhas):
        if i:
            comandos.append("T*")
        if y < 48:
            comandos.append(f"({_texto_pdf_escape('Conteudo continua em consulta posterior.')}) Tj")
            break
        comandos.append(f"({_texto_pdf_escape(linha)}) Tj")
        y -= 14
    comandos.append("ET")
    stream = "\n".join(comandos).encode("latin-1", errors="replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    saida = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida.extend(f"{i} 0 obj\n".encode("ascii"))
        saida.extend(obj)
        saida.extend(b"\nendobj\n")
    xref_pos = len(saida)
    saida.extend(f"xref\n0 {len(objetos) + 1}\n".encode("ascii"))
    saida.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        saida.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    saida.extend(
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(saida)


def _salvar_pdf_simples_local(destino: Path, cnpj_limpo: str, dados: dict[str, Any]) -> None:
    optante = dados.get("optante_simples")
    if optante is True:
        situacao = "Optante pelo Simples Nacional"
    elif optante is False:
        situacao = "Nao optante pelo Simples Nacional"
    else:
        situacao = "Situacao do Simples Nacional indisponivel na fonte consultada"

    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    razao = str(dados.get("razao_social") or "Nao informada").strip()
    linhas = [
        "AutoLiquid - Consulta Simples Nacional",
        "",
        f"CNPJ: {_formatar_cnpj(cnpj_limpo)}",
        f"Razao social: {razao}",
        f"Situacao: {situacao}",
        f"Gerado em: {agora}",
        "",
        "Fonte dos dados: BrasilAPI / cadastro publico de CNPJ.",
        "Observacao: este arquivo e um comprovante operacional gerado localmente pelo AutoLiquid.",
        "Para certidao oficial da Receita Federal, use o portal oficial quando necessario.",
    ]
    linhas_quebradas: list[str] = []
    for linha in linhas:
        linhas_quebradas.extend(_quebrar_linha_pdf(linha))
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(_gerar_pdf_texto(linhas_quebradas))


def _nome_pdf_simples(cnpj_limpo: str, dados: dict[str, Any]) -> str:
    optante = dados.get("optante_simples")
    if optante is True:
        prefixo = "Optante Simples"
    elif optante is False:
        prefixo = "Não Optante Simples"
    else:
        prefixo = "Consulta Simples"
    return f"{prefixo} {cnpj_limpo}.pdf"


def _optante_simples_por_texto_receita(texto: str) -> bool | None:
    texto_norm = _normalizar_texto_status(texto)
    if re.search(r"\bnao\s+optante\b", texto_norm):
        return False
    if re.search(r"\boptante\b", texto_norm) and "simples nacional" in texto_norm:
        return True
    return None


def _nome_pdf_simples_receita(cnpj_limpo: str, texto_receita: str = "") -> str:
    optante = _optante_simples_por_texto_receita(texto_receita)
    if optante is True:
        prefixo = "Optante Simples"
    elif optante is False:
        prefixo = "Não Optante Simples"
    else:
        prefixo = "Consulta Simples"
    return f"{prefixo} {cnpj_limpo}.pdf"


def _pagina_receita_resultado_simples(
    pagina: Any,
    cnpj_limpo: str,
    *,
    permitir_sem_cnpj: bool = False,
) -> tuple[bool, str]:
    try:
        texto = pagina.locator("body").inner_text(timeout=3000)
    except Exception:
        return False, ""

    digitos_pagina = "".join(ch for ch in texto if ch.isdigit())
    texto_norm = _normalizar_texto_status(texto)
    tem_cnpj = cnpj_limpo in digitos_pagina
    tem_resultado = (
        "simples nacional" in texto_norm
        and ("optante" in texto_norm or "consulta optantes" in texto_norm)
    )
    return bool((tem_cnpj or permitir_sem_cnpj) and tem_resultado), texto


def _localizar_pagina_receita(contexto: Any, cnpj_limpo: str = "") -> Any | None:
    paginas_receita = [
        pagina
        for pagina in contexto.pages
        if "consopt.www8.receita.fazenda.gov.br/consultaoptantes" in (pagina.url or "")
    ]
    for pagina in reversed(paginas_receita):
        resultado_ok, _texto = _pagina_receita_resultado_simples(
            pagina,
            cnpj_limpo,
            permitir_sem_cnpj=not bool(cnpj_limpo),
        )
        if resultado_ok:
            return pagina
    for pagina in contexto.pages:
        if "consopt.www8.receita.fazenda.gov.br/consultaoptantes" in (pagina.url or ""):
            return pagina
    return None


def _eh_pagina_receita_simples(pagina: Any) -> bool:
    try:
        url = pagina.url or ""
    except Exception:
        return False
    return "consopt.www8.receita.fazenda.gov.br/consultaoptantes" in url


def _fechar_pagina_receita_simples(pagina: Any | None) -> bool:
    if pagina is None:
        return False
    try:
        if not _eh_pagina_receita_simples(pagina):
            return False
        if getattr(pagina, "is_closed", lambda: False)():
            return False
        pagina.close(run_before_unload=False)
        return True
    except Exception:
        return False


def _configurar_download_receita(pagina: Any, destino: Path) -> None:
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        sessao = pagina.context.new_cdp_session(pagina)
        sessao.send("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(destino.parent)})
    except Exception:
        pass


def _snapshot_pdfs(diretorio: Path) -> dict[str, tuple[int, int]]:
    try:
        return {
            str(path): (path.stat().st_mtime_ns, path.stat().st_size)
            for path in diretorio.glob("*.pdf")
            if path.is_file()
        }
    except Exception:
        return {}


def _arquivo_estavel(path: Path) -> bool:
    try:
        tamanho = path.stat().st_size
        if tamanho <= 0:
            return False
        time.sleep(0.25)
        return path.exists() and path.stat().st_size == tamanho
    except Exception:
        return False


def _mover_pdf_baixado(origem: Path, destino: Path) -> bool:
    try:
        if origem.resolve() == destino.resolve():
            return True
    except Exception:
        pass

    for _ in range(20):
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            if destino.exists():
                destino.unlink()
            shutil.move(str(origem), str(destino))
            return True
        except Exception:
            time.sleep(0.25)
    return False


def _aguardar_pdf_baixado(diretorio: Path, snapshot: dict[str, tuple[int, int]], destino: Path, timeout_s: float = 12) -> Path | None:
    limite = time.time() + max(timeout_s, 1)
    while time.time() < limite:
        try:
            if destino.exists() and _arquivo_estavel(destino):
                return destino

            baixando = list(diretorio.glob("*.crdownload")) + list(diretorio.glob("*.tmp"))
            candidatos: list[Path] = []
            for path in diretorio.glob("*.pdf"):
                if not path.is_file():
                    continue
                stat = path.stat()
                estado_anterior = snapshot.get(str(path))
                if estado_anterior == (stat.st_mtime_ns, stat.st_size):
                    continue
                candidatos.append(path)

            candidatos.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for candidato in candidatos:
                if _arquivo_estavel(candidato) and _mover_pdf_baixado(candidato, destino):
                    return destino

            if not baixando:
                time.sleep(0.35)
            else:
                time.sleep(0.6)
        except Exception:
            time.sleep(0.35)
    return None


def _baixar_pdf_url_receita(pagina: Any, url: str, destino: Path) -> bool:
    if not url.lower().startswith(("http://", "https://")):
        return False

    try:
        cookies = {cookie["name"]: cookie["value"] for cookie in pagina.context.cookies(url)}
    except Exception:
        cookies = {}
    try:
        user_agent = pagina.evaluate("navigator.userAgent")
    except Exception:
        user_agent = "Mozilla/5.0"

    try:
        resposta = requests.get(url, cookies=cookies, headers={"User-Agent": user_agent}, timeout=30)
        conteudo = resposta.content or b""
        tipo = resposta.headers.get("content-type", "").lower()
        if resposta.ok and (conteudo.startswith(b"%PDF") or "application/pdf" in tipo):
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
            return True
    except Exception:
        return False
    return False


def _salvar_pdf_de_pagina_receita(pagina: Any, destino: Path) -> str | None:
    try:
        pagina.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass

    try:
        url = pagina.url or ""
    except Exception:
        url = ""

    if _baixar_pdf_url_receita(pagina, url, destino):
        return "download"

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        pagina.pdf(path=str(destino), format="A4", print_background=True)
        return "print"
    except Exception:
        return None


def _baixar_pdf_oficial_receita(pagina: Any, destino: Path) -> str:
    botoes = [
        pagina.get_by_role("button", name=re.compile(r"gerar\s*pdf|imprimir|pdf", re.I)),
        pagina.locator("button, a, input[type='button'], input[type='submit']").filter(
            has_text=re.compile(r"gerar\s*pdf|imprimir|pdf", re.I)
        ),
        pagina.locator(
            "input[type='button'][value*='PDF' i], input[type='submit'][value*='PDF' i], "
            "button[onclick*='pdf' i], a[onclick*='pdf' i]"
        ),
    ]
    ultimo_erro: Exception | None = None
    for botao in botoes:
        try:
            if botao.count() <= 0:
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            # NÃO chamar _configurar_download_receita antes do expect_download:
            # setDownloadBehavior:allow faz o browser salvar com o nome original
            # (ConsultaOptantes.pdf) enquanto save_as() cria um segundo arquivo
            # com o nome correto mas 0 bytes (stream já consumido).
            # O expect_download intercepta o download antes de tocar o disco.
            snapshot = _snapshot_pdfs(destino.parent)
            paginas_antes = set(pagina.context.pages)
            elemento = botao.first
            try:
                elemento.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

            try:
                with pagina.expect_download(timeout=8000) as download_info:
                    elemento.click(timeout=5000)
                download = download_info.value
                destino.parent.mkdir(parents=True, exist_ok=True)
                download.save_as(str(destino))
                # Garante que o arquivo foi salvo com conteúdo
                if destino.exists() and destino.stat().st_size > 0:
                    return "download"
            except Exception as exc:
                ultimo_erro = exc

            # Fallback: usa CDP para monitorar downloads que já caíram no disco
            _configurar_download_receita(pagina, destino)
            baixado = _aguardar_pdf_baixado(destino.parent, snapshot, destino, timeout_s=10)
            if baixado is not None:
                return "download"

            paginas_novas = [p for p in pagina.context.pages if p not in paginas_antes]
            for pagina_pdf in reversed(paginas_novas):
                origem = _salvar_pdf_de_pagina_receita(pagina_pdf, destino)
                if origem:
                    try:
                        if not getattr(pagina_pdf, "is_closed", lambda: False)():
                            pagina_pdf.close(run_before_unload=False)
                    except Exception:
                        pass
                    return origem
        except Exception as exc:
            ultimo_erro = exc

    origem = _salvar_pdf_de_pagina_receita(pagina, destino)
    if origem:
        return origem

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        pagina.pdf(path=str(destino), format="A4", print_background=True)
        return "print"
    except Exception as exc:
        ultimo_erro = exc

    raise RuntimeError(f"Não foi possível baixar o PDF oficial da Receita: {ultimo_erro}")


def _consultar_simples_receita_no_navegador(pagina: Any, cnpj_limpo: str) -> tuple[bool, str]:
    campo_cnpj = pagina.locator("#Cnpj")
    if campo_cnpj.count() <= 0:
        return False, ""

    campo_cnpj.first.fill(cnpj_limpo, timeout=5000)
    try:
        with pagina.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            pagina.locator("button, input[type='submit']").filter(
                has_text=re.compile(r"consultar", re.I)
            ).first.click(timeout=5000)
    except Exception:
        try:
            pagina.locator("button.h-captcha, button[type='submit'], button").filter(
                has_text=re.compile(r"consultar", re.I)
            ).first.click(timeout=5000)
        except Exception:
            try:
                pagina.evaluate("document.getElementById('consultarForm')?.submit()")
            except Exception:
                pass

    try:
        pagina.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        pagina.wait_for_timeout(1500)
    except Exception:
        pass
    return _pagina_receita_resultado_simples(pagina, cnpj_limpo)


@app.post("/api/simples/consultar")
def consultar_simples(body: dict[str, Any]) -> dict[str, Any]:
    import core.consulta_cnpj as _cnpj_mod

    cnpj_raw = str(body.get("cnpj", ""))
    cnpj_limpo = "".join(c for c in cnpj_raw if c.isdigit())
    if len(cnpj_limpo) != 14:
        raise HTTPException(status_code=422, detail="CNPJ deve ter 14 dígitos.")

    cached = _cnpj_mod._cache_get(cnpj_limpo)
    if cached is not None:
        print(f"  /simples: cache hit para {cnpj_limpo}")
        return {
            "cnpj": cnpj_limpo,
            "razaoSocial": cached.get("razao_social") or "",
            "optanteSimples": cached.get("optante_simples"),
            "fonte": "cache",
        }

    dados = _cnpj_mod.obter_dados_empresa(cnpj_limpo)

    if dados.get("nao_encontrado"):
        raise HTTPException(status_code=404, detail="CNPJ não encontrado na base da Receita Federal.")

    return {
        "cnpj": cnpj_limpo,
        "razaoSocial": dados.get("razao_social") or "",
        "optanteSimples": dados.get("optante_simples"),
        "fonte": "api",
    }


@app.post("/api/simples/gerar-pdf")
def gerar_pdf_simples(body: dict[str, Any]) -> dict[str, Any]:
    cnpj_raw = str(body.get("cnpj", ""))
    cnpj_limpo = "".join(c for c in cnpj_raw if c.isdigit())
    if len(cnpj_limpo) != 14:
        raise HTTPException(status_code=422, detail="CNPJ deve ter 14 dígitos.")
    download_only = bool(body.get("downloadOnly"))

    url_consulta = "https://consopt.www8.receita.fazenda.gov.br/consultaoptantes"
    playwright = None
    try:
        chrome_service = _chrome_service()
        porta = obter_porta_chrome()
        if not chrome_service.chrome_esta_pronto(porta):
            chrome_service.abrir_chrome(porta, aguardar=True, timeout_s=20)

        playwright, pagina_base = chrome_service.conectar_chrome_cdp(porta, abrir_se_fechado=True)
        contexto = pagina_base.context
        pagina = _localizar_pagina_receita(contexto, cnpj_limpo)
        if pagina is None:
            if download_only:
                return {
                    "success": True,
                    "status": "preenchido",
                    "mensagem": "A página de resultado da Receita ainda não foi encontrada para baixar o PDF.",
                }
            pagina = contexto.new_page()
            pagina.goto(url_consulta, wait_until="domcontentloaded", timeout=30000)

        resultado_ok, texto_receita = _pagina_receita_resultado_simples(
            pagina,
            cnpj_limpo,
            permitir_sem_cnpj=download_only,
        )
        if resultado_ok:
            downloads_dir = Path.home() / "Downloads"
            if not downloads_dir.exists():
                downloads_dir = Path(tempfile.gettempdir())
            destino = downloads_dir / _nome_pdf_simples_receita(cnpj_limpo, texto_receita)
            origem = _baixar_pdf_oficial_receita(pagina, destino)
            aba_fechada = _fechar_pagina_receita_simples(pagina)
            mensagem = f"PDF oficial da Receita salvo em {destino}."
            if origem == "print":
                mensagem = f"PDF salvo a partir da página oficial da Receita em {destino}."
            return {
                "success": True,
                "status": "gerado",
                "arquivo": str(destino),
                "mensagem": mensagem,
                "abaFechada": aba_fechada,
            }

        if download_only:
            return {
                "success": True,
                "status": "preenchido",
                "mensagem": "A página da Receita ainda não exibiu o resultado. Conclua a consulta no site e clique em Gerar PDF novamente.",
            }

        if "consopt.www8.receita.fazenda.gov.br/consultaoptantes" not in (pagina.url or ""):
            pagina.goto(url_consulta, wait_until="domcontentloaded", timeout=30000)

        campo_cnpj = pagina.locator("#Cnpj")
        if campo_cnpj.count() <= 0:
            pagina.goto(url_consulta, wait_until="domcontentloaded", timeout=30000)
            campo_cnpj = pagina.locator("#Cnpj")
        if campo_cnpj.count() <= 0:
            raise RuntimeError("Campo de CNPJ da Receita não foi encontrado.")

        resultado_ok, texto_receita = _consultar_simples_receita_no_navegador(pagina, cnpj_limpo)
        if resultado_ok:
            downloads_dir = Path.home() / "Downloads"
            if not downloads_dir.exists():
                downloads_dir = Path(tempfile.gettempdir())
            destino = downloads_dir / _nome_pdf_simples_receita(cnpj_limpo, texto_receita)
            origem = _baixar_pdf_oficial_receita(pagina, destino)
            aba_fechada = _fechar_pagina_receita_simples(pagina)
            mensagem = f"PDF oficial da Receita salvo em {destino}."
            if origem == "print":
                mensagem = f"PDF salvo a partir da página oficial da Receita em {destino}."
            return {
                "success": True,
                "status": "gerado",
                "arquivo": str(destino),
                "mensagem": mensagem,
                "abaFechada": aba_fechada,
            }

        return {
            "success": True,
            "status": "preenchido",
            "mensagem": (
                "Consulta preparada no site da Receita. Se a página já exibiu o resultado, "
                "clique em Gerar PDF novamente no AutoLiquid para baixar e renomear o PDF oficial."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


def _bool_opcional(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    texto = str(value).strip().casefold()
    if texto in {"1", "true", "t", "sim", "s", "yes", "y"}:
        return True
    if texto in {"0", "false", "f", "nao", "não", "n", "no"}:
        return False
    return None


def _salvar_simples_batch_cache_persistido(registros: list[tuple[str, str, bool]]) -> None:
    if not registros:
        return

    def _run() -> None:
        for cnpj, razao_social, optante in registros:
            try:
                _turso_service().salvar_simples_cnpj(cnpj, razao_social, optante)
            except Exception:
                log.debug("simples-batch: falha ao persistir cache do CNPJ %s.", cnpj, exc_info=True)

    Thread(target=_run, name="simples-cache-save", daemon=True).start()


@app.post("/api/cnpj/simples-batch")
def simples_batch(body: dict[str, Any]) -> dict[str, Any]:
    import core.consulta_cnpj as _cnpj_mod
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    cnpjs_raw = body.get("cnpjs",[])
    if not isinstance(cnpjs_raw, list):
        raise HTTPException(status_code=422, detail="'cnpjs' deve ser uma lista de strings.")

    cnpjs_limpos = list(dict.fromkeys(
        c for cnpj in cnpjs_raw
        if len(c := "".join(d for d in str(cnpj) if d.isdigit())) == 14
    ))
    if not cnpjs_limpos:
        return {"resultado": {}}

    resultado: dict[str, bool | None] = {cnpj: None for cnpj in cnpjs_limpos}

    pendentes: list[str] =[]
    for cnpj in cnpjs_limpos:
        if resultado.get(cnpj) is not None:
            continue
        cached = _cnpj_mod._cache_get(cnpj)
        if cached is not None:
            optante = cached.get("optante_simples")
            resultado[cnpj] = _bool_opcional(optante)
        else:
            pendentes.append(cnpj)

    persistir: list[tuple[str, str, bool]] = []
    if pendentes:
        def _consultar_um(cnpj: str) -> tuple[str, bool | None, str]:
            try:
                dados = _cnpj_mod.obter_dados_empresa(cnpj)
                if dados.get("nao_encontrado"):
                    return cnpj, None, ""
                optante = dados.get("optante_simples")
                return cnpj, _bool_opcional(optante), str(dados.get("razao_social") or "").strip()
            except Exception:
                log.debug("simples-batch: falha ao consultar CNPJ %s", cnpj)
                return cnpj, None, ""

        max_workers = min(5, len(pendentes))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_consultar_um, cnpj): cnpj for cnpj in pendentes}
            try:
                for future in _as_completed(futures, timeout=60):
                    try:
                        cnpj, optante, razao_social = future.result(timeout=30)
                        resultado[cnpj] = optante
                        if optante is not None:
                            persistir.append((cnpj, razao_social, optante))
                    except Exception:
                        resultado[futures[future]] = None
            except TimeoutError:
                # Retorna resultado parcial: CNPJs restantes ficam como None
                for future, cnpj in futures.items():
                    if cnpj not in resultado:
                        resultado[cnpj] = None

    _salvar_simples_batch_cache_persistido(persistir)
    return {"resultado": resultado}


# ─────────────────────────────────────────────────────────────────────────────
# SIAFI ATULC — endpoints de execução e streaming
# ─────────────────────────────────────────────────────────────────────────────

# Fila de eventos por execução: execution_id → Queue[str | None]
# None sinaliza fim de stream.
_SIAFI_ATULC_SESSIONS: dict[str, "Queue[str | None]"] = {}
_SIAFI_ATULC_SESSIONS_LOCK = Lock()


def _siafi_broadcast(execution_id: str, payload: dict) -> None:
    """Envia um evento JSON para a fila do execution_id."""
    import json as _json
    with _SIAFI_ATULC_SESSIONS_LOCK:
        q = _SIAFI_ATULC_SESSIONS.get(execution_id)
    if q:
        q.put(_json.dumps(payload, ensure_ascii=False))


def _siafi_close(execution_id: str) -> None:
    """Sinaliza fim de stream (None) e remove a fila."""
    with _SIAFI_ATULC_SESSIONS_LOCK:
        q = _SIAFI_ATULC_SESSIONS.pop(execution_id, None)
    if q:
        q.put(None)


@app.post("/api/siafi/atulc/executar")
def siafi_atulc_executar(body: dict[str, Any]) -> dict[str, Any]:
    """
    Dispara a execução do ATULC em background e retorna um execution_id
    para acompanhar o progresso via SSE em /api/siafi/atulc/stream/{execution_id}.

    Body esperado:
      {
        "credores": [{"cpf": "...", "banco": "...", "agencia": "...", "conta": "...", "valor": "..."}],
        "codigo_acesso": "20222425322",   <- código gerado pelo SIAFI Web (HOD)
        "numero_lista": "2026LC001",
        "ug_emitente": "153163",
        "gestao_emitente": "15237",
        "suprimento_fundos": "N",
        "tipo_pagamento": "1",
        "cpf_usuario": null,
        "senha": null
      }
    """
    from scripts.siafi_atulc import executar_atulc

    execution_id = str(uuid4())
    q: Queue[str | None] = Queue()
    with _SIAFI_ATULC_SESSIONS_LOCK:
        _SIAFI_ATULC_SESSIONS[execution_id] = q

    def _callback(acao: str, tela: list, estado: str) -> None:
        _siafi_broadcast(execution_id, {
            "type": "update",
            "acao": acao,
            "tela": tela,
            "estado": estado,
        })

    def _run() -> None:
        try:
            resultado = executar_atulc(
                credores=body.get("credores", []),
                codigo_acesso=body.get("codigo_acesso", ""),
                ug_emitente=body.get("ug_emitente", "153163"),
                gestao_emitente=body.get("gestao_emitente", "15237"),
                numero_lista=body.get("numero_lista", ""),
                sequencial=body.get("sequencial", ""),
                suprimento_fundos=body.get("suprimento_fundos", "N"),
                tipo_pagamento=body.get("tipo_pagamento", "1"),
                cpf_usuario=body.get("cpf_usuario"),
                senha=body.get("senha"),
                on_update=_callback,
            )
            _siafi_broadcast(execution_id, {"type": "resultado", **resultado})
        except Exception as exc:
            _siafi_broadcast(execution_id, {
                "type": "resultado",
                "ok": False,
                "mensagem": str(exc),
                "estado": "excecao",
                "tela": "",
            })
        finally:
            _siafi_close(execution_id)

    Thread(target=_run, name=f"siafi-atulc-{execution_id[:8]}", daemon=True).start()
    return {"execution_id": execution_id}


@app.get("/api/siafi/atulc/stream/{execution_id}")
async def siafi_atulc_stream(execution_id: str, request: Request):
    """
    SSE stream do progresso de uma execução ATULC.
    Emite eventos do tipo 'update' (progresso) e 'resultado' (finalização).
    """
    with _SIAFI_ATULC_SESSIONS_LOCK:
        q = _SIAFI_ATULC_SESSIONS.get(execution_id)
    if q is None:
        raise HTTPException(status_code=404, detail="execution_id não encontrado")

    async def event_generator():
        ultimo_keepalive = time.monotonic()
        try:
            yield "event: ready\ndata: {\"type\":\"ready\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    mensagem = q.get_nowait()
                    if mensagem is None:
                        yield "event: done\ndata: {\"type\":\"done\"}\n\n"
                        break
                    yield f"event: siafi\ndata: {mensagem}\n\n"
                except Empty:
                    if time.monotonic() - ultimo_keepalive >= 15:
                        ultimo_keepalive = time.monotonic()
                        yield ": keepalive\n\n"
                    await asyncio.sleep(0.3)
        finally:
            _siafi_close(execution_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Bug Reports ───────────────────────────────────────────────────────────────

class BugReportBody(BaseModel):
    pagina: str = ""
    descricao: str
    contexto: dict = {}
    camposDom: dict = {}
    errosConsole: list = []
    versaoApp: str = ""
    servidorNome: str = ""


@app.post("/api/bug-report")
async def criar_bug_report(body: BugReportBody):
    turso = _turso_service()
    if not turso.turso_configurado():
        raise HTTPException(status_code=503, detail="Banco de dados não configurado.")
    bug_id = turso.salvar_bug_report(
        pagina=body.pagina,
        descricao=body.descricao,
        contexto=body.contexto or None,
        campos_dom=body.camposDom or None,
        erros_console=body.errosConsole or None,
        versao_app=body.versaoApp,
        servidor_nome=body.servidorNome,
    )
    return {"ok": True, "id": bug_id}


@app.get("/api/bug-reports")
async def listar_bug_reports(resolvido: str | None = None):
    turso = _turso_service()
    filtro: bool | None = None
    if resolvido == "true":
        filtro = True
    elif resolvido == "false":
        filtro = False
    reports = turso.listar_bug_reports(resolvido=filtro)
    return {"reports": reports}


@app.patch("/api/bug-reports/{bug_id}/resolver")
async def resolver_bug_report(bug_id: int):
    turso = _turso_service()
    if not turso.turso_configurado():
        raise HTTPException(status_code=503, detail="Banco de dados não configurado.")
    turso.resolver_bug_report(bug_id)
    return {"ok": True}


@app.delete("/api/bug-reports/{bug_id}")
async def deletar_bug_report(bug_id: int):
    turso = _turso_service()
    if not turso.turso_configurado():
        raise HTTPException(status_code=503, detail="Banco de dados não configurado.")
    turso.deletar_bug_report(bug_id)
    return {"ok": True}


def _warmup_turso_schema() -> None:
    """
    Inicializa o schema do Turso em background logo que a API sobe.
    Evita que a primeira requisição do usuário (ex: login, datas-globais)
    fique bloqueada pelos ~30-60s de criação das tabelas.
    """
    started_at = time.monotonic()
    try:
        from services import turso_service as _turso
        if _turso.turso_configurado():
            try:
                _turso.garantir_schema_fila_cache(
                    timeout=float(os.getenv("AUTO_LIQUID_TURSO_FILA_WARMUP_TIMEOUT", "5") or "5")
                )
                snapshot = _carregar_snapshot_fila_turso()
                if snapshot:
                    log.info(
                        "Warmup da fila Turso concluido em %.0fms (%d linhas).",
                        (time.monotonic() - started_at) * 1000,
                        int(snapshot.get("total") or 0),
                    )
            except Exception:
                log.debug("Warmup da fila Turso falhou (não crítico).", exc_info=True)

        delay_seconds = float(os.getenv("AUTO_LIQUID_TURSO_WARMUP_DELAY", "3") or "0")
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        if _turso.turso_configurado():
            timeout_seconds = int(os.getenv("AUTO_LIQUID_TURSO_WARMUP_TIMEOUT", "25") or "25")
            _turso.garantir_schema_cache(timeout=timeout_seconds)
            try:
                _turso.garantir_schema_bug_reports(timeout=8)
            except Exception:
                log.debug("Warmup do schema bug_reports falhou (não crítico).", exc_info=True)
            log.info("Warmup do schema Turso concluido em %.0fms.", (time.monotonic() - started_at) * 1000)
    except Exception:
        log.debug("Warmup do schema Turso falhou (não crítico).", exc_info=True)

def _resetar_execucoes_travadas_startup() -> None:
    """Libera, no startup, qualquer execução que ficou presa com is_running=True
    após um encerramento abrupto da API. Sem isso, a flag presa bloqueia toda
    nova execução com HTTP 409 e a fila parece "não fazer nada no Chrome"."""
    try:
        corrigidos = _local_cache_service().resetar_execucoes_travadas()
        if corrigidos:
            log.info(
                "Reset de execuções travadas: %d documento(s) liberado(s) no startup.",
                corrigidos,
            )
    except Exception:
        log.debug("Reset de execuções travadas falhou (não crítico).", exc_info=True)


_resetar_execucoes_travadas_startup()

Thread(target=_warmup_turso_schema, name="turso-warmup", daemon=True).start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
