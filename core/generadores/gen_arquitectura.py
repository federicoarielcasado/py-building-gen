"""Generador de scripts Dynamo de arquitectura.

Produce:
  02_muros_perimetrales.dyn  — muros exteriores e interiores por nivel
  03_losas.dyn               — losas por nivel
  05_aberturas.dyn           — puertas y ventanas
  06_escaleras_ascensores.dyn — núcleos de circulación
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript
from core.generadores.gen_familias import nombres_tipos

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

# ---------------------------------------------------------------------------
# 02 — Muros perimetrales
# ---------------------------------------------------------------------------

_CODE_MUROS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Wall, WallType, Level, Line, XYZ,
    FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m        = float(IN[0])
fondo_m         = float(IN[1])
altura_pb       = float(IN[2])
altura_tipo     = float(IN[3])
pisos_tipo      = int(IN[4])
nombre_muro_ext = str(IN[5])   # "Muro exterior - 200mm"  (creado por 00_familias.dyn)
nombre_tabique  = str(IN[6])   # "Tabique interior - 100mm"

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_wall_type(nombre_exacto, fallback_keyword):
    tipos = FilteredElementCollector(doc).OfClass(WallType).ToElements()
    # 1° intento: nombre exacto creado por 00_familias.dyn
    match = next((t for t in tipos if t.Name == nombre_exacto), None)
    if match:
        return match
    # fallback: búsqueda por keyword (si 00_familias no se corrió aún)
    match = next((t for t in tipos if fallback_keyword.lower() in t.Name.lower()), None)
    return match or tipos[0]

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

wt_ext = get_wall_type(nombre_muro_ext, "200")
wt_int = get_wall_type(nombre_tabique,  "100")

muros_creados = []

def crear_muros_nivel(nombre_nivel, altura_m, es_pb):
    lvl = get_level(nombre_nivel)
    h   = m_to_ft(altura_m)
    f   = m_to_ft(frente_m)
    fo  = m_to_ft(fondo_m)

    # Perímetro exterior (4 muros)
    perimetro = [
        (XYZ(0, 0, 0),  XYZ(f, 0, 0)),    # frente
        (XYZ(f, 0, 0),  XYZ(f, fo, 0)),   # derecha
        (XYZ(f, fo, 0), XYZ(0, fo, 0)),   # contrafrente
        (XYZ(0, fo, 0), XYZ(0, 0, 0)),    # izquierda (medianera)
    ]
    for p1, p2 in perimetro:
        w = Wall.Create(doc, Line.CreateBound(p1, p2), wt_ext.Id, lvl.Id, h, 0, False, False)
        muros_creados.append(w.Id.IntegerValue)

    # Tabique de hall central (simplificado: a 1/3 del fondo)
    y_hall = m_to_ft(fondo_m / 3)
    w_hall = Wall.Create(
        doc, Line.CreateBound(XYZ(0, y_hall, 0), XYZ(f, y_hall, 0)),
        wt_int.Id, lvl.Id, h, 0, False, False,
    )
    muros_creados.append(w_hall.Id.IntegerValue)

with Transaction(doc, "py-building-gen: Muros") as t:
    t.Start()
    crear_muros_nivel("PB", altura_pb, es_pb=True)
    for i in range(1, pisos_tipo + 1):
        crear_muros_nivel(f"P{i:02d}", altura_tipo, es_pb=False)
    t.Commit()

OUT = muros_creados
'''

# ---------------------------------------------------------------------------
# 03 — Losas
# ---------------------------------------------------------------------------

_CODE_LOSAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Floor, FloorType, Level, CurveLoop, Line, XYZ,
    FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m      = float(IN[0])
fondo_m       = float(IN[1])
pisos_tipo    = int(IN[2])
tiene_azotea  = bool(IN[3])
espesor_cm    = float(IN[4])
nombre_losa   = str(IN[5])   # "Losa HA H-21 - 30cm"     (creado por 00_familias.dyn)
nombre_losa_azo = str(IN[6]) # "Losa azotea HA H-21 - 30cm"

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_floor_type(nombre_exacto):
    tipos = FilteredElementCollector(doc).OfClass(FloorType).ToElements()
    # 1° intento: nombre exacto creado por 00_familias.dyn
    match = next((t for t in tipos if t.Name == nombre_exacto), None)
    if match:
        return match
    # fallback: búsqueda por keyword
    _kw = ("concrete", "hormigon", "hormigón", "ha ", "losa")
    match = next((t for t in tipos if any(k in t.Name.lower() for k in _kw)), None)
    return match or tipos[0]

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

def contorno_losa():
    loop = CurveLoop()
    pts = [
        XYZ(m_to_ft(0),          m_to_ft(0),          0),
        XYZ(m_to_ft(frente_m),   m_to_ft(0),          0),
        XYZ(m_to_ft(frente_m),   m_to_ft(fondo_m),    0),
        XYZ(m_to_ft(0),          m_to_ft(fondo_m),    0),
    ]
    for i in range(len(pts)):
        loop.Append(Line.CreateBound(pts[i], pts[(i + 1) % len(pts)]))
    return loop

ft_tipo = get_floor_type(nombre_losa)
ft_azo  = get_floor_type(nombre_losa_azo)
losas_creadas = []

with Transaction(doc, "py-building-gen: Losas") as t:
    t.Start()
    for i in range(1, pisos_tipo + 1):
        nom = f"P{i:02d}"
        lvl = get_level(nom)
        losa = Floor.Create(doc, [contorno_losa()], ft_tipo.Id, lvl.Id)
        losas_creadas.append({"nivel": nom, "id": losa.Id.IntegerValue})
    if tiene_azotea:
        lvl = get_level("AZO")
        losa = Floor.Create(doc, [contorno_losa()], ft_azo.Id, lvl.Id)
        losas_creadas.append({"nivel": "AZO", "id": losa.Id.IntegerValue})
    t.Commit()

OUT = losas_creadas
'''

# ---------------------------------------------------------------------------
# 05 — Aberturas
# ---------------------------------------------------------------------------

_CODE_ABERTURAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FamilySymbol, FamilyInstance, Wall, Level,
    FilteredElementCollector, BuiltInCategory,
    Transaction, StructuralType, XYZ,
    UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Structure import StructuralType as ST

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m   = float(IN[0])
pisos_tipo = int(IN[1])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

_KW_PUERTAS  = ("door", "puerta", "single", "simple")
_KW_VENTANAS = ("window", "ventana", "fixed", "fija", "doble", "double")

def get_symbol(categoria, keyword):
    col = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(categoria).ToElements()
    # Buscar con keyword original y sus equivalentes en español/inglés
    kw_map = {
        "door":   _KW_PUERTAS,
        "window": _KW_VENTANAS,
    }
    keywords = kw_map.get(keyword.lower(), (keyword.lower(),))
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in keywords)), None)
    return match or (col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

def get_muro_frente(nivel_id):
    col = FilteredElementCollector(doc).OfClass(Wall).ToElements()
    return next((w for w in col if w.LevelId == nivel_id), None)

sym_puerta  = get_symbol(BuiltInCategory.OST_Doors,   "door")
sym_ventana = get_symbol(BuiltInCategory.OST_Windows, "window")

aberturas = []

with Transaction(doc, "py-building-gen: Aberturas") as t:
    t.Start()

    for sym in [sym_puerta, sym_ventana]:
        if sym and not sym.IsActive:
            sym.Activate()

    # Puerta de entrada en PB
    if sym_puerta:
        lvl_pb = get_level("PB")
        muro_pb = get_muro_frente(lvl_pb.Id)
        if muro_pb:
            mid = XYZ(m_to_ft(frente_m / 2), 0, 0)
            inst = doc.Create.NewFamilyInstance(mid, sym_puerta, muro_pb, lvl_pb, ST.NonStructural)
            aberturas.append({"tipo": "puerta_entrada", "id": inst.Id.IntegerValue})

    # Ventanas en pisos tipo (una por fachada principal)
    if sym_ventana:
        for i in range(1, pisos_tipo + 1):
            lvl = get_level(f"P{i:02d}")
            muro = get_muro_frente(lvl.Id)
            if muro:
                pos = XYZ(m_to_ft(frente_m / 2), 0, m_to_ft(0.90))
                inst = doc.Create.NewFamilyInstance(pos, sym_ventana, muro, lvl, ST.NonStructural)
                aberturas.append({"tipo": f"ventana_P{i:02d}", "id": inst.Id.IntegerValue})

    t.Commit()

OUT = aberturas
'''

# ---------------------------------------------------------------------------
# 06 — Escaleras y ascensores
# ---------------------------------------------------------------------------

_CODE_CIRC = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Opening, CurveArray, Level, XYZ, Line,
    FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m      = float(IN[0])
fondo_m       = float(IN[1])
pisos_tipo    = int(IN[2])
cant_asc      = int(IN[3])
cant_esc      = int(IN[4])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_levels():
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return sorted(levels, key=lambda l: l.Elevation)

def rect_curve_array(x0, y0, ancho, largo):
    arr = CurveArray()
    pts = [
        XYZ(m_to_ft(x0),         m_to_ft(y0),         0),
        XYZ(m_to_ft(x0 + ancho), m_to_ft(y0),         0),
        XYZ(m_to_ft(x0 + ancho), m_to_ft(y0 + largo), 0),
        XYZ(m_to_ft(x0),         m_to_ft(y0 + largo), 0),
    ]
    for i in range(len(pts)):
        arr.Append(Line.CreateBound(pts[i], pts[(i + 1) % len(pts)]))
    return arr

nucleos = []
levels = get_levels()
lvl_pb = next((l for l in levels if l.Name == "PB"), levels[0])
lvl_techo = levels[-1]

with Transaction(doc, "py-building-gen: Núcleos circulación") as t:
    t.Start()

    # Caja(s) de escalera — esquina posterior derecha del edificio
    for i in range(cant_esc):
        x0 = frente_m - 3.0 - i * 3.5
        arr = rect_curve_array(x0, fondo_m * 0.65, 2.80, 5.50)
        op = doc.Create.NewOpening(lvl_pb, lvl_techo, arr)
        nucleos.append({"tipo": f"escalera_{i+1}", "id": op.Id.IntegerValue})

    # Caja(s) de ascensor — al lado de la escalera
    for i in range(cant_asc):
        x0 = frente_m - 3.0 - cant_esc * 3.5 - i * 2.2
        arr = rect_curve_array(x0, fondo_m * 0.65, 1.80, 2.10)
        op = doc.Create.NewOpening(lvl_pb, lvl_techo, arr)
        nucleos.append({"tipo": f"ascensor_{i+1}", "id": op.Id.IntegerValue})

    t.Commit()

OUT = nucleos
'''


def _script_muros(params: "ParametrosEdificio", output_dir: Path) -> Path:
    nombres = nombres_tipos(params)
    s = DynScript("02_muros_perimetrales", "Crea muros exteriores e interiores por nivel.")
    cb_frente    = s.add_code_block(str(params.frente),      label="frente_m",     col=0, row=0)
    cb_fondo     = s.add_code_block(str(params.fondo),       label="fondo_m",      col=0, row=1)
    cb_alt_pb    = s.add_code_block(str(params.altura_pb),   label="altura_pb_m",  col=0, row=2)
    cb_alt_tipo  = s.add_code_block(str(params.altura_tipo), label="altura_tipo_m",col=0, row=3)
    cb_pisos     = s.add_code_block(str(params.pisos_tipo),  label="pisos_tipo",   col=0, row=4)
    cb_muro_ext  = s.add_code_block(f'"{nombres["muro_ext"]}"', label="nombre_muro_ext", col=0, row=5)
    cb_tabique   = s.add_code_block(f'"{nombres["tabique"]}"',  label="nombre_tabique",  col=0, row=6)

    py = s.add_python_node(_CODE_MUROS, n_inputs=7, label="Crear Muros", col=1, row=0)
    for i, cb in enumerate([cb_frente, cb_fondo, cb_alt_pb, cb_alt_tipo, cb_pisos, cb_muro_ext, cb_tabique]):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Muros creados", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "02_muros_perimetrales.dyn")


def _script_losas(params: "ParametrosEdificio", output_dir: Path) -> Path:
    from core.predimensionado import predimensionar
    res = predimensionar(params)
    espesor_cm = res.losas[0].espesor_cm if res.losas else 20.0
    nombres = nombres_tipos(params)

    s = DynScript("03_losas", "Crea losas de hormigón armado por nivel.")
    cb_frente   = s.add_code_block(str(params.frente),               label="frente_m",       col=0, row=0)
    cb_fondo    = s.add_code_block(str(params.fondo),                label="fondo_m",        col=0, row=1)
    cb_pisos    = s.add_code_block(str(params.pisos_tipo),           label="pisos_tipo",     col=0, row=2)
    cb_azotea   = s.add_code_block(str(params.tiene_azotea).lower(), label="tiene_azotea",   col=0, row=3)
    cb_esp      = s.add_code_block(str(espesor_cm),                  label="espesor_cm",     col=0, row=4)
    cb_losa     = s.add_code_block(f'"{nombres["losa"]}"',           label="nombre_losa",    col=0, row=5)
    cb_losa_azo = s.add_code_block(f'"{nombres["losa_azo"]}"',       label="nombre_losa_azo",col=0, row=6)

    py = s.add_python_node(_CODE_LOSAS, n_inputs=7, label="Crear Losas", col=1, row=0)
    for i, cb in enumerate([cb_frente, cb_fondo, cb_pisos, cb_azotea, cb_esp, cb_losa, cb_losa_azo]):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Losas creadas", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "03_losas.dyn")


def _script_aberturas(params: "ParametrosEdificio", output_dir: Path) -> Path:
    s = DynScript("05_aberturas", "Coloca puertas y ventanas en muros exteriores.")
    s.add_code_block(str(params.frente),      label="frente_m",   col=0, row=0)
    s.add_code_block(str(params.pisos_tipo),  label="pisos_tipo", col=0, row=1)

    py = s.add_python_node(_CODE_ABERTURAS, n_inputs=2, label="Crear Aberturas", col=1, row=0)
    cbs = [n for n in s._nodes if n is not py]
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Aberturas creadas", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "05_aberturas.dyn")


def _script_circulacion(params: "ParametrosEdificio", output_dir: Path) -> Path:
    s = DynScript("06_escaleras_ascensores", "Crea shafts de escaleras y ascensores.")
    s.add_code_block(str(params.frente),               label="frente_m",   col=0, row=0)
    s.add_code_block(str(params.fondo),                label="fondo_m",    col=0, row=1)
    s.add_code_block(str(params.pisos_tipo),           label="pisos_tipo", col=0, row=2)
    s.add_code_block(str(params.cant_ascensores),      label="cant_asc",   col=0, row=3)
    s.add_code_block(str(params.cant_cajas_escalera),  label="cant_esc",   col=0, row=4)

    py = s.add_python_node(_CODE_CIRC, n_inputs=5, label="Crear Circulación", col=1, row=0)
    cbs = [n for n in s._nodes if n is not py]
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Núcleos creados", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "06_escaleras_ascensores.dyn")


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> list[Path]:
    """Genera los scripts Dynamo de arquitectura (02, 03, 05, 06).

    Returns:
        Lista de Path a los archivos .dyn generados.
    """
    output_dir = Path(output_dir)
    return [
        _script_muros(params, output_dir),
        _script_losas(params, output_dir),
        _script_aberturas(params, output_dir),
        _script_circulacion(params, output_dir),
    ]
