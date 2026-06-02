# py-building-gen — Claude Code Instructions

## Resumen del proyecto

Aplicación de escritorio en PyQt6 que genera scripts Dynamo (.dyn) para Autodesk Revit 2027, a partir de parámetros ingresados por el usuario. El proyecto produce un edificio residencial paramétrico completo, incluyendo arquitectura, estructura, instalaciones y documentación técnica, emplazado en un lote real de CABA, Argentina.

El output final es un portfolio profesional compuesto por láminas A3 en formato IRAM y un sitio web en GitHub Pages.

---

## Contexto del desarrollador

- **Nombre:** Federico Ariel Casado
- **Stack Python:** PyQt6, pandas, numpy, openpyxl, matplotlib, ezdxf, SQLAlchemy
- **Software CAD/BIM:** Autodesk Revit 2027, AutoCAD, Civil 3D
- **Dynamo:** versión integrada en Revit 2027 — **Dynamo 4.0**, motor **PythonNet3** por defecto (CPython3 ya no se admite en Dynamo 4.0)
- **Render:** Blender (export FBX desde Revit)
- **Clash detection:** Navisworks Manage 2027
- **OS:** Windows

---

## Arquitectura del proyecto

```
py-building-gen/
├── main.py                  # Entry point PyQt6
├── ui/
│   ├── main_window.py       # Ventana principal
│   ├── tabs/
│   │   ├── tab_lote.py          # Parámetros del lote
│   │   ├── tab_arquitectura.py  # Parámetros arquitectónicos
│   │   ├── tab_estructura.py    # Parámetros estructurales
│   │   ├── tab_instalaciones.py # Parámetros de instalaciones
│   │   └── tab_presupuesto.py   # Configuración de cómputo
│   └── widgets/
│       ├── preview_widget.py    # Previsualización planta (matplotlib)
│       └── predim_widget.py     # Resultados de predimensionado
├── core/
│   ├── parametros.py        # Dataclass con todos los parámetros del proyecto
│   ├── predimensionado.py   # Cálculo estructural previo (CIRSOC 201-2005)
│   ├── generadores/
│   │   ├── gen_niveles.py       # Genera script: niveles y grilla
│   │   ├── gen_arquitectura.py  # Genera script: muros, losas, aberturas
│   │   ├── gen_estructura.py    # Genera script: columnas, vigas, losas
│   │   ├── gen_instalaciones.py # Genera script: MEP básico
│   │   ├── gen_vistas.py        # Genera script: plantas, cortes, fachadas
│   │   └── gen_sheets.py        # Genera script: sheets y title blocks IRAM
│   ├── computo/
│   │   ├── mediciones.py        # Cómputo métrico por rubro
│   │   ├── precios.py           # Base de precios (INDEC ICC + UOCRA 2026)
│   │   ├── analisis_precios.py  # Análisis de precios unitarios
│   │   └── exportador.py        # Export a Excel y PDF
│   └── dynamo/
│       ├── dyn_builder.py       # Constructor de archivos .dyn (JSON)
│       └── templates/           # Templates base de scripts Dynamo
├── data/
│   ├── lote/
│   │   ├── caballito_parcela.geojson  # Parcela real de CABA (Buenos Aires Data)
│   │   └── topografia.csv             # Datos de elevación procesados en QGis
│   ├── precios/
│   │   ├── icc_indec_2026.json        # ICC INDEC actualizado
│   │   ├── uocra_2026.json            # Mano de obra UOCRA Zona A
│   │   └── materiales_sismat.json     # Precios materiales Sismat
│   ├── normativa/
│   │   ├── cirsoc_101_cargas.json     # Cargas y sobrecargas (CIRSOC 101)
│   │   └── cirsoc_201_2005.json       # Parámetros HA (CIRSOC 201-2005)
│   └── familias/
│       └── family_map.json            # Mapeo de familias Revit default
├── output/
│   ├── dynamo/                  # Scripts .dyn generados
│   ├── computo/                 # Excel y PDF de presupuesto
│   └── portfolio/               # Láminas A3 exportadas
├── tests/
└── requirements.txt
```

---

## Parámetros del proyecto (dataclass)

```python
@dataclass
class ParametrosEdificio:
    # Lote
    frente: float          # metros (típico CABA: 8.66 o 10.0)
    fondo: float           # metros (típico CABA: 24.0)
    usar_lote_real: bool   # True = usar geojson de Buenos Aires Data

    # Volumetría
    pisos_tipo: int        # Cantidad de pisos tipo (1-20)
    altura_pb: float       # Altura planta baja (default: 3.50m)
    altura_tipo: float     # Altura piso tipo (default: 2.80m)
    tiene_subsuelo: bool
    cant_subsuelos: int    # 0, 1 o 2
    tiene_azotea: bool

    # Planta baja
    tipo_pb: str           # "comercial" | "porteria" | "vivienda" | "mixto"
    tiene_cochera: bool
    cochera_ubicacion: str # "pb" | "subsuelo"

    # Servicios
    cant_ascensores: int   # 1 o 2
    cant_cajas_escalera: int  # 1 o 2
    sala_maquinas: str     # "azotea" | "subsuelo"

    # Departamentos por piso
    cant_depto_tipo: int   # Departamentos por piso tipo
    mix_tipologias: list   # [{"tipo": "2amb", "cantidad": 1}, ...]

    # Estructura
    sistema_estructural: str  # "porticos" | "muros" | "mixto"
    hormigon_tipo: str        # "H-21" | "H-25" | "H-30"
    acero_tipo: str           # "ADN 420" | "AL 220"

    # Instalaciones a generar
    instalacion_sanitaria: bool
    instalacion_electrica: bool
    instalacion_gas: bool
    instalacion_incendio: bool
    instalacion_termomecanica: bool

    # Presupuesto
    incluir_honorarios: bool
    incluir_gastos_generales: bool
    moneda: str            # "ARS" | "USD"
```

---

## Módulo de predimensionado (CIRSOC 201-2005)

El predimensionado se calcula **antes** de generar los scripts Dynamo. El usuario puede revisar y ajustar los resultados en la UI antes de proceder.

### Cargas (CIRSOC 101)
- Peso propio losa: 0.20m × 25 kN/m³ = 5.0 kN/m²
- Carpeta + piso: 1.5 kN/m²
- Tabiques: 1.0 kN/m²
- Sobrecarga vivienda: 2.0 kN/m² (CIRSOC 101 Tabla 4.1)
- Sobrecarga azotea no transitable: 1.0 kN/m²

### Predimensionado de elementos
```
Losas:       h ≥ L/35 (losa maciza), mínimo 0.12m
Vigas:       h ≥ L/12, b = h/2, mínimo 0.20×0.40m
Columnas:    A ≥ N_total / (0.45 × f'c), mínimo 0.25×0.25m
Zapatas:     A ≥ N_total / σ_adm (suelo tipo CABA: 1.5-2.0 kgf/cm²)
```

### Output del predimensionado
- Tabla de secciones por nivel
- Memoria de cálculo exportable a PDF
- Verificación de esbeltez y pandeo en columnas

---

## Generación de scripts Dynamo (.dyn)

### Formato
Los archivos `.dyn` son **JSON** (Dynamo 2.x+ abandonó XML). Cada generador produce un script independiente que se corre en orden dentro de Revit.

### Orden de ejecución (indicado en la UI)
1. `01_niveles_grilla.dyn` — Niveles, grilla estructural, ejes
2. `02_muros_perimetrales.dyn` — Muros exteriores e interiores
3. `03_losas.dyn` — Losas por nivel
4. `04_estructura.dyn` — Columnas y vigas
5. `05_aberturas.dyn` — Puertas y ventanas
6. `06_escaleras_ascensores.dyn` — Núcleos de circulación
7. `07_instalaciones_mep.dyn` — Sistemas MEP básicos
8. `08_vistas.dyn` — Plantas, cortes, fachadas, 3D
9. `09_sheets.dyn` — Sheets con title block IRAM
10. `10_schedules.dyn` — Tablas de cómputo en Revit

### Compatibilidad Revit 2027
- Dynamo version: **4.0** (integrado en Revit 2027)
- Python engine: **PythonNet3** — motor por defecto en Dynamo 4.0 (CPython3 ya no se admite)
- Usar `clr` (pythonnet) para importar librerías de Revit
- Imports obligatorios en cada Python node:
```python
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import *
import Autodesk.Revit.DB as DB
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
```

---

## Cómputo y presupuesto

### Rubros
1. Trabajos preliminares (obrador, demolición, limpieza)
2. Movimiento de suelos (excavación, relleno, compactación)
3. Fundaciones (excavación, hormigón, armadura)
4. Estructura (columnas, vigas, losas por nivel)
5. Mampostería (muros exteriores e interiores)
6. Revoques y revestimientos
7. Carpinterías (puertas y ventanas por tipo)
8. Cubiertas e impermeabilizaciones
9. Instalación sanitaria (por m² de planta)
10. Instalación eléctrica (por m² de planta)
11. Instalación de gas
12. Instalación contra incendio
13. Instalación termomecánica
14. Pintura y terminaciones
15. Equipamiento (ascensores, tanques, bombas)
16. Gastos generales (% sobre costo directo)
17. Honorarios profesionales (% según escala CAd/SCA)

### Precios de referencia
- **Mano de obra:** UOCRA Zona A 2026 — actualización mensual
- **Materiales:** ICC INDEC + Sismat.com.ar
- **Índice actualización:** CAC mensual
- **Moneda:** ARS con conversión opcional a USD (tipo de cambio oficial BNA)

### Análisis de precios unitarios
Cada ítem incluye:
- Materiales (cantidad × precio unitario)
- Mano de obra (jornal × rendimiento)
- Equipos (amortización + combustible)
- Total unitario
- Subtotal por rubro

### Exportación
- **Excel:** una hoja por rubro + resumen ejecutivo + curva de inversión
- **PDF:** formato de presentación con logo, datos del proyecto y tabla de rubros

---

## Normativa de referencia

### Estructural
- CIRSOC 201-2005 — Estructuras de Hormigón Armado
- CIRSOC 101 — Cargas y sobrecargas mínimas
- CIRSOC 102 — Acción del viento
- INPRES-CIRSOC 103 — Construcciones sismorresistentes (zona sísmica CABA: 0)

### Instalaciones
- **Sanitaria:** Normas AySA 2023 + Código de Edificación CABA
- **Eléctrica:** Reglamentación AEA + IRAM 2281
- **Gas:** NAG 200/211 (ENARGAS)
- **Incendio:** NFPA 13 + NFPA 72 (referencia académica UTN)

### Documentación técnica
- **Title block:** Formato IRAM 4505
- **Escalas:** Sistema métrico decimal
- **Láminas:** A3 horizontal (420 × 297 mm)
- **Capas AutoCAD:** Norma IRAM para dibujo técnico

---

## Datos geoespaciales del lote

### Fuente
- **Parcelas:** Buenos Aires Data — `data.buenosaires.gob.ar/dataset/parcelas`
- **Formato descarga:** Shapefile (.shp) o GeoJSON
- **Procesamiento:** QGis → exportar a CSV de vértices del lote
- **Barrio seleccionado:** Caballito, CABA
- **Lote típico:** 10.00m × 24.00m entre medianeras

### Integración con Revit
- Los vértices del lote se importan como `TopographySurface` en Revit vía Dynamo
- La topografía se genera desde los datos de elevación procesados en QGis
- Coordenadas en sistema de referencia: POSGAR 2007 / Faja 5 (EPSG:5347)

---

## Portfolio

### Estructura de capítulos
Cada capítulo es un trabajo independiente en el portfolio:

| # | Capítulo | Contenido | Herramientas |
|---|----------|-----------|--------------|
| 1 | Arquitectura | Plantas, cortes, fachadas, renders, detalles | Revit + Blender |
| 2 | Estructura | Predimensionado, planos estructurales, detalles armadura | Revit + AutoCAD |
| 3 | Inst. Sanitaria | Planos de agua fría/caliente, desagües, isométricos | Revit MEP + AutoCAD |
| 4 | Inst. Eléctrica | Tableros, circuitos, iluminación, diagrama unifilar | Revit MEP + AutoCAD |
| 5 | Inst. Gas | Esquema de distribución, planos de planta | AutoCAD |
| 6 | Inst. Incendio | Detección, rociadores, bocas de incendio | Revit MEP + AutoCAD |
| 7 | Clash Detection | Reporte de interferencias Navisworks | Navisworks |
| 8 | Cómputo y Presupuesto | Planillas por rubro, análisis de precios, curva inversión | Excel + PDF |

### Formatos de entrega
- **Láminas:** A3 horizontal, title block IRAM 4505, exportadas desde Revit/AutoCAD
- **Portfolio PDF:** compilado de todas las láminas por capítulo
- **Web:** GitHub Pages en `federicoarielcasado.github.io/py-building-gen`
- **Plataformas:** LinkedIn (sección Proyectos) + Behance + GitHub

---

## Convenciones de código

- Lenguaje: Python 3.10+ (scripts Dynamo también usan CPython 3 — sin excepciones)
- Estilo: PEP 8
- Docstrings: Google style
- Type hints: sí, en todo el código Python 3
- Tests: pytest para módulos de cómputo y predimensionado
- Git: un commit por módulo completado

---

## Orden de desarrollo sugerido

1. `core/parametros.py` — Dataclass completo
2. `core/predimensionado.py` — Lógica CIRSOC
3. `ui/` — Interfaz PyQt6 con previsualización matplotlib
4. `core/dynamo/dyn_builder.py` — Constructor XML base
5. `core/generadores/gen_niveles.py` — Primer script Dynamo
6. Generadores restantes en orden de ejecución
7. `core/computo/` — Módulo de presupuestación
8. `output/` — Exportadores Excel y PDF
9. Tests
10. Portfolio y documentación

---

## Recursos clave

| Recurso | URL |
|---------|-----|
| Dynamo Primer (Python + Revit API) | primer.dynamobim.org |
| Buenos Aires Data — Parcelas | data.buenosaires.gob.ar/dataset/parcelas |
| ICC INDEC | indec.gob.ar |
| UOCRA Zona A 2026 | miobra.com.ar/costo-mano-obra-uocra |
| Sismat (materiales) | sismat.com.ar |
| CIRSOC (reglamentos) | inti.gob.ar/areas/servicios-industriales/construcciones-e-infraestructura/cirsoc |
| AySA instalaciones sanitarias | grupoinsani.com.ar/reglamento-instalaciones-sanitarias-aysa-2025 |
| Navisworks Education | autodesk.com/education |
