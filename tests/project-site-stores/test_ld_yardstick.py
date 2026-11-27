#!/usr/bin/env python3
"""The LD yardstick results: collected, drawn, linked from the tiles (og-dev-hub#10 round 2, opengwasdb-stores#504).

Run from the repository root:
    python3 tests/project-site-stores/test_ld_yardstick.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import stores_fixtures as fx
from yardstick import result as yardstick_result

from project_site import stores_view
from project_site.collect import common, stores


def collected(registry: Path) -> dict:
    return common.envelope("stores", available=True, error=None, **stores.collect(registry, commit="c" * 40))


class Fixture(unittest.TestCase):
    ld_run = True

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="ld-yardstick-"))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.registry = fx.make_registry(cls.root, ld_run=cls.ld_run)
        cls.doc = collected(cls.registry)
        cls.view = stores_view.benchmarking_view(cls.doc)["yardstick"]
        cls.stores = stores_view.stores_view(cls.doc)


class CollectedLdRuns(Fixture):
    def test_the_fixture_is_a_valid_result(self) -> None:
        yardstick_result.validate(fx.ld_run_result())

    def test_a_run_with_an_ld_section_keeps_each_stores_measures_and_the_readers_version_and_no_location(self) -> None:
        run = [r for r in self.doc["yardstick"]["runs"] if r["ld"]][0]
        self.assertEqual(run["ld"]["ogquery_version"], "0.5.0")
        self.assertEqual(sorted(run["ld"]["stores"]), ["OGL-00006", "OGL-00007"])
        ld6 = run["ld"]["stores"]["OGL-00006"]
        self.assertEqual((ld6["kind"], ld6["label"]), ("ld_store", "hgdp1kgp-v2-EUR-k10 (Partner Rows)"))
        self.assertEqual(ld6["measures"]["region_3mb"]["median_ms"], 594.934)
        self.assertEqual(ld6["measures"]["bytes_on_disk"]["store_bytes"], 478327170)
        self.assertEqual(run["ld"]["stores"]["OGL-00007"]["measures"]["bytes_on_disk"]["genotype_bytes"], 4139037382)
        self.assertNotIn("/data/", json.dumps(run["ld"]))
        self.assertNotIn("location", json.dumps(run["ld"]))

    def test_every_run_before_504_has_no_ld_section_and_that_is_not_zero(self) -> None:
        runs = self.doc["yardstick"]["runs"]
        self.assertEqual([r["ld"] for r in runs[:-1]], [None, None, None])


class DrawnLdYardstick(Fixture):
    def test_both_stores_are_drawn_with_their_measures_and_one_not_applicable_with_its_reason(self) -> None:
        ld = self.view["ld"]
        self.assertTrue(ld["available"])
        self.assertEqual([s["store_id"] for s in ld["stores"]], ["OGL-00006", "OGL-00007"])
        by = {s["store_id"]: s for s in ld["stores"]}
        rows = {m["name"]: m for m in by["OGL-00006"]["measures"]}
        self.assertEqual(list(rows), list(yardstick_result.LD_TIMED))
        self.assertEqual((rows["region_3mb"]["median"], rows["region_3mb"]["p95"]), ("594.9 ms", "642.3 ms"))
        self.assertEqual((rows["proxies_100"]["state"], rows["proxies_100"]["note"]),
                         ("not_applicable", "this run did not exercise the 100-proxy query"))
        self.assertEqual(by["OGL-00006"]["peak_memory"]["display"], "1,146 MB")
        self.assertEqual(by["OGL-00006"]["versions"], "engine 0.27.0 · ogquery 0.5.0")
        self.assertEqual(by["OGL-00007"]["peak_memory"]["display"], "unavailable: the worker was killed reading …/81-eur")
        self.assertEqual(by["OGL-00007"]["kind"], "Genotype Store")
        self.assertEqual(by["OGL-00007"]["measures"][-1]["median"], "14.53 s")

    def test_size_is_labelled_as_files_read_and_the_stores_own_files_are_stated_apart(self) -> None:
        by = {s["store_id"]: s for s in self.view["ld"]["stores"]}
        self.assertEqual(by["OGL-00006"]["size_on_disk"]["display"], "85.0 GB")
        self.assertEqual(by["OGL-00006"]["size_on_disk"]["details"], ["files read, links followed", "the Store's own files: 478.3 MB"])
        self.assertEqual(by["OGL-00007"]["size_on_disk"]["details"][1], "the Store's own files: 1.5 GB, and 4.1 GB of genotype files")

    def test_ld_trends_are_their_own_and_keyed_by_ld_id(self) -> None:
        trends = self.view["ld"]["trends"]
        self.assertEqual([t["measure"] for t in trends], [*yardstick_result.LD_TIMED, "peak_rss", "bytes_on_disk"])
        self.assertEqual([x["store_id"] for x in trends[0]["series"]], ["OGL-00006", "OGL-00007"])
        self.assertNotIn("OGS-", trends[0]["svg"])
        self.assertEqual([t["measure"] for t in self.view["trends"] if t["measure"] == "clump"], [])

    def test_the_gwas_measures_and_unmeasured_list_hold_no_ld_id_or_measure(self) -> None:
        self.assertFalse(set(stores_view.MEASURES) & {"matrix_10", "matrix_500", "region_1mb", "region_3mb", "proxies_1", "proxies_10", "proxies_100", "clump"})
        self.assertFalse([u for u in self.view["unmeasured"] if u["store_id"].startswith("OGL-")])
        self.assertFalse([s for s in self.view["stores"] if s["store_id"].startswith("OGL-")])

    def test_a_measured_stores_tile_links_to_its_benchmarking_row_and_an_unmeasured_one_does_not(self) -> None:
        tiles = {t["store_id"]: t for t in self.stores["ld_resources"]["rows"]}
        self.assertEqual(tiles["OGL-00006"]["benchmark"], {"href": "#ld-bench-OGL-00006", "text": "LD yardstick results"})
        self.assertEqual(tiles["OGL-00007"]["benchmark"]["href"], "#ld-bench-OGL-00007")
        self.assertIsNone(tiles["OGL-00001"]["benchmark"])

    def test_the_not_measured_yet_gap_is_gone_once_a_result_has_an_ld_section(self) -> None:
        self.assertIsNone(self.stores["ld_resources"]["benchmarking"])


class NoLdRun(Fixture):
    ld_run = False

    def test_a_result_without_an_ld_section_is_not_measured_in_this_run(self) -> None:
        ld = self.view["ld"]
        self.assertFalse(ld["available"])
        self.assertEqual(ld["stores"], [])
        self.assertIn("LD not measured in this run (2026-11-17)", ld["gap"])
        self.assertIn("not measured yet", ld["gap"])

    def test_the_stores_page_says_not_measured_yet_without_naming_504_as_unbuilt(self) -> None:
        gap = self.stores["ld_resources"]["benchmarking"]
        self.assertTrue(gap.startswith("LD Stores are not measured yet"))
        self.assertNotIn("504", gap)
        for tile in self.stores["ld_resources"]["rows"]:
            self.assertIsNone(tile["benchmark"])


class NewestRunWithoutLd(Fixture):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        results = cls.root / "docs" / "_yardstick"
        partial = fx.run("yardstick-7", "0.27.1", "2026-11-28T00:00:00Z", 1.0, [])
        partial["ld"] = fx.ld_run_result()["ld"]
        partial["ld"]["stores"] = partial["ld"]["stores"][1:]
        yardstick_result.validate(partial)
        (results / "20261128T000000Z-0.27.1.json").write_text(json.dumps(partial))
        later = fx.run("yardstick-7", "0.27.2", "2026-11-29T00:00:00Z", 1.0, [])
        (results / "20261129T000000Z-0.27.2.json").write_text(json.dumps(later))
        cls.doc = collected(cls.registry)
        cls.view = stores_view.benchmarking_view(cls.doc)["yardstick"]

    def test_each_row_names_its_own_run_when_the_newest_result_did_not_measure_ld(self) -> None:
        ld = self.view["ld"]
        self.assertTrue(ld["available"])
        self.assertEqual(ld["notice"], "LD not measured in this run (2026-11-29): each row is from the latest run that measured that Store, dated in its Run column.")
        self.assertEqual([(s["store_id"], s["run"], s["notice"]) for s in ld["stores"]], [
            ("OGL-00006", "2026-11-27 · yardstick-6", "not in the latest run (2026-11-29): this is the latest run that measured it."),
            ("OGL-00007", "2026-11-28 · yardstick-7", "not in the latest run (2026-11-29): this is the latest run that measured it.")])


class HostPathsInAResult(unittest.TestCase):
    """Inspect the allowed fields at the collection boundary, before the site is built."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="ld-hostile-"))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.registry = fx.make_registry(cls.root, ld_run=True)
        path = cls.root / "docs" / "_yardstick" / "20261127T121611Z-0.27.0.json"
        result = fx.ld_run_result_with_host_paths()
        yardstick_result.validate(result)
        path.write_text(json.dumps(result))
        cls.run_with_ld = next(r for r in collected(cls.registry)["yardstick"]["runs"] if r["ld"])

    def test_ld_measure_keeps_only_display_keys(self) -> None:
        measures = self.run_with_ld["ld"]["stores"]["OGL-00006"]["measures"]
        self.assertEqual(set(measures["region_1mb"]), {"status", "median_ms", "p95_ms"})
        self.assertEqual(set(measures["bytes_on_disk"]), {"status", "bytes", "store_bytes"})

    def test_label_versions_and_reasons_are_scrubbed_at_collection(self) -> None:
        run = self.run_with_ld
        ld6, ld7 = (run["ld"]["stores"][i] for i in ("OGL-00006", "OGL-00007"))
        self.assertEqual(run["engine_version"], "0.27.0+…/engine")
        self.assertEqual(run["ld"]["ogquery_version"], "0.5.0 at …/ogquery")
        self.assertEqual(ld6["label"], "…/EUR …/foo")
        self.assertEqual(ld6["measures"]["proxies_100"]["reason"], "read …/x failed; see …/bar; receipt:…/trace.txt")
        self.assertEqual(ld7["measures"]["clump"]["error"], "…/input: read failed; retry: see:…/secret")
        self.assertEqual(ld7["measures"]["peak_rss"]["error"], "worker stopped; input: …/81-eur")


class TheGapIsDecidedFromTheResultsAlone(Fixture):
    def view_of(self, doc: dict) -> dict:
        return stores_view.stores_view(doc)["ld_resources"]

    def test_an_unreadable_inventory_does_not_make_the_results_not_measured(self) -> None:
        doc = {**self.doc, "ld_resources": {"available": False, "error": "the registry could not be listed", "rows": []}}
        section = self.view_of(doc)
        self.assertFalse(section["available"])
        self.assertIsNone(section["benchmarking"])

    def test_a_result_with_an_ld_section_and_no_stores_measured_no_ld_stores(self) -> None:
        doc = json.loads(json.dumps(self.doc))
        for run in doc["yardstick"]["runs"]:
            if run["ld"]:
                run["ld"]["stores"] = {}
        self.assertIsNone(self.view_of(doc)["benchmarking"])
        ld = stores_view.benchmarking_view(doc)["yardstick"]["ld"]
        self.assertTrue(ld["available"])
        self.assertEqual(ld["stores"], [])
        self.assertEqual(ld["notice"], "The latest run with an LD section (2026-11-27) measured no LD Stores.")

    def test_an_empty_latest_ld_run_is_reported_even_when_older_rows_are_shown(self) -> None:
        empty = fx.run("yardstick-7", "0.27.1", "2026-11-28T00:00:00Z", 1.0, [])
        empty["ld"] = {**fx.ld_run_result()["ld"], "stores": []}
        yardstick_result.validate(empty)
        root = Path(tempfile.mkdtemp(prefix="ld-empty-"))
        self.addCleanup(shutil.rmtree, root, True)
        registry = fx.make_registry(root, ld_run=True)
        (root / "docs" / "_yardstick" / "20261128T000000Z-0.27.1.json").write_text(json.dumps(empty))
        doc = collected(registry)
        self.assertIsNone(self.view_of(doc)["benchmarking"])
        ld = stores_view.benchmarking_view(doc)["yardstick"]["ld"]
        self.assertEqual(ld["notice"], "The latest run with an LD section (2026-11-28) measured no LD Stores.")
        self.assertEqual([row["run"] for row in ld["stores"]], ["2026-11-27 · yardstick-6"] * 2)

    def test_no_result_with_a_section_is_the_gap_whatever_the_inventory(self) -> None:
        doc = json.loads(json.dumps(self.doc))
        for run in doc["yardstick"]["runs"]:
            run["ld"] = None
        self.assertEqual(self.view_of(doc)["benchmarking"], stores_view.LD_BENCHMARKING_GAP)
        doc["ld_resources"] = {"available": False, "error": "x", "rows": []}
        self.assertEqual(self.view_of(doc)["benchmarking"], stores_view.LD_BENCHMARKING_GAP)


class LdRowFields(Fixture):
    def test_an_ld_row_has_the_run_display_but_no_unused_metadata_or_pending_text(self) -> None:
        for row in self.view["ld"]["stores"]:
            self.assertEqual(row["run"], "2026-11-27 · yardstick-6")
            self.assertIsNone(row["notice"])
            self.assertFalse({"date", "workload_id", "state", "reason", "pending"} & row.keys())


if __name__ == "__main__":
    unittest.main()
