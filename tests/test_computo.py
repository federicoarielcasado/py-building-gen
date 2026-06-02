"""Tests del módulo de cómputo y presupuestación."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.parametros import ParametrosEdificio
from core.computo.mediciones import calcular, MedicionesEdificio
from core.computo.precios import cargar, CatalogoPrecios
from core.computo.analisis_precios import analizar, PresupuestoCompleto

DATA_DIR = Path(__file__).parent.parent / "data" / "precios"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def params_base() -> ParametrosEdificio:
    return ParametrosEdificio()


@pytest.fixture
def params_grande() -> ParametrosEdificio:
    return ParametrosEdificio(
        frente=10.0,
        fondo=24.0,
        pisos_tipo=12,
        altura_pb=3.50,
        altura_tipo=2.80,
        tiene_subsuelo=True,
        cant_subsuelos=2,
        tiene_azotea=True,
        cant_ascensores=2,
        cant_cajas_escalera=2,
    )


@pytest.fixture
def precios() -> CatalogoPrecios:
    return cargar(DATA_DIR)


# ---------------------------------------------------------------------------
# Tests de mediciones
# ---------------------------------------------------------------------------

class TestMediciones:
    def test_rubros_base_no_vacio(self, params_base: ParametrosEdificio) -> None:
        med = calcular(params_base)
        assert len(med.rubros) >= 10
        assert all(len(r.items) > 0 for r in med.rubros)

    def test_rubros_con_todas_instalaciones(self) -> None:
        p = ParametrosEdificio(
            instalacion_sanitaria=True,
            instalacion_electrica=True,
            instalacion_gas=True,
            instalacion_incendio=True,
            instalacion_termomecanica=True,
        )
        med = calcular(p)
        numeros = [r.numero for r in med.rubros]
        assert 9 in numeros
        assert 10 in numeros
        assert 11 in numeros
        assert 12 in numeros
        assert 13 in numeros

    def test_sin_instalaciones_opcionales(self) -> None:
        p = ParametrosEdificio(
            instalacion_sanitaria=False,
            instalacion_electrica=False,
            instalacion_gas=False,
            instalacion_incendio=False,
            instalacion_termomecanica=False,
        )
        med = calcular(p)
        numeros = [r.numero for r in med.rubros]
        assert 9 not in numeros
        assert 10 not in numeros
        assert 13 not in numeros

    def test_cantidades_positivas(self, params_base: ParametrosEdificio) -> None:
        med = calcular(params_base)
        for rubro in med.rubros:
            for item in rubro.items:
                assert item.cantidad >= 0, f"{item.codigo} tiene cantidad negativa"

    def test_sup_planta_correcta(self, params_base: ParametrosEdificio) -> None:
        med = calcular(params_base)
        assert med.sup_planta_m2 == pytest.approx(params_base.frente * params_base.fondo)

    def test_cant_columnas_positiva(self, params_base: ParametrosEdificio) -> None:
        med = calcular(params_base)
        assert med.cant_columnas > 0

    def test_subsuelo_agrega_excavacion(self, params_grande: ParametrosEdificio) -> None:
        med = calcular(params_grande)
        r2 = med.rubro(2)
        assert r2 is not None
        exc = next((i for i in r2.items if i.codigo == "2.1"), None)
        assert exc is not None
        assert exc.cantidad > 0  # tiene subsuelo

    def test_sin_subsuelo_excavacion_cero(self, params_base: ParametrosEdificio) -> None:
        assert not params_base.tiene_subsuelo
        med = calcular(params_base)
        r2 = med.rubro(2)
        exc = next((i for i in r2.items if i.codigo == "2.1"), None)
        assert exc.cantidad == 0.0

    def test_losas_incluyen_azotea(self) -> None:
        p = ParametrosEdificio(pisos_tipo=4, tiene_azotea=True)
        med = calcular(p)
        r4 = med.rubro(4)
        losa = next((i for i in r4.items if i.codigo == "4.3"), None)
        assert losa is not None and losa.cantidad > 0

    def test_equipamiento_ascensores(self, params_base: ParametrosEdificio) -> None:
        med = calcular(params_base)
        r15 = med.rubro(15)
        assert r15 is not None
        asc = next((i for i in r15.items if i.codigo == "15.1"), None)
        assert asc.cantidad == params_base.cant_ascensores

    def test_carpinterias_proporcionales_a_deptos(self) -> None:
        p1 = ParametrosEdificio(pisos_tipo=3, cant_depto_tipo=2)
        p2 = ParametrosEdificio(pisos_tipo=6, cant_depto_tipo=2)
        m1 = calcular(p1)
        m2 = calcular(p2)
        v1 = next(i for r in m1.rubros for i in r.items if i.codigo == "7.2")
        v2 = next(i for r in m2.rubros for i in r.items if i.codigo == "7.2")
        assert v2.cantidad == pytest.approx(v1.cantidad * 2)


# ---------------------------------------------------------------------------
# Tests de precios
# ---------------------------------------------------------------------------

class TestPrecios:
    def test_carga_sin_error(self, precios: CatalogoPrecios) -> None:
        assert precios is not None
        assert precios.fecha != ""

    def test_jornal_con_cargas_mayor_que_base(self, precios: CatalogoPrecios) -> None:
        base = precios.mano_obra.oficial_jornal
        con_cargas = precios.mano_obra.jornal_con_cargas("oficial")
        assert con_cargas > base

    def test_hormigon_h25_mayor_h21(self, precios: CatalogoPrecios) -> None:
        assert precios.materiales.hormigon_m3("H-25") > precios.materiales.hormigon_m3("H-21")

    def test_hormigon_h30_mayor_h25(self, precios: CatalogoPrecios) -> None:
        assert precios.materiales.hormigon_m3("H-30") > precios.materiales.hormigon_m3("H-25")

    def test_conversion_usd(self, precios: CatalogoPrecios) -> None:
        valor_ars = 1_000_000
        valor_usd = precios.precio_en(valor_ars, "USD")
        assert valor_usd < valor_ars
        assert valor_usd > 0

    def test_conversion_ars_identidad(self, precios: CatalogoPrecios) -> None:
        valor = 500_000.0
        assert precios.precio_en(valor, "ARS") == pytest.approx(valor)


# ---------------------------------------------------------------------------
# Tests de análisis de precios
# ---------------------------------------------------------------------------

class TestAnalisis:
    def test_presupuesto_no_vacio(
        self,
        params_base: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        med = calcular(params_base)
        ppto = analizar(med, precios, params_base)
        assert ppto.total > 0
        assert len(ppto.rubros) >= 10

    def test_total_mayor_costo_directo(
        self,
        params_base: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        med = calcular(params_base)
        ppto = analizar(med, precios, params_base)
        assert ppto.total >= ppto.costo_directo

    def test_gastos_generales_correctos(
        self,
        params_base: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        med = calcular(params_base)
        ppto = analizar(med, precios, params_base)
        esperado = ppto.costo_directo * ppto.pct_gastos_generales
        assert ppto.gastos_generales == pytest.approx(esperado, rel=1e-6)

    def test_sin_honorarios_no_suma(
        self,
        precios: CatalogoPrecios,
    ) -> None:
        p = ParametrosEdificio(incluir_honorarios=False, incluir_gastos_generales=False)
        med = calcular(p)
        ppto = analizar(med, precios, p)
        assert ppto.honorarios == 0.0
        assert ppto.gastos_generales == 0.0
        assert ppto.total == pytest.approx(ppto.costo_directo)

    def test_costo_m2_en_rango_icc(
        self,
        params_base: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        med = calcular(params_base)
        ppto = analizar(med, precios, params_base)
        sup = params_base.superficie_total_edificio
        costo_m2 = ppto.total / sup
        # Rango ICC: 500k–1.5M ARS/m² para vivienda multifamiliar media
        assert 300_000 < costo_m2 < 2_000_000, f"Costo/m² fuera de rango: {costo_m2:,.0f} ARS"

    def test_items_tienen_precio_positivo(
        self,
        params_base: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        med = calcular(params_base)
        ppto = analizar(med, precios, params_base)
        for rubro in ppto.rubros:
            for item in rubro.items:
                assert item.precio_unitario >= 0, (
                    f"{item.codigo} tiene precio unitario negativo: {item.precio_unitario}"
                )

    def test_edificio_grande_cuesta_mas(
        self,
        params_grande: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        p_base = ParametrosEdificio()
        m_base = calcular(p_base)
        m_grande = calcular(params_grande)
        ppto_base = analizar(m_base, precios, p_base)
        ppto_grande = analizar(m_grande, precios, params_grande)
        assert ppto_grande.total > ppto_base.total

    def test_resumen_porcentajes_suman_100(
        self,
        params_base: ParametrosEdificio,
        precios: CatalogoPrecios,
    ) -> None:
        med = calcular(params_base)
        ppto = analizar(med, precios, params_base)
        total_pct = sum(r["pct_sobre_total"] for r in ppto.resumen_por_rubro)
        assert total_pct == pytest.approx(100.0, rel=1e-3)
