"""Tests de generadores Dynamo — validan estructura JSON de los .dyn."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from core.parametros import ParametrosEdificio
from core.generadores import (
    gen_niveles, gen_arquitectura, gen_estructura,
    gen_instalaciones, gen_vistas, gen_sheets,
)

_PARAMS = ParametrosEdificio()
_PARAMS_SUB = ParametrosEdificio(
    tiene_subsuelo=True, cant_subsuelos=1,
    instalacion_termomecanica=True,
)


def _load_dyn(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _generar_todos(params: ParametrosEdificio, out: Path) -> list[Path]:
    archivos: list[Path] = []
    archivos += [gen_niveles.generar(params, out)]
    archivos += gen_arquitectura.generar(params, out)
    archivos += gen_estructura.generar(params, out)
    archivos += gen_instalaciones.generar(params, out)
    archivos += gen_vistas.generar(params, out)
    archivos += gen_sheets.generar(params, out)
    return archivos


@pytest.fixture(scope="module")
def tmp_out(tmp_path_factory):
    return tmp_path_factory.mktemp("dynamo")


@pytest.fixture(scope="module")
def archivos_base(tmp_out):
    return _generar_todos(_PARAMS, tmp_out)


# ---------------------------------------------------------------------------
# Estructura del archivo .dyn
# ---------------------------------------------------------------------------

class TestEstructuraDyn:
    def test_genera_10_archivos(self, archivos_base):
        assert len(archivos_base) == 10

    def test_todos_son_json_valido(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            assert isinstance(data, dict), f"{p.name} no es un dict JSON"

    def test_campos_obligatorios(self, archivos_base):
        campos = {"Uuid", "Name", "Nodes", "Connectors", "View"}
        for p in archivos_base:
            data = _load_dyn(p)
            faltantes = campos - data.keys()
            assert not faltantes, f"{p.name} le faltan: {faltantes}"

    def test_version_dynamo_4x(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            version = data["View"]["Dynamo"]["Version"]
            assert version.startswith("4."), f"{p.name} tiene versión {version}"

    def test_modo_ejecucion_manual(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            run_type = data["View"]["Dynamo"]["RunType"]
            assert run_type == "Manual", f"{p.name} tiene RunType={run_type}"

    def test_todos_tienen_nodos(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            assert len(data["Nodes"]) > 0, f"{p.name} no tiene nodos"

    def test_todos_tienen_conectores(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            assert len(data["Connectors"]) > 0, f"{p.name} no tiene conectores"

    def test_node_views_coincide_con_nodos(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            assert len(data["View"]["NodeViews"]) == len(data["Nodes"]), \
                f"{p.name}: NodeViews != Nodes"


# ---------------------------------------------------------------------------
# Nodos Python usan CPython 3
# ---------------------------------------------------------------------------

class TestNodosPython:
    def test_engine_pythonnet3(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            py_nodes = [n for n in data["Nodes"] if "PythonNode" in n.get("ConcreteType", "")]
            for n in py_nodes:
                assert n.get("Engine") == "PythonNet3", \
                    f"{p.name}: nodo Python usa engine={n.get('Engine')}"

    def test_codigo_no_vacio(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            py_nodes = [n for n in data["Nodes"] if "PythonNode" in n.get("ConcreteType", "")]
            for n in py_nodes:
                assert n.get("Code", "").strip(), f"{p.name}: nodo Python sin código"

    def test_imports_revit_api(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            py_nodes = [n for n in data["Nodes"] if "PythonNode" in n.get("ConcreteType", "")]
            for n in py_nodes:
                code = n.get("Code", "")
                assert "RevitAPI" in code, \
                    f"{p.name}: falta import RevitAPI en nodo Python"


# ---------------------------------------------------------------------------
# Conectores bien formados
# ---------------------------------------------------------------------------

class TestConectores:
    def test_conectores_tienen_campos(self, archivos_base):
        campos = {"Start", "End", "Id", "StartIndex", "EndIndex"}
        for p in archivos_base:
            data = _load_dyn(p)
            for c in data["Connectors"]:
                faltantes = campos - c.keys()
                assert not faltantes, f"{p.name}: conector incompleto {c}"

    def test_indices_no_negativos(self, archivos_base):
        for p in archivos_base:
            data = _load_dyn(p)
            for c in data["Connectors"]:
                assert c["StartIndex"] >= 0
                assert c["EndIndex"] >= 0


# ---------------------------------------------------------------------------
# Scripts específicos
# ---------------------------------------------------------------------------

class TestScriptsEspecificos:
    def test_01_niveles_nodos_correctos(self, tmp_out):
        p = gen_niveles.generar(_PARAMS, tmp_out)
        data = _load_dyn(p)
        # 10 CodeBlocks + 3 PythonNodes (niveles + grilla + plantas por disciplina)
        assert len(data["Nodes"]) == 13

    def test_01_niveles_con_subsuelo(self, tmp_path):
        p = ParametrosEdificio(tiene_subsuelo=True, cant_subsuelos=2)
        out = gen_niveles.generar(p, tmp_path)
        data = _load_dyn(out)
        # El code block de cant_subsuelos debe tener el valor 2
        cb_nodes = [n for n in data["Nodes"] if n.get("NodeType") == "CodeBlockNode"]
        codigos = [n["Code"].rstrip(";") for n in cb_nodes]
        assert "2" in codigos

    def test_04_estructura_usa_predimensionado(self, tmp_path):
        from core.predimensionado import predimensionar
        p = ParametrosEdificio(hormigon_tipo="H-30", pisos_tipo=10)
        res = predimensionar(p)
        lado_cm = round(res.columnas[0].lado_m * 100) if res.columnas else 25
        out_paths = gen_estructura.generar(p, tmp_path)
        data = _load_dyn(out_paths[0])
        cbs = [n for n in data["Nodes"] if n.get("NodeType") == "CodeBlockNode"]
        codigos = [n["Code"].rstrip(";") for n in cbs]
        assert str(lado_cm) in codigos, f"Sección {lado_cm}cm no encontrada en CodeBlocks"

    def test_10_scripts_con_todas_instalaciones(self, tmp_path):
        p = ParametrosEdificio(instalacion_termomecanica=True)
        archivos = _generar_todos(p, tmp_path)
        assert len(archivos) == 10

    def test_archivos_orden_numerico(self, tmp_out):
        archivos = sorted(_generar_todos(_PARAMS, tmp_out))
        nombres = [a.name for a in archivos]
        for nombre in nombres:
            assert nombre[0].isdigit(), f"{nombre} no empieza con número"
