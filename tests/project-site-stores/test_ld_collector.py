#!/usr/bin/env python3
"""The LD resources collector: the registry's rows, without `location` (og-dev-hub#10, seam 1).

Run from the repository root:
    python3 tests/project-site-stores/test_ld_collector.py
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

import stores_fixtures as fx

from project_site.collect import ld_resources, stores

# A host path anywhere: at the start, after a space, quote or colon, inside a URL. Not `resources/data/…`.
HOST_PATH = re.compile(r"(?<![\w.~-])/data/")


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
            self.assertIsNone(HOST_PATH.search(repr(row)), row)

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

    def test_a_panel_has_its_block_count_and_a_store_has_none(self) -> None:
        self.assertEqual(self.rows["OGL-00005"]["n_blocks"], 1357)
        self.assertIsNone(self.rows["OGL-00001"]["n_blocks"])

    def test_every_form_of_host_path_is_cut_and_a_relative_data_path_is_kept(self) -> None:
        for raw in ("receipt:/data/x/y.json", "https://h/?f=/data/x/y.json", "file:///data/x/y.json", "/data/x/y.json at the start",
                    "see /data/x/y.json", "'/data/x/y.json'", '"/data/x/y.json"', "a;/data/x/y.json"):
            with self.subTest(raw=raw):
                shown = ld_resources.scrub(raw)
                self.assertIsNone(HOST_PATH.search(shown), shown)
                self.assertIn("y.json", shown)
        self.assertEqual(ld_resources.scrub("from resources/data/derived/x.tsv"), "from resources/data/derived/x.tsv")

    def test_a_number_in_a_text_column_is_text_and_a_text_in_a_number_column_is_a_gap(self) -> None:
        row = ld_resources.public_row({"used_for": 5, "n": "many", "label": None, "record": "stores/ld/OGL-00001/record.yaml"})
        self.assertEqual((row["used_for"], row["n"], row["label"]), ("5", None, None))

    def test_a_record_path_is_relative_and_inside_the_registry_or_it_gives_no_link(self) -> None:
        for bad in ("/data/x/record.yaml", "stores/ld/../../etc/x", "elsewhere/record.yaml", "../stores/ld/OGL-00001/record.yaml", None):
            with self.subTest(record=bad):
                row = ld_resources.public_row({"record": bad})
                self.assertIsNone(row["record"])
                self.assertTrue(row["record_gap"])
                self.assertIsNone(HOST_PATH.search(row["record_gap"]), row["record_gap"])
        self.assertEqual(ld_resources.public_row({"record": "resources/reference-resources/p/resource.yaml"})["record_gap"], None)

    def test_a_panel_the_reader_cannot_read_makes_the_section_unavailable_with_the_exception(self) -> None:
        declaration = self.registry.parent / "resources" / "reference-resources" / "fixture-ld-panel" / "resource.yaml"
        original = declaration.read_text()
        declaration.write_text(original.replace("source:", "source: scalar\nignored:", 1))
        try:
            got = ld_resources.collect(self.registry)
        finally:
            declaration.write_text(original)
        self.assertFalse(got["available"])
        self.assertEqual(got["rows"], [])
        self.assertRegex(got["error"], r"AttributeError: ")


if __name__ == "__main__":
    unittest.main()
