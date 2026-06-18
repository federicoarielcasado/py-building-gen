"""Verificación automatizada de la ejecución de los scripts Dynamo.

Fase 1 del pipeline de automatización. La idea: en vez de abrir Revit y revisar
a ojo si cada ``.dyn`` hizo lo que debía, los Python nodes dejan en disco un JSON
de auto-reporte (inyectado por ``core.dynamo.dyn_builder``) con el valor de ``OUT``
y las advertencias de Revit. Este módulo lee esos reportes y decide **PASS/FAIL**
comparando el resultado real contra lo que los ``ParametrosEdificio`` predicen.

Cubre dos clases de fallo:

* **Estructural** (genérico, todos los scripts): un nodo que quedó en estado
  ``"started"`` (se rompió a mitad), un reporte ausente (el nodo nunca corrió),
  o advertencias de Revit que conviene mirar.
* **Cuantitativo** (específico por script): el conteo real de elementos creados
  no coincide con el esperado — el síntoma clásico del bug de "el input nunca
  llegó a Revit" (p.ej. ``frente_m_recibido == 0.0`` ⇒ 0 ejes creados).

Uso por línea de comandos::

    python -m core.verificador                       # usa output/dynamo/_reports
    python -m core.verificador ruta/a/_reports

Uso programático::

    from core.verificador import verificar
    rep = verificar(params, "output/dynamo/_reports")
    print(rep.to_text())
    if not rep.ok:
        ...
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.parametros import ParametrosEdificio

# Directorio por defecto donde los .dyn dejan sus reportes (ver DynScript.save).
_REPORT_DIR_DEFAULT = Path("output/dynamo/_reports")


# ---------------------------------------------------------------------------
# Modelo de resultados
# ---------------------------------------------------------------------------

SEV_ERROR = "error"
SEV_WARNING = "warning"
SEV_INFO = "info"


@dataclass
class Resultado:
    """Un hallazgo individual de la verificación."""

    script: str
    chequeo: str
    ok: bool
    severidad: str
    detalle: str

    @property
    def icono(self) -> str:
        if self.severidad == SEV_ERROR:
            return "[X]"
        if self.severidad == SEV_WARNING:
            return "[!]"
        return "[OK]" if self.ok else "[--]"


@dataclass
class ReporteVerificacion:
    """Resultado agregado de verificar un directorio de reportes."""

    resultados: list[Resultado] = field(default_factory=list)

    # -- estado global --------------------------------------------------
    @property
    def ok(self) -> bool:
        """True si no hay ningún resultado de severidad error."""
        return not any(r.severidad == SEV_ERROR for r in self.resultados)

    @property
    def n_errores(self) -> int:
        return sum(1 for r in self.resultados if r.severidad == SEV_ERROR)

    @property
    def n_warnings(self) -> int:
        return sum(1 for r in self.resultados if r.severidad == SEV_WARNING)

    def por_script(self) -> dict[str, list[Resultado]]:
        out: dict[str, list[Resultado]] = {}
        for r in self.resultados:
            out.setdefault(r.script, []).append(r)
        return out

    # -- salidas --------------------------------------------------------
    def to_text(self) -> str:
        """Resumen legible en consola."""
        lineas: list[str] = []
        for script, res in self.por_script().items():
            lineas.append(f"\n{script}")
            for r in res:
                lineas.append(f"  {r.icono} {r.chequeo}: {r.detalle}")
        estado = "PASS" if self.ok else "FAIL"
        lineas.append(
            f"\n=== {estado} === {self.n_errores} error(es), "
            f"{self.n_warnings} advertencia(s)"
        )
        return "\n".join(lineas)

    def to_html(self) -> str:
        """Reporte HTML autocontenido para abrir en el navegador."""
        estado = "PASS" if self.ok else "FAIL"
        color = "#1a7f37" if self.ok else "#cf222e"
        filas: list[str] = []
        for script, res in self.por_script().items():
            filas.append(f'<tr><th colspan="3" class="sc">{_esc(script)}</th></tr>')
            for r in res:
                c = {"error": "#cf222e", "warning": "#9a6700"}.get(r.severidad, "#1a7f37")
                filas.append(
                    f'<tr><td style="color:{c}">{_esc(r.icono)}</td>'
                    f"<td>{_esc(r.chequeo)}</td><td>{_esc(r.detalle)}</td></tr>"
                )
        return f"""<!doctype html><html lang="es"><meta charset="utf-8">
<title>Verificacion py-building-gen</title>
<style>
 body{{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:2rem;color:#1f2328}}
 h1{{font-size:1.4rem}} .estado{{color:{color};font-weight:700}}
 table{{border-collapse:collapse;width:100%;margin-top:1rem}}
 td,th{{border:1px solid #d0d7de;padding:.4rem .6rem;text-align:left;vertical-align:top}}
 th.sc{{background:#f6f8fa}}
</style>
<h1>Verificacion de scripts Dynamo — <span class="estado">{estado}</span></h1>
<p>{self.n_errores} error(es), {self.n_warnings} advertencia(s).</p>
<table>{''.join(filas)}</table>
</html>"""


def _esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Carga de reportes
# ---------------------------------------------------------------------------

def cargar_reportes(report_dir: Path | str) -> list[dict]:
    """Lee todos los ``*.json`` de auto-reporte del directorio.

    Ignora archivos que no sean reportes válidos (p.ej. el HTML de salida).
    """
    d = Path(report_dir)
    reportes: list[dict] = []
    if not d.is_dir():
        return reportes
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and "status" in data and "key" in data:
            data["_archivo"] = p.name
            reportes.append(data)
    return reportes


_RE_PBG = re.compile(r"_PBG_(SCRIPT|NODE|KEY)\s*=\s*(['\"])(.*?)\2")


def claves_esperadas_de_dyn(dyn_dir: Path | str) -> list[dict]:
    """Lee los ``.dyn`` y extrae qué nodos DEBERÍAN dejar reporte al correr.

    Cada Python node lleva embebido su ``_PBG_SCRIPT/_PBG_NODE/_PBG_KEY`` (lo
    inyecta el builder). Parseándolos sabemos el conjunto exacto de nodos que
    tienen que ejecutarse en Revit — y por lo tanto qué reportes faltan si algún
    nodo se salteó. Funciona para los 10 scripts sin hardcodear nada.

    Returns:
        Lista de ``{"script", "nodo", "key"}`` (una por Python node con reporte).
    """
    d = Path(dyn_dir)
    esperados: list[dict] = []
    if not d.is_dir():
        return esperados
    for p in sorted(d.glob("*.dyn")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for n in data.get("Nodes", []):
            if "PythonNode" not in n.get("ConcreteType", ""):
                continue
            campos = {m.group(1): m.group(3) for m in _RE_PBG.finditer(n.get("Code", ""))}
            if "KEY" in campos:
                esperados.append({
                    "script": campos.get("SCRIPT", p.stem),
                    "nodo": campos.get("NODE", "?"),
                    "key": campos["KEY"],
                })
    return esperados


def _contar_out(out) -> Optional[int]:
    """Extrae un conteo de elementos del OUT de un nodo, o None si no aplica.

    Cubre los shapes reales de los generadores: listas (niveles, plantas,
    tipos…) y dicts con ``total`` / ``total_tags`` / ``total_vigas`` /
    ``total_vf`` / ``vistas_configuradas`` / ``creados``.
    """
    if isinstance(out, list):
        return len(out)
    if isinstance(out, dict):
        for k in ("total", "total_tags", "total_vigas", "total_vf",
                  "vistas_configuradas"):
            if isinstance(out.get(k), int):
                return out[k]
        creados = out.get("creados")
        if isinstance(creados, list):
            return len(creados)
    return None


def _buscar(reportes: list[dict], script: str, node_substr: str) -> Optional[dict]:
    """Primer reporte cuyo script coincide y cuya etiqueta contiene node_substr."""
    sub = node_substr.lower()
    for r in reportes:
        if r.get("script") == script and sub in str(r.get("nodo", "")).lower():
            return r
    return None


def limpiar_reportes(report_dir: Path | str) -> int:
    """Borra los JSON de reporte previos. Retorna cuántos borró.

    Conviene llamarlo antes de re-correr los scripts para que un nodo que
    desaparece (o nunca corre) no deje un reporte viejo que parezca válido.
    """
    d = Path(report_dir)
    n = 0
    if not d.is_dir():
        return 0
    for p in d.glob("*.json"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n


# ---------------------------------------------------------------------------
# Chequeos genéricos (aplican a todo reporte de todo script)
# ---------------------------------------------------------------------------

def _chequeos_genericos(reportes: list[dict]) -> list[Resultado]:
    res: list[Resultado] = []
    for r in reportes:
        script = r.get("script", r.get("_archivo", "?"))
        nodo = r.get("nodo", "?")
        status = r.get("status")
        if status == "ok":
            res.append(Resultado(script, f"nodo '{nodo}'", True, SEV_INFO, "ejecutado OK"))
        elif status == "started":
            res.append(Resultado(
                script, f"nodo '{nodo}'", False, SEV_ERROR,
                "quedó en 'started' — el nodo se rompió antes de terminar "
                "(revisar error de Dynamo / input desconectado)",
            ))
        else:
            res.append(Resultado(
                script, f"nodo '{nodo}'", False, SEV_ERROR,
                f"status inesperado: {status!r}",
            ))
        # Advertencias de Revit recogidas por el nodo.
        warns = r.get("warnings") or []
        if warns:
            muestra = "; ".join(str(w) for w in warns[:3])
            extra = "" if len(warns) <= 3 else f" (+{len(warns) - 3} más)"
            res.append(Resultado(
                script, f"advertencias Revit en '{nodo}'", False, SEV_WARNING,
                f"{len(warns)} advertencia(s): {muestra}{extra}",
            ))
        # Nodo que corrió OK pero no creó nada: fallo silencioso frecuente.
        # Warning (no error) porque algunos nodos legítimamente crean 0.
        if status == "ok":
            n = _contar_out(r.get("out"))
            if n == 0:
                res.append(Resultado(
                    script, f"elementos creados en '{nodo}'", False, SEV_WARNING,
                    "el nodo corrió pero creó 0 elementos (¿input vacío o "
                    "familia faltante?)",
                ))
    return res


# ---------------------------------------------------------------------------
# Chequeos cuantitativos específicos
# ---------------------------------------------------------------------------
# Cada función recibe (params, reportes) y devuelve resultados. Compara el OUT
# real contra lo que los parámetros predicen. Para agregar un script nuevo,
# escribir una función y registrarla en _CHECKS_ESPECIFICOS.

# Parámetros de grilla replicados de gen_niveles._CODE_GRILLA (mantener en sync).
_PASO_GRILLA = 5.0
_MIN_BAY = 2.5


def _ejes(span: float, paso: float = _PASO_GRILLA, min_bay: float = _MIN_BAY) -> list[float]:
    """Espejo de la función ejes() embebida en gen_niveles (conteo esperado)."""
    if span <= paso + 1e-9:
        return [0.0, round(span, 4)]
    pos: list[float] = []
    x = 0.0
    while x < span - 1e-6:
        pos.append(round(x, 4))
        x += paso
    resto = span - pos[-1]
    if resto < min_bay and len(pos) >= 2:
        pos.pop()
    pos.append(round(span, 4))
    return pos


def _cmp(script: str, chequeo: str, esperado, real) -> Resultado:
    ok = esperado == real
    sev = SEV_INFO if ok else SEV_ERROR
    detalle = (
        f"esperado {esperado}, real {real}" if ok
        else f"esperado {esperado}, real {real}  <-- NO COINCIDE"
    )
    return Resultado(script, chequeo, ok, sev, detalle)


def _check_niveles(params: ParametrosEdificio, reportes: list[dict]) -> list[Resultado]:
    script = "01_niveles_grilla"
    res: list[Resultado] = []

    # --- Niveles ---
    rep = _buscar(reportes, script, "nivel")
    if rep and rep.get("status") == "ok":
        n_real = len(rep.get("out") or [])
        n_esp = (
            params.cant_subsuelos
            + 1  # PB
            + params.pisos_tipo
            + (1 if params.tiene_azotea else 0)
        )
        res.append(_cmp(script, "cantidad de niveles", n_esp, n_real))

    # --- Grilla / ejes ---
    rep = _buscar(reportes, script, "grilla")
    if rep and rep.get("status") == "ok":
        out = rep.get("out") or {}
        total_real = out.get("total")
        total_esp = len(_ejes(params.frente)) + len(_ejes(params.fondo))
        res.append(_cmp(script, "cantidad de ejes de grilla", total_esp, total_real))
        # Pista directa del bug de inputs: ¿llegaron las dimensiones del lote?
        if math.isclose(out.get("frente_m_recibido", 0.0), 0.0) or \
           math.isclose(out.get("fondo_m_recibido", 0.0), 0.0):
            res.append(Resultado(
                script, "inputs de lote llegaron al nodo", False, SEV_ERROR,
                f"frente/fondo recibidos = {out.get('frente_m_recibido')}/"
                f"{out.get('fondo_m_recibido')} (esperado "
                f"{params.frente}/{params.fondo}) — input desconectado",
            ))

    # --- Plantas por disciplina (ARQ + EST + MEP) ---
    rep = _buscar(reportes, script, "planta")
    if rep and rep.get("status") == "ok":
        out = rep.get("out") or {}
        niveles_sobre_rasante = 1 + params.pisos_tipo + (1 if params.tiene_azotea else 0)
        esp = niveles_sobre_rasante * 3  # 3 disciplinas
        res.append(_cmp(script, "cantidad de plantas (vistas)", esp, out.get("total")))

    return res


_CHECKS_ESPECIFICOS = {
    "01_niveles_grilla": _check_niveles,
}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def verificar(
    params: ParametrosEdificio,
    report_dir: Path | str = _REPORT_DIR_DEFAULT,
    *,
    dyn_dir: Optional[Path | str] = None,
    scripts_esperados: Optional[list[str]] = None,
) -> ReporteVerificacion:
    """Verifica la ejecución de los scripts a partir de sus auto-reportes.

    Args:
        params: Parámetros con los que se generaron los scripts (define lo esperado).
        report_dir: Carpeta ``_reports`` donde los .dyn dejan sus JSON.
        dyn_dir: Carpeta con los ``.dyn``. Si tiene scripts, se derivan de ellos
            TODOS los nodos que deberían haber corrido (en los 10 scripts) y se
            marca error por cada nodo sin reporte. Por defecto, ``report_dir`` y
            los .dyn son hermanos, así que se usa ``report_dir.parent``.
        scripts_esperados: Fallback usado solo si no hay .dyn en ``dyn_dir``:
            nombres de script que deberían tener al menos un reporte.

    Returns:
        ReporteVerificacion con todos los hallazgos.
    """
    reportes = cargar_reportes(report_dir)
    rep = ReporteVerificacion()

    if not reportes:
        rep.resultados.append(Resultado(
            "(global)", "reportes presentes", False, SEV_ERROR,
            f"no se encontró ningún reporte en {report_dir} — "
            "¿se corrieron los scripts en Revit?",
        ))
        return rep

    # Nodos que esperábamos ver ejecutados, derivados de los propios .dyn.
    if dyn_dir is None:
        dyn_dir = Path(report_dir).parent
    nodos_esperados = claves_esperadas_de_dyn(dyn_dir)
    keys_con_reporte = {r.get("key") for r in reportes}

    if nodos_esperados:
        # Cobertura completa: cada nodo de cada script debe tener su reporte.
        for e in nodos_esperados:
            if e["key"] not in keys_con_reporte:
                rep.resultados.append(Resultado(
                    e["script"], f"nodo '{e['nodo']}' ejecutado", False, SEV_ERROR,
                    "sin reporte — el nodo no se corrió en Revit "
                    "(¿script no ejecutado o detenido antes de llegar?)",
                ))
    else:
        # Fallback sin .dyn: solo chequear presencia por script.
        esperados = scripts_esperados or list(_CHECKS_ESPECIFICOS.keys())
        scripts_con_reporte = {r.get("script") for r in reportes}
        for s in esperados:
            if s not in scripts_con_reporte:
                rep.resultados.append(Resultado(
                    s, "script ejecutado", False, SEV_ERROR,
                    "sin ningún reporte — el script no se corrió en Revit",
                ))

    rep.resultados.extend(_chequeos_genericos(reportes))
    for script, fn in _CHECKS_ESPECIFICOS.items():
        rep.resultados.extend(fn(params, reportes))

    return rep


def verificar_y_guardar(
    params: ParametrosEdificio,
    report_dir: Path | str = _REPORT_DIR_DEFAULT,
) -> ReporteVerificacion:
    """Verifica y además escribe ``_verificacion.html`` en el report_dir."""
    rep = verificar(params, report_dir)
    salida = Path(report_dir) / "_verificacion.html"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(rep.to_html(), encoding="utf-8")
    return rep


def _main(argv: list[str]) -> int:
    report_dir = Path(argv[1]) if len(argv) > 1 else _REPORT_DIR_DEFAULT
    # Sin un .pbg de parámetros, usamos los defaults. El usuario puede pasar uno
    # como segundo argumento para verificar contra parámetros reales.
    if len(argv) > 2:
        params = ParametrosEdificio.cargar(argv[2])
    else:
        params = ParametrosEdificio()
    rep = verificar_y_guardar(params, report_dir)
    print(rep.to_text())
    print(f"\nHTML: {Path(report_dir) / '_verificacion.html'}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv))
