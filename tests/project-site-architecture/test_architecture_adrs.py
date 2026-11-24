#!/usr/bin/env python3
"""Where an ADR is placed on the architecture (#418).

An ADR is placed by the code it cites (a path, or a dotted module name, resolved
through the claims) and by a component's name in its title. A component's name
that appears only in the body, however often, places nothing. The fixtures are in
`architecture_fixtures.py`, each ADR commented with what it is there to show.

Run from the repository root:
    python3 tests/project-site-architecture/test_architecture_adrs.py
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import architecture_fixtures as fx

from project_site.collect import architecture


def collect(test: unittest.TestCase) -> dict:
    root = Path(tempfile.mkdtemp(prefix="arch-"))
    test.addCleanup(__import__("shutil").rmtree, root, True)
    fx.make_repo(root / "registry", {**fx.REGISTRY_FILES, **fx.REGISTRY_ADRS})
    fx.make_repo(root / "engine", {**fx.ENGINE_FILES, **fx.ENGINE_ADRS})
    system = root / "system.yaml"
    system.write_text(fx.SYSTEM_YAML, encoding="utf-8")
    return architecture.collect(fx.repositories(root / "registry", root / "engine"), system_file=system)


class AdrPlacementTests(unittest.TestCase):
    def test_adrs_are_placed_by_cited_code_and_by_names_in_titles_only(self) -> None:
        placed = {(a["repo"], a["number"]): a["components"] for a in collect(self)["adrs"]}
        self.assertEqual(
            placed,
            {
                (fx.REGISTRY, "0001"): {"gen": "code"},
                (fx.REGISTRY, "0002"): {"gen": "code", "store": "code"},
                (fx.REGISTRY, "0003"): {"ogs": "title"},
                (fx.REGISTRY, "0004"): {},
                (fx.REGISTRY, "0005"): {"store": "code"},
                (fx.REGISTRY, "0006"): {"ogs": "title"},
                (fx.ENGINE, "0001"): {"query": "title"},
                (fx.ENGINE, "0002"): {"check": "code", "cli": "code"},
                (fx.ENGINE, "0003"): {},
                (fx.ENGINE, "0004"): {},
            },
        )

    def test_the_summary_counts_adrs_placed_of_all_and_lists_the_rest(self) -> None:
        result = collect(self)
        self.assertEqual((result["summary"]["adrs_placed"], result["summary"]["adrs_total"]), (7, 10))
        unplaced = [(a["repo"], a["number"]) for a in result["adrs"] if not a["components"]]
        self.assertEqual(unplaced, [(fx.REGISTRY, "0004"), (fx.ENGINE, "0003"), (fx.ENGINE, "0004")])

    def test_an_adr_carries_its_title_status_and_link(self) -> None:
        result = collect(self)
        by_key = {(a["repo"], a["number"]): a for a in result["adrs"]}
        cites = by_key[(fx.ENGINE, "0002")]
        self.assertEqual(cites["title"], "0002. Layers")
        self.assertEqual(cites["status"], "superseded")
        # At the commit read, from the one GitHub root (og-dev-hub#6), never `main`, which moves.
        commit = result["repos"][fx.ENGINE]["commit"]
        self.assertEqual(cites["url"], f"https://github.com/opengwas/opengwasdb/blob/{commit}/docs/adr/0002-cites.md")
        self.assertEqual(by_key[(fx.REGISTRY, "0001")]["status"], "current")


if __name__ == "__main__":
    unittest.main()
