# AutoLiquid — Guia de Agentes e Boas Práticas

Este arquivo documenta regras arquiteturais obrigatórias para qualquer agente ou desenvolvedor que trabalhe no codebase do AutoLiquid. O objetivo é evitar a repetição de erros de arquitetura identificados em produção.

---

## Boas Práticas de Banco de Dados (Turso/SQLite)

O banco de dados do AutoLiquid é hospedado no **Turso** (SQLite via libSQL) e acessado exclusivamente via **HTTP API** (`/v2/pipeline`). Por ser SQLite, ele usa um arquivo único com WAL (Write-Ahead Log) — operações de escrita mal estruturadas causam **locks de dezenas de segundos** e degradam todo o sistema.

As regras abaixo são **obrigatórias** em qualquer implementação nova ou refatoração.

---

### Regra 1 — Proibido: loops com inserções ou atualizações individuais

**É estritamente proibido** usar laços (`for`, `while`) para chamar `executar()` individualmente dentro do loop. Cada chamada individual a `executar()` abre e fecha uma transação automática no SQLite, multiplicando a contenção de locks pelo número de linhas.

**Errado:**
```python
for row in rows:
    executar("INSERT INTO tabela VALUES (?, ?)", [row["a"], row["b"]])
```

**Certo — usar `executemany` (batch via pipeline):**
```python
# Acumular statements e enviar em lote
statements = [
    ("INSERT INTO tabela VALUES (?, ?)", [row["a"], row["b"]])
    for row in rows
]
executar_pipeline_transacional(statements, chunk_size=500, timeout=60)
```

**Ainda melhor — batch INSERT com múltiplos valores por statement:**
```python
_BATCH = 50
for start in range(0, len(valid_rows), _BATCH):
    chunk = valid_rows[start : start + _BATCH]
    placeholders = ", ".join("(?, ?)" for _ in chunk)
    flat_args = [v for row in chunk for v in row]
    statements.append((f"INSERT INTO tabela VALUES {placeholders}", flat_args))
executar_pipeline_transacional(statements, chunk_size=500, timeout=60)
```

---

### Regra 2 — Operações em massa dentro de uma única transação (BEGIN / COMMIT)

Operações que limpam e repopulam uma tabela (padrão DELETE + INSERT) **devem sempre** ser encapsuladas em uma única transação explícita para evitar locks no arquivo do banco.

Sem BEGIN/COMMIT, o Turso/SQLite auto-commita cada statement individualmente → N write-transactions → contenção de WAL → locks de 15–25 segundos observados em produção.

**Use sempre `executar_pipeline_transacional`** (definida em `services/turso_service.py`) para qualquer operação em massa:

```python
# Padrão correto: DELETE + INSERTs em batch, tudo em uma transação
def salvar_minha_tabela(rows: list[dict]) -> None:
    garantir_schema_cache(timeout=10)
    valid_rows = [...]  # normalizar dados primeiro

    statements: list[tuple[str, list]] = [("DELETE FROM minha_tabela", None)]
    for start in range(0, len(valid_rows), 50):
        chunk = valid_rows[start : start + 50]
        placeholders = ", ".join("(?, ?)" for _ in chunk)
        flat_args = [v for row in chunk for v in row]
        statements.append((f"INSERT INTO minha_tabela VALUES {placeholders}", flat_args))

    # Uma transação, não N auto-commits
    executar_pipeline_transacional(statements, chunk_size=500, timeout=60)
```

`executar_pipeline_transacional` adiciona automaticamente `BEGIN` e `COMMIT` ao redor de cada chunk, garantindo atomicidade e desempenho.

---

### Regra 3 — Avaliar índices para tabelas de alto volume

Toda tabela que sofre alto volume de leitura filtrada ou deleções com cláusula `WHERE` deve ter **índices adequados** criados no schema (`garantir_schema_cache`).

Considere criar índices para:
- Colunas usadas frequentemente em `WHERE`, `JOIN ON` ou `ORDER BY`
- Colunas de FK (chaves estrangeiras) em tabelas de detalhe (ex: `execucao_id`, `processo_id`)
- Colunas usadas em deleções seletivas (`WHERE x = ?`)

**Não criar índices para:**
- Colunas de PRIMARY KEY (já indexadas automaticamente)
- Tabelas muito pequenas (< 1.000 linhas estáticas)
- Colunas de alta cardinalidade usadas apenas em INSERT

**Exemplo de índice composto para fila:**
```sql
CREATE INDEX IF NOT EXISTS idx_fila_atual_presente_ordem
  ON fila_processos_atual(presente, competencia, numero_processo, chave);
```

---

### Referência: funções de banco disponíveis

| Função | Uso |
|--------|-----|
| `executar(sql, args)` | Uma única query simples — leituras e escritas únicas |
| `executar_pipeline(statements)` | Múltiplas queries em um HTTP request, **sem transação explícita** |
| `executar_pipeline_transacional(statements, chunk_size, timeout)` | **Padrão obrigatório para escritas em massa** — envolve cada chunk em BEGIN/COMMIT |

> **Nunca chame `executar_pipeline` diretamente para operações de escrita em massa.** Use sempre `executar_pipeline_transacional`.

---

### Contexto: por que isso importa no Turso

O Turso usa SQLite com WAL mode sobre HTTP. Diferente de bancos relacionais tradicionais, SQLite só permite **um writer por vez**. Sem transações explícitas:

- 500 INSERTs = 500 transações separadas = 500 bloqueios sequenciais do WAL
- Cada lock dura ~0.05ms, mas com concorrência acumulam 25 segundos de espera
- O `DELETE` em tabela grande sem transação pode travar leitores por vários segundos

Com `BEGIN`/`COMMIT` envolvendo tudo:
- 500 INSERTs = 1 transação = 1 lock de ~100ms
- O `DELETE` + todos os INSERTs ocorrem atomicamente
- Redução de 99%+ no tempo de operações em massa (observado: de 25s para < 1s)

---

## Arquitetura Geral

- **Backend**: FastAPI (Python) em `api.py` + serviços em `services/`
- **Frontend**: Next.js + Tauri (desktop app)
- **Banco de dados**: Turso (SQLite/libSQL via HTTP API) — `services/turso_service.py`
- **Automação**: Playwright via CDP para SIAFI Web, TN3270 para SIAFI mainframe
- **PDF**: `pdfplumber` para extração, `core/extrator.py` para parsing

## Padrões de UI / Frontend

### Tooltip de ícones e badges informativos

**Padrão obrigatório:** use o componente `<Tooltip>` do Radix UI para **todos** os tooltips da aplicação — tanto em botões interativos quanto em badges informativos. **Nunca** use o atributo `title` nativo em elementos interativos (buttons, links com onClick). O `title` nativo só é aceitável em elementos puramente textuais que truncam conteúdo (spans, tds com `truncate`).

O estilo visual do `TooltipContent` já está padronizado globalmente em `ui/tooltip.tsx` (`rounded-xl`, `py-2`, `max-w-72`, `leading-5`). Não é necessário passar essas classes manualmente — use `<TooltipContent>` direto.

**Z-index:** dentro de modais que usam `z-[200]`, adicione `className="z-[210]"` ao `TooltipContent` e ao `PopoverContent` para garantir que apareçam por cima.

Exemplo canônico:
```tsx
<Tooltip>
  <TooltipTrigger asChild>
    <button type="button" aria-label={message} className="...">
      {/* ícone */}
    </button>
  </TooltipTrigger>
  <TooltipContent>
    {message}
  </TooltipContent>
</Tooltip>
```

Dentro de modal (`z-[200]`):
```tsx
<TooltipContent className="z-[210]">Descrição</TooltipContent>
```

### Tooltip + Popover no mesmo elemento

Quando um botão precisa de **Tooltip** (hover) **e** **Popover** (click), o `<Tooltip>` deve ficar **fora** do `<Popover>`, não dentro. Colocar `<Tooltip>` dentro de `<Popover>` cria conflito de eventos e impede o Popover de abrir.

**Correto:**
```tsx
<Tooltip>
  <Popover open={open} onOpenChange={setOpen}>
    <TooltipTrigger asChild>
      <PopoverTrigger asChild>
        <button>...</button>
      </PopoverTrigger>
    </TooltipTrigger>
    <PopoverContent>...</PopoverContent>
  </Popover>
  <TooltipContent>Descrição do botão</TooltipContent>
</Tooltip>
```

---

## Regras Gerais

- Não usar `executar()` em loop — sempre batch via `executar_pipeline_transacional`
- Não colocar lógica de negócio diretamente em `api.py` — usar `services/`
- Não fazer requests síncronos longos no main thread — usar `asyncio` ou threads
- Versão em `VERSION`, `package.json`, `src-tauri/tauri.conf.json` e `src-tauri/Cargo.toml` — sempre manter em sync
