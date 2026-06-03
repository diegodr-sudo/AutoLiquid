from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any


MONEY_RE = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
CNPJ_RE = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"


def brl_para_float(valor: str) -> float:
    texto = re.sub(r"[^\d,.-]", "", str(valor or "").strip())
    if not texto:
        return 0.0
    negativo = texto.startswith("-")
    texto = texto.replace("-", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return 0.0
    return -numero if negativo else numero


def _normalizar_linhas(texto: str) -> list[str]:
    linhas: list[str] = []
    for linha in str(texto or "").splitlines():
        limpa = re.sub(r"\s+", " ", linha).strip()
        if limpa:
            linhas.append(limpa)
    return linhas


def _texto_pdf(pdf_bytes: bytes) -> str:
    return "\n".join(_textos_paginas_pdf(pdf_bytes))


def _textos_paginas_pdf(pdf_bytes: bytes) -> list[str]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def _parece_fatura_aires(texto: str) -> bool:
    base = texto.upper()
    return (
        "AIRES TURISMO" in base
        and "FATURA" in base
        and ("FORNECEDOR CNPJ/CPF" in base or "RESUMO FINANCEIRO DA FATURA" in base)
    )


def _numero_fatura(texto: str) -> str:
    for padrao in (
        r"\bN[ºO]\s*FATURA\s*:\s*(\d+)",
        r"\bFATURA\s*:\s*(\d+)",
        r"\bFATURA[_\s-]+(\d{4,})\b",
    ):
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _emissao(texto: str) -> str:
    match = re.search(r"\bEMISS[ÃA]O\s*:\s*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    return match.group(1) if match else ""


def _vencimento(texto: str) -> str:
    match = re.search(r"\bVencimento\s*:\s*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    return match.group(1) if match else ""


def _periodo(texto: str) -> str:
    match = re.search(r"\bPer[íi]odo\s*:\s*(\d{2}/\d{2}/\d{4}\s+a\s+\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    return match.group(1) if match else ""


def _coletar_bloco(linhas: list[str], inicio_re: str, fim_re: str) -> list[str]:
    inicio = -1
    for index, linha in enumerate(linhas):
        if re.search(inicio_re, linha, re.IGNORECASE):
            inicio = index + 1
            break
    if inicio < 0:
        return []

    fim = len(linhas)
    for index in range(inicio, len(linhas)):
        if re.search(fim_re, linhas[index], re.IGNORECASE):
            fim = index
            break
    return linhas[inicio:fim]


def _parse_fornecedor_linha(linha: str) -> dict[str, Any] | None:
    match = re.match(rf"(?P<nome>.+?)\s+(?P<cnpj>{CNPJ_RE})\s+(?P<resto>.+)$", linha)
    if not match:
        return None

    valores = re.findall(MONEY_RE, match.group("resto"))
    if len(valores) < 9:
        return None

    prefixo = re.sub(rf"(?:{MONEY_RE}\s*)+$", "", match.group("resto")).strip()
    partes = prefixo.split()
    servico = partes[0] if partes else ""
    voo = " ".join(partes[1:]) if len(partes) > 1 else ""
    return {
        "nome": match.group("nome").strip(),
        "cnpj": match.group("cnpj"),
        "servico": servico,
        "voo": voo,
        "tarifa": brl_para_float(valores[0]),
        "irpj_24": brl_para_float(valores[1]),
        "csll_1": brl_para_float(valores[2]),
        "cofins": brl_para_float(valores[3]),
        "pis": brl_para_float(valores[4]),
        "imp_tarifa": brl_para_float(valores[5]),
        "outras_taxas": brl_para_float(valores[6]),
        "imp_outras_taxas": brl_para_float(valores[7]),
        "total_imposto": brl_para_float(valores[8]),
    }


def _parse_concessionaria_linha(linha: str) -> dict[str, Any] | None:
    match = re.match(rf"(?P<nome>.+?)\s+(?P<cnpj>{CNPJ_RE})\s+(?P<resto>.+)$", linha)
    if not match:
        return None

    valores = re.findall(MONEY_RE, match.group("resto"))
    if len(valores) < 6:
        return None

    return {
        "nome": match.group("nome").strip(),
        "cnpj": match.group("cnpj"),
        "base_taxa": brl_para_float(valores[0]),
        "ret_taxa": brl_para_float(valores[5]),
    }


def _extrair_fatura_aires_texto(texto: str, origem: str = "") -> dict[str, Any]:
    if not texto.strip():
        raise ValueError("PDF sem texto legível.")

    numero = _numero_fatura(texto)
    if not _parece_fatura_aires(texto) or not numero:
        raise ValueError("PDF não parece ser uma fatura AIRES com resumo financeiro legível.")

    linhas = _normalizar_linhas(texto)
    fornecedores = [
        item
        for linha in _coletar_bloco(
            linhas,
            r"^Fornecedor\s+CNPJ/CPF\s+Servi[cç]o",
            r"^Concession[aá]ria\s+CNPJ",
        )
        if (item := _parse_fornecedor_linha(linha))
    ]
    concessionarias = [
        item
        for linha in _coletar_bloco(
            linhas,
            r"^Concession[aá]ria\s+CNPJ",
            r"^\(\+\)|^\(=\)|^_{3,}|^Assinatura|^Importa",
        )
        if (item := _parse_concessionaria_linha(linha))
    ]

    return {
        "numeroFatura": numero,
        "emissao": _emissao(texto),
        "vencimento": _vencimento(texto),
        "periodo": _periodo(texto),
        "origem": origem,
        "fornecedores": fornecedores,
        "concessionarias": concessionarias,
    }


def extrair_fatura_aires_pdf_bytes(pdf_bytes: bytes, origem: str = "") -> dict[str, Any]:
    return _extrair_fatura_aires_texto(_texto_pdf(pdf_bytes), origem=origem)


def extrair_faturas_aires_pdf_bytes(pdf_bytes: bytes, origem: str = "") -> list[dict[str, Any]]:
    grupos: list[tuple[str, list[str]]] = []

    for texto_pagina in _textos_paginas_pdf(pdf_bytes):
        numero = _numero_fatura(texto_pagina)
        if not numero:
            continue
        if grupos and grupos[-1][0] == numero:
            grupos[-1][1].append(texto_pagina)
        else:
            grupos.append((numero, [texto_pagina]))

    if not grupos:
        return [extrair_fatura_aires_pdf_bytes(pdf_bytes, origem=origem)]

    faturas: list[dict[str, Any]] = []
    for numero, textos in grupos:
        fatura = _extrair_fatura_aires_texto("\n".join(textos), origem=origem)
        if str(fatura.get("numeroFatura") or "") != numero:
            raise ValueError(f"Fatura materializada identificada como {numero}, mas extração retornou {fatura.get('numeroFatura')}.")
        faturas.append(fatura)
    return faturas


def extrair_fatura_aires_pdf(caminho_pdf: str | Path) -> dict[str, Any]:
    path = Path(caminho_pdf)
    return extrair_fatura_aires_pdf_bytes(path.read_bytes(), origem=str(path))


def analisar_faturas_aires(caminhos_pdf: list[str]) -> dict[str, Any]:
    faturas: list[dict[str, Any]] = []
    rejeitados: list[dict[str, str]] = []

    for caminho in caminhos_pdf:
        try:
            faturas.append(extrair_fatura_aires_pdf(caminho))
        except Exception as exc:
            rejeitados.append({"origem": caminho, "motivo": str(exc)})

    return {
        "faturas": faturas,
        "rejeitados": rejeitados,
        "totais": {
            "faturas": len(faturas),
            "fornecedores": sum(len(item.get("fornecedores") or []) for item in faturas),
            "concessionarias": sum(len(item.get("concessionarias") or []) for item in faturas),
        },
    }
