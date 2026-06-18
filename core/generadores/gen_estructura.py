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

doc = DocumentManager.Instance.CurrentDBDocument

frente_m        = _fi(IN[0])
fondo_m         = _fi(IN[1])
lado_col_cm     = _fi(IN[2])
pisos_tipo      = _ii(IN[3])
nombre_col_tipo = _si(IN[4])
paso_m          = 5.0

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_all_col_syms():
    return list(FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_StructuralColumns)
           .ToElements())

def get_col_symbol():
    col = get_all_col_syms()
    match = next((s for s in col if s.Name == nombre_col_tipo), None)
    if match:
        return match
    _kw = ("concrete","hormigon","hormigón","ha ","h.a","rectangular")
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in _kw)), None)
    return match or (col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None) \
           or sorted(levels, key=lambda l: l.Elevation)[0]

def set_section(sym, lado_m):
    lado_ft = m_to_ft(lado_m)
    for n in ("b","Ancho","Width","w"):
        p = sym.LookupParameter(n)
        if p and not p.IsReadOnly:
            try: p.Set(lado_ft); break
            except Exception: pass
    for n in ("h","Alto","Depth","d"):
        p = sym.LookupParameter(n)
        if p and not p.IsReadOnly:
            try: p.Set(lado_ft); break
            except Exception: pass

# ── Secciones: inferior (pisos bajos) y superior (pisos altos, −5cm) ─────────
# Cada grupo usa su propio FamilySymbol para que la sección no se pise.
lado_inf_m = lado_col_cm / 100.0
lado_sup_m = max(0.25, lado_inf_m - 0.05)
piso_corte = pisos_tipo // 2 + 1
misma_seccion = (lado_inf_m == lado_sup_m)

nombre_inf = f"Col HA {lado_inf_m*100:.0f}x{lado_inf_m*100:.0f}cm"
nombre_sup = f"Col HA {lado_sup_m*100:.0f}x{lado_sup_m*100:.0f}cm"

sym_base = get_col_symbol()
columnas  = []

if sym_base:
    with Transaction(doc, "py-building-gen: Columnas v2") as t:
        t.Start()

        todos = get_all_col_syms()

        # Tipo inferior
        sym_inf = next((s for s in todos if s.Name == nombre_inf), None)
        if sym_inf is None:
            sym_inf = sym_base.Duplicate(nombre_inf)
            set_section(sym_inf, lado_inf_m)
        if not sym_inf.IsActive:
            sym_inf.Activate()

        # Tipo superior (solo si difiere del inferior)
        if misma_seccion:
            sym_sup = sym_inf
        else:
            sym_sup = next((s for s in todos if s.Name == nombre_sup), None)
            if sym_sup is None:
                sym_sup = sym_base.Duplicate(nombre_sup)
                set_section(sym_sup, lado_sup_m)
            if not sym_sup.IsActive:
                sym_sup.Activate()

        for idx_piso, nombre_nivel in enumerate(
            ["PB"] + [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]
        ):
            lvl = get_level(nombre_nivel)
            sym_local = sym_sup if idx_piso >= piso_corte else sym_inf
            x = 0.0
            while x <= frente_m + 0.001:
                y = 0.0
                while y <= fondo_m + 0.001:
                    pt = XYZ(m_to_ft(x), m_to_ft(y), 0)
                    inst = doc.Create.NewFamilyInstance(pt, sym_local, lvl, StructuralType.Column)
                    columnas.append(inst.Id.Value)
                    y += paso_m
                x += paso_m

        t.Commit()

OUT = {
    "total": len(columnas),
    "seccion_inferior": f"{lado_inf_m*100:.0f}x{lado_inf_m*100:.0f}cm (pisos 1-{piso_corte-1})",
    "seccion_superior": f"{lado_sup_m*100:.0f}x{lado_sup_m*100:.0f}cm (pisos {piso_corte}-{pisos_tipo})",
}
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

frente_m        = _fi(IN[0])
fondo_m         = _fi(IN[1])
ancho_cm        = _fi(IN[2])
alto_cm         = _fi(IN[3])
pisos_tipo      = _ii(IN[4])
nombre_viga_tipo = _si(IN[5])   # "Viga HA 45x85cm"  (creado por 00_familias.dyn)
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
            # La curva de una viga vive en coordenadas del modelo: el Level solo
            # fija el "Nivel de referencia", NO la altura física. Sin este z las
            # vigas de todos los pisos se apilan en z=0 → "ejemplares idénticos".
            z = lvl.Elevation

            # Vigas en dirección X (paralelas al frente) — una por eje Y
            y = 0.0
            while y <= fondo_m + 0.001:
                x = 0.0
                while x + paso_m <= frente_m + 0.001:
                    p1 = XYZ(m_to_ft(x),        m_to_ft(y), z)
                    p2 = XYZ(m_to_ft(x + paso_m), m_to_ft(y), z)
                    inst = doc.Create.NewFamilyInstance(
                        Line.CreateBound(p1, p2), sym, lvl, StructuralType.Beam
                    )
                    vigas.append(inst.Id.Value)
                    x += paso_m
                y += paso_m

            # Vigas en dirección Y (paralelas al fondo)
            x = 0.0
            while x <= frente_m + 0.001:
                y = 0.0
                while y + paso_m <= fondo_m + 0.001:
                    p1 = XYZ(m_to_ft(x), m_to_ft(y),        z)
                    p2 = XYZ(m_to_ft(x), m_to_ft(y + paso_m), z)
                    inst = doc.Create.NewFamilyInstance(
                        Line.CreateBound(p1, p2), sym, lvl, StructuralType.Beam
                    )
                    vigas.append(inst.Id.Value)
                    y += paso_m
                x += paso_m

        t.Commit()

OUT = {"total_vigas": len(vigas), "seccion": f"{ancho_cm:.0f}x{alto_cm:.0f}cm"}
'''

# ---------------------------------------------------------------------------
# Vigas de fundación — conectan zapatas en la grilla (nivel de cimentación)
# ---------------------------------------------------------------------------

_CODE_VIGAS_FUND = '''\
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

doc = DocumentManager.Instance.CurrentDBDocument

frente_m        = _fi(IN[0])
fondo_m         = _fi(IN[1])
ancho_vf_cm     = _fi(IN[2])   # sección viga de fundación (CIRSOC: ≥ 30×60cm)
alto_vf_cm      = _fi(IN[3])
tiene_subsuelo  = bool(IN[4])
nombre_viga_tipo = _si(IN[5])
paso_m          = 5.0
Z_OFFSET        = -0.30           # m — centro viga a 30cm bajo nivel de fundación

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_beam_symbol():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_StructuralFraming)
           .ToElements())
    match = next((s for s in col if s.Name == nombre_viga_tipo), None)
    if match: return match
    _kw = ("concrete","hormigon","hormigón","ha ","h.a","rectangular")
    return next((s for s in col if any(k in s.FamilyName.lower() for k in _kw)), col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None) \
           or sorted(levels, key=lambda l: l.Elevation)[0]

sym = get_beam_symbol()
vigas_fund = []

if sym:
    try:
        sym.LookupParameter("b").Set(m_to_ft(ancho_vf_cm / 100))
        sym.LookupParameter("h").Set(m_to_ft(alto_vf_cm  / 100))
    except Exception:
        pass
    if not sym.IsActive:
        sym.Activate()

    lvl_fund = get_level("SS01" if tiene_subsuelo else "PB")

    with Transaction(doc, "py-building-gen: Vigas de fundación") as t:
        t.Start()
        z = lvl_fund.Elevation + m_to_ft(Z_OFFSET)

        # Dirección X (paralelas al frente)
        y = 0.0
        while y <= fondo_m + 0.001:
            x = 0.0
            while x + paso_m <= frente_m + 0.001:
                p1 = XYZ(m_to_ft(x),          m_to_ft(y), z)
                p2 = XYZ(m_to_ft(x + paso_m), m_to_ft(y), z)
                inst = doc.Create.NewFamilyInstance(Line.CreateBound(p1, p2), sym, lvl_fund, StructuralType.Beam)
                vigas_fund.append(inst.Id.Value)
                x += paso_m
            y += paso_m

        # Dirección Y (paralelas al fondo)
        x = 0.0
        while x <= frente_m + 0.001:
            y = 0.0
            while y + paso_m <= fondo_m + 0.001:
                p1 = XYZ(m_to_ft(x), m_to_ft(y),          z)
                p2 = XYZ(m_to_ft(x), m_to_ft(y + paso_m), z)
                inst = doc.Create.NewFamilyInstance(Line.CreateBound(p1, p2), sym, lvl_fund, StructuralType.Beam)
                vigas_fund.append(inst.Id.Value)
                y += paso_m
            x += paso_m

        t.Commit()

OUT = {"total_vf": len(vigas_fund), "nivel": "SS01" if tiene_subsuelo else "PB",
       "seccion": f"{ancho_vf_cm:.0f}x{alto_vf_cm:.0f}cm"}
'''

# ---------------------------------------------------------------------------
# Zapatas aisladas bajo columnas (nivel de fundación)
# ---------------------------------------------------------------------------

_CODE_ZAPATAS = '''\
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

doc = DocumentManager.Instance.CurrentDBDocument

frente_m       = _fi(IN[0])
fondo_m        = _fi(IN[1])
lado_zapata_cm = _fi(IN[2])   # lado de la zapata cuadrada (predimensionado)
altura_pb      = _fi(IN[3])
tiene_subsuelo = bool(IN[4])
nombre_zapata  = _si(IN[5], "")   # tipo exacto creado por 00_familias.dyn
paso_m         = 5.0

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_foundation_sym():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_StructuralFoundation)
           .ToElements())
    # 1° intento: tipo exacto resuelto/creado por 00_familias.dyn
    match = next((s for s in col if s.Name == nombre_zapata), None)
    if match:
        return match
    _kw = ("pad","isolated","zapata","footing","aislada","foundation")
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in _kw)), None)
    return match or (col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None) \
           or sorted(levels, key=lambda l: l.Elevation)[0]

sym = get_foundation_sym()
zapatas = []
nom_fund = "SS01" if tiene_subsuelo else "PB"   # nivel de fundación (def. siempre)

if sym:
    # Tamaño de zapata
    lado_ft = m_to_ft(lado_zapata_cm / 100.0)
    for n in ("Width","Ancho","b","w","Length","Largo"):
        p = sym.LookupParameter(n)
        if p and not p.IsReadOnly:
            try: p.Set(lado_ft)
            except Exception: pass
    for n in ("Thickness","Espesor","h","d","Depth"):
        p = sym.LookupParameter(n)
        if p and not p.IsReadOnly:
            try: p.Set(m_to_ft(0.50)); break   # espesor zapata: 0.50m
            except Exception: pass
    if not sym.IsActive:
        sym.Activate()

    # Nivel de fundación: PB si no hay subsuelo, SS01 si hay
    lvl_fund = get_level(nom_fund)

    with Transaction(doc, "py-building-gen: Zapatas") as t:
        t.Start()
        x = 0.0
        while x <= frente_m + 0.001:
            y = 0.0
            while y <= fondo_m + 0.001:
                pt = XYZ(m_to_ft(x), m_to_ft(y), lvl_fund.Elevation)
                inst = doc.Create.NewFamilyInstance(pt, sym, lvl_fund, StructuralType.Footing)
                zapatas.append(inst.Id.Value)
                y += paso_m
            x += paso_m
        t.Commit()

if sym:
    OUT = {
        "total": len(zapatas),
        "lado_cm": lado_zapata_cm,
        "nivel": nom_fund,
        "familia": sym.FamilyName,
    }
else:
    OUT = {
        "total": 0,
        "resultado": "No se encontro familia de fundacion (OST_StructuralFoundation) cargada en el modelo.",
        "accion_requerida": (
            "Cargar una familia de zapata/base estructural (p.ej. "
            "'Base estructural rectangular' o 'Footing-Rectangular') desde "
            "Insertar -> Cargar familia, luego volver a correr 04_estructura.dyn."
        ),
    }
'''


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> list[Path]:
    """Genera ``04_estructura.dyn`` con columnas, vigas y zapatas predimensionadas.

    Returns:
        Lista con el Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    res = predimensionar(params)

    col_base  = res.columnas[0] if res.columnas else None
    viga_base = res.vigas[0]    if res.vigas    else None
    zapata_base = getattr(res, "zapata", None)

    lado_col_cm   = round(col_base.lado_m  * 100) if col_base  else 25
    alto_viga_cm  = round(viga_base.alto_m  * 100) if viga_base else 50
    ancho_viga_cm = round(viga_base.ancho_m * 100) if viga_base else 25
    lado_zap_cm   = round(zapata_base.lado_m * 100) if zapata_base and zapata_base.lado_m else 120

    nombres = nombres_tipos(params)

    s = DynScript(
        "04_estructura",
        "Crea columnas (con reducción de sección), vigas y zapatas aisladas según CIRSOC 201-2005.",
    )

    # --- Columnas ---
    cb_col_frente = s.add_code_block(str(params.frente),        label="frente_m",    col=0, row=0)
    cb_col_fondo  = s.add_code_block(str(params.fondo),         label="fondo_m",     col=0, row=1)
    cb_col_lado   = s.add_code_block(str(lado_col_cm),          label="lado_col_cm", col=0, row=2)
    cb_col_pisos  = s.add_code_block(str(params.pisos_tipo),    label="pisos_tipo",  col=0, row=3)
    cb_col_nombre = s.add_code_block(f'"{nombres["columna"]}"', label="nombre_col",  col=0, row=4)

    py_col = s.add_python_node(_CODE_COLUMNAS, n_inputs=5, label="Crear Columnas v2", col=1, row=0)
    for i, cb in enumerate([cb_col_frente, cb_col_fondo, cb_col_lado, cb_col_pisos, cb_col_nombre]):
        s.connect(cb, py_col, to_input=i)
    w_col = s.add_watch(label="Columnas", col=2, row=0)
    s.connect(py_col, w_col)

    # --- Vigas ---
    cb_viga_frente = s.add_code_block(str(params.frente),       label="frente_m",      col=0, row=6)
    cb_viga_fondo  = s.add_code_block(str(params.fondo),        label="fondo_m",       col=0, row=7)
    cb_viga_ancho  = s.add_code_block(str(ancho_viga_cm),       label="ancho_viga_cm", col=0, row=8)
    cb_viga_alto   = s.add_code_block(str(alto_viga_cm),        label="alto_viga_cm",  col=0, row=9)
    cb_viga_pisos  = s.add_code_block(str(params.pisos_tipo),   label="pisos_tipo",    col=0, row=10)
    cb_viga_nombre = s.add_code_block(f'"{nombres["viga"]}"',   label="nombre_viga",   col=0, row=11)

    py_viga = s.add_python_node(_CODE_VIGAS, n_inputs=6, label="Crear Vigas", col=1, row=6)
    for i, cb in enumerate([cb_viga_frente, cb_viga_fondo, cb_viga_ancho,
                             cb_viga_alto, cb_viga_pisos, cb_viga_nombre]):
        s.connect(cb, py_viga, to_input=i)
    w_viga = s.add_watch(label="Vigas", col=2, row=6)
    s.connect(py_viga, w_viga)

    # --- Vigas de fundación ---
    ancho_vf_cm = max(30, ancho_viga_cm)
    alto_vf_cm  = max(60, alto_viga_cm)
    cb_vf_frente = s.add_code_block(str(params.frente),                  label="frente_m",      col=0, row=13)
    cb_vf_fondo  = s.add_code_block(str(params.fondo),                   label="fondo_m",       col=0, row=14)
    cb_vf_ancho  = s.add_code_block(str(ancho_vf_cm),                   label="ancho_vf_cm",   col=0, row=15)
    cb_vf_alto   = s.add_code_block(str(alto_vf_cm),                    label="alto_vf_cm",    col=0, row=16)
    cb_vf_sub    = s.add_code_block(str(params.tiene_subsuelo).lower(),  label="tiene_subsuelo",col=0, row=17)
    cb_vf_nombre = s.add_code_block(f'"{nombres["viga"]}"',              label="nombre_viga",   col=0, row=18)

    py_vf = s.add_python_node(_CODE_VIGAS_FUND, n_inputs=6, label="Vigas de Fundación", col=1, row=13)
    for i, cb in enumerate([cb_vf_frente, cb_vf_fondo, cb_vf_ancho, cb_vf_alto, cb_vf_sub, cb_vf_nombre]):
        s.connect(cb, py_vf, to_input=i)
    w_vf = s.add_watch(label="Vigas fundación", col=2, row=13)
    s.connect(py_vf, w_vf)

    # --- Zapatas aisladas ---
    cb_zap_frente = s.add_code_block(str(params.frente),                label="frente_m",       col=0, row=20)
    cb_zap_fondo  = s.add_code_block(str(params.fondo),                 label="fondo_m",        col=0, row=21)
    cb_zap_lado   = s.add_code_block(str(lado_zap_cm),                  label="lado_zapata_cm", col=0, row=22)
    cb_zap_altpb  = s.add_code_block(str(params.altura_pb),             label="altura_pb_m",    col=0, row=23)
    cb_zap_sub    = s.add_code_block(str(params.tiene_subsuelo).lower(), label="tiene_subsuelo", col=0, row=24)
    cb_zap_nombre = s.add_code_block(f'"{nombres["zapata"]}"',           label="nombre_zapata",  col=0, row=25)

    py_zap = s.add_python_node(_CODE_ZAPATAS, n_inputs=6, label="Crear Zapatas", col=1, row=20)
    for i, cb in enumerate([cb_zap_frente, cb_zap_fondo, cb_zap_lado, cb_zap_altpb, cb_zap_sub, cb_zap_nombre]):
        s.connect(cb, py_zap, to_input=i)
    w_zap = s.add_watch(label="Zapatas", col=2, row=20)
    s.connect(py_zap, w_zap)

    return [s.save(output_dir / "04_estructura.dyn")]
