"""Tab de parámetros arquitectónicos."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QScrollArea,
    QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QHBoxLayout,
)
from PyQt6.QtCore import pyqtSignal, Qt

from core.parametros import ParametrosEdificio, TipologiaDepto

_TIPOS_DEPTO = ["1amb", "2amb", "3amb", "4amb", "duplex", "estudio"]


class TabArquitectura(QWidget):
    params_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        self._connect_signals()
        self._update_subsuelo_state()
        self._update_cochera_state()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        scroll.setWidget(container)

        # --- Volumetría ---
        grp_vol = QGroupBox("Volumetría")
        form_vol = QFormLayout(grp_vol)
        form_vol.setSpacing(6)

        self.sb_pisos = QSpinBox()
        self.sb_pisos.setRange(1, 20)
        self.sb_pisos.setValue(6)
        form_vol.addRow("Pisos tipo:", self.sb_pisos)

        self.sb_alt_pb = QDoubleSpinBox()
        self.sb_alt_pb.setRange(2.40, 6.00)
        self.sb_alt_pb.setSingleStep(0.05)
        self.sb_alt_pb.setDecimals(2)
        self.sb_alt_pb.setSuffix(" m")
        self.sb_alt_pb.setValue(3.50)
        form_vol.addRow("Altura PB:", self.sb_alt_pb)

        self.sb_alt_tipo = QDoubleSpinBox()
        self.sb_alt_tipo.setRange(2.40, 4.00)
        self.sb_alt_tipo.setSingleStep(0.05)
        self.sb_alt_tipo.setDecimals(2)
        self.sb_alt_tipo.setSuffix(" m")
        self.sb_alt_tipo.setValue(2.80)
        form_vol.addRow("Altura piso tipo:", self.sb_alt_tipo)

        layout.addWidget(grp_vol)

        # --- Subsuelo y azotea ---
        grp_sub = QGroupBox("Subsuelo y azotea")
        form_sub = QFormLayout(grp_sub)
        form_sub.setSpacing(6)

        self.chk_subsuelo = QCheckBox("Tiene subsuelo")
        form_sub.addRow(self.chk_subsuelo)

        self.sb_cant_sub = QSpinBox()
        self.sb_cant_sub.setRange(0, 2)
        self.sb_cant_sub.setValue(0)
        form_sub.addRow("Cantidad de subsuelos:", self.sb_cant_sub)

        self.chk_azotea = QCheckBox("Tiene azotea")
        self.chk_azotea.setChecked(True)
        form_sub.addRow(self.chk_azotea)

        layout.addWidget(grp_sub)

        # --- Planta baja ---
        grp_pb = QGroupBox("Planta baja")
        form_pb = QFormLayout(grp_pb)
        form_pb.setSpacing(6)

        self.cb_tipo_pb = QComboBox()
        self.cb_tipo_pb.addItems(["porteria", "comercial", "vivienda", "mixto"])
        form_pb.addRow("Uso de PB:", self.cb_tipo_pb)

        self.chk_cochera = QCheckBox("Tiene cochera")
        form_pb.addRow(self.chk_cochera)

        self.cb_cochera_ubic = QComboBox()
        self.cb_cochera_ubic.addItems(["pb", "subsuelo"])
        self.cb_cochera_ubic.setEnabled(False)
        form_pb.addRow("Ubicación cochera:", self.cb_cochera_ubic)

        layout.addWidget(grp_pb)

        # --- Servicios ---
        grp_svc = QGroupBox("Servicios")
        form_svc = QFormLayout(grp_svc)
        form_svc.setSpacing(6)

        self.sb_ascensores = QSpinBox()
        self.sb_ascensores.setRange(1, 2)
        self.sb_ascensores.setValue(1)
        form_svc.addRow("Ascensores:", self.sb_ascensores)

        self.sb_escaleras = QSpinBox()
        self.sb_escaleras.setRange(1, 2)
        self.sb_escaleras.setValue(1)
        form_svc.addRow("Cajas de escalera:", self.sb_escaleras)

        self.cb_sala_maq = QComboBox()
        self.cb_sala_maq.addItems(["azotea", "subsuelo"])
        form_svc.addRow("Sala de máquinas:", self.cb_sala_maq)

        layout.addWidget(grp_svc)

        # --- Mix de departamentos ---
        grp_dep = QGroupBox("Departamentos por piso tipo")
        vbox_dep = QVBoxLayout(grp_dep)
        vbox_dep.setSpacing(6)

        self.lbl_total_dep = QLabel("Total: 2 depto/piso")
        vbox_dep.addWidget(self.lbl_total_dep)

        self.tbl_dep = QTableWidget(0, 3)
        self.tbl_dep.setHorizontalHeaderLabels(["Tipología", "Cantidad", "Sup. (m²)"])
        self.tbl_dep.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_dep.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_dep.setMaximumHeight(160)
        vbox_dep.addWidget(self.tbl_dep)

        btns_dep = QHBoxLayout()
        self.btn_add_dep = QPushButton("+ Agregar")
        self.btn_add_dep.clicked.connect(self._add_tipologia_row)
        btns_dep.addWidget(self.btn_add_dep)
        self.btn_del_dep = QPushButton("− Quitar")
        self.btn_del_dep.clicked.connect(self._del_tipologia_row)
        btns_dep.addWidget(self.btn_del_dep)
        vbox_dep.addLayout(btns_dep)

        layout.addWidget(grp_dep)
        layout.addStretch()

        # Filas por defecto
        self._add_tipologia_row("2amb", 1, 55.0)
        self._add_tipologia_row("3amb", 1, 75.0)

    def _connect_signals(self) -> None:
        self.sb_pisos.valueChanged.connect(self.params_changed)
        self.sb_alt_pb.valueChanged.connect(self.params_changed)
        self.sb_alt_tipo.valueChanged.connect(self.params_changed)
        self.chk_subsuelo.toggled.connect(self._update_subsuelo_state)
        self.chk_subsuelo.toggled.connect(self.params_changed)
        self.sb_cant_sub.valueChanged.connect(self.params_changed)
        self.chk_azotea.toggled.connect(self.params_changed)
        self.cb_tipo_pb.currentTextChanged.connect(self.params_changed)
        self.chk_cochera.toggled.connect(self._update_cochera_state)
        self.chk_cochera.toggled.connect(self.params_changed)
        self.cb_cochera_ubic.currentTextChanged.connect(self.params_changed)
        self.sb_ascensores.valueChanged.connect(self.params_changed)
        self.sb_escaleras.valueChanged.connect(self.params_changed)
        self.cb_sala_maq.currentTextChanged.connect(self.params_changed)
        self.tbl_dep.itemChanged.connect(self._on_table_changed)

    def _update_subsuelo_state(self) -> None:
        activo = self.chk_subsuelo.isChecked()
        self.sb_cant_sub.setEnabled(activo)
        if not activo:
            self.sb_cant_sub.setValue(0)

    def _update_cochera_state(self) -> None:
        self.cb_cochera_ubic.setEnabled(self.chk_cochera.isChecked())

    def _on_table_changed(self) -> None:
        self._update_total_label()
        self.params_changed.emit()

    def _update_total_label(self) -> None:
        total = 0
        for r in range(self.tbl_dep.rowCount()):
            try:
                total += int(self.tbl_dep.item(r, 1).text())
            except (AttributeError, ValueError):
                pass
        self.lbl_total_dep.setText(f"Total: {total} depto/piso")

    def _add_tipologia_row(
        self,
        tipo: str = "2amb",
        cantidad: int = 1,
        superficie: float = 55.0,
    ) -> None:
        self.tbl_dep.blockSignals(True)
        r = self.tbl_dep.rowCount()
        self.tbl_dep.insertRow(r)
        self.tbl_dep.setItem(r, 0, QTableWidgetItem(tipo))
        self.tbl_dep.setItem(r, 1, QTableWidgetItem(str(cantidad)))
        self.tbl_dep.setItem(r, 2, QTableWidgetItem(str(superficie)))
        self.tbl_dep.blockSignals(False)
        self._update_total_label()

    def _del_tipologia_row(self) -> None:
        rows = {idx.row() for idx in self.tbl_dep.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.tbl_dep.removeRow(r)
        self._update_total_label()
        self.params_changed.emit()

    def _parse_tipologias(self) -> list[TipologiaDepto]:
        result: list[TipologiaDepto] = []
        for r in range(self.tbl_dep.rowCount()):
            try:
                tipo = (self.tbl_dep.item(r, 0).text().strip() or "2amb")
                cant = int(self.tbl_dep.item(r, 1).text())
                sup = float(self.tbl_dep.item(r, 2).text())
                result.append(TipologiaDepto(tipo=tipo, cantidad=cant, superficie_m2=sup))
            except (AttributeError, ValueError):
                pass
        return result

    def apply_to_params(self, params: ParametrosEdificio) -> None:
        params.pisos_tipo = self.sb_pisos.value()
        params.altura_pb = self.sb_alt_pb.value()
        params.altura_tipo = self.sb_alt_tipo.value()
        params.tiene_subsuelo = self.chk_subsuelo.isChecked()
        params.cant_subsuelos = self.sb_cant_sub.value()
        params.tiene_azotea = self.chk_azotea.isChecked()
        params.tipo_pb = self.cb_tipo_pb.currentText()
        params.tiene_cochera = self.chk_cochera.isChecked()
        params.cochera_ubicacion = self.cb_cochera_ubic.currentText()
        params.cant_ascensores = self.sb_ascensores.value()
        params.cant_cajas_escalera = self.sb_escaleras.value()
        params.sala_maquinas = self.cb_sala_maq.currentText()
        tipologias = self._parse_tipologias()
        params.mix_tipologias = tipologias
        params.cant_depto_tipo = sum(t.cantidad for t in tipologias)

    def load_from_params(self, params: ParametrosEdificio) -> None:
        self.sb_pisos.setValue(params.pisos_tipo)
        self.sb_alt_pb.setValue(params.altura_pb)
        self.sb_alt_tipo.setValue(params.altura_tipo)
        self.chk_subsuelo.setChecked(params.tiene_subsuelo)
        self.sb_cant_sub.setValue(params.cant_subsuelos)
        self.chk_azotea.setChecked(params.tiene_azotea)
        self.cb_tipo_pb.setCurrentText(params.tipo_pb)
        self.chk_cochera.setChecked(params.tiene_cochera)
        self.cb_cochera_ubic.setCurrentText(params.cochera_ubicacion)
        self.sb_ascensores.setValue(params.cant_ascensores)
        self.sb_escaleras.setValue(params.cant_cajas_escalera)
        self.cb_sala_maq.setCurrentText(params.sala_maquinas)
        self.tbl_dep.setRowCount(0)
        for t in params.mix_tipologias:
            self._add_tipologia_row(t.tipo, t.cantidad, t.superficie_m2)
