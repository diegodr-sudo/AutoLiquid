"""Integracao Turso via SQL over HTTP."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

import requests

from services.config_service import carregar_config_app

_SCHEMA_OK = False
_FILA_SCHEMA_OK = False
_QUEUE_SERVERS_CONFIG_KEY = "fila_servidores_sorteio"
log = logging.getLogger(__name__)


def _now_iso() -> str:
    """Retorna o instante atual em UTC com sufixo 'Z', garantindo que o
    frontend interprete o valor corretamente (sem deslocamento de 3h)."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _config() -> tuple[str, str]:
    cfg = carregar_config_app()
    url = str(cfg.get("turso_database_url") or os.getenv("TURSO_DATABASE_URL") or "").strip()
    token = str(cfg.get("turso_auth_token") or os.getenv("TURSO_AUTH_TOKEN") or "").strip()
    return url, token


def turso_configurado() -> bool:
    url, token = _config()
    return bool(url and token)


def _pipeline_url() -> str:
    url, _token = _config()
    if not url:
        raise RuntimeError("URL do Turso nao configurada.")
    if url.startswith("libsql://"):
        url = "https://" + url.removeprefix("libsql://")
    return url.rstrip("/") + "/v2/pipeline"


def _arg(value: Any) -> dict[str, str]:
    if value is None:
        return {"type": "null", "value": ""}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def executar(sql: str, args: list[Any] | tuple[Any, ...] | None = None, *, timeout: float = 10) -> dict[str, Any]:
    _url, token = _config()
    if not token:
        raise RuntimeError("Token do Turso nao configurado.")
    stmt: dict[str, Any] = {"sql": sql}
    if args:
        stmt["args"] = [_arg(item) for item in args]
    response = requests.post(
        _pipeline_url(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]},
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(f"Turso respondeu HTTP {response.status_code}: {response.text[:300]}")
    try:
        response_json = response.json()
    except Exception as exc:
        raise RuntimeError(f"Turso respondeu sem JSON valido: {response.text[:300]}") from exc
    result = (response_json.get("results") or [{}])[0]
    if result.get("type") != "ok":
        raise RuntimeError(f"Turso recusou a consulta: {json.dumps(result, ensure_ascii=False)[:500]}")
    return result.get("response", {}).get("result", {})


def executar_pipeline(
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]],
    *,
    timeout: float = 20,
) -> list[dict[str, Any]]:
    _url, token = _config()
    if not token:
        raise RuntimeError("Token do Turso nao configurado.")
    if not statements:
        return []
    payload: list[dict[str, Any]] = []
    for sql, args in statements:
        stmt: dict[str, Any] = {"sql": sql}
        if args:
            stmt["args"] = [_arg(item) for item in args]
        payload.append({"type": "execute", "stmt": stmt})
    payload.append({"type": "close"})
    response = requests.post(
        _pipeline_url(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"requests": payload},
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(f"Turso respondeu HTTP {response.status_code}: {response.text[:300]}")
    try:
        response_json = response.json()
    except Exception as exc:
        raise RuntimeError(f"Turso respondeu sem JSON valido: {response.text[:300]}") from exc
    results = response_json.get("results") or []
    for result in results[:-1]:
        if result.get("type") != "ok":
            raise RuntimeError(f"Turso recusou a consulta: {json.dumps(result, ensure_ascii=False)[:500]}")
    return [
        (result.get("response", {}) or {}).get("result", {})
        for result in results
        if result.get("type") == "ok"
    ]


def executar_pipeline_transacional(
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]],
    *,
    chunk_size: int = 500,
    timeout: float = 60,
) -> list[dict[str, Any]]:
    """Executa statements em lote dentro de transações explícitas (BEGIN/COMMIT).

    Elimina os database locks causados por N auto-commits individuais — cada
    statement sem BEGIN/COMMIT abre e fecha uma transação própria no SQLite,
    o que causa bloqueios de dezenas de segundos com grandes volumes.

    Para datasets grandes, divide em chunks de `chunk_size` statements, cada
    chunk numa transação própria. O primeiro chunk deve conter o DELETE (se
    houver), e os subsequentes apenas INSERTs.
    """
    if not statements:
        return []
    results: list[dict[str, Any]] = []
    for start in range(0, len(statements), chunk_size):
        chunk = statements[start : start + chunk_size]
        # Encapsula cada chunk em BEGIN / COMMIT para garantir escrita atômica
        txn: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = (
            [("BEGIN", None)] + chunk + [("COMMIT", None)]
        )
        results.extend(executar_pipeline(txn, timeout=timeout))
    return results


def _cell_value(cell: Any) -> Any:
    if isinstance(cell, dict):
        if cell.get("type") == "null":
            return None
        return cell.get("value")
    return cell


def _row_to_dict(result: dict[str, Any], row: list[Any]) -> dict[str, Any]:
    cols = [str(col.get("name") or "") for col in result.get("cols") or []]
    return {cols[i]: _cell_value(cell) for i, cell in enumerate(row or []) if i < len(cols) and cols[i]}


def _rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [_row_to_dict(result, row) for row in result.get("rows") or []]


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _schema_name(sql: str) -> str:
    match = re.search(r"create\s+(?:unique\s+)?(?:table|index)\s+if\s+not\s+exists\s+([^\s(]+)", sql, re.I)
    return (match.group(1) if match else "").strip().casefold()


def garantir_schema_cache(*, timeout: float = 10) -> None:
    global _SCHEMA_OK, _FILA_SCHEMA_OK
    if _SCHEMA_OK:
        return
    statements = [
            ("""create table if not exists cache_snapshots (chave text primary key, payload text not null, atualizado_em text)""", None),
            ("""create table if not exists documentos_processados (id text primary key, payload text not null, atualizado_em text default current_timestamp)""", None),
            ("""create table if not exists datas_globais (id integer primary key check (id = 1), vencimento_pagamento text, data_apuracao text, atualizado_em text default current_timestamp)""", None),
            ("""create table if not exists contrato_ic_de_para (sarf text primary key, ig text not null, cnpj text, razao_social text, atualizado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_contrato_ic_ig on contrato_ic_de_para(ig)""", None),
            ("""create index if not exists idx_contrato_ic_cnpj on contrato_ic_de_para(cnpj)""", None),
            ("""create table if not exists vpd_de_para (chave text primary key, natureza text not null, natureza_base text, situacao_dsp text, situacao_norm text, vpd text not null, atualizado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_vpd_de_para_natureza on vpd_de_para(natureza, situacao_norm)""", None),
            ("""create index if not exists idx_vpd_de_para_base on vpd_de_para(natureza_base, situacao_norm)""", None),
            ("""create table if not exists uorg_de_para (ugr text primary key, uorg text not null, nome text, atualizado_em text default current_timestamp)""", None),
            ("""create table if not exists servidores (id integer primary key autoincrement, nome text not null, login text unique, email text, setor text, ativo integer not null default 1)""", None),
            ("""create table if not exists servidores_config (nome text primary key, nome_completo text, cor text, ordem integer default 0, criado_em text default current_timestamp)""", None),
            ("""create table if not exists tabelas_operacionais (chave text primary key, dados text not null, atualizado_em text default current_timestamp)""", None),
            ("""create table if not exists processos (id integer primary key autoincrement, numero_processo text not null unique, cnpj text, fornecedor text, contrato text, natureza text, tipo_liquidacao text, optante_simples integer, simples_consultado_em text, atualizado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_processos_cnpj on processos(cnpj)""", None),
            ("""create index if not exists idx_processos_contrato on processos(contrato)""", None),
            ("""create table if not exists execucoes (id integer primary key autoincrement, processo_id integer not null, servidor_id integer, documento_id text unique, data_execucao text default current_timestamp, bruto real default 0, deducoes real default 0, liquido real default 0, status text, possui_divergencia integer default 0, qtd_notas integer default 0, qtd_deducoes integer default 0, exige_intervencao_manual integer default 0, lf_numero text, ugr_numero text, vencimento_documento text, usar_conta_pdf integer default 1, conta_banco text, conta_agencia text, conta_conta text, observacoes text, vpd_manual text, vpd_informado_usuario integer default 0, empenhos_json text default '[]')""", None),
            ("""create index if not exists idx_execucoes_processo on execucoes(processo_id, data_execucao)""", None),
            ("""create index if not exists idx_execucoes_data on execucoes(data_execucao)""", None),
            ("""create index if not exists idx_execucoes_servidor on execucoes(servidor_id)""", None),
            ("""create table if not exists execucao_etapas (id integer primary key autoincrement, execucao_id integer not null, etapa_nome text, status text, mensagem text)""", None),
            ("""create table if not exists execucao_pendencias (id integer primary key autoincrement, execucao_id integer not null, tipo text, titulo text, descricao text, resolvida integer default 0)""", None),
            ("""create index if not exists idx_pendencias_execucao on execucao_pendencias(execucao_id)""", None),
            ("""create table if not exists notas_fiscais_execucao (id integer primary key autoincrement, execucao_id integer not null, numero_nota text, tipo text, emissao text, ateste text, valor real default 0)""", None),
            ("""create index if not exists idx_notas_execucao on notas_fiscais_execucao(execucao_id)""", None),
            ("""create table if not exists deducoes_execucao (id integer primary key autoincrement, execucao_id integer not null, codigo text, siafi text, tipo text, valor real default 0, base_calculo real default 0, status text)""", None),
            ("""create index if not exists idx_deducoes_execucao on deducoes_execucao(execucao_id)""", None),
            ("""create table if not exists liquidacao_registros (documento_id text primary key, numero_processo text, servidor_nome text, servidor_username text, finalizada integer not null default 0, tipo_documento text, numero_documento text, dificuldade integer, registrado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_liquidacao_registros_processo on liquidacao_registros(numero_processo, registrado_em)""", None),
            ("""create table if not exists empenhos (id integer primary key autoincrement, processo_id integer not null, numero text, situacao text, recurso text, natureza text, valor real default 0, saldo real default 0)""", None),
            ("""create index if not exists idx_empenhos_processo on empenhos(processo_id)""", None),
            ("""create index if not exists idx_empenhos_numero on empenhos(numero)""", None),
            ("""create table if not exists fila_processos_atual (chave text primary key, numero_processo text, sol_pagamento text, protocolo text, competencia text, dados text not null default '{}', responsavel_manual text, responsavel_manual_por text, responsavel_manual_em text, concluido integer not null default 0, concluido_por text, concluido_em text, presente integer not null default 1, atualizado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_fila_atual_presente_ordem on fila_processos_atual(presente, competencia, numero_processo, chave)""", None),
            ("""create table if not exists fila_processos_historico (chave text primary key, numero_processo text, sol_pagamento text, protocolo text, competencia text, dados text not null default '{}', responsavel_manual text, concluido integer not null default 0, presente integer not null default 0, primeiro_visto_em text, ultimo_visto_em text, saiu_da_fila_em text, retornou_em text, atualizado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_fila_historico_numero on fila_processos_historico(numero_processo, ultimo_visto_em)""", None),
            ("""create index if not exists idx_fila_historico_presente on fila_processos_historico(presente, competencia, numero_processo)""", None),
            ("""create table if not exists fila_processos_alertas (id integer primary key autoincrement, chave text not null, numero_processo text, sol_pagamento text, mensagem text not null, autor text, ativo integer not null default 1, criado_em text default current_timestamp)""", None),
            ("""create index if not exists idx_fila_alertas_chave on fila_processos_alertas(chave, ativo, criado_em)""", None),
            ("""create index if not exists idx_fila_alertas_numero on fila_processos_alertas(numero_processo, ativo, criado_em)""", None),
            ("""create table if not exists ausencias (id text primary key, servidor text not null, tipo text not null, inicio text not null, fim text not null, obs text)""", None),
        ]
    existing_result = executar(
        "select name from sqlite_master where type in ('table', 'index')",
        timeout=timeout,
    )
    existing = {str(row.get("name") or "").casefold() for row in _rows(existing_result)}

    pending = [(sql, args) for sql, args in statements if _schema_name(sql) not in existing]
    for start in range(0, len(pending), 4):
        executar_pipeline(pending[start:start + 4], timeout=timeout)
    _garantir_colunas(
        "servidores",
        {
            "role": "alter table servidores add column role text not null default 'user'",
            "senha": "alter table servidores add column senha text",
        },
        timeout=timeout,
    )
    _garantir_colunas(
        "execucoes",
        {
            "vpd_resolvido": "alter table execucoes add column vpd_resolvido text",
            "vpd_origem": "alter table execucoes add column vpd_origem text",
            "liquidacao_finalizada": "alter table execucoes add column liquidacao_finalizada integer",
            "registro_tipo_documento": "alter table execucoes add column registro_tipo_documento text",
            "registro_numero_documento": "alter table execucoes add column registro_numero_documento text",
            "dificuldade_pontuacao": "alter table execucoes add column dificuldade_pontuacao integer",
            "registro_preenchido_em": "alter table execucoes add column registro_preenchido_em text",
        },
        timeout=timeout,
    )
    _SCHEMA_OK = True
    _FILA_SCHEMA_OK = True
    _garantir_usuarios_auth(timeout=timeout)


def garantir_schema_fila_cache(*, timeout: float = 5) -> None:
    global _FILA_SCHEMA_OK
    if _SCHEMA_OK or _FILA_SCHEMA_OK:
        return
    statements = [
        ("""create table if not exists cache_snapshots (chave text primary key, payload text not null, atualizado_em text)""", None),
        ("""create table if not exists fila_processos_atual (chave text primary key, numero_processo text, sol_pagamento text, protocolo text, competencia text, dados text not null default '{}', responsavel_manual text, responsavel_manual_por text, responsavel_manual_em text, concluido integer not null default 0, concluido_por text, concluido_em text, presente integer not null default 1, atualizado_em text default current_timestamp)""", None),
        ("""create index if not exists idx_fila_atual_presente_ordem on fila_processos_atual(presente, competencia, numero_processo, chave)""", None),
        ("""create table if not exists fila_processos_alertas (id integer primary key autoincrement, chave text not null, numero_processo text, sol_pagamento text, mensagem text not null, autor text, ativo integer not null default 1, criado_em text default current_timestamp)""", None),
        ("""create index if not exists idx_fila_alertas_chave on fila_processos_alertas(chave, ativo, criado_em)""", None),
        ("""create index if not exists idx_fila_alertas_numero on fila_processos_alertas(numero_processo, ativo, criado_em)""", None),
    ]
    existing_result = executar(
        "select name from sqlite_master where type in ('table', 'index')",
        timeout=timeout,
    )
    existing = {str(row.get("name") or "").casefold() for row in _rows(existing_result)}
    pending = [(sql, args) for sql, args in statements if _schema_name(sql) not in existing]
    for start in range(0, len(pending), 4):
        executar_pipeline(pending[start:start + 4], timeout=timeout)
    _FILA_SCHEMA_OK = True


def _garantir_colunas(table: str, columns: dict[str, str], *, timeout: float = 10) -> None:
    result = executar(f"pragma table_info({table})", timeout=timeout)
    existentes = {str(row.get("name") or "").casefold() for row in _rows(result)}
    statements = [
        (sql, None)
        for name, sql in columns.items()
        if name.casefold() not in existentes
    ]
    if statements:
        executar_pipeline(statements, timeout=timeout)


def _senha_aleatoria() -> str:
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]


def _nome_canonico_auth(*values: Any) -> str:
    joined = " ".join(str(value or "") for value in values).strip().casefold()
    if not joined:
        return ""
    if "diego" in joined:
        return "diego"
    partes = re.findall(r"[a-z0-9]+", joined)
    return partes[0] if partes else joined


def _normalizar_role_auth(value: Any, *identity_values: Any) -> str:
    raw = str(value or "").strip().casefold()
    identity = " ".join(str(item or "") for item in identity_values).casefold()
    if "diego" in identity:
        return "moderator"
    if raw in {"moderator", "moderador", "admin", "administrator", "administrador"}:
        return "moderator"
    return "user"


def _garantir_usuarios_auth(*, timeout: float = 10) -> None:
    try:
        config_result = executar("select nome, nome_completo from servidores_config", timeout=timeout)
        inserts: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
        for item in _rows(config_result):
            nome = str(item.get("nome") or item.get("nome_completo") or "").strip()
            nome_completo = str(item.get("nome_completo") or nome).strip()
            if not nome:
                continue
            role = "moderator" if "diego" in f"{nome} {nome_completo}".casefold() else "user"
            inserts.append(
                (
                    """
                    insert into servidores (nome, login, email, setor, ativo, role, senha)
                    values (?, ?, null, null, 1, ?, ?)
                    on conflict(login) do nothing
                    """,
                    [nome_completo or nome, nome, role, _senha_aleatoria()],
                )
            )
        for start in range(0, len(inserts), 20):
            executar_pipeline(inserts[start:start + 20], timeout=timeout)
    except Exception:
        log.debug("Falha ao espelhar servidores_config para usuários de autenticação", exc_info=True)

    try:
        result = executar("select id, nome, login, senha, role from servidores", timeout=timeout)
    except Exception:
        return
    config_result = executar("select nome, nome_completo from servidores_config", timeout=timeout)
    config_keys = {
        _nome_canonico_auth(item.get("nome"), item.get("nome_completo"))
        for item in _rows(config_result)
    }
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
    found_diego = False
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(result):
        nome = str(row.get("nome") or "").strip()
        login = str(row.get("login") or "").strip()
        rows_by_key.setdefault(_nome_canonico_auth(nome, login), []).append(row)

    duplicate_ids: set[int] = set()
    for key, rows in rows_by_key.items():
        if not key or len(rows) <= 1:
            continue
        preferred = sorted(
            rows,
            key=lambda item: (
                0 if key in config_keys and _nome_canonico_auth(item.get("login")) == key else 1,
                0 if _nome_canonico_auth(item.get("nome")) == key else 1,
                _to_int(item.get("id")),
            ),
        )[0]
        duplicate_ids.update(_to_int(item.get("id")) for item in rows if _to_int(item.get("id")) != _to_int(preferred.get("id")))

    if duplicate_ids:
        placeholders = ",".join("?" for _ in duplicate_ids)
        statements.append((f"update servidores set ativo = 0 where id in ({placeholders})", list(duplicate_ids)))

    for row in _rows(result):
        if _to_int(row.get("id")) in duplicate_ids:
            continue
        nome = str(row.get("nome") or "").strip()
        login = str(row.get("login") or "").strip()
        key = f"{nome} {login}".casefold()
        is_diego = "diego" in key
        found_diego = found_diego or is_diego
        senha = str(row.get("senha") or "").strip()
        role = "moderator" if is_diego else str(row.get("role") or "user").strip().lower()
        if role not in {"user", "moderator"}:
            role = "user"
        if not senha:
            senha = _senha_aleatoria()
        statements.append(
            ("update servidores set senha = ?, role = ? where id = ?", [senha, role, row.get("id")])
        )
    if not found_diego:
        statements.append(
            (
                "insert into servidores (nome, login, email, setor, ativo, role, senha) values (?, ?, null, null, 1, 'moderator', ?)",
                ["Diego", "diego", _senha_aleatoria()],
            )
        )
    for start in range(0, len(statements), 20):
        executar_pipeline(statements[start:start + 20], timeout=timeout)


def testar_conexao() -> dict[str, Any]:
    inicio = time.perf_counter()
    garantir_schema_cache()
    result = executar("select 1 as ok")
    return {
        "configured": True,
        "ok": True,
        "durationMs": round((time.perf_counter() - inicio) * 1000, 1),
        "rowsRead": result.get("rows_read"),
        "rowsWritten": result.get("rows_written"),
    }


def _servidor_contexto() -> dict[str, str]:
    login = (os.getenv("AUTO_LIQUID_USER") or os.getenv("USER") or os.getenv("USERNAME") or "desconhecido").strip()
    nome = (os.getenv("AUTO_LIQUID_NOME") or os.getenv("FULLNAME") or login).strip()
    return {"login": login, "nome": nome, "email": (os.getenv("AUTO_LIQUID_EMAIL") or "").strip(), "setor": (os.getenv("AUTO_LIQUID_SETOR") or socket.gethostname() or "").strip()}


def _first_returning_id(result: dict[str, Any]) -> int:
    rows = result.get("rows") or []
    if rows and rows[0]:
        return _to_int(_cell_value(rows[0][0]))
    return _to_int(result.get("last_insert_rowid"))


def _upsert_servidor(contexto: dict[str, str]) -> int:
    result = executar(
        """
        insert into servidores (nome, login, email, setor, ativo, role, senha)
        values (?, ?, ?, ?, 1, ?, ?)
        on conflict(login) do update set
          nome = excluded.nome,
          email = excluded.email,
          setor = excluded.setor,
          role = case when lower(excluded.nome) like '%diego%' or lower(excluded.login) like '%diego%' then 'moderator' else servidores.role end,
          senha = coalesce(servidores.senha, excluded.senha),
          ativo = 1
        returning id
        """,
        [
            contexto["nome"],
            contexto["login"],
            contexto["email"] or None,
            contexto["setor"] or None,
            "moderator" if "diego" in f"{contexto['nome']} {contexto['login']}".casefold() else "user",
            _senha_aleatoria(),
        ],
        timeout=30,
    )
    return _first_returning_id(result)


def listar_usuarios_auth() -> list[dict[str, Any]]:
    result = executar(
        """
        select id, nome, login, email, setor, ativo, role, senha
        from servidores
        where ativo = 1
        order by lower(nome), lower(login)
        """,
        timeout=5,
    )
    usuarios: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in _rows(result):
        nome = str(row.get("nome") or row.get("login") or "").strip()
        login = str(row.get("login") or nome).strip()
        key = _nome_canonico_auth(nome, login)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        role = _normalizar_role_auth(row.get("role"), nome, login)
        usuarios.append({
            "id": _to_int(row.get("id")),
            "nome": nome,
            "username": login,
            "role": role,
            "senha": str(row.get("senha") or ""),
        })
    return usuarios


def autenticar_usuario(username: str, password: str) -> dict[str, Any] | None:
    username_clean = str(username or "").strip()
    password_clean = str(password or "")
    if not username_clean or not password_clean:
        return None
    result = executar(
        """
        select id, nome, login, role, senha
        from servidores
        where ativo = 1
          and (lower(login) = lower(?) or lower(nome) = lower(?))
        order by case when lower(login) = lower(?) then 0 else 1 end
        limit 1
        """,
        [username_clean, username_clean, username_clean],
        timeout=8,
    )
    rows = _rows(result)
    if not rows:
        return None
    row = rows[0]
    senha = str(row.get("senha") or "")
    if not secrets.compare_digest(senha, password_clean):
        return None
    role = _normalizar_role_auth(row.get("role"), row.get("nome"), row.get("login"))
    return {
        "id": _to_int(row.get("id")),
        "nome": str(row.get("nome") or row.get("login") or "").strip(),
        "username": str(row.get("login") or row.get("nome") or "").strip(),
        "role": role,
    }


def atualizar_usuario_auth(username: str, *, role: str | None = None, senha: str | None = None) -> dict[str, Any]:
    garantir_schema_cache(timeout=8)
    _garantir_usuarios_auth(timeout=8)
    username_clean = str(username or "").strip()
    if not username_clean:
        raise ValueError("Usuário obrigatório.")
    updates: list[str] = []
    args: list[Any] = []
    if role is not None:
        role_clean = str(role or "user").strip().lower()
        if role_clean not in {"user", "moderator"}:
            raise ValueError("Perfil inválido.")
        updates.append("role = ?")
        args.append(role_clean)
    if senha is not None:
        senha_clean = str(senha or "").strip() or _senha_aleatoria()
        updates.append("senha = ?")
        args.append(senha_clean)
    if updates:
        args.extend([username_clean, username_clean])
        executar(
            f"update servidores set {', '.join(updates)} where lower(login) = lower(?) or lower(nome) = lower(?)",
            args,
            timeout=8,
        )
    usuarios = listar_usuarios_auth()
    for usuario in usuarios:
        if usuario["username"].casefold() == username_clean.casefold() or usuario["nome"].casefold() == username_clean.casefold():
            return usuario
    raise ValueError("Usuário não encontrado.")


def _resolver_status_execucao(snapshot: dict[str, Any]) -> str:
    if bool(snapshot.get("isRunning")):
        return "executando"
    etapas = snapshot.get("etapas", []) or []
    deducoes = snapshot.get("deducoes", []) or []
    if any(str(item.get("status") or "") == "erro" for item in [*etapas, *deducoes]):
        return "erro"
    if etapas and all(str(etapa.get("status") or "") == "concluido" for etapa in etapas):
        return "concluido"
    return "aguardando"


def _upsert_processo(snapshot: dict[str, Any]) -> int:
    documento = snapshot.get("documento", {}) or {}
    numero = str(documento.get("processo") or snapshot.get("id") or "").strip()
    if not numero:
        raise RuntimeError("Nao foi possivel identificar o numero do processo para persistencia.")
    optante = snapshot.get("optante_simples")
    result = executar(
        """
        insert into processos (numero_processo, cnpj, fornecedor, contrato, natureza, tipo_liquidacao, optante_simples, atualizado_em)
        values (?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(numero_processo) do update set
          cnpj = excluded.cnpj,
          fornecedor = excluded.fornecedor,
          contrato = excluded.contrato,
          natureza = excluded.natureza,
          tipo_liquidacao = excluded.tipo_liquidacao,
          optante_simples = coalesce(excluded.optante_simples, processos.optante_simples),
          atualizado_em = current_timestamp
        returning id
        """,
        [
            numero,
            str(documento.get("cnpj") or "").strip() or None,
            str(documento.get("nomeCredor") or documento.get("fornecedor") or "").strip() or None,
            str(documento.get("contrato") or "").strip() or None,
            str(documento.get("natureza") or "").strip() or None,
            str(documento.get("tipoLiquidacao") or "").strip() or None,
            None if optante is None else bool(optante),
        ],
        timeout=30,
    )
    return _first_returning_id(result)


def _upsert_execucao(snapshot: dict[str, Any], processo_id: int, servidor_id: int) -> int:
    documento_id = str(snapshot.get("id") or "").strip() or None
    resumo = snapshot.get("resumo", {}) or {}
    pendencias = snapshot.get("pendencias", []) or []
    # Campos informados no registro ficam apenas na execucao/historico.
    # Nao alimente tabelas *_de_para a partir daqui: elas representam regras globais.
    vpd_manual = str(snapshot.get("vpd") or snapshot.get("vpd_manual") or "").strip() or None
    vpd_resolvido, vpd_origem = resolver_vpd(
        str((snapshot.get("documento") or {}).get("natureza") or "").strip(),
        str((snapshot.get("documento") or {}).get("tipoLiquidacao") or "").strip(),
        vpd_manual,
    )
    empenhos_normalizados = enriquecer_empenhos_com_siorg(
        snapshot.get("empenhos", []) or [],
        str(snapshot.get("ugrNumero") or "").strip(),
    )
    result = executar(
        """
        insert into execucoes (
          processo_id, servidor_id, documento_id, data_execucao, bruto, deducoes, liquido,
          status, possui_divergencia, qtd_notas, qtd_deducoes, exige_intervencao_manual,
          lf_numero, ugr_numero, vencimento_documento, usar_conta_pdf,
          conta_banco, conta_agencia, conta_conta, observacoes, vpd_manual,
          vpd_informado_usuario, empenhos_json, vpd_resolvido, vpd_origem
        )
        values (?, ?, ?, current_timestamp, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(documento_id) do update set
          processo_id = excluded.processo_id,
          servidor_id = excluded.servidor_id,
          data_execucao = current_timestamp,
          bruto = excluded.bruto,
          deducoes = excluded.deducoes,
          liquido = excluded.liquido,
          status = excluded.status,
          possui_divergencia = excluded.possui_divergencia,
          qtd_notas = excluded.qtd_notas,
          qtd_deducoes = excluded.qtd_deducoes,
          exige_intervencao_manual = excluded.exige_intervencao_manual,
          lf_numero = coalesce(excluded.lf_numero, execucoes.lf_numero),
          ugr_numero = coalesce(excluded.ugr_numero, execucoes.ugr_numero),
          vencimento_documento = coalesce(excluded.vencimento_documento, execucoes.vencimento_documento),
          usar_conta_pdf = excluded.usar_conta_pdf,
          conta_banco = coalesce(excluded.conta_banco, execucoes.conta_banco),
          conta_agencia = coalesce(excluded.conta_agencia, execucoes.conta_agencia),
          conta_conta = coalesce(excluded.conta_conta, execucoes.conta_conta),
          observacoes = coalesce(excluded.observacoes, execucoes.observacoes),
          vpd_manual = coalesce(excluded.vpd_manual, execucoes.vpd_manual),
          vpd_informado_usuario = execucoes.vpd_informado_usuario or excluded.vpd_informado_usuario,
          empenhos_json = excluded.empenhos_json,
          vpd_resolvido = coalesce(excluded.vpd_resolvido, execucoes.vpd_resolvido),
          vpd_origem = coalesce(excluded.vpd_origem, execucoes.vpd_origem)
        returning id
        """,
        [
            processo_id,
            servidor_id,
            documento_id,
            _to_float(resumo.get("bruto")),
            _to_float(resumo.get("deducoes")),
            _to_float(resumo.get("liquido")),
            _resolver_status_execucao(snapshot),
            any(p.get("tipo") == "divergencia" for p in pendencias),
            len(snapshot.get("notasFiscais", []) or []),
            len(snapshot.get("deducoes", []) or []),
            any(p.get("tipo") in {"bloqueio", "divergencia"} for p in pendencias),
            str(snapshot.get("lfNumero") or "").strip() or None,
            str(snapshot.get("ugrNumero") or "").strip() or None,
            str(snapshot.get("vencimentoDocumento") or "").strip() or None,
            bool(snapshot.get("usarContaPdf", True)),
            str(snapshot.get("contaBanco") or "").strip() or None,
            str(snapshot.get("contaAgencia") or "").strip() or None,
            str(snapshot.get("contaConta") or "").strip() or None,
            str((snapshot.get("statusGeral", {}) or {}).get("descricao") or "").strip() or None,
            vpd_manual,
            bool(vpd_manual),
            json.dumps(empenhos_normalizados, ensure_ascii=False, separators=(",", ":")),
            vpd_resolvido or None,
            vpd_origem or None,
        ],
        timeout=30,
    )
    return _first_returning_id(result)


def persistir_documento(snapshot: dict[str, Any]) -> int | None:
    if not turso_configurado():
        return None
    garantir_schema_cache(timeout=15)
    servidor_id = _upsert_servidor(_servidor_contexto())
    processo_id = _upsert_processo(snapshot)
    execucao_id = _upsert_execucao(snapshot, processo_id, servidor_id)
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
        ("delete from execucao_etapas where execucao_id = ?", [execucao_id]),
        ("delete from execucao_pendencias where execucao_id = ?", [execucao_id]),
        ("delete from notas_fiscais_execucao where execucao_id = ?", [execucao_id]),
        ("delete from deducoes_execucao where execucao_id = ?", [execucao_id]),
        ("delete from empenhos where processo_id = ?", [processo_id]),
    ]
    for etapa in snapshot.get("etapas", []) or []:
        statements.append(("insert into execucao_etapas (execucao_id, etapa_nome, status, mensagem) values (?, ?, ?, ?)", [execucao_id, str(etapa.get("nome") or "").strip(), str(etapa.get("status") or "aguardando").strip(), None]))
    for item in snapshot.get("pendencias", []) or []:
        statements.append(("insert into execucao_pendencias (execucao_id, tipo, titulo, descricao, resolvida) values (?, ?, ?, ?, 0)", [execucao_id, str(item.get("tipo") or "").strip(), str(item.get("titulo") or "").strip(), str(item.get("descricao") or "").strip() or None]))
    for item in snapshot.get("notasFiscais", []) or []:
        statements.append(("insert into notas_fiscais_execucao (execucao_id, numero_nota, tipo, emissao, ateste, valor) values (?, ?, ?, ?, ?, ?)", [execucao_id, str(item.get("nota") or item.get("numero") or "").strip() or None, str(item.get("tipo") or "").strip() or None, str(item.get("emissao") or "").strip() or None, str(item.get("ateste") or "").strip() or None, _to_float(item.get("valor"))]))
    for item in snapshot.get("deducoes", []) or []:
        statements.append(("insert into deducoes_execucao (execucao_id, codigo, siafi, tipo, valor, base_calculo, status) values (?, ?, ?, ?, ?, ?, ?)", [execucao_id, str(item.get("codigo") or "").strip() or None, str(item.get("siafi") or "").strip() or None, str(item.get("tipo") or "").strip() or None, _to_float(item.get("valor")), _to_float(item.get("baseCalculo")), str(item.get("status") or "aguardando").strip()]))
    for item in snapshot.get("empenhos", []) or []:
        statements.append(("insert into empenhos (processo_id, numero, situacao, recurso, natureza, valor, saldo) values (?, ?, ?, ?, ?, ?, ?)", [processo_id, str(item.get("numero") or "").strip() or None, str(item.get("situacao") or "").strip() or None, str(item.get("recurso") or "").strip() or None, str(item.get("natureza") or "").strip() or None, _to_float(item.get("valor")), _to_float(item.get("saldo"))]))
    executar_pipeline_transacional(statements, chunk_size=500, timeout=30)
    return execucao_id


def persistir_documento_com_log(snapshot: dict[str, Any]) -> int | None:
    try:
        return persistir_documento(snapshot)
    except Exception as exc:
        log.warning("Falha ao persistir documento no historico do Turso: %s", exc, exc_info=True)
        return None


def registrar_liquidacao(
    *,
    documento_id: str,
    numero_processo: str,
    finalizada: bool,
    tipo_documento: str = "",
    numero_documento: str = "",
    dificuldade: float | None = None,
    servidor_nome: str = "",
    servidor_username: str = "",
) -> None:
    garantir_schema_cache(timeout=8)
    documento_id = str(documento_id or "").strip()
    numero_processo = str(numero_processo or "").strip()
    if not documento_id and not numero_processo:
        raise ValueError("Informe o documento ou o número do processo.")
    tipo = str(tipo_documento or "").strip().upper()
    if finalizada and tipo not in {"NP", "RP", "LF"}:
        raise ValueError("Tipo de documento inválido.")
    numero_doc = str(numero_documento or "").strip()
    dificuldade_valor = None
    if finalizada:
        dificuldade_float = _to_float(dificuldade or 1)
        dificuldade_valor = max(1.0, min(5.0, round(dificuldade_float * 2) / 2))
    if finalizada and not numero_doc:
        raise ValueError("Número do documento obrigatório.")

    executar(
        """
        insert into liquidacao_registros (
          documento_id, numero_processo, servidor_nome, servidor_username, finalizada,
          tipo_documento, numero_documento, dificuldade, registrado_em
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        on conflict(documento_id) do update set
          numero_processo = excluded.numero_processo,
          servidor_nome = excluded.servidor_nome,
          servidor_username = excluded.servidor_username,
          -- Nunca faz downgrade de finalizada (1→0): garante que chamadas tardias
          -- de "pendente" não sobrescrevam um registro já concluído.
          finalizada = max(coalesce(liquidacao_registros.finalizada, 0), excluded.finalizada),
          -- Tipo, número e dificuldade só são sobrescritos quando a nova entrada é finalizada.
          tipo_documento = case when excluded.finalizada = 1 then excluded.tipo_documento else liquidacao_registros.tipo_documento end,
          numero_documento = case when excluded.finalizada = 1 then excluded.numero_documento else liquidacao_registros.numero_documento end,
          dificuldade = case when excluded.finalizada = 1 then excluded.dificuldade else liquidacao_registros.dificuldade end,
          registrado_em = current_timestamp
        """,
        [
            documento_id or numero_processo,
            numero_processo or None,
            str(servidor_nome or "").strip() or None,
            str(servidor_username or "").strip() or None,
            1 if finalizada else 0,
            tipo if finalizada else None,
            numero_doc if finalizada else None,
            dificuldade_valor,
        ],
        timeout=8,
    )

    if documento_id:
        executar(
            """
            update execucoes
            set liquidacao_finalizada = ?,
                registro_tipo_documento = ?,
                registro_numero_documento = ?,
                dificuldade_pontuacao = ?,
                registro_preenchido_em = current_timestamp
            where documento_id = ?
            """,
            [
                1 if finalizada else 0,
                tipo if finalizada else None,
                numero_doc if finalizada else None,
                dificuldade_valor,
                documento_id,
            ],
            timeout=8,
        )


def obter_liquidacao_pendente(
    *,
    servidor_nome: str = "",
    servidor_username: str = "",
) -> dict[str, Any] | None:
    if not turso_configurado():
        return None
    garantir_schema_cache(timeout=8)
    servidor_nome = str(servidor_nome or "").strip()
    servidor_username = str(servidor_username or "").strip()
    filtros = ["coalesce(finalizada, 0) = 0"]
    args: list[Any] = []
    if servidor_username:
        filtros.append("servidor_username = ?")
        args.append(servidor_username)
    elif servidor_nome:
        filtros.append("servidor_nome = ?")
        args.append(servidor_nome)

    result = executar(
        f"""
        select documento_id, numero_processo, registrado_em
        from liquidacao_registros
        where {' and '.join(filtros)}
        order by registrado_em desc
        limit 1
        """,
        args,
        timeout=8,
    )
    rows = _rows(result)
    if not rows:
        return None
    row = rows[0]
    return {
        "documentoId": str(row.get("documento_id") or ""),
        "numeroProcesso": str(row.get("numero_processo") or ""),
        "criadoEm": str(row.get("registrado_em") or ""),
    }


def descartar_liquidacao_pendente(documento_id: str) -> None:
    if not turso_configurado():
        return
    garantir_schema_cache(timeout=8)
    documento_id = str(documento_id or "").strip()
    if not documento_id:
        return
    executar(
        """
        delete from liquidacao_registros
        where documento_id = ?
          and coalesce(finalizada, 0) = 0
        """,
        [documento_id],
        timeout=8,
    )


def salvar_documento(doc_id: str, payload: dict) -> None:
    if not turso_configurado():
        return
    garantir_schema_cache()
    executar(
        """
        insert into documentos_processados (id, payload, atualizado_em)
        values (?, ?, current_timestamp)
        on conflict(id) do update set payload = excluded.payload, atualizado_em = current_timestamp
        """,
        [doc_id, json.dumps(payload, ensure_ascii=False)],
    )


def obter_documento(doc_id: str) -> dict | None:
    if not turso_configurado():
        return None
    garantir_schema_cache(timeout=5)
    rows = executar("select payload from documentos_processados where id = ?", [doc_id], timeout=5).get("rows") or []
    if not rows:
        return None
    parsed = _json_loads(_cell_value(rows[0][0]), None)
    return parsed if isinstance(parsed, dict) else None


def salvar_datas_globais(datas: dict[str, str]) -> None:
    garantir_schema_cache(timeout=10)
    executar(
        """
        insert into datas_globais (id, vencimento_pagamento, data_apuracao, atualizado_em)
        values (1, ?, ?, current_timestamp)
        on conflict(id) do update set
          vencimento_pagamento = excluded.vencimento_pagamento,
          data_apuracao = excluded.data_apuracao,
          atualizado_em = current_timestamp
        """,
        [str(datas.get("vencimento") or ""), str(datas.get("apuracao") or "")],
        timeout=30,
    )


def obter_datas_globais() -> dict[str, str]:
    if not turso_configurado():
        return {"vencimento": "", "apuracao": ""}
    garantir_schema_cache(timeout=4)
    result = executar("select vencimento_pagamento, data_apuracao from datas_globais where id = 1", timeout=4)
    rows = result.get("rows") or []
    if not rows:
        return {"vencimento": "", "apuracao": ""}
    return {"vencimento": str(_cell_value(rows[0][0]) or ""), "apuracao": str(_cell_value(rows[0][1]) or "")}


def salvar_simples_cnpj(cnpj_limpo: str, razao_social: str, optante: bool | None) -> None:
    if optante is None:
        return
    garantir_schema_cache(timeout=6)
    executar(
        """
        update processos
        set optante_simples = ?, simples_consultado_em = current_timestamp,
            fornecedor = coalesce(nullif(trim(?), ''), fornecedor)
        where replace(replace(replace(replace(cnpj, '.', ''), '/', ''), '-', ''), ' ', '') = ?
        """,
        [bool(optante), razao_social or "", cnpj_limpo],
        timeout=6,
    )


def consultar_simples_por_cnpj(cnpj_limpo: str) -> dict | None:
    if not turso_configurado():
        return None
    garantir_schema_cache(timeout=4)
    result = executar(
        """
        select fornecedor, optante_simples, simples_consultado_em
        from processos
        where replace(replace(replace(replace(cnpj, '.', ''), '/', ''), '-', ''), ' ', '') = ?
        order by (optante_simples is not null) desc, simples_consultado_em desc
        limit 1
        """,
        [cnpj_limpo],
        timeout=4,
    )
    rows = _rows(result)
    if not rows:
        return None
    consulted = str(rows[0].get("simples_consultado_em") or "")
    expired = True
    if consulted:
        try:
            expired = datetime.fromisoformat(consulted.replace("Z", "+00:00")) < datetime.now() - timedelta(days=30)
        except Exception:
            expired = True
    optante = rows[0].get("optante_simples")
    return {"razao_social": str(rows[0].get("fornecedor") or ""), "optante_simples": None if optante is None else bool(_to_int(optante)), "cache_expirado": expired}


def consultar_simples_batch(cnpjs: list[str]) -> dict[str, bool | None]:
    if not turso_configurado() or not cnpjs:
        return {}
    cnpjs_limpos = list(dict.fromkeys("".join(c for c in cnpj if c.isdigit()) for cnpj in cnpjs))
    cnpjs_limpos = [item for item in cnpjs_limpos if len(item) == 14]
    if not cnpjs_limpos:
        return {}
    placeholders = ",".join("?" for _ in cnpjs_limpos)
    result = executar(
        f"""
        select replace(replace(replace(replace(cnpj, '.', ''), '/', ''), '-', ''), ' ', '') as cnpj_limpo,
               optante_simples
        from processos
        where replace(replace(replace(replace(cnpj, '.', ''), '/', ''), '-', ''), ' ', '') in ({placeholders})
          and optante_simples is not null
        order by simples_consultado_em desc
        """,
        cnpjs_limpos,
        timeout=8,
    )
    out: dict[str, bool | None] = {}
    for row in _rows(result):
        cnpj = str(row.get("cnpj_limpo") or "")
        if cnpj and cnpj not in out:
            out[cnpj] = bool(_to_int(row.get("optante_simples")))
    return out


def _nome_servidor_simples(nome: str) -> str:
    partes = str(nome or "").strip().split()
    return partes[0] if partes else ""


def listar_servidores_config() -> list[dict[str, Any]]:
    garantir_schema_cache(timeout=6)
    result = executar("select nome, nome_completo, cor from servidores_config order by coalesce(ordem, 999999), criado_em, nome", timeout=6)
    return [{"nome": str(r.get("nome") or r.get("nome_completo") or ""), "nomeCompleto": str(r.get("nome_completo") or r.get("nome") or ""), "cor": str(r.get("cor") or "#6366f1")} for r in _rows(result)]


def salvar_servidor_config(nome: str, cor: str) -> None:
    garantir_schema_cache(timeout=8)
    nome_completo = str(nome or "").strip()
    if not nome_completo:
        raise ValueError("Nome do servidor e obrigatorio.")
    nome_simples = _nome_servidor_simples(nome_completo)
    executar(
        """
        insert into servidores_config (nome, nome_completo, cor, criado_em)
        values (?, ?, ?, current_timestamp)
        on conflict(nome) do update set nome_completo = excluded.nome_completo, cor = excluded.cor
        """,
        [nome_simples, nome_completo, str(cor or "#6366f1").strip() or "#6366f1"],
        timeout=8,
    )
    role = "moderator" if _nome_canonico_auth(nome_simples, nome_completo) == "diego" else "user"
    executar(
        """
        insert into servidores (nome, login, email, setor, ativo, role, senha)
        values (?, ?, null, null, 1, ?, ?)
        on conflict(login) do update set
          nome = excluded.nome,
          ativo = 1,
          role = case when ? = 'moderator' then 'moderator' else servidores.role end,
          senha = coalesce(servidores.senha, excluded.senha)
        """,
        [nome_completo, nome_simples, role, _senha_aleatoria(), role],
        timeout=8,
    )


def deletar_servidor_config(nome: str) -> None:
    garantir_schema_cache(timeout=8)
    nome_limpo = str(nome or "").strip()
    executar("delete from servidores_config where lower(nome) = lower(?) or lower(nome_completo) = lower(?)", [_nome_servidor_simples(nome_limpo), nome_limpo], timeout=8)
    nome_simples = _nome_servidor_simples(nome_limpo)
    executar(
        "update servidores set ativo = 0 where lower(login) = lower(?) or lower(nome) = lower(?) or lower(nome) = lower(?)",
        [nome_simples, nome_limpo, nome_simples],
        timeout=8,
    )


def obter_tabela_operacional(chave: str) -> list[dict[str, Any]] | None:
    garantir_schema_cache(timeout=10)
    result = executar("select dados from tabelas_operacionais where chave = ?", [str(chave or "").strip()], timeout=15)
    rows = result.get("rows") or []
    if not rows:
        return None
    parsed = _json_loads(_cell_value(rows[0][0]), [])
    return parsed if isinstance(parsed, list) else []


def salvar_tabela_operacional(chave: str, rows: list[dict[str, Any]]) -> None:
    garantir_schema_cache(timeout=10)
    chave_limpa = str(chave or "").strip()
    executar(
        """
        insert into tabelas_operacionais (chave, dados, atualizado_em)
        values (?, ?, current_timestamp)
        on conflict(chave) do update set dados = excluded.dados, atualizado_em = current_timestamp
        """,
        [chave_limpa, json.dumps(rows or [], ensure_ascii=False, separators=(",", ":"))],
        timeout=30,
    )
    if chave_limpa == "vpd":
        salvar_vpd_de_para(rows)
    elif chave_limpa == "uorg":
        salvar_uorg_de_para(rows)
    elif chave_limpa == _QUEUE_SERVERS_CONFIG_KEY:
        materializar_sorteio_fila(rows)


def _normalizar_situacao_vpd(situacao: str) -> str:
    return re.sub(r"[^A-Z0-9/]+", "", str(situacao or "").upper())


def _situacao_vpd_compativel(situacao_linha: str, situacao_alvo: str) -> bool:
    linha = _normalizar_situacao_vpd(situacao_linha)
    alvo = _normalizar_situacao_vpd(situacao_alvo)
    if not alvo:
        return True
    if not linha:
        return False
    if linha == alvo or alvo in linha or linha in alvo:
        return True
    codigos_linha = set(re.findall(r"[A-Z]{2,4}\d{3}", linha))
    codigos_alvo = set(re.findall(r"[A-Z]{2,4}\d{3}", alvo))
    return bool(codigos_linha and codigos_alvo and codigos_linha & codigos_alvo)


def salvar_vpd_de_para(rows: list[dict[str, Any]]) -> None:
    """Recria o de/para global somente a partir da tabela operacional VPD.

    DELETE + batch INSERTs dentro de uma única transação para evitar locks.
    """
    garantir_schema_cache(timeout=10)
    valid_rows: list[list[Any]] = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        natureza = str(row.get("natureza") or "").strip()
        situacao = str(row.get("situacaoDsp") or "").strip()
        vpd = str(row.get("vpd") or "").strip()
        if not natureza or not vpd:
            continue
        natureza_base = natureza.split(".")[0]
        situacao_norm = _normalizar_situacao_vpd(situacao)
        chave = f"{natureza}|{situacao_norm}|{index}"
        valid_rows.append([chave, natureza, natureza_base, situacao, situacao_norm, vpd])

    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
        ("delete from vpd_de_para", None)
    ]
    for start in range(0, len(valid_rows), _BATCH_INSERT_SIZE):
        chunk = valid_rows[start : start + _BATCH_INSERT_SIZE]
        placeholders = ", ".join("(?, ?, ?, ?, ?, ?, current_timestamp)" for _ in chunk)
        flat_args = [val for row_args in chunk for val in row_args]
        statements.append(
            (
                f"insert into vpd_de_para (chave, natureza, natureza_base, situacao_dsp, situacao_norm, vpd, atualizado_em) values {placeholders}",
                flat_args,
            )
        )
    executar_pipeline_transacional(statements, chunk_size=500, timeout=60)
    materializar_vpd_execucoes()


def salvar_uorg_de_para(rows: list[dict[str, Any]]) -> None:
    """Recria o de/para global somente a partir da tabela operacional UORG.

    DELETE + batch INSERTs dentro de uma única transação para evitar locks.
    """
    garantir_schema_cache(timeout=10)
    valid_rows: list[list[Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ugr = "".join(ch for ch in str(row.get("ugr") or "") if ch.isdigit())
        uorg = "".join(ch for ch in str(row.get("uorg") or row.get("siorg") or "") if ch.isdigit())
        nome = str(row.get("nome") or "").strip()
        if not ugr or not uorg:
            continue
        valid_rows.append([ugr, uorg, nome or None])

    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
        ("delete from uorg_de_para", None)
    ]
    for start in range(0, len(valid_rows), _BATCH_INSERT_SIZE):
        chunk = valid_rows[start : start + _BATCH_INSERT_SIZE]
        placeholders = ", ".join("(?, ?, ?, current_timestamp)" for _ in chunk)
        flat_args = [val for row_args in chunk for val in row_args]
        statements.append(
            (
                f"insert into uorg_de_para (ugr, uorg, nome, atualizado_em) values {placeholders}",
                flat_args,
            )
        )
    executar_pipeline_transacional(statements, chunk_size=500, timeout=60)
    materializar_siorg_execucoes()


def _vpd_candidates(natureza: str) -> list[dict[str, Any]]:
    nat = str(natureza or "").strip()
    if not nat:
        return []
    nat_base = nat.split(".")[0]
    result = executar(
        """
        select natureza, natureza_base, situacao_dsp, vpd
        from vpd_de_para
        where upper(natureza) = upper(?)
           or natureza_base = ?
        order by case when upper(natureza) = upper(?) then 0 else 1 end, chave
        """,
        [nat, nat_base, nat],
        timeout=8,
    )
    return _rows(result)


def _buscar_vpd(natureza: str, situacao: str = "") -> str:
    rows = _vpd_candidates(natureza)
    for row in rows:
        if str(row.get("natureza") or "").strip().upper() == str(natureza or "").strip().upper() and _situacao_vpd_compativel(str(row.get("situacao_dsp") or ""), situacao):
            return str(row.get("vpd") or "").strip()
    for row in rows:
        if str(row.get("natureza") or "").strip().upper() == str(natureza or "").strip().upper():
            return str(row.get("vpd") or "").strip()
    nat_base = str(natureza or "").strip().split(".")[0]
    for row in rows:
        if str(row.get("natureza_base") or "") == nat_base and _situacao_vpd_compativel(str(row.get("situacao_dsp") or ""), situacao):
            return str(row.get("vpd") or "").strip()
    for row in rows:
        if str(row.get("natureza_base") or "") == nat_base:
            return str(row.get("vpd") or "").strip()
    return ""


def resolver_vpd(natureza: str, situacao: str = "", manual: Any = "") -> tuple[str, str]:
    """Resolve VPD sem transformar preenchimento manual em regra global."""
    manual_txt = str(manual or "").strip()
    vpd_tabela = _buscar_vpd(natureza, situacao)
    vpd_norm = vpd_tabela.upper().replace("Ç", "C")
    de_acordo_nf = "DE ACORDO" in vpd_norm and "NF" in vpd_norm
    if vpd_tabela and not de_acordo_nf:
        return vpd_tabela, "tabela"
    if manual_txt:
        return manual_txt, "manual"
    if vpd_tabela:
        return vpd_tabela, "tabela"
    return "", ""


def resolver_siorg_por_ugr(ugr: Any) -> str:
    ugr_digitos = "".join(ch for ch in str(ugr or "") if ch.isdigit())
    if not ugr_digitos:
        return ""
    result = executar("select uorg from uorg_de_para where ugr = ?", [ugr_digitos], timeout=6)
    rows = _rows(result)
    return str(rows[0].get("uorg") or "").strip() if rows else ""


def enriquecer_empenhos_com_siorg(empenhos: list[dict[str, Any]], ugr: Any) -> list[dict[str, Any]]:
    ugr_txt = str(ugr or "").strip()
    siorg = resolver_siorg_por_ugr(ugr_txt)
    return [
        {
            **dict(item or {}),
            "ugrNumero": str((item or {}).get("ugrNumero") or ugr_txt),
            "siorgNumero": str((item or {}).get("siorgNumero") or siorg),
        }
        for item in (empenhos or [])
    ]


def materializar_vpd_execucoes() -> int:
    garantir_schema_cache(timeout=10)
    result = executar(
        """
        select e.id, p.natureza, p.tipo_liquidacao, e.vpd_manual
        from execucoes e
        join processos p on p.id = e.processo_id
        """,
        timeout=10,
    )
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
    for row in _rows(result):
        resolvido, origem = resolver_vpd(
            str(row.get("natureza") or ""),
            str(row.get("tipo_liquidacao") or ""),
            row.get("vpd_manual"),
        )
        statements.append(
            (
                "update execucoes set vpd_resolvido = ?, vpd_origem = ? where id = ?",
                [resolvido or None, origem or None, row.get("id")],
            )
        )
    for start in range(0, len(statements), 80):
        executar_pipeline(statements[start:start + 80], timeout=30)
    return len(statements)


def materializar_siorg_execucoes() -> int:
    garantir_schema_cache(timeout=10)
    result = executar("select id, ugr_numero, empenhos_json from execucoes", timeout=10)
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
    for row in _rows(result):
        empenhos = _json_loads(row.get("empenhos_json"), [])
        if not isinstance(empenhos, list):
            continue
        enriquecidos = enriquecer_empenhos_com_siorg(empenhos, row.get("ugr_numero"))
        if enriquecidos != empenhos:
            statements.append(
                (
                    "update execucoes set empenhos_json = ? where id = ?",
                    [json.dumps(enriquecidos, ensure_ascii=False, separators=(",", ":")), row.get("id")],
                )
            )
    for start in range(0, len(statements), 80):
        executar_pipeline(statements[start:start + 80], timeout=30)
    return len(statements)


def obter_servidores_sorteio() -> list[dict[str, Any]] | None:
    return obter_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY)


def salvar_servidores_sorteio(rows: list[dict[str, Any]]) -> None:
    salvar_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY, rows)


_BATCH_INSERT_SIZE = 50  # linhas por INSERT multi-valores (ajuste conforme payload médio)


def salvar_contratos_ic_de_para(rows: list[dict[str, Any]]) -> None:
    """Recria contrato_ic_de_para em uma única transação atômica.

    Usa batch inserts (N linhas por INSERT) dentro de BEGIN/COMMIT para
    evitar os locks de 25s causados por N auto-commits individuais.
    """
    garantir_schema_cache(timeout=15)
    normalized: list[dict[str, str]] = []
    valid_rows: list[list[Any]] = []

    for row in rows or []:
        sarf = str((row or {}).get("sarf") or "").strip()
        ig = str((row or {}).get("ig") or "").strip()
        if not sarf or not ig:
            continue
        cnpj = str((row or {}).get("cnpj") or "").strip()
        razao = str((row or {}).get("razaoSocial") or "").strip()
        normalized.append({"sarf": sarf, "ig": ig, "cnpj": cnpj, "razaoSocial": razao})
        valid_rows.append([sarf, ig, cnpj, razao])

    # Monta statements: DELETE + batch INSERTs + cache snapshot
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
        ("delete from contrato_ic_de_para", None)
    ]
    for start in range(0, len(valid_rows), _BATCH_INSERT_SIZE):
        chunk = valid_rows[start : start + _BATCH_INSERT_SIZE]
        placeholders = ", ".join("(?, ?, ?, ?, current_timestamp)" for _ in chunk)
        flat_args = [val for row_args in chunk for val in row_args]
        statements.append(
            (
                f"insert into contrato_ic_de_para (sarf, ig, cnpj, razao_social, atualizado_em) values {placeholders}",
                flat_args,
            )
        )
    statements.append(
        (
            "insert into cache_snapshots (chave, payload, atualizado_em) values ('contrato_ic_de_para', ?, current_timestamp) on conflict(chave) do update set payload = excluded.payload, atualizado_em = excluded.atualizado_em",
            [json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))],
        )
    )
    # Uma única transação: DELETE + todos os INSERTs em lote
    executar_pipeline_transacional(statements, chunk_size=500, timeout=60)
    aplicar_de_para_contratos_na_fila()


def obter_contratos_ic_de_para() -> dict[str, str]:
    garantir_schema_cache(timeout=4)
    result = executar("select sarf, ig from contrato_ic_de_para", timeout=4)
    return {str(r.get("sarf") or "").strip().upper(): str(r.get("ig") or "").strip() for r in _rows(result) if r.get("sarf") and r.get("ig")}


def listar_ausencias() -> list[dict[str, Any]]:
    garantir_schema_cache(timeout=6)
    result = executar("select id, servidor, tipo, inicio, fim, obs from ausencias order by inicio, servidor", timeout=6)
    return [{"id": str(r.get("id") or ""), "servidor": str(r.get("servidor") or ""), "tipo": str(r.get("tipo") or ""), "inicio": str(r.get("inicio") or ""), "fim": str(r.get("fim") or ""), "obs": r.get("obs")} for r in _rows(result)]


def criar_ausencia(ausencia: dict[str, Any]) -> dict[str, Any]:
    garantir_schema_cache(timeout=8)
    item = {"id": str(ausencia["id"]), "servidor": str(ausencia["servidor"]).strip(), "tipo": str(ausencia["tipo"]), "inicio": str(ausencia["inicio"]), "fim": str(ausencia["fim"]), "obs": str(ausencia.get("obs") or "").strip() or None}
    executar(
        "insert into ausencias (id, servidor, tipo, inicio, fim, obs) values (?, ?, ?, ?, ?, ?) on conflict(id) do update set servidor = excluded.servidor, tipo = excluded.tipo, inicio = excluded.inicio, fim = excluded.fim, obs = excluded.obs",
        [item["id"], item["servidor"], item["tipo"], item["inicio"], item["fim"], item["obs"]],
        timeout=8,
    )
    return item


def deletar_ausencia(ausencia_id: str) -> bool:
    garantir_schema_cache(timeout=8)
    result = executar("delete from ausencias where id = ?", [str(ausencia_id)], timeout=8)
    return _to_int(result.get("affected_row_count")) > 0


def _fila_row_key(row: dict[str, Any]) -> str:
    numero = str(row.get("Número Processo") or row.get("numeroProcesso") or row.get("numero_processo") or "").strip()
    sol = str(row.get("Sol. Pagamento") or row.get("solPagamento") or row.get("sol_pagamento") or "").strip()
    protocolo = str(row.get("Protocolo") or row.get("protocolo") or "").strip()
    return f"{numero}::{sol}" if numero or sol else protocolo or json.dumps(row, ensure_ascii=False, sort_keys=True)


def _numero_processo_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _numero_processo_match_keys(value: Any) -> list[str]:
    text = str(value or "").strip()
    digits = _numero_processo_digits(text)
    keys = [digits] if digits else []
    match = re.search(r"\b23080\.(\d{1,6})/\d{4}", text)
    if match:
        sequencial = match.group(1)
        keys.extend([sequencial, sequencial.lstrip("0")])
    seen: set[str] = set()
    return [key for key in keys if key and not (key in seen or seen.add(key))]


def _normalizar_sarf_fila(contrato: str) -> str:
    texto = str(contrato or "").strip()
    match = re.match(r"^(\d+)/(\d{4})$", texto)
    if match:
        return f"{match.group(2)}{match.group(1).zfill(5)}"
    return texto.upper()


def _mapa_contratos_ic() -> dict[str, str]:
    mapa = obter_contratos_ic_de_para()
    if mapa:
        return mapa
    rows = obter_tabela_operacional("contratos") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sarf = str(row.get("sarf") or "").strip().upper()
        ig = str(row.get("ig") or "").strip()
        if sarf and ig:
            mapa[sarf] = ig
    return mapa


def _aplicar_de_para_contratos_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapa = _mapa_contratos_ic()
    if not mapa:
        return rows
    enriched: list[dict[str, Any]] = []
    for row in rows or []:
        next_row = dict(row or {})
        contrato = str(next_row.get("Contrato") or next_row.get("contrato") or "").strip()
        ic_atual = str(next_row.get("IC") or next_row.get("ic") or "").strip()
        if contrato and not ic_atual:
            ig = mapa.get(_normalizar_sarf_fila(contrato))
            if ig:
                next_row["IC"] = ig
                next_row["__ic_origem"] = "turso_de_para"
        enriched.append(next_row)
    return enriched


def aplicar_de_para_contratos_na_fila() -> int:
    garantir_schema_cache(timeout=8)
    result = executar("select chave, dados from fila_processos_atual", timeout=8)
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
    alteradas = 0
    for item in _rows(result):
        base = _json_loads(item.get("dados"), {})
        if not isinstance(base, dict):
            continue
        enriched = _aplicar_de_para_contratos_rows([base])[0]
        if enriched != base:
            alteradas += 1
            statements.append(
                (
                    "update fila_processos_atual set dados = ?, atualizado_em = current_timestamp where chave = ?",
                    [json.dumps(enriched, ensure_ascii=False, separators=(",", ":")), item.get("chave")],
                )
            )
    if statements:
        executar_pipeline(statements, timeout=15)
    return alteradas


def salvar_snapshot_fila(rows: list[dict[str, Any]], updated_at: str | None) -> None:
    garantir_schema_cache()
    rows = _aplicar_de_para_contratos_rows(rows or [])
    try:
        from services import fila_sorteio_service

        rows = fila_sorteio_service.aplicar_sorteio_rows(
            rows,
            obter_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY) or [],
        )
    except Exception:
        pass
    presentes = executar("select chave from fila_processos_atual where presente = 1", timeout=8)
    chaves_presentes_antes = {str(row.get("chave") or "") for row in _rows(presentes)}
    chaves_snapshot = {_fila_row_key(row) for row in rows or []}
    snapshot_em = updated_at or _now_iso()
    gravado_em = _now_iso()
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
        ("insert into cache_snapshots (chave, payload, atualizado_em) values (?, ?, ?) on conflict(chave) do update set payload = excluded.payload, atualizado_em = excluded.atualizado_em", ["fila_processos_atual", json.dumps(rows or [], ensure_ascii=False, separators=(",", ":")), updated_at]),
    ]
    if chaves_snapshot:
        placeholders = ",".join("?" for _ in chaves_snapshot)
        args_ausentes = [gravado_em, *sorted(chaves_snapshot)]
        statements.append((f"update fila_processos_atual set presente = 0, atualizado_em = ? where presente = 1 and chave not in ({placeholders})", args_ausentes))
        statements.append((f"update fila_processos_historico set presente = 0, saiu_da_fila_em = coalesce(saiu_da_fila_em, ?), atualizado_em = ? where presente = 1 and chave not in ({placeholders})", [gravado_em, gravado_em, *sorted(chaves_snapshot)]))
    else:
        statements.append(("update fila_processos_atual set presente = 0, atualizado_em = ? where presente = 1", [gravado_em]))
        statements.append(("update fila_processos_historico set presente = 0, saiu_da_fila_em = coalesce(saiu_da_fila_em, ?), atualizado_em = ? where presente = 1", [gravado_em, gravado_em]))
    for row in rows or []:
        row_key = _fila_row_key(row)
        resetar_conclusao = 1 if row_key not in chaves_presentes_antes else 0
        numero_processo = str(row.get("Número Processo") or "").strip() or None
        sol_pagamento = str(row.get("Sol. Pagamento") or "").strip() or None
        protocolo = str(row.get("Protocolo") or "").strip() or None
        competencia = str(row.get("Competência") or "").strip() or None
        dados_json = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        responsavel_manual = str(row.get("__responsavel_manual") or "").strip() or None
        concluido = 1 if str(row.get("__concluido") or "") == "1" else 0
        statements.append(
            (
                """
                insert into fila_processos_atual (chave, numero_processo, sol_pagamento, protocolo, competencia, dados, responsavel_manual, responsavel_manual_por, responsavel_manual_em, concluido, concluido_por, concluido_em, presente, atualizado_em)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                on conflict(chave) do update set
                  numero_processo = excluded.numero_processo,
                  sol_pagamento = excluded.sol_pagamento,
                  protocolo = excluded.protocolo,
                  competencia = excluded.competencia,
                  dados = excluded.dados,
                  responsavel_manual = coalesce(excluded.responsavel_manual, fila_processos_atual.responsavel_manual),
                  responsavel_manual_por = coalesce(excluded.responsavel_manual_por, fila_processos_atual.responsavel_manual_por),
                  responsavel_manual_em = coalesce(excluded.responsavel_manual_em, fila_processos_atual.responsavel_manual_em),
                  concluido = case when ? = 1 then 0 when excluded.concluido = 1 then 1 else fila_processos_atual.concluido end,
                  concluido_por = case when ? = 1 then null else coalesce(excluded.concluido_por, fila_processos_atual.concluido_por) end,
                  concluido_em = case when ? = 1 then null else coalesce(excluded.concluido_em, fila_processos_atual.concluido_em) end,
                  presente = 1,
                  atualizado_em = excluded.atualizado_em
                """,
                [
                    row_key,
                    numero_processo,
                    sol_pagamento,
                    protocolo,
                    competencia,
                    dados_json,
                    responsavel_manual,
                    str(row.get("__responsavel_alterado_por") or "").strip() or None,
                    str(row.get("__responsavel_alterado_em") or "").strip() or None,
                    concluido,
                    str(row.get("__concluido_por") or "").strip() or None,
                    str(row.get("__concluido_em") or "").strip() or None,
                    gravado_em,
                    resetar_conclusao,
                    resetar_conclusao,
                    resetar_conclusao,
                ],
            )
        )
        statements.append(
            (
                """
                insert into fila_processos_historico (
                  chave, numero_processo, sol_pagamento, protocolo, competencia,
                  dados, responsavel_manual, concluido, presente, primeiro_visto_em,
                  ultimo_visto_em, saiu_da_fila_em, retornou_em, atualizado_em
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, null, ?, ?)
                on conflict(chave) do update set
                  numero_processo = excluded.numero_processo,
                  sol_pagamento = excluded.sol_pagamento,
                  protocolo = excluded.protocolo,
                  competencia = excluded.competencia,
                  dados = excluded.dados,
                  responsavel_manual = coalesce(excluded.responsavel_manual, fila_processos_historico.responsavel_manual),
                  concluido = case when ? = 1 then 0 when excluded.concluido = 1 then 1 else fila_processos_historico.concluido end,
                  presente = 1,
                  ultimo_visto_em = excluded.ultimo_visto_em,
                  saiu_da_fila_em = null,
                  retornou_em = case when fila_processos_historico.presente = 0 then excluded.ultimo_visto_em else fila_processos_historico.retornou_em end,
                  atualizado_em = excluded.atualizado_em
                """,
                [
                    row_key,
                    numero_processo,
                    sol_pagamento,
                    protocolo,
                    competencia,
                    dados_json,
                    responsavel_manual,
                    concluido,
                    snapshot_em,
                    gravado_em,
                    gravado_em if resetar_conclusao else None,
                    gravado_em,
                    resetar_conclusao,
                ],
            )
        )
    executar_pipeline_transacional(statements, chunk_size=500, timeout=90)


def materializar_sorteio_fila(servidores: list[dict[str, Any]] | None = None) -> int:
    garantir_schema_cache(timeout=8)
    try:
        from services import fila_sorteio_service
    except Exception:
        return 0

    if servidores is None:
        servidores = obter_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY) or []

    result = executar("select chave, dados from fila_processos_atual where presente = 1", timeout=8)
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
    for item in _rows(result):
        base = _json_loads(item.get("dados"), {})
        if not isinstance(base, dict):
            continue
        enriched = fila_sorteio_service.aplicar_sorteio_rows([base], servidores)[0]
        if enriched != base:
            statements.append(
                (
                    "update fila_processos_atual set dados = ?, atualizado_em = current_timestamp where chave = ?",
                    [json.dumps(enriched, ensure_ascii=False, separators=(",", ":")), item.get("chave")],
                )
            )

    for start in range(0, len(statements), 80):
        executar_pipeline(statements[start:start + 80], timeout=20)
    return len(statements)


def _mesclar_override_fila(row: dict[str, Any], meta: dict[str, Any], alertas: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(row or {})
    merged["__responsavel_manual"] = str(meta.get("responsavel_manual") or "").strip()
    merged["__responsavel_alterado"] = "1" if merged["__responsavel_manual"] else ""
    merged["__responsavel_alterado_por"] = str(meta.get("responsavel_manual_por") or "").strip()
    merged["__responsavel_alterado_em"] = str(meta.get("responsavel_manual_em") or "").strip()
    merged["__alertas_json"] = json.dumps(alertas or [], ensure_ascii=False)
    merged["__concluido"] = "1" if bool(_to_int(meta.get("concluido"))) else ""
    merged["__concluido_por"] = str(meta.get("concluido_por") or "").strip()
    merged["__concluido_em"] = str(meta.get("concluido_em") or "").strip()
    return merged


def obter_snapshot_fila(*, timeout: float = 2.5) -> dict[str, Any]:
    if not turso_configurado():
        return {"rows": [], "updatedAt": None}
    garantir_schema_fila_cache(timeout=timeout)
    result = executar(
        "select chave, numero_processo, dados, responsavel_manual, responsavel_manual_por, responsavel_manual_em, concluido, concluido_por, concluido_em, atualizado_em from fila_processos_atual where presente = 1 order by competencia asc, numero_processo asc, chave asc",
        timeout=timeout,
    )
    table_rows = _rows(result)
    if not table_rows:
        estado = _rows(executar(
            "select count(*) as total, coalesce(max(atualizado_em), '') as updated_at from fila_processos_atual where presente = 1",
            timeout=timeout,
        ))
        if _to_int((estado[0] if estado else {}).get("total")) > 0:
            return {"rows": [], "updatedAt": str((estado[0] if estado else {}).get("updated_at") or "") or None}
        snapshot = executar("select payload, atualizado_em from cache_snapshots where chave = ?", ["fila_processos_atual"], timeout=timeout)
        snap_rows = snapshot.get("rows") or []
        if not snap_rows:
            return {"rows": [], "updatedAt": None}
        parsed = _json_loads(_cell_value(snap_rows[0][0]), [])
        return {"rows": [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else [], "updatedAt": _cell_value(snap_rows[0][1]) if len(snap_rows[0]) > 1 else None}
    chaves = [str(row.get("chave") or "") for row in table_rows if row.get("chave")]
    numeros_por_chave = {str(row.get("chave") or ""): str(row.get("numero_processo") or "").strip() for row in table_rows}
    chaves_por_numero: dict[str, list[str]] = {}
    for chave, numero in numeros_por_chave.items():
        if numero:
            chaves_por_numero.setdefault(numero, []).append(chave)
    numeros = sorted(chaves_por_numero)
    alertas_por_chave: dict[str, list[dict[str, Any]]] = {}
    if chaves or numeros:
        chave_placeholders = ",".join("?" for _ in chaves) if chaves else "null"
        numero_placeholders = ",".join("?" for _ in numeros) if numeros else "null"
        alerts = executar(
            f"""
            select chave, numero_processo, id, mensagem, autor, criado_em
            from fila_processos_alertas
            where ativo = 1
              and (chave in ({chave_placeholders}) or numero_processo in ({numero_placeholders}))
            order by criado_em desc, id desc
            """,
            [*chaves, *numeros],
            timeout=timeout,
        )
        ids_por_chave: dict[str, set[int]] = {}
        for alerta in _rows(alerts):
            chave = str(alerta.get("chave") or "")
            numero = str(alerta.get("numero_processo") or "").strip()
            alerta_id = _to_int(alerta.get("id"))
            payload = {"id": alerta_id, "mensagem": str(alerta.get("mensagem") or ""), "autor": str(alerta.get("autor") or ""), "criadoEm": str(alerta.get("criado_em") or "") or None}
            destino_chaves = []
            if chave in chaves:
                destino_chaves.append(chave)
            destino_chaves.extend(chaves_por_numero.get(numero, []))
            for destino in dict.fromkeys(destino_chaves):
                if alerta_id in ids_por_chave.setdefault(destino, set()):
                    continue
                ids_por_chave[destino].add(alerta_id)
                alertas_por_chave.setdefault(destino, []).append(payload)
    parsed_rows: list[dict[str, Any]] = []
    updated_values: list[str] = []
    for item in table_rows:
        base = _json_loads(item.get("dados"), {})
        parsed_rows.append(_mesclar_override_fila(base if isinstance(base, dict) else {}, item, alertas_por_chave.get(str(item.get("chave") or ""), [])))
        if item.get("atualizado_em"):
            updated_values.append(str(item.get("atualizado_em")))
    return {"rows": parsed_rows, "updatedAt": max(updated_values) if updated_values else None}


def obter_setores_fila_historico(limite: int = 300, *, timeout: float = 3.0) -> list[str]:
    if not turso_configurado():
        return []
    garantir_schema_cache(timeout=timeout)
    result = executar(
        """
        select setor
        from (
          select distinct
            nullif(trim(coalesce(
              json_extract(dados, '$."Setor Origem"'),
              json_extract(dados, '$.setorOrigem'),
              json_extract(dados, '$.setor_origem'),
              ''
            )), '') as setor
          from fila_processos_historico
        ) setores
        where setor is not null
        order by lower(setor), setor
        limit ?
        """,
        [max(1, min(int(limite or 300), 1000))],
        timeout=timeout,
    )
    return [
        str(row.get("setor") or "").strip()
        for row in _rows(result)
        if str(row.get("setor") or "").strip()
    ]


def obter_token_tempo_real_fila(*, timeout: float = 2.0) -> str:
    if not turso_configurado():
        return "turso:disabled"
    garantir_schema_cache(timeout=timeout)
    fila = _rows(executar(
        """
        select count(*) as total,
               coalesce(max(atualizado_em), '') as updated_at
        from fila_processos_atual
        """,
        timeout=timeout,
    ))
    fila_presente = _rows(executar(
        """
        select count(*) as total
        from fila_processos_atual
        where presente = 1
        """,
        timeout=timeout,
    ))
    alertas = _rows(executar(
        """
        select count(*) as total,
               coalesce(max(id), 0) as max_id
        from fila_processos_alertas
        where ativo = 1
        """,
        timeout=timeout,
    ))
    configuracoes = _rows(executar(
        """
        select chave, coalesce(atualizado_em, '') as updated_at
        from tabelas_operacionais
        where chave in (?, ?)
        """,
        [_QUEUE_SERVERS_CONFIG_KEY, "fila_alerta_servico_regras"],
        timeout=timeout,
    ))
    fila_row = fila[0] if fila else {}
    fila_presente_row = fila_presente[0] if fila_presente else {}
    alertas_row = alertas[0] if alertas else {}
    config_updated_at = {
        str(row.get("chave") or ""): str(row.get("updated_at") or "")
        for row in configuracoes
    }
    return "|".join([
        "turso",
        str(fila_presente_row.get("total") or 0),
        str(fila_row.get("updated_at") or ""),
        str(alertas_row.get("total") or 0),
        str(alertas_row.get("max_id") or 0),
        config_updated_at.get(_QUEUE_SERVERS_CONFIG_KEY, ""),
        config_updated_at.get("fila_alerta_servico_regras", ""),
    ])


def salvar_responsavel_fila(*, numero_processo: str, sol_pagamento: str, responsavel: str, autor: str = "") -> str | None:
    garantir_schema_cache(timeout=8)
    row_key = _fila_row_key({"Número Processo": numero_processo, "Sol. Pagamento": sol_pagamento})
    alterado_em = _now_iso() if responsavel.strip() else None
    executar_pipeline(
        [
            (
                "insert into fila_processos_atual (chave, numero_processo, sol_pagamento, dados, responsavel_manual, responsavel_manual_por, responsavel_manual_em, presente, atualizado_em) values (?, ?, ?, '{}', ?, ?, ?, 1, ?) on conflict(chave) do update set numero_processo = excluded.numero_processo, sol_pagamento = excluded.sol_pagamento, responsavel_manual = excluded.responsavel_manual, responsavel_manual_por = excluded.responsavel_manual_por, responsavel_manual_em = excluded.responsavel_manual_em, atualizado_em = excluded.atualizado_em",
                [row_key, numero_processo.strip() or None, sol_pagamento.strip() or None, responsavel.strip() or None, autor or None, alterado_em, _now_iso()],
            ),
            (
                "update fila_processos_historico set responsavel_manual = ?, atualizado_em = ? where chave = ? or numero_processo = ?",
                [responsavel.strip() or None, _now_iso(), row_key, numero_processo.strip() or None],
            ),
        ],
        timeout=8,
    )
    return alterado_em


def salvar_conclusao_fila(*, numero_processo: str, sol_pagamento: str, concluido: bool, autor: str = "") -> dict[str, Any]:
    garantir_schema_cache(timeout=8)
    numero_limpo = numero_processo.strip()
    sol_limpa = sol_pagamento.strip()
    row_key = _fila_row_key({"Número Processo": numero_processo, "Sol. Pagamento": sol_pagamento})
    concluido_em = _now_iso() if concluido else ""
    concluido_por = autor if concluido else ""
    atualizado_em = _now_iso()
    if numero_limpo and not sol_limpa:
        numero_match_keys = _numero_processo_match_keys(numero_limpo)
        numero_placeholders = ",".join("?" for _ in numero_match_keys) or "?"
        numero_args = numero_match_keys or [""]
        matches = _rows(executar(
            f"""
            select chave, numero_processo
            from fila_processos_atual
            where presente = 1
              and (
                numero_processo = ?
                or replace(replace(replace(replace(coalesce(numero_processo, ''), '.', ''), '/', ''), '-', ''), ' ', '') in ({numero_placeholders})
              )
            """,
            [numero_limpo, *numero_args],
            timeout=8,
        ))
        if matches:
            chaves = [str(row.get("chave") or "").strip() for row in matches if str(row.get("chave") or "").strip()]
            placeholders = ",".join("?" for _ in chaves)
            statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
                (
                    f"update fila_processos_atual set concluido = ?, concluido_por = ?, concluido_em = ?, atualizado_em = ? where chave in ({placeholders})",
                    [1 if concluido else 0, concluido_por or None, concluido_em or None, atualizado_em, *chaves],
                ),
                (
                    f"""
                    update fila_processos_historico
                    set concluido = ?, atualizado_em = ?
                    where numero_processo = ?
                       or replace(replace(replace(replace(coalesce(numero_processo, ''), '.', ''), '/', ''), '-', ''), ' ', '') in ({numero_placeholders})
                    """,
                    [1 if concluido else 0, atualizado_em, numero_limpo, *numero_args],
                ),
            ]
            executar_pipeline(statements, timeout=8)
        return {
            "concluido": concluido,
            "concluidoPor": concluido_por,
            "concluidoEm": concluido_em,
            "matched": len(matches),
        }
    executar_pipeline(
        [
            (
                "insert into fila_processos_atual (chave, numero_processo, sol_pagamento, dados, concluido, concluido_por, concluido_em, presente, atualizado_em) values (?, ?, ?, '{}', ?, ?, ?, 1, ?) on conflict(chave) do update set numero_processo = excluded.numero_processo, sol_pagamento = excluded.sol_pagamento, concluido = excluded.concluido, concluido_por = excluded.concluido_por, concluido_em = excluded.concluido_em, atualizado_em = excluded.atualizado_em",
                [row_key, numero_limpo or None, sol_limpa or None, 1 if concluido else 0, concluido_por or None, concluido_em or None, atualizado_em],
            ),
            (
                "update fila_processos_historico set concluido = ?, atualizado_em = ? where chave = ? or numero_processo = ?",
                [1 if concluido else 0, atualizado_em, row_key, numero_limpo or None],
            ),
        ],
        timeout=8,
    )
    return {"concluido": concluido, "concluidoPor": concluido_por, "concluidoEm": concluido_em, "matched": 1}


def salvar_alerta_fila(*, numero_processo: str, sol_pagamento: str, mensagem: str, autor: str = "") -> dict[str, Any]:
    texto = str(mensagem or "").strip()
    if not texto:
        raise ValueError("Informe uma mensagem.")
    garantir_schema_cache(timeout=8)
    row_key = _fila_row_key({"Número Processo": numero_processo, "Sol. Pagamento": sol_pagamento})
    criado_em = _now_iso()
    result = executar("insert into fila_processos_alertas (chave, numero_processo, sol_pagamento, mensagem, autor, ativo, criado_em) values (?, ?, ?, ?, ?, 1, ?)", [row_key, numero_processo.strip() or None, sol_pagamento.strip() or None, texto, autor or None, criado_em], timeout=8)
    return {"id": _to_int(result.get("last_insert_rowid")) or int(time.time() * 1000), "mensagem": texto, "autor": autor, "criadoEm": criado_em}


def remover_alerta_fila(
    *,
    alerta_id: int,
    numero_processo: str = "",
    sol_pagamento: str = "",
    mensagem: str = "",
) -> None:
    garantir_schema_cache(timeout=8)
    row_key = _fila_row_key({"Número Processo": numero_processo, "Sol. Pagamento": sol_pagamento})
    texto = str(mensagem or "").strip()
    if row_key and texto:
        executar(
            """
            update fila_processos_alertas
            set ativo = 0
            where ativo = 1
              and (id = ? or (chave = ? and mensagem = ?))
            """,
            [alerta_id, row_key, texto],
            timeout=8,
        )
        return
    executar(
        "update fila_processos_alertas set ativo = 0 where id = ?",
        [alerta_id],
        timeout=8,
    )


def _period_start(periodo: str) -> str | None:
    now = datetime.now()
    p = str(periodo or "semana").strip().lower()
    if p in {"dia", "hoje"}:
        start = now
    elif p in {"semana", "este-mes"}:
        if p == "semana":
            start = now - timedelta(days=now.weekday())
        else:
            start = now.replace(day=1)
    elif p in {"mes", "30-dias"}:
        start = now - timedelta(days=30)
    elif p == "trimestre":
        start = now - timedelta(days=90)
    elif p == "semestre":
        start = now - timedelta(days=180)
    elif p == "ano":
        start = now - timedelta(days=365)
    else:
        return None
    return start.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _base_execucoes(where_sql: str = "1=1", args: Sequence[Any] = (), limite: int = 40) -> list[dict[str, Any]]:
    garantir_schema_cache(timeout=10)
    result = executar(
        f"""
        select p.id as processo_id, p.numero_processo, p.cnpj, p.fornecedor, p.contrato,
               p.natureza, p.tipo_liquidacao, p.atualizado_em,
               e.id as execucao_id, e.documento_id, e.data_execucao,
               case when coalesce(e.liquidacao_finalizada, lr.finalizada, 0) = 1 then 'concluido' else e.status end as status,
               e.bruto, e.deducoes as total_deducoes,
               e.liquido, e.lf_numero, e.ugr_numero, e.vencimento_documento,
               e.usar_conta_pdf, e.conta_banco, e.conta_agencia, e.conta_conta,
               e.possui_divergencia, e.exige_intervencao_manual, e.observacoes,
               e.vpd_manual, e.vpd_informado_usuario, e.vpd_resolvido, e.vpd_origem, e.empenhos_json,
               coalesce(e.liquidacao_finalizada, lr.finalizada, 0) as liquidacao_finalizada,
               coalesce(e.registro_tipo_documento, lr.tipo_documento, '') as registro_tipo_documento,
               coalesce(e.registro_numero_documento, lr.numero_documento, '') as registro_numero_documento,
               coalesce(e.dificuldade_pontuacao, lr.dificuldade) as dificuldade_pontuacao,
               coalesce(e.registro_preenchido_em, lr.registrado_em) as registro_preenchido_em,
               s.nome as servidor_nome, s.setor as servidor_setor
        from processos p
        join execucoes e on e.processo_id = p.id
        left join liquidacao_registros lr on lr.documento_id = e.documento_id
        left join servidores s on s.id = e.servidor_id
        where {where_sql}
        order by e.data_execucao desc, e.id desc
        limit ?
        """,
        [*args, limite],
        timeout=10,
    )
    return _rows(result)


def _children(table: str, exec_ids: list[int], cols: str, order: str) -> dict[int, list[dict[str, Any]]]:
    if not exec_ids:
        return {}
    placeholders = ",".join("?" for _ in exec_ids)
    result = executar(f"select execucao_id, {cols} from {table} where execucao_id in ({placeholders}) order by execucao_id, {order}", exec_ids, timeout=8)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in _rows(result):
        grouped.setdefault(_to_int(row.get("execucao_id")), []).append(row)
    return grouped


def _empenhos_por_processo(processo_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not processo_ids:
        return {}
    placeholders = ",".join("?" for _ in processo_ids)
    result = executar(f"select processo_id, numero, situacao, recurso, natureza, valor, saldo from empenhos where processo_id in ({placeholders}) order by processo_id, id", processo_ids, timeout=8)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in _rows(result):
        grouped.setdefault(_to_int(row.get("processo_id")), []).append({"numero": str(row.get("numero") or ""), "situacao": str(row.get("situacao") or ""), "recurso": str(row.get("recurso") or ""), "natureza": str(row.get("natureza") or ""), "valor": _to_float(row.get("valor")), "saldo": _to_float(row.get("saldo"))})
    return grouped


def _montar_historico(rows_exec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exec_ids = [_to_int(r.get("execucao_id")) for r in rows_exec]
    processo_ids = list(dict.fromkeys(_to_int(r.get("processo_id")) for r in rows_exec))
    notas = _children("notas_fiscais_execucao", exec_ids, "numero_nota, tipo, emissao, ateste, valor", "emissao")
    deducoes = _children("deducoes_execucao", exec_ids, "codigo, siafi, tipo, valor, base_calculo, status", "tipo")
    pendencias = _children("execucao_pendencias", exec_ids, "tipo, titulo, descricao, resolvida", "tipo")
    empenhos = _empenhos_por_processo(processo_ids)
    processos: dict[int, dict[str, Any]] = {}
    for row in rows_exec:
        pid = _to_int(row.get("processo_id"))
        eid = _to_int(row.get("execucao_id"))
        if pid not in processos:
            processos[pid] = {"numeroProcesso": str(row.get("numero_processo") or ""), "cnpj": str(row.get("cnpj") or ""), "fornecedor": str(row.get("fornecedor") or ""), "contrato": str(row.get("contrato") or ""), "natureza": str(row.get("natureza") or ""), "tipoLiquidacao": str(row.get("tipo_liquidacao") or ""), "atualizadoEm": str(row.get("atualizado_em") or ""), "execucoes": []}
        empenhos_json = _json_loads(row.get("empenhos_json"), [])
        empenhos_exec = empenhos_json if isinstance(empenhos_json, list) and empenhos_json else empenhos.get(pid)
        processos[pid]["execucoes"].append({
            "id": eid,
            "documentoId": str(row.get("documento_id") or ""),
            "dataExecucao": str(row.get("data_execucao") or ""),
            "status": str(row.get("status") or ""),
            "liquidacaoFinalizada": bool(_to_int(row.get("liquidacao_finalizada"))),
            "registroTipoDocumento": str(row.get("registro_tipo_documento") or ""),
            "registroNumeroDocumento": str(row.get("registro_numero_documento") or ""),
            "dificuldade": _to_float(row.get("dificuldade_pontuacao")) if row.get("dificuldade_pontuacao") is not None else None,
            "registroPreenchidoEm": str(row.get("registro_preenchido_em") or ""),
            "bruto": _to_float(row.get("bruto")),
            "totalDeducoes": _to_float(row.get("total_deducoes")),
            "liquido": _to_float(row.get("liquido")),
            "lfNumero": str(row.get("lf_numero") or ""),
            "ugrNumero": str(row.get("ugr_numero") or ""),
            "siorgNumero": resolver_siorg_por_ugr(row.get("ugr_numero") or ""),
            "vencimentoDocumento": str(row.get("vencimento_documento") or ""),
            "usarContaPdf": bool(_to_int(row.get("usar_conta_pdf", 1))) if row.get("usar_conta_pdf") is not None else True,
            "contaBanco": str(row.get("conta_banco") or ""),
            "contaAgencia": str(row.get("conta_agencia") or ""),
            "contaConta": str(row.get("conta_conta") or ""),
            "possuiDivergencia": bool(_to_int(row.get("possui_divergencia"))),
            "exigeIntervencao": bool(_to_int(row.get("exige_intervencao_manual"))),
            "observacoes": str(row.get("observacoes") or ""),
            "vpd": str(row.get("vpd_resolvido") or row.get("vpd_manual") or ""),
            "vpdManual": str(row.get("vpd_origem") or "") == "manual" or bool(_to_int(row.get("vpd_informado_usuario")) and not row.get("vpd_resolvido")),
            "servidorNome": str(row.get("servidor_nome") or ""),
            "servidorSetor": str(row.get("servidor_setor") or ""),
            "notasFiscais": [{"numero": str(n.get("numero_nota") or ""), "tipo": str(n.get("tipo") or ""), "emissao": str(n.get("emissao") or ""), "ateste": str(n.get("ateste") or ""), "valor": _to_float(n.get("valor"))} for n in notas.get(eid, [])],
            "deducoes": [{"codigo": str(d.get("codigo") or ""), "siafi": str(d.get("siafi") or ""), "tipo": str(d.get("tipo") or ""), "valor": _to_float(d.get("valor")), "baseCalculo": _to_float(d.get("base_calculo")), "status": str(d.get("status") or "")} for d in deducoes.get(eid, [])],
            "pendencias": [{"tipo": str(p.get("tipo") or ""), "titulo": str(p.get("titulo") or ""), "descricao": str(p.get("descricao") or ""), "resolvida": bool(_to_int(p.get("resolvida")))} for p in pendencias.get(eid, [])],
            "empenhos": empenhos_exec if isinstance(empenhos_exec, list) else [],
        })
    return list(processos.values())


def buscar_historico_por_cnpj(cnpj_limpo: str, contrato_filtro: str | Sequence[str] | None = None, limite: int = 40) -> list[dict[str, Any]]:
    cnpj = "".join(c for c in str(cnpj_limpo or "") if c.isdigit())
    if not cnpj:
        return []
    args: list[Any] = [cnpj]
    where = "replace(replace(replace(replace(p.cnpj, '.', ''), '/', ''), '-', ''), ' ', '') = ?"
    contratos = [contrato_filtro.strip()] if isinstance(contrato_filtro, str) and contrato_filtro.strip() else [str(item).strip() for item in (contrato_filtro or []) if str(item).strip()] if not isinstance(contrato_filtro, str) else []
    if contratos:
        where += " and (" + " or ".join("upper(p.contrato) like upper(?)" for _ in contratos) + ")"
        args.extend([f"%{item}%" for item in contratos])
    return _montar_historico(_base_execucoes(where, args, limite))


def buscar_historico_por_numero_processo(numero_processo_raw: str, limite: int = 40) -> list[dict[str, Any]]:
    texto = str(numero_processo_raw or "").strip()
    if not texto:
        return []
    return _montar_historico(_base_execucoes("p.numero_processo like ?", [f"%{texto}%"], limite))


def buscar_historico_por_contrato(contrato_filtro: str | Sequence[str], limite: int = 40) -> list[dict[str, Any]]:
    contratos = [contrato_filtro.strip()] if isinstance(contrato_filtro, str) and contrato_filtro.strip() else [str(item).strip() for item in contrato_filtro if str(item).strip()]
    if not contratos:
        return []
    where = "(" + " or ".join("upper(p.contrato) like upper(?)" for _ in contratos) + ")"
    return _montar_historico(_base_execucoes(where, [f"%{item}%" for item in contratos], limite))


def buscar_historico_por_empenho(empenho_filtro: str, limite: int = 40) -> list[dict[str, Any]]:
    empenho = str(empenho_filtro or "").strip()
    if not empenho:
        return []
    return _montar_historico(_base_execucoes("exists (select 1 from empenhos emp where emp.processo_id = p.id and emp.numero like ?)", [f"%{empenho}%"], limite))


def obter_dashboard(periodo: str = "semana", servidor_nome: str = "", limite: int = 5) -> dict[str, Any]:
    if not turso_configurado():
        return {"habilitado": False, "periodo": periodo, "valorBruto": 0, "quantidadeProcessos": 0, "ultimosProcessos": []}
    garantir_schema_cache(timeout=8)
    limite = max(1, min(100, _to_int(limite) or 5))
    start = _period_start(periodo)
    args: list[Any] = []
    where = "1=1"
    if start:
        where += " and e.data_execucao >= ?"
        args.append(start)
    if servidor_nome.strip():
        where += " and lower(s.nome) = lower(?)"
        args.append(servidor_nome.strip())
    total_row = _rows(executar(f"""
        with dedup as (
            select
                p.numero_processo,
                e.bruto,
                row_number() over (partition by p.numero_processo order by e.data_execucao desc, e.id desc) as rn
            from execucoes e
            left join servidores s on s.id = e.servidor_id
            join processos p on p.id = e.processo_id
            where {where}
        )
        select
            coalesce(sum(bruto), 0) as valor_bruto,
            count(*) as quantidade_processos
        from dedup
        where rn = 1
    """, args, timeout=8))[0]
    ultimos = _rows(executar(f"""
        with execucoes_unicas as (
          select
            e.id,
            e.processo_id,
            e.documento_id,
            e.bruto,
            e.data_execucao,
            e.liquidacao_finalizada,
            row_number() over (partition by p.numero_processo order by e.data_execucao desc, e.id desc) as rn
          from execucoes e
          left join servidores s on s.id = e.servidor_id
          join processos p on p.id = e.processo_id
          where {where}
        )
        select
          p.numero_processo,
          p.fornecedor,
          eu.bruto,
          eu.data_execucao,
          coalesce(eu.liquidacao_finalizada, lr.finalizada, 0) as finalizada
        from execucoes_unicas eu
        join processos p on p.id = eu.processo_id
        left join liquidacao_registros lr on lr.documento_id = eu.documento_id
        where eu.rn = 1
        order by eu.data_execucao desc
        limit ?
    """, [*args, limite], timeout=8))
    return {"habilitado": True, "periodo": periodo, "valorBruto": _to_float(total_row.get("valor_bruto")), "quantidadeProcessos": _to_int(total_row.get("quantidade_processos")), "ultimosProcessos": [{"numeroProcesso": str(r.get("numero_processo") or ""), "fornecedor": str(r.get("fornecedor") or ""), "bruto": _to_float(r.get("bruto")), "dataExecucao": str(r.get("data_execucao") or ""), "status": "concluido" if _to_int(r.get("finalizada")) else "aguardando"} for r in ultimos]}


def obter_dashboard_historico(empresa: str = "", contrato: str = "", servidor: str = "", periodo: str = "semana") -> dict[str, Any]:
    if not turso_configurado():
        return {"habilitado": False, "total": 0, "totalValor": 0, "porServidor": [], "porEmpresa": [], "porContrato": [], "porMes": []}
    garantir_schema_cache(timeout=8)
    start = _period_start(periodo)
    where_parts = ["1=1"]
    args: list[Any] = []
    if start:
        where_parts.append("e.data_execucao >= ?")
        args.append(start)
    if empresa.strip():
        where_parts.append("upper(p.fornecedor) like upper(?)")
        args.append(f"%{empresa.strip()}%")
    if contrato.strip():
        where_parts.append("upper(p.contrato) like upper(?)")
        args.append(f"%{contrato.strip()}%")
    if servidor.strip():
        where_parts.append("upper(s.nome) like upper(?)")
        args.append(f"%{servidor.strip()}%")
    where = " and ".join(where_parts)
    base_cte = f"""
        with execucoes_ranked as (
          select
            e.processo_id,
            e.bruto,
            e.data_execucao,
            coalesce(nullif(trim(s.nome), ''), '-') as servidor_nome,
            coalesce(nullif(trim(p.fornecedor), ''), '-') as fornecedor_nome,
            upper(coalesce(nullif(trim(p.fornecedor), ''), '-')) as fornecedor_key,
            coalesce(nullif(trim(p.cnpj), ''), '') as cnpj,
            coalesce(nullif(trim(p.contrato), ''), '(sem contrato)') as contrato_label,
            coalesce(e.liquidacao_finalizada, lr.finalizada, 0) as finalizada,
            row_number() over (partition by e.processo_id order by e.data_execucao desc, e.id desc) as rn
          from execucoes e
          join processos p on p.id = e.processo_id
          left join servidores s on s.id = e.servidor_id
          left join liquidacao_registros lr on lr.documento_id = e.documento_id
          where {where}
        ),
        base as (
          select *
          from execucoes_ranked
          where rn = 1 and finalizada = 1
        )
    """
    total = _rows(executar(f"{base_cte} select count(*) as cnt, coalesce(sum(bruto), 0) as total from base", args, timeout=8))[0]
    por_servidor = _rows(executar(f"{base_cte} select servidor_nome as nome, count(*) as count, coalesce(sum(bruto), 0) as valor from base group by servidor_nome order by valor desc limit 20", args, timeout=8))
    por_empresa = _rows(executar(f"{base_cte} select min(fornecedor_nome) as nome, cnpj, count(*) as count, coalesce(sum(bruto), 0) as valor from base group by fornecedor_key, cnpj order by valor desc limit 20", args, timeout=8))
    por_contrato = _rows(executar(f"{base_cte} select contrato_label as contrato, count(*) as count, coalesce(sum(bruto), 0) as valor from base group by contrato_label order by valor desc limit 15", args, timeout=8))
    por_mes = _rows(executar(f"{base_cte} select substr(data_execucao, 1, 7) as mes, count(*) as count, coalesce(sum(bruto), 0) as valor from base where data_execucao is not null group by mes order by mes limit 24", args, timeout=8))
    return {
        "habilitado": True,
        "total": _to_int(total.get("cnt")),
        "totalValor": _to_float(total.get("total")),
        "porServidor": [{"nome": str(r.get("nome") or "-"), "count": _to_int(r.get("count")), "valor": _to_float(r.get("valor"))} for r in por_servidor],
        "porEmpresa": [{"nome": str(r.get("nome") or "-"), "cnpj": str(r.get("cnpj") or ""), "count": _to_int(r.get("count")), "valor": _to_float(r.get("valor"))} for r in por_empresa],
        "porContrato": [{"contrato": str(r.get("contrato") or "-"), "count": _to_int(r.get("count")), "valor": _to_float(r.get("valor"))} for r in por_contrato],
        "porMes": [{"mes": str(r.get("mes") or ""), "count": _to_int(r.get("count")), "valor": _to_float(r.get("valor"))} for r in por_mes],
    }


# ── Bug Reports ───────────────────────────────────────────────────────────────

_BUG_REPORTS_SCHEMA_OK = False


def garantir_schema_bug_reports(*, timeout: float = 10) -> None:
    global _BUG_REPORTS_SCHEMA_OK
    if _BUG_REPORTS_SCHEMA_OK:
        return
    existing_result = executar(
        "select name from sqlite_master where type in ('table', 'index')",
        timeout=timeout,
    )
    existing = {str(row.get("name") or "").casefold() for row in _rows(existing_result)}
    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = []
    if "bug_reports" not in existing:
        statements.append((
            """create table if not exists bug_reports (
                id integer primary key autoincrement,
                pagina text,
                descricao text not null,
                contexto text,
                campos_dom text,
                erros_console text,
                versao_app text,
                servidor_nome text,
                resolvido integer not null default 0,
                criado_em text default current_timestamp,
                resolvido_em text
            )""",
            None,
        ))
    if "idx_bug_reports_criado" not in existing:
        statements.append((
            "create index if not exists idx_bug_reports_criado on bug_reports(criado_em desc)",
            None,
        ))
    if statements:
        executar_pipeline(statements, timeout=timeout)
    _BUG_REPORTS_SCHEMA_OK = True


def salvar_bug_report(
    *,
    pagina: str = "",
    descricao: str,
    contexto: dict | None = None,
    campos_dom: dict | None = None,
    erros_console: list | None = None,
    versao_app: str = "",
    servidor_nome: str = "",
) -> int:
    garantir_schema_bug_reports(timeout=8)
    result = executar(
        """
        insert into bug_reports
            (pagina, descricao, contexto, campos_dom, erros_console, versao_app, servidor_nome)
        values (?, ?, ?, ?, ?, ?, ?)
        returning id
        """,
        [
            str(pagina or "").strip() or None,
            str(descricao or "").strip(),
            json.dumps(contexto or {}, ensure_ascii=False) if contexto else None,
            json.dumps(campos_dom or {}, ensure_ascii=False) if campos_dom else None,
            json.dumps(erros_console or [], ensure_ascii=False) if erros_console else None,
            str(versao_app or "").strip() or None,
            str(servidor_nome or "").strip() or None,
        ],
        timeout=8,
    )
    return _first_returning_id(result)


def listar_bug_reports(*, resolvido: bool | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if not turso_configurado():
        return []
    garantir_schema_bug_reports(timeout=6)
    filtro = ""
    args: list[Any] = []
    if resolvido is not None:
        filtro = "where resolvido = ?"
        args.append(1 if resolvido else 0)
    result = executar(
        f"""
        select id, pagina, descricao, contexto, campos_dom, erros_console,
               versao_app, servidor_nome, resolvido, criado_em, resolvido_em
        from bug_reports
        {filtro}
        order by criado_em desc
        limit ?
        """,
        [*args, limit],
        timeout=8,
    )
    out = []
    for row in _rows(result):
        out.append({
            "id": _to_int(row.get("id")),
            "pagina": str(row.get("pagina") or ""),
            "descricao": str(row.get("descricao") or ""),
            "contexto": _json_loads(row.get("contexto"), {}),
            "camposDom": _json_loads(row.get("campos_dom"), {}),
            "errosConsole": _json_loads(row.get("erros_console"), []),
            "versaoApp": str(row.get("versao_app") or ""),
            "servidorNome": str(row.get("servidor_nome") or ""),
            "resolvido": bool(_to_int(row.get("resolvido"))),
            "criadoEm": str(row.get("criado_em") or ""),
            "resolvidoEm": str(row.get("resolvido_em") or ""),
        })
    return out


def resolver_bug_report(bug_id: int) -> bool:
    garantir_schema_bug_reports(timeout=6)
    executar(
        "update bug_reports set resolvido = 1, resolvido_em = current_timestamp where id = ?",
        [bug_id],
        timeout=6,
    )
    return True


def deletar_bug_report(bug_id: int) -> bool:
    garantir_schema_bug_reports(timeout=6)
    executar(
        "delete from bug_reports where id = ?",
        [bug_id],
        timeout=6,
    )
    return True


def importar_historico_postgres(postgres_service: Any) -> dict[str, int]:
    """Copia as tabelas historicas do PostgreSQL para o Turso."""
    garantir_schema_cache(timeout=20)
    if not postgres_service.postgres_habilitado():
        return {"processos": 0, "execucoes": 0, "empenhos": 0, "notas": 0, "deducoes": 0, "pendencias": 0}

    def _fetch(sql: str) -> list[dict[str, Any]]:
        with postgres_service._get_connection(statement_timeout_ms=30000) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]

    processos = _fetch("select id, numero_processo, cnpj, fornecedor, contrato, natureza, tipo_liquidacao, optante_simples, simples_consultado_em, atualizado_em from processos")
    servidores = _fetch("select id, nome, login, email, setor, ativo from servidores")
    execucoes = _fetch("select id, processo_id, servidor_id, documento_id, data_execucao, bruto, deducoes, liquido, status, possui_divergencia, qtd_notas, qtd_deducoes, exige_intervencao_manual, lf_numero, ugr_numero, vencimento_documento, usar_conta_pdf, conta_banco, conta_agencia, conta_conta, observacoes, vpd_manual, vpd_informado_usuario, coalesce(empenhos_json, '[]'::jsonb) as empenhos_json from execucoes")
    empenhos = _fetch("select processo_id, numero, situacao, recurso, natureza, valor, saldo from empenhos")
    notas = _fetch("select execucao_id, numero_nota, tipo, emissao, ateste, valor from notas_fiscais_execucao")
    deducoes = _fetch("select execucao_id, codigo, siafi, tipo, valor, base_calculo, status from deducoes_execucao")
    pendencias = _fetch("select execucao_id, tipo, titulo, descricao, resolvida from execucao_pendencias")

    statements: list[tuple[str, list[Any] | tuple[Any, ...] | None]] = [
        ("delete from execucao_pendencias", None),
        ("delete from deducoes_execucao", None),
        ("delete from notas_fiscais_execucao", None),
        ("delete from empenhos", None),
        ("delete from execucao_etapas", None),
        ("delete from execucoes", None),
        ("delete from processos", None),
        ("delete from servidores", None),
    ]
    for r in servidores:
        statements.append(("insert into servidores (id, nome, login, email, setor, ativo) values (?, ?, ?, ?, ?, ?)", [r.get("id"), r.get("nome"), r.get("login"), r.get("email"), r.get("setor"), bool(r.get("ativo", True))]))
    for r in processos:
        statements.append(("insert into processos (id, numero_processo, cnpj, fornecedor, contrato, natureza, tipo_liquidacao, optante_simples, simples_consultado_em, atualizado_em) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [r.get("id"), r.get("numero_processo"), r.get("cnpj"), r.get("fornecedor"), r.get("contrato"), r.get("natureza"), r.get("tipo_liquidacao"), None if r.get("optante_simples") is None else bool(r.get("optante_simples")), str(r.get("simples_consultado_em") or "") or None, str(r.get("atualizado_em") or "") or None]))
    for r in execucoes:
        statements.append(("insert into execucoes (id, processo_id, servidor_id, documento_id, data_execucao, bruto, deducoes, liquido, status, possui_divergencia, qtd_notas, qtd_deducoes, exige_intervencao_manual, lf_numero, ugr_numero, vencimento_documento, usar_conta_pdf, conta_banco, conta_agencia, conta_conta, observacoes, vpd_manual, vpd_informado_usuario, empenhos_json, vpd_resolvido, vpd_origem) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null, null)", [r.get("id"), r.get("processo_id"), r.get("servidor_id"), r.get("documento_id"), str(r.get("data_execucao") or "") or None, _to_float(r.get("bruto")), _to_float(r.get("deducoes")), _to_float(r.get("liquido")), r.get("status"), bool(r.get("possui_divergencia")), _to_int(r.get("qtd_notas")), _to_int(r.get("qtd_deducoes")), bool(r.get("exige_intervencao_manual")), r.get("lf_numero"), r.get("ugr_numero"), r.get("vencimento_documento"), bool(r.get("usar_conta_pdf", True)), r.get("conta_banco"), r.get("conta_agencia"), r.get("conta_conta"), r.get("observacoes"), r.get("vpd_manual"), bool(r.get("vpd_informado_usuario")), json.dumps(r.get("empenhos_json") if isinstance(r.get("empenhos_json"), list) else _json_loads(r.get("empenhos_json"), []), ensure_ascii=False)]))
    for r in empenhos:
        statements.append(("insert into empenhos (processo_id, numero, situacao, recurso, natureza, valor, saldo) values (?, ?, ?, ?, ?, ?, ?)", [r.get("processo_id"), r.get("numero"), r.get("situacao"), r.get("recurso"), r.get("natureza"), _to_float(r.get("valor")), _to_float(r.get("saldo"))]))
    for r in notas:
        statements.append(("insert into notas_fiscais_execucao (execucao_id, numero_nota, tipo, emissao, ateste, valor) values (?, ?, ?, ?, ?, ?)", [r.get("execucao_id"), r.get("numero_nota"), r.get("tipo"), str(r.get("emissao") or "") or None, str(r.get("ateste") or "") or None, _to_float(r.get("valor"))]))
    for r in deducoes:
        statements.append(("insert into deducoes_execucao (execucao_id, codigo, siafi, tipo, valor, base_calculo, status) values (?, ?, ?, ?, ?, ?, ?)", [r.get("execucao_id"), r.get("codigo"), r.get("siafi"), r.get("tipo"), _to_float(r.get("valor")), _to_float(r.get("base_calculo")), r.get("status")]))
    for r in pendencias:
        statements.append(("insert into execucao_pendencias (execucao_id, tipo, titulo, descricao, resolvida) values (?, ?, ?, ?, ?)", [r.get("execucao_id"), r.get("tipo"), r.get("titulo"), r.get("descricao"), bool(r.get("resolvida"))]))
    for start in range(0, len(statements), 80):
        executar_pipeline(statements[start:start + 80], timeout=30)
    materializar_vpd_execucoes()
    materializar_siorg_execucoes()
    return {"processos": len(processos), "execucoes": len(execucoes), "empenhos": len(empenhos), "notas": len(notas), "deducoes": len(deducoes), "pendencias": len(pendencias)}
