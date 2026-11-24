#!/usr/bin/env python3
"""The architecture collector: both repositories' models combined (#418).

Fixture repositories stand in for this repository and the engine. Expected
values are literals written from the fixtures in `architecture_fixtures.py`.

Run from the repository root:
    python3 tests/project-site-architecture/test_architecture_collector.py
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import architecture_fixtures as fx

from project_site import staging
from project_site.collect import __main__ as command, architecture, common
from project_site.collect.common import CollectError


class Fixture:
    def __init__(self, test: unittest.TestCase, engine_files: dict[str, str] | None = None,
                 registry_files: dict[str, str] | None = None) -> None:
        root = Path(tempfile.mkdtemp(prefix="arch-"))
        test.addCleanup(__import__("shutil").rmtree, root, True)
        self.registry = root / "registry"
        self.engine = root / "engine"
        self.system = root / "system.yaml"
        self.system.write_text(fx.SYSTEM_YAML, encoding="utf-8")
        self.registry_commit = fx.make_repo(self.registry, registry_files or fx.REGISTRY_FILES, branch="trunk")
        self.engine_commit = fx.make_repo(self.engine, engine_files or fx.ENGINE_FILES)

    def collect(self) -> dict:
        return architecture.collect(staging.registry_root(self.registry), engine_git=self.engine, engine_ref="main",
                                  system_file=self.system)


class CombinedModelTests(unittest.TestCase):
    def test_components_of_both_repositories_are_listed_with_their_repository(self) -> None:
        result = Fixture(self).collect()
        by_id = {c["id"]: c["repo"] for c in result["components"]}
        self.assertEqual(
            by_id,
            {"cli": "engine", "query": "engine", "check": "engine", "store": "engine", "model": "engine",
             "gen": "registry", "ogs": "registry", "tools": "registry"},
        )
        self.assertEqual([layer["name"] for layer in result["model"]["layers"]],
                         ["Entry", "Use", "Storage", "Foundations"])

    def test_each_repository_records_the_ref_and_commit_read(self) -> None:
        fixture = Fixture(self)
        result = fixture.collect()
        self.assertEqual(result["engine"]["ref"], "main")
        self.assertEqual(result["engine"]["commit"], fixture.engine_commit)
        self.assertTrue(result["engine"]["model"])
        self.assertEqual(result["registry"]["commit"], fixture.registry_commit)

    def test_an_unclaimed_engine_file_and_a_stale_claim_are_gaps_not_errors(self) -> None:
        engine = dict(fx.ENGINE_FILES)
        engine["opengwasdb/orphan.py"] = "x = 1\n"
        engine["docs/architecture/components.yaml"] = fx.ENGINE_MODEL.replace(
            "paths: [opengwasdb/model/]", "paths: [opengwasdb/model/, opengwasdb/gone/]")
        result = Fixture(self, engine_files=engine).collect()
        self.assertEqual(result["gaps"]["engine"]["unclaimed"], ["opengwasdb/orphan.py"])
        self.assertEqual(result["gaps"]["engine"]["stale"],
                         [{"path": "opengwasdb/gone/", "component": "model"}])
        self.assertEqual(result["gaps"]["registry"],
                         {"unclaimed": [], "stale": [], "containers": [], "system_sections": []})

    def test_the_description_says_unknown_for_engine_gaps_without_a_model(self) -> None:
        from project_site.collect import __main__ as command

        engine = {k: v for k, v in fx.ENGINE_FILES.items() if k != "docs/architecture/components.yaml"}
        line = command._describe_architecture(Fixture(self, engine_files=engine).collect())
        self.assertIn("gaps registry 0/0 engine unknown (unclaimed/stale)", line)

    def test_an_engine_ref_without_a_model_says_so_and_keeps_this_repositorys_components(self) -> None:
        engine = {k: v for k, v in fx.ENGINE_FILES.items() if k != "docs/architecture/components.yaml"}
        fixture = Fixture(self, engine_files=engine)
        result = fixture.collect()
        self.assertFalse(result["engine"]["model"])
        self.assertEqual(result["engine"]["ref"], "main")
        self.assertEqual(result["engine"]["commit"], fixture.engine_commit)
        self.assertEqual([c["id"] for c in result["components"]], ["gen", "ogs", "tools"])
        # Unknown, not "no gaps": nothing was judged against missing claims.
        self.assertIsNone(result["gaps"]["engine"])
        self.assertEqual(result["gaps"]["registry"],
                         {"unclaimed": [], "stale": [], "containers": [], "system_sections": []})
        self.assertEqual(result["model"]["layers"], [])
        # Unknown, not empty: the layering cannot be measured without the model.
        self.assertIsNone(result["upward_imports"])
        self.assertIsNone(result["summary"]["upward_imports"])

    def test_component_size_is_counted_from_the_files_it_claims(self) -> None:
        result = Fixture(self).collect()
        store = next(c for c in result["components"] if c["id"] == "store")
        self.assertEqual((store["files"], store["lines"]), (3, 3))

    def test_every_code_file_is_read_and_its_lines_counted(self) -> None:
        result = Fixture(self).collect()
        ogs = next(c for c in result["components"] if c["id"] == "ogs")
        # src/ogs/run.py (2 lines), workflow/run.sh (2) and workflow/Snakefile (5)
        self.assertEqual((ogs["files"], ogs["lines"]), (3, 9))

    def test_a_file_that_does_not_parse_makes_the_source_fail_naming_the_path(self) -> None:
        engine = {**fx.ENGINE_FILES, "opengwasdb/store/broken.py": "def (:\n"}
        with self.assertRaises(CollectError) as caught:
            Fixture(self, engine_files=engine).collect()
        self.assertIn("opengwasdb/store/broken.py", str(caught.exception))

    def test_a_path_holding_a_newline_is_read_as_its_own_file(self) -> None:
        registry = {
            **fx.REGISTRY_FILES,
            "tools/z.py": "x = 1\n",
            "tools/z.py\nignored.py": "import os\nfrom opengwasdb.cli import main\nx = 1\n",
        }
        result = Fixture(self, registry_files=registry).collect()
        tools = next(c for c in result["components"] if c["id"] == "tools")
        self.assertEqual((tools["files"], tools["lines"]), (3, 5))  # run.py 1, z.py 1, the newline-named file 3
        edge = next(e for e in result["edges"] if (e["from"], e["to"]) == ("tools", "cli"))
        self.assertEqual(edge["imports"], 2)  # run.py's and the newline-named file's

    def test_the_tracked_code_paths_of_each_tree_are_listed_whole(self) -> None:
        registry = {**fx.REGISTRY_FILES, "tools/z.py\nignored.py": "x = 1\n"}
        files = Fixture(self, registry_files=registry).collect()["files"]
        self.assertEqual(files["registry"], [
            "src/gen/__init__.py", "src/gen/make.py", "src/ogs/run.py", "tools/run.py", "tools/z.py\nignored.py",
            "workflow/Snakefile", "workflow/run.sh"])
        self.assertEqual(files["engine"], [
            "opengwasdb/__init__.py", "opengwasdb/check/run.py", "opengwasdb/cli/__init__.py", "opengwasdb/cli/main.py",
            "opengwasdb/model/__init__.py", "opengwasdb/model/enums.py", "opengwasdb/model/store/util.py",
            "opengwasdb/query/__init__.py", "opengwasdb/query/facade.py", "opengwasdb/store/__init__.py",
            "opengwasdb/store/paths.py", "opengwasdb/store/util.py"])

    def test_the_engine_commit_date_is_recorded(self) -> None:
        fixture = Fixture(self)
        committed = fx.git(fixture.engine, "show", "-s", "--format=%cI", "HEAD")
        self.assertEqual(fixture.collect()["engine"]["committed"], committed)


class SystemModelTests(unittest.TestCase):
    """og-dev-hub's system.yaml is the only system model (#8).

    The repositories are built once for the class: every test here only reads them.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="arch-system-"))
        cls.addClassCleanup(__import__("shutil").rmtree, cls.root, True)
        cls.engine = cls.root / "engine"
        fx.make_repo(cls.engine, fx.ENGINE_FILES)
        cls.system = cls.root / "system.yaml"
        cls.system.write_text(fx.SYSTEM_YAML, encoding="utf-8")
        old_sections = fx.REGISTRY_MODEL.replace("stages:", fx.SYSTEM_SECTIONS.replace("OpenGWAS", "OldName").replace(
            "ld_registry", "old_only") + "stages:", 1)
        unknown_container = fx.REGISTRY_MODEL.replace("name: Scripts\n    container: generation",
                                                      "name: Scripts\n    container: site")
        cls.results = {}
        for name, model in (("plain", fx.REGISTRY_MODEL), ("sections", old_sections), ("unknown", unknown_container)):
            registry = cls.root / name
            fx.make_repo(registry, {**fx.REGISTRY_FILES, "docs/architecture/components.yaml": model}, branch="trunk")
            cls.results[name] = cls.collect(registry)

    @classmethod
    def collect(cls, registry: Path, system: Path | None = None) -> dict:
        return architecture.collect(staging.registry_root(registry), engine_git=cls.engine, engine_ref="main",
                                    system_file=system or cls.system)

    def test_the_models_system_keys_are_systems_yamls_and_the_stages_are_the_registrys(self) -> None:
        model = self.results["plain"]["model"]
        self.assertEqual(model["system"], {"name": "OpenGWAS", "summary": "The system."})
        self.assertEqual([c["id"] for c in model["containers"]], ["engine", "generation", "ld_registry"])
        self.assertEqual([p["id"] for p in model["people"]], ["curator"])
        self.assertEqual([x["id"] for x in model["external"]], ["sources"])
        self.assertEqual(model["container_relations"][2], ["ld_registry", "sources", "reads"])
        self.assertEqual([s["id"] for s in model["stages"]], ["build", "query"])

    def test_a_broken_system_yaml_raises_naming_the_problem(self) -> None:
        broken = self.root / "broken.yaml"
        broken.write_text(fx.SYSTEM_YAML.replace('[ld_registry, sources, "reads"]',
                                                 '[ld_registry, nowhere, "reads"]'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "system.yaml.*'nowhere'"):
            self.collect(self.root / "plain", broken)

    def test_a_broken_system_yaml_makes_the_architecture_source_unavailable_naming_the_file(self) -> None:
        for name, text in (("syntax.yaml", "system: [unclosed\n"),
                           ("noname.yaml", fx.SYSTEM_YAML.replace("name: Engine, ", ""))):
            broken = self.root / name
            broken.write_text(text, encoding="utf-8")
            result = common.collect_source("architecture", lambda: self.collect(self.root / "plain", broken))
            self.assertIs(result["available"], False)
            self.assertIn("system.yaml", result["error"])

    def test_system_sections_left_in_a_components_file_are_ignored_and_reported(self) -> None:
        result = self.results["sections"]
        self.assertEqual(result["gaps"]["registry"]["system_sections"],
                         ["system", "people", "external", "containers", "container_relations"])
        self.assertEqual(result["model"]["system"]["name"], "OpenGWAS")
        self.assertNotIn("old_only", [c["id"] for c in result["model"]["containers"]])
        self.assertEqual(len(result["components"]), 8)  # the rest is collected
        self.assertIn("SYSTEM GAPS: registry system sections ignored: system, people, external, containers, "
                      "container_relations (system sections belong in og-dev-hub's `system.yaml`)",
                      command._describe_architecture(result))
        self.assertEqual(result["gaps"]["engine"]["system_sections"], [])

    def test_a_component_naming_a_container_system_yaml_lacks_is_a_gap_naming_both(self) -> None:
        result = self.results["unknown"]
        self.assertEqual(result["gaps"]["registry"]["containers"], [{"component": "tools", "container": "site"}])
        self.assertEqual(result["gaps"]["engine"]["containers"], [])
        self.assertIn("registry tools names container site, which `system.yaml` does not have",
                      command._describe_architecture(result))


class UpwardImportTests(unittest.TestCase):
    def test_each_upward_import_is_listed_by_file_and_name_with_components_and_layers(self) -> None:
        result = Fixture(self).collect()
        self.assertEqual(
            result["upward_imports"],
            [
                {"file": "opengwasdb/model/enums.py", "name": "opengwasdb.store.util",
                 "from": "model", "to": "store", "from_layer": 0, "to_layer": 1},
                {"file": "opengwasdb/query/facade.py", "name": "opengwasdb.cli.main",
                 "from": "query", "to": "cli", "from_layer": 2, "to_layer": 3},
                {"file": "opengwasdb/store/paths.py", "name": "opengwasdb.query.facade",
                 "from": "store", "to": "query", "from_layer": 1, "to_layer": 2},
            ],
        )


class RefreshTests(unittest.TestCase):
    def clone(self, fixture: Fixture, origin: str) -> Path:
        bare = fixture.engine.parent / "engine.git"
        fx.git(fixture.engine, "clone", "-q", "--bare", str(fixture.engine), str(bare))
        fx.git(bare, "remote", "set-url", "origin", origin)
        return bare

    def test_a_refresh_that_fails_is_recorded_with_gits_error(self) -> None:
        fixture = Fixture(self)
        bare = self.clone(fixture, str(fixture.engine.parent / "no-such-origin"))
        result = architecture.collect(staging.registry_root(fixture.registry), engine_git=bare, refresh_engine=True)
        self.assertFalse(result["engine"]["refresh"]["ok"])
        self.assertIn("no-such-origin", result["engine"]["refresh"]["error"])
        self.assertEqual(result["engine"]["commit"], fixture.engine_commit)

    def test_a_refresh_that_works_reads_the_new_main(self) -> None:
        fixture = Fixture(self)
        bare = self.clone(fixture, str(fixture.engine))
        (fixture.engine / "opengwasdb" / "store" / "extra.py").write_text("x = 1\n")
        fx.git(fixture.engine, "add", "opengwasdb/store/extra.py")
        fx.git(fixture.engine, "-c", "user.name=t", "-c", "user.email=t@e.org", "commit", "-q", "-m", "more")
        head = fx.git(fixture.engine, "rev-parse", "HEAD")
        result = architecture.collect(staging.registry_root(fixture.registry), engine_git=bare, refresh_engine=True)
        self.assertEqual(result["engine"]["refresh"], {"ok": True, "error": None})
        self.assertEqual(result["engine"]["commit"], head)
        self.assertNotEqual(head, fixture.engine_commit)

    def test_no_refresh_is_recorded_as_not_attempted(self) -> None:
        self.assertIsNone(Fixture(self).collect()["engine"]["refresh"])


if __name__ == "__main__":
    unittest.main()
