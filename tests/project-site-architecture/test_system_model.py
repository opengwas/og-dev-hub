#!/usr/bin/env python3
"""The loader of og-dev-hub's `system.yaml`, the one system model (#8).

The real file is read through the loader, so CI fails on a broken `system.yaml`.

Run from the repository root:
    python3 tests/project-site-architecture/test_system_model.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from project_site import paths
from project_site.collect import architecture_model as model

GOOD = """\
system: {name: S, summary: The system.}
people: [{id: p, name: P, summary: x}]
external: [{id: x, name: X, summary: x}]
containers: [{id: a, name: A, repo: r, tech: t, summary: s}, {id: b, name: B, repo: null, tech: t, summary: s}]
container_relations: [[p, a, "uses"], [a, x, "reads"]]
repos: [{name: r, visibility: public}]
"""


def broken(**changes) -> str:
    doc = yaml.safe_load(GOOD)
    for key, value in changes.items():
        if value is KeyError:
            del doc[key]
        else:
            doc[key] = value
    return yaml.safe_dump(doc)


class LoadSystemTests(unittest.TestCase):
    def test_the_real_system_yaml_loads(self) -> None:
        system = model.load_system((paths.repo_root() / "system.yaml").read_text(encoding="utf-8"))
        self.assertEqual(system["system"]["name"], "OpenGWAS")
        self.assertEqual(len(system["containers"]), 17)
        self.assertIn("ld_registry", {c["id"] for c in system["containers"]})
        self.assertEqual(system["repos"][0]["name"], "opengwasdb")

    def test_a_good_file_loads_with_its_repos(self) -> None:
        self.assertEqual(model.load_system(GOOD)["repos"], [{"name": "r", "visibility": "public"}])

    def test_a_missing_key_is_named(self) -> None:
        for key in ("system", "people", "external", "containers", "container_relations"):
            with self.assertRaisesRegex(ValueError, f"system.yaml.*`{key}`"):
                model.load_system(broken(**{key: KeyError}))

    def test_a_key_of_the_wrong_shape_is_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "`containers`"):
            model.load_system(broken(containers={"id": "a"}))
        with self.assertRaisesRegex(ValueError, "`system`"):
            model.load_system(broken(system=[]))
        with self.assertRaisesRegex(ValueError, "`container_relations`.*\\[from, to, text\\]"):
            model.load_system(broken(container_relations=[["p", "a"]]))

    def test_a_yaml_syntax_error_names_the_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "system.yaml is not valid YAML"):
            model.load_system("system: [unclosed\n")

    def test_the_architecture_model_names_what_it_is_when_it_is_not_yaml(self) -> None:
        with self.assertRaisesRegex(ValueError, "the architecture model is not valid YAML"):
            model.load_model("components: [unclosed\n")

    def test_what_the_pages_index_is_checked_by_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "`containers`.*`id` and a `name`"):
            model.load_system(broken(containers=[{"id": "a", "repo": "r"}]))
        with self.assertRaisesRegex(ValueError, "`people`.*`id` and a `name`"):
            model.load_system(broken(people=[{"id": "p"}]))
        with self.assertRaisesRegex(ValueError, "`external`.*`id` and a `name`"):
            model.load_system(broken(external=[{"name": "X"}]))
        with self.assertRaisesRegex(ValueError, "`system`.*`name` and a `summary`"):
            model.load_system(broken(system={"name": "S"}))
        with self.assertRaisesRegex(ValueError, "`system`.*`name` and a `summary`"):
            model.load_system(broken(system={"summary": "The system."}))

    def test_one_reader_reads_this_checkouts_file_or_names_one_it_cannot_read(self) -> None:
        # og-dev-hub#6: the collector, the command line and the public view read system.yaml through it.
        from project_site import paths

        self.assertEqual(paths.system_file(), paths.repo_root() / "system.yaml")
        self.assertEqual(model.read_system()["system"]["name"], "OpenGWAS")
        with self.assertRaisesRegex(ValueError, "system.yaml cannot be read: .*no-such-dir"):
            model.read_system(Path("/no-such-dir/system.yaml"))

    def test_an_id_that_is_not_text_is_refused_as_a_models_is(self) -> None:
        # og-dev-hub#9: one entity check for system.yaml and the components files, with one rule.
        with self.assertRaisesRegex(ValueError, "system.yaml: `containers` #0 has no `id` of text"):
            model.load_system(broken(containers=[{"id": 5, "name": "Five", "repo": "r"}]))
        with self.assertRaisesRegex(ValueError, "component #0 has no `id` of text"):
            model.load_model("components:\n  - {id: 5, name: Five}\n")

    def test_a_duplicate_id_across_people_external_and_containers_is_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate id 'a'"):
            model.load_system(broken(people=[{"id": "a", "name": "P", "summary": "x"}]))

    def test_a_relation_to_an_unknown_id_is_named(self) -> None:
        with self.assertRaisesRegex(ValueError, "'nowhere'"):
            model.load_system(broken(container_relations=[["p", "nowhere", "uses"]]))

    def test_text_that_is_not_a_mapping_is_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "system.yaml"):
            model.load_system("- a\n")


if __name__ == "__main__":
    unittest.main()
