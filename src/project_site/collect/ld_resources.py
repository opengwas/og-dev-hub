"""The LD resources collector: each row of the LD Store Registry's `ld-resources.tsv`, through its owner (og-dev-hub#10).

The registry is the run's staged tree (`staging.extract_tree`), read as
`ld_registry.index.resource_rows` reads it: the records under `stores/ld/` and
the LD panels' `resource.yaml` declarations. No TSV is parsed here. A row is
every LD Store, Genotype Store and LD panel, in id order, with a missing value
`None`.

`location` is the host path of the Store and is dropped here: only `PUBLIC`
columns leave this module, so nothing a later column adds reaches the site until
it is named. A registry that cannot be listed (not in this revision, or a record
that breaks the spec) is `available: false` with the reason, and stops nothing
else (ADR 0001: a gap never fails the build).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from ld_registry.index import resource_rows, resources_root_of
from ld_registry.record import LD_ROOT
from ogstores.resources import REFERENCE_RESOURCES_DIR

from project_site.architecture_public import scrub_text

# The columns the Stores page draws, and no others: `location` is never among them.
TEXT = ("ld_id", "label", "kind", "provenance", "status", "used_for", "ancestry", "source_panel", "reference_assembly",
        "built_with", "notes")
NUMBERS = ("n", "store_bytes", "genotype_bytes", "n_variants", "n_blocks")
PUBLIC = TEXT + NUMBERS + ("record",)
# Where a row's `record` may point: a record under `stores/ld/`, or a declaration under `resources/reference-resources/`.
RECORD_DIRECTORIES = (LD_ROOT.as_posix(), REFERENCE_RESOURCES_DIR.as_posix())


def number(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def record_link(record: Any) -> tuple[str | None, str | None]:
    """`(record, gap)`: the record path if it is relative and inside the registry's two directories, else no link and why."""
    path = PurePosixPath(str(record)) if record else None
    if path is None:
        return None, "the registry gives no record path"
    if path.is_absolute() or ".." in path.parts or not any(path.parts[:len(PurePosixPath(d).parts)] == PurePosixPath(d).parts for d in RECORD_DIRECTORIES):
        return None, f"the record path {scrub_text(record)} is not inside {' or '.join(RECORD_DIRECTORIES)}"
    return path.as_posix(), None


def public_row(row: Any) -> dict[str, Any]:
    """The columns the page draws, every text scrubbed and every number a number, and the record link checked."""
    out: dict[str, Any] = {c: scrub_text(row.get(c)) for c in TEXT}
    out.update({c: number(row.get(c)) for c in NUMBERS})
    out["record"], out["record_gap"] = record_link(row.get("record"))
    return out


def collect(stores: Path) -> dict[str, Any]:
    """`{available, error, rows}` for the registry whose Release Bundles are under `stores` (its `stores/`).

    Whatever the reader or a row raises makes the LD section unavailable with the exception's type and message:
    an LD failure is a gap and never takes the GWAS Stores down with it (ADR 0001).
    """
    ld_root = Path(stores) / LD_ROOT.name
    if not ld_root.is_dir():
        return {"available": False, "error": f"this registry revision has no {LD_ROOT.as_posix()}/: the LD Store Registry is not in it", "rows": []}
    try:
        rows = [public_row(row) for row in resource_rows(ld_root, resources_root_of(ld_root))]
    except Exception as error:  # noqa: BLE001 — the reader is the owner's: any failure of it is a gap here
        # The registry's root is the host's business, so a record is named by its place in the registry (`stores/ld/OGL-00003/…`).
        why = f"{type(error).__name__}: {error}".replace(str(ld_root.parent.parent) + "/", "")
        return {"available": False, "error": scrub_text(f"the LD Store Registry could not be listed: {why}"), "rows": []}
    return {"available": True, "error": None, "rows": rows}
