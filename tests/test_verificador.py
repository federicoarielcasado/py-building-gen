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
        # Tests enfocados en niveles: acotamos el set de scripts esperados.
        rep = verificar(_PARAMS, tmp_path, scripts_esperados=["01_niveles_grilla"])
        assert rep.ok, rep.to_text()
        assert rep.n_errores == 0

    def test_genera_html(self, tmp_path):
        _reportes_niveles_ok(tmp_path)
        verificar_y_guardar(_PARAMS, tmp_path)
        html = (tmp_path / "_verificacion.html").read_text(encoding="utf-8")
        assert "PASS" in html or "FAIL" in html  # el HTML se genera en ambos casos


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
        rep = verificar(_PARAMS, tmp_path, scripts_esperados=["01_niveles_grilla"])
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


class TestCheckLosas:
    """03_losas: una losa por piso tipo + azotea."""

    def _reporte(self, d, total):
        _escribir_reporte(
            d, "03_losas__00_crear_losas_v2", "03_losas", "Crear Losas v2",
            out={"total": total, "detalle": []},
        )

    def test_conteo_correcto_pasa(self, tmp_path):
        self._reporte(tmp_path, 7)  # 6 pisos + azotea
        rep = verificar(_PARAMS, tmp_path)
        assert all(r.ok for r in rep.resultados if r.script == "03_losas")

    def test_conteo_incorrecto_falla(self, tmp_path):
        self._reporte(tmp_path, 5)
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "03_losas" and "losas" in r.chequeo and not r.ok
                   for r in rep.resultados)

    def test_sin_azotea(self, tmp_path):
        params = ParametrosEdificio(tiene_azotea=False)
        self._reporte(tmp_path, params.pisos_tipo)  # sin losa de azotea
        rep = verificar(params, tmp_path)
        assert any(r.script == "03_losas" and r.ok and "losas" in r.chequeo
                   for r in rep.resultados)


class TestCheckEstructura:
    """04_estructura: columnas, vigas, vigas de fundación y zapatas en grilla 5m."""

    def _reportes(self, d, columnas=105, vigas=132, vf=22, zapatas=15,
                  zap_extra=None):
        _escribir_reporte(d, "04_estructura__00_crear_columnas_v2",
                          "04_estructura", "Crear Columnas v2",
                          out={"total": columnas})
        _escribir_reporte(d, "04_estructura__01_crear_vigas",
                          "04_estructura", "Crear Vigas",
                          out={"total_vigas": vigas})
        _escribir_reporte(d, "04_estructura__02_vigas_de_fundacion",
                          "04_estructura", "Vigas de Fundación",
                          out={"total_vf": vf})
        out_zap = {"total": zapatas}
        if zap_extra:
            out_zap.update(zap_extra)
        _escribir_reporte(d, "04_estructura__03_crear_zapatas",
                          "04_estructura", "Crear Zapatas", out=out_zap)

    def test_conteos_default_pasan(self, tmp_path):
        self._reportes(tmp_path)
        rep = verificar(_PARAMS, tmp_path)
        est = [r for r in rep.resultados if r.script == "04_estructura"]
        assert est and all(r.ok for r in est), [r.detalle for r in est if not r.ok]

    def test_columnas_incorrectas_falla(self, tmp_path):
        self._reportes(tmp_path, columnas=90)
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "04_estructura" and "columnas" in r.chequeo
                   and not r.ok for r in rep.resultados)

    def test_vigas_distingue_entrepiso_de_fundacion(self, tmp_path):
        # Viga entrepiso mal, fundación bien: solo debe fallar la de entrepiso.
        self._reportes(tmp_path, vigas=999, vf=22)
        rep = verificar(_PARAMS, tmp_path)
        falla_entrepiso = any(r.chequeo == "cantidad de vigas" and not r.ok
                              for r in rep.resultados)
        ok_fundacion = any(r.chequeo == "cantidad de vigas de fundación" and r.ok
                           for r in rep.resultados)
        assert falla_entrepiso and ok_fundacion

    def test_zapatas_sin_familia_es_error_con_mensaje(self, tmp_path):
        self._reportes(tmp_path, zapatas=0,
                       zap_extra={"accion_requerida": "Cargar familia de zapata."})
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "04_estructura" and "zapatas" in r.chequeo
                   and not r.ok and "Cargar familia" in r.detalle
                   for r in rep.resultados)


_NIV_TIPO = ["P01", "P02", "P03", "P04", "P05", "P06"]  # _PARAMS.pisos_tipo == 6


def _detalle(niveles):
    return [{"nivel": n, "id": i} for i, n in enumerate(niveles)]


class TestCheckMuros:
    """02_muros: deben aparecer muros en PB + cada piso tipo."""

    def test_cobertura_completa_pasa(self, tmp_path):
        _escribir_reporte(
            tmp_path, "02_muros_perimetrales__00_crear_muros_v2",
            "02_muros_perimetrales", "Crear Muros v2",
            out={"total": 99, "detalle": _detalle(["PB", *_NIV_TIPO])},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "02_muros_perimetrales" and r.ok
                   and "niveles" in r.chequeo for r in rep.resultados)

    def test_falta_un_nivel_es_error(self, tmp_path):
        # Síntoma del bug de conectores: solo se crea PB con defaults.
        _escribir_reporte(
            tmp_path, "02_muros_perimetrales__00_crear_muros_v2",
            "02_muros_perimetrales", "Crear Muros v2",
            out={"total": 10, "detalle": _detalle(["PB"])},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "02_muros_perimetrales" and not r.ok
                   and r.severidad == SEV_ERROR for r in rep.resultados)


class TestCheckAberturas:
    """05_aberturas: aberturas en PB (acceso) + cada piso tipo."""

    def test_cobertura_completa_pasa(self, tmp_path):
        _escribir_reporte(
            tmp_path, "05_aberturas__00_crear_aberturas_v2",
            "05_aberturas", "Crear Aberturas v2",
            out={"total": 50, "detalle": _detalle(["PB", *_NIV_TIPO])},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "05_aberturas" and r.ok and "niveles" in r.chequeo
                   for r in rep.resultados)

    def test_pisos_sin_aberturas_es_error(self, tmp_path):
        _escribir_reporte(
            tmp_path, "05_aberturas__00_crear_aberturas_v2",
            "05_aberturas", "Crear Aberturas v2",
            out={"total": 3, "detalle": _detalle(["PB", "P01"])},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "05_aberturas" and not r.ok for r in rep.resultados)


class TestCheckCirculacion:
    """06: ascensores == cant_ascensores; tramos de escalera por caja × piso."""

    def _reporte(self, d, ascensores=1, escaleras=None, tipo="Escalera de hormigón"):
        if escaleras is None:
            escaleras = [{"tipo": "escalera_real", "nivel": n} for n in _NIV_TIPO]
        _escribir_reporte(
            d, "06_escaleras_ascensores__00_escaleras_y_ascensores",
            "06_escaleras_ascensores", "Escaleras y Ascensores",
            out={"ascensores": [{"tipo": f"ascensor_{i+1}"} for i in range(ascensores)],
                 "escaleras": escaleras, "escalera_tipo": tipo},
        )

    def test_conteos_correctos_pasan(self, tmp_path):
        self._reporte(tmp_path)
        rep = verificar(_PARAMS, tmp_path)
        circ = [r for r in rep.resultados if r.script == "06_escaleras_ascensores"]
        assert circ and all(r.ok for r in circ), [r.detalle for r in circ if not r.ok]

    def test_ascensor_faltante_es_error(self, tmp_path):
        self._reporte(tmp_path, ascensores=0)
        rep = verificar(_PARAMS, tmp_path)
        assert any("ascensores" in r.chequeo and not r.ok for r in rep.resultados)

    def test_escalera_con_error_es_error(self, tmp_path):
        self._reporte(tmp_path, escaleras=[{"tipo": "error", "msg": "scope falló"}])
        rep = verificar(_PARAMS, tmp_path)
        assert any("escaleras sin error" in r.chequeo and not r.ok
                   for r in rep.resultados)

    def test_rama_fallback_espera_una_por_caja(self, tmp_path):
        self._reporte(tmp_path, tipo="fallback_shaft",
                      escaleras=[{"tipo": "shaft_fallback"}])
        rep = verificar(_PARAMS, tmp_path)  # cant_cajas_escalera == 1
        assert any("tramos de escalera" in r.chequeo and r.ok
                   for r in rep.resultados)


class TestCheckInstalaciones:
    """07: un MEP Space por piso tipo; matafuego + tablero por piso."""

    def _reporte(self, d, spaces=6, artefactos=12):
        _escribir_reporte(
            d, "07_instalaciones_mep__00_artefactos_mep_v2",
            "07_instalaciones_mep", "Artefactos MEP v2",
            out={"spaces_mep": spaces, "artefactos": artefactos, "detalle": []},
        )

    def test_conteos_correctos_pasan(self, tmp_path):
        self._reporte(tmp_path)  # 6 spaces, 12 artefactos (incendio + eléctrica)
        rep = verificar(_PARAMS, tmp_path)
        inst = [r for r in rep.resultados if r.script == "07_instalaciones_mep"]
        assert inst and all(r.ok for r in inst), [r.detalle for r in inst if not r.ok]

    def test_spaces_incorrectos_falla(self, tmp_path):
        self._reporte(tmp_path, spaces=3)
        rep = verificar(_PARAMS, tmp_path)
        assert any("espacios MEP" in r.chequeo and not r.ok for r in rep.resultados)

    def test_artefactos_segun_instalaciones_activas(self, tmp_path):
        # Sin incendio: solo tableros eléctricos -> 6 artefactos.
        params = ParametrosEdificio(instalacion_incendio=False)
        self._reporte(tmp_path, artefactos=params.pisos_tipo)
        rep = verificar(params, tmp_path)
        assert any("artefactos" in r.chequeo and r.ok for r in rep.resultados)


class TestCheckPlantas:
    """08: una planta por PB + pisos tipo + azotea."""

    def _reporte(self, d, n):
        _escribir_reporte(
            d, "08_vistas__00_crear_plantas", "08_vistas", "Crear Plantas",
            out=[{"nivel": f"L{i}", "id": i} for i in range(n)],
        )

    def test_conteo_correcto_pasa(self, tmp_path):
        self._reporte(tmp_path, 8)  # PB + 6 + azotea
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "08_vistas" and r.ok and "plantas" in r.chequeo
                   for r in rep.resultados)

    def test_conteo_incorrecto_falla(self, tmp_path):
        self._reporte(tmp_path, 6)
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "08_vistas" and "plantas" in r.chequeo and not r.ok
                   for r in rep.resultados)


class TestCheckSheets:
    """09: 13 láminas A3 IRAM; falta de title block es error explícito."""

    def test_conteo_correcto_pasa(self, tmp_path):
        _escribir_reporte(
            tmp_path, "09_sheets__00_crear_sheets_v2", "09_sheets",
            "Crear Sheets v2", out={"total": 13, "laminas": []},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "09_sheets" and r.ok and "láminas" in r.chequeo
                   for r in rep.resultados)

    def test_title_block_faltante_es_error(self, tmp_path):
        _escribir_reporte(
            tmp_path, "09_sheets__00_crear_sheets_v2", "09_sheets",
            "Crear Sheets v2",
            out={"error": "No se encontró title block. Cargar familia IRAM A3."},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "09_sheets" and not r.ok and "title block" in r.chequeo
                   for r in rep.resultados)


class TestCheckSchedules:
    """10: 7 schedules de cómputo."""

    def test_conteo_correcto_pasa(self, tmp_path):
        _escribir_reporte(
            tmp_path, "10_schedules__00_crear_schedules", "10_schedules",
            "Crear Schedules", out={"total": 7, "schedules": []},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "10_schedules" and r.ok and "schedules" in r.chequeo
                   for r in rep.resultados)

    def test_conteo_incorrecto_falla(self, tmp_path):
        _escribir_reporte(
            tmp_path, "10_schedules__00_crear_schedules", "10_schedules",
            "Crear Schedules", out={"total": 4, "schedules": []},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "10_schedules" and not r.ok for r in rep.resultados)


class TestCheckHabitaciones:
    """11: rooms en cada piso tipo, sin errores de creación."""

    def test_cobertura_completa_pasa(self, tmp_path):
        rooms = [{"nivel": n, "depto": "A", "nombre": "Living"} for n in _NIV_TIPO]
        _escribir_reporte(
            tmp_path, "11_habitaciones__00_crear_rooms", "11_habitaciones",
            "Crear Rooms", out={"total": len(rooms), "rooms": rooms},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "11_habitaciones" and r.ok and "pisos tipo" in r.chequeo
                   for r in rep.resultados)

    def test_room_con_error_es_error(self, tmp_path):
        rooms = [{"nivel": n} for n in _NIV_TIPO]
        rooms.append({"nivel": "P03", "error": "local no cerrado"})
        _escribir_reporte(
            tmp_path, "11_habitaciones__00_crear_rooms", "11_habitaciones",
            "Crear Rooms", out={"total": len(rooms), "rooms": rooms},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "11_habitaciones" and not r.ok
                   and "sin error" in r.chequeo for r in rep.resultados)

    def test_piso_sin_rooms_es_error(self, tmp_path):
        rooms = [{"nivel": n} for n in _NIV_TIPO[:3]]  # faltan P04..P06
        _escribir_reporte(
            tmp_path, "11_habitaciones__00_crear_rooms", "11_habitaciones",
            "Crear Rooms", out={"total": len(rooms), "rooms": rooms},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "11_habitaciones" and not r.ok
                   and "pisos tipo" in r.chequeo for r in rep.resultados)


class TestCheckAnotaciones:
    """09b: detecta el error de dimensiones sin la vista PLANTA PB."""

    def test_sin_error_pasa(self, tmp_path):
        _escribir_reporte(
            tmp_path, "09b_anotaciones__01_dimensiones", "09b_anotaciones",
            "Dimensiones",
            out={"total": 2, "detalle": [{"tipo": "frente", "id": 1}]},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert not any(r.script == "09b_anotaciones" and not r.ok
                       for r in rep.resultados)

    def test_vista_pb_faltante_es_error(self, tmp_path):
        _escribir_reporte(
            tmp_path, "09b_anotaciones__01_dimensiones", "09b_anotaciones",
            "Dimensiones",
            out={"total": 1, "detalle": [
                {"error": "Vista PLANTA PB no encontrada. Correr 08_vistas primero."}]},
        )
        rep = verificar(_PARAMS, tmp_path)
        assert any(r.script == "09b_anotaciones" and not r.ok
                   and "dimensiones" in r.chequeo for r in rep.resultados)


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
