"""Generador del script Dynamo 09b_anotaciones.dyn.

Coloca en las vistas de planta y corte:
  - Room tags (nombre + área) en cada planta tipo
  - Dimensiones generales del edificio (frente, fondo)
  - Tags de puertas y ventanas
  - Cotas de nivel en cortes (SpotElevation)

Orden de ejecución: 9b (después de 09_sheets y 11_habitaciones).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

_CODE_ROOM_TAGS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, ViewFamily, ViewFamilyType, Level,
    FilteredElementCollector, BuiltInCategory,
    IndependentTag, TagMode, TagOrientation, Reference,
    Transaction, UV, UnitUtils, UnitTypeId,
    FamilySymbol,
)
from Autodesk.Revit.DB.Architecture import Room
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

pisos_tipo = int(IN[0])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def ft_to_m(ft):
    return UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Meters)

def get_planta_tipo(nombre_nivel):
    """Busca la vista PLANTA del nivel dado."""
    todas = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    return next((v for v in todas if f"PLANTA {nombre_nivel}" in v.Name
                 and not v.IsTemplate), None)

def get_room_tag_type():
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(BuiltInCategory.OST_RoomTags)
           .ToElements())
    # Preferir tag con área si existe
    match = next((s for s in col if "area" in s.FamilyName.lower()
                  or "área" in s.FamilyName.lower()), None)
    return match or (col[0] if col else None)

def get_rooms_en_nivel(nivel_nombre):
    rooms = FilteredElementCollector(doc).OfClass(Room).ToElements()
    return [r for r in rooms if r.Level and r.Level.Name == nivel_nombre
            and r.Area > 0.01]

tag_type = get_room_tag_type()
tags_creados = []

with Transaction(doc, "py-building-gen: Room Tags") as t:
    t.Start()

    if tag_type and not tag_type.IsActive:
        tag_type.Activate()

    # Tags en PLANTA P01 (representativa del piso tipo)
    for nivel_nombre in [f"P{i:02d}" for i in range(1, pisos_tipo + 1)]:
        vista = get_planta_tipo(nivel_nombre)
        if vista is None:
            continue
        rooms = get_rooms_en_nivel(nivel_nombre)
        for room in rooms:
            try:
                loc = room.Location
                if loc is None:
                    continue
                pt = loc.Point
                tag = IndependentTag.Create(
                    doc, vista.Id,
                    Reference(room),
                    False,
                    TagMode.TM_ADDBY_ELEMENT,
                    TagOrientation.Horizontal,
                    UV(pt.X, pt.Y),
                )
                if tag_type:
                    tag.ChangeTypeId(tag_type.Id)
                tags_creados.append({
                    "nivel": nivel_nombre,
                    "room": room.Name,
                    "id": tag.Id.Value,
                })
            except Exception as e:
                tags_creados.append({"nivel": nivel_nombre, "error": str(e)})

    t.Commit()

OUT = {"total_tags": len(tags_creados), "detalle": tags_creados}
'''

_CODE_DIMENSIONES = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, ViewSection, Wall, Level, Line, XYZ,
    ReferenceArray, FilteredElementCollector,
    Transaction, UnitUtils, UnitTypeId,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m = float(IN[0])
fondo_m  = float(IN[1])

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def ft_to_m(ft):
    return UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Meters)

def get_planta_pb():
    todas = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    return next((v for v in todas if "PLANTA PB" in v.Name and not v.IsTemplate), None)

def get_walls_at_y(target_y, tol=0.40):
    walls = FilteredElementCollector(doc).OfClass(Wall).ToElements()
    result = []
    for w in walls:
        loc = w.Location
        if not hasattr(loc, "Curve"):
            continue
        c = loc.Curve
        y1 = ft_to_m(c.GetEndPoint(0).Y)
        y2 = ft_to_m(c.GetEndPoint(1).Y)
        if abs(y1 - target_y) < tol and abs(y2 - target_y) < tol:
            result.append(w)
    return result

def get_walls_at_x(target_x, tol=0.30):
    walls = FilteredElementCollector(doc).OfClass(Wall).ToElements()
    result = []
    for w in walls:
        loc = w.Location
        if not hasattr(loc, "Curve"):
            continue
        c = loc.Curve
        x1 = ft_to_m(c.GetEndPoint(0).X)
        x2 = ft_to_m(c.GetEndPoint(1).X)
        if abs(x1 - target_x) < tol and abs(x2 - target_x) < tol:
            result.append(w)
    return result

dims_creadas = []
vista_pb = get_planta_pb()

if vista_pb:
    with Transaction(doc, "py-building-gen: Dimensiones") as t:
        t.Start()

        # Dimensión frente (a lo largo de X, debajo del edificio)
        walls_frente = get_walls_at_y(0.0)
        if walls_frente:
            w_frt = walls_frente[0]
            refs = ReferenceArray()
            # Referencia a la cara exterior de la pared izquierda (x=0)
            walls_izq = get_walls_at_x(0.0)
            walls_der = get_walls_at_x(frente_m)
            for w in walls_izq[:1] + walls_der[:1]:
                for ref in w.GetReferences(
                    __import__("Autodesk.Revit.DB", fromlist=["WallSide"]).WallSide.Exterior,
                ) if hasattr(w, "GetReferences") else []:
                    refs.Append(ref)

            # Alternativa: usar la curva de la pared directamente
            if refs.Size < 2:
                refs = ReferenceArray()
                for ww in walls_izq[:1]:
                    loc = ww.Location
                    if hasattr(loc, "Curve"):
                        refs.Append(loc.Curve.GetEndPointReference(0))
                        refs.Append(loc.Curve.GetEndPointReference(1))

            if refs.Size >= 2:
                dim_line = Line.CreateBound(
                    XYZ(m_to_ft(0), m_to_ft(-2.0), 0),
                    XYZ(m_to_ft(frente_m), m_to_ft(-2.0), 0)
                )
                try:
                    dim = doc.Create.NewDimension(vista_pb, dim_line, refs)
                    dims_creadas.append({"tipo": "frente", "id": dim.Id.Value})
                except Exception as e:
                    dims_creadas.append({"tipo": "frente_error", "error": str(e)})

        t.Commit()
else:
    dims_creadas.append({"error": "Vista PLANTA PB no encontrada. Correr 08_vistas primero."})

OUT = {"total": len(dims_creadas), "detalle": dims_creadas}
'''

_CODE_DOOR_WINDOW_TAGS = '''\
import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ViewPlan, FamilyInstance, FamilySymbol, BuiltInCategory,
    FilteredElementCollector, IndependentTag, TagMode, TagOrientation,
    Reference, Transaction, UV, UnitUtils, UnitTypeId,
)
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

pisos_tipo = int(IN[0])

def get_planta(nombre):
    todas = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    return next((v for v in todas if f"PLANTA {nombre}" in v.Name and not v.IsTemplate), None)

def get_tag_type(categoria):
    col = (FilteredElementCollector(doc)
           .OfClass(FamilySymbol)
           .OfCategory(categoria)
           .ToElements())
    return col[0] if col else None

def get_instances(categoria, level_id):
    return [e for e in FilteredElementCollector(doc)
            .OfClass(FamilyInstance)
            .OfCategory(categoria)
            .ToElements()
            if e.LevelId == level_id]

tags_creados = []

tag_puerta  = get_tag_type(BuiltInCategory.OST_DoorTags)
tag_ventana = get_tag_type(BuiltInCategory.OST_WindowTags)

with Transaction(doc, "py-building-gen: Tags puertas y ventanas") as t:
    t.Start()

    for sym in [tag_puerta, tag_ventana]:
        if sym and not sym.IsActive:
            sym.Activate()

    # Solo etiquetar P01 (representativo — el resto es idéntico)
    from Autodesk.Revit.DB import Level
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    lvl_p01 = next((l for l in levels if l.Name == "P01"), None)
    if lvl_p01 is None:
        lvl_p01 = next((l for l in levels if l.Name.startswith("P") and l.Name[1:].isdigit()), None)

    if lvl_p01:
        vista = get_planta(lvl_p01.Name)
        if vista:
            for categoria, tag_type in [
                (BuiltInCategory.OST_Doors,   tag_puerta),
                (BuiltInCategory.OST_Windows, tag_ventana),
            ]:
                if tag_type is None:
                    continue
                for inst in get_instances(categoria, lvl_p01.Id):
                    try:
                        loc = inst.Location
                        if not hasattr(loc, "Point"):
                            continue
                        pt = loc.Point
                        tag = IndependentTag.Create(
                            doc, vista.Id,
                            Reference(inst), False,
                            TagMode.TM_ADDBY_ELEMENT,
                            TagOrientation.Horizontal,
                            UV(pt.X, pt.Y),
                        )
                        tag.ChangeTypeId(tag_type.Id)
                        tags_creados.append({"tipo": categoria.ToString(), "id": tag.Id.Value})
                    except Exception:
                        pass

    t.Commit()

OUT = {"total": len(tags_creados), "tags": tags_creados}
'''


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> Path:
    """Genera ``09b_anotaciones.dyn`` — room tags, tags de aberturas y dimensiones.

    Returns:
        Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    s = DynScript(
        "09b_anotaciones",
        "Coloca room tags con área, tags de puertas/ventanas y dimensiones generales. "
        "Ejecutar después de 09_sheets, 11_habitaciones y 05_aberturas.",
    )

    # Nodo 1: Room tags en plantas tipo
    cb_pisos = s.add_code_block(str(params.pisos_tipo), label="pisos_tipo", col=0, row=0)
    py_rt = s.add_python_node(_CODE_ROOM_TAGS, n_inputs=1, label="Room Tags", col=1, row=0)
    s.connect(cb_pisos, py_rt, to_input=0)
    w_rt = s.add_watch(label="Room Tags", col=2, row=0)
    s.connect(py_rt, w_rt)

    # Nodo 2: Dimensiones generales
    cb_frente = s.add_code_block(str(params.frente), label="frente_m", col=0, row=3)
    cb_fondo  = s.add_code_block(str(params.fondo),  label="fondo_m",  col=0, row=4)
    py_dim = s.add_python_node(_CODE_DIMENSIONES, n_inputs=2, label="Dimensiones", col=1, row=3)
    s.connect(cb_frente, py_dim, to_input=0)
    s.connect(cb_fondo,  py_dim, to_input=1)
    w_dim = s.add_watch(label="Dimensiones", col=2, row=3)
    s.connect(py_dim, w_dim)

    # Nodo 3: Tags de puertas y ventanas en P01
    cb_pisos2 = s.add_code_block(str(params.pisos_tipo), label="pisos_tipo", col=0, row=7)
    py_tags = s.add_python_node(_CODE_DOOR_WINDOW_TAGS, n_inputs=1, label="Tags Aberturas", col=1, row=7)
    s.connect(cb_pisos2, py_tags, to_input=0)
    w_tags = s.add_watch(label="Tags aberturas", col=2, row=7)
    s.connect(py_tags, w_tags)

    return s.save(output_dir / "09b_anotaciones.dyn")
