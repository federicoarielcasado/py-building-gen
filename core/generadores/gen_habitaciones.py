"""Generador del script Dynamo 11_habitaciones.dyn.

Crea objetos Room (local) en Revit para cada zona de cada departamento,
habilitando los schedules de áreas y los tags en planta.

Orden de ejecución: 11 de 12 (después de 02_muros y 01_niveles).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from core.dynamo.dyn_builder import DynScript

if TYPE_CHECKING:
    from core.parametros import ParametrosEdificio

_OUTPUT_DIR = Path("output/dynamo")

_CODE_ROOMS = '''\
import clr
import json
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    Level, UV, FilteredElementCollector, Transaction,
    UnitUtils, UnitTypeId,
)
from Autodesk.Revit.DB.Architecture import Room
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

frente_m        = _fi(IN[0])
fondo_m         = _fi(IN[1])
pisos_tipo      = _ii(IN[2])
cant_depto_tipo = _ii(IN[3])
tipologias_str  = _si(IN[4])   # "2amb:1,3amb:1" (quote-free para Code Block)
cant_escaleras  = _ii(IN[5])
cant_ascensores = _ii(IN[6])

apts = []
for _par in tipologias_str.split(","):
    _par = _par.strip()
    if not _par:
        continue
    _tipo, _, _cant = _par.partition(":")
    _tipo = _tipo.strip() or "2amb"
    try:
        _n = int(_cant)
    except Exception:
        _n = 1
    for _ in range(_n):
        apts.append(_tipo)

# ── Layout geometry (identical constants to Scripts 02 y 05) ─────────────────
ESC_ANCHO = 3.00; ESC_FONDO = 5.50; ASC_ANCHO = 2.00; PASILLO_PROF = 1.20
_n_apts      = max(cant_depto_tipo, 1)
ancho_nucleo = cant_escaleras * ESC_ANCHO + cant_ascensores * ASC_ANCHO
y_nucleo     = fondo_m - ESC_FONDO
y_pasillo    = y_nucleo - PASILLO_PROF
apt_ancho    = frente_m / _n_apts

_PROP_LIVING = {"1amb":0.00,"estudio":0.00,"2amb":0.40,"3amb":0.38,"4amb":0.35,"duplex":0.35}
_PROP_SERV   = {"1amb":0.65,"estudio":0.70,"2amb":0.70,"3amb":0.68,"4amb":0.65,"duplex":0.65}
_NOMBRES = {
    "living":    "Living-Comedor",
    "dorm_p":    "Dormitorio Principal",
    "dorm":      "Dormitorio",
    "dorm1":     "Dormitorio 1",
    "dorm2":     "Dormitorio 2",
    "dorm3":     "Dormitorio 3",
    "living_d":  "Living-Dormitorio",
    "cocina":    "Cocina",
    "bano":      "Baño",
    "bano1":     "Baño 1",
    "bano2":     "Baño 2",
    "pasillo":   "Pasillo",
}

def m_to_ft(m):
    return UnitUtils.ConvertToInternalUnits(m, UnitTypeId.Meters)

def get_level(nombre):
    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    return next((l for l in levels if l.Name == nombre), None)

def zonas_apt(apt_idx, tipo):
    """Retorna lista de (nombre, x_centroid, y_centroid) para cada zona del depto."""
    x0 = apt_ancho * apt_idx
    x1 = x0 + apt_ancho
    pct_l = _PROP_LIVING.get(tipo, 0.40)
    pct_s = _PROP_SERV.get(tipo, 0.70)
    y_l   = y_pasillo * pct_l
    y_s   = y_pasillo * pct_s

    cx = (x0 + x1) / 2       # centro X del depto
    xcoc = x0 + apt_ancho * 0.55 / 2        # centro X cocina
    xban = x0 + apt_ancho * 0.55 + apt_ancho * 0.45 / 2  # centro X baño

    zonas = []

    if tipo in ("1amb", "estudio"):
        zonas.append((_NOMBRES["living_d"], cx, y_s / 2))
        zonas.append((_NOMBRES["cocina"],   xcoc, y_s + (y_pasillo - y_s) / 2))
        zonas.append((_NOMBRES["bano"],     xban, y_s + (y_pasillo - y_s) / 2))

    elif tipo == "2amb":
        zonas.append((_NOMBRES["living"],  cx, y_l / 2))
        zonas.append((_NOMBRES["dorm_p"],  cx, y_l + (y_s - y_l) / 2))
        zonas.append((_NOMBRES["cocina"],  xcoc, y_s + (y_pasillo - y_s) / 2))
        zonas.append((_NOMBRES["bano"],    xban, y_s + (y_pasillo - y_s) / 2))

    elif tipo == "3amb":
        x_mid = x0 + apt_ancho * 0.50
        zonas.append((_NOMBRES["living"],  cx, y_l / 2))
        zonas.append((_NOMBRES["dorm1"],   (x0 + x_mid) / 2,  y_l + (y_s - y_l) / 2))
        zonas.append((_NOMBRES["dorm2"],   (x_mid + x1) / 2,  y_l + (y_s - y_l) / 2))
        zonas.append((_NOMBRES["cocina"],  xcoc, y_s + (y_pasillo - y_s) / 2))
        zonas.append((_NOMBRES["bano1"],   xban, y_s + (y_pasillo - y_s) / 2))

    elif tipo in ("4amb", "duplex"):
        x_13 = x0 + apt_ancho * 0.33
        x_23 = x0 + apt_ancho * 0.67
        zonas.append((_NOMBRES["living"],  cx, y_l / 2))
        zonas.append((_NOMBRES["dorm_p"],  (x0 + x_13) / 2,  y_l + (y_s - y_l) / 2))
        zonas.append((_NOMBRES["dorm1"],   (x_13 + x_23) / 2, y_l + (y_s - y_l) / 2))
        zonas.append((_NOMBRES["dorm2"],   (x_23 + x1) / 2,  y_l + (y_s - y_l) / 2))
        zonas.append((_NOMBRES["cocina"],  xcoc, y_s + (y_pasillo - y_s) / 2))
        zonas.append((_NOMBRES["bano1"],   xban, y_s + (y_pasillo - y_s) / 2))

    return zonas

rooms_creados = []

with Transaction(doc, "py-building-gen: Rooms") as t:
    t.Start()
    for i_piso in range(1, pisos_tipo + 1):
        nombre_nivel = f"P{i_piso:02d}"
        lvl = get_level(nombre_nivel)
        if lvl is None:
            continue
        for apt_idx in range(_n_apts):
            tipo = apts[apt_idx] if apt_idx < len(apts) else "2amb"
            letra_depto = chr(ord("A") + apt_idx)
            for i_zona, (nombre_zona, cx, cy) in enumerate(zonas_apt(apt_idx, tipo)):
                try:
                    room = doc.Create.NewRoom(lvl, UV(m_to_ft(cx), m_to_ft(cy)))
                    room.Name = nombre_zona
                    room.Number = f"{i_piso}{letra_depto}{i_zona+1:02d}"
                    rooms_creados.append({
                        "nivel": nombre_nivel,
                        "depto": letra_depto,
                        "nombre": nombre_zona,
                        "numero": room.Number,
                        "id": room.Id.Value,
                    })
                except Exception as e:
                    rooms_creados.append({"nivel": nombre_nivel, "error": str(e)})
    t.Commit()

OUT = {"total": len(rooms_creados), "rooms": rooms_creados}
'''


def generar(params: "ParametrosEdificio", output_dir: Path = _OUTPUT_DIR) -> Path:
    """Genera ``11_habitaciones.dyn`` — crea Room objects en cada departamento.

    Returns:
        Path al archivo .dyn generado.
    """
    output_dir = Path(output_dir)
    # Formato quote-free para Code Block DesignScript: "2amb:1,3amb:1"
    tipologias_str = ",".join(
        f"{t.tipo}:{t.cantidad}" for t in params.mix_tipologias
    )

    s = DynScript(
        "11_habitaciones",
        "Crea Room objects en Revit para cada local de cada departamento. "
        "Ejecutar después de 02_muros y 01_niveles.",
    )

    cb_frente  = s.add_code_block(str(params.frente),               label="frente_m",         col=0, row=0)
    cb_fondo   = s.add_code_block(str(params.fondo),                label="fondo_m",          col=0, row=1)
    cb_pisos   = s.add_code_block(str(params.pisos_tipo),           label="pisos_tipo",       col=0, row=2)
    cb_ndepto  = s.add_code_block(str(params.cant_depto_tipo),      label="cant_depto_tipo",  col=0, row=3)
    cb_tipol   = s.add_code_block(f'"{tipologias_str}"',            label="tipologias",       col=0, row=4)
    cb_nesc    = s.add_code_block(str(params.cant_cajas_escalera),  label="cant_escaleras",   col=0, row=5)
    cb_nasc    = s.add_code_block(str(params.cant_ascensores),      label="cant_ascensores",  col=0, row=6)

    cbs = [cb_frente, cb_fondo, cb_pisos, cb_ndepto, cb_tipol, cb_nesc, cb_nasc]
    py = s.add_python_node(_CODE_ROOMS, n_inputs=len(cbs), label="Crear Rooms", col=1, row=0)
    for i, cb in enumerate(cbs):
        s.connect(cb, py, to_input=i)

    w = s.add_watch(label="Rooms creados", col=2, row=0)
    s.connect(py, w)
    return s.save(output_dir / "11_habitaciones.dyn")
