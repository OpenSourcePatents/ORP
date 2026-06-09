# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bank-angle schedule — a *replayed* control history, never a solved one.

A :class:`~orp.core.bank_schedule.schedule.BankSchedule` maps simulation time to bank angle
σ(t) and is replayed by the simulator. It is an **input**, defined ahead of time; ORP never
computes a schedule to reach a target. See the module for the forward-only wall.
"""

from orp.core.bank_schedule.schedule import BankSchedule

__all__ = ["BankSchedule"]
