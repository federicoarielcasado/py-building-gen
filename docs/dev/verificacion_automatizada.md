# Verificación automatizada de los scripts Dynamo

Objetivo: **dejar de abrir Revit y revisar a ojo el resultado de cada `.dyn`.**
En su lugar, los scripts se auto-reportan y un módulo Python decide PASS/FAIL.

El problema tiene dos mitades, y se resuelven por separado:

| Mitad | Estado | Cómo |
|-------|--------|------|
| **Revisar** si cada script funcionó | ✅ implementado (Fase 1) | auto-reporte JSON + `core.verificador` |
| **Ejecutar** los scripts sin apretar Run | ⏳ pendiente (Fase 2) | ver más abajo — bloqueado por Revit 2027 |

---

## Fase 1 — Auto-verificación (implementada)

### Cómo funciona

1. **El builder inyecta un auto-reporte en cada Python node.**
   `core/dynamo/dyn_builder.py` envuelve el código de cada nodo con un preámbulo
   y un epílogo (`_REPORT_PREAMBLE` / `_REPORT_EPILOGUE`):
   - Antes del código de usuario escribe un JSON con `status="started"`.
   - Después lo sobrescribe con `status="ok"`, el valor de `OUT` y las
     advertencias de Revit (`doc.GetWarnings()`).
   - El código de usuario **no se modifica ni se indenta**: si el nodo se rompe
     a mitad, el reporte queda en `"started"` y eso identifica el nodo culpable.

   Los JSON se escriben en `<carpeta del .dyn>/_reports/`, un archivo por nodo.
   La ruta se fija (absoluta) en `DynScript.save()`.

2. **`core/verificador.py` lee los reportes y decide PASS/FAIL.** Tres capas:
   - **Cobertura completa (los 10 scripts):** `claves_esperadas_de_dyn()` parsea
     los `.dyn` y extrae el `_PBG_KEY` de cada Python node, así sabe el conjunto
     exacto de nodos que deben correr. Cualquier nodo sin reporte → error "no se
     corrió". No hay nada hardcodeado: cubre todos los scripts automáticamente.
   - **Genéricos (todo nodo):** `"started"` → error; advertencias de Revit →
     warning; nodo que corrió pero creó **0 elementos** → warning (fallo
     silencioso típico; warning y no error porque algunos nodos crean 0 legítimo).
   - **Específicos por script:** compara el resultado real contra el que predicen
     los `ParametrosEdificio`. Hay dos estilos según qué tan derivable es el
     conteo. **Exactos** (`_cmp`), donde la cantidad sale limpia de los params:
     - `01_niveles_grilla` — niveles, ejes de grilla, plantas. Detecta el bug
       histórico de "el input nunca llegó a Revit" mirando `frente_m_recibido`.
     - `03_losas` — una losa por piso tipo + azotea.
     - `04_estructura` — columnas `(pisos+1)·nx·ny`, vigas de entrepiso, vigas de
       fundación y zapatas `nx·ny`, sobre la grilla estructural de 5 m (paso fijo
       inclusive, **distinta** a la grilla de niveles). Marca error si falta la
       familia de fundación cargada.
     - `06_escaleras_ascensores` — ascensores `== cant_ascensores`; tramos de
       escalera `cajas·pisos` (o `cajas` en la rama fallback sin `StairsType`).
       Las escaleras con error se reportan aparte.
     - `07_instalaciones_mep` — un MEP Space por piso tipo; artefactos
       `pisos·(incendio? + eléctrica?)`.
     - `08_vistas` — una planta por PB + pisos tipo + azotea.
     - `09_sheets` — 13 láminas A3 IRAM (error explícito si falta el title block).
     - `10_schedules` — 7 tablas de cómputo.

     **De cobertura por nivel**, donde la geometría es compleja y replicar el
     conteo exacto sería frágil: se verifica que SÍ haya elementos en *todos* los
     niveles esperados (el síntoma del bug de conectores era geometría solo en PB
     / solo defaults):
     - `02_muros_perimetrales` y `05_aberturas` — cobertura PB + pisos tipo.
     - `11_habitaciones` — rooms en cada piso tipo, sin entradas con `error`.
     - `09b_anotaciones` — detecta el error de dimensiones sin la vista PLANTA PB.

     Todos los nodos pasan además por la capa genérica (corrió + creó >0).

### Uso — el ciclo sin revisar a mano

```bash
# 1. Generar (también limpia los reportes viejos para empezar de cero):
python generar.py
# 2. Correr los 10 .dyn en Revit (a mano por ahora; ver Fase 2).
#    Cada nodo deja su JSON en output/dynamo/_reports/.
# 3. Verificar — PASS/FAIL + _verificacion.html, exit code 1 si falla:
python generar.py --verificar
```

También directo: `python -m core.verificador output/dynamo/_reports`.

Programático (p.ej. para un botón "Verificar" en la UI):

```python
from core.verificador import verificar_y_guardar
rep = verificar_y_guardar(params, "output/dynamo/_reports")
print(rep.to_text())
if not rep.ok:
    ...  # rep.resultados tiene el detalle
```

Código de salida del CLI: `0` si PASS, `1` si hay errores (apto para CI).

### Agregar chequeos cuantitativos a más scripts

En `core/verificador.py`, escribir una función `_check_<algo>(params, reportes)`
que devuelva una lista de `Resultado`, y registrarla en `_CHECKS_ESPECIFICOS`.
Usar `_buscar(reportes, script, "<substring del label del nodo>")` para ubicar el
reporte y `_cmp(...)` para comparar esperado vs. real. Modelo a seguir:
`_check_niveles`.

> ⚠️ Si un chequeo replica lógica del generador, mantener ambas copias en sync:
> `_ejes()` espeja la grilla de `gen_niveles._CODE_GRILLA`; `_nodos_estructura()`
> espeja los loops de paso fijo de `gen_estructura` (columnas/vigas/zapatas).
> Son grillas distintas — no intercambiarlas.

---

## Fase 2 — Ejecución headless (pendiente)

Investigado el 2026-06-18:

- **RevitBatchProcessor** (la herramienta estándar para correr `.dyn` en batch
  sin intervención) soporta **Revit 2015–2026, todavía NO 2027.** No es viable
  hoy en el target del proyecto.
- **DynamoCLI / DynamoSandbox no sirve**: nuestros nodos usan
  `__revit__` / `DocumentManager.Instance.CurrentDBDocument`, necesitan Revit
  vivo. El CLI corre Dynamo aislado, sin documento de Revit.
- Para cualquier ejecución batch, el `.dyn` debe estar en **RunType "Automatic"**;
  hoy el builder los emite como `"Manual"` (`dyn_builder._DYNAMO_VERSION` zone →
  `View.Dynamo.RunType`). Habrá que parametrizarlo cuando se aborde la Fase 2.

Caminos posibles cuando se retome:

1. **Esperar el soporte 2027 de RevitBatchProcessor** (o un fork de la comunidad)
   y armar un task script que corra los 10 `.dyn` en orden sobre un `.rvt` limpio.
2. **pyRevit** (su doc cubre agregar versiones nuevas de Revit) como runner
   alternativo.
3. **Journal file + add-in propio** que abra Revit 2027 y dispare los scripts.
   Es el más robusto pero el de más trabajo.

En cualquiera de los tres, la Fase 1 ya queda lista: una vez que el batch corre
los scripts, los reportes aparecen solos y `core.verificador` cierra el lazo.
El objetivo final es un único comando "Generar → correr → verificar" (o un botón
en la UI PyQt) que solo te pida atención cuando algo da FAIL.
