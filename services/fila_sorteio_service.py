"""Sorteio deterministico da fila.

O Turso/SQLite guarda a fila e a configuracao dos servidores; a aplicacao
executa a formula em memoria para manter compatibilidade com a planilha.
"""

from __future__ import annotations

from typing import Any


LEGACY_DISTRIBUTION_NAMES: tuple[str, ...] = (
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
)

DEFAULT_QUEUE_SERVERS: tuple[dict[str, str], ...] = (
    {"id": "diego", "nome": "Diego", "modo": "ativo"},
    {"id": "rubens", "nome": "Rubens", "modo": "ativo"},
    {"id": "gabriel", "nome": "Gabriel", "modo": "ativo"},
    {"id": "karine", "nome": "Karine", "modo": "ativo"},
    {"id": "ramone", "nome": "Ramone", "modo": "metade"},
)


def normalizar_servidor_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def normalizar_servidores_sorteio(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    servidores: list[dict[str, str]] = []
    source = rows if rows else list(DEFAULT_QUEUE_SERVERS)
    for index, item in enumerate(source):
        nome = str((item or {}).get("nome") or "").strip()
        if not nome:
            continue
        modo = str((item or {}).get("modo") or "ativo").strip().lower()
        if modo not in {"ativo", "metade", "fora"}:
            modo = "ativo"
        servidor_id = str((item or {}).get("id") or f"server-{index + 1}").strip()
        servidores.append({"id": servidor_id, "nome": nome, "modo": modo})
    return servidores


def _build_distribution_slots(servidores: list[dict[str, str]]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    ocorrencias: dict[str, int] = {}

    for nome in LEGACY_DISTRIBUTION_NAMES:
        key = normalizar_servidor_key(nome)
        occurrence = ocorrencias.get(key, 0)
        ocorrencias[key] = occurrence + 1
        slots.append({"name": nome, "key": key, "halfEligible": occurrence % 2 == 0})

    legacy_keys = {normalizar_servidor_key(nome) for nome in LEGACY_DISTRIBUTION_NAMES}
    for servidor in servidores:
        nome = str(servidor.get("nome") or "").strip()
        key = normalizar_servidor_key(nome)
        if not nome or key in legacy_keys:
            continue
        for index in range(20):
            slots.append({"name": nome, "key": key, "halfEligible": index % 2 == 0})

    return slots


def sortear_responsavel(numero_processo: Any, servidores: list[dict[str, Any]] | None) -> str:
    servidores_normalizados = normalizar_servidores_sorteio(servidores)
    server_map = {
        normalizar_servidor_key(item["nome"]): item
        for item in servidores_normalizados
        if str(item.get("nome") or "").strip()
    }
    slots = _build_distribution_slots(servidores_normalizados)
    active_slots = [
        slot
        for slot in slots
        if (server := server_map.get(slot["key"]))
        and server["modo"] != "fora"
        and (server["modo"] != "metade" or bool(slot["halfEligible"]))
    ]
    if not active_slots:
        return "Ninguém ativo"

    digits = "".join(ch for ch in str(numero_processo or "") if ch.isdigit())
    id_calculo = int(digits or "0")
    total_slots = len(slots)
    pos_base = (int(id_calculo * 7919) % total_slots + total_slots) % total_slots

    best_weight = -1
    best_name = str(active_slots[0]["name"])
    for index, slot in enumerate(slots):
        server = server_map.get(slot["key"])
        if not server or server["modo"] == "fora":
            continue
        if server["modo"] == "metade" and not slot["halfEligible"]:
            continue

        sequence_index = index + 1
        weight_base = int(id_calculo * (sequence_index * 104729 + 13))
        weight = (weight_base % 10000 + 10000) % 10000
        if index == pos_base:
            weight += 1000000
        if weight > best_weight:
            best_weight = weight
            best_name = str(slot["name"])

    return best_name


def aplicar_sorteio_rows(rows: list[dict[str, Any]], servidores: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows or []:
        next_row = dict(row or {})
        if not str(next_row.get("__responsavel_manual") or "").strip() and not str(next_row.get("Recebido Por") or "").strip():
            next_row["__responsavel_sorteado"] = sortear_responsavel(next_row.get("Número Processo"), servidores)
        else:
            next_row["__responsavel_sorteado"] = ""
        enriched.append(next_row)
    return enriched
