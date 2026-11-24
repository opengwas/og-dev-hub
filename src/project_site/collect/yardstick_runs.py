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

# What a measure record may carry that the view draws (`path` is `top_hits`': `index` or `scan`, which differ in kind); every other key stays in the registry.
RECORD_KEYS = ("status", "median_ms", "p95_ms", "reps", "reason", "error", "peak_mb", "bytes", "source", "path")


def _record(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record[k] for k in RECORD_KEYS if k in record}


def _run(file: str, doc: dict[str, Any]) -> dict[str, Any]:
    stores = {}
    for store in doc["stores"]:
        stores[store["store_id"]] = {
            "layout": store["layout"], "coverage": store["coverage"], "status": store["status"],
            "reason": store.get("reason"),
            "measures": {name: _record(rec) for name, rec in (store.get("measures") or {}).items()},
        }
    return {
        "file": file,
        "workload_id": doc.get("workload_id"),
        "engine_version": doc["opengwasdb"]["version"],
        "engine_revision": doc["opengwasdb"]["revision"],
        "started_utc": doc["started_utc"],
        "cpu_count": doc["host"]["cpu_count"],
        "load_average": doc["load_average"],
        "veeam_window": doc["veeam_window"],
        "stores": stores,
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
