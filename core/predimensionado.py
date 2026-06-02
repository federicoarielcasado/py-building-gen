"""Predimensionado estructural según CIRSOC 201-2005 y CIRSOC 101."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio


# ---------------------------------------------------------------------------
# Cargas (CIRSOC 101)
# ---------------------------------------------------------------------------

PESO_LOSA_KN_M2 = 5.0        # 0.20m × 25 kN/m³
CARPETA_PISO_KN_M2 = 1.5
TABIQUES_KN_M2 = 1.0
SC_VIVIENDA_KN_M2 = 2.0
SC_AZOTEA_KN_M2 = 1.0
SC_COCHERA_KN_M2 = 2.5

CARGA_PISO_TIPO_KN_M2 = PESO_LOSA_KN_M2 + CARPETA_PISO_KN_M2 + TABIQUES_KN_M2 + SC_VIVIENDA_KN_M2
CARGA_AZOTEA_KN_M2 = PESO_LOSA_KN_M2 + CARPETA_PISO_KN_M2 + SC_AZOTEA_KN_M2

SIGMA_ADM_SUELO_KGF_CM2 = 1.80  # Suelo medio CABA


@dataclass
class SeccionLosa:
    nivel: str
    luz_libre_m: float
    espesor_m: float
    carga_total_kN_m2: float

    @property
    def espesor_cm(self) -> float:
        return round(self.espesor_m * 100, 1)


@dataclass
class SeccionViga:
    nivel: str
    luz_libre_m: float
    alto_m: float
    ancho_m: float
    carga_lineal_kN_m: float

    @property
    def descripcion(self) -> str:
        return "{:d}x{:d}cm".format(int(self.ancho_m * 100), int(self.alto_m * 100))


@dataclass
class SeccionColumna:
    nivel: str
    carga_acumulada_kN: float
    lado_m: float
    f_c_mpa: float

    @property
    def descripcion(self) -> str:
        lado_cm = int(self.lado_m * 100)
        return "{:d}x{:d}cm".format(lado_cm, lado_cm)

    @property
    def area_m2(self) -> float:
        return self.lado_m ** 2

    @property
    def area_requerida_m2(self) -> float:
        """Área mínima requerida por capacidad resistente (CIRSOC 201 § 10.3.6)."""
        f_c_kN_m2 = self.f_c_mpa * 1000.0
        return self.carga_acumulada_kN / (0.45 * f_c_kN_m2)


@dataclass
class SeccionZapata:
    nivel: str = "Fundacion"
    carga_total_kN: float = 0.0
    lado_m: float = 0.0
    sigma_adm_kgf_cm2: float = SIGMA_ADM_SUELO_KGF_CM2

    @property
    def descripcion(self) -> str:
        lado_cm = int(self.lado_m * 100)
        return "{:d}x{:d}cm".format(lado_cm, lado_cm)

    @property
    def sigma_adm_kN_m2(self) -> float:
        return self.sigma_adm_kgf_cm2 * 98.0665

    @property
    def area_requerida_m2(self) -> float:
        return self.carga_total_kN / self.sigma_adm_kN_m2


@dataclass
class ResultadoPredimensionado:
    """Resultado completo del predimensionado para todos los niveles."""

    losas: list[SeccionLosa] = field(default_factory=list)
    vigas: list[SeccionViga] = field(default_factory=list)
    columnas: list[SeccionColumna] = field(default_factory=list)
    zapata: SeccionZapata = field(default_factory=SeccionZapata)
    advertencias: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        """Texto resumido para mostrar en la UI."""
        lines = ["=== PREDIMENSIONADO ESTRUCTURAL (CIRSOC 201-2005) ===", ""]
        lines.append("LOSAS:")
        for losa in self.losas:
            lines.append("  {:12s}  h = {:5.2f}m ({:5.1f}cm)  q = {:.1f} kN/m²".format(
                losa.nivel, losa.espesor_m, losa.espesor_cm, losa.carga_total_kN_m2))
        lines.append("")
        lines.append("VIGAS:")
        for viga in self.vigas:
            lines.append("  {:12s}  {} × {}m luz  q_lin = {:.1f} kN/m".format(
                viga.nivel, viga.descripcion, viga.luz_libre_m, viga.carga_lineal_kN_m))
        lines.append("")
        lines.append("COLUMNAS (carga acumulada + sección mínima):")
        for col in self.columnas:
            lines.append("  {:12s}  {}  N = {:.0f} kN  A_req = {:.4f} m²".format(
                col.nivel, col.descripcion, col.carga_acumulada_kN, col.area_requerida_m2))
        lines.append("")
        lines.append("ZAPATA CORRIDA / AISLADA (típica):")
        lines.append("  {}  N = {:.0f} kN  A_req = {:.3f} m²  σ_adm = {:.2f} kgf/cm²".format(
            self.zapata.descripcion, self.zapata.carga_total_kN,
            self.zapata.area_requerida_m2, self.zapata.sigma_adm_kgf_cm2))
        if self.advertencias:
            lines.append("")
            lines.append("ADVERTENCIAS:")
            for adv in self.advertencias:
                lines.append("  [!] " + adv)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Motor de cálculo
# ---------------------------------------------------------------------------

def _redondear_arriba_5cm(valor_m: float) -> float:
    """Redondea un valor en metros al múltiplo de 5 cm superior."""
    cm = valor_m * 100.0
    return math.ceil(cm / 5.0) * 5.0 / 100.0


def predimensionar(params: "ParametrosEdificio") -> ResultadoPredimensionado:
    """Calcula el predimensionado estructural a partir de los parámetros del edificio.

    Args:
        params: Instancia de ParametrosEdificio validada.

    Returns:
        ResultadoPredimensionado con secciones de losas, vigas, columnas y zapatas.
    """
    resultado = ResultadoPredimensionado()

    luz_max_m = min(params.frente, params.fondo)  # Luz libre conservadora
    f_c_mpa = params.f_c_mpa
    area_planta = params.superficie_planta_tipo

    # ------------------------------------------------------------------
    # Losas
    # ------------------------------------------------------------------
    h_losa_min = max(luz_max_m / 35.0, 0.12)
    h_losa = _redondear_arriba_5cm(h_losa_min)

    for i in range(1, params.pisos_tipo + 1):
        nivel = "P{:02d}".format(i)
        resultado.losas.append(SeccionLosa(
            nivel=nivel,
            luz_libre_m=luz_max_m,
            espesor_m=h_losa,
            carga_total_kN_m2=CARGA_PISO_TIPO_KN_M2,
        ))

    if params.tiene_azotea:
        h_losa_azotea = max(luz_max_m / 35.0, 0.12)
        h_losa_azotea = _redondear_arriba_5cm(h_losa_azotea)
        resultado.losas.append(SeccionLosa(
            nivel="AZO",
            luz_libre_m=luz_max_m,
            espesor_m=h_losa_azotea,
            carga_total_kN_m2=CARGA_AZOTEA_KN_M2,
        ))

    # ------------------------------------------------------------------
    # Vigas
    # ------------------------------------------------------------------
    h_viga_min = max(luz_max_m / 12.0, 0.40)
    h_viga = _redondear_arriba_5cm(h_viga_min)
    b_viga_min = max(h_viga / 2.0, 0.20)
    b_viga = _redondear_arriba_5cm(b_viga_min)
    carga_lineal = CARGA_PISO_TIPO_KN_M2 * (params.fondo / 2.0)

    for i in range(1, params.pisos_tipo + 1):
        nivel = "P{:02d}".format(i)
        resultado.vigas.append(SeccionViga(
            nivel=nivel,
            luz_libre_m=luz_max_m,
            alto_m=h_viga,
            ancho_m=b_viga,
            carga_lineal_kN_m=carga_lineal,
        ))

    if params.tiene_azotea:
        carga_lineal_azotea = CARGA_AZOTEA_KN_M2 * (params.fondo / 2.0)
        resultado.vigas.append(SeccionViga(
            nivel="AZO",
            luz_libre_m=luz_max_m,
            alto_m=h_viga,
            ancho_m=b_viga,
            carga_lineal_kN_m=carga_lineal_azotea,
        ))

    # ------------------------------------------------------------------
    # Columnas — carga acumulada nivel a nivel (de arriba hacia abajo)
    # ------------------------------------------------------------------
    cant_columnas = _estimar_cant_columnas(params)
    carga_por_nivel_kN = CARGA_PISO_TIPO_KN_M2 * area_planta

    carga_acumulada = 0.0
    for i in range(params.pisos_tipo, 0, -1):
        nivel = "P{:02d}".format(i)
        if i == params.pisos_tipo and params.tiene_azotea:
            carga_acumulada += CARGA_AZOTEA_KN_M2 * area_planta
        carga_acumulada += carga_por_nivel_kN
        carga_columna = carga_acumulada / cant_columnas

        f_c_kN_m2 = f_c_mpa * 1000.0
        area_req = carga_columna / (0.45 * f_c_kN_m2)
        lado_req = math.sqrt(area_req)
        lado = max(_redondear_arriba_5cm(lado_req), 0.25)

        resultado.columnas.append(SeccionColumna(
            nivel=nivel,
            carga_acumulada_kN=carga_columna,
            lado_m=lado,
            f_c_mpa=f_c_mpa,
        ))

        if lado / params.altura_tipo > 14.0:
            resultado.advertencias.append(
                "Columna {} — esbeltez {:.1f} > 14 (verificar pandeo según CIRSOC 201 §10.10)".format(
                    nivel, lado / params.altura_tipo)
            )

    resultado.columnas.reverse()  # Presentar de PB hacia arriba

    # ------------------------------------------------------------------
    # Zapatas
    # ------------------------------------------------------------------
    carga_total_edificio = (
        CARGA_PISO_TIPO_KN_M2 * area_planta * params.pisos_tipo
        + (CARGA_AZOTEA_KN_M2 * area_planta if params.tiene_azotea else 0.0)
    )
    carga_por_zapata = carga_total_edificio / cant_columnas
    sigma_kN_m2 = SIGMA_ADM_SUELO_KGF_CM2 * 98.0665
    area_zap = carga_por_zapata / sigma_kN_m2
    lado_zap = _redondear_arriba_5cm(math.sqrt(area_zap))

    resultado.zapata = SeccionZapata(
        nivel="Fundacion",
        carga_total_kN=carga_por_zapata,
        lado_m=lado_zap,
        sigma_adm_kgf_cm2=SIGMA_ADM_SUELO_KGF_CM2,
    )

    # ------------------------------------------------------------------
    # Advertencias generales
    # ------------------------------------------------------------------
    if params.pisos_tipo > 12:
        resultado.advertencias.append(
            "Edificio de {:d} pisos — considerar verificación sísmica INPRES-CIRSOC 103.".format(
                params.pisos_tipo)
        )
    if params.frente < 6.0:
        resultado.advertencias.append(
            "Frente de lote {:.1f}m — revisar posibilidad de luz libre para vigas.".format(params.frente)
        )
    if h_losa > 0.25:
        resultado.advertencias.append(
            "Losa h = {:.2f}m — considerar losa nervurada o bidireccional.".format(h_losa)
        )

    return resultado


def _estimar_cant_columnas(params: "ParametrosEdificio") -> int:
    """Estima la cantidad de columnas en planta según el sistema estructural y dimensiones del lote."""
    if params.sistema_estructural == "muros":
        return max(int(params.frente / 5.0) * 2, 4)

    cols_frente = max(int(params.frente / 5.0) + 1, 2)
    cols_fondo = max(int(params.fondo / 5.0) + 1, 3)
    return cols_frente * cols_fondo
