"""Tests para core/parametros.py."""

import json
import tempfile
from pathlib import Path

import pytest

from core.parametros import ParametrosEdificio, TipologiaDepto


def test_defaults_validos():
    p = ParametrosEdificio()
    assert p.validar() == []


def test_propiedades_derivadas():
    p = ParametrosEdificio(frente=10.0, fondo=24.0, pisos_tipo=6)
    assert p.superficie_planta_tipo == pytest.approx(240.0)
    assert p.altura_total == pytest.approx(3.50 + 2.80 * 6)
    assert p.cant_departamentos_total == 12  # 2 deptos × 6 pisos


def test_f_c_mpa():
    assert ParametrosEdificio(hormigon_tipo="H-21").f_c_mpa == pytest.approx(21.0)
    assert ParametrosEdificio(hormigon_tipo="H-25").f_c_mpa == pytest.approx(25.0)
    assert ParametrosEdificio(hormigon_tipo="H-30").f_c_mpa == pytest.approx(30.0)


def test_fy_mpa():
    assert ParametrosEdificio(acero_tipo="ADN 420").fy_mpa == pytest.approx(420.0)
    assert ParametrosEdificio(acero_tipo="AL 220").fy_mpa == pytest.approx(220.0)


def test_validacion_pisos_fuera_rango():
    errores = ParametrosEdificio(pisos_tipo=25).validar()
    assert any("pisos_tipo" in e for e in errores)


def test_validacion_subsuelo_inconsistente():
    errores = ParametrosEdificio(tiene_subsuelo=True, cant_subsuelos=0).validar()
    assert any("cant_subsuelos" in e for e in errores)

    errores2 = ParametrosEdificio(tiene_subsuelo=False, cant_subsuelos=1).validar()
    assert any("cant_subsuelos" in e for e in errores2)


def test_validacion_cochera_sin_subsuelo():
    errores = ParametrosEdificio(
        tiene_cochera=True,
        cochera_ubicacion="subsuelo",
        tiene_subsuelo=False,
        cant_subsuelos=0,
    ).validar()
    assert any("subsuelo" in e for e in errores)


def test_validacion_mix_tipologias_inconsistente():
    p = ParametrosEdificio(
        cant_depto_tipo=3,
        mix_tipologias=[
            TipologiaDepto(tipo="2amb", cantidad=1, superficie_m2=55.0),
            TipologiaDepto(tipo="3amb", cantidad=1, superficie_m2=75.0),
        ],
    )
    errores = p.validar()
    assert any("mix_tipologias" in e for e in errores)


def test_validacion_altura_minima():
    errores = ParametrosEdificio(altura_pb=2.0).validar()
    assert any("altura_pb" in e for e in errores)

    errores2 = ParametrosEdificio(altura_tipo=2.0).validar()
    assert any("altura_tipo" in e for e in errores2)


def test_superficie_total_con_subsuelo():
    p = ParametrosEdificio(
        frente=10.0, fondo=24.0, pisos_tipo=4,
        tiene_subsuelo=True, cant_subsuelos=1,
        tiene_azotea=True,
    )
    # PB + 4 pisos tipo + azotea + 1 subsuelo = 7 niveles
    assert p.superficie_total_edificio == pytest.approx(240.0 * 7)


# ---------------------------------------------------------------------------
# Tests de serialización
# ---------------------------------------------------------------------------

def test_guardar_y_cargar_roundtrip():
    p_orig = ParametrosEdificio(
        frente=8.66, fondo=20.0, pisos_tipo=8,
        hormigon_tipo="H-25", acero_tipo="ADN 420",
        tiene_subsuelo=True, cant_subsuelos=1,
        instalacion_termomecanica=True,
    )
    with tempfile.NamedTemporaryFile(suffix=".pbg", delete=False) as tmp:
        path = Path(tmp.name)

    try:
        p_orig.guardar(path)
        p_cargado = ParametrosEdificio.cargar(path)

        assert p_cargado.frente == pytest.approx(p_orig.frente)
        assert p_cargado.fondo == pytest.approx(p_orig.fondo)
        assert p_cargado.pisos_tipo == p_orig.pisos_tipo
        assert p_cargado.hormigon_tipo == p_orig.hormigon_tipo
        assert p_cargado.tiene_subsuelo == p_orig.tiene_subsuelo
        assert p_cargado.cant_subsuelos == p_orig.cant_subsuelos
        assert p_cargado.instalacion_termomecanica == p_orig.instalacion_termomecanica
    finally:
        path.unlink(missing_ok=True)


def test_guardar_produce_json_valido():
    p = ParametrosEdificio()
    with tempfile.NamedTemporaryFile(suffix=".pbg", delete=False, mode="w") as tmp:
        path = Path(tmp.name)
    try:
        p.guardar(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "frente" in data
        assert "mix_tipologias" in data
        assert isinstance(data["mix_tipologias"], list)
    finally:
        path.unlink(missing_ok=True)


def test_cargar_preserva_tipologias():
    tipologias = [
        TipologiaDepto(tipo="1amb", cantidad=2, superficie_m2=38.0),
        TipologiaDepto(tipo="3amb", cantidad=1, superficie_m2=85.0),
    ]
    p_orig = ParametrosEdificio(
        cant_depto_tipo=3,
        mix_tipologias=tipologias,
    )
    with tempfile.NamedTemporaryFile(suffix=".pbg", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        p_orig.guardar(path)
        p_cargado = ParametrosEdificio.cargar(path)
        assert len(p_cargado.mix_tipologias) == 2
        assert p_cargado.mix_tipologias[0].tipo == "1amb"
        assert p_cargado.mix_tipologias[0].cantidad == 2
        assert p_cargado.mix_tipologias[1].superficie_m2 == pytest.approx(85.0)
        assert p_cargado.validar() == []
    finally:
        path.unlink(missing_ok=True)
