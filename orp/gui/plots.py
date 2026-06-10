# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless trajectory plotting — :class:`~orp.core.simulation.flight_data.FlightData` to PNG.

Strictly non-interactive: figures are built on :class:`matplotlib.figure.Figure` objects
directly (no ``pyplot``, no backend selection, no GUI event loop), so this module is safe
on headless machines and in test runners. Matplotlib is imported lazily inside the plotting
calls, mirroring the PyYAML pattern in the vehicle library: importing :mod:`orp.gui.plots`
never requires matplotlib to be installed.

Provenance travels onto the artifact: every figure carries a stamp with the trajectory's
weakest-link validation level (and its limiting source when available), so a rendered plot
can never be passed around without the question "how validated is this?" being answerable
from the image itself.

Plots are pure *outputs* of an already-integrated trajectory. Nothing in this module (or
anywhere in ORP) accepts a desired endpoint and returns controls — plotting keeps to the
forward-only wall like everything else.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from orp.core.simulation import flight_data as fd
from orp.core.simulation.flight_data import FlightData, FlightDataBranch

if TYPE_CHECKING:  # pragma: no cover - typing only
    from matplotlib.figure import Figure

__all__ = [
    "plot_altitude_time",
    "plot_velocity_time",
    "plot_g_load_time",
    "plot_heat_rate_time",
    "plot_ground_track",
    "save_standard_plots",
]


def _new_figure() -> "Figure":
    """Create a bare, backend-independent Figure (lazy matplotlib import)."""
    try:
        from matplotlib.figure import Figure
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "matplotlib is required for plotting. Install it with 'pip install matplotlib' "
            "(or the 'orp[plot]' extra)."
        ) from exc

    return Figure(figsize=(8.0, 5.0), dpi=120)


def _stamp_provenance(figure: "Figure", flight_data: FlightData) -> None:
    """Print the trajectory's provenance level (and limiting source) on the figure."""
    provenance = flight_data.provenance
    text = f"Provenance: {provenance.level.name}"
    if provenance.source:
        text += f" — {provenance.source}"
    # Bottom-left corner, small but legible; part of the rendered artifact by design.
    figure.text(0.01, 0.01, text, fontsize=7, color="dimgray", wrap=True)


def _primary_branch(flight_data: FlightData) -> FlightDataBranch:
    if flight_data.branch_count == 0:
        raise ValueError("FlightData has no branches to plot.")
    return flight_data.get_branch(0)


def _line_plot(
    flight_data: FlightData,
    x_type: fd.FlightDataType,
    y_type: fd.FlightDataType,
    *,
    title: str,
    path: Path | str | None,
) -> "Figure":
    """Shared single-channel-vs-channel line plot with provenance stamp."""
    branch = _primary_branch(flight_data)
    figure = _new_figure()
    axes = figure.subplots()
    axes.plot(branch.get(x_type), branch.get(y_type), linewidth=1.2)
    axes.set_xlabel(str(x_type))
    axes.set_ylabel(str(y_type))
    axes.set_title(title)
    axes.grid(True, alpha=0.3)
    _stamp_provenance(figure, flight_data)
    figure.set_layout_engine("tight")
    if path is not None:
        figure.savefig(path)
    return figure


def plot_altitude_time(flight_data: FlightData, path: Path | str | None = None) -> "Figure":
    """Altitude vs. time. Saves to ``path`` if given; returns the Figure either way."""
    return _line_plot(
        flight_data, fd.TYPE_TIME, fd.TYPE_ALTITUDE, title="Altitude vs. time", path=path
    )


def plot_velocity_time(flight_data: FlightData, path: Path | str | None = None) -> "Figure":
    """Planet-relative speed vs. time."""
    return _line_plot(
        flight_data, fd.TYPE_TIME, fd.TYPE_VELOCITY, title="Velocity vs. time", path=path
    )


def plot_g_load_time(flight_data: FlightData, path: Path | str | None = None) -> "Figure":
    """Sensed deceleration (g) vs. time."""
    return _line_plot(
        flight_data, fd.TYPE_TIME, fd.TYPE_DECELERATION, title="Sensed g-load vs. time", path=path
    )


def plot_heat_rate_time(flight_data: FlightData, path: Path | str | None = None) -> "Figure":
    """Stagnation-point convective heat rate vs. time."""
    return _line_plot(
        flight_data, fd.TYPE_TIME, fd.TYPE_HEAT_RATE,
        title="Stagnation heat rate vs. time", path=path,
    )


def plot_ground_track(flight_data: FlightData, path: Path | str | None = None) -> "Figure":
    """Ground track: latitude vs. longitude (degrees), entry point marked."""
    branch = _primary_branch(flight_data)
    longitude = branch.get(fd.TYPE_LONGITUDE)
    latitude = branch.get(fd.TYPE_LATITUDE)

    figure = _new_figure()
    axes = figure.subplots()
    axes.plot(longitude, latitude, linewidth=1.2)
    if longitude and latitude:
        axes.plot(longitude[0], latitude[0], marker="^", color="tab:green", label="entry")
        axes.plot(longitude[-1], latitude[-1], marker="v", color="tab:red", label="end")
        axes.legend(loc="best", fontsize=8)
    axes.set_xlabel(str(fd.TYPE_LONGITUDE))
    axes.set_ylabel(str(fd.TYPE_LATITUDE))
    axes.set_title("Ground track")
    axes.grid(True, alpha=0.3)
    _stamp_provenance(figure, flight_data)
    figure.set_layout_engine("tight")
    if path is not None:
        figure.savefig(path)
    return figure


def save_standard_plots(flight_data: FlightData, directory: Path | str) -> list[Path]:
    """Render the standard five trajectory plots into ``directory`` as PNG files.

    Returns the written paths (altitude, velocity, g-load, heat-rate, ground-track).
    The directory is created if needed.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plotters = (
        ("altitude_time", plot_altitude_time),
        ("velocity_time", plot_velocity_time),
        ("g_load_time", plot_g_load_time),
        ("heat_rate_time", plot_heat_rate_time),
        ("ground_track", plot_ground_track),
    )
    written: list[Path] = []
    for stem, plotter in plotters:
        target = directory / f"{stem}.png"
        plotter(flight_data, target)
        written.append(target)
    return written
