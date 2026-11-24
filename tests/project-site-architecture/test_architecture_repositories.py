#!/usr/bin/env python3
"""The collectors read every repository `system.yaml` lists (og-dev-hub#9).

Fixture repositories stand in for opengwasdb-stores, opengwasdb and four more:
`ogquery` (public, with a model, importing the engine), `ogld` (private, with a
model and an ADR), `opengwaspy` (public, no model), `opengwas-gateway` (whose
clone cannot be read) and `ogdb-api` (`visibility: null`, planned). Expected
values are literals written from the fixtures.

Run from the repository root:
    python3 tests/project-site-architecture/test_architecture_repositories.py
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import architecture_fixtures as fx

from project_site import staging
from project_site.collect import __main__ as command, architecture
from project_site.collect import architecture_model as model

OGQUERY_MODEL = """\
repo: opengwas/ogquery
components:
  - {id: oq_read, name: Light reads, container: engine, stages: [query], summary: Reads stores., paths: [src/ogquery/]}
"""
OGQUERY_FILES = {
    "docs/architecture/components.yaml": OGQUERY_MODEL,
    "src/ogquery/__init__.py": "",
    "src/ogquery/read.py": "from opengwasdb.store import paths\nimport ogquery.util\n",
    "src/ogquery/util.py": "",
    "README.md": "readme\n",
}
OGLD_MODEL = """\
repo: opengwas/ogld
components:
  - {id: ld_panels, name: Panel readers, container: engine, stages: [build], summary: Reads panels., paths: [ogld/genotypes/]}
"""
OGLD_FILES = {
    "docs/architecture/components.yaml": OGLD_MODEL,
    "ogld/__init__.py": "",
    "ogld/genotypes/read.py": "import os\n",
    "docs/adr/0001-secret-panel-layout.md": "# 0001. Secret panel layout\n\nSee ogld/genotypes/read.py.\n",
}
SYSTEM = fx.SYSTEM_SECTIONS.replace(
    "containers:\n", "containers:\n  - {id: ld_lib, name: LD library, repo: ogld, tech: Python, summary: LD code.}\n", 1) + """\
repos:
  - {name: opengwasdb-stores, visibility: public}
  - {name: opengwasdb, visibility: public}
  - {name: ogquery, visibility: public}
  - {name: ogld, visibility: private}
  - {name: opengwaspy, visibility: public}
  - {name: opengwas-gateway, visibility: public}
  - {name: ogdb-api, visibility: null}
"""


class World:
    """Every fixture repository, and the read handles of one run over them."""

    def __init__(self, test: unittest.TestCase, *, registry_files: dict[str, str] | None = None,
                 engine_files: dict[str, str] | None = None) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="arch-repos-"))
        test.addCleanup(shutil.rmtree, self.root, True)
        self.system = self.root / "system.yaml"
        self.system.write_text(SYSTEM, encoding="utf-8")
        fx.make_repo(self.root / "registry", registry_files or {**fx.REGISTRY_FILES, **fx.REGISTRY_ADRS}, branch="trunk")
        fx.make_repo(self.root / "engine", engine_files or {**fx.ENGINE_FILES, **fx.ENGINE_ADRS})
        fx.make_repo(self.root / "ogquery", OGQUERY_FILES)
        fx.make_repo(self.root / "ogld", OGLD_FILES)
        fx.make_repo(self.root / "opengwaspy", {"README.md": "py\n", "docs/adr/0001-client.md": "# 0001. A client\n"})
        self.repositories = staging.Repositories(
            checkouts={fx.REGISTRY: self.root / "registry"},
            git_dirs={fx.ENGINE: self.root / "engine", "ogquery": self.root / "ogquery", "ogld": self.root / "ogld",
                      "opengwaspy": self.root / "opengwaspy", "opengwas-gateway": self.root / "nowhere.git",
                      # Planned: a git directory is named, and still never read.
                      "ogdb-api": self.root / "engine"},
        )

    def collect(self) -> dict:
        return architecture.collect(self.repositories, system_file=self.system)


class EveryListedRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = World(unittest.TestCase())
        cls.result = cls.world.collect()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.world.root, True)

    def test_every_listed_repository_is_recorded_in_system_yamls_order(self) -> None:
        self.assertEqual(list(self.result["repos"]), [
            "opengwasdb-stores", "opengwasdb", "ogquery", "ogld", "opengwaspy", "opengwas-gateway", "ogdb-api"])
        self.assertEqual(self.result["repos"]["ogld"]["visibility"], "private")

    def test_a_planned_repository_is_drawn_and_never_read(self) -> None:
        planned = self.result["repos"]["ogdb-api"]
        self.assertTrue(planned["planned"])
        self.assertIsNone(planned["commit"])
        self.assertNotIn("ogdb-api", self.world.repositories.handles)
        self.assertNotIn("ogdb-api", self.result["gaps"])

    def test_a_repository_that_cannot_be_read_is_its_gap_with_gits_message_and_the_rest_is_collected(self) -> None:
        gap = self.result["gaps"]["opengwas-gateway"]
        self.assertIn("opengwas-gateway cannot be read", gap["unreadable"])
        self.assertIn("nowhere.git", gap["unreadable"])
        self.assertIsNone(gap["unclaimed"])
        self.assertEqual(self.result["repos"]["opengwas-gateway"]["error"], gap["unreadable"])
        self.assertEqual(len([c for c in self.result["components"] if c["repo"] == fx.ENGINE]), 5)

    def test_a_repository_without_a_model_is_a_gap_and_its_components_are_unknown(self) -> None:
        gap = self.result["gaps"]["opengwaspy"]
        self.assertTrue(gap["no_model"].startswith("docs/architecture/components.yaml is not in opengwaspy at main ("))
        self.assertIsNone(gap["unclaimed"])
        self.assertIsNone(gap["stale"])
        self.assertIs(self.result["repos"]["opengwaspy"]["model"], False)
        self.assertIsNone(self.result["files"]["opengwaspy"])
        self.assertIn("NO MODEL: opengwaspy", command._describe_architecture(self.result))

    def test_an_import_of_another_listed_repository_is_an_across_edge(self) -> None:
        across = [e for e in self.result["edges"] if e["scope"] == "across" and e["from_repo"] == "ogquery"]
        self.assertEqual(across, [{"from": "oq_read", "to": "store", "imports": 1, "scope": "across",
                                   "from_repo": "ogquery", "to_repo": "opengwasdb", "upward": False}])

    def test_the_seam_and_the_layering_report_what_they_did_with_two_repositories(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(
            {k: summary[k] for k in ("upward_edges", "upward_imports", "registry_to_engine_edges", "registry_to_engine_imports")},
            {"upward_edges": 3, "upward_imports": 3, "registry_to_engine_edges": 4, "registry_to_engine_imports": 5},
        )
        self.assertEqual(len(self.result["upward_imports"]), 3)
        self.assertEqual(self.result["baseline"]["measured"], 5)

    def test_adrs_are_collected_from_every_repository_read(self) -> None:
        repos = sorted({a["repo"] for a in self.result["adrs"]})
        self.assertEqual(repos, ["ogld", "opengwasdb", "opengwasdb-stores", "opengwaspy"])
        secret = next(a for a in self.result["adrs"] if a["repo"] == "ogld")
        self.assertEqual(secret["components"], {"ld_panels": "code"})
        self.assertEqual(secret["url"], "https://github.com/opengwas/ogld/blob/main/docs/adr/0001-secret-panel-layout.md")

    def test_one_fetch_is_attempted_per_repository_per_run(self) -> None:
        # The handles are the run's: asking again is the same handle, never a second read.
        handle = self.world.repositories.get(fx.ENGINE)
        self.assertIs(self.world.repositories.get(fx.ENGINE), handle)


class CodeRootsTests(unittest.TestCase):
    def test_the_roots_are_the_top_level_directories_the_claims_name(self) -> None:
        registry = model.claims_of(model.load_model(fx.REGISTRY_MODEL)["components"])
        engine = model.claims_of(model.load_model(fx.ENGINE_MODEL)["components"])
        self.assertEqual(model.code_roots(registry), {"src", "workflow", "tools"})
        self.assertEqual(model.code_roots(engine), {"opengwasdb"})
        self.assertEqual(model.code_roots([("STORES.md", "x"), ("stores/", "x")]), {"stores"})

    def test_code_is_a_code_suffix_or_a_snakefile_under_a_root(self) -> None:
        rule = model.code_rule([("workflow/run.sh", "a"), ("src/x/", "b")])
        self.assertEqual(
            [p for p in ("workflow/Snakefile", "workflow/a.smk", "src/x/y.R", "src/x/y.r", "src/x/y.md", "docs/a.py", "setup.py")
             if rule(p)],
            ["workflow/Snakefile", "workflow/a.smk", "src/x/y.R", "src/x/y.r"])


class MissingModelTests(unittest.TestCase):
    def test_opengwasdb_stores_without_a_model_is_a_gap_not_an_error(self) -> None:
        registry = {k: v for k, v in fx.REGISTRY_FILES.items() if k != "docs/architecture/components.yaml"}
        result = World(self, registry_files=registry).collect()
        self.assertIn("is not in opengwasdb-stores at HEAD", result["gaps"][fx.REGISTRY]["no_model"])
        self.assertIsNone(result["gaps"][fx.REGISTRY]["unclaimed"])
        self.assertNotIn(fx.REGISTRY, {c["repo"] for c in result["components"]})
        # Unknown, never 0: nothing of the seam was measured.
        self.assertIsNone(result["summary"]["registry_to_engine_imports"])
        self.assertIsNone(result["summary"]["registry_to_engine_edges"])
        self.assertIsNone(result["baseline"]["measured"])
        self.assertEqual(result["summary"]["upward_imports"], 3)

    def test_a_model_that_cannot_be_used_is_a_gap_naming_why(self) -> None:
        registry = {**fx.REGISTRY_FILES, "docs/architecture/components.yaml": "components: [unclosed\n"}
        gap = World(self, registry_files=registry).collect()["gaps"][fx.REGISTRY]
        self.assertIn("cannot be used", gap["no_model"])


class AdrCitationTests(unittest.TestCase):
    def test_a_citation_naming_a_listed_repository_is_recorded_on_the_citing_adr(self) -> None:
        engine = {**fx.ENGINE_FILES, **fx.ENGINE_ADRS,
                  "docs/adr/0003-none.md": "# 0003. Nothing\n\nAs opengwasdb-stores ADR 0072 decided, and nowhere ADR 0001.\n"}
        registry = {**fx.REGISTRY_FILES, "docs/adr/0072-bundles.md": "# 0072. Release Bundles\n"}
        result = World(self, registry_files=registry, engine_files=engine).collect()
        citing = next(a for a in result["adrs"] if (a["repo"], a["number"]) == (fx.ENGINE, "0003"))
        self.assertEqual(citing["cites"], [{"repo": "opengwasdb-stores", "number": "0072"}])
        self.assertEqual(next(a for a in result["adrs"] if a["number"] == "0072")["cites"], [])

    def test_the_longer_repository_name_wins_and_a_bare_number_is_no_citation(self) -> None:
        from project_site.collect.architecture_adrs import adr_citations

        names = ["opengwasdb", "opengwasdb-stores", "ogld"]
        self.assertEqual(adr_citations("opengwasdb-stores ADR 72; opengwasdb ADR 0039; ADR 0001; xogld ADR 0002", names),
                         [{"repo": "opengwasdb", "number": "0039"}, {"repo": "opengwasdb-stores", "number": "0072"}])


if __name__ == "__main__":
    unittest.main()
