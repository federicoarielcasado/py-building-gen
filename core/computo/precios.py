"""Base de precios unificada: INDEC ICC + UOCRA Zona A + Sismat.

Carga los tres archivos JSON de referencia y expone métodos de consulta.
Los precios se expresan en ARS. La conversión a USD se aplica en el
módulo de análisis según el tipo de cambio oficial BNA vigente.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_DATA_DIR = Path("data/precios")


@dataclass
class PreciosManoObra:
    oficial_especializado_jornal: float   # ARS/jornada
    oficial_jornal: float
    ayudante_jornal: float
    cargas_sociales_pct: float            # factor multiplicador (ej: 0.75 → +75%)
    rendimientos: dict[str, float]        # m²/jornada o kg/jornada por actividad

    def jornal_con_cargas(self, categoria: str = "oficial") -> float:
        """Retorna jornal diario con cargas sociales incluidas."""
        base = {
            "oficial_especializado": self.oficial_especializado_jornal,
            "oficial": self.oficial_jornal,
            "ayudante": self.ayudante_jornal,
        }.get(categoria, self.oficial_jornal)
        return base * (1 + self.cargas_sociales_pct)

    def costo_mo_por_m2(self, actividad: str, categoria: str = "oficial") -> float:
        """Costo de mano de obra por m² para una actividad dada."""
        rendimiento = self.rendimientos.get(actividad, 10.0)
        return self.jornal_con_cargas(categoria) / rendimiento


@dataclass
class PreciosMateriales:
    hormigon: dict[str, float]    # "H-21_m3", "H-25_m3", "H-30_m3"
    acero: dict[str, float]       # "ADN_420_kg", "AL_220_kg", "malla_Q188_m2"
    mamposteria: dict[str, float]
    morteros: dict[str, float]
    impermeabilizacion: dict[str, float]
    carpinterias: dict[str, float]
    instalaciones: dict[str, float]
    ascensores: dict[str, float]

    def hormigon_m3(self, tipo: str) -> float:
        """Precio de hormigón elaborado por m³. tipo: 'H-21', 'H-25' o 'H-30'."""
        key = f"{tipo}_m3"
        return self.hormigon.get(key, self.hormigon.get("H-21_m3", 125000))

    def acero_kg(self, tipo: str = "ADN 420") -> float:
        """Precio de acero de refuerzo por kg."""
        key = "ADN_420_kg" if "420" in tipo else "AL_220_kg"
        return self.acero.get(key, 2100)


@dataclass
class IndiceICC:
    nivel_general: float          # índice base 2016=100
    variacion_mensual_pct: float
    variacion_anual_pct: float
    costo_m2_vivienda_media: float
    costo_m2_vivienda_alta: float
    fecha: str


@dataclass
class CatalogoPrecios:
    materiales: PreciosMateriales
    mano_obra: PreciosManoObra
    icc: IndiceICC
    fecha: str

    # Tipo de cambio referencial (se puede actualizar externamente)
    tipo_cambio_usd: float = 1250.0

    def precio_en(self, valor_ars: float, moneda: str = "ARS") -> float:
        """Convierte un valor ARS a la moneda solicitada."""
        if moneda == "USD":
            return round(valor_ars / self.tipo_cambio_usd, 2)
        return round(valor_ars, 2)


def cargar(data_dir: Path = _DATA_DIR) -> CatalogoPrecios:
    """Carga el catálogo de precios desde los archivos JSON de referencia.

    Args:
        data_dir: Directorio que contiene los tres archivos de precios.

    Returns:
        CatalogoPrecios listo para usar en el análisis de precios.
    """
    data_dir = Path(data_dir)

    with open(data_dir / "icc_indec_2026.json", encoding="utf-8") as f:
        icc_raw = json.load(f)

    with open(data_dir / "uocra_2026.json", encoding="utf-8") as f:
        uocra_raw = json.load(f)

    with open(data_dir / "materiales_sismat.json", encoding="utf-8") as f:
        sismat_raw = json.load(f)

    mats = sismat_raw["materiales"]

    materiales = PreciosMateriales(
        hormigon=mats["hormigon_elaborado"],
        acero=mats["acero"],
        mamposteria=mats["mamposteria"],
        morteros=mats["morteros_kg"],
        impermeabilizacion=mats["impermeabilizacion"],
        carpinterias=mats["carpinterias"],
        instalaciones=mats["instalaciones"],
        ascensores=mats["ascensores"],
    )

    cats = uocra_raw["categorias"]
    mano_obra = PreciosManoObra(
        oficial_especializado_jornal=cats["oficial_especializado"]["jornal_diario_ARS"],
        oficial_jornal=cats["oficial"]["jornal_diario_ARS"],
        ayudante_jornal=cats["ayudante"]["jornal_diario_ARS"],
        cargas_sociales_pct=uocra_raw["cargas_sociales_pct"],
        rendimientos=uocra_raw["rendimientos_m2_jornada"],
    )

    ng = icc_raw["nivel_general"]
    ref = icc_raw["costo_m2_referencia_ARS"]
    icc = IndiceICC(
        nivel_general=ng["base_2016_100"],
        variacion_mensual_pct=ng["variacion_mensual_pct"],
        variacion_anual_pct=ng["variacion_anual_pct"],
        costo_m2_vivienda_media=ref["vivienda_multifamiliar_media"],
        costo_m2_vivienda_alta=ref["vivienda_multifamiliar_alta"],
        fecha=icc_raw["fecha"],
    )

    return CatalogoPrecios(
        materiales=materiales,
        mano_obra=mano_obra,
        icc=icc,
        fecha=icc_raw["fecha"],
    )
