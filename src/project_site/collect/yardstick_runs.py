"""The yardstick's committed results, read through `yardstick.result` (og-dev-hub#16).

`docs/_yardstick/*.json` of the registry holds one file per run. Each is
validated by `yardstick.result.validate`, the schema's owner; a file it refuses
is not read at all but recorded as a gap naming the file and the validator's
reason. A run keeps only what the Stores view draws, so the raw result files stay
in opengwasdb-stores.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yardstick import result as yardstick_result

from project_site.architecture_public import scrub_text

# What a measure record may carry that the view draws (`path` is `top_hits`': `index` or `scan`, which differ in kind); every other key stays in the registry.
RECORD_KEYS = ("status", "median_ms", "p95_ms", "reps", "reason", "error", "peak_mb", "bytes", "source", "path")
# What the LD view draws of a measure record, and no GWAS-only key (`path` and `source` are `top_hits`' and the walk's). An LD
# Store's `bytes_on_disk` is the files a query reads, links followed (`bytes`); `store_bytes` is the Store's own files
# and `genotype_bytes` a Genotype Store's pgen, psam and pvar files.
LD_RECORD_KEYS = ("status", "median_ms", "p95_ms", "reason", "error", "peak_mb", "bytes", "store_bytes", "genotype_bytes")


def _display_text(value: Any) -> str | None:
    """One string for the browser, with host paths scrubbed before joining any structured note."""
    if isinstance(value, list):
        return "; ".join(_display_text(item) or "" for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{scrub_text(key)}: {_display_text(item) or ''}" for key, item in value.items())
    return scrub_text(value)


def _record(record: dict[str, Any], keys: tuple[str, ...] = RECORD_KEYS) -> dict[str, Any]:
    out = {}
    for key in keys:
        if key in record:
            value = record[key]
            out[key] = _display_text(value) if key in ("reason", "error") or isinstance(value, (str, list, dict)) else value
    return out


def _ld(section: Any) -> dict[str, Any] | None:
    """A run's `ld` section (opengwasdb-stores#504) as the view draws it, or `None` for a run without one: LD was not
    measured in that run, which is not a measure of zero. Each Store is read through `_record` as a GWAS Store is.
    `location` (a host path) and the inputs (the clump input's path among them) are not kept: only the reader's version is."""
    if not isinstance(section, dict):
        return None
    return {
        "ogquery_version": _display_text((section.get("ogquery") or {}).get("version")),
        "stores": {
            store["ld_id"]: {
                "kind": store["kind"], "label": _display_text(store.get("label")), "status": store["status"],
                "reason": _display_text(store.get("reason")),
                "measures": {name: _record(rec, LD_RECORD_KEYS) for name, rec in (store.get("measures") or {}).items()},
            }
            for store in section.get("stores") or []
        },
    }


def _run(file: str, doc: dict[str, Any]) -> dict[str, Any]:
    stores = {}
    for store in doc["stores"]:
        stores[store["store_id"]] = {
            "layout": store["layout"], "coverage": store["coverage"], "status": store["status"],
            "reason": _display_text(store.get("reason")),
            "measures": {name: _record(rec) for name, rec in (store.get("measures") or {}).items()},
        }
    return {
        "file": file,
        "workload_id": _display_text(doc.get("workload_id")),
        "engine_version": _display_text(doc["opengwasdb"]["version"]),
        "engine_revision": doc["opengwasdb"]["revision"],
        "started_utc": doc["started_utc"],
        "cpu_count": doc["host"]["cpu_count"],
        "load_average": doc["load_average"],
        "veeam_window": doc["veeam_window"],
        "stores": stores,
        "ld": _ld(doc.get("ld")),
    }


def collect(directory: Path) -> dict[str, Any]:
    """Every run under `directory`, oldest first, and the files that are not valid results.

    A directory that is not there is `available: false` with why, so the view
    says yardstick has no results rather than drawing nothing.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return {"available": False, "reason": "the registry has no docs/_yardstick/ at the commit read", "runs": [], "invalid": []}
    runs, invalid = [], []
    for path in sorted(directory.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            yardstick_result.validate(doc)
            runs.append(_run(path.name, doc))
        except (OSError, ValueError, KeyError, TypeError) as error:
            invalid.append({"file": path.name, "error": f"{type(error).__name__}: {error}"})
    runs.sort(key=lambda run: (run["started_utc"], run["file"]))
    return {"available": True, "reason": None, "runs": runs, "invalid": invalid}
