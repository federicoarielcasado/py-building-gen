# py-building-gen

Generador paramétrico de proyectos BIM para Revit 2027. Produce edificios residenciales completos —arquitectura, estructura, instalaciones y documentación técnica— a partir de parámetros ingresados por el usuario, mediante scripts Dynamo 4.0 + PythonNet3.

El output es un modelo BIM navegable en Revit y un portfolio profesional compuesto por láminas A3 en formato IRAM, listo para presentación académica o profesional.

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Interfaz de usuario | Python 3.10+ · PyQt6 |
| Generación de scripts | Python · JSON (formato .dyn) |
| Motor BIM | Autodesk Revit 2027 |
| Scripting BIM | Dynamo 4.0 · PythonNet3 |
| Cómputo y presupuesto | pandas · openpyxl · reportlab |
| Geoespacial | shapely · pyproj · ezdxf |
| Visualización previa | matplotlib |
| Tests | pytest |

---

## Estructura del proyecto

```
py-building-gen/
├── main.py                        # Entry point PyQt6
├── ui/
│   ├── main_window.py
│   └── tabs/
│       ├── tab_lote.py
│       ├── tab_arquitectura.py
│       ├── tab_estructura.py
│       ├── tab_instalaciones.py
│       └── tab_presupuesto.py
├── core/
│   ├── parametros.py              # Dataclass ParametrosEdificio
│   ├── predimensionado.py         # CIRSOC 201-2005
│   ├── generadores/               # Generadores de scripts .dyn
│   ├── computo/                   # Cómputo métrico y presupuesto
│   └── dynamo/                    # Constructor de archivos .dyn
├── output/
│   └── dynamo/edificio_caballito/ # Scripts .dyn generados
├── data/
│   ├── normativa/                 # CIRSOC 101/201, cargas
│   ├── precios/                   # ICC INDEC, UOCRA, Sismat
│   ├── familias/                  # Mapeo de familias Revit
│   └── lote/                      # GeoJSON parcela CABA
├── tests/
├── requirements.txt
└── ejemplo_default.pbg
```

---

## Prerrequisitos

- Python 3.10+
- Autodesk Revit 2027 (con Dynamo 4.0 integrado)
- Template de Revit: `Default_M_ESP.rte`

---

## Instalación

```bash
git clone https://github.com/federicoarielcasado/py-building-gen.git
cd py-building-gen
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Uso

### 1. Generar los scripts Dynamo desde la UI

```bash
python main.py
```

Completar parámetros en las pestañas y hacer clic en **Generar**. Los scripts `.dyn` se escriben en `output/dynamo/<nombre_proyecto>/`.

### 2. Ejecutar los scripts en Revit

Abrir Revit → crear proyecto nuevo desde `Default_M_ESP.rte` → abrir Dynamo y correr los scripts en orden:

| # | Script | Qué crea |
|---|--------|----------|
| 00 | `00_familias.dyn` | Materiales, tipos de muro, losa y elementos estructurales |
| 01 | `01_niveles_grilla.dyn` | Niveles (PB, P01…P0N, AZO) y grilla estructural |
| 02 | `02_muros_perimetrales.dyn` | Muros exteriores, medianeras y tabiques |
| 03 | `03_losas.dyn` | Losas de entrepiso y azotea |
| 04 | `04_estructura.dyn` | Columnas y vigas de HA |
| 05 | `05_aberturas.dyn` | Puertas y ventanas en fachada |
| 06 | `06_escaleras_ascensores.dyn` | Shafts de escaleras y ascensores |
| 07 | `07_instalaciones_mep.dyn` | Espacios MEP por nivel |
| 08 | `08_vistas.dyn` | Plantas, cortes, fachada y vista 3D |
| 09 | `09_sheets.dyn` | Láminas A3 con title block |
| 10 | `10_schedules.dyn` | Tablas de cómputo en Revit |

---

## Parámetros del proyecto

```python
@dataclass
class ParametrosEdificio:
    # Lote
    frente: float           # metros
    fondo: float            # metros

    # Volumetría
    pisos_tipo: int
    altura_pb: float        # default 3.50m
    altura_tipo: float      # default 2.80m
    tiene_subsuelo: bool
    cant_subsuelos: int
    tiene_azotea: bool

    # Programa
    tipo_pb: str            # "comercial" | "porteria" | "vivienda" | "mixto"
    mix_tipologias: list    # [{"tipo": "2amb", "cantidad": 2}, ...]

    # Nivel de detalle (roadmap)
    nivel_detalle: str      # "masa" | "arquitectura" | "interior" | "full"
    calidad: str            # "estandar" | "premium" | "lujo"

    # Estructura
    sistema_estructural: str
    hormigon_tipo: str
    acero_tipo: str

    # Instalaciones
    instalacion_sanitaria: bool
    instalacion_electrica: bool
    instalacion_gas: bool
    instalacion_incendio: bool
    instalacion_termomecanica: bool

    # Presupuesto
    moneda: str             # "ARS" | "USD"
```

---

## Normativa de referencia

- **Estructural:** CIRSOC 201-2005 · CIRSOC 101 · INPRES-CIRSOC 103
- **Instalaciones:** Normas AySA 2023 · AEA · IRAM 2281 · NAG 200/211 · NFPA 13/72
- **Documentación:** IRAM 4505 · Código de Edificación CABA

---

## Roadmap

### Nivel de detalle variable (LOD)

El parámetro `nivel_detalle` controlará qué scripts se ejecutan:

- **`masa`** → scripts 00-03 (envolvente básica)
- **`arquitectura`** → scripts 00-10 (modelo completo sin mobiliario)
- **`interior`** → 00-10 + script de mobiliario con familias del sistema
- **`full`** → 00-10 + mobiliario diferenciado por calidad + materiales de terminación

### Script 11 — Mobiliario y ambientación

Generación automática de mobiliario por tipología de departamento y nivel de calidad:

- **Tipologías:** monoambiente, 2 ambientes, 3 ambientes, PH
- **Calidad estándar:** familias del sistema Revit (clonadas y ajustadas por parámetros)
- **Calidad premium/lujo:** familias de mayor detalle + materiales diferenciados
- **Espacios comunes:** hall de entrada, SUM, cocheras, circulaciones
- Estrategia de implementación: clonar familias existentes como base + DirectShape como fallback para piezas sin familia disponible

### Script 12 — Macro de ejecución secuencial

Macro de Revit (C#) que llama a la API de DynamoRevit para ejecutar los scripts en orden automáticamente, eliminando la carga manual uno a uno.

### Automatización de Dynamo Player

Integración con Dynamo Player para correr scripts sin abrir el grafo completo.

### Familias paramétricas personalizadas

Para piezas no disponibles en la biblioteca de Revit: generación de familias `.rfa` via `FamilyDocument API` desde Python. Geometría paramétrica (extrusiones, sweeps) con parámetros de tipo y de instancia.

### Portfolio web

Exportación automática de láminas A3 a PDF + generación de sitio estático en GitHub Pages con renders y documentación técnica.

---

## Lote de referencia

Parcela real en barrio Caballito, CABA, Argentina.

- **Fuente:** Buenos Aires Data — dataset de parcelas
- **Sistema de coordenadas:** POSGAR 2007 / Faja 5 (EPSG:5347)
- **Dimensiones típicas:** 10.00m × 24.00m entre medianeras

---

## Precios y presupuesto

- **Mano de obra:** UOCRA Zona A 2026
- **Materiales:** ICC INDEC + Sismat.com.ar
- **Índice de actualización:** CAC mensual
- **Moneda:** ARS con conversión opcional a USD (tipo de cambio BNA)

---

## Licencia

MIT — ver [LICENSE](LICENSE).
