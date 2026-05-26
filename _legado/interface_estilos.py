"""
interface_estilos.py
Constantes, paletas, QSS, SVGs, utilitários e tabelas de dados da aplicação.
"""

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

from core.theme_tokens import LISTA_TEMAS, STATUS_STYLE, STEP_COLORS as _STEP_COLORS, TC
from services.config_service import carregar_tabelas_config as _carregar_tabelas_config
from services.config_service import salvar_tabelas_config as _salvar_tabelas_config

_NATUREZA_PADRAO = {
    "449052.04": "1.2.3.1.1.01.01", "449052.06": "1.2.3.1.1.01.02",
    "449052.08": "1.2.3.1.1.01.03", "449052.10": "1.2.3.1.1.01.04",
    "449052.12": "1.2.3.1.1.03.01", "449052.18": "1.2.3.1.1.04.02",
    "449052.20": "1.2.3.1.1.05.06", "449052.24": "1.2.3.1.1.01.05",
    "449052.28": "1.2.3.1.1.01.06", "449052.30": "1.2.3.1.1.01.07",
    "449052.32": "1.2.3.1.1.01.08", "449052.33": "1.2.3.1.1.04.05",
    "449052.34": "1.2.3.1.1.01.25", "449052.35": "1.2.3.1.1.02.01",
    "449052.36": "1.2.3.1.1.03.02", "449052.38": "1.2.3.1.1.01.09",
    "449052.39": "1.2.3.1.1.01.21", "449052.40": "1.2.3.1.1.01.20",
    "449052.41": "1.2.3.1.1.02.01", "449052.42": "1.2.3.1.1.03.03",
    "449052.44": "1.2.3.1.1.04.06", "449052.46": "1.2.3.1.1.01.10",
    "449052.48": "1.2.3.1.1.05.01", "449052.49": "1.2.3.1.1.01.11",
    "449052.51": "1.2.3.1.1.99.09", "449052.52": "1.2.3.1.1.05.03",
    "449052.54": "1.2.3.1.1.01.14", "449052.57": "1.2.3.1.1.01.12",
    "449052.60": "1.2.3.1.1.01.13", "449052.96": "1.2.3.1.1.07.03",
}
_tc = _carregar_tabelas_config()
NATUREZA_BENS_MOVEIS = _tc.get("natureza_bens_moveis", dict(_NATUREZA_PADRAO))

_NAT_RENDIMENTO_PADRAO = [
    ("17001", "Alimentação", "6147"),
    ("17002", "Energia elétrica", "6147"),
    ("17003", "Serviços prestados com emprego de materiais", "6147"),
    ("17004", "Construção Civil por empreitada com emprego de materiais", "6147"),
    ("17005", "Serviços hospitalares de que trata o art. 30 da Instrução Normativa RFB nº 1.234, de 2012", "6147"),
    ("17006", "Transporte de cargas", "6147"),
    ("17007", "Serviços de auxílio diagnóstico e terapia", "6147"),
    ("17008", "Produtos farmacêuticos, perfumaria, toucador ou higiene pessoal", "6147"),
    ("17009", "Mercadorias e bens em geral", "6147"),
    ("17010", "Gasolina, óleo diesel, gás liquefeito de petróleo (GLP)", "9060"),
    ("17011", "Álcool etílico hidratado, inclusive para fins carburantes", "9060"),
    ("17012", "Biodiesel adquirido de produtor ou importador", "9060"),
    ("17013", "Gasolina, exceto gasolina de aviação, óleo diesel e gás liquefeito de petróleo", "8739"),
    ("17014", "Álcool etílico hidratado nacional para fins carburantes (varejista)", "8739"),
    ("17015", "Biodiesel adquirido de distribuidores e comerciantes varejistas", "8739"),
    ("17016", "Biodiesel produtor detentor selo 'Combustível Social'", "8739"),
    ("17017", "Transporte internacional de cargas efetuado por empresas nacionais", "8767"),
    ("17018", "Estaleiros navais brasileiros", "8767"),
    ("17019", "Produtos de perfumaria, toucador e higiene pessoal (art. 1º IN RFB 1.234/2012)", "8767"),
    ("17020", "Produtos a que se refere o § 2º do art. 22 da IN RFB 1.234/2012", "8767"),
    ("17021", "Produtos de que tratam as alíneas 'c' a 'k' do art. 5º da IN RFB 1.234/2012", "8767"),
    ("17022", "Outros prod./serv. com isenção, não incidência ou alíquotas zero (PIS/Pasep/Cofins)", "8767"),
    ("17023", "Passagens aéreas, rodov. e demais serv. de transporte de passageiros", "6175"),
    ("17024", "Transporte internacional de passageiros efetuado por empresas nacionais", "8850"),
    ("17025", "Serviços prestados por associações profissionais ou assemelhadas e cooperativas", "8863"),
    ("17026", "Serviços prestados por bancos comerciais, bancos de investimento", "6188"),
    ("17027", "Seguro Saúde", "6188"),
    ("17028", "Serviços de abastecimento de água", "6190"),
    ("17029", "Telefone", "6190"),
    ("17030", "Correio e telégrafos", "6190"),
    ("17031", "Vigilância", "6190"),
    ("17032", "Limpeza", "6190"),
    ("17033", "Locação de mão de obra", "6190"),
    ("17034", "Intermediação de negócios", "6190"),
    ("17035", "Administração, locação ou cessão de bens imóveis, móveis e direitos de qualquer natureza", "6190"),
    ("17036", "Factoring", "6190"),
    ("17037", "Plano de saúde humano, veterinário ou odontológico", "6190"),
    ("17038", "Pagamento efetuado à sociedade cooperativa pelo fornecimento de bens (art. 24 IN 1234/12)", "8863"),
    ("17040", "Serviços prestados por associações profissionais (emprego de materiais)", "6147"),
    ("17041", "Serviços prestados por associações profissionais (demais serviços)", "6190"),
    ("17042", "Pagamentos efetuados às associações e cooperativas médicas/odontológicas", "6190"),
    ("17043", "Pagamento à sociedade cooperativa de produção (art. 25 IN 1234/12)", "6147"),
    ("17046", "Pagamento efetuado na aquisição de bem imóvel (art. 23 inc I IN RFB 1234/2012)", "6147"),
    ("17047", "Pagamento efetuado na aquisição de bem imóvel (art. 23 inc II IN RFB 1234/2012)", "8767"),
    ("17049", "Propaganda e Publicidade, em desconformidade com o art 16 da IN RFB 1234/2012", "6190"),
    ("17050", "Propaganda e Publicidade, em conformidade com o art 16 da IN RFB 1234/2012", "8863"),
    ("17099", "Demais serviços", "6190"),
]

_FONTES_RECURSO_PADRAO = [
    ("1050000394", ""), ("1051000394", ""), ("0150153163", ""),
    ("0150262460", ""), ("0250153163", ""), ("0250262460", ""),
    ("0263262460", ""), ("0280153163", ""), ("8150262460", ""),
    ("8250262740", ""), ("8280153163", ""), ("8650262460", ""),
    ("8180153163", ""),
]

_SHEETS_URL_PADRAO = "https://docs.google.com/spreadsheets/d/1O2Ft4Ioy3_t4bKmPQ38d56UhHY2TBHfPI6kTkNkmy-4/edit"

_VPD_PADRAO = [["339030.01", "DSP 001", "3.3.2.3.X.04.00"]]

_SVG_DOCUMENTO = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="1.5" width="10" height="14" rx="1.5" fill="none" stroke="{c}" stroke-width="1.5"/></svg>'
_SVG_GRAFICO = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="10" width="3.5" height="5.5" rx="0.5" fill="{c}"/></svg>'
_SVG_DEDUCAO = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7" fill="none" stroke="{c}" stroke-width="1.5"/></svg>'
_SVG_PAGAMENTO = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="4" width="15" height="10" rx="1.5" fill="none" stroke="{c}" stroke-width="1.5"/></svg>'
_SVG_LOCALIZACAO = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="7.2" r="2.2" fill="{c}"/></svg>'
_SVG_PLAY = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.5" fill="{c}"/></svg>'
_SVG_CHECK_CIRCLE = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.5" fill="{c}"/></svg>'
_SVG_ENGRENAGEM = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="2.8" fill="none" stroke="{c}" stroke-width="1.5"/></svg>'
_SVG_CHROME = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><circle cx="9" cy="9" r="7.5" fill="none" stroke="{c}" stroke-width="1.5"/></svg>'
_SVG_VOLTAR = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><path d="M10 4L5 9L10 14" fill="none" stroke="{c}" stroke-width="1.8"/></svg>'
_SVG_PDF = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="1" width="14" height="16" rx="1.5" fill="none" stroke="{c}" stroke-width="1.4"/></svg>'
_SVG_UPLOAD = '<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg"><rect x="8" y="32" width="32" height="8" rx="2" fill="none" stroke="{c}" stroke-width="2.5"/></svg>'
_SVG_CALENDARIO = '<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><rect x="1.5" y="2.5" width="13" height="12" rx="1.5" fill="none" stroke="{c}" stroke-width="1.4"/></svg>'
_SVG_FILA = '<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><path d="M2 4h14M2 9h14M2 14h10" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/></svg>'


def _svg_para_icone(svg_template: str, cor: str, tamanho: int = 18) -> QIcon:
    svg = svg_template.replace("{c}", cor)
    try:
        from PyQt6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(svg.encode("utf-8"))
        pix = QPixmap(tamanho, tamanho)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        return QIcon(pix)
    except ImportError:
        pix = QPixmap(tamanho, tamanho)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(cor), 1.5))
        painter.setBrush(QBrush(QColor(cor)))
        margem = tamanho // 4
        painter.drawEllipse(margem, margem, tamanho - 2 * margem, tamanho - 2 * margem)
        painter.end()
        return QIcon(pix)


def _primeiros_dias_uteis(ano: int, mes: int, n: int = 3) -> list:
    dias = []
    data = datetime(ano, mes, 1)
    while len(dias) < n:
        if data.weekday() < 5:
            dias.append(data.day)
        data += timedelta(days=1)
        if data.month != mes:
            break
    return dias


def _parse_valor_float(s: str) -> float:
    import re as _re
    if not s:
        return 0.0
    bruto = str(s).strip()
    negativo = "-" in bruto
    s = _re.sub(r"[^\d,.]", "", bruto)
    if not s:
        return 0.0
    virgulas = s.count(",")
    pontos = s.count(".")
    if virgulas >= 1 and pontos >= 1:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif virgulas >= 1 and pontos == 0:
        partes = s.split(",")
        if len(partes) > 2:
            s = "".join(partes)
        elif len(partes) == 2 and len(partes[1]) > 2:
            s = f"{partes[0]}{partes[1][:-2]}.{partes[1][-2:]}"
        else:
            s = s.replace(",", ".")
    elif pontos > 1:
        partes = s.split(".")
        if len(partes[-1]) == 2:
            s = f"{''.join(partes[:-1])}.{partes[-1]}"
        else:
            s = "".join(partes)
    elif pontos == 1:
        partes = s.split(".")
        if len(partes[1]) > 2:
            s = f"{partes[0]}{partes[1][:-2]}.{partes[1][-2:]}"
    try:
        valor = float(s)
        return -valor if negativo else valor
    except ValueError:
        return 0.0


def _gerar_qss(tema: str) -> str:
    c = TC[tema]
    return f"""
QWidget {{
    background-color: {c['bg']};
    font-family: \"Segoe UI\", Roboto, Arial, sans-serif;
    font-size: 13px;
    color: {c['text']};
}}
QFrame {{ background-color: transparent; }}
QLabel {{ background: transparent; }}
.Card {{ background-color: {c['card']}; border-radius: 10px; border: 1px solid {c['border']}; }}
QLineEdit {{ padding: 9px 12px; border: 1.5px solid {c['border']}; border-radius: 7px; background-color: {c['bg']}; color: {c['text']}; font-size: 13px; }}
QLineEdit:focus {{ border: 1.5px solid {c['accent']}; background-color: {c['card']}; }}
QRadioButton {{ spacing: 8px; font-size: 13px; color: {c['text']}; }}
QRadioButton::indicator {{ width: 15px; height: 15px; }}
QTableWidget, QTreeWidget {{ background-color: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; alternate-background-color: {c['card_alt']}; }}
QHeaderView::section {{ background-color: {c['surface']}; color: {c['muted']}; padding: 7px 8px; border: none; border-bottom: 1.5px solid {c['border']}; font-weight: 600; font-size: 11px; }}
QGroupBox {{ color: {c['muted']}; font-weight: 600; font-size: 11px; border: 1px solid {c['border']}; border-radius: 8px; margin-top: 8px; background-color: {c['card']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 0px 6px 6px 6px; background: {c['card']}; }}
QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 8px 18px; margin-right: 2px; font-size: 12px; font-weight: 500; border-bottom: 2px solid transparent; min-width: 100px; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; font-weight: 600; }}
QScrollBar:vertical {{ background: {c['card']}; width: 6px; border-radius: 3px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollArea {{ border: none; background: transparent; }}
.DropZone {{ background-color: {c['card']}; border: 1.5px dashed {c['border']}; border-radius: 12px; }}
.DropZone:hover {{ background-color: {c['card_alt']}; border-color: {c['accent']}; }}
.DropLabel {{ color: {c['muted']}; font-size: 13px; border: none; background: transparent; }}
QFrame#topStrip, QFrame#topBar {{ background: {c['card']}; border-bottom: 1px solid {c['border']}; }}
QFrame#queueItem {{ background: {c['card']}; border-radius: 8px; border: 1px solid {c['border_dim']}; }}
QFrame#queueItem:hover {{ border-color: {c['border']}; background: {c['card_alt']}; }}
QFrame#resumoCard {{ background: {c['surface']}; border-radius: 8px; border: 1px solid {c['border']}; }}
QFrame#logHeader {{ background: {c['surface']}; border-radius: 6px 6px 0 0; border-bottom: 1px solid {c['border']}; }}
QTextEdit#logText {{ background: {c['log_bg']}; color: {c['log_fg']}; border: none; border-radius: 0 0 6px 6px; padding: 6px 8px; }}
QFrame#dataPill {{ background: {c['accent']}12; border: 1px solid {c['accent']}40; border-radius: 5px; }}
QFrame#dataPillWarn {{ background: #d9770618; border: 1px solid #d9770650; border-radius: 5px; }}
"""


MAPA_ESTILOS = {tema: _gerar_qss(tema) for tema in LISTA_TEMAS}
