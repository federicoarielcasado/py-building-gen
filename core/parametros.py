"""Dataclass central con todos los parámetros del edificio a generar."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


TipoHormigon = Literal["H-21", "H-25", "H-30"]
TipoAcero = Literal["ADN 420", "AL 220"]
TipoSistemaEstructural = Literal["porticos", "muros", "mixto"]
TipoPB = Literal["comercial", "porteria", "vivienda", "mixto"]
UbicacionCochera = Literal["pb", "subsuelo"]
UbicacionSalaMaquinas = Literal["azotea", "subsuelo"]
Moneda = Literal["ARS", "USD"]


@dataclass
class TipologiaDepto:
    """Un tipo de departamento y su cantidad por piso."""

    tipo: Literal["1amb", "2amb", "3amb", "4amb", "duplex", "estudio"]
    cantidad: int
    superficie_m2: float = 0.0


@dataclass
class ParametrosEdificio:
    """Parámetros completos del edificio a generar en Revit vía Dynamo."""

    # ------------------------------------------------------------------
    # Identificación del proyecto
    # ------------------------------------------------------------------
    nombre_proyecto: str = "Edificio Caballito"
    autor: str = "Federico A. Casado"

    # ------------------------------------------------------------------
    # Lote
    # ------------------------------------------------------------------
    frente: float = 10.0
    fondo: float = 24.0
    usar_lote_real: bool = False

    # ------------------------------------------------------------------
    # Volumetría
    # ------------------------------------------------------------------
    pisos_tipo: int = 6
    altura_pb: float = 3.50
    altura_tipo: float = 2.80
    tiene_subsuelo: bool = False
    cant_subsuelos: int = 0
    tiene_azotea: bool = True

    # ------------------------------------------------------------------
    # Planta baja
    # ------------------------------------------------------------------
    tipo_pb: TipoPB = "porteria"
    tiene_cochera: bool = False
    cochera_ubicacion: UbicacionCochera = "pb"

    # ------------------------------------------------------------------
    # Servicios
    # ------------------------------------------------------------------
    cant_ascensores: int = 1
    cant_cajas_escalera: int = 1
    sala_maquinas: UbicacionSalaMaquinas = "azotea"

    # ------------------------------------------------------------------
    # Departamentos por piso tipo
    # ------------------------------------------------------------------
    cant_depto_tipo: int = 2
    mix_tipologias: list[TipologiaDepto] = field(default_factory=lambda: [
        TipologiaDepto(tipo="2amb", cantidad=1, superficie_m2=55.0),
        TipologiaDepto(tipo="3amb", cantidad=1, superficie_m2=75.0),
    ])

    # ------------------------------------------------------------------
    # Estructura
    # ------------------------------------------------------------------
    sistema_estructural: TipoSistemaEstructural = "porticos"
    hormigon_tipo: TipoHormigon = "H-21"
    acero_tipo: TipoAcero = "ADN 420"

    # ------------------------------------------------------------------
    # Instalaciones a generar
    # ------------------------------------------------------------------
    instalacion_sanitaria: bool = True
    instalacion_electrica: bool = True
    instalacion_gas: bool = True
    instalacion_incendio: bool = True
    instalacion_termomecanica: bool = False

    # ------------------------------------------------------------------
    # Presupuesto
    # ------------------------------------------------------------------
    incluir_honorarios: bool = True
    incluir_gastos_generales: bool = True
    moneda: Moneda = "ARS"

    # ------------------------------------------------------------------
    # Propiedades derivadas
    # ------------------------------------------------------------------

    @property
    def altura_total(self) -> float:
        """Altura total del edificio desde PB hasta techo de último piso tipo."""
        return self.altura_pb + self.altura_tipo * self.pisos_tipo

    @property
    def superficie_planta_tipo(self) -> float:
        """Superficie bruta de planta tipo en m²."""
        return self.frente * self.fondo

    @property
    def superficie_total_edificio(self) -> float:
        """Superficie total construida incluyendo PB, pisos tipo y azotea."""
        niveles = 1 + self.pisos_tipo + (1 if self.tiene_azotea else 0)
        niveles += self.cant_subsuelos
        return self.superficie_planta_tipo * niveles

    @property
    def cant_departamentos_total(self) -> int:
        """Total de departamentos en todos los pisos tipo."""
        return self.cant_depto_tipo * self.pisos_tipo

    @property
    def f_c_mpa(self) -> float:
        """Resistencia característica del hormigón f'c en MPa."""
        tabla = {"H-21": 21.0, "H-25": 25.0, "H-30": 30.0}
        return tabla[self.hormigon_tipo]

    @property
    def fy_mpa(self) -> float:
        """Tensión de fluencia del acero fy en MPa."""
        tabla = {"ADN 420": 420.0, "AL 220": 220.0}
        return tabla[self.acero_tipo]

    def validar(self) -> list[str]:
        """Valida consistencia de parámetros. Retorna lista de errores encontrados."""
        errores: list[str] = []

        if not (1 <= self.pisos_tipo <= 20):
            errores.append("pisos_tipo debe estar entre 1 y 20.")
        if not (0 <= self.cant_subsuelos <= 2):
            errores.append("cant_subsuelos debe ser 0, 1 o 2.")
        if self.tiene_subsuelo and self.cant_subsuelos == 0:
            errores.append("tiene_subsuelo=True pero cant_subsuelos=0.")
        if not self.tiene_subsuelo and self.cant_subsuelos > 0:
            errores.append("cant_subsuelos > 0 pero tiene_subsuelo=False.")
        if self.tiene_cochera and self.cochera_ubicacion == "subsuelo" and not self.tiene_subsuelo:
            errores.append("cochera en subsuelo pero el edificio no tiene subsuelo.")
        if not (1 <= self.cant_ascensores <= 2):
            errores.append("cant_ascensores debe ser 1 o 2.")
        if not (1 <= self.cant_cajas_escalera <= 2):
            errores.append("cant_cajas_escalera debe ser 1 o 2.")
        if self.frente <= 0 or self.fondo <= 0:
            errores.append("Las dimensiones del lote deben ser positivas.")
        if self.altura_pb < 2.40:
            errores.append("altura_pb mínima es 2.40m (Código de Edificación CABA).")
        if self.altura_tipo < 2.40:
            errores.append("altura_tipo mínima es 2.40m (Código de Edificación CABA).")
        if self.cant_depto_tipo != sum(t.cantidad for t in self.mix_tipologias):
            errores.append("cant_depto_tipo no coincide con la suma de tipologías en mix_tipologias.")

        return errores

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def guardar(self, path: Path | str) -> Path:
        """Serializa los parámetros a un archivo JSON (.pbg)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return out

    @classmethod
    def cargar(cls, path: Path | str) -> "ParametrosEdificio":
        """Carga parámetros desde un archivo JSON (.pbg)."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tipologias = [TipologiaDepto(**t) for t in data.pop("mix_tipologias", [])]
        return cls(**data, mix_tipologias=tipologias)
