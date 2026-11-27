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

from pathlib import Path
from typing import Any

from ld_registry.index import resource_rows, resources_root_of

# The columns the Stores page draws, and no others: `location` is never among them.
PUBLIC = ("ld_id", "label", "kind", "provenance", "status", "used_for", "ancestry", "source_panel", "n",
          "reference_assembly", "store_bytes", "genotype_bytes", "n_variants", "built_with", "record", "notes")


def collect(stores: Path) -> dict[str, Any]:
    """`{available, error, rows}` for the registry whose Release Bundles are under `stores` (its `stores/`)."""
    ld_root = Path(stores) / "ld"
    if not ld_root.is_dir():
        return {"available": False, "error": "this registry revision has no stores/ld/: the LD Store Registry is not in it", "rows": []}
    try:
        rows = resource_rows(ld_root, resources_root_of(ld_root))
    except (ValueError, OSError) as error:  # InvalidRecords, IdCollision and PanelError are ValueErrors
        return {"available": False, "error": f"the LD Store Registry could not be listed: {error}", "rows": []}
    return {"available": True, "error": None, "rows": [{column: row.get(column) for column in PUBLIC} for row in rows]}
