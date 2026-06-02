"""Tab de configuración de cómputo y presupuesto."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QCheckBox, QComboBox, QLabel,
)
from PyQt6.QtCore import pyqtSignal

from core.parametros import ParametrosEdificio

_NOTAS_MONEDA = {
    "ARS": "Pesos argentinos — precios ICC INDEC + UOCRA Zona A 2026",
    "USD": "Dólares — conversión tipo de cambio oficial BNA al momento de generación",
}


class TabPresupuesto(QWidget):
    params_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Moneda
        grp_mon = QGroupBox("Moneda")
        form_mon = QFormLayout(grp_mon)
        form_mon.setSpacing(8)

        self.cb_moneda = QComboBox()
        self.cb_moneda.addItems(["ARS", "USD"])
        form_mon.addRow("Moneda:", self.cb_moneda)

        self.lbl_moneda = QLabel()
        self.lbl_moneda.setStyleSheet("color: #666666; font-size: 10px;")
        self.lbl_moneda.setWordWrap(True)
        form_mon.addRow("", self.lbl_moneda)

        layout.addWidget(grp_mon)

        # Rubros adicionales
        grp_rubros = QGroupBox("Rubros a incluir")
        vbox_r = QVBoxLayout(grp_rubros)
        vbox_r.setSpacing(8)

        self.chk_honorarios = QCheckBox("Honorarios profesionales")
        self.chk_honorarios.setChecked(True)
        vbox_r.addWidget(self.chk_honorarios)

        lbl_hon = QLabel("  Escala de honorarios CAd / SCA vigente")
        lbl_hon.setStyleSheet("color: #666666; font-size: 10px;")
        vbox_r.addWidget(lbl_hon)

        self.chk_gastos = QCheckBox("Gastos generales")
        self.chk_gastos.setChecked(True)
        vbox_r.addWidget(self.chk_gastos)

        lbl_gas = QLabel("  Porcentaje sobre costo directo (imprevistos, administración, utilidad)")
        lbl_gas.setStyleSheet("color: #666666; font-size: 10px;")
        lbl_gas.setWordWrap(True)
        vbox_r.addWidget(lbl_gas)

        layout.addWidget(grp_rubros)

        # Info precios
        grp_ref = QGroupBox("Precios de referencia")
        vbox_ref = QVBoxLayout(grp_ref)
        for linea in [
            "Mano de obra: UOCRA Zona A 2026",
            "Materiales: ICC INDEC + Sismat.com.ar",
            "Índice de actualización: CAC mensual",
        ]:
            lbl = QLabel(f"  • {linea}")
            lbl.setStyleSheet("font-size: 10px;")
            vbox_ref.addWidget(lbl)
        layout.addWidget(grp_ref)

        layout.addStretch()
        self._refresh_nota_moneda()

    def _connect_signals(self) -> None:
        self.cb_moneda.currentTextChanged.connect(self._refresh_nota_moneda)
        self.cb_moneda.currentTextChanged.connect(self.params_changed)
        self.chk_honorarios.toggled.connect(self.params_changed)
        self.chk_gastos.toggled.connect(self.params_changed)

    def _refresh_nota_moneda(self) -> None:
        self.lbl_moneda.setText(_NOTAS_MONEDA.get(self.cb_moneda.currentText(), ""))

    def apply_to_params(self, params: ParametrosEdificio) -> None:
        params.moneda = self.cb_moneda.currentText()
        params.incluir_honorarios = self.chk_honorarios.isChecked()
        params.incluir_gastos_generales = self.chk_gastos.isChecked()

    def load_from_params(self, params: ParametrosEdificio) -> None:
        self.cb_moneda.setCurrentText(params.moneda)
        self.chk_honorarios.setChecked(params.incluir_honorarios)
        self.chk_gastos.setChecked(params.incluir_gastos_generales)
