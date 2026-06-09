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
import json
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Wall, WallType, Level, Line, XYZ,
    FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m          = _fi(IN[0])
fondo_m           = _fi(IN[1])
altura_pb         = _fi(IN[2])
altura_tipo       = _fi(IN[3])
pisos_tipo        = _ii(IN[4])
cant_depto_tipo   = _ii(IN[5])
tipologias_json   = _si(IN[6])   # [{"tipo":"2amb","cantidad":1}, ...]
cant_escaleras    = _ii(IN[7])
cant_ascensores   = _ii(IN[8])
nombre_muro_ext   = _si(IN[9])   # "Muro exterior - 200mm"
nombre_tabique    = _si(IN[10])  # "Tabique interior - 100mm"
nombre_cortafuego = _si(IN[11])  # "Muro cortafuego - 200mm"

tipologias_raw = json.loads(tipologias_json)

# Tipología por departamento (aplanada, en orden de izquierda a derecha)
apts = []
for t_item in tipologias_raw:
    for _ in range(int(t_item.get("cantidad", 1))):
        apts.append(t_item.get("tipo", "2amb"))

# ── Constantes normativa CABA ─────────────────────────────────────────────────
ESC_ANCHO    = 3.00   # m — caja escalera
ESC_FONDO    = 5.50   # m — profundidad del núcleo
ASC_ANCHO    = 2.00   # m — caja ascensor
PASILLO_PROF = 1.20   # m — pasillo común mínimo (Art. 4.8 CABA)

# ── Geometría derivada ────────────────────────────────────────────────────────
_n_apts      = max(cant_depto_tipo, 1)
ancho_nucleo = cant_escaleras * ESC_ANCHO + cant_ascensores * ASC_ANCHO
x_nucleo     = (frente_m - ancho_nucleo) / 2.0
y_nucleo     = fondo_m - ESC_FONDO        # frente del shaft (y positivo = hacia atrás)
y_pasillo    = y_nucleo - PASILLO_PROF    # límite depto / pasillo
apt_ancho    = frente_m / _n_apts

# Proporciones internas por tipología (fracción del fondo útil)
_PROP_LIVING = {                          # fin de zona living (0 = sin separación)
    "1amb": 0.00, "estudio": 0.00,
    "2amb": 0.40, "3amb": 0.38, "4amb": 0.35, "duplex": 0.35,
}
_PROP_SERV = {                            # inicio de zona servicio (cocina + baños)
    "1amb": 0.65, "estudio": 0.70,
    "2amb": 0.70, "3amb": 0.68, "4amb": 0.65, "duplex": 0.65,
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_wall_type(nombre_exacto, fallback_kw):
    tipos = FilteredElementCollector(doc).OfClass(WallType).ToElements()
    match = next((wt for wt in tipos if wt.Name == nombre_exacto), None)
    if match:
        return match
    return next((wt for wt in tipos if fallback_kw.lower() in wt.Name.lower()), tipos[0])

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

def make_wall(lvl, x1, y1, x2, y2, h_m, wt):
    """Crea un muro Wall; retorna None si la longitud es prácticamente cero."""
    p1 = XYZ(m_to_ft(x1), m_to_ft(y1), 0)
    p2 = XYZ(m_to_ft(x2), m_to_ft(y2), 0)
    if p1.DistanceTo(p2) < 1e-3:
        return None
    return Wall.Create(doc, Line.CreateBound(p1, p2), wt.Id, lvl.Id, m_to_ft(h_m), 0, False, False)

# ── Segmentos por zona ────────────────────────────────────────────────────────
wt_ext = get_wall_type(nombre_muro_ext,    "200")
wt_tab = get_wall_type(nombre_tabique,     "100")
wt_cf  = get_wall_type(nombre_cortafuego,  "cortafuego")

def segs_perimetro():
    """4 muros exteriores del edificio."""
    return [
        (0,        0,       frente_m, 0,       wt_ext),
        (frente_m, 0,       frente_m, fondo_m, wt_ext),
        (frente_m, fondo_m, 0,        fondo_m, wt_ext),
        (0,        fondo_m, 0,        0,       wt_ext),
    ]

def segs_nucleo():
    """Paredes del núcleo de escalera + ascensor (shaft)."""
    x0 = x_nucleo
    x1 = x_nucleo + ancho_nucleo
    segs = []
    # Frente del shaft (cara al pasillo)
    segs.append((x0, y_nucleo, x1, y_nucleo, wt_ext))
    # Laterales del shaft (sólo si no coinciden con medianeras)
    if x0 > 0.02:
        segs.append((x0, y_nucleo, x0, fondo_m, wt_ext))
    if x1 < frente_m - 0.02:
        segs.append((x1, y_nucleo, x1, fondo_m, wt_ext))
    # División entre escalera y ascensor
    if cant_escaleras > 0 and cant_ascensores > 0:
        x_div = x_nucleo + cant_escaleras * ESC_ANCHO
        segs.append((x_div, y_nucleo, x_div, fondo_m, wt_ext))
    return segs

def segs_pasillo():
    """Muro separando los departamentos del pasillo común."""
    return [(0, y_pasillo, frente_m, y_pasillo, wt_tab)]

def segs_divisorias():
    """Muros cortafuego verticales entre departamentos (REI-120, CABA Art. 6.1)."""
    segs = []
    for i in range(1, _n_apts):
        x = apt_ancho * i
        segs.append((x, 0, x, y_pasillo, wt_cf))
    return segs

def segs_internos_apt(apt_idx):
    """Tabiques internos de un departamento según su tipología."""
    if apt_idx >= len(apts):
        return []
    tipo = apts[apt_idx]
    x0 = apt_ancho * apt_idx
    x1 = x0 + apt_ancho

    pct_living = _PROP_LIVING.get(tipo, _PROP_LIVING["2amb"])
    pct_serv   = _PROP_SERV.get(tipo, _PROP_SERV["2amb"])
    y_living   = y_pasillo * pct_living   # 0 → sin muro living/dorm
    y_serv     = y_pasillo * pct_serv

    segs = []

    if tipo in ("1amb", "estudio"):
        # Un solo ambiente + zona servicio al fondo
        segs.append((x0, y_serv, x1, y_serv, wt_tab))
        x_cx = x0 + apt_ancho * 0.55
        segs.append((x_cx, y_serv, x_cx, y_pasillo, wt_tab))

    elif tipo == "2amb":
        # Living | Dormitorio | Servicio
        segs.append((x0, y_living, x1, y_living, wt_tab))
        segs.append((x0, y_serv,   x1, y_serv,   wt_tab))
        x_cx = x0 + apt_ancho * 0.55
        segs.append((x_cx, y_serv, x_cx, y_pasillo, wt_tab))

    elif tipo == "3amb":
        # Living | Dorm1 + Dorm2 | Servicio
        segs.append((x0,              y_living, x1, y_living, wt_tab))
        segs.append((x0 + apt_ancho * 0.50, y_living,
                     x0 + apt_ancho * 0.50, y_serv,   wt_tab))
        segs.append((x0, y_serv, x1, y_serv, wt_tab))
        x_cx = x0 + apt_ancho * 0.55
        segs.append((x_cx, y_serv, x_cx, y_pasillo, wt_tab))

    elif tipo in ("4amb", "duplex"):
        # Living | Dorm1 + Dorm2 + Dorm3 | Servicio
        segs.append((x0, y_living, x1, y_living, wt_tab))
        segs.append((x0 + apt_ancho * 0.33, y_living,
                     x0 + apt_ancho * 0.33, y_serv,   wt_tab))
        segs.append((x0 + apt_ancho * 0.67, y_living,
                     x0 + apt_ancho * 0.67, y_serv,   wt_tab))
        segs.append((x0, y_serv, x1, y_serv, wt_tab))
        x_cx = x0 + apt_ancho * 0.55
        segs.append((x_cx, y_serv, x_cx, y_pasillo, wt_tab))

    return segs

# ── Crear muros por nivel ─────────────────────────────────────────────────────
muros_creados = []

def crear_nivel(nombre_nivel, altura_m, es_pb=False):
    lvl = get_level(nombre_nivel)
    todos = list(segs_perimetro()) + list(segs_nucleo()) + list(segs_pasillo())
    if not es_pb:
        todos.extend(segs_divisorias())
        for i in range(_n_apts):
            todos.extend(segs_internos_apt(i))
    for x1, y1, x2, y2, wt in todos:
        w = make_wall(lvl, x1, y1, x2, y2, altura_m, wt)
        if w:
            muros_creados.append({"nivel": nombre_nivel, "id": w.Id.Value})

with Transaction(doc, "py-building-gen: Muros v2") as t:
    t.Start()
    crear_nivel("PB", altura_pb, es_pb=True)
    for i in range(1, pisos_tipo + 1):
        crear_nivel(f"P{i:02d}", altura_tipo)
    t.Commit()

OUT = {"total": len(muros_creados), "detalle": muros_creados}
'''

# ---------------------------------------------------------------------------
# 03 — Losas
# ---------------------------------------------------------------------------

_CODE_LOSAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Floor, FloorType, Level, CurveLoop, Line, XYZ,
    FilteredElementCollector, ElementCategoryFilter,
    BuiltInCategory, Transaction,
    UnitUtils, UnitTypeId,
)
import System
from System.Collections.Generic import List as NetList
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m        = _fi(IN[0])
fondo_m         = _fi(IN[1])
pisos_tipo      = _ii(IN[2])
tiene_azotea    = bool(IN[3])
espesor_cm      = _fi(IN[4])
nombre_losa     = _si(IN[5])
nombre_losa_azo = _si(IN[6])
cant_escaleras  = _ii(IN[7])
cant_ascensores = _ii(IN[8])

# ── Shaft geometry (same constants as Script 02) ──────────────────────────────
ESC_ANCHO = 3.00; ESC_FONDO = 5.50; ASC_ANCHO = 2.00
ancho_nucleo = cant_escaleras * ESC_ANCHO + cant_ascensores * ASC_ANCHO
x_nucleo     = (frente_m - ancho_nucleo) / 2.0
y_nucleo     = fondo_m - ESC_FONDO

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_floor_type(nombre_exacto):
    cat_filter = ElementCategoryFilter(BuiltInCategory.OST_Floors)
    tipos = (FilteredElementCollector(doc)
             .OfClass(FloorType)
             .WherePasses(cat_filter)
             .ToElements())
    match = next((t for t in tipos if t.Name == nombre_exacto), None)
    if match:
        return match
    _kw = ("concrete", "hormigon", "hormigón", "ha ", "losa")
    match = next((t for t in tipos if any(k in t.Name.lower() for k in _kw)), None)
    return match or tipos[0]

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    match = next((l for l in levels if l.Name == nombre), None)
    return match or sorted(levels, key=lambda l: l.Elevation)[0]

def curve_loops_losa():
    """Contorno exterior + hueco de shaft (contra-horario + horario)."""
    # Outer boundary — counter-clockwise
    outer = CurveLoop()
    pts_out = [
        XYZ(m_to_ft(0),        m_to_ft(0),       0),
        XYZ(m_to_ft(frente_m), m_to_ft(0),       0),
        XYZ(m_to_ft(frente_m), m_to_ft(fondo_m), 0),
        XYZ(m_to_ft(0),        m_to_ft(fondo_m), 0),
    ]
    for i in range(4):
        outer.Append(Line.CreateBound(pts_out[i], pts_out[(i+1)%4]))

    loops = [outer]

    # Shaft hole — clockwise (inner loop)
    if ancho_nucleo > 0.1:
        x0 = m_to_ft(x_nucleo)
        x1 = m_to_ft(x_nucleo + ancho_nucleo)
        y0 = m_to_ft(y_nucleo)
        y1 = m_to_ft(fondo_m)
        shaft = CurveLoop()
        pts_sh = [XYZ(x0,y0,0), XYZ(x0,y1,0), XYZ(x1,y1,0), XYZ(x1,y0,0)]
        for i in range(4):
            shaft.Append(Line.CreateBound(pts_sh[i], pts_sh[(i+1)%4]))
        loops.append(shaft)

    return loops

ft_tipo = get_floor_type(nombre_losa)
ft_azo  = get_floor_type(nombre_losa_azo)
losas_creadas = []

with Transaction(doc, "py-building-gen: Losas v2") as t:
    t.Start()
    for i in range(1, pisos_tipo + 1):
        nom = f"P{i:02d}"
        lvl = get_level(nom)
        losa = Floor.Create(doc, NetList[CurveLoop](curve_loops_losa()), ft_tipo.Id, lvl.Id)
        losas_creadas.append({"nivel": nom, "id": losa.Id.Value})
    if tiene_azotea:
        lvl = get_level("AZO")
        losa = Floor.Create(doc, NetList[CurveLoop](curve_loops_losa()), ft_azo.Id, lvl.Id)
        losas_creadas.append({"nivel": "AZO", "id": losa.Id.Value})
    t.Commit()

OUT = {"total": len(losas_creadas), "detalle": losas_creadas}
'''

# ---------------------------------------------------------------------------
# 05 — Aberturas
# ---------------------------------------------------------------------------

_CODE_ABERTURAS = '''\
import clr
import json
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FamilySymbol, Wall, Level,
    FilteredElementCollector, BuiltInCategory,
    Transaction, XYZ, UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Structure import StructuralType as ST
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m        = _fi(IN[0])
fondo_m         = _fi(IN[1])
altura_tipo     = _fi(IN[2])
pisos_tipo      = _ii(IN[3])
cant_depto_tipo = _ii(IN[4])
tipologias_json = _si(IN[5])
cant_escaleras  = _ii(IN[6])
cant_ascensores = _ii(IN[7])

tipologias_raw = json.loads(tipologias_json)
apts = []
for t_item in tipologias_raw:
    for _ in range(int(t_item.get("cantidad", 1))):
        apts.append(t_item.get("tipo", "2amb"))

# ── Layout geometry (same constants as Script 02) ─────────────────────────────
ESC_ANCHO = 3.00; ESC_FONDO = 5.50; ASC_ANCHO = 2.00; PASILLO_PROF = 1.20
_n_apts      = max(cant_depto_tipo, 1)
ancho_nucleo = cant_escaleras * ESC_ANCHO + cant_ascensores * ASC_ANCHO
y_nucleo     = fondo_m - ESC_FONDO
y_pasillo    = y_nucleo - PASILLO_PROF
apt_ancho    = frente_m / _n_apts

_PROP_LIVING = {"1amb":0.00,"estudio":0.00,"2amb":0.40,"3amb":0.38,"4amb":0.35,"duplex":0.35}

# ── Helpers ───────────────────────────────────────────────────────────────────
def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def ft_to_m(ft):
    return UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Meters)

def get_sym(categoria, keywords):
    col = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(categoria).ToElements()
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in keywords)), None)
    return match or (col[0] if col else None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None)

def find_wall_at_y(lvl_id, target_y, tol=0.40):
    """Primer muro horizontal (paralelo a X) con ambos extremos a y ≈ target_y."""
    for w in FilteredElementCollector(doc).OfClass(Wall).ToElements():
        if w.LevelId != lvl_id:
            continue
        loc = w.Location
        if not hasattr(loc, "Curve"):
            continue
        c = loc.Curve
        y1 = ft_to_m(c.GetEndPoint(0).Y)
        y2 = ft_to_m(c.GetEndPoint(1).Y)
        if abs(y1 - target_y) < tol and abs(y2 - target_y) < tol:
            return w
    return None

def set_size(inst, ancho_m, alto_m):
    for name in ("Width", "Ancho", "w", "b"):
        p = inst.LookupParameter(name)
        if p and not p.IsReadOnly:
            try: p.Set(m_to_ft(ancho_m)); break
            except Exception: pass
    for name in ("Height", "Alto", "h", "Height 1"):
        p = inst.LookupParameter(name)
        if p and not p.IsReadOnly:
            try: p.Set(m_to_ft(alto_m)); break
            except Exception: pass

def place(sym, wall, lvl, x, y, z=0.0):
    if wall is None or sym is None:
        return None
    pt = XYZ(m_to_ft(x), m_to_ft(y), m_to_ft(z))
    try:
        return doc.Create.NewFamilyInstance(pt, sym, wall, lvl, ST.NonStructural)
    except Exception:
        return None

# ── Symbols ───────────────────────────────────────────────────────────────────
sym_p = get_sym(BuiltInCategory.OST_Doors,   ("door","puerta","single","simple","entry"))
sym_v = get_sym(BuiltInCategory.OST_Windows, ("window","ventana","fixed","fija","casement"))

aberturas = []

def crear_nivel(nombre, es_pb=False):
    lvl = get_level(nombre)
    if not lvl:
        return
    w_frente  = find_wall_at_y(lvl.Id, 0.0)
    w_pasillo = find_wall_at_y(lvl.Id, y_pasillo)

    if es_pb:
        # PB: puerta de acceso al edificio (centrada en el frente)
        if sym_p and w_frente:
            inst = place(sym_p, w_frente, lvl, frente_m / 2, 0.0)
            if inst:
                set_size(inst, 1.20, 2.40)
                aberturas.append({"nivel": nombre, "tipo": "puerta_acceso_edificio", "id": inst.Id.Value})
        return

    for apt_idx in range(_n_apts):
        tipo  = apts[apt_idx] if apt_idx < len(apts) else "2amb"
        x0    = apt_ancho * apt_idx
        x_cen = x0 + apt_ancho / 2.0
        pct_l = _PROP_LIVING.get(tipo, 0.40)
        y_l   = y_pasillo * pct_l   # y-coord del muro living/dorm (0 si no hay)

        # ── 1. Ventana de living — fachada principal, zona izq del apt ────
        if sym_v and w_frente:
            x_vl  = x0 + apt_ancho * 0.30
            ancho_v = min(apt_ancho * 0.55, 2.40)
            inst = place(sym_v, w_frente, lvl, x_vl, 0.0, 0.90)
            if inst:
                set_size(inst, ancho_v, 1.50)
                aberturas.append({"nivel": nombre, "tipo": "ventana_living", "id": inst.Id.Value})

        # ── 2. Ventanas de dormitorios — fachada principal, zona der del apt
        n_dorms = {"1amb":0,"estudio":0,"2amb":1,"3amb":2,"4amb":3,"duplex":3}.get(tipo, 1)
        if sym_v and w_frente and n_dorms > 0:
            x_start = x0 + apt_ancho * 0.60
            paso_d  = apt_ancho * 0.35 / max(n_dorms, 1)
            for d in range(n_dorms):
                x_vd = x_start + paso_d * d
                if x_vd < x0 + apt_ancho - 0.30:
                    inst = place(sym_v, w_frente, lvl, x_vd, 0.0, 0.90)
                    if inst:
                        set_size(inst, 1.20, 1.20)
                        aberturas.append({"nivel": nombre, "tipo": f"ventana_dorm{d+1}", "id": inst.Id.Value})

        # ── 3. Puerta de entrada al depto — muro del pasillo ─────────────
        if sym_p and w_pasillo:
            inst = place(sym_p, w_pasillo, lvl, x_cen, y_pasillo)
            if inst:
                set_size(inst, 0.90, 2.10)
                aberturas.append({"nivel": nombre, "tipo": "puerta_entrada_depto", "id": inst.Id.Value})

        # ── 4. Puertas interiores — muro separador living/dormitorios ─────
        if sym_p and y_l > 0.50:
            w_sep = find_wall_at_y(lvl.Id, y_l)
            if w_sep:
                inst = place(sym_p, w_sep, lvl, x0 + apt_ancho * 0.25, y_l)
                if inst:
                    set_size(inst, 0.80, 2.10)
                    aberturas.append({"nivel": nombre, "tipo": "puerta_int_living_dorm", "id": inst.Id.Value})

with Transaction(doc, "py-building-gen: Aberturas v2") as t:
    t.Start()
    for sym in [sym_p, sym_v]:
        if sym and not sym.IsActive:
            sym.Activate()
    crear_nivel("PB", es_pb=True)
    for i in range(1, pisos_tipo + 1):
        crear_nivel(f"P{i:02d}")
    t.Commit()

OUT = {"total": len(aberturas), "detalle": aberturas}
'''

# ---------------------------------------------------------------------------
# 06 — Escaleras y ascensores
# ---------------------------------------------------------------------------

_CODE_CIRC = '''\
import clr
import math
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Level, Line, XYZ, FilteredElementCollector,
    Transaction, UnitUtils, UnitTypeId,
    Opening, CurveArray, FailureHandlingOptions,
)
from Autodesk.Revit.DB.Architecture import (
    Stairs, StairsEditScope, StairsRun, StairsType,
    StairsRunJustification,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m    = _fi(IN[0])
fondo_m     = _fi(IN[1])
pisos_tipo  = _ii(IN[2])
cant_esc    = _ii(IN[3])
cant_asc    = _ii(IN[4])
altura_pb   = _fi(IN[5])
altura_tipo = _fi(IN[6])

# ── Misma geometría que Scripts 02/03/05 ──────────────────────────────────────
ESC_ANCHO = 3.00; ESC_FONDO = 5.50; ASC_ANCHO = 2.00
ancho_nucleo = cant_esc * ESC_ANCHO + cant_asc * ASC_ANCHO
x_nucleo     = (frente_m - ancho_nucleo) / 2.0
y_nucleo     = fondo_m - ESC_FONDO

# ── Geometría de la escalera por piso ────────────────────────────────────────
# 2 tramos rectos + descanso intermedio, dentro del shaft ESC_ANCHO × ESC_FONDO
MARGEN     = 0.10  # m — separación de muros de shaft
DESCANSO   = 1.10  # m — profundidad de descanso (mínimo CABA)
n_risers   = math.ceil(altura_tipo / 0.175)   # contrahuella ~17.5cm → 16 para 2.80m
n_por_tramo = n_risers // 2                    # 8 por tramo
run_len    = (ESC_FONDO - 2 * MARGEN - DESCANSO) / 2   # 2.10m
huella_m   = run_len / n_por_tramo              # ~0.2625m > 25cm CABA ✓

y_r1_ini = y_nucleo + MARGEN
y_r1_fin = y_r1_ini + run_len
y_r2_ini = y_r1_fin + DESCANSO
y_r2_fin = y_r2_ini + run_len

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None) \
           or sorted(levels, key=lambda l: l.Elevation)[0]

def get_levels_sorted():
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return sorted(levels, key=lambda l: l.Elevation)

def get_stair_type():
    col = FilteredElementCollector(doc).OfClass(StairsType).ToElements()
    return col[0] if col else None

def rect_opening_shaft(x0, y0, ancho, largo):
    arr = CurveArray()
    pts = [
        XYZ(m_to_ft(x0),       m_to_ft(y0),       0),
        XYZ(m_to_ft(x0+ancho), m_to_ft(y0),       0),
        XYZ(m_to_ft(x0+ancho), m_to_ft(y0+largo), 0),
        XYZ(m_to_ft(x0),       m_to_ft(y0+largo), 0),
    ]
    for k in range(4):
        arr.Append(Line.CreateBound(pts[k], pts[(k+1)%4]))
    return arr

# ── Escaleras ────────────────────────────────────────────────────────────────
stair_type = get_stair_type()
escaleras  = []
niveles    = ["PB"] + [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]

if stair_type:
    for i_esc in range(cant_esc):
        x_cen = x_nucleo + i_esc * ESC_ANCHO + ESC_ANCHO / 2.0
        for idx in range(len(niveles) - 1):
            lvl_bot = get_level(niveles[idx])
            lvl_top = get_level(niveles[idx + 1])
            if lvl_bot is None or lvl_top is None:
                continue
            scope = None
            try:
                scope = StairsEditScope(doc, f"Esc{i_esc+1}_{niveles[idx+1]}")
                stair_id = Stairs.Create(doc, stair_type.Id, lvl_bot.Id, lvl_top.Id)
                elem = doc.GetElement(stair_id)
                elem.DesiredRisersNumber = n_risers
                # Tramo 1
                StairsRun.CreateStraightRun(doc, stair_id,
                    Line.CreateBound(XYZ(m_to_ft(x_cen), m_to_ft(y_r1_ini), 0),
                                     XYZ(m_to_ft(x_cen), m_to_ft(y_r1_fin), 0)),
                    StairsRunJustification.Center)
                # Tramo 2
                StairsRun.CreateStraightRun(doc, stair_id,
                    Line.CreateBound(XYZ(m_to_ft(x_cen), m_to_ft(y_r2_ini), 0),
                                     XYZ(m_to_ft(x_cen), m_to_ft(y_r2_fin), 0)),
                    StairsRunJustification.Center)
                scope.Commit(FailureHandlingOptions())
                scope = None
                escaleras.append({"tipo": "escalera_real", "nivel": niveles[idx+1],
                                   "id": stair_id.Value, "risers": n_risers,
                                   "huella_m": round(huella_m, 3)})
            except Exception as e:
                if scope is not None:
                    try: scope.Cancel()
                    except Exception: pass
                escaleras.append({"tipo": "error", "nivel": niveles[idx+1], "msg": str(e)})
else:
    # Fallback: shaft openings si no hay StairsType en el template
    all_lvls = get_levels_sorted()
    lvl_pb   = next((l for l in all_lvls if l.Name == "PB"), all_lvls[0])
    lvl_top  = all_lvls[-1]
    with Transaction(doc, "py-building-gen: Escalera shaft fallback") as t:
        t.Start()
        for i in range(cant_esc):
            x0 = x_nucleo + i * ESC_ANCHO
            arr = rect_opening_shaft(x0, y_nucleo, ESC_ANCHO, ESC_FONDO)
            op = doc.Create.NewOpening(lvl_pb, lvl_top, arr)
            escaleras.append({"tipo": "shaft_fallback", "id": op.Id.Value})
        t.Commit()

# ── Ascensores: shaft opening (apropiado para cabina de ascensor) ─────────────
ascensores = []
all_lvls = get_levels_sorted()
lvl_pb   = next((l for l in all_lvls if l.Name == "PB"), all_lvls[0])
lvl_top  = all_lvls[-1]

with Transaction(doc, "py-building-gen: Shaft ascensores") as t:
    t.Start()
    for i in range(cant_asc):
        x0 = x_nucleo + cant_esc * ESC_ANCHO + i * ASC_ANCHO
        arr = rect_opening_shaft(x0, y_nucleo, ASC_ANCHO, ESC_FONDO)
        op = doc.Create.NewOpening(lvl_pb, lvl_top, arr)
        ascensores.append({"tipo": f"ascensor_{i+1}", "id": op.Id.Value})
    t.Commit()

OUT = {
    "escaleras": escaleras,
    "ascensores": ascensores,
    "escalera_tipo": stair_type.Name if stair_type else "fallback_shaft",
    "config": {"n_escalones": n_risers, "n_por_tramo": n_por_tramo,
                "huella_m": round(huella_m, 3), "descanso_m": DESCANSO},
}
'''


def _script_muros(params: "ParametrosEdificio", output_dir: Path) -> Path:
    import json as _json
    nombres = nombres_tipos(params)

    tipologias_list = [
        {"tipo": t.tipo, "cantidad": t.cantidad}
        for t in params.mix_tipologias
    ]
    tipologias_json = _json.dumps(tipologias_list, ensure_ascii=False)

    s = DynScript(
        "02_muros_perimetrales",
        "Crea muros exteriores, núcleo, pasillo, divisorias y tabiques internos por nivel.",
    )
    cb_frente  = s.add_code_block(str(params.frente),        label="frente_m",         col=0, row=0)
    cb_fondo   = s.add_code_block(str(params.fondo),         label="fondo_m",          col=0, row=1)
    cb_alt_pb  = s.add_code_block(str(params.altura_pb),     label="altura_pb_m",      col=0, row=2)
    cb_alt_t   = s.add_code_block(str(params.altura_tipo),   label="altura_tipo_m",    col=0, row=3)
    cb_pisos   = s.add_code_block(str(params.pisos_tipo),    label="pisos_tipo",       col=0, row=4)
    cb_ndepto  = s.add_code_block(str(params.cant_depto_tipo), label="cant_depto_tipo", col=0, row=5)
    cb_tipol   = s.add_code_block(f'"{tipologias_json}"',    label="tipologias_json",  col=0, row=6)
    cb_nesc    = s.add_code_block(str(params.cant_cajas_escalera), label="cant_escaleras", col=0, row=7)
    cb_nasc    = s.add_code_block(str(params.cant_ascensores),     label="cant_ascensores", col=0, row=8)
    cb_ext     = s.add_code_block(f'"{nombres["muro_ext"]}"',   label="nombre_muro_ext",   col=0, row=9)
    cb_tab     = s.add_code_block(f'"{nombres["tabique"]}"',     label="nombre_tabique",    col=0, row=10)
    cb_cf      = s.add_code_block(f'"{nombres["cortafuego"]}"',  label="nombre_cortafuego", col=0, row=11)

    cbs = [cb_frente, cb_fondo, cb_alt_pb, cb_alt_t, cb_pisos,
           cb_ndepto, cb_tipol, cb_nesc, cb_nasc, cb_ext, cb_tab, cb_cf]
    py = s.add_python_node(_CODE_MUROS, n_inputs=len(cbs), label="Crear Muros v2", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Muros creados", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "02_muros_perimetrales.dyn")


def _script_losas(params: "ParametrosEdificio", output_dir: Path) -> Path:
    from core.predimensionado import predimensionar
    res = predimensionar(params)
    espesor_cm = res.losas[0].espesor_cm if res.losas else 20.0
    nombres = nombres_tipos(params)

    s = DynScript("03_losas", "Crea losas HA por nivel con hueco de shaft para escalera y ascensor.")
    cb_frente   = s.add_code_block(str(params.frente),               label="frente_m",       col=0, row=0)
    cb_fondo    = s.add_code_block(str(params.fondo),                label="fondo_m",        col=0, row=1)
    cb_pisos    = s.add_code_block(str(params.pisos_tipo),           label="pisos_tipo",     col=0, row=2)
    cb_azotea   = s.add_code_block(str(params.tiene_azotea).lower(), label="tiene_azotea",   col=0, row=3)
    cb_esp      = s.add_code_block(str(espesor_cm),                  label="espesor_cm",     col=0, row=4)
    cb_losa     = s.add_code_block(f'"{nombres["losa"]}"',           label="nombre_losa",    col=0, row=5)
    cb_losa_azo = s.add_code_block(f'"{nombres["losa_azo"]}"',       label="nombre_losa_azo",col=0, row=6)
    cb_nesc     = s.add_code_block(str(params.cant_cajas_escalera),  label="cant_escaleras", col=0, row=7)
    cb_nasc     = s.add_code_block(str(params.cant_ascensores),      label="cant_ascensores",col=0, row=8)

    cbs = [cb_frente, cb_fondo, cb_pisos, cb_azotea, cb_esp, cb_losa, cb_losa_azo, cb_nesc, cb_nasc]
    py = s.add_python_node(_CODE_LOSAS, n_inputs=len(cbs), label="Crear Losas v2", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Losas creadas", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "03_losas.dyn")


def _script_aberturas(params: "ParametrosEdificio", output_dir: Path) -> Path:
    import json as _json
    nombres = nombres_tipos(params)
    tipologias_list = [
        {"tipo": t.tipo, "cantidad": t.cantidad}
        for t in params.mix_tipologias
    ]
    tipologias_json = _json.dumps(tipologias_list, ensure_ascii=False)

    s = DynScript(
        "05_aberturas",
        "Coloca ventanas de living y dormitorios en fachada, puertas de acceso a deptos y puertas interiores.",
    )
    cb_frente  = s.add_code_block(str(params.frente),          label="frente_m",         col=0, row=0)
    cb_fondo   = s.add_code_block(str(params.fondo),           label="fondo_m",          col=0, row=1)
    cb_alt_t   = s.add_code_block(str(params.altura_tipo),     label="altura_tipo_m",    col=0, row=2)
    cb_pisos   = s.add_code_block(str(params.pisos_tipo),      label="pisos_tipo",       col=0, row=3)
    cb_ndepto  = s.add_code_block(str(params.cant_depto_tipo), label="cant_depto_tipo",  col=0, row=4)
    cb_tipol   = s.add_code_block(f'"{tipologias_json}"',      label="tipologias_json",  col=0, row=5)
    cb_nesc    = s.add_code_block(str(params.cant_cajas_escalera), label="cant_escaleras", col=0, row=6)
    cb_nasc    = s.add_code_block(str(params.cant_ascensores),     label="cant_ascensores", col=0, row=7)

    cbs = [cb_frente, cb_fondo, cb_alt_t, cb_pisos, cb_ndepto, cb_tipol, cb_nesc, cb_nasc]
    py = s.add_python_node(_CODE_ABERTURAS, n_inputs=len(cbs), label="Crear Aberturas v2", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Aberturas creadas", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "05_aberturas.dyn")


def _script_circulacion(params: "ParametrosEdificio", output_dir: Path) -> Path:
    s = DynScript(
        "06_escaleras_ascensores",
        "Crea escaleras reales (StairsEditScope, 2 tramos + descanso, CABA) "
        "y shaft openings para ascensores.",
    )
    cb_frente  = s.add_code_block(str(params.frente),              label="frente_m",    col=0, row=0)
    cb_fondo   = s.add_code_block(str(params.fondo),               label="fondo_m",     col=0, row=1)
    cb_pisos   = s.add_code_block(str(params.pisos_tipo),          label="pisos_tipo",  col=0, row=2)
    cb_nesc    = s.add_code_block(str(params.cant_cajas_escalera), label="cant_esc",    col=0, row=3)
    cb_nasc    = s.add_code_block(str(params.cant_ascensores),     label="cant_asc",    col=0, row=4)
    cb_alt_pb  = s.add_code_block(str(params.altura_pb),           label="altura_pb_m", col=0, row=5)
    cb_alt_t   = s.add_code_block(str(params.altura_tipo),         label="altura_tipo_m",col=0, row=6)

    cbs = [cb_frente, cb_fondo, cb_pisos, cb_nesc, cb_nasc, cb_alt_pb, cb_alt_t]
    py = s.add_python_node(_CODE_CIRC, n_inputs=len(cbs), label="Escaleras y Ascensores", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Circulación creada", col=2, row=0)
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
