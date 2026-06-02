"""Análisis de precios unitarios y presupuesto completo.

Combina las mediciones del edificio con el catálogo de precios para
producir un presupuesto con desglose de materiales, mano de obra y equipos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.computo.mediciones import MedicionesEdificio, RubroMedicion, ItemMedicion
from core.computo.precios import CatalogoPrecios

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio


# ---------------------------------------------------------------------------
# Dataclasses de análisis
# ---------------------------------------------------------------------------

@dataclass
class LineaAnalisis:
    descripcion: str
    unidad: str
    cantidad: float
    precio_unitario: float
    tipo: str   # "material" | "mano_obra" | "equipo"

    @property
    def subtotal(self) -> float:
        return self.cantidad * self.precio_unitario


@dataclass
class AnalisisItem:
    """Análisis de precio unitario de un ítem de cómputo."""

    codigo: str
    descripcion: str
    unidad: str
    cantidad_obra: float
    lineas: list[LineaAnalisis] = field(default_factory=list)

    @property
    def total_material(self) -> float:
        return sum(l.subtotal for l in self.lineas if l.tipo == "material")

    @property
    def total_mano_obra(self) -> float:
        return sum(l.subtotal for l in self.lineas if l.tipo == "mano_obra")

    @property
    def total_equipo(self) -> float:
        return sum(l.subtotal for l in self.lineas if l.tipo == "equipo")

    @property
    def precio_unitario(self) -> float:
        return self.total_material + self.total_mano_obra + self.total_equipo

    @property
    def subtotal_obra(self) -> float:
        return self.precio_unitario * self.cantidad_obra


@dataclass
class RubroAnalizado:
    numero: int
    nombre: str
    items: list[AnalisisItem] = field(default_factory=list)

    @property
    def subtotal(self) -> float:
        return sum(i.subtotal_obra for i in self.items)


@dataclass
class PresupuestoCompleto:
    """Presupuesto total del edificio con todos los rubros analizados."""

    rubros: list[RubroAnalizado] = field(default_factory=list)
    pct_gastos_generales: float = 0.20
    pct_honorarios: float = 0.10
    moneda: str = "ARS"
    fecha: str = ""
    incluir_gastos: bool = True
    incluir_honorarios: bool = True

    @property
    def costo_directo(self) -> float:
        return sum(r.subtotal for r in self.rubros)

    @property
    def gastos_generales(self) -> float:
        return self.costo_directo * self.pct_gastos_generales if self.incluir_gastos else 0.0

    @property
    def honorarios(self) -> float:
        return (self.costo_directo + self.gastos_generales) * self.pct_honorarios if self.incluir_honorarios else 0.0

    @property
    def total(self) -> float:
        return self.costo_directo + self.gastos_generales + self.honorarios

    @property
    def resumen_por_rubro(self) -> list[dict]:
        base = self.costo_directo or 1.0
        return [
            {
                "numero": r.numero,
                "nombre": r.nombre,
                "subtotal": r.subtotal,
                "pct_sobre_total": r.subtotal / base * 100,
            }
            for r in self.rubros
        ]


# ---------------------------------------------------------------------------
# Precios unitarios por ítem (ARS, valores de referencia Sismat + UOCRA 2026)
# ---------------------------------------------------------------------------

def _analizar_item(
    item: ItemMedicion,
    precios: CatalogoPrecios,
    params: "ParametrosEdificio",
) -> AnalisisItem:
    """Construye el análisis de precio unitario para un ítem de cómputo."""

    m = precios.materiales
    mo = precios.mano_obra
    ai = AnalisisItem(
        codigo=item.codigo,
        descripcion=item.descripcion,
        unidad=item.unidad,
        cantidad_obra=item.cantidad,
    )

    def mat(desc: str, unidad: str, qty: float, pu: float) -> None:
        ai.lineas.append(LineaAnalisis(desc, unidad, qty, pu, "material"))

    def mano(desc: str, unidad: str, qty: float, pu: float) -> None:
        ai.lineas.append(LineaAnalisis(desc, unidad, qty, pu, "mano_obra"))

    def equipo(desc: str, unidad: str, qty: float, pu: float) -> None:
        ai.lineas.append(LineaAnalisis(desc, unidad, qty, pu, "equipo"))

    jornal_of = mo.jornal_con_cargas("oficial")
    jornal_esp = mo.jornal_con_cargas("oficial_especializado")
    jornal_ay = mo.jornal_con_cargas("ayudante")
    tipo_ha = params.hormigon_tipo
    tipo_ac = params.acero_tipo

    cod = item.codigo

    # --- Trabajos preliminares ---
    if cod == "1.1":
        mat("Materiales obrador (chapas, madera)", "gl", 1.0, 350_000)
        mano("Armado obrador", "jornada", 5.0, jornal_of)
        equipo("Alquiler equipamiento menor", "mes", 6.0, 80_000)
    elif cod == "1.2":
        mano("Limpieza terreno", "m²", 1.0, jornal_ay / 80)
        equipo("Retroexcavadora hora", "h", 1/80, 25_000)
    elif cod in ("1.3", "1.4"):
        mano("Replanteo / cerco", "m", 1.0, jornal_of / 40)

    # --- Movimiento de suelos ---
    elif cod in ("2.1", "2.2"):
        equipo("Retroexcavadora", "h", 0.25, 25_000)
        equipo("Camión volcador", "h", 0.20, 18_000)
        mano("Peón", "jornada", 1/30, jornal_ay)
    elif cod == "2.3":
        equipo("Compactadora vibratoria", "h", 0.15, 12_000)
        mano("Peón compactación", "jornada", 1/20, jornal_ay)
    elif cod == "2.4":
        equipo("Camión volcador retiro tierra", "h", 0.30, 18_000)

    # --- Fundaciones ---
    elif cod in ("3.1", "3.2"):
        mat(f"Hormigón {tipo_ha} elaborado", "m³", 1.05, m.hormigon_m3(tipo_ha))
        mano("Colocación HA", "jornada", 1/mo.rendimientos["hormigon_colocado_m3"], jornal_of)
        equipo("Vibrador de inmersión", "h", 0.50, 3_500)
    elif cod == "3.3":
        mat(f"Acero {tipo_ac}", "kg", 1.08, m.acero_kg(tipo_ac))
        mano("Doblado y colocación armadura", "jornada", 1/mo.rendimientos["armadura_kg"], jornal_esp)
    elif cod == "3.4":
        mat("Madera pino encofrado", "m²", 1.10, 4_500)
        mat("Clavo y alambre", "kg", 0.30, 2_100)
        mano("Encofrado y desencofrado", "jornada", 1/6, jornal_of)
    elif cod == "3.5":
        mat("Hormigón pobre H-13 elaborado", "m³", 1.02, 85_000)
        mano("Colocación", "jornada", 1/5, jornal_ay)

    # --- Estructura HA ---
    elif cod in ("4.1", "4.2", "4.3"):
        mat(f"Hormigón {tipo_ha} elaborado", "m³", 1.05, m.hormigon_m3(tipo_ha))
        mano("Colocación HA", "jornada", 1/mo.rendimientos["hormigon_colocado_m3"], jornal_of)
        equipo("Bomba de hormigón", "h", 0.25, 15_000)
        equipo("Vibrador", "h", 0.50, 3_500)
    elif cod in ("4.4", "4.5", "4.6"):
        mat(f"Acero {tipo_ac}", "kg", 1.08, m.acero_kg(tipo_ac))
        mano("Armador", "jornada", 1/mo.rendimientos["armadura_kg"], jornal_esp)
    elif cod in ("4.7", "4.8", "4.9"):
        mat("Tablero fenólico 18mm", "m²", 0.15, 18_000)
        mat("Madera pino 3×3cm", "m",  2.00,  950)
        mat("Puntales metálicos alquiler", "u",  0.50, 1_200)
        mano("Encofrado", "jornada", 1/mo.rendimientos["encofrado_losa"], jornal_of)

    # --- Mampostería ---
    elif cod == "5.1":
        mat("Ladrillo cerámico 18cm", "u", 55.0, m.mamposteria["ladrillo_cercon_18_18_33_unidad"])
        mat("Cemento portland", "kg", 7.0, m.morteros["cemento_portland_40kg"] / 40)
        mat("Cal hidratada", "kg", 3.0, m.morteros["cal_hidratada_30kg"] / 30)
        mat("Arena fina", "m³", 0.025, m.morteros["arena_m3"])
        mano("Albañil oficial", "jornada", 1/mo.rendimientos["mamposteria_ladrillo_ceramico"], jornal_of)
        mano("Ayudante", "jornada", 0.5/mo.rendimientos["mamposteria_ladrillo_ceramico"], jornal_ay)
    elif cod == "5.2":
        mat("Ladrillo cerámico 12cm", "u", 40.0, m.mamposteria["ladrillo_ceramico_18_9_6_unidad"])
        mat("Mortero mixto", "kg", 5.0, m.morteros["cemento_portland_40kg"] / 40)
        mano("Albañil", "jornada", 1/mo.rendimientos["mamposteria_ladrillo_ceramico"], jornal_of)

    # --- Revoques ---
    elif cod == "6.1":
        mat("Mortero grueso (cemento+arena)", "m²", 1.0, 800)
        mano("Revoque grueso", "jornada", 1/mo.rendimientos["revoque_grueso"], jornal_of)
    elif cod == "6.2":
        mat("Yeso proyectado", "m²", 1.0, 650)
        mano("Revoque fino enlucido", "jornada", 1/mo.rendimientos["revoque_fino"], jornal_of)
    elif cod == "6.3":
        mat("Mortero monocapa exterior", "m²", 1.0, 1_850)
        mano("Revoque exterior", "jornada", 1/8, jornal_esp)
    elif cod == "6.4":
        mat("Porcellanato o azulejo 40×40", "m²", 1.05, 8_500)
        mat("Adhesivo cerámico", "kg", 4.0, 280)
        mano("Colocación cerámica", "jornada", 1/mo.rendimientos["colocacion_ceramica"], jornal_of)

    # --- Carpinterías ---
    elif cod == "7.1":
        mat("Puerta blindex 90×210cm", "u", 1.0, m.carpinterias["puerta_blindex_90x210_unidad"])
        mano("Colocación", "jornada", 0.25, jornal_esp)
    elif cod == "7.2":
        mat("Puerta placa 90×200cm", "u", 1.0, m.carpinterias["puerta_interior_90x200_unidad"])
        mano("Colocación", "jornada", 0.15, jornal_of)
    elif cod == "7.3":
        mat("Ventana aluminio 1.50×1.20m", "u", 1.0, m.carpinterias["ventana_aluminio_1_5x1_2_unidad"])
        mano("Colocación ventana", "jornada", 0.20, jornal_esp)
    elif cod == "7.4":
        mat("Ventana aluminio 1.00×1.00m", "u", 1.0, m.carpinterias["ventana_aluminio_1x1_unidad"])
        mano("Colocación", "jornada", 0.15, jornal_esp)

    # --- Cubiertas ---
    elif cod == "8.1":
        mat("Membrana asfáltica 4mm", "m²", 1.05, m.impermeabilizacion["membrana_asfaltica_4mm_m2"])
        mat("Imprimación asfáltica", "lt", 0.30, m.impermeabilizacion["pintura_asfaltica_lt"])
        mano("Impermeabilizador", "jornada", 1/15, jornal_esp)
        equipo("Soplete gas", "h", 0.08, 1_500)
    elif cod == "8.2":
        mat("Ladrillo vista protección", "m²", 1.0, 3_200)
        mano("Colocación protección", "jornada", 1/12, jornal_of)
    elif cod == "8.3":
        mat("Pintura asfáltica", "lt", 0.50, m.impermeabilizacion["pintura_asfaltica_lt"])
        mano("Pintor", "jornada", 1/20, jornal_of)

    # --- Instalación sanitaria ---
    elif cod.startswith("9."):
        if cod in ("9.1", "9.2"):
            mat("Cañería PP-R con accesorios", "m", 1.10, m.instalaciones["caño_polipropileno_dn25_m"])
            mano("Plomero oficial especializado", "jornada", 1/15, jornal_esp)
        elif cod in ("9.3", "9.4"):
            mat("Caño PVC desagüe c/accesorios", "m", 1.10, m.instalaciones["caño_pvc_dn110_m"])
            mano("Plomero", "jornada", 1/12, jornal_esp)
        elif cod == "9.5":
            mat("Artefactos sanitarios completos", "gl", 1.0, 850_000)
            mano("Plomero instalación", "jornada", 2.0, jornal_esp)
        elif cod in ("9.6", "9.7"):
            mat("Tanque + bomba con instalación", "gl", 1.0, 1_200_000)

    # --- Instalación eléctrica ---
    elif cod.startswith("10."):
        if cod in ("10.1",):
            mat("Cañería eléctrica corrugada DN20", "m", 1.05, m.instalaciones["cañeria_electrica_dn20_m"])
            mano("Electricista", "jornada", 1/25, jornal_esp)
        elif cod in ("10.2",):
            mat("Conductor Cu 2.5mm²", "m", 1.05, 680)
            mano("Electricista", "jornada", 1/50, jornal_esp)
        elif cod in ("10.3",):
            mat("Tablero seccional 12 módulos", "u", 1.0, 95_000)
            mano("Electricista tablero", "jornada", 0.50, jornal_esp)
        elif cod in ("10.4",):
            mat("Tablero general BT 48 módulos", "u", 1.0, 380_000)
            mano("Electricista tablero principal", "jornada", 2.0, jornal_esp)
        elif cod in ("10.5",):
            mat("Artefactos iluminación por depto", "gl", 1.0, 280_000)
            mano("Electricista colocación", "jornada", 1.0, jornal_esp)

    # --- Instalación gas ---
    elif cod.startswith("11."):
        mat("Cañería cobre DN20 c/accesorios", "m", 1.10, 4_800)
        mano("Gasista matriculado", "jornada", 1/10, jornal_esp)

    # --- Incendio ---
    elif cod.startswith("12."):
        if cod == "12.1":
            mat("Red húmeda PVC DN63", "m", 1.05, m.instalaciones["caño_pvc_dn63_m"] * 1.5)
            mano("Instalador incendio", "jornada", 1/10, jornal_esp)
        elif cod == "12.2":
            mat("Boca de incendio equipada", "u", 1.0, 185_000)
            mano("Colocación", "jornada", 0.30, jornal_esp)
        elif cod == "12.3":
            mat("Matafuego ABC 10kg", "u", 1.0, 48_000)
        elif cod == "12.4":
            mat("Central detección incendio", "u", 1.0, 650_000)
            mano("Instalación y programación", "jornada", 3.0, jornal_esp)
        elif cod == "12.5":
            mat("Detector de humo óptico", "u", 1.0, 18_500)
            mano("Colocación y cableado", "jornada", 0.10, jornal_esp)

    # --- Termomecánica ---
    elif cod.startswith("13."):
        if cod == "13.1":
            mat("Split frío-calor 3000 frigorías", "u", 1.0, 850_000)
            mano("Instalación split", "jornada", 0.50, jornal_esp)
        else:
            mat("Conducto + aislación", "m²", 1.0, 15_000)
            mano("Instalación conductos", "jornada", 1/10, jornal_esp)

    # --- Pintura ---
    elif cod == "14.1":
        mat("Pintura látex interior 20L", "lt", 0.35, 4_800)
        mat("Fijador + sellador", "lt", 0.10, 3_200)
        mano("Pintor (2 manos)", "jornada", 1/mo.rendimientos["pintura_latex"], jornal_of)
    elif cod == "14.2":
        mat("Pintura texturada exterior", "lt", 0.50, 6_500)
        mano("Pintor exterior (andamios)", "jornada", 1/18, jornal_of)
        equipo("Alquiler andamios", "m²·mes", 0.25, 1_800)
    elif cod == "14.3":
        mat("Contrapiso H-13 + piso porcellanato", "m²", 1.0, 32_000)
        mano("Colocación pisos", "jornada", 1/mo.rendimientos["contrapiso"], jornal_of)

    # --- Equipamiento ---
    elif cod == "15.1":
        mat("Ascensor hidráulico 6 personas instalado", "u", 1.0,
            m.ascensores["ascensor_6_personas_hidraulico"])
        mano("Coordinación instalación", "jornada", 5.0, jornal_esp)
    elif cod == "15.2":
        mat("Tanque cisterna 10.000L polietileno", "u", 1.0, 380_000)
        mano("Colocación", "jornada", 1.0, jornal_of)
    elif cod == "15.3":
        mat("Tanque elevado 5.000L + base metálica", "u", 1.0, 280_000)
        mano("Colocación", "jornada", 1.0, jornal_of)
    elif cod == "15.4":
        mat("Grupo electrógeno 15 kVA", "u", 1.0, 2_800_000)
        mano("Instalación y puesta en marcha", "jornada", 3.0, jornal_esp)

    else:
        # Ítem sin análisis detallado: precio global estimado
        mat("Materiales varios (estimado)", item.unidad, item.cantidad, 5_000)
        mano("Mano de obra (estimado)", "jornada", item.cantidad / 20, jornal_of)

    return ai


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def analizar(
    mediciones: MedicionesEdificio,
    precios: CatalogoPrecios,
    params: "ParametrosEdificio",
) -> PresupuestoCompleto:
    """Produce el presupuesto completo con análisis de precios unitarios.

    Args:
        mediciones: Cómputo métrico del edificio.
        precios: Catálogo de precios cargado desde los JSON.
        params: Parámetros del edificio (para tipo de hormigón, acero, etc.).

    Returns:
        PresupuestoCompleto con todos los rubros analizados.
    """
    ppto = PresupuestoCompleto(
        moneda=params.moneda,
        fecha=precios.fecha,
        incluir_gastos=params.incluir_gastos_generales,
        incluir_honorarios=params.incluir_honorarios,
    )

    for rubro_med in mediciones.rubros:
        rubro_an = RubroAnalizado(numero=rubro_med.numero, nombre=rubro_med.nombre)
        for item in rubro_med.items:
            ai = _analizar_item(item, precios, params)
            rubro_an.items.append(ai)
        ppto.rubros.append(rubro_an)

    # GG y honorarios se exponen como propiedades del presupuesto,
    # NO se agregan a rubros para evitar doble conteo en costo_directo.
    return ppto
