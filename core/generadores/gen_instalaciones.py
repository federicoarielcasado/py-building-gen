"""Generador del script Dynamo 07_instalaciones_mep.dyn.

Crea espacios MEP (Spaces) y zonas de instalaciones por nivel.
Es un script base — las redes de tuberías y conductos se completan
manualmente en Revit MEP o en un script posterior más detallado.

Orden de ejecución: 7 de 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

_CODE_MEP_SPACES = '''\
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from Autodesk.Revit.DB import (
    Level, XYZ, FilteredElementCollector,
    Transaction, UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Mechanical import Space

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

pisos_tipo = int(IN[0])
frente_m   = float(IN[1])
fondo_m    = float(IN[2])
inst_san   = bool(IN[3])
inst_elec  = bool(IN[4])
inst_gas   = bool(IN[5])
inst_inc   = bool(IN[6])
inst_term  = bool(IN[7])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_levels_tipo():
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return [l for l in levels if l.Name.startswith("P") and l.Name[1:].isdigit()]

spaces_creados = []

with Transaction(doc, "py-building-gen: Espacios MEP") as t:
    t.Start()

    for lvl in get_levels_tipo():
        # Espacio central de servicios (shaft de instalaciones)
        pt = XYZ(m_to_ft(frente_m * 0.5), m_to_ft(fondo_m * 0.5), lvl.Elevation + 0.1)
        try:
            sp = Space(doc, lvl, pt)
            sp.Number = lvl.Name
            sp.LookupParameter("Name") and sp.LookupParameter("Name").Set(f"Zona MEP {lvl.Name}")
            spaces_creados.append({"nivel": lvl.Name, "id": sp.Id.IntegerValue})
        except Exception as e:
            spaces_creados.append({"nivel": lvl.Name, "error": str(e)})

    t.Commit()

instalaciones_activas = []
if inst_san:  instalaciones_activas.append("Sanitaria")
if inst_elec: instalaciones_activas.append("Eléctrica")
if inst_gas:  instalaciones_activas.append("Gas")
if inst_inc:  instalaciones_activas.append("Incendio")
if inst_term: instalaciones_activas.append("Termomecánica")

OUT = {
    "spaces": spaces_creados,
    "instalaciones_a_modelar": instalaciones_activas,
    "nota": (
        "Espacios MEP creados por nivel. "
        "Completar redes de tuberías y conductos manualmente en Revit MEP."
    ),
}
'''

_CODE_MEP_SISTEMAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    MEPSystemType, FilteredElementCollector,
    Transaction, BuiltInCategory,
)
from Autodesk.Revit.DB.Plumbing import PipingSystemType
from Autodesk.Revit.DB.Mechanical import MechanicalSystemType

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

inst_san  = bool(IN[0])
inst_elec = bool(IN[1])
inst_gas  = bool(IN[2])
inst_inc  = bool(IN[3])
inst_term = bool(IN[4])

sistemas = []

def listar_sistemas(cls, nombre_sistema):
    col = FilteredElementCollector(doc).OfClass(cls).ToElements()
    return [{"sistema": nombre_sistema, "tipo": s.Name} for s in col]

if inst_san or inst_inc:
    sistemas += listar_sistemas(PipingSystemType, "Plomería / Incendio")
if inst_term:
    sistemas += listar_sistemas(MechanicalSystemType, "Termomecánica")

OUT = sistemas if sistemas else ["Sin sistemas MEP definidos en la plantilla"]
'''


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> list[Path]:
    """Genera ``07_instalaciones_mep.dyn``.

    Returns:
        Lista con el Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    s = DynScript(
        "07_instalaciones_mep",
        "Crea espacios MEP por nivel e inventaría sistemas disponibles en la plantilla.",
    )

    # Nodo 1: Espacios MEP por nivel
    s.add_code_block(str(params.pisos_tipo),                           label="pisos_tipo", col=0, row=0)
    s.add_code_block(str(params.frente),                               label="frente_m",   col=0, row=1)
    s.add_code_block(str(params.fondo),                                label="fondo_m",    col=0, row=2)
    s.add_code_block(str(params.instalacion_sanitaria).lower(),        label="inst_san",   col=0, row=3)
    s.add_code_block(str(params.instalacion_electrica).lower(),        label="inst_elec",  col=0, row=4)
    s.add_code_block(str(params.instalacion_gas).lower(),              label="inst_gas",   col=0, row=5)
    s.add_code_block(str(params.instalacion_incendio).lower(),         label="inst_inc",   col=0, row=6)
    s.add_code_block(str(params.instalacion_termomecanica).lower(),    label="inst_term",  col=0, row=7)

    py_spaces = s.add_python_node(_CODE_MEP_SPACES, n_inputs=8, label="Espacios MEP", col=1, row=0)
    cbs = [n for n in s._nodes if n is not py_spaces]
    for i, cb in enumerate(cbs):
        s.connect(cb, py_spaces, to_input=i)

    w_spaces = s.add_watch(label="Espacios MEP", col=2, row=0)
    s.connect(py_spaces, w_spaces)

    # Nodo 2: Inventario de sistemas MEP disponibles en la plantilla
    s.add_code_block(str(params.instalacion_sanitaria).lower(),     label="inst_san",  col=0, row=10)
    s.add_code_block(str(params.instalacion_electrica).lower(),     label="inst_elec", col=0, row=11)
    s.add_code_block(str(params.instalacion_gas).lower(),           label="inst_gas",  col=0, row=12)
    s.add_code_block(str(params.instalacion_incendio).lower(),      label="inst_inc",  col=0, row=13)
    s.add_code_block(str(params.instalacion_termomecanica).lower(), label="inst_term", col=0, row=14)

    py_sis = s.add_python_node(_CODE_MEP_SISTEMAS, n_inputs=5, label="Sistemas MEP", col=1, row=10)
    all_cbs = [n for n in s._nodes if hasattr(n, 'output_port_id') and n is not py_spaces and n is not py_sis]
    sis_cbs = all_cbs[-5:]
    for i, cb in enumerate(sis_cbs):
        s.connect(cb, py_sis, to_input=i)

    w_sis = s.add_watch(label="Sistemas disponibles", col=2, row=10)
    s.connect(py_sis, w_sis)

    return [s.save(output_dir / "07_instalaciones_mep.dyn")]
