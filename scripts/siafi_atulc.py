"""
siafi_atulc.py
Automação da transação ATULC (Atualiza Lista de Credores) no SIAFI Tela Preta
via protocolo TN3270 usando a biblioteca py3270.

DEPENDÊNCIAS:
  pip install py3270
  macOS:  brew install x3270        (instala o binário s3270)
  Windows: baixar ws3270 em https://x3270.miraheze.org/wiki/Ws3270
           e adicionar ao PATH

FLUXO:
  1. Encontra e parseia o .jnlp do SIAFI em ~/Downloads → extrai host:porta
  2. Conecta ao mainframe via TN3270
  3. (Opcional) Faz login com CPF/senha se ainda não autenticado
  4. Na tela de COMANDO, digita "atulc" + Enter
  5. Preenche o formulário ATULC (UG, gestão, número da lista, etc.)
  6. Na tela de credores, preenche uma linha por credor (CPF, banco, agência, conta, valor)
  7. Confirma com Enter e retorna o resultado

USO:
  from scripts.siafi_atulc import executar_atulc

  resultado = executar_atulc(
      credores=[
          {"cpf": "01698811993", "banco": "001", "agencia": "0599", "conta": "1376349", "valor_centavos": 165000},
          {"cpf": "09267257935", "banco": "001", "agencia": "4550", "conta": "17592",   "valor_centavos":  47000},
      ],
      ug_emitente="153163",
      gestao_emitente="15237",
      # numero_lista não precisa ser passado — SIAFI gera e retorna
      sequencial="",              # deixar vazio se não aplicável
      suprimento_fundos="N",
      tipo_pagamento="1",
      # Credenciais: obrigatórias apenas se o SIAFI não estiver aberto/logado
      cpf_usuario=None,
      senha=None,
  )
"""

import os
import re
import sys
import time
import glob
import logging
import platform
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SISTEMA DE EVENTOS — usado pelo frontend para visualização em tempo real
# ─────────────────────────────────────────────────────────────────────────────

# Tipo do callback: on_update(acao, tela_linhas, estado)
#   acao       str  — descrição legível do que está acontecendo ("Digitando atulc...", etc.)
#   tela       list[str] — 24 linhas da tela 3270 atual (ou [] se não disponível)
#   estado     str  — identificador interno da tela ("menu", "atulc_form", etc.)
EventCallback = Callable[[str, list[str], str], None]

_noop_callback: EventCallback = lambda acao, tela, estado: None

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE TELA (posições 3270, base-1)
# Ajuste se o layout da sua versão do SIAFI for diferente.
# ─────────────────────────────────────────────────────────────────────────────

# Tela de Login
LOGIN_LINHA_USUARIO   = 7   # linha onde fica o campo de usuário/CPF
LOGIN_LINHA_SENHA     = 9   # linha onde fica o campo de senha
LOGIN_COL_VALOR       = 20  # coluna onde começa o campo

# Tela principal (COMANDO:)
MENU_LINHA_COMANDO    = 23  # linha do campo COMANDO
MENU_COL_COMANDO      = 11  # coluna onde começa o input (após "COMANDO: >")

# Tela ATULC – formulário
ATULC_LINHA_UG        = 5   # linha de UG/GESTAO EMITENTE
ATULC_COL_NUMERO      = 49  # coluna de NUMERO DA LISTA
ATULC_LINHA_NUMERO    = 5
ATULC_LINHA_SEQ       = 6   # linha de SEQUENCIAL
ATULC_COL_SEQ         = 20
ATULC_LINHA_CREDOR    = 7   # linha de FAVORECIDO/CREDOR (opcional)
ATULC_COL_CREDOR      = 20
ATULC_LINHA_SUPRIM    = 8
ATULC_COL_SUPRIM      = 20
ATULC_LINHA_TIPO      = 9
ATULC_COL_TIPO        = 20

# Tela de credores – grade
CREDORES_LINHA_INICIO = 4   # primeira linha de dados
CREDORES_COL_CPF      = 9   # coluna do CPF/CNPJ
CREDORES_COL_BANCO    = 23  # coluna do banco
CREDORES_COL_AGENCIA  = 27  # coluna da agência
CREDORES_COL_CONTA    = 32  # coluna da conta
CREDORES_COL_VALOR    = 50  # coluna do valor (centavos, sem ponto/vírgula)
CREDORES_LINHAS_PAG   = 7   # linhas de credores por página


# ─────────────────────────────────────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────────────────────────────────────

def _encontrar_jnlp() -> Optional[Path]:
    """Procura o arquivo .jnlp do SIAFI na pasta Downloads do usuário."""
    downloads = Path.home() / "Downloads"
    candidatos = sorted(downloads.glob("*.jnlp"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidatos:
        conteudo = p.read_text(errors="ignore")
        if "siafi" in conteudo.lower() or "serpro" in conteudo.lower():
            logger.info(f"JNLP encontrado: {p}")
            return p
    # Fallback: qualquer .jnlp mais recente
    if candidatos:
        logger.warning(f"Usando o .jnlp mais recente (sem garantia de ser o SIAFI): {candidatos[0]}")
        return candidatos[0]
    return None


def _parsear_host_porta(jnlp_path: Path) -> tuple[str, int]:
    """
    Extrai host e porta de um arquivo .jnlp do SIAFI.
    Tenta várias estratégias porque o formato varia por versão.
    Retorna (host, porta).
    """
    conteudo = jnlp_path.read_text(errors="ignore")

    # Estratégia 1: argumento explícito -hostname= e -port=
    host_m = re.search(r"-hostname=([^\s<\"']+)", conteudo)
    port_m = re.search(r"-port=(\d+)", conteudo)
    if host_m and port_m:
        return host_m.group(1), int(port_m.group(1))

    # Estratégia 2: atributo "host" e "port" no XML
    try:
        root = ET.fromstring(conteudo)
        ns = {"j": "http://www.jcp.org/jnlp/1.0"}

        def find_attr(tag, attr):
            el = root.find(f".//{tag}")
            if el is not None:
                return el.get(attr)
            return None

        host = find_attr("applet-desc", "documentbase") or find_attr("resources", "href")
        # Procura <param name="host" value="..."> e <param name="port" value="...">
        for param in root.iter("param"):
            name = param.get("name", "").lower()
            if name in ("host", "hostname"):
                host = param.get("value", host)
            if name == "port":
                port_m = param.get("value")
    except ET.ParseError:
        pass

    # Estratégia 3: URL no próprio jnlp href
    href_m = re.search(r'href="([^"]+)"', conteudo)
    if href_m:
        url = href_m.group(1)
        url_host = re.search(r"https?://([^/:]+)", url)
        if url_host:
            host = host or url_host.group(1)

    # Estratégia 4: busca por IP/hostname genérico
    ip_m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', conteudo)
    if ip_m and not host_m:
        host = ip_m.group(1)

    porta = int(port_m.group(1)) if isinstance(port_m, re.Match) else 9623
    host = host or "siafi.serpro.gov.br"

    logger.info(f"Conexão TN3270: {host}:{porta}")
    return host, porta


def _cpf_sem_formatacao(cpf: str) -> str:
    """Remove pontos e traços do CPF: '016.988.119-93' → '01698811993'"""
    return re.sub(r"[.\-]", "", cpf.strip())


def _valor_centavos(valor) -> str:
    """
    Converte valor para string no formato SIAFI (centavos inteiros, sem separadores).
    Aceita int (já em centavos), float (em reais) ou str ('1.650,00' ou '1650.00').
    """
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return str(int(round(valor * 100)))
    s = str(valor).strip().replace("R$", "").replace(" ", "")
    # Formato brasileiro: 1.650,00
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return str(int(round(float(s) * 100)))


# ─────────────────────────────────────────────────────────────────────────────
# DETECÇÃO DE TELA
# ─────────────────────────────────────────────────────────────────────────────

def _ler_tela(m) -> list[str]:
    """Lê as 24 linhas da tela 3270 e retorna como lista de strings."""
    linhas = []
    for row in range(1, 25):
        try:
            linhas.append(m.string_get(row, 1, 80))
        except Exception:
            linhas.append("")
    return linhas


def _detectar_estado(linhas: list[str]) -> str:
    """
    Identifica em qual tela do SIAFI estamos.
    Retorna: 'login', 'menu', 'atulc_form', 'atulc_credores', 'erro', 'desconhecido'
    """
    tela = "\n".join(linhas).upper()
    if "SENHA" in tela and ("USUARIO" in tela or "CPF" in tela) and "SIAFI" in tela:
        return "login"
    if "COMANDO:" in tela and ("PF3=SAI" in tela or "PF8=AVANCA" in tela):
        return "menu"
    if "ATULC" in tela and "NUMERO DA LISTA" in tela:
        return "atulc_form"
    if "CREDOR/FAVORECIDO" in tela and "DOMICILIO BANCARIO" in tela:
        return "atulc_credores"
    if "ERRO" in tela or "INVALIDO" in tela or "NAO ENCONTRADO" in tela:
        return "erro"
    return "desconhecido"


# ─────────────────────────────────────────────────────────────────────────────
# AÇÕES DE TELA
# ─────────────────────────────────────────────────────────────────────────────

def _aguardar_pronto(m, timeout: float = 15.0):
    """Espera o emulador sinalizar que o campo está pronto para input."""
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            m.wait_for_field()
            return
        except Exception:
            time.sleep(0.3)
    raise TimeoutError("SIAFI não respondeu em tempo hábil")


def _fazer_login(m, cpf_usuario: str, senha: str, on_update: EventCallback = _noop_callback):
    """Preenche as credenciais na tela de login do SIAFI."""
    logger.info("Realizando login no SIAFI...")
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    estado = _detectar_estado(linhas)
    if estado != "login":
        logger.info(f"Tela atual: {estado} — login não necessário")
        return

    on_update("Digitando usuário e senha...", linhas, estado)
    m.move_to(LOGIN_LINHA_USUARIO, LOGIN_COL_VALOR)
    m.send_string(_cpf_sem_formatacao(cpf_usuario))
    m.send_tab()

    m.move_to(LOGIN_LINHA_SENHA, LOGIN_COL_VALOR)
    m.send_string(senha)
    m.send_enter()
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    on_update("Login enviado, aguardando menu...", linhas, _detectar_estado(linhas))
    logger.info("Login enviado")


def _ir_para_atulc(m, on_update: EventCallback = _noop_callback):
    """Da tela de menu (COMANDO:), digita 'atulc' e pressiona Enter."""
    logger.info("Navegando para transação ATULC...")
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    estado = _detectar_estado(linhas)
    if estado != "menu":
        raise RuntimeError(f"Esperava tela de menu, encontrei: {estado}\n" + "\n".join(linhas[:5]))

    on_update("Digitando >atulc no campo COMANDO...", linhas, estado)
    m.move_to(MENU_LINHA_COMANDO, MENU_COL_COMANDO)
    m.send_string("\x1b")  # clear field (se suportado)
    m.send_string("atulc")
    m.send_enter()
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    on_update("Formulário ATULC aberto", linhas, _detectar_estado(linhas))


def _preencher_formulario_atulc(
    m,
    ug_emitente: str,
    gestao_emitente: str,
    numero_lista: str,
    sequencial: str,
    suprimento_fundos: str,
    tipo_pagamento: str,
    on_update: EventCallback = _noop_callback,
):
    """Preenche o formulário da transação ATULC (primeira tela após o comando)."""
    logger.info("Preenchendo formulário ATULC...")
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    estado = _detectar_estado(linhas)
    if estado != "atulc_form":
        raise RuntimeError(f"Esperava formulário ATULC, encontrei: {estado}\n" + "\n".join(linhas[:5]))

    on_update("Preenchendo formulário ATULC...", linhas, estado)

    # Tab navega pelos campos na ordem da tela.
    # A ordem esperada: UG → GESTAO → NUMERO_LISTA → SEQUENCIAL → FAVORECIDO → SUPRIMENTO → TIPO
    m.send_tab()  # pula UG (já preenchido)
    m.send_tab()  # pula GESTAO (já preenchido)

    # NUMERO DA LISTA: deixa vazio — o SIAFI atribui e retorna o número ao final
    if numero_lista:
        m.send_string(numero_lista)
    m.send_tab()

    if sequencial:
        m.send_string(sequencial)
    m.send_tab()

    m.send_tab()  # FAVORECIDO/CREDOR (opcional)

    m.send_string(suprimento_fundos)
    m.send_tab()

    m.send_string(tipo_pagamento)
    m.send_enter()
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    on_update("Abrindo lista de credores...", linhas, _detectar_estado(linhas))
    logger.info("Formulário ATULC enviado")


def _preencher_credores(m, credores: list[dict], on_update: EventCallback = _noop_callback):
    """
    Preenche a tela de credores do ATULC.
    Cada credor deve ter: cpf, banco, agencia, conta, valor_centavos (int) ou valor (R$).
    """
    total = len(credores)
    logger.info(f"Preenchendo {total} credor(es)...")
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    estado = _detectar_estado(linhas)
    if estado != "atulc_credores":
        raise RuntimeError(f"Esperava tela de credores, encontrei: {estado}\n" + "\n".join(linhas[:5]))

    on_update(f"Iniciando preenchimento de {total} credor(es)...", linhas, estado)

    for i, credor in enumerate(credores):
        if i > 0 and i % CREDORES_LINHAS_PAG == 0:
            logger.info(f"Avançando página de credores (PF8) — credor {i+1}")
            m.send_pf(8)
            _aguardar_pronto(m)

        linha = CREDORES_LINHA_INICIO + (i % CREDORES_LINHAS_PAG)
        cpf     = _cpf_sem_formatacao(credor.get("cpf", ""))
        banco   = credor.get("banco", "").zfill(3)
        agencia = credor.get("agencia", "")
        conta   = credor.get("conta", "")
        valor   = _valor_centavos(credor.get("valor_centavos") or credor.get("valor", 0))

        logger.debug(f"  Linha {linha}: CPF={cpf} banco={banco} ag={agencia} conta={conta} valor={valor}")

        linhas_atuais = _ler_tela(m)
        on_update(
            f"Credor {i+1}/{total}: {cpf[:3]}.***.{cpf[-2:]}",
            linhas_atuais,
            _detectar_estado(linhas_atuais),
        )

        m.move_to(linha, CREDORES_COL_CPF)
        m.send_string(cpf)
        m.move_to(linha, CREDORES_COL_BANCO)
        m.send_string(banco)
        m.move_to(linha, CREDORES_COL_AGENCIA)
        m.send_string(agencia)
        m.move_to(linha, CREDORES_COL_CONTA)
        m.send_string(conta)
        m.move_to(linha, CREDORES_COL_VALOR)
        m.send_string(valor)

    m.send_enter()
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    on_update("Confirmando lista de credores...", linhas, _detectar_estado(linhas))
    logger.info("Credores enviados")


def _extrair_numero_lista(linhas: list[str]) -> Optional[str]:
    """
    Tenta extrair o número da lista LC gerado pelo SIAFI após a confirmação.
    O SIAFI costuma exibir algo como:
      NUMERO DA LISTA : 2026LC001
      ou na mensagem de sucesso: LISTA 2026LC001 INCLUIDA
    """
    tela = "\n".join(linhas)
    # Padrão: YYYYLCNNN (4 dígitos + LC + dígitos)
    m = re.search(r'\b(\d{4}LC\d+)\b', tela, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _ler_resultado(m) -> dict:
    """
    Lê a tela após a confirmação e retorna status, mensagem e o número da lista
    gerado pelo SIAFI (campo `numero_lista`).
    """
    linhas = _ler_tela(m)
    tela = "\n".join(linhas)
    estado = _detectar_estado(linhas)

    numero_lista = _extrair_numero_lista(linhas)

    if estado == "erro":
        msg = next((l.strip() for l in linhas if l.strip()), "Erro desconhecido")
        return {"ok": False, "estado": estado, "mensagem": msg, "tela": tela, "numero_lista": None}

    if any(k in tela.upper() for k in ("OPERACAO REALIZADA", "GRAVADO", "CONFIRMADO", "INCLUIDO")):
        msg = f"Lista {numero_lista} gerada com sucesso" if numero_lista else "Operação realizada com sucesso"
        return {"ok": True, "estado": estado, "mensagem": msg, "tela": tela, "numero_lista": numero_lista}

    return {"ok": True, "estado": estado, "mensagem": "Operação enviada (verifique a tela)", "tela": tela, "numero_lista": numero_lista}


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def _detectar_codigo_acesso(linhas: list[str]) -> bool:
    """Retorna True se a tela está pedindo o Código de Acesso HOD."""
    tela = "\n".join(linhas).upper()
    return "CODIGO DE ACESSO" in tela


def _digitar_codigo_acesso(m, codigo: str, on_update: EventCallback = _noop_callback):
    """
    Digita o Código de Acesso HOD na tela inicial do SIAFI tela preta.
    Esse código é gerado pelo SIAFI Web e muda a cada sessão.
    """
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    if not _detectar_codigo_acesso(linhas):
        return  # tela não pede código, pula

    on_update("Digitando Código de Acesso HOD...", linhas, "codigo_acesso")
    logger.info("Tela de Código de Acesso detectada — preenchendo...")

    # O campo de código fica na linha 19, coluna variável — localizamos pelo cursor
    # ou digitamos diretamente após posicionar com Tab
    m.send_string(codigo.strip())
    m.send_enter()
    _aguardar_pronto(m)
    linhas = _ler_tela(m)
    on_update("Código de acesso enviado, aguardando menu...", linhas, _detectar_estado(linhas))
    logger.info("Código de acesso enviado")


def executar_atulc(
    credores: list[dict],
    codigo_acesso: str = "",
    ug_emitente: str = "153163",
    gestao_emitente: str = "15237",
    numero_lista: str = "",
    sequencial: str = "",
    suprimento_fundos: str = "N",
    tipo_pagamento: str = "1",
    cpf_usuario: Optional[str] = None,
    senha: Optional[str] = None,
    jnlp_path: Optional[str] = None,
    host: Optional[str] = None,
    porta: Optional[int] = None,
    on_update: EventCallback = _noop_callback,
) -> dict:
    """
    Executa a transação ATULC no SIAFI tela preta.

    FLUXO DE AUTENTICAÇÃO:
      1. O SIAFI Web gera um "Código de Acesso HOD" temporário (muda a cada sessão).
         Passe-o via `codigo_acesso`. O Playwright pode raspar esse código
         automaticamente do popup no SIAFI Web antes de chamar esta função.
      2. O terminal pede o código → digitamos → abre o menu principal.
      3. Se o SIAFI tiver tela de login (usuário/senha), passamos cpf_usuario/senha.

    Parâmetros:
        credores           Lista de dicts: cpf, banco, agencia, conta,
                           valor_centavos (int) OU valor (str "R$" ou float reais).
        codigo_acesso      Código de Acesso HOD gerado pelo SIAFI Web (obrigatório
                           quando o terminal ainda não tem sessão ativa).
        ug_emitente        UG emitente (default '153163')
        gestao_emitente    Gestão emitente (default '15237')
        numero_lista       Deixe vazio (padrão). O SIAFI gera e retorna o número
                           da lista automaticamente após o cadastro dos credores.
                           O número retornado fica em resultado["numero_lista"].
        sequencial         Sequencial (opcional)
        suprimento_fundos  'N' ou 'S'
        tipo_pagamento     '1' (padrão)
        cpf_usuario        CPF do usuário SIAFI (se houver tela de login separada)
        senha              Senha SIAFI
        jnlp_path          Caminho para o .jnlp (se None, busca em ~/Downloads)
        host               Host TN3270 direto (sobrescreve .jnlp)
        porta              Porta TN3270 (sobrescreve .jnlp, default 9623)
        on_update          Callback(acao, tela_linhas, estado) para streaming ao frontend

    Retorna:
        dict com chaves: ok (bool), mensagem (str), estado (str), tela (str)
    """
    try:
        from py3270 import Emulator
    except ImportError:
        return {
            "ok": False,
            "mensagem": (
                "py3270 não instalado. Execute:\n"
                "  pip install py3270\n"
                "  macOS:   brew install x3270\n"
                "  Windows: instale ws3270 e adicione ao PATH"
            ),
            "estado": "erro_instalacao",
            "tela": "",
        }

    # ── Resolve host:porta ──────────────────────────────────────────────────
    if not (host and porta):
        caminho_jnlp = Path(jnlp_path) if jnlp_path else _encontrar_jnlp()
        if caminho_jnlp:
            h, p = _parsear_host_porta(caminho_jnlp)
            host  = host  or h
            porta = porta or p
        else:
            logger.warning(
                ".jnlp não encontrado em ~/Downloads. "
                "Abra o SIAFI no navegador para baixar o .jnlp primeiro."
            )
            host  = host  or "siafi.serpro.gov.br"
            porta = porta or 9623

    destino = f"{host}:{porta}"
    logger.info(f"Conectando ao SIAFI em {destino}...")
    on_update(f"Conectando ao SIAFI ({destino})...", [], "conectando")

    is_windows = platform.system() == "Windows"

    try:
        m = Emulator(use_emulator="ws3270" if is_windows else "s3270", visible=False)
        m.connect(destino)
        _aguardar_pronto(m)

        # ── Código de Acesso HOD (primeira tela) ───────────────────────────
        if codigo_acesso:
            _digitar_codigo_acesso(m, codigo_acesso, on_update)
        else:
            linhas = _ler_tela(m)
            if _detectar_codigo_acesso(linhas):
                on_update("Aguardando Código de Acesso HOD...", linhas, "codigo_acesso")
                return {
                    "ok": False,
                    "mensagem": (
                        "O SIAFI está pedindo o Código de Acesso HOD. "
                        "Abra o SIAFI Web, copie o código gerado e passe-o "
                        "via parâmetro `codigo_acesso`."
                    ),
                    "estado": "aguardando_codigo_acesso",
                    "tela": "\n".join(linhas),
                }

        # ── Login usuário/senha (se necessário) ────────────────────────────
        if cpf_usuario and senha:
            _fazer_login(m, cpf_usuario, senha, on_update)

        # ── Verifica menu ──────────────────────────────────────────────────
        linhas = _ler_tela(m)
        estado = _detectar_estado(linhas)
        if estado == "login":
            return {
                "ok": False,
                "mensagem": "SIAFI ainda na tela de login. Informe cpf_usuario e senha.",
                "estado": estado,
                "tela": "\n".join(linhas),
            }

        # ── Executa o fluxo ATULC ──────────────────────────────────────────
        _ir_para_atulc(m, on_update)
        _preencher_formulario_atulc(
            m,
            ug_emitente=ug_emitente,
            gestao_emitente=gestao_emitente,
            numero_lista=numero_lista,
            sequencial=sequencial,
            suprimento_fundos=suprimento_fundos,
            tipo_pagamento=tipo_pagamento,
            on_update=on_update,
        )
        _preencher_credores(m, credores, on_update)
        resultado = _ler_resultado(m)
        nr = resultado.get("numero_lista")
        msg_fim = f"✓ Lista {nr} gerada com sucesso" if nr else "✓ " + resultado.get("mensagem", "Concluído")
        on_update(msg_fim, _ler_tela(m), resultado.get("estado", ""))

    except Exception as e:
        logger.exception("Erro ao executar ATULC")
        return {
            "ok": False,
            "mensagem": str(e),
            "estado": "excecao",
            "tela": "",
        }
    finally:
        try:
            m.terminate()
        except Exception:
            pass

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# CLI RÁPIDO PARA TESTE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Teste rápido via terminal:
      python scripts/siafi_atulc.py
    """
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")

    # Exemplo com os dados do screenshot
    resultado = executar_atulc(
        credores=[
            {"cpf": "016988119-93", "banco": "001", "agencia": "0599", "conta": "1376349", "valor": "1650,00"},
            {"cpf": "092672579-35", "banco": "001", "agencia": "4550", "conta": "17592",   "valor":  "470,00"},
        ],
        ug_emitente="153163",
        gestao_emitente="15237",
        numero_lista="2026LC001",
        suprimento_fundos="N",
        tipo_pagamento="1",
        # cpf_usuario="00000000000",
        # senha="SUASENHA",
    )

    print("\n─── RESULTADO ───")
    print(f"OK:       {resultado['ok']}")
    print(f"Mensagem: {resultado['mensagem']}")
    print(f"Estado:   {resultado['estado']}")
    if resultado.get("tela"):
        print("\n─── ÚLTIMA TELA ───")
        print(resultado["tela"])
