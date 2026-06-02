"""Tab de parámetros del lote."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QCheckBox, QLineEdit, QPushButton,
    QHBoxLayout, QFileDialog,
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont

from core.parametros import ParametrosEdificio


class TabLote(QWidget):
    params_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Grupo: datos del proyecto
        grp_proy = QGroupBox("Datos del proyecto")
        grp_proy.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        form_proy = QFormLayout(grp_proy)
        form_proy.setSpacing(8)

        self.le_nombre = QLineEdit()
        self.le_nombre.setPlaceholderText("Nombre del proyecto")
        self.le_nombre.setText("Edificio Caballito")
        form_proy.addRow("Nombre:", self.le_nombre)

        self.le_autor = QLineEdit()
        self.le_autor.setPlaceholderText("Nombre del profesional")
        self.le_autor.setText("Federico A. Casado")
        form_proy.addRow("Autor:", self.le_autor)

        layout.addWidget(grp_proy)

        # Grupo: dimensiones
        grp_dim = QGroupBox("Dimensiones del lote")
        form = QFormLayout(grp_dim)
        form.setSpacing(8)

        self.sb_frente = QDoubleSpinBox()
        self.sb_frente.setRange(4.0, 50.0)
        self.sb_frente.setSingleStep(0.01)
        self.sb_frente.setDecimals(2)
        self.sb_frente.setSuffix(" m")
        self.sb_frente.setValue(10.0)
        form.addRow("Frente:", self.sb_frente)

        self.sb_fondo = QDoubleSpinBox()
        self.sb_fondo.setRange(8.0, 100.0)
        self.sb_fondo.setSingleStep(0.01)
        self.sb_fondo.setDecimals(2)
        self.sb_fondo.setSuffix(" m")
        self.sb_fondo.setValue(24.0)
        form.addRow("Fondo:", self.sb_fondo)

        layout.addWidget(grp_dim)

        # Grupo: lote real
        grp_real = QGroupBox("Lote real (Buenos Aires Data)")
        vbox = QVBoxLayout(grp_real)
        vbox.setSpacing(6)

        self.chk_lote_real = QCheckBox("Usar lote real desde GeoJSON")
        vbox.addWidget(self.chk_lote_real)

        row = QHBoxLayout()
        self.le_geojson = QLineEdit()
        self.le_geojson.setPlaceholderText("data/lote/caballito_parcela.geojson")
        self.le_geojson.setEnabled(False)
        row.addWidget(self.le_geojson)

        self.btn_browse = QPushButton("...")
        self.btn_browse.setFixedWidth(32)
        self.btn_browse.setEnabled(False)
        self.btn_browse.clicked.connect(self._browse_geojson)
        row.addWidget(self.btn_browse)
        vbox.addLayout(row)

        layout.addWidget(grp_real)
        layout.addStretch()

        self.chk_lote_real.toggled.connect(self.le_geojson.setEnabled)
        self.chk_lote_real.toggled.connect(self.btn_browse.setEnabled)

    def _connect_signals(self) -> None:
        self.le_nombre.textChanged.connect(self.params_changed)
        self.le_autor.textChanged.connect(self.params_changed)
        self.sb_frente.valueChanged.connect(self.params_changed)
        self.sb_fondo.valueChanged.connect(self.params_changed)
        self.chk_lote_real.toggled.connect(self.params_changed)
        self.le_geojson.textChanged.connect(self.params_changed)

    def _browse_geojson(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar GeoJSON del lote", "", "GeoJSON (*.geojson *.json)"
        )
        if path:
            self.le_geojson.setText(path)

    def apply_to_params(self, params: ParametrosEdificio) -> None:
        params.nombre_proyecto = self.le_nombre.text().strip() or "Proyecto"
        params.autor = self.le_autor.text().strip() or "Autor"
        params.frente = self.sb_frente.value()
        params.fondo = self.sb_fondo.value()
        params.usar_lote_real = self.chk_lote_real.isChecked()

    def load_from_params(self, params: ParametrosEdificio) -> None:
        self.le_nombre.setText(params.nombre_proyecto)
        self.le_autor.setText(params.autor)
        self.sb_frente.setValue(params.frente)
        self.sb_fondo.setValue(params.fondo)
        self.chk_lote_real.setChecked(params.usar_lote_real)
