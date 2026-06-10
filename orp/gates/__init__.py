# SPDX-License-Identifier: GPL-3.0-or-later
# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
"""Validation gates — forward simulations compared against sourced flight truths.

A gate encodes a real flight's sourced entry state and truth data and runs the validated
simulator FORWARD against them. Gates are *honest by construction* (the pattern of
OpenReentry's gate2/gate3): every value is sourced or explicitly flagged, no flight point is
fabricated, and a gate that cannot yet be validated declares ``NOT_VALIDATED`` rather than
emitting a silent (possibly wrong) pass. Forward-only: gates replay control inputs; they
never solve for controls to hit a target.
"""
