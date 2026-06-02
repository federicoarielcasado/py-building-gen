"""Generador de scripts Dynamo de documentación.

Produce:
  09_sheets.dyn     — sheets con title block IRAM A3 y vistas colocadas
  10_schedules.dyn  — tablas de cómputo (áreas, puertas, ventanas, locales)

Orden de ejecución: 9 y 10 de 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

# ---------------------------------------------------------------------------
# 09 — Sheets
# ---------------------------------------------------------------------------

_CODE_SHEETS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewSheet, FamilySymbol, ViewPlan, ViewSection, View3D,
    FilteredElementCollector, BuiltInCategory,
    Transaction, Viewport, XYZ,
    UnitUtils, UnitTypeId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

proyecto   = str(IN[0])
autor      = str(IN[1])
escala_planta = int(IN[2])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_title_block():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_TitleBlocks)
           .ToElements())
    # Buscar IRAM A3 primero, luego A3 genérico
    for keyword in ["iram", "A3", "a3"]:
        match = next((s for s in col if keyword.lower() in s.Name.lower()), None)
        if match:
            return match
    return col[0] if col else None

def get_views_by_type(cls):
    return FilteredElementCollector(doc).OfClass(cls).ToElements()

tb = get_title_block()
sheets_creados = []

if not tb:
    OUT = {"error": "No se encontró title block en la plantilla. Cargar familia IRAM A3."}
else:
    if not tb.IsActive:
        tb.Activate()

    # Organización de láminas según portfolio
    config_laminas = [
        {"numero": "A-01", "titulo": "PLANTA BAJA",             "filtro": "PB"},
        {"numero": "A-02", "titulo": "PLANTAS TIPO",            "filtro": "P01"},
        {"numero": "A-03", "titulo": "PLANTA AZOTEA",           "filtro": "AZO"},
        {"numero": "A-04", "titulo": "CORTES",                  "filtro": "CORTE"},
        {"numero": "A-05", "titulo": "FACHADA PRINCIPAL",       "filtro": "FACHADA"},
        {"numero": "E-01", "titulo": "ESTRUCTURA - PLANTA TIPO","filtro": "P01"},
        {"numero": "M-01", "titulo": "VISTA 3D GENERAL",        "filtro": "3D"},
    ]

    # Obtener todas las vistas disponibles
    todas_vistas = (
        list(get_views_by_type(ViewPlan)) +
        list(get_views_by_type(ViewSection)) +
        list(get_views_by_type(View3D))
    )

    with Transaction(doc, "py-building-gen: Sheets") as t:
        t.Start()

        for cfg in config_laminas:
            sheet = ViewSheet.Create(doc, tb.Id)
            sheet.SheetNumber = cfg["numero"]
            sheet.Name = cfg["titulo"]

            # Metadatos del sheet — nombres en inglés y español según idioma de Revit
            _meta = [
                (["Drawn By",    "Dibujado por",   "Elaborado por"], autor),
                (["Designed By", "Diseñado por",   "Proyectado por"], autor),
                (["Project Name","Nombre del proyecto", "Proyecto"], proyecto),
            ]
            for nombres_param, valor in _meta:
                for nombre in nombres_param:
                    p = sheet.LookupParameter(nombre)
                    if p:
                        p.Set(valor)
                        break

            # Colocar vista correspondiente (centrada en A3)
            filtro = cfg["filtro"].lower()
            vista_match = next(
                (v for v in todas_vistas if filtro in v.Name.lower() and sheet.CanAddViewToSheet(v)),
                None,
            )
            if vista_match:
                # Centro de lámina A3 en pies (420x297 mm)
                centro = XYZ(m_to_ft(0.420 / 2), m_to_ft(0.297 / 2), 0)
                Viewport.Create(doc, sheet.Id, vista_match.Id, centro)

            sheets_creados.append({
                "numero": cfg["numero"],
                "titulo": cfg["titulo"],
                "id": sheet.Id.IntegerValue,
            })

        t.Commit()

OUT = sheets_creados
'''

# ---------------------------------------------------------------------------
# 10 — Schedules
# ---------------------------------------------------------------------------

_CODE_SCHEDULES = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewSchedule, ScheduleFieldType, BuiltInParameter,
    ScheduleDefinition, FilteredElementCollector,
    BuiltInCategory, ScheduleSortGroupField,
    Transaction, ElementId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

pisos_tipo = int(IN[0])

def crear_schedule(nombre, categoria):
    try:
        sch = ViewSchedule.CreateSchedule(doc, ElementId(categoria))
        sch.Name = nombre
        return sch
    except Exception:
        return None

schedules_creados = []

with Transaction(doc, "py-building-gen: Tablas de cómputo") as t:
    t.Start()

    config = [
        ("CÓMPUTO - ÁREAS POR NIVEL",    int(BuiltInCategory.OST_Rooms)),
        ("CÓMPUTO - PUERTAS",            int(BuiltInCategory.OST_Doors)),
        ("CÓMPUTO - VENTANAS",           int(BuiltInCategory.OST_Windows)),
        ("CÓMPUTO - COLUMNAS",           int(BuiltInCategory.OST_StructuralColumns)),
        ("CÓMPUTO - VIGAS",              int(BuiltInCategory.OST_StructuralFraming)),
        ("CÓMPUTO - MUROS",              int(BuiltInCategory.OST_Walls)),
        ("CÓMPUTO - LOSAS",              int(BuiltInCategory.OST_Floors)),
    ]

    for nombre, cat_id in config:
        sch = crear_schedule(nombre, cat_id)
        if sch:
            schedules_creados.append({"nombre": nombre, "id": sch.Id.IntegerValue})

    t.Commit()

OUT = schedules_creados
'''


def _script_sheets(params: "ParametrosEdificio", output_dir: Path) -> Path:
    s = DynScript(
        "09_sheets",
        "Crea láminas A3 con title block IRAM 4505 y coloca las vistas de documentación.",
    )

    s.add_code_block(f'"{params.nombre_proyecto}"', label="nombre_proyecto", col=0, row=0)
    s.add_code_block(f'"{params.autor}"',          label="autor",           col=0, row=1)
    s.add_code_block("100",                        label="escala_planta",   col=0, row=2)

    py = s.add_python_node(_CODE_SHEETS, n_inputs=3, label="Crear Sheets", col=1, row=0)
    cbs = [n for n in s._nodes if n is not py]
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Sheets creados", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "09_sheets.dyn")


def _script_schedules(params: "ParametrosEdificio", output_dir: Path) -> Path:
    s = DynScript(
        "10_schedules",
        "Crea tablas de cómputo (áreas, puertas, ventanas, estructura) para documentación y presupuesto.",
    )

    s.add_code_block(str(params.pisos_tipo), label="pisos_tipo", col=0, row=0)

    py = s.add_python_node(_CODE_SCHEDULES, n_inputs=1, label="Crear Schedules", col=1, row=0)
    cbs = [n for n in s._nodes if n is not py]
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Tablas creadas", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "10_schedules.dyn")


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> list[Path]:
    """Genera los scripts de documentación (09 y 10).

    Returns:
        Lista de Path a los archivos .dyn generados.
    """
    output_dir = Path(output_dir)
    return [
        _script_sheets(params, output_dir),
        _script_schedules(params, output_dir),
    ]
