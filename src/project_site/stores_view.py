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

Document = Mapping[str, Any]

# A run is taken "under load" when any load average it recorded, before or after, is over this share of its CPUs.
LOAD_SHARE = 0.25
LOAD_RULE = "a load average (1, 5 or 15 minutes, before or after the run) over a quarter of the host's CPUs"
VEEAM_RULE = "the run overlapped the nightly Veeam backup window that throttled disk I/O until 2026-11-02"

# Every measure the schema knows, in the order the page draws them, then the two that are not timed.
TIMED = tuple(yardstick_result.TIMED)
MEASURES = (*TIMED, "peak_rss", "bytes_on_disk")
UNITS = {"peak_rss": "MB", "bytes_on_disk": "bytes"}

CHART_COLUMNS = 6  # series classes `series-0` to `series-5`


def text(value: Any) -> Any:
    return architecture_public.reason(value)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


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
    field = field if isinstance(field, Mapping) else {}
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
            detail=f"over the {count(median.get('with_sample_size', 0))} of {count(median.get('of', 0))} built rows that have one"),
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


def _measure(name: str, record: Mapping[str, Any]) -> dict[str, Any]:
    state = record.get("status")
    out: dict[str, Any] = {"name": name, "state": state, "median": None, "p95": None, "note": None}
    if state == "not_applicable":
        out["note"] = text(record.get("reason"))
    elif state == "unavailable":
        out["note"] = text(record.get("error"))
    elif state == "measured":
        out["median"], out["p95"] = duration(record["median_ms"]), duration(record["p95_ms"])
    return out


def _fact(record: Mapping[str, Any] | None, show) -> dict[str, Any]:
    """Peak memory or size on disk: its figure, or its state with why (a Store without the record says so)."""
    if record is None:
        return {"state": "absent", "text": None, "note": "this run did not measure it"}
    state = record.get("status")
    if state == "measured":
        return {"state": state, "text": show(record), "note": None}
    return {"state": state, "text": None, "note": text(record.get("reason") if state == "not_applicable" else record.get("error"))}


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
    return {
        "store_id": store_id, "label": labels.get(store_id), "layout": store["layout"], "coverage": store["coverage"],
        "state": store["status"], "reason": text(store.get("reason")),
        "engine_version": run["engine_version"], "date": run["started_utc"][:10], "workload_id": run["workload_id"],
        "flags": run_flags(run),
        "peak_memory": _fact(measures.get("peak_rss"), lambda r: megabytes(r["peak_mb"])),
        "size_on_disk": _fact(measures.get("bytes_on_disk"), lambda r: size(r["bytes"])),
        "measures": [_measure(name, measures[name]) for name in MEASURES if name in measures
                     and name not in ("peak_rss", "bytes_on_disk")],
    }


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def _value(name: str, record: Mapping[str, Any]) -> float | None:
    if record.get("status") != "measured":
        return None
    key = {"peak_rss": "peak_mb", "bytes_on_disk": "bytes"}.get(name, "median_ms")
    value = record.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _label(name: str, value: float) -> str:
    if name == "bytes_on_disk":
        return size(value)
    return megabytes(value) if name == "peak_rss" else duration(value)


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
    unit = UNITS.get(name, "ms")
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
                     f'<text class="tick" x="{left - 5}" y="{y(value) + 3:.1f}" text-anchor="end">{html.escape(_label(name, value))}</text>')
    for index, version in enumerate(versions):
        parts.append(f'<text class="tick" x="{x(index):.1f}" y="{height - bottom + 14}" text-anchor="end" '
                     f'transform="rotate(-40 {x(index):.1f} {height - bottom + 14})">{html.escape(version)}</text>')
    flagged = 0
    for number, store_id in enumerate(series):
        cls = f"series-{number % CHART_COLUMNS}"
        mine = sorted(((versions.index(v), pt) for v, pt in points[store_id].items()), key=lambda item: item[0])
        if len(mine) > 1:
            path = " ".join(f"{x(i):.1f},{y(pt[0]):.1f}" for i, pt in mine)
            parts.append(f'<polyline class="line {cls}" points="{path}"/>')
        for i, (value, run, store) in mine:
            flags = run_flags(run)
            title = (f"{store_id} · engine {run['engine_version']} · {_label(name, value)} · {run['started_utc'][:10]}"
                     f" · {run['workload_id']}" + "".join(f" · {f}" for f in flags))
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
    out["inventory"] = [
        inventory_row(r, paths.github_url(paths.REGISTRY, commit, f"stores/{r['store_id']}/") if commit else None) for r in rows
    ]
    labels = {r["store_id"]: text(r.get("label")) for r in rows}
    out["yardstick"] = yardstick_view(doc.get("yardstick") or {}, labels, [r["store_id"] for r in rows])
    return out
