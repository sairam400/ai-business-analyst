"""One consistent professional chart theme, applied everywhere a chart gets
made. Palette and rules follow a validated categorical/sequential/status
system (see the project's dataviz reference): hues assigned by fixed order,
never cycled or reused for rank; sequential magnitude gets one hue,
light-to-dark; status colors are reserved and never doubled as series 4+."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS = "#c3c2b7"

# fixed order -- never cycle or reassign by rank
CATEGORICAL = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]

STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_SECONDARY,
        "axes.titlecolor": INK_PRIMARY,
        "axes.grid": True,
        "grid.color": GRIDLINE,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "text.color": INK_PRIMARY,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.facecolor": SURFACE,
        "lines.linewidth": 2.0,
        "axes.prop_cycle": plt.cycler(color=CATEGORICAL),
    })


def categorical_colors(n: int) -> list[str]:
    if n > len(CATEGORICAL):
        return CATEGORICAL + [INK_MUTED] * (n - len(CATEGORICAL))
    return CATEGORICAL[:n]
