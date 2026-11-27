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
        validation={"status": "passed", "validated_at": "2026-11-13T09:30:00Z", "build_environment": {"opengwasdb_version": "0.9.1"},
                    "observed": {
            "format_version": "1.2", "n_analyses": 4, "n_variants": 11191070, "store_bytes": 62_100_000_000, "has_hm3": True, "has_rho": False,
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
    # Withdrawn before any build record: it will never be built. And a built Store whose every row is excluded.
    write_bundle(
        stores, "OGS-00007",
        release={"label": "withdrawn-bare", "status": "withdrawn", "association_coverage": "gwas"},
        build={"layout": "dense", "completion_state": "observed_only"}, validation=None,
        analyses="analysis_id\tassigned_ancestry\nG1\tEUR\n",
    )
    write_bundle(
        stores, "OGS-00008",
        release={"label": "all-excluded", "status": "built", "association_coverage": "gwas"},
        build={"layout": "dense", "completion_state": "observed_only"},
        validation={"status": "passed", "observed": {"has_rho": None}},
        analyses="analysis_id\tassigned_ancestry\tsample_size\texclude_from_build\nH1\tEUR\t5\ttrue\n",
    )
    make_ld_registry(root)
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


# ---------------------------------------------------------------------------
# The LD Store Registry (og-dev-hub#10): `stores/ld/OGL-NNNNN/record.yaml` and the LD panels' `resource.yaml`.
# Each record is shaped as the real ones at opengwasdb-stores 75fe637a are (docs/spec/ld-store-registry.md); each
# `location` is a host path, which the site must never carry.
# ---------------------------------------------------------------------------

LD_HOST_PATH = "/data/opengwasdb/work/ogld/stores"


def ld_record(ld_id: str, kind: str, status: str, **fields) -> dict:
    """A valid record. `fields` replace top-level keys; `provenance` and `measured` replace their own keys."""
    provenance = {
        "source_kind": "genotypes", "source_description": "HGDP+1kGP phased v2 (Koenig et al. 2024), EUR, converted by build-inputs §3",
        "source_panel": "hgdp1kgp-v2-EUR", "ancestry": "EUR", "n": 665, "k": 10, "reference_assembly": "GRCh38",
        "format_version": "0.1.0", "r_scale": 511, "near_bp": 3000000, "far_bp": 10000000, "t_far": 0.0318,
        "n_variants": 8586889, "software": {"ogld": "0.5.0"}, "created_at": "2026-11-21T20:42:19Z", "wall_seconds": 838.3,
        **fields.pop("provenance", {}),
    }
    measured = {"store_bytes": 79_278_843_340, **fields.pop("measured", {})}
    return {
        "ld_id": ld_id, "kind": kind, "label": f"hgdp1kgp-v2-EUR-k10-{ld_id[-2:]}", "status": status, "licence": "to confirm",
        "used_for": "Data API LD: matrix, region, proxies, clump", "issue": "ogld#7",
        "rebuild": {"repository": "opengwas/ogld", "version": "0.5.0", "script": "ogld build",
                    "commands": [f"pixi run -e dev ogld build {LD_HOST_PATH}/{ld_id}.store"]},
        "location": f"{LD_HOST_PATH}/{ld_id}.store", "provenance": provenance, "provenance_sha256": "a" * 64,
        "measured": measured, **fields,
    }


LD_PANEL = {
    "resource_id": "fixture-ld-panel", "label": "A fixture LD reference panel", "kind": "ld_panel", "ancestry": ["AMR"],
    "genome_build": "GRCh38", "location": "/data/opengwasdb/reference/fixture/panel",
    "ld": {"representation": "eigendecomposition", "n_blocks": {"AMR": 1357}, "bytes": {"AMR": 21_012_529_996}},
    "source": {"cohort": "gnomAD v3.1.2 HGDP+1kGP, AMR samples only", "n_individuals": {"AMR": 345}},
    "ld_ids": {"AMR": "OGL-00005"}, "used_for": "reference completion (opengwasdb complete-dense)", "licence": "to confirm",
    "status": "available", "notes": "Built from /data/opengwasdb/reference/fixture/runs/receipt.json.",
}


def make_ld_registry(root: Path) -> None:
    """Five rows: an LD Store served, a Genotype Store built, an LD Store retired, one kept as `reference`, and an LD panel
    (whose `n_variants` its declaration does not hold, so that cell is empty)."""
    records = [
        ld_record("OGL-00001", "ld_store", "served", default=True, notes="served by ogdb-api; stays as the reference"),
        ld_record("OGL-00002", "genotype_store", "built", measured={"genotype_bytes": 4_139_037_382},
                  provenance={"n_variants": 8586889},
                  rebuild={"repository": "opengwas/ogld", "version": "0.5.0", "script": "ogld build --genotypes",
                           "commands": [f"pixi run -e dev ogld build {LD_HOST_PATH}/x.store --genotypes"]}),
        ld_record("OGL-00003", "ld_store", "retired", provenance={"ancestry": "AFR", "n": 608},
                  notes="retired 2026-11-27: its files are deleted"),
        ld_record("OGL-00004", "ld_store", "reference", provenance={"ancestry": "AMR", "n": 345}),
    ]
    for record in records:
        directory = root / "stores" / "ld" / record["ld_id"]
        directory.mkdir(parents=True)
        (directory / "record.yaml").write_text(yaml.safe_dump(record, sort_keys=False))
    panel = root / "resources" / "reference-resources" / LD_PANEL["resource_id"]
    panel.mkdir(parents=True)
    (panel / "resource.yaml").write_text(yaml.safe_dump(LD_PANEL, sort_keys=False))
