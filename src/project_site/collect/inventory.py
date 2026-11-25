"""The Stores inventory: one row per Release Bundle, each field a value or a gap that names its cause (og-dev-hub#16).

Every reading rule belongs to the registry, and is called, never re-derived:

- the bundle: `ogstores.bundle.load`, and its `layout`, `completion_state`,
  `association_coverage` and `status`;
- the Validation Record's flags and top-hit counts: `bundle.observed_flag` and
  `bundle.top_hit_counts_text` (opengwasdb-stores#502);
- the Release Manifest: `bundle.manifest_summary`, which counts built rows only
  (an `exclude_from_build` audit row is in no figure but its own count).

A field the bundle does not hold is a **gap**: `{"value": null, "gap": "<what fills it>"}`,
and the cause is the true one: a Store that is not built yet has no observed
facts to wait for a backfill of. A gap is never zero (og-dev-hub ADR 0001: a gap
never fails the build). A cell is `{"value", "gap"}`; the site's build writes the text a reader sees.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ogstores import bundle as release_bundle
from ogstores import plan

from project_site.shapes import mapping as _mapping

BACKFILL = "recorded from opengwasdb-stores#502's backfill"
HM3_UNRECORDED = "no record says how the HM3 step ended"
COUNTS = "counts come with opengwasdb#488"
CLUMPED = "pending opengwasdb-stores#507"
FORMAT_PENDING = "the format version is recorded once opengwasdb-stores#512 lands"


def cell(value: Any = None, gap: str | None = None) -> dict[str, Any]:
    """A field: its value, or the gap that names what fills it (never both)."""
    return {"value": None if gap else value, "gap": gap}


def _from_bundle(label: str, read) -> dict[str, Any]:
    try:
        value = read()
    except ValueError as error:
        return cell(gap=str(error))
    return cell(value, None if value is not None else f"{label} is not recorded in the bundle")


def _not_built(bundle: release_bundle.Bundle) -> str | None:
    """Why a Store has no observed facts to show yet, or `None` when it is built and has a Validation Record."""
    if bundle.status in ("candidate", "accepted"):
        return f"not built yet (Release Status {bundle.status})"
    if not isinstance(bundle.validation, dict):
        # Withdrawn or superseded before any build record: it never will be built.
        return (f"no Validation Record (Release Status {bundle.status})" if bundle.status in ("withdrawn", "superseded")
                else f"not built yet (Release Status {bundle.status})")
    return None


def _is_count(value: Any) -> bool:
    """The one count rule: a non-negative integer (a bool is not one)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _observed_count(observed: Mapping[str, Any], key: str, *, null_gap: str) -> dict[str, Any]:
    """A count of the Validation Record's `observed`: absent is the backfill's to fill, `null` is `null_gap`'s."""
    if key not in observed:
        return cell(gap=BACKFILL)
    value = observed[key]
    if value is None:
        return cell(gap=null_gap)
    return cell(value) if _is_count(value) else cell(gap=f"observed.{key} {value!r} is not a count")


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
    try:
        declared = plan.declared_top_hits(dict(_mapping(build.get("post"))))
    except ValueError as error:
        return cell(gap=str(error))
    if not declared:
        return cell(gap="not computed: the Build Recipe's post.top_hits is not true")
    if "n_top_hits" not in observed:
        return cell(gap=BACKFILL)
    try:
        text = release_bundle.top_hit_counts_text(observed)
    except ValueError as error:
        return cell(gap=str(error))
    if text is None:
        return cell(gap=COUNTS)
    counts = json.loads(text)
    for threshold, count in counts.items():
        if not _is_count(count):
            return cell(gap=f"observed.n_top_hits[{threshold}] {count!r} is not a count")
    return cell([{"threshold": threshold, "count": count} for threshold, count in counts.items()])


def _record_cells(bundle: release_bundle.Bundle, observed: Mapping[str, Any], unbuilt: str | None) -> dict[str, dict[str, Any]]:
    """`format_version`, `built_with` and `last_built`, read from the loaded Validation Record (the bundle has no reader for them)."""
    validation = _mapping(bundle.validation)
    if unbuilt:
        return {k: cell(gap=unbuilt) for k in ("format_version", "built_with", "last_built")}
    version = observed.get("format_version")
    environment = validation.get("build_environment")
    engine = environment.get("opengwasdb_version") if isinstance(environment, Mapping) else None
    return {
        "format_version": cell(version) if version not in (None, "") else cell(gap=FORMAT_PENDING),
        "built_with": (cell(engine) if engine not in (None, "") else
                       cell(gap="the Validation Record has no build_environment.opengwasdb_version")),
        "last_built": (cell(validation.get("validated_at")) if validation.get("validated_at") not in (None, "") else
                       cell(gap="the Validation Record has no validated_at")),
    }


def _manifest(bundle: release_bundle.Bundle) -> dict[str, dict[str, Any]]:
    """`n_analyses`, `median_sample_size` and `ancestry` from `bundle.manifest_summary`; or each as the gap naming why not."""
    try:
        summary = release_bundle.manifest_summary(bundle)
    except FileNotFoundError:
        why = "analyses.tsv is not in the bundle"
    except (OSError, ValueError, UnicodeDecodeError) as error:
        why = f"analyses.tsv cannot be read: {type(error).__name__}: {error}"
    else:
        have, built, bad = summary["n_with_sample_size"], summary["n_built"], summary["n_unparseable_sample_size"]
        no_median = "the Release Manifest records no sample size for any built row" + (
            f" ({bad} value is not a number)" if bad == 1 else f" ({bad} values are not numbers)" if bad else "")
        return {
            "n_analyses": cell(built) | {"excluded": summary["n_excluded"]},
            "median_sample_size": (
                cell(summary["median_sample_size"]) | {"with_sample_size": have, "of": built, "unparseable": bad}
                if summary["median_sample_size"] is not None
                else cell(gap=no_median) | {"with_sample_size": 0, "of": built, "unparseable": bad}
            ),
            "ancestry": (cell(gap="the manifest has no Assigned Ancestry column") if summary["ancestry"] is None
                         else cell(summary["ancestry"]) if summary["ancestry"]
                         else cell(gap="no built row, so there is no ancestry to count")),
        }
    return {name: cell(gap=why) for name in ("n_analyses", "median_sample_size", "ancestry")}


def row(bundle: release_bundle.Bundle) -> dict[str, Any]:
    """The inventory row of one Release Bundle: exactly the fields the Stores view draws."""
    release, build = _mapping(bundle.release), _mapping(bundle.build)
    observed = _mapping(_mapping(bundle.validation).get("observed"))
    unbuilt = _not_built(bundle)
    no_block = None if unbuilt or isinstance(_mapping(bundle.validation).get("observed"), Mapping) else (
        "the Validation Record has no observed block")  # the backfill skips such a record, so it never fills
    if unbuilt or no_block:
        # Nothing was built (or nothing observed): no backfill or engine release will fill these.
        observed_cells = {k: cell(gap=unbuilt or no_block) for k in
                          ("store_bytes", "n_variants", "top_hits", "has_hm3", "has_rho", "n_clumped")}
    else:
        observed_cells = {
            "store_bytes": _observed_count(observed, "store_bytes", null_gap=BACKFILL),
            "n_variants": _observed_count(observed, "n_variants", null_gap=COUNTS),
            "top_hits": _top_hits(build, observed),
            "has_hm3": _flag(observed, "has_hm3", null_gap=HM3_UNRECORDED),
            "has_rho": _flag(observed, "has_rho", null_gap="the recipe builds no Rho Matrix, so whether the Store holds one is unknown until opengwasdb#488"),
            "n_clumped": (cell(gap=CLUMPED) if observed.get("n_clumped") is None
                          else _observed_count(observed, "n_clumped", null_gap=CLUMPED)),
        }
    return {
        "store_id": bundle.store_id,
        "label": release.get("label"),
        "description": release.get("description"),
        "layout": _from_bundle("layout", lambda: bundle.layout),
        "completion_state": _from_bundle("completion_state", lambda: bundle.completion_state),
        "coverage": _from_bundle("association_coverage", lambda: bundle.association_coverage),
        "status": _from_bundle("Release Status", lambda: bundle.status),
        **observed_cells,
        **_record_cells(bundle, observed, unbuilt),
        **_manifest(bundle),
    }
