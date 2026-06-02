"""Ventana principal de py-building-gen."""

import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QSplitter, QPushButton, QStatusBar, QLabel,
    QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from core.parametros import ParametrosEdificio
from core.predimensionado import predimensionar
from core.generadores import (
    gen_familias, gen_niveles, gen_arquitectura, gen_estructura,
    gen_instalaciones, gen_vistas, gen_sheets,
)
from core.computo.mediciones import calcular as calcular_mediciones
from core.computo.precios import cargar as cargar_precios
from core.computo.analisis_precios import analizar as analizar_precios
from core.computo.exportador import exportar_excel, exportar_pdf
from ui.tabs.tab_lote import TabLote
from ui.tabs.tab_arquitectura import TabArquitectura
from ui.tabs.tab_estructura import TabEstructura
from ui.tabs.tab_instalaciones import TabInstalaciones
from ui.tabs.tab_presupuesto import TabPresupuesto
from ui.widgets.preview_widget import PreviewWidget
from ui.widgets.predim_widget import PredimWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("py-building-gen — Generador Dynamo para Revit 2027")
        self.setMinimumSize(1200, 700)

        self.params = ParametrosEdificio()
        self._build_ui()
        self._build_menu()
        self._refresh_all()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter, stretch=1)

        # Panel izquierdo: tabs + botones
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.tabs = QTabWidget()
        self.tab_lote = TabLote()
        self.tab_arquitectura = TabArquitectura()
        self.tab_estructura = TabEstructura()
        self.tab_instalaciones = TabInstalaciones()
        self.tab_presupuesto = TabPresupuesto()
        self.tabs.addTab(self.tab_lote, "Lote")
        self.tabs.addTab(self.tab_arquitectura, "Arquitectura")
        self.tabs.addTab(self.tab_estructura, "Estructura")
        self.tabs.addTab(self.tab_instalaciones, "Instalaciones")
        self.tabs.addTab(self.tab_presupuesto, "Presupuesto")
        left_layout.addWidget(self.tabs, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_predim = QPushButton("Calcular Predimensionado")
        self.btn_predim.clicked.connect(self._on_predimensionar)
        btn_row.addWidget(self.btn_predim)

        self.btn_generar = QPushButton("Generar Scripts Dynamo")
        self.btn_generar.setEnabled(False)
        self.btn_generar.clicked.connect(self._on_generar)
        btn_row.addWidget(self.btn_generar)

        self.btn_presupuesto = QPushButton("Exportar Presupuesto")
        self.btn_presupuesto.setEnabled(False)
        self.btn_presupuesto.clicked.connect(self._on_exportar_presupuesto)
        btn_row.addWidget(self.btn_presupuesto)

        left_layout.addLayout(btn_row)

        splitter.addWidget(left_widget)

        # Panel derecho: preview + predim
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.preview = PreviewWidget()
        right_layout.addWidget(self.preview, stretch=3)

        self.predim_widget = PredimWidget()
        right_layout.addWidget(self.predim_widget, stretch=2)

        splitter.addWidget(right_widget)
        splitter.setSizes([440, 760])

        # Status bar
        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label)

        # Señales
        self.tab_lote.params_changed.connect(self._on_params_changed)
        self.tab_arquitectura.params_changed.connect(self._on_params_changed)
        self.tab_estructura.params_changed.connect(self._on_params_changed)
        self.tab_instalaciones.params_changed.connect(self._on_params_changed)
        self.tab_presupuesto.params_changed.connect(self._on_params_changed)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        m_archivo = mb.addMenu("Archivo")

        act_nuevo = QAction("Nuevo proyecto", self)
        act_nuevo.setShortcut("Ctrl+N")
        act_nuevo.triggered.connect(self._on_nuevo)
        m_archivo.addAction(act_nuevo)

        act_abrir = QAction("Abrir proyecto (.pbg)…", self)
        act_abrir.setShortcut("Ctrl+O")
        act_abrir.triggered.connect(self._on_abrir)
        m_archivo.addAction(act_abrir)

        act_guardar = QAction("Guardar proyecto (.pbg)…", self)
        act_guardar.setShortcut("Ctrl+S")
        act_guardar.triggered.connect(self._on_guardar)
        m_archivo.addAction(act_guardar)

        m_archivo.addSeparator()

        act_salir = QAction("Salir", self)
        act_salir.setShortcut("Ctrl+Q")
        act_salir.triggered.connect(self.close)
        m_archivo.addAction(act_salir)

    def _load_params_into_tabs(self) -> None:
        for tab in (
            self.tab_lote, self.tab_arquitectura, self.tab_estructura,
            self.tab_instalaciones, self.tab_presupuesto,
        ):
            tab.load_from_params(self.params)
        self._refresh_all()

    def _on_nuevo(self) -> None:
        self.params = ParametrosEdificio()
        self._load_params_into_tabs()

    def _on_abrir(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir proyecto", "", "Proyecto py-building-gen (*.pbg);;JSON (*.json)"
        )
        if not path:
            return
        try:
            self.params = ParametrosEdificio.cargar(path)
            self._load_params_into_tabs()
        except Exception as exc:
            QMessageBox.critical(self, "Error al abrir", str(exc))

    def _on_guardar(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar proyecto", "proyecto.pbg",
            "Proyecto py-building-gen (*.pbg);;JSON (*.json)"
        )
        if not path:
            return
        try:
            self.params.guardar(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))

    def _on_params_changed(self) -> None:
        for tab in (
            self.tab_lote, self.tab_arquitectura, self.tab_estructura,
            self.tab_instalaciones, self.tab_presupuesto,
        ):
            tab.apply_to_params(self.params)
        self._refresh_all()

    def _refresh_all(self) -> None:
        errores = self.params.validar()
        if errores:
            self.status_label.setText("⚠  " + errores[0])
            self.btn_predim.setEnabled(False)
        else:
            self.status_label.setText(
                f"Lote {self.params.frente:.2f} × {self.params.fondo:.2f} m  |  "
                f"Sup. planta {self.params.superficie_planta_tipo:.1f} m²  |  "
                f"Alt. total {self.params.altura_total:.2f} m"
            )
            self.btn_predim.setEnabled(True)
        self.preview.update_plot(self.params)

    def _on_predimensionar(self) -> None:
        errores = self.params.validar()
        if errores:
            QMessageBox.warning(self, "Parámetros inválidos", "\n".join(errores))
            return
        resultado = predimensionar(self.params)
        self.predim_widget.mostrar(resultado)
        self.btn_generar.setEnabled(True)
        self.btn_presupuesto.setEnabled(True)

    @staticmethod
    def _carpeta_proyecto(nombre: str) -> str:
        """Convierte el nombre del proyecto en un nombre de carpeta válido."""
        s = nombre.strip().lower()
        for origen, dest in [
            ("áàä", "a"), ("éèë", "e"), ("íìï", "i"),
            ("óòö", "o"), ("úùü", "u"), ("ñ", "n"),
        ]:
            for c in origen:
                s = s.replace(c, dest)
        s = re.sub(r"[^a-z0-9_\-]", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s or "proyecto"

    def _on_generar(self) -> None:
        errores = self.params.validar()
        if errores:
            QMessageBox.warning(self, "Parámetros inválidos", "\n".join(errores))
            return

        base_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta raíz de salida",
            str(Path("output/dynamo").resolve()),
        )
        if not base_dir:
            return

        carpeta = self._carpeta_proyecto(self.params.nombre_proyecto)
        out = Path(base_dir) / carpeta
        out.mkdir(parents=True, exist_ok=True)

        try:
            archivos: list[Path] = []
            archivos += [gen_familias.generar(self.params, out)]
            archivos += [gen_niveles.generar(self.params, out)]
            archivos += gen_arquitectura.generar(self.params, out)
            archivos += gen_estructura.generar(self.params, out)
            archivos += gen_instalaciones.generar(self.params, out)
            archivos += gen_vistas.generar(self.params, out)
            archivos += gen_sheets.generar(self.params, out)

            lista = "\n".join(f"  ✓  {p.name}" for p in archivos)
            QMessageBox.information(
                self,
                "Scripts generados",
                f"Proyecto: {self.params.nombre_proyecto}\n"
                f"Carpeta:  {out}\n\n"
                f"{lista}\n\n"
                "Ejecutar en Revit en el orden numérico indicado.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al generar", str(exc))

    def _on_exportar_presupuesto(self) -> None:
        errores = self.params.validar()
        if errores:
            QMessageBox.warning(self, "Parámetros inválidos", "\n".join(errores))
            return

        out_dir = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de salida", str(Path("output/computo").resolve())
        )
        if not out_dir:
            return

        carpeta = self._carpeta_proyecto(self.params.nombre_proyecto)
        out = Path(out_dir) / carpeta
        out.mkdir(parents=True, exist_ok=True)

        try:
            med = calcular_mediciones(self.params)
            precios = cargar_precios()
            ppto = analizar_precios(med, precios, self.params)
            moneda = self.params.moneda

            p_xlsx = exportar_excel(ppto, out / "presupuesto.xlsx", moneda)
            p_pdf  = exportar_pdf(
                ppto, out / "presupuesto.pdf", moneda,
                nombre_proyecto=self.params.nombre_proyecto,
                autor=self.params.autor,
            )

            QMessageBox.information(
                self,
                "Presupuesto exportado",
                f"Costo directo:  {moneda} {ppto.costo_directo:,.0f}\n"
                f"Total c/GG+Hon: {moneda} {ppto.total:,.0f}\n"
                f"Costo/m²:       {moneda} {ppto.total / self.params.superficie_total_edificio:,.0f}\n\n"
                f"✓  {p_xlsx.name}\n"
                f"✓  {p_pdf.name}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar presupuesto", str(exc))
