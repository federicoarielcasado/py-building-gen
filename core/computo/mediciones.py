"""Cómputo métrico por rubro a partir de los parámetros del edificio.

Calcula cantidades en las unidades propias de cada rubro (m², m³, kg, u)
usando los parámetros del edificio y los resultados del predimensionado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.predimensionado import predimensionar, ResultadoPredimensionado, _estimar_cant_columnas

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio


# ---------------------------------------------------------------------------
# Dataclasses de output
# ---------------------------------------------------------------------------

@dataclass
class ItemMedicion:
    codigo: str
    descripcion: str
    unidad: str
    cantidad: float

    @property
    def cantidad_redondeada(self) -> float:
        return round(self.cantidad, 2)


@dataclass
class RubroMedicion:
    numero: int
    nombre: str
    items: list[ItemMedicion] = field(default_factory=list)

    def agregar(self, codigo: str, descripcion: str, unidad: str, cantidad: float) -> None:
        self.items.append(ItemMedicion(codigo, descripcion, unidad, cantidad))


@dataclass
class MedicionesEdificio:
    rubros: list[RubroMedicion] = field(default_factory=list)
    sup_planta_m2: float = 0.0
    sup_total_m2: float = 0.0
    cant_columnas: int = 0
    predim: ResultadoPredimensionado = field(default_factory=ResultadoPredimensionado)

    def rubro(self, numero: int) -> RubroMedicion | None:
        return next((r for r in self.rubros if r.numero == numero), None)


# ---------------------------------------------------------------------------
# Motor de cálculo
# ---------------------------------------------------------------------------

def calcular(params: "ParametrosEdificio") -> MedicionesEdificio:
    """Calcula el cómputo métrico completo del edificio.

    Args:
        params: Parámetros validados del edificio.

    Returns:
        MedicionesEdificio con todos los rubros y cantidades.
    """
    predim = predimensionar(params)
    med = MedicionesEdificio(
        sup_planta_m2=params.superficie_planta_tipo,
        sup_total_m2=params.superficie_total_edificio,
        cant_columnas=_estimar_cant_columnas(params),
        predim=predim,
    )

    f = params.frente
    fo = params.fondo
    perimetro = 2 * (f + fo)
    sup_planta = f * fo
    sup_edif = sup_planta * 0.70       # FOS típico CABA
    cant_col = med.cant_columnas
    alt_pb = params.altura_pb
    alt_tipo = params.altura_tipo
    n_pisos = params.pisos_tipo
    alt_total = params.altura_total

    losa = predim.losas[0] if predim.losas else None
    viga = predim.vigas[0] if predim.vigas else None
    col  = predim.columnas[0] if predim.columnas else None
    zap  = predim.zapata

    h_losa  = losa.espesor_m if losa else 0.20
    b_viga  = viga.ancho_m   if viga else 0.25
    h_viga  = viga.alto_m    if viga else 0.50
    lado_col = col.lado_m    if col  else 0.30

    # Estimación vigas: una por eje en cada dirección, cada paso de 5 m
    paso = 5.0
    ejes_x = math.floor(f / paso) + 1
    ejes_y = math.floor(fo / paso) + 1
    long_vigas_x = f * ejes_y
    long_vigas_y = fo * ejes_x
    long_vigas_total = (long_vigas_x + long_vigas_y) * n_pisos

    # ---------------------------------------------------------------------------
    # Rubro 1 — Trabajos preliminares
    # ---------------------------------------------------------------------------
    r1 = RubroMedicion(1, "Trabajos preliminares")
    r1.agregar("1.1", "Obrador y limpieza de obra",           "gl",  1.0)
    r1.agregar("1.2", "Demolición / limpieza terreno",        "m²",  f * fo)
    r1.agregar("1.3", "Cerco de obra y carteles",             "m",   perimetro)
    r1.agregar("1.4", "Replanteo topográfico",                "m²",  f * fo)
    med.rubros.append(r1)

    # ---------------------------------------------------------------------------
    # Rubro 2 — Movimiento de suelos
    # ---------------------------------------------------------------------------
    r2 = RubroMedicion(2, "Movimiento de suelos")
    vol_exc_general = f * fo * params.cant_subsuelos * alt_tipo if params.tiene_subsuelo else 0.0
    vol_exc_zapatas = cant_col * zap.lado_m ** 2 * 0.70
    vol_relleno = vol_exc_general * 0.15
    r2.agregar("2.1", "Excavación subsuelos",                 "m³",  vol_exc_general)
    r2.agregar("2.2", "Excavación zapatas y vigas fundación", "m³",  vol_exc_zapatas)
    r2.agregar("2.3", "Relleno y compactación",               "m³",  vol_relleno)
    r2.agregar("2.4", "Retiro de tierra sobrante",            "m³",  vol_exc_general + vol_exc_zapatas - vol_relleno)
    med.rubros.append(r2)

    # ---------------------------------------------------------------------------
    # Rubro 3 — Fundaciones
    # ---------------------------------------------------------------------------
    r3 = RubroMedicion(3, "Fundaciones")
    vol_zap_ha  = cant_col * zap.lado_m ** 2 * 0.40        # zapatas h=40cm
    arm_zap_kg  = vol_zap_ha * 100                          # 100 kg/m³ típico
    enc_zap_m2  = cant_col * 4 * zap.lado_m * 0.40         # 4 caras
    vol_vf_ha   = perimetro * 0.30 * 0.60                  # viga de fundación

    r3.agregar("3.1", "Hormigón HA zapatas aisaldas",         "m³",  vol_zap_ha)
    r3.agregar("3.2", "Hormigón HA vigas de fundación",       "m³",  vol_vf_ha)
    r3.agregar("3.3", "Armadura zapatas y vigas de fund.",     "kg",  arm_zap_kg + vol_vf_ha * 80)
    r3.agregar("3.4", "Encofrado zapatas",                    "m²",  enc_zap_m2)
    r3.agregar("3.5", "Hormigón pobre (H-13) base zapatas",   "m³",  cant_col * zap.lado_m ** 2 * 0.10)
    med.rubros.append(r3)

    # ---------------------------------------------------------------------------
    # Rubro 4 — Estructura
    # ---------------------------------------------------------------------------
    r4 = RubroMedicion(4, "Estructura")

    vol_col_ha  = lado_col ** 2 * alt_tipo * cant_col * n_pisos
    vol_col_pb  = lado_col ** 2 * alt_pb   * cant_col
    vol_viga_ha = b_viga * h_viga * long_vigas_total
    vol_losa_ha = sup_edif * h_losa * (n_pisos + (1 if params.tiene_azotea else 0))

    arm_col_kg  = (vol_col_ha + vol_col_pb) * 120
    arm_viga_kg = vol_viga_ha * 150
    arm_losa_kg = vol_losa_ha * 90

    enc_col_m2  = cant_col * 4 * lado_col * (alt_tipo * n_pisos + alt_pb)
    enc_viga_m2 = long_vigas_total * (2 * h_viga + b_viga)
    enc_losa_m2 = sup_edif * (n_pisos + (1 if params.tiene_azotea else 0))

    r4.agregar("4.1", "Hormigón HA columnas",                 "m³",  vol_col_ha + vol_col_pb)
    r4.agregar("4.2", "Hormigón HA vigas",                    "m³",  vol_viga_ha)
    r4.agregar("4.3", "Hormigón HA losas",                    "m³",  vol_losa_ha)
    r4.agregar("4.4", "Armadura columnas",                    "kg",  arm_col_kg)
    r4.agregar("4.5", "Armadura vigas",                       "kg",  arm_viga_kg)
    r4.agregar("4.6", "Armadura losas (malla + bastones)",    "kg",  arm_losa_kg)
    r4.agregar("4.7", "Encofrado columnas",                   "m²",  enc_col_m2)
    r4.agregar("4.8", "Encofrado vigas",                      "m²",  enc_viga_m2)
    r4.agregar("4.9", "Encofrado losas",                      "m²",  enc_losa_m2)
    med.rubros.append(r4)

    # ---------------------------------------------------------------------------
    # Rubro 5 — Mampostería
    # ---------------------------------------------------------------------------
    r5 = RubroMedicion(5, "Mampostería")
    sup_muros_ext = perimetro * alt_total * 0.80   # descontando aberturas aprox
    # Tabiques interiores: estimado 1.2 m de tabique por m² de planta
    sup_tabiques  = sup_planta * 1.2 * n_pisos
    r5.agregar("5.1", "Muro exterior ladrillo cerámico 18cm", "m²",  sup_muros_ext)
    r5.agregar("5.2", "Tabique interior ladrillo cerámico 12cm","m²", sup_tabiques)
    med.rubros.append(r5)

    # ---------------------------------------------------------------------------
    # Rubro 6 — Revoques y revestimientos
    # ---------------------------------------------------------------------------
    r6 = RubroMedicion(6, "Revoques y revestimientos")
    sup_revoque = (sup_muros_ext + sup_tabiques) * 2  # dos caras
    r6.agregar("6.1", "Revoque grueso interior",              "m²",  sup_revoque * 0.70)
    r6.agregar("6.2", "Revoque fino interior",                "m²",  sup_revoque * 0.70)
    r6.agregar("6.3", "Revoque exterior (frente/medianeras)", "m²",  sup_muros_ext)
    r6.agregar("6.4", "Azulejos baños (estimado)",            "m²",  params.cant_departamentos_total * 15.0)
    med.rubros.append(r6)

    # ---------------------------------------------------------------------------
    # Rubro 7 — Carpinterías
    # ---------------------------------------------------------------------------
    r7 = RubroMedicion(7, "Carpinterías")
    # Puertas: 1 entrada + 3 interiores por depto
    puertas_ext   = 1
    puertas_int   = params.cant_departamentos_total * 3
    ventanas_tipo = params.cant_departamentos_total * 2
    r7.agregar("7.1", "Puerta exterior blindex 90×210cm",     "u",   puertas_ext)
    r7.agregar("7.2", "Puerta interior placa 90×200cm",       "u",   puertas_int)
    r7.agregar("7.3", "Ventana aluminio 1.50×1.20m",          "u",   ventanas_tipo)
    r7.agregar("7.4", "Ventana aluminio 1.00×1.00m (baños)",  "u",   params.cant_departamentos_total)
    med.rubros.append(r7)

    # ---------------------------------------------------------------------------
    # Rubro 8 — Cubiertas e impermeabilizaciones
    # ---------------------------------------------------------------------------
    r8 = RubroMedicion(8, "Cubiertas e impermeabilizaciones")
    sup_cubierta = sup_edif
    r8.agregar("8.1", "Membrana asfáltica 4mm azotea",        "m²",  sup_cubierta)
    r8.agregar("8.2", "Protección mecánica membrana",         "m²",  sup_cubierta)
    r8.agregar("8.3", "Pintura asfáltica balcones/terrazas",  "m²",  sup_planta * 0.10 * n_pisos)
    med.rubros.append(r8)

    # ---------------------------------------------------------------------------
    # Rubros 9-13 — Instalaciones (por m² de planta si activa)
    # ---------------------------------------------------------------------------
    sup_inst = sup_planta * (n_pisos + 1)

    if params.instalacion_sanitaria:
        r9 = RubroMedicion(9, "Instalación sanitaria")
        r9.agregar("9.1", "Cañería agua fría DN25 PP-R",      "m",   sup_inst * 0.60)
        r9.agregar("9.2", "Cañería agua caliente DN20 PP-R",  "m",   sup_inst * 0.40)
        r9.agregar("9.3", "Cañería desagüe cloacal PVC DN63", "m",   sup_inst * 0.30)
        r9.agregar("9.4", "Cañería desagüe PVC DN110",        "m",   sup_inst * 0.20)
        r9.agregar("9.5", "Artefactos sanitarios por depto",  "gl",  params.cant_departamentos_total)
        r9.agregar("9.6", "Tanque cisterna + tanque elevado", "u",   1.0)
        r9.agregar("9.7", "Bomba presurización",              "u",   1.0)
        med.rubros.append(r9)

    if params.instalacion_electrica:
        r10 = RubroMedicion(10, "Instalación eléctrica")
        r10.agregar("10.1","Cañería eléctrica corrugada DN20","m",   sup_inst * 1.20)
        r10.agregar("10.2","Conductor 2.5mm² (circuitos)",    "m",   sup_inst * 2.50)
        r10.agregar("10.3","Tablero seccional por depto",     "u",   params.cant_departamentos_total)
        r10.agregar("10.4","Tablero general de BT",           "u",   1.0)
        r10.agregar("10.5","Artefactos iluminación (estimado)","gl", params.cant_departamentos_total)
        med.rubros.append(r10)

    if params.instalacion_gas:
        r11 = RubroMedicion(11, "Instalación de gas")
        r11.agregar("11.1","Cañería cobre DN20",              "m",   sup_inst * 0.25)
        r11.agregar("11.2","Gabinete medidores",              "u",   math.ceil(params.cant_departamentos_total / 4))
        r11.agregar("11.3","Llave de paso por depto",         "u",   params.cant_departamentos_total)
        med.rubros.append(r11)

    if params.instalacion_incendio:
        r12 = RubroMedicion(12, "Instalación contra incendio")
        r12.agregar("12.1","Red húmeda vertical DN63 PVC",    "m",   alt_total * 1.20)
        r12.agregar("12.2","Boca de incendio por piso",       "u",   n_pisos + 1)
        r12.agregar("12.3","Matafuegos ABC 10kg por piso",    "u",   n_pisos + 1)
        r12.agregar("12.4","Central de detección de incendio","u",   1.0)
        r12.agregar("12.5","Detector de humo por depto",      "u",   params.cant_departamentos_total)
        med.rubros.append(r12)

    if params.instalacion_termomecanica:
        r13 = RubroMedicion(13, "Instalación termomecánica")
        r13.agregar("13.1","Split frío-calor por depto",      "u",   params.cant_departamentos_total * 2)
        r13.agregar("13.2","Conducto retorno aire (m²)",      "m²",  sup_inst * 0.08)
        med.rubros.append(r13)

    # ---------------------------------------------------------------------------
    # Rubro 14 — Pintura y terminaciones
    # ---------------------------------------------------------------------------
    r14 = RubroMedicion(14, "Pintura y terminaciones")
    sup_pintura = sup_revoque + sup_planta * (n_pisos + 1)  # muros + cielos
    r14.agregar("14.1","Pintura látex interior (2 manos)",    "m²",  sup_pintura * 0.70)
    r14.agregar("14.2","Pintura frente exterior",             "m²",  f * alt_total)
    r14.agregar("14.3","Contrapisos y pisos por depto",       "m²",  sup_planta * n_pisos)
    med.rubros.append(r14)

    # ---------------------------------------------------------------------------
    # Rubro 15 — Equipamiento
    # ---------------------------------------------------------------------------
    r15 = RubroMedicion(15, "Equipamiento")
    r15.agregar("15.1","Ascensor (incl. instalación)",        "u",   params.cant_ascensores)
    r15.agregar("15.2","Tanque cisterna 10.000 L",            "u",   1.0)
    r15.agregar("15.3","Tanque elevado 5.000 L por sector",   "u",   math.ceil(params.cant_departamentos_total / 8))
    r15.agregar("15.4","Grupo electrógeno emergencia",        "u",   1.0)
    med.rubros.append(r15)

    return med
