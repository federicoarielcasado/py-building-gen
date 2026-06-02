"""Widget de previsualización: planta de situación + silueta en alzado."""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.parametros import ParametrosEdificio

_FOS_EDIFICIO = 0.70   # Factor de Ocupación del Suelo típico CABA entre medianeras


class PreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.fig = Figure(figsize=(5, 7))
        gs = gridspec.GridSpec(2, 1, figure=self.fig, height_ratios=[3, 2], hspace=0.35)
        self.ax_planta = self.fig.add_subplot(gs[0])
        self.ax_alzado = self.fig.add_subplot(gs[1])
        self.canvas = FigureCanvas(self.fig)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def update_plot(self, params: ParametrosEdificio) -> None:
        self.ax_planta.clear()
        self.ax_alzado.clear()
        self._draw_planta(params)
        self._draw_alzado(params)
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Planta de situación
    # ------------------------------------------------------------------

    def _draw_planta(self, params: ParametrosEdificio) -> None:
        ax = self.ax_planta
        f, fo = params.frente, params.fondo
        build_fo = fo * _FOS_EDIFICIO

        ax.add_patch(mpatches.Rectangle(
            (0, 0), f, fo,
            linewidth=1.5, edgecolor="#555555", facecolor="#f5f0e8",
            linestyle="--", zorder=1,
        ))
        ax.add_patch(mpatches.Rectangle(
            (0, 0), f, build_fo,
            linewidth=2, edgecolor="#1a4f7a", facecolor="#cce0f5", zorder=2,
        ))
        ax.add_patch(mpatches.Rectangle(
            (0, build_fo), f, fo - build_fo,
            linewidth=1, edgecolor="#3a7a20", facecolor="#d8f0c8",
            linestyle=":", zorder=2,
        ))

        # Cotas
        y_c = -fo * 0.06
        ax.annotate("", xy=(f, y_c), xytext=(0, y_c),
                    arrowprops=dict(arrowstyle="<->", color="#333", lw=1.1))
        ax.text(f / 2, y_c - fo * 0.04, f"{f:.2f} m", ha="center", va="top", fontsize=7.5)

        x_c = f + f * 0.10
        ax.annotate("", xy=(x_c, fo), xytext=(x_c, 0),
                    arrowprops=dict(arrowstyle="<->", color="#333", lw=1.1))
        ax.text(x_c + f * 0.04, fo / 2, f"{fo:.2f} m",
                ha="left", va="center", fontsize=7.5, rotation=90)

        ax.text(f / 2, build_fo / 2, "Edificio",
                ha="center", va="center", fontsize=8, color="#1a4f7a", fontweight="bold", zorder=3)
        ax.text(f / 2, build_fo + (fo - build_fo) / 2, "Patio A y L",
                ha="center", va="center", fontsize=7, color="#3a7a20", zorder=3)

        # Flecha norte
        nx, ny = f * 0.88, fo * 0.88
        ax.annotate("", xy=(nx, ny + fo * 0.06), xytext=(nx, ny),
                    arrowprops=dict(arrowstyle="->", color="#222", lw=1.6))
        ax.text(nx, ny + fo * 0.08, "N", ha="center", va="bottom", fontsize=8, fontweight="bold")

        fos = build_fo / fo
        ax.text(
            0.02, 0.01,
            f"Sup. lote:  {f * fo:.0f} m²\n"
            f"Sup. edif.: {f * build_fo:.0f} m²\n"
            f"FOS est.:   {fos:.2f}",
            transform=ax.transAxes, fontsize=7, va="bottom", family="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#bbb", alpha=0.9),
        )

        mx, my = f * 0.25, fo * 0.15
        ax.set_xlim(-mx, f + mx * 2.5)
        ax.set_ylim(-my * 1.5, fo + my)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title("Planta de situación — esquemática", fontsize=8.5, pad=5)

    # ------------------------------------------------------------------
    # Silueta en alzado (fachada principal)
    # ------------------------------------------------------------------

    def _draw_alzado(self, params: ParametrosEdificio) -> None:
        ax = self.ax_alzado
        f = params.frente
        h_pb = params.altura_pb
        h_tip = params.altura_tipo
        n = params.pisos_tipo

        alt_total = params.altura_total
        colores_piso = ["#cce0f5", "#d6e8f8"]

        y = 0.0

        # Subsuelos
        for i in range(params.cant_subsuelos):
            ax.add_patch(mpatches.Rectangle(
                (0, -(i + 1) * h_tip), f, h_tip,
                linewidth=1, edgecolor="#888", facecolor="#e0e0e0", zorder=2,
            ))
            ax.text(f / 2, -(i + 0.5) * h_tip, f"SS{i+1:02d}",
                    ha="center", va="center", fontsize=6.5, color="#555")

        # PB
        ax.add_patch(mpatches.Rectangle(
            (0, 0), f, h_pb,
            linewidth=1.5, edgecolor="#1a4f7a", facecolor="#b8d4ee", zorder=2,
        ))
        ax.text(f / 2, h_pb / 2, "PB", ha="center", va="center", fontsize=7, color="#1a4f7a")
        y = h_pb

        # Pisos tipo
        for i in range(n):
            col = colores_piso[i % 2]
            ax.add_patch(mpatches.Rectangle(
                (0, y), f, h_tip,
                linewidth=0.8, edgecolor="#4a80aa", facecolor=col, zorder=2,
            ))
            if i % 2 == 0 or i == n - 1:
                ax.text(f / 2, y + h_tip / 2, f"P{i+1:02d}",
                        ha="center", va="center", fontsize=6, color="#2a5f8a")
            y += h_tip

        # Azotea
        if params.tiene_azotea:
            ax.add_patch(mpatches.Rectangle(
                (0, y), f, 0.60,
                linewidth=1, edgecolor="#555", facecolor="#a0b8cc", zorder=2,
            ))
            ax.text(f / 2, y + 0.30, "AZO", ha="center", va="center", fontsize=6, color="#333")
            y += 0.60

        # Cota de altura total
        ax.annotate("", xy=(f + f * 0.08, y), xytext=(f + f * 0.08, 0),
                    arrowprops=dict(arrowstyle="<->", color="#333", lw=1.1))
        ax.text(f + f * 0.12, y / 2, f"{alt_total:.2f} m",
                ha="left", va="center", fontsize=7, rotation=90)

        # Info: n pisos + deptos
        total_dep = params.cant_departamentos_total
        ax.text(
            0.02, 0.98,
            f"{n} pisos tipo  |  {total_dep} deptos total\n"
            f"H° {params.hormigon_tipo}  /  {params.acero_tipo}",
            transform=ax.transAxes, fontsize=7, va="top", family="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#bbb", alpha=0.9),
        )

        sub_offset = params.cant_subsuelos * h_tip
        ax.set_xlim(-f * 0.10, f + f * 0.35)
        ax.set_ylim(-sub_offset - h_pb * 0.3, y + h_pb * 0.4)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title("Silueta en alzado — fachada principal", fontsize=8.5, pad=5)
