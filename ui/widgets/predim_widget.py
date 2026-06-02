"""Widget de resultados de predimensionado estructural."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QTextEdit
from PyQt6.QtGui import QFont

from core.predimensionado import ResultadoPredimensionado


class PredimWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        grp = QGroupBox("Predimensionado estructural (CIRSOC 201-2005)")
        inner = QVBoxLayout(grp)

        self.txt = QTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setFont(QFont("Courier New", 8))
        self.txt.setPlaceholderText(
            "Presione «Calcular Predimensionado» para ver los resultados."
        )
        inner.addWidget(self.txt)
        layout.addWidget(grp)

    def mostrar(self, resultado: ResultadoPredimensionado) -> None:
        self.txt.setPlainText(resultado.resumen())
