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
import shutil
import socket
import subprocess
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


def _ler_cfg_hod_terminal() -> Optional[tuple[str, int, bool]]:
    """Lê o cache local do IBM HOD e retorna host/porta/SSL da sessão Terminal 3270."""
    candidatos = sorted((Path.home() / "HODServers").glob("**/cfg*.cf"))
    for cfg in candidatos:
        try:
            valores: dict[str, str] = {}
            for raw in cfg.read_text(errors="ignore").splitlines():
                if "=" not in raw:
                    continue
                chave, valor = raw.split("=", 1)
                valores[chave.strip()] = valor.strip()
        except Exception:
            continue

        nome = valores.get("name") or valores.get("sessionName") or ""
        if nome.lower() != "terminal 3270":
            continue
        host = valores.get("host", "").strip()
        porta = valores.get("port", "").strip()
        if host and porta.isdigit():
            ssl = valores.get("SSL", "").strip().lower() == "true"
            logger.info(f"Config HOD local encontrada: {cfg} -> {host}:{porta} SSL={ssl}")
            return host, int(porta), ssl
    return None


def _ler_cfg_hod_terminal_detalhado() -> Optional[dict[str, object]]:
    """Lê o cache IBM HOD e retorna os dados completos da sessão Terminal 3270."""
    candidatos = sorted((Path.home() / "HODServers").glob("**/cfg*.cf"))
    for cfg in candidatos:
        try:
            valores: dict[str, str] = {}
            for raw in cfg.read_text(errors="ignore").splitlines():
                if "=" not in raw:
                    continue
                chave, valor = raw.split("=", 1)
                valores[chave.strip()] = valor.strip()
        except Exception:
            continue

        nome = valores.get("name") or valores.get("sessionName") or ""
        if nome.lower() != "terminal 3270":
            continue
        host = valores.get("host", "").strip()
        porta = valores.get("port", "").strip()
        if not (host and porta.isdigit()):
            continue
        return {
            "cfg": cfg,
            "host": host,
            "porta": int(porta),
            "ssl": valores.get("SSL", "").strip().lower() == "true",
            "lu": valores.get("LUName", "").strip(),
            "valores": valores,
        }
    return None


def _extrair_lu_jnlp(jnlp_path: Optional[Path]) -> str:
    """Extrai o LUName do .jnlp, quando o SIAFI Web informa algo como Terminal 3270=AWVAMONE."""
    if not jnlp_path or not jnlp_path.exists():
        return ""
    conteudo = jnlp_path.read_text(errors="ignore")
    match = re.search(r'jnlp\.hod\.LUName["\']\s+value=["\'][^=]+=\s*([^"\']+)', conteudo)
    if match:
        return match.group(1).strip()
    match = re.search(r'Terminal\s+3270\s*=\s*([A-Z0-9_-]+)', conteudo, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parsear_host_porta(jnlp_path: Path) -> tuple[str, int, bool]:
    """
    Extrai host e porta de um arquivo .jnlp do SIAFI.
    Tenta várias estratégias porque o formato varia por versão.
    Retorna (host, porta, ssl).
    """
    cfg_hod = _ler_cfg_hod_terminal()
    if cfg_hod:
        return cfg_hod

    conteudo = jnlp_path.read_text(errors="ignore")
    host: Optional[str] = None
    port_m = None

    # Estratégia 1: argumento explícito -hostname= e -port=
    host_m = re.search(r"-hostname=([^\s<\"']+)", conteudo)
    port_m = re.search(r"-port=(\d+)", conteudo)
    if host_m and port_m:
        return host_m.group(1), int(port_m.group(1)), False

    # Estratégia 2: atributo "host" e "port" no XML
    try:
        root = ET.fromstring(conteudo)
        ns = {"j": "http://www.jcp.org/jnlp/1.0"}

        def find_attr(tag, attr):
            el = root.find(f".//{tag}")
            if el is not None:
                return el.get(attr)
            return None

        # Procura <param name="host" value="..."> e <param name="port" value="...">
        for param in root.iter("param"):
            name = param.get("name", "").lower()
            if name in ("host", "hostname"):
                host = param.get("value", host)
            if name == "port":
                port_m = param.get("value")
    except ET.ParseError:
        pass

    # Estratégia 3: busca por IP/hostname genérico. Não usa codebase/href do
    # JNLP como host TN3270, pois ali normalmente fica o servidor web do HOD.
    ip_m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', conteudo)
    if ip_m and not host_m:
        host = ip_m.group(1)

    porta = int(port_m.group(1)) if isinstance(port_m, re.Match) else int(port_m) if port_m else 9623
    if not host:
        raise RuntimeError(
            "O hodcivws.jnlp baixado não informa o host TN3270 da sessão. "
            "Ele contém apenas o servidor web do HOD. Abra o HOD/Java uma vez "
            "ou informe o host TN3270 real para o AutoLiquid conectar."
        )

    logger.info(f"Conexão TN3270: {host}:{porta}")
    return host, porta, False


def _validar_destino_3270(host: str, porta: int, timeout_s: float = 6.0) -> None:
    """Falha rápido se o destino TN3270 não aceitar conexão."""
    try:
        with socket.create_connection((host, int(porta)), timeout=timeout_s):
            return
    except Exception as exc:
        raise TimeoutError(f"Não foi possível conectar ao TN3270 em {host}:{porta}: {exc}") from exc


def _formatar_destino_3270(host: str, porta: int, ssl: bool = False) -> str:
    """Formata destino para x3270/s3270. Prefixo L: ativa TLS direto."""
    prefixo = "L:" if ssl else ""
    return f"{prefixo}{host}:{porta}"


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


def _resolver_emulador_3270() -> str:
    """Resolve o executável 3270 mesmo quando o app não herda o PATH do shell."""
    if platform.system() == "Windows":
        return shutil.which("ws3270") or "ws3270"
    return (
        shutil.which("s3270")
        or next(
            (
                str(candidato)
                for candidato in (
                    Path("/opt/homebrew/bin/s3270"),
                    Path("/usr/local/bin/s3270"),
                    Path("/opt/homebrew/opt/x3270/bin/s3270"),
                    Path("/usr/local/opt/x3270/bin/s3270"),
                )
                if candidato.exists()
            ),
            "s3270",
        )
    )


def _preparar_ambiente_3270() -> None:
    """Garante que s3270 esteja no PATH visto pelo app/JavaScript desktop."""
    caminhos = ["/opt/homebrew/bin", "/usr/local/bin"]
    atual = os.environ.get("PATH", "")
    partes = atual.split(os.pathsep) if atual else []
    for caminho in reversed(caminhos):
        if caminho not in partes and Path(caminho).exists():
            partes.insert(0, caminho)
    os.environ["PATH"] = os.pathsep.join(partes)


def _criar_emulador_3270(Emulator):
    _preparar_ambiente_3270()
    return Emulator(
        visible=False,
        timeout=15,
        args=[
            "-connecttimeout", "10",
            "-noverifycert",
        ],
    )


def _resolver_hod_webstart_bundle() -> Optional[Path]:
    """Localiza o bundle WebStart cacheado que abre o IBM HOD do SIAFI."""
    bundles_dir = Path.home() / "Library/Application Support/Oracle/Java/Deployment/cache/6.0/bundles"
    candidatos = sorted(bundles_dir.glob("*.app"), key=lambda p: p.stat().st_mtime, reverse=True)
    for app in candidatos:
        info = app / "Contents" / "Info.plist"
        try:
            texto = info.read_text(errors="ignore")
        except Exception:
            texto = ""
        nome = app.name.lower()
        if "painel de controle" in nome or "host on-demand" in texto.lower() or "hod" in texto.lower():
            return app
    return None


def _abrir_hod_webstart(jnlp_path: Optional[Path]) -> str:
    """Abre o IBM HOD pelo WebStart real; este é o cliente que negocia SSL com o SERPRO."""
    app = _resolver_hod_webstart_bundle()
    if app:
        subprocess.Popen(["open", str(app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(app)

    if jnlp_path and jnlp_path.exists():
        javaws = shutil.which("javaws") or "/usr/bin/javaws"
        subprocess.Popen([javaws, str(jnlp_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(jnlp_path)

    raise RuntimeError("Bundle WebStart/JNLP do IBM HOD não encontrado. Clique em SIAFI Operacional para baixar o hodcivws.jnlp.")


def _processo_java_hod_conectado(porta: int) -> Optional[int]:
    """Retorna o PID Java conectado à porta HOD, quando o WebStart está ativo."""
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    for linha in result.stdout.splitlines():
        partes = linha.split()
        if len(partes) < 2:
            continue
        if partes[0].lower() != "java":
            continue
        if f":{porta}" not in linha or "ESTABLISHED" not in linha:
            continue
        try:
            return int(partes[1])
        except ValueError:
            return None
    return None


def _applescript_string(texto: str) -> str:
    """Escapa texto para uso seguro em string literal do AppleScript."""
    return '"' + str(texto).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _digitar_texto_no_hod_webstart(pid: int, texto: str, enter: bool = True) -> tuple[bool, str]:
    """Tenta focar a janela Java/HOD e digitar texto pelo macOS."""
    texto = str(texto or "")
    if not texto:
        return False, "Texto vazio para digitar no HOD."
    if platform.system() != "Darwin":
        return False, "Digitação automática do HOD só está implementada no macOS."

    enter_script = "      key code 36\n" if enter else ""
    script = f'''
    tell application "System Events"
      set targetProcess to first process whose unix id is {int(pid)}
      set frontmost of targetProcess to true
      delay 0.8
      keystroke {_applescript_string(texto)}
{enter_script}    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "osascript falhou").strip()
    return True, "Texto digitado na janela Java/HOD."


def _digitar_codigo_no_hod_webstart(pid: int, codigo: str) -> tuple[bool, str]:
    """Tenta focar a janela Java/HOD e digitar o Código HOD pelo macOS."""
    codigo = re.sub(r"\D", "", codigo or "")
    if not codigo:
        return False, "Código HOD vazio."
    ok, detalhe = _digitar_texto_no_hod_webstart(pid, codigo, enter=True)
    if ok:
        return True, "Código HOD digitado na janela Java/HOD."
    return ok, detalhe


def _resolver_contexto_hod_webstart(
    jnlp_path: Optional[str] = None,
    host: Optional[str] = None,
    porta: Optional[int] = None,
) -> tuple[Optional[Path], Optional[dict[str, object]], str, int, bool, str]:
    """Resolve jnlp/cache, host, porta, SSL e LUName do HOD WebStart."""
    caminho_jnlp = Path(jnlp_path).expanduser() if jnlp_path else _encontrar_jnlp()
    cfg_hod = _ler_cfg_hod_terminal_detalhado()
    ssl = False
    if not (host and porta):
        if cfg_hod:
            h = str(cfg_hod["host"])
            p = int(cfg_hod["porta"])
            ssl_cfg = bool(cfg_hod["ssl"])
            host = host or h
            porta = porta or p
            ssl = ssl_cfg
        elif caminho_jnlp:
            h, p, ssl_cfg = _parsear_host_porta(caminho_jnlp)
            host = host or h
            porta = porta or p
            ssl = ssl_cfg
        else:
            host = host or "hod.serpro.gov.br"
            porta = porta or 23000
    elif cfg_hod:
        ssl = bool(cfg_hod["ssl"])

    host_resolvido = str(host or "hod.serpro.gov.br")
    porta_resolvida = int(porta or 23000)
    lu = _extrair_lu_jnlp(caminho_jnlp) or (str(cfg_hod.get("lu") or "") if cfg_hod else "")
    return caminho_jnlp, cfg_hod, host_resolvido, porta_resolvida, ssl, lu


def _linhas_status_hod_comando(host: str, porta: int, lu: str, comando: str, conectado: bool, enviado: bool) -> list[str]:
    linhas = [
        "SIAFI Terminal 3270 - IBM HOD WebStart",
        "",
        f"Host: {host}",
        f"Porta: {porta}",
        f"LUName: {lu or '(nao informado)'}",
        "",
        "Gerar LC nesta etapa usa a janela Java/HOD ja aberta.",
        "A automacao direta TN3270/s3270 nao e usada aqui.",
        "",
        f"Conexao Java/HOD: {'estabelecida' if conectado else 'nao localizada'}",
        f"Comando: {comando}",
        f"Envio do comando: {'enviado' if enviado else 'pendente'}",
    ]
    return linhas[:24]


def _linhas_status_hod(host: str, porta: int, lu: str, codigo: str, origem: str, conectado: bool, digitado: bool) -> list[str]:
    linhas = [
        "SIAFI Terminal 3270 - IBM HOD WebStart",
        "",
        f"Host: {host}",
        f"Porta: {porta}",
        f"LUName: {lu or '(nao informado)'}",
        f"Origem: {origem}",
        "",
        "O host/porta foram descobertos no cache local do IBM HOD.",
        "O .jnlp baixado pelo navegador e apenas o lancador WebStart.",
        "",
        f"Conexao Java/HOD: {'estabelecida' if conectado else 'aguardando'}",
    ]
    if codigo:
        linhas.append(f"Codigo HOD capturado: {codigo}")
        linhas.append("Digitacao automatica: " + ("enviada" if digitado else "pendente/bloqueada pelo macOS"))
    return linhas[:24]


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


def abrir_terminal_siafi(
    codigo_acesso: str = "",
    jnlp_path: Optional[str] = None,
    host: Optional[str] = None,
    porta: Optional[int] = None,
    on_update: EventCallback = _noop_callback,
) -> dict:
    """Abre o SIAFI tela preta pelo IBM HOD WebStart real, sem executar ATULC."""
    try:
        caminho_jnlp = Path(jnlp_path) if jnlp_path else _encontrar_jnlp()
        cfg_hod = _ler_cfg_hod_terminal_detalhado()
        ssl = False
        if not (host and porta):
            if cfg_hod:
                h = str(cfg_hod["host"])
                p = int(cfg_hod["porta"])
                ssl_cfg = bool(cfg_hod["ssl"])
                host = host or h
                porta = porta or p
                ssl = ssl_cfg
            elif caminho_jnlp:
                h, p, ssl_cfg = _parsear_host_porta(caminho_jnlp)
                host = host or h
                porta = porta or p
                ssl = ssl_cfg
            else:
                host = host or "hod.serpro.gov.br"
                porta = porta or 23000
        elif cfg_hod:
            ssl = bool(cfg_hod["ssl"])

        host = str(host or "hod.serpro.gov.br")
        porta = int(porta or 23000)
        lu = _extrair_lu_jnlp(caminho_jnlp) or (str(cfg_hod.get("lu") or "") if cfg_hod else "")
        origem = _abrir_hod_webstart(caminho_jnlp)
        codigo_limpo = re.sub(r"\D", "", codigo_acesso or "")
        linhas = _linhas_status_hod(host, porta, lu, codigo_limpo, origem, False, False)
        on_update(f"Abrindo IBM HOD WebStart ({host}:{porta})...", linhas, "hod_webstart_abrindo")

        pid: Optional[int] = None
        limite = time.time() + 45
        while time.time() < limite:
            pid = _processo_java_hod_conectado(porta)
            if pid:
                break
            time.sleep(1)

        if not pid:
            linhas = _linhas_status_hod(host, porta, lu, codigo_limpo, origem, False, False)
            on_update("IBM HOD aberto, aguardando conexão TN3270.", linhas, "hod_webstart_aguardando")
            return {
                "ok": False,
                "mensagem": (
                    f"Host/porta encontrados ({host}:{porta}), mas o Java/HOD ainda não estabeleceu conexão. "
                    "Verifique a janela do IBM HOD/WebStart."
                ),
                "estado": "hod_webstart_aguardando",
                "tela": "\n".join(linhas),
                "host": host,
                "porta": porta,
                "ssl": ssl,
                "lu": lu,
                "origem": origem,
            }

        digitado = False
        detalhe_digitacao = ""
        if codigo_limpo:
            digitado, detalhe_digitacao = _digitar_codigo_no_hod_webstart(pid, codigo_limpo)

        linhas = _linhas_status_hod(host, porta, lu, codigo_limpo, origem, True, digitado)
        mensagem = f"IBM HOD conectado ao SIAFI tela preta em {host}:{porta}."
        if codigo_limpo and digitado:
            mensagem += " Código HOD enviado para a janela Java."
        elif codigo_limpo:
            mensagem += f" Código HOD capturado; digitação automática não confirmada ({detalhe_digitacao})."
        on_update(mensagem, linhas, "hod_webstart_conectado")
        return {
            "ok": True,
            "mensagem": mensagem,
            "estado": "hod_webstart_conectado",
            "tela": "\n".join(linhas),
            "host": host,
            "porta": porta,
            "ssl": ssl,
            "lu": lu,
            "origem": origem,
            "pid": pid,
            "codigo_digitado": digitado,
        }
    except Exception as e:
        logger.exception("Erro ao abrir terminal SIAFI")
        return {
            "ok": False,
            "mensagem": str(e),
            "estado": "excecao",
            "tela": "",
        }


def enviar_comando_atulc_hod_webstart(
    codigo_acesso: str = "",
    jnlp_path: Optional[str] = None,
    host: Optional[str] = None,
    porta: Optional[int] = None,
    on_update: EventCallback = _noop_callback,
) -> dict:
    """Envia o comando >atulc para a janela Java/HOD ja aberta."""
    comando = ">atulc"
    try:
        _caminho_jnlp, _cfg_hod, host, porta, ssl, lu = _resolver_contexto_hod_webstart(
            jnlp_path=jnlp_path,
            host=host,
            porta=porta,
        )
        codigo_limpo = re.sub(r"\D", "", codigo_acesso or "")

        linhas = _linhas_status_hod_comando(host, porta, lu, comando, False, False)
        on_update(f"Localizando IBM HOD WebStart ({host}:{porta})...", linhas, "hod_webstart_aguardando")

        pid = _processo_java_hod_conectado(porta)
        if not pid:
            return {
                "ok": False,
                "mensagem": (
                    "SIAFI tela preta nao foi localizado conectado ao HOD. "
                    "Clique primeiro em Abrir SIAFI tela preta, aguarde o codigo ser digitado e tente Gerar LC novamente."
                ),
                "estado": "hod_webstart_aguardando",
                "tela": "\n".join(linhas),
                "host": host,
                "porta": porta,
                "ssl": ssl,
                "lu": lu,
            }

        linhas = _linhas_status_hod_comando(host, porta, lu, comando, True, False)
        if codigo_limpo:
            linhas.append(f"Codigo HOD ja capturado neste fluxo: {codigo_limpo}")
        on_update("Digitando >atulc no SIAFI tela preta...", linhas, "menu")

        enviado, detalhe = _digitar_texto_no_hod_webstart(pid, comando, enter=True)
        linhas = _linhas_status_hod_comando(host, porta, lu, comando, True, enviado)
        if codigo_limpo:
            linhas.append(f"Codigo HOD ja capturado neste fluxo: {codigo_limpo}")

        if not enviado:
            return {
                "ok": False,
                "mensagem": f"Nao consegui digitar >atulc no HOD Java: {detalhe}",
                "estado": "erro",
                "tela": "\n".join(linhas),
                "host": host,
                "porta": porta,
                "ssl": ssl,
                "lu": lu,
                "pid": pid,
            }

        mensagem = "Comando >atulc enviado ao SIAFI tela preta."
        on_update(mensagem, linhas, "atulc_comando_enviado")
        return {
            "ok": True,
            "mensagem": mensagem,
            "estado": "atulc_comando_enviado",
            "tela": "\n".join(linhas),
            "host": host,
            "porta": porta,
            "ssl": ssl,
            "lu": lu,
            "pid": pid,
        }
    except Exception as e:
        logger.exception("Erro ao enviar comando ATULC no HOD WebStart")
        return {
            "ok": False,
            "mensagem": str(e),
            "estado": "excecao",
            "tela": "",
        }


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
    ssl = False
    if not (host and porta):
        caminho_jnlp = Path(jnlp_path) if jnlp_path else _encontrar_jnlp()
        if caminho_jnlp:
            h, p, ssl_cfg = _parsear_host_porta(caminho_jnlp)
            host  = host  or h
            porta = porta or p
            ssl = ssl_cfg
        else:
            logger.warning(
                ".jnlp não encontrado em ~/Downloads. "
                "Abra o SIAFI no navegador para baixar o .jnlp primeiro."
            )
            host  = host  or "siafi.serpro.gov.br"
            porta = porta or 9623

    destino = _formatar_destino_3270(host, int(porta), ssl)
    logger.info(f"Conectando ao SIAFI em {destino}...")
    on_update(f"Conectando ao SIAFI ({destino})...", [], "conectando")
    _validar_destino_3270(host, int(porta))

    try:
        m = _criar_emulador_3270(Emulator)
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
