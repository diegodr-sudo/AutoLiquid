"""Servicos de suporte para configuracoes e tabelas consumidas pela UI web."""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import Any

from core.datas_impostos import TABELA_GENERICA, _VENCE_DIA_10, obter_regras_datas_impostos
from core.de_para_contratos import obter_arquivo_contratos, recarregar as recarregar_contratos
from services.config_service import (
    carregar_config_app,
    carregar_tabelas_config,
    salvar_config_app,
    salvar_tabelas_config,
)

log = logging.getLogger(__name__)
_CONTRATOS_TURSO_SYNC_AT = 0.0

WEB_THEME_VALUES = {"light", "dark", "system"}
WEB_NIVEL_LOG_VALUES = {"desenvolvedor"}
WEB_NAVEGADOR_VALUES = {"chrome", "edge"}


def fonte_dados_habilitada(tabela: str, provedor: str) -> bool:
    """Todos os dados usam Turso exclusivamente após migração completa."""
    _ = tabela  # mantido para não quebrar chamadas existentes
    return provedor == "turso"


def modo_banco_ativo() -> str:
    return "turso"

VPD_PADRAO = [["339030.01", "DSP 001", "3.3.2.3.X.04.00"]]

NAT_RENDIMENTO_PADRAO = [
    ("17001", "Alimentacao", "6147"),
    ("17002", "Energia eletrica", "6147"),
    ("17003", "Servicos prestados com emprego de materiais", "6147"),
    ("17004", "Construcao Civil por empreitada com emprego de materiais", "6147"),
    ("17005", "Servicos hospitalares de que trata o art. 30 da IN RFB 1.234/2012", "6147"),
    ("17006", "Transporte de cargas", "6147"),
    ("17007", "Servicos de auxilio diagnostico e terapia", "6147"),
    ("17008", "Produtos farmaceuticos, perfumaria, toucador ou higiene pessoal", "6147"),
    ("17009", "Mercadorias e bens em geral", "6147"),
    ("17010", "Gasolina, oleo diesel, gas liquefeito de petroleo (GLP)", "9060"),
    ("17011", "Alcool etilico hidratado, inclusive para fins carburantes", "9060"),
    ("17012", "Biodiesel adquirido de produtor ou importador", "9060"),
    ("17013", "Gasolina, exceto gasolina de aviacao, oleo diesel e GLP", "8739"),
    ("17014", "Alcool etilico hidratado nacional para fins carburantes (varejista)", "8739"),
    ("17015", "Biodiesel adquirido de distribuidores e comerciantes varejistas", "8739"),
    ("17016", "Biodiesel produtor detentor selo Combustivel Social", "8739"),
    ("17017", "Transporte internacional de cargas efetuado por empresas nacionais", "8767"),
    ("17018", "Estaleiros navais brasileiros", "8767"),
    ("17019", "Produtos de perfumaria, toucador e higiene pessoal", "8767"),
    ("17020", "Produtos a que se refere o paragrafo 2 do art. 22 da IN RFB 1.234/2012", "8767"),
    ("17021", "Produtos das alineas c a k do art. 5 da IN RFB 1.234/2012", "8767"),
    ("17022", "Outros prod./serv. com isencao, nao incidencia ou aliquotas zero", "8767"),
    ("17023", "Passagens aereas, rodov. e demais serv. de transporte de passageiros", "6175"),
    ("17024", "Transporte internacional de passageiros efetuado por empresas nacionais", "8850"),
    ("17025", "Servicos prestados por associacoes profissionais ou assemelhadas", "8863"),
    ("17026", "Servicos prestados por bancos comerciais, bancos de investimento", "6188"),
    ("17027", "Seguro Saude", "6188"),
    ("17028", "Servicos de abastecimento de agua", "6190"),
    ("17029", "Telefone", "6190"),
    ("17030", "Correio e telegrafos", "6190"),
    ("17031", "Vigilancia", "6190"),
    ("17032", "Limpeza", "6190"),
    ("17033", "Locacao de mao de obra", "6190"),
    ("17034", "Intermediacao de negocios", "6190"),
    ("17035", "Administracao, locacao ou cessao de bens imoveis, moveis e direitos", "6190"),
    ("17036", "Factoring", "6190"),
    ("17037", "Plano de saude humano, veterinario ou odontologico", "6190"),
    ("17038", "Pagamento a sociedade cooperativa pelo fornecimento de bens", "8863"),
    ("17040", "Servicos por associacoes profissionais (emprego de materiais)", "6147"),
    ("17041", "Servicos por associacoes profissionais (demais servicos)", "6190"),
    ("17042", "Pagamentos as associacoes e cooperativas medicas/odontologicas", "6190"),
    ("17043", "Pagamento a sociedade cooperativa de producao", "6147"),
    ("17046", "Pagamento efetuado na aquisicao de bem imovel - art. 23 I", "6147"),
    ("17047", "Pagamento efetuado na aquisicao de bem imovel - art. 23 II", "8767"),
    ("17049", "Propaganda e Publicidade em desconformidade com o art. 16", "6190"),
    ("17050", "Propaganda e Publicidade em conformidade com o art. 16", "8863"),
    ("17099", "Demais servicos", "6190"),
]

FONTES_RECURSO_PADRAO = [
    ("1050000394", ""),
    ("1051000394", ""),
    ("0150153163", ""),
    ("0150262460", ""),
    ("0250153163", ""),
    ("0250262460", ""),
    ("0263262460", ""),
    ("0280153163", ""),
    ("8150262460", ""),
    ("8250262740", ""),
    ("8280153163", ""),
    ("8650262460", ""),
    ("8180153163", ""),
]

UORG_PADRAO = [
    ("151245", "251831", "CAMPUS UNIVERSITARIO DE ARARANGUA"),
    ("151246", "109918", "CAMPUS UNIVERSITARIO DE JOINVILLE"),
    ("151247", "251730", "CAMPUS UNIVERSITARIO DE CURITIBANOS"),
    ("153169", "26075", "GABINETE DO REITOR"),
    ("153170", "26115", "PRO-REITORIA DE DESEN GESTAO PESSOAS"),
    ("153171", "26115", "PRO-REITORIA DE DESEN GESTAO PESSOAS - DRH"),
    ("153415", "301347", "DEPARTAMENTO DE MANUTENCAO EXTERNA"),
    ("153416", "97298", "SECRETARIA DE RELACOES INTERNACIONAIS"),
    ("153417", "301236", "PRO-REITORIA DE GRADUACAO E EDUCACAO BASICA"),
    ("153419", "301236", "PROGRAD/UFSC - BOLSA MONITORIA"),
    ("153420", "301236", "PROGRAD/UFSC - BOLSA ESTAGIO"),
    ("153421", "251270", "COLEGIO DE APLICACAO DA UFSC"),
    ("153422", "200750", "CAMPUS UNIVERSITARIO DE BLUMENAU"),
    ("153424", "250970", "BIBLIOTECA UNIVERSITARIA DA UFSC"),
    ("153425", "206550", "BIOTERIO CENTRAL DA UFSC"),
    ("153426", "301230", "PRO-REITORIA DE ASSUNTOS ESTUDANTIS"),
    ("153428", "301230", "PRAE/UFSC - BOLSA"),
    ("153429", "85460", "RESTAURANTE UNIVERSITARIO DA UFSC"),
    ("153430", "84217", "PRO-REITORIA DE POS-GRADUACAO"),
    ("153431", "84217", "PROPG/UFSC - PROF"),
    ("153432", "301233", "PRO-REITORIA DE PESQUISA E INOVACAO"),
    ("153433", "301233", "PROPESQ/UFSC - BOLSA PIBIC"),
    ("153434", "119942", "PRO-REITORIA DE EXTENSAO"),
    ("153435", "14892", "CENTRO DE CIENCIA DA SAUDE DA UFSC"),
    ("153436", "14894", "CENTRO TECNOLOGICO DA UFSC"),
    ("153437", "14957", "CENTRO SOCIO-ECONOMICO DA UFSC"),
    ("153438", "14994", "CENTRO DE CIENCIAS DA EDUCACAO DA UFSC"),
    ("153439", "14668", "CENTRO DE CIENCIAS BIOLOGICAS DA UFSC"),
    ("153440", "15004", "CENTRO DE CIENCIA AGRARIAS DA UFSC"),
    ("153441", "15056", "CENTRO DE DESPORTOS DA UFSC"),
    ("153442", "26293", "CENTRO DE CIENCIA JURIDICAS DA UFSC"),
    ("153443", "14726", "CENTRO DE COMUNICACAO E EXPRESSAO DA UFSC"),
    ("153444", "14675", "CENTRO DE CIENCIA FISICAS E MATEMATICAS-UFSC"),
    ("153445", "14723", "CENTRO DE CIENCIA HUMANAS DA UFSC"),
    ("153446", "97297", "SECRETARIA DE PLANEJAMENTO E ORCAMENTO"),
    ("153447", "206594", "SUP DE GOVERNANCA ELETRONICA E TIC"),
    ("153771", "26114", "PRO-REITORIA DE ADMINISTRACAO"),
    ("153772", "250743", "PREFEITURA UNIVERSITARIA"),
    ("153773", "51095", "DEPARTAMENTO DE COMPRAS"),
    ("153774", "423069", "DEPARTAMENTO DE CONTRATOS"),
    ("153806", "301245", "SECRETARIA DE CULTURA, ARTE E ESPORTE"),
    ("153809", "119942", "PROEX/UFSC - BOLSA"),
    ("153810", "60377", "NUCLEO DE DESENVOLVIMENTO INFANTIS DA UFSC"),
    ("153930", "250764", "DEPARTAMENTO DE FISCALIZACAO DE OBRAS"),
    ("155937", "251511", "DEPARTAMETNO DE INOVACAO"),
    ("155938", "301269", "DEPARTAMENTO DE ESPORTE, CULTURA E LAZER"),
    ("155939", "301240", "PRO-REITORIA DE ACOES AFIRMATIVAS E EQUIDADES"),
    ("156188", "218792", "SECRETARIA DE EDUCACAO A DISTANCIA"),
    ("156982", "251421", "COORDENADORIA DE GESTAO AMBIENTAL"),
    ("156983", "301251", "SECRETARIA DE COMUNICACAO"),
    ("156984", "218795", "SECRETARIA DE SEGURANCA INSTITUCIONAL"),
    ("157024", "251422", "MUSEU DE ARQ E ETNOLOGIA"),
    ("157026", "251425", "EDITORA UNIVERSITARIA"),
    ("157465", "423109", "DEPARTAMENTO DE GESTAO DE BENS PERMANT."),
]

NCM_PADRAO: list[tuple[str, ...]] = [
    # (ncm, descricao, codigo, obs)
    ("0201...", "Carne e produtos origem animal", "8767", ""),
    ("0202....", "Carne e produtos origem animal", "8767", ""),
    ("0203...", "Carne e produtos origem animal", "8767", ""),
    ("0204...", "Carne e produtos origem animal", "8767", ""),
    ("0207...", "Carne e produtos origem animal", "8767", ""),
    ("0209...", "Carne e produtos origem animal", "8767", ""),
    ("0302...", "Peixes (exceto 03029000)", "8767", ""),
    ("0303...", "Peixes", "8767", ""),
    ("0304...", "Peixes", "8767", ""),
    ("02102000", "Charque", "8767", ""),
    ("04012010", "Leite UHT", "8767", ""),
    ("04014020", "Creme de Leite", "6147", ""),
    ("04015021", "Creme de Leite", "6147", ""),
    ("04032000", "Iogurte Natural", "8767", ""),
    ("0407...", "Ovos", "8767", ""),
    ("0511...", "Sementes", "8767", ""),
    ("07...", "Horticolas e frutas", "8767", ""),
    ("08...", "Horticolas e frutas", "8767", ""),
    ("0901...", "Cafe", "8767", ""),
    ("100620...", "Arroz", "8767", ""),
    ("100630...", "Arroz", "8767", ""),
    ("110220...", "Farinha", "8767", ""),
    ("110313...", "Semolas", "8767", ""),
    ("110419...", "Graos de milho", "8767", ""),
    ("11042300", "Canjica branca", "6147", ""),
    ("110620..", "Farinhas", "8767", ""),
    ("12119090", "Manjericao", "6147", ""),
    ("1507...", "Oleo de Soja", "8767", ""),
    ("15092000", "Azeite de Oliva", "8767", ""),
    ("1508...", "Oleo vegetal", "8767", ""),
    ("1514...", "Oleo vegetal", "8767", ""),
    ("16010000", "Linguica", "6147", ""),
    ("16023220", "Frango Empanado", "6147", ""),
    ("16025000", "Almondega", "6147", ""),
    ("16041390", "Peixe Empanado", "6147", ""),
    ("17011400", "Acucar", "8767", ""),
    ("17019900", "Acucar", "8767", ""),
    ("18069000", "Bombom", "6147", ""),
    ("19021900", "Massa", "8767", ""),
    ("19059090", "Pao", "8767", ""),
    ("19051090", "Pao com especiarias", "8767", ""),
    ("20029000", "Extrato de tomate", "6147", ""),
    ("20054000", "Ervilha em lata", "6147", ""),
    ("20058000", "Milho em lata", "6147", ""),
    ("20087010", "Pessego em lata", "6147", ""),
    ("20091200", "Suco de Laranja", "6147", ""),
    ("21011...", "Cafe", "8767", ""),
    ("21032090", "Catchup", "6147", ""),
    ("21033021", "Mostarda", "6147", ""),
    ("21039091", "Molho Barbecue", "6147", ""),
    ("21069029", "Gelatina", "6147", ""),
    ("22029900", "Leite de Aveia", "6147", ""),
    ("2203...", "Cerveja", "8767", ""),
    ("22071090", "Alcool", "6147", ""),
    ("22072019", "Alcool", "6147", ""),
    ("22090000", "Vinagre branco alcool", "6147", ""),
    ("25010020", "Sal", "6147", ""),
    ("30039099", "Clorexidina", "6147", ""),
    ("31052000", "Fertilizantes", "8767", ""),
    ("39269040", "Artigos laboratorio/farmacia", "8767", ""),
    ("49019900", "Livros", "8767", ""),
    ("40151...", "Luvas", "8767", "Se vier da saude. Se nao, codigo 6147"),
]

TABLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "contratos": {
        "label": "Contratos",
        "description": "Mapeamento SARF para IG usado na conferencia do contrato.",
        "search_placeholder": "Buscar por SARF, IG, CNPJ ou Razao Social...",
        "columns": [
            {"key": "sarf", "label": "SARF", "editable": True},
            {"key": "ig", "label": "IG", "editable": True},
            {"key": "cnpj", "label": "CNPJ", "editable": True},
            {"key": "razaoSocial", "label": "Razao Social", "editable": True},
        ],
    },
    "vpd": {
        "label": "VPD",
        "description": "Conta de variacao patrimonial diminutiva por natureza e situacao DSP.",
        "search_placeholder": "Buscar por Natureza, Situacao DSP ou VPD...",
        "columns": [
            {"key": "natureza", "label": "Natureza (DE)", "editable": True},
            {"key": "situacaoDsp", "label": "Situacao DSP", "editable": True},
            {"key": "vpd", "label": "VPD (PARA)", "editable": True},
        ],
    },
    "vpd-especiais": {
        "label": "VPDs Especiais",
        "description": "Mapeamentos especiais e referencias complementares, como DETER, CREA, Bombeiro e Contrato.",
        "search_placeholder": "Buscar por grupo, conta de origem, conta destino ou descricao...",
        "columns": [
            {"key": "grupo", "label": "Grupo", "editable": True},
            {"key": "codigoOrigem", "label": "Conta Origem", "editable": True},
            {"key": "codigoDestino", "label": "Conta Destino", "editable": True},
            {"key": "descricao", "label": "Descricao", "editable": True},
        ],
    },
    "uorg": {
        "label": "UORG",
        "description": "Relacionamento entre UGR, UORG e unidade responsavel.",
        "search_placeholder": "Buscar por UGR, UORG ou nome...",
        "columns": [
            {"key": "ugr", "label": "UGR", "editable": True},
            {"key": "uorg", "label": "UORG", "editable": True},
            {"key": "nome", "label": "Nome", "editable": True},
        ],
    },
    "nat-rendimento": {
        "label": "Nat. Rendimento",
        "description": "Naturezas de rendimento e seus codigos DARF.",
        "search_placeholder": "Buscar por codigo, descricao ou DARF...",
        "columns": [
            {"key": "codigo", "label": "Codigo", "editable": True},
            {"key": "naturezaRendimento", "label": "Natureza Rendimento", "editable": True},
            {"key": "codigoDarf", "label": "Cod. DARF", "editable": True},
        ],
    },
    "fontes-recurso": {
        "label": "Fontes Recurso",
        "description": "",
        "search_placeholder": "Buscar por fonte ou descricao...",
        "columns": [
            {"key": "fonteRecurso", "label": "Fonte Recurso", "editable": True},
            {"key": "descricao", "label": "Descricao", "editable": True},
        ],
    },
    "datas-impostos": {
        "label": "Datas",
        "description": "Regras reais de vencimento, apuracao e excecoes por codigo e municipio. Adicione novas linhas quando um municipio ou DARF novo entrar no fluxo.",
        "search_placeholder": "Buscar por municipio, codigo DARF, SIAFI ou regra...",
        "columns": [
            {"key": "imposto", "label": "Imposto / Municipio", "editable": True},
            {"key": "codigo", "label": "Codigo", "editable": True},
            {"key": "siafi", "label": "SIAFI", "editable": True},
            {"key": "dia", "label": "Dia de Venc.", "editable": True},
            {"key": "apuracao", "label": "Regra de Apuracao", "editable": True},
            {"key": "lf", "label": "Pede LF?", "editable": True},
        ],
    },
    "ncm": {
        "label": "NCM",
        "description": "Codigos NCM e seus respectivos codigos de retencao (DARF). Usado na conferencia de impostos sobre produtos.",
        "search_placeholder": "Buscar por NCM, descricao ou codigo DARF...",
        "columns": [
            {"key": "ncm", "label": "NCM", "editable": True},
            {"key": "descricao", "label": "Descricao", "editable": True},
            {"key": "codigo", "label": "Codigo DARF", "editable": True},
            {"key": "obs", "label": "Observacao", "editable": True},
        ],
    },
}


def _sanitize_text(value: Any) -> str:
    return str(value or "").strip()


def _column_keys(table_key: str) -> list[str]:
    return [str(coluna.get("key") or "").strip() for coluna in TABLE_DEFINITIONS[table_key]["columns"]]


def _normalize_table_rows(table_key: str, rows: list[dict[str, Any]] | list[list[Any]] | None) -> list[dict[str, str]]:
    keys = _column_keys(table_key)
    normalized: list[dict[str, str]] = []
    for raw_row in rows or []:
        if isinstance(raw_row, dict):
            row = {key: _sanitize_text(raw_row.get(key)) for key in keys}
        elif isinstance(raw_row, (list, tuple)):
            row = {
                key: _sanitize_text(raw_row[idx] if idx < len(raw_row) else "")
                for idx, key in enumerate(keys)
            }
        else:
            continue
        if any(row.values()):
            normalized.append(row)
    return normalized


def _filter_rows(rows: list[dict[str, str]], search: str) -> list[dict[str, str]]:
    termo = search.strip().lower()
    if not termo:
        return rows
    return [
        row
        for row in rows
        if termo in " ".join(_sanitize_text(valor).lower() for valor in row.values())
    ]


def _load_contract_rows() -> list[dict[str, str]]:
    caminho = Path(obter_arquivo_contratos())
    if not caminho.exists():
        return []

    rows: list[dict[str, str]] = []
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        primeira = arquivo.readline()
        if "SARF" in primeira.upper():
            arquivo.seek(0)
        reader = csv.DictReader(arquivo)
        for row in reader:
            rows.append(
                {
                    "sarf": _sanitize_text(row.get("SARF")),
                    "ig": _sanitize_text(row.get("IG")),
                    "cnpj": _sanitize_text(row.get("CNPJ")),
                    "razaoSocial": _sanitize_text(
                        row.get("RAZAO SOCIAL") or row.get("RAZÃO SOCIAL") or row.get("RAZ\u00c3O SOCIAL")
                    ),
                }
            )
    if not rows:
        try:
            recarregar_contratos()
            caminho = Path(obter_arquivo_contratos())
            with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
                primeira = arquivo.readline()
                if "SARF" in primeira.upper():
                    arquivo.seek(0)
                reader = csv.DictReader(arquivo)
                for row in reader:
                    rows.append(
                        {
                            "sarf": _sanitize_text(row.get("SARF")),
                            "ig": _sanitize_text(row.get("IG")),
                            "cnpj": _sanitize_text(row.get("CNPJ")),
                            "razaoSocial": _sanitize_text(
                                row.get("RAZAO SOCIAL") or row.get("RAZÃO SOCIAL") or row.get("RAZ\u00c3O SOCIAL")
                            ),
                        }
                    )
        except Exception:
            pass
    return rows


def _save_contract_rows(rows: list[dict[str, Any]]) -> None:
    caminho = Path(obter_arquivo_contratos())
    linha_instrucao = ""
    if caminho.exists():
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            primeira = arquivo.readline()
            if "SARF" not in primeira.upper():
                linha_instrucao = primeira.rstrip("\n\r")

    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        writer = csv.writer(arquivo)
        if linha_instrucao:
            arquivo.write(linha_instrucao + "\n")
        writer.writerow(["SARF", "IG", "CNPJ", "RAZAO SOCIAL"])
        for row in rows:
            valores = [
                _sanitize_text(row.get("sarf")),
                _sanitize_text(row.get("ig")),
                _sanitize_text(row.get("cnpj")),
                _sanitize_text(row.get("razaoSocial")),
            ]
            if any(valores):
                writer.writerow(valores)

    recarregar_contratos()


def _rows_from_config(config_key: str, keys: list[str], default_rows: list[tuple[str, ...]] | list[list[str]]) -> list[dict[str, str]]:
    dados = carregar_tabelas_config()
    lista = dados.get(config_key, default_rows)
    if not lista:
        lista = default_rows
    rows: list[dict[str, str]] = []
    for row in lista:
        row_lista = list(row)
        rows.append(
            {
                chave: _sanitize_text(row_lista[idx] if idx < len(row_lista) else "")
                for idx, chave in enumerate(keys)
            }
        )
    return rows


def _save_rows_to_config(config_key: str, keys: list[str], rows: list[dict[str, Any]]) -> None:
    dados = carregar_tabelas_config()
    dados[config_key] = [
        [_sanitize_text(row.get(chave)) for chave in keys]
        for row in rows
        if any(_sanitize_text(row.get(chave)) for chave in keys)
    ]
    salvar_tabelas_config(dados)


def _load_datas_impostos_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in obter_regras_datas_impostos():
        rows.append(
            {
                "imposto": _sanitize_text(row.get("imposto")),
                "codigo": _sanitize_text(row.get("codigo")),
                "siafi": _sanitize_text(row.get("siafi")),
                "dia": _sanitize_text(row.get("dia")),
                "apuracao": _sanitize_text(row.get("apuracao")),
                "lf": _sanitize_text(row.get("lf")),
            }
        )
    return rows


def _save_datas_impostos_rows(rows: list[dict[str, Any]]) -> None:
    regras_normalizadas: list[dict[str, str]] = []
    overrides: dict[str, int] = {}
    for row in rows:
        codigo = _sanitize_text(row.get("codigo"))
        imposto = _sanitize_text(row.get("imposto"))
        siafi = _sanitize_text(row.get("siafi")).upper()
        apuracao = _sanitize_text(row.get("apuracao"))
        lf = _sanitize_text(row.get("lf")) or "Não"
        dia_texto = _sanitize_text(row.get("dia"))

        if not any([codigo, imposto, siafi, dia_texto, apuracao, lf]):
            continue
        regra = {
            "imposto": imposto,
            "codigo": codigo,
            "siafi": siafi,
            "dia": dia_texto,
            "apuracao": apuracao,
            "lf": lf,
        }
        regras_normalizadas.append(regra)

        if codigo:
            dia_padrao = 10 if codigo in _VENCE_DIA_10 else 20
            try:
                dia = int(dia_texto or dia_padrao)
            except ValueError:
                continue
            if dia != dia_padrao:
                overrides[codigo] = dia

    dados = carregar_tabelas_config()
    dados["datas_impostos_regras"] = regras_normalizadas
    dados["datas_impostos_overrides"] = overrides
    salvar_tabelas_config(dados)


def _carregar_tabela_local(table_key: str) -> list[dict[str, str]]:
    if table_key == "contratos":
        rows = _load_contract_rows()
    elif table_key == "vpd":
        rows = _rows_from_config("vpd_lista", ["natureza", "situacaoDsp", "vpd"], VPD_PADRAO)
    elif table_key == "vpd-especiais":
        rows = _rows_from_config(
            "vpd_especiais_lista",
            ["grupo", "codigoOrigem", "codigoDestino", "descricao"],
            [],
        )
    elif table_key == "uorg":
        rows = _rows_from_config("uorg_lista", ["ugr", "uorg", "nome"], UORG_PADRAO)
    elif table_key == "nat-rendimento":
        rows = _rows_from_config(
            "nat_rendimento_lista",
            ["codigo", "naturezaRendimento", "codigoDarf"],
            NAT_RENDIMENTO_PADRAO,
        )
    elif table_key == "fontes-recurso":
        rows = _rows_from_config(
            "fontes_recurso_lista",
            ["fonteRecurso", "descricao"],
            FONTES_RECURSO_PADRAO,
        )
    elif table_key == "ncm":
        rows = _rows_from_config(
            "ncm_lista",
            ["ncm", "descricao", "codigo", "obs"],
            NCM_PADRAO,
        )
    else:
        rows = _load_datas_impostos_rows()
    return _normalize_table_rows(table_key, rows)


def _salvar_tabela_local(table_key: str, rows: list[dict[str, Any]]) -> None:
    if table_key == "contratos":
        _save_contract_rows(rows)
    elif table_key == "vpd":
        _save_rows_to_config("vpd_lista", ["natureza", "situacaoDsp", "vpd"], rows)
    elif table_key == "vpd-especiais":
        _save_rows_to_config(
            "vpd_especiais_lista",
            ["grupo", "codigoOrigem", "codigoDestino", "descricao"],
            rows,
        )
    elif table_key == "uorg":
        _save_rows_to_config("uorg_lista", ["ugr", "uorg", "nome"], rows)
    elif table_key == "nat-rendimento":
        _save_rows_to_config("nat_rendimento_lista", ["codigo", "naturezaRendimento", "codigoDarf"], rows)
    elif table_key == "fontes-recurso":
        _save_rows_to_config("fontes_recurso_lista", ["fonteRecurso", "descricao"], rows)
    elif table_key == "ncm":
        _save_rows_to_config("ncm_lista", ["ncm", "descricao", "codigo", "obs"], rows)
    else:
        _save_datas_impostos_rows(rows)


# Sentinela interno: diferencia "erro de conexão" de "linha não existe no Turso".
# Isso evita que um erro temporário de leitura dispare um bootstrap que
# sobrescreveria dados reais com os defaults locais.
class _ErroRemoto:
    pass

_ERRO_REMOTO = _ErroRemoto()


def _carregar_tabela_remota(table_key: str) -> list[dict[str, str]] | None | _ErroRemoto:
    """Retorna:
    - list   → dados carregados do Turso (pode ser [] se a linha existir vazia)
    - None   → Turso indisponível OU linha ainda não existe (bootstrap seguro)
    - _ERRO_REMOTO → falha de conexão/leitura (NÃO fazer bootstrap)
    """
    if fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            from services import turso_service

            if turso_service.turso_configurado():
                rows = turso_service.obter_tabela_operacional(table_key)
                if rows is not None:
                    return _normalize_table_rows(table_key, rows)
        except Exception:
            log.exception("Falha ao carregar tabela '%s' do Turso.", table_key)
            if modo_banco_ativo() == "turso":
                return _ERRO_REMOTO

    return None


def _salvar_tabela_remota(table_key: str, rows: list[dict[str, Any]]) -> bool:
    saved = False
    normalized = _normalize_table_rows(table_key, rows)
    if fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            from services import turso_service

            if turso_service.turso_configurado():
                turso_service.salvar_tabela_operacional(table_key, normalized)
                if table_key == "contratos":
                    turso_service.salvar_contratos_ic_de_para(normalized)
                saved = True
        except Exception:
            log.exception("Falha ao salvar tabela '%s' no Turso.", table_key)

    return saved


def _sincronizar_contratos_turso(rows: list[dict[str, Any]], *, force: bool = False) -> None:
    global _CONTRATOS_TURSO_SYNC_AT

    if not fonte_dados_habilitada("tabelas_operacionais", "turso"):
        return
    if not force and time.monotonic() - _CONTRATOS_TURSO_SYNC_AT < 600:
        return
    try:
        from services import turso_service

        if turso_service.turso_configurado():
            turso_service.salvar_contratos_ic_de_para(_normalize_table_rows("contratos", rows))
            _CONTRATOS_TURSO_SYNC_AT = time.monotonic()
    except Exception:
        log.exception("Falha ao sincronizar de/para Contrato → IC no Turso.")


def carregar_tabela_web(table_key: str, search: str = "") -> dict[str, Any]:
    if table_key not in TABLE_DEFINITIONS:
        raise KeyError(table_key)

    definition = TABLE_DEFINITIONS[table_key]
    storage = "local"
    remoto = _carregar_tabela_remota(table_key)

    if isinstance(remoto, _ErroRemoto):
        # Erro de conexão: usa local SEM bootstrap para não sobrescrever dados remotos
        rows = _carregar_tabela_local(table_key)
        storage = "local"
    elif remoto is None:
        # Turso indisponível ou linha ainda não existe: bootstrap seguro
        rows = _carregar_tabela_local(table_key)
        if _salvar_tabela_remota(table_key, rows):
            storage = "turso-bootstrap"
    else:
        rows = remoto
        storage = "turso"

    filtered_rows = _filter_rows(rows, search)
    return {
        "key": table_key,
        "label": definition["label"],
        "description": definition["description"],
        "searchPlaceholder": definition["search_placeholder"],
        "columns": definition["columns"],
        "rows": filtered_rows,
        "totalRows": len(filtered_rows),
        "fixedRows": bool(definition.get("fixed_rows", False)),
        "storage": storage,
    }


def salvar_tabela_web(table_key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if table_key not in TABLE_DEFINITIONS:
        raise KeyError(table_key)

    normalized_rows = _normalize_table_rows(table_key, rows)
    if not _salvar_tabela_remota(table_key, normalized_rows):
        _salvar_tabela_local(table_key, normalized_rows)
    if table_key == "contratos":
        _sincronizar_contratos_turso(normalized_rows, force=True)

    return carregar_tabela_web(table_key)


def _mapa_contratos_ic(rows: list[dict[str, Any]]) -> dict[str, str]:
    mapa: dict[str, str] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        sarf = str(row.get("sarf") or "").strip().upper()
        ig = str(row.get("ig") or "").strip()
        if sarf and ig:
            mapa[sarf] = ig
    return mapa


def carregar_contratos_ic_de_para(*, somente_local: bool = False) -> dict[str, str]:
    if somente_local:
        return _mapa_contratos_ic(_carregar_tabela_local("contratos"))

    tabela = carregar_tabela_web("contratos")
    mapa = _mapa_contratos_ic(tabela.get("rows") or [])
    if mapa:
        _sincronizar_contratos_turso(tabela.get("rows") or [])
        return mapa

    if fonte_dados_habilitada("tabelas_operacionais", "turso"):
        try:
            from services import turso_service

            if turso_service.turso_configurado():
                mapa.update(turso_service.obter_contratos_ic_de_para())
        except Exception:
            log.exception("Falha ao carregar de/para Contrato → IC do Turso.")
    return mapa


def carregar_configuracoes_web() -> dict[str, Any]:
    config = carregar_config_app()
    tema_web = _sanitize_text(config.get("tema_web") or "light").lower()
    if tema_web not in WEB_THEME_VALUES:
        tema_web = "light"

    try:
        chrome_porta = int(config.get("chrome_porta") or 9222)
    except (TypeError, ValueError):
        chrome_porta = 9222
    if not 1 <= chrome_porta <= 65535:
        chrome_porta = 9222

    nivel_log = "desenvolvedor"

    navegador = _sanitize_text(config.get("navegador") or "chrome").lower()
    if navegador not in WEB_NAVEGADOR_VALUES:
        navegador = "chrome"

    return {
        "chromePorta": chrome_porta,
        "fecharAbaFila": bool(config.get("fechar_aba_fila", False)),
        "perguntarLimparMes": bool(config.get("perguntar_limpar_mes", True)),
        "temaWeb": tema_web,
        "nivelLog": nivel_log,
        "navegador": navegador,
        "tursoDatabaseUrl": str(config.get("turso_database_url") or ""),
        "tursoAuthToken": str(config.get("turso_auth_token") or ""),
        "nomeUsuario": str(config.get("nome_usuario") or ""),
        "nfServicoAlertaDiasUteis": int(config.get("nf_servico_alerta_dias_uteis", 3) or 0),
        "rocketChatUrl": str(config.get("rocket_chat_url") or "https://chat.ufsc.br"),
        "rocketChatUserId": str(config.get("rocket_chat_user_id") or ""),
        "rocketChatAuthToken": str(config.get("rocket_chat_auth_token") or ""),
        "rocketChatContar": str(config.get("rocket_chat_contar") or "tudo"),
    }


def salvar_configuracoes_web(dados: dict[str, Any]) -> dict[str, Any]:
    import os

    tema_web = _sanitize_text(dados.get("temaWeb") or "light").lower()
    if tema_web not in WEB_THEME_VALUES:
        tema_web = "light"

    chrome_porta = dados.get("chromePorta", 9222)
    try:
        chrome_porta = int(chrome_porta)
    except (TypeError, ValueError) as exc:
        raise ValueError("Porta do Chrome invalida.") from exc

    if not 1 <= chrome_porta <= 65535:
        raise ValueError("Porta do Chrome deve ficar entre 1 e 65535.")

    nivel_log = "desenvolvedor"

    navegador = _sanitize_text(dados.get("navegador") or "chrome").lower()
    if navegador not in WEB_NAVEGADOR_VALUES:
        navegador = "chrome"

    turso_database_url = str(dados.get("tursoDatabaseUrl") or "").strip()
    turso_auth_token = str(dados.get("tursoAuthToken") or "").strip()
    nome_usuario = str(dados.get("nomeUsuario") or "").strip()
    rocket_chat_url = str(dados.get("rocketChatUrl") or "https://chat.ufsc.br").strip().rstrip("/")
    if rocket_chat_url and not rocket_chat_url.startswith(("http://", "https://")):
        rocket_chat_url = f"https://{rocket_chat_url}"
    rocket_chat_user_id = str(dados.get("rocketChatUserId") or "").strip()
    rocket_chat_auth_token = str(dados.get("rocketChatAuthToken") or "").strip()
    rocket_chat_contar = str(dados.get("rocketChatContar") or "tudo").strip().lower()
    if rocket_chat_contar not in {"tudo", "mencoes"}:
        rocket_chat_contar = "tudo"
    try:
        nf_servico_alerta_dias_uteis = int(dados.get("nfServicoAlertaDiasUteis", 3) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dias úteis do alerta de NF Serviço inválidos.") from exc
    if not 0 <= nf_servico_alerta_dias_uteis <= 60:
        raise ValueError("Dias úteis do alerta de NF Serviço devem ficar entre 0 e 60.")

    salvar_config_app(
        {
            "chrome_porta": chrome_porta,
            "navegador": navegador,
            "fechar_aba_fila": bool(dados.get("fecharAbaFila", False)),
            "perguntar_limpar_mes": bool(dados.get("perguntarLimparMes", True)),
            "tema_web": tema_web,
            "nivel_log": nivel_log,
            "turso_database_url": turso_database_url,
            "turso_auth_token": turso_auth_token,
            "nome_usuario": nome_usuario,
            "nf_servico_alerta_dias_uteis": nf_servico_alerta_dias_uteis,
            "rocket_chat_url": rocket_chat_url,
            "rocket_chat_user_id": rocket_chat_user_id,
            "rocket_chat_auth_token": rocket_chat_auth_token,
            "rocket_chat_contar": rocket_chat_contar,
        }
    )

    # Aplica imediatamente no ambiente para não precisar reiniciar
    if nome_usuario:
        os.environ["AUTO_LIQUID_NOME"] = nome_usuario
        if fonte_dados_habilitada("servidores_config", "turso"):
            try:
                from services import turso_service

                if turso_service.turso_configurado():
                    turso_service.salvar_servidor_config(nome_usuario, "#6366f1")
            except Exception:
                log.warning("Não foi possível registrar '%s' no cadastro único de servidores no Turso.", nome_usuario, exc_info=True)
    elif "AUTO_LIQUID_NOME" in os.environ:
        os.environ.pop("AUTO_LIQUID_NOME", None)

    if turso_database_url:
        os.environ["TURSO_DATABASE_URL"] = turso_database_url
    elif "TURSO_DATABASE_URL" in os.environ:
        os.environ.pop("TURSO_DATABASE_URL", None)

    if turso_auth_token:
        os.environ["TURSO_AUTH_TOKEN"] = turso_auth_token
    elif "TURSO_AUTH_TOKEN" in os.environ:
        os.environ.pop("TURSO_AUTH_TOKEN", None)

    return carregar_configuracoes_web()
