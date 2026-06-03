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

_CODE_MEP_ARTEFACTOS = '''\
import clr
import json
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Level, XYZ, FamilySymbol,
    FilteredElementCollector, BuiltInCategory,
    Transaction, UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Structure import StructuralType as ST
from Autodesk.Revit.DB.Mechanical import Space
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

pisos_tipo      = _ii(IN[0])
frente_m        = _fi(IN[1])
fondo_m         = _fi(IN[2])
cant_escaleras  = _ii(IN[3])
cant_ascensores = _ii(IN[4])
inst_san        = bool(IN[5])
inst_elec       = bool(IN[6])
inst_inc        = bool(IN[7])

# ── Layout geometry ────────────────────────────────────────────────────────────
ESC_ANCHO = 3.00; ESC_FONDO = 5.50; ASC_ANCHO = 2.00; PASILLO_PROF = 1.20
ancho_nucleo = cant_escaleras * ESC_ANCHO + cant_ascensores * ASC_ANCHO
x_nucleo     = (frente_m - ancho_nucleo) / 2.0
y_nucleo     = fondo_m - ESC_FONDO
y_pasillo    = y_nucleo - PASILLO_PROF
# Matafuego y tablero: contra pared del pasillo, lado izquierdo del núcleo
x_mat = max(0.30, x_nucleo - 0.50)   # 0.50m antes del shaft
y_mat = y_pasillo + 0.60              # en el pasillo, cerca del inicio del shaft

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_levels_tipo():
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return sorted(
        [l for l in levels if l.Name.startswith("P") and l.Name[1:].isdigit()],
        key=lambda l: l.Elevation
    )

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None)

def get_sym(categoria, keywords):
    col = FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(categoria).ToElements()
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in keywords)), None)
    return match or (col[0] if col else None)

# ── Symbols ────────────────────────────────────────────────────────────────────
_KW_MAT  = ("fire","extintor","matafuego","extinguisher","sprinkler")
_KW_TAB  = ("panel","tablero","board","electrical","distribution","cuadro")

sym_mat = get_sym(BuiltInCategory.OST_FireAlarmDevices,   _KW_MAT) or \
          get_sym(BuiltInCategory.OST_GenericModel,        _KW_MAT)
sym_tab = get_sym(BuiltInCategory.OST_ElectricalEquipment, _KW_TAB) or \
          get_sym(BuiltInCategory.OST_GenericModel,         _KW_TAB)

artefactos = []
spaces_creados = []

with Transaction(doc, "py-building-gen: Artefactos MEP v2") as t:
    t.Start()

    # Activar símbolos
    for sym in [sym_mat, sym_tab]:
        if sym and not sym.IsActive:
            sym.Activate()

    for lvl in get_levels_tipo():
        # MEP Space (para análisis de cargas)
        pt_sp = XYZ(m_to_ft(frente_m * 0.5), m_to_ft(fondo_m * 0.5), lvl.Elevation + 0.1)
        try:
            sp = Space(doc, lvl, pt_sp)
            p_name = sp.LookupParameter("Name")
            if p_name:
                p_name.Set(f"Zona MEP {lvl.Name}")
            spaces_creados.append({"nivel": lvl.Name, "id": sp.Id.Value})
        except Exception as e:
            spaces_creados.append({"nivel": lvl.Name, "error": str(e)})

        # Matafuego — NFPA 13: 1 por piso en pasillo junto a escalera
        if inst_inc and sym_mat:
            pt = XYZ(m_to_ft(x_mat), m_to_ft(y_mat), lvl.Elevation + m_to_ft(1.50))
            try:
                inst = doc.Create.NewFamilyInstance(pt, sym_mat, lvl, ST.NonStructural)
                artefactos.append({"nivel": lvl.Name, "tipo": "matafuego", "id": inst.Id.Value})
            except Exception:
                pass

        # Tablero eléctrico seccional — 1 por piso en pasillo
        if inst_elec and sym_tab:
            pt = XYZ(m_to_ft(x_mat + 0.60), m_to_ft(y_mat), lvl.Elevation + m_to_ft(1.50))
            try:
                inst = doc.Create.NewFamilyInstance(pt, sym_tab, lvl, ST.NonStructural)
                artefactos.append({"nivel": lvl.Name, "tipo": "tablero_seccional", "id": inst.Id.Value})
            except Exception:
                pass

    t.Commit()

instalaciones = []
if inst_san:  instalaciones.append("Sanitaria")
if inst_elec: instalaciones.append("Eléctrica")
if inst_inc:  instalaciones.append("Incendio")

OUT = {
    "spaces_mep": len(spaces_creados),
    "artefactos": len(artefactos),
    "detalle": artefactos,
    "instalaciones_activas": instalaciones,
    "nota": "Completar redes de tuberías y conductos manualmente en Revit MEP.",
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
    """Genera ``07_instalaciones_mep.dyn`` con espacios MEP, matafuegos y tableros.

    Returns:
        Lista con el Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    s = DynScript(
        "07_instalaciones_mep",
        "Crea espacios MEP, matafuegos (NFPA 13) y tableros eléctricos seccionales por nivel.",
    )

    cb_pisos = s.add_code_block(str(params.pisos_tipo),                    label="pisos_tipo",     col=0, row=0)
    cb_frente= s.add_code_block(str(params.frente),                        label="frente_m",       col=0, row=1)
    cb_fondo = s.add_code_block(str(params.fondo),                         label="fondo_m",        col=0, row=2)
    cb_nesc  = s.add_code_block(str(params.cant_cajas_escalera),           label="cant_escaleras", col=0, row=3)
    cb_nasc  = s.add_code_block(str(params.cant_ascensores),               label="cant_ascensores",col=0, row=4)
    cb_san   = s.add_code_block(str(params.instalacion_sanitaria).lower(), label="inst_san",       col=0, row=5)
    cb_elec  = s.add_code_block(str(params.instalacion_electrica).lower(), label="inst_elec",      col=0, row=6)
    cb_inc   = s.add_code_block(str(params.instalacion_incendio).lower(),  label="inst_inc",       col=0, row=7)

    cbs = [cb_pisos, cb_frente, cb_fondo, cb_nesc, cb_nasc, cb_san, cb_elec, cb_inc]
    py = s.add_python_node(_CODE_MEP_ARTEFACTOS, n_inputs=len(cbs), label="Artefactos MEP v2", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Artefactos MEP", col=2, row=0)
    s.connect(py, w)

    # Nodo de inventario de sistemas (sigue igual, no requiere cambios)
    s.add_code_block(str(params.instalacion_sanitaria).lower(),     label="inst_san",  col=0, row=10)
    s.add_code_block(str(params.instalacion_electrica).lower(),     label="inst_elec", col=0, row=11)
    s.add_code_block(str(params.instalacion_gas).lower(),           label="inst_gas",  col=0, row=12)
    s.add_code_block(str(params.instalacion_incendio).lower(),      label="inst_inc",  col=0, row=13)
    s.add_code_block(str(params.instalacion_termomecanica).lower(), label="inst_term", col=0, row=14)

    py_sis = s.add_python_node(_CODE_MEP_SISTEMAS, n_inputs=5, label="Sistemas MEP", col=1, row=10)
    all_cbs_sis = [n for n in s._nodes
                   if hasattr(n, "output_port_id") and n is not py and n is not py_sis]
    for i, cb in enumerate(all_cbs_sis[-5:]):
        s.connect(cb, py_sis, to_input=i)

    w_sis = s.add_watch(label="Sistemas disponibles", col=2, row=10)
    s.connect(py_sis, w_sis)

    return [s.save(output_dir / "07_instalaciones_mep.dyn")]
