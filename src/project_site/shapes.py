"""The one reader of a value that should be a mapping, for the collectors and the build alike."""

from __future__ import annotations

from typing import Any, Mapping


def mapping(value: Any) -> Mapping[str, Any]:
    """`value` if it is a mapping, else none: data of another shape is read as holding nothing."""
    return value if isinstance(value, Mapping) else {}
