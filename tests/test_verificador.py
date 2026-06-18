"""Tests del pipeline de verificación automatizada (Fase 1).

Dos frentes:
  1. El dyn_builder inyecta el auto-reporte en cada Python node y el código
     resultante compila (lo que Dynamo correrá en Revit).
  2. core.verificador interpreta correctamente los reportes: PASS cuando los
     conteos coinciden, FAIL cuando un nodo se rompió o el input no llegó.

Como no hay Revit en CI, los reportes se simulan escribiendo los JSON con el
mismo esquema que produce el preámbulo/epílogo inyectado.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.parametros import ParametrosEdificio
from core.verificador import (
    SEV_ERROR,
    cargar_reportes,
    claves_esperadas_de_dyn,
    limpiar_reportes,
    verificar,
    verificar_y_guardar,
)
from core.generadores import (
    gen_niveles, gen_arquitectura, gen_estructura,
    gen_instalaciones, gen_vistas, gen_sheets,
)

_PARAMS = ParametrosEdificio()  # pisos_tipo=6, azotea=True, frente=10, fondo=24


# ---------------------------------------------------------------------------
# 1. Inyección de auto-reporte en el builder
# ---------------------------------------------------------------------------

def _todos_los_dyn(params, out: Path) -> list[Path]:
    archivos: list[Path] = [gen_niveles.generar(params, out)]
    for mod in (gen_arquitectura, gen_estructura, gen_instalaciones,
                gen_vistas, gen_sheets):
        archivos += mod.generar(params, out)
    return archivos


class TestInyeccionReporte:
    def test_python_nodes_inyectan_reporte_y_compilan(self, tmp_path):
        archivos = _todos_los_dyn(_PARAMS, tmp_path)
        n_python = 0
        for p in archivos:
            data = json.loads(p.read_text(encoding="utf-8"))
            for n in data["Nodes"]:
                if "PythonNode" not in n.get("ConcreteType", ""):
                    continue
                n_python += 1
                code = n["Code"]
                assert '_pbg_report("started")' in code, f"{p.name}: falta 'started'"
                assert '_pbg_report("ok"' in code, f"{p.name}: falta 'ok'"
                assert "_reports" in code, f"{p.name}: falta el report_dir"
                # Debe compilar exactamente como lo ejecutará Dynamo.
                compile(code, f"{p.name}:{n.get('Id')}", "exec")
        assert n_python >= 20, f"se esperaban muchos nodos Python, hubo {n_python}"

    def test_clave_de_reporte_es_unica_por_nodo(self, tmp_path):
        # Cada Python node escribe en un archivo distinto: las claves _PBG_KEY
        # no deben repetirse dentro de un mismo script.
        p = gen_niveles.generar(_PARAMS, tmp_path)
        data = json.loads(p.read_text(encoding="utf-8"))
        claves = []
        for n in data["Nodes"]:
            if "PythonNode" not in n.get("ConcreteType", ""):
                continue
            linea = next(l for l in n["Code"].splitlines() if "_PBG_KEY" in l)
            claves.append(linea)
        assert len(claves) == len(set(claves)), "claves de reporte duplicadas"


# ---------------------------------------------------------------------------
# Helpers para simular un directorio de reportes
# ---------------------------------------------------------------------------

def _escribir_reporte(d: Path, key: str, script: str, nodo: str,
                      status: str = "ok", out=None, warnings=None) -> None:
    d.mkdir(parents=True, exist_ok=True)
    rec = {
        "script": script, "nodo": nodo, "key": key, "status": status,
        "timestamp": "2026-06-18T12:00:00", "out": out,
        "warnings": warnings or [],
    }
    (d / f"{key}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _reportes_niveles_ok(d: Path) -> None:
    """Reportes coherentes con _PARAMS (8 niveles, 9 ejes, 24 plantas)."""
    _escribir_reporte(
        d, "01_niveles_grilla__00_crear_niveles", "01_niveles_grilla",
        "Crear Niveles",
        out=[{"nombre": n} for n in
             ["PB", "P01", "P02", "P03", "P04", "P05", "P06", "AZO"]],
    )
    _escribir_reporte(
        d, "01_niveles_grilla__01_crear_grilla", "01_niveles_grilla",
        "Crear Grilla",
        out={"total": 9, "frente_m_recibido": 10.0, "fondo_m_recibido": 24.0,
             "ejes": list("ABC") + ["1", "2", "3", "4", "5", "6"]},
    )
    _escribir_reporte(
        d, "01_niveles_grilla__02_plantas_por_disciplina", "01_niveles_grilla",
        "Plantas por Disciplina", out={"total": 24, "detalle": []},
    )


# ---------------------------------------------------------------------------
# 2. Lógica del verificador
# ---------------------------------------------------------------------------

class TestVerificadorPass:
    def test_run_limpio_es_pass(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        rep = verificar(_PARAMS, tmp_path)
        assert rep.ok, rep.to_text()
        assert rep.n_errores == 0

    def test_genera_html(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        verificar_y_guardar(_PARAMS, tmp_path)
        html = (tmp_path / "_verificacion.html").read_text(encoding="utf-8")
        assert "PASS" in html


class TestVerificadorFail:
    def test_sin_reportes_es_fail(self, tmp_path):
        rep = verificar(_PARAMS, tmp_path)
        assert not rep.ok
        assert any("reporte" in r.detalle for r in rep.resultados)

    def test_nodo_started_es_error(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        # Sobrescribir grilla con un estado "started" (se rompió a mitad).
        _escribir_reporte(
            tmp_path, "01_niveles_grilla__01_crear_grilla", "01_niveles_grilla",
            "Crear Grilla", status="started",
        )
        rep = verificar(_PARAMS, tmp_path)
        assert not rep.ok
        assert any(r.severidad == SEV_ERROR and "started" in r.detalle
                   for r in rep.resultados)

    def test_conteo_de_niveles_incorrecto_es_error(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        # Solo 5 niveles cuando se esperan 8.
        _escribir_reporte(
            tmp_path, "01_niveles_grilla__00_crear_niveles", "01_niveles_grilla",
            "Crear Niveles", out=[{"nombre": f"L{i}"} for i in range(5)],
        )
        rep = verificar(_PARAMS, tmp_path)
        assert not rep.ok
        assert any("niveles" in r.chequeo and not r.ok for r in rep.resultados)

    def test_input_de_lote_no_llego_es_error(self, tmp_path):
        # El bug clásico: frente/fondo llegan en 0.0 -> grilla degenerada.
        _reportes_niveles_ok(tmp_path)
        _escribir_reporte(
            tmp_path, "01_niveles_grilla__01_crear_grilla", "01_niveles_grilla",
            "Crear Grilla",
            out={"total": 2, "frente_m_recibido": 0.0, "fondo_m_recibido": 0.0},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert not rep.ok
        assert any("input" in r.chequeo.lower() and not r.ok
                   for r in rep.resultados)

    def test_script_esperado_ausente_es_error(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        rep = verificar(_PARAMS, tmp_path,
                        scripts_esperados=["01_niveles_grilla", "03_losas"])
        assert not rep.ok
        assert any(r.script == "03_losas" and not r.ok for r in rep.resultados)

    def test_advertencia_revit_es_warning_no_error(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        _escribir_reporte(
            tmp_path, "01_niveles_grilla__00_crear_niveles", "01_niveles_grilla",
            "Crear Niveles",
            out=[{"nombre": n} for n in
                 ["PB", "P01", "P02", "P03", "P04", "P05", "P06", "AZO"]],
            warnings=["Los elementos estan ligeramente fuera de eje"],
        )
        rep = verificar(_PARAMS, tmp_path)
        # Una advertencia NO debe tumbar el PASS, pero sí aparecer.
        assert rep.ok, rep.to_text()
        assert rep.n_warnings >= 1


# ---------------------------------------------------------------------------
# Utilidades de carga / limpieza
# ---------------------------------------------------------------------------

class TestNodosEsperadosDesdeDyn:
    """Cobertura completa: los nodos esperados se derivan de los propios .dyn,
    así un nodo que no corre se detecta en CUALQUIERA de los 10 scripts."""

    def test_extrae_claves_de_todos_los_scripts(self, tmp_path):
        _todos_los_dyn(_PARAMS, tmp_path)
        esperados = claves_esperadas_de_dyn(tmp_path)
        # Al menos los 20 nodos Python de los 6 generadores principales.
        assert len(esperados) >= 20
        # Cada uno trae script/nodo/key no vacíos y claves únicas.
        keys = [e["key"] for e in esperados]
        assert len(keys) == len(set(keys))
        assert all(e["script"] and e["nodo"] and e["key"] for e in esperados)

    def test_nodo_sin_reporte_es_error(self, tmp_path):
        # Generamos los .dyn y simulamos que SOLO corrió el primer nodo.
        _todos_los_dyn(_PARAMS, tmp_path)
        esperados = claves_esperadas_de_dyn(tmp_path)
        report_dir = tmp_path / "_reports"
        _escribir_reporte(
            report_dir, esperados[0]["key"], esperados[0]["script"],
            esperados[0]["nodo"], out={"total": 5},
        )
        rep = verificar(_PARAMS, report_dir, dyn_dir=tmp_path)
        assert not rep.ok
        # Hay un error por cada nodo que no dejó reporte.
        faltantes = [r for r in rep.resultados
                     if "no se corrió" in r.detalle and r.severidad == SEV_ERROR]
        assert len(faltantes) == len(esperados) - 1

    def test_nodo_creo_cero_elementos_es_warning(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        _escribir_reporte(
            tmp_path, "01_niveles_grilla__02_plantas_por_disciplina",
            "01_niveles_grilla", "Plantas por Disciplina",
            out={"total": 0, "detalle": []},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any("0 elementos" in r.detalle for r in rep.resultados)


class TestCargaYLimpieza:
    def test_cargar_ignora_no_reportes(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        (tmp_path / "_verificacion.html").write_text("<html>", encoding="utf-8")
        (tmp_path / "basura.json").write_text("{}", encoding="utf-8")  # sin status/key
        reportes = cargar_reportes(tmp_path)
        assert len(reportes) == 3  # solo los 3 reportes válidos

    def test_limpiar_borra_los_json(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        n = limpiar_reportes(tmp_path)
        assert n == 3
        assert cargar_reportes(tmp_path) == []

    def test_directorio_inexistente_no_falla(self, tmp_path):
        assert cargar_reportes(tmp_path / "no_existe") == []
        rep = verificar(_PARAMS, tmp_path / "no_existe")
        assert not rep.ok
