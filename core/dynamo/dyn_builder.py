"""Constructor de archivos .dyn (JSON) para Dynamo 4.0 / Revit 2027.

Dynamo 2.x+ abandona XML y usa JSON. Cada script es un grafo de nodos
conectados. Este módulo provee una API de alto nivel para construirlos
sin manipular el JSON a mano.

Uso típico::

    from core.dynamo.dyn_builder import DynScript

    s = DynScript("01_niveles_grilla", "Crea niveles y grilla en Revit")
    cb = s.add_code_block("6", label="pisos_tipo")
    py = s.add_python_node(code=CODIGO, n_inputs=1, label="Crear Niveles")
    s.connect(cb, py, to_input=0)
    s.save(Path("output/dynamo/01_niveles_grilla.dyn"))
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Version string que Dynamo 3.x escribe en los archivos que genera.
# Usamos una cadena compatible; Dynamo lee cualquier 3.x sin error.
_DYNAMO_VERSION = "4.0.0.0"

# Helpers inyectados al inicio de todos los Python nodes.
# Previenen TypeError cuando un input llega como None (nodo desconectado o
# code block sin evaluar). Usar _fi/_ii/_si en lugar de float/int/str directos.
_INPUT_HELPERS = '''\
def _fi(v, d=0.0): return float(v) if v is not None else float(d)
def _ii(v, d=0):   return int(v)   if v is not None else int(d)
def _si(v, d=""):  return str(v)   if v is not None else str(d)
'''

# Separación entre nodos en el canvas (píxeles del canvas de Dynamo)
_COL_W = 300.0
_ROW_H = 130.0


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _port(name: str = "", desc: str = "") -> dict:
    return {
        "Id": _uid(),
        "Name": name,
        "Description": desc,
        "UsingDefaultValue": False,
        "Level": 2,
        "UseLevels": False,
        "KeepListStructure": False,
    }


# ---------------------------------------------------------------------------
# Tipos de nodo
# ---------------------------------------------------------------------------

@dataclass
class _BaseNode:
    id: str = field(default_factory=_uid)
    label: str = ""
    x: float = 0.0
    y: float = 0.0

    def node_dict(self) -> dict:
        raise NotImplementedError

    def view_dict(self) -> dict:
        return {
            "Id": self.id,
            "IsSetAsInput": False,
            "IsSetAsOutput": False,
            "Name": self.label,
            "ShowGeometry": True,
            "Excluded": False,
            "X": self.x,
            "Y": self.y,
        }


@dataclass
class CodeBlockNode(_BaseNode):
    """Nodo Code Block — expresión DesignScript (valor constante o fórmula)."""

    code: str = "0;"
    _out_id: str = field(default_factory=_uid)

    @property
    def output_port_id(self) -> str:
        return self._out_id

    def node_dict(self) -> dict:
        return {
            "ConcreteType": "Dynamo.Graph.Nodes.CodeBlockNodeModel, DynamoCore",
            "NodeType": "CodeBlockNode",
            "Code": self.code,
            "Id": self.id,
            "Inputs": [],
            "Outputs": [
                {
                    "Id": self._out_id,
                    "Name": "",
                    "Description": "Value of expression at line 1",
                    "UsingDefaultValue": False,
                    "Level": 2,
                    "UseLevels": False,
                    "KeepListStructure": False,
                }
            ],
            "Replication": "Disabled",
            "Description": "Allows for DesignScript code to be authored directly",
        }


@dataclass
class PythonNode(_BaseNode):
    """Nodo Python Script — CPython 3 (motor por defecto en Dynamo 3.x)."""

    code: str = "OUT = None"
    n_inputs: int = 1
    _input_port_ids: list[str] = field(default_factory=list)
    _out_id: str = field(default_factory=_uid)

    def __post_init__(self) -> None:
        if not self._input_port_ids:
            self._input_port_ids = [_uid() for _ in range(self.n_inputs)]

    def input_port_id(self, index: int) -> str:
        return self._input_port_ids[index]

    @property
    def output_port_id(self) -> str:
        return self._out_id

    def node_dict(self) -> dict:
        inputs = [
            {
                "Id": self._input_port_ids[i],
                "Name": f"IN[{i}]",
                "Description": f"Input {i}",
                "UsingDefaultValue": False,
                "Level": 2,
                "UseLevels": False,
                "KeepListStructure": False,
            }
            for i in range(self.n_inputs)
        ]
        return {
            "ConcreteType": "PythonNodeModels.PythonNode, PythonNodeModels",
            "NodeType": "ExtensionNode",
            "Code": _INPUT_HELPERS + self.code,
            "Engine": "PythonNet3",
            "EngineName": "PythonNet3",
            "VariableInputPorts": True,
            "Id": self.id,
            "Inputs": inputs,
            "Outputs": [
                {
                    "Id": self._out_id,
                    "Name": "OUT",
                    "Description": "",
                    "UsingDefaultValue": False,
                    "Level": 2,
                    "UseLevels": False,
                    "KeepListStructure": False,
                }
            ],
            "Replication": "Disabled",
            "Description": "Runs an embedded Python script.",
        }


@dataclass
class WatchNode(_BaseNode):
    """Nodo Watch — muestra el valor de salida en el canvas (debug)."""

    _in_id: str = field(default_factory=_uid)
    _out_id: str = field(default_factory=_uid)

    @property
    def input_port_id(self) -> str:
        return self._in_id

    @property
    def output_port_id(self) -> str:
        return self._out_id

    def node_dict(self) -> dict:
        return {
            "ConcreteType": "Dynamo.Graph.Nodes.Watch, DynamoCore",
            "NodeType": "ExtensionNode",
            "Id": self.id,
            "Inputs": [
                {
                    "Id": self._in_id,
                    "Name": "",
                    "Description": "Node to evaluate.",
                    "UsingDefaultValue": False,
                    "Level": 2,
                    "UseLevels": False,
                    "KeepListStructure": False,
                }
            ],
            "Outputs": [
                {
                    "Id": self._out_id,
                    "Name": "",
                    "Description": "Watched value",
                    "UsingDefaultValue": False,
                    "Level": 2,
                    "UseLevels": False,
                    "KeepListStructure": False,
                }
            ],
            "Replication": "Disabled",
            "Description": "Visualize the node's output",
        }


# ---------------------------------------------------------------------------
# Conector
# ---------------------------------------------------------------------------

@dataclass
class _Connector:
    start_port_id: str   # Id del PUERTO de salida del nodo origen
    end_port_id: str     # Id del PUERTO de entrada del nodo destino
    id: str = field(default_factory=_uid)

    def to_dict(self) -> dict:
        # Formato estandar Dynamo 2.x+: Start/End referencian IDs de PUERTO
        # (los Id dentro de Inputs/Outputs), NO IDs de nodo. Sin StartIndex/
        # EndIndex ni PortType. Usar IDs de nodo deja todo desconectado y los
        # nodos Python reciben IN[x] = None -> defaults (bug sistemico).
        return {
            "Start": self.start_port_id,
            "End": self.end_port_id,
            "Id": self.id,
            "IsHidden": "False",
        }


# ---------------------------------------------------------------------------
# Script completo
# ---------------------------------------------------------------------------

class DynScript:
    """Representa un script Dynamo (.dyn) completo.

    Args:
        name: Nombre del script (se muestra en Dynamo).
        description: Descripción breve del script.
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._nodes: list[_BaseNode] = []
        self._connectors: list[_Connector] = []
        self._auto_col: int = 0   # columna actual para auto-layout
        self._auto_row: int = 0   # fila actual para auto-layout

    # ------------------------------------------------------------------
    # Agregar nodos
    # ------------------------------------------------------------------

    def add_code_block(
        self,
        code: str,
        label: str = "",
        *,
        col: Optional[int] = None,
        row: Optional[int] = None,
    ) -> CodeBlockNode:
        """Agrega un nodo Code Block y retorna la instancia."""
        c, r = self._resolve_pos(col, row)
        # DesignScript requiere punto y coma para evaluar la expresión como statement.
        # Sin él, el nodo produce null y los Python nodes reciben IN[x] = None.
        code_ds = code if code.rstrip().endswith(";") else code.rstrip() + ";"
        node = CodeBlockNode(
            code=code_ds,
            label=label or code[:20],
            x=c * _COL_W,
            y=r * _ROW_H,
        )
        self._nodes.append(node)
        self._auto_row += 1
        return node

    def add_python_node(
        self,
        code: str,
        n_inputs: int = 1,
        label: str = "Python Script",
        *,
        col: Optional[int] = None,
        row: Optional[int] = None,
    ) -> PythonNode:
        """Agrega un nodo Python Script y retorna la instancia."""
        c, r = self._resolve_pos(col, row, advance_col=True)
        node = PythonNode(
            code=code,
            n_inputs=n_inputs,
            label=label,
            x=c * _COL_W,
            y=r * _ROW_H,
        )
        self._nodes.append(node)
        return node

    def add_watch(
        self,
        label: str = "Watch",
        *,
        col: Optional[int] = None,
        row: Optional[int] = None,
    ) -> WatchNode:
        """Retorna un placeholder — Watch nodes omitidos en Dynamo 4.0.

        El formato de Watch cambió en Dynamo 4.0 y genera errores de
        resolución. Los scripts funcionan igual: los resultados se ven
        en el modelo Revit. El nodo NO se agrega al grafo.
        """
        # Placeholder: mismo id dummy para que connect() no falle
        return WatchNode(label=label, x=0, y=0)

    # ------------------------------------------------------------------
    # Conectar nodos
    # ------------------------------------------------------------------

    def connect(
        self,
        from_node: CodeBlockNode | PythonNode | WatchNode,
        to_node: PythonNode | WatchNode,
        to_input: int = 0,
        from_output: int = 0,
    ) -> None:
        """Conecta la salida de `from_node` a la entrada `to_input` de `to_node`.

        Ignora silenciosamente conexiones hacia WatchNode (placeholders).
        """
        # Watch nodes son placeholders — no se agregan al grafo
        if to_node not in self._nodes or from_node not in self._nodes:
            return
        start_port = self._resolve_output_port(from_node, from_output)
        end_port = self._resolve_input_port(to_node, to_input)
        if start_port is None or end_port is None:
            return
        self._connectors.append(_Connector(
            start_port_id=start_port,
            end_port_id=end_port,
        ))

    @staticmethod
    def _resolve_output_port(node, index: int) -> Optional[str]:
        """Devuelve el Id del puerto de SALIDA del nodo.

        Todos los nodos del builder tienen una sola salida (`output_port_id`).
        """
        return getattr(node, "output_port_id", None)

    @staticmethod
    def _resolve_input_port(node, index: int) -> Optional[str]:
        """Devuelve el Id del puerto de ENTRADA `index` del nodo destino."""
        if isinstance(node, PythonNode):
            try:
                return node.input_port_id(index)
            except IndexError:
                return None
        if isinstance(node, WatchNode):
            return node.input_port_id
        return None

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Retorna el documento .dyn completo como diccionario Python."""
        nodes = [n.node_dict() for n in self._nodes]
        connectors = [c.to_dict() for c in self._connectors]
        node_views = [n.view_dict() for n in self._nodes]

        return {
            "Uuid": _uid(),
            "IsCustomNode": False,
            "Description": self.description,
            "Name": self.name,
            "ElementResolver": {"ResolutionMap": {}},
            "Inputs": [],
            "Outputs": [],
            "Nodes": nodes,
            "Connectors": connectors,
            "Dependencies": [],
            "NodeLibraryDependencies": [],
            "EnableLegacyPolyCurveBehavior": True,
            "Bindings": [],
            "View": {
                "Dynamo": {
                    "ScaleFactor": 1.0,
                    "HasRunWithTimeout": False,
                    "IsVisibleInDynamoLibrary": True,
                    "Version": _DYNAMO_VERSION,
                    "RunType": "Manual",
                    "RunPeriod": "1000",
                },
                "Camera": {
                    "Name": "Background Preview",
                    "EyeX": -17.0,
                    "EyeY": 24.0,
                    "EyeZ": 50.0,
                    "LookX": 12.0,
                    "LookY": -13.0,
                    "LookZ": -58.0,
                    "UpX": 0.0,
                    "UpY": 1.0,
                    "UpZ": 0.0,
                },
                "ConnectorPins": [],
                "NodeViews": node_views,
                "Annotations": [],
                "X": 0.0,
                "Y": 0.0,
                "Zoom": 0.75,
            },
        }

    def save(self, path: Path | str) -> Path:
        """Escribe el archivo .dyn en disco y retorna el Path resultante."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return out

    # ------------------------------------------------------------------
    # Auto-layout
    # ------------------------------------------------------------------

    def _resolve_pos(
        self,
        col: Optional[int],
        row: Optional[int],
        advance_col: bool = False,
    ) -> tuple[int, int]:
        c = col if col is not None else self._auto_col
        r = row if row is not None else self._auto_row
        if advance_col:
            self._auto_col = c + 1
            self._auto_row = 0
        return c, r
