"""Tab de parámetros estructurales."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QComboBox, QLabel,
)
from PyQt6.QtCore import pyqtSignal

from core.parametros import ParametrosEdificio

_FC = {"H-21": "21 MPa  — uso general", "H-25": "25 MPa  — cargas medias", "H-30": "30 MPa  — cargas altas"}
_FY = {"ADN 420": "420 MPa — barra corrugada (más común)", "AL 220": "220 MPa — barra lisa (fundaciones)"}


class TabEstructura(QWidget):
    params_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Sistema estructural
        grp_sis = QGroupBox("Sistema estructural")
        form_sis = QFormLayout(grp_sis)
        form_sis.setSpacing(8)

        self.cb_sistema = QComboBox()
        self.cb_sistema.addItems(["porticos", "muros", "mixto"])
        self.cb_sistema.setToolTip(
            "Pórticos: columnas y vigas\n"
            "Muros: losas y muros portantes\n"
            "Mixto: combinación"
        )
        form_sis.addRow("Sistema:", self.cb_sistema)
        layout.addWidget(grp_sis)

        # Hormigón
        grp_horm = QGroupBox("Hormigón armado")
        form_horm = QFormLayout(grp_horm)
        form_horm.setSpacing(8)

        self.cb_hormigon = QComboBox()
        self.cb_hormigon.addItems(list(_FC.keys()))
        form_horm.addRow("Tipo:", self.cb_hormigon)

        self.lbl_fc = QLabel()
        form_horm.addRow("", self.lbl_fc)
        layout.addWidget(grp_horm)

        # Acero
        grp_acero = QGroupBox("Acero de refuerzo")
        form_acero = QFormLayout(grp_acero)
        form_acero.setSpacing(8)

        self.cb_acero = QComboBox()
        self.cb_acero.addItems(list(_FY.keys()))
        form_acero.addRow("Tipo:", self.cb_acero)

        self.lbl_fy = QLabel()
        form_acero.addRow("", self.lbl_fy)
        layout.addWidget(grp_acero)

        layout.addStretch()

        self._refresh_labels()

    def _connect_signals(self) -> None:
        self.cb_sistema.currentTextChanged.connect(self.params_changed)
        self.cb_hormigon.currentTextChanged.connect(self._refresh_labels)
        self.cb_hormigon.currentTextChanged.connect(self.params_changed)
        self.cb_acero.currentTextChanged.connect(self._refresh_labels)
        self.cb_acero.currentTextChanged.connect(self.params_changed)

    def _refresh_labels(self) -> None:
        self.lbl_fc.setText(_FC.get(self.cb_hormigon.currentText(), ""))
        self.lbl_fy.setText(_FY.get(self.cb_acero.currentText(), ""))

    def apply_to_params(self, params: ParametrosEdificio) -> None:
        params.sistema_estructural = self.cb_sistema.currentText()
        params.hormigon_tipo = self.cb_hormigon.currentText()
        params.acero_tipo = self.cb_acero.currentText()

    def load_from_params(self, params: ParametrosEdificio) -> None:
        self.cb_sistema.setCurrentText(params.sistema_estructural)
        self.cb_hormigon.setCurrentText(params.hormigon_tipo)
        self.cb_acero.setCurrentText(params.acero_tipo)
