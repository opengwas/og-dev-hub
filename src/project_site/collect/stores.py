"""The Stores collector: each registered Store Release's facts, through `ogstores.bundle` (#389).

The registry is the one read (`stores/` of the run's `staging.registry_files`), not `/data`. A
Release Bundle is read as `ogstores.bundle.load` reads it and no Store is
opened. A fact the bundle cannot state exactly (a `trial` that is not a
boolean, a coverage outside the vocabulary) is `null` with the reason in
`problems`: absence stays distinct from a value, and one bad Store stops
nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ogstores import bundle as release_bundle
from ogstores import paths

from project_site.collect import inventory, ld_resources, yardstick_runs
from project_site.collect.common import CollectError
from project_site.shapes import mapping as _mapping


def registered_store_ids(registry: Path) -> list[str]:
    return sorted(p.name for p in registry.iterdir() if p.is_dir() and paths.is_valid_store_id(p.name))


def _store(registry: Path, store_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The Store's record and its inventory row (`inventory.row`), from one load of its bundle."""
    bundle = release_bundle.load(store_id, registry_root=registry)
    release, build = _mapping(bundle.release), _mapping(bundle.build)
    validation = _mapping(bundle.validation)
    problems: list[str] = []

    def exact(fact: Callable[[], Any]) -> Any:
        try:
            return fact()
        except ValueError as exc:
            problems.append(str(exc))
            return None

    for name, document in (("release.yaml", release), ("build.yaml", build), ("validation.yaml", validation)):
        for key in ("__yaml_error__", "__read_error__", "__document_error__"):
            if key in document:
                problems.append(f"{name}: {document[key]}")
    observed = validation.get("observed")
    record = {
        "store_id": store_id,
        "label": release.get("label"),
        "status": release.get("status"),
        "trial": exact(lambda: bundle.trial),
        "layout": bundle.layout,
        "completion_state": bundle.completion_state,
        "association_coverage": exact(lambda: bundle.association_coverage),
        "access_posture": release.get("access_posture"),
        "derived_from": release.get("derived_from"),
        "superseded_by": release.get("superseded_by"),
        "created_at": release.get("created_at"),
        "accepted_at": release.get("accepted_at"),
        "validated_at": validation.get("validated_at"),
        "validation_status": validation.get("status"),
        "observed": observed if isinstance(observed, dict) else None,
        "description": release.get("description"),
        "notes": release.get("notes"),
        "problems": problems,
    }
    return record, inventory.row(bundle)


def collect(registry: Path, *, yardstick: Path | None = None, commit: str | None = None) -> dict[str, Any]:
    """The Release Bundles under `registry` (the run's `stores/`), their inventory rows and yardstick's results.

    `yardstick` is the registry's `docs/_yardstick/` (by default beside `stores/`), `commit` the
    registry commit read. `ld_resources` is the LD Store Registry's rows (`collect.ld_resources`), without `location`. `registry` is a host path and is never published (`stores_view`).
    """
    registry = Path(registry)
    if not registry.is_dir():
        raise CollectError(f"registry {registry} is not a directory")
    read = [_store(registry, i) for i in registered_store_ids(registry)]
    return {
        "registry": str(registry), "commit": commit,
        "stores": [record for record, _ in read],
        "inventory": [row for _, row in read],
        "ld_resources": ld_resources.collect(registry),
        "yardstick": yardstick_runs.collect(yardstick or registry.parent / "docs" / "_yardstick"),
    }
