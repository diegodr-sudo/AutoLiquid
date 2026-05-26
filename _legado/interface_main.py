"""
interface_main.py
AplicativoPrincipal + DialogoConfiguracoes + ponto de entrada (main).
"""

import logging

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_paths import PORTA_CHROME
from core.runtime_config import (
    obter_datas_salvas,
    obter_porta_chrome,
    obter_preferencia_alerta_inicio_mes,
    salvar_datas_processo,
    salvar_porta_chrome,
    salvar_preferencia_alerta_inicio_mes,
)
from core.theme_tokens import LISTA_TEMAS, TC
from interface_estilos import (
    MAPA_ESTILOS,
    _primeiros_dias_uteis,
    _svg_para_icone,
    _SVG_CHROME,
    _SVG_ENGRENAGEM,
    _SVG_FILA,
)
from services.chrome_service import abrir_chrome, chrome_esta_aberto
from interface_workers import AutomacaoWorker, ExtracaoWorker
from interface_dialogos import DialogoTabelas
from interface_telas import TelaUpload, TelaResultados

# ─────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────────────────
class DialogoConfiguracoes(QDialog):
    """Configurações gerais: tema, Chrome, preferências e doação."""

    def __init__(self, app_ref, parent=None):
        super().__init__(parent)
        self._app = app_ref          # referência a AplicativoPrincipal
        self._porta_chrome = obter_porta_chrome()
        self._pergunta_inicio_mes = obter_preferencia_alerta_inicio_mes()
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(420)
        self.setModal(True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(24, 22, 24, 22)
        vl.setSpacing(20)

        # ── Aparência ─────────────────────────────────────────────────────────
        grp_tema = QGroupBox("Aparência")
        gt_vl = QVBoxLayout(grp_tema)
        gt_vl.setSpacing(8)

        self._btn_group_tema = QButtonGroup(self)
        temas_info = [
            ("claro",    "☀  Claro"),
            ("navy",     "🌙  Modo Noturno"),
            ("colorido", "🎨  Colorido"),
        ]
        for valor, rotulo in temas_info:
            rb = QRadioButton(rotulo)
            rb.setStyleSheet("font-size: 13px;")
            if valor == LISTA_TEMAS[app_ref._idx_tema]:
                rb.setChecked(True)
            rb.clicked.connect(lambda _checked, v=valor: self._app._aplicar_tema_completo(v))
            self._btn_group_tema.addButton(rb)
            gt_vl.addWidget(rb)
        vl.addWidget(grp_tema)

        # ── Conexão Chrome ────────────────────────────────────────────────────
        grp_chrome = QGroupBox("Conexão Chrome")
        gc_form = QFormLayout(grp_chrome)
        gc_form.setSpacing(10)
        gc_form.setContentsMargins(12, 12, 12, 12)

        self._campo_porta = QLineEdit(str(self._porta_chrome))
        self._campo_porta.setPlaceholderText(str(PORTA_CHROME))
        self._campo_porta.setFixedWidth(90)
        self._campo_porta.setStyleSheet("font-size: 13px;")
        gc_form.addRow("Porta de depuração:", self._campo_porta)

        lbl_chrome_info = QLabel(
            "Porta usada pelo Chrome com --remote-debugging-port.\n"
            f"Altere somente se usar porta diferente de {PORTA_CHROME}."
        )
        lbl_chrome_info.setStyleSheet("font-size: 11px; color: #6b7280;")
        lbl_chrome_info.setWordWrap(True)
        gc_form.addRow(lbl_chrome_info)
        vl.addWidget(grp_chrome)

        # ── Preferências de datas ─────────────────────────────────────────────
        grp_datas = QGroupBox("Preferências")
        gd_vl = QVBoxLayout(grp_datas)
        gd_vl.setContentsMargins(12, 12, 12, 12)

        self._chk_limpar_mes = QCheckBox("Perguntar sobre datas salvas no início de cada mês")
        self._chk_limpar_mes.setChecked(self._pergunta_inicio_mes)
        self._chk_limpar_mes.setStyleSheet("font-size: 13px;")
        gd_vl.addWidget(self._chk_limpar_mes)
        vl.addWidget(grp_datas)

        # ── Apoie o projeto ───────────────────────────────────────────────────
        grp_cafe = QGroupBox("☕  Apoie o projeto")
        gce_vl = QVBoxLayout(grp_cafe)
        gce_vl.setContentsMargins(12, 12, 12, 12)
        gce_vl.setSpacing(8)

        lbl_cafe_desc = QLabel(
            "Se esta ferramenta te ajuda no trabalho diário,\n"
            "considere fazer uma contribuição simbólica. ☕"
        )
        lbl_cafe_desc.setStyleSheet("font-size: 12px; color: #374151;")
        lbl_cafe_desc.setWordWrap(True)
        gce_vl.addWidget(lbl_cafe_desc)

        pix_frame = QFrame()
        pix_frame.setStyleSheet(
            "QFrame { background: #f0fdf4; border: 1px solid #86efac;"
            "  border-radius: 8px; }"
        )
        pix_hl = QHBoxLayout(pix_frame)
        pix_hl.setContentsMargins(12, 10, 12, 10)
        pix_hl.setSpacing(12)

        lbl_pix_title = QLabel("PIX")
        lbl_pix_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #15803d; background: transparent;"
        )
        pix_hl.addWidget(lbl_pix_title)

        self._lbl_pix = QLabel("11177961911")
        self._lbl_pix.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #166534;"
            "font-family: 'Menlo','Consolas',monospace; background: transparent;"
        )
        self._lbl_pix.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        pix_hl.addWidget(self._lbl_pix, stretch=1)

        btn_copiar_pix = QPushButton("Copiar")
        btn_copiar_pix.setFixedSize(64, 28)
        btn_copiar_pix.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copiar_pix.setStyleSheet(
            "QPushButton { background: #16a34a; color: white; font-weight: 700;"
            "  font-size: 11px; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #15803d; }"
        )
        btn_copiar_pix.clicked.connect(self._copiar_pix)
        pix_hl.addWidget(btn_copiar_pix)
        gce_vl.addWidget(pix_frame)

        lbl_nome_dev = QLabel("Diego Dutra Ramos  —  DCF/UFSC")
        lbl_nome_dev.setStyleSheet("font-size: 11px; color: #6b7280;")
        lbl_nome_dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gce_vl.addWidget(lbl_nome_dev)
        vl.addWidget(grp_cafe)

        # ── Botões ────────────────────────────────────────────────────────────
        bb = QDialogButtonBox()
        btn_fechar = bb.addButton("Fechar", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_fechar.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; font-weight: 700;"
            "  border-radius: 6px; padding: 7px 20px; border: none; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        bb.accepted.connect(self.accept)
        vl.addWidget(bb)

    def _copiar_pix(self):
        QApplication.clipboard().setText("11177961911")
        QMessageBox.information(
            self, "PIX Copiado",
            "Chave PIX copiada!\n\n"
            "Diego Dutra Ramos\nChave: 11177961911\n\n"
            "Obrigado pelo apoio! ☕"
        )

    def accept(self):
        texto_porta = self._campo_porta.text().strip() or str(PORTA_CHROME)
        try:
            porta = int(texto_porta)
        except ValueError:
            QMessageBox.warning(self, "Configurações", "Informe uma porta válida entre 1 e 65535.")
            self._campo_porta.setFocus()
            return
        if not 1 <= porta <= 65535:
            QMessageBox.warning(self, "Configurações", "Informe uma porta válida entre 1 e 65535.")
            self._campo_porta.setFocus()
            return

        salvar_porta_chrome(porta)
        salvar_preferencia_alerta_inicio_mes(self._chk_limpar_mes.isChecked())
        self._app._atualizar_btn_chrome()
        super().accept()


# ─────────────────────────────────────────────────────────────────────────────
# APLICATIVO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
class AplicativoPrincipal(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DCF · Automação de Liquidação")
        self.resize(1140, 720)
        self.setMinimumSize(960, 640)
        self._idx_tema = 0
        self._apuracao  = ""
        self.setStyleSheet(MAPA_ESTILOS["claro"])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────────────
        self._topbar = QFrame()
        self._topbar.setObjectName("topBar")
        self._topbar.setFixedHeight(46)
        tb_hl = QHBoxLayout(self._topbar)
        tb_hl.setContentsMargins(18, 0, 18, 0)
        tb_hl.setSpacing(10)

        self._lbl_app = QLabel("DCF · Automação de Liquidação")
        self._lbl_app.setStyleSheet(
            "font-size: 14px; font-weight: 700; letter-spacing: -0.2px;"
        )
        tb_hl.addWidget(self._lbl_app)
        tb_hl.addStretch()

        # Botão Tabelas
        self.btn_tabelas = QPushButton("  Tabelas")
        self.btn_tabelas.setIcon(_svg_para_icone(_SVG_ENGRENAGEM, "#6b7280", 15))
        self.btn_tabelas.setIconSize(QSize(15, 15))
        self.btn_tabelas.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tabelas.setMinimumWidth(100)
        self.btn_tabelas.clicked.connect(self._abrir_tabelas)
        tb_hl.addWidget(self.btn_tabelas)

        # Botão Fila de Trabalho
        self.btn_fila = QPushButton("  Fila de Trabalho")
        self.btn_fila.setIcon(_svg_para_icone(_SVG_FILA, "#6b7280", 15))
        self.btn_fila.setIconSize(QSize(15, 15))
        self.btn_fila.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fila.setMinimumWidth(140)
        self.btn_fila.setToolTip("Atualizar fila de trabalho via Solar UFSC")
        self.btn_fila.clicked.connect(self._atualizar_fila_trabalho)
        tb_hl.addWidget(self.btn_fila)

        # Botão Chrome
        self.btn_chrome = QPushButton()
        self.btn_chrome.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_chrome.setMinimumWidth(150)
        self.btn_chrome.clicked.connect(self._acao_chrome)
        tb_hl.addWidget(self.btn_chrome)

        # Botão Configurações (substitui o antigo botão de tema)
        self.btn_config = QPushButton("  Configurações")
        self.btn_config.setIcon(_svg_para_icone(_SVG_ENGRENAGEM, "#6b7280", 15))
        self.btn_config.setIconSize(QSize(15, 15))
        self.btn_config.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_config.setMinimumWidth(130)
        self.btn_config.clicked.connect(self._abrir_configuracoes)
        tb_hl.addWidget(self.btn_config)

        root.addWidget(self._topbar)

        # ── Stack ────────────────────────────────────────────────────────────
        self.stack        = QStackedWidget()
        self.tela_upload  = TelaUpload(self)
        self.tela_result  = TelaResultados(self)
        self.stack.addWidget(self.tela_upload)
        self.stack.addWidget(self.tela_result)
        root.addWidget(self.stack)

        # Passa a referência do app principal para tela_result usar no aviso
        self.tela_result._app_principal = self

        # Timer do Chrome
        self._timer_chrome = QTimer(self)
        self._timer_chrome.timeout.connect(self._atualizar_btn_chrome)
        self._timer_chrome.start(3000)

        self._aplicar_tema_completo("claro")
        self._alerta_inicio_mes()

    # ── Tema ─────────────────────────────────────────────────────────────────
    def _aplicar_tema_completo(self, nome):
        # Garante que _idx_tema fica sincronizado
        if nome in LISTA_TEMAS:
            self._idx_tema = LISTA_TEMAS.index(nome)
        c = TC[nome]
        self.setStyleSheet(MAPA_ESTILOS[nome])
        self._lbl_app.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {c['text']}; letter-spacing: -0.2px;"
        )
        _estilo_pill = (
            f"QPushButton {{ background: transparent; color: {c['muted']}; font-weight: 600;"
            f"  border: 1px solid {c['border']}; border-radius: 16px; padding: 4px 14px;"
            f"  font-size: 12px; }}"
            f"QPushButton:hover {{ background: {c['card_alt']}; color: {c['text']}; }}"
        )
        self.btn_tabelas.setStyleSheet(_estilo_pill)
        self.btn_fila.setStyleSheet(_estilo_pill)
        self.btn_config.setStyleSheet(_estilo_pill)
        self._atualizar_btn_chrome()
        self.tela_result.aplicar_tema(nome)

    def _atualizar_btn_chrome(self):
        nome = LISTA_TEMAS[self._idx_tema]
        c = TC[nome]
        porta = obter_porta_chrome()
        aberto = chrome_esta_aberto(porta)
        if aberto:
            self.btn_chrome.setIcon(_svg_para_icone(_SVG_CHROME, c['green'], 15))
            self.btn_chrome.setIconSize(QSize(15, 15))
            self.btn_chrome.setText("  Chrome Pronto")
            self.btn_chrome.setToolTip(f"Chrome ativo na porta {porta}.")
            self.btn_chrome.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {c['green']}; font-weight: 600;"
                f"  border: 1px solid {c['green']}60; border-radius: 16px; padding: 4px 14px;"
                f"  font-size: 12px; }}"
                f"QPushButton:hover {{ background: {c['green']}12; }}"
            )
        else:
            self.btn_chrome.setIcon(_svg_para_icone(_SVG_CHROME, "white", 15))
            self.btn_chrome.setIconSize(QSize(15, 15))
            self.btn_chrome.setText("  Abrir Chrome")
            self.btn_chrome.setToolTip("Chrome não detectado. Clique para abrir.")
            self.btn_chrome.setStyleSheet(
                f"QPushButton {{ background: {c['red']}; color: white; font-weight: 600;"
                f"  border: none; border-radius: 16px; padding: 4px 14px; font-size: 12px; }}"
                f"QPushButton:hover {{ background: {c['red']}cc; }}"
            )

    def _acao_chrome(self):
        porta = obter_porta_chrome()
        if chrome_esta_aberto(porta):
            QMessageBox.information(
                self, "Chrome",
                f"O Chrome já está aberto na porta {porta}.\n"
                "Pode rodar os scripts normalmente."
            )
        else:
            self.btn_chrome.setText("  Abrindo...")
            self.btn_chrome.setEnabled(False)
            abrir_chrome(porta)

            def verificar(tentativas=[0]):
                tentativas[0] += 1
                if chrome_esta_aberto(porta):
                    self.btn_chrome.setEnabled(True)
                    self._atualizar_btn_chrome()
                    QMessageBox.information(
                        self, "Chrome", f"Chrome aberto na porta {porta}!"
                    )
                elif tentativas[0] < 20:
                    QTimer.singleShot(500, lambda: verificar(tentativas))
                else:
                    self.btn_chrome.setEnabled(True)
                    self._atualizar_btn_chrome()
                    QMessageBox.warning(self, "Chrome", "Chrome demorou para responder.")

            QTimer.singleShot(500, lambda: verificar())

    # ── Diálogos ─────────────────────────────────────────────────────────────
    def _abrir_tabelas(self):
        DialogoTabelas(self).exec()

    def _abrir_configuracoes(self):
        DialogoConfiguracoes(self, parent=self).exec()

    # ── Fila de Trabalho (Solar) ──────────────────────────────────────────────
    def _atualizar_fila_trabalho(self):
        if not chrome_esta_aberto(obter_porta_chrome()):
            QMessageBox.warning(
                self, "Chrome Necessário",
                "O Chrome precisa estar aberto para acessar o Solar.\n"
                "Clique em 'Abrir Chrome' primeiro."
            )
            return

        resposta = QMessageBox.question(
            self, "Atualizar Fila de Trabalho",
            "Isso vai:\n"
            "1. Acessar o Solar UFSC\n"
            "2. Consultar solicitações de pagamento\n"
            "3. Enviar os dados para a planilha Google Sheets\n\n"
            "Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self.btn_fila.setEnabled(False)
        self.btn_fila.setText("  Atualizando...")
        QApplication.processEvents()

        from solar_fila import executar

        self._worker_fila = AutomacaoWorker(lambda: executar())
        self._worker_fila.finalizado.connect(self._ao_finalizar_fila)
        self._worker_fila.start()

    def _ao_finalizar_fila(self, resultado):
        self.btn_fila.setEnabled(True)
        self.btn_fila.setText("  Fila de Trabalho")
        if resultado["status"] == "sucesso":
            QMessageBox.information(self, "Fila Atualizada", resultado["mensagem"])
        elif resultado["status"] == "aviso":
            QMessageBox.warning(self, "Fila — Aviso", resultado["mensagem"])
        else:
            QMessageBox.critical(self, "Erro na Fila", resultado["mensagem"])

    # ── Alerta início de mês ──────────────────────────────────────────────────
    def _alerta_inicio_mes(self):
        from datetime import datetime

        if not obter_preferencia_alerta_inicio_mes():
            return
        hoje = datetime.now()
        primeiros_uteis = _primeiros_dias_uteis(hoje.year, hoje.month)
        if hoje.day not in primeiros_uteis:
            return
        try:
            cfg = obter_datas_salvas()
        except Exception:
            return
        apuracao   = cfg.get("apuracao", "").strip()
        vencimento = cfg.get("vencimento", "").strip()
        if not apuracao and not vencimento:
            return

        resp = QMessageBox.question(
            self, "Verificação de Datas — Início de Mês",
            f"Início de mês detectado (dia útil {primeiros_uteis.index(hoje.day) + 1}/3).\n\n"
            f"Datas salvas do processo anterior:\n"
            f"   Apuração:    {apuracao or '—'}\n"
            f"   Vencimento:  {vencimento or '—'}\n\n"
            f"Deseja continuar utilizando essas datas?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.No:
            try:
                salvar_datas_processo("", "")
            except Exception as _e:
                logging.warning("Não foi possível limpar configurações: %s", _e)
            self.tela_upload.campo_apuracao.clear()
            self.tela_upload.campo_vencimento.clear()
            self.tela_upload.campo_apuracao.setFocus()

    # ── Extração de PDF ───────────────────────────────────────────────────────
    def iniciar_extracao(self, caminho):
        apuracao, vencimento = self.tela_upload.salvar_e_obter()
        self._apuracao = apuracao

        self.tela_upload.drop.setEnabled(False)
        self.tela_upload.drop.label.setText("Processando PDF...")
        self.tela_upload.drop._atualizar_icone("#4f46e5")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self._worker_extracao = ExtracaoWorker(caminho, vencimento)
        self._worker_extracao.concluido.connect(
            lambda dados, simples: self._ao_extrair(dados, vencimento, simples)
        )
        self._worker_extracao.erro.connect(self._ao_erro_extracao)
        self._worker_extracao.start()

    def _ao_extrair(self, dados, vencimento, status_simples):
        QApplication.restoreOverrideCursor()
        self.tela_upload.drop.setEnabled(True)
        self.tela_upload.drop.label.setText(
            "Arraste o PDF da Liquidação aqui\nou clique para selecionar"
        )
        self.tela_upload.drop._atualizar_icone("#9ca3af")

        cnpj = dados.get("CNPJ", "")
        if status_simples == "sim":
            QMessageBox.information(
                self, "Receita Federal", f"CNPJ: {cnpj}\n\nOptante pelo Simples Nacional."
            )
        elif status_simples == "nao":
            QMessageBox.warning(
                self, "Receita Federal",
                f"CNPJ: {cnpj}\n\nNÃO optante pelo Simples Nacional."
            )
        elif status_simples == "erro":
            QMessageBox.warning(
                self, "Receita Federal",
                "Não foi possível conectar à Receita Federal.\nVerifique sua conexão."
            )

        self.tela_result.preencher_dados(dados, vencimento, self._apuracao, status_simples)
        self.stack.setCurrentIndex(1)

    def _ao_erro_extracao(self, mensagem):
        QApplication.restoreOverrideCursor()
        self.tela_upload.drop.setEnabled(True)
        self.tela_upload.drop.label.setText(
            "Arraste o PDF da Liquidação aqui\nou clique para selecionar"
        )
        self.tela_upload.drop._atualizar_icone("#9ca3af")
        QMessageBox.critical(self, "Erro na Extração", mensagem)

    def voltar_para_upload(self):
        self.stack.setCurrentIndex(0)
