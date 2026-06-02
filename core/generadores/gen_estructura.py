"""Generador del script Dynamo 04_estructura.dyn.

Crea columnas y vigas de hormigón armado en la grilla estructural,
con secciones derivadas del predimensionado CIRSOC 201-2005.

Orden de ejecución: 4 de 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript
from core.predimensionado import predimensionar
from core.generadores.gen_familias import nombres_tipos

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

_CODE_COLUMNAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FamilySymbol, Level, XYZ,
    FilteredElementCollector, BuiltInCategory,
    Transaction, UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Structure import StructuralType

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m       = float(IN[0])
fondo_m        = float(IN[1])
lado_col_cm    = float(IN[2])   # sección cuadrada en cm (predimensionado)
pisos_tipo     = int(IN[3])
nombre_col_tipo = str(IN[4])    # "Columna HA 35x35cm"  (creado por 00_familias.dyn)
paso_m         = 5.0

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_col_symbol():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_StructuralColumns)
           .ToElements())
    # 1° intento: tipo exacto creado por 00_familias.dyn
    match = next((s for s in col if s.Name == nombre_col_tipo), None)
    if match:
        return match
    # 2° intento: familia con keyword de hormigón
    _kw = ("concrete", "hormigon", "hormigón", "ha ", "h.a")
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in _kw)), None)
    return match or (col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

sym = get_col_symbol()
columnas = []

if sym:
    # Ajustar parámetro de sección si el tipo lo permite
    try:
        lado_ft = m_to_ft(lado_col_cm / 100)
        sym.LookupParameter("b").Set(lado_ft)
        sym.LookupParameter("h").Set(lado_ft)
    except Exception:
        pass

    if not sym.IsActive:
        sym.Activate()

    with Transaction(doc, "py-building-gen: Columnas") as t:
        t.Start()

        for nombre_nivel in ["PB"] + [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]:
            lvl = get_level(nombre_nivel)
            x = 0.0
            while x <= frente_m + 0.001:
                y = 0.0
                while y <= fondo_m + 0.001:
                    pt = XYZ(m_to_ft(x), m_to_ft(y), 0)
                    inst = doc.Create.NewFamilyInstance(pt, sym, lvl, StructuralType.Column)
                    columnas.append(inst.Id.IntegerValue)
                    y += paso_m
                x += paso_m

        t.Commit()

OUT = f"{len(columnas)} columnas {lado_col_cm:.0f}x{lado_col_cm:.0f}cm creadas"
'''

_CODE_VIGAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FamilySymbol, Level, XYZ, Line,
    FilteredElementCollector, BuiltInCategory,
    Transaction, UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Structure import StructuralType

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m        = float(IN[0])
fondo_m         = float(IN[1])
ancho_cm        = float(IN[2])
alto_cm         = float(IN[3])
pisos_tipo      = int(IN[4])
nombre_viga_tipo = str(IN[5])   # "Viga HA 45x85cm"  (creado por 00_familias.dyn)
paso_m          = 5.0

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_beam_symbol():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_StructuralFraming)
           .ToElements())
    # 1° intento: tipo exacto creado por 00_familias.dyn
    match = next((s for s in col if s.Name == nombre_viga_tipo), None)
    if match:
        return match
    # 2° intento: familia con keyword de hormigón
    _kw = ("concrete", "hormigon", "hormigón", "ha ", "h.a")
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in _kw)), None)
    return match or (col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

sym = get_beam_symbol()
vigas = []

if sym:
    try:
        sym.LookupParameter("b").Set(m_to_ft(ancho_cm / 100))
        sym.LookupParameter("h").Set(m_to_ft(alto_cm  / 100))
    except Exception:
        pass

    if not sym.IsActive:
        sym.Activate()

    with Transaction(doc, "py-building-gen: Vigas") as t:
        t.Start()

        for nombre_nivel in [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]:
            lvl = get_level(nombre_nivel)

            # Vigas en dirección X (paralelas al frente) — una por eje Y
            y = 0.0
            while y <= fondo_m + 0.001:
                x = 0.0
                while x + paso_m <= frente_m + 0.001:
                    p1 = XYZ(m_to_ft(x),        m_to_ft(y), 0)
                    p2 = XYZ(m_to_ft(x + paso_m), m_to_ft(y), 0)
                    inst = doc.Create.NewFamilyInstance(
                        Line.CreateBound(p1, p2), sym, lvl, StructuralType.Beam
                    )
                    vigas.append(inst.Id.IntegerValue)
                    x += paso_m
                y += paso_m

            # Vigas en dirección Y (paralelas al fondo)
            x = 0.0
            while x <= frente_m + 0.001:
                y = 0.0
                while y + paso_m <= fondo_m + 0.001:
                    p1 = XYZ(m_to_ft(x), m_to_ft(y),        0)
                    p2 = XYZ(m_to_ft(x), m_to_ft(y + paso_m), 0)
                    inst = doc.Create.NewFamilyInstance(
                        Line.CreateBound(p1, p2), sym, lvl, StructuralType.Beam
                    )
                    vigas.append(inst.Id.IntegerValue)
                    y += paso_m
                x += paso_m

        t.Commit()

OUT = f"{len(vigas)} vigas {ancho_cm:.0f}x{alto_cm:.0f}cm creadas"
'''


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> list[Path]:
    """Genera ``04_estructura.dyn`` con columnas y vigas predimensionadas.

    Returns:
        Lista con el Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    res = predimensionar(params)

    # Secciones del piso base (mayor carga)
    col_base = res.columnas[0] if res.columnas else None
    viga_base = res.vigas[0] if res.vigas else None
    lado_col_cm  = round(col_base.lado_m * 100)  if col_base  else 25
    alto_viga_cm = round(viga_base.alto_m * 100) if viga_base else 50
    ancho_viga_cm = round(viga_base.ancho_m * 100) if viga_base else 25

    nombres = nombres_tipos(params)

    s = DynScript("04_estructura", "Crea columnas y vigas de H° A° según predimensionado CIRSOC 201-2005.")

    # --- Columnas ---
    cb_col_frente = s.add_code_block(str(params.frente),          label="frente_m",    col=0, row=0)
    cb_col_fondo  = s.add_code_block(str(params.fondo),           label="fondo_m",     col=0, row=1)
    cb_col_lado   = s.add_code_block(str(lado_col_cm),            label="lado_col_cm", col=0, row=2)
    cb_col_pisos  = s.add_code_block(str(params.pisos_tipo),      label="pisos_tipo",  col=0, row=3)
    cb_col_nombre = s.add_code_block(f'"{nombres["columna"]}"',   label="nombre_col",  col=0, row=4)

    py_col = s.add_python_node(_CODE_COLUMNAS, n_inputs=5, label="Crear Columnas", col=1, row=0)
    s.connect(cb_col_frente,  py_col, to_input=0)
    s.connect(cb_col_fondo,   py_col, to_input=1)
    s.connect(cb_col_lado,    py_col, to_input=2)
    s.connect(cb_col_pisos,   py_col, to_input=3)
    s.connect(cb_col_nombre,  py_col, to_input=4)

    w_col = s.add_watch(label="Columnas", col=2, row=0)
    s.connect(py_col, w_col)

    # --- Vigas ---
    cb_viga_frente = s.add_code_block(str(params.frente),         label="frente_m",     col=0, row=6)
    cb_viga_fondo  = s.add_code_block(str(params.fondo),          label="fondo_m",      col=0, row=7)
    cb_viga_ancho  = s.add_code_block(str(ancho_viga_cm),         label="ancho_viga_cm",col=0, row=8)
    cb_viga_alto   = s.add_code_block(str(alto_viga_cm),          label="alto_viga_cm", col=0, row=9)
    cb_viga_pisos  = s.add_code_block(str(params.pisos_tipo),     label="pisos_tipo",   col=0, row=10)
    cb_viga_nombre = s.add_code_block(f'"{nombres["viga"]}"',     label="nombre_viga",  col=0, row=11)

    py_viga = s.add_python_node(_CODE_VIGAS, n_inputs=6, label="Crear Vigas", col=1, row=6)
    s.connect(cb_viga_frente,  py_viga, to_input=0)
    s.connect(cb_viga_fondo,   py_viga, to_input=1)
    s.connect(cb_viga_ancho,   py_viga, to_input=2)
    s.connect(cb_viga_alto,    py_viga, to_input=3)
    s.connect(cb_viga_pisos,   py_viga, to_input=4)
    s.connect(cb_viga_nombre,  py_viga, to_input=5)

    w_viga = s.add_watch(label="Vigas", col=2, row=6)
    s.connect(py_viga, w_viga)

    return [s.save(output_dir / "04_estructura.dyn")]
