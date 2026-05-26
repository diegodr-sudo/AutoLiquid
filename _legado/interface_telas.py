"""
interface_telas.py
TelaUpload, BarraProgressoCustom e TelaResultados.
"""

import logging

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from interface_estilos import (
    TC, _STEP_COLORS, _parse_valor_float,
    _svg_para_icone, NATUREZA_BENS_MOVEIS,
    _SVG_VOLTAR, _SVG_FILA, _SVG_PLAY, _SVG_CHECK_CIRCLE,
    _SVG_CALENDARIO,
    _SVG_DOCUMENTO, _SVG_GRAFICO, _SVG_DEDUCAO, _SVG_PAGAMENTO, _SVG_LOCALIZACAO,
)
from interface_workers import (
    ZonaDeDrop, PainelLog, AutomacaoWorker, BadgeStatus,
)
from interface_dialogos import DialogoLF
from core.runtime_config import obter_datas_salvas, salvar_datas_processo

# ─────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE AVISO DE PAGAMENTO PRÓXIMO
# ─────────────────────────────────────────────────────────────────────────────
_URL_CHAT_UFSC = "https://chat.ufsc.br"


class _DialogoAvisoPagamento(QDialog):
    """
    Exibe aviso quando INSS ou ISS vencem em ≤ 7 dias úteis após a apropriação.
    Oferece botão para abrir o chat UFSC e copia a mensagem automaticamente.
    """

    def __init__(self, avisos: list, num_processo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚠ Atenção — Imposto vencendo em breve")
        self.setMinimumWidth(520)
        self.setModal(True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(24, 22, 24, 22)
        vl.setSpacing(14)

        # Título
        tit = QLabel("Imposto com vencimento próximo!")
        tit.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: #b45309;"
        )
        vl.addWidget(tit)

        desc = QLabel(
            "Os seguintes impostos vencem em até <b>7 dias úteis</b>. "
            "É recomendado avisar a equipe pelo chat da UFSC."
        )
        desc.setTextFormat(Qt.TextFormat.RichText)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #374151;")
        vl.addWidget(desc)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #fde68a; border: none;")
        vl.addWidget(sep)

        # Uma linha por aviso + botão de cópia
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QClipboard

        self._mensagens = []
        for av in avisos:
            tipo = av["tipo"]
            venc = av["vencimento"]
            dias = av["dias"]
            processo_label = num_processo if num_processo else "[processo]"
            mensagem = (
                f"Processo {processo_label} vencendo {tipo} dia {venc}"
            )
            self._mensagens.append(mensagem)

            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #fffbeb; border: 1.5px solid #fcd34d;"
                "  border-radius: 8px; }"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 10, 14, 10)
            cl.setSpacing(6)

            alerta_lbl = QLabel(
                f"<b>{tipo}</b> — vencimento: <b>{venc}</b> "
                f"({dias} dia{'s' if dias != 1 else ''} útil{'s' if dias != 1 else ''})"
            )
            alerta_lbl.setTextFormat(Qt.TextFormat.RichText)
            alerta_lbl.setStyleSheet("font-size: 13px; color: #92400e;")
            cl.addWidget(alerta_lbl)

            msg_lbl = QLabel(f"💬 <i>{mensagem}</i>")
            msg_lbl.setTextFormat(Qt.TextFormat.RichText)
            msg_lbl.setStyleSheet("font-size: 12px; color: #374151;")
            cl.addWidget(msg_lbl)

            vl.addWidget(card)

        # Botões de ação
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #e5e7eb; border: none;")
        vl.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_chat = QPushButton("  Abrir Chat UFSC  ↗")
        btn_chat.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_chat.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; font-weight: 700;"
            "  font-size: 13px; border-radius: 8px; border: none; padding: 8px 20px; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        btn_chat.clicked.connect(self._abrir_chat)
        btn_row.addWidget(btn_chat)

        btn_copiar = QPushButton("  Copiar mensagem")
        btn_copiar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copiar.setStyleSheet(
            "QPushButton { background: #e5e7eb; color: #1f2937; font-size: 12px;"
            "  border-radius: 8px; border: none; padding: 8px 16px; }"
            "QPushButton:hover { background: #d1d5db; }"
        )
        btn_copiar.clicked.connect(self._copiar_mensagem)
        btn_row.addWidget(btn_copiar)

        btn_row.addStretch()

        btn_fechar = QPushButton("Fechar")
        btn_fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_fechar.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 8px 16px; border-radius: 8px;"
            "  background: #f3f4f6; border: 1px solid #d1d5db; color: #374151; }"
            "QPushButton:hover { background: #e5e7eb; }"
        )
        btn_fechar.clicked.connect(self.accept)
        btn_row.addWidget(btn_fechar)

        vl.addLayout(btn_row)

        # Copia automaticamente para o clipboard ao abrir
        self._copiar_mensagem(silencioso=True)

    def _texto_mensagem_completo(self) -> str:
        return "\n".join(self._mensagens)

    def _copiar_mensagem(self, silencioso: bool = False):
        from PyQt6.QtWidgets import QApplication
        texto = self._texto_mensagem_completo()
        QApplication.clipboard().setText(texto)
        if not silencioso:
            from PyQt6.QtWidgets import QToolTip
            QToolTip.showText(
                self.mapToGlobal(self.rect().center()),
                "Mensagem copiada!",
                self,
            )

    def _abrir_chat(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        # Garante que a mensagem está no clipboard antes de abrir
        self._copiar_mensagem(silencioso=True)
        QDesktopServices.openUrl(QUrl(_URL_CHAT_UFSC))


# ─────────────────────────────────────────────────────────────────────────────
# TELA UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
class TelaUpload(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        cfg = self._carregar()
        self._construir(cfg)

    def _carregar(self):
        return obter_datas_salvas()

    def salvar_e_obter(self):
        dados = salvar_datas_processo(
            self.campo_apuracao.text(),
            self.campo_vencimento.text(),
        )
        return dados["apuracao"], dados["vencimento"]

    def _auto_ajustar_data(self, field: QLineEdit, label: str):
        """
        Ao sair do campo de data, verifica se a data informada é dia útil.
        Se não for (feriado Fpolis ou fim de semana), ajusta para o dia útil
        imediatamente anterior e exibe tooltip informando o ajuste.
        """
        texto = field.text().strip()
        if len(texto) != 10:   # espera DD/MM/AAAA completo
            return
        try:
            from datas_impostos import ajustar_data_util
        except ImportError:
            return
        nova, foi = ajustar_data_util(texto)
        if foi:
            field.setText(nova)
            field.setStyleSheet(
                "QLineEdit { border: 1.5px solid #f59e0b; background: #fffbeb; font-size: 14px;"
                "  font-weight: 600; color: #92400e; border-radius: 7px; padding: 9px 12px; }"
                "QLineEdit:focus { border-color: #d97706; }"
            )
            from PyQt6.QtWidgets import QToolTip
            QToolTip.showText(
                field.mapToGlobal(field.rect().bottomLeft()),
                f"⚠ {label} ajustada: {texto} era feriado/fim de semana → {nova}",
                field,
            )
        else:
            field.setStyleSheet(
                "QLineEdit { border: 1.5px solid #c7d2fe; background: white; font-size: 14px;"
                "  font-weight: 600; color: #1e1b4b; border-radius: 7px; padding: 9px 12px; }"
                "QLineEdit:focus { border-color: #4f46e5; }"
            )

    def _construir(self, cfg):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QVBoxLayout()
        content.setContentsMargins(0, 48, 0, 48)
        content.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        lbl_titulo = QLabel("Automação de Liquidação")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setStyleSheet(
            "font-size: 26px; font-weight: 800; background: transparent; margin-bottom: 2px;"
            "letter-spacing: -0.5px;"
        )
        content.addWidget(lbl_titulo)

        lbl_sub = QLabel("Processamento automático de notas fiscais  ·  Comprasnet / SIAFI")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sub.setStyleSheet(
            "font-size: 13px; color: #6b7280; background: transparent; margin-bottom: 36px;"
        )
        content.addWidget(lbl_sub)

        card = QFrame()
        card.setProperty("class", "Card")
        card.setFixedWidth(560)
        card_vl = QVBoxLayout(card)
        card_vl.setContentsMargins(32, 28, 32, 28)
        card_vl.setSpacing(22)

        datas_frame = QFrame()
        datas_frame.setObjectName("dataPill")
        datas_vl = QVBoxLayout(datas_frame)
        datas_vl.setContentsMargins(16, 14, 16, 14)
        datas_vl.setSpacing(12)

        lbl_datas_header = QLabel("DATAS DO PROCESSO")
        lbl_datas_header.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #4f46e5;"
            "letter-spacing: 0.1em; background: transparent;"
        )
        datas_vl.addWidget(lbl_datas_header)

        row_datas = QHBoxLayout()
        row_datas.setSpacing(16)

        for label_txt, attr, placeholder, cfg_key in [
            ("Data de Apuração",   "campo_apuracao",   "DD/MM/AAAA", "apuracao"),
            ("Data de Vencimento", "campo_vencimento", "DD/MM/AAAA", "vencimento"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(6)
            lbl = QLabel(label_txt)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #374151; background: transparent;"
            )
            col.addWidget(lbl)
            field = QLineEdit(cfg.get(cfg_key, ""))
            field.setPlaceholderText(placeholder)
            field.setStyleSheet(
                "QLineEdit { border: 1.5px solid #c7d2fe; background: white; font-size: 14px;"
                "  font-weight: 600; color: #1e1b4b; border-radius: 7px; padding: 9px 12px; }"
                "QLineEdit:focus { border-color: #4f46e5; }"
            )
            # Ajuste automático: se data cair em feriado/fim de semana → dia útil anterior
            field.editingFinished.connect(
                lambda f=field, l=label_txt: self._auto_ajustar_data(f, l)
            )
            col.addWidget(field)
            setattr(self, attr, field)
            row_datas.addLayout(col)

        datas_vl.addLayout(row_datas)
        card_vl.addWidget(datas_frame)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #e5e7eb; border: none;")
        card_vl.addWidget(div)

        self.drop = ZonaDeDrop(self.main_app)
        self.drop.setMinimumHeight(130)
        card_vl.addWidget(self.drop)

        card_row = QHBoxLayout()
        card_row.addStretch()
        card_row.addWidget(card)
        card_row.addStretch()
        content.addLayout(card_row)

        fila_row = QHBoxLayout()
        fila_row.setContentsMargins(0, 16, 0, 0)
        fila_row.addStretch()
        self._btn_fila_upload = QPushButton("  Fila de Trabalho")
        self._btn_fila_upload.setIcon(_svg_para_icone(_SVG_FILA, "#6b7280", 14))
        self._btn_fila_upload.setIconSize(QSize(14, 14))
        self._btn_fila_upload.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_fila_upload.setToolTip("Atualizar fila de trabalho via Solar UFSC")
        self._btn_fila_upload.setStyleSheet(
            "QPushButton { font-size: 12px; font-weight: 600; color: #6b7280;"
            "  background: transparent; border: 1px solid #d1d5db;"
            "  border-radius: 16px; padding: 6px 18px; }"
            "QPushButton:hover { background: #f3f4f6; color: #374151; border-color: #9ca3af; }"
        )
        self._btn_fila_upload.clicked.connect(
            lambda: self.main_app._atualizar_fila_trabalho()
        )
        fila_row.addWidget(self._btn_fila_upload)
        fila_row.addStretch()
        content.addLayout(fila_row)

        content.addStretch()
        outer.addLayout(content)


# ─────────────────────────────────────────────────────────────────────────────
# BARRA DE PROGRESSO CUSTOMIZADA
# ─────────────────────────────────────────────────────────────────────────────
class BarraProgressoCustom(QFrame):
    def __init__(self):
        super().__init__()
        self._total = 5
        self._atual = 0
        self.setFixedHeight(36)
        self._construir()

    def _construir(self):
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(4)

        row_txt = QHBoxLayout()
        row_txt.setContentsMargins(0, 0, 0, 0)
        self._lbl_status = QLabel("Aguardando execução")
        self._lbl_status.setStyleSheet(
            "font-size: 11px; color: #6b7280; background: transparent;"
        )
        self._lbl_contagem = QLabel("0 / 0")
        self._lbl_contagem.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #4f46e5; background: transparent;"
        )
        row_txt.addWidget(self._lbl_status)
        row_txt.addStretch()
        row_txt.addWidget(self._lbl_contagem)
        vl.addLayout(row_txt)

        self._barra_container = QFrame()
        self._barra_container.setFixedHeight(8)
        self._barra_container.setStyleSheet(
            "QFrame { background: #e5e7eb; border-radius: 4px; border: none; }"
        )
        barra_layout = QHBoxLayout(self._barra_container)
        barra_layout.setContentsMargins(0, 0, 0, 0)
        barra_layout.setSpacing(0)

        self._barra_fill = QFrame()
        self._barra_fill.setFixedHeight(8)
        self._barra_fill.setFixedWidth(0)
        self._barra_fill.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "  stop:0 #4f46e5, stop:0.5 #7c3aed, stop:1 #6366f1);"
            "  border-radius: 4px; border: none; }"
        )
        barra_layout.addWidget(self._barra_fill)
        barra_layout.addStretch()
        vl.addWidget(self._barra_container)

    def definir_total(self, total: int):
        self._total = max(1, total)
        self._atualizar()

    def definir_progresso(self, atual: int):
        self._atual = max(0, min(atual, self._total))
        self._atualizar()

    def reset(self):
        self._atual = 0
        self._atualizar()

    def _atualizar(self):
        frac = self._atual / self._total if self._total > 0 else 0
        largura_total = self._barra_container.width()
        if largura_total <= 0:
            largura_total = 260
        largura_fill = int(frac * largura_total)
        self._barra_fill.setFixedWidth(max(0, largura_fill))

        if self._atual == 0:
            self._lbl_status.setText("Aguardando execução")
            self._lbl_contagem.setText(f"0 / {self._total}")
        elif self._atual >= self._total:
            self._lbl_status.setText("Concluído")
            self._lbl_contagem.setText(f"{self._total} / {self._total}")
        else:
            self._lbl_status.setText("Em execução...")
            self._lbl_contagem.setText(f"{self._atual} / {self._total}")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._atualizar()


# ─────────────────────────────────────────────────────────────────────────────
# TELA RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────
class TelaResultados(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app  = main_app
        self.dados     = {}
        self.vencimento = ""
        self.apuracao   = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Faixa superior ───────────────────────────────────────────────────
        top = QFrame()
        top.setObjectName("topStrip")
        top.setFixedHeight(46)
        top_hl = QHBoxLayout(top)
        top_hl.setContentsMargins(14, 0, 14, 0)
        top_hl.setSpacing(10)

        self._btn_voltar = QPushButton("  Voltar")
        self._btn_voltar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_voltar.setIcon(_svg_para_icone(_SVG_VOLTAR, "#6b7280", 16))
        self._btn_voltar.setIconSize(QSize(16, 16))
        self._btn_voltar.setStyleSheet(
            "QPushButton { background: transparent; font-weight: 600;"
            "  font-size: 12px; border: none; padding: 0 8px 0 0; color: #6b7280; }"
            "QPushButton:hover { color: #4f46e5; }"
        )
        self._btn_voltar.clicked.connect(self.main_app.voltar_para_upload)
        top_hl.addWidget(self._btn_voltar)

        self._lbl_titulo_top = QLabel("Conferência e Automação")
        self._lbl_titulo_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_titulo_top.setStyleSheet(
            "font-size: 13px; font-weight: 700; background: transparent; letter-spacing: 0.02em;"
        )
        top_hl.addWidget(self._lbl_titulo_top, stretch=1)

        self._pill_apuracao   = self._criar_pill("Apuração", "—", "#4f46e5")
        self._pill_vencimento = self._criar_pill("Vencimento", "—", "#0369a1")
        top_hl.addWidget(self._pill_apuracao)
        top_hl.addWidget(self._pill_vencimento)
        top_hl.addSpacing(4)
        outer.addWidget(top)

        # ── 3 colunas ────────────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(10)

        # ══ ESQUERDA: Sidebar ════════════════════════════════════════════════
        left = QFrame()
        left.setFixedWidth(210)
        left.setProperty("class", "Card")
        left_vl = QVBoxLayout(left)
        left_vl.setContentsMargins(16, 18, 16, 16)
        left_vl.setSpacing(0)

        self._lbl_section_doc = QLabel("DOCUMENTO")
        self._lbl_section_doc.setStyleSheet(
            "font-size: 9px; font-weight: 700; color: #4f46e5;"
            "letter-spacing: 0.14em; margin-bottom: 14px; background: transparent;"
        )
        left_vl.addWidget(self._lbl_section_doc)

        self._info_headers = []
        self._info_values  = []

        def _info_row(rotulo, atributo, cor_especial=None):
            frame = QFrame()
            frame.setStyleSheet("QFrame { background: transparent; }")
            vl2 = QVBoxLayout(frame)
            vl2.setContentsMargins(0, 0, 0, 8)
            vl2.setSpacing(1)
            lbl_r = QLabel(rotulo)
            lbl_r.setStyleSheet(
                "font-size: 9px; font-weight: 500; letter-spacing: 0.05em;"
                "text-transform: uppercase; color: #94a3b8; background: transparent;"
            )
            lbl_v = QLabel("—")
            lbl_v.setWordWrap(True)
            lbl_v.setStyleSheet(
                "font-size: 12px; font-weight: 600; background: transparent; padding: 1px 0;"
            )
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._info_headers.append(lbl_r)
            self._info_values.append((lbl_v, cor_especial))
            vl2.addWidget(lbl_r)
            vl2.addWidget(lbl_v)
            setattr(self, atributo, lbl_v)
            return frame

        left_vl.addWidget(_info_row("CNPJ",           "lbl_cnpj"))
        left_vl.addWidget(_info_row("Processo",        "lbl_proc"))
        left_vl.addWidget(_info_row("Sol. Pagamento",  "lbl_sol"))
        left_vl.addWidget(_info_row("Convênio",        "lbl_conv"))
        left_vl.addWidget(_info_row("Natureza",        "lbl_nat",     "info_nat"))
        left_vl.addWidget(_info_row("Ateste",          "lbl_ateste",  "info_ateste"))
        left_vl.addWidget(_info_row("Contrato",        "lbl_contrato"))
        left_vl.addWidget(_info_row("Cód. PARA (IG)",  "lbl_ig",      "accent"))
        left_vl.addWidget(_info_row("Tipo Liquidação", "lbl_tipo_liq"))

        self._frame_aviso_simples = QFrame()
        self._frame_aviso_simples.setStyleSheet(
            "QFrame { background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 8px; }"
        )
        _avs_vl = QVBoxLayout(self._frame_aviso_simples)
        _avs_vl.setContentsMargins(8, 6, 8, 6)
        _avs_vl.setSpacing(2)
        self._lbl_aviso_simples = QLabel("")
        self._lbl_aviso_simples.setWordWrap(True)
        self._lbl_aviso_simples.setStyleSheet(
            "font-size: 10px; font-weight: 600; color: #5b21b6; background: transparent;"
        )
        _avs_vl.addWidget(self._lbl_aviso_simples)
        self._frame_aviso_simples.setVisible(False)
        left_vl.addWidget(self._frame_aviso_simples)

        _sep = QFrame()
        _sep.setFixedHeight(1)
        _sep.setStyleSheet("background: #e2e8f0; margin: 4px 0;")
        left_vl.addWidget(_sep)

        card_resumo = QFrame()
        card_resumo.setObjectName("resumoCard")
        card_resumo.setStyleSheet(
            "QFrame#resumoCard { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        cr_vl = QVBoxLayout(card_resumo)
        cr_vl.setContentsMargins(10, 8, 10, 8)
        cr_vl.setSpacing(3)

        self._lbl_resumo_titulo = QLabel("RESUMO FINANCEIRO")
        self._lbl_resumo_titulo.setStyleSheet(
            "font-size: 9px; font-weight: 700; color: #4f46e5;"
            "letter-spacing: 0.12em; background: transparent;"
        )
        self.lbl_resumo = QLabel("—")
        self.lbl_resumo.setStyleSheet(
            "font-size: 11px; font-weight: 600; line-height: 1.5; background: transparent;"
        )
        self.lbl_resumo.setWordWrap(True)
        cr_vl.addWidget(self._lbl_resumo_titulo)
        cr_vl.addWidget(self.lbl_resumo)
        left_vl.addWidget(card_resumo)
        left_vl.addStretch()
        body.addWidget(left)

        # ══ CENTRO: Abas de tabelas ══════════════════════════════════════════
        abas_tabelas = QTabWidget()
        abas_tabelas.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        abas_tabelas.setUsesScrollButtons(True)
        abas_tabelas.tabBar().setExpanding(False)
        self._abas_tabelas_widget = abas_tabelas

        self.tab_nf = QTableWidget(0, 5)
        self.tab_nf.setHorizontalHeaderLabels(["Tipo", "Nota", "Emissão", "Ateste", "Valor"])
        self.tab_nf.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tab_nf.setAlternatingRowColors(True)
        self.tab_nf.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        abas_tabelas.addTab(self.tab_nf, "Notas Fiscais")

        self.tab_emp = QTableWidget(0, 4)
        self.tab_emp.setHorizontalHeaderLabels(["Empenho", "Situação", "Recurso", "Fonte"])
        self.tab_emp.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tab_emp.setAlternatingRowColors(True)
        self.tab_emp.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        abas_tabelas.addTab(self.tab_emp, "Empenhos")

        # Deduções — QTreeWidget
        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
        ded_frame = QFrame()
        ded_vl = QVBoxLayout(ded_frame)
        ded_vl.setContentsMargins(0, 0, 0, 0)
        ded_vl.setSpacing(4)

        _DED_HEADERS = ["Situação", "SIAFI", "Recolhedor", "Valor", "Taxa %", "% s/Total"]
        self.tree_ded = QTreeWidget()
        self.tree_ded.setColumnCount(len(_DED_HEADERS))
        self.tree_ded.setHeaderLabels(_DED_HEADERS)
        self.tree_ded.setAlternatingRowColors(True)
        self.tree_ded.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree_ded.setObjectName("tree_ded")
        self.tree_ded.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree_ded.header().setStretchLastSection(True)
        self.tree_ded.setColumnWidth(0, 100)
        self.tree_ded.setColumnWidth(1, 80)
        self.tree_ded.setColumnWidth(2, 170)
        self.tree_ded.setColumnWidth(3, 100)
        self.tree_ded.setColumnWidth(4, 80)
        self.tree_ded.setColumnWidth(5, 100)
        self.tree_ded.itemChanged.connect(self._ao_check_nf_ded)
        ded_vl.addWidget(self.tree_ded)

        self._ded_soma_bar = QFrame()
        self._ded_soma_bar.setStyleSheet(
            "QFrame { background: #ede9fe; border-radius: 5px; padding: 4px 10px; }"
        )
        soma_hl = QHBoxLayout(self._ded_soma_bar)
        soma_hl.setContentsMargins(10, 4, 10, 4)
        soma_hl.setSpacing(16)
        self._lbl_soma_nfs = QLabel("NFs selecionadas: —")
        self._lbl_soma_nfs.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #4f46e5; background: transparent;"
        )
        self._lbl_soma_ded = QLabel("Deduções: —")
        self._lbl_soma_ded.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #6d28d9; background: transparent;"
        )
        soma_hl.addWidget(self._lbl_soma_nfs)
        soma_hl.addWidget(self._lbl_soma_ded)
        soma_hl.addStretch()

        btn_sel_todos = QPushButton("Selecionar Todos")
        btn_sel_todos.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: 600; padding: 2px 10px;"
            "  background: #4f46e5; color: white; border-radius: 4px; border: none; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        btn_sel_todos.setFixedHeight(22)
        btn_sel_todos.clicked.connect(self._selecionar_todos_ded)
        soma_hl.addWidget(btn_sel_todos)

        btn_desel_todos = QPushButton("Desmarcar Todos")
        btn_desel_todos.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: 600; padding: 2px 10px;"
            "  background: #e5e7eb; color: #374151; border-radius: 4px; border: none; }"
            "QPushButton:hover { background: #d1d5db; }"
        )
        btn_desel_todos.setFixedHeight(22)
        btn_desel_todos.clicked.connect(self._desmarcar_todos_ded)
        soma_hl.addWidget(btn_desel_todos)
        ded_vl.addWidget(self._ded_soma_bar)
        abas_tabelas.addTab(ded_frame, "Deduções")

        body.addWidget(abas_tabelas, stretch=1)

        # ══ DIREITA: Fila + log ══════════════════════════════════════════════
        right = QFrame()
        right.setFixedWidth(310)
        right.setProperty("class", "Card")
        right_vl = QVBoxLayout(right)
        right_vl.setContentsMargins(14, 16, 14, 14)
        right_vl.setSpacing(6)

        self._lbl_fila = QLabel("FILA DE EXECUÇÃO")
        self._lbl_fila.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #4f46e5;"
            "letter-spacing: 0.12em; margin-bottom: 4px; background: transparent;"
        )
        right_vl.addWidget(self._lbl_fila)

        self._abas = [
            ("Dados Básicos",        _SVG_DOCUMENTO,   self._exec_dados_basicos),
            ("Princ. Com Orçamento", _SVG_GRAFICO,     self._exec_principal_orcamento),
            ("Dedução",              _SVG_DEDUCAO,     self._exec_deducao),
            ("Dados de Pagamento",   _SVG_PAGAMENTO,   self._exec_dados_pagamento),
            ("Centro de Custo",      _SVG_LOCALIZACAO, self._exec_centro_custo),
        ]
        self._badges      = {}
        self._botoes      = {}
        self._num_labels  = {}
        self._item_frames = {}

        for idx, (nome, svg_tmpl, func) in enumerate(self._abas):
            color = _STEP_COLORS[idx]
            item_frame = QFrame()
            item_frame.setObjectName("queueItem")
            item_hl = QHBoxLayout(item_frame)
            item_hl.setContentsMargins(10, 7, 10, 7)
            item_hl.setSpacing(10)

            num_lbl = QLabel(str(idx + 1))
            num_lbl.setFixedSize(24, 24)
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num_lbl.setStyleSheet(
                f"background: {color}; color: white; border-radius: 12px;"
                f"font-weight: 700; font-size: 10px; min-width: 24px;"
            )
            self._num_labels[nome] = num_lbl
            item_hl.addWidget(num_lbl)

            icone_lbl = QLabel()
            icone_lbl.setFixedSize(18, 18)
            icone_lbl.setStyleSheet("background: transparent;")
            try:
                from PyQt6.QtSvg import QSvgRenderer
                svg_str = svg_tmpl.replace("{c}", color)
                renderer = QSvgRenderer(svg_str.encode("utf-8"))
                pix = QPixmap(18, 18)
                pix.fill(Qt.GlobalColor.transparent)
                p = QPainter(pix)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                renderer.render(p)
                p.end()
                icone_lbl.setPixmap(pix)
            except ImportError:
                pass
            item_hl.addWidget(icone_lbl)

            btn = QPushButton(nome)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; font-weight: 600;"
                f"  font-size: 12px; border: none; text-align: left; padding: 0; color: #111827; }}"
                f"QPushButton:hover {{ color: {color}; }}"
                f"QPushButton:disabled {{ color: #9ca3af; }}"
            )
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            btn.clicked.connect(
                lambda checked, n=nome, f=func: self._executar_async(n, f, silencioso=False)
            )
            self._botoes[nome] = btn
            item_hl.addWidget(btn, stretch=1)

            badge = BadgeStatus()
            self._badges[nome] = badge
            item_hl.addWidget(badge)

            self._item_frames[nome] = item_frame
            right_vl.addWidget(item_frame)

        self.sep = QFrame()
        self.sep.setFixedHeight(1)
        self.sep.setStyleSheet("background: #e5e7eb; border: none;")
        right_vl.addWidget(self.sep)

        row_acoes = QHBoxLayout()
        row_acoes.setSpacing(6)

        self.btn_executar_tudo = QPushButton("  Executar Tudo")
        self.btn_executar_tudo.setMinimumHeight(34)
        self.btn_executar_tudo.setIcon(_svg_para_icone(_SVG_PLAY, "white", 16))
        self.btn_executar_tudo.setIconSize(QSize(16, 16))
        self.btn_executar_tudo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_executar_tudo.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; font-weight: 700;"
            "  font-size: 12px; border-radius: 8px; border: none; padding: 0 14px; }"
            "QPushButton:hover { background: #4338ca; }"
            "QPushButton:disabled { background: #e5e7eb; color: #9ca3af; }"
        )
        self.btn_executar_tudo.clicked.connect(self._iniciar_execucao_tudo)
        row_acoes.addWidget(self.btn_executar_tudo)

        self.btn_finalizar = QPushButton("  Apropriar SIAFI")
        self.btn_finalizar.setMinimumHeight(34)
        self.btn_finalizar.setIcon(_svg_para_icone(_SVG_CHECK_CIRCLE, "white", 16))
        self.btn_finalizar.setIconSize(QSize(16, 16))
        self.btn_finalizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_finalizar.setStyleSheet(
            "QPushButton { background: #059669; color: white; font-weight: 700;"
            "  font-size: 12px; border-radius: 8px; border: none; padding: 0 14px; }"
            "QPushButton:hover { background: #047857; }"
            "QPushButton:disabled { background: #e5e7eb; color: #9ca3af; }"
        )
        self.btn_finalizar.clicked.connect(self._exec_finalizar)
        row_acoes.addWidget(self.btn_finalizar)
        right_vl.addLayout(row_acoes)

        self.barra_progresso = BarraProgressoCustom()
        right_vl.addWidget(self.barra_progresso)

        self.painel_log = PainelLog()
        right_vl.addWidget(self.painel_log, stretch=1)

        body.addWidget(right)
        outer.addLayout(body, stretch=1)

        self._etapa_atual = 0
        self._mensagens_parada = []
        self.worker = None

    # ── Pill de data ─────────────────────────────────────────────────────────
    def _criar_pill(self, rotulo: str, valor: str, cor: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dataPill")
        hl = QHBoxLayout(frame)
        hl.setContentsMargins(10, 4, 10, 4)
        hl.setSpacing(6)

        try:
            from PyQt6.QtSvg import QSvgRenderer
            svg_str = _SVG_CALENDARIO.replace("{c}", cor)
            renderer = QSvgRenderer(svg_str.encode("utf-8"))
            pix = QPixmap(14, 14)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            renderer.render(p)
            p.end()
            ico = QLabel()
            ico.setPixmap(pix)
            ico.setFixedSize(14, 14)
            ico.setStyleSheet("background: transparent;")
            hl.addWidget(ico)
        except ImportError:
            pass

        lbl_r = QLabel(f"{rotulo}:")
        lbl_r.setStyleSheet(
            f"font-size: 10px; font-weight: 500; color: {cor}; background: transparent;"
        )
        hl.addWidget(lbl_r)

        lbl_v = QLabel(valor)
        lbl_v.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {cor}; background: transparent;"
        )
        hl.addWidget(lbl_v)

        frame._lbl_valor = lbl_v
        return frame

    def _atualizar_pill(self, pill: QFrame, valor: str):
        if hasattr(pill, "_lbl_valor"):
            pill._lbl_valor.setText(valor if valor else "—")

    # ── Tema ─────────────────────────────────────────────────────────────────
    def aplicar_tema(self, nome: str):
        c = TC[nome]
        for lbl in self._info_headers:
            lbl.setStyleSheet(
                f"font-size: 10px; font-weight: 500; color: {c['dim']};"
                f"letter-spacing: 0.04em; text-transform: uppercase; background: transparent;"
            )
        for lbl_v, cor_key in self._info_values:
            cor = c.get(cor_key, c["text"]) if cor_key else c["text"]
            lbl_v.setStyleSheet(
                f"font-size: 12px; font-weight: 600; color: {cor}; background: transparent;"
            )
        for lbl in [self._lbl_section_doc, self._lbl_fila, self._lbl_resumo_titulo]:
            lbl.setStyleSheet(
                f"font-size: 10px; font-weight: 700; color: {c['accent']};"
                f"letter-spacing: 0.12em; background: transparent;"
            )
        for idx, (btn_nome, btn) in enumerate(self._botoes.items()):
            color = _STEP_COLORS[idx]
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {c['text']}; font-weight: 600;"
                f"  font-size: 12px; border: none; text-align: left; padding: 0; }}"
                f"QPushButton:hover {{ color: {color}; }}"
                f"QPushButton:disabled {{ color: {c['dim']}; }}"
            )
        self.btn_executar_tudo.setStyleSheet(
            f"QPushButton {{ background: {c['accent']}; color: white; font-weight: 700;"
            f"  font-size: 12px; border-radius: 8px; border: none; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {c['accent_h']}; }}"
            f"QPushButton:disabled {{ background: {c['card_alt']}; color: {c['dim']}; }}"
        )
        self.btn_finalizar.setStyleSheet(
            f"QPushButton {{ background: {c['green']}; color: white; font-weight: 700;"
            f"  font-size: 12px; border-radius: 8px; border: none; padding: 0 14px; }}"
            f"QPushButton:hover {{ background: {c['green']}cc; }}"
            f"QPushButton:disabled {{ background: {c['card_alt']}; color: {c['dim']}; }}"
        )
        self.sep.setStyleSheet(f"background: {c['border']}; border: none;")

    # ── Preenchimento de dados ────────────────────────────────────────────────
    def preencher_dados(self, dados, vencimento, apuracao="", status_simples="pulado"):
        self.dados           = dados
        self.vencimento      = vencimento
        self.apuracao        = apuracao
        self._status_simples = status_simples

        self._atualizar_pill(self._pill_apuracao,   apuracao)
        self._atualizar_pill(self._pill_vencimento, vencimento)

        # Cálculo automático de datas por imposto
        try:
            from datas_impostos import calcular_datas_documento
            self._datas_impostos = calcular_datas_documento(dados, vencimento, apuracao)

            impostos_com_lf = [
                {"codigo": cod, "descricao": info["descricao"], "vencimento": info["vencimento"]}
                for cod, info in self._datas_impostos.items()
                if info.get("precisa_lf")
            ]
            self._lfs_impostos = {}
            if impostos_com_lf:
                dlg = DialogoLF(impostos_com_lf, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._lfs_impostos = dlg.obter_lfs()
        except Exception as _e:
            logging.debug("Cálculo de datas de impostos: %s", _e)
            self._datas_impostos = {}
            self._lfs_impostos   = {}

        # Sidebar
        self.lbl_cnpj.setText(dados.get("CNPJ", "N/A"))
        self.lbl_proc.setText(dados.get("Processo", "N/A"))
        self.lbl_sol.setText(dados.get("Solicitação de Pagamento", "N/A"))
        self.lbl_conv.setText(dados.get("Tem Convênio?", dados.get("Tem Convênio", "N/A")))
        nat = dados.get("Natureza", "")
        self.lbl_nat.setText(nat if nat else "Não encontrada")

        ateste_recente = dados.get("Data de Ateste", "")
        self.lbl_ateste.setText(ateste_recente if ateste_recente else "—")

        tem_contrato = dados.get("Tem Contrato?", dados.get("Tem Contrato", "Não"))
        num_contrato = dados.get("Número do Contrato", "")
        sarf_code    = dados.get("SARF", "")
        ig_code      = dados.get("IG", "")

        if tem_contrato == "Sim" and num_contrato:
            self.lbl_contrato.setText(f"{num_contrato}  ({sarf_code})")
            self.lbl_ig.setText(ig_code if ig_code else "— não encontrado")
            cor_ig = "#dc2626" if not ig_code else "#4f46e5"
            self.lbl_ig.setStyleSheet(
                f"font-size: 13px; font-weight: 700; color: {cor_ig}; background: transparent;"
            )
        else:
            self.lbl_contrato.setText("Sem contrato")
            self.lbl_ig.setText("—")

        emps     = dados.get("Empenhos", [])
        notas    = dados.get("Notas Fiscais", [])
        is_simples   = (status_simples == "sim")
        tem_material = any("aterial" in n.get("Tipo", "") for n in notas)
        tem_servico  = any("ervi" in n.get("Tipo", "") for n in notas)

        situacoes = [e.get("Situação", "") for e in emps]
        tem_dsp101_102 = any(
            s.startswith("DSP101") or s.startswith("DSP102")
            or s.startswith("DSP 101") or s.startswith("DSP 102")
            or "101" in s or "102" in s for s in situacoes
        )
        tem_dsp201 = any(
            s.startswith("DSP201") or s.startswith("DSP 201") or "201" in s
            for s in situacoes
        )

        partes_tipo = []
        if tem_dsp101_102 or tem_material:
            partes_tipo.append("Material Simples" if is_simples else "Material Não Simples")
        if tem_dsp201:
            partes_tipo.append(
                "Bem Permanente (Simples)" if is_simples else "Bem Permanente (Não Simples)"
            )
        if tem_servico and not tem_dsp201:
            partes_tipo.append("Serviço Simples" if is_simples else "Serviço não simples")

        tipo_txt = " + ".join(partes_tipo) if partes_tipo else (
            "Material Simples" if is_simples else "Material Não Simples"
        )
        self.lbl_tipo_liq.setText(tipo_txt)
        cor_tipo = "#059669" if is_simples else "#4f46e5"
        self.lbl_tipo_liq.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {cor_tipo}; background: transparent;"
        )

        deds = dados.get("Deduções", [])
        tem_ddf055 = any(
            "DDF055" in d.get("Situação SIAFI", "").upper()
            or "DDF055" in d.get("Situação", "").upper()
            for d in deds
        )
        aviso_msg, aviso_cor = "", ""

        if is_simples and tem_ddf055:
            aviso_msg = "Simples Nacional com DDF055 — verificar se a retenção é devida."
            aviso_cor = "warn"
        elif not is_simples and not tem_ddf055 and status_simples == "nao":
            aviso_msg = "Não é Simples Nacional e sem DDF055 — verificar retenções faltantes."
            aviso_cor = "warn"
        elif status_simples == "nao" and tem_ddf055:
            aviso_msg = "Não Simples + DDF055 presente"
            aviso_cor = "ok"
        elif is_simples and not tem_ddf055:
            aviso_msg = "Simples Nacional — sem retenções"
            aviso_cor = "ok"

        if aviso_msg:
            if aviso_cor == "warn":
                self._frame_aviso_simples.setStyleSheet(
                    "QFrame { background: #fef3c7; border: 1px solid #e0c97a; border-radius: 8px; }"
                )
                self._lbl_aviso_simples.setStyleSheet(
                    "font-size: 10px; font-weight: 600; color: #92400e; background: transparent;"
                )
                self._lbl_aviso_simples.setText(f"⚠  {aviso_msg}")
            else:
                self._frame_aviso_simples.setStyleSheet(
                    "QFrame { background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 8px; }"
                )
                self._lbl_aviso_simples.setStyleSheet(
                    "font-size: 10px; font-weight: 600; color: #5b21b6; background: transparent;"
                )
                self._lbl_aviso_simples.setText(f"✓  {aviso_msg}")
            self._frame_aviso_simples.setVisible(True)
        else:
            self._frame_aviso_simples.setVisible(False)

        # Notas Fiscais
        notas = dados.get("Notas Fiscais", [])
        self.tab_nf.setRowCount(len(notas))
        for i, n in enumerate(notas):
            self.tab_nf.setItem(i, 0, QTableWidgetItem(n.get("Tipo", "")))
            self.tab_nf.setItem(i, 1, QTableWidgetItem(n.get("Número da Nota", "")))
            self.tab_nf.setItem(i, 2, QTableWidgetItem(n.get("Data de Emissão", "")))
            ateste_item = QTableWidgetItem(n.get("Data de Ateste", ""))
            if n.get("Data de Ateste", "") == ateste_recente:
                ateste_item.setForeground(QColor("#059669"))
            self.tab_nf.setItem(i, 3, ateste_item)
            self.tab_nf.setItem(i, 4, QTableWidgetItem(n.get("Valor", "")))

        # Empenhos
        emps = dados.get("Empenhos", [])
        fonte_global = dados.get("Fonte", "")
        self.tab_emp.setRowCount(len(emps))
        for i, e in enumerate(emps):
            self.tab_emp.setItem(i, 0, QTableWidgetItem(e.get("Empenho", "")))
            self.tab_emp.setItem(i, 1, QTableWidgetItem(e.get("Situação", "")))
            rec_item = QTableWidgetItem(e.get("Recurso", ""))
            rec_item.setForeground(QColor("#4f46e5"))
            self.tab_emp.setItem(i, 2, rec_item)
            fonte_emp = e.get("Fonte", fonte_global)
            fonte_item = QTableWidgetItem(fonte_emp)
            fonte_item.setForeground(QColor("#0369a1"))
            self.tab_emp.setItem(i, 3, fonte_item)

        # Deduções — QTreeWidget
        from PyQt6.QtWidgets import QTreeWidgetItem
        deds        = dados.get("Deduções", [])
        notas       = dados.get("Notas Fiscais", [])
        resumo      = dados.get("Resumo", {})
        val_bruto   = _parse_valor_float(resumo.get("Valor Bruto", "0"))
        val_tot_ded = _parse_valor_float(resumo.get("Total Deduções", "0"))

        self.tree_ded.blockSignals(True)
        self.tree_ded.clear()
        self.tree_ded.setRootIsDecorated(True)

        _cor_siafi  = QColor("#0369a1")
        _cor_taxa   = QColor("#92400e")
        _cor_pct_t  = QColor("#065f46")
        _cor_ded_nf = QColor("#6d28d9")
        _cor_filho  = QColor("#374151")
        _bg_filho   = QColor("#f8fafc")
        _aln        = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        fnt_bold    = QFont(); fnt_bold.setBold(True)

        def _fmt_brl(v):
            return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        for di, d in enumerate(deds):
            val_ded   = _parse_valor_float(d.get("Valor", "0"))
            base_calc = _parse_valor_float(d.get("Base Cálculo", "0"))
            taxa      = val_ded / base_calc if base_calc > 0 else (
                val_ded / val_bruto if val_bruto > 0 else 0
            )
            taxa_txt  = f"{taxa * 100:.2f}%"
            pct_tot   = f"{val_ded / val_tot_ded * 100:.2f}%" if val_tot_ded > 0 else "—"

            situacao = d.get("Situação", "")
            siafi    = d.get("Situação SIAFI", "")
            pai = QTreeWidgetItem([situacao, siafi, d.get("Recolhedor", ""), d.get("Valor", ""), taxa_txt, pct_tot])
            pai.setForeground(1, _cor_siafi)
            for col in (3, 4, 5):
                pai.setTextAlignment(col, _aln)
            pai.setForeground(4, _cor_taxa)
            pai.setForeground(5, _cor_pct_t)
            for col in range(6):
                pai.setFont(col, fnt_bold)

            for j, nf in enumerate(notas):
                val_nf  = _parse_valor_float(nf.get("Valor", "0"))
                ded_nf  = taxa * val_nf
                num_nf  = nf.get("Número da Nota", f"{j+1}")
                tipo_nf = nf.get("Tipo", "")
                val_nf_s = nf.get("Valor", "")

                filho = QTreeWidgetItem([
                    f"NF {num_nf}", tipo_nf, val_nf_s, taxa_txt, _fmt_brl(ded_nf), "",
                ])
                filho.setFlags(filho.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                filho.setCheckState(0, Qt.CheckState.Checked)
                filho.setTextAlignment(2, _aln)
                filho.setTextAlignment(3, _aln)
                filho.setTextAlignment(4, _aln)
                for col in range(6):
                    filho.setBackground(col, _bg_filho)
                    filho.setForeground(col, _cor_filho)
                filho.setForeground(3, _cor_taxa)
                filho.setForeground(4, _cor_ded_nf)
                filho.setData(0, Qt.ItemDataRole.UserRole, val_nf)
                filho.setData(1, Qt.ItemDataRole.UserRole, ded_nf)
                pai.addChild(filho)

            pai.setExpanded(True)
            self.tree_ded.addTopLevelItem(pai)

        self.tree_ded.blockSignals(False)
        self._atualizar_soma_ded()

        # Resumo financeiro
        bruto   = resumo.get("Valor Bruto", "")
        liquido = resumo.get("Valor Líquido", "")
        ded_tot = resumo.get("Total Deduções", "")
        if bruto or liquido:
            partes = []
            if bruto:   partes.append(f"Bruto:    R$ {bruto}")
            if ded_tot: partes.append(f"Deduções: R$ {ded_tot}")
            if liquido: partes.append(f"Líquido:  R$ {liquido}")
            self.lbl_resumo.setText("\n".join(partes))
        else:
            self.lbl_resumo.setText("—")

        for nome, _, __ in self._abas:
            self._badges[nome].set("aguardando")
            self._botoes[nome].setEnabled(True)
        self.barra_progresso.definir_total(len(self._abas))
        self.barra_progresso.reset()
        self.painel_log.limpar()

    # ── Deduções ─────────────────────────────────────────────────────────────
    def _ao_check_nf_ded(self, item, column):
        self._atualizar_soma_ded()

    def _atualizar_soma_ded(self):
        soma_nfs, soma_ded, qtd_sel = 0.0, 0.0, 0
        for pi in range(self.tree_ded.topLevelItemCount()):
            pai = self.tree_ded.topLevelItem(pi)
            for ci in range(pai.childCount()):
                filho = pai.child(ci)
                if filho.checkState(0) == Qt.CheckState.Checked:
                    soma_nfs += filho.data(0, Qt.ItemDataRole.UserRole) or 0.0
                    soma_ded += filho.data(1, Qt.ItemDataRole.UserRole) or 0.0
                    qtd_sel  += 1

        def _fmt(v):
            return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        self._lbl_soma_nfs.setText(f"NFs selecionadas: {qtd_sel}  ({_fmt(soma_nfs)})")
        self._lbl_soma_ded.setText(f"Deduções: {_fmt(soma_ded)}")

    def _selecionar_todos_ded(self):
        self.tree_ded.blockSignals(True)
        for pi in range(self.tree_ded.topLevelItemCount()):
            pai = self.tree_ded.topLevelItem(pi)
            for ci in range(pai.childCount()):
                pai.child(ci).setCheckState(0, Qt.CheckState.Checked)
        self.tree_ded.blockSignals(False)
        self._atualizar_soma_ded()

    def _desmarcar_todos_ded(self):
        self.tree_ded.blockSignals(True)
        for pi in range(self.tree_ded.topLevelItemCount()):
            pai = self.tree_ded.topLevelItem(pi)
            for ci in range(pai.childCount()):
                pai.child(ci).setCheckState(0, Qt.CheckState.Unchecked)
        self.tree_ded.blockSignals(False)
        self._atualizar_soma_ded()

    # ── Progresso ────────────────────────────────────────────────────────────
    def _atualizar_progresso_real(self):
        completos = sum(
            1 for nome, _, __ in self._abas
            if self._badges[nome].status() in ("sucesso", "pulado", "alerta")
        )
        self.barra_progresso.definir_progresso(completos)

    # ── Execução ─────────────────────────────────────────────────────────────
    def _executar_async(self, nome, func_bot, silencioso=False):
        for b in self._botoes.values():
            b.setEnabled(False)
        self.btn_executar_tudo.setEnabled(False)
        self.btn_finalizar.setEnabled(False)
        self._badges[nome].set("executando")
        self.painel_log.secao(nome)
        self.worker = AutomacaoWorker(func_bot)
        self.worker.finalizado.connect(
            lambda res: self._ao_finalizar_async(nome, res, silencioso)
        )
        self.worker.start()

    def _ao_finalizar_async(self, nome, resultado, silencioso):
        self._badges[nome].set(resultado["status"])
        self._atualizar_progresso_real()

        if not silencioso:
            for b in self._botoes.values():
                b.setEnabled(True)
            self.btn_executar_tudo.setEnabled(True)
            self.btn_finalizar.setEnabled(True)
            if resultado["status"] == "sucesso":
                QMessageBox.information(self, nome, resultado["mensagem"])
            elif resultado["status"] == "pulado":
                QMessageBox.information(self, f"{nome} — Pulado", resultado["mensagem"])
            elif resultado["status"] == "alerta":
                QMessageBox.warning(self, f"{nome} — Alerta", resultado["mensagem"])
            else:
                QMessageBox.critical(self, f"{nome} — Erro", resultado["mensagem"])
        else:
            if resultado["status"] in ("erro", "alerta"):
                self._mensagens_parada.append(f"Etapa '{nome}': {resultado['mensagem']}")
                self._finalizar_lote(sucesso=False)
            else:
                self._etapa_atual += 1
                QTimer.singleShot(5000, self._processar_proxima_etapa)

    def _iniciar_execucao_tudo(self):
        for btn in self._botoes.values():
            btn.setEnabled(False)
        self.btn_executar_tudo.setEnabled(False)
        self.btn_finalizar.setEnabled(False)
        self._etapa_atual = 0
        self._mensagens_parada = []
        for nome, _, __ in self._abas:
            self._badges[nome].set("aguardando")
        self.barra_progresso.reset()
        self.painel_log.limpar()
        self._processar_proxima_etapa()

    def _processar_proxima_etapa(self):
        if self._etapa_atual >= len(self._abas):
            self._finalizar_lote(sucesso=True)
            return
        nome, _svg, func = self._abas[self._etapa_atual]
        self._executar_async(nome, func, silencioso=True)

    def _finalizar_lote(self, sucesso):
        for btn in self._botoes.values():
            btn.setEnabled(True)
        self.btn_executar_tudo.setEnabled(True)
        self.btn_finalizar.setEnabled(True)
        if sucesso:
            QMessageBox.information(self, "Automação Concluída",
                "Todas as etapas rodaram com sucesso!\nVocê já pode Apropriar no SIAFI.")
        else:
            QMessageBox.warning(self, "Processo Interrompido",
                "O processo foi interrompido:\n\n" + "\n".join(self._mensagens_parada))

    # ── Apropriação ──────────────────────────────────────────────────────────
    def _exec_finalizar(self):
        resposta = QMessageBox.question(
            self, "Confirmação de Apropriação",
            "Tem certeza que deseja Apropriar no SIAFI?\nVerifique se todas as etapas estão concluídas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.btn_finalizar.setEnabled(False)
            import comprasnet_finalizar
            self.worker_fin = AutomacaoWorker(lambda: comprasnet_finalizar.executar())
            self.worker_fin.finalizado.connect(self._ao_finalizar_apropriacao)
            self.worker_fin.start()

    def _ao_finalizar_apropriacao(self, resultado):
        self.btn_finalizar.setEnabled(True)
        if resultado["status"] == "sucesso":
            QMessageBox.information(self, "Apropriação Concluída", resultado["mensagem"])
            tem_201 = any("201" in str(e.get("Situação", ""))
                          for e in self.dados.get("Empenhos", []))
            if tem_201:
                self._dialog_imb050()
            # Verifica vencimentos próximos de INSS/ISS (≤ 7 dias úteis)
            self._verificar_vencimentos_proximos()
        else:
            QMessageBox.critical(self, "Erro na Apropriação", resultado["mensagem"])

    # ── Aviso de vencimento próximo ──────────────────────────────────────────
    def _verificar_vencimentos_proximos(self):
        """
        Após a apropriação, verifica se INSS (DDF050) ou ISS (DDR001/DOB001)
        vencem em ≤ 7 dias úteis. Se sim, exibe DialogoAvisoPagamento.
        """
        try:
            from datas_impostos import CODIGO_SIAFI, dias_uteis_ate
        except ImportError:
            return

        datas = getattr(self, "_datas_impostos", {})
        if not datas:
            return

        num_processo = getattr(self, "dados", {}).get("Processo", "").strip()

        # Códigos de INSS e ISS
        _inss  = {"1162", "1164"}
        _iss   = {"8105", "8047", "8179", "8093", "8027", "5549"}

        avisos = []   # lista de dicts: {tipo, vencimento, dias}
        _vistos_venc = set()   # dedup por (tipo, vencimento)

        for codigo, info in datas.items():
            siafi = info.get("siafi", "")
            if siafi not in ("DDF050", "DDR001", "DOB001"):
                continue
            venc = info.get("vencimento", "")
            if not venc:
                continue

            if codigo in _inss:
                tipo = "INSS"
            elif codigo in _iss:
                tipo = "ISS"
            else:
                continue

            chave = (tipo, venc)
            if chave in _vistos_venc:
                continue
            _vistos_venc.add(chave)

            dias = dias_uteis_ate(venc)
            if 0 <= dias <= 7:
                avisos.append({"tipo": tipo, "vencimento": venc, "dias": dias})

        if not avisos:
            return

        _DialogoAvisoPagamento(avisos, num_processo, parent=self).exec()

    def _dialog_imb050(self):
        natureza   = self.dados.get("Natureza", "")
        subitem    = natureza.split(".")[-1] if "." in natureza else "??"
        bens_uso   = NATUREZA_BENS_MOVEIS.get(natureza, "Não mapeado — consulte a tabela")
        bens_almox = "1.2.3.1.1.08.01"
        nao_mapeado = "Não mapeado" in bens_uso

        try:
            total = sum(
                _parse_valor_float(n.get("Valor", "0"))
                for n in self.dados.get("Notas Fiscais", [])
            )
            valor_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            valor_str = "—"

        dlg = QDialog(self)
        dlg.setWindowTitle("Lançamento SIAFI — IMB050")
        dlg.setMinimumWidth(480)
        dlg.setModal(True)
        vl = QVBoxLayout(dlg)
        vl.setSpacing(12)
        vl.setContentsMargins(24, 22, 24, 22)

        tit = QLabel("Próximo Passo: Lançamento IMB050")
        tit.setStyleSheet("font-size: 15px; font-weight: 800;")
        vl.addWidget(tit)

        inst = QLabel("A apropriação foi realizada. Acesse no SIAFI:\n"
                      "<b>Outros Lançamentos → Situação: IMB050</b>")
        inst.setTextFormat(Qt.TextFormat.RichText)
        inst.setStyleSheet("font-size: 13px;")
        vl.addWidget(inst)

        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px; }"
        )
        cl = QFormLayout(card)
        cl.setSpacing(11)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def rotulo(txt):
            l = QLabel(f"<b>{txt}</b>")
            l.setTextFormat(Qt.TextFormat.RichText)
            l.setStyleSheet("font-size: 13px; color: #374151;")
            return l

        def valor_label(txt, destaque=False, aviso=False):
            l = QLabel(txt)
            cor = "#b45309" if aviso else ("#1d4ed8" if destaque else "#1e293b")
            l.setStyleSheet(
                f"font-family: 'Menlo','Consolas',monospace; font-size: 14px;"
                f"font-weight: {'700' if destaque else '500'}; color: {cor};"
                f"background: transparent;"
            )
            l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return l

        cl.addRow(rotulo("Situação:"),                    valor_label("IMB050", destaque=True))
        cl.addRow(rotulo("Subitem da Despesa:"),          valor_label(subitem, destaque=True))
        cl.addRow(rotulo("Bens Móveis em Uso:"),
                  valor_label(bens_uso, destaque=not nao_mapeado, aviso=nao_mapeado))
        cl.addRow(rotulo("Bens Móveis em Almoxarifado:"), valor_label(bens_almox, destaque=True))
        cl.addRow(rotulo("Valor:"),                       valor_label(valor_str, destaque=True))
        vl.addWidget(card)

        if nao_mapeado:
            av = QLabel(f"Natureza '{natureza}' não encontrada na tabela de mapeamento.\n"
                        "Edite via Configurações → Tabelas.")
            av.setStyleSheet("color: #b45309; font-size: 12px;")
            av.setWordWrap(True)
            vl.addWidget(av)

        bb = QDialogButtonBox()
        btn_ok = bb.addButton("OK — Entendido", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_ok.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; font-weight: 700;"
            "  border-radius: 6px; padding: 8px 20px; border: none; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        bb.accepted.connect(dlg.accept)
        vl.addWidget(bb)
        dlg.exec()

    # ── Wrappers ─────────────────────────────────────────────────────────────
    def _exec_dados_basicos(self):
        import comprasnet_dados_basicos
        return comprasnet_dados_basicos.executar(self.dados, self.vencimento)

    def _exec_principal_orcamento(self):
        import comprasnet_principal_orcamento
        return comprasnet_principal_orcamento.executar(self.dados)

    def _exec_deducao(self):
        import comprasnet_deducao
        return comprasnet_deducao.executar(self.dados)

    def _exec_dados_pagamento(self):
        import comprasnet_dados_pagamento
        return comprasnet_dados_pagamento.executar(self.dados, self.vencimento)

    def _exec_centro_custo(self):
        import comprasnet_centro_custo
        return comprasnet_centro_custo.executar(self.dados)
