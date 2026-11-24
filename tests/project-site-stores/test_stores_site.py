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
# An absolute path under /data on the host that built the site: not a `resources/data/` of a repository.
HOST_PATH = re.compile(r"(?<![\w.:/~-])/data/")


def build(cleanup, *, stores_doc: dict | None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="stores-site-"))
    cleanup(shutil.rmtree, root, True)
    registry = fx.make_registry(root / "registry")
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
        self.assertEqual([r["store_id"] for r in data["inventory"]], [f"OGS-0000{n}" for n in range(1, 7)])
        self.assertEqual(data["registry"]["stores_url"],
                         "https://github.com/opengwas/opengwasdb-stores/tree/" + "c" * 40 + "/stores/")
        self.assertEqual(data["inventory"][0]["url"],
                         "https://github.com/opengwas/opengwasdb-stores/tree/" + "c" * 40 + "/stores/OGS-00001/")

    def test_no_host_path_is_under_the_built_site(self) -> None:
        files = [p for p in self.out.rglob("*") if p.is_file()]
        self.assertTrue(files)
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(self.out))):
                self.assertNotRegex(text, HOST_PATH)
                self.assertNotIn("/data/opengwasdb", text)

    def test_the_page_names_the_script_and_the_content_section(self) -> None:
        page = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('src="js/stores.js"', page)
        self.assertIn('id="stores-content"', page)

    def test_the_trend_charts_are_in_the_data_as_svg_and_the_site_has_no_chart_library(self) -> None:
        data = json.loads((self.out / "data" / "stores.json").read_text(encoding="utf-8"))
        self.assertTrue(all(t["svg"].startswith("<svg ") for t in data["yardstick"]["trends"]))
        self.assertEqual(sorted(p.name for p in (self.out / "js").iterdir()),
                         ["app.js", "architecture.js", "context.js", "decisions.js", "stores.js"])


class StoresScript(unittest.TestCase):
    """`stores.js` draws the data it is given in `node`, and draws a source that was not collected as a notice."""

    def drawn(self, out: Path) -> str:
        done = subprocess.run(["node", str(RUNNER), str(out)], capture_output=True, text=True, check=True, timeout=60)
        return json.loads(done.stdout)["stores"]

    def test_the_inventory_gaps_and_yardstick_are_drawn(self) -> None:
        text = self.drawn(build(self.addCleanup, stores_doc=None))
        self.assertNotIn("could not be drawn", text)
        for expected in ("OGS-00001", "dense-new", "62.1 GB", "AFR 1 · EUR 2 · unassigned 1",
                         "recorded from opengwasdb-stores#502's backfill", "counts come with opengwasdb#488",
                         "pending opengwasdb-stores#507", "not computed",
                         "not applicable", "unavailable", "20261118T000000Z-broken.json is not a valid result",
                         "Not measured by yardstick", "taken under load: load average 70 over 56",
                         "not built yet (Release Status candidate)", "withdrawn", "answered by its scan",
                         "no record says how the HM3 step ended"):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)

    def test_a_store_source_that_was_not_collected_is_a_notice_and_nothing_throws(self) -> None:
        doc = {"source": "stores", "available": False, "collected_at": None, "error": "CollectError: registry is not a directory"}
        text = self.drawn(build(self.addCleanup, stores_doc=doc))
        self.assertNotIn("could not be drawn", text)
        self.assertIn("The Stores could not be collected", text)


if __name__ == "__main__":
    unittest.main()
