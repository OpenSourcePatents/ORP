# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""ORP core: simulation engine, vehicle/environment models, and the provenance system.

This package mirrors the architecture of OpenRocket's flight-simulation subsystem
(design patterns only — no source is copied), adapted from ascent to atmospheric
*reentry*.

Two invariants hold across every module here. They are not guidelines; they are the
identity of the product.

FORWARD SIMULATION ONLY
-----------------------
ORP integrates the equations of motion forward in time from entry conditions and a
*replayed* :class:`~orp.core.bank_schedule.schedule.BankSchedule`. **No function anywhere
in ORP accepts a desired landing point (or any terminal target) and returns a bank
schedule, control law, or any other guidance solution.** ORP answers "given this control
history, where does the vehicle go?" — never the inverse "what control history reaches
this point?". The inverse problem (guidance / trajectory optimization / targeting) is
deliberately, permanently out of scope. If you are unsure whether a proposed function
crosses this line, it does: raise, do not compute.

PROVENANCE ON EVERYTHING
------------------------
Every vehicle property is a :class:`~orp.core.provenance.tags.TaggedValue` carrying a
:class:`~orp.core.provenance.tags.ValidationLevel` and a source citation. Every
environment/aerodynamic model exposes a :class:`~orp.core.provenance.tags.ProvenanceTag`.
Every simulation output (a :class:`~orp.core.simulation.flight_data.FlightData`) carries a
provenance tag computed as the *weakest* of all contributing inputs — a trajectory is only
as validated as the least-validated thing that produced it.

PLACEHOLDER-PHYSICS CONVENTION
------------------------------
This is an architectural skeleton. Methods that compute *flight-dependent* physics
(aerodynamic force coefficients, equation-of-motion derivatives, altitude-dependent
atmosphere profiles, latitude/altitude gravity variation) currently return zero — or, where
a zero would make a derived quantity undefined (e.g. density from a zero-temperature
atmosphere), a planet *reference constant*. Every such body is marked

    # --- PHYSICS SEAM ---

with the real formula documented in the surrounding docstring, so a real implementation
drops into a named seam without reshaping the contract. Planet/vehicle *constants*
(gas constants, surface gravity, mean radius, rotation rate, mass, reference area) are real
values, because they parameterize the seams rather than being part of the placeholder
computation.
"""
