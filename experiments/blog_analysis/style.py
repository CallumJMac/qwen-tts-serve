"""Shared figure style and SVG theming for the blog figures.

Conventions follow print research figures: Helvetica embedded as outlines so
layout is exact in every browser, open axes with outward ticks, no in-figure
titles (captions carry them), direct labels in place of legends, and units in
axis labels rather than tick labels.

Figures are drawn with light-mode colours, then every colour is rewritten to a
CSS custom property so one SVG serves light and dark readers. Surfaces match
the blog's page background exactly, so a figure has no visible card.
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt  # noqa: E402

LIGHT = {
    "surface": "#fdfdfd",
    "ink": "#1d1d1f",
    "ink-secondary": "#55565b",
    "ink-muted": "#8c8d92",
    "rule": "#b9babe",
    "band": "#ebebed",
    "series-1": "#2a78d6",
    "series-2": "#eb6834",
}
DARK = {
    "surface": "#212737",
    "ink": "#eaedf3",
    "ink-secondary": "#b8bdc9",
    "ink-muted": "#8a90a0",
    "rule": "#5a6278",
    "band": "#2e3549",
    "series-1": "#3987e5",
    "series-2": "#d95926",
}
CURRENT = LIGHT["series-1"]
OMNI = LIGHT["series-2"]

# Physical sizes. The blog's text column is about 680px wide; displaying a
# full-width figure at that width puts 7.5pt tick labels at about 12px.
FULL_WIDTH_INCHES = 6.0
SINGLE_WIDTH_INCHES = 4.0
DISPLAY_PIXELS_PER_POINT = 680 / (FULL_WIDTH_INCHES * 72)


def apply() -> None:
    plt.rcParams.update(
        {
            "svg.fonttype": "path",
            "svg.hashsalt": "qwen-tts-blog",
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial"],
            "font.size": 8,
            "axes.labelsize": 8.5,
            "axes.labelcolor": LIGHT["ink"],
            "axes.edgecolor": LIGHT["ink-secondary"],
            "axes.linewidth": 0.6,
            "axes.facecolor": LIGHT["surface"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "axes.labelpad": 3,
            "xtick.color": LIGHT["ink-secondary"],
            "ytick.color": LIGHT["ink-secondary"],
            "xtick.labelcolor": LIGHT["ink"],
            "ytick.labelcolor": LIGHT["ink"],
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "xtick.minor.size": 1.5,
            "ytick.minor.size": 1.5,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.minor.width": 0.5,
            "ytick.minor.width": 0.5,
            "xtick.major.pad": 2,
            "ytick.major.pad": 2,
            "lines.linewidth": 1.2,
            "lines.markersize": 3.5,
            "errorbar.capsize": 0,
            "legend.frameon": False,
            "figure.facecolor": LIGHT["surface"],
            "savefig.facecolor": LIGHT["surface"],
            "text.color": LIGHT["ink"],
            "mathtext.default": "regular",
        }
    )


def panel_label(axis, letter: str, x_offset: float = -0.13) -> None:
    axis.text(
        x_offset,
        1.02,
        letter,
        transform=axis.transAxes,
        fontweight="bold",
        fontsize=9.5,
        color=LIGHT["ink"],
        ha="left",
        va="bottom",
    )


def reference_line(
    axis,
    value: float,
    label: str,
    *,
    align: str = "left",
    x_range: tuple[float, float] | None = None,
) -> None:
    """A thin dashed threshold with its label sitting just above it.

    With ``x_range`` the line spans only that data interval, leaving room for
    direct labels beyond the data.
    """
    style_kwargs = {
        "color": LIGHT["ink-muted"],
        "linewidth": 0.7,
        "linestyle": (0, (3, 2)),
        "zorder": 1,
    }
    if x_range is None:
        axis.axhline(value, **style_kwargs)
        position, coordinates = (0.01 if align == "left" else 0.99), "axes fraction"
    else:
        axis.hlines(value, *x_range, **style_kwargs)
        position, coordinates = (x_range[0] if align == "left" else x_range[1]), "data"
    axis.annotate(
        label,
        xy=(position, value),
        xycoords=(coordinates, "data"),
        xytext=(0, 1.5),
        textcoords="offset points",
        ha=align,
        va="bottom",
        fontsize=7,
        color=LIGHT["ink-secondary"],
    )


def _theme_svg(svg: str, description: str) -> str:
    for token, light_hex in LIGHT.items():
        svg = re.sub(re.escape(light_hex), f"var(--{token})", svg, flags=re.IGNORECASE)

    def block(palette: dict[str, str]) -> str:
        return " ".join(f"--{token}: {value};" for token, value in palette.items())

    style = (
        f"<style>:root {{ {block(LIGHT)} }}"
        f" @media (prefers-color-scheme: dark) {{ :root {{ {block(DARK)} }} }}</style>"
    )
    escaped = description.replace("&", "&amp;").replace("<", "&lt;")
    svg = re.sub(r"<metadata>.*?</metadata>", "", svg, flags=re.DOTALL)
    return re.sub(
        r"(<svg[^>]*>)",
        lambda match: f"{match.group(1)}<desc>{escaped}</desc>{style}",
        svg,
        count=1,
    )


def save(figure, path: Path, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path, format="svg", bbox_inches="tight", pad_inches=0.04, metadata={"Date": None}
    )
    plt.close(figure)
    path.write_text(_theme_svg(path.read_text(), description))
