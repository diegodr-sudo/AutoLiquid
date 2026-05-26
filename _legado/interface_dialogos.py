"""
interface_dialogos.py
Diálogos modais: DialogoTabelas (tabelas editáveis) e DialogoLF (número de LF).
"""

import csv as _csv
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QFrame, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QPushButton,
)
from PyQt6.QtGui import QColor, QFont

from interface_estilos import (
    _carregar_tabelas_config, _salvar_tabelas_config,
    _SHEETS_URL_PADRAO, _NAT_RENDIMENTO_PADRAO,
    _FONTES_RECURSO_PADRAO, _VPD_PADRAO,
)

# ─────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE TABELAS EDITÁVEIS
# ─────────────────────────────────────────────────────────────────────────────
class DialogoTabelas(QDialog):
    _SHEETS_URL = _SHEETS_URL_PADRAO

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração de Tabelas")
        self.setMinimumSize(860, 580)
        self.resize(900, 620)
        self.setModal(True)
        self.setStyleSheet(
            "QTableWidget QLineEdit { padding: 2px 4px; border: 1.5px solid #4f46e5;"
            "  border-radius: 2px; background: white; font-size: 12px; margin: 0; }"
        )

        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(12)

        desc = QLabel("Edite as tabelas de mapeamento usadas pela automação. "
                      "Alterações são salvas localmente.")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #6b7280;")
        vl.addWidget(desc)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.setUsesScrollButtons(True)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 14px; font-size: 11px; min-width: 0; }"
        )

        # ── Aba 1: Contratos ──────────────────────────────────────────────────
        contratos_frame = QFrame()
        cf_vl = QVBoxLayout(contratos_frame)
        cf_vl.setContentsMargins(0, 6, 0, 0)
        cf_vl.setSpacing(6)
        cf_toolbar = QHBoxLayout()
        cf_toolbar.setSpacing(8)

        self._busca_contratos = QLineEdit()
        self._busca_contratos.setPlaceholderText("Buscar por SARF, IG, CNPJ ou Razão Social…")
        self._busca_contratos.setClearButtonEnabled(True)
        self._busca_contratos.setFixedHeight(28)
        self._busca_contratos.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px;"
        )
        self._busca_contratos.textChanged.connect(self._filtrar_contratos)
        cf_toolbar.addWidget(self._busca_contratos, stretch=1)

        self._lbl_contratos_info = QLabel("")
        self._lbl_contratos_info.setStyleSheet(
            "font-size: 10px; color: #64748b; background: transparent;"
        )
        cf_toolbar.addWidget(self._lbl_contratos_info)
        cf_toolbar.addWidget(self._btn_gsheets("contratos"))
        cf_vl.addLayout(cf_toolbar)

        self._tab_contratos = QTableWidget(0, 4)
        self._tab_contratos.setHorizontalHeaderLabels(["SARF", "IG", "CNPJ", "Razão Social"])
        hdr_c = self._tab_contratos.horizontalHeader()
        hdr_c.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr_c.setStretchLastSection(True)
        hdr_c.setDefaultSectionSize(130)
        self._tab_contratos.setColumnWidth(0, 100)
        self._tab_contratos.setColumnWidth(1, 80)
        self._tab_contratos.setColumnWidth(2, 150)
        self._tab_contratos.setAlternatingRowColors(True)
        self._tab_contratos.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tab_contratos.setWordWrap(True)
        cf_vl.addWidget(self._tab_contratos)
        self._carregar_contratos_csv()
        self._tabs.addTab(contratos_frame, "Contratos")

        # ── Aba 2: VPD ───────────────────────────────────────────────────────
        vpd_frame = QFrame()
        vf_vl = QVBoxLayout(vpd_frame)
        vf_vl.setContentsMargins(0, 6, 0, 0)
        vf_vl.setSpacing(6)

        vpd_toolbar = QHBoxLayout()
        vpd_toolbar.setSpacing(8)
        self._busca_vpd = QLineEdit()
        self._busca_vpd.setPlaceholderText("Buscar por Natureza, Situação DSP ou VPD…")
        self._busca_vpd.setClearButtonEnabled(True)
        self._busca_vpd.setFixedHeight(28)
        self._busca_vpd.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px;"
        )
        self._busca_vpd.textChanged.connect(self._filtrar_vpd)
        vpd_toolbar.addWidget(self._busca_vpd, stretch=1)
        vpd_toolbar.addWidget(self._btn_gsheets("natureza"))
        vf_vl.addLayout(vpd_toolbar)

        self._tab_vpd = QTableWidget(0, 3)
        self._tab_vpd.setHorizontalHeaderLabels(["Natureza (DE)", "Situação DSP", "VPD (PARA)"])
        hdr_v = self._tab_vpd.horizontalHeader()
        hdr_v.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr_v.setStretchLastSection(True)
        self._tab_vpd.setColumnWidth(0, 120)
        self._tab_vpd.setColumnWidth(1, 110)
        self._tab_vpd.setAlternatingRowColors(True)
        self._tab_vpd.setWordWrap(True)
        self._popular_vpd()
        vf_vl.addWidget(self._tab_vpd)
        self._tabs.addTab(vpd_frame, "VPD")

        # ── Aba 3: UORG ──────────────────────────────────────────────────────
        uorg_frame = QFrame()
        uf_vl = QVBoxLayout(uorg_frame)
        uf_vl.setContentsMargins(0, 6, 0, 0)
        uf_vl.setSpacing(6)

        uorg_toolbar = QHBoxLayout()
        uorg_toolbar.setSpacing(8)
        self._busca_uorg = QLineEdit()
        self._busca_uorg.setPlaceholderText("Buscar por UGR, UORG ou Nome…")
        self._busca_uorg.setClearButtonEnabled(True)
        self._busca_uorg.setFixedHeight(28)
        self._busca_uorg.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px;"
        )
        self._busca_uorg.textChanged.connect(self._filtrar_uorg)
        uorg_toolbar.addWidget(self._busca_uorg, stretch=1)
        uorg_toolbar.addWidget(self._btn_gsheets("uorg"))
        uf_vl.addLayout(uorg_toolbar)

        self._tab_uorg = QTableWidget(0, 3)
        self._tab_uorg.setHorizontalHeaderLabels(["UGR", "UORG", "NOME"])
        hdr_u = self._tab_uorg.horizontalHeader()
        hdr_u.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr_u.setStretchLastSection(True)
        self._tab_uorg.setColumnWidth(0, 80)
        self._tab_uorg.setColumnWidth(1, 80)
        self._tab_uorg.setAlternatingRowColors(True)
        self._tab_uorg.setWordWrap(True)
        self._popular_uorg()
        uf_vl.addWidget(self._tab_uorg)
        self._tabs.addTab(uorg_frame, "UORG")

        # ── Aba 4: Natureza de Rendimento ─────────────────────────────────────
        nr_frame = QFrame()
        nr_vl = QVBoxLayout(nr_frame)
        nr_vl.setContentsMargins(0, 6, 0, 0)
        nr_vl.setSpacing(6)

        nr_toolbar = QHBoxLayout()
        nr_toolbar.setSpacing(8)
        self._busca_nat_rend = QLineEdit()
        self._busca_nat_rend.setPlaceholderText("Buscar por Código, Descrição ou Código DARF…")
        self._busca_nat_rend.setClearButtonEnabled(True)
        self._busca_nat_rend.setFixedHeight(28)
        self._busca_nat_rend.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px;"
        )
        self._busca_nat_rend.textChanged.connect(self._filtrar_nat_rend)
        nr_toolbar.addWidget(self._busca_nat_rend, stretch=1)
        nr_toolbar.addWidget(self._btn_gsheets("nat_rendimento"))
        nr_vl.addLayout(nr_toolbar)

        self._tab_nat_rend = QTableWidget(0, 3)
        self._tab_nat_rend.setHorizontalHeaderLabels(["Código", "Natureza Rendimento", "Cód. DARF"])
        hdr_nr = self._tab_nat_rend.horizontalHeader()
        hdr_nr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr_nr.setStretchLastSection(True)
        self._tab_nat_rend.setColumnWidth(0, 70)
        self._tab_nat_rend.setColumnWidth(1, 500)
        self._tab_nat_rend.setAlternatingRowColors(True)
        self._tab_nat_rend.setWordWrap(True)
        self._popular_nat_rend()
        nr_vl.addWidget(self._tab_nat_rend)
        self._tabs.addTab(nr_frame, "Nat. Rendimento")

        # ── Aba 5: Fontes de Recursos ─────────────────────────────────────────
        fr_frame = QFrame()
        fr_vl = QVBoxLayout(fr_frame)
        fr_vl.setContentsMargins(0, 6, 0, 0)
        fr_vl.setSpacing(6)

        fr_toolbar = QHBoxLayout()
        fr_toolbar.setSpacing(8)
        self._busca_fontes = QLineEdit()
        self._busca_fontes.setPlaceholderText("Buscar por Fonte de Recurso…")
        self._busca_fontes.setClearButtonEnabled(True)
        self._busca_fontes.setFixedHeight(28)
        self._busca_fontes.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; border: 1px solid #d1d5db; border-radius: 5px;"
        )
        self._busca_fontes.textChanged.connect(self._filtrar_fontes)
        fr_toolbar.addWidget(self._busca_fontes, stretch=1)
        fr_toolbar.addWidget(self._btn_gsheets("fontes"))
        fr_vl.addLayout(fr_toolbar)

        self._tab_fontes = QTableWidget(0, 2)
        self._tab_fontes.setHorizontalHeaderLabels(["Fonte Recurso", "Descrição"])
        hdr_fr = self._tab_fontes.horizontalHeader()
        hdr_fr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr_fr.setStretchLastSection(True)
        self._tab_fontes.setColumnWidth(0, 120)
        self._tab_fontes.setAlternatingRowColors(True)
        self._tab_fontes.setWordWrap(True)
        self._popular_fontes()
        fr_vl.addWidget(self._tab_fontes)
        self._tabs.addTab(fr_frame, "Fontes Recurso")

        # ── Aba 6: Datas dos Impostos (coluna Dia editável) ───────────────────
        from datas_impostos import TABELA_GENERICA, _VENCE_DIA_10
        di_frame = QFrame()
        di_vl = QVBoxLayout(di_frame)
        di_vl.setContentsMargins(0, 6, 0, 0)
        di_vl.setSpacing(4)

        lbl_di = QLabel(
            "Regras de vencimento por código de imposto. "
            "Edite a coluna <b>Dia</b> para sobrescrever o dia de vencimento "
            "(ex.: altere 20 → 19 se o dia 20 cair em feriado local não cadastrado). "
            "As demais colunas são somente leitura."
        )
        lbl_di.setWordWrap(True)
        lbl_di.setStyleSheet("font-size: 11px; color: #6b7280; padding: 2px 0 6px 0;")
        di_vl.addWidget(lbl_di)

        # Carrega overrides salvos para pré-preencher a coluna Dia
        _tc_di  = _carregar_tabelas_config()
        _ov_dia = _tc_di.get("datas_impostos_overrides", {})

        # Colunas: Imposto | Código | SIAFI | Dia (editável) | Apuração | LF?
        cols_di = ["Imposto", "Código", "SIAFI", "Dia", "Apuração", "LF?"]
        self._tab_datas_imp = QTableWidget(len(TABELA_GENERICA), len(cols_di))
        self._tab_datas_imp.setHorizontalHeaderLabels(cols_di)
        hdr_di = self._tab_datas_imp.horizontalHeader()
        hdr_di.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr_di.setStretchLastSection(True)
        self._tab_datas_imp.setColumnWidth(0, 140)
        self._tab_datas_imp.setColumnWidth(1, 60)
        self._tab_datas_imp.setColumnWidth(2, 70)
        self._tab_datas_imp.setColumnWidth(3, 45)
        self._tab_datas_imp.setColumnWidth(4, 200)
        # Habilita edição apenas via duplo-clique ou F2
        self._tab_datas_imp.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked
        )
        self._tab_datas_imp.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self._tab_datas_imp.setAlternatingRowColors(True)
        self._tab_datas_imp.setWordWrap(False)
        self._tab_datas_imp.verticalHeader().setVisible(False)
        self._tab_datas_imp.setStyleSheet(
            "QTableWidget { font-size: 11px; }"
            "QTableWidget::item { padding: 4px 6px; }"
        )

        _cor_map = {
            "DDF050": QColor("#dbeafe"),
            "DDF055": QColor("#ede9fe"),
            "DDR001": QColor("#d1fae5"),
            "DOB001": QColor("#fef3c7"),
        }
        _readonly_flag = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        _editable_flag = _readonly_flag | Qt.ItemFlag.ItemIsEditable

        for i, row in enumerate(TABELA_GENERICA):
            # row = (Imposto, Código, SIAFI, Vencimento-texto, Apuração-texto, LF?)
            imposto, codigo, siafi, _venc_txt, apuracao, lf = row
            bg = _cor_map.get(siafi, QColor("white"))

            # Dia de vencimento: override do usuário ou padrão
            if str(codigo) in _ov_dia:
                dia_val = str(_ov_dia[str(codigo)])
            else:
                dia_val = "10" if codigo in _VENCE_DIA_10 else "20"

            row_cells = [imposto, codigo, siafi, dia_val, apuracao, lf]
            for j, val in enumerate(row_cells):
                item = QTableWidgetItem(str(val))
                item.setBackground(bg)
                # Coluna 2 (SIAFI) em negrito
                if j == 2:
                    fnt = QFont(); fnt.setBold(True)
                    item.setFont(fnt)
                # Coluna 5 (LF?) em vermelho se "Sim"
                if j == 5 and val == "Sim":
                    item.setForeground(QColor("#dc2626"))
                # Somente coluna 3 (Dia) é editável
                if j == 3:
                    item.setFlags(_editable_flag)
                    # Destaque visual para coluna editável
                    item.setBackground(QColor("#fefce8"))
                    fnt2 = QFont(); fnt2.setBold(True)
                    item.setFont(fnt2)
                    item.setForeground(QColor("#92400e"))
                else:
                    item.setFlags(_readonly_flag)
                self._tab_datas_imp.setItem(i, j, item)

        di_vl.addWidget(self._tab_datas_imp, stretch=1)
        self._tabs.addTab(di_frame, "Datas Impostos")

        vl.addWidget(self._tabs, stretch=1)

        # ── Botões de ação ────────────────────────────────────────────────────
        row_btns = QHBoxLayout()
        for txt, fn in [("+ Adicionar", self._adicionar_linha), ("- Remover", self._remover_linha)]:
            b = QPushButton(txt)
            b.setStyleSheet("font-size: 12px; padding: 4px 12px;")
            b.clicked.connect(fn)
            row_btns.addWidget(b)
        row_btns.addStretch()
        vl.addLayout(row_btns)

        bb = QDialogButtonBox()
        btn_salvar = bb.addButton("Salvar", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_salvar.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; font-weight: 700;"
            "  border-radius: 6px; padding: 6px 18px; border: none; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        btn_cancelar = bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        btn_cancelar.setStyleSheet("font-size: 12px; padding: 6px 14px;")
        bb.accepted.connect(self._salvar_e_fechar)
        bb.rejected.connect(self.reject)
        vl.addWidget(bb)

    # ── Botão Google Sheets ────────────────────────────────────────────────
    def _btn_gsheets(self, tab_key):
        btn = QPushButton("  ↻  Atualizar via Planilha")
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { font-size: 10px; font-weight: 600; padding: 0 12px;"
            "  background: #64748b; color: white; border-radius: 5px; border: none; }"
            "QPushButton:hover { background: #475569; }"
            "QPushButton:pressed { background: #334155; }"
        )
        btn.setToolTip("Em breve: sincronizar com planilha Google Sheets")
        btn.clicked.connect(lambda checked=False, k=tab_key: self._btn_gsheets_placeholder(k))
        return btn

    def _btn_gsheets_placeholder(self, tab_key):
        QMessageBox.information(
            self, "Em breve",
            "A sincronização automática com a planilha será configurada em breve.\n\n"
            "Por enquanto, edite as linhas manualmente e clique em Salvar."
        )

    # ── Contratos CSV ─────────────────────────────────────────────────────
    def _arquivo_contratos(self):
        from de_para_contratos import obter_arquivo_contratos

        return obter_arquivo_contratos()

    def _carregar_contratos_csv(self):
        path = self._arquivo_contratos()
        if not os.path.exists(path):
            self._lbl_contratos_info.setText("Arquivo não encontrado")
            return
        try:
            linhas = []
            with open(path, encoding="utf-8-sig", newline="") as f:
                primeira = f.readline()
                if "SARF" in primeira.upper():
                    f.seek(0)
                reader = _csv.DictReader(f)
                for row in reader:
                    linhas.append([
                        row.get("SARF", "").strip(),
                        row.get("IG", "").strip(),
                        row.get("CNPJ", "").strip(),
                        row.get("RAZÃO SOCIAL", row.get("RAZ\u00c3O SOCIAL", "")).strip(),
                    ])
            self._tab_contratos.setRowCount(len(linhas))
            for i, cols in enumerate(linhas):
                for j, val in enumerate(cols):
                    self._tab_contratos.setItem(i, j, QTableWidgetItem(val))
            self._lbl_contratos_info.setText(f"{len(linhas)} contratos")
        except Exception as e:
            self._lbl_contratos_info.setText(f"Erro: {e}")

    def _salvar_contratos_csv(self):
        path = self._arquivo_contratos()
        try:
            linha_instrucao = ""
            if os.path.exists(path):
                with open(path, encoding="utf-8-sig", newline="") as f:
                    primeira = f.readline()
                    if "SARF" not in primeira.upper():
                        linha_instrucao = primeira.rstrip("\n\r")
            rows = self._tab_contratos.rowCount()
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = _csv.writer(f)
                if linha_instrucao:
                    f.write(linha_instrucao + "\n")
                writer.writerow(["SARF", "IG", "CNPJ", "RAZÃO SOCIAL"])
                for i in range(rows):
                    row_data = []
                    for j in range(4):
                        item = self._tab_contratos.item(i, j)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)
            self._lbl_contratos_info.setText(f"Salvo: {rows} contratos")
            try:
                import de_para_contratos as _dpc
                _dpc.recarregar()
            except Exception as _e:
                logging.debug("Não foi possível invalidar cache de contratos: %s", _e)
        except Exception as e:
            self._lbl_contratos_info.setText(f"Erro ao salvar: {e}")

    # ── Filtros ───────────────────────────────────────────────────────────
    def _filtrar_tabela_generico(self, tabela, ncols, texto):
        t = texto.strip().lower()
        for i in range(tabela.rowCount()):
            if not t:
                tabela.setRowHidden(i, False)
                continue
            match = any(
                (item := tabela.item(i, j)) and t in item.text().lower()
                for j in range(ncols)
            )
            tabela.setRowHidden(i, not match)

    def _filtrar_contratos(self, texto):
        self._filtrar_tabela_generico(self._tab_contratos, 4, texto)

    def _filtrar_vpd(self, texto):
        self._filtrar_tabela_generico(self._tab_vpd, 3, texto)

    def _filtrar_uorg(self, texto):
        self._filtrar_tabela_generico(self._tab_uorg, 3, texto)

    def _filtrar_nat_rend(self, texto):
        self._filtrar_tabela_generico(self._tab_nat_rend, 3, texto)

    def _filtrar_fontes(self, texto):
        self._filtrar_tabela_generico(self._tab_fontes, 2, texto)

    # ── Populadores ───────────────────────────────────────────────────────
    _UORG_DADOS = [
        ("151245", "251831", "CAMPUS UNIVERSITARIO DE ARARANGUÁ"),
        ("151246", "109918", "CAMPUS UNIVERSITARIO DE JOINVILLE"),
        ("151247", "251730", "CAMPUS UNIVERSITARIO DE CURITIBANOS"),
        ("153169", "26075", "GABINETE DO REITOR"),
        ("153170", "26115", "PRO-REITORIA DE DESEN GESTAO PESSOAS"),
        ("153171", "26115", "PRO-REITORIA DE DESEN GESTAO PESSOAS - DRH"),
        ("153415", "301347", "DEPARTAMENTO DE MANUTENÇÃO EXTERNA"),
        ("153416", "97298", "SECRETARIA DE RELAÇÕES INTERNACIONAIS"),
        ("153417", "301236", "PRO-REITORIA DE GRADUAÇÃO E EDUCAÇÃO BÁSICA"),
        ("153419", "301236", "PROGRAD/UFSC - BOLSA MONITORIA"),
        ("153420", "301236", "PROGRAD/UFSC - BOLSA ESTAGIO"),
        ("153421", "251270", "COLEGIO DE APLICAÇÃO DA UFSC"),
        ("153422", "200750", "CAMPUS UNIVERSITARIO DE BLUMENAU"),
        ("153424", "250970", "BIBLIOTECA UNIVERSITARIA DA UFSC"),
        ("153425", "206550", "BIOTERIO CENTRAL DA UFSC"),
        ("153426", "301230", "PRO-REITORIA DE ASSUNTOS ESTUDANTIS"),
        ("153428", "301230", "PRAE/UFSC - BOLSA"),
        ("153429", "85460", "RESTAURANTE UNIVERSITARIO DA UFSC"),
        ("153430", "84217", "PRO-REITORIA DE POS-GRADUAÇÃO"),
        ("153431", "84217", "PROPG/UFSC - PROF"),
        ("153432", "301233", "PRO-REITORIA DE PESQUISA E INOVAÇÃO"),
        ("153433", "301233", "PROPESQ/UFSC - BOLSA PIBIC"),
        ("153434", "119942", "PRO-REITORIA DE EXTENSÃO"),
        ("153435", "14892", "CENTRO DE CIENCIA DA SAUDE DA UFSC"),
        ("153436", "14894", "CENTRO TECNOLOGICO DA UFSC"),
        ("153437", "14957", "CENTRO SOCIO-ECONOMICO DA UFSC"),
        ("153438", "14994", "CENTRO DE CIENCIAS DA EDUCAÇÃO DA UFSC"),
        ("153439", "14668", "CENTRO DE CIENCIAS BIOLOGICAS DA UFSC"),
        ("153440", "15004", "CENTRO DE CIENCIA AGRARIAS DA UFSC"),
        ("153441", "15056", "CENTRO DE DESPORTOS DA UFSC"),
        ("153442", "26293", "CENTRO DE CIENCIA JURIDICAS DA UFSC"),
        ("153443", "14726", "CENTRO DE COMUNICAÇÃO E EXPRESSÃO DA UFSC"),
        ("153444", "14675", "CENTRO DE CIÊNCIA FÍSICAS E MATEMÁTICAS-UFSC"),
        ("153445", "14723", "CENTRO DE CIENCIA HUMANAS DA UFSC"),
        ("153446", "97297", "SECRETARIA DE PLANEJAMENTO E ORÇAMENTO"),
        ("153447", "206594", "SUP DE GOVERNANÇA ELETRÔNICA E TIC"),
        ("153771", "26114", "PRO-REITORIA DE ADMINISTRAÇÃO"),
        ("153772", "250743", "PREFEITURA UNIVERSITÁRIA"),
        ("153773", "51095", "DEPARTAMENTO DE COMPRAS"),
        ("153774", "423069", "DEPARTAMENTO DE CONTRATOS"),
        ("153806", "301245", "SECRETARIA DE CULTURA, ARTE E ESPORTE"),
        ("153809", "119942", "PROEX/UFSC - BOLSA"),
        ("153810", "60377", "NUCLEO DE DESENVOLVIMENTO INFANTIS DA UFSC"),
        ("153930", "250764", "DEPARTAMENTO DE FISCALIZAÇÃO DE OBRAS"),
        ("155937", "251511", "DEPARTAMETNO DE INOVAÇÃO"),
        ("155938", "301269", "DEPARTAMENTO DE ESPORTE, CULTURA E LAZER"),
        ("155939", "301240", "PRO-REITORIA DE AÇÕES AFIRMATIVAS E EQUIDADES"),
        ("156188", "218792", "SECRETARIA DE EDUCAÇÃO A DISTÂNCIA"),
        ("156982", "251421", "COORDENADORIA DE GESTÃO AMBIENTAL"),
        ("156983", "301251", "SECRETARIA DE COMUNICAÇÃO"),
        ("156984", "218795", "SECRETARIA DE SEGURANÇA INSTITUCIONAL"),
        ("157024", "251422", "MUSEU DE ARQ E ETNOLOGIA"),
        ("157026", "251425", "EDITORA UNIVERSITÁRIA"),
        ("157465", "423109", "DEPARTAMENTO DE GESTÃO DE BENS PERMANT."),
    ]

    def _popular_vpd(self):
        tc = _carregar_tabelas_config()
        vpd_data = tc.get("vpd_lista", _VPD_PADRAO)
        self._tab_vpd.setRowCount(len(vpd_data))
        for i, row in enumerate(vpd_data):
            for j, val in enumerate(row[:3]):
                self._tab_vpd.setItem(i, j, QTableWidgetItem(str(val)))

    def _popular_uorg(self):
        tc = _carregar_tabelas_config()
        uorg_data = tc.get("uorg_lista", self._UORG_DADOS)
        self._tab_uorg.setRowCount(len(uorg_data))
        for i, row in enumerate(uorg_data):
            for j, val in enumerate(row[:3]):
                self._tab_uorg.setItem(i, j, QTableWidgetItem(str(val)))

    def _popular_nat_rend(self):
        tc = _carregar_tabelas_config()
        nr_data = tc.get("nat_rendimento_lista", _NAT_RENDIMENTO_PADRAO)
        self._tab_nat_rend.setRowCount(len(nr_data))
        for i, row in enumerate(nr_data):
            for j, val in enumerate(row[:3]):
                self._tab_nat_rend.setItem(i, j, QTableWidgetItem(str(val)))

    def _popular_fontes(self):
        tc = _carregar_tabelas_config()
        fr_data = tc.get("fontes_recurso_lista", _FONTES_RECURSO_PADRAO)
        self._tab_fontes.setRowCount(len(fr_data))
        for i, row in enumerate(fr_data):
            for j, val in enumerate(row[:2]):
                self._tab_fontes.setItem(i, j, QTableWidgetItem(str(val)))

    # ── Edição genérica ───────────────────────────────────────────────────
    def _adicionar_linha(self):
        tab = self._tabs.currentWidget()
        if isinstance(tab, QFrame):
            for child in tab.findChildren(QTableWidget):
                child.insertRow(child.rowCount())
                return
        if isinstance(tab, QTableWidget):
            tab.insertRow(tab.rowCount())

    def _remover_linha(self):
        tab = self._tabs.currentWidget()
        if isinstance(tab, QFrame):
            for child in tab.findChildren(QTableWidget):
                if child.currentRow() >= 0:
                    child.removeRow(child.currentRow())
                return
        if isinstance(tab, QTableWidget) and tab.currentRow() >= 0:
            tab.removeRow(tab.currentRow())

    def _extrair_tabela(self, tabela, ncols):
        resultado = []
        for i in range(tabela.rowCount()):
            row = []
            for j in range(ncols):
                item = tabela.item(i, j)
                row.append(item.text().strip() if item else "")
            if any(row):
                resultado.append(tuple(row))
        return resultado

    def _salvar_e_fechar(self):
        novo_vpd  = [list(r) for r in self._extrair_tabela(self._tab_vpd, 3)]
        novo_uorg = list(self._extrair_tabela(self._tab_uorg, 3))
        novo_nr   = list(self._extrair_tabela(self._tab_nat_rend, 3))
        novo_fr   = list(self._extrair_tabela(self._tab_fontes, 2))
        self._salvar_contratos_csv()

        # ── Overrides de dia de vencimento por código ──────────────────────
        # Lê coluna 1 (Código) e coluna 3 (Dia) da tabela de Datas Impostos
        from datas_impostos import _VENCE_DIA_10
        overrides_dia = {}
        for i in range(self._tab_datas_imp.rowCount()):
            codigo_item = self._tab_datas_imp.item(i, 1)
            dia_item    = self._tab_datas_imp.item(i, 3)
            if not (codigo_item and dia_item):
                continue
            codigo = codigo_item.text().strip()
            try:
                dia = int(dia_item.text().strip())
            except ValueError:
                continue
            # Só salva se diferente do padrão (evita poluir o JSON com defaults)
            padrao = 10 if codigo in _VENCE_DIA_10 else 20
            if dia != padrao:
                overrides_dia[codigo] = dia

        dados = _carregar_tabelas_config()
        dados["vpd_lista"]                  = novo_vpd
        dados["uorg_lista"]                 = novo_uorg
        dados["nat_rendimento_lista"]       = novo_nr
        dados["fontes_recurso_lista"]       = novo_fr
        dados["datas_impostos_overrides"]   = overrides_dia
        _salvar_tabelas_config(dados)
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE LF
# ─────────────────────────────────────────────────────────────────────────────
class DialogoLF(QDialog):
    """Diálogo para preencher o número de LF de impostos DOB001."""

    def __init__(self, impostos_lf: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preencher LF dos Impostos")
        self.setMinimumWidth(480)
        self.setModal(True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(16)

        lbl_titulo = QLabel("Número de LF necessário")
        lbl_titulo.setStyleSheet("font-size: 15px; font-weight: 700; color: #1e1b4b;")
        vl.addWidget(lbl_titulo)

        lbl_desc = QLabel(
            "Os impostos abaixo são DOB001 e precisam de um número de LF "
            "(Liquidação Financeira) para serem processados. Preencha cada campo:"
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 12px; color: #6b7280;")
        vl.addWidget(lbl_desc)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #e5e7eb;")
        vl.addWidget(sep)

        self._campos_lf = {}

        for imp in impostos_lf:
            codigo    = imp["codigo"]
            descricao = imp["descricao"]
            venc      = imp.get("vencimento", "")

            grp = QFrame()
            grp.setStyleSheet(
                "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
            )
            grp_vl = QVBoxLayout(grp)
            grp_vl.setContentsMargins(14, 10, 14, 10)
            grp_vl.setSpacing(6)

            hl = QHBoxLayout()
            lbl_nome = QLabel(f"<b>{descricao}</b>  <span style='color:#6b7280'>— cód. {codigo}</span>")
            lbl_nome.setStyleSheet("font-size: 12px;")
            hl.addWidget(lbl_nome)
            hl.addStretch()
            if venc:
                lbl_venc = QLabel(f"Venc. {venc}")
                lbl_venc.setStyleSheet("font-size: 10px; color: #7c3aed; font-weight: 600;")
                hl.addWidget(lbl_venc)
            grp_vl.addLayout(hl)

            campo = QLineEdit()
            campo.setPlaceholderText("Número da LF  (ex.: 2026LF00123)")
            campo.setStyleSheet(
                "QLineEdit { border: 1.5px solid #c7d2fe; background: white;"
                "  font-size: 13px; font-weight: 600; color: #1e1b4b;"
                "  border-radius: 6px; padding: 7px 10px; }"
                "QLineEdit:focus { border-color: #4f46e5; }"
            )
            grp_vl.addWidget(campo)
            self._campos_lf[codigo] = campo
            vl.addWidget(grp)

        bb = QDialogButtonBox()
        btn_ok = bb.addButton("Confirmar", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_ok.setStyleSheet(
            "QPushButton { background: #4f46e5; color: white; font-weight: 700;"
            "  border-radius: 6px; padding: 7px 20px; border: none; }"
            "QPushButton:hover { background: #4338ca; }"
        )
        btn_pular = bb.addButton("Preencher depois", QDialogButtonBox.ButtonRole.RejectRole)
        btn_pular.setStyleSheet("font-size: 12px; padding: 7px 14px;")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        vl.addWidget(bb)

    def obter_lfs(self) -> dict:
        return {cod: campo.text().strip() for cod, campo in self._campos_lf.items()}
