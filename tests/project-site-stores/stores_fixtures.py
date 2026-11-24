"""A fixture registry (`stores/` and `docs/_yardstick/`) for the Stores view's tests (og-dev-hub#16).

One Store per GWAS layout, in the two shapes the registry has: the Validation
Record before opengwasdb-stores#502 (`OGS-00002`, `OGS-00003`) and after it
(`OGS-00001`); and yardstick results in the old workload (`yardstick-3`) and the
new (`yardstick-4`).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

ANALYSES_HEADER = "analysis_id\tassigned_ancestry\tsample_size\texclude_from_build"
# OGS-00001's Release Manifest: three built rows with a sample size (100, 200, 300), one built row without,
# and one excluded audit row whose 1,000,000 would move the median from 200 to 250.
ANALYSES_DENSE = "\n".join([
    ANALYSES_HEADER,
    "A1\tEUR\t100\t",
    "A2\tEUR\t200\tfalse",
    "A3\tAFR\t300\t",
    "A4\t\t\t",
    "A5\tEAS\t1000000\ttrue",
]) + "\n"


def write_bundle(registry: Path, store_id: str, *, release: dict, build: dict, validation: dict | None, analyses: str | None) -> None:
    root = registry / store_id
    root.mkdir(parents=True)
    (root / "release.yaml").write_text(yaml.safe_dump({"store_id": store_id, **release}))
    (root / "build.yaml").write_text(yaml.safe_dump({"store_id": store_id, **build}))
    if analyses is not None:
        (root / "analyses.tsv").write_text(analyses)
    if validation is not None:
        (root / "validation.yaml").write_text(yaml.safe_dump(validation))


def make_registry(root: Path) -> Path:
    """`root/stores/` with a Dense, a Hybrid and a Ragged Store, and `root/docs/_yardstick/` with three results."""
    stores = root / "stores"
    stores.mkdir(parents=True)
    write_bundle(
        stores, "OGS-00001",
        release={"label": "dense-new", "status": "validated", "association_coverage": "gwas",
                 "description": "Read at /data/opengwasdb/raw/gwas-vcf/ukb-b by the builder."},
        build={"layout": "dense", "completion_state": "reference_completed", "post": {"top_hits": True}},
        validation={"status": "passed", "observed": {
            "n_analyses": 4, "n_variants": 11191070, "store_bytes": 62_100_000_000, "has_hm3": True, "has_rho": False,
            "n_top_hits": {"5e-08": 10, "5e-06": 1200, "5e-04": 34567}}},
        analyses=ANALYSES_DENSE,
    )
    write_bundle(
        stores, "OGS-00002",
        release={"label": "hybrid-old", "status": "built", "association_coverage": "gwas"},
        build={"layout": "hybrid", "completion_state": "reference_completed", "post": {"top_hits": False}},
        validation={"status": "passed", "observed": {"n_analyses": 2, "n_variants": None, "n_associations": None, "store_bytes": None}},
        analyses="analysis_id\tassigned_ancestry\tsample_size\nB1\tEUR\t50\nB2\tEUR\t70\n",
    )
    write_bundle(
        stores, "OGS-00003",
        release={"label": "ragged-old", "status": "validated", "association_coverage": "cis"},
        build={"layout": "ragged", "completion_state": "observed_only", "post": {"top_hits": True}},
        validation={"status": "passed", "observed": {"n_analyses": 3, "n_variants": 8927061}},
        analyses="analysis_id\tsample_size\nC1\t10\nC2\t\nC3\t30\n",
    )
    # A withdrawn Store was built, so its observed facts read as any built Store's; `has_hm3: null` is the schema's
    # "the phase plans it and no record says how it ended".
    write_bundle(
        stores, "OGS-00004",
        release={"label": "hybrid-withdrawn", "status": "withdrawn", "association_coverage": "gwas"},
        build={"layout": "hybrid", "completion_state": "reference_completed", "post": {"top_hits": True}},
        validation={"status": "passed", "observed": {
            "n_variants": 7, "store_bytes": 1, "has_hm3": None, "has_rho": None, "n_top_hits": {"5e-08": None}}},
        analyses="analysis_id\tassigned_ancestry\tsample_size\nD1\tEUR\tunknown\nD2\tEUR\t\n",
    )
    # Not built: a candidate with no Validation Record, and an accepted one whose `observed` is all null.
    write_bundle(
        stores, "OGS-00005",
        release={"label": "candidate-bare", "status": "candidate", "association_coverage": "gwas"},
        build={"layout": "dense", "completion_state": "observed_only", "post": {"top_hits": True}},
        validation=None, analyses="analysis_id\tassigned_ancestry\nE1\tEUR\n",
    )
    write_bundle(
        stores, "OGS-00006",
        release={"label": "accepted-null", "status": "accepted", "association_coverage": "gwas"},
        build={"layout": "dense", "completion_state": "observed_only", "post": {"top_hits": True}},
        validation={"status": None, "observed": {
            "n_variants": None, "store_bytes": None, "has_hm3": None, "has_rho": None, "n_top_hits": None}},
        analyses="analysis_id\tassigned_ancestry\nF1\tEUR\n",
    )
    (stores / "by-label").mkdir()
    (stores / "README.md").write_text("x")
    results = root / "docs" / "_yardstick"
    results.mkdir(parents=True)
    for name, doc in (
        ("20261101T120000Z-0.3.2.json", run("yardstick-3", "0.3.2", "2026-11-01T12:00:00Z", 1.0, [
            store("OGS-00001", "dense", 100.0, bytes_=62_100_000_000, rss=900.0, top_hits="index"),
            store("OGS-00002", "hybrid", 200.0, bytes_=1_000_000_000, rss=300.0)])),
        ("20261105T060000Z-0.3.3.json", run("yardstick-3", "0.3.3", "2026-11-05T06:00:00Z", 1.0, [
            store("OGS-00001", "dense", 110.0, bytes_=62_100_000_000, rss=910.0, top_hits="index"),
            store("OGS-00002", "hybrid", 180.0, bytes_=1_000_000_000, rss=310.0)], veeam=True)),
        ("20261117T113000Z-0.10.0.json", run("yardstick-4", "0.10.0", "2026-11-17T11:30:00Z", 70.0, [
            store("OGS-00001", "dense", 90.0, bytes_=62_100_000_000, rss=950.0, new=True, top_hits="scan"),
            store("OGS-00002", "hybrid", 150.0, bytes_=1_000_000_000, rss=320.0, new=True)], cpus=224)),
    ):
        (results / name).write_text(json.dumps(doc))
    broken = copy.deepcopy(json.loads((results / "20261117T113000Z-0.10.0.json").read_text()))
    broken["schema"] = 99
    (results / "20261118T000000Z-broken.json").write_text(json.dumps(broken))
    return stores


def timed(median: float, *, first: bool = True) -> dict:
    return {"status": "measured", "first_read_ms": median * 2, "median_ms": median, "p95_ms": median * 1.2, "reps": 5,
            "result_count": 10, **({"first_result_count": 10} if first else {})}


def store(store_id: str, layout: str, median: float, *, bytes_: int, rss: float, new: bool = False,
          top_hits: str | None = None) -> dict:
    measures = {
        "open": {"status": "measured", "first_read_ms": 1.0, "median_ms": median / 10, "p95_ms": median / 8, "reps": 5},
        "phewas_rsid": timed(median),
        "bytes_on_disk": {"status": "measured", "bytes": bytes_, "source": "walk"},
        "peak_rss": {"status": "measured", "baseline_mb": 100.0, "peak_mb": rss, "delta_mb": rss - 100, "result_count": 5},
    }
    if new:
        measures["lookup_100x100"] = timed(median * 3)
        measures["range_by_analysis"] = ({"status": "not_applicable", "reason": "the cis query is Ragged only"}
                                         if layout != "ragged" else timed(median))
        measures["region_100kb"] = {"status": "unavailable", "error": "region failed reading /data/opengwasdb/stores/OGS-00001/store"}
        measures["rho"] = {"status": "not_applicable", "reason": "no Rho Matrix"}
    if top_hits:
        measures["top_hits"] = timed(median / 2) | {"path": top_hits}
    return {"store_id": store_id, "layout": layout, "coverage": "gwas", "status": "measured", "measures": measures}


def run(workload: str, version: str, started: str, load: float, stores: list[dict], *, veeam: bool = False, cpus: int = 16) -> dict:
    return {
        "schema": 1, "workload_id": workload, "workload_sha256": "0" * 64,
        "opengwasdb": {"version": version, "revision": "a" * 40},
        "ogstores": {"version": "0.37.2", "commit": "b" * 40, "dirty": False},
        "host": {"name": "host", "cpu_count": cpus},
        "load_average": {"before": [load, load, load], "after": [load, load, load]},
        "started_utc": started, "ended_utc": started, "duration_s": 60.0, "local_utc_offset_minutes": 0,
        "veeam_window": veeam, "repetitions": {"default": 5}, "stores": stores,
    }
