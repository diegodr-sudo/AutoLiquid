"""
turso_cleanup.py — Limpeza do banco Turso do AutoLiquid.

Remove tabelas vazias/órfãs e índices redundantes identificados em auditoria.
Execute uma vez, depois pode deletar este arquivo.

Rode com:
    python3 turso_cleanup.py
"""
import requests
import json

URL = "https://autoliquid-diegodutraramos.aws-us-east-1.turso.io/v2/pipeline"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODAwMTY2NDEsImlkIjoiMDE5ZGNmMDYtMDIwMS03NmQ2LWE3N2QtN2ZiOTZmYjEyZDhjIiwicmlkIjoiMmM1NDA5Y2MtYWFjMi00ZGI1LWE0NDItMjA1ZGZhZWQ2YzFmIn0.55Jq9CSAfZXswWf3ZXCWlwL4iNjmdKclBmqIkchXfvvKPMcp6qRRzMde8VCR6cQH9_I0ffzd9YlQItPKNngxAw"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def run(sql: str) -> dict:
    r = requests.post(
        URL,
        headers=HEADERS,
        json={"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]},
        timeout=15,
    )
    r.raise_for_status()
    result = r.json()["results"][0]
    if result["type"] != "ok":
        raise RuntimeError(f"Turso recusou: {json.dumps(result)[:300]}")
    return result["response"]["result"]


def count(table: str) -> int:
    res = run(f"SELECT COUNT(*) as n FROM {table}")
    return int(res["rows"][0][0]["value"])


DROPS = [
    # ── Tabelas vazias / nunca usadas ─────────────────────────────────────────
    ("DROP TABLE IF EXISTS bolsistas",
     "Tabela bolsistas: 0 rows, nunca recebe INSERT pelo código. 3 índices eliminados junto."),

    ("DROP TABLE IF EXISTS regras_operacionais",
     "Tabela regras_operacionais: 0 rows, zero leituras/escritas em todo o codebase."),

    ("DROP TABLE IF EXISTS autoliquid_release_probe",
     "Tabela autoliquid_release_probe: 1 row, órfã — não existe no schema do código."),

    # ── Índices redundantes ────────────────────────────────────────────────────
    ("DROP INDEX IF EXISTS idx_processos_numero",
     "Índice idx_processos_numero: duplicata do autoindex gerado pela UNIQUE constraint em numero_processo."),

    ("DROP INDEX IF EXISTS idx_fila_atual_presente",
     "Índice idx_fila_atual_presente: (presente,competencia,numero_processo) é subconjunto de "
     "idx_fila_atual_presente_ordem que tem as mesmas colunas + chave. O maior cobre o menor."),

    ("DROP INDEX IF EXISTS idx_fila_alertas_ativo",
     "Índice idx_fila_alertas_ativo: (ativo,criado_em) coberto pelos índices _chave e _numero "
     "que já incluem ativo,criado_em. Nenhuma query filtra só por ativo sem chave/numero."),
]

print("=" * 70)
print("TURSO CLEANUP — AutoLiquid")
print("=" * 70)
print()

errors = []
for sql, descricao in DROPS:
    obj_name = sql.split()[-1]  # última palavra = nome do objeto
    try:
        run(sql)
        print(f"  ✅ OK   {obj_name}")
        print(f"         {descricao}")
    except Exception as e:
        print(f"  ❌ ERRO {obj_name}: {e}")
        errors.append((obj_name, str(e)))
    print()

print("=" * 70)
if errors:
    print(f"Concluído com {len(errors)} erro(s). Verifique acima.")
else:
    print("Limpeza concluída sem erros.")

print()
print("Verificando estado final do banco...")
print()

check_tables = [
    "bolsistas", "regras_operacionais", "autoliquid_release_probe",
    "contrato_ic_de_para", "vpd_de_para", "fila_processos_atual",
]
res = run("SELECT type, name FROM sqlite_master WHERE type IN ('table','index') ORDER BY type, name")
cols = [c["name"] for c in res.get("cols", [])]
objects = [{cols[i]: cell.get("value") for i, cell in enumerate(row)} for row in res.get("rows", [])]

tables_remaining = [o["name"] for o in objects if o["type"] == "table"]
indexes_remaining = [o["name"] for o in objects if o["type"] == "index"]

dropped_tables = {"bolsistas", "regras_operacionais", "autoliquid_release_probe"}
dropped_indexes = {"idx_processos_numero", "idx_fila_atual_presente", "idx_fila_alertas_ativo"}

print(f"  Tabelas no banco:  {len(tables_remaining)}")
print(f"  Índices no banco:  {len(indexes_remaining)}")
print()

still_there = dropped_tables & set(tables_remaining)
if still_there:
    print(f"  ⚠️  Ainda presentes (não dropadas): {still_there}")
else:
    print("  ✅ Todas as tabelas obsoletas foram removidas.")

still_idx = dropped_indexes & set(indexes_remaining)
if still_idx:
    print(f"  ⚠️  Índices ainda presentes: {still_idx}")
else:
    print("  ✅ Todos os índices redundantes foram removidos.")
