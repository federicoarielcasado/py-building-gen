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
tipologias_str    = _si(IN[6])   # "2amb:1,3amb:1" (quote-free para Code Block)
cant_escaleras    = _ii(IN[7])
cant_ascensores   = _ii(IN[8])
nombre_muro_ext   = _si(IN[9])   # "Muro exterior - 200mm"
nombre_tabique    = _si(IN[10])  # "Tabique interior - 100mm"
nombre_cortafuego = _si(IN[11])  # "Muro cortafuego - 200mm"

# Tipología por departamento (aplanada, izquierda a derecha).
# Formato quote-free "tipo:cant,tipo:cant" — DesignScript no soporta comillas
# escapadas en Code Blocks de forma confiable (bugs Dynamo #7425/#7781/#9117).
apts = []
for _par in tipologias_str.split(","):
    _par = _par.strip()
    if not _par:
        continue
    _tipo, _, _cant = _par.partition(":")
    _tipo = _tipo.strip() or "2amb"
    try:
        _n = int(_cant)
    except Exception:
        _n = 1
    for _ in range(_n):
        apts.append(_tipo)

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
    """Contorno de la losa como un único loop contra-horario.

    El núcleo (escalera + ascensor) está contra la medianera de fondo, así que su
    borde trasero coincide con la arista trasera de la losa. Un loop interior que
    comparte esa arista NO es un hueco válido (Revit: "curve loops intersect").
    Por eso el contorno se recorta en U alrededor del shaft en vez de perforarlo.
    """
    F  = m_to_ft(frente_m)
    D  = m_to_ft(fondo_m)

    # Recorte en U sólo si el shaft existe y queda holgura a ambos lados.
    margen = m_to_ft(0.02)
    x0 = m_to_ft(x_nucleo)
    x1 = m_to_ft(x_nucleo + ancho_nucleo)
    yn = m_to_ft(y_nucleo)
    notch = ancho_nucleo > 0.1 and x0 > margen and x1 < F - margen

    if notch:
        # CCW: perímetro con entrante rectangular en el borde de fondo.
        pts = [
            XYZ(0,  0,  0),
            XYZ(F,  0,  0),
            XYZ(F,  D,  0),
            XYZ(x1, D,  0),
            XYZ(x1, yn, 0),
            XYZ(x0, yn, 0),
            XYZ(x0, D,  0),
            XYZ(0,  D,  0),
        ]
    else:
        pts = [XYZ(0, 0, 0), XYZ(F, 0, 0), XYZ(F, D, 0), XYZ(0, D, 0)]

    loop = CurveLoop()
    n = len(pts)
    for i in range(n):
        loop.Append(Line.CreateBound(pts[i], pts[(i+1) % n]))

    return [loop]

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
tipologias_str  = _si(IN[5])   # "2amb:1,3amb:1" (quote-free para Code Block)
cant_escaleras  = _ii(IN[6])
cant_ascensores = _ii(IN[7])

apts = []
for _par in tipologias_str.split(","):
    _par = _par.strip()
    if not _par:
        continue
    _tipo, _, _cant = _par.partition(":")
    _tipo = _tipo.strip() or "2amb"
    try:
        _n = int(_cant)
    except Exception:
        _n = 1
    for _ in range(_n):
        apts.append(_tipo)

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
    # Z absoluto = elevación del nivel + offset (sill). Sin sumar lvl.Elevation la
    # abertura cae en z absoluto: en pisos altos queda FUERA del muro ("No es
    # posible cortar del muro") y se apila con las de los demás pisos en el mismo
    # punto ("ejemplares idénticos"). lvl.Elevation ya está en pies.
    pt = XYZ(m_to_ft(x), m_to_ft(y), lvl.Elevation + m_to_ft(z))
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
        # PB: puerta de acceso al edificio. frente/2 cae sobre una divisoria
        # cuando hay un número par de deptos → la corremos al centro del 1er depto.
        x_acc = frente_m / 2.0
        if _n_apts > 1 and _n_apts % 2 == 0:
            x_acc = apt_ancho * 0.5
        if sym_p and w_frente:
            inst = place(sym_p, w_frente, lvl, x_acc, 0.0)
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

        # ── 1+2. Ventanas de fachada (living + dormitorios) ───────────────
        # Se reparten en slots NO solapados: 1 living + n_dorms ventanas, cada
        # una centrada en su slot con un gap. Dos huecos que se intersecan en el
        # mismo muro disparan "No es posible cortar del muro", así que el ancho
        # se acota al slot disponible en lugar de usar posiciones fijas.
        n_dorms = {"1amb":0,"estudio":0,"2amb":1,"3amb":2,"4amb":3,"duplex":3}.get(tipo, 1)
        if sym_v and w_frente:
            GAP_W    = 0.30   # m — separación entre borde de ventana y borde de slot
            # Margen contra los muros divisorios/medianeras del apt. Debe cubrir
            # media pared (cortafuego 200mm) + jamba para no caer en la unión de
            # muros ("Conflictos de inserción con muro unido" / "No es posible
            # cortar del muro").
            MARGEN_A = 0.45
            n_win    = 1 + n_dorms
            slot     = (apt_ancho - 2 * MARGEN_A) / n_win
            for k in range(n_win):
                cx = x0 + MARGEN_A + slot * (k + 0.5)
                if k == 0:
                    ancho_w, alto_w, tag = min(2.40, slot - GAP_W), 1.50, "ventana_living"
                else:
                    ancho_w, alto_w, tag = min(1.20, slot - GAP_W), 1.20, "ventana_dorm%d" % k
                if ancho_w < 0.40:        # slot demasiado angosto para una ventana
                    continue
                inst = place(sym_v, w_frente, lvl, cx, 0.0, 0.90)
                if inst:
                    set_size(inst, ancho_w, alto_w)
                    aberturas.append({"nivel": nombre, "tipo": tag, "id": inst.Id.Value})

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
    Opening, CurveArray,
    IFailuresPreprocessor, FailureProcessingResult,
)
from Autodesk.Revit.DB.Architecture import (
    Stairs, StairsEditScope, StairsRun, StairsType,
    StairsRunJustification,
)

# Preprocesador de fallos requerido por StairsEditScope.Commit (IFailuresPreprocessor).
# Continúa ante warnings (p.ej. escalones fuera de rango), evita diálogos modales.
class _StairFailures(IFailuresPreprocessor):
    def PreprocessFailures(self, failuresAccessor):
        return FailureProcessingResult.Continue
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
            # Riser count y elevaciones derivados de la altura REAL del tramo
            # (PB→P01 usa altura_pb; el resto altura_tipo). lvl.Elevation ya está en pies.
            h_seg_ft = lvl_top.Elevation - lvl_bot.Elevation
            n_seg = max(2, int(round(h_seg_ft / m_to_ft(0.175))))
            if n_seg % 2 != 0:
                n_seg += 1                       # par → dos tramos iguales
            z_base = lvl_bot.Elevation           # base de la escalera (pies, modelo)
            z_mid  = z_base + h_seg_ft / 2.0     # nivel del descanso intermedio

            scope = StairsEditScope(doc, f"Esc{i_esc+1}_{niveles[idx+1]}")
            try:
                # Start crea una escalera vacía con tipo por defecto y devuelve su Id
                stair_id = scope.Start(lvl_bot.Id, lvl_top.Id)
                # Crear los tramos dentro de una Transaction abierta en el scope
                with Transaction(doc, "py-building-gen: Tramos escalera") as tr:
                    tr.Start()
                    stair_elem = doc.GetElement(stair_id)
                    stair_elem.DesiredRisersNumber = n_seg
                    # Tramo 1 — arranca en la base del tramo (Z = z_base)
                    StairsRun.CreateStraightRun(doc, stair_id,
                        Line.CreateBound(XYZ(m_to_ft(x_cen), m_to_ft(y_r1_ini), z_base),
                                         XYZ(m_to_ft(x_cen), m_to_ft(y_r1_fin), z_base)),
                        StairsRunJustification.Center)
                    # Tramo 2 — arranca en el descanso (Z = z_mid)
                    StairsRun.CreateStraightRun(doc, stair_id,
                        Line.CreateBound(XYZ(m_to_ft(x_cen), m_to_ft(y_r2_ini), z_mid),
                                         XYZ(m_to_ft(x_cen), m_to_ft(y_r2_fin), z_mid)),
                        StairsRunJustification.Center)
                    tr.Commit()
                scope.Commit(_StairFailures())
                escaleras.append({"tipo": "escalera_real", "nivel": niveles[idx+1],
                                   "id": stair_id.Value, "risers": n_seg,
                                   "huella_m": round(huella_m, 3)})
            except Exception as e:
                # Cancelar el scope si quedó abierto (idempotente bajo try/except)
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
    nombres = nombres_tipos(params)

    # Formato quote-free para Code Block DesignScript: "2amb:1,3amb:1"
    tipologias_str = ",".join(
        f"{t.tipo}:{t.cantidad}" for t in params.mix_tipologias
    )

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
    cb_tipol   = s.add_code_block(f'"{tipologias_str}"',     label="tipologias",       col=0, row=6)
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
    nombres = nombres_tipos(params)
    # Formato quote-free para Code Block DesignScript: "2amb:1,3amb:1"
    tipologias_str = ",".join(
        f"{t.tipo}:{t.cantidad}" for t in params.mix_tipologias
    )

    s = DynScript(
        "05_aberturas",
        "Coloca ventanas de living y dormitorios en fachada, puertas de acceso a deptos y puertas interiores.",
    )
    cb_frente  = s.add_code_block(str(params.frente),          label="frente_m",         col=0, row=0)
    cb_fondo   = s.add_code_block(str(params.fondo),           label="fondo_m",          col=0, row=1)
    cb_alt_t   = s.add_code_block(str(params.altura_tipo),     label="altura_tipo_m",    col=0, row=2)
    cb_pisos   = s.add_code_block(str(params.pisos_tipo),      label="pisos_tipo",       col=0, row=3)
    cb_ndepto  = s.add_code_block(str(params.cant_depto_tipo), label="cant_depto_tipo",  col=0, row=4)
    cb_tipol   = s.add_code_block(f'"{tipologias_str}"',       label="tipologias",       col=0, row=5)
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
