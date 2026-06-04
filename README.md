# py-building-gen

Generador paramétrico de proyectos BIM para Revit 2027. Produce edificios residenciales completos —arquitectura, estructura, instalaciones, documentación técnica y presupuesto— a partir de parámetros definidos por el usuario, mediante 13 scripts Dynamo 4.0 + PythonNet3.

El output es un modelo BIM navegable en Revit con láminas A3 (formato IRAM), schedules de áreas y aberturas, y un presupuesto completo en Excel + PDF, listo para portfolio profesional o académico.

---

## Inicio rápido

```bash
git clone https://github.com/federicoarielcasado/py-building-gen.git
cd py-building-gen
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

# Generar todos los scripts .dyn + Excel + PDF con valores default
python generar.py
```

Los archivos se escriben en `output/dynamo/` y `output/computo/`. Luego ejecutar en Revit en el orden que muestra el resumen impreso.

---

## Parámetros del usuario

Todos los parámetros se definen en `core/parametros.py` como un dataclass. Se pueden cargar y guardar en formato `.pbg` (JSON):

```bash
python generar.py --save mi_edificio.pbg   # guardar configuración actual
python generar.py --load mi_edificio.pbg   # cargar y generar
```

### Grupo 1 — Lote

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `frente` | `float` | `10.0` | Frente del lote en metros |
| `fondo` | `float` | `24.0` | Fondo del lote en metros |
| `usar_lote_real` | `bool` | `False` | Si `True`, lee vértices del GeoJSON de Caballito, CABA |

### Grupo 2 — Volumetría

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `pisos_tipo` | `int` | `6` | Cantidad de pisos tipo repetidos (1–20) |
| `altura_pb` | `float` | `3.50` | Altura libre planta baja en metros (mín. 2.60 CABA) |
| `altura_tipo` | `float` | `2.80` | Altura libre pisos tipo en metros (mín. 2.60 CABA) |
| `tiene_subsuelo` | `bool` | `False` | Agrega niveles de subsuelo |
| `cant_subsuelos` | `int` | `0` | Cantidad de subsuelos (0, 1 o 2) |
| `tiene_azotea` | `bool` | `True` | Agrega nivel y losa de azotea |

### Grupo 3 — Programa

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `tipo_pb` | `str` | `"porteria"` | Uso de planta baja: `"comercial"` \| `"porteria"` \| `"vivienda"` \| `"mixto"` |
| `tiene_cochera` | `bool` | `False` | Incluye cochera |
| `cochera_ubicacion` | `str` | `"pb"` | `"pb"` \| `"subsuelo"` |
| `cant_ascensores` | `int` | `1` | Cantidad de ascensores (1–2) |
| `cant_cajas_escalera` | `int` | `1` | Cantidad de cajas de escalera (1–2) |
| `sala_maquinas` | `str` | `"azotea"` | Ubicación sala de máquinas: `"azotea"` \| `"subsuelo"` |

### Grupo 4 — Departamentos por piso

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `cant_depto_tipo` | `int` | `2` | Departamentos por piso tipo |
| `mix_tipologias` | `list[TipologiaDepto]` | `[2amb×1, 3amb×1]` | Tipología y cantidad de deptos por piso |

Tipologías disponibles: `"1amb"`, `"2amb"`, `"3amb"`, `"4amb"`, `"duplex"`, `"estudio"`.

```python
# Ejemplo: 4 deptos por piso con mix
mix_tipologias = [
    TipologiaDepto(tipo="1amb", cantidad=2, superficie_m2=38),
    TipologiaDepto(tipo="2amb", cantidad=2, superficie_m2=55),
]
```

### Grupo 5 — Estructura

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `sistema_estructural` | `str` | `"porticos"` | `"porticos"` \| `"muros"` \| `"mixto"` |
| `hormigon_tipo` | `str` | `"H-21"` | Resistencia del hormigón: `"H-21"` \| `"H-25"` \| `"H-30"` |
| `acero_tipo` | `str` | `"ADN 420"` | Tipo de acero: `"ADN 420"` \| `"AL 220"` |

### Grupo 6 — Instalaciones

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `instalacion_sanitaria` | `bool` | `True` | Activa rubro sanitaria en cómputo y artefactos |
| `instalacion_electrica` | `bool` | `True` | Activa tableros eléctricos y rubro electrica |
| `instalacion_gas` | `bool` | `True` | Activa rubro gas en cómputo |
| `instalacion_incendio` | `bool` | `True` | Activa matafuegos en Revit y rubro incendio |
| `instalacion_termomecanica` | `bool` | `False` | Activa rubro termomecánica en cómputo |

### Grupo 7 — Presupuesto y entrega

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `nombre_proyecto` | `str` | `"Edificio Caballito"` | Aparece en title block y portada del presupuesto |
| `autor` | `str` | `"Federico A. Casado"` | Aparece en láminas y PDF |
| `incluir_honorarios` | `bool` | `True` | Suma honorarios profesionales al total |
| `incluir_gastos_generales` | `bool` | `True` | Suma gastos generales al total |
| `moneda` | `str` | `"ARS"` | `"ARS"` \| `"USD"` — moneda de las planillas |

---

## Scripts Dynamo — qué produce cada uno y qué parámetros lo controlan

### 00 — Familias y tipos
**Archivo:** `00_familias.dyn` · **Ejecutar siempre primero**

Prepara el modelo Revit antes de crear geometría. Si un tipo ya existe, lo actualiza; no crea duplicados.

**Crea:**
- **6 tipos de muro** con capas de material definidas:
  - Muro exterior 200mm (revoque 15mm + ladrillo 170mm + revoque 15mm)
  - Tabique interior 100mm
  - Medianera 200mm
  - Muro cortafuego 200mm (REI-120, CABA Art. 6.1)
  - Muro shaft HA 300mm (REI-180, caja escalera/ascensor)
  - Tabique baño 100mm (con capa de membrana hidrófuga)
- **2 tipos de losa** con espesor calculado por predimensionado CIRSOC
- **Materiales:** hormigones H-21/H-25/H-30, aceros, ladrillo, revoques, membrana asfáltica
- **Tipos estructurales:** Columna HA y Viga HA con secciones del predimensionado

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `hormigon_tipo` | Determina el nombre del material de hormigón usado en losas, shaft y tipos estructurales |
| `acero_tipo` | Determina el material de armadura en los tipos estructurales |
| `pisos_tipo`, `frente`, `fondo` | Vía predimensionado: calculan el espesor de losa y las secciones de columna/viga |

> **Aviso:** si el template no tiene familia de columna/viga HA rectangular cargada, el nodo retorna instrucciones para cargarla manualmente desde *Insertar → Cargar familia*. Hacerlo antes de correr el script 04.

---

### 01 — Niveles y grilla
**Archivo:** `01_niveles_grilla.dyn`

**Crea:**
- **Niveles** en Revit con nombre y elevación exacta
- **Grilla estructural** con ejes A-B-C (dirección Y) y 1-2-N (dirección X)
- **Plantas de documentación** por disciplina (ARQ / EST / MEP) para cada nivel

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `pisos_tipo` | Crea niveles PB + P01 a P0N |
| `altura_pb` | Elevación de P01 = `altura_pb` |
| `altura_tipo` | Elevación de P0i = `altura_pb + (i-1) × altura_tipo` |
| `tiene_subsuelo` / `cant_subsuelos` | Agrega SS01, SS02 a elevaciones negativas |
| `tiene_azotea` | Agrega nivel AZO a `altura_pb + pisos_tipo × altura_tipo` |
| `frente` | Ejes A-B-C hasta `frente`, con paso de 5.00m |
| `fondo` | Ejes 1-2-N hasta `fondo`, con paso de 5.00m |

**Ejemplo (valores default):**

```
PB  →  ±0.00 m
P01 →  +3.50 m
P02 →  +6.30 m
...
P06 → +17.50 m
AZO → +20.30 m
Ejes: A (0m), B (5m), C (10m) × 1 (0m), 2 (5m), 3 (10m), 4 (15m), 5 (20m), 6 (24m¹)
```
¹ El último eje se ubica exactamente en el límite del lote.

---

### 02 — Muros (distribución interna completa)
**Archivo:** `02_muros_perimetrales.dyn`

El script más complejo. Genera toda la mampostería del edificio respetando la normativa CABA.

**Geometría calculada internamente:**

```
Núcleo de circulación (centrado):
  ancho_nucleo = cant_escaleras × 3.0m + cant_ascensores × 2.0m
  x_nucleo     = (frente - ancho_nucleo) / 2
  y_nucleo     = fondo - 5.5m        ← frente del shaft
  y_pasillo    = y_nucleo - 1.2m     ← muro que separa deptos del pasillo
  apt_ancho    = frente / cant_depto_tipo
```

**Crea (por piso tipo):**

| Zona | Tipo de muro | Cantidad |
|------|-------------|----------|
| Perímetro exterior | Muro exterior 200mm | 4 |
| Núcleo circulación (frente + laterales + div. esc/asc) | Muro exterior 200mm | 3–4 |
| Pasillo común (1.20m — mínimo CABA) | Tabique 100mm | 1 |
| Divisoria entre deptos | Cortafuego 200mm REI-120 | `cant_depto_tipo - 1` |
| Tabiques internos por depto (zona living, dorms, servicio) | Tabique 100mm | 3–5 por depto |

**Layout interno por tipología** (proporciones sobre la profundidad útil `y_pasillo`):

| Tipología | Zona living | Zona dormitorios | Zona servicio |
|-----------|------------|-----------------|--------------|
| `1amb` / `estudio` | — (único ambiente) | — | 35–30% |
| `2amb` | 40% | 30% | 30% |
| `3amb` | 38% | 30% + muro divisor dorms | 32% |
| `4amb` / `duplex` | 35% | 30% + 2 muros divisores | 35% |

**PB** solo genera: perímetro + núcleo + pasillo (sin tabiques de departamentos).

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `frente`, `fondo` | Definen el rectángulo exterior y la profundidad del edificio |
| `altura_pb`, `altura_tipo` | Altura de los muros en cada nivel |
| `pisos_tipo` | Cantidad de pisos con distribución interna |
| `cant_depto_tipo` | Ancho de cada depto (`frente/cant_depto_tipo`) y número de divisorias |
| `mix_tipologias` | Determina qué tabiques internos se crean en cada depto |
| `cant_cajas_escalera`, `cant_ascensores` | Tamaño y posición del núcleo de circulación |

---

### 03 — Losas
**Archivo:** `03_losas.dyn`

**Crea:**
- Una losa por nivel (P01 a P0N, más AZO si corresponde)
- Cada losa tiene **hueco de shaft** integrado en el contorno (doble CurveLoop)
- La losa de azotea incluye capa de membrana asfáltica + mortero de pendiente

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `frente`, `fondo` | Contorno exterior de cada losa |
| `pisos_tipo` | Cantidad de losas de entrepiso |
| `tiene_azotea` | Agrega losa de azotea con tipo diferente |
| `hormigon_tipo`, `pisos_tipo` | Vía predimensionado: espesor de losa (h ≥ L/35, mín. 12cm) |
| `cant_cajas_escalera`, `cant_ascensores` | Tamaño del hueco de shaft cortado en cada losa |

---

### 04 — Estructura
**Archivo:** `04_estructura.dyn`

**Crea:**
- **Columnas HA** en cada nodo de la grilla, con reducción de sección en pisos superiores
- **Vigas HA** en las dos direcciones (X e Y) en cada nivel de entrepiso
- **Vigas de fundación** conectando las zapatas en la grilla (ambas direcciones, a -30cm del nivel de cimentación)
- **Zapatas aisladas** bajo cada columna al nivel de fundación

**Lógica de predimensionado CIRSOC 201-2005:**

```
Sección columna:     A ≥ N_total / (0.45 × f'c)   [mínimo 25×25cm]
Altura viga:         h ≥ L / 12                    [mínimo 40cm]
Ancho viga:          b = h / 2                     [mínimo 20cm]
Viga de fundación:   ≥ 30×60cm (CIRSOC mínimo)
```

**Reducción de sección en altura:** el script crea **dos `FamilySymbol` independientes** — uno para pisos inferiores y otro (5cm menor) para pisos superiores (>50% del total). Cada nivel usa el tipo correcto, de forma que la sección queda grabada en el modelo sin interferencias entre niveles.

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `frente`, `fondo` | Posición de columnas y vigas (grilla cada 5.0m) |
| `pisos_tipo` | Número de niveles con columnas y vigas |
| `altura_pb`, `altura_tipo` | Altura de columnas por nivel |
| `hormigon_tipo` | `f'c` → sección de columnas (H-30 = sección menor que H-21) |
| `acero_tipo` | `fy` → armadura, afecta precio en cómputo |
| `tiene_subsuelo` | Nivel de fundación para vigas y zapatas (PB o SS01) |

**Ejemplo (default H-21, 6 pisos, 10×24m):**

```
Columnas:          Col HA 35x35cm (pisos 1-3) + Col HA 30x30cm (pisos 4-6)
Vigas entrepiso:   45×85cm en toda la altura
Vigas fundación:   45×85cm en ambas direcciones a -30cm del nivel de cimentación
Zapatas:           120×120cm al nivel de cimentación exacto
Total:             105 columnas, 15 zapatas
```

---

### 05 — Aberturas
**Archivo:** `05_aberturas.dyn`

Usa las mismas constantes de geometría que el Script 02 para encontrar los muros donde insertar cada abertura.

**Crea:**
- **1 puerta de acceso** al edificio en fachada frontal de PB (centrada, 1.20×2.40m)
- **Ventanas de living** en fachada frontal por departamento por piso (ancho ≈ 55% del `apt_ancho`, 1.50m de alto)
- **Ventanas de dormitorios** en fachada frontal (1.20×1.20m), cantidad según tipología
- **Puertas de entrada** a cada departamento en el muro de pasillo (0.90×2.10m)
- **Puertas interiores** en el muro separador living/dormitorios (0.80×2.10m)

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `frente` | Posición X de ventanas (distribución por `apt_ancho`) |
| `fondo` | Posición Y del pasillo y puertas de entrada (`fondo - 5.5 - 1.2`) |
| `pisos_tipo` | Número de pisos con aberturas |
| `cant_depto_tipo` | Número de ventanas/puertas por piso |
| `mix_tipologias` | Determina cuántas ventanas de dormitorio (1 para 2amb, 2 para 3amb, 3 para 4amb) |
| `cant_cajas_escalera`, `cant_ascensores` | Posición del pasillo → posición de puertas de entrada |

**Ejemplo (default, por piso tipo):**

```
Ventanas living:      2 (una por depto)
Ventanas dormitorios: 3 (1 en depto 2amb, 2 en depto 3amb)
Puertas entrada:      2 (una por depto, en muro de pasillo)
Puertas interiores:   2 (una por depto, en muro living/dorm)
Total por piso:       9 aberturas × 6 pisos + 1 PB = 55 aberturas
```

---

### 06 — Escaleras y ascensores
**Archivo:** `06_escaleras_ascensores.dyn`

**Crea:**
- **Escalera real** (StairsEditScope API) por cada caja de escalera y por cada piso:
  - 2 tramos rectos + descanso intermedio de 1.10m (mínimo CABA)
  - Contrahuella calculada: `⌈altura_tipo / 17.5cm⌉` escalones (~16 para 2.80m)
  - Huella calculada: `(5.50m shaft - márgenes - descanso) / n_escalones` ≈ 26cm ≥ 25cm CABA
  - Baranda/pasamanos generados automáticamente por Revit al crear la escalera
- **Shaft opening** para cada ascensor (apertura rectangular en toda la altura del edificio)

> **Fallback automático:** si el template no contiene ningún `StairsType`, el script crea shaft openings rectangulares para la escalera y reporta el motivo en `OUT`.

**Geometría calculada internamente:**

```
n_risers   = ⌈altura_tipo / 0.175⌉      → 16 para 2.80m
run_length = (ESC_FONDO - 2×0.10 - 1.10) / 2  → 2.10m por tramo
huella_m   = run_length / (n_risers/2)   → 0.2625m ≈ 26cm ✓
```

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `frente`, `fondo` | Posición del núcleo centrado (misma fórmula que Scripts 02/03/05) |
| `cant_cajas_escalera` | Número de escaleras reales creadas |
| `cant_ascensores` | Número de shaft openings de ascensor |
| `altura_tipo` | Determina número de escalones y longitud de cada tramo |
| `pisos_tipo` | Número de pisos con escalera (PB→P01, P01→P02, etc.) |

---

### 07 — Instalaciones MEP
**Archivo:** `07_instalaciones_mep.dyn`

**Crea:**
- **MEP Space** por piso tipo (necesario para análisis de cargas en Revit MEP)
- **Matafuego** por piso en el pasillo junto al shaft (NFPA 13: 1 por piso)
- **Tablero eléctrico seccional** por piso en el pasillo (a 0.60m del matafuego)
- Inventario de sistemas MEP disponibles en el template

Los artefactos se buscan por familia en el template. Si no existen, el nodo reporta el error sin interrumpir la ejecución.

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `pisos_tipo` | Número de pisos con MEP Space, matafuego y tablero |
| `frente`, `fondo`, `cant_cajas_escalera`, `cant_ascensores` | Posición del matafuego y tablero (x ≈ x_nucleo - 0.5m, y ≈ y_pasillo + 0.6m) |
| `instalacion_incendio` | Activa/desactiva colocación de matafuegos |
| `instalacion_electrica` | Activa/desactiva colocación de tableros seccionales |

---

### 08 — Vistas de documentación
**Archivo:** `08_vistas.dyn`

**Crea:**
- **Plantas de arquitectura** para cada nivel (PLANTA PB, PLANTA P01 … PLANTA AZO)
- **2 cortes:** A-A transversal (perpendicular al frente, a mitad del fondo) y B-B longitudinal
- **4 fachadas:** Principal (frente), Contrafrente, Lateral Izquierda, Lateral Derecha
- **1 vista 3D** isométrica general
- **Visibility overrides por disciplina** en todas las vistas:
  - Vistas ARQ (`PLANTA`, `CORTE`, `FACHADA`): estructura oculta (columnas, vigas, fundaciones)
  - Vistas EST (`EST …`): elementos ARQ ocultos (muros, losas, puertas, ventanas, escaleras)
  - Vistas MEP (`MEP …`): estructura oculta

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `pisos_tipo`, `tiene_azotea` | Número de plantas generadas |
| `frente`, `fondo` | Bounding box de cortes y fachadas (tamaño del encuadre) |
| `altura_total` (derivado) | Altura del campo de visión en cortes y fachadas |

---

### 09 — Láminas A3
**Archivo:** `09_sheets.dyn`

**Crea 13 láminas A3** con title block IRAM 4505, metadatos completos y la vista correspondiente colocada centrada:

| Lámina | Contenido |
|--------|-----------|
| A-01 | ARQ — Planta Baja |
| A-02 | ARQ — Planta Tipo P01 |
| A-03 | ARQ — Planta Azotea |
| A-04 | ARQ — Corte A-A |
| A-05 | ARQ — Corte B-B |
| A-06 | ARQ — Fachada Principal |
| A-07 | ARQ — Fachada Contrafrente |
| A-08 | ARQ — Fachadas Laterales |
| E-01 | EST — Planta Fundaciones |
| E-02 | EST — Planta Estructura Tipo |
| M-01 | MEP — Instalaciones PB |
| M-02 | MEP — Instalaciones Piso Tipo |
| G-01 | Vista 3D General |

También coloca en el proyecto:
- **Símbolo de norte** en la vista PLANTA PB (busca familia "North Arrow" / "Flecha Norte" / "arrow" en anotaciones genéricas del template)
- **Cuadro de superficies** como TextNote en la lámina A-01, con: lote, superficie útil/piso, circulación y superficie total construida

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `nombre_proyecto` | Aparece en el campo *Project Name* del title block |
| `autor` | Aparece en los campos *Drawn By* y *Designed By* |
| `tiene_azotea` | Si `False`, la lámina A-03 queda sin vista asignada |
| `frente`, `fondo`, `pisos_tipo` | Datos del cuadro de superficies |

> El script busca title blocks con las palabras "iram", "a3" o "A3" en el nombre. Si el template no tiene ninguno, el nodo retorna un mensaje indicando qué cargar. El símbolo de norte se omite silenciosamente si no hay familia compatible en el template.

---

### 09b — Anotaciones
**Archivo:** `09b_anotaciones.dyn`

**Crea:**
- **Room tags** con nombre y área en cada planta tipo (un tag por Room creado)
- **Tags de puertas y ventanas** en la vista PLANTA P01
- **Dimensiones** del frente del edificio en la planta de PB

> El sistema de dimensiones en Revit requiere referencias a caras de muro. Si los muros no fueron creados por el Script 02, el nodo de dimensiones informa el error sin interrumpir el resto.

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `pisos_tipo` | Niveles donde se colocan room tags |
| `frente`, `fondo` | Línea de cota del frente del edificio |

---

### 10 — Schedules (tablas de cómputo)
**Archivo:** `10_schedules.dyn`

**Crea 7 tablas de cómputo** en Revit con campos completos:

| Tabla | Campos incluidos |
|-------|----------------|
| Locales y Áreas | Nombre, Número, Nivel, Área, Perímetro |
| Puertas | Mark, Familia/Tipo, Nivel, Ancho, Alto |
| Ventanas | Mark, Familia/Tipo, Nivel, Ancho, Alto |
| Muros | Tipo, Nivel base, Área, Longitud |
| Losas | Tipo, Nivel, Área |
| Columnas | Mark, Tipo, Nivel base, Altura |
| Vigas | Mark, Tipo, Longitud |

Las tablas se populan automáticamente con los elementos creados por los scripts anteriores. Requiere que Script 11 (Rooms) haya corrido para que la tabla de áreas tenga datos.

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `pisos_tipo` | Número de pisos incluidos en la tabla |

---

### 11 — Habitaciones (Rooms)
**Archivo:** `11_habitaciones.dyn`

Crea objetos **Room** en Revit para cada local de cada departamento. Los Rooms son la base de los schedules de área y los room tags de las láminas.

**Crea (por piso tipo):**

| Tipología | Rooms creados |
|-----------|--------------|
| `1amb` / `estudio` | Living-Dormitorio · Cocina · Baño |
| `2amb` | Living-Comedor · Dormitorio Principal · Cocina · Baño |
| `3amb` | Living-Comedor · Dormitorio 1 · Dormitorio 2 · Cocina · Baño 1 |
| `4amb` / `duplex` | Living-Comedor · Dormitorio Principal · Dormitorio 1 · Dormitorio 2 · Cocina · Baño 1 |

Cada Room recibe número en formato `{piso}{depto}{secuencial}` (ej: `1A02` = Piso 1, Depto A, local 2).

**Parámetros que lo controlan:**

| Parámetro | Efecto |
|-----------|--------|
| `frente`, `fondo`, `cant_cajas_escalera`, `cant_ascensores` | Posición del centroide de cada Room (calculado con la misma geometría del Script 02) |
| `pisos_tipo` | Número de pisos con Rooms |
| `cant_depto_tipo`, `mix_tipologias` | Número y tipo de Rooms por piso |

---

## Cómputo y presupuesto

Generado automáticamente por `python generar.py` en `output/computo/`.

### Archivos generados

- **`presupuesto_<proyecto>.xlsx`** — 18+ hojas:
  - *RESUMEN EJECUTIVO*: tabla de rubros con subtotales, totales y porcentajes
  - *01 Trabajos preliminares* a *15 Equipamiento*: una hoja por rubro con descripción, unidad, cantidad, precio unitario y subtotal
  - *CURVA DE INVERSIÓN*: distribución mensual estimada en 18 meses con gráfico de barras

- **`presupuesto_<proyecto>.pdf`** — documento de presentación con tabla de rubros, notas de alcance y fuentes de precios

### Rubros incluidos

| # | Rubro | Unidad base |
|---|-------|------------|
| 1 | Trabajos preliminares | gl, m², m |
| 2 | Movimiento de suelos | m³ |
| 3 | Fundaciones | m³ HA, kg acero |
| 4 | Estructura (columnas, vigas, losas) | m³ HA, kg acero, m² enc. |
| 5 | Mampostería | m² |
| 6 | Revoques y revestimientos | m² |
| 7 | Carpinterías (puertas, ventanas) | u |
| 8 | Cubiertas e impermeabilizaciones | m² |
| 9 | Instalación sanitaria* | m, gl, u |
| 10 | Instalación eléctrica* | m, u |
| 11 | Instalación de gas* | m, u |
| 12 | Instalación contra incendio* | m, u |
| 13 | Instalación termomecánica* | u |
| 14 | Pintura y terminaciones | m² |
| 15 | Equipamiento (ascensores, tanques) | u |

\* Se incluye solo si el parámetro `instalacion_X = True`.

**Índices de precios:** UOCRA Zona A 2026 (mano de obra) · ICC INDEC 2026 (materiales) · Sismat.com.ar (materiales específicos)

**Ejemplo con valores default** (10×24m, 6 pisos, 12 deptos):

```
Costo directo:      ARS 692.433.063
Gastos generales:   ARS 138.486.613
Honorarios:         ARS  83.091.968
TOTAL PRESUPUESTO:  ARS 914.011.644
```

### Parámetros que afectan el cómputo

| Parámetro | Efecto |
|-----------|--------|
| `frente`, `fondo` | Superficie del lote, perímetro, volúmenes base de todos los rubros |
| `pisos_tipo`, `tiene_azotea` | Superficie total construida → todos los rubros |
| `hormigon_tipo` | Precio del m³ de HA en rubros 3 y 4 |
| `acero_tipo` | Precio del kg de acero en rubros 3 y 4 |
| `cant_departamentos_total` | Rubros de carpinterías, artefactos sanitarios, instalaciones |
| `cant_ascensores` | Rubro 15 — precio de ascensores |
| `instalacion_*` | Activa/desactiva los rubros 9–13 |
| `incluir_gastos_generales` | Suma 20% sobre costo directo |
| `incluir_honorarios` | Suma 10% sobre (costo directo + GG) |
| `moneda` | Encabezados del Excel y PDF; conversión USD vía tipo de cambio BNA |

---

## Estructura del proyecto

```
py-building-gen/
├── generar.py                     # CLI: genera .dyn + Excel + PDF (un comando)
├── main.py                        # Entry point PyQt6 (UI)
├── core/
│   ├── parametros.py              # Dataclass ParametrosEdificio
│   ├── predimensionado.py         # Cálculo estructural CIRSOC 201-2005
│   ├── generadores/
│   │   ├── gen_familias.py        # Script 00 — materiales y tipos
│   │   ├── gen_niveles.py         # Script 01 — niveles, grilla, plantas disciplina
│   │   ├── gen_arquitectura.py    # Scripts 02 (muros), 03 (losas), 05 (aberturas), 06 (escaleras)
│   │   ├── gen_estructura.py      # Script 04 — columnas, vigas, vigas fund., zapatas
│   │   ├── gen_instalaciones.py   # Script 07 — MEP spaces, matafuegos, tableros
│   │   ├── gen_vistas.py          # Script 08 — plantas, cortes, fachadas, visibility overrides
│   │   ├── gen_sheets.py          # Scripts 09 (sheets + norte + cuadro), 10 (schedules)
│   │   ├── gen_habitaciones.py    # Script 11 — Room objects por local y tipología
│   │   └── gen_anotaciones.py     # Script 09b — room tags, tags aberturas, dimensiones
│   ├── computo/
│   │   ├── mediciones.py          # Cálculo de cantidades
│   │   ├── precios.py             # Catálogo de precios (UOCRA + INDEC + Sismat)
│   │   ├── analisis_precios.py    # Análisis de precios unitarios
│   │   └── exportador.py          # Export Excel (.xlsx) y PDF
│   └── dynamo/
│       └── dyn_builder.py         # Constructor de archivos .dyn (JSON)
├── data/
│   ├── normativa/
│   │   ├── cirsoc_101_cargas.json
│   │   ├── cirsoc_201_2005.json
│   │   └── codigo_edificacion_caba.json
│   ├── precios/
│   │   ├── icc_indec_2026.json
│   │   ├── uocra_2026.json
│   │   └── materiales_sismat.json
│   └── lote/
│       ├── caballito_parcela.geojson
│       └── topografia.csv
├── output/
│   ├── dynamo/                    # Scripts .dyn generados
│   └── computo/                   # Excel y PDF de presupuesto
├── tests/
└── requirements.txt
```

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Interfaz de usuario | Python 3.10+ · PyQt6 |
| CLI de generación | Python · argparse |
| Generación de scripts | Python · JSON (formato .dyn) |
| Motor BIM | Autodesk Revit 2027 |
| Scripting BIM | Dynamo 4.0 · PythonNet3 (CPython3) |
| Predimensionado | NumPy · CIRSOC 201-2005 |
| Cómputo y presupuesto | openpyxl · reportlab |
| Geoespacial | shapely · pyproj · ezdxf |
| Visualización previa | matplotlib |
| Tests | pytest (70 tests) |

---

## Compatibilidad Revit / Dynamo

- **Revit:** 2027 (API Revit 2024+ — usa `ElementId.Value` en lugar de `.IntegerValue`)
- **Dynamo:** 4.0 integrado en Revit 2027
- **Motor Python en Dynamo:** PythonNet3 (CPython3) — **CPython2/IronPython no compatible**
- **Template:** `Default_M_ESP.rte`

---

## Normativa de referencia

| Área | Normativa |
|------|-----------|
| Estructura HA | CIRSOC 201-2005 |
| Cargas y sobrecargas | CIRSOC 101 |
| Viento | CIRSOC 102 |
| Sismoresistencia | INPRES-CIRSOC 103 (zona sísmica CABA = 0) |
| Instalación sanitaria | Normas AySA 2023 · Código de Edificación CABA |
| Instalación eléctrica | AEA · IRAM 2281 |
| Gas | NAG 200/211 (ENARGAS) |
| Incendio | NFPA 13 · NFPA 72 |
| Documentación | IRAM 4505 (title block A3) |
| Urbanística | Código de Planeamiento Urbano CABA — Zona R2b (FOT 2.4, FOS 0.60) |
| Locales habitables | Código de Edificación CABA Art. 4.1 (ilum. 1/8, vent. 1/16 de sup.) |

---

## Fixes técnicos — API Revit 2027 / Dynamo 4.0 / PythonNet3

Bugs corregidos tras revisión sistemática de todos los generadores contra la API de Revit 2024+:

| Script | Fix | Causa raíz |
|--------|-----|------------|
| `00_familias` — Crear Floor Types | `FA.Finish1` reemplazado por `FA.Substrate` (carpeta) y `FA.Membrane` (membrana) en `CompoundStructure` para `FloorType` | `Finish1`/`Finish2` activan `OpeningWrapping` en walls; aplicado a un `FloorType` Revit lanza `"wrong EndCap condition"` |
| `04_estructura` — Columnas | Dos `FamilySymbol` separados (`Col HA 35x35cm` / `Col HA 30x30cm`) en lugar de mutar el tipo dentro del loop | `set_section()` modifica parámetros de tipo → todas las instancias quedan con la sección del último nivel procesado |
| `04_estructura` — Vigas de fundación | `z = lvl_fund.Elevation + m_to_ft(Z_OFFSET)` (relativo al nivel) | Z absoluto = -0.30m colocaba vigas a 2.50m por encima del nivel SS01 cuando `tiene_subsuelo=True` |
| `04_estructura` — Zapatas | `pt = XYZ(x, y, lvl_fund.Elevation)` (relativo al nivel) | Z = 0 absoluto colocaba zapatas fuera del nivel de cimentación cuando había subsuelo |
| `07_instalaciones` — MEP Spaces | `doc.Create.NewSpace(lvl, UV(x, y))` | El constructor `Space(doc, lvl, XYZ)` no existe en Revit 2024+; `NewSpace` es el método canónico |
| `08_vistas` — Plantas | Chequeo de existencia antes de `ViewPlan.Create` | El script 01 ya crea `"PLANTA PB"`, `"PLANTA P01"`, etc.; intentar crearlas de nuevo lanzaba `ArgumentException: Name is already in use` |
| `09_sheets` — Láminas EST/MEP | Filtros corregidos: `"EST PB"` / `"MEP PB"` en lugar de `"PLANTA PB"` | Las láminas estructurales y MEP recibían vistas arquitectónicas por coincidencia de nombre |
| `09b_anotaciones` — Tags | `XYZ(pt.X, pt.Y, 0)` en lugar de `UV(pt.X, pt.Y)` en `IndependentTag.Create` | La firma de `IndependentTag.Create` requiere `XYZ` como 7.° argumento; `UV` lanzaba `ArgumentException` |
| `09b_anotaciones` — Dimensiones | `WallSide` importado en bloque de imports del nodo | Import dinámico `__import__(...)` dentro de un list comprehension no es confiable en PythonNet3 |

---

## Licencia

MIT — ver [LICENSE](LICENSE).
