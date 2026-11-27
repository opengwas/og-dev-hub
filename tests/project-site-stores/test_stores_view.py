#!/usr/bin/env python3
"""The Stores view: the inventory and yardstick's results, from a fixture registry (og-dev-hub#16).

Run from the repository root:
    python3 tests/project-site-stores/test_stores_view.py
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import yaml
import tempfile
import unittest
from pathlib import Path

import stores_fixtures as fx

from project_site import stores_view
from project_site.collect import common, stores

HOST_PATH = re.compile(r"(?<![\w.~-])/data/")


def collected(registry: Path) -> dict:
    return common.envelope("stores", available=True, error=None, **stores.collect(registry, commit="c" * 40))


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="stores-view-"))
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.registry = fx.make_registry(cls.root)
        cls.doc = collected(cls.registry)
        cls.view = stores_view.stores_view(cls.doc)
        cls.rows = {r["store_id"]: r for r in cls.doc["inventory"]}
        cls.shown = {r["store_id"]: r for r in cls.view["inventory"]}


class InventoryTests(Fixture):
    """Seam 1: each inventory field, from a Store of each layout, checked against literals."""

    def test_every_store_has_a_row_and_nothing_else_does(self) -> None:
        self.assertEqual(list(self.rows), [f"OGS-0000{n}" for n in range(1, 9)])
        self.assertEqual([r["store_id"] for r in self.view["inventory"]], list(self.rows))

    def test_the_dense_store_with_every_field(self) -> None:
        row = self.shown["OGS-00001"]
        self.assertEqual({k: row[k]["text"] for k in row if isinstance(row[k], dict)}, {
            "layout": "dense", "completion_state": "reference_completed", "format_version": "1.2",
            "built_with": "opengwasdb 0.9.1", "last_built": "2026-11-13", "coverage": "gwas", "status": "validated",
            "store_bytes": "62.1 GB", "n_variants": "11,191,070",
            "top_hits": "p < 5e-04: 34,567 · p < 5e-06: 1,200 · p < 5e-08: 10",
            "has_hm3": "yes", "has_rho": "no", "n_clumped": None,
            "n_analyses": "4", "median_sample_size": "200", "ancestry": "AFR 1 · EUR 2 · unassigned 1",
        })
        self.assertEqual(row["label"], "dense-new")

    def test_the_other_layouts_read_from_their_own_bundles(self) -> None:
        self.assertEqual((self.shown["OGS-00002"]["layout"]["text"], self.shown["OGS-00003"]["layout"]["text"]), ("hybrid", "ragged"))
        self.assertEqual(self.shown["OGS-00003"]["coverage"]["text"], "cis")
        self.assertEqual(self.shown["OGS-00002"]["median_sample_size"]["text"], "60")
        self.assertEqual(self.shown["OGS-00003"]["n_variants"]["text"], "8,927,061")

    def test_n_clumped_is_pending_until_opengwasdb_stores_507(self) -> None:
        for store_id in ("OGS-00001", "OGS-00002", "OGS-00003", "OGS-00004"):
            self.assertEqual(self.shown[store_id]["n_clumped"], {"text": None, "gap": "pending opengwasdb-stores#507", "display": "n/a", "detail": None})

    def test_the_row_holds_the_ticket_fields_and_no_others(self) -> None:
        self.assertEqual(sorted(self.shown["OGS-00001"]), sorted([
            "store_id", "url", "label", "description", "summary", "facts", "why_na", "layout", "completion_state", "format_version", "built_with", "last_built", "coverage", "status", "store_bytes",
            "n_variants", "top_hits", "has_hm3", "has_rho", "n_clumped", "n_analyses", "median_sample_size", "ancestry"]))


class TileTests(Fixture):
    """The tile's data: the short description, and `n/a` for each gap with its reason kept (og-dev-hub#21)."""

    LONG = ("The UK Biobank GWAS of blood biochemistry markers run through the pan-ancestry pipeline with a very long "
            "first sentence that keeps going past the cut so that it has to be shortened on a word boundary. A second sentence.")

    def test_a_description_longer_than_the_cut_ends_in_an_ellipsis_on_a_word_boundary(self) -> None:
        short = stores_view.summary(self.LONG)
        self.assertEqual(short, "The UK Biobank GWAS of blood biochemistry markers run through the pan-ancestry pipeline with a very long "
                                "first sentence that keeps going past the cut so that it…")
        self.assertLessEqual(len(short), 161)
        self.assertNotIn("A second sentence", short)

    def test_a_host_path_ends_the_summary_before_it_and_never_leaves_two_ellipses(self) -> None:
        real = ("Full dense Store Release of all 2,514 UK Biobank (ukb-b) GWAS-VCF Analyses declared in the OpenGWAS IGD "
                "collection and verified present in /data/opengwasdb/raw/gwas-vcf/ukb-b, reference-completed under its own id "
                "against the UKB EUR LD panel (ADR 0037).")
        short = stores_view.summary(real)
        self.assertEqual(short, "Full dense Store Release of all 2,514 UK Biobank (ukb-b) GWAS-VCF Analyses declared in the "
                                "OpenGWAS IGD collection and verified present in…")
        self.assertNotIn("…/", short)
        self.assertEqual(stores_view.summary("Read at /data/opengwasdb/raw/x by the builder."), "Read at…")

    def test_et_al_and_other_abbreviations_do_not_end_the_sentence(self) -> None:
        chen = ("Full European-ancestry slice of the Chen et al. 2023 plasma metabolome atlas (PMID 36635386): every candidate "
                "analysis for this ancestry, no cap, as a single-ancestry no-cis ragged GWAS-SSF release.\n")
        self.assertEqual(stores_view.summary(chen), "Full European-ancestry slice of the Chen et al. 2023 plasma metabolome atlas "
                         "(PMID 36635386): every candidate analysis for this ancestry, no cap, as a…")
        sun = ("First 10 Sun et al. INTERVAL SomaScan plasma-proteome pQTL analyses (PMID 29875488) -- a deterministic prefix of "
               "the 100-analysis 2018-sun-pilot-100 selection, built end-to-end through OpenGWASDB's real ragged builder as a small, "
               "current, grounded proof that this Store Family's pipeline (Trait Ontology Mapping, CURIE-normalised trait_ontology_id, "
               "analysis_label) actually produces a working store.\n")
        self.assertEqual(stores_view.summary(sun), "First 10 Sun et al. INTERVAL SomaScan plasma-proteome pQTL analyses (PMID 29875488) "
                         "-- a deterministic prefix of the 100-analysis 2018-sun-pilot-100 selection…")
        self.assertEqual(stores_view.summary("Use a tool, e.g. a script. Then stop."), "Use a tool, e.g. a script.")
        self.assertEqual(stores_view.summary("Run by J. Smith in 2026. Then stop."), "Run by J. Smith in 2026.")
        self.assertEqual(stores_view.summary("That is, i.e. this one. Next."), "That is, i.e. this one.")

    def test_each_status_tag_has_its_tone_written_by_the_build(self) -> None:
        tone = {s: r["status"]["tone"] for s, r in ((r["status"]["text"], r) for r in self.shown.values())}
        self.assertEqual(tone, {"validated": "ok", "built": "ok", "candidate": None, "accepted": None, "withdrawn": "muted"})
        self.assertEqual(stores_view.STATUS_TONE["superseded"], "muted")

    def test_a_shorter_description_is_its_first_sentence_alone(self) -> None:
        self.assertEqual(stores_view.summary("Dense build of UKB. Second sentence."), "Dense build of UKB.")
        self.assertEqual(stores_view.summary("No full stop here"), "No full stop here")
        self.assertIsNone(stores_view.summary("  "))

    def test_the_full_description_is_still_written(self) -> None:
        row = self.shown["OGS-00001"]
        self.assertEqual(row["description"], "Read at …/ukb-b by the builder.")
        self.assertTrue(row["summary"] and row["description"].startswith(row["summary"].rstrip("…")))

    def test_a_gap_displays_n_a_and_keeps_its_reason(self) -> None:
        row = self.shown["OGS-00003"]
        fact = {f["label"]: f for f in row["facts"]}
        self.assertEqual((fact["Size on disk"]["display"], fact["Size on disk"]["na"]), ("n/a", True))
        self.assertEqual(row["store_bytes"]["gap"], "recorded from opengwasdb-stores#502's backfill")
        self.assertIn({"label": "Size on disk", "reason": "recorded from opengwasdb-stores#502's backfill"}, row["why_na"])
        self.assertEqual(fact["Layout"]["display"], "ragged")

    def test_completion_reads_as_a_phrase_and_a_missing_state_is_n_a(self) -> None:
        def fact(row: dict) -> dict:
            shown = stores_view.inventory_row({"store_id": "X", **row}, None)
            return {"fact": next(f for f in shown["facts"] if f["label"] == "Completion"), "why": shown["why_na"]}

        done = fact({"store_id": "OGS-00009", "completion_state": {"value": "reference_completed"}})
        self.assertEqual(done["fact"], {"label": "Completion", "display": "reference completed", "detail": None, "na": False})
        observed = fact({"store_id": "OGS-00027", "completion_state": {"value": "observed_only"}})
        self.assertEqual(observed["fact"]["display"], "observed only")
        self.assertEqual(fact({"completion_state": {"value": "in_progress"}})["fact"]["display"], "in_progress")
        gap = fact({"completion_state": {"gap": "no build.yaml"}})
        self.assertEqual((gap["fact"]["display"], gap["fact"]["na"]), ("n/a", True))
        self.assertIn({"label": "Completion", "reason": "no build.yaml"}, gap["why"])
        labels = [f["label"] for f in self.shown["OGS-00001"]["facts"]]
        self.assertEqual(labels[:3], ["Layout", "Coverage", "Completion"])

    def test_format_built_with_and_last_built(self) -> None:
        def shown(row: dict) -> dict:
            out = stores_view.inventory_row({"store_id": "X", **row}, None)
            return {"facts": {f["label"]: f for f in out["facts"]}, "why": out["why_na"]}

        full = shown({
            "format_version": {"value": "1.2"}, "built_with": {"value": "0.9.1"}, "last_built": {"value": "2026-11-13"}})
        self.assertEqual(full["facts"]["Format"]["display"], "1.2")
        self.assertEqual(full["facts"]["Built with"], {"label": "Built with", "display": "opengwasdb 0.9.1", "detail": None, "na": False})
        self.assertEqual(full["facts"]["Last built"]["display"], "2026-11-13")
        gaps = shown({"built_with": {"gap": "no build_environment"}})
        for label in ("Format", "Built with", "Last built"):
            self.assertEqual((gaps["facts"][label]["display"], gaps["facts"][label]["na"]), ("n/a", True))
        self.assertIn({"label": "Built with", "reason": "no build_environment"}, gaps["why"])
        self.assertEqual([f["label"] for f in self.shown["OGS-00001"]["facts"]][2:6], ["Completion", "Format", "Built with", "Last built"])

    def test_the_dense_fixture_reads_its_record(self) -> None:
        facts = {f["label"]: f["display"] for f in self.shown["OGS-00001"]["facts"]}
        self.assertEqual((facts["Format"], facts["Built with"], facts["Last built"]), ("1.2", "opengwasdb 0.9.1", "2026-11-13"))

    def test_a_record_with_no_build_environment_shows_n_a_and_format_waits_for_512(self) -> None:
        row = self.shown["OGS-00003"]  # built, with a Validation Record that has neither build_environment nor validated_at
        facts = {f["label"]: f["display"] for f in row["facts"]}
        self.assertEqual((facts["Format"], facts["Built with"], facts["Last built"]), ("n/a", "n/a", "n/a"))
        self.assertIn({"label": "Format", "reason": "no format version is recorded in the Validation Record"}, row["why_na"])
        self.assertIn("Built with", [w["label"] for w in row["why_na"]])

    def test_last_built_is_a_utc_date(self) -> None:
        import datetime
        from project_site.collect import inventory
        for value, want in (("2026-11-13T23:30:00-05:00", "2026-11-14"), ("2026-11-13T09:30:00Z", "2026-11-13"),
                            (datetime.datetime(2026, 11, 13, 23, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))), "2026-11-14"),
                            (yaml.safe_load("validated_at: 2026-11-13 09:30:00")["validated_at"], "2026-11-13"),
                            (datetime.date(2026, 11, 13), "2026-11-13")):
            self.assertEqual(inventory.utc_date(value), want, value)

    def test_a_bad_value_is_a_gap_that_names_it(self) -> None:
        from project_site.collect import inventory
        cells = inventory._record_cells({"validated_at": "last Tuesday", "build_environment": {"opengwasdb_version": 9},
                                         "observed": {"format_version": 2}}, None, None)
        self.assertEqual(cells["last_built"]["gap"], "validated_at 'last Tuesday' is not a timestamp")
        self.assertEqual(cells["built_with"]["gap"], "build_environment.opengwasdb_version 9 is not a version string")
        self.assertEqual(cells["format_version"]["gap"], "observed.format_version 2 is not a version string")

    def test_each_format_gap_names_its_cause(self) -> None:
        from project_site.collect import inventory
        self.assertEqual(inventory._record_cells({"observed": {}}, None, None)["format_version"]["gap"], inventory.FORMAT_UNRECORDED)
        self.assertEqual(inventory._record_cells({"observed": {"format_version": None}}, None, None)["format_version"]["gap"], inventory.FORMAT_UNRECORDED)
        no_block = "the Validation Record has no observed block"
        self.assertEqual(inventory._record_cells({}, None, no_block)["format_version"]["gap"], no_block)
        self.assertEqual(inventory._record_cells({}, "not built yet (Release Status candidate)", None)["last_built"]["gap"],
                         "not built yet (Release Status candidate)")

    def test_a_store_with_no_gap_has_no_reasons(self) -> None:
        self.assertEqual([w["label"] for w in self.shown["OGS-00001"]["why_na"]], [])

    def test_every_tile_fact_is_n_a_or_a_figure_never_blank(self) -> None:
        for row in self.shown.values():
            for f in row["facts"]:
                self.assertTrue(f["display"], (row["store_id"], f["label"]))
                self.assertEqual(f["display"] == "n/a", f["na"])


class GapTests(Fixture):
    """Seam 2: a Validation Record without #502's fields shows each as a gap naming its source, never as zero."""

    BACKFILL = "recorded from opengwasdb-stores#502's backfill"

    def test_each_missing_field_is_a_gap_naming_what_fills_it(self) -> None:
        old = self.shown["OGS-00003"]
        for field in ("store_bytes", "has_hm3", "has_rho", "top_hits"):
            with self.subTest(field=field):
                self.assertEqual((old[field]["text"], old[field]["gap"]), (None, self.BACKFILL))

    def test_a_count_the_record_left_null_waits_for_the_engine(self) -> None:
        self.assertEqual(self.shown["OGS-00002"]["n_variants"]["gap"], "counts come with opengwasdb#488")

    def test_a_store_without_a_top_hit_index_says_not_computed(self) -> None:
        gap = self.shown["OGS-00002"]["top_hits"]["gap"]
        self.assertTrue(gap.startswith("not computed"), gap)
        self.assertIn("post.top_hits", gap)

    def test_a_null_top_hit_count_on_an_indexed_store_waits_for_the_engine(self) -> None:
        stores_dir = self.registry
        yaml_path = stores_dir / "OGS-00003" / "validation.yaml"
        original = yaml_path.read_text()
        self.addCleanup(yaml_path.write_text, original)
        yaml_path.write_text(original.replace("observed:", "observed:\n  n_top_hits: null\n  has_hm3: null"))
        row = stores_view.stores_view(collected(stores_dir))["inventory"][2]
        self.assertEqual(row["top_hits"]["gap"], "counts come with opengwasdb#488")
        self.assertEqual(row["has_hm3"]["gap"], "no record says how the HM3 step ended")

    def test_no_gap_is_ever_drawn_as_zero(self) -> None:
        for row in self.shown.values():
            for key, cell in row.items():
                if isinstance(cell, dict) and cell["gap"]:
                    with self.subTest(store=row["store_id"], field=key):
                        self.assertIsNone(cell["text"])
        for row in self.rows.values():  # and the collected value of a gap is null, not 0
            for key, cell in row.items():
                if isinstance(cell, dict) and cell.get("gap"):
                    self.assertIsNone(cell["value"], (row["store_id"], key))

    def test_a_manifest_without_an_ancestry_column_is_a_gap(self) -> None:
        self.assertEqual(self.shown["OGS-00003"]["ancestry"]["gap"], "the manifest has no Assigned Ancestry column")

    def test_a_missing_manifest_is_a_gap_for_what_it_holds_and_stops_nothing(self) -> None:
        (self.registry / "OGS-00003" / "analyses.tsv").rename(self.registry / "OGS-00003" / "gone.tsv")
        self.addCleanup((self.registry / "OGS-00003" / "gone.tsv").rename, self.registry / "OGS-00003" / "analyses.tsv")
        row = stores_view.stores_view(collected(self.registry))["inventory"][2]
        for field in ("n_analyses", "median_sample_size", "ancestry"):
            self.assertEqual(row[field]["gap"], "analyses.tsv is not in the bundle")
        self.assertEqual(row["layout"]["text"], "ragged")


class BuiltRowsTests(Fixture):
    """Seam 3: counts, ancestry and the median skip the `exclude_from_build` audit rows."""

    def test_the_excluded_row_is_not_counted(self) -> None:
        row = self.shown["OGS-00001"]
        self.assertEqual(row["n_analyses"]["text"], "4")
        self.assertEqual(self.rows["OGS-00001"]["n_analyses"]["excluded"], 1)

    def test_the_excluded_sample_size_does_not_move_the_median(self) -> None:
        self.assertEqual(self.rows["OGS-00001"]["median_sample_size"]["value"], 200)  # 250 if the excluded row counted

    def test_the_median_says_how_many_built_rows_had_a_sample_size(self) -> None:
        self.assertEqual(self.shown["OGS-00001"]["median_sample_size"]["detail"], "over the 3 of 4 built rows that have one")

    def test_the_excluded_ancestry_is_not_counted(self) -> None:
        self.assertEqual(self.rows["OGS-00001"]["ancestry"]["value"], {"AFR": 1, "EUR": 2, "unassigned": 1})


class CauseTests(Fixture):
    """Every blank names its true cause: an unbuilt Store waits for no backfill, and a built one's gap is the record's."""

    OBSERVED = ("store_bytes", "n_variants", "top_hits", "has_hm3", "has_rho", "n_clumped")

    def test_a_candidate_with_no_validation_record_is_not_built_yet_in_every_observed_field(self) -> None:
        for field in self.OBSERVED:
            with self.subTest(field=field):
                self.assertEqual(self.shown["OGS-00005"][field]["gap"], "not built yet (Release Status candidate)")

    def test_an_accepted_store_with_an_all_null_record_is_not_built_yet_either(self) -> None:
        for field in self.OBSERVED:
            with self.subTest(field=field):
                self.assertEqual(self.shown["OGS-00006"][field]["gap"], "not built yet (Release Status accepted)")

    def test_an_unbuilt_store_never_names_the_backfill_or_the_engine(self) -> None:
        for store_id in ("OGS-00005", "OGS-00006"):
            for field in self.OBSERVED:
                gap = self.shown[store_id][field]["gap"]
                self.assertNotRegex(gap, r"#502|#488|#507")

    def test_an_unbuilt_store_still_shows_what_its_manifest_holds(self) -> None:
        self.assertEqual(self.shown["OGS-00005"]["n_analyses"]["text"], "1")
        self.assertEqual(self.shown["OGS-00005"]["ancestry"]["text"], "EUR 1")

    def test_hm3_null_on_a_built_store_says_no_record_says_how_the_step_ended(self) -> None:
        self.assertEqual(self.shown["OGS-00004"]["has_hm3"]["gap"], "no record says how the HM3 step ended")

    def test_a_null_top_hit_count_is_a_gap_naming_the_bad_value_and_never_crashes_the_build(self) -> None:
        gap = self.shown["OGS-00004"]["top_hits"]["gap"]
        self.assertEqual(gap, "observed.n_top_hits[5e-08] None is not a count")

    def test_a_median_gap_names_its_cause(self) -> None:
        self.assertEqual(self.shown["OGS-00004"]["median_sample_size"]["gap"],
                         "the Release Manifest records no sample size for any built row (1 value is not a number)")

    def test_a_median_over_values_some_of_which_are_not_numbers_says_so(self) -> None:
        doc = json.loads(json.dumps(self.doc))
        row = next(r for r in doc["inventory"] if r["store_id"] == "OGS-00001")
        row["median_sample_size"] |= {"unparseable": 2}
        shown = stores_view.stores_view(doc)["inventory"][0]
        self.assertEqual(shown["median_sample_size"]["detail"],
                         "over the 3 of 4 built rows that have one; 2 values are not numbers")

    def test_a_withdrawn_store_with_no_record_will_never_be_built(self) -> None:
        self.assertEqual(self.shown["OGS-00007"]["store_bytes"]["gap"], "no Validation Record (Release Status withdrawn)")

    def test_an_empty_ancestry_is_a_gap_with_its_reason_never_a_blank_cell(self) -> None:
        self.assertEqual(self.shown["OGS-00008"]["ancestry"], {"text": None, "detail": None, "display": "n/a",
                         "gap": "no built row, so there is no ancestry to count"})
        self.assertEqual(self.shown["OGS-00003"]["ancestry"]["gap"], "the manifest has no Assigned Ancestry column")
        self.assertEqual(self.shown["OGS-00008"]["n_analyses"]["text"], "0")

    def test_has_rho_null_is_said_in_plain_words(self) -> None:
        self.assertEqual(self.shown["OGS-00008"]["has_rho"]["gap"],
                         "the recipe builds no Rho Matrix, so whether the Store holds one is unknown until opengwasdb#488")

    def test_the_plural_follows_the_count(self) -> None:
        self.assertEqual(stores_view.plural(1, "value is", "values are"), "1 value is")
        self.assertEqual(stores_view.plural(2, "value is", "values are"), "2 values are")

    def test_a_withdrawn_store_shows_its_status(self) -> None:
        self.assertEqual(self.shown["OGS-00004"]["status"]["text"], "withdrawn")
        self.assertEqual(self.shown["OGS-00004"]["store_bytes"]["text"], "1 B")  # built once: its record reads as any built Store's


class LdResourcesTests(Fixture):
    """Seam 2: the counts, each fact as display text, a NULL column as n/a with its reason, retired as retired (og-dev-hub#10)."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.ld = cls.view["ld_resources"]
        cls.tiles = {r["store_id"]: r for r in cls.ld["rows"]}

    def facts(self, ld_id: str) -> dict:
        return {f["label"]: f["display"] for f in self.tiles[ld_id]["facts"]}

    def test_the_old_gap_is_gone(self) -> None:
        self.assertNotIn("ld_stores", self.view)

    def test_gwas_stores_and_ld_resources_are_counted_separately_with_each_ld_kind(self) -> None:
        self.assertEqual(self.view["counts"]["gwas_stores"], {"n": 8, "text": "8 GWAS Stores"})
        ld = self.view["counts"]["ld_resources"]
        self.assertEqual(ld["n"], 5)
        self.assertEqual([(k["kind"], k["n"], k["text"]) for k in ld["by_kind"]],
                         [("ld_store", 3, "3 LD Stores"), ("genotype_store", 1, "1 Genotype Store"), ("ld_panel", 1, "1 LD panel")])
        self.assertEqual(ld["text"], "5 LD resources: 3 LD Stores, 1 Genotype Store, 1 LD panel")

    def test_an_ld_store_tile_states_each_fact_as_text(self) -> None:
        self.assertEqual(self.facts("OGL-00001"), {
            "Kind": "LD Store", "Provenance": "genotypes", "Source Panel": "hgdp1kgp-v2-EUR · EUR · n 665",
            "Reference Assembly": "GRCh38", "Size on disk": "79.3 GB", "Variants": "8,586,889",
            "Built with": "ogld 0.5.0 (ogld build)"})
        tile = self.tiles["OGL-00001"]
        self.assertEqual((tile["label"], tile["status"]["display"], tile["status"]["tone"]), ("hgdp1kgp-v2-EUR-k10-01", "served", "ok"))
        self.assertEqual(tile["summary"], "Data API LD: matrix, region, proxies, clump")
        self.assertEqual(tile["notes"], "served by ogdb-api; stays as the reference")
        self.assertEqual(tile["url"], "https://github.com/opengwas/opengwasdb-stores/blob/" + "c" * 40 + "/stores/ld/OGL-00001/record.yaml")

    def test_a_genotype_store_shows_its_genotype_bytes_too_and_the_kind_in_words(self) -> None:
        facts = self.facts("OGL-00002")
        self.assertEqual((facts["Kind"], facts["Size on disk"]), ("Genotype Store", "79.3 GB · genotypes 4.1 GB"))

    def test_an_ld_panel_links_its_declaration_and_an_empty_cell_is_n_a_with_its_reason(self) -> None:
        tile, facts = self.tiles["OGL-00005"], self.facts("OGL-00005")
        self.assertEqual((facts["Kind"], facts["Variants"], facts["Built with"], facts["Blocks"]), ("LD panel", "n/a", "n/a", "1,357"))
        self.assertEqual(facts["Source Panel"], "gnomAD v3.1.2 HGDP+1kGP, AMR samples only · AMR · n 345")
        self.assertTrue(tile["url"].endswith("/resources/reference-resources/fixture-ld-panel/resource.yaml"))
        reasons = {w["label"]: w["reason"] for w in tile["why_na"]}
        self.assertEqual(set(reasons), {"Variants", "Built with"})
        self.assertIn("declaration", reasons["Variants"])

    def test_a_missing_sample_size_is_n_a_with_its_reason_and_not_nothing(self) -> None:
        doc = copy.deepcopy(self.doc)
        doc["ld_resources"]["rows"][4]["n"] = None  # the panel
        doc["ld_resources"]["rows"][0]["n"] = None  # a Store
        tiles = {r["store_id"]: r for r in stores_view.stores_view(doc)["ld_resources"]["rows"]}
        self.assertEqual({f["label"]: f["display"] for f in tiles["OGL-00005"]["facts"]}["Source Panel"],
                         "gnomAD v3.1.2 HGDP+1kGP, AMR samples only · AMR · n n/a")
        self.assertIn({"label": "Source Panel n", "reason": "the panel's declaration holds no sample size"}, tiles["OGL-00005"]["why_na"])
        self.assertIn({"label": "Source Panel n", "reason": "the Store's record holds no sample size"}, tiles["OGL-00001"]["why_na"])

    def test_the_view_turns_a_numeric_label_into_display_text(self) -> None:
        doc = copy.deepcopy(self.doc)
        doc["ld_resources"]["rows"][0]["label"] = 42
        self.assertEqual(stores_view.stores_view(doc)["ld_resources"]["rows"][0]["label"], "42")

    def test_the_sample_size_gap_is_reported_even_without_a_source_panel_name(self) -> None:
        doc = copy.deepcopy(self.doc)
        doc["ld_resources"]["rows"][4].update(n=None, source_panel=None)
        tile = next(r for r in stores_view.stores_view(doc)["ld_resources"]["rows"] if r["store_id"] == "OGL-00005")
        self.assertEqual({f["label"]: f["display"] for f in tile["facts"]}["Source Panel"], "n/a")
        self.assertIn({"label": "Source Panel n", "reason": "the panel's declaration holds no sample size"}, tile["why_na"])

    def test_blocks_are_a_panels_fact_and_no_store_draws_them(self) -> None:
        for ld_id, tile in self.tiles.items():
            self.assertEqual("Blocks" in self.facts(ld_id), ld_id == "OGL-00005", ld_id)
            self.assertNotIn("Blocks", {w["label"] for w in tile["why_na"]} if ld_id != "OGL-00005" else set())

    def test_the_description_is_abbreviated_as_a_gwas_tile_is_and_the_open_tile_holds_it_whole(self) -> None:
        long = "Data API LD for every ancestry, " + "with a very long account of what it is used for, " * 8 + "and the end."
        doc = copy.deepcopy(self.doc)
        doc["ld_resources"]["rows"][0]["used_for"] = long
        tile = stores_view.stores_view(doc)["ld_resources"]["rows"][0]
        self.assertTrue(tile["summary"].endswith("…"))
        self.assertLessEqual(len(tile["summary"]), 162)
        self.assertEqual(tile["description"], long)
        self.assertEqual(tile["notes"], "served by ogdb-api; stays as the reference")

    def test_a_record_with_no_valid_link_has_no_url_and_says_why(self) -> None:
        doc = copy.deepcopy(self.doc)
        doc["ld_resources"]["rows"][0].update(record=None, record_gap="the record path is not inside stores/ld")
        tile = stores_view.stores_view(doc)["ld_resources"]["rows"][0]
        self.assertIsNone(tile["url"])
        self.assertIn({"label": "Record", "reason": "the record path is not inside stores/ld"}, tile["why_na"])

    def test_the_build_writes_the_notice_for_a_section_that_is_not_listed(self) -> None:
        doc = {**self.doc, "ld_resources": {"available": False, "error": "no stores/ld/", "rows": []}}
        ld = stores_view.stores_view(doc)["ld_resources"]
        self.assertEqual(ld["notice"], "LD resources are not listed: no stores/ld/")
        self.assertIsNone(stores_view.stores_view(self.doc)["ld_resources"]["notice"])

    def test_a_row_the_view_cannot_draw_makes_the_section_unavailable_and_the_gwas_tiles_still_render(self) -> None:
        doc = copy.deepcopy(self.doc)
        doc["ld_resources"]["rows"][1]["n_variants"] = "many"
        view = stores_view.stores_view(doc)
        self.assertFalse(view["ld_resources"]["available"])
        self.assertRegex(view["ld_resources"]["gap"], r"^ValueError: ")
        self.assertEqual(view["counts"]["ld_resources"]["text"], "LD resources: not counted")
        self.assertEqual(view["counts"]["gwas_stores"]["n"], 8)
        self.assertEqual(len(view["inventory"]), 8)

    def test_a_panel_the_reader_cannot_read_leaves_the_gwas_tiles_and_count(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="stores-ld-bad-"))
        self.addCleanup(shutil.rmtree, root, True)
        registry = fx.make_registry(root)
        declaration = root / "resources" / "reference-resources" / "fixture-ld-panel" / "resource.yaml"
        declaration.write_text(declaration.read_text().replace("source:", "source: scalar\nignored:", 1))
        view = stores_view.stores_view(collected(registry))
        self.assertTrue(view["available"])
        self.assertEqual((len(view["inventory"]), view["counts"]["gwas_stores"]["n"]), (8, 8))
        self.assertFalse(view["ld_resources"]["available"])
        self.assertIn("AttributeError", view["ld_resources"]["notice"])
        self.assertEqual(view["counts"]["ld_resources"]["n"], None)

    def test_a_numeric_used_for_is_shown_as_text(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="stores-ld-num-"))
        self.addCleanup(shutil.rmtree, root, True)
        registry = fx.make_registry(root)
        declaration = root / "resources" / "reference-resources" / "fixture-ld-panel" / "resource.yaml"
        declaration.write_text(declaration.read_text().replace("used_for: reference completion (opengwasdb complete-dense)", "used_for: 42"))
        view = stores_view.stores_view(collected(registry))
        self.assertTrue(view["ld_resources"]["available"])
        self.assertEqual(view["ld_resources"]["rows"][4]["summary"], "42")

    def test_retired_and_reference_are_shown_as_they_are(self) -> None:
        self.assertEqual(self.tiles["OGL-00003"]["status"], {"display": "retired", "tone": "muted"})
        self.assertEqual(self.tiles["OGL-00004"]["status"], {"display": "reference", "tone": "muted"})

    def test_facts_that_do_not_apply_to_ld_are_not_drawn_at_all(self) -> None:
        for tile in self.ld["rows"]:
            labels = {f["label"] for f in tile["facts"]} | {w["label"] for w in tile["why_na"]}
            self.assertFalse(labels & {"Top hits", "HM3", "Rho", "Clumped", "Layout", "Coverage", "Analyses"}, labels)

    def test_benchmarking_is_a_named_gap_worded_like_the_others(self) -> None:
        self.assertEqual(self.ld["benchmarking"], "LD Stores are not measured yet: no committed yardstick result has an LD section.")

    def test_a_host_path_in_a_note_is_cut_to_its_last_name(self) -> None:
        self.assertNotIn("/data/", json.dumps(self.view))
        self.assertIn("receipt.json", self.tiles["OGL-00005"]["notes"])

    def test_a_registry_that_could_not_be_listed_is_a_gap_and_not_a_count_of_zero(self) -> None:
        doc = {**self.doc, "ld_resources": {"available": False, "error": "the LD Store Registry could not be listed: OGL-00003", "rows": []}}
        ld = stores_view.stores_view(doc)
        self.assertIsNone(ld["counts"]["ld_resources"]["n"])
        self.assertEqual(ld["counts"]["ld_resources"]["text"], "LD resources: not counted")
        self.assertEqual(ld["ld_resources"]["rows"], [])
        self.assertIn("could not be listed", ld["ld_resources"]["gap"])
        self.assertEqual(ld["counts"]["gwas_stores"]["n"], 8)


class LdBenchmarkingTests(Fixture):
    """Seam 5: an LD id is never one of the GWAS Stores the Benchmarking tab lists as unmeasured."""

    def test_ld_ids_are_not_in_the_unmeasured_list(self) -> None:
        unmeasured = [u["store_id"] for u in stores_view.benchmarking_view(self.doc)["yardstick"]["unmeasured"]]
        self.assertTrue(unmeasured)
        self.assertFalse([i for i in unmeasured if i.startswith("OGL-")])


class DeclaredTopHitsTests(unittest.TestCase):
    """The recipe's top-hit rule is `ogstores.plan.declared_top_hits`'s, not a second copy of it."""

    COUNTS = {"n_top_hits": {"5e-08": 3}}

    def top_hits(self, build: dict, observed: dict) -> dict:
        from project_site.collect import inventory
        return inventory._top_hits(build, observed)

    def test_the_hyphenated_alias_declares_the_index(self) -> None:
        got = self.top_hits({"post": {"top-hits": True}}, self.COUNTS)
        self.assertEqual(got["value"], [{"threshold": "5e-08", "count": 3}])
        self.assertTrue(self.top_hits({"post": {"top-hits": False}}, self.COUNTS)["gap"].startswith("not computed"))

    def test_a_recipe_with_no_key_does_not_declare_it(self) -> None:
        self.assertTrue(self.top_hits({"post": {}}, self.COUNTS)["gap"].startswith("not computed"))
        self.assertTrue(self.top_hits({}, self.COUNTS)["gap"].startswith("not computed"))

    def test_a_value_that_is_not_a_boolean_is_a_gap_carrying_the_owners_message(self) -> None:
        self.assertEqual(self.top_hits({"post": {"top_hits": "yes"}}, self.COUNTS)["gap"],
                         "post.top_hits is 'yes'; it is true or false")

    def test_a_bad_count_is_refused_by_the_one_count_rule(self) -> None:
        got = self.top_hits({"post": {"top_hits": True}}, {"n_top_hits": {"5e-08": -1}})
        self.assertEqual(got["gap"], "observed.n_top_hits[5e-08] -1 is not a count")


class NoObservedBlockTests(Fixture):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        fx.write_bundle(cls.registry, "OGS-00009", release={"label": "bare", "status": "validated", "association_coverage": "gwas"},
                        build={"layout": "dense", "completion_state": "observed_only", "post": {"top_hits": True}},
                        validation={"status": "passed"}, analyses="analysis_id\nX1\n")
        cls.row = {r["store_id"]: r for r in stores_view.stores_view(collected(cls.registry))["inventory"]}["OGS-00009"]

    def test_a_built_store_whose_record_has_no_observed_block_says_so_and_not_the_backfill(self) -> None:
        for field in ("store_bytes", "n_variants", "top_hits", "has_hm3", "has_rho", "n_clumped"):
            with self.subTest(field=field):
                self.assertEqual(self.row[field]["gap"], "the Validation Record has no observed block")


class YardstickTests(Fixture):
    """Seam 4: old and new workloads both render; the states are distinct; an invalid file is a gap."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.y = stores_view.benchmarking_view(cls.doc)["yardstick"]
        cls.latest = {s["store_id"]: s for s in cls.y["stores"]}

    def test_every_valid_run_shows_and_the_invalid_one_is_a_gap_naming_its_file(self) -> None:
        self.assertEqual(self.y["runs"], 3)
        self.assertEqual(self.y["workloads"], ["yardstick-3", "yardstick-4"])
        self.assertEqual([i["file"] for i in self.y["invalid"]], ["20261118T000000Z-broken.json"])
        self.assertIn("schema", self.y["invalid"][0]["error"])

    def test_the_latest_run_per_store_gives_its_facts(self) -> None:
        dense = self.latest["OGS-00001"]
        self.assertEqual((dense["engine_version"], dense["date"], dense["workload_id"]), ("0.10.0", "2026-11-17", "yardstick-4"))
        self.assertEqual(dense["peak_memory"]["text"], "950 MB")
        self.assertEqual(dense["size_on_disk"]["text"], "62.1 GB")
        by_name = {m["name"]: m for m in dense["measures"]}
        self.assertEqual((by_name["phewas_rsid"]["median"], by_name["phewas_rsid"]["p95"]), ("90.0 ms", "108.0 ms"))

    def test_an_old_workload_result_renders_without_the_new_measures(self) -> None:
        old_only = {"runs": [r for r in self.doc["yardstick"]["runs"] if r["workload_id"] == "yardstick-3"],
                    "invalid": [], "available": True, "reason": None}
        view = stores_view.yardstick_view(old_only, {}, ["OGS-00001"])
        dense = view["stores"][0]
        self.assertEqual([m["name"] for m in dense["measures"]], ["open", "phewas_rsid", "top_hits"])
        self.assertEqual(dense["engine_version"], "0.3.3")

    def test_the_new_measures_appear_once_a_run_carries_them(self) -> None:
        names = [m["name"] for m in self.latest["OGS-00001"]["measures"]]
        for name in ("lookup_100x100", "range_by_analysis", "top_hits", "region_100kb", "rho"):
            self.assertIn(name, names)

    def test_not_applicable_and_unavailable_are_drawn_distinctly(self) -> None:
        by_name = {m["name"]: m for m in self.latest["OGS-00001"]["measures"]}
        self.assertEqual((by_name["range_by_analysis"]["state"], by_name["range_by_analysis"]["note"]),
                         ("not_applicable", "the cis query is Ragged only"))
        self.assertEqual(by_name["rho"]["state"], "not_applicable")
        self.assertEqual(by_name["region_100kb"]["state"], "unavailable")
        self.assertIn("region failed reading", by_name["region_100kb"]["note"])
        self.assertNotEqual(by_name["rho"]["state"], by_name["region_100kb"]["state"])
        # The build writes each state's label and tone; the script renders them.
        self.assertEqual((by_name["rho"]["label"], by_name["rho"]["tone"]), ("not applicable", None))
        self.assertEqual((by_name["region_100kb"]["label"], by_name["region_100kb"]["tone"]), ("unavailable", "fault"))
        for state in (by_name["rho"], by_name["region_100kb"]):
            self.assertIsNone(state["median"])

    def test_a_store_yardstick_does_not_measure_says_so(self) -> None:
        self.assertEqual([u["store_id"] for u in self.y["unmeasured"]], ["OGS-00003", "OGS-00004", "OGS-00005", "OGS-00006", "OGS-00007", "OGS-00008"])

    def test_raw_runs_are_not_listed(self) -> None:
        self.assertNotIn("runs_list", self.y)
        self.assertNotIn("20261105T060000Z-0.3.3.json", json.dumps(self.view))

    def test_a_directory_without_results_says_so(self) -> None:
        view = stores_view.yardstick_view({"available": False, "reason": "no results"}, {}, [])
        self.assertEqual(view, {"available": False, "reason": "no results"})


class LdRegistryVocabularyTests(unittest.TestCase):
    def test_import_rejects_drift_in_registry_kinds_and_store_statuses_even_with_optimization(self) -> None:
        for change, diagnostic in (
            ("record.KINDS += ('new_store',)", "LD resource kinds"),
            ("panels.PANEL_KIND = 'new_panel'", "LD resource kinds"),
            ("record.STATUSES += ('available',)", "LD Store statuses"),
        ):
            with self.subTest(change=change):
                code = f"from ld_registry import panels, record; {change}; import project_site.stores_view"
                done = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True, check=False)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(f"RuntimeError: {diagnostic}", done.stderr)


class LatestRunTests(Fixture):
    def test_a_store_the_newest_run_leaves_out_says_so_above_the_older_run_shown(self) -> None:
        doc = json.loads(json.dumps(self.doc["yardstick"]))
        del doc["runs"][-1]["stores"]["OGS-00002"]
        view = stores_view.yardstick_view(doc, {}, [])
        by_store = {s["store_id"]: s for s in view["stores"]}
        self.assertEqual(by_store["OGS-00002"]["not_in_latest"], "not in the latest run (2026-11-17)")
        self.assertEqual(by_store["OGS-00002"]["date"], "2026-11-05")
        self.assertIsNone(by_store["OGS-00001"]["not_in_latest"])

    def test_a_store_the_newest_run_lists_as_pending_says_so_too(self) -> None:
        doc = json.loads(json.dumps(self.doc["yardstick"]))
        doc["runs"][-1]["stores"]["OGS-00002"] |= {"status": "pending", "reason": "rebuilding", "measures": {}}
        by_store = {s["store_id"]: s for s in stores_view.yardstick_view(doc, {}, [])["stores"]}
        self.assertEqual(by_store["OGS-00002"]["not_in_latest"], "not in the latest run (2026-11-17)")
        self.assertEqual(by_store["OGS-00002"]["state"], "measured")

    def test_the_panel_wording_is_written_by_the_build(self) -> None:
        doc = json.loads(json.dumps(self.doc["yardstick"]))
        doc["runs"][-1]["stores"]["OGS-00002"] |= {"status": "pending", "reason": "rebuilding", "measures": {}}
        del doc["runs"][-1]["stores"]["OGS-00001"]
        by_store = {s["store_id"]: s for s in stores_view.yardstick_view(doc, {}, [])["stores"]}
        self.assertEqual(by_store["OGS-00002"]["notice"],
                         "not in the latest run (2026-11-17): this is the latest run that measured it.")
        self.assertIsNone(by_store["OGS-00002"]["pending"])
        pending = json.loads(json.dumps(doc))
        for run in pending["runs"]:
            run["stores"]["OGS-00002"] |= {"status": "pending", "reason": "rebuilding", "measures": {}}
        got = next(s for s in stores_view.yardstick_view(pending, {}, [])["stores"] if s["store_id"] == "OGS-00002")
        self.assertEqual(got["pending"], "Pending in its latest run: rebuilding.")

    def test_the_one_measure_table_says_which_are_facts(self) -> None:
        self.assertEqual([n for n, m in stores_view.MEASURE.items() if m.fact], ["peak_rss", "bytes_on_disk"])
        self.assertFalse(hasattr(stores_view, "UNTIMED"))

    def test_a_status_the_build_cannot_draw_is_a_raise_not_an_assert(self) -> None:
        code = ("import yardstick.result as r; r.STATUSES = r.STATUSES + ('paused',); "
                "import project_site.stores_view")
        done = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("say how each status is drawn", done.stderr)

    def test_the_states_the_build_draws_are_exactly_the_schemas(self) -> None:
        from yardstick import result

        self.assertEqual({k for k in stores_view.STATE} - {"absent"}, set(result.STATUSES))
        self.assertEqual(stores_view.state("absent")["label"], "not in this run")


class SplitTests(Fixture):
    """Seam 2: the Stores data carries no yardstick panel; the Benchmarking data does."""

    def test_stores_data_has_no_yardstick_and_benchmarking_carries_it(self) -> None:
        self.assertNotIn("yardstick", self.view)
        bench = stores_view.benchmarking_view(self.doc)["yardstick"]
        self.assertIn("trends", bench)
        self.assertIn("stores", bench)

    def test_an_uncollected_source_is_an_envelope_with_its_reason(self) -> None:
        bench = stores_view.benchmarking_view({"source": "stores", "available": False, "error": "gone"})
        self.assertEqual((bench["available"], bench["error"]), (False, "gone"))
        self.assertNotIn("yardstick", bench)


class TopHitsPathTests(Fixture):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.y = stores_view.benchmarking_view(cls.doc)["yardstick"]

    def test_the_latest_top_hits_row_says_how_it_was_answered(self) -> None:
        dense = next(s for s in self.y["stores"] if s["store_id"] == "OGS-00001")
        top = next(m for m in dense["measures"] if m["name"] == "top_hits")
        self.assertEqual(top["path"], "scan")
        phewas = next(m for m in dense["measures"] if m["name"] == "phewas_rsid")
        self.assertIsNone(phewas["path"])

    def test_a_trend_never_joins_an_index_point_to_a_scan_point(self) -> None:
        trend = next(t for t in self.y["trends"] if t["measure"] == "top_hits")
        svg = trend["svg"]
        self.assertEqual(len(re.findall(r'<circle class="pt', svg)), 3)
        lines = re.findall(r'<polyline class="line[^"]*" points="([^"]*)"', svg)
        self.assertEqual([len(line.split()) for line in lines], [2])  # the two index points; the scan point stands alone
        self.assertIn("via index", svg)
        self.assertIn("via scan", svg)


class FlagTests(Fixture):
    def test_the_veeam_window_and_a_load_over_a_quarter_of_the_cpus_mark_a_run(self) -> None:
        runs = {r["file"]: r for r in self.doc["yardstick"]["runs"]}
        self.assertEqual(stores_view.run_flags(runs["20261101T120000Z-0.3.2.json"]), [])
        self.assertEqual(stores_view.run_flags(runs["20261105T060000Z-0.3.3.json"]), ["taken in the Veeam window"])
        (loaded,) = stores_view.run_flags(runs["20261117T113000Z-0.10.0.json"])  # 70 on 224 CPUs is over 56
        self.assertIn("load average 70 over 56", loaded)

    def test_a_load_at_a_quarter_exactly_is_not_marked(self) -> None:
        run = {"cpu_count": 16, "load_average": {"before": [4, 1, 1], "after": [1, 1, 1]}, "veeam_window": False}
        self.assertEqual(stores_view.run_flags(run), [])
        run["load_average"]["after"] = [4.01, 1, 1]
        self.assertEqual(len(stores_view.run_flags(run)), 1)


class TrendTests(Fixture):
    """Seam 5: one point per engine version, and a flagged run is marked."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.trends = {t["measure"]: t for t in stores_view.benchmarking_view(cls.doc)["yardstick"]["trends"]}

    @staticmethod
    def points(svg: str) -> list[str]:
        return re.findall(r'<circle class="pt[^"]*"', svg)

    def test_one_point_per_engine_version_per_store(self) -> None:
        trend = self.trends["phewas_rsid"]
        self.assertEqual(trend["versions"], ["0.3.2", "0.3.3", "0.10.0"])
        self.assertEqual(len(self.points(trend["svg"])), 6)  # two Stores, three versions
        self.assertEqual([s["points"] for s in trend["series"]], [3, 3])

    def test_a_measure_only_the_newest_run_carries_has_one_point(self) -> None:
        trend = self.trends["lookup_100x100"]
        self.assertEqual(trend["versions"], ["0.10.0"])
        self.assertEqual(len(self.points(trend["svg"])), 2)

    def test_a_flagged_run_is_marked_and_the_others_are_not(self) -> None:
        trend = self.trends["phewas_rsid"]
        self.assertEqual(trend["flagged"], 4)  # the Veeam run and the loaded run, for both Stores
        self.assertEqual(trend["svg"].count('class="flag-ring"'), 4)
        self.assertEqual(len(re.findall(r'<circle class="pt[^"]*flagged"', trend["svg"])), 4)

    def test_a_version_run_twice_shows_one_point(self) -> None:
        doc = json.loads(json.dumps(self.doc["yardstick"]))
        again = json.loads(json.dumps(doc["runs"][1]))
        again["started_utc"], again["file"] = "2026-11-06T06:00:00Z", "again.json"
        doc["runs"].insert(2, again)
        trend = next(t for t in stores_view.yardstick_view(doc, {}, [])["trends"] if t["measure"] == "phewas_rsid")
        self.assertEqual(trend["versions"], ["0.3.2", "0.3.3", "0.10.0"])
        self.assertEqual(len(self.points(trend["svg"])), 6)

    def test_peak_memory_and_size_have_their_own_trends(self) -> None:
        self.assertEqual((self.trends["peak_rss"]["unit"], self.trends["bytes_on_disk"]["unit"]), ("MB", "bytes"))

    def test_the_svg_is_self_contained(self) -> None:
        svg = self.trends["phewas_rsid"]["svg"]
        self.assertTrue(svg.startswith("<svg ") and svg.endswith("</svg>"))
        self.assertNotRegex(svg, r"<script|href=|src=|http")


class HostPathTests(Fixture):
    def test_no_host_path_is_in_the_view(self) -> None:
        text = json.dumps(self.view)
        self.assertNotRegex(text, HOST_PATH)
        self.assertNotIn(str(self.root), text)
        self.assertIn("…/ukb-b", self.shown["OGS-00001"]["description"])

    def test_no_host_path_is_in_an_error(self) -> None:
        by_name = {m["name"]: m for m in next(s for s in stores_view.benchmarking_view(self.doc)["yardstick"]["stores"] if s["store_id"] == "OGS-00001")["measures"]}
        self.assertNotRegex(by_name["region_100kb"]["note"], HOST_PATH)

    def test_the_collected_registry_path_is_not_published(self) -> None:
        # The published `registry` is the repository's name, URL and commit, not where this run read it.
        self.assertEqual(sorted(self.view["registry"]), ["commit", "name", "stores_url", "url"])


class UnavailableTests(unittest.TestCase):
    def test_a_source_that_was_not_collected_says_why(self) -> None:
        view = stores_view.stores_view({"source": "stores", "available": False, "collected_at": None,
                                        "error": "CollectError: registry /data/x/stores is not a directory"})
        self.assertFalse(view["available"])
        self.assertNotRegex(view["error"], HOST_PATH)
        self.assertNotIn("inventory", view)


if __name__ == "__main__":
    unittest.main()
