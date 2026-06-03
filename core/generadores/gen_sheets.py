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
    Transaction, Viewport, XYZ, UnitUtils, UnitTypeId,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

proyecto      = str(IN[0])
autor         = str(IN[1])
pisos_tipo    = int(IN[2])
tiene_azotea  = bool(IN[3])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

# Centro A3 horizontal (420 × 297 mm)
CENTRO_A3 = XYZ(m_to_ft(0.210), m_to_ft(0.1485), 0)

def get_title_block():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_TitleBlocks)
           .ToElements())
    for kw in ("iram","a3","A3"):
        match = next((s for s in col if kw.lower() in s.Name.lower()), None)
        if match:
            return match
    return col[0] if col else None

def todas_las_vistas():
    return (list(FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()) +
            list(FilteredElementCollector(doc).OfClass(ViewSection).ToElements()) +
            list(FilteredElementCollector(doc).OfClass(View3D).ToElements()))

def set_meta(sheet, proyecto, autor):
    for nombres, val in [
        (["Drawn By","Dibujado por","Elaborado por"], autor),
        (["Designed By","Diseñado por","Proyectado por"], autor),
        (["Project Name","Nombre del proyecto","Proyecto"], proyecto),
    ]:
        for n in nombres:
            p = sheet.LookupParameter(n)
            if p and not p.IsReadOnly:
                p.Set(val)
                break

def create_sheet(tb, numero, titulo, filtro, vistas):
    sheet = ViewSheet.Create(doc, tb.Id)
    sheet.SheetNumber = numero
    sheet.Name = titulo
    set_meta(sheet, proyecto, autor)
    filtro_l = filtro.lower()
    vm = next((v for v in vistas if filtro_l in v.Name.lower()
               and sheet.CanAddViewToSheet(v)), None)
    if vm:
        Viewport.Create(doc, sheet.Id, vm.Id, CENTRO_A3)
    return sheet.Id.Value

tb = get_title_block()
sheets_creados = []

if not tb:
    OUT = {"error": "No se encontró title block. Cargar familia IRAM A3 antes de correr este script."}
else:
    if not tb.IsActive:
        tb.Activate()

    vistas = todas_las_vistas()

    # ── Configuración de láminas por disciplina ─────────────────────────────
    config_laminas = [
        # ARQ — plantas
        ("A-01", "ARQ - PLANTA BAJA",             "PLANTA PB"),
        ("A-02", "ARQ - PLANTA TIPO (P01)",        "PLANTA P01"),
        ("A-03", "ARQ - PLANTA AZOTEA",            "PLANTA AZO"),
        # ARQ — cortes y alzados
        ("A-04", "ARQ - CORTE A-A",                "CORTE A-A"),
        ("A-05", "ARQ - CORTE B-B",                "CORTE B-B"),
        ("A-06", "ARQ - FACHADA PRINCIPAL",        "FACHADA PRINCIPAL"),
        ("A-07", "ARQ - FACHADA CONTRAFRENTE",     "FACHADA CONTRAFRENTE"),
        ("A-08", "ARQ - FACHADAS LATERALES",       "FACHADA LATERAL"),
        # EST — estructura
        ("E-01", "EST - PLANTA FUNDACIONES",       "PLANTA PB"),
        ("E-02", "EST - PLANTA ESTRUCTURA TIPO",   "PLANTA P01"),
        # MEP — instalaciones
        ("M-01", "MEP - PLANTA INSTALACIONES PB",  "PLANTA PB"),
        ("M-02", "MEP - PLANTA INSTALACIONES TIPO","PLANTA P01"),
        # General
        ("G-01", "3D - VISTA GENERAL",             "3D"),
    ]

    with Transaction(doc, "py-building-gen: Sheets v2") as t:
        t.Start()
        for numero, titulo, filtro in config_laminas:
            sid = create_sheet(tb, numero, titulo, filtro, vistas)
            sheets_creados.append({"numero": numero, "titulo": titulo, "id": sid})
        t.Commit()

OUT = {"total": len(sheets_creados), "laminas": sheets_creados}
'''

# ---------------------------------------------------------------------------
# 10 — Schedules
# ---------------------------------------------------------------------------

_CODE_SCHEDULES = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewSchedule, SchedulableField, ScheduleFieldType,
    BuiltInParameter, FilteredElementCollector,
    BuiltInCategory, ScheduleSortGroupField,
    Transaction, ElementId,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

pisos_tipo = int(IN[0])

def crear_schedule(nombre, cat_id_int):
    try:
        sch = ViewSchedule.CreateSchedule(doc, ElementId(cat_id_int))
        sch.Name = nombre
        return sch
    except Exception:
        return None

def agregar_campos(sch, bip_list):
    """Agrega campos BuiltInParameter al schedule si están disponibles."""
    sched_def = sch.Definition
    campos_disponibles = {f.ParameterId: f for f in sched_def.GetSchedulableFields()}
    for bip in bip_list:
        fid = ElementId(int(bip))
        if fid in campos_disponibles:
            try:
                sched_def.AddField(campos_disponibles[fid])
            except Exception:
                pass

schedules_creados = []

# Campos por categoría (BuiltInParameter)
CAMPOS = {
    int(BuiltInCategory.OST_Rooms): [
        BuiltInParameter.ROOM_NAME,
        BuiltInParameter.ROOM_NUMBER,
        BuiltInParameter.LEVEL_NAME,
        BuiltInParameter.ROOM_AREA,
        BuiltInParameter.ROOM_PERIMETER,
    ],
    int(BuiltInCategory.OST_Doors): [
        BuiltInParameter.ALL_MODEL_MARK,
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.LEVEL_PARAM,
        BuiltInParameter.DOOR_WIDTH,
        BuiltInParameter.DOOR_HEIGHT,
    ],
    int(BuiltInCategory.OST_Windows): [
        BuiltInParameter.ALL_MODEL_MARK,
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.LEVEL_PARAM,
        BuiltInParameter.WINDOW_WIDTH,
        BuiltInParameter.WINDOW_HEIGHT,
    ],
    int(BuiltInCategory.OST_Walls): [
        BuiltInParameter.ALL_MODEL_MARK,
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.WALL_BASE_CONSTRAINT,
        BuiltInParameter.HOST_AREA_COMPUTED,
        BuiltInParameter.CURVE_ELEM_LENGTH,
    ],
    int(BuiltInCategory.OST_Floors): [
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.LEVEL_PARAM,
        BuiltInParameter.HOST_AREA_COMPUTED,
        BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,
    ],
    int(BuiltInCategory.OST_StructuralColumns): [
        BuiltInParameter.ALL_MODEL_MARK,
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.SCHEDULE_BASE_LEVEL_PARAM,
        BuiltInParameter.FAMILY_HEIGHT_PARAM,
    ],
    int(BuiltInCategory.OST_StructuralFraming): [
        BuiltInParameter.ALL_MODEL_MARK,
        BuiltInParameter.ELEM_FAMILY_AND_TYPE_PARAM,
        BuiltInParameter.STRUCTURAL_BEAM_END0_ELEVATION,
        BuiltInParameter.CURVE_ELEM_LENGTH,
    ],
}

config = [
    ("CÓMPUTO - LOCALES Y ÁREAS",   int(BuiltInCategory.OST_Rooms)),
    ("CÓMPUTO - PUERTAS",           int(BuiltInCategory.OST_Doors)),
    ("CÓMPUTO - VENTANAS",          int(BuiltInCategory.OST_Windows)),
    ("CÓMPUTO - MUROS",             int(BuiltInCategory.OST_Walls)),
    ("CÓMPUTO - LOSAS",             int(BuiltInCategory.OST_Floors)),
    ("CÓMPUTO - COLUMNAS",          int(BuiltInCategory.OST_StructuralColumns)),
    ("CÓMPUTO - VIGAS",             int(BuiltInCategory.OST_StructuralFraming)),
]

with Transaction(doc, "py-building-gen: Schedules v2") as t:
    t.Start()
    for nombre, cat_id in config:
        sch = crear_schedule(nombre, cat_id)
        if sch:
            campos_bip = CAMPOS.get(cat_id, [])
            agregar_campos(sch, campos_bip)
            schedules_creados.append({"nombre": nombre, "id": sch.Id.Value})
    t.Commit()

OUT = {"total": len(schedules_creados), "schedules": schedules_creados}
'''


_CODE_NORTE_CUADRO = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, ViewSheet, FamilySymbol, FamilyInstance,
    FilteredElementCollector, BuiltInCategory,
    Transaction, TextNote, TextNoteOptions,
    XYZ, UV, UnitUtils, UnitTypeId, ElementId,
)
from Autodesk.Revit.DB.Structure import StructuralType as ST
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m  = float(IN[0])
fondo_m   = float(IN[1])
pisos_tipo = int(IN[2])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_planta_pb():
    todas = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    return next((v for v in todas if "PLANTA PB" in v.Name and not v.IsTemplate), None)

def get_sheet(numero):
    sheets = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
    return next((s for s in sheets if s.SheetNumber == numero), None)

resultado = []
vista_pb  = get_planta_pb()

with Transaction(doc, "py-building-gen: Norte y cuadro superficies") as t:
    t.Start()

    # ── Símbolo de Norte ───────────────────────────────────────────────────
    # Buscar familia "North Arrow" o "Flecha Norte" en anotaciones genéricas
    north_col = (FilteredElementCollector(doc)
                 .OfClass(FamilySymbol)
                 .OfCategory(BuiltInCategory.OST_GenericAnnotation)
                 .ToElements())
    _kw_norte = ("north","norte","arrow","flecha","nort")
    north_sym = next((s for s in north_col
                      if any(k in s.FamilyName.lower() for k in _kw_norte)), None)

    if north_sym and vista_pb:
        if not north_sym.IsActive:
            north_sym.Activate()
        # Colocar en el ángulo superior izquierdo de la planta
        pt_norte = XYZ(m_to_ft(-2.0), m_to_ft(fondo_m + 1.5), 0)
        inst = doc.Create.NewFamilyInstance(pt_norte, north_sym, vista_pb, ST.NonStructural)
        resultado.append({"tipo": "norte", "id": inst.Id.Value})
    else:
        resultado.append({"tipo": "norte", "status": "familia no encontrada en template"})

    # ── Cuadro de superficies (TextNote en hoja A-01) ────────────────────
    sheet_a01 = get_sheet("A-01")
    if sheet_a01 and vista_pb:
        # Calcular superficies
        ESC_ANCHO = 3.00; ESC_FONDO = 5.50; ASC_ANCHO = 2.00; PASILLO = 1.20
        ancho_nuc = 1 * ESC_ANCHO + 1 * ASC_ANCHO   # default: 1 esc + 1 asc
        y_nuc   = fondo_m - ESC_FONDO
        y_pas   = y_nuc - PASILLO
        sup_planta = frente_m * fondo_m
        sup_util   = frente_m * y_pas   # área de departamentos
        sup_circ   = frente_m * (fondo_m - y_pas)  # pasillo + shaft

        lineas = [
            f"CUADRO DE SUPERFICIES",
            f"Lote:                {frente_m:.2f} x {fondo_m:.2f} = {sup_planta:.1f} m²",
            f"Sup. útil/piso tipo: {sup_util:.1f} m²",
            f"Sup. circulación:    {sup_circ:.1f} m²",
            f"Pisos tipo:          {pisos_tipo}",
            f"Sup. total construida: {sup_planta * (pisos_tipo + 2):.1f} m²",
        ]
        texto = "\\n".join(lineas)

        try:
            tnOpts = TextNoteOptions(ElementId.InvalidElementId)
            # Colocar en la esquina inferior derecha de la hoja (en coordenadas de hoja)
            pt_txt = XYZ(m_to_ft(0.300), m_to_ft(0.035), 0)
            tn = TextNote.Create(doc, sheet_a01.Id, pt_txt, texto, tnOpts)
            resultado.append({"tipo": "cuadro_superficies", "id": tn.Id.Value})
        except Exception as e:
            resultado.append({"tipo": "cuadro_superficies", "error": str(e)})

    t.Commit()

OUT = {"resultado": resultado}
'''


def _script_sheets(params: "ParametrosEdificio", output_dir: Path) -> Path:
    s = DynScript(
        "09_sheets",
        "Crea 13 láminas A3 IRAM organizadas por disciplina (ARQ, EST, MEP, 3D) con vistas colocadas.",
    )

    cb_proy   = s.add_code_block(f'"{params.nombre_proyecto}"',          label="nombre_proyecto", col=0, row=0)
    cb_autor  = s.add_code_block(f'"{params.autor}"',                    label="autor",           col=0, row=1)
    cb_pisos  = s.add_code_block(str(params.pisos_tipo),                 label="pisos_tipo",      col=0, row=2)
    cb_azotea = s.add_code_block(str(params.tiene_azotea).lower(),       label="tiene_azotea",    col=0, row=3)

    cbs = [cb_proy, cb_autor, cb_pisos, cb_azotea]
    py = s.add_python_node(_CODE_SHEETS, n_inputs=len(cbs), label="Crear Sheets v2", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Sheets creados", col=2, row=0)
    s.connect(py, w)

    # Norte + cuadro de superficies
    cb_frente2 = s.add_code_block(str(params.frente),       label="frente_m",   col=0, row=6)
    cb_fondo2  = s.add_code_block(str(params.fondo),        label="fondo_m",    col=0, row=7)
    cb_pisos2  = s.add_code_block(str(params.pisos_tipo),   label="pisos_tipo", col=0, row=8)
    py_nc = s.add_python_node(_CODE_NORTE_CUADRO, n_inputs=3, label="Norte y Cuadro", col=1, row=6)
    s.connect(cb_frente2, py_nc, to_input=0)
    s.connect(cb_fondo2,  py_nc, to_input=1)
    s.connect(cb_pisos2,  py_nc, to_input=2)
    w_nc = s.add_watch(label="Norte y cuadro", col=2, row=6)
    s.connect(py_nc, w_nc)

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
