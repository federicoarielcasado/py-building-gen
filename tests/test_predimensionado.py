"""Tests para core/predimensionado.py."""

import pytest

from core.parametros import ParametrosEdificio
from core.predimensionado import (
    predimensionar,
    _redondear_arriba_5cm,
    CARGA_PISO_TIPO_KN_M2,
    CARGA_AZOTEA_KN_M2,
)


def test_redondear_arriba_5cm():
    assert _redondear_arriba_5cm(0.12) == pytest.approx(0.15)
    assert _redondear_arriba_5cm(0.15) == pytest.approx(0.15)
    assert _redondear_arriba_5cm(0.21) == pytest.approx(0.25)
    assert _redondear_arriba_5cm(0.286) == pytest.approx(0.30)


def test_losas_cantidad():
    p = ParametrosEdificio(pisos_tipo=6, tiene_azotea=True)
    r = predimensionar(p)
    assert len(r.losas) == 7  # 6 pisos + azotea


def test_losas_sin_azotea():
    p = ParametrosEdificio(pisos_tipo=4, tiene_azotea=False)
    r = predimensionar(p)
    assert len(r.losas) == 4


def test_losa_espesor_minimo():
    p = ParametrosEdificio(frente=6.0, fondo=24.0, pisos_tipo=2, tiene_azotea=False)
    r = predimensionar(p)
    for losa in r.losas:
        assert losa.espesor_m >= 0.12


def test_losa_espesor_formula():
    # Losa con luz libre 10m: h ≥ 10/35 = 0.2857 → redondea a 0.30
    p = ParametrosEdificio(frente=10.0, fondo=24.0, pisos_tipo=2, tiene_azotea=False)
    r = predimensionar(p)
    assert r.losas[0].espesor_m == pytest.approx(0.30)


def test_vigas_cantidad():
    p = ParametrosEdificio(pisos_tipo=5, tiene_azotea=True)
    r = predimensionar(p)
    assert len(r.vigas) == 6  # 5 pisos + azotea


def test_viga_dimensiones_minimas():
    p = ParametrosEdificio()
    r = predimensionar(p)
    for viga in r.vigas:
        assert viga.alto_m >= 0.40
        assert viga.ancho_m >= 0.20


def test_columnas_cantidad():
    p = ParametrosEdificio(pisos_tipo=6)
    r = predimensionar(p)
    assert len(r.columnas) == 6


def test_columna_dimension_minima():
    p = ParametrosEdificio(pisos_tipo=3)
    r = predimensionar(p)
    for col in r.columnas:
        assert col.lado_m >= 0.25


def test_columna_carga_acumulada_crece():
    p = ParametrosEdificio(pisos_tipo=4, tiene_azotea=False)
    r = predimensionar(p)
    cargas = [col.carga_acumulada_kN for col in r.columnas]
    # Después de reverse(), index 0 = piso inferior (más carga), -1 = techo (menos carga)
    assert cargas[0] >= cargas[-1]


def test_zapata_area_positiva():
    p = ParametrosEdificio()
    r = predimensionar(p)
    assert r.zapata.area_requerida_m2 > 0.0


def test_resumen_incluye_secciones():
    p = ParametrosEdificio()
    r = predimensionar(p)
    texto = r.resumen()
    assert "LOSAS" in texto
    assert "VIGAS" in texto
    assert "COLUMNAS" in texto
    assert "ZAPATA" in texto


def test_advertencia_edificio_alto():
    p = ParametrosEdificio(pisos_tipo=15)
    r = predimensionar(p)
    assert any("INPRES" in adv for adv in r.advertencias)


def test_cargas_constantes():
    assert CARGA_PISO_TIPO_KN_M2 == pytest.approx(9.5)   # 5+1.5+1+2
    assert CARGA_AZOTEA_KN_M2 == pytest.approx(7.5)       # 5+1.5+1
