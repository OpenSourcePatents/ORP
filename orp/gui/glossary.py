# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The GUI glossary: every (i) definition, as plain reviewable strings.

CONTENT RULES (the honesty guard applies to tooltips too):
- The provenance/tag definitions restate the documented meanings EXACTLY — the
  ValidationLevel descriptions from orp/core/provenance/tags.py and the dataset-tag
  wording from data/flights/artemis1_bank_commanded.csv — followed by plain-language
  context that never softens them. orp/tests/test_gui.py pins each documented
  sentence verbatim inside its entry.
- The wall vocabulary rules apply to every string here: nothing endpoint-seeking,
  with forbidden terms allowed only in explicit negations ("an input, not a target").
"""

from __future__ import annotations

__all__ = ["GLOSSARY", "glossary_text"]

GLOSSARY: dict[str, str] = {
    # ----- core objects ---------------------------------------------------------
    "planet": (
        "The environment the vehicle flies through. A planet bundles an atmosphere "
        "model, a gravity model, a mean radius, and a rotation rate; Earth and Mars "
        "ship in the registry. Each model carries its own provenance tag."
    ),
    "vehicle": (
        "The reentry body, loaded from the YAML library. Every property (mass, "
        "reference area, nose radius, drag coefficient, lift-to-drag, trim angle of "
        "attack, half-cone angle) carries its own provenance tag and source "
        "citation; the vehicle's overall level is its weakest property."
    ),
    # ----- frames ----------------------------------------------------------------
    "frame": (
        "Which reference frame the entry state you typed is expressed in. The engine "
        "consumes a planet-relative state; an inertial state is converted at this "
        "boundary via orp.core.frames before the run (convert first, then run)."
    ),
    "inertial": (
        "A frame that does not rotate with the planet. Tracking and publications "
        "often quote entry states this way. ORP converts an inertial entry state to "
        "planet-relative by subtracting the eastward planet-rotation velocity, then "
        "runs; the saved session records the converted state."
    ),
    "planet-relative": (
        "A frame rotating with the planet: velocity measured relative to the local "
        "atmosphere-carrying surface. This is the state the engine actually "
        "integrates, and the only frame session files record."
    ),
    # ----- entry state -----------------------------------------------------------
    "entry speed": (
        "Speed at entry interface, meters per second, expressed in the selected "
        "frame."
    ),
    "flight path angle": (
        "The angle between the velocity vector and the local horizontal, in degrees; "
        "negative means descending. Steeper (more negative) entries decelerate "
        "harder and heat faster."
    ),
    "initial heading": (
        "Where the velocity vector points at entry interface, degrees clockwise from "
        "north. It is an input flown forward — an input, not a target. ORP never "
        "accepts an endpoint and produces controls; where the vehicle ends up is an "
        "output of the replay."
    ),
    "entry altitude": (
        "Height above the planet's mean radius at entry interface, meters."
    ),
    "entry latitude": (
        "Latitude where the run starts, degrees. This is where the vehicle IS at "
        "entry interface; everything after that is integrated forward."
    ),
    "entry longitude": (
        "Longitude where the run starts, degrees. This is where the vehicle IS at "
        "entry interface; everything after that is integrated forward."
    ),
    # ----- bank schedule ----------------------------------------------------------
    "bank angle": (
        "The roll angle sigma that rotates the lift vector about the velocity "
        "vector: its cosine component raises or lowers the flight path, its sine "
        "component turns the heading. In ORP the bank history is a pre-recorded "
        "control input replayed forward, never solved for."
    ),
    "constant angle": (
        "Hold one fixed bank command for the whole run. Hand-entered, so its "
        "provenance is NOT_VALIDATED: no validation; it is an unsourced control "
        "history, and the run's weakest link will say so."
    ),
    "CSV import": (
        "Load a two-column (time, bank angle) commanded-bank history through "
        "BankSchedule.from_csv, which refuses rather than repairs: blank cells, "
        "gaps, duplicate or backwards timestamps are errors, never interpolated "
        "over. Imported histories are tagged ASSERTED naming the file."
    ),
    "piecewise editor": (
        "Type a bank history point by point; the schedule replays it with linear "
        "interpolation between points. Hand-entered histories from this editor are "
        "tagged ASSERTED."
    ),
    # ----- provenance levels (documented meanings, exact) -------------------------
    "NOT_VALIDATED": (
        "No validation; placeholder or unsourced. Nothing vouches for this value — "
        "it may be a stand-in. Any run that uses it is NOT_VALIDATED overall, and "
        "ORP says so rather than rounding up."
    ),
    "ASSERTED": (
        "Asserted by a credible source; not independently reproduced. Someone "
        "trustworthy published the number and it is cited, but ORP has not "
        "reproduced it."
    ),
    "VERIFIED_SOURCE": (
        "Implementation verified against its defining source document. The code was "
        "checked against the document that defines it — that verifies the "
        "implementation, not agreement with flight."
    ),
    "VERIFIED_CFD": (
        "Reproduced against CFD / numerical analysis. Independent computation "
        "agrees; still not flight evidence."
    ),
    "VERIFIED_FLIGHT": (
        "Reconciled against real flight data. The strongest tag ORP issues: the "
        "value agrees with what actually flew."
    ),
    "MACHINE-DIGITIZED": (
        "A dataset tag meaning pixel extraction from a published figure; not flight "
        "telemetry. The numbers were measured off a plot in a paper, with the "
        "digitization method and uncertainty documented; treat them with that "
        "uncertainty, not as telemetry."
    ),
    "weakest link": (
        "Provenance propagates: a trajectory is only as trustworthy as the weakest "
        "input that produced it. Every run reports the lowest tag among vehicle, "
        "planet models, aerodynamics, bank schedule, and equations of motion — "
        "quoting one strong component would launder the weak ones."
    ),
    # ----- results summary ---------------------------------------------------------
    "peak deceleration": (
        "The largest sensed aerodynamic load of the run, in standard g. It is the "
        "drag and lift force per unit mass (gravity excluded, as an accelerometer "
        "would sense it) divided by standard gravity."
    ),
    "peak heat rate": (
        "The largest stagnation-point convective heating rate, in watts per square "
        "meter, from the Sutton-Graves correlation using the planet's constant, the "
        "local density, the nose radius, and velocity cubed. Convective only - no "
        "radiative term."
    ),
    "peak dynamic pressure": (
        "The largest dynamic pressure q = 1/2 * density * speed^2 of the run, in "
        "pascals - the structural-load measure of how hard the air is pushing."
    ),
    "impact velocity": (
        "The planet-relative speed at the final recorded sample - ground contact if "
        "the run reached the surface, otherwise wherever it ended. ORP models no "
        "parachutes yet, so this is the unbraked aerodynamic value."
    ),
}


def glossary_text(key: str) -> str:
    """The definition for ``key`` (KeyError if missing — icons must never dangle)."""
    return GLOSSARY[key]
