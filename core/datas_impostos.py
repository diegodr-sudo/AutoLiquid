"""
datas_impostos.py
Cálculo automático de datas de vencimento e apuração por código de imposto.
Regras baseadas nas normas da DCF/UFSC.

Os dias de vencimento (padrão Dia 20 / Dia 10) podem ser sobrescritos pelo
usuário via DialogoTabelas → aba "Datas Impostos". As sobrescrições são
persistidas em tabelas_config.json sob a chave "datas_impostos_overrides",
no formato: { "8105": 20, "8047": 10, ... }.
"""

from datetime import date, timedelta
import logging

from services.config_service import carregar_tabelas_config

log = logging.getLogger(__name__)

SIAFI_LEGADO_PARA_ATUAL = {
    "DDF021": "DDF050",
    "DDF025": "DDF055",
}


def _normalizar_siafi(value: str) -> str:
    siafi = str(value or "").strip().upper()
    return SIAFI_LEGADO_PARA_ATUAL.get(siafi, siafi)


def _carregar_overrides_dia() -> dict:
    """
    Lê tabelas_config.json e retorna dict { codigo: dia_int }.
    Retorna {} se arquivo não existir ou não tiver a chave.
    """
    try:
        cfg = carregar_tabelas_config()
        overrides = cfg.get("datas_impostos_overrides", {})
        # Garante que os valores são int
        return {str(k): int(v) for k, v in overrides.items() if v}
    except Exception:
        log.warning("datas_impostos: falha ao carregar overrides de dia.")
        return {}


def _carregar_regras_remotas() -> list[dict[str, str]] | None:
    try:
        from services import turso_service

        if turso_service.turso_configurado():
            rows = turso_service.obter_tabela_operacional("datas-impostos")
            if rows is not None:
                regras = _normalizar_regras_rows(rows)
                if regras:
                    return regras
    except Exception as exc:
        log.warning("datas_impostos: falha ao carregar regras remotas do Turso: %s", exc)

    try:
        from services.postgres_service import obter_tabela_operacional, postgres_habilitado

        if not postgres_habilitado():
            return None
        rows = obter_tabela_operacional("datas-impostos")
        if rows is None:
            return None
        regras = _normalizar_regras_rows(rows)
        return regras
    except Exception as exc:
        log.warning("datas_impostos: falha ao carregar regras remotas: %s", exc)
        return None

# ─────────────────────────────────────────────────────────────────────────────
# FERIADOS
# ─────────────────────────────────────────────────────────────────────────────

def _pascoa(ano):
    """Calcula a data da Páscoa (algoritmo anônimo gregoriano)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_ano(ano):
    """
    Retorna um set com todas as datas de feriado relevantes para Florianópolis.
    Inclui: nacionais fixos, nacionais móveis, SC e Florianópolis.
    """
    f = set()

    # ── Nacionais fixos ───────────────────────────────────────────────────────
    f.add(date(ano, 1,  1))   # Confraternização Universal
    f.add(date(ano, 4, 21))   # Tiradentes
    f.add(date(ano, 5,  1))   # Dia do Trabalho
    f.add(date(ano, 9,  7))   # Independência
    f.add(date(ano, 10, 12))  # Nossa Senhora Aparecida
    f.add(date(ano, 11,  2))  # Finados
    f.add(date(ano, 11, 15))  # Proclamação da República
    f.add(date(ano, 11, 20))  # Consciência Negra (lei 14.759/2023)
    f.add(date(ano, 12, 25))  # Natal

    # ── Nacionais móveis (base: Páscoa) ─────────────────────────────────────
    pascoa = _pascoa(ano)
    f.add(pascoa - timedelta(days=47))   # Carnaval (2ª feira) — ponto facultativo federal
    f.add(pascoa - timedelta(days=48))   # Carnaval (terça)
    f.add(pascoa - timedelta(days=2))    # Sexta-Feira Santa
    f.add(pascoa)                        # Páscoa (domingo, não útil de qqlr forma)
    f.add(pascoa + timedelta(days=60))   # Corpus Christi

    # ── Estado de Santa Catarina ─────────────────────────────────────────────
    f.add(date(ano, 8, 11))   # Dia de Santa Catarina

    # ── Florianópolis (municipais) ───────────────────────────────────────────
    f.add(date(ano, 2,  2))   # Nossa Senhora dos Navegantes
    f.add(date(ano, 3,  4))   # Fundação de Florianópolis

    return f


# ─────────────────────────────────────────────────────────────────────────────
# DIA ÚTIL
# ─────────────────────────────────────────────────────────────────────────────

def e_dia_util(d: date, feriados: set = None) -> bool:
    """Retorna True se 'd' é dia útil (não é fim de semana nem feriado)."""
    if d.weekday() >= 5:   # 5=sábado, 6=domingo
        return False
    if feriados is None:
        feriados = feriados_ano(d.year)
    return d not in feriados


def dia_util_anterior_ou_igual(d: date) -> date:
    """
    Retorna 'd' se for dia útil, senão recua até o dia útil imediatamente anterior.
    Exemplo: sábado dia 20 → retorna sexta-feira dia 19.
    """
    feriados = feriados_ano(d.year) | feriados_ano(d.year - 1)  # cobre virada de ano
    while not e_dia_util(d, feriados):
        d -= timedelta(days=1)
    return d


def dia_util_proximo_ou_igual(d: date) -> date:
    """
    Retorna 'd' se for dia útil, senão avança até o dia útil imediatamente posterior.
    Exemplo: sábado dia 20 → retorna segunda-feira dia 22.
    """
    feriados = feriados_ano(d.year) | feriados_ano(d.year + 1)
    while not e_dia_util(d, feriados):
        d += timedelta(days=1)
    return d


def ajustar_dia_nao_util(d: date, ajuste: str = "antecipar") -> date:
    ajuste_normalizado = str(ajuste or "antecipar").strip().lower()
    if ajuste_normalizado == "manter":
        return d
    if ajuste_normalizado == "prorrogar":
        return dia_util_proximo_ou_igual(d)
    return dia_util_anterior_ou_igual(d)


# ─────────────────────────────────────────────────────────────────────────────
# REGRAS DE IMPOSTO
# ─────────────────────────────────────────────────────────────────────────────

# Códigos que vencem dia 20 do mês posterior (dia útil Fpolis)
_VENCE_DIA_20 = {"1162", "1164", "8105", "8179", "8093", "8027"}

# Códigos que vencem dia 10 do mês posterior (dia útil Fpolis)
_VENCE_DIA_10 = {"8047", "5549"}

# Mapeamento código → situação SIAFI
CODIGO_SIAFI = {
    "1162": "DDF050",   # INSS
    "1164": "DDF050",   # INSS (outra alíquota)
    "6147": "DDF055",   # Retenções DDF055
    "9060": "DDF055",   # Retenções DDF055
    "8739": "DDF055",   # Retenções DDF055
    "8767": "DDF055",   # Retenções DDF055
    "6175": "DDF055",   # Retenções DDF055
    "8850": "DDF055",   # Retenções DDF055
    "8863": "DDF055",   # Retenções DDF055
    "6188": "DDF055",   # Retenções DDF055
    "6190": "DDF055",   # DIVS / outros DDF055
    "8105": "DDR001",   # ISS Florianópolis
    "8047": "DDR001",   # ISS Blumenau
    "8179": "DOB001",   # ISS Joinville
    "8093": "DOB001",   # ISS Curitibanos
    "8027": "DOB001",   # ISS Araranguá
    "5549": "DOB001",   # ISS Barra do Sul
    "8465": "DOB001",   # ISS Gov. Celso Ramos
}

# DOB001 que precisam de LF preenchida pelo usuário (Joinville é exceção — não precisa)
DOB001_SEM_LF = {"8179"}   # Joinville

# Descrição de cada código
DESCRICAO_CODIGO = {
    "1162": "INSS",
    "1164": "INSS",
    "6147": "Retenção DDF055",
    "9060": "Retenção DDF055",
    "8739": "Retenção DDF055",
    "8767": "Retenção DDF055",
    "6175": "Retenção DDF055",
    "8850": "Retenção DDF055",
    "8863": "Retenção DDF055",
    "6188": "Retenção DDF055",
    "6190": "Retenção DDF055 (DIVS)",
    "8105": "ISS Florianópolis",
    "8047": "ISS Blumenau",
    "8179": "ISS Joinville",
    "8093": "ISS Curitibanos",
    "8027": "ISS Araranguá",
    "5549": "ISS Barra do Sul",
    "8465": "ISS Gov. Celso Ramos",
}

# Regra de vencimento (texto legível para tabela genérica)
REGRA_VENCIMENTO = {
    "1162": "Dia 20 do mês posterior — dia útil Fpolis",
    "1164": "Dia 20 do mês posterior — dia útil Fpolis",
    "6147": "Informado pelo usuário (DDF055)",
    "9060": "Informado pelo usuário (DDF055)",
    "8739": "Informado pelo usuário (DDF055)",
    "8767": "Informado pelo usuário (DDF055)",
    "6175": "Informado pelo usuário (DDF055)",
    "8850": "Informado pelo usuário (DDF055)",
    "8863": "Informado pelo usuário (DDF055)",
    "6188": "Informado pelo usuário (DDF055)",
    "6190": "Informado pelo usuário (DDF055)",
    "8105": "Dia 20 do mês posterior — dia útil Fpolis",
    "8047": "Dia 10 do mês posterior — dia útil Fpolis",
    "8179": "Dia 20 do mês posterior — dia útil Fpolis",
    "8093": "Dia 20 do mês posterior — dia útil Fpolis",
    "8027": "Dia 20 do mês posterior — dia útil Fpolis",
    "5549": "Dia 10 do mês posterior — dia útil Fpolis",
    "8465": "Dia 20 do mesmo mês da NF — dia útil",
}

REGRA_APURACAO = {
    "1162": "Data de emissão mais antiga das NFs",
    "1164": "Data de emissão mais antiga das NFs",
    "6147": "Informado pelo usuário (DDF055)",
    "9060": "Informado pelo usuário (DDF055)",
    "8739": "Informado pelo usuário (DDF055)",
    "8767": "Informado pelo usuário (DDF055)",
    "6175": "Informado pelo usuário (DDF055)",
    "8850": "Informado pelo usuário (DDF055)",
    "8863": "Informado pelo usuário (DDF055)",
    "6188": "Informado pelo usuário (DDF055)",
    "6190": "Informado pelo usuário (DDF055)",
    "8105": "Data de emissão mais antiga das NFs",
    "8047": "Data de emissão mais antiga das NFs",
    "8179": "Data de emissão mais antiga das NFs",
    "8093": "Data de emissão mais antiga das NFs",
    "8027": "Data de emissão mais antiga das NFs",
    "5549": "Data de emissão mais antiga das NFs",
    "8465": "Data de emissão mais antiga das NFs",
}

# Tabela genérica completa para exibição no DialogoTabelas
TABELA_GENERICA = [
    # (Imposto, Código, Situação SIAFI, Regra Vencimento, Regra Apuração, Precisa LF?)
    ("INSS",             "1162", "DDF050", "Dia 20 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Não"),
    ("INSS",             "1164", "DDF050", "Dia 20 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Não"),
    ("Retenção",         "6147", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "9060", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "8739", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "8767", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "6175", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "8850", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "8863", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção",         "6188", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("Retenção (DIVS)",  "6190", "DDF055", "Informado pelo usuário",                  "Informado pelo usuário",       "Não"),
    ("ISS Florianópolis","8105", "DDR001", "Dia 20 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Não"),
    ("ISS Blumenau",     "8047", "DDR001", "Dia 10 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Não"),
    ("ISS Joinville",    "8179", "DOB001", "Dia 20 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Não"),
    ("ISS Curitibanos",  "8093", "DOB001", "Dia 20 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Sim"),
    ("ISS Araranguá",    "8027", "DOB001", "Dia 20 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Sim"),
    ("ISS Barra do Sul", "5549", "DOB001", "Dia 10 mês posterior — dia útil Fpolis", "Emissão mais antiga das NFs", "Sim"),
    ("ISS Gov. Celso Ramos", "8465", "DOB001", "Dia 20 do mesmo mês — dia útil", "Emissão mais antiga das NFs", "Sim"),
]


def _texto_bool(value) -> str:
    texto = str(value or "").strip().lower()
    return "Sim" if texto in {"1", "sim", "s", "true", "lf", "yes"} else "Não"


def _dia_padrao_codigo(codigo: str) -> int | None:
    codigo = str(codigo or "").strip()
    if codigo in _VENCE_DIA_10:
        return 10
    if codigo in _VENCE_DIA_20:
        return 20
    return 20 if codigo else None


def _regra_default_dicts() -> list[dict[str, str]]:
    return [
        {
            "imposto": str(imposto),
            "codigo": str(codigo),
            "siafi": str(siafi),
            "dia": "" if "informado pelo usuário" in str(regra_apuracao).lower() else str(_dia_padrao_codigo(codigo) or ""),
            "mes": "atual" if str(codigo) == "8465" else "seguinte",
            "apuracao": str(regra_apuracao),
            "lf": _texto_bool(lf),
        }
        for imposto, codigo, siafi, _regra_vencimento, regra_apuracao, lf in TABELA_GENERICA
    ]


def _normalizar_regras_rows(rows: list[dict]) -> list[dict[str, str]]:
    regras: list[dict[str, str]] = []
    for row in rows or []:
        mes = str((row or {}).get("mes", (row or {}).get("mesVencimento", ""))).strip().lower()
        if mes not in {"atual", "seguinte"}:
            mes = "atual" if str((row or {}).get("codigo", "")).strip() == "8465" else "seguinte"
        regra = {
            "imposto": str((row or {}).get("imposto", "")).strip(),
            "codigo": str((row or {}).get("codigo", "")).strip(),
            "siafi": _normalizar_siafi(str((row or {}).get("siafi", "")).strip()),
            "dia": str((row or {}).get("dia", "")).strip(),
            "mes": mes,
            "apuracao": str((row or {}).get("apuracao", "")).strip(),
            "ajusteDiaNaoUtil": str((row or {}).get("ajusteDiaNaoUtil", (row or {}).get("ajuste_dia_nao_util", "antecipar"))).strip().lower(),
            "lf": _texto_bool((row or {}).get("lf", "")),
        }
        if regra["ajusteDiaNaoUtil"] not in {"antecipar", "prorrogar", "manter"}:
            regra["ajusteDiaNaoUtil"] = "antecipar"
        if any(regra.values()):
            regras.append(regra)
    return regras


def obter_regras_datas_impostos() -> list[dict[str, str]]:
    """
    Retorna as regras efetivas de datas, unificando defaults, overrides antigos
    e regras completas salvas pela interface web.
    """
    regras_remotas = _carregar_regras_remotas()
    if regras_remotas:
        return regras_remotas

    config = carregar_tabelas_config()
    regras_salvas = config.get("datas_impostos_regras", [])

    if regras_salvas:
        regras = _normalizar_regras_rows(regras_salvas)
        if regras:
            return regras

    overrides = {
        str(chave): int(valor)
        for chave, valor in config.get("datas_impostos_overrides", {}).items()
        if str(valor).strip()
    }

    regras = _regra_default_dicts()
    for regra in regras:
        codigo = regra.get("codigo", "")
        if codigo in overrides:
            regra["dia"] = str(overrides[codigo])
    return regras


def _regra_por_codigo(codigo: str) -> dict[str, str]:
    codigo_limpo = str(codigo or "").strip()
    for regra in obter_regras_datas_impostos():
        if str(regra.get("codigo", "")).strip() == codigo_limpo:
            return regra
    return {}


def obter_mapa_codigo_siafi() -> dict[str, str]:
    mapa = dict(CODIGO_SIAFI)
    for regra in obter_regras_datas_impostos():
        codigo = str(regra.get("codigo", "") or "").strip()
        siafi = _normalizar_siafi(str(regra.get("siafi", "") or "").strip())
        if codigo and siafi:
            mapa[codigo] = siafi
    return mapa


# ─────────────────────────────────────────────────────────────────────────────
# CÁLCULO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def _mes_posterior_dia(data_ref: date, dia: int) -> date:
    """Retorna o 'dia' do mês seguinte a 'data_ref'."""
    mes  = data_ref.month + 1
    ano  = data_ref.year
    if mes > 12:
        mes = 1
        ano += 1
    # Garante que o dia existe no mês (ex: dia 31 em mês de 30 dias)
    import calendar
    ultimo = calendar.monthrange(ano, mes)[1]
    dia    = min(dia, ultimo)
    return date(ano, mes, dia)


def _mes_atual_dia(data_ref: date, dia: int) -> date:
    """Retorna o 'dia' do mesmo mês de data_ref."""
    import calendar
    ultimo = calendar.monthrange(data_ref.year, data_ref.month)[1]
    return date(data_ref.year, data_ref.month, min(dia, ultimo))


def _parse_data(s: str):
    """Converte string DD/MM/AAAA para date. Retorna None se inválido."""
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            from datetime import datetime
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _data_mais_antiga(datas_str: list) -> date:
    """Retorna a data mais antiga de uma lista de strings DD/MM/AAAA."""
    validas = [d for d in (_parse_data(s) for s in datas_str) if d]
    return min(validas) if validas else None


def _dia_vencimento(codigo: str, overrides: dict = None) -> int:
    """
    Retorna o dia do mês de vencimento para o código, respeitando overrides do usuário.
    Padrão: 20 para _VENCE_DIA_20, 10 para _VENCE_DIA_10, 20 para fallback.
    """
    if overrides and codigo in overrides:
        return int(overrides[codigo])
    if codigo in _VENCE_DIA_20:
        return 20
    if codigo in _VENCE_DIA_10:
        return 10
    return 20   # fallback genérico


def calcular_datas(
    codigo: str,
    datas_emissao_nf: list,
    vencimento_usuario: str = "",
    apuracao_usuario: str   = "",
    overrides_dia: dict     = None,
    regra: dict | None      = None,
) -> dict:
    """
    Calcula vencimento e apuração para um código de imposto.

    Parâmetros:
        codigo              – código do imposto (ex: "1162", "8105")
        datas_emissao_nf    – lista de strings DD/MM/AAAA das NFs
        vencimento_usuario  – data informada na tela inicial (para DDF055)
        apuracao_usuario    – data informada na tela inicial (para DDF055)
        overrides_dia       – dict {codigo: dia_int} com sobrescrições do usuário;
                              se None, carrega automaticamente de tabelas_config.json

    Retorna dict com:
        vencimento   – str DD/MM/AAAA
        apuracao     – str DD/MM/AAAA
        siafi        – situação SIAFI
        precisa_lf   – bool
        descricao    – nome do imposto
        dia_venc     – int (dia configurado de vencimento, p/ exibição)
    """
    if overrides_dia is None:
        overrides_dia = _carregar_overrides_dia()

    regra = regra or _regra_por_codigo(codigo)
    siafi = _normalizar_siafi(str(regra.get("siafi", "") or CODIGO_SIAFI.get(codigo, "")).strip())
    descricao = str(regra.get("imposto", "") or DESCRICAO_CODIGO.get(codigo, codigo)).strip()
    precisa_lf = siafi == "DOB001" and _texto_bool(regra.get("lf", "Não")) == "Sim"
    apuracao_regra = str(regra.get("apuracao", "")).strip().lower()
    dia_regra = str(regra.get("dia", "")).strip()

    # DDF055: usa datas do usuário
    if siafi == "DDF055" or "informado pelo usuário" in apuracao_regra:
        return {
            "vencimento":  vencimento_usuario,
            "apuracao":    apuracao_usuario,
            "siafi":       siafi,
            "precisa_lf":  precisa_lf,
            "descricao":   descricao,
            "dia_venc":    int(dia_regra) if dia_regra.isdigit() else None,
        }

    # Para os demais (DDF050, DDR001, DOB001): usa data mais antiga das NFs
    data_ref = _data_mais_antiga(datas_emissao_nf)
    if not data_ref:
        return {
            "vencimento":  "",
            "apuracao":    "",
            "siafi":       siafi,
            "precisa_lf":  precisa_lf,
            "descricao":   descricao,
            "dia_venc":    int(dia_regra) if dia_regra.isdigit() else _dia_vencimento(codigo, overrides_dia),
        }

    apuracao_date = data_ref
    dia = int(dia_regra) if dia_regra.isdigit() else _dia_vencimento(codigo, overrides_dia)
    mes_regra = str(regra.get("mes", "") or "").strip().lower()
    if mes_regra == "atual" or (not mes_regra and codigo == "8465"):
        alvo = _mes_atual_dia(data_ref, dia)
    else:
        alvo = _mes_posterior_dia(data_ref, dia)
    ajuste_dia_nao_util = str(regra.get("ajusteDiaNaoUtil") or regra.get("ajuste_dia_nao_util") or "antecipar").strip().lower()
    if ajuste_dia_nao_util not in {"antecipar", "prorrogar", "manter"}:
        ajuste_dia_nao_util = "antecipar"
    vencimento_date = ajustar_dia_nao_util(alvo, ajuste_dia_nao_util)
    if vencimento_date == alvo:
        ajuste_observacao = "Data original mantida."
    elif vencimento_date < alvo:
        ajuste_observacao = f"Antecipado do dia {alvo.strftime('%d/%m/%Y')} para o dia útil anterior."
    else:
        ajuste_observacao = f"Prorrogado do dia {alvo.strftime('%d/%m/%Y')} para o próximo dia útil."

    return {
        "vencimento":  vencimento_date.strftime("%d/%m/%Y"),
        "apuracao":    apuracao_date.strftime("%d/%m/%Y"),
        "siafi":       siafi,
        "precisa_lf":  precisa_lf,
        "descricao":   descricao,
        "dia_venc":    dia,
        "data_original_vencimento": alvo.strftime("%d/%m/%Y"),
        "ajuste_dia_nao_util": ajuste_dia_nao_util,
        "ajuste_observacao": ajuste_observacao,
    }


def calcular_datas_documento(dados: dict, vencimento_usuario="", apuracao_usuario="") -> dict:
    """
    Calcula as datas de todos os impostos presentes em um documento extraído.

    Parâmetros:
        dados              – dict retornado pelo extrator (contém 'Deduções' e 'Notas Fiscais')
        vencimento_usuario – data de vencimento DDF055 informada pelo usuário
        apuracao_usuario   – data de apuração DDF055 informada pelo usuário

    Retorna dict { codigo → resultado_calcular_datas }
    """
    deds  = dados.get("Deduções", [])
    notas = dados.get("Notas Fiscais", [])
    datas_emissao = [n.get("Data de Emissão", "") for n in notas]

    # Carrega overrides uma única vez para todo o documento
    overrides_dia = _carregar_overrides_dia()

    regras_por_codigo = {
        str(regra.get("codigo", "")).strip(): regra
        for regra in obter_regras_datas_impostos()
        if str(regra.get("codigo", "")).strip()
    }

    resultado = {}
    for d in deds:
        codigo = d.get("Código", "").strip().lstrip("0") or d.get("Código", "").strip()
        # Normaliza para sem zeros à esquerda apenas se < 5 dígitos
        if len(codigo) <= 4:
            codigo = codigo.lstrip("0") or "0"
        if not codigo or codigo == "—":
            continue
        if codigo not in resultado:
            resultado[codigo] = calcular_datas(
                codigo, datas_emissao, vencimento_usuario, apuracao_usuario,
                overrides_dia=overrides_dia,
                regra=regras_por_codigo.get(codigo),
            )

    return resultado


def ajustar_data_util(data_str: str) -> tuple:
    """
    Recebe uma data no formato DD/MM/AAAA.
    Se for fim de semana ou feriado (Fpolis), recua para o dia útil anterior.
    Retorna (data_ajustada_str, foi_ajustada: bool).
    Exemplo: '19/04/2026' (sábado) → ('17/04/2026', True).
    """
    from datetime import datetime
    if not data_str:
        return data_str, False
    try:
        d = datetime.strptime(data_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return data_str, False
    ajustado = dia_util_anterior_ou_igual(d)
    foi = (ajustado != d)
    return ajustado.strftime("%d/%m/%Y"), foi


def dias_uteis_ate(data_alvo_str: str) -> int:
    """
    Conta quantos dias úteis (Florianópolis) há entre hoje e data_alvo_str (inclusive).
    Retorna valor negativo se a data já passou.
    Aceita formato DD/MM/AAAA.
    """
    from datetime import datetime
    if not data_alvo_str:
        return 999
    try:
        alvo = datetime.strptime(data_alvo_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return 999

    hoje = date.today()
    if alvo < hoje:
        return -1

    feriados = feriados_ano(hoje.year)
    if alvo.year != hoje.year:
        feriados |= feriados_ano(alvo.year)

    contagem = 0
    d = hoje
    while d <= alvo:
        if e_dia_util(d, feriados):
            contagem += 1
        d += timedelta(days=1)
    return contagem
