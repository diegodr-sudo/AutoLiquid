"""
Parser de PDF de NF-e / NFS-e — calibrado para o formato NFS-e Nacional (DFSe).

Extrai via pdfplumber (texto + tabelas):
  - CNPJ e razão social do prestador
  - Número da nota, data de emissão
  - Valor bruto, valor líquido
  - Deduções: ISS, IRRF, PIS, COFINS, CSLL, INSS
  - Município / local de incidência do ISS
  - Alíquota ISS
"""

from __future__ import annotations

import io
import re
from typing import Optional


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _brl(s: str) -> float:
    """'R$ 1.234,56' ou '1.234,56' → 1234.56"""
    t = re.sub(r"[^\d,.]", "", (s or "").replace("R$", "").strip())
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _buscar(padrao: str, texto: str, grupo: int = 1) -> str:
    m = re.search(padrao, texto, re.IGNORECASE)
    return m.group(grupo).strip() if m else ""


def _valor(padrao: str, texto: str) -> float:
    v = _buscar(padrao, texto)
    return _brl(v) if v else 0.0


# ─── Extração de campos específicos ──────────────────────────────────────────

def _cnpj_prestador(texto: str) -> str:
    """CNPJ da seção PRESTADOR DE SERVIÇOS (primeiro CNPJ formatado)."""
    # Pega o bloco entre PRESTADOR e TOMADOR
    m = re.search(
        r"PRESTADOR\s+DE\s+SERVI[ÇC]OS(.*?)(?:TOMADOR|DISCRIMINA[ÇC][ÃA]O)",
        texto, re.IGNORECASE | re.DOTALL
    )
    bloco = m.group(1) if m else texto

    # CNPJ formatado: XX.XXX.XXX/XXXX-XX
    m2 = re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", bloco)
    return m2.group(0) if m2 else ""


def _razao_social(texto: str) -> str:
    """Razão social do prestador (linha 'Nome/Razão Social:')."""
    # Bloco do prestador
    m = re.search(
        r"PRESTADOR\s+DE\s+SERVI[ÇC]OS(.*?)(?:TOMADOR|DISCRIMINA[ÇC][ÃA]O)",
        texto, re.IGNORECASE | re.DOTALL
    )
    bloco = m.group(1) if m else texto

    m2 = re.search(r"Nome/Raz[aã]o\s+Social:\s*([^\n\r]+)", bloco, re.IGNORECASE)
    if m2:
        nome = m2.group(1).strip()
        # Remove o que vier depois de "Inscrição Estadual:" etc.
        nome = re.split(r"\s{2,}|Inscri[çc][aã]o", nome)[0].strip()
        return nome

    # Fallback: linha após "Nome Fantasia:"
    m3 = re.search(r"Nome\s+Fantasia:\s*([^\n]+)\nNome/Raz", bloco, re.IGNORECASE)
    return m3.group(1).strip() if m3 else ""


def _numero_nota(texto: str) -> str:
    """Número da nota fiscal."""
    for p in [
        r"N[úu]mero\s+da\s+Nota\s*\n?(\d+)",
        r"N[úu]mero\s+NFS-?e\s*[:\|]?\s*(\d+)",
        r"NFS-e\s+de\s+n[úu]mero\s+(\d+)",
    ]:
        v = _buscar(p, texto)
        if v:
            return v
    return ""


def _data_emissao(texto: str) -> str:
    """Data de emissão no formato DD/MM/AAAA."""
    for p in [
        r"Data\s+da\s+Emiss[aã]o\s+da\s+Nota\s*\n?(\d{2}/\d{2}/\d{4})",
        r"Emiss[aã]o\s+da\s+Nota\s*[:\|]?\s*(\d{2}/\d{2}/\d{4})",
        r"Data\s+de\s+Emiss[aã]o\s*[:\|]?\s*(\d{2}/\d{2}/\d{4})",
    ]:
        v = _buscar(p, texto)
        if v:
            return v
    # Fallback: primeira data que não seja "Fato Gerador"
    datas = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", texto)
    return datas[0] if datas else ""


def _valor_bruto(texto: str) -> float:
    """Valor bruto — linha 'Valor bruto = R$ X'."""
    for p in [
        r"Valor\s+bruto\s*=\s*R\$\s*([\d.,]+)",
        r"Valor\s+do\s+Servi[çc]o\s+([\d.,]+)",
        r"Valor\s+Total\s+do\s+Servi[çc]o\s*=?\s*R?\$?\s*([\d.,]+)",
        r"Valor\s+Bruto\s*[=:]\s*R?\$?\s*([\d.,]+)",
    ]:
        v = _valor(p, texto)
        if v > 0:
            return v
    return 0.0


def _valor_liquido(texto: str) -> float:
    """Valor líquido — linha 'Valor líquido = R$ X'."""
    for p in [
        r"Valor\s+l[íi]quido\s*=\s*R\$\s*([\d.,]+)",
        r"Valor\s+L[íi]quido\s*[=:]\s*R?\$?\s*([\d.,]+)",
    ]:
        v = _valor(p, texto)
        if v > 0:
            return v
    return 0.0


def _retencoes_federais(texto: str) -> dict[str, float]:
    """
    Extrai PIS, COFINS, INSS, IRRF (IR), CSLL do bloco de Retenções Federais.

    Formato típico:
      RETENÇÕES FEDERAIS
      PIS/PASEP  COFINS  INSS  IR  CSLL  Outras Retenções
      R$ 124,15  R$ 573,00  R$ 2.100,99  R$ 916,79  R$ 191,00  R$ 0,00
    """
    result = {"pis": 0.0, "cofins": 0.0, "inss": 0.0, "irrf": 0.0, "csll": 0.0}

    # Busca o bloco a partir de "RETENÇÕES FEDERAIS"
    m = re.search(r"RETEN[ÇC][ÕO]ES\s+FEDERAIS(.*?)(?:\n\n|\nC[oó]digo|\nValor\s+bruto|\nDesc\.)",
                  texto, re.IGNORECASE | re.DOTALL)
    bloco = m.group(1) if m else texto

    # Linha de cabeçalho (identifica a ordem dos campos)
    header_match = re.search(
        r"(PIS[/\s]PASEP[^\n]*COFINS[^\n]*INSS[^\n]*IR[^\n]*CSLL[^\n]*)",
        bloco, re.IGNORECASE
    )
    # Todos os R$ values na sequência
    valores_str = re.findall(r"R\$\s*([\d.,]+)", bloco)

    if header_match and len(valores_str) >= 5:
        # Ordem esperada: PIS, COFINS, INSS, IR(RF), CSLL, [Outras]
        result["pis"]    = _brl(valores_str[0])
        result["cofins"] = _brl(valores_str[1])
        result["inss"]   = _brl(valores_str[2])
        result["irrf"]   = _brl(valores_str[3])
        result["csll"]   = _brl(valores_str[4])
        return result

    # Fallback: regex individuais
    for p, k in [
        (r"PIS[/\s]PASEP\s*\n?R?\$?\s*([\d.,]+)", "pis"),
        (r"COFINS\s*\n?R?\$?\s*([\d.,]+)", "cofins"),
        (r"INSS\s*\n?R?\$?\s*([\d.,]+)", "inss"),
        (r"\bIR\b\s*\n?R?\$?\s*([\d.,]+)", "irrf"),
        (r"CSLL\s*\n?R?\$?\s*([\d.,]+)", "csll"),
    ]:
        v = _valor(p, texto)
        if v > 0:
            result[k] = v

    return result


def _iss(texto: str) -> tuple[float, float]:
    """Retorna (valor_iss, aliquota_iss)."""
    # Valor ISS da tabela resumo: "Valor ISS(R$)\n954,99"
    v_iss = _valor(r"Valor\s+ISS\s*\(R\$\)\s*\n?([\d.,]+)", texto)

    # Alíquota: "5,0000%"
    aliq = _valor(r"([\d.,]+)\s*%\s*(?:[\d.,]+\s*)?$", texto)
    if aliq == 0:
        aliq = _valor(r"Al[íi]quota\s*[:\|]?\s*([\d.,]+)", texto)

    # Fallback valor ISS via cálculo base*aliq
    if v_iss == 0 and aliq > 0:
        base = _valor(r"Base\s+de\s+C[áa]lculo\s*\n?([\d.,]+)", texto)
        if base > 0:
            v_iss = round(base * aliq / 100, 2)

    return v_iss, aliq


def _municipio_incidencia(texto: str) -> str:
    """Local de incidência do ISS."""
    for p in [
        r"Local\s+de\s+Incid[eê]ncia\s+ISS:\s*([^\n\r]+)",
        r"Local\s+de\s+Incid[eê]ncia\s*[:\|]\s*([^\n\r]+)",
        r"ISS\s+(?:[eé]\s+)?devido\s+(?:em|no\s+munic[íi]pio\s+de)\s+([^\n\r,\.]+)",
    ]:
        v = _buscar(p, texto)
        if v:
            return v.strip().rstrip(".")
    return ""


# ─── Função principal ─────────────────────────────────────────────────────────

def extrair_dados_nf_pdf(pdf_bytes: bytes) -> dict:
    """
    Extrai dados financeiros de um PDF de NF-e ou NFS-e.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        paginas_texto = []
        for page in pdf.pages:
            t = page.extract_text() or ""
            paginas_texto.append(t)
        texto = "\n".join(paginas_texto)

    if not texto.strip():
        raise ValueError("PDF não contém texto legível — pode estar escaneado sem OCR.")

    # Tipo de documento
    tipo = "NFS-e" if re.search(r"NFS-?e|Nota\s+Fiscal\s+Eletr[ôo]nica\s+de\s+Presta[çc][aã]o", texto, re.I) else "NF-e"

    # Campos de identificação
    cnpj        = _cnpj_prestador(texto)
    razao       = _razao_social(texto)
    numero_nota = _numero_nota(texto)
    data_emissao = _data_emissao(texto)

    # Valores principais
    valor_bruto  = _valor_bruto(texto)
    valor_liq    = _valor_liquido(texto)

    # ISS
    v_iss, aliquota = _iss(texto)
    municipio       = _municipio_incidencia(texto)

    # Retenções federais
    ret = _retencoes_federais(texto)

    deducoes = {
        "iss":    round(v_iss, 2),
        "irrf":   round(ret["irrf"], 2),
        "pis":    round(ret["pis"], 2),
        "cofins": round(ret["cofins"], 2),
        "csll":   round(ret["csll"], 2),
        "inss":   round(ret["inss"], 2),
    }

    total_deducoes = round(sum(deducoes.values()), 2)

    # Valor líquido: usa o do PDF se disponível, senão calcula
    if valor_liq == 0 and valor_bruto > 0:
        valor_liq = round(valor_bruto - total_deducoes, 2)

    return {
        "tipoDocumento":      tipo,
        "cnpj":               cnpj,
        "razaoSocial":        razao,
        "numeroNota":         numero_nota,
        "dataEmissao":        data_emissao,
        "valorBruto":         round(valor_bruto, 2),
        "aliquotaIss":        round(aliquota, 2),
        "municipioIncidencia": municipio,
        "deducoes":           deducoes,
        "totalDeducoes":      total_deducoes,
        "valorLiquido":       round(valor_liq, 2),
    }


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("Uso: python -m core.parser_nf_pdf arquivo.pdf")
        sys.exit(1)
    with open(sys.argv[1], "rb") as f:
        print(json.dumps(extrair_dados_nf_pdf(f.read()), ensure_ascii=False, indent=2))
