# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate evaluation shared by every front end (CLI ``orp gates``, GUI gates panel).

Each gate's status is reported exactly as the gate states it — NOT_VALIDATED and the
replay gate's honest FAIL included, never reworded — and re-evaluated against the
predicates the gate's tests pin. A gate counts as expected when its current behavior
matches its pinned expectation (an honest, pinned FAIL is expected); anything else is
an unexpected deviation.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GateRow", "GatesReport", "evaluate_gates"]


@dataclass(frozen=True)
class GateRow:
    """One gate's status line and whether it matches its pinned expectation."""

    line: str
    as_expected: bool


@dataclass(frozen=True)
class GatesReport:
    """Every gate's row plus the one-line summary and the overall verdict."""

    rows: tuple[GateRow, ...]
    summary_line: str
    all_expected: bool
    validated_count: int


def evaluate_gates() -> GatesReport:
    """Run the gates and report statuses exactly as the gates state them."""
    # Imported at call time so a monkeypatched gate module is honored.
    from orp.gates import gate3_artemis as g3
    from orp.gates import gate3_artemis_replay as gr
    from orp.gates import gate_stardust as gs

    rows: list[GateRow] = []

    # --- Gate 3 scaffold (Artemis I) — pinned by orp/tests/test_gate3_artemis.py ----
    deviations: list[str] = []
    if g3.GATE3_STATUS != "NOT_VALIDATED":
        deviations.append(
            f"GATE3_STATUS is {g3.GATE3_STATUS!r}; pinned expectation is 'NOT_VALIDATED'"
        )
    if g3.lateral_corridor_check()["within_corridor"] is not True:
        deviations.append("lateral corridor check no longer holds")
    try:
        g3.bank_schedule()
        deviations.append(
            "bank_schedule() no longer refuses (the un-locked sign convention is pinned)"
        )
    except NotImplementedError:
        pass
    line = f"GATE 3: Artemis I (Orion) skip entry  --  STATUS: {g3.GATE3_STATUS}"
    if deviations:
        line += f"  [UNEXPECTED DEVIATION: {'; '.join(deviations)}]"
    rows.append(GateRow(line, not deviations))

    # --- Stardust gate — pinned by orp/tests/test_gate_stardust.py -------------------
    deviations = []
    if gs.GATE_STARDUST_STATUS != "NOT_VALIDATED":
        deviations.append(
            f"GATE_STARDUST_STATUS is {gs.GATE_STARDUST_STATUS!r}; "
            "pinned expectation is 'NOT_VALIDATED'"
        )
    entry = gs.run_entry(28.5)
    if abs(entry["peak_g"] - gs.TRUTH_PEAK_G) > gs.TRUTH_PEAK_G_3SIGMA:
        deviations.append(
            f"peak g {entry['peak_g']:.2f} no longer within the flight 3-sigma "
            f"({gs.TRUTH_PEAK_G} +/- {gs.TRUTH_PEAK_G_3SIGMA})"
        )
    line = f"GATE: Stardust SRC ballistic entry  --  STATUS: {gs.GATE_STARDUST_STATUS}"
    if deviations:
        line += f"  [UNEXPECTED DEVIATION: {'; '.join(deviations)}]"
    rows.append(GateRow(line, not deviations))

    # --- Gate 3 replay (Artemis I digitized bank) — honest FAIL pinned by
    # orp/tests/test_gate3_replay.py; verdict wording from docs/gates/gate3_artemis_replay.md:
    # "FAIL against the pre-registered tolerances", sign "NOT LOCKED",
    # "The gate stays NOT_VALIDATED". Re-evaluated here, never reworded. ----------------
    replay = gr.run_replay(mass_kg=10160.5, lift_to_drag=0.25, sign=+1.0)
    flight_ballistic_s = g3.TABLE2_PHASE_TIMES["PredGuid Ballistic"][0]
    deviations = []
    if not (replay["dipped_and_rose"] and not replay["returned"]):
        deviations.append("the replay now returns from the first pass (pinned: it does not)")
    if not replay["skip_apogee_kft"] > 10 * gr.SKIP_APOGEE_KFT_FLIGHT:
        deviations.append(
            f"skip apogee {replay['skip_apogee_kft']:.0f} kft no longer >10x flight "
            f"(pinned divergence)"
        )
    if not all(ep is None for ep in replay["endpoints"].values()):
        deviations.append("a Table-4 altitude crossing is now reached (pinned: none)")
    if not (
        replay["t_drag_fall6_s"] is not None
        and abs(replay["t_drag_fall6_s"] - flight_ballistic_s) > gr.TOL_PHASE_PROXY_S_NOMINAL
    ):
        deviations.append(
            "the phase proxy now agrees within the pre-registered tolerance "
            "(pinned: it does not)"
        )
    line = (
        "GATE 3 REPLAY: Artemis I digitized bank command, forward replay  --  STATUS: "
        "FAIL against the pre-registered tolerances; bank-sign convention NOT LOCKED; "
        "the gate stays NOT_VALIDATED"
    )
    if deviations:
        line = (
            "GATE 3 REPLAY: Artemis I digitized bank command, forward replay  --  "
            f"STATUS: UNEXPECTED DEVIATION from the pinned honest FAIL: "
            f"{'; '.join(deviations)}"
        )
    rows.append(GateRow(line, not deviations))

    # --- summary ----------------------------------------------------------------------
    # A gate counts as validated only if its own status says neither NOT_VALIDATED
    # nor FAIL — derived from the status text, so this tracks future gates.
    validated = sum(
        1 for row in rows if "NOT_VALIDATED" not in row.line and "FAIL" not in row.line
    )
    scaffolded = len(rows) - validated
    all_expected = all(row.as_expected for row in rows)
    closing = (
        "all gates report their pinned expected statuses."
        if all_expected
        else "UNEXPECTED DEVIATION from the pinned statuses detected."
    )
    summary_line = (
        f"Summary: {validated} of {len(rows)} gates validated, "
        f"{scaffolded} scaffolded or honest-FAIL; {closing}"
    )
    return GatesReport(tuple(rows), summary_line, all_expected, validated)
