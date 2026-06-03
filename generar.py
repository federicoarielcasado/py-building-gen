"""Script de línea de comandos para generar todos los archivos del proyecto.

Uso:
    python generar.py                      # parámetros default
    python generar.py --load proyecto.pbg  # cargar parámetros guardados

Genera en output/:
    dynamo/   — 12 scripts .dyn para Revit 2027 + Dynamo 4.0
    computo/  — presupuesto_<proyecto>.xlsx + .pdf
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from core.parametros import ParametrosEdificio
from core.generadores import (
    gen_familias,
    gen_niveles,
    gen_arquitectura,
    gen_estructura,
    gen_instalaciones,
    gen_vistas,
    gen_sheets,
    gen_habitaciones,
    gen_anotaciones,
)
from core.computo.mediciones import calcular as calcular_mediciones
from core.computo.precios import cargar as cargar_precios
from core.computo.analisis_precios import analizar as analizar_precios
from core.computo.exportador import exportar_excel, exportar_pdf


def _slug(nombre: str) -> str:
    import re
    return re.sub(r"[^\w]+", "_", nombre.lower()).strip("_")


def generar_todo(params: ParametrosEdificio) -> dict[str, list[Path]]:
    """Genera todos los scripts .dyn y el cómputo a partir de los parámetros.

    Returns:
        Diccionario con keys 'dynamo' y 'computo' y listas de Path generados.
    """
    out_dyn = Path("output/dynamo")
    out_cmp = Path("output/computo")
    out_dyn.mkdir(parents=True, exist_ok=True)
    out_cmp.mkdir(parents=True, exist_ok=True)

    slug = _slug(params.nombre_proyecto)

    archivos: dict[str, list[Path]] = {"dynamo": [], "computo": []}

    pasos = [
        ("00 — Familias",         lambda: [gen_familias.generar(params, out_dyn)]),
        ("01 — Niveles y grilla", lambda: [gen_niveles.generar(params, out_dyn)]),
        ("02/03/05/06 — Arquitectura", lambda: gen_arquitectura.generar(params, out_dyn)),
        ("04 — Estructura",       lambda: gen_estructura.generar(params, out_dyn)),
        ("07 — Instalaciones MEP",lambda: gen_instalaciones.generar(params, out_dyn)),
        ("08 — Vistas",           lambda: gen_vistas.generar(params, out_dyn)),
        ("09 — Sheets",           lambda: gen_sheets.generar(params, out_dyn)),
        ("11 — Habitaciones",     lambda: [gen_habitaciones.generar(params, out_dyn)]),
        ("09b — Anotaciones",     lambda: [gen_anotaciones.generar(params, out_dyn)]),
    ]

    for nombre, fn in pasos:
        print(f"  {nombre}...", end=" ", flush=True)
        t0 = time.perf_counter()
        paths = fn()
        archivos["dynamo"].extend(paths if isinstance(paths, list) else [paths])
        print(f"{time.perf_counter()-t0:.2f}s")

    # Cómputo y presupuesto
    print("  Cómputo y presupuesto...", end=" ", flush=True)
    t0 = time.perf_counter()
    med = calcular_mediciones(params)
    precios = cargar_precios()
    ppto = analizar_precios(med, precios, params)
    xls = exportar_excel(ppto, out_cmp / f"presupuesto_{slug}.xlsx", moneda=params.moneda)
    pdf = exportar_pdf(
        ppto, out_cmp / f"presupuesto_{slug}.pdf",
        moneda=params.moneda,
        nombre_proyecto=params.nombre_proyecto,
        autor=params.autor,
    )
    archivos["computo"].extend([xls, pdf])
    print(f"{time.perf_counter()-t0:.2f}s")

    return archivos


def _print_resumen(params: ParametrosEdificio, archivos: dict) -> None:
    from core.computo.mediciones import calcular as _calc
    from core.computo.precios import cargar as _cargar
    from core.computo.analisis_precios import analizar as _analizar

    med = _calc(params)
    ppto = _analizar(med, _cargar(), params)

    print()
    print("=" * 60)
    print(f"  PROYECTO: {params.nombre_proyecto}")
    print(f"  AUTOR:    {params.autor}")
    print("=" * 60)
    print(f"  Lote:           {params.frente}m × {params.fondo}m")
    print(f"  Niveles:        PB + {params.pisos_tipo} pisos + {'AZO' if params.tiene_azotea else '-'}")
    print(f"  Altura total:   {params.altura_total:.2f}m")
    print(f"  Departamentos:  {params.cant_departamentos_total} total ({params.cant_depto_tipo}/piso)")
    print(f"  Tipologías:     {', '.join(f'{t.cantidad}x{t.tipo}' for t in params.mix_tipologias)}")
    print(f"  Hormigón:       {params.hormigon_tipo}")
    print()
    print(f"  PRESUPUESTO TOTAL ({params.moneda}): {ppto.total:>20,.0f}")
    print(f"  Costo directo:             {ppto.costo_directo:>20,.0f}")
    print()
    print(f"  Scripts .dyn generados: {len(archivos['dynamo'])}")
    for p in sorted(archivos["dynamo"]):
        print(f"    {p.name}")
    print()
    print(f"  Cómputo generado: {len(archivos['computo'])}")
    for p in archivos["computo"]:
        print(f"    {p.name}  ({p.stat().st_size // 1024} KB)")
    print()
    print("  ORDEN DE EJECUCIÓN EN REVIT:")
    dyns = sorted(archivos["dynamo"])
    for i, p in enumerate(dyns, 1):
        print(f"    {i:2d}. {p.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera scripts Dynamo y cómputo para py-building-gen.")
    parser.add_argument("--load", metavar="ARCHIVO.pbg", help="Cargar parámetros desde JSON.")
    parser.add_argument("--save", metavar="ARCHIVO.pbg", help="Guardar parámetros default a JSON.")
    args = parser.parse_args()

    if args.load:
        print(f"Cargando parámetros desde {args.load}...")
        params = ParametrosEdificio.cargar(args.load)
    else:
        params = ParametrosEdificio()

    if args.save:
        params.guardar(args.save)
        print(f"Parámetros guardados en {args.save}")

    errores = params.validar()
    if errores:
        for e in errores:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nGenerando proyecto: {params.nombre_proyecto}")
    print("-" * 60)
    archivos = generar_todo(params)
    _print_resumen(params, archivos)


if __name__ == "__main__":
    main()
