"""Cache local leve para acelerar a abertura do AutoLiquid.

Este cache usa SQLite da biblioteca padrão como primeira etapa local-first.
Depois podemos trocar o arquivo por libSQL/Turso Sync sem mudar o contrato
consumido pela API.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.app_paths import DIR_DADOS


CAMINHO_CACHE_LOCAL: Path = DIR_DADOS / "autoliquid_cache.sqlite3"


def _connect(timeout_s: float = 5.0) -> sqlite3.Connection:
    conn = sqlite3.connect(CAMINHO_CACHE_LOCAL, timeout=timeout_s)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode = wal")
    conn.execute("pragma synchronous = normal")
    conn.execute(
        """
        create table if not exists cache_snapshots (
            chave text primary key,
            payload text not null,
            atualizado_em text
        )
        """
    )
    conn.execute(
        """
        create table if not exists documentos_processados (
            id text primary key,
            payload text not null,
            atualizado_em text
        )
        """
    )
    conn.execute(
        """
        create table if not exists liquidacao_registros_pendentes (
            documento_id text primary key,
            payload text not null,
            sincronizado integer not null default 0,
            atualizado_em text
        )
        """
    )
    return conn


def salvar_fila_processos_snapshot(rows: list[dict[str, Any]], updated_at: str | None) -> None:
    payload = json.dumps(rows or[], ensure_ascii=False, separators=(",", ":"))
    with _connect(timeout_s=5.0) as conn:
        conn.execute(
            """
            insert into cache_snapshots (chave, payload, atualizado_em)
            values ('fila_processos_atual', ?, ?)
            on conflict(chave) do update set
              payload = excluded.payload,
              atualizado_em = excluded.atualizado_em
            """,
            (payload, updated_at),
        )


def obter_fila_processos_snapshot() -> dict[str, Any]:
    try:
        with _connect(timeout_s=0.8) as conn:
            row = conn.execute(
                """
                select payload, atualizado_em
                from cache_snapshots
                where chave = 'fila_processos_atual'
                """
            ).fetchone()
    except Exception:
        return {"rows":[], "updatedAt": None}

    if not row:
        return {"rows":[], "updatedAt": None}

    try:
        rows = json.loads(str(row["payload"] or "[]"))
    except Exception:
        rows =[]

    if not isinstance(rows, list):
        rows = []

    return {
        "rows":[item for item in rows if isinstance(item, dict)],
        "updatedAt": row["atualizado_em"],
    }


def salvar_documento(doc_id: str, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            """
            insert into documentos_processados (id, payload, atualizado_em)
            values (?, ?, datetime('now'))
            on conflict(id) do update set
              payload = excluded.payload,
              atualizado_em = datetime('now')
            """,
            (doc_id, data)
        )


def obter_documento(doc_id: str) -> dict | None:
    try:
        with _connect() as conn:
            row = conn.execute("select payload from documentos_processados where id = ?", (doc_id,)).fetchone()
            if row:
                return json.loads(row["payload"])
    except Exception:
        pass
    return None


def resetar_execucoes_travadas() -> int:
    """Libera execuções que ficaram presas após um encerramento abrupto da API.

    Um processo recém-iniciado não pode ter nenhuma execução legitimamente em
    andamento. Se um run anterior morreu antes de rodar o bloco `finally` que
    zera `is_running`, a flag permanece `True` no cache e TODA nova execução é
    bloqueada com HTTP 409 ("Execução já em andamento") — sem feedback visível,
    o que faz parecer que "nada acontece no Chrome".

    Esta função roda no startup: para cada documento, zera `is_running` e
    `cancel_requested` e converte qualquer etapa com status "executando" de
    volta para "aguardando", para que o usuário possa reexecutar.

    Retorna a quantidade de documentos corrigidos.
    """
    corrigidos = 0
    try:
        with _connect() as conn:
            linhas = conn.execute(
                "select id, payload from documentos_processados"
            ).fetchall()
            for linha in linhas:
                try:
                    doc = json.loads(linha["payload"])
                except Exception:
                    continue

                mudou = False
                if doc.get("is_running"):
                    doc["is_running"] = False
                    mudou = True
                if doc.get("cancel_requested"):
                    doc["cancel_requested"] = False
                    mudou = True
                for etapa in doc.get("etapas") or []:
                    if isinstance(etapa, dict) and etapa.get("status") == "executando":
                        etapa["status"] = "aguardando"
                        mudou = True

                if mudou:
                    conn.execute(
                        """
                        update documentos_processados
                           set payload = ?, atualizado_em = datetime('now')
                         where id = ?
                        """,
                        (json.dumps(doc, ensure_ascii=False), linha["id"]),
                    )
                    corrigidos += 1
    except Exception:
        # Nunca deixar o startup falhar por causa do reset.
        return corrigidos
    return corrigidos


def _normalizar_texto(valor: Any) -> str:
    return (
        unicodedata.normalize("NFD", str(valor or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


def _to_float(valor: Any) -> float:
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor or "").strip()
    if not texto:
        return 0.0
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except Exception:
        return 0.0


def _period_start(periodo: str) -> datetime | None:
    now = datetime.now()
    p = str(periodo or "semana").strip().lower()
    if p in {"dia", "hoje"}:
        start = now
    elif p == "semana":
        start = now - timedelta(days=now.weekday())
    elif p in {"este-mes", "mes-atual"}:
        start = now.replace(day=1)
    elif p in {"mes", "30-dias"}:
        start = now - timedelta(days=30)
    else:
        return None
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_datetime_local(valor: Any) -> datetime | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    for candidato in (texto, texto.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidato)
        except Exception:
            pass
    return None


def _info_documento_dashboard(payload_doc: dict[str, Any] | None) -> dict[str, Any]:
    dados = (payload_doc or {}).get("dados_extraidos")
    if not isinstance(dados, dict):
        dados = {}
    resumo = dados.get("Resumo")
    if not isinstance(resumo, dict):
        resumo = {}
    return {
        "numeroProcesso": str(dados.get("Processo") or "").strip(),
        "fornecedor": str(dados.get("Nome do Credor") or "").strip(),
        "bruto": _to_float(resumo.get("Valor Bruto")),
    }


def obter_dashboard_registros_liquidacao(periodo: str = "semana", servidor_nome: str = "") -> dict[str, Any]:
    start = _period_start(periodo)
    servidor_norm = _normalizar_texto(servidor_nome)
    processos: dict[str, dict[str, Any]] = {}

    try:
        with _connect(timeout_s=1.5) as conn:
            rows = conn.execute(
                """
                select documento_id, payload, atualizado_em
                from liquidacao_registros_pendentes
                order by atualizado_em desc
                """
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(str(row["payload"] or "{}"))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue

                registrado_em = (
                    _parse_datetime_local(row["atualizado_em"])
                    or _parse_datetime_local(payload.get("registradoLocalmenteEm"))
                    or datetime.now()
                )
                if start and registrado_em < start:
                    continue

                servidor_payload = payload.get("servidorNome") or payload.get("servidor_nome")
                username_payload = payload.get("servidorUsername") or payload.get("servidor_username")
                if servidor_norm and servidor_norm not in {
                    _normalizar_texto(servidor_payload),
                    _normalizar_texto(username_payload),
                }:
                    continue

                documento_id = str(row["documento_id"] or "").strip()
                doc_row = conn.execute(
                    "select payload from documentos_processados where id = ?",
                    (documento_id,),
                ).fetchone()
                doc_payload = None
                if doc_row:
                    try:
                        doc_payload = json.loads(str(doc_row["payload"] or "{}"))
                    except Exception:
                        doc_payload = None

                doc_info = _info_documento_dashboard(doc_payload if isinstance(doc_payload, dict) else None)
                numero = str(
                    payload.get("numeroProcesso")
                    or payload.get("numero_processo")
                    or doc_info.get("numeroProcesso")
                    or ""
                ).strip()
                if not numero:
                    continue

                atual = {
                    "numeroProcesso": numero,
                    "fornecedor": doc_info.get("fornecedor") or "",
                    "bruto": float(doc_info.get("bruto") or 0),
                    "dataExecucao": registrado_em.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "concluido" if bool(payload.get("finalizada")) else "aguardando",
                }
                anterior = processos.get(numero)
                if not anterior or str(atual["dataExecucao"]) > str(anterior.get("dataExecucao") or ""):
                    processos[numero] = atual
    except Exception:
        return {"valorBruto": 0.0, "quantidadeProcessos": 0, "ultimosProcessos": []}

    ultimos = sorted(
        processos.values(),
        key=lambda item: str(item.get("dataExecucao") or ""),
        reverse=True,
    )
    return {
        "valorBruto": sum(float(item.get("bruto") or 0) for item in processos.values()),
        "quantidadeProcessos": len(processos),
        "ultimosProcessos": ultimos,
    }


def salvar_registro_liquidacao(payload: dict[str, Any], *, sincronizado: bool = False) -> None:
    documento_id = str(payload.get("documentoId") or payload.get("documento_id") or "").strip()
    numero_processo = str(payload.get("numeroProcesso") or payload.get("numero_processo") or "").strip()
    chave = documento_id or numero_processo
    if not chave:
        return

    data = dict(payload)
    data["registradoLocalmenteEm"] = datetime.now().isoformat(timespec="seconds")
    with _connect(timeout_s=2.0) as conn:
        conn.execute(
            """
            insert into liquidacao_registros_pendentes (documento_id, payload, sincronizado, atualizado_em)
            values (?, ?, ?, datetime('now'))
            on conflict(documento_id) do update set
              payload = excluded.payload,
              sincronizado = excluded.sincronizado,
              atualizado_em = excluded.atualizado_em
            """,
            (chave, json.dumps(data, ensure_ascii=False), 1 if sincronizado else 0),
        )
