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
pisos_tipo   = int(IN[0])
altura_pb    = float(IN[1])   # metros
altura_tipo  = float(IN[2])   # metros
tiene_sub    = bool(IN[3])
cant_sub     = int(IN[4])
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
clr.AddReference("RevitAPIUI")
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from Autodesk.Revit.DB import (
    Grid, Line, XYZ, Transaction,
    UnitUtils, UnitTypeId,
)
import Autodesk.Revit.DB as DB

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

# --- Parámetros ---
frente_m = float(IN[0])
fondo_m  = float(IN[1])
paso_m   = 5.0          # módulo de grilla estructural (5.00 m típico CABA)

def m_to_ft(m: float) -> float:
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

grillas_creadas = []

with Transaction(doc, "py-building-gen: Grilla") as t:
    t.Start()

    # Ejes verticales (paralelos al fondo, dirección Y) — A, B, C ...
    x = 0.0
    col_idx = 0
    while x <= frente_m + 0.001:
        nombre = chr(ord("A") + col_idx)
        p1 = XYZ(m_to_ft(x), m_to_ft(-1.0), 0)
        p2 = XYZ(m_to_ft(x), m_to_ft(fondo_m + 1.0), 0)
        grid = Grid.Create(doc, Line.CreateBound(p1, p2))
        grid.Name = nombre
        grillas_creadas.append(nombre)
        x += paso_m
        col_idx += 1

    # Ejes horizontales (paralelos al frente, dirección X) — 1, 2, 3 ...
    y = 0.0
    row_idx = 1
    while y <= fondo_m + 0.001:
        nombre = str(row_idx)
        p1 = XYZ(m_to_ft(-1.0), m_to_ft(y), 0)
        p2 = XYZ(m_to_ft(frente_m + 1.0), m_to_ft(y), 0)
        grid = Grid.Create(doc, Line.CreateBound(p1, p2))
        grid.Name = nombre
        grillas_creadas.append(nombre)
        y += paso_m
        row_idx += 1

    t.Commit()

OUT = grillas_creadas
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

    return s.save(output_dir / "01_niveles_grilla.dyn")
