"""
interface_workers.py
Threads de automação, log em tempo real e widgets auxiliares (Badge, PainelLog, ZonaDeDrop).
"""

import html as _html
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from interface_estilos import _SVG_UPLOAD, STATUS_STYLE

# ─────────────────────────────────────────────────────────────────────────────
# LOG EM TEMPO REAL
# ─────────────────────────────────────────────────────────────────────────────
class LogEmitter(QObject):
    nova_linha = pyqtSignal(str)

_log_emitter = LogEmitter()


class LogRedirector:
    def __init__(self):
        self._buf = ""

    def write(self, text):
        self._buf += text
        while "\n" in self._buf:
            linha, self._buf = self._buf.split("\n", 1)
            if linha.strip():
                _log_emitter.nova_linha.emit(linha.strip())

    def flush(self):
        if self._buf.strip():
            _log_emitter.nova_linha.emit(self._buf.strip())
            self._buf = ""

# ─────────────────────────────────────────────────────────────────────────────
# BADGE DE STATUS
# ─────────────────────────────────────────────────────────────────────────────
class BadgeStatus(QLabel):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(72)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._status = "aguardando"
        self.set("aguardando")

    def set(self, status):
        self._status = status
        texto, cor, _ = STATUS_STYLE.get(status, STATUS_STYLE["aguardando"])
        self.setText(texto)
        self.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {cor}; background: transparent;"
        )

    def status(self):
        return self._status

# ─────────────────────────────────────────────────────────────────────────────
# WORKERS
# ─────────────────────────────────────────────────────────────────────────────
class AutomacaoWorker(QThread):
    finalizado = pyqtSignal(dict)

    def __init__(self, func):
        super().__init__()
        self.func = func

    def run(self):
        old_stdout = sys.stdout
        sys.stdout = LogRedirector()
        try:
            res = self.func()
            if res is None:
                res = {"status": "sucesso", "mensagem": "Etapa concluída."}
            elif not isinstance(res, dict) or "status" not in res:
                res = {"status": "alerta", "mensagem": f"Retorno inesperado: {res}"}
        except Exception as e:
            res = {"status": "erro", "mensagem": str(e)}
        finally:
            sys.stdout = old_stdout
        self.finalizado.emit(res)


class ExtracaoWorker(QThread):
    concluido = pyqtSignal(dict, str)
    erro = pyqtSignal(str)

    def __init__(self, caminho_pdf, vencimento):
        super().__init__()
        self.caminho_pdf = caminho_pdf
        self.vencimento = vencimento

    def run(self):
        try:
            from extrator import extrair_dados_pdf

            dados = extrair_dados_pdf(
                self.caminho_pdf,
                nome_arquivo=Path(self.caminho_pdf).name,
            )
            if not dados:
                self.erro.emit("Não foi possível extrair dados do PDF.\nVerifique se o arquivo está correto.")
                return
            status_simples = "pulado"
            cnpj = dados.get("CNPJ", "")
            if cnpj and cnpj != "Não encontrado":
                try:
                    import consulta_cnpj
                    resultado = consulta_cnpj.verificar_simples_nacional(cnpj)
                    if resultado is True:    status_simples = "sim"
                    elif resultado is False: status_simples = "nao"
                    else:                   status_simples = "erro"
                except Exception:
                    logging.error("Erro na consulta CNPJ:\n" + traceback.format_exc())
                    status_simples = "erro"
            self.concluido.emit(dados, status_simples)
        except Exception as e:
            logging.error("Erro na extração do PDF:\n" + traceback.format_exc())
            self.erro.emit(f"Erro ao processar o PDF:\n{e}\n\nDetalhes salvos em erros.log")

# ─────────────────────────────────────────────────────────────────────────────
# PAINEL DE LOG
# ─────────────────────────────────────────────────────────────────────────────
class PainelLog(QFrame):
    _COR = {
        "ok": "#059669", "warn": "#d97706", "err": "#dc2626",
        "sec": "#4f46e5", "info": "#6b7280",
    }

    def __init__(self):
        super().__init__()
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        hdr = QFrame()
        hdr.setObjectName("logHeader")
        hdr.setFixedHeight(32)
        hdr_hl = QHBoxLayout(hdr)
        hdr_hl.setContentsMargins(12, 0, 10, 0)

        lbl = QLabel("Log de Execução")
        lbl.setStyleSheet(
            "font-weight: 600; font-size: 11px; letter-spacing: 0.05em; color: inherit; background: transparent;"
        )

        self._btn_limpar = QPushButton("limpar")
        self._btn_limpar.setFixedSize(48, 20)
        self._btn_limpar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_limpar.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; font-size: 10px;"
            "  border: 1px solid #d1d5db; border-radius: 4px; }"
            "QPushButton:hover { color: #dc2626; border-color: #dc2626; }"
        )
        self._btn_limpar.clicked.connect(self.limpar)
        hdr_hl.addWidget(lbl)
        hdr_hl.addStretch()
        hdr_hl.addWidget(self._btn_limpar)
        vl.addWidget(hdr)

        self._te = QTextEdit()
        self._te.setObjectName("logText")
        self._te.setReadOnly(True)
        self._te.setFont(QFont("Menlo, Monaco, Consolas", 11))
        self._te.setMinimumHeight(100)
        vl.addWidget(self._te)
        _log_emitter.nova_linha.connect(self._adicionar)

    def _tipo(self, linha):
        l = linha.lower()
        if any(x in l for x in ["confere", "verificad", "confirmad", "concluíd", "pronto", "sucesso", "salvo", "preenchid"]):
            return "ok"
        if any(x in l for x in ["divergente", "aviso", "alerta", "não encontrad", "não foi possível"]):
            return "warn"
        if any(x in l for x in ["erro", "error", "exception", "traceback", "failed"]):
            return "err"
        if any(x in l for x in ["===", "──", "iniciando", "abrindo", "clicando"]):
            return "sec"
        return "info"

    def _adicionar(self, linha):
        tipo = self._tipo(linha)
        cor  = self._COR[tipo]
        hora = datetime.now().strftime("%H:%M:%S")
        icone = {"ok": "✓", "warn": "!", "err": "x", "sec": ">", "info": "·"}[tipo]
        h = _html.escape(linha)
        self._te.insertHtml(
            f'<span style="color:#64748b">[{hora}]</span>&nbsp;'
            f'<span style="color:{cor}">{icone}&nbsp;{h}</span><br>'
        )
        sb = self._te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def secao(self, texto):
        self._te.insertHtml(
            f'<br><span style="color:#4f46e5; font-weight:bold">'
            f'── {_html.escape(texto)} ──</span><br>'
        )
        sb = self._te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def limpar(self):
        self._te.clear()

# ─────────────────────────────────────────────────────────────────────────────
# ZONA DE DROP
# ─────────────────────────────────────────────────────────────────────────────
class ZonaDeDrop(QFrame):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setAcceptDrops(True)
        self.setProperty("class", "DropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icone_lbl = QLabel()
        self._icone_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icone_lbl.setFixedSize(52, 52)
        self._icone_lbl.setProperty("class", "DropLabel")
        self._atualizar_icone("#9ca3af")
        layout.addWidget(self._icone_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel("Arraste o PDF da Liquidação aqui\nou clique para selecionar")
        self.label.setProperty("class", "DropLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 13px; line-height: 1.6;")
        layout.addWidget(self.label)

        lbl_ext = QLabel("Formato aceito: .pdf")
        lbl_ext.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ext.setStyleSheet("font-size: 11px; color: #9ca3af; background: transparent;")
        layout.addWidget(lbl_ext)

        self.setLayout(layout)

    def _atualizar_icone(self, cor: str):
        try:
            from PyQt6.QtSvg import QSvgRenderer
            svg = _SVG_UPLOAD.replace("{c}", cor).encode("utf-8")
            renderer = QSvgRenderer(svg)
            pix = QPixmap(48, 48)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(p)
            p.end()
            self._icone_lbl.setPixmap(pix)
        except ImportError:
            self._icone_lbl.setText("[PDF]")

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.accept()
            self._atualizar_icone("#4f46e5")
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._atualizar_icone("#9ca3af")

    def dropEvent(self, e):
        self._atualizar_icone("#9ca3af")
        for url in e.mimeData().urls():
            cam = url.toLocalFile()
            if cam.lower().endswith(".pdf"):
                self.main_app.iniciar_extracao(cam)
                return
        QMessageBox.warning(self, "Erro", "Solte um arquivo PDF válido.")

    def mousePressEvent(self, e):
        cam, _ = QFileDialog.getOpenFileName(self, "Selecione o PDF", "", "PDF (*.pdf)")
        if cam:
            self.main_app.iniciar_extracao(cam)
