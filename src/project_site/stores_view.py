"""`data/stores.json`: the Stores view, decided at build time from the collected `stores.json` (og-dev-hub#16).

The collector (`collect.stores`) read the registry; this turns what it read into
what the page draws, so `static/js/stores.js` only renders:

- **the inventory**: one row per Release Bundle, each field a `{text, gap}` cell.
  A gap names what fills it and is never drawn as zero;
- **yardstick**: for each Store it measures, its latest run's median and p95 per
  measure, peak memory, size on disk, engine version and date; one trend per
  measure across engine versions, as small inline SVG drawn here; and each run
  taken under load or in the Veeam window marked. Raw runs are not listed.

Nothing reaches the file but the fields named here, and every text a collector
wrote has its host paths cut to the last name (`architecture_public.reason`).
"""

from __future__ import annotations

import html
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

# LD Stores have no registry yet: say so as a gap, never as a count of zero (docs/spec/project-site.md).
LD_STORES = {"gap": "LD Stores are not listed yet: their registry is opengwasdb-stores#496 and the view waits on "
                    "og-dev-hub#10. Their number is unknown, not 0."}

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
        return {"text": None, "gap": text(field.get("gap") or "not collected"), "detail": None}
    return {"text": show(field["value"]), "gap": None, "detail": detail}


def _yes_no(value: Any) -> str:
    return "yes" if value else "no"


def _top_hits(value: Any) -> str:
    return " · ".join(f"p < {t['threshold']}: {count(t['count'])}" for t in value)


def _ancestry(value: Mapping[str, int]) -> str:
    return " · ".join(f"{code} {count(n)}" for code, n in value.items())


def inventory_row(row: Mapping[str, Any], url: str | None) -> dict[str, Any]:
    median = row.get("median_sample_size") or {}
    n_analyses = row.get("n_analyses") or {}
    return {
        "store_id": row.get("store_id"),
        "url": url,
        "label": text(row.get("label")),
        "description": text((row.get("description") or "").strip() or None),
        "layout": _cell(row.get("layout"), str),
        "completion_state": _cell(row.get("completion_state"), str),
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


def latest_run(store_id: str, labels: Mapping[str, Any], runs: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    found = _latest(runs, store_id)
    if found is None:
        return None
    run, store = found
    measures = store.get("measures") or {}
    newest = runs[-1]
    return {
        "store_id": store_id, "label": labels.get(store_id), "layout": store["layout"], "coverage": store["coverage"],
        "state": store["status"], "reason": text(store.get("reason")),
        # The newest run left this Store out, or listed it pending: say so above the older run shown.
        "not_in_latest": None if run is newest else f"not in the latest run ({newest['started_utc'][:10]})",
        # The wording the panel shows, written here: the script does not choose it.
        "notice": None if run is newest else (
            f"not in the latest run ({newest['started_utc'][:10]}): this is the latest run that measured it."
            if store["status"] == "measured" else f"not in the latest run ({newest['started_utc'][:10]})."),
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


def _value(name: str, record: Mapping[str, Any]) -> float | None:
    value = record.get(MEASURE[name].key)
    return float(value) if record.get("status") == "measured" and isinstance(value, (int, float)) else None


def _path(name: str, point: tuple) -> Any:
    """`index` or `scan` for a `top_hits` point, else `None`."""
    return ((point[2].get("measures") or {}).get(name) or {}).get("path")


def trend(name: str, runs: list[Mapping[str, Any]], stores: list[str]) -> dict[str, Any] | None:
    """One measure across engine versions, as SVG: a series per Store, one point per engine version it was measured at.

    A version run more than once shows its latest run of that Store. Versions
    are ordered by when they were first run, not by their number.
    """
    points: dict[str, dict[str, tuple[float, Mapping[str, Any], Mapping[str, Any]]]] = {}
    versions: list[str] = []
    for run in runs:
        for store_id in stores:
            store = run["stores"].get(store_id)
            value = _value(name, (store or {}).get("measures", {}).get(name) or {})
            if value is None:
                continue
            if run["engine_version"] not in versions:
                versions.append(run["engine_version"])
            points.setdefault(store_id, {})[run["engine_version"]] = (value, run, store)
    if not points:
        return None
    series = [s for s in stores if s in points]
    unit = MEASURE[name].unit
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
                     f'<text class="tick" x="{left - 5}" y="{y(value) + 3:.1f}" text-anchor="end">{html.escape(MEASURE[name].show(value))}</text>')
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
            title = (f"{store_id} · engine {run['engine_version']} · {MEASURE[name].show(value)} · {run['started_utc'][:10]}"
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
    }


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def stores_view(doc: Document) -> dict[str, Any]:
    """`data/stores.json` from the collected `stores.json`; a source that is not available says why."""
    out = {k: doc.get(k) for k in architecture_public.ENVELOPE}
    out["error"] = text(out["error"])
    if not doc.get("available"):
        return out
    commit = doc.get("commit")
    rows = [r for r in doc.get("inventory") or [] if isinstance(r, Mapping)]
    out["registry"] = {
        "name": paths.REGISTRY, "url": paths.clone_url(paths.REGISTRY), "commit": commit,
        "stores_url": paths.github_url(paths.REGISTRY, commit, "stores/") if commit else None,
    }
    out["ld_stores"] = LD_STORES
    out["inventory"] = [
        inventory_row(r, paths.github_url(paths.REGISTRY, commit, f"stores/{r['store_id']}/") if commit else None) for r in rows
    ]
    return out


def benchmarking_view(doc: Document) -> dict[str, Any]:
    """`data/benchmarking.json`: yardstick's results (the tab's label is Benchmarking; the name stays yardstick).

    The trends come first, then each Store's latest run."""
    out = {k: doc.get(k) for k in architecture_public.ENVELOPE}
    out["error"] = text(out["error"])
    if not doc.get("available"):
        return out
    rows = [r for r in doc.get("inventory") or [] if isinstance(r, Mapping)]
    labels = {r["store_id"]: text(r.get("label")) for r in rows}
    view = yardstick_view(doc.get("yardstick") or {}, labels, [r["store_id"] for r in rows])
    out["yardstick"] = {k: view[k] for k in sorted(view, key=lambda k: k != "trends") if k in view}
    return out
