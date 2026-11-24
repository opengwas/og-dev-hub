#!/usr/bin/env python3
"""The board's pages draw a private repository's epics and tickets only as a count (og-dev-hub#9).

The board lists issues of every repository, private ones too. A private
repository is drawn on the public site as its container only, so its epics,
tickets and milestones are counted, never named: no title, number, link or Next
text, and no page of their own. A repository the board names that `system.yaml`
does not list is treated as private, because a fallback must be safe.
Visibility comes from `system.yaml`, through the `architecture.json` the same
run collected from it, else from the file itself.

Run from the repository root:
    python3 tests/project-site-pages/test_private_board.py
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_project_site_pages import child, envelope, epic, milestone

from project_site import pages

# The private items themselves. A public item's own text may name a private issue, and is drawn as written.
PRIVATE_REFERENCES = ("ogdb-api#150", "ogdb-api#160", "ogld#19", "ogld-api#1", "ogdb-dashboard#5")
SECRETS = ("SECRET", "github.com/opengwas/ogld", "github.com/opengwas/ogdb-api", "github.com/opengwas/ogdb-dashboard")


def board() -> dict:
    public = epic("opengwasdb#58", "Hybrid layout", status="Active",
                  next_line="Land the reader; waiting ogdb-api#192 and opengwas/ogld#88", children=[
        child("opengwasdb#57", "A public ticket", blocked_by=[{"key": "ogdb-api#160", "state": "OPEN"}]),
        child("ogld#19", "SECRET ticket in ogld", blocked_by=[{"key": "opengwasdb#57", "state": "OPEN"}]),
    ])
    private = epic("ogdb-api#150", "SECRET epic of the Data API", status="Active", next_line="SECRET next step",
                   children=[child("ogdb-api#160", "SECRET ops-up.sh reports")])
    unlisted = epic("ogld-api#1", "SECRET epic of an unlisted repository", status="Todo")
    return envelope("board", project="opengwas/1", epics=[public, private, unlisted],
                    milestones=[milestone("opengwasdb#300", "Public milestone", 1, 2),
                                milestone("ogdb-dashboard#5", "SECRET milestone", 0, 3)],
                    items=[])


def architecture() -> dict:
    """Only what the board's view reads of it: which repositories `system.yaml` lists, and how visible each is."""
    repos = {name: {"name": name, "visibility": visibility, "planned": visibility is None}
             for name, visibility in (("opengwasdb", "public"), ("opengwasdb-stores", "public"), ("ogld", "private"),
                                      ("ogdb-api", "private"), ("ogdb-dashboard", "private"))}
    return envelope("architecture", repos=repos, model={}, components=[], edges=[], adrs=[], gaps={}, summary={})


class PrivateBoardTests(unittest.TestCase):
    def generate(self, *, with_architecture: bool = True) -> dict[str, str]:
        root = Path(tempfile.mkdtemp(prefix="private-board-"))
        self.addCleanup(__import__("shutil").rmtree, root, True)
        data, docs = root / "_data", root / "docs"
        data.mkdir()
        docs.mkdir()
        (data / "board.json").write_text(json.dumps(board()), encoding="utf-8")
        if with_architecture:
            (data / "architecture.json").write_text(json.dumps(architecture()), encoding="utf-8")
        written = pages.generate(docs=docs, data_dir=data)
        return {path.relative_to(docs).as_posix(): path.read_text(encoding="utf-8") for path in written}

    def test_no_page_names_a_private_or_unlisted_repositorys_epic_ticket_or_milestone(self) -> None:
        for with_architecture in (True, False):
            for name, page in self.generate(with_architecture=with_architecture).items():
                for secret in (*PRIVATE_REFERENCES, *SECRETS):
                    with self.subTest(source="architecture.json" if with_architecture else "system.yaml",
                                      page=name, secret=secret):
                        self.assertNotIn(secret, page)

    def test_no_page_is_generated_for_a_private_epic(self) -> None:
        written = self.generate()
        self.assertIn("epics/opengwasdb-58.qmd", written)
        self.assertEqual([name for name in written if name.startswith("epics/")], ["epics/opengwasdb-58.qmd"])

    def test_what_is_left_out_is_counted(self) -> None:
        written = self.generate()
        self.assertIn("2 epics in private repositories are not shown.", written["epics.qmd"])
        self.assertIn("1 ticket in a private repository is not shown.", written["epics/opengwasdb-58.qmd"])
        self.assertIn("1 milestone in a private repository is not shown.", written["index.qmd"])
        self.assertIn("1 epic in a private repository is not shown.", written["index.qmd"])  # the Active one

    def test_the_public_epic_is_drawn_whole(self) -> None:
        page = self.generate()["epics/opengwasdb-58.qmd"]
        self.assertIn("A public ticket", page)
        # Text authored on a public item passes through as written, private issue numbers and all (og-dev-hub#9).
        self.assertIn("Land the reader; waiting ogdb-api#192 and opengwas/ogld#88", page)


class VisibilityTests(unittest.TestCase):
    def test_one_predicate_calls_a_private_or_unlisted_repository_private(self) -> None:
        from project_site import architecture_public

        private = architecture_public.visibility({"opengwasdb": "public", "ogld": "private", "ogquery": None})
        self.assertEqual([r for r in ("opengwasdb", "ogld", "ogquery", "ogld-api") if private(r)], ["ogld", "ogld-api"])


if __name__ == "__main__":
    unittest.main()
