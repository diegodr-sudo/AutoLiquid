"""
Consulta de NF-e via chave de acesso de 44 dígitos.

Fluxo:
  1. Recebe a chave de acesso (44 dígitos numéricos).
  2. Conecta ao serviço SEFAZ DistribuicaoDFe com o certificado digital A1
     configurado (PFX/PEM). Requer CNPJ do destinatário na configuração.
  3. Extrai o XML da NF-e do envelope SOAP (gzip+base64).
  4. Parseia com nfelib (se disponível) ou xml.etree.ElementTree como fallback.
  5. Retorna dict padronizado com razão social, valores e deduções.
"""

from __future__ import annotations

import base64
import gzip
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import requests

# ─── Constantes ──────────────────────────────────────────────────────────────

_NS_NFE = "http://www.portalfiscal.inf.br/nfe"
_TIMEOUT = 30

# Endpoint nacional DistribuicaoDFe (exige certificado do destinatário)
_ENDPOINT_DIST = "https://www.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
_ENDPOINT_DIST_HML = "https://hom.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"

# Endpoint NFeConsultaProtocolo4 por cUF (para consulta de status/protocolo)
_ENDPOINTS_CONSULTA: dict[str, str] = {
    "13": "https://nfe.sefaz.am.gov.br/services2/services/NfeConsulta2",
    "23": "https://nfe.sefaz.ce.gov.br/nfe/services/NfeConsulta2",
    "26": "https://nfe.sefaz.pe.gov.br/nfe-service/services/NfeConsulta2",
    "29": "https://nfe.sefaz.ba.gov.br/webservices/nfeconsulta/nfeconsulta.asmx",
    "31": "https://nfe.fazenda.mg.gov.br/nfe2/services/NfeConsulta2",
    "33": "https://nfe.fazenda.rj.gov.br/nfe/services/NfeConsulta2",
    "35": "https://nfe.fazenda.sp.gov.br/nfe/services/NfeConsulta2",
    "41": "https://nfe.fazenda.pr.gov.br/nfe/services/NfeConsulta2",
    "42": "https://nfe.fazenda.sc.gov.br/nfe/services/NfeConsulta2",
    "43": "https://nfe.fazenda.rs.gov.br/nfe/services/NfeConsulta2",
    "50": "https://nfe.fazenda.ms.gov.br/nfe/services/NfeConsulta2",
    "51": "https://nfe.sefaz.mt.gov.br/nfews/v2/services/NfeConsulta2",
    "52": "https://nfe.sefaz.go.gov.br/nfe/services/NfeConsulta2",
    "53": "https://nfe.fazenda.df.gov.br/nfe/services/NfeConsulta2",
}
_ENDPOINT_SVRS = "https://nfe.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta2.asmx"

# ─── Validação de chave ───────────────────────────────────────────────────────

def validar_chave(chave: str) -> str:
    """Remove espaços/pontos/traços e valida 44 dígitos. Retorna chave limpa."""
    limpa = re.sub(r"[^0-9]", "", chave)
    if len(limpa) != 44:
        raise ValueError(
            f"Chave de acesso deve ter exatamente 44 dígitos numéricos "
            f"(encontrado: {len(limpa)})."
        )
    return limpa


# ─── Carregamento de certificado ─────────────────────────────────────────────

def _extrair_pem_de_pfx(pfx_path: str, senha: str) -> tuple[str, str]:
    """
    Converte PFX → PEM temporários e retorna (cert_path, key_path).
    Usa a biblioteca `cryptography`; levanta ImportError se não disponível.
    """
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
    with open(pfx_path, "rb") as f:
        pfx_bytes = f.read()

    senha_bytes = senha.encode() if senha else None
    pk, cert, _ = pkcs12.load_key_and_certificates(pfx_bytes, senha_bytes)

    tmp = tempfile.mkdtemp(prefix="autoliquid_cert_")

    cert_path = os.path.join(tmp, "cert.pem")
    key_path  = os.path.join(tmp, "key.pem")

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(Encoding.PEM))

    with open(key_path, "wb") as f:
        f.write(pk.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))

    return cert_path, key_path


def _resolver_cert(cert_path: Optional[str], cert_senha: Optional[str]) -> tuple:
    """
    Retorna `cert` no formato aceito por requests (tuple ou None).
    Suporta PFX/P12 (converte para PEM temporário) e PEM direto.
    """
    if not cert_path or not os.path.isfile(cert_path):
        return None

    ext = Path(cert_path).suffix.lower()
    if ext in (".pfx", ".p12"):
        cert_pem, key_pem = _extrair_pem_de_pfx(cert_path, cert_senha or "")
        return (cert_pem, key_pem)

    # Assume PEM; tenta encontrar key.pem paralelo
    key_path = str(Path(cert_path).with_suffix("")) + "_key.pem"
    if os.path.isfile(key_path):
        return (cert_path, key_path)

    # PEM com chave embutida (single-file)
    return cert_path


# ─── SOAP Envelopes ──────────────────────────────────────────────────────────

def _soap_dist_dfe(cnpj: str, c_uf: str, chave: str, tp_amb: str = "1") -> bytes:
    """Monta envelope SOAP para DistribuicaoDFe por chave de acesso."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:nfed="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
  <soapenv:Header/>
  <soapenv:Body>
    <nfed:nfeDistDFeInteresse>
      <nfed:nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{tp_amb}</tpAmb>
          <cUFAutor>{c_uf}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <consChNFe>
            <chNFe>{chave}</chNFe>
          </consChNFe>
        </distDFeInt>
      </nfed:nfeDadosMsg>
    </nfed:nfeDistDFeInteresse>
  </soapenv:Body>
</soapenv:Envelope>""".encode("utf-8")


def _soap_consulta_protocolo(chave: str, tp_amb: str = "1") -> bytes:
    """Monta envelope SOAP para NFeConsultaProtocolo4."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://www.w3.org/2003/05/soap-envelope"
                  xmlns:nfe="http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4">
  <soapenv:Header/>
  <soapenv:Body>
    <nfe:nfeDadosMsg>
      <consSitNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
        <tpAmb>{tp_amb}</tpAmb>
        <xServ>CONSULTAR</xServ>
        <chNFe>{chave}</chNFe>
      </consSitNFe>
    </nfe:nfeDadosMsg>
  </soapenv:Body>
</soapenv:Envelope>""".encode("utf-8")


# ─── Chamadas SEFAZ ──────────────────────────────────────────────────────────

def _post_soap(url: str, body: bytes, cert, action: str = "") -> bytes:
    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
    }
    if action:
        headers["SOAPAction"] = action
    r = requests.post(url, data=body, headers=headers, cert=cert,
                      timeout=_TIMEOUT, verify=True)
    if r.status_code != 200:
        raise RuntimeError(
            f"SEFAZ retornou HTTP {r.status_code}.\n{r.text[:400]}"
        )
    return r.content


def _extrair_nfe_xml_de_dist_dfe(soap_resp: bytes) -> bytes:
    """
    Extrai o XML da NF-e da resposta SOAP do DistribuicaoDFe.
    O conteúdo vem comprimido (gzip) e codificado em base64 no elemento <docZip>.
    """
    root = ET.fromstring(soap_resp)
    NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
    NS_WS   = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
    NS_DIST = "http://www.portalfiscal.inf.br/nfe"

    # Verifica status
    c_stat = None
    for el in root.iter(f"{{{NS_DIST}}}cStat"):
        c_stat = el.text
        break

    if c_stat not in ("138", "100", "104"):
        x_motivo = ""
        for el in root.iter(f"{{{NS_DIST}}}xMotivo"):
            x_motivo = el.text or ""
            break
        raise RuntimeError(
            f"SEFAZ não localizou o documento (cStat={c_stat}): {x_motivo}"
        )

    # Extrai docZip (base64 de gzip do XML da NF-e)
    doc_zip_el = None
    for el in root.iter(f"{{{NS_DIST}}}docZip"):
        doc_zip_el = el
        break
    if doc_zip_el is None or not doc_zip_el.text:
        raise RuntimeError("Elemento <docZip> não encontrado na resposta SEFAZ.")

    compressed = base64.b64decode(doc_zip_el.text.strip())
    xml_bytes  = gzip.decompress(compressed)
    return xml_bytes


# ─── Parsing da NF-e ─────────────────────────────────────────────────────────

def _parse_nfe_xml(xml_bytes: bytes) -> dict:
    """
    Parseia XML de NF-e (procNFe ou apenas NFe) usando nfelib se disponível,
    ou xml.etree.ElementTree como fallback.
    Retorna dict padronizado.
    """
    try:
        return _parse_com_nfelib(xml_bytes)
    except Exception:
        pass
    return _parse_com_etree(xml_bytes)


def _parse_com_nfelib(xml_bytes: bytes) -> dict:
    """Parsing via nfelib (xsdata-based). Levanta ImportError se indisponível."""
    from nfelib.nfe.bindings.v4_0.leiaute_nfe_v4_00 import TnfeProc, Tnfe
    from xsdata.formats.dataclass.parsers import XmlParser

    parser = XmlParser()

    # Tenta como procNFe (NF-e + protocolo)
    try:
        proc = parser.from_bytes(xml_bytes, TnfeProc)
        nfe = proc.NFe
    except Exception:
        nfe = parser.from_bytes(xml_bytes, Tnfe)

    inf = nfe.infNFe
    emit = inf.emit

    def _f(v) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    icms_tot = inf.total.ICMSTot if inf.total else None
    ret      = inf.total.retTrib if inf.total and inf.total.retTrib else None
    iss_tot  = inf.total.ISSQNtot if inf.total and inf.total.ISSQNtot else None

    v_nf     = _f(icms_tot.vNF if icms_tot else None)
    v_irrf   = _f(ret.vIRRF   if ret else None)
    v_pis    = _f(ret.vRetPIS   if ret else None)
    v_cofins = _f(ret.vRetCOFINS if ret else None)
    v_csll   = _f(ret.vRetCSLL  if ret else None)
    v_inss   = _f(ret.vRetPrev  if ret else None)
    v_iss    = _f(iss_tot.vISSRet if iss_tot else None)

    dt_emi = str(inf.ide.dhEmi or inf.ide.dEmi or "")
    cnpj   = emit.CNPJ or emit.CPF or ""
    nome   = emit.xNome or emit.xFant or ""

    return {
        "numero":       str(inf.ide.nNF or ""),
        "serie":        str(inf.ide.serie or ""),
        "emitente":     str(nome).strip(),
        "cnpjEmitente": str(cnpj).strip(),
        "dataEmissao":  dt_emi[:10] if dt_emi else "",
        "valorBruto":   round(v_nf, 2),
        "deducoes": {
            "irrf":   round(v_irrf, 2),
            "pis":    round(v_pis, 2),
            "cofins": round(v_cofins, 2),
            "csll":   round(v_csll, 2),
            "inss":   round(v_inss, 2),
            "iss":    round(v_iss, 2),
        },
    }


def _parse_com_etree(xml_bytes: bytes) -> dict:
    """Parsing via xml.etree.ElementTree (fallback sem nfelib)."""
    NS = _NS_NFE

    def _f(v) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    def _tag(el, path: str):
        r = el.find(f".//{{{NS}}}{path}")
        if r is None:
            r = el.find(f".//{path}")
        return r

    def _txt(el, path: str) -> str:
        t = _tag(el, path)
        return (t.text or "").strip() if t is not None else ""

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"XML inválido: {e}")

    inf = _tag(root, "infNFe")
    if inf is None:
        raise ValueError("Elemento <infNFe> não encontrado.")

    numero   = _txt(inf, "nNF")
    serie    = _txt(inf, "serie")
    cnpj_em  = _txt(inf, "emit/CNPJ") or _txt(inf, "emit/CPF")
    nome_em  = _txt(inf, "emit/xNome") or _txt(inf, "emit/xFant")
    dt_emis  = _txt(inf, "ide/dhEmi") or _txt(inf, "ide/dEmi")

    v_nf = _f(_txt(inf, "total/ICMSTot/vNF")) or _f(_txt(inf, "total/ICMSTot/vProd"))
    v_irrf   = _f(_txt(inf, "total/retTrib/vIRRF"))
    v_pis    = _f(_txt(inf, "total/retTrib/vRetPIS"))
    v_cofins = _f(_txt(inf, "total/retTrib/vRetCOFINS"))
    v_csll   = _f(_txt(inf, "total/retTrib/vRetCSLL"))
    v_inss   = _f(_txt(inf, "total/retTrib/vRetPrev"))
    v_iss    = _f(_txt(inf, "total/ICMSTot/vISS")) or _f(_txt(inf, "total/ISSQNtot/vISSRet"))

    return {
        "numero":       numero,
        "serie":        serie,
        "emitente":     nome_em,
        "cnpjEmitente": cnpj_em,
        "dataEmissao":  dt_emis[:10] if dt_emis else "",
        "valorBruto":   round(v_nf, 2),
        "deducoes": {
            "irrf":   round(v_irrf, 2),
            "pis":    round(v_pis, 2),
            "cofins": round(v_cofins, 2),
            "csll":   round(v_csll, 2),
            "inss":   round(v_inss, 2),
            "iss":    round(v_iss, 2),
        },
    }


# ─── API principal ───────────────────────────────────────────────────────────

def consultar_chave_acesso(
    chave: str,
    cert_path: Optional[str] = None,
    cert_senha: Optional[str] = None,
    cnpj_receptor: Optional[str] = None,
) -> dict:
    """
    Consulta uma NF-e na SEFAZ via DistribuicaoDFe usando a chave de acesso.

    Parâmetros:
        chave          – Chave de acesso de 44 dígitos.
        cert_path      – Caminho para o certificado digital (.pfx, .p12 ou .pem).
        cert_senha     – Senha do certificado (para PFX/P12).
        cnpj_receptor  – CNPJ da empresa consultante (destinatário da NF-e).

    Retorna dict com: numero, serie, emitente, cnpjEmitente, dataEmissao,
    valorBruto, deducoes {irrf, pis, cofins, csll, inss, iss}.
    """
    chave = validar_chave(chave)
    c_uf  = chave[:2]

    cert = _resolver_cert(cert_path, cert_senha)
    if cert is None:
        raise RuntimeError(
            "Certificado digital não configurado. "
            "Adicione o arquivo .pfx em Configurações → Certificado Digital."
        )
    if not cnpj_receptor:
        raise RuntimeError(
            "CNPJ do receptor não configurado. "
            "Informe o CNPJ da sua empresa em Configurações → Certificado Digital."
        )

    cnpj_limpo = re.sub(r"[^0-9]", "", cnpj_receptor)
    soap_body  = _soap_dist_dfe(cnpj_limpo, c_uf, chave)
    soap_resp  = _post_soap(_ENDPOINT_DIST, soap_body, cert)
    xml_bytes  = _extrair_nfe_xml_de_dist_dfe(soap_resp)

    dados = _parse_nfe_xml(xml_bytes)
    print(f"  NF-e {chave[:4]}…: {dados['emitente']} — R$ {dados['valorBruto']:.2f}")
    return dados


if __name__ == "__main__":
    # Teste local — ajuste conforme seu ambiente
    import sys
    if len(sys.argv) >= 2:
        resultado = consultar_chave_acesso(
            sys.argv[1],
            cert_path=os.getenv("NF_CERT_PATH"),
            cert_senha=os.getenv("NF_CERT_SENHA"),
            cnpj_receptor=os.getenv("NF_CNPJ"),
        )
        print(resultado)
