#!/usr/bin/env python3
"""The LD resources collector: the registry's rows, without `location` (og-dev-hub#10, seam 1).

Run from the repository root:
    python3 tests/project-site-stores/test_ld_collector.py
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import stores_fixtures as fx

from project_site.collect import ld_resources, stores


class Collector(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="ld-collector-"))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.registry = fx.make_registry(cls.root)
        cls.got = ld_resources.collect(cls.registry)
        cls.rows = {r["ld_id"]: r for r in cls.got["rows"]}

    def test_every_row_of_each_kind_is_returned_in_id_order(self) -> None:
        self.assertTrue(self.got["available"])
        self.assertEqual(list(self.rows), [f"OGL-0000{n}" for n in range(1, 6)])
        self.assertEqual({r["kind"] for r in self.rows.values()}, {"ld_store", "genotype_store", "ld_panel"})

    def test_a_row_holds_the_registry_values_and_never_location(self) -> None:
        store = self.rows["OGL-00001"]
        self.assertEqual((store["kind"], store["status"], store["ancestry"], store["n"], store["store_bytes"]),
                         ("ld_store", "served", "EUR", 665, 79_278_843_340))
        self.assertEqual(store["built_with"], "ogld 0.5.0 (ogld build)")
        self.assertEqual(store["record"], "stores/ld/OGL-00001/record.yaml")
        self.assertEqual(self.rows["OGL-00002"]["genotype_bytes"], 4_139_037_382)
        for row in self.rows.values():
            self.assertNotIn("location", row)
            self.assertNotIn("/data/", repr(row).replace("/data/opengwasdb/reference/fixture/runs", ""))

    def test_a_panel_row_links_its_declaration_and_an_empty_count_is_none(self) -> None:
        panel = self.rows["OGL-00005"]
        self.assertEqual(panel["record"], "resources/reference-resources/fixture-ld-panel/resource.yaml")
        self.assertIsNone(panel["n_variants"])
        self.assertIsNone(panel["built_with"])
        self.assertEqual((panel["ancestry"], panel["n"]), ("AMR", 345))

    def test_stores_collect_carries_it(self) -> None:
        self.assertEqual(stores.collect(self.registry)["ld_resources"], self.got)

    def test_a_registry_with_no_ld_tree_is_a_gap_not_a_failure(self) -> None:
        (self.registry / "ld").rename(self.registry / "ld-aside")
        try:
            got = ld_resources.collect(self.registry)
        finally:
            (self.registry / "ld-aside").rename(self.registry / "ld")
        self.assertEqual((got["available"], got["rows"]), (False, []))
        self.assertIn("no stores/ld/", got["error"])

    def test_a_record_that_breaks_the_spec_is_a_gap_naming_it(self) -> None:
        record = self.registry / "ld" / "OGL-00003" / "record.yaml"
        original = record.read_text()
        record.write_text(original + "stray_key: 1\n")
        try:
            got = ld_resources.collect(self.registry)
        finally:
            record.write_text(original)
        self.assertFalse(got["available"])
        self.assertIn("OGL-00003", got["error"])


if __name__ == "__main__":
    unittest.main()
