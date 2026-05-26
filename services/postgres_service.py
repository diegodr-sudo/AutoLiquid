"""Persistencia de processos e execucoes no PostgreSQL."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from typing import Any, Sequence

log = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - dependencia opcional em ambiente local
    psycopg = None
    dict_row = None

_FILA_NOTIFY_CHANNEL = "autoliquid_fila_updates"
_QUEUE_SERVERS_CONFIG_KEY = "fila_servidores_sorteio"
_SERVIDORES_CORES_PADRAO = [
    "#6366f1",
    "#0ea5e9",
    "#10b981",
    "#f97316",
    "#ef4444",
    "#8b5cf6",
    "#14b8a6",
    "#eab308",
]
_VPD_PADRAO_HISTORICO: list[list[str]] = [
    ["339030.01", "DSP 001", "3.3.2.3.X.04.00"],
]
_VPD_CACHE_ROWS: list[list[str]] = []
_VPD_CACHE_TS: float = 0.0
_VPD_CACHE_TTL_SECONDS = 60.0
_SERVIDORES_CONFIG_CACHE_ROWS: list[dict[str, Any]] = []
_SERVIDORES_CONFIG_CACHE_TS = 0.0
_SERVIDORES_CONFIG_CACHE_TTL_SECONDS = 30.0
_PG_LOCAL = threading.local()
_PG_SHARED_CONN: Any | None = None
_PG_SHARED_LOCK = threading.RLock()


class _ReusableConnection:
    """Context manager leve: reutiliza a conexão da thread sem fechá-la a cada consulta."""

    def __init__(self, conn: Any, lock: threading.RLock | None = None, statement_timeout_ms: int | None = None):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_lock", lock)
        object.__setattr__(self, "_statement_timeout_ms", statement_timeout_ms)

    def __enter__(self):
        lock = object.__getattribute__(self, "_lock")
        if lock is not None:
            lock.acquire()
        timeout = object.__getattribute__(self, "_statement_timeout_ms")
        if timeout is not None:
            object.__getattribute__(self, "_conn").execute(f"set statement_timeout = {int(timeout)}")
        return self

    def __exit__(self, exc_type, exc, tb):
        conn = object.__getattribute__(self, "_conn")
        lock = object.__getattribute__(self, "_lock")
        try:
            if getattr(conn, "closed", False):
                return False
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            if getattr(_PG_LOCAL, "conn", None) is conn:
                _PG_LOCAL.conn = None
            raise
        finally:
            if lock is not None:
                lock.release()
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_conn"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_conn"), name, value)


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def postgres_habilitado() -> bool:
    return bool(psycopg is not None and _database_url())


def _get_connection(*, connect_timeout: int = 4, statement_timeout_ms: int = 5000, reuse: bool = True):
    global _PG_SHARED_CONN
    if psycopg is None:
        raise RuntimeError("psycopg nao esta instalado no ambiente.")
    url = _database_url()
    if not url:
        raise RuntimeError("DATABASE_URL nao configurada.")
    if reuse:
        with _PG_SHARED_LOCK:
            if _PG_SHARED_CONN is not None and not getattr(_PG_SHARED_CONN, "closed", False):
                return _ReusableConnection(_PG_SHARED_CONN, _PG_SHARED_LOCK, statement_timeout_ms)
            _PG_SHARED_CONN = None

    cached = getattr(_PG_LOCAL, "conn", None)
    if not reuse and cached is not None and not getattr(cached, "closed", False):
        try:
            cached.execute(f"set statement_timeout = {int(statement_timeout_ms)}")
            return _ReusableConnection(cached)
        except Exception:
            try:
                cached.close()
            except Exception:
                pass
            _PG_LOCAL.conn = None

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            conn = psycopg.connect(
                url,
                row_factory=dict_row,
                connect_timeout=connect_timeout,
                options=f"-c statement_timeout={statement_timeout_ms}",
            )
            if reuse:
                _PG_SHARED_CONN = conn
                return _ReusableConnection(conn, _PG_SHARED_LOCK, statement_timeout_ms)
            _PG_LOCAL.conn = conn
            return _ReusableConnection(conn)
        except Exception as exc:
            last_exc = exc
            if "timeout" not in str(exc).lower() or attempt == 1:
                break
            time.sleep(0.35)
    raise last_exc or RuntimeError("Nao foi possivel conectar ao PostgreSQL.")


def _notificar_fila(cur, tipo: str, **payload: Any) -> None:
    mensagem = json.dumps({"type": tipo, **payload}, ensure_ascii=False)
    cur.execute("select pg_notify(%s, %s)", (_FILA_NOTIFY_CHANNEL, mensagem))


def _servidor_contexto() -> dict[str, str]:
    login = (
        os.getenv("AUTO_LIQUID_USER")
        or os.getenv("USER")
        or os.getenv("USERNAME")
        or "desconhecido"
    ).strip()
    nome = (
        os.getenv("AUTO_LIQUID_NOME")
        or os.getenv("FULLNAME")
        or login
    ).strip()
    setor = (os.getenv("AUTO_LIQUID_SETOR") or socket.gethostname() or "").strip()
    return {
        "login": login,
        "nome": nome,
        "email": (os.getenv("AUTO_LIQUID_EMAIL") or "").strip(),
        "setor": setor,
    }


def _upsert_servidor(cur, contexto: dict[str, str]) -> int:
    cur.execute(
        """
        insert into servidores (nome, login, email, setor, ativo)
        values (%s, %s, %s, %s, true)
        on conflict (login)
        do update set
          nome = excluded.nome,
          email = excluded.email,
          setor = excluded.setor,
          ativo = true
        returning id
        """,
        (
            contexto["nome"],
            contexto["login"],
            contexto["email"] or None,
            contexto["setor"] or None,
        ),
    )
    row = cur.fetchone()
    return int(row["id"])


_SIMPLES_CACHE_DIAS = 30  # Re-verifica após este número de dias


def _upsert_processo(cur, snapshot: dict[str, Any]) -> int:
    documento = snapshot.get("documento", {}) or {}
    numero_processo = str(documento.get("processo") or snapshot.get("id") or "").strip()
    if not numero_processo:
        raise RuntimeError("Nao foi possivel identificar o numero do processo para persistencia.")

    optante = snapshot.get("optante_simples")
    optante_val = bool(optante) if optante is not None else None

    cur.execute(
        """
        insert into processos (
          numero_processo, cnpj, fornecedor, contrato, natureza, tipo_liquidacao, optante_simples
        )
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (numero_processo)
        do update set
          cnpj = excluded.cnpj,
          fornecedor = excluded.fornecedor,
          contrato = excluded.contrato,
          natureza = excluded.natureza,
          tipo_liquidacao = excluded.tipo_liquidacao,
          optante_simples = coalesce(excluded.optante_simples, processos.optante_simples),
          atualizado_em = now()
        returning id
        """,
        (
            numero_processo,
            str(documento.get("cnpj") or "").strip() or None,
            str(documento.get("nomeCredor") or documento.get("fornecedor") or "").strip() or None,
            str(documento.get("contrato") or "").strip() or None,
            str(documento.get("natureza") or "").strip() or None,
            str(documento.get("tipoLiquidacao") or "").strip() or None,
            optante_val,
        ),
    )
    row = cur.fetchone()
    return int(row["id"])


def consultar_simples_por_cnpj(cnpj_limpo: str) -> dict | None:
    """
    Consulta o status Simples Nacional de um CNPJ no histórico de processos.

    Retorna dict com 'razao_social', 'optante_simples' e 'cache_expirado'
    se o CNPJ estiver no banco, ou None se não estiver.

    cache_expirado = True quando o status existe mas foi consultado há mais
    de _SIMPLES_CACHE_DIAS dias — sinal para re-verificar nas APIs externas.
    """
    if not postgres_habilitado():
        return None

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select fornecedor, optante_simples, simples_consultado_em
                    from processos
                    where regexp_replace(cnpj, '[^0-9]', '', 'g') = %s
                    order by
                      (optante_simples is not null) desc,
                      (simples_consultado_em is not null) desc,
                      simples_consultado_em desc
                    limit 1
                    """,
                    (cnpj_limpo,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                consultado_em = row["simples_consultado_em"]
                cache_expirado = True  # padrão: expirado se não soubermos quando foi
                if consultado_em is not None:
                    import datetime
                    delta = datetime.datetime.now(tz=datetime.timezone.utc) - consultado_em.replace(
                        tzinfo=datetime.timezone.utc
                    ) if consultado_em.tzinfo is None else \
                    datetime.datetime.now(tz=datetime.timezone.utc) - consultado_em
                    cache_expirado = delta.days >= _SIMPLES_CACHE_DIAS

                return {
                    "razao_social":    str(row["fornecedor"] or ""),
                    "optante_simples": row["optante_simples"],  # True / False / None
                    "cache_expirado":  cache_expirado,
                }
    except Exception:
        log.exception("Falha ao consultar simples por CNPJ no Supabase")
        return None


def consultar_simples_batch(cnpjs: list[str]) -> dict[str, bool | None]:
    """
    Consulta status Simples Nacional de múltiplos CNPJs em uma única query.
    Retorna dict CNPJ_LIMPO → True/False/None com apenas os CNPJs encontrados no cache.
    CNPJs não encontrados são omitidos do resultado.
    """
    if not postgres_habilitado() or not cnpjs:
        return {}
    cnpjs_limpos = list({
        "".join(c for c in cnpj if c.isdigit())
        for cnpj in cnpjs
        if len("".join(c for c in cnpj if c.isdigit())) == 14
    })
    if not cnpjs_limpos:
        return {}
    try:
        with _get_connection(statement_timeout_ms=8000) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select distinct on (regexp_replace(cnpj, '[^0-9]', '', 'g'))
                      regexp_replace(cnpj, '[^0-9]', '', 'g') as cnpj_limpo,
                      optante_simples
                    from processos
                    where regexp_replace(cnpj, '[^0-9]', '', 'g') = any(%s)
                      and optante_simples is not null
                    order by regexp_replace(cnpj, '[^0-9]', '', 'g'),
                             simples_consultado_em desc nulls last
                    """,
                    (cnpjs_limpos,),
                )
                return {
                    row["cnpj_limpo"]: row["optante_simples"]
                    for row in cur.fetchall()
                }
    except Exception:
        log.exception("Falha ao consultar simples em batch no Supabase")
        return {}


def salvar_simples_cnpj(cnpj_limpo: str, razao_social: str, optante: bool | None) -> None:
    """
    Persiste resultado de consulta Simples no histórico de processos.
    Atualiza todos os processos existentes desse CNPJ com o novo status
    e registra o timestamp da consulta para controle de TTL.
    """
    if not postgres_habilitado() or optante is None:
        return

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update processos
                    set optante_simples        = %s,
                        simples_consultado_em  = now(),
                        fornecedor = coalesce(nullif(trim(%s), ''), fornecedor)
                    where regexp_replace(cnpj, '[^0-9]', '', 'g') = %s
                    """,
                    (optante, razao_social or "", cnpj_limpo),
                )
            conn.commit()
    except Exception:
        log.exception("Falha ao salvar simples por CNPJ no Supabase")


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


def _upsert_execucao(cur, snapshot: dict[str, Any], processo_id: int, servidor_id: int) -> int:
    documento_id = str(snapshot.get("id") or "").strip() or None
    resumo = snapshot.get("resumo", {}) or {}
    pendencias = snapshot.get("pendencias", []) or []
    status = _resolver_status_execucao(snapshot)
    usar_conta_pdf = bool(snapshot.get("usarContaPdf", True))
    conta_banco = str(snapshot.get("contaBanco") or "").strip() or None
    conta_agencia = str(snapshot.get("contaAgencia") or "").strip() or None
    conta_conta = str(snapshot.get("contaConta") or "").strip() or None
    vpd_manual = str(snapshot.get("vpd") or snapshot.get("vpd_manual") or "").strip() or None

    execucao_id = None
    # Consolidamos por processo + servidor para evitar duplicacao por reanexo
    # do mesmo PDF/documento ao longo do dia.
    cur.execute(
        """
        select id
        from execucoes
        where processo_id = %s and servidor_id = %s
        order by data_execucao desc, id desc
        limit 1
        """,
        (processo_id, servidor_id),
    )
    row = cur.fetchone()
    if row:
        execucao_id = int(row["id"])
    elif documento_id:
        cur.execute(
            "select id from execucoes where documento_id = %s order by id desc limit 1",
            (documento_id,),
        )
        row = cur.fetchone()
        if row:
            execucao_id = int(row["id"])

    payload = (
        processo_id,
        servidor_id,
        documento_id,
        float(resumo.get("bruto") or 0),
        float(resumo.get("deducoes") or 0),
        float(resumo.get("liquido") or 0),
        status,
        any(p.get("tipo") == "divergencia" for p in pendencias),
        int(len(snapshot.get("notasFiscais", []) or [])),
        int(len(snapshot.get("deducoes", []) or [])),
        any(p.get("tipo") in {"bloqueio", "divergencia"} for p in pendencias),
        str(snapshot.get("lfNumero") or "").strip() or None,
        str(snapshot.get("ugrNumero") or "").strip() or None,
        str(snapshot.get("vencimentoDocumento") or "").strip() or None,
        usar_conta_pdf,
        conta_banco,
        conta_agencia,
        conta_conta,
        str((snapshot.get("statusGeral", {}) or {}).get("descricao") or "").strip() or None,
        vpd_manual,
        bool(vpd_manual),
    )

    if execucao_id is None:
        cur.execute(
            """
            insert into execucoes (
              processo_id, servidor_id, documento_id, bruto, deducoes, liquido,
              status, possui_divergencia, qtd_notas, qtd_deducoes,
              exige_intervencao_manual, lf_numero, ugr_numero,
              vencimento_documento, usar_conta_pdf, conta_banco,
              conta_agencia, conta_conta, observacoes,
              vpd_manual, vpd_informado_usuario
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            payload,
        )
        row = cur.fetchone()
        return int(row["id"])

    cur.execute(
        """
        update execucoes
        set
          processo_id = %s,
          servidor_id = %s,
          documento_id = %s,
          bruto = %s,
          deducoes = %s,
          liquido = %s,
          status = %s,
          possui_divergencia = %s,
          qtd_notas = %s,
          qtd_deducoes = %s,
          exige_intervencao_manual = %s,
          lf_numero = COALESCE(%s, lf_numero),
          ugr_numero = COALESCE(%s, ugr_numero),
          vencimento_documento = COALESCE(%s, vencimento_documento),
          usar_conta_pdf = %s,
          conta_banco = COALESCE(%s, conta_banco),
          conta_agencia = COALESCE(%s, conta_agencia),
          conta_conta = COALESCE(%s, conta_conta),
          observacoes = COALESCE(%s, observacoes),
          vpd_manual = COALESCE(%s, vpd_manual),
          vpd_informado_usuario = vpd_informado_usuario OR %s,
          data_execucao = now()
        where id = %s
        """,
        (*payload, execucao_id),
    )
    return execucao_id


def _replace_etapas(cur, execucao_id: int, etapas: list[dict[str, Any]]) -> None:
    cur.execute("delete from execucao_etapas where execucao_id = %s", (execucao_id,))
    if not etapas:
        return
    cur.executemany(
        """
        insert into execucao_etapas (execucao_id, etapa_nome, status, mensagem)
        values (%s, %s, %s, %s)
        """,
        [
            (
                execucao_id,
                str(etapa.get("nome") or "").strip(),
                str(etapa.get("status") or "aguardando").strip(),
                None,
            )
            for etapa in etapas
        ],
    )


def _replace_pendencias(cur, execucao_id: int, pendencias: list[dict[str, Any]]) -> None:
    cur.execute("delete from execucao_pendencias where execucao_id = %s", (execucao_id,))
    if not pendencias:
        return
    cur.executemany(
        """
        insert into execucao_pendencias (execucao_id, tipo, titulo, descricao, resolvida)
        values (%s, %s, %s, %s, false)
        """,
        [
            (
                execucao_id,
                str(item.get("tipo") or "").strip(),
                str(item.get("titulo") or "").strip(),
                str(item.get("descricao") or "").strip() or None,
            )
            for item in pendencias
        ],
    )


def _replace_notas(cur, execucao_id: int, notas: list[dict[str, Any]]) -> None:
    cur.execute("delete from notas_fiscais_execucao where execucao_id = %s", (execucao_id,))
    if not notas:
        return
    cur.executemany(
        """
        insert into notas_fiscais_execucao (execucao_id, numero_nota, tipo, emissao, ateste, valor)
        values (%s, %s, %s, %s, %s, %s)
        """,
        [
            (
                execucao_id,
                str(item.get("nota") or "").strip() or None,
                str(item.get("tipo") or "").strip() or None,
                str(item.get("emissao") or "").strip() or None,
                str(item.get("ateste") or "").strip() or None,
                float(item.get("valor") or 0),
            )
            for item in notas
        ],
    )


def _replace_deducoes(cur, execucao_id: int, deducoes: list[dict[str, Any]]) -> None:
    cur.execute("delete from deducoes_execucao where execucao_id = %s", (execucao_id,))
    if not deducoes:
        return
    cur.executemany(
        """
        insert into deducoes_execucao (execucao_id, codigo, siafi, tipo, valor, base_calculo, status)
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                execucao_id,
                str(item.get("codigo") or "").strip() or None,
                str(item.get("siafi") or "").strip() or None,
                str(item.get("tipo") or "").strip() or None,
                float(item.get("valor") or 0),
                float(item.get("baseCalculo") or 0),
                str(item.get("status") or "aguardando").strip(),
            )
            for item in deducoes
        ],
    )


def _salvar_empenhos_json(cur, execucao_id: int, empenhos: list[dict[str, Any]]) -> None:
    """Persiste empenhos como JSONB na coluna empenhos_json de execucoes."""
    payload = json.dumps(
        [
            {
                "numero":   str(item.get("numero") or "").strip(),
                "situacao": str(item.get("situacao") or "").strip(),
                "recurso":  str(item.get("recurso") or "").strip(),
                "natureza": str(item.get("natureza") or "").strip(),
                "valor":    float(item.get("valor") or 0),
                "saldo":    float(item.get("saldo") or 0),
            }
            for item in empenhos
        ],
        ensure_ascii=False,
    )
    cur.execute(
        "update execucoes set empenhos_json = %s::jsonb where id = %s",
        (payload, execucao_id),
    )


def _replace_empenhos_processo(cur, processo_id: int, empenhos: list[dict[str, Any]]) -> None:
    """Substitui os empenhos do processo (delete + insert)."""
    cur.execute("delete from empenhos where processo_id = %s", (processo_id,))
    if not empenhos:
        return
    cur.executemany(
        """
        insert into empenhos (processo_id, numero, situacao, recurso, natureza, valor, saldo)
        values (%s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                processo_id,
                str(item.get("numero") or "").strip() or None,
                str(item.get("situacao") or "").strip() or None,
                str(item.get("recurso") or "").strip() or None,
                str(item.get("natureza") or "").strip() or None,
                float(item.get("valor") or 0),
                float(item.get("saldo") or 0),
            )
            for item in empenhos
        ],
    )


def obter_tabela_operacional(chave: str) -> list[dict[str, Any]] | None:
    if not postgres_habilitado():
        return None

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select dados
                from tabelas_operacionais
                where chave = %s
                """,
                (str(chave or "").strip(),),
            )
            row = cur.fetchone()
            if not row:
                return None

            dados = row.get("dados")
            if isinstance(dados, str):
                try:
                    dados = json.loads(dados)
                except Exception:
                    dados = []
            return dados if isinstance(dados, list) else []


def obter_regras_operacionais() -> list[dict[str, Any]] | None:
    if not postgres_habilitado():
        return None

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select chave, dados, ativo
                from regras_operacionais
                order by chave
                """
            )
            rows = cur.fetchall()

    regras: list[dict[str, Any]] = []
    for row in rows:
        dados = row.get("dados")
        if isinstance(dados, str):
            try:
                dados = json.loads(dados)
            except Exception:
                dados = {}
        if not isinstance(dados, dict):
            dados = {}
        regra = dict(dados)
        regra["id"] = str(regra.get("id") or row.get("chave") or "").strip()
        regra["ativa"] = bool(row.get("ativo"))
        if regra["id"]:
            regras.append(regra)
    return regras


def salvar_tabela_operacional(chave: str, rows: list[dict[str, Any]]) -> None:
    if not postgres_habilitado():
        return

    chave_limpa = str(chave or "").strip()
    payload = json.dumps(rows or [], ensure_ascii=False)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into tabelas_operacionais (chave, dados, atualizado_em)
                values (%s, %s::jsonb, now())
                on conflict (chave)
                do update set
                  dados = excluded.dados,
                  atualizado_em = now()
                """,
                (chave_limpa, payload),
            )
        conn.commit()
    if chave_limpa == "vpd":
        global _VPD_CACHE_ROWS, _VPD_CACHE_TS
        _VPD_CACHE_ROWS = []
        _VPD_CACHE_TS = 0.0


def obter_servidores_sorteio() -> list[dict[str, Any]] | None:
    config = obter_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY) or []
    modos: dict[str, str] = {}
    ids: dict[str, str] = {}
    if isinstance(config, list):
        for item in config:
            if not isinstance(item, dict):
                continue
            nome = str(item.get("nome") or "").strip()
            if not nome:
                continue
            chave = nome.casefold()
            modos[chave] = str(item.get("modo") or "fora").strip() or "fora"
            ids[chave] = str(item.get("id") or f"server-{nome}").strip()

    servidores = listar_servidores_config(config if isinstance(config, list) else [], incluir_servidores_execucao=False)
    if not servidores:
        return config if isinstance(config, list) else []

    return [
        {
            "id": ids.get(str(servidor["nome"]).casefold(), f"server-{servidor['nome']}"),
            "nome": servidor["nome"],
            "modo": modos.get(str(servidor["nome"]).casefold(), "fora"),
        }
        for servidor in servidores
        if str(servidor.get("nome") or "").strip()
    ]


def salvar_servidores_sorteio(rows: list[dict[str, Any]]) -> None:
    if not postgres_habilitado():
        return

    payload = json.dumps(rows or [], ensure_ascii=False)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into tabelas_operacionais (chave, dados, atualizado_em)
                values (%s, %s::jsonb, now())
                on conflict (chave)
                do update set
                  dados = excluded.dados,
                  atualizado_em = now()
                """,
                (_QUEUE_SERVERS_CONFIG_KEY, payload),
            )
            _notificar_fila(cur, "servidores-sorteio-atualizados")
        conn.commit()


def _nome_servidor_simples(nome: str) -> str:
    partes = str(nome or "").strip().split()
    return partes[0] if partes else ""


def _normalizar_servidor_identificado(row: dict[str, Any], indice: int = 0) -> dict[str, str]:
    nome_completo = str(row.get("nome_completo") or row.get("nome") or "").strip()
    nome_simples = str(row.get("nome_simples") or _nome_servidor_simples(nome_completo)).strip()
    cor = str(row.get("cor") or _SERVIDORES_CORES_PADRAO[indice % len(_SERVIDORES_CORES_PADRAO)]).strip()
    return {
        "nome": nome_simples or nome_completo,
        "nomeCompleto": nome_completo or nome_simples,
        "cor": cor,
    }


def listar_servidores_config(
    candidatos_sorteio: list[dict[str, Any]] | None = None,
    *,
    incluir_servidores_execucao: bool = True,
) -> list[dict[str, Any]]:
    """Lista o cadastro unico de servidores usado por fila, sorteio e ausencias."""
    global _SERVIDORES_CONFIG_CACHE_ROWS, _SERVIDORES_CONFIG_CACHE_TS
    if not postgres_habilitado():
        return []
    if (
        candidatos_sorteio is None
        and incluir_servidores_execucao
        and _SERVIDORES_CONFIG_CACHE_ROWS
        and time.monotonic() - _SERVIDORES_CONFIG_CACHE_TS < _SERVIDORES_CONFIG_CACHE_TTL_SECONDS
    ):
        return [dict(row) for row in _SERVIDORES_CONFIG_CACHE_ROWS]

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select nome_completo, nome as nome_simples, cor, ordem, criado_em
                from servidores_config
                order by coalesce(ordem, 999999), criado_em nulls last, nome
                """
            )
            rows = [_normalizar_servidor_identificado(r, i) for i, r in enumerate(cur.fetchall())]

    existentes = {str(r["nome"]).casefold() for r in rows if r.get("nome")}
    candidatos: list[str] = []
    try:
        sorteio = candidatos_sorteio
        if sorteio is None:
            sorteio = obter_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY) or []
        for item in sorteio:
            if isinstance(item, dict):
                nome = str(item.get("nome") or "").strip()
                if nome and nome.casefold() not in existentes:
                    candidatos.append(nome)
                    existentes.add(nome.casefold())
    except Exception:
        pass

    for nome in candidatos:
        try:
            salvar_servidor_config(nome, _SERVIDORES_CORES_PADRAO[len(rows) % len(_SERVIDORES_CORES_PADRAO)])
            rows.append(
                _normalizar_servidor_identificado(
                    {"nome_completo": nome, "nome_simples": _nome_servidor_simples(nome)},
                    len(rows),
                )
            )
        except Exception:
            log.warning("Falha ao migrar servidor '%s' para cadastro unico.", nome, exc_info=True)

    if candidatos_sorteio is None and incluir_servidores_execucao:
        _SERVIDORES_CONFIG_CACHE_ROWS = [dict(row) for row in rows]
        _SERVIDORES_CONFIG_CACHE_TS = time.monotonic()
    return rows


def salvar_servidor_config(nome: str, cor: str) -> None:
    """Upsert no cadastro unico de servidores identificados."""
    global _SERVIDORES_CONFIG_CACHE_ROWS, _SERVIDORES_CONFIG_CACHE_TS
    if not postgres_habilitado():
        raise RuntimeError("Banco de dados não configurado.")

    nome_completo = str(nome or "").strip()
    if not nome_completo:
        raise ValueError("Nome do servidor é obrigatório.")
    nome_simples = _nome_servidor_simples(nome_completo)
    cor_limpa = str(cor or "#6366f1").strip() or "#6366f1"

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update servidores_config
                   set nome_completo = %s,
                       nome = %s,
                       cor = %s,
                       criado_em = coalesce(criado_em, now())
                 where lower(coalesce(nome, '')) = lower(%s)
                    or lower(coalesce(nome_completo, '')) = lower(%s)
                """,
                (nome_completo, nome_simples, cor_limpa, nome_simples, nome_completo),
            )
            if (cur.rowcount or 0) == 0:
                cur.execute(
                    """
                    insert into servidores_config
                        (nome_completo, nome, cor, ordem, criado_em)
                    values (%s, %s, %s, 0, now())
                    """,
                    (nome_completo, nome_simples, cor_limpa),
                )
            conn.commit()
    _SERVIDORES_CONFIG_CACHE_ROWS = []
    _SERVIDORES_CONFIG_CACHE_TS = 0.0


def deletar_servidor_config(nome: str) -> None:
    global _SERVIDORES_CONFIG_CACHE_ROWS, _SERVIDORES_CONFIG_CACHE_TS
    if not postgres_habilitado():
        raise RuntimeError("Banco de dados não configurado.")

    nome_limpo = str(nome or "").strip()
    nome_simples = _nome_servidor_simples(nome_limpo)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                delete from servidores_config
                 where lower(coalesce(nome, '')) = lower(%s)
                    or lower(coalesce(nome_completo, '')) = lower(%s)
                """,
                (nome_simples, nome_limpo),
            )
            config = obter_tabela_operacional(_QUEUE_SERVERS_CONFIG_KEY) or []
            if isinstance(config, list):
                filtrado = [
                    item for item in config
                    if not (
                        isinstance(item, dict)
                        and str(item.get("nome") or "").strip().casefold()
                        in {nome_limpo.casefold(), nome_simples.casefold()}
                    )
                ]
                cur.execute(
                    """
                    insert into tabelas_operacionais (chave, dados, atualizado_em)
                    values (%s, %s::jsonb, now())
                    on conflict (chave)
                    do update set dados = excluded.dados, atualizado_em = now()
                    """,
                    (_QUEUE_SERVERS_CONFIG_KEY, json.dumps(filtrado, ensure_ascii=False)),
                )
            _notificar_fila(cur, "servidores-sorteio-atualizados")
            conn.commit()
    _SERVIDORES_CONFIG_CACHE_ROWS = []
    _SERVIDORES_CONFIG_CACHE_TS = 0.0


def salvar_regras_operacionais(rows: list[dict[str, Any]]) -> None:
    if not postgres_habilitado():
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            chaves_validas: list[str] = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                chave = str(row.get("id") or "").strip()
                if not chave:
                    continue
                payload = dict(row)
                payload["id"] = chave
                ativo = bool(payload.get("ativa", True))
                chaves_validas.append(chave)
                cur.execute(
                    """
                    insert into regras_operacionais (chave, dados, ativo, atualizado_em)
                    values (%s, %s::jsonb, %s, now())
                    on conflict (chave)
                    do update set
                      dados = excluded.dados,
                      ativo = excluded.ativo,
                      atualizado_em = now()
                    """,
                    (chave, json.dumps(payload, ensure_ascii=False), ativo),
                )

            if chaves_validas:
                cur.execute(
                    "delete from regras_operacionais where not (chave = any(%s))",
                    (chaves_validas,),
                )
        conn.commit()


def _fila_row_key(row: dict[str, Any]) -> str:
    numero_processo = str(row.get("Número Processo") or row.get("numero_processo") or "").strip()
    sol_pagamento = str(row.get("Sol. Pagamento") or row.get("sol_pagamento") or "").strip()
    protocolo = str(row.get("Protocolo") or row.get("protocolo") or "").strip()
    cpf_cnpj = str(row.get("CPF/CNPJ") or row.get("cpf_cnpj") or "").strip()
    base = numero_processo or sol_pagamento or protocolo or cpf_cnpj
    if not base:
        base = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return base


def _mesclar_override_fila(
    row: dict[str, Any],
    responsavel_manual: str | None,
    responsavel_manual_por: str | None = None,
    responsavel_manual_em: str | None = None,
    alertas: list[dict[str, Any]] | None = None,
    concluido: bool = False,
    concluido_por: str | None = None,
    concluido_em: str | None = None,
) -> dict[str, Any]:
    merged = dict(row)
    responsavel = str(responsavel_manual or "").strip()
    autor = str(responsavel_manual_por or "").strip()
    alterado_em = str(responsavel_manual_em or "").strip()
    if responsavel:
        merged["__responsavel_manual"] = responsavel
        merged["__responsavel_alterado"] = "1"
        merged["__responsavel_alterado_por"] = autor
        merged["__responsavel_alterado_em"] = alterado_em
    else:
        merged["__responsavel_manual"] = ""
        merged["__responsavel_alterado"] = ""
        merged["__responsavel_alterado_por"] = ""
        merged["__responsavel_alterado_em"] = ""
    merged["__alertas_json"] = json.dumps(alertas or [], ensure_ascii=False)
    merged["__concluido"] = "1" if concluido else ""
    merged["__concluido_por"] = str(concluido_por or "").strip()
    merged["__concluido_em"] = str(concluido_em or "").strip()
    return merged


def _carregar_alertas_fila_por_chave(cur, chaves: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not chaves:
        return {}

    cur.execute(
        """
        select chave, id, mensagem, autor, criado_em
        from fila_processos_alertas
        where ativo = true
          and chave = any(%s)
        order by criado_em desc, id desc
        """,
        (chaves,),
    )
    resultado: dict[str, list[dict[str, Any]]] = {}
    for row in cur.fetchall():
        chave = str(row.get("chave") or "")
        resultado.setdefault(chave, []).append(
            {
                "id": int(row.get("id")),
                "mensagem": str(row.get("mensagem") or "").strip(),
                "autor": str(row.get("autor") or "").strip(),
                "criadoEm": row.get("criado_em").isoformat() if row.get("criado_em") else None,
            }
        )
    return resultado


def salvar_snapshot_fila_processos(
    rows: list[dict[str, Any]],
    *,
    updated_at: str | None = None,
    origem: str = "solar-headless",
) -> list[dict[str, Any]]:
    if not postgres_habilitado():
        return rows

    snapshot_rows = rows or []
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select chave from fila_processos_atual where presente = true")
            chaves_presentes_antes = {str(row.get("chave") or "") for row in cur.fetchall()}
            cur.execute("update fila_processos_atual set presente = false")

            for row in snapshot_rows:
                chave = _fila_row_key(row)
                resetar_conclusao = chave not in chaves_presentes_antes
                numero_processo = str(row.get("Número Processo") or "").strip() or None
                sol_pagamento = str(row.get("Sol. Pagamento") or "").strip() or None
                protocolo = str(row.get("Protocolo") or "").strip() or None
                competencia = str(row.get("Competência") or "").strip() or None
                payload = json.dumps(row, ensure_ascii=False)

                cur.execute(
                    """
                    insert into fila_processos_atual (
                      chave, numero_processo, sol_pagamento, protocolo,
                      competencia, dados, presente, atualizado_em
                    )
                    values (%s, %s, %s, %s, %s, %s::jsonb, true, now())
                    on conflict (chave)
                    do update set
                      numero_processo = excluded.numero_processo,
                      sol_pagamento = excluded.sol_pagamento,
                      protocolo = excluded.protocolo,
                      competencia = excluded.competencia,
                      dados = excluded.dados,
                      concluido = case when %s then false else fila_processos_atual.concluido end,
                      concluido_por = case when %s then null else fila_processos_atual.concluido_por end,
                      concluido_em = case when %s then null else fila_processos_atual.concluido_em end,
                      presente = true,
                      atualizado_em = now()
                    """,
                    (
                        chave,
                        numero_processo,
                        sol_pagamento,
                        protocolo,
                        competencia,
                        payload,
                        resetar_conclusao,
                        resetar_conclusao,
                        resetar_conclusao,
                    ),
                )
                cur.execute(
                    """
                    insert into fila_processos_historico (
                      chave, numero_processo, sol_pagamento, protocolo,
                      competencia, origem, dados, registrado_em
                    )
                    values (%s, %s, %s, %s, %s, %s, %s::jsonb, coalesce(%s::timestamptz, now()))
                    on conflict (chave) do update set
                      numero_processo = excluded.numero_processo,
                      sol_pagamento = excluded.sol_pagamento,
                      protocolo = excluded.protocolo,
                      competencia = excluded.competencia,
                      origem = excluded.origem,
                      dados = excluded.dados
                    """,
                    (chave, numero_processo, sol_pagamento, protocolo, competencia, origem, payload, updated_at),
                )

            cur.execute(
                """
                select chave, dados, responsavel_manual, responsavel_manual_por, responsavel_manual_em,
                       concluido, concluido_por, concluido_em
                from fila_processos_atual
                where presente = true
                order by atualizado_em desc, chave
                """
            )
            fetched_rows = cur.fetchall()
            alertas_por_chave = _carregar_alertas_fila_por_chave(
                cur,
                [str(row.get("chave") or "") for row in fetched_rows],
            )
            merged_rows = [
                _mesclar_override_fila(
                    dict(row.get("dados") or {}),
                    str(row.get("responsavel_manual") or "").strip() or None,
                    str(row.get("responsavel_manual_por") or "").strip() or None,
                    row.get("responsavel_manual_em").isoformat() if row.get("responsavel_manual_em") else None,
                    alertas_por_chave.get(str(row.get("chave") or ""), []),
                    bool(row.get("concluido")),
                    str(row.get("concluido_por") or "").strip() or None,
                    row.get("concluido_em").isoformat() if row.get("concluido_em") else None,
                )
                for row in fetched_rows
            ]
            _notificar_fila(
                cur,
                "fila-atualizada",
                updatedAt=updated_at,
                total=len(snapshot_rows),
                origem=origem,
            )
        conn.commit()
    return merged_rows


def obter_fila_processos_snapshot_atual() -> dict[str, Any]:
    if not postgres_habilitado():
        return {"rows": [], "updatedAt": None}

    with _get_connection(connect_timeout=1, statement_timeout_ms=1500) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select chave, dados, responsavel_manual, responsavel_manual_por, responsavel_manual_em,
                       concluido, concluido_por, concluido_em, atualizado_em
                from fila_processos_atual
                where presente = true
                order by competencia asc nulls last, numero_processo asc nulls last, chave asc
                """
            )
            rows = cur.fetchall()
            alertas_por_chave = _carregar_alertas_fila_por_chave(
                cur,
                [str(row.get("chave") or "") for row in rows],
            )
    merged_rows = [
        _mesclar_override_fila(
            dict(row.get("dados") or {}),
            str(row.get("responsavel_manual") or "").strip() or None,
            str(row.get("responsavel_manual_por") or "").strip() or None,
            row.get("responsavel_manual_em").isoformat() if row.get("responsavel_manual_em") else None,
            alertas_por_chave.get(str(row.get("chave") or ""), []),
            bool(row.get("concluido")),
            str(row.get("concluido_por") or "").strip() or None,
            row.get("concluido_em").isoformat() if row.get("concluido_em") else None,
        )
        for row in rows
    ]
    updated_at_values = [row.get("atualizado_em") for row in rows if row.get("atualizado_em")]
    latest_updated_at = max(updated_at_values).isoformat() if updated_at_values else None
    return {
        "rows": merged_rows,
        "updatedAt": latest_updated_at,
    }


def obter_fila_processos_atual() -> list[dict[str, Any]]:
    return obter_fila_processos_snapshot_atual()["rows"]


def obter_setores_fila_historico(limite: int = 300) -> list[str]:
    if not postgres_habilitado():
        return []

    with _get_connection(connect_timeout=2, statement_timeout_ms=3000) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select setor
                from (
                  select distinct
                    nullif(trim(coalesce(
                      dados ->> 'Setor Origem',
                      dados ->> 'setorOrigem',
                      dados ->> 'setor_origem',
                      ''
                    )), '') as setor
                  from fila_processos_historico
                ) setores
                where setor is not null
                order by lower(setor), setor
                limit %s
                """,
                (max(1, min(int(limite or 300), 1000)),),
            )
            return [
                str(row.get("setor") or "").strip()
                for row in cur.fetchall()
                if str(row.get("setor") or "").strip()
            ]


def obter_token_tempo_real_fila() -> str:
    if not postgres_habilitado():
        return "postgres:disabled"

    with _get_connection(connect_timeout=1, statement_timeout_ms=1500) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select count(*) as total,
                       coalesce(max(atualizado_em)::text, '') as updated_at
                from fila_processos_atual
                where presente = true
                """
            )
            fila = cur.fetchone() or {}
            cur.execute(
                """
                select count(*) as total,
                       coalesce(max(id), 0) as max_id
                from fila_processos_alertas
                where ativo = true
                """
            )
            alertas = cur.fetchone() or {}
            cur.execute(
                """
                select coalesce(atualizado_em::text, '') as updated_at
                from regras_operacionais
                where chave = %s
                """,
                (_QUEUE_SERVERS_CONFIG_KEY,),
            )
            servidores = cur.fetchone() or {}
    return "|".join([
        "postgres",
        str(fila.get("total") or 0),
        str(fila.get("updated_at") or ""),
        str(alertas.get("total") or 0),
        str(alertas.get("max_id") or 0),
        str(servidores.get("updated_at") or ""),
    ])


def salvar_responsavel_fila(
    *,
    numero_processo: str,
    sol_pagamento: str,
    responsavel: str,
) -> str | None:
    if not postgres_habilitado():
        return None

    row_key = _fila_row_key({
        "Número Processo": numero_processo,
        "Sol. Pagamento": sol_pagamento,
    })
    contexto = _servidor_contexto()
    responsavel_manual_em = None
    with _get_connection() as conn:
        with conn.cursor() as cur:
            servidor_id = _upsert_servidor(cur, contexto)
            cur.execute(
                """
                insert into fila_processos_atual (
                  chave, numero_processo, sol_pagamento, dados, responsavel_manual, responsavel_manual_por, responsavel_manual_em, presente, atualizado_em
                )
                values (%s, %s, %s, '{}'::jsonb, %s, %s, case when nullif(%s, '') is null then null else now() end, true, now())
                on conflict (chave)
                do update set
                  numero_processo = excluded.numero_processo,
                  sol_pagamento = excluded.sol_pagamento,
                  responsavel_manual = excluded.responsavel_manual,
                  responsavel_manual_por = excluded.responsavel_manual_por,
                  responsavel_manual_em = excluded.responsavel_manual_em,
                  atualizado_em = now()
                returning responsavel_manual_em
                """,
                (
                    row_key,
                    numero_processo.strip() or None,
                    sol_pagamento.strip() or None,
                    responsavel.strip() or None,
                    contexto["nome"] or contexto["login"] or None,
                    responsavel.strip(),
                ),
            )
            saved_row = cur.fetchone() or {}
            responsavel_manual_em = saved_row.get("responsavel_manual_em")
            cur.execute(
                """
                insert into fila_processos_edicoes (
                  chave, numero_processo, sol_pagamento, responsavel, servidor_id, responsavel_por
                )
                values (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row_key,
                    numero_processo.strip() or None,
                    sol_pagamento.strip() or None,
                    responsavel.strip() or None,
                    servidor_id,
                    contexto["nome"] or contexto["login"] or None,
                ),
            )
            cur.execute(
                """
                update fila_processos_historico
                set responsavel_manual = %s
                where chave = %s
                """,
                (
                    responsavel.strip() or None,
                    row_key,
                ),
            )
            _notificar_fila(
                cur,
                "responsavel-alterado",
                rowKey=row_key,
                numeroProcesso=numero_processo.strip() or None,
                solPagamento=sol_pagamento.strip() or None,
                responsavel=responsavel.strip() or None,
                alteradoPor=contexto["nome"] or contexto["login"] or None,
                alteradoEm=responsavel_manual_em.isoformat() if responsavel_manual_em else None,
            )
        conn.commit()
    return responsavel_manual_em.isoformat() if responsavel_manual_em else None


def salvar_conclusao_fila(
    *,
    numero_processo: str,
    sol_pagamento: str,
    concluido: bool,
) -> dict[str, Any]:
    if not postgres_habilitado():
        return {"concluido": concluido, "concluidoPor": "", "concluidoEm": None}

    row_key = _fila_row_key({
        "Número Processo": numero_processo,
        "Sol. Pagamento": sol_pagamento,
    })
    contexto = _servidor_contexto()
    autor = contexto["nome"] or contexto["login"] or ""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into fila_processos_atual (
                  chave, numero_processo, sol_pagamento, dados, concluido, concluido_por, concluido_em, presente, atualizado_em
                )
                values (%s, %s, %s, '{}'::jsonb, %s, case when %s then %s else null end, case when %s then now() else null end, true, now())
                on conflict (chave)
                do update set
                  numero_processo = excluded.numero_processo,
                  sol_pagamento = excluded.sol_pagamento,
                  concluido = excluded.concluido,
                  concluido_por = excluded.concluido_por,
                  concluido_em = excluded.concluido_em,
                  atualizado_em = now()
                returning concluido, concluido_por, concluido_em
                """,
                (
                    row_key,
                    numero_processo.strip() or None,
                    sol_pagamento.strip() or None,
                    concluido,
                    concluido,
                    autor or None,
                    concluido,
                ),
            )
            row = cur.fetchone() or {}
            _notificar_fila(
                cur,
                "conclusao-alterada",
                rowKey=row_key,
                numeroProcesso=numero_processo.strip() or None,
                solPagamento=sol_pagamento.strip() or None,
                concluido=bool(row.get("concluido")),
                concluidoPor=str(row.get("concluido_por") or ""),
                concluidoEm=row.get("concluido_em").isoformat() if row.get("concluido_em") else None,
            )
        conn.commit()
    return {
        "concluido": bool(row.get("concluido")),
        "concluidoPor": str(row.get("concluido_por") or ""),
        "concluidoEm": row.get("concluido_em").isoformat() if row.get("concluido_em") else None,
    }


def salvar_alerta_fila(
    *,
    numero_processo: str,
    sol_pagamento: str,
    mensagem: str,
) -> dict[str, Any] | None:
    if not postgres_habilitado():
        return None

    texto = str(mensagem or "").strip()
    if not texto:
        raise ValueError("Informe uma mensagem.")

    row_key = _fila_row_key({
        "Número Processo": numero_processo,
        "Sol. Pagamento": sol_pagamento,
    })
    contexto = _servidor_contexto()
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into fila_processos_alertas (
                  chave, numero_processo, sol_pagamento, mensagem, servidor_id, autor, ativo, criado_em
                )
                values (%s, %s, %s, %s, %s, %s, true, now())
                returning id, criado_em
                """,
                (
                    row_key,
                    numero_processo.strip() or None,
                    sol_pagamento.strip() or None,
                    texto,
                    None,
                    contexto["nome"] or contexto["login"] or None,
                ),
            )
            created = cur.fetchone() or {}
            alerta = {
                "id": int(created.get("id")),
                "mensagem": texto,
                "autor": contexto["nome"] or contexto["login"] or "",
                "criadoEm": created.get("criado_em").isoformat() if created.get("criado_em") else None,
            }
            _notificar_fila(
                cur,
                "alerta-adicionado",
                rowKey=row_key,
                numeroProcesso=numero_processo.strip() or None,
                solPagamento=sol_pagamento.strip() or None,
                alerta=alerta,
            )
        conn.commit()
    return alerta


def remover_alerta_fila(*, alerta_id: int) -> None:
    if not postgres_habilitado():
        return

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update fila_processos_alertas
                set ativo = false
                where id = %s
                """,
                (alerta_id,),
            )
            _notificar_fila(cur, "alerta-removido", alertaId=alerta_id)
        conn.commit()


def persistir_documento(snapshot: dict[str, Any]) -> int | None:
    """Salva ou atualiza o snapshot atual do documento no PostgreSQL."""
    if not postgres_habilitado():
        return None

    with _get_connection() as conn:
        with conn.cursor() as cur:
            servidor_id = _upsert_servidor(cur, _servidor_contexto())
            processo_id = _upsert_processo(cur, snapshot)
            execucao_id = _upsert_execucao(cur, snapshot, processo_id, servidor_id)
            _replace_etapas(cur, execucao_id, snapshot.get("etapas", []) or [])
            _replace_pendencias(cur, execucao_id, snapshot.get("pendencias", []) or [])
            _replace_notas(cur, execucao_id, snapshot.get("notasFiscais", []) or [])
            _replace_deducoes(cur, execucao_id, snapshot.get("deducoes", []) or [])
            empenhos_lista = snapshot.get("empenhos", []) or []
            _salvar_empenhos_json(cur, execucao_id, empenhos_lista)
            _replace_empenhos_processo(cur, processo_id, empenhos_lista)
        conn.commit()
        return execucao_id


def persistir_documento_com_log(snapshot: dict[str, Any]) -> int | None:
    try:
        return persistir_documento(snapshot)
    except Exception:
        log.exception("Falha ao persistir documento no PostgreSQL")
        return None


def _normalizar_situacao_vpd_historico(situacao: str) -> str:
    import re

    return re.sub(r"[^A-Z0-9/]+", "", str(situacao or "").upper())


def _situacao_vpd_compativel_historico(situacao_linha: str, situacao_alvo: str) -> bool:
    import re

    linha = _normalizar_situacao_vpd_historico(situacao_linha)
    alvo = _normalizar_situacao_vpd_historico(situacao_alvo)
    if not alvo:
        return True
    if not linha:
        return False
    if linha == alvo or alvo in linha or linha in alvo:
        return True
    codigos_linha = set(re.findall(r"[A-Z]{2,4}\d{3}", linha))
    codigos_alvo = set(re.findall(r"[A-Z]{2,4}\d{3}", alvo))
    if codigos_linha and codigos_alvo:
        return bool(codigos_linha & codigos_alvo)
    return False


def _obter_vpd_lista_historico() -> list[list[str]]:
    """Carrega a tabela VPD uma vez por janela curta para não consultar Supabase por linha."""
    global _VPD_CACHE_ROWS, _VPD_CACHE_TS

    agora = time.monotonic()
    if _VPD_CACHE_ROWS and (agora - _VPD_CACHE_TS) < _VPD_CACHE_TTL_SECONDS:
        return _VPD_CACHE_ROWS

    vpd_lista: list[list[str]] = []
    try:
        rows = obter_tabela_operacional("vpd")
        if rows is not None:
            vpd_lista = [
                [
                    str((row or {}).get("natureza", "")).strip(),
                    str((row or {}).get("situacaoDsp", "")).strip(),
                    str((row or {}).get("vpd", "")).strip(),
                ]
                for row in rows
            ]
    except Exception as exc:
        log.warning("Histórico VPD: falha ao ler tabela remota: %s", exc)

    if not vpd_lista:
        try:
            from services.config_service import carregar_tabelas_config

            cfg = carregar_tabelas_config()
            vpd_lista = [
                [str(item[0]).strip(), str(item[1]).strip(), str(item[2]).strip()]
                for item in (cfg.get("vpd_lista", []) or [])
                if isinstance(item, list) and len(item) >= 3
            ]
        except Exception as exc:
            log.warning("Histórico VPD: falha ao ler tabelas_config.json: %s", exc)

    if not vpd_lista:
        vpd_lista = _VPD_PADRAO_HISTORICO

    _VPD_CACHE_ROWS = vpd_lista
    _VPD_CACHE_TS = agora
    return _VPD_CACHE_ROWS


def _buscar_vpd_historico(natureza: str, situacao: str = "") -> str:
    nat = str(natureza or "").strip()
    if not nat:
        return ""

    vpd_lista = _obter_vpd_lista_historico()

    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip()
        row_situacao = str(row[1]).strip() if len(row) > 1 else ""
        row_vpd = str(row[2]).strip()
        if row_nat.upper() == nat.upper() and _situacao_vpd_compativel_historico(row_situacao, situacao):
            return row_vpd

    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip()
        row_vpd = str(row[2]).strip()
        if row_nat.upper() == nat.upper():
            return row_vpd

    nat_base = nat.split(".")[0]
    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip().split(".")[0]
        row_situacao = str(row[1]).strip() if len(row) > 1 else ""
        if row_nat == nat_base and _situacao_vpd_compativel_historico(row_situacao, situacao):
            return str(row[2]).strip()

    for row in vpd_lista:
        if len(row) < 3:
            continue
        row_nat = str(row[0]).strip().split(".")[0]
        if row_nat == nat_base:
            return str(row[2]).strip()

    return ""


def _resolver_vpd_historico(
    natureza: Any,
    situacao: Any,
    vpd_manual: Any,
) -> tuple[str, bool]:
    """Resolve VPD para exibição: tabela DE/PARA primeiro, manual só como fallback."""
    natureza_txt = str(natureza or "").strip()
    situacao_txt = str(situacao or "").strip()
    manual_txt = str(vpd_manual or "").strip()
    vpd_tabela = ""
    if natureza_txt:
        try:
            vpd_tabela = str(_buscar_vpd_historico(natureza_txt, situacao_txt) or "").strip()
        except Exception:
            log.exception("Falha ao resolver VPD do histórico pela tabela")
            vpd_tabela = ""
    vpd_tabela_norm = vpd_tabela.upper().replace("Ç", "C")
    vpd_de_acordo_nf = "DE ACORDO" in vpd_tabela_norm and "NF" in vpd_tabela_norm
    if vpd_tabela and not vpd_de_acordo_nf:
        return vpd_tabela, False
    if manual_txt:
        return manual_txt, True
    if vpd_tabela:
        return vpd_tabela, False
    return "", False


def _apenas_digitos(texto: Any) -> str:
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def _resolver_siorg_por_ugr_historico(ugr: Any) -> str:
    ugr_digitos = _apenas_digitos(ugr)
    if not ugr_digitos:
        return ""

    rows: list[Any] = []
    try:
        rows = obter_tabela_operacional("uorg") or []
    except Exception:
        rows = []

    if not rows:
        try:
            from services.config_service import carregar_tabelas_config

            rows = carregar_tabelas_config().get("uorg_lista", []) or []
        except Exception:
            rows = []

    for row in rows:
        if isinstance(row, dict):
            row_ugr = row.get("ugr")
            row_siorg = row.get("uorg") or row.get("siorg")
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            row_ugr = row[0]
            row_siorg = row[1]
        else:
            continue
        if _apenas_digitos(row_ugr) == ugr_digitos:
            return str(row_siorg or "").strip()
    return ""


def _enriquecer_empenhos_historico(empenhos: list[dict], ugr: Any) -> list[dict]:
    ugr_txt = str(ugr or "").strip()
    siorg = _resolver_siorg_por_ugr_historico(ugr_txt)
    return [
        {
            **dict(emp or {}),
            "ugrNumero": str((emp or {}).get("ugrNumero") or ugr_txt),
            "siorgNumero": str((emp or {}).get("siorgNumero") or siorg),
        }
        for emp in (empenhos or [])
    ]


def buscar_historico_por_cnpj(
    cnpj_limpo: str,
    contrato_filtro: str | Sequence[str] | None = None,
    limite: int = 40,
) -> list[dict[str, Any]]:
    """
    Busca histórico de processos por CNPJ (+ contrato opcional).

    Retorna lista de processos ordenados pela execução mais recente,
    cada um contendo suas execuções com NFs, deduções e pendências.
    """
    if not postgres_habilitado():
        return []

    cnpj_digitos = "".join(c for c in str(cnpj_limpo or "") if c.isdigit())
    cnpj_candidatos = [cnpj_digitos]
    if len(cnpj_digitos) == 14:
        cnpj_candidatos.append(
            f"{cnpj_digitos[:2]}.{cnpj_digitos[2:5]}.{cnpj_digitos[5:8]}/{cnpj_digitos[8:12]}-{cnpj_digitos[12:]}"
        )
    cnpj_candidatos = list(dict.fromkeys(item for item in cnpj_candidatos if item))
    if not cnpj_candidatos:
        return []

    with _get_connection() as conn:
        with conn.cursor() as cur:
            # ── 1. Processos + execuções ──────────────────────────────────
            params_base: list[Any] = [cnpj_candidatos]
            where_contrato = ""
            if isinstance(contrato_filtro, str):
                contratos_filtro = [contrato_filtro.strip()] if contrato_filtro.strip() else []
            else:
                contratos_filtro = [
                    str(item).strip()
                    for item in (contrato_filtro or [])
                    if str(item).strip()
                ]
            contratos_filtro = list(dict.fromkeys(contratos_filtro))
            if contratos_filtro:
                placeholders = " OR ".join(["upper(p.contrato) LIKE upper(%s)"] * len(contratos_filtro))
                where_contrato = f"AND ({placeholders})"
                params_base.extend([f"%{item}%" for item in contratos_filtro])

            cur.execute(
                f"""
                SELECT
                  p.id                      AS processo_id,
                  p.numero_processo,
                  p.cnpj,
                  p.fornecedor,
                  p.contrato,
                  p.natureza,
                  p.tipo_liquidacao,
                  p.atualizado_em,
                  e.id                      AS execucao_id,
                  e.data_execucao,
                  e.status,
                  e.bruto,
                  e.deducoes                AS total_deducoes,
                  e.liquido,
                  e.lf_numero,
                  e.ugr_numero,
                  e.vencimento_documento,
                  e.possui_divergencia,
                  e.exige_intervencao_manual,
                  e.observacoes,
                  e.vpd_manual,
                  e.vpd_informado_usuario,
                  coalesce(e.empenhos_json, '[]'::jsonb) AS empenhos_json,
                  s.nome                    AS servidor_nome,
                  s.setor                   AS servidor_setor
                FROM processos p
                JOIN execucoes e ON e.processo_id = p.id
                LEFT JOIN servidores s ON s.id = e.servidor_id
                WHERE p.cnpj = ANY(%s)
                  {where_contrato}
                ORDER BY e.data_execucao DESC, e.id DESC
                LIMIT %s
                """,
                [*params_base, limite],
            )
            rows_exec = cur.fetchall()

            if not rows_exec:
                return []

            exec_ids = [int(r["execucao_id"]) for r in rows_exec]

            # ── 2. Notas fiscais ──────────────────────────────────────────
            cur.execute(
                """
                SELECT execucao_id, numero_nota, tipo, emissao, ateste, valor
                FROM notas_fiscais_execucao
                WHERE execucao_id = ANY(%s)
                ORDER BY execucao_id, emissao
                """,
                (exec_ids,),
            )
            notas_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                notas_map.setdefault(eid, []).append({
                    "numero":  str(r["numero_nota"] or ""),
                    "tipo":    str(r["tipo"] or ""),
                    "emissao": str(r["emissao"] or ""),
                    "ateste":  str(r["ateste"] or ""),
                    "valor":   float(r["valor"] or 0),
                })

            # ── 3. Deduções ───────────────────────────────────────────────
            cur.execute(
                """
                SELECT execucao_id, codigo, siafi, tipo, valor, base_calculo, status
                FROM deducoes_execucao
                WHERE execucao_id = ANY(%s)
                ORDER BY execucao_id, tipo
                """,
                (exec_ids,),
            )
            deducoes_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                deducoes_map.setdefault(eid, []).append({
                    "codigo":      str(r["codigo"] or ""),
                    "siafi":       str(r["siafi"] or ""),
                    "tipo":        str(r["tipo"] or ""),
                    "valor":       float(r["valor"] or 0),
                    "baseCalculo": float(r["base_calculo"] or 0),
                    "status":      str(r["status"] or ""),
                })

            # ── 4. Pendências ─────────────────────────────────────────────
            cur.execute(
                """
                SELECT execucao_id, tipo, titulo, descricao, resolvida
                FROM execucao_pendencias
                WHERE execucao_id = ANY(%s)
                ORDER BY execucao_id, tipo
                """,
                (exec_ids,),
            )
            pendencias_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                pendencias_map.setdefault(eid, []).append({
                    "tipo":      str(r["tipo"] or ""),
                    "titulo":    str(r["titulo"] or ""),
                    "descricao": str(r["descricao"] or ""),
                    "resolvida": bool(r["resolvida"]),
                })

            # ── 5. Empenhos (tabela relacional por processo) ──────────────
            processo_ids = list({int(r["processo_id"]) for r in rows_exec})
            empenhos_map: dict[int, list[dict]] = {}
            try:
                cur.execute(
                    """
                    SELECT processo_id, numero, situacao, recurso, natureza, valor, saldo
                    FROM empenhos
                    WHERE processo_id = ANY(%s)
                    ORDER BY processo_id, id
                    """,
                    (processo_ids,),
                )
                for r in cur.fetchall():
                    pid = int(r["processo_id"])
                    empenhos_map.setdefault(pid, []).append({
                        "numero":   str(r["numero"] or ""),
                        "situacao": str(r["situacao"] or ""),
                        "recurso":  str(r["recurso"] or ""),
                        "natureza": str(r["natureza"] or ""),
                        "valor":    float(r["valor"] or 0),
                        "saldo":    float(r["saldo"] or 0),
                    })
            except Exception:
                log.exception("Falha ao buscar empenhos relacionais; usando fallback JSONB")

    # ── Montar estrutura agrupada por processo ────────────────────────────────
    def _fmt(v: Any) -> str | None:
        if v is None:
            return None
        return v.isoformat() if hasattr(v, "isoformat") else str(v)

    def _parse_empenhos_json(raw: Any) -> list[dict]:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw) if isinstance(raw, str) else []
        except Exception:
            return []

    processos: dict[int, dict] = {}
    for row in rows_exec:
        pid = int(row["processo_id"])
        eid = int(row["execucao_id"])

        if pid not in processos:
            processos[pid] = {
                "numeroProcesso": str(row["numero_processo"] or ""),
                "cnpj":           str(row["cnpj"] or ""),
                "fornecedor":     str(row["fornecedor"] or ""),
                "contrato":       str(row["contrato"] or ""),
                "natureza":       str(row["natureza"] or ""),
                "tipoLiquidacao": str(row["tipo_liquidacao"] or ""),
                "atualizadoEm":   _fmt(row["atualizado_em"]),
                "execucoes":      [],
            }

        # Empenhos: preferir tabela relacional; fallback para JSONB (registros antigos)
        empenhos_processo = _enriquecer_empenhos_historico(
            empenhos_map.get(pid) or _parse_empenhos_json(row.get("empenhos_json")),
            row["ugr_numero"],
        )
        vpd_resolvida, vpd_manual = _resolver_vpd_historico(
            row["natureza"],
            row["tipo_liquidacao"],
            row["vpd_manual"],
        )

        processos[pid]["execucoes"].append({
            "id":                  eid,
            "dataExecucao":        _fmt(row["data_execucao"]),
            "status":              str(row["status"] or ""),
            "bruto":               float(row["bruto"] or 0),
            "totalDeducoes":       float(row["total_deducoes"] or 0),
            "liquido":             float(row["liquido"] or 0),
            "lfNumero":            str(row["lf_numero"] or ""),
            "ugrNumero":           str(row["ugr_numero"] or ""),
            "vencimentoDocumento": str(row["vencimento_documento"] or ""),
            "possuiDivergencia":   bool(row["possui_divergencia"]),
            "exigeIntervencao":    bool(row["exige_intervencao_manual"]),
            "observacoes":         str(row["observacoes"] or ""),
            "vpd":                 vpd_resolvida,
            "vpdManual":           vpd_manual,
            "servidorNome":        str(row["servidor_nome"] or ""),
            "servidorSetor":       str(row["servidor_setor"] or ""),
            "notasFiscais":        notas_map.get(eid, []),
            "deducoes":            deducoes_map.get(eid, []),
            "pendencias":          pendencias_map.get(eid, []),
            "empenhos":            empenhos_processo,
        })

    # Ordena processos pelo data_execucao mais recente
    resultado = list(processos.values())
    resultado.sort(
        key=lambda p: p["execucoes"][0]["dataExecucao"] or "" if p["execucoes"] else "",
        reverse=True,
    )
    return resultado


def _normalizar_numero_processo(texto: str) -> str:
    """
    Aceita qualquer formato e extrai a parte pesquisável.
    Exemplos:
      '17645/26'        → '017645/2026'
      '017645/2026'     → '017645/2026'
      '23080.017645/2026' → '017645/2026'
    """
    import re
    texto = texto.strip()
    # Remove prefixo UORG (ex: '23080.')
    texto = re.sub(r"^\d{4,6}\.", "", texto)
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", texto)
    if m:
        numero = m.group(1).zfill(6)
        ano = m.group(2)
        if len(ano) == 2:
            ano = "20" + ano
        return f"{numero}/{ano}"
    return texto


def buscar_historico_por_numero_processo(
    numero_processo_raw: str,
    limite: int = 40,
) -> list[dict]:
    """Busca processos pelo número (parte NNNNN/AAAA), com normalização flexível."""
    if not postgres_habilitado():
        raise RuntimeError("Banco de dados não configurado.")

    numero_normalizado = _normalizar_numero_processo(numero_processo_raw)
    candidatos_exatos = list(dict.fromkeys(
        item.strip()
        for item in [numero_processo_raw, numero_normalizado]
        if str(item or "").strip()
    ))
    if candidatos_exatos:
        try:
            resultado_exato = _buscar_historico_por_condicao(
                "p.numero_processo = ANY(%s)",
                [candidatos_exatos],
                limite,
            )
            if resultado_exato:
                return resultado_exato
        except Exception:
            log.exception("Falha na busca exata por número do processo; tentando busca flexível")
    if "." in str(numero_processo_raw or "") and "/" in str(numero_processo_raw or ""):
        return []

    with _get_connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                """
                SELECT
                  p.id                      AS processo_id,
                  p.numero_processo,
                  p.cnpj,
                  p.fornecedor,
                  p.contrato,
                  p.natureza,
                  p.tipo_liquidacao,
                  p.atualizado_em,
                  e.id                      AS execucao_id,
                  e.data_execucao,
                  e.status,
                  e.bruto,
                  e.deducoes                AS total_deducoes,
                  e.liquido,
                  e.lf_numero,
                  e.ugr_numero,
                  e.vencimento_documento,
                  e.possui_divergencia,
                  e.exige_intervencao_manual,
                  e.observacoes,
                  e.vpd_manual,
                  e.vpd_informado_usuario,
                  coalesce(e.empenhos_json, '[]'::jsonb) AS empenhos_json,
                  s.nome                    AS servidor_nome,
                  s.setor                   AS servidor_setor
                FROM processos p
                JOIN execucoes e ON e.processo_id = p.id
                LEFT JOIN servidores s ON s.id = e.servidor_id
                WHERE p.numero_processo ILIKE %s
                ORDER BY e.data_execucao DESC, e.id DESC
                LIMIT %s
                """,
                [f"%{numero_normalizado}%", limite],
            )
            rows_exec = cur.fetchall()

            if not rows_exec:
                return []

            exec_ids = [int(r["execucao_id"]) for r in rows_exec]

            cur.execute(
                "SELECT execucao_id, numero_nota, tipo, emissao, ateste, valor FROM notas_fiscais_execucao WHERE execucao_id = ANY(%s) ORDER BY execucao_id, emissao",
                (exec_ids,),
            )
            notas_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                notas_map.setdefault(eid, []).append({
                    "numero": str(r["numero_nota"] or ""), "tipo": str(r["tipo"] or ""),
                    "emissao": str(r["emissao"] or ""), "ateste": str(r["ateste"] or ""),
                    "valor": float(r["valor"] or 0),
                })

            cur.execute(
                "SELECT execucao_id, codigo, siafi, tipo, valor, base_calculo, status FROM deducoes_execucao WHERE execucao_id = ANY(%s) ORDER BY execucao_id, tipo",
                (exec_ids,),
            )
            deducoes_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                deducoes_map.setdefault(eid, []).append({
                    "codigo": str(r["codigo"] or ""), "siafi": str(r["siafi"] or ""),
                    "tipo": str(r["tipo"] or ""), "valor": float(r["valor"] or 0),
                    "baseCalculo": float(r["base_calculo"] or 0), "status": str(r["status"] or ""),
                })

            cur.execute(
                "SELECT execucao_id, tipo, titulo, descricao, resolvida FROM execucao_pendencias WHERE execucao_id = ANY(%s) ORDER BY execucao_id, tipo",
                (exec_ids,),
            )
            pendencias_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                pendencias_map.setdefault(eid, []).append({
                    "tipo": str(r["tipo"] or ""), "titulo": str(r["titulo"] or ""),
                    "descricao": str(r["descricao"] or ""), "resolvida": bool(r["resolvida"]),
                })

            # ── Empenhos (tabela relacional por processo) ─────────────────
            processo_ids = list({int(r["processo_id"]) for r in rows_exec})
            empenhos_map: dict[int, list[dict]] = {}
            try:
                cur.execute(
                    "SELECT processo_id, numero, situacao, recurso, natureza, valor, saldo FROM empenhos WHERE processo_id = ANY(%s) ORDER BY processo_id, id",
                    (processo_ids,),
                )
                for r in cur.fetchall():
                    pid = int(r["processo_id"])
                    empenhos_map.setdefault(pid, []).append({
                        "numero":   str(r["numero"] or ""),
                        "situacao": str(r["situacao"] or ""),
                        "recurso":  str(r["recurso"] or ""),
                        "natureza": str(r["natureza"] or ""),
                        "valor":    float(r["valor"] or 0),
                        "saldo":    float(r["saldo"] or 0),
                    })
            except Exception:
                log.exception("Falha ao buscar empenhos relacionais; usando fallback JSONB")

    def _fmt(v: Any) -> str | None:
        return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v is not None else None)

    def _parse_empenhos_json(raw: Any) -> list[dict]:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw) if isinstance(raw, str) else []
        except Exception:
            return []

    processos: dict[int, dict] = {}
    for row in rows_exec:
        pid = int(row["processo_id"])
        eid = int(row["execucao_id"])
        if pid not in processos:
            processos[pid] = {
                "numeroProcesso": str(row["numero_processo"] or ""),
                "cnpj":           str(row["cnpj"] or ""),
                "fornecedor":     str(row["fornecedor"] or ""),
                "contrato":       str(row["contrato"] or ""),
                "natureza":       str(row["natureza"] or ""),
                "tipoLiquidacao": str(row["tipo_liquidacao"] or ""),
                "atualizadoEm":   _fmt(row["atualizado_em"]),
                "execucoes":      [],
            }
        empenhos_processo = _enriquecer_empenhos_historico(
            empenhos_map.get(pid) or _parse_empenhos_json(row.get("empenhos_json")),
            row["ugr_numero"],
        )
        vpd_resolvida, vpd_manual = _resolver_vpd_historico(
            row["natureza"],
            row["tipo_liquidacao"],
            row["vpd_manual"],
        )
        processos[pid]["execucoes"].append({
            "id": eid, "dataExecucao": _fmt(row["data_execucao"]),
            "status": str(row["status"] or ""), "bruto": float(row["bruto"] or 0),
            "totalDeducoes": float(row["total_deducoes"] or 0), "liquido": float(row["liquido"] or 0),
            "lfNumero": str(row["lf_numero"] or ""), "ugrNumero": str(row["ugr_numero"] or ""),
            "vencimentoDocumento": str(row["vencimento_documento"] or ""),
            "possuiDivergencia": bool(row["possui_divergencia"]),
            "exigeIntervencao": bool(row["exige_intervencao_manual"]),
            "observacoes": str(row["observacoes"] or ""),
            "vpd": vpd_resolvida,
            "vpdManual": vpd_manual,
            "servidorNome": str(row["servidor_nome"] or ""),
            "servidorSetor": str(row["servidor_setor"] or ""),
            "notasFiscais": notas_map.get(eid, []),
            "deducoes": deducoes_map.get(eid, []),
            "pendencias": pendencias_map.get(eid, []),
            "empenhos": empenhos_processo,
        })

    resultado = list(processos.values())
    resultado.sort(
        key=lambda p: p["execucoes"][0]["dataExecucao"] or "" if p["execucoes"] else "",
        reverse=True,
    )
    return resultado


def _buscar_historico_por_condicao(
    where_sql: str,
    params: list[Any],
    limite: int = 40,
) -> list[dict]:
    """Busca processos por uma condição segura e retorna o histórico completo."""
    if not postgres_habilitado():
        raise RuntimeError("Banco de dados não configurado.")

    with _get_connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                  p.id                      AS processo_id,
                  p.numero_processo,
                  p.cnpj,
                  p.fornecedor,
                  p.contrato,
                  p.natureza,
                  p.tipo_liquidacao,
                  p.atualizado_em,
                  e.id                      AS execucao_id,
                  e.data_execucao,
                  e.status,
                  e.bruto,
                  e.deducoes                AS total_deducoes,
                  e.liquido,
                  e.lf_numero,
                  e.ugr_numero,
                  e.vencimento_documento,
                  e.possui_divergencia,
                  e.exige_intervencao_manual,
                  e.observacoes,
                  e.vpd_manual,
                  e.vpd_informado_usuario,
                  coalesce(e.empenhos_json, '[]'::jsonb) AS empenhos_json,
                  s.nome                    AS servidor_nome,
                  s.setor                   AS servidor_setor
                FROM processos p
                JOIN execucoes e ON e.processo_id = p.id
                LEFT JOIN servidores s ON s.id = e.servidor_id
                WHERE {where_sql}
                ORDER BY e.data_execucao DESC, e.id DESC
                LIMIT %s
                """,
                [*params, limite],
            )
            rows_exec = cur.fetchall()

            if not rows_exec:
                return []

            exec_ids = [int(r["execucao_id"]) for r in rows_exec]

            cur.execute(
                "SELECT execucao_id, numero_nota, tipo, emissao, ateste, valor FROM notas_fiscais_execucao WHERE execucao_id = ANY(%s) ORDER BY execucao_id, emissao",
                (exec_ids,),
            )
            notas_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                notas_map.setdefault(eid, []).append({
                    "numero": str(r["numero_nota"] or ""), "tipo": str(r["tipo"] or ""),
                    "emissao": str(r["emissao"] or ""), "ateste": str(r["ateste"] or ""),
                    "valor": float(r["valor"] or 0),
                })

            cur.execute(
                "SELECT execucao_id, codigo, siafi, tipo, valor, base_calculo, status FROM deducoes_execucao WHERE execucao_id = ANY(%s) ORDER BY execucao_id, tipo",
                (exec_ids,),
            )
            deducoes_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                deducoes_map.setdefault(eid, []).append({
                    "codigo": str(r["codigo"] or ""), "siafi": str(r["siafi"] or ""),
                    "tipo": str(r["tipo"] or ""), "valor": float(r["valor"] or 0),
                    "baseCalculo": float(r["base_calculo"] or 0), "status": str(r["status"] or ""),
                })

            cur.execute(
                "SELECT execucao_id, tipo, titulo, descricao, resolvida FROM execucao_pendencias WHERE execucao_id = ANY(%s) ORDER BY execucao_id, tipo",
                (exec_ids,),
            )
            pendencias_map: dict[int, list[dict]] = {}
            for r in cur.fetchall():
                eid = int(r["execucao_id"])
                pendencias_map.setdefault(eid, []).append({
                    "tipo": str(r["tipo"] or ""), "titulo": str(r["titulo"] or ""),
                    "descricao": str(r["descricao"] or ""), "resolvida": bool(r["resolvida"]),
                })

            processo_ids = list({int(r["processo_id"]) for r in rows_exec})
            empenhos_map: dict[int, list[dict]] = {}
            try:
                cur.execute(
                    "SELECT processo_id, numero, situacao, recurso, natureza, valor, saldo FROM empenhos WHERE processo_id = ANY(%s) ORDER BY processo_id, id",
                    (processo_ids,),
                )
                for r in cur.fetchall():
                    pid = int(r["processo_id"])
                    empenhos_map.setdefault(pid, []).append({
                        "numero":   str(r["numero"] or ""),
                        "situacao": str(r["situacao"] or ""),
                        "recurso":  str(r["recurso"] or ""),
                        "natureza": str(r["natureza"] or ""),
                        "valor":    float(r["valor"] or 0),
                        "saldo":    float(r["saldo"] or 0),
                    })
            except Exception:
                log.exception("Falha ao buscar empenhos relacionais; usando fallback JSONB")

    def _fmt(v: Any) -> str | None:
        return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v is not None else None)

    def _parse_empenhos_json(raw: Any) -> list[dict]:
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw) if isinstance(raw, str) else []
        except Exception:
            return []

    processos: dict[int, dict] = {}
    for row in rows_exec:
        pid = int(row["processo_id"])
        eid = int(row["execucao_id"])
        if pid not in processos:
            processos[pid] = {
                "numeroProcesso": str(row["numero_processo"] or ""),
                "cnpj":           str(row["cnpj"] or ""),
                "fornecedor":     str(row["fornecedor"] or ""),
                "contrato":       str(row["contrato"] or ""),
                "natureza":       str(row["natureza"] or ""),
                "tipoLiquidacao": str(row["tipo_liquidacao"] or ""),
                "atualizadoEm":   _fmt(row["atualizado_em"]),
                "execucoes":      [],
            }
        empenhos_processo = _enriquecer_empenhos_historico(
            empenhos_map.get(pid) or _parse_empenhos_json(row.get("empenhos_json")),
            row["ugr_numero"],
        )
        vpd_resolvida, vpd_manual = _resolver_vpd_historico(
            row["natureza"],
            row["tipo_liquidacao"],
            row["vpd_manual"],
        )
        processos[pid]["execucoes"].append({
            "id": eid, "dataExecucao": _fmt(row["data_execucao"]),
            "status": str(row["status"] or ""), "bruto": float(row["bruto"] or 0),
            "totalDeducoes": float(row["total_deducoes"] or 0), "liquido": float(row["liquido"] or 0),
            "lfNumero": str(row["lf_numero"] or ""), "ugrNumero": str(row["ugr_numero"] or ""),
            "vencimentoDocumento": str(row["vencimento_documento"] or ""),
            "possuiDivergencia": bool(row["possui_divergencia"]),
            "exigeIntervencao": bool(row["exige_intervencao_manual"]),
            "observacoes": str(row["observacoes"] or ""),
            "vpd": vpd_resolvida,
            "vpdManual": vpd_manual,
            "servidorNome": str(row["servidor_nome"] or ""),
            "servidorSetor": str(row["servidor_setor"] or ""),
            "notasFiscais": notas_map.get(eid, []),
            "deducoes": deducoes_map.get(eid, []),
            "pendencias": pendencias_map.get(eid, []),
            "empenhos": empenhos_processo,
        })

    resultado = list(processos.values())
    resultado.sort(
        key=lambda p: p["execucoes"][0]["dataExecucao"] or "" if p["execucoes"] else "",
        reverse=True,
    )
    return resultado


def buscar_historico_por_contrato(contrato_filtro: str | Sequence[str], limite: int = 40) -> list[dict]:
    if isinstance(contrato_filtro, str):
        contratos = [contrato_filtro.strip()] if contrato_filtro.strip() else []
    else:
        contratos = [str(item).strip() for item in contrato_filtro if str(item).strip()]
    contratos = list(dict.fromkeys(contratos))
    if not contratos:
        return []
    placeholders = " OR ".join(["upper(p.contrato) LIKE upper(%s)"] * len(contratos))
    return _buscar_historico_por_condicao(
        f"({placeholders})",
        [f"%{contrato}%" for contrato in contratos],
        limite,
    )


def buscar_historico_por_empenho(empenho_filtro: str, limite: int = 40) -> list[dict]:
    empenho = empenho_filtro.strip()
    if not empenho:
        return []
    empenho_digitos = "".join(c for c in empenho if c.isdigit())
    return _buscar_historico_por_condicao(
        """
        exists (
          select 1
          from empenhos emp
          where emp.processo_id = p.id
            and (
              emp.numero ILIKE %s
              or regexp_replace(coalesce(emp.numero, ''), '[^0-9]', '', 'g') LIKE %s
            )
        )
        """,
        [f"%{empenho}%", f"%{empenho_digitos or empenho}%"],
        limite,
    )


def obter_datas_globais() -> dict[str, str]:
    """Lê a linha de datas globais do Supabase (primeira linha cadastrada)."""
    if not postgres_habilitado():
        return {"vencimento": "", "apuracao": ""}
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select vencimento_pagamento, data_apuracao from datas_globais order by id asc limit 1"
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            return {"vencimento": "", "apuracao": ""}
        return {
            "vencimento": str(row["vencimento_pagamento"] or ""),
            "apuracao":   str(row["data_apuracao"] or ""),
        }
    except Exception:
        log.exception("Falha ao obter datas globais do Supabase")
        return {"vencimento": "", "apuracao": ""}


def _where_periodo(periodo: str) -> str:
    periodo = str(periodo or "semana").strip().lower()
    if periodo == "dia":
        return "e.data_execucao >= date_trunc('day', now())"
    if periodo == "mes":
        return "e.data_execucao >= now() - interval '30 days'"
    if periodo == "este-mes":
        return "e.data_execucao >= date_trunc('month', now())"
    return "e.data_execucao >= date_trunc('week', now())"


def obter_dashboard(periodo: str = "semana", servidor_nome: str = "", limite: int = 5) -> dict[str, Any]:
    if not postgres_habilitado():
        return {
            "habilitado": False,
            "periodo": periodo,
            "valorBruto": 0,
            "quantidadeProcessos": 0,
            "ultimosProcessos": [],
        }

    limite = max(1, min(100, int(limite or 5)))
    where_periodo = _where_periodo(periodo)
    # Filtro de servidor: quando informado, filtra apenas execuções do nome exato
    servidor_filter = "and lower(s.nome) = lower(%(servidor_nome)s)" if servidor_nome.strip() else ""
    params: dict[str, Any] = {"servidor_nome": servidor_nome.strip()}

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                with execucoes_unicas as (
                  select distinct on (e.processo_id)
                    e.processo_id,
                    e.bruto,
                    e.data_execucao
                  from execucoes e
                  join servidores s on s.id = e.servidor_id
                  where {where_periodo}
                  {servidor_filter}
                  order by e.processo_id, e.data_execucao desc, e.id desc
                )
                select
                  coalesce(sum(bruto), 0) as valor_bruto,
                  count(*) as quantidade_processos
                from execucoes_unicas
                """,
                params,
            )
            bruto_row = cur.fetchone() or {}

            cur.execute(
                f"""
                with execucoes_unicas as (
                  select distinct on (e.processo_id)
                    e.processo_id,
                    e.bruto,
                    e.data_execucao
                  from execucoes e
                  join servidores s on s.id = e.servidor_id
                  where {where_periodo}
                  {servidor_filter}
                  order by e.processo_id, e.data_execucao desc, e.id desc
                )
                select p.numero_processo, p.fornecedor, eu.bruto, eu.data_execucao
                from execucoes_unicas eu
                join processos p on p.id = eu.processo_id
                order by eu.data_execucao desc
                limit %(limite)s
                """,
                {**params, "limite": limite},
            )
            ultimos = [
                {
                    "numeroProcesso": str(row["numero_processo"] or ""),
                    "fornecedor": str(row["fornecedor"] or ""),
                    "bruto": float(row["bruto"] or 0),
                    "dataExecucao": row["data_execucao"].isoformat() if row["data_execucao"] else None,
                    "status": "aguardando",
                }
                for row in cur.fetchall()
            ]

    return {
        "habilitado": True,
        "periodo": periodo,
        "valorBruto": float(bruto_row.get("valor_bruto") or 0),
        "quantidadeProcessos": int(bruto_row.get("quantidade_processos") or 0),
        "ultimosProcessos": ultimos,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD HISTÓRICO
# ─────────────────────────────────────────────────────────────────────────────

def _where_periodo_hist(periodo: str) -> str:
    p = str(periodo or "semana").strip().lower()
    if p == "semana":
        return "e.data_execucao >= date_trunc('week', now())"
    if p == "mes":
        return "e.data_execucao >= now() - interval '30 days'"
    if p == "trimestre":
        return "e.data_execucao >= now() - interval '90 days'"
    if p == "semestre":
        return "e.data_execucao >= now() - interval '180 days'"
    if p == "ano":
        return "e.data_execucao >= now() - interval '365 days'"
    return "1=1"  # tudo


def obter_dashboard_historico(
    empresa: str = "",
    contrato: str = "",
    servidor: str = "",
    periodo: str = "semana",
) -> dict[str, Any]:
    """Retorna dados agregados de todos os processos já executados, com filtros."""
    if not postgres_habilitado():
        return {
            "habilitado": False,
            "total": 0, "totalValor": 0,
            "porServidor": [], "porEmpresa": [],
            "porContrato": [], "porMes": [],
        }

    where_parts: list[str] = [_where_periodo_hist(periodo)]
    params: dict[str, Any] = {}

    if empresa.strip():
        where_parts.append("upper(p.fornecedor) like upper(%(empresa)s)")
        params["empresa"] = f"%{empresa.strip()}%"
    if contrato.strip():
        where_parts.append("upper(p.contrato) like upper(%(contrato)s)")
        params["contrato"] = f"%{contrato.strip()}%"
    if servidor.strip():
        where_parts.append("upper(s.nome) like upper(%(servidor)s)")
        params["servidor"] = f"%{servidor.strip()}%"

    where_sql = " and ".join(where_parts)

    base_cte = f"""
        with execucoes_ranked as (
          select distinct on (e.processo_id)
            e.processo_id,
            e.bruto,
            e.data_execucao,
            s.nome          as servidor_nome,
            p.fornecedor,
            p.contrato,
            p.cnpj,
            e.status
          from execucoes e
          join processos  p on p.id = e.processo_id
          join servidores s on s.id = e.servidor_id
          where {where_sql}
          order by e.processo_id, e.data_execucao desc, e.id desc
        ),
        base as (
          select *
          from execucoes_ranked
          where lower(coalesce(status, '')) like 'conclu%'
        )
    """

    with _get_connection() as conn:
        with conn.cursor() as cur:
            # ── Totais ────────────────────────────────────────────────────────
            cur.execute(
                base_cte + """
                select count(*) as cnt, coalesce(sum(bruto), 0) as total
                from base
                """,
                params,
            )
            row_totais = cur.fetchone() or {}
            total = int(row_totais.get("cnt") or 0)
            total_valor = float(row_totais.get("total") or 0)

            # ── Por servidor ─────────────────────────────────────────────────
            # Agrupamos pelo primeiro nome para unificar "Karine" e "Karine LUDTKE"
            cur.execute(
                base_cte + """
                select
                  split_part(servidor_nome, ' ', 1) as nome_curto,
                  count(*)                          as cnt,
                  coalesce(sum(bruto), 0)           as total
                from base
                group by nome_curto
                order by total desc
                limit 20
                """,
                params,
            )
            por_servidor = [
                {
                    "nome": str(r["nome_curto"] or "—"),
                    "count": int(r["cnt"]),
                    "valor": float(r["total"]),
                }
                for r in cur.fetchall()
            ]

            # ── Por empresa ──────────────────────────────────────────────────
            cur.execute(
                base_cte + """
                select
                  fornecedor,
                  cnpj,
                  count(*)                as cnt,
                  coalesce(sum(bruto), 0) as total
                from base
                group by fornecedor, cnpj
                order by total desc
                limit 20
                """,
                params,
            )
            por_empresa = [
                {
                    "nome": str(r["fornecedor"] or "—"),
                    "cnpj": str(r["cnpj"] or ""),
                    "count": int(r["cnt"]),
                    "valor": float(r["total"]),
                }
                for r in cur.fetchall()
            ]

            # ── Por contrato ─────────────────────────────────────────────────
            cur.execute(
                base_cte + """
                select
                  coalesce(nullif(trim(contrato), ''), '(sem contrato)') as contrato_label,
                  count(*)                as cnt,
                  coalesce(sum(bruto), 0) as total
                from base
                group by contrato_label
                order by total desc
                limit 15
                """,
                params,
            )
            por_contrato = [
                {
                    "contrato": str(r["contrato_label"] or "—"),
                    "count": int(r["cnt"]),
                    "valor": float(r["total"]),
                }
                for r in cur.fetchall()
            ]

            # ── Por mês ───────────────────────────────────────────────────────
            cur.execute(
                base_cte + """
                select
                  to_char(data_execucao, 'YYYY-MM') as mes,
                  count(*)                           as cnt,
                  coalesce(sum(bruto), 0)            as total
                from base
                where data_execucao is not null
                group by mes
                order by mes
                limit 24
                """,
                params,
            )
            por_mes = [
                {
                    "mes": str(r["mes"]),
                    "count": int(r["cnt"]),
                    "valor": float(r["total"]),
                }
                for r in cur.fetchall()
            ]

    return {
        "habilitado": True,
        "total": total,
        "totalValor": total_valor,
        "porServidor": por_servidor,
        "porEmpresa": por_empresa,
        "porContrato": por_contrato,
        "porMes": por_mes,
    }


def listar_ausencias() -> list[dict[str, Any]]:
    if not postgres_habilitado():
        return []
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, servidor, tipo,
                       to_char(inicio, 'YYYY-MM-DD') as inicio,
                       to_char(fim,    'YYYY-MM-DD') as fim,
                       obs
                from ausencias
                order by inicio, servidor
                """
            )
            return [
                {
                    "id": r["id"],
                    "servidor": r["servidor"],
                    "tipo": r["tipo"],
                    "inicio": r["inicio"],
                    "fim": r["fim"],
                    "obs": r["obs"],
                }
                for r in cur.fetchall()
            ]


def criar_ausencia(ausencia: dict[str, Any]) -> dict[str, Any]:
    if not postgres_habilitado():
        raise RuntimeError("Banco de dados não configurado.")
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into ausencias (id, servidor, tipo, inicio, fim, obs)
                values (%s, %s, %s, %s::date, %s::date, %s)
                returning id, servidor, tipo,
                          to_char(inicio, 'YYYY-MM-DD') as inicio,
                          to_char(fim,    'YYYY-MM-DD') as fim,
                          obs
                """,
                (
                    str(ausencia["id"]),
                    str(ausencia["servidor"]).strip(),
                    str(ausencia["tipo"]),
                    str(ausencia["inicio"]),
                    str(ausencia["fim"]),
                    str(ausencia.get("obs") or "").strip() or None,
                ),
            )
            conn.commit()
            row = cur.fetchone()
            return {
                "id": row["id"],
                "servidor": row["servidor"],
                "tipo": row["tipo"],
                "inicio": row["inicio"],
                "fim": row["fim"],
                "obs": row["obs"],
            }


def deletar_ausencia(ausencia_id: str) -> bool:
    if not postgres_habilitado():
        raise RuntimeError("Banco de dados não configurado.")
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from ausencias where id = %s", (ausencia_id,))
            conn.commit()
            return (cur.rowcount or 0) > 0
