# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Provenance system — validation levels, provenance tags, and tagged values.

Every vehicle property and every simulation output in ORP carries provenance. This
package defines the vocabulary (:class:`ValidationLevel`), the citation record
(:class:`ProvenanceTag`), the value wrapper (:class:`TaggedValue`), and the propagation
rule (:func:`weakest`) by which provenance degrades to its weakest contributing input.
"""

from orp.core.provenance.tags import (
    ProvenanceTag,
    TaggedValue,
    ValidationLevel,
    weakest,
)

__all__ = [
    "ValidationLevel",
    "ProvenanceTag",
    "TaggedValue",
    "weakest",
]
