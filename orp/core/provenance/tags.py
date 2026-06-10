# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validation levels, provenance tags, and the tagged-value wrapper.

This module is the foundation of ORP's "provenance on everything" principle. It is
imported by essentially every other module, so it deliberately depends on nothing inside
ORP.

The propagation rule (:func:`weakest`) is the linchpin: when several provenanced inputs
combine to produce a result, the result's provenance is the *weakest* (least-validated) of
its inputs. A trajectory computed from a flight-verified mass but a not-validated drag
coefficient is, as a whole, not validated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Iterable, TypeVar

T = TypeVar("T")

__all__ = [
    "ValidationLevel",
    "ProvenanceTag",
    "TaggedValue",
    "weakest",
]


class ValidationLevel(Enum):
    """How thoroughly a value has been validated, ordered worst → best by :attr:`rank`.

    The ordering matters: provenance combines by taking the *minimum* level (see
    :func:`weakest`), so ``NOT_VALIDATED`` must rank below ``ASSERTED`` below
    ``VERIFIED_SOURCE`` below ``VERIFIED_CFD`` below ``VERIFIED_FLIGHT``.

    ``VERIFIED_SOURCE`` sits between ``ASSERTED`` and ``VERIFIED_CFD``: the implementation
    has been verified (term-by-term or by spot checks) against its *defining* document —
    stronger than merely citing a source, weaker than independent reproduction against CFD
    or flight data. Spot-checks against a defining document verify the implementation, not
    the physics' agreement with flight.
    """

    #: No validation — a placeholder, guess, or as-yet-unsourced value.
    NOT_VALIDATED = ("not_validated", 0, "No validation; placeholder or unsourced.")
    #: Asserted by a credible source (datasheet, paper, report) but not independently
    #: reproduced by ORP.
    ASSERTED = ("asserted", 1, "Asserted by a credible source; not independently reproduced.")
    #: Implementation verified against the defining source document (term-by-term equation
    #: match or table spot-checks), but not independently reproduced against CFD or flight.
    VERIFIED_SOURCE = (
        "verified_source",
        2,
        "Implementation verified against its defining source document.",
    )
    #: Reproduced against computational fluid dynamics / numerical analysis.
    VERIFIED_CFD = ("verified_cfd", 3, "Reproduced against CFD / numerical analysis.")
    #: Reconciled against real flight telemetry / reconstructed flight data.
    VERIFIED_FLIGHT = ("verified_flight", 4, "Reconciled against real flight data.")

    def __init__(self, key: str, rank: int, description: str) -> None:
        self._key = key
        self._rank = rank
        self._description = description

    @property
    def key(self) -> str:
        """Stable lowercase string key (used in YAML and serialized output)."""
        return self._key

    @property
    def rank(self) -> int:
        """Integer ordering; higher is more thoroughly validated."""
        return self._rank

    @property
    def description(self) -> str:
        """Human-readable explanation of what this level means."""
        return self._description

    @classmethod
    def from_string(cls, text: str) -> "ValidationLevel":
        """Parse a level from its enum name or its :attr:`key` (case-insensitive).

        Accepts e.g. ``"VERIFIED_FLIGHT"``, ``"verified_flight"``, or ``"Verified Flight"``.

        Raises:
            ValueError: if ``text`` matches no known level.
        """
        normalized = text.strip().lower().replace(" ", "_").replace("-", "_")
        for level in cls:
            if normalized in (level.name.lower(), level.key):
                return level
        valid = ", ".join(level.name for level in cls)
        raise ValueError(f"Unknown validation level {text!r}; expected one of: {valid}")

    def __lt__(self, other: "ValidationLevel") -> bool:
        if not isinstance(other, ValidationLevel):
            return NotImplemented
        return self.rank < other.rank

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class ProvenanceTag:
    """A validation level plus the citation/notes that justify it.

    Immutable. Attached to every model and combined to tag every simulation output.

    Attributes:
        level: The :class:`ValidationLevel` of the tagged thing.
        source: A citation string (paper, dataset, datasheet, URL). Required in spirit
            for vehicle properties; may be empty for models that document themselves.
        notes: Optional free text (assumptions, caveats, revision).
    """

    level: ValidationLevel
    source: str = ""
    notes: str = ""

    def is_at_least(self, level: ValidationLevel) -> bool:
        """Return ``True`` if this tag is validated at least as strongly as ``level``."""
        return self.level.rank >= level.rank

    def __str__(self) -> str:
        if self.source:
            return f"{self.level.name} <{self.source}>"
        return self.level.name


@dataclass(frozen=True)
class TaggedValue(Generic[T]):
    """A value bound to its provenance (and optionally its physical unit).

    Vehicle properties are stored as ``TaggedValue`` instances so that a value can never
    be used without the question "how do we know this?" being answerable. Use
    :meth:`get` to read the underlying value at the point of use.

    Attributes:
        value: The wrapped value (mass in kg, area in m², a coefficient, …).
        provenance: How the value was validated and where it came from.
        unit: Optional SI unit string for documentation/serialization (e.g. ``"kg"``).
    """

    value: T
    provenance: ProvenanceTag
    unit: str = ""

    def get(self) -> T:
        """Return the underlying value. Explicit by design — reads should be visible."""
        return self.value

    @property
    def level(self) -> ValidationLevel:
        """Shortcut to ``self.provenance.level``."""
        return self.provenance.level

    @classmethod
    def asserted(
        cls,
        value: T,
        source: str,
        *,
        unit: str = "",
        notes: str = "",
    ) -> "TaggedValue[T]":
        """Convenience constructor for an ``ASSERTED`` value with a source citation."""
        return cls(
            value=value,
            provenance=ProvenanceTag(ValidationLevel.ASSERTED, source, notes),
            unit=unit,
        )

    def __str__(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        return f"{self.value}{unit} [{self.provenance}]"


def weakest(items: Iterable[ProvenanceTag | TaggedValue | ValidationLevel]) -> ProvenanceTag:
    """Combine provenance from many inputs into the single weakest-link tag.

    This is the propagation rule for ORP's "provenance on everything" principle: a result
    is only as validated as the least-validated input that produced it. Given a mix of
    :class:`ProvenanceTag`, :class:`TaggedValue`, and bare :class:`ValidationLevel`
    inputs, returns a :class:`ProvenanceTag` at the minimum level, whose ``source``
    aggregates the citations of every input that sits at that minimum level (so the
    returned tag explains *why* the result is only that strong).

    Args:
        items: The contributing provenances (tags, tagged values, or levels). May be empty.

    Returns:
        A :class:`ProvenanceTag` at the weakest level found. For an empty input the result
        is ``NOT_VALIDATED`` with an explanatory note (nothing was provided to trust).
    """
    tags: list[ProvenanceTag] = []
    for item in items:
        if isinstance(item, TaggedValue):
            tags.append(item.provenance)
        elif isinstance(item, ProvenanceTag):
            tags.append(item)
        elif isinstance(item, ValidationLevel):
            tags.append(ProvenanceTag(item))
        else:  # pragma: no cover - defensive
            raise TypeError(
                f"weakest() expects ProvenanceTag/TaggedValue/ValidationLevel, got {type(item)!r}"
            )

    if not tags:
        return ProvenanceTag(
            ValidationLevel.NOT_VALIDATED,
            notes="No provenanced inputs were supplied.",
        )

    min_rank = min(tag.level.rank for tag in tags)
    limiting = [tag for tag in tags if tag.level.rank == min_rank]
    level = limiting[0].level
    sources = sorted({tag.source for tag in limiting if tag.source})
    source = "; ".join(sources)
    notes = f"Limited by {len(limiting)} input(s) at {level.name}."
    return ProvenanceTag(level=level, source=source, notes=notes)
