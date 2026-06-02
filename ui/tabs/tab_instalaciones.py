"""Tab de selección de instalaciones a generar."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QCheckBox, QLabel,
)
from PyQt6.QtCore import pyqtSignal

from core.parametros import ParametrosEdificio

_DESCRIPCIONES = {
    "sanitaria":      "Agua fría/caliente, desagüe cloacal, pluviales · Norma AySA 2023",
    "electrica":      "Tableros, circuitos, iluminación, diagrama unifilar · AEA / IRAM 2281",
    "gas":            "Distribución gas natural, medidores · NAG 200/211 (ENARGAS)",
    "incendio":       "Detección, rociadores, bocas de incendio · NFPA 13 / NFPA 72",
    "termomecanica":  "Climatización, ventilación mecánica · ASHRAE / IRAM",
}


class TabInstalaciones(QWidget):
    params_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        grp = QGroupBox("Instalaciones a incluir en los scripts Dynamo")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(8)

        self.chk_sanitaria = self._make_row(
            vbox, "Instalación sanitaria", _DESCRIPCIONES["sanitaria"], checked=True
        )
        self.chk_electrica = self._make_row(
            vbox, "Instalación eléctrica", _DESCRIPCIONES["electrica"], checked=True
        )
        self.chk_gas = self._make_row(
            vbox, "Instalación de gas", _DESCRIPCIONES["gas"], checked=True
        )
        self.chk_incendio = self._make_row(
            vbox, "Instalación contra incendio", _DESCRIPCIONES["incendio"], checked=True
        )
        self.chk_termomecanica = self._make_row(
            vbox, "Instalación termomecánica", _DESCRIPCIONES["termomecanica"], checked=False
        )

        layout.addWidget(grp)
        layout.addStretch()

    @staticmethod
    def _make_row(parent_layout: QVBoxLayout, titulo: str, desc: str, checked: bool) -> QCheckBox:
        chk = QCheckBox(titulo)
        chk.setChecked(checked)
        parent_layout.addWidget(chk)
        lbl = QLabel(f"  {desc}")
        lbl.setStyleSheet("color: #666666; font-size: 10px;")
        lbl.setWordWrap(True)
        parent_layout.addWidget(lbl)
        return chk

    def _connect_signals(self) -> None:
        for chk in (
            self.chk_sanitaria, self.chk_electrica, self.chk_gas,
            self.chk_incendio, self.chk_termomecanica,
        ):
            chk.toggled.connect(self.params_changed)

    def apply_to_params(self, params: ParametrosEdificio) -> None:
        params.instalacion_sanitaria = self.chk_sanitaria.isChecked()
        params.instalacion_electrica = self.chk_electrica.isChecked()
        params.instalacion_gas = self.chk_gas.isChecked()
        params.instalacion_incendio = self.chk_incendio.isChecked()
        params.instalacion_termomecanica = self.chk_termomecanica.isChecked()

    def load_from_params(self, params: ParametrosEdificio) -> None:
        self.chk_sanitaria.setChecked(params.instalacion_sanitaria)
        self.chk_electrica.setChecked(params.instalacion_electrica)
        self.chk_gas.setChecked(params.instalacion_gas)
        self.chk_incendio.setChecked(params.instalacion_incendio)
        self.chk_termomecanica.setChecked(params.instalacion_termomecanica)
