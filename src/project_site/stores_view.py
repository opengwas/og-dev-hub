"""`data/stores.json` and `data/benchmarking.json`: the Stores and Benchmarking views, decided at build time
from the collected `stores.json` (og-dev-hub#16, #19).

The collector (`collect.stores`) read the registry; this turns what it read into
what the page draws, so `static/js/stores.js` and `static/js/benchmarking.js` only render:

- **the inventory**: one row per Release Bundle, each field a `{text, gap}` cell.
  A gap names what fills it and is never drawn as zero;
- **yardstick** (`benchmarking_view`, the Benchmarking tab's file): for each Store it measures, its latest run's median and p95 per
  measure, peak memory, size on disk, engine version and date; one trend per
  measure across engine versions, as small inline SVG drawn here; and each run
  taken under load or in the Veeam window marked. Raw runs are not listed.

Nothing reaches the file but the fields named here, and every text a collector
wrote has its host paths cut to the last name (`architecture_public.reason`).
"""

from __future__ import annotations

import html
import re
from typing import Any, Mapping

from yardstick import result as yardstick_result

from project_site import architecture_public, paths
from project_site.shapes import mapping

Document = Mapping[str, Any]

# A run is taken "under load" when any load average it recorded, before or after, is over this share of its CPUs.
LOAD_SHARE = 0.25
LOAD_RULE = "a load average (1, 5 or 15 minutes, before or after the run) over a quarter of the host's CPUs"
VEEAM_RULE = "the run overlapped the nightly Veeam backup window that throttled disk I/O until 2026-11-02"



class Measure:
    """How one measure is read and drawn: the record key it is trended on, its unit, and how a figure is written."""

    def __init__(self, unit: str, key: str, show, *, fact: bool = False) -> None:
        # `fact`: drawn as a fact of the Store, and as a trend, not as a row of the table.
        self.unit, self.key, self.show, self.fact = unit, key, show, fact


# Every measure the schema knows, in the order the page draws them. The one table every reader of a measure uses.
MEASURE: dict[str, Measure] = {
    **{name: Measure("ms", "median_ms", lambda v: duration(v)) for name in yardstick_result.TIMED},
    "peak_rss": Measure("MB", "peak_mb", lambda v: megabytes(v), fact=True),
    "bytes_on_disk": Measure("bytes", "bytes", lambda v: size(v), fact=True),
}
MEASURES = tuple(MEASURE)

# How each status the schema knows is drawn: (label, tone). The build decides this; the script only renders it.
# `absent` is the one state this view adds: a run that does not hold the measure.
_STATE = {"measured": ("measured", None), "unavailable": ("unavailable", "fault"), "not_applicable": ("not applicable", None)}
if set(_STATE) != set(yardstick_result.STATUSES):  # a raise, not an assert: it must hold under `python -O`
    raise RuntimeError(f"yardstick.result.STATUSES is {yardstick_result.STATUSES}: say how each status is drawn")
STATE = {**_STATE, "absent": ("not in this run", None)}

# Said on the LD section while no committed result has an `ld` section (og-dev-hub#10): a gap, worded as the others are.
LD_BENCHMARKING_GAP = "LD Stores are not measured yet: no committed yardstick result has an LD section."

CHART_COLUMNS = 6  # series classes `series-0` to `series-5`


def state(name: str) -> dict[str, Any]:
    label, tone = STATE[name]
    return {"state": name, "label": label, "tone": tone}


def text(value: Any) -> Any:
    return architecture_public.reason(value)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def plural(n: int, one: str, many: str) -> str:
    return f"{count(n)} {one if n == 1 else many}"


def count(n: int | float) -> str:
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.1f}"


def size(n: int | float) -> str:
    """A byte count in decimal units: `62.1 GB`."""
    value = float(n)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1000
    raise AssertionError("unreachable")


def duration(ms: int | float) -> str:
    return f"{ms:,.1f} ms" if ms < 1000 else f"{ms / 1000:,.2f} s"


def megabytes(mb: int | float) -> str:
    return f"{mb:,.0f} MB"


# ---------------------------------------------------------------------------
# The inventory
# ---------------------------------------------------------------------------


def _cell(field: Mapping[str, Any] | None, show, *, detail: str | None = None) -> dict[str, Any]:
    """`{text, gap, detail}`: the text of a value, or the gap that names what fills it; exactly one of the two."""
    field = mapping(field)
    if field.get("gap") or field.get("value") is None:
        # `display` is what a tile draws: `n/a`. The reason stays in `gap`, for the expanded tile and for the file.
        return {"text": None, "gap": text(field.get("gap") or "not collected"), "display": NA, "detail": None}
    shown = show(field["value"])
    return {"text": shown, "gap": None, "display": shown, "detail": detail}


NA = "n/a"
SUMMARY_CUT = 160  # the short description is cut to about this many characters
# The facts a tile lists, in order: (cell, label).
TILE_FACTS = (("layout", "Layout"), ("coverage", "Coverage"), ("completion_state", "Completion"), ("format_version", "Format"),
              ("built_with", "Built with"), ("last_built", "Last built"), ("store_bytes", "Size on disk"), ("n_variants", "Variants"),
              ("n_analyses", "Analyses"), ("median_sample_size", "Median sample size"), ("ancestry", "Ancestry"),
              ("top_hits", "Top hits"), ("has_hm3", "HM3"), ("has_rho", "Rho"))
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
# A full stop after one of these does not end a sentence: "et al.", "e.g.", "i.e." or a single initial ("J. Smith").
_ABBREVIATION = re.compile(r"(?:^|[\s(])(?:et al|e\.g|i\.e|[A-Za-z])\.$", re.IGNORECASE)
# The tone of a Release Status tag, written by the build: built and validated are ok, a Store not built yet is neutral, a
# Store that is gone is muted.
STATUS_TONE = {"validated": "ok", "built": "ok", "candidate": None, "accepted": None, "withdrawn": "muted", "superseded": "muted"}


def summary(description: Any, limit: int = SUMMARY_CUT) -> str | None:
    """The first sentence of a description as written, cut to about `limit` characters on a word boundary, ending in `…` when cut.

    The cut is made before host paths are scrubbed; a cut text that holds a host path ends before it.
    """
    flat = " ".join(str(description or "").split())
    if not flat:
        return None
    first = flat
    for end in _SENTENCE_END.finditer(flat):
        if not _ABBREVIATION.search(flat[:end.end()]):
            first = flat[:end.end()]
            break
    cut = first
    if len(first) > limit:
        cut = first[:limit + 1]
        cut = cut[:cut.rfind(" ")] if " " in cut else first[:limit]
    path = architecture_public.HOST_PATH.search(cut)
    if path:  # end before a host path: the build never shows one, and a scrubbed `…/x` would sit beside the cut's `…`
        cut = cut[:path.start()]
    elif len(first) <= limit:
        return first
    return cut.rstrip(" ,;:.-") + "…"


COMPLETION = {"reference_completed": "reference completed", "observed_only": "observed only"}


def _completion(value: Any) -> str:
    """A `completion_state` as a person reads it; a value not listed shows as written."""
    return COMPLETION.get(value, str(value))


def _built_with(value: Any) -> str:
    return f"opengwasdb {value}"


def _yes_no(value: Any) -> str:
    return "yes" if value else "no"


def _top_hits(value: Any) -> str:
    return " · ".join(f"p < {t['threshold']}: {count(t['count'])}" for t in value)


def _ancestry(value: Mapping[str, int]) -> str:
    return " · ".join(f"{code} {count(n)}" for code, n in value.items())


def tile_lists(cells: list[tuple[str, Mapping[str, Any]]], also: list[tuple[str, Mapping[str, Any]]] = ()) -> dict[str, Any]:
    """The one assembler of a tile's lists, for GWAS and LD tiles alike: `facts` from `cells` (`{label, display, detail, na}`)
    and `why_na`, the reason behind each gap among `cells` and `also` (cells the tile does not list as facts, such as its status)."""
    return {
        "facts": [{"label": label, "display": cell["display"], "detail": cell["detail"], "na": bool(cell["gap"])} for label, cell in cells],
        "why_na": [{"label": label, "reason": cell["gap"]} for label, cell in [*cells, *also] if cell["gap"]],
    }


def inventory_row(row: Mapping[str, Any], url: str | None) -> dict[str, Any]:
    median = row.get("median_sample_size") or {}
    n_analyses = row.get("n_analyses") or {}
    out = {
        "store_id": row.get("store_id"),
        "url": url,
        "label": text(row.get("label")),
        "description": text((row.get("description") or "").strip() or None),
        "summary": text(summary(row.get("description"))),
        "layout": _cell(row.get("layout"), str),
        "completion_state": _cell(row.get("completion_state"), str),
        "format_version": _cell(row.get("format_version"), str),
        "built_with": _cell(row.get("built_with"), _built_with),
        "last_built": _cell(row.get("last_built"), str),
        "coverage": _cell(row.get("coverage"), str),
        "status": _cell(row.get("status"), str),
        "store_bytes": _cell(row.get("store_bytes"), size),
        "n_variants": _cell(row.get("n_variants"), count),
        "top_hits": _cell(row.get("top_hits"), _top_hits),
        "has_hm3": _cell(row.get("has_hm3"), _yes_no),
        "has_rho": _cell(row.get("has_rho"), _yes_no),
        "n_clumped": _cell(row.get("n_clumped"), count),
        "n_analyses": _cell(n_analyses, count,
                            detail=f"{count(n_analyses['excluded'])} excluded rows not counted" if n_analyses.get("excluded") else None),
        "median_sample_size": _cell(
            median, count,
            detail=f"over the {count(median.get('with_sample_size', 0))} of {count(median.get('of', 0))} built rows that have one"
                   + (f"; {plural(median['unparseable'], 'value is', 'values are')} not {'a number' if median['unparseable'] == 1 else 'numbers'}"
                      if median.get("unparseable") else "")),
        "ancestry": _cell(row.get("ancestry"), _ancestry),
    }
    # What the tile draws: each fact's display (a gap is `n/a`), and the reason behind each `n/a` for the expanded tile.
    out["status"]["tone"] = None if out["status"]["gap"] else STATUS_TONE.get(out["status"]["text"])
    if not out["completion_state"]["gap"]:  # `text` stays the state as recorded; the tile draws it as a phrase
        out["completion_state"]["display"] = _completion(out["completion_state"]["text"])
    out.update(tile_lists([(label, out[key]) for key, label in TILE_FACTS], [("Release Status", out["status"])]))
    return out


# ---------------------------------------------------------------------------
# LD resources (og-dev-hub#10)
# ---------------------------------------------------------------------------

# The three kinds of the LD Store Registry: (kind, how it is said, singular, plural), in the order the page counts them.
LD_KINDS = (("ld_store", "LD Store", "LD Stores"), ("genotype_store", "Genotype Store", "Genotype Stores"), ("ld_panel", "LD panel", "LD panels"))
LD_KIND_LABEL = {kind: one for kind, one, _ in LD_KINDS}
# The tone of an LD resource's status tag: what is served, built or available is ok, what is gone or only kept is muted.
LD_STATUS_TONE = {"served": "ok", "built": "ok", "available": "ok", "retiring": None, "reference": "muted", "retired": "muted"}


def _ld_gap(kind: Any, what: str) -> str:
    """Why an LD resource's cell is empty: an LD panel's numbers are in its declaration, a Store's in its record."""
    return f"the panel's declaration holds no {what}" if kind == "ld_panel" else f"the Store's record holds no {what}"


def _ld_footprint(row: Mapping[str, Any]) -> str | None:
    """`store_bytes`, and the pgen files' `genotype_bytes` where a Genotype Store has them, through `size`."""
    if row.get("store_bytes") is None:
        return None
    if row.get("genotype_bytes") is None:
        return size(row["store_bytes"])
    return f"{size(row['store_bytes'])} · genotypes {size(row['genotype_bytes'])}"


def _ld_source_panel(row: Mapping[str, Any]) -> str | None:
    """`cohort · ancestry · n 665`; a sample size the registry does not hold reads `n n/a` (its reason is in the tile's "Why n/a")."""
    if not row.get("source_panel"):
        return None
    return " · ".join([str(row["source_panel"])] + ([str(row["ancestry"])] if row.get("ancestry") else [])
                      + [f"n {count(row['n'])}" if row.get("n") is not None else f"n {NA}"])


def ld_row(row: Mapping[str, Any], url: str | None, anchor: str | None = None) -> dict[str, Any]:
    """One tile of the LD section, shaped as a GWAS Store's so one script draws both: `store_id` is the LD id.

    Facts that do not apply to LD (top hits, HM3, Rho, clumping) are not here at all, so they are not `n/a`; Blocks is
    an LD panel's alone. A fact the registry leaves empty is `n/a`, with its reason in `why_na`.
    """
    kind = row.get("kind")

    def cell(value: Any, what: str, show=str) -> dict[str, Any]:
        return _cell({"value": value, "gap": None if value is not None else _ld_gap(kind, what)}, show)

    cells = [
        ("Kind", cell(LD_KIND_LABEL.get(kind, kind), "kind")),
        ("Provenance", cell(row.get("provenance") or None, "provenance")),
        ("Source Panel", cell(_ld_source_panel(row), "source panel")),
        ("Reference Assembly", cell(row.get("reference_assembly") or None, "reference assembly")),
        ("Size on disk", cell(_ld_footprint(row), "size on disk")),
        ("Variants", cell(row.get("n_variants"), "variant count", count)),
        *([("Blocks", cell(row.get("n_blocks"), "block count", count))] if kind == "ld_panel" else []),
        ("Built with", cell(row.get("built_with") or None, "build version")),
    ]
    status = row.get("status")
    status_cell = cell(status or None, "status")
    record_gap = row.get("record_gap")
    description = (row.get("used_for") or "").strip() or None
    out = {
        "store_id": row.get("ld_id"), "url": url, "label": text(row.get("label")), "kind": kind,
        "status": {"display": status if status else NA, "tone": LD_STATUS_TONE.get(status)},
        # As a GWAS tile: the short description in the summary, the full text (and the notes) in the open tile.
        "summary": text(summary(description)), "description": text(description),
        "notes": text((row.get("notes") or "").strip() or None),
        **tile_lists(cells, [("Status", status_cell)]),
        # A Store a committed result measured links to its row in the Benchmarking tab.
        "benchmark": {"href": f"#{anchor}", "text": "LD yardstick results"} if anchor else None,
    }
    if row.get("n") is None:
        out["why_na"].append({"label": "Source Panel n", "reason": _ld_gap(kind, "sample size")})
    if record_gap:  # no link: the reason is a gap, shown with the others
        out["why_na"].append({"label": "Record", "reason": text(record_gap)})
    return out


def _unavailable(reason: str, benchmarking: str | None) -> dict[str, Any]:
    return {"available": False, "gap": reason, "notice": f"LD resources are not listed: {reason}",
            "benchmarking": benchmarking, "rows": []}


def ld_resources_view(doc: Document, commit: str | None) -> dict[str, Any]:
    """The LD section, assembled once: its tiles, or the reason there are none. Whatever raises here makes the section
    unavailable, with the exception's type and message, and never the whole view (ADR 0001)."""
    ld = mapping(doc.get("ld_resources"))
    benchmarked = ld_benchmarked(doc)
    # The gap is "no committed result has an `ld` section", decided from the results alone.
    benchmarking = None if ld_runs(doc) else LD_BENCHMARKING_GAP
    if not ld.get("available"):
        return _unavailable(text(ld.get("error")) or "the LD Store Registry was not collected", benchmarking)
    try:
        rows = [ld_row(r, paths.github_url(paths.REGISTRY, commit, str(r["record"])) if commit and r.get("record") else None,
                       benchmarked.get(r.get("ld_id")))
                for r in ld.get("rows") or [] if isinstance(r, Mapping)]
    except Exception as error:  # noqa: BLE001
        return _unavailable(text(f"{type(error).__name__}: {error}"), benchmarking)
    return {"available": True, "gap": None, "notice": None, "rows": rows,
            "benchmarking": benchmarking}


def counts(gwas: int, ld: Mapping[str, Any]) -> dict[str, Any]:
    """The page's two counts: GWAS Stores, and the LD section's rows with how many of each LD kind (`None` when not listed)."""
    out: dict[str, Any] = {"gwas_stores": {"n": gwas, "text": plural(gwas, "GWAS Store", "GWAS Stores")}}
    if not ld["available"]:
        out["ld_resources"] = {"n": None, "by_kind": [], "text": "LD resources: not counted"}
        return out
    rows = ld["rows"]
    by_kind = [{"kind": kind, "n": n, "text": plural(n, one, many)}
               for kind, one, many in LD_KINDS for n in [sum(1 for r in rows if r["kind"] == kind)]]
    out["ld_resources"] = {"n": len(rows), "by_kind": by_kind,
                           "text": f"{plural(len(rows), 'LD resource', 'LD resources')}: " + ", ".join(k["text"] for k in by_kind)}
    return out


# ---------------------------------------------------------------------------
# Yardstick
# ---------------------------------------------------------------------------


def run_flags(run: Mapping[str, Any]) -> list[str]:
    """Why a run is marked: the Veeam window, or a load average over `LOAD_SHARE` of its CPUs."""
    flags = []
    if run.get("veeam_window"):
        flags.append("taken in the Veeam window")
    limit = float(run.get("cpu_count") or 0) * LOAD_SHARE
    loads = [v for key in ("before", "after") for v in (run.get("load_average") or {}).get(key, [])]
    if loads and max(loads) > limit:
        flags.append(f"taken under load: load average {max(loads):g} over {limit:g} (a quarter of {run['cpu_count']} CPUs)")
    return flags


def _why(record: Mapping[str, Any]) -> Any:
    return text(record.get("reason") if record.get("status") == "not_applicable" else record.get("error"))


def _measure(name: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """One row of the table: the median and p95 of a measured one, else its state and why.

    `path` is `top_hits`': `index` or `scan`, which differ in kind and so are said beside it.
    """
    status = record.get("status")
    measured = status == "measured"
    return {"name": name, "path": record.get("path"), **state(status),
            "median": duration(record["median_ms"]) if measured else None,
            "p95": duration(record["p95_ms"]) if measured else None,
            "note": None if measured else _why(record)}


def _fact(name: str, record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Peak memory or size on disk: its figure, or its state with why (a run that does not hold it says so)."""
    if record is None:
        return {**state("absent"), "text": None, "note": "this run did not measure it"}
    measured = record.get("status") == "measured"
    return {**state(record["status"]), "text": MEASURE[name].show(record[MEASURE[name].key]) if measured else None,
            "note": None if measured else _why(record)}


def _latest(runs: list[Mapping[str, Any]], store_id: str) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """The latest run that measured `store_id`, else the latest that lists it (pending)."""
    listed = [(run, run["stores"][store_id]) for run in runs if store_id in run["stores"]]
    measured = [pair for pair in listed if pair[1]["status"] == "measured"]
    return (measured or listed or [None])[-1]


def _carry_forward(run: Mapping[str, Any], newest: Mapping[str, Any], *, measured: bool) -> tuple[str | None, str | None]:
    """The short run label and panel notice when we show an older result for a Store."""
    if run["file"] == newest["file"]:
        return None, None
    label = f"not in the latest run ({newest['started_utc'][:10]})"
    return label, label + (": this is the latest run that measured it." if measured else ".")


def latest_run(store_id: str, labels: Mapping[str, Any], runs: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    found = _latest(runs, store_id)
    if found is None:
        return None
    run, store = found
    measures = store.get("measures") or {}
    not_in_latest, notice = _carry_forward(run, runs[-1], measured=store["status"] == "measured")
    return {
        "store_id": store_id, "label": labels.get(store_id), "layout": store["layout"], "coverage": store["coverage"],
        "state": store["status"], "reason": text(store.get("reason")),
        "not_in_latest": not_in_latest, "notice": notice,
        "pending": f"Pending in its latest run: {text(store.get('reason')) or 'no reason recorded'}." if store["status"] != "measured" else None,
        "engine_version": run["engine_version"], "date": run["started_utc"][:10], "workload_id": run["workload_id"],
        "flags": run_flags(run),
        "peak_memory": _fact("peak_rss", measures.get("peak_rss")),
        "size_on_disk": _fact("bytes_on_disk", measures.get("bytes_on_disk")),
        "measures": [_measure(name, measures[name]) for name in MEASURES if name in measures and not MEASURE[name].fact],
    }


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def _value(name: str, record: Mapping[str, Any], table: Mapping[str, Measure] = MEASURE) -> float | None:
    value = record.get(table[name].key)
    return float(value) if record.get("status") == "measured" and isinstance(value, (int, float)) else None


def _path(name: str, point: tuple) -> Any:
    """`index` or `scan` for a `top_hits` point, else `None`."""
    return ((point[2].get("measures") or {}).get(name) or {}).get("path")


def trend(name: str, runs: list[Mapping[str, Any]], stores: list[str], table: Mapping[str, Measure] = MEASURE) -> dict[str, Any] | None:
    """One measure across engine versions, as SVG: a series per Store, one point per engine version it was measured at.

    A version run more than once shows its latest run of that Store. Versions
    are ordered by when they were first run, not by their number.
    """
    points: dict[str, dict[str, tuple[float, Mapping[str, Any], Mapping[str, Any]]]] = {}
    versions: list[str] = []
    for run in runs:
        for store_id in stores:
            store = run["stores"].get(store_id)
            value = _value(name, (store or {}).get("measures", {}).get(name) or {}, table)
            if value is None:
                continue
            if run["engine_version"] not in versions:
                versions.append(run["engine_version"])
            points.setdefault(store_id, {})[run["engine_version"]] = (value, run, store)
    if not points:
        return None
    series = [s for s in stores if s in points]
    unit = table[name].unit
    width, height, left, right, top, bottom = 440, 190, 58, 12, 12, 54
    top_value = max(v for s in points.values() for v, _, _ in s.values()) * 1.08 or 1.0

    def x(index: int) -> float:
        return left + (width - left - right) * (index / (len(versions) - 1) if len(versions) > 1 else 0.5)

    def y(value: float) -> float:
        return top + (height - top - bottom) * (1 - value / top_value)

    parts = [f'<svg class="trend-svg" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{html.escape(name)} ({unit}) by engine version">']
    for tick in (0, 0.5, 1):
        value = top_value / 1.08 * tick
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(value):.1f}" y2="{y(value):.1f}"/>'
                     f'<text class="tick" x="{left - 5}" y="{y(value) + 3:.1f}" text-anchor="end">{html.escape(table[name].show(value))}</text>')
    for index, version in enumerate(versions):
        parts.append(f'<text class="tick" x="{x(index):.1f}" y="{height - bottom + 14}" text-anchor="end" '
                     f'transform="rotate(-40 {x(index):.1f} {height - bottom + 14})">{html.escape(version)}</text>')
    flagged = 0
    for number, store_id in enumerate(series):
        cls = f"series-{number % CHART_COLUMNS}"
        mine = sorted(((versions.index(v), pt) for v, pt in points[store_id].items()), key=lambda item: item[0])
        # A line never joins points answered differently (`top_hits` by its index, or by a scan of every cell).
        segments: list[list[tuple[int, tuple]]] = []
        for i, pt in mine:
            if segments and _path(name, segments[-1][-1][1]) == _path(name, pt):
                segments[-1].append((i, pt))
            else:
                segments.append([(i, pt)])
        for segment in segments:
            if len(segment) > 1:
                path = " ".join(f"{x(i):.1f},{y(pt[0]):.1f}" for i, pt in segment)
                parts.append(f'<polyline class="line {cls}" points="{path}"/>')
        for i, (value, run, store) in mine:
            flags = run_flags(run)
            via = _path(name, (value, run, store))
            title = (f"{store_id} · engine {run['engine_version']} · {table[name].show(value)} · {run['started_utc'][:10]}"
                     f" · {run['workload_id']}" + (f" · via {via}" if via else "") + "".join(f" · {f}" for f in flags))
            if flags:
                flagged += 1
                parts.append(f'<circle class="flag-ring" cx="{x(i):.1f}" cy="{y(value):.1f}" r="7"/>')
            parts.append(f'<circle class="pt {cls}{" flagged" if flags else ""}" cx="{x(i):.1f}" cy="{y(value):.1f}" r="3.5">'
                         f'<title>{html.escape(title)}</title></circle>')
    parts.append("</svg>")
    return {
        "measure": name, "unit": unit, "versions": versions, "flagged": flagged,
        "series": [{"store_id": s, "class": f"series-{n % CHART_COLUMNS}", "points": len(points[s])} for n, s in enumerate(series)],
        "svg": "".join(parts),
    }


# The LD section's measures (opengwasdb-stores#504), drawn apart from `MEASURE`: `yardstick.result.LD_TIMED` as timings,
# and the two facts every Store has. Keyed by `ld_id`, never mixed into the GWAS table, trends or unmeasured list.
LD_MEASURE: dict[str, Measure] = {
    **{name: Measure("ms", "median_ms", lambda v: duration(v)) for name in yardstick_result.LD_TIMED},
    "peak_rss": MEASURE["peak_rss"], "bytes_on_disk": MEASURE["bytes_on_disk"],
}
LD_SIZE_BASIS = "files read, links followed"


def _ld_size(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Size on disk of an LD Store: the files a query reads (`bytes`), and, apart, the Store's own files and a Genotype Store's pgen files."""
    fact = _fact("bytes_on_disk", record)
    out = {**fact, "display": _display(fact), "details": []}
    if record is not None and record.get("status") == "measured":
        own = f"the Store's own files: {size(record['store_bytes'])}" if record.get("store_bytes") is not None else None
        if own and record.get("genotype_bytes") is not None:
            own += f", and {size(record['genotype_bytes'])} of genotype files"
        out["details"] = [LD_SIZE_BASIS] + ([own] if own else [])
    return out


def _display(fact: Mapping[str, Any]) -> str:
    """What a table cell draws of a figure: the figure, or its state with why, as the timed measures say it."""
    return fact["text"] if fact.get("text") else f"{fact['label']}: {fact['note']}" if fact.get("note") else str(fact["label"])


def _ld_store(store_id: str, runs: list[Mapping[str, Any]], newest: Mapping[str, Any]) -> dict[str, Any] | None:
    found = _latest(runs, store_id)
    if found is None:
        return None
    run, store = found
    measures = store.get("measures") or {}
    _, notice = _carry_forward(run, newest, measured=True)
    peak = _fact("peak_rss", measures.get("peak_rss"))
    return {
        "store_id": store_id, "anchor": f"ld-bench-{store_id}", "label": store.get("label"),
        "kind": LD_KIND_LABEL.get(store["kind"], store["kind"]),
        "versions": f"engine {run['engine_version']} · ogquery {run['ld']['ogquery_version']}",
        "run": f"{run['started_utc'][:10]} · {run['workload_id']}", "flags": run_flags(run), "notice": notice,
        "peak_memory": {**peak, "display": _display(peak)}, "size_on_disk": _ld_size(measures.get("bytes_on_disk")),
        "measures": [_measure(name, measures[name]) for name in yardstick_result.LD_TIMED if name in measures],
    }


def ld_yardstick(runs: list[Mapping[str, Any]]) -> dict[str, Any]:
    """The Benchmarking tab's LD section: the latest run per LD Store that measured it, and one trend per measure.

    A run without an `ld` section did not measure LD, which is not a measure of zero, and every result before
    opengwasdb-stores#504 is such a run. With no run that has one, there is only the gap. A run whose section
    holds no Store measured no LD Stores, which is not the same thing.
    """
    ld_runs = [{**run, "stores": run["ld"]["stores"]} for run in runs if run.get("ld")]
    newest = runs[-1]["started_utc"][:10] if runs else None
    if not ld_runs:
        why = f"LD not measured in this run ({newest}), nor in any committed run." if newest else "no yardstick result is committed."
        return {"available": False, "gap": f"LD Stores are not measured yet: {why}", "notice": None, "runs": 0, "stores": [], "trends": []}
    ids = sorted({i for run in ld_runs for i in run["stores"]})
    rows = [row for row in (_ld_store(i, ld_runs, runs[-1]) for i in ids) if row]
    latest_ld = ld_runs[-1]
    notices = []
    if latest_ld["file"] != runs[-1]["file"]:
        not_measured = f"LD not measured in this run ({newest})"
        notices.append(not_measured + (": each row is from the latest run that measured that Store, dated in its Run column."
                                       if rows else "."))
    if not latest_ld["stores"]:
        notices.append(f"The latest run with an LD section ({latest_ld['started_utc'][:10]}) measured no LD Stores.")
    return {
        "available": True, "gap": None, "runs": len(ld_runs), "notice": " ".join(notices) or None, "stores": rows,
        "trends": [t for t in (trend(name, ld_runs, ids, LD_MEASURE) for name in LD_MEASURE) if t],
    }


def ld_runs(doc: Document) -> list[Mapping[str, Any]]:
    """The committed results that hold an `ld` section, from the results alone: whether the inventory is readable or has tiles is not asked."""
    return [run for run in mapping(doc.get("yardstick")).get("runs") or [] if isinstance(run, Mapping) and run.get("ld")]


def ld_benchmarked(doc: Document) -> dict[str, str]:
    """`{ld_id: anchor}` for each LD Store some committed result measured: where its tile links to."""
    return {i: f"ld-bench-{i}" for run in ld_runs(doc) for i in run["ld"]["stores"]}


def yardstick_view(doc: Mapping[str, Any], labels: Mapping[str, Any], registry_ids: list[str]) -> dict[str, Any]:
    if not doc.get("available"):
        return {"available": False, "reason": text(doc.get("reason")) or "yardstick's results were not collected"}
    runs = list(doc.get("runs") or [])
    measured_ids = sorted({s for run in runs for s in run["stores"]})
    latest = [row for row in (latest_run(s, labels, runs) for s in measured_ids) if row]
    return {
        "available": True, "reason": None,
        "runs": len(runs), "load_rule": LOAD_RULE, "veeam_rule": VEEAM_RULE,
        "invalid": [{"file": i["file"], "error": text(i["error"])} for i in doc.get("invalid") or []],
        "stores": latest,
        "unmeasured": [{"store_id": s, "label": labels.get(s)} for s in registry_ids if s not in measured_ids],
        "trends": [t for t in (trend(name, runs, measured_ids) for name in MEASURES) if t],
        "workloads": list(dict.fromkeys(str(run["workload_id"]) for run in runs)),
        "ld": ld_yardstick(runs),
    }


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def _envelope(doc: Document) -> dict[str, Any]:
    """The envelope both files start with: what was collected, when, and (if it was not) why."""
    out = {k: doc.get(k) for k in architecture_public.ENVELOPE}
    out["error"] = text(out["error"])
    return out


def stores_view(doc: Document) -> dict[str, Any]:
    """`data/stores.json` from the collected `stores.json`; a source that is not available says why."""
    out = _envelope(doc)
    if not doc.get("available"):
        return out
    commit = doc.get("commit")
    rows = [r for r in doc.get("inventory") or [] if isinstance(r, Mapping)]
    out["registry"] = {
        "name": paths.REGISTRY, "url": paths.clone_url(paths.REGISTRY), "commit": commit,
        "stores_url": paths.github_url(paths.REGISTRY, commit, "stores/") if commit else None,
    }
    out["ld_resources"] = ld_resources_view(doc, commit)
    out["counts"] = counts(len(rows), out["ld_resources"])
    out["inventory"] = [
        inventory_row(r, paths.github_url(paths.REGISTRY, commit, f"stores/{r['store_id']}/") if commit else None) for r in rows
    ]
    return out


def benchmarking_view(doc: Document) -> dict[str, Any]:
    """`data/benchmarking.json`: yardstick's results (the tab's label is Benchmarking; the name stays yardstick)."""
    out = _envelope(doc)
    if not doc.get("available"):
        return out
    rows = [r for r in doc.get("inventory") or [] if isinstance(r, Mapping)]
    labels = {r["store_id"]: text(r.get("label")) for r in rows}
    view = yardstick_view(doc.get("yardstick") or {}, labels, [r["store_id"] for r in rows])
    out["yardstick"] = view
    return out
