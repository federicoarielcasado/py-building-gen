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

doc = DocumentManager.Instance.CurrentDBDocument

frente_m     = float(IN[0])
fondo_m      = float(IN[1])
altura_total = float(IN[2])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_vft_section():
    tipos = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
    return next((t for t in tipos if t.ViewFamily == ViewFamily.Section), None)

def make_section(vft, origen, basis_x, basis_z, half_w, h, profundidad):
    """Crea una ViewSection con los vectores dados."""
    bbox = BoundingBoxXYZ()
    xf = Transform.Identity
    xf.BasisX = basis_x
    xf.BasisY = XYZ(0, 0, 1)
    xf.BasisZ = basis_z
    xf.Origin = origen
    bbox.Transform = xf
    margen = m_to_ft(1.0)
    bbox.Min = XYZ(-half_w - margen, 0, -margen)
    bbox.Max = XYZ( half_w + margen, h,  profundidad + margen)
    return ViewSection.CreateSection(doc, vft.Id, bbox)

vft  = get_vft_section()
vistas = []

if vft:
    with Transaction(doc, "py-building-gen: Cortes y Alzados v2") as t:
        t.Start()

        h      = m_to_ft(altura_total + 1.0)
        hf_x   = m_to_ft(frente_m / 2)
        hf_y   = m_to_ft(fondo_m  / 2)
        prof   = m_to_ft(fondo_m + 2.0)

        # ── Corte A-A transversal (perpendicular al frente) ───────────────
        v = make_section(vft,
            XYZ(hf_x, hf_y, 0),
            XYZ(1,0,0), XYZ(0,-1,0),
            hf_x, h, m_to_ft(fondo_m / 2 + 1.0))
        v.Name = "CORTE A-A"
        vistas.append({"tipo": "corte_transversal", "id": v.Id.Value})

        # ── Corte B-B longitudinal (paralelo al frente) ───────────────────
        v2 = make_section(vft,
            XYZ(hf_x, hf_y, 0),
            XYZ(0,1,0), XYZ(1,0,0),
            hf_y, h, m_to_ft(frente_m / 2 + 1.0))
        v2.Name = "CORTE B-B"
        vistas.append({"tipo": "corte_longitudinal", "id": v2.Id.Value})

        # ── Fachada principal (mirando desde el frente, Y negativo) ───────
        v3 = make_section(vft,
            XYZ(hf_x, m_to_ft(-2.0), 0),
            XYZ(1,0,0), XYZ(0,1,0),
            hf_x, h, prof)
        v3.Name = "FACHADA PRINCIPAL"
        vistas.append({"tipo": "fachada_principal", "id": v3.Id.Value})

        # ── Fachada contrafrente (mirando desde el fondo, Y positivo) ─────
        v4 = make_section(vft,
            XYZ(hf_x, m_to_ft(fondo_m + 2.0), 0),
            XYZ(-1,0,0), XYZ(0,-1,0),
            hf_x, h, prof)
        v4.Name = "FACHADA CONTRAFRENTE"
        vistas.append({"tipo": "fachada_contrafrente", "id": v4.Id.Value})

        # ── Fachada lateral izquierda (X = 0) ────────────────────────────
        v5 = make_section(vft,
            XYZ(m_to_ft(-2.0), hf_y, 0),
            XYZ(0,1,0), XYZ(-1,0,0),
            hf_y, h, prof)
        v5.Name = "FACHADA LATERAL IZQ"
        vistas.append({"tipo": "fachada_lateral_izq", "id": v5.Id.Value})

        # ── Fachada lateral derecha (X = frente_m) ───────────────────────
        v6 = make_section(vft,
            XYZ(m_to_ft(frente_m + 2.0), hf_y, 0),
            XYZ(0,-1,0), XYZ(1,0,0),
            hf_y, h, prof)
        v6.Name = "FACHADA LATERAL DER"
        vistas.append({"tipo": "fachada_lateral_der", "id": v6.Id.Value})

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

# ---------------------------------------------------------------------------
# Visibility overrides — controla qué categorías muestra cada disciplina
# ---------------------------------------------------------------------------

_CODE_VISIBILITY = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, View, BuiltInCategory, ElementId,
    OverrideGraphicSettings, FilteredElementCollector,
    Transaction,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

# Categorías a ocultar según disciplina de la vista
CAT_ESTRUCTURA = [
    int(BuiltInCategory.OST_StructuralColumns),
    int(BuiltInCategory.OST_StructuralFraming),
    int(BuiltInCategory.OST_StructuralFoundation),
    int(BuiltInCategory.OST_StructuralStiffener),
]
CAT_ARQ = [
    int(BuiltInCategory.OST_Walls),
    int(BuiltInCategory.OST_Floors),
    int(BuiltInCategory.OST_Doors),
    int(BuiltInCategory.OST_Windows),
    int(BuiltInCategory.OST_Stairs),
    int(BuiltInCategory.OST_Rooms),
]

def is_arq_view(v):
    return v.Name.startswith("PLANTA") or v.Name.startswith("CORTE") or v.Name.startswith("FACHADA")

def is_est_view(v):
    return v.Name.startswith("EST ")

def is_mep_view(v):
    return v.Name.startswith("MEP ")

def set_hidden(view, cat_ids, hidden):
    for cat_id in cat_ids:
        eid = ElementId(cat_id)
        try:
            view.SetCategoryHidden(eid, hidden)
        except Exception:
            pass

vistas_config = []

with Transaction(doc, "py-building-gen: Visibility Overrides") as t:
    t.Start()
    all_views = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    for v in all_views:
        if v.IsTemplate:
            continue
        try:
            if is_arq_view(v):
                set_hidden(v, CAT_ESTRUCTURA, True)    # oculta estructura en ARQ
                vistas_config.append({"vista": v.Name, "config": "ARQ — estructura oculta"})
            elif is_est_view(v):
                set_hidden(v, CAT_ARQ, True)            # oculta elementos ARQ en EST
                vistas_config.append({"vista": v.Name, "config": "EST — elementos ARQ ocultos"})
            elif is_mep_view(v):
                set_hidden(v, CAT_ESTRUCTURA, True)
                vistas_config.append({"vista": v.Name, "config": "MEP — estructura oculta"})
        except Exception as e:
            vistas_config.append({"vista": v.Name, "error": str(e)})
    t.Commit()

OUT = {"vistas_configuradas": len(vistas_config), "detalle": vistas_config}
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

    # Visibility overrides por disciplina
    py_vis = s.add_python_node(_CODE_VISIBILITY, n_inputs=0, label="Visibility Overrides", col=1, row=10)
    w_vis = s.add_watch(label="Vistas configuradas", col=2, row=10)
    s.connect(py_vis, w_vis)

    return [s.save(output_dir / "08_vistas.dyn")]
