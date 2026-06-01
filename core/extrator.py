import pdfplumber
import re
from datetime import datetime
from pathlib import Path
from core.datas_impostos import obter_mapa_codigo_siafi

try:
    from core.de_para_contratos import buscar_ig_por_contrato
except ImportError:
    def buscar_ig_por_contrato(n):
        return "", ""

# Conjunto para consulta O(1): reduz custo nas verificações de recurso.
FONTES_RECURSO_3 = {
    '1050000394', '1051000394', '0150153163', '0150262460',
    '0250153163', '0250262460', '0263262460', '0280153163',
    '8150262460', '8250262740', '8280153163', '8650262460',
    '8180153163',
}

def _is_garbled(s: str) -> bool:
    """Retorna True se a string parece ser artefato de sobreposição de colunas no pdfplumber.

    Uma string garbled tem a maioria das posições como pares de caracteres idênticos.
    Ex.: '66,,007755..2277' → quase 100% das transições são pares iguais → garbled.
    Ex.: '1.500,00'         → apenas o '00' final forma par → ~14% → não garbled.
    """
    if len(s) < 4:
        return False
    pares = sum(1 for i in range(len(s) - 1) if s[i] == s[i + 1])
    return pares / (len(s) - 1) > 0.5


def _ungarble(s: str) -> str:
    """Remove duplicação de caracteres causada por sobreposição de colunas no pdfplumber.
    Ex.: '66,,007755..2277' → '6,075.27'

    Só é aplicado quando a string passa no teste _is_garbled para não corromper
    valores com dígitos repetidos legítimos (ex.: '1.500,00' → não deve mudar).
    """
    if not _is_garbled(s):
        return s
    result, i = [], 0
    while i < len(s):
        c = s[i]
        if i + 1 < len(s) and s[i + 1] == c:
            result.append(c)
            i += 2
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def _parse_date(s: str):
    """Converte datas comuns do PDF para datetime; retorna datetime.min em falha."""
    texto = str(s or "").strip()
    for formato in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato)
        except Exception:
            pass
    return datetime.min


def _valor_brl_para_float(valor: str) -> float:
    texto = str(valor or "").strip()
    if not texto:
        return 0.0

    negativo = "-" in texto
    texto = "".join(ch for ch in texto if ch.isdigit() or ch in ".,")
    if not texto:
        return 0.0

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        partes = texto.split(",")
        if len(partes) > 2:
            texto = "".join(partes)
        elif len(partes) == 2 and len(partes[1]) > 2:
            texto = f"{partes[0]}{partes[1][:-2]}.{partes[1][-2:]}"
        else:
            texto = texto.replace(".", "").replace(",", ".")
    elif "." in texto:
        partes = texto.split(".")
        if len(partes) > 2:
            if len(partes[-1]) == 2:
                texto = f"{''.join(partes[:-1])}.{partes[-1]}"
            else:
                texto = "".join(partes)
        elif len(partes) == 2 and len(partes[1]) > 2:
            texto = f"{partes[0]}{partes[1][:-2]}.{partes[1][-2:]}"
    try:
        valor_float = float(texto)
        return -valor_float if negativo else valor_float
    except Exception:
        return 0.0


def _float_para_valor_brl(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _normalizar_data_br(valor: str) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    for formato in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).strftime("%d/%m/%Y")
        except Exception:
            pass
    return texto


def _texto_pdf(caminho_pdf: str | Path) -> str:
    with pdfplumber.open(caminho_pdf) as pdf:
        return "\n".join((pagina.extract_text() or "") for pagina in pdf.pages)


def _extrair_identificadores_documento(texto: str) -> tuple[str, str]:
    sol = ""
    processo = ""

    match_sol = re.search(r"Sol\.Pagto\.:\s*(\d+)", texto, re.IGNORECASE)
    if match_sol:
        sol = match_sol.group(1).strip()

    match_processo = re.search(r"Processo:\s*([\d./-]+)", texto, re.IGNORECASE)
    if match_processo:
        processo = match_processo.group(1).strip()

    return sol, processo


def _limpar_campo_documento(valor: str, fallback: str = "—") -> str:
    texto = str(valor or "").strip()
    if not texto or texto.lower() == "não encontrado":
        return fallback
    return texto


def _normalizar_documento_fiscal(valor: str) -> str:
    """Retorna CPF/CNPJ apenas com dígitos quando o tamanho parece válido."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) in {11, 14}:
        return digitos
    if len(digitos) > 14:
        # Em alguns PDFs o texto cola rótulos/colunas; preserva o CNPJ à direita.
        for tamanho in (14, 11):
            candidato = digitos[-tamanho:]
            if len(candidato) == tamanho:
                return candidato
    return ""


def _extrair_cpf_cnpj_documento(texto: str, texto_cabecalho: str = "") -> str:
    """Aceita os layouts antigos e o layout novo com rótulo CNPJ/CPF."""
    texto_busca = "\n".join([str(texto_cabecalho or ""), str(texto or "")])
    padroes_rotulo = [
        r"CPF\s*/\s*CNPJ\s*/\s*UG\s*:?\s*([0-9][0-9.\-/\s]{10,24})",
        r"CNPJ\s*/\s*CPF\s*:?\s*([0-9][0-9.\-/\s]{10,24})",
        r"CPF\s*/\s*CNPJ\s*:?\s*([0-9][0-9.\-/\s]{10,24})",
        r"\bCNPJ\s*:?\s*([0-9][0-9.\-/\s]{10,24})",
    ]
    for padrao in padroes_rotulo:
        match = re.search(padrao, texto_busca, re.IGNORECASE)
        if match:
            documento = _normalizar_documento_fiscal(match.group(1))
            if documento:
                return documento

    topo = "\n".join(texto_busca.splitlines()[:35])
    match_formatado = re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", topo)
    if match_formatado:
        documento = _normalizar_documento_fiscal(match_formatado.group(0))
        if documento:
            return documento

    return ""


def _tokens_nome_arquivo(nome_arquivo: str | None) -> list[str]:
    if not nome_arquivo:
        return []
    stem = Path(nome_arquivo).stem
    return [token for token in re.findall(r"\d{6,}", stem) if token]


def _pontuar_pagina_documento(texto: str, tokens_nome: list[str]) -> int:
    if not texto.strip():
        return -1

    score = 0
    texto_upper = texto.upper()
    texto_digitos = re.sub(r"\D", "", texto)

    if "DOCUMENTO AUXILIAR DE LIQUIDAÇÃO" in texto_upper:
        score += 120
    if re.search(r"Sol\.Pagto\.:\s*\d+", texto, re.IGNORECASE):
        score += 80
    if re.search(r"Processo:\s*[\d./-]+", texto, re.IGNORECASE):
        score += 60
    if "DOCUMENTOS FISCAIS:" in texto_upper:
        score += 50
    if "DADOS ORÇAMENTÁRIOS:" in texto_upper or "DADOS ORCAMENTÁRIOS:" in texto_upper:
        score += 35
    if "RESUMO:" in texto_upper:
        score += 25

    for token in tokens_nome:
        if token in texto_digitos:
            score += 150

    return score


def _selecionar_bloco_documento(textos_paginas: list[str], nome_arquivo: str | None) -> tuple[str, str, int, int]:
    textos_limpos = [str(texto or "").strip() for texto in textos_paginas]
    if not any(textos_limpos):
        return "", "", 0, 0

    tokens_nome = _tokens_nome_arquivo(nome_arquivo)
    pontuacoes = [_pontuar_pagina_documento(texto, tokens_nome) for texto in textos_limpos]

    inicio = max(
        range(len(textos_limpos)),
        key=lambda idx: (pontuacoes[idx], -idx),
    )

    sol_inicio, processo_inicio = _extrair_identificadores_documento(textos_limpos[inicio])
    fim = inicio

    for idx in range(inicio + 1, len(textos_limpos)):
        texto = textos_limpos[idx]
        if not texto:
            continue

        sol_atual, processo_atual = _extrair_identificadores_documento(texto)
        eh_novo_documento = (
            ("DOCUMENTO AUXILIAR DE LIQUIDAÇÃO" in texto.upper() or sol_atual or processo_atual)
            and (
                (sol_inicio and sol_atual and sol_atual != sol_inicio)
                or (processo_inicio and processo_atual and processo_atual != processo_inicio)
            )
        )
        if eh_novo_documento:
            break
        fim = idx

    bloco_paginas = [texto for texto in textos_limpos[inicio : fim + 1] if texto]
    texto_principal = bloco_paginas[0] if bloco_paginas else textos_limpos[inicio]
    texto_documento = "\n".join(bloco_paginas) if bloco_paginas else texto_principal
    return texto_principal, texto_documento, inicio, fim


def determinar_recurso(ano_empenho, fonte, tem_convenio):
    ano_atual = datetime.now().year
    if tem_convenio:
        return "3"
    if fonte in FONTES_RECURSO_3:
        return "3"
    if ano_empenho == ano_atual:
        return "1"
    elif ano_empenho < ano_atual:
        return "2"
    else:
        return "Ano fora do padrão"


def extrair_dados_pdf(caminho_pdf, nome_arquivo: str | None = None):
    dados_extraidos = {}

    with pdfplumber.open(caminho_pdf) as pdf:
        textos_paginas = [(pagina.extract_text() or "") for pagina in pdf.pages]
        texto_cabecalho, texto, pagina_inicio, pagina_fim = _selecionar_bloco_documento(
            textos_paginas,
            nome_arquivo,
        )

        if not texto:
            print("Não foi possível ler o texto do PDF.")
            return None

        # ── 0. Município de Emissão da NF (topo do PDF) ───────────────────────
        # Tenta detectar o município nas primeiras linhas do texto extraído.
        _CIDADES_SCAN = [
            (r'florian[oó]polis',  'Florianópolis'),
            (r'blumenau',          'Blumenau'),
            (r'joinville',         'Joinville'),
            (r'curitibanos',       'Curitibanos'),
            (r'ararangu[aá]',      'Araranguá'),
            (r'barra do sul',      'Barra do Sul'),
            (r's[aã]o jos[eé]',    'São José'),
            (r'palho[cç]a',        'Palhoça'),
            (r'big[oó]rrilho',     'Bigorrilho'),
            (r'chapec[oó]',        'Chapecó'),
            (r'itaja[ií]',         'Itajaí'),
            (r'crici[úu]ma',       'Criciúma'),
        ]
        texto_inicio = '\n'.join(texto_cabecalho.split('\n')[:20])
        _municipio_nf = ''
        for _pat, _nome in _CIDADES_SCAN:
            if re.search(_pat, texto_inicio, re.IGNORECASE):
                _municipio_nf = _nome
                break
        if not _municipio_nf:
            m_mun = re.search(
                r'Munic[íi]pio[:\s]+([A-Za-zÀ-ú\s]+)(:\n|/SC|/RS|\s{3,})',
                texto_inicio, re.IGNORECASE
            )
            if m_mun:
                _municipio_nf = m_mun.group(1).strip()
        dados_extraidos['Município da NF'] = _municipio_nf

        # ── 1. CNPJ/CPF ──────────────────────────────────────────────────────
        dados_extraidos['CNPJ'] = (
            _extrair_cpf_cnpj_documento(texto, texto_cabecalho)
            or "Não encontrado"
        )

        match_nome_credor = (
            re.search(r"Nome\s+do\s+Credor:\s*([^\n]+)", texto, re.IGNORECASE)
            or re.search(r"Favorecido:\s*([^\n]+)", texto, re.IGNORECASE)
            or re.search(r"Credor:\s*([^\n]+)", texto, re.IGNORECASE)
            or re.search(r"\bNome:\s*([^\n]+?)(?=\s+(?:Munic[íi]pio|Banco|Ag[eê]ncia|CNPJ|CPF)\b|$)", texto, re.IGNORECASE)
        )
        dados_extraidos['Nome do Credor'] = (
            match_nome_credor.group(1).strip() if match_nome_credor else ""
        )

        # ── 1.1 Dados bancários (Banco / Agência / Conta) ────────────────────
        # Linha típica: "Banco: 033   Agência: 2102   Conta: 130057029"
        match_banco   = re.search(r"Banco:\s*(\d+)", texto, re.IGNORECASE)
        match_agencia = re.search(r"Ag[eê]ncia:\s*(\d+)", texto, re.IGNORECASE)
        match_conta   = re.search(r"\bConta:\s*([\d.]+(?:-[\dA-Za-z]+)?)", texto, re.IGNORECASE)
        dados_extraidos['Banco']   = match_banco.group(1).strip()   if match_banco   else ""
        dados_extraidos['Agência'] = match_agencia.group(1).strip() if match_agencia else ""
        dados_extraidos['Conta']   = match_conta.group(1).strip()   if match_conta   else ""

        # ── 1.5 Processo ─────────────────────────────────────────────────────
        match_processo = (
            re.search(r"Processo\s*:\s*([\d./-]{7,})", texto, re.IGNORECASE)
            or re.search(r"\bProcesso\b[^\d]{0,20}([\d./-]{7,})", texto, re.IGNORECASE)
            or re.search(r"\b(\d{5}\.\d{5,}/\d{4})\b", texto)
            or re.search(r"\b(\d{5}\.\d{6}/\d{4})\b", texto)
        )
        dados_extraidos['Processo'] = match_processo.group(1).strip() if match_processo else "Não encontrado"

        # ── 1.6 Natureza — prioriza as linhas dos empenhos ───────────────────
        natureza_raw = ""
        empenhos_com_natureza = []
        for linha in texto.splitlines():
            linha_limpa = " ".join(str(linha or "").split()).strip()
            if not linha_limpa:
                continue
            # Dados Orçamentários: EMPENHO SITUACAO CLASSIF1 CLASSIF2 NATUREZA SALDO VALOR [FONTE]
            # Ex: "2026000968 DSP001 3323__00 213110400 339039.79 16,968.12 13,031.08 1000000000"
            match_empenho_nat = re.search(
                r"(\d{10,})\s+(DSP\d+)\s+\S+\s+\S+\s+(\d{6}[.,]\d{2})\s+([\d,.]+)\s+([\d,.]+)",
                linha_limpa,
                re.IGNORECASE,
            )
            if match_empenho_nat:
                numero_empenho, situacao_empenho, natureza_linha, saldo_empenho, valor_empenho = match_empenho_nat.groups()
                natureza_linha = natureza_linha.replace(",", ".")
                empenhos_com_natureza.append(
                    {
                        "Empenho": numero_empenho,
                        "Situação": situacao_empenho,
                        "Natureza": natureza_linha,
                        "Saldo": saldo_empenho,
                        "Valor": valor_empenho,
                    }
                )
                if not natureza_raw:
                    natureza_raw = natureza_linha

        if not natureza_raw:
            match_nat = re.search(r"Natureza[^\d]{0,20}([\d]{6}[.,]\d{2})", texto, re.IGNORECASE)
            natureza_raw = match_nat.group(1).replace(",", ".") if match_nat else ""

        dados_extraidos['Natureza'] = natureza_raw

        # ── 1.7 Contrato ─────────────────────────────────────────────────────
        # Aceita variações como:
        # "Contrato S   Número do Contrato: 00160/2020"
        # "Contrato ? S   Número do Contrato: 00058/2023"
        # "Número do Contrato: 00058/2023"
        # Em alguns PDFs o pdfplumber cola os rótulos:
        # "Contrato? S NúmerodoContrato: 00077/2022"
        match_contrato = re.search(
            r"(?:Contrato\s*\??\s*(?:S|SIM|N|NÃO|NAO)?\s*)?N[úu]mero\s*do\s*Contrato\s*:\s*(\d+/\d{4})",
            texto,
            re.IGNORECASE,
        )
        if match_contrato:
            num_contrato = match_contrato.group(1).strip()
            sarf_code, ig_code = buscar_ig_por_contrato(num_contrato)
            dados_extraidos['Tem Contrato']       = 'Sim'
            dados_extraidos['Tem Contrato?']      = 'Sim'
            dados_extraidos['Número do Contrato'] = num_contrato
            dados_extraidos['SARF']               = sarf_code
            dados_extraidos['IG']                 = ig_code
        else:
            dados_extraidos['Tem Contrato']       = 'Não'
            dados_extraidos['Tem Contrato?']      = 'Não'
            dados_extraidos['Número do Contrato'] = ''
            dados_extraidos['SARF']               = ''
            dados_extraidos['IG']                 = ''

        # ── 2. Solicitação de Pagamento ───────────────────────────────────────
        match_sol = re.search(r"Sol\.Pagto\.:\s*(\d+)", texto)
        dados_extraidos['Solicitação de Pagamento'] = match_sol.group(1) if match_sol else "Não encontrado"

        lista_notas = []
        lista_bolsas = []
        bloco_documentos = ""
        match_docs = re.search(
            r"Documentos\s*Fiscais\s*:(.*?)(?:Dados\s*Orçamentários\s*:|Detalhamento\s*de\s*Fonte\s*:|RESUMO\s*:)",
            texto,
            re.DOTALL | re.IGNORECASE,
        )
        if match_docs:
            bloco_documentos = match_docs.group(1)

        pendente_desconto = 0.0

        def adicionar_documento(tipo: str, numero: str, emissao: str, ateste: str, valor: str) -> None:
            nonlocal pendente_desconto
            valor_final = _valor_brl_para_float(valor) + pendente_desconto
            pendente_desconto = 0.0
            lista_notas.append({
                'Tipo':            tipo,
                'Número da Nota':  str(numero).strip(),
                'Data de Emissão': emissao,
                'Data de Ateste':  ateste,
                'Valor':           _float_para_valor_brl(max(0.0, valor_final)),
            })

        def adicionar_bolsa(numero: str, emissao: str, ateste: str, valor: str) -> None:
            valor_final = _valor_brl_para_float(valor)
            lista_bolsas.append({
                'Número da Remessa': str(numero).strip(),
                'Data de Emissão': _normalizar_data_br(emissao),
                'Data de Ateste': _normalizar_data_br(ateste),
                'Valor': _float_para_valor_brl(max(0.0, valor_final)),
            })
            lista_notas.append({
                'Tipo': 'Bolsa',
                'Número da Nota': str(numero).strip(),
                'Data de Emissão': emissao,
                'Data de Ateste': ateste,
                'Valor': _float_para_valor_brl(max(0.0, valor_final)),
            })

        if bloco_documentos:
            for linha in bloco_documentos.splitlines():
                linha = " ".join(str(linha or "").split()).strip()
                if not linha or re.match(r"Tipo\s+Nota\s+Emiss[aã]o", linha, re.IGNORECASE):
                    continue

                m_desc = re.match(
                    r"Desconto\s+Carta\s+de\s+desconto\s+([\d-]+)\s+([\d-]+)\s+(-?[\d,.]+)$",
                    linha,
                    re.IGNORECASE,
                )
                if m_desc:
                    _, _, valor_desconto = m_desc.groups()
                    pendente_desconto += _valor_brl_para_float(valor_desconto)
                    continue

                m_nf = re.match(
                    r"NF\s*(Material|Servi[çc]o)\s+([\d.]+)\s+([\d-]+)\s+([\d-]+)\s+([\d,.]+)$",
                    linha,
                    re.IGNORECASE,
                )
                if m_nf:
                    tipo_nf, numero_nf, emissao_nf, ateste_nf, valor_nf = m_nf.groups()
                    adicionar_documento(f"NF {tipo_nf.capitalize()}", numero_nf, emissao_nf, ateste_nf, valor_nf)
                    continue

                m_bolsa = re.match(
                    r"Bolsa\s+(?:Remessa\s+)?(\d+)\s+([\d/\-]+)\s+([\d/\-]+)\s+([\d,.]+)",
                    linha,
                    re.IGNORECASE,
                )
                if m_bolsa:
                    numero_remessa, emissao_bolsa, ateste_bolsa, valor_bolsa = m_bolsa.groups()
                    adicionar_bolsa(numero_remessa, emissao_bolsa, ateste_bolsa, valor_bolsa)
                    continue

                m_fatura = re.match(
                    r"Fatura\s+([\d.]+)\s+([\d-]+)\s+([\d-]+)\s+([\d,.]+)$",
                    linha,
                    re.IGNORECASE,
                )
                if m_fatura:
                    numero_fatura, emissao_fatura, ateste_fatura, valor_fatura = m_fatura.groups()
                    adicionar_documento("Fatura", numero_fatura, emissao_fatura, ateste_fatura, valor_fatura)
                    continue

        if not lista_notas:
            notas_encontradas = re.findall(
                r"NF\s*(Material|Servi[çc]o)\s+([\d.]+)\s+([\d-]+)\s+([\d-]+)\s+([\d,\.]+)",
                texto, re.IGNORECASE
            )
            for nota in notas_encontradas:
                lista_notas.append({
                    'Tipo':            f"NF {nota[0].capitalize()}",
                    'Número da Nota':  nota[1],
                    'Data de Emissão': nota[2],
                    'Data de Ateste':  nota[3],
                    'Valor':           nota[4],
                })

            bolsas_encontradas = re.findall(
                r"Bolsa\s+(?:Remessa\s+)?(\d+)\s+([\d/\-]+)\s+([\d/\-]+)\s+([\d,\.]+)",
                texto,
                re.IGNORECASE,
            )
            for bolsa in bolsas_encontradas:
                numero_remessa = str(bolsa[0]).strip()
                if any(str(item.get('Número da Remessa', '')).strip() == numero_remessa for item in lista_bolsas):
                    continue
                adicionar_bolsa(numero_remessa, bolsa[1], bolsa[2], bolsa[3])

            faturas_encontradas = re.findall(
                r"Fatura\s+([\d.]+)\s+([\d-]+)\s+([\d-]+)\s+([\d,\.]+)",
                texto,
                re.IGNORECASE,
            )
            for fatura in faturas_encontradas:
                numero_fatura = str(fatura[0]).strip()
                if any(str(nota.get('Número da Nota', '')).strip() == numero_fatura for nota in lista_notas):
                    continue
                lista_notas.append({
                    'Tipo':            'Fatura',
                    'Número da Nota':  numero_fatura,
                    'Data de Emissão': fatura[1],
                    'Data de Ateste':  fatura[2],
                    'Valor':           fatura[3],
                })

        if pendente_desconto and lista_notas:
            ultima_nota = lista_notas[-1]
            valor_atual = _valor_brl_para_float(ultima_nota.get('Valor', '0'))
            ultima_nota['Valor'] = _float_para_valor_brl(max(0.0, valor_atual + pendente_desconto))

        dados_extraidos['Notas Fiscais'] = lista_notas
        dados_extraidos['Bolsas'] = lista_bolsas
        dados_extraidos['Tipo Operacional'] = 'bolsa' if lista_bolsas else 'comprasnet'

        # Data de ateste mais recente entre todas as NFs
        datas_ateste = [n['Data de Ateste'] for n in lista_notas if n['Data de Ateste']]
        dados_extraidos['Data de Ateste'] = (
            max(datas_ateste, key=_parse_date) if datas_ateste else ""
        )

        # ── 4. Fonte e Convênio ───────────────────────────────────────────────
        # Fonte pode ser numérica (1000000000) ou alfanumérica (1000A0008U) — sempre 10 chars
        # Convênio: 8 dígitos que precedem a fonte na linha do Detalhamento
        match_detalhe = re.search(
            r"Detalhamento\s*de\s*Fonte\s*:(.*)RESUMO\s*:",
            texto,
            re.DOTALL | re.IGNORECASE,
        )
        fonte_encontrada = ""
        tem_convenio = False

        if match_detalhe:
            bloco_detalhe = match_detalhe.group(1).strip()
            # Linha de dados: "[conv8] [siafi] [fonte10] [valor]" ou "[fonte10] [valor]"
            for linha in bloco_detalhe.split('\n'):
                linha = linha.strip()
                if not linha or re.match(r'Conv[eê]nio', linha, re.IGNORECASE):
                    continue
                # Tenta capturar fonte (10 chars alfanum) com convênio de 8 dígitos antes
                m_conv = re.search(r"(\d{8})\s+\S+\s+([A-Z0-9]{10})", linha)
                if m_conv:
                    fonte_encontrada = m_conv.group(2)
                    tem_convenio = True
                    break
                # Sem convênio: linha começa com a fonte de 10 chars
                m_fonte = re.search(r"\b([A-Z0-9]{10})\b", linha)
                if m_fonte:
                    fonte_encontrada = m_fonte.group(1)
                    break

        dados_extraidos['Fonte'] = fonte_encontrada
        dados_extraidos['Tem Convênio'] = "Sim" if tem_convenio else "Não"
        dados_extraidos['Tem Convênio?'] = dados_extraidos['Tem Convênio']

        # ── 5. Empenhos e Recurso ─────────────────────────────────────────────
        empenhos_encontrados = re.findall(r"(\d{10,})\s+(DSP\d+)", texto)
        lista_empenhos = []
        natureza_por_empenho = {
            item["Empenho"]: item["Natureza"] for item in empenhos_com_natureza
        }
        # Dict completo com todos os campos extraídos por empenho (inclui Valor)
        natureza_por_empenho_info = {
            item["Empenho"]: item for item in empenhos_com_natureza
        }
        for empenho in empenhos_encontrados:
            numero_empenho = empenho[0]
            situacao = empenho[1]
            ano_do_empenho = int(numero_empenho[:4])
            recurso = determinar_recurso(ano_do_empenho, fonte_encontrada, tem_convenio)
            info_emp = natureza_por_empenho_info.get(numero_empenho, {})
            lista_empenhos.append({
                'Empenho': numero_empenho,
                'Situação': situacao,
                'Recurso': recurso,
                'Natureza': natureza_por_empenho.get(numero_empenho, natureza_raw),
                'Valor': info_emp.get("Valor", ""),
                'Saldo': info_emp.get("Saldo", ""),
            })
        dados_extraidos['Empenhos'] = lista_empenhos

        # ── 6. Resumo ─────────────────────────────────────────────────────────
        resumo = {'Valor Bruto': '', 'Total Deduções': '', 'Valor Líquido': '', 'Valor Encargos': ''}
        match_resumo = re.search(r"RESUMO\s*:(.*)", texto, re.DOTALL | re.IGNORECASE)
        if match_resumo:
            bloco_resumo = match_resumo.group(1)
            def _ev(pattern, bloco):
                m = re.search(pattern, bloco, re.IGNORECASE)
                return m.group(1).strip() if m else ''
            resumo['Valor Bruto']    = _ev(r"Valor\s*Bruto\s*:\s*([\d,.]+)", bloco_resumo)
            resumo['Total Deduções'] = _ev(r"Dedu[çc][õo]es:\s*([\d,.]+)", bloco_resumo)
            resumo['Valor Líquido']  = _ev(r"Valor\s*L[íi]quido\s*:?\s*([\d,.]+)", bloco_resumo)
            resumo['Valor Encargos'] = _ev(r"Valor\s*Encargos\s*:\s*([\d,.]+)", bloco_resumo)
        dados_extraidos['Resumo'] = resumo

        # ── 7. Deduções ───────────────────────────────────────────────────────
        # Valores da tabela ficam garbled (ex.: 66,,007755..2277) → ungarble
        # Linha COM código:    SITUACAO 4DIGITS CNPJ8+/xxx-xx BASE GARBLED [REND5+]
        # Linha SEM código:    SITUACAO CNPJ8+/xxx-xx BASE GARBLED [REND5+]
        lista_deducoes = []
        codigo_situacao_siafi = obter_mapa_codigo_siafi()
        match_ded_bloco = re.search(
            r"Dedu[çc][õo]es\s*:(.*?)(?=Detalhamento\s*de\s*Fonte\s*:|RESUMO\s*:)",
            texto, re.DOTALL | re.IGNORECASE
        )
        if match_ded_bloco:
            bloco_ded = match_ded_bloco.group(1)
            for linha in bloco_ded.strip().split('\n'):
                linha = linha.strip()
                if not linha or re.match(r'Situa[çc]', linha, re.IGNORECASE):
                    continue

                codigo = ''
                rendimento = ''

                # Tenta com código numérico de 4 dígitos.
                # Ex.: "DIVS 6147 43843358/0003-50 26.592,17 1.555,64 17009"
                # Ex.: "DIVS 6147 43.843.358/0001-52 26.592,17 1.555,64 17009"
                m = re.match(
                    r'([A-Z][A-Z0-9]+)\s+(\d{4})\s+([\d.]{8,}/[\d\-]+)\s+([\d,.]+)\s+(-?[\d,.]+)(?:\s+(\d{5,}))?$',
                    linha
                )
                if m:
                    sit, codigo, recolhedor, base, val_garb, rendimento = m.groups()
                else:
                    # Sem código — situação já é o nome SIAFI ou código ausente.
                    m = re.match(
                        r'([A-Z][A-Z0-9]+)\s+([\d.]{8,}/[\d\-]+)\s+([\d,.]+)\s+(-?[\d,.]+)(?:\s+(\d{5,}))?$',
                        linha
                    )
                    if m:
                        sit, recolhedor, base, val_garb, rendimento = m.groups()
                    else:
                        continue

                valor_limpo = _ungarble(val_garb)
                base_limpa  = _ungarble(base)   # garbling também afeta a coluna Base Cálculo
                siafi_sit = (
                    codigo_situacao_siafi.get(codigo, '')
                    or sit   # quando sem código, o próprio nome é o SIAFI
                )

                lista_deducoes.append({
                    'Situação':       sit,
                    'Código':         codigo or '—',
                    'Situação SIAFI': siafi_sit,
                    'Recolhedor':     recolhedor,
                    'Base Cálculo':   base_limpa,
                    'Valor':          valor_limpo,
                    'Rendimento':     rendimento or '—',
                })

        dados_extraidos['Deduções'] = lista_deducoes
        dados_extraidos['_pagina_inicio'] = pagina_inicio + 1
        dados_extraidos['_pagina_fim'] = pagina_fim + 1

    dados_extraidos['CNPJ'] = _limpar_campo_documento(dados_extraidos.get('CNPJ', ''), "—")
    dados_extraidos['Processo'] = _limpar_campo_documento(dados_extraidos.get('Processo', ''), "—")
    dados_extraidos['Natureza'] = _limpar_campo_documento(dados_extraidos.get('Natureza', ''), "—")
    return dados_extraidos


def extrair_remessa_bolsa_pdf(caminho_pdf, nome_arquivo: str | None = None):
    texto = _texto_pdf(caminho_pdf)
    if not texto.strip():
        return None

    match_remessa = re.search(r"\bREMESSA\s+(\d+)", texto, re.IGNORECASE)
    numero_remessa = match_remessa.group(1).strip() if match_remessa else ""

    match_bolsa = re.search(
        r"Bolsa:\s*(.+?)\s+Mes\s*/\s*Ano:\s*([0-9]{1,2}/[0-9]{4})",
        texto,
        re.IGNORECASE,
    )
    bolsa_descricao = ""
    bolsa_codigo = ""
    mes_ano = ""
    if match_bolsa:
        bolsa_descricao = " ".join(match_bolsa.group(1).split())
        mes_ano = match_bolsa.group(2).strip()
        codigo_match = re.search(r"\((\d+)\)\s*$", bolsa_descricao)
        if codigo_match:
            bolsa_codigo = codigo_match.group(1)
            bolsa_descricao = bolsa_descricao[:codigo_match.start()].strip()

    match_data = re.search(r"\bData:\s*(\d{2}[-/]\d{2}[-/]\d{4})", texto, re.IGNORECASE)
    data_remessa = _normalizar_data_br(match_data.group(1)) if match_data else ""

    match_sol = re.search(r"Solicita[çc][aã]o\s+Pagamento:\s*(\d+)", texto, re.IGNORECASE)
    solicitacao_pagamento = match_sol.group(1).strip() if match_sol else ""

    match_processo = re.search(r"Processo:\s*([\d./-]+)", texto, re.IGNORECASE)
    processo = match_processo.group(1).strip() if match_processo else ""

    bolsistas = []
    linhas = texto.splitlines()
    lendo_tabela = False
    for linha in linhas:
        linha_limpa = " ".join(str(linha or "").split()).strip()
        if not linha_limpa:
            continue
        if re.search(r"\bNome\s+CPF\s+Banco\s+Ag[eê]ncia\s+Conta\s+Valor\b", linha_limpa, re.IGNORECASE):
            lendo_tabela = True
            continue
        if lendo_tabela and re.match(r"N[úu]mero\s+de\s+Bolsas:|Total\s*:", linha_limpa, re.IGNORECASE):
            break
        if not lendo_tabela:
            continue

        # CPF pode vir formatado (123.456.789-01) ou sem pontos (12345678901 ou 123456789-01).
        # Agência: 4-6 dígitos, possivelmente com dígito verificador separado por hífen.
        # Conta: alfanumérico com ponto ou hífen.
        # Valor: formato brasileiro (1.234,56) ou americano (1,234.56).
        # Sit/LC: valores opcionais de status e código de LC.
        match_linha = re.match(
            r"(.+?)\s+"
            r"(\d{3}\.?\d{3}\.?\d{3}-\d{2}|\d{11})\s+"
            r"(\d{3})\s+"
            r"(\d{1,6}(?:-\d+)?)\s+"
            r"([0-9A-Za-z.\-/]+)\s+"
            r"([\d.,]+)\s+"
            r"(\S+)"
            r"(?:\s+(\S+))?",
            linha_limpa,
        )
        if not match_linha:
            continue

        nome, cpf, banco, agencia, conta, valor, situacao_lc, lc = match_linha.groups()
        bolsistas.append({
            "nome": nome.strip(),
            "cpf": cpf.strip(),
            "banco": banco.strip(),
            "agencia": agencia.strip(),
            "conta": conta.strip(),
            "valor": _float_para_valor_brl(_valor_brl_para_float(valor)),
            "valorNumerico": round(_valor_brl_para_float(valor), 2),
            "situacaoLc": situacao_lc.strip(),
            "lc": (lc or "").strip(),
        })

    totais = {
        "quantidade": len(bolsistas),
        "valor": _float_para_valor_brl(sum(item["valorNumerico"] for item in bolsistas)),
        "valorNumerico": round(sum(item["valorNumerico"] for item in bolsistas), 2),
        "aceitosQuantidade": 0,
        "aceitosValor": "0,00",
        "rejeitadosQuantidade": 0,
        "rejeitadosValor": "0,00",
        "canceladosQuantidade": 0,
        "canceladosValor": "0,00",
        "pendentesQuantidade": 0,
        "pendentesValor": "0,00",
    }

    def _capturar_total(label: str) -> tuple[int, str, float] | None:
        m = re.search(rf"{label}:\s*(\d+)\s+([\d.]+,\d{{2}})", texto, re.IGNORECASE)
        if not m:
            return None
        valor = _float_para_valor_brl(_valor_brl_para_float(m.group(2)))
        return int(m.group(1)), valor, round(_valor_brl_para_float(valor), 2)

    total_doc = _capturar_total(r"N[úu]mero\s+de\s+Bolsas")
    if total_doc:
        totais["quantidade"], totais["valor"], totais["valorNumerico"] = total_doc

    for chave, label in (
        ("aceitos", "Aceitos"),
        ("rejeitados", "Rejeitados"),
        ("cancelados", "Cancelados"),
        ("pendentes", "Pendentes"),
    ):
        total = _capturar_total(label)
        if total:
            totais[f"{chave}Quantidade"], totais[f"{chave}Valor"], _ = total

    return {
        "numeroRemessa": numero_remessa,
        "bolsa": bolsa_descricao,
        "codigoBolsa": bolsa_codigo,
        "mesAno": mes_ano,
        "data": data_remessa,
        "solicitacaoPagamento": solicitacao_pagamento,
        "processo": processo,
        "nomeArquivo": Path(nome_arquivo or caminho_pdf).name,
        "bolsistas": bolsistas,
        "totais": totais,
    }


# ── TESTE ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    arquivo_teste = sys.argv[1] if len(sys.argv) > 1 else "Liquidação 202602971.pdf"
    r = extrair_dados_pdf(arquivo_teste, nome_arquivo=Path(arquivo_teste).name)
    if not r:
        sys.exit(1)

    print("── GERAL ────────────────────────────────────────")
    print(f"CNPJ:           {r['CNPJ']}")
    print(f"Processo:       {r['Processo']}")
    print(f"Sol. Pagamento: {r['Solicitação de Pagamento']}")
    print(f"Natureza:       {r['Natureza']}")
    print(f"Fonte:          {r['Fonte']}  |  Convênio: {r['Tem Convênio']}")
    print(f"Ateste (recente): {r['Data de Ateste']}")

    print("\n── NOTAS FISCAIS ────────────────────────────────")
    for n in r['Notas Fiscais']:
        print(f"  {n['Tipo']:12s}  {n['Número da Nota']:8s}  em:{n['Data de Emissão']}  at:{n['Data de Ateste']}  R${n['Valor']}")

    print("\n── EMPENHOS ─────────────────────────────────────")
    for e in r['Empenhos']:
        print(f"  {e['Empenho']}  {e['Situação']}  Recurso:{e['Recurso']}")

    print("\n── DEDUÇÕES ─────────────────────────────────────")
    for d in r['Deduções']:
        print(f"  {d['Situação']:8s}  cód:{d['Código']:4s}  SIAFI:{d['Situação SIAFI']:8s}"
              f"  recol:{d['Recolhedor']}  base:{d['Base Cálculo']}  val:{d['Valor']}"
              f"  DARF:{d['Rendimento']}")

    res = r['Resumo']
    print(f"\n── RESUMO ───────────────────────────────────────")
    print(f"  Bruto:{res['Valor Bruto']}  Ded:{res['Total Deduções']}  Líq:{res['Valor Líquido']}  Enc:{res['Valor Encargos']}")
