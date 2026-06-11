# Referencia Dynamo 4.0 / Revit API / PythonNet3

> Documento vivo. Se construye a medida que desarrollamos `py-building-gen`, porque
> Dynamo 4.0 + Revit 2027 + PythonNet3 está pobremente documentado y muchos patrones
> que funcionaban en IronPython 2.7 / Dynamo 2.x ya **no** aplican.
>
> Entorno objetivo: **Revit 2027 · Dynamo 4.0 · motor PythonNet3** (CPython3 ya no se
> admite). Template `Default_M_ESP.rte`.
>
> Convención: cada entrada trae un snippet mínimo que funciona + el *gotcha* que nos
> costó encontrar. Cuando un patrón está aplicado en el código, se cita el generador.

---

## 1. Cómo Dynamo ejecuta un nodo Python

- Las entradas llegan en la lista global `IN` (`IN[0]`, `IN[1]`, …). Las salidas se
  asignan a `OUT`.
- El builder (`core/dynamo/dyn_builder.py`) **inyecta** estos helpers al inicio de
  cada nodo para evitar `TypeError` cuando un input llega `None`:
  ```python
  def _fi(v, d=0.0): return float(v) if v is not None else float(d)
  def _ii(v, d=0):   return int(v)   if v is not None else int(d)
  def _si(v, d=""):  return str(v)   if v is not None else str(d)
  ```
  Usar siempre `_fi/_ii/_si` en vez de `float/int/str` directos sobre `IN[x]`.
- Acceso al documento (vía RevitServices, no `__revit__` en nodos Dynamo):
  ```python
  import clr
  clr.AddReference("RevitAPI")
  clr.AddReference("RevitServices")
  from RevitServices.Persistence import DocumentManager
  doc   = DocumentManager.Instance.CurrentDBDocument
  uidoc = DocumentManager.Instance.CurrentUIDocument   # si hace falta UI
  ```
- Todos los `import` van al bloque superior del nodo. Evitar imports dinámicos dentro
  de expresiones (`__import__(...)`), rompen en PythonNet3.
- El código de cada nodo vive en strings `_CODE_*` que `generar.py` **nunca compila**.
  Un `SyntaxError`/`IndentationError` ahí no se detecta hasta Revit. Por eso el test
  `TestSintaxisCodigoEmbebido` compila los 28 nodos con `compile()`. Correrlo siempre
  tras editar generadores.

### Formato de Connectors en el .dyn — referencian IDs de PUERTO (no de nodo)
El bug más costoso del proyecto. En el JSON de Dynamo 2.x+ un conector es:
```json
{ "Start": "<id del puerto de SALIDA>", "End": "<id del puerto de ENTRADA>",
  "Id": "<id del conector>", "IsHidden": "False" }
```
`Start`/`End` son los `Id` que están dentro de los arrays `Outputs`/`Inputs` de los
nodos — **NO** los `Id` de los nodos. **No** existen `StartIndex`/`EndIndex`/`PortType`.
Si se usan IDs de nodo, Dynamo no resuelve ninguna conexión: cada `IN[x]` llega `None`,
y los nodos Python caen a los defaults de `_fi/_ii/_si` → el script ignora por completo
los parámetros del usuario. Síntomas: grilla con 2 ejes en el origen (frente=fondo=0),
muros de largo cero, todo "funciona sin error" pero con valores default.
> Causa raíz encontrada 2026-06-10. Test `test_start_end_referencian_puertos_no_nodos`
> valida que cada `Start`/`End` sea un puerto real y no un id de nodo.

### Pasar datos por Code Blocks — NO meter comillas adentro
Un Code Block de DesignScript define strings con comillas dobles. Si el valor que
inyectás (ej. JSON) contiene comillas dobles, DesignScript cierra el string en la
primera comilla interna y el resto lo lee como código → `se esperaba ';'` y el nodo
Python recibe vacío (`Expecting value: line 1 column 1`). DesignScript *especifica*
escape `\"` pero Dynamo tiene bugs conocidos manejándolo (issues #7425/#7781/#9117).
**Solución:** usar un formato sin comillas ni backslashes y parsearlo en el nodo:
```python
# Productor (Python):  "2amb:1,3amb:1"
tipologias_str = ",".join(f"{t.tipo}:{t.cantidad}" for t in mix)
s.add_code_block(f'"{tipologias_str}"', label="tipologias")
# Consumidor (nodo):
apts = []
for par in _si(IN[i]).split(","):
    tipo, _, cant = par.strip().partition(":")
    apts += [tipo or "2amb"] * (int(cant) if cant.isdigit() else 1)
```
> Aplicado en muros/aberturas/habitaciones (`02`, `05`, `11`).

---

## 2. PythonNet3 — marshaling de tipos (CRÍTICO)

### IList&lt;T&gt; no se convierte automáticamente
Las listas Python **no** se marshalean a `IList<T>`. Usar `NetList[T]` explícito:
```python
from System.Collections.Generic import List as NetList

net_loops = NetList[CurveLoop](python_list)
Floor.Create(doc, net_loops, ft_id, lvl_id)

net_layers = NetList[CompoundStructureLayer]()
net_layers.Add(layer)
```
Afecta a `Floor.Create`, `CompoundStructure.*`, `Wall.Create` con curvas, etc.

### Enums con nombre reservado en Python
`OpeningWrappingCondition.None`, `ViewDetailLevel.None`, … chocan con la keyword
`None`. Usar `getattr(Enum, 'None')` o el valor entero `0`. Ojo: PythonNet3 puede
mapear el miembro `.None` de un enum .NET al `None` de Python — no confiar en
asignarlo desde afuera (ver §4 FloorType).

### Implementar una interfaz .NET
Se puede subclasear una interfaz .NET directamente:
```python
class _StairFailures(IFailuresPreprocessor):
    def PreprocessFailures(self, failuresAccessor):
        return FailureProcessingResult.Continue
```

---

## 3. Identificadores y unidades

- **ElementId**: usar `.Value` (Int64). `.IntegerValue` (Int32) es obsoleto desde
  Revit 2024 y puede lanzar `OverflowException` con IDs altos.
- **Unidades**: el modelo trabaja en pies. Convertir siempre:
  ```python
  UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)     # m  -> ft
  UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Meters)  # ft -> m
  ```
- **Elevaciones**: `Level.Elevation` ya está en pies. La Z de inserción es relativa
  al modelo, no a 0 — con subsuelos `Level.Elevation` puede ser negativo.

---

## 4. Patrones por elemento

### Levels y Grids
```python
lvl = Level.Create(doc, m_to_ft(elev_m)); lvl.Name = "P01"
g = Grid.Create(doc, Line.CreateBound(p1, p2)); g.Name = "A"
```

### Walls
```python
Wall.Create(doc, Line.CreateBound(p1, p2), wallType.Id, lvl.Id,
            m_to_ft(altura), 0, False, False)
```

### Floors + CompoundStructure — el famoso "wrong EndCap condition"
`FilteredElementCollector(...).OfClass(FloorType)` **también** devuelve `CeilingType`
y losas de fundación (misma clase .NET). Filtrar por categoría antes de duplicar:
```python
cat = ElementCategoryFilter(BuiltInCategory.OST_Floors)
fts = FilteredElementCollector(doc).OfClass(FloorType).WherePasses(cat).ToElements()
```
Crear un `CompoundStructure` desde cero (`Create` / `CreateSimpleCompoundStructure`)
**siempre** hereda atributos de WallType (OpeningWrapping, EndCap por capa) que
`FloorType.SetCompoundStructure` rechaza. **Solución que funciona**: reemplazar solo
las capas del CS que el FloorType ya trae:
```python
cs = ft.GetCompoundStructure()
cs.SetLayers(net_layers)            # NetList[CompoundStructureLayer]
ft.SetCompoundStructure(cs)
```
En capas de losa usar `MaterialFunctionAssignment.Substrate` / `.Membrane` /
`.Structure`. **No** usar `.Finish1`/`.Finish2` (activan OpeningWrapping → mismo error;
son válidos solo en WallType).
> Aplicado en `gen_familias._CODE_LOSA_TIPO`. Verificación final en Revit: pendiente.

### Columnas / Vigas / Zapatas (FamilyInstance estructural)
```python
from Autodesk.Revit.DB.Structure import StructuralType
doc.Create.NewFamilyInstance(pt, sym, lvl, StructuralType.Column)              # columna
doc.Create.NewFamilyInstance(Line.CreateBound(p1,p2), sym, lvl, StructuralType.Beam)  # viga
doc.Create.NewFamilyInstance(pt, sym, lvl, StructuralType.Footing)            # zapata
```
- Activar el símbolo antes de instanciar: `if not sym.IsActive: sym.Activate()`
  (idealmente `doc.Regenerate()` después).
- **No mutar parámetros de tipo dentro del loop de creación**: afectan a todas las
  instancias retroactivamente. Crear un `FamilySymbol` por sección con
  `sym.Duplicate(nombre)` *antes* del loop.

### Escaleras reales — StairsEditScope (NO existe `Stairs.Create`)
```python
scope = StairsEditScope(doc, "nombre")
stair_id = scope.Start(lvl_bot.Id, lvl_top.Id)   # devuelve Id de la escalera nueva
with Transaction(doc, "tramos") as tr:           # los runs van DENTRO de una Transaction
    tr.Start()
    doc.GetElement(stair_id).DesiredRisersNumber = n
    StairsRun.CreateStraightRun(doc, stair_id, line, StairsRunJustification.Center)
    tr.Commit()
scope.Commit(_StairFailures())                    # IFailuresPreprocessor, no FailureHandlingOptions
```
- La Z de la línea de cada run debe ser ≥ elevación base de la escalera. Tramo 1
  Z = `lvl_bot.Elevation`; tramo 2 Z = base + altura/2. Z=0 rompe en pisos altos.
- Riser count derivado de la altura **real** del tramo (PB→P01 usa `altura_pb`).
> Aplicado en `gen_arquitectura._CODE_CIRC`.

### Shaft openings (ascensores, ductos)
```python
doc.Create.NewOpening(lvl_bottom, lvl_top, CurveArray)   # hueco vertical multinivel
```

### Rooms y Spaces
```python
doc.Create.NewRoom(lvl, UV(m_to_ft(x), m_to_ft(y)))      # Room (arquitectura)
doc.Create.NewSpace(lvl, UV(m_to_ft(x), m_to_ft(y)))     # Space (MEP)
```
El constructor `Space(doc, lvl, XYZ)` **no** existe en Revit 2024+. Un Room sin
recinto cerrado se crea igual pero con `Area == 0`.

### Vistas
```python
ViewPlan.Create(doc, vft.Id, lvl.Id)                     # planta
ViewSection.CreateSection(doc, vft.Id, bbox)             # corte/fachada (BoundingBoxXYZ con Transform)
View3D.CreateIsometric(doc, vft.Id)                      # 3D
```
`ViewFamilyType` se busca por `t.ViewFamily == ViewFamily.FloorPlan/StructuralPlan/Section/ThreeDimensional`.
**Verificar nombre duplicado antes de crear** (otro script puede haber creado "PLANTA P01").

### Sheets, Viewports, Schedules
```python
sheet = ViewSheet.Create(doc, titleBlock.Id)
Viewport.Create(doc, sheet.Id, view.Id, XYZ_centro)      # validar sheet.CanAddViewToSheet(view)
sch = ViewSchedule.CreateSchedule(doc, ElementId(int(BuiltInCategory.OST_Rooms)))
# campos disponibles: {f.ParameterId: f for f in sch.Definition.GetSchedulableFields()}
```

### Tags, Dimensiones, TextNote
```python
IndependentTag.Create(doc, view.Id, Reference(elem), False,
                      TagMode.TM_ADDBY_ELEMENT, TagOrientation.Horizontal, XYZ(x,y,0))
# 7º argumento es XYZ, NO UV.

doc.Create.NewDimension(view, dim_line, refArray)        # refArray: ReferenceArray
# referencias útiles: loc.Curve.GetEndPointReference(0/1)

# Símbolo de anotación 2D (Norte, detalle): overload SIN StructuralType
doc.Create.NewFamilyInstance(pt, annoSym, view)

# TextNote requiere un TextNoteType válido (InvalidElementId falla)
tnt = FilteredElementCollector(doc).OfClass(TextNoteType).FirstElement()
TextNote.Create(doc, view.Id, pt, texto, TextNoteOptions(tnt.Id))
```

---

## 5. Errores conocidos → solución

| Síntoma | Causa | Solución |
|--------|-------|----------|
| `wrong EndCap condition for this element type` | CS creado desde cero con atributos de muro asignado a FloorType | `ft.GetCompoundStructure()` + `SetLayers` (§4) |
| `FloorType` base resulta ser techo/fundación | `OfClass(FloorType)` no filtra categoría | `WherePasses(ElementCategoryFilter(OST_Floors))` |
| `TypeError` / método no acepta lista | PythonNet3 no marshalea `IList<T>` | `NetList[T]` (§2) |
| `OverflowException` con ElementId | `.IntegerValue` (Int32) obsoleto | usar `.Value` (Int64) |
| `Stairs.Create` no existe | API mal recordada | `StairsEditScope.Start` (§4) |
| Escalera rompe en pisos altos | Z del run < base de escalera | Z = `lvl_bot.Elevation` / base+altura/2 |
| Anotación 2D no se coloca / error de host | overload con `StructuralType` toma la View como host | `NewFamilyInstance(pt, sym, view)` |
| `TextNote.Create` falla silenciosamente | `TextNoteOptions(InvalidElementId)` | pasar un `TextNoteType.Id` real |
| Nodo Python falla recién en Revit | `SyntaxError` dentro de string `_CODE_*` | test `TestSintaxisCodigoEmbebido` |

---

## 6. Checklist al escribir un nodo nuevo

1. Imports de Revit API + RevitServices arriba; `doc` desde `DocumentManager`.
2. `IN[x]` saneados con `_fi/_ii/_si`.
3. Conversión de unidades en todo punto/longitud.
4. Listas → `NetList[T]` donde la API pida `IList<T>`.
5. `FamilySymbol.Activate()` antes de instanciar; no mutar tipos en loops.
6. Operaciones de modelo dentro de `Transaction` (las escaleras, dentro del scope).
7. `try/except` alrededor de cada creación frágil, acumulando errores en `OUT`.
8. Verificar duplicados por nombre antes de crear vistas/tipos.
9. Correr `pytest` (incluye compilación de los 28 nodos) antes de regenerar.

---

## 7. Fuentes

- Revit API Docs (no oficial, navegable): https://www.revitapidocs.com/
- Creating and Editing Stairs (Autodesk): https://help.autodesk.com/cloudhelp/2018/ENU/Revit-API/Revit_API_Developers_Guide/Revit_Geometric_Elements/Stairs_and_Railings/Creating_and_Editing_Stairs.html
- Dynamo BIM (foros + docs): https://dynamobim.org/
- Dynamo Primer (Python + Revit API): https://primer.dynamobim.org/
- The Building Coder (blog de referencia API): https://thebuildingcoder.typepad.com/

---

*Última actualización: 2026-06-10 — seed inicial tras auditoría de los 9 generadores.*
