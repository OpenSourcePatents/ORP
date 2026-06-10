# ORP — Open Reentry Platform
# Copyright (C) Charles W. Dowd Jr.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Vehicle library — load :class:`EntryVehicle` definitions from YAML.

Each YAML file describes one vehicle. Every physical property is given as a mapping of
``value`` / ``unit`` / ``validation`` / ``source`` / ``notes`` so that the provenance is
captured at the data source, not bolted on later. The loader turns each such mapping into a
:class:`~orp.core.provenance.tags.TaggedValue`.

PyYAML is imported lazily inside the loading methods, so importing this module never requires
PyYAML to be installed (the smoke-test import graph stays dependency-light); it is only
needed when a file is actually read.

Canonical units (values in the YAML are taken as-is, no conversion): mass in kg, areas in
m², lengths in m, coefficients dimensionless, angles in **radians**.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orp.core.provenance.tags import ProvenanceTag, TaggedValue, ValidationLevel
from orp.core.vehicles.base import EntryVehicle

__all__ = ["VehicleLibrary", "load_vehicle"]

# Required tagged properties and the optional ones (defaulted to NOT_VALIDATED zero).
_REQUIRED_PROPERTIES = ("mass", "reference_area", "nose_radius", "drag_coefficient")
_OPTIONAL_PROPERTIES = ("lift_to_drag", "trim_angle_of_attack", "half_cone_angle")


def _parse_tagged_value(name: str, raw: Any) -> TaggedValue[float]:
    """Convert one YAML property mapping into a :class:`TaggedValue`.

    Args:
        name: Property name (for error messages).
        raw: The YAML node — a mapping with at least ``value`` and ``validation``.

    Raises:
        ValueError: if the node is not a mapping or is missing required keys.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"Property {name!r} must be a mapping with 'value'/'validation'/'source', "
            f"got {type(raw).__name__}."
        )
    if "value" not in raw:
        raise ValueError(f"Property {name!r} is missing required key 'value'.")
    if "validation" not in raw:
        raise ValueError(f"Property {name!r} is missing required key 'validation'.")

    level = ValidationLevel.from_string(str(raw["validation"]))
    provenance = ProvenanceTag(
        level=level,
        source=str(raw.get("source", "")),
        notes=str(raw.get("notes", "")),
    )
    return TaggedValue(value=float(raw["value"]), provenance=provenance, unit=str(raw.get("unit", "")))


def _default_tagged_value() -> TaggedValue[float]:
    """A zero value tagged NOT_VALIDATED, used for absent optional properties."""
    return TaggedValue(
        value=0.0,
        provenance=ProvenanceTag(ValidationLevel.NOT_VALIDATED, notes="Not specified."),
    )


class VehicleLibrary:
    """Loads :class:`EntryVehicle` definitions from a directory of YAML files.

    Args:
        data_dir: Directory containing ``*.yaml`` vehicle definitions. Defaults to the
            bundled ``orp/data/vehicles`` directory.
    """

    #: The bundled vehicle-definition directory (orp/data/vehicles).
    DEFAULT_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data" / "vehicles"

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir: Path = Path(data_dir) if data_dir is not None else self.DEFAULT_DATA_DIR

    def list_available(self) -> list[str]:
        """Return the names (filename stems) of all YAML vehicle definitions found."""
        if not self.data_dir.is_dir():
            return []
        return sorted(p.stem for p in self.data_dir.glob("*.yaml"))

    def load(self, name: str) -> EntryVehicle:
        """Load a vehicle by name (the YAML filename without extension).

        Args:
            name: e.g. ``"apollo"`` for ``apollo.yaml`` in :attr:`data_dir`.

        Raises:
            FileNotFoundError: if no matching YAML file exists.
        """
        path = self.data_dir / f"{name}.yaml"
        if not path.is_file():
            available = ", ".join(self.list_available()) or "(none)"
            raise FileNotFoundError(
                f"No vehicle named {name!r} in {self.data_dir} (available: {available})."
            )
        return self.load_file(path)

    def load_file(self, path: Path | str) -> EntryVehicle:
        """Load a vehicle definition from a specific YAML file path.

        Raises:
            ImportError: if PyYAML is not installed.
            ValueError: if the file is malformed or missing required properties.
        """
        try:
            import yaml  # lazy: importing this module must not require PyYAML
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "PyYAML is required to load vehicle definitions. Install it with "
                "'pip install pyyaml' (it is a declared dependency of orp)."
            ) from exc

        path = Path(path)
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        if not isinstance(data, dict):
            raise ValueError(f"{path}: top-level YAML must be a mapping.")
        return self._from_mapping(data, source_path=path)

    @staticmethod
    def _from_mapping(data: dict[str, Any], *, source_path: Path | None = None) -> EntryVehicle:
        """Build an :class:`EntryVehicle` from a parsed YAML mapping."""
        where = f" in {source_path}" if source_path is not None else ""

        name = data.get("name")
        if not name:
            raise ValueError(f"Vehicle definition is missing 'name'{where}.")

        properties = data.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"Vehicle {name!r} is missing a 'properties' mapping{where}.")

        for key in _REQUIRED_PROPERTIES:
            if key not in properties:
                raise ValueError(f"Vehicle {name!r} is missing required property {key!r}{where}.")

        tagged: dict[str, TaggedValue[float]] = {
            key: _parse_tagged_value(key, properties[key]) for key in _REQUIRED_PROPERTIES
        }
        for key in _OPTIONAL_PROPERTIES:
            tagged[key] = (
                _parse_tagged_value(key, properties[key])
                if key in properties
                else _default_tagged_value()
            )

        return EntryVehicle(
            name=str(name),
            mass=tagged["mass"],
            reference_area=tagged["reference_area"],
            nose_radius=tagged["nose_radius"],
            drag_coefficient=tagged["drag_coefficient"],
            lift_to_drag=tagged["lift_to_drag"],
            trim_angle_of_attack=tagged["trim_angle_of_attack"],
            half_cone_angle=tagged["half_cone_angle"],
            intended_planet=str(data.get("intended_planet", "earth")),
            description=str(data.get("description", "")),
        )


def load_vehicle(name: str, data_dir: Path | None = None) -> EntryVehicle:
    """Module-level convenience: load a bundled vehicle by name.

    Equivalent to ``VehicleLibrary(data_dir).load(name)``.
    """
    return VehicleLibrary(data_dir).load(name)
