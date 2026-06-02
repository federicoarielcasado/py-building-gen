"""Generador del script Dynamo 08_vistas.dyn.

Crea vistas de documentación en Revit:
  - Plantas por nivel (ViewPlan)
  - Cortes transversal y longitudinal (ViewSection)
  - Alzados / fachadas (ViewSection con orientación)
  - Vista 3D isométrica (View3D)

Orden de ejecución: 8 de 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

_CODE_PLANTAS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, ViewFamilyType, ViewFamily, Level,
    FilteredElementCollector, Transaction,
    ElementId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

pisos_tipo   = int(IN[0])
tiene_azotea = bool(IN[1])

def get_view_family_type(familia):
    tipos = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
    return next((t for t in tipos if t.ViewFamily == familia), None)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None)

vft_planta = get_view_family_type(ViewFamily.FloorPlan)
plantas = []

if vft_planta:
    with Transaction(doc, "py-building-gen: Plantas") as t:
        t.Start()

        nombres_nivel = ["PB"] + [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]
        if tiene_azotea:
            nombres_nivel.append("AZO")

        for nombre in nombres_nivel:
            lvl = get_level(nombre)
            if lvl:
                vista = ViewPlan.Create(doc, vft_planta.Id, lvl.Id)
                vista.Name = f"PLANTA {nombre}"
                plantas.append({"nivel": nombre, "id": vista.Id.IntegerValue})

        t.Commit()

OUT = plantas
'''

_CODE_CORTES = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewSection, ViewFamilyType, ViewFamily, BoundingBoxXYZ,
    XYZ, Transform, FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

frente_m    = float(IN[0])
fondo_m     = float(IN[1])
altura_total = float(IN[2])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_vft_section():
    tipos = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
    return next((t for t in tipos if t.ViewFamily == ViewFamily.Section), None)

vft = get_vft_section()
vistas = []

if vft:
    with Transaction(doc, "py-building-gen: Cortes y Alzados") as t:
        t.Start()

        margen = m_to_ft(1.0)
        h      = m_to_ft(altura_total + 1.0)

        # Corte transversal — a mitad del fondo, mirando hacia frente (eje X)
        bbox_trans = BoundingBoxXYZ()
        xform = Transform.Identity
        xform.BasisX = XYZ(1, 0, 0)
        xform.BasisY = XYZ(0, 0, 1)
        xform.BasisZ = XYZ(0, -1, 0)
        xform.Origin = XYZ(m_to_ft(frente_m / 2), m_to_ft(fondo_m / 2), 0)
        bbox_trans.Transform = xform
        bbox_trans.Min = XYZ(-m_to_ft(frente_m / 2) - margen, 0, -margen)
        bbox_trans.Max = XYZ( m_to_ft(frente_m / 2) + margen, h,  margen)
        v = ViewSection.CreateSection(doc, vft.Id, bbox_trans)
        v.Name = "CORTE A-A"
        vistas.append({"tipo": "corte_transversal", "id": v.Id.IntegerValue})

        # Corte longitudinal — a mitad del frente, mirando hacia el fondo (eje Y)
        bbox_long = BoundingBoxXYZ()
        xform2 = Transform.Identity
        xform2.BasisX = XYZ(0, 1, 0)
        xform2.BasisY = XYZ(0, 0, 1)
        xform2.BasisZ = XYZ(1, 0, 0)
        xform2.Origin = XYZ(m_to_ft(frente_m / 2), m_to_ft(fondo_m / 2), 0)
        bbox_long.Transform = xform2
        bbox_long.Min = XYZ(-m_to_ft(fondo_m / 2) - margen, 0, -margen)
        bbox_long.Max = XYZ( m_to_ft(fondo_m / 2) + margen, h,  margen)
        v2 = ViewSection.CreateSection(doc, vft.Id, bbox_long)
        v2.Name = "CORTE B-B"
        vistas.append({"tipo": "corte_longitudinal", "id": v2.Id.IntegerValue})

        # Alzado frontal (fachada principal)
        bbox_fach = BoundingBoxXYZ()
        xform3 = Transform.Identity
        xform3.BasisX = XYZ(1, 0, 0)
        xform3.BasisY = XYZ(0, 0, 1)
        xform3.BasisZ = XYZ(0, 1, 0)
        xform3.Origin = XYZ(m_to_ft(frente_m / 2), m_to_ft(-1.5), 0)
        bbox_fach.Transform = xform3
        bbox_fach.Min = XYZ(-m_to_ft(frente_m / 2) - margen, 0, -margen)
        bbox_fach.Max = XYZ( m_to_ft(frente_m / 2) + margen, h,  m_to_ft(fondo_m + 2))
        v3 = ViewSection.CreateSection(doc, vft.Id, bbox_fach)
        v3.Name = "FACHADA PRINCIPAL"
        vistas.append({"tipo": "fachada", "id": v3.Id.IntegerValue})

        t.Commit()

OUT = vistas
'''

_CODE_3D = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    View3D, ViewFamilyType, ViewFamily,
    FilteredElementCollector, Transaction,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

def get_vft_3d():
    tipos = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
    return next((t for t in tipos if t.ViewFamily == ViewFamily.ThreeDimensional), None)

vft = get_vft_3d()
resultado = []

if vft:
    with Transaction(doc, "py-building-gen: Vista 3D") as t:
        t.Start()
        v3d = View3D.CreateIsometric(doc, vft.Id)
        v3d.Name = "3D - Vista General"
        resultado.append({"tipo": "3d_isometrica", "id": v3d.Id.IntegerValue})
        t.Commit()

OUT = resultado
'''


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> list[Path]:
    """Genera ``08_vistas.dyn``.

    Returns:
        Lista con el Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    altura_total = params.altura_total

    s = DynScript(
        "08_vistas",
        "Crea plantas, cortes, alzados y vista 3D para documentación técnica.",
    )

    # Plantas por nivel
    s.add_code_block(str(params.pisos_tipo),              label="pisos_tipo",    col=0, row=0)
    s.add_code_block(str(params.tiene_azotea).lower(),    label="tiene_azotea",  col=0, row=1)

    py_plantas = s.add_python_node(_CODE_PLANTAS, n_inputs=2, label="Crear Plantas", col=1, row=0)
    cbs_plantas = [n for n in s._nodes if n is not py_plantas]
    for i, cb in enumerate(cbs_plantas):
        s.connect(cb, py_plantas, to_input=i)

    w_plantas = s.add_watch(label="Plantas creadas", col=2, row=0)
    s.connect(py_plantas, w_plantas)

    # Cortes y alzados
    s.add_code_block(str(params.frente),      label="frente_m",     col=0, row=3)
    s.add_code_block(str(params.fondo),       label="fondo_m",      col=0, row=4)
    s.add_code_block(str(altura_total),       label="altura_total_m", col=0, row=5)

    py_cortes = s.add_python_node(_CODE_CORTES, n_inputs=3, label="Crear Cortes y Alzados", col=1, row=3)
    all_cbs = [n for n in s._nodes if hasattr(n, 'output_port_id') and n is not py_plantas and n is not py_cortes]
    cortes_cbs = all_cbs[-3:]
    for i, cb in enumerate(cortes_cbs):
        s.connect(cb, py_cortes, to_input=i)

    w_cortes = s.add_watch(label="Cortes y alzados", col=2, row=3)
    s.connect(py_cortes, w_cortes)

    # Vista 3D (sin inputs paramétricos)
    py_3d = s.add_python_node(_CODE_3D, n_inputs=0, label="Crear Vista 3D", col=1, row=7)
    w_3d = s.add_watch(label="Vista 3D", col=2, row=7)
    s.connect(py_3d, w_3d)

    return [s.save(output_dir / "08_vistas.dyn")]
