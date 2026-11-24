"""The Stores inventory: one row per Release Bundle, each field a value or a gap that names its cause (og-dev-hub#16).

Every reading rule belongs to the registry, and is called, never re-derived:

- the bundle: `ogstores.bundle.load`, and its `layout`, `completion_state`,
  `association_coverage` and `status`;
- the Validation Record's flags and top-hit counts: `bundle.observed_flag` and
  `bundle.top_hit_counts_text` (opengwasdb-stores#502);
- the Release Manifest: `opengwasdb.model.analyses.read_analyses` reads
  `analyses.tsv`, and `bundle.partition_membership` splits the built rows from
  the `exclude_from_build` audit rows. Only built rows are counted.

A field the bundle does not hold is a **gap**: `{"value": null, "gap": "<what fills it>"}`.
It is never zero (og-dev-hub ADR 0001: a gap never fails the build). A cell is
`{"value", "gap"}`; the site's build writes the text a reader sees.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from typing import Any, Mapping

from ogstores import bundle as release_bundle

BACKFILL = "recorded from opengwasdb-stores#502's backfill"
COUNTS = "counts come with opengwasdb#488"
CLUMPED = "pending opengwasdb-stores#507"
UNASSIGNED = "unassigned"


def cell(value: Any = None, gap: str | None = None) -> dict[str, Any]:
    """A field: its value, or the gap that names what fills it (never both)."""
    return {"value": None if gap else value, "gap": gap}


def _mapping(document: Any) -> dict[str, Any]:
    return document if isinstance(document, dict) else {}


def _from_bundle(label: str, read) -> dict[str, Any]:
    try:
        value = read()
    except ValueError as error:
        return cell(gap=str(error))
    return cell(value, None if value is not None else f"{label} is not recorded in the bundle")


def _observed_count(observed: Mapping[str, Any], key: str, *, null_gap: str) -> dict[str, Any]:
    """A count of the Validation Record's `observed`: absent is the backfill's to fill, `null` is `null_gap`'s."""
    if key not in observed:
        return cell(gap=BACKFILL)
    value = observed[key]
    if value is None:
        return cell(gap=null_gap)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return cell(gap=f"observed.{key} {value!r} is not a count")
    return cell(value)


def _flag(observed: Mapping[str, Any], key: str, *, null_gap: str) -> dict[str, Any]:
    if key not in observed:
        return cell(gap=BACKFILL)
    try:
        value = release_bundle.observed_flag(observed, key)
    except ValueError as error:
        return cell(gap=str(error))
    return cell(value) if value is not None else cell(gap=null_gap)


def _top_hits(build: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    """The count at each threshold, as `top_hit_counts_text` encodes it, or "not computed" when the recipe has no index."""
    post = _mapping(build.get("post"))
    if post.get("top_hits") is False:
        return cell(gap="not computed: the Build Recipe's post.top_hits is false")
    if "n_top_hits" not in observed:
        return cell(gap=BACKFILL)
    try:
        text = release_bundle.top_hit_counts_text(observed)
    except ValueError as error:
        return cell(gap=str(error))
    if text is None:
        return cell(gap=COUNTS)
    return cell([{"threshold": threshold, "count": count} for threshold, count in json.loads(text).items()])


def _clumped(observed: Mapping[str, Any]) -> dict[str, Any]:
    if observed.get("n_clumped") is None:
        return cell(gap=CLUMPED)
    return _observed_count(observed, "n_clumped", null_gap=CLUMPED)


def _number(text: Any) -> float | None:
    try:
        value = float(str(text).strip().replace(",", ""))
    except ValueError:
        return None
    return value if value == value and value not in (float("inf"), float("-inf")) and value >= 0 else None


def _manifest(bundle: release_bundle.Bundle) -> dict[str, dict[str, Any]]:
    """`n_analyses`, `sample_size` and `ancestry` from the built rows of `analyses.tsv`; or each as the gap naming why not."""
    try:
        from opengwasdb.model import analyses as engine_analyses

        table = engine_analyses.read_analyses(bundle.analyses_path)
        built, excluded = release_bundle.partition_membership(table)
    except FileNotFoundError:
        why = "analyses.tsv is not in the bundle"
    except (OSError, ValueError, UnicodeDecodeError) as error:
        why = f"analyses.tsv cannot be read: {type(error).__name__}: {error}"
    else:
        sizes = [n for n in (_number(row.get("sample_size")) for row in built) if n is not None]
        ancestry = (
            cell(dict(sorted(Counter((row.get("assigned_ancestry") or "").strip() or UNASSIGNED for row in built).items())))
            if "assigned_ancestry" in table.fieldnames
            else cell(gap="analyses.tsv has no assigned_ancestry column")
        )
        return {
            "n_analyses": cell(len(built)) | {"excluded": len(excluded)},
            "median_sample_size": (
                cell(statistics.median(sizes)) | {"with_sample_size": len(sizes), "of": len(built)}
                if sizes
                else cell(gap="no built row records a sample size") | {"with_sample_size": 0, "of": len(built)}
            ),
            "ancestry": ancestry,
        }
    return {name: cell(gap=why) for name in ("n_analyses", "median_sample_size", "ancestry")}


def row(bundle: release_bundle.Bundle) -> dict[str, Any]:
    """The inventory row of one Release Bundle: exactly the fields the Stores view draws."""
    release, build = _mapping(bundle.release), _mapping(bundle.build)
    validation = _mapping(bundle.validation)
    observed = _mapping(validation.get("observed"))
    return {
        "store_id": bundle.store_id,
        "label": release.get("label"),
        "description": release.get("description"),
        "layout": _from_bundle("layout", lambda: bundle.layout),
        "completion_state": _from_bundle("completion_state", lambda: bundle.completion_state),
        "coverage": _from_bundle("association_coverage", lambda: bundle.association_coverage),
        "status": _from_bundle("Release Status", lambda: bundle.status),
        "store_bytes": _observed_count(observed, "store_bytes", null_gap=BACKFILL),
        "n_variants": _observed_count(observed, "n_variants", null_gap=COUNTS),
        "top_hits": _top_hits(build, observed),
        "has_hm3": _flag(observed, "has_hm3", null_gap=BACKFILL),
        "has_rho": _flag(observed, "has_rho", null_gap="not recorded: a Rho Matrix built outside the recipe is not"),
        "n_clumped": _clumped(observed),
        **_manifest(bundle),
    }
