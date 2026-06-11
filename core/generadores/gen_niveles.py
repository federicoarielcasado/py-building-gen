"""Generador del script Dynamo 01_niveles_grilla.dyn.

Crea los niveles (Levels) y la grilla estructural (Grids) en Revit
a partir de los parámetros del edificio.

Orden de ejecución: 1 de 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

# Directorio de salida por defecto
_OUTPUT_DIR = Path("output/dynamo")

# ---------------------------------------------------------------------------
# Código Python que se incrusta en el nodo Dynamo
# ---------------------------------------------------------------------------

_CODE_NIVELES = '''\
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from Autodesk.Revit.DB import (
    Level, Transaction, XYZ, Line, Grid,
    UnitUtils, UnitTypeId,
)
import Autodesk.Revit.DB as DB

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument
uidoc = DocumentManager.Instance.CurrentUIDocument

# --- Parámetros desde nodos Code Block ---
pisos_tipo   = _ii(IN[0])
altura_pb    = _fi(IN[1])   # metros
altura_tipo  = _fi(IN[2])   # metros
tiene_sub    = bool(IN[3])
cant_sub     = _ii(IN[4])
tiene_azotea = bool(IN[5])

def m_to_ft(m: float) -> float:
    """Convierte metros a pies (unidad interna de Revit)."""
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

niveles_creados = []

with Transaction(doc, "py-building-gen: Niveles") as t:
    t.Start()

    # Subsuelos (debajo de +-0.00)
    for i in range(cant_sub, 0, -1):
        elev_m = -i * altura_tipo
        nombre = f"SS{i:02d}"
        lvl = Level.Create(doc, m_to_ft(elev_m))
        lvl.Name = nombre
        niveles_creados.append({"nombre": nombre, "elevacion_m": elev_m})

    # Planta baja (±0.00)
    lvl_pb = Level.Create(doc, m_to_ft(0.0))
    lvl_pb.Name = "PB"
    niveles_creados.append({"nombre": "PB", "elevacion_m": 0.0})

    # Pisos tipo
    for i in range(1, pisos_tipo + 1):
        elev_m = altura_pb + (i - 1) * altura_tipo
        nombre = f"P{i:02d}"
        lvl = Level.Create(doc, m_to_ft(elev_m))
        lvl.Name = nombre
        niveles_creados.append({"nombre": nombre, "elevacion_m": elev_m})

    # Azotea
    if tiene_azotea:
        elev_m = altura_pb + pisos_tipo * altura_tipo
        lvl = Level.Create(doc, m_to_ft(elev_m))
        lvl.Name = "AZO"
        niveles_creados.append({"nombre": "AZO", "elevacion_m": elev_m})

    t.Commit()

OUT = niveles_creados
'''

_CODE_GRILLA = '''\
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from Autodesk.Revit.DB import (
    Grid, Line, XYZ, Transaction,
    FilteredElementCollector,
    UnitUtils, UnitTypeId,
)
doc = DocumentManager.Instance.CurrentDBDocument

frente_m = _fi(IN[0])
fondo_m  = _fi(IN[1])
PASO     = 5.0    # m — modulo objetivo entre ejes
MIN_BAY  = 2.5    # m — bahia minima; si el resto es menor, se absorbe

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def ejes(span, paso=PASO, min_bay=MIN_BAY):
    """Posiciones de eje en [0, span]: modulo de 5m + eje de cierre en el borde.

    Siempre incluye 0 y span (medianeras/fachada). Si el ultimo paño quedaria
    mas chico que min_bay, se fusiona con el anterior (evita bahias minusculas).
    """
    if span <= paso + 1e-9:
        return [0.0, round(span, 4)]
    pos = []
    x = 0.0
    while x < span - 1e-6:
        pos.append(round(x, 4))
        x += paso
    resto = span - pos[-1]
    if resto < min_bay and len(pos) >= 2:
        pos.pop()            # absorber: la ultima bahia queda paso+resto
    pos.append(round(span, 4))
    return pos

def es_grid_nuestro(nombre):
    # Ejes de py-building-gen: una sola letra A-Z, o solo digitos
    return (len(nombre) == 1 and nombre.isalpha()) or nombre.isdigit()

xs = ejes(frente_m)   # ejes verticales (A, B, C…) a lo ancho del frente
ys = ejes(fondo_m)    # ejes horizontales (1, 2, 3…) a lo largo del fondo
grillas_creadas = []

with Transaction(doc, "py-building-gen: Grilla") as t:
    t.Start()

    # Idempotencia: borrar ejes previos de py-building-gen y reposicionarlos.
    # (Grid.Create + asignar un nombre ya usado lanza error al re-correr.)
    for g in list(FilteredElementCollector(doc).OfClass(Grid).ToElements()):
        if es_grid_nuestro(g.Name):
            try: doc.Delete(g.Id)
            except Exception: pass

    # Ejes verticales A, B, C … (x constante, corren en Y)
    for i, x in enumerate(xs):
        nombre = chr(ord("A") + i)
        p1 = XYZ(m_to_ft(x), m_to_ft(-1.0), 0)
        p2 = XYZ(m_to_ft(x), m_to_ft(fondo_m + 1.0), 0)
        g = Grid.Create(doc, Line.CreateBound(p1, p2))
        g.Name = nombre
        grillas_creadas.append(nombre)

    # Ejes horizontales 1, 2, 3 … (y constante, corren en X)
    for i, y in enumerate(ys):
        nombre = str(i + 1)
        p1 = XYZ(m_to_ft(-1.0), m_to_ft(y), 0)
        p2 = XYZ(m_to_ft(frente_m + 1.0), m_to_ft(y), 0)
        g = Grid.Create(doc, Line.CreateBound(p1, p2))
        g.Name = nombre
        grillas_creadas.append(nombre)

    t.Commit()

OUT = {
    "ejes": grillas_creadas,
    "total": len(grillas_creadas),
    "frente_m_recibido": frente_m,
    "fondo_m_recibido": fondo_m,
    "x_ejes_m": [round(v, 2) for v in xs],
    "y_ejes_m": [round(v, 2) for v in ys],
}
'''

# ---------------------------------------------------------------------------
# ViewPlan por nivel (disciplinas: arquitectura + estructura + MEP)
# ---------------------------------------------------------------------------

_CODE_VIEW_TEMPLATES = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, ViewFamilyType, ViewFamily, Level,
    FilteredElementCollector, Transaction,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

pisos_tipo   = _ii(IN[0])
tiene_azotea = bool(IN[1])

def get_vft(familia):
    tipos = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
    return next((t for t in tipos if t.ViewFamily == familia), None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None)

vft_arq = get_vft(ViewFamily.FloorPlan)
vft_est = get_vft(ViewFamily.StructuralPlan)   # planta estructural
vft_mep = get_vft(ViewFamily.FloorPlan)         # reutiliza FloorPlan para MEP

niveles = ["PB"] + [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]
if tiene_azotea:
    niveles.append("AZO")

vistas = []

with Transaction(doc, "py-building-gen: Plantas por disciplina") as t:
    t.Start()
    for nom in niveles:
        lvl = get_level(nom)
        if lvl is None:
            continue
        for vft, prefijo in [(vft_arq, "PLANTA"), (vft_est, "EST"), (vft_mep, "MEP")]:
            if vft is None:
                continue
            nombre_vista = f"{prefijo} {nom}"
            # Verificar si ya existe una vista con ese nombre
            existente = next(
                (v for v in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
                 if v.Name == nombre_vista), None
            )
            if existente:
                vistas.append({"nivel": nom, "tipo": prefijo, "id": existente.Id.Value, "nuevo": False})
                continue
            vista = ViewPlan.Create(doc, vft.Id, lvl.Id)
            vista.Name = nombre_vista
            vistas.append({"nivel": nom, "tipo": prefijo, "id": vista.Id.Value, "nuevo": True})
    t.Commit()

OUT = {"total": len(vistas), "detalle": vistas}
'''


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> Path:
    """Genera el script ``01_niveles_grilla.dyn``.

    Args:
        params: Parámetros completos del edificio.
        output_dir: Directorio donde se escribe el archivo .dyn.

    Returns:
        Path al archivo .dyn generado.
    """
    s = DynScript(
        name="01_niveles_grilla",
        description=(
            "Crea Levels y Grids en Revit 2027. "
            "Generado por py-building-gen. Ejecutar primero."
        ),
    )

    # --- Nodos de entrada para el script de Niveles ---
    cb_pisos       = s.add_code_block(str(params.pisos_tipo),    label="pisos_tipo",    col=0, row=0)
    cb_alt_pb      = s.add_code_block(str(params.altura_pb),     label="altura_pb_m",   col=0, row=1)
    cb_alt_tipo    = s.add_code_block(str(params.altura_tipo),   label="altura_tipo_m", col=0, row=2)
    cb_tiene_sub   = s.add_code_block(str(params.tiene_subsuelo).lower(), label="tiene_subsuelo", col=0, row=3)
    cb_cant_sub    = s.add_code_block(str(params.cant_subsuelos), label="cant_subsuelos", col=0, row=4)
    cb_azotea      = s.add_code_block(str(params.tiene_azotea).lower(), label="tiene_azotea", col=0, row=5)

    py_niveles = s.add_python_node(
        code=_CODE_NIVELES,
        n_inputs=6,
        label="Crear Niveles",
        col=1, row=0,
    )
    s.connect(cb_pisos,     py_niveles, to_input=0)
    s.connect(cb_alt_pb,    py_niveles, to_input=1)
    s.connect(cb_alt_tipo,  py_niveles, to_input=2)
    s.connect(cb_tiene_sub, py_niveles, to_input=3)
    s.connect(cb_cant_sub,  py_niveles, to_input=4)
    s.connect(cb_azotea,    py_niveles, to_input=5)

    watch_niv = s.add_watch(label="Niveles creados", col=2, row=0)
    s.connect(py_niveles, watch_niv)

    # --- Nodos de entrada para el script de Grilla ---
    cb_frente = s.add_code_block(str(params.frente), label="frente_m", col=0, row=7)
    cb_fondo  = s.add_code_block(str(params.fondo),  label="fondo_m",  col=0, row=8)

    py_grilla = s.add_python_node(
        code=_CODE_GRILLA,
        n_inputs=2,
        label="Crear Grilla",
        col=1, row=7,
    )
    s.connect(cb_frente, py_grilla, to_input=0)
    s.connect(cb_fondo,  py_grilla, to_input=1)

    watch_grid = s.add_watch(label="Ejes creados", col=2, row=7)
    s.connect(py_grilla, watch_grid)

    # --- Plantas por disciplina (ARQ + EST + MEP) ---
    cb_pisos2  = s.add_code_block(str(params.pisos_tipo),              label="pisos_tipo",    col=0, row=10)
    cb_azotea2 = s.add_code_block(str(params.tiene_azotea).lower(),    label="tiene_azotea",  col=0, row=11)

    py_vistas = s.add_python_node(
        code=_CODE_VIEW_TEMPLATES,
        n_inputs=2,
        label="Plantas por Disciplina",
        col=1, row=10,
    )
    s.connect(cb_pisos2,  py_vistas, to_input=0)
    s.connect(cb_azotea2, py_vistas, to_input=1)

    watch_vistas = s.add_watch(label="Plantas creadas", col=2, row=10)
    s.connect(py_vistas, watch_vistas)

    return s.save(output_dir / "01_niveles_grilla.dyn")
