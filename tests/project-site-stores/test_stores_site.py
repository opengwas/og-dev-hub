#!/usr/bin/env python3
"""A built `_site/` carries the Stores view: its data file, its script in `node`, and no host path (og-dev-hub#16).

Run from the repository root:
    python3 tests/project-site-stores/test_stores_site.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import stores_fixtures as fx

from project_site import site
from project_site.collect import common, stores

RUNNER = Path(__file__).resolve().parents[1] / "project-site-architecture" / "view_runner.js"
# Absolute /data paths and file URLs. Not a repository's relative `resources/data/`.
HOST_PATH_BYTES = re.compile(rb"(?<![\w.~-])/data/|file://", re.IGNORECASE)


def build(cleanup, *, stores_doc: dict | None, ld_run: bool = False, ld_result: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="stores-site-"))
    cleanup(shutil.rmtree, root, True)
    registry = fx.make_registry(root / "registry", ld_run=ld_run or ld_result is not None)
    if ld_result is not None:
        (registry.parent / "docs" / "_yardstick" / "20261127T121611Z-0.27.0.json").write_text(json.dumps(ld_result))
    data = root / "data"
    unavailable = {"source": "architecture", "available": False, "collected_at": None, "error": "not collected here"}
    common.write_source(data, unavailable)
    if stores_doc is None:
        stores_doc = common.envelope("stores", available=True, error=None, **stores.collect(registry, commit="c" * 40))
    common.write_source(data, stores_doc)
    (root / "CONTEXT.md").write_text("# OpenGWAS\n", encoding="utf-8")
    site.build(data, root / "_site", context=root / "CONTEXT.md")
    return root / "_site"


class BuiltStoresView(unittest.TestCase):
    """Seam 6: `data/stores.json` is in the site, and no host path is anywhere under `_site/`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.out = build(cls.addClassCleanup, stores_doc=None)

    def test_the_site_holds_data_stores_json(self) -> None:
        data = json.loads((self.out / "data" / "stores.json").read_text(encoding="utf-8"))
        self.assertTrue(data["available"])
        self.assertEqual([r["store_id"] for r in data["inventory"]], [f"OGS-0000{n}" for n in range(1, 9)])
        self.assertEqual(data["registry"]["stores_url"],
                         "https://github.com/opengwas/opengwasdb-stores/tree/" + "c" * 40 + "/stores/")
        self.assertEqual(data["inventory"][0]["url"],
                         "https://github.com/opengwas/opengwasdb-stores/tree/" + "c" * 40 + "/stores/OGS-00001/")

    def test_no_host_path_is_under_the_built_site(self) -> None:
        files = [p for p in self.out.rglob("*") if p.is_file()]
        self.assertTrue(files)
        for path in files:
            raw = path.read_bytes()
            with self.subTest(path=str(path.relative_to(self.out))):
                self.assertIsNone(HOST_PATH_BYTES.search(raw))
                self.assertNotIn(b"/data/opengwasdb", raw)

    def test_the_built_site_lists_every_ld_row_and_carries_no_location(self) -> None:
        data = json.loads((self.out / "data" / "stores.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["ld_resources"]["rows"]), 5)
        self.assertEqual(data["counts"]["ld_resources"]["n"], 5)
        self.assertNotIn("location", json.dumps(data))
        self.assertNotIn(fx.LD_HOST_PATH.encode(), b"".join(p.read_bytes() for p in self.out.rglob("*") if p.is_file()))

    def test_the_page_names_the_script_and_the_content_section(self) -> None:
        page = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="js/stores.js"', page)
        self.assertIn('id="stores-content"', page)

    def test_the_trend_charts_are_in_the_data_as_svg_and_the_site_has_no_chart_library(self) -> None:
        data = json.loads((self.out / "data" / "benchmarking.json").read_text(encoding="utf-8"))
        self.assertTrue(all(t["svg"].startswith("<svg ") for t in data["yardstick"]["trends"]))
        self.assertEqual(sorted(p.name for p in (self.out / "js").iterdir()),
                         ["app.js", "architecture.js", "benchmarking.js", "context.js", "decisions.js", "stores.js"])


class StoresScript(unittest.TestCase):
    """`stores.js` draws the data it is given in `node`, and draws a source that was not collected as a notice."""

    def drawn(self, out: Path, view: str = "stores") -> str:
        done = subprocess.run(["node", str(RUNNER), str(out)], capture_output=True, text=True, check=True, timeout=60)
        return json.loads(done.stdout)[view]

    def test_the_inventory_gaps_and_yardstick_are_drawn(self) -> None:
        text = self.drawn(build(self.addCleanup, stores_doc=None))
        self.assertNotIn("could not be drawn", text)
        for expected in ("OGS-00001", "dense-new", "62.1 GB", "AFR 1 · EUR 2 · unassigned 1",
                         "recorded from opengwasdb-stores#502's backfill", "counts come with opengwasdb#488",
                         "not computed",
                         "not built yet (Release Status candidate)", "withdrawn",
                         "no record says how the HM3 step ended"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_one_tile_per_store_is_drawn_and_the_table_is_gone(self) -> None:
        text = self.drawn(build(self.addCleanup, stores_doc=None))
        self.assertEqual(text.count("Layout "), 8)  # one tile each; the runner gives the drawn text
        self.assertIn("Why n/a", text)
        self.assertIn("Size on disk n/a", text)
        self.assertNotIn("Inventory", text)
        self.assertNotIn("LD Stores are not listed yet", text)

    def test_each_tile_is_a_details_whose_summary_holds_the_facts_and_escape_closes_it(self) -> None:
        out = build(self.addCleanup, stores_doc=None)
        done = subprocess.run(["node", str(RUNNER), str(out)], capture_output=True, text=True, check=True, timeout=60)
        drawn = json.loads(done.stdout)
        gwas = [t for t in drawn["_tiles"] if t["id"].startswith("store-")]
        self.assertEqual(len(gwas), 8)
        for tile in gwas:
            with self.subTest(tile=tile["id"]):
                self.assertTrue(tile["summary"])
                for label in ("Layout", "Size on disk", "Top hits", "Rho"):
                    self.assertIn(label, tile["summaryText"])
                for label in ("Completion", "Format", "Built with", "Last built"):
                    self.assertIn(label, tile["summaryText"])
                self.assertFalse(tile["linkInSummary"])
                self.assertTrue(tile["linkInBody"])
        by_id = {t["id"]: t["summaryText"] for t in gwas}
        self.assertRegex(by_id["store-OGS-00001"], r"Completion\s*reference completed")
        self.assertRegex(by_id["store-OGS-00001"], r"Built with\s*opengwasdb 0\.9\.1")
        self.assertRegex(by_id["store-OGS-00001"], r"Last built\s*2026-11-13")
        self.assertRegex(by_id["store-OGS-00001"], r"Format\s*1\.2")
        self.assertRegex(by_id["store-OGS-00003"], r"Completion\s*observed only")
        tags = {t["id"]: t["tagClass"] for t in gwas}
        self.assertEqual(tags["store-OGS-00001"], "tag tag-ok")        # validated
        self.assertEqual(tags["store-OGS-00005"], "tag")               # candidate
        self.assertEqual(tags["store-OGS-00007"], "tag tag-muted")     # withdrawn
        self.assertEqual(drawn["_escape"], {"before": 2, "after": 0})  # every open tile, focus or none
        self.assertTrue(drawn["_otherKey"])                            # another key closes nothing

    def test_ld_resources_are_drawn_as_tiles_with_the_separate_counts(self) -> None:
        out = build(self.addCleanup, stores_doc=None)
        drawn = json.loads(subprocess.run(["node", str(RUNNER), str(out)], capture_output=True, text=True, check=True, timeout=60).stdout)
        text = drawn["stores"]
        self.assertIn("8 GWAS Stores", text)
        self.assertIn("5 LD resources: 3 LD Stores, 1 Genotype Store, 1 LD panel", text)
        self.assertIn("LD Stores are not measured yet: no committed yardstick result has an LD section.", text)
        ld = {t["id"]: t for t in drawn["_tiles"] if t["id"].startswith("ld-")}
        self.assertEqual(sorted(ld), [f"ld-OGL-0000{n}" for n in range(1, 6)])
        for tile in ld.values():
            with self.subTest(tile=tile["id"]):
                self.assertTrue(tile["summary"])
                for label in ("Kind", "Provenance", "Source Panel", "Reference Assembly", "Size on disk", "Variants", "Built with"):
                    self.assertIn(label, tile["summaryText"])
                for label in ("Top hits", "HM3", "Rho", "Layout"):
                    self.assertNotIn(label, tile["summaryText"])
                self.assertFalse(tile["linkInSummary"])
                self.assertTrue(tile["linkInBody"])
        self.assertRegex(ld["ld-OGL-00002"]["summaryText"], r"Kind\s*Genotype Store")
        self.assertRegex(ld["ld-OGL-00002"]["summaryText"], r"Size on disk\s*79\.3 GB · genotypes 4\.1 GB")
        self.assertRegex(ld["ld-OGL-00005"]["summaryText"], r"Variants\s*n/a")
        self.assertRegex(ld["ld-OGL-00005"]["summaryText"], r"Blocks\s*1,357")
        self.assertNotIn("Blocks", ld["ld-OGL-00001"]["summaryText"])
        self.assertEqual({k: v["tagClass"] for k, v in ld.items()}["ld-OGL-00003"], "tag tag-muted")  # retired

    def test_the_benchmarking_tab_is_drawn_with_its_line_and_the_runs(self) -> None:
        self.out_page = build(self.addCleanup, stores_doc=None)
        text = self.drawn(self.out_page, "benchmarking")
        self.assertNotIn("could not be drawn", text)
        for expected in ("20261118T000000Z-broken.json is not a valid result", "Not measured by yardstick",
                         "taken under load: load average 70 over 56", "answered by its scan", "not applicable", "unavailable"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertLess(text.index("Trends across engine versions"), text.index("OGS-00001"))
        page = (self.out_page / "index.html").read_text(encoding="utf-8")
        pane = page[page.index('id="pane-benchmarking"'):]
        self.assertIn("One fixed query workload (the yardstick), run at the finish of every epic that changes the engine.", pane)
        self.assertNotIn("benchmark ", text.lower().replace("benchmarking", ""))

    def test_a_store_source_that_was_not_collected_is_a_notice_and_nothing_throws(self) -> None:
        doc = {"source": "stores", "available": False, "collected_at": None, "error": "CollectError: registry is not a directory"}
        text = self.drawn(build(self.addCleanup, stores_doc=doc))
        self.assertNotIn("could not be drawn", text)
        self.assertIn("The Stores could not be collected", text)
        self.assertIn("could not be collected", self.drawn(build(self.addCleanup, stores_doc=doc), "benchmarking"))


class LdYardstickSite(unittest.TestCase):
    """The LD yardstick in a built site: the Benchmarking tab's LD table in `node`, the tiles' links to its rows, no host path."""

    def drawn(self, out: Path) -> dict:
        return json.loads(subprocess.run(["node", str(RUNNER), str(out)], capture_output=True, text=True, check=True, timeout=60).stdout)

    def test_the_ld_table_is_drawn_with_a_row_anchor_for_each_store_and_the_tiles_link_to_them(self) -> None:
        out = build(self.addCleanup, stores_doc=None, ld_run=True)
        drawn = self.drawn(out)
        text = drawn["benchmarking"]
        self.assertNotIn("could not be drawn", text)
        for expected in ("LD Stores", "OGL-00006", "OGL-00007", "Genotype Store", "engine 0.27.0 · ogquery 0.5.0", "unavailable: the worker was killed reading …/81-eur", "594.9 ms", "files read, links followed",
                         "the Store's own files: 478.3 MB", "the Store has no Partner Rows", "not applicable", "LD trends across engine versions"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertLessEqual({"ld-bench-OGL-00006", "ld-bench-OGL-00007"}, set(drawn["_ids"]))
        self.assertLessEqual({"#ld-bench-OGL-00006", "#ld-bench-OGL-00007"}, set(drawn["_links"]))
        self.assertNotIn("LD Stores are not measured yet", drawn["stores"])
        for path in out.rglob("*"):
            if path.is_file():
                with self.subTest(path=str(path.relative_to(out))):
                    self.assertIsNone(HOST_PATH_BYTES.search(path.read_bytes()))

    def test_a_result_with_host_paths_keeps_them_out_of_the_site_and_trend_tooltips(self) -> None:
        out = build(self.addCleanup, stores_doc=None, ld_result=fx.ld_run_result_with_host_paths())
        for path in out.rglob("*"):
            if path.is_file():
                with self.subTest(path=str(path.relative_to(out))):
                    self.assertNotRegex(path.read_bytes(), HOST_PATH_BYTES)
        data = json.loads((out / "data" / "benchmarking.json").read_text(encoding="utf-8"))
        ld = data["yardstick"]["ld"]
        self.assertEqual(ld["stores"][0]["label"], "…/EUR …/foo")
        self.assertEqual(ld["stores"][0]["versions"], "engine 0.27.0+…/engine · ogquery 0.5.0 at …/ogquery")
        svg = next(t for t in ld["trends"] if t["measure"] == "region_1mb")["svg"]
        self.assertIn("<title>OGL-00006 · engine 0.27.0+…/engine ·", svg)
        self.assertNotIn("via", svg)

    def test_a_link_to_an_ld_row_opens_the_benchmarking_tab_at_that_row(self) -> None:
        out = build(self.addCleanup, stores_doc=None, ld_run=True)
        done = subprocess.run(["node", str(RUNNER), str(out), "#ld-bench-OGL-00006"], capture_output=True, text=True, check=True, timeout=60)
        opened = json.loads(done.stdout)
        self.assertEqual([v for v, shown in opened["_panes"].items() if shown], ["benchmarking"])
        self.assertTrue(opened["_target"])
        self.assertEqual(opened["_scrolled"], ["ld-bench-OGL-00006"])

    def test_without_an_ld_result_the_gap_is_drawn_and_there_are_no_ld_rows(self) -> None:
        drawn = self.drawn(build(self.addCleanup, stores_doc=None))
        self.assertIn("LD Stores are not measured yet: LD not measured in this run (2026-11-17)", drawn["benchmarking"])
        self.assertIn("LD Stores are not measured yet: no committed yardstick result has an LD section.", drawn["stores"])
        self.assertFalse([i for i in drawn["_ids"] if i.startswith("ld-bench-")])
        self.assertFalse([l for l in drawn["_links"] if l.startswith("#ld-bench-")])


if __name__ == "__main__":
    unittest.main()
