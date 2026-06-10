# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Numerical experiments — scripted, documented, forward-only studies.

Each experiment replays fixed control inputs through the forward simulator and reports
outputs (peak loads, crossrange, timelines) against published flight data, with every
approximation flagged and results documented whichever way they fall. Experiments never
solve for controls: the bank schedule is always an input, crossrange always an output.
"""
