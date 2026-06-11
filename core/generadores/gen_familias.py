"""Generador del script Dynamo 00_familias.dyn.

Prepara el modelo Revit antes de ejecutar el resto de scripts:
  1. Crea materiales: hormigón H-21/H-25/H-30, acero ADN 420/AL 220,
     mampostería, mortero, terminaciones.
  2. Crea/actualiza tipos de muro (compound structure):
     - Muro exterior 200mm  (revoque + ladrillo 170mm + revoque)
     - Tabique interior 100mm
     - Medianera 200mm (sin revoque exterior)
  3. Crea tipos de losa con espesor del predimensionado CIRSOC.
  4. Encuentra familias estructurales cargadas en el template y crea
     tipos parametrizados (35x35cm, 40x40cm…) con las secciones calculadas.

Debe ejecutarse PRIMERO, antes de 01_niveles_grilla.dyn.

Orden de ejecución: 0 de 10.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript
from core.predimensionado import predimensionar

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

# ---------------------------------------------------------------------------
# Nodo 1 — Materiales
# ---------------------------------------------------------------------------

_CODE_MATERIALES = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Material, Color, FillPatternElement,
    FilteredElementCollector, Transaction,
    BuiltInParameter, ElementId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

tipo_hormigon = _si(IN[0])   # "H-21" | "H-25" | "H-30"
tipo_acero    = _si(IN[1])   # "ADN 420" | "AL 220"

def color(r, g, b):
    return Color(r, g, b)

def get_or_create_material(nombre, r, g, b):
    col = FilteredElementCollector(doc).OfClass(Material).ToElements()
    mat = next((m for m in col if m.Name == nombre), None)
    if mat:
        return mat
    mat_id = Material.Create(doc, nombre)
    mat = doc.GetElement(mat_id)
    mat.Color = color(r, g, b)
    return mat

materiales_creados = []

with Transaction(doc, "py-building-gen: Materiales") as t:
    t.Start()

    # Hormigones según tipo seleccionado (+ los otros para referencia)
    for nombre, rgb in [
        ("Hormigón H-21",  (180, 180, 180)),
        ("Hormigón H-25",  (160, 160, 160)),
        ("Hormigón H-30",  (140, 140, 140)),
    ]:
        m = get_or_create_material(nombre, *rgb)
        materiales_creados.append(m.Name)

    # Aceros
    for nombre, rgb in [
        ("Acero ADN 420", (80,  80,  80)),
        ("Acero AL 220",  (100, 100, 100)),
    ]:
        m = get_or_create_material(nombre, *rgb)
        materiales_creados.append(m.Name)

    # Mampostería y terminaciones
    for nombre, rgb in [
        ("Ladrillo cerámico",    (195, 100,  60)),
        ("Mortero de cemento",   (220, 210, 200)),
        ("Revoque grueso",       (230, 220, 210)),
        ("Revoque fino / yeso",  (245, 240, 235)),
        ("Pintura látex blanca", (255, 255, 255)),
        ("Cámara de aire",       (200, 230, 255)),
        ("Membrana asfáltica",   ( 30,  30,  30)),
    ]:
        m = get_or_create_material(nombre, *rgb)
        materiales_creados.append(m.Name)

    t.Commit()

OUT = {
    "materiales_creados": materiales_creados,
    "tipo_hormigon_proyecto": tipo_hormigon,
    "tipo_acero_proyecto": tipo_acero,
}
'''

# ---------------------------------------------------------------------------
# Nodo 2 — Tipos de muro (compound structure)
# ---------------------------------------------------------------------------

_CODE_MUROS_TIPOS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    WallType, CompoundStructure, CompoundStructureLayer,
    MaterialFunctionAssignment, Material, ElementId,
    FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)
import System
from System.Collections.Generic import List as NetList

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_material_id(nombre):
    col = FilteredElementCollector(doc).OfClass(Material).ToElements()
    mat = next((m for m in col if m.Name == nombre), None)
    return mat.Id if mat else ElementId.InvalidElementId

def get_or_duplicate_wall_type(nombre_base, nombre_nuevo):
    wts = FilteredElementCollector(doc).OfClass(WallType).ToElements()
    existente = next((wt for wt in wts if wt.Name == nombre_nuevo), None)
    if existente:
        return existente
    base = next((wt for wt in wts if nombre_base.lower() in wt.Name.lower()), wts[0])
    return base.Duplicate(nombre_nuevo)

def build_compound_structure(capas):
    net_layers = NetList[CompoundStructureLayer]()
    for espesor_m, funcion, nombre_mat in capas:
        mat_id = get_material_id(nombre_mat)
        net_layers.Add(CompoundStructureLayer(m_to_ft(espesor_m), funcion, mat_id))
    return CompoundStructure.CreateSimpleCompoundStructure(net_layers)

FA = MaterialFunctionAssignment  # alias
tipos_creados = []

# Buscar keyword para muro genérico en español e inglés
_kw_muro = ("generic", "genérico", "generico", "basic", "básico", "basico")

with Transaction(doc, "py-building-gen: Tipos de muro") as t:
    t.Start()

    # 1. Muro exterior 200mm
    wt_ext = get_or_duplicate_wall_type("genér", "Muro exterior - 200mm")
    capas_ext = [
        (0.015, FA.Finish1,    "Revoque fino / yeso"),
        (0.170, FA.Structure,  "Ladrillo cerámico"),
        (0.015, FA.Finish2,    "Revoque grueso"),
    ]
    wt_ext.SetCompoundStructure(build_compound_structure(capas_ext))
    tipos_creados.append("Muro exterior - 200mm")

    # 2. Tabique interior 100mm
    wt_tab = get_or_duplicate_wall_type("genér", "Tabique interior - 100mm")
    capas_tab = [
        (0.013, FA.Finish1,    "Revoque fino / yeso"),
        (0.074, FA.Structure,  "Ladrillo cerámico"),
        (0.013, FA.Finish2,    "Revoque fino / yeso"),
    ]
    wt_tab.SetCompoundStructure(build_compound_structure(capas_tab))
    tipos_creados.append("Tabique interior - 100mm")

    # 3. Medianera 200mm (sin revoque exterior — va contra pared lindante)
    wt_med = get_or_duplicate_wall_type("genér", "Medianera - 200mm")
    capas_med = [
        (0.185, FA.Structure,  "Ladrillo cerámico"),
        (0.015, FA.Finish2,    "Revoque grueso"),
    ]
    wt_med.SetCompoundStructure(build_compound_structure(capas_med))
    tipos_creados.append("Medianera - 200mm")

    # 4. Muro cortafuego 200mm (REI-120 — divisoria entre departamentos, CABA Art. 6.1)
    wt_cf = get_or_duplicate_wall_type("genér", "Muro cortafuego - 200mm")
    capas_cf = [
        (0.020, FA.Finish1,   "Revoque fino / yeso"),
        (0.160, FA.Structure, "Ladrillo cerámico"),
        (0.020, FA.Finish2,   "Revoque fino / yeso"),
    ]
    wt_cf.SetCompoundStructure(build_compound_structure(capas_cf))
    tipos_creados.append("Muro cortafuego - 200mm")

    # 5. Muro shaft HA 300mm (REI-180 — caja escalera y ascensor)
    wt_sh = get_or_duplicate_wall_type("genér", "Muro shaft HA - 300mm")
    capas_sh = [
        (0.300, FA.Structure, "Hormigón H-25"),
    ]
    wt_sh.SetCompoundStructure(build_compound_structure(capas_sh))
    tipos_creados.append("Muro shaft HA - 300mm")

    # 6. Tabique de baño 100mm (ladrillo + membrana hidrófuga)
    wt_ban = get_or_duplicate_wall_type("genér", "Tabique baño - 100mm")
    capas_ban = [
        (0.010, FA.Finish1,   "Revoque fino / yeso"),
        (0.074, FA.Structure, "Ladrillo cerámico"),
        (0.010, FA.Substrate, "Mortero de cemento"),
        (0.006, FA.Finish2,   "Membrana asfáltica"),
    ]
    wt_ban.SetCompoundStructure(build_compound_structure(capas_ban))
    tipos_creados.append("Tabique baño - 100mm")

    t.Commit()

OUT = tipos_creados
'''

# ---------------------------------------------------------------------------
# Nodo 3 — Tipos de losa
# ---------------------------------------------------------------------------

_CODE_LOSA_TIPO = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FloorType, CompoundStructure, CompoundStructureLayer,
    MaterialFunctionAssignment, Material, ElementId,
    FilteredElementCollector, ElementCategoryFilter,
    BuiltInCategory, Transaction,
    UnitUtils, UnitTypeId, OpeningWrappingCondition,
)
import System
from System.Collections.Generic import List as NetList

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

espesor_losa_cm = _fi(IN[0], 20.0)
tipo_hormigon   = _si(IN[1], "H-21")

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_material_id(nombre):
    col = FilteredElementCollector(doc).OfClass(Material).ToElements()
    mat = next((m for m in col if m.Name == nombre), None)
    return mat.Id if mat else ElementId.InvalidElementId

def get_or_duplicate_floor_type(nombre_nuevo):
    cat_filter = ElementCategoryFilter(BuiltInCategory.OST_Floors)
    fts = (FilteredElementCollector(doc)
           .OfClass(FloorType)
           .WherePasses(cat_filter)
           .ToElements())
    existente = next((ft for ft in fts if ft.Name == nombre_nuevo), None)
    if existente:
        return existente
    if not fts:
        raise Exception("No se encontraron FloorTypes OST_Floors en el modelo.")
    return fts[0].Duplicate(nombre_nuevo)

FA = MaterialFunctionAssignment

def build_layers(capas):
    """Construye NetList[CompoundStructureLayer] y devuelve (net, idx_estructura).

    Regla de Revit: las capas de MEMBRANA deben tener espesor CERO. Cualquier otro
    valor invalida el CompoundStructure.
    """
    net = NetList[CompoundStructureLayer]()
    idx_struct = 0
    for i, (esp, func, mat_nombre) in enumerate(capas):
        mat_id = get_material_id(mat_nombre)
        espesor_ft = 0.0 if func == FA.Membrane else m_to_ft(esp)
        net.Add(CompoundStructureLayer(espesor_ft, func, mat_id))
        if func == FA.Structure:
            idx_struct = i
    return net, idx_struct

def construir_cs(ft, capas):
    """Reemplaza capas en el CS existente del FloorType y fija la capa estructural."""
    net, idx_struct = build_layers(capas)
    cs = ft.GetCompoundStructure()
    if cs is None:
        cs = CompoundStructure.CreateSimpleCompoundStructure(net)
    else:
        cs.SetLayers(net)
    # Tras SetLayers el índice estructural puede quedar apuntando a otra capa
    try:
        cs.StructuralMaterialIndex = idx_struct
    except Exception:
        pass
    return cs

def validar_cs(cs):
    """Llama a CompoundStructure.IsValid y devuelve (ok, [errores...]).

    IsValid(doc, out errors, out faultyLayers) → PythonNet3 lo expone como tupla.
    """
    try:
        chk = cs.IsValid(doc)
    except Exception as e:
        return (None, ["IsValid lanzo excepcion: " + str(e)])
    if isinstance(chk, tuple):
        ok = chk[0]
        errs = []
        for extra in chk[1:]:
            if extra is None:
                continue
            try:
                errs.extend([str(x) for x in extra])
            except Exception:
                errs.append(str(extra))
        return (ok, errs)
    return (chk, [])

espesor_m = espesor_losa_cm / 100.0
nombre_mat_ha = f"Hormigón {tipo_hormigon}"

definiciones = [
    (f"Losa HA {tipo_hormigon} - {espesor_losa_cm:.0f}cm", [
        (0.030,     FA.Substrate, "Mortero de cemento"),
        (espesor_m, FA.Structure, nombre_mat_ha),
    ]),
    (f"Losa azotea HA {tipo_hormigon} - {espesor_losa_cm:.0f}cm", [
        (0.000,     FA.Membrane,  "Membrana asfáltica"),   # membrana = espesor cero
        (0.020,     FA.Substrate, "Mortero de cemento"),
        (espesor_m, FA.Structure, nombre_mat_ha),
    ]),
]

tipos_creados = []
diagnostico = []

with Transaction(doc, "py-building-gen: Tipos de losa") as t:
    t.Start()
    for nombre, capas in definiciones:
        ft = get_or_duplicate_floor_type(nombre)
        cs = construir_cs(ft, capas)
        ok, errs = validar_cs(cs)
        if ok:
            ft.SetCompoundStructure(cs)
            tipos_creados.append(nombre)
        else:
            # No hacemos SetCompoundStructure (lanzaria y cortaria la transaccion).
            # Reportamos el error exacto para diagnostico.
            diagnostico.append({"tipo": nombre, "valido": str(ok), "errores": errs})
    t.Commit()

OUT = {"creados": tipos_creados, "diagnostico": diagnostico}
'''

# ---------------------------------------------------------------------------
# Nodo 4 — Tipos de familias estructurales
# ---------------------------------------------------------------------------

_CODE_STRUCT_TIPOS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    FamilySymbol, Material, ElementId,
    FilteredElementCollector, BuiltInCategory,
    Transaction, UnitUtils, UnitTypeId,
)

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
doc  = DocumentManager.Instance.CurrentDBDocument

lado_col_cm   = _fi(IN[0], 35.0)
ancho_viga_cm = _fi(IN[1], 25.0)
alto_viga_cm  = _fi(IN[2], 50.0)
tipo_hormigon = _si(IN[3], "H-21")

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_material_id(nombre):
    col = FilteredElementCollector(doc).OfClass(Material).ToElements()
    mat = next((m for m in col if m.Name == nombre), None)
    return mat.Id if mat else ElementId.InvalidElementId

_KW_COL  = ("concrete", "hormigon", "hormigón", "pilar", "column", "ha ", "rectangular")
_KW_VIGA = ("concrete", "hormigon", "hormigón", "viga",  "beam",   "ha ", "rectangular")

def find_symbol(categoria, keywords):
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(categoria)
           .ToElements())
    match = next((s for s in col if any(k in s.FamilyName.lower() for k in keywords)), None)
    return match or (col[0] if col else None)

def set_param(symbol, nombres, valor_m):
    """Intenta asignar un parámetro de sección por múltiples nombres posibles."""
    for nombre in nombres:
        p = symbol.LookupParameter(nombre)
        if p and not p.IsReadOnly:
            try:
                p.Set(m_to_ft(valor_m))
                return True
            except Exception:
                pass
    return False

mat_id_ha = get_material_id(f"Hormigón {tipo_hormigon}")
tipos_creados = []

with Transaction(doc, "py-building-gen: Tipos estructurales") as t:
    t.Start()

    # --- Columnas ---
    sym_col = find_symbol(BuiltInCategory.OST_StructuralColumns, _KW_COL)
    if sym_col:
        if not sym_col.IsActive:
            sym_col.Activate()

        nombre_col = f"Columna HA {lado_col_cm:.0f}x{lado_col_cm:.0f}cm"
        try:
            nuevo_col = sym_col.Duplicate(nombre_col)
        except Exception:
            nuevo_col = sym_col

        # Parámetros de sección (nombres varían según familia y versión)
        lado = lado_col_cm / 100.0
        set_param(nuevo_col, ["b", "Ancho", "Width", "w"],  lado)
        set_param(nuevo_col, ["h", "Alto",  "Depth", "d"],  lado)

        # Material estructural
        p_mat = nuevo_col.LookupParameter("Material estructural") or \
                nuevo_col.LookupParameter("Structural Material") or \
                nuevo_col.LookupParameter("Material")
        if p_mat and mat_id_ha != ElementId.InvalidElementId:
            try:
                p_mat.Set(mat_id_ha)
            except Exception:
                pass

        tipos_creados.append(nombre_col)

    # --- Vigas ---
    sym_viga = find_symbol(BuiltInCategory.OST_StructuralFraming, _KW_VIGA)
    if sym_viga:
        if not sym_viga.IsActive:
            sym_viga.Activate()

        nombre_viga = f"Viga HA {ancho_viga_cm:.0f}x{alto_viga_cm:.0f}cm"
        try:
            nuevo_viga = sym_viga.Duplicate(nombre_viga)
        except Exception:
            nuevo_viga = sym_viga

        ancho = ancho_viga_cm / 100.0
        alto  = alto_viga_cm  / 100.0
        set_param(nuevo_viga, ["b", "Ancho", "Width",  "w"], ancho)
        set_param(nuevo_viga, ["h", "Alto",  "Depth",  "d"], alto)

        p_mat = nuevo_viga.LookupParameter("Material estructural") or \
                nuevo_viga.LookupParameter("Structural Material") or \
                nuevo_viga.LookupParameter("Material")
        if p_mat and mat_id_ha != ElementId.InvalidElementId:
            try:
                p_mat.Set(mat_id_ha)
            except Exception:
                pass

        tipos_creados.append(nombre_viga)

    t.Commit()

if not tipos_creados:
    OUT = {
        "resultado": "No se encontraron familias estructurales en el template.",
        "accion_requerida": (
            "Cargar manualmente una familia de columna y viga de HA "
            "desde Insertar → Cargar familia, luego volver a correr este script."
        ),
    }
else:
    OUT = {
        "tipos_creados": tipos_creados,
        "nota": "Verificar secciones en Propiedades de tipo antes de correr 04_estructura.dyn",
    }
'''


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def nombres_tipos(params: "ParametrosEdificio") -> dict[str, str]:
    """Retorna los nombres exactos de los tipos creados por 00_familias.dyn.

    Usar en los demás generadores para buscar por nombre exacto en lugar de
    por keyword genérica.
    """
    res = predimensionar(params)
    col_base  = res.columnas[0] if res.columnas else None
    viga_base = res.vigas[0]    if res.vigas    else None
    losa_base = res.losas[0]    if res.losas    else None

    lado_col_cm   = round(col_base.lado_m   * 100) if col_base  else 25
    alto_viga_cm  = round(viga_base.alto_m  * 100) if viga_base else 50
    ancho_viga_cm = round(viga_base.ancho_m * 100) if viga_base else 25
    espesor_cm    = round(losa_base.espesor_cm)     if losa_base else 20
    ha = params.hormigon_tipo

    return {
        "muro_ext":     "Muro exterior - 200mm",
        "tabique":      "Tabique interior - 100mm",
        "medianera":    "Medianera - 200mm",
        "cortafuego":   "Muro cortafuego - 200mm",
        "shaft":        "Muro shaft HA - 300mm",
        "tabique_bano": "Tabique baño - 100mm",
        "losa":         f"Losa HA {ha} - {espesor_cm:.0f}cm",
        "losa_azo":     f"Losa azotea HA {ha} - {espesor_cm:.0f}cm",
        "columna":      f"Columna HA {lado_col_cm:.0f}x{lado_col_cm:.0f}cm",
        "viga":         f"Viga HA {ancho_viga_cm:.0f}x{alto_viga_cm:.0f}cm",
    }


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> Path:
    """Genera ``00_familias.dyn`` — preparación del modelo Revit.

    Debe ejecutarse antes que todos los demás scripts.

    Args:
        params: Parámetros del edificio (hormigón, acero, predimensionado).
        output_dir: Directorio de salida.

    Returns:
        Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    res = predimensionar(params)

    col_base  = res.columnas[0] if res.columnas else None
    viga_base = res.vigas[0]    if res.vigas    else None
    lado_col_cm   = round(col_base.lado_m  * 100) if col_base  else 25
    alto_viga_cm  = round(viga_base.alto_m  * 100) if viga_base else 50
    ancho_viga_cm = round(viga_base.ancho_m * 100) if viga_base else 25
    espesor_losa_cm = round(res.losas[0].espesor_cm) if res.losas else 20

    s = DynScript(
        "00_familias",
        "Crea materiales, wall types, floor types y tipos estructurales. "
        "Ejecutar PRIMERO, antes de 01_niveles_grilla.dyn.",
    )

    # --- Nodo 1: Materiales ---
    cb_ha   = s.add_code_block(f'"{params.hormigon_tipo}"', label="tipo_hormigon", col=0, row=0)
    cb_ac   = s.add_code_block(f'"{params.acero_tipo}"',   label="tipo_acero",    col=0, row=1)
    py_mat  = s.add_python_node(_CODE_MATERIALES, n_inputs=2, label="Crear Materiales", col=1, row=0)
    s.connect(cb_ha, py_mat, to_input=0)
    s.connect(cb_ac, py_mat, to_input=1)
    w_mat   = s.add_watch(label="Materiales", col=2, row=0)
    s.connect(py_mat, w_mat)

    # --- Nodo 2: Tipos de muro ---
    py_muro = s.add_python_node(_CODE_MUROS_TIPOS, n_inputs=0, label="Crear Wall Types", col=1, row=3)
    w_muro  = s.add_watch(label="Wall Types", col=2, row=3)
    s.connect(py_muro, w_muro)

    # --- Nodo 3: Tipos de losa ---
    cb_esp  = s.add_code_block(str(espesor_losa_cm),       label="espesor_losa_cm", col=0, row=5)
    cb_ha2  = s.add_code_block(f'"{params.hormigon_tipo}"', label="tipo_hormigon",   col=0, row=6)
    py_losa = s.add_python_node(_CODE_LOSA_TIPO, n_inputs=2, label="Crear Floor Types", col=1, row=5)
    s.connect(cb_esp, py_losa, to_input=0)
    s.connect(cb_ha2, py_losa, to_input=1)
    w_losa  = s.add_watch(label="Floor Types", col=2, row=5)
    s.connect(py_losa, w_losa)

    # --- Nodo 4: Tipos estructurales ---
    cb_lado  = s.add_code_block(str(lado_col_cm),          label="lado_col_cm",    col=0, row=8)
    cb_ancho = s.add_code_block(str(ancho_viga_cm),        label="ancho_viga_cm",  col=0, row=9)
    cb_alto  = s.add_code_block(str(alto_viga_cm),         label="alto_viga_cm",   col=0, row=10)
    cb_ha3   = s.add_code_block(f'"{params.hormigon_tipo}"', label="tipo_hormigon", col=0, row=11)
    py_str   = s.add_python_node(_CODE_STRUCT_TIPOS, n_inputs=4, label="Crear Tipos Estructurales", col=1, row=8)
    s.connect(cb_lado,  py_str, to_input=0)
    s.connect(cb_ancho, py_str, to_input=1)
    s.connect(cb_alto,  py_str, to_input=2)
    s.connect(cb_ha3,   py_str, to_input=3)
    w_str   = s.add_watch(label="Tipos estructurales", col=2, row=8)
    s.connect(py_str, w_str)

    return s.save(output_dir / "00_familias.dyn")
