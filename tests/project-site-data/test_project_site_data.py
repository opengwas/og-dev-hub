#!/usr/bin/env python3
"""The site data's collectors: the board, the Stores and the command that runs them (#389, og-dev-hub#15).

Each test is at a seam named in the spec, `docs/spec/project-site.md`. Expected
values are literals. Fixtures are built here or read from `fixtures/`; nothing
is read from `/data/opengwasdb/stores` and nothing is written outside a
temporary directory.

Run from the repository root:
    python3 tests/project-site-data/test_project_site_data.py
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import yaml
from pathlib import Path

from project_site import paths as site_paths
from project_site import staging
from project_site.collect import __main__ as site_data
from project_site.collect import board, common, stores

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestBoardCollector(unittest.TestCase):
    """`board.parse` over a response recorded once from the real API (fixtures/board-graphql.json)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = board.parse(json.loads((FIXTURES / "board-graphql.json").read_text()))
        cls.epics = {e["key"]: e for e in cls.data["epics"]}
        cls.milestones = {m["key"]: m for m in cls.data["milestones"]}

    def test_every_project_item_is_an_epic_a_milestone_or_other(self) -> None:
        self.assertEqual(
            (len(self.data["epics"]), len(self.data["milestones"]), len(self.data["items"])),
            (17, 2, 2),
        )
        self.assertEqual(sorted(i["key"] for i in self.data["items"]), ["opengwasdb-stores#312", "opengwasdb-stores#314"])

    def test_an_epic_carries_its_board_fields_and_sub_issue_progress(self) -> None:
        epic = self.epics["opengwasdb-stores#313"]
        self.assertEqual(
            {k: epic[k] for k in ("title", "url", "state", "status", "workstream", "priority", "sub_issues")},
            {
                "title": "Epic: Analysis catalog across all Stores",
                "url": "https://github.com/opengwas/opengwasdb-stores/issues/313",
                "state": "OPEN",
                "status": "Active",
                "workstream": "Interface",
                "priority": None,
                "sub_issues": {"total": 12, "completed": 11},
            },
        )
        self.assertTrue(epic["next"].startswith("9/10 merged on PR #353 · implementing #359"))
        self.assertEqual(self.epics["opengwasdb-stores#366"]["priority"], "P2 · Medium")

    def test_an_epic_without_an_issue_type_is_found_by_its_title(self) -> None:
        self.assertIn("opengwasdb-stores#214", self.epics)

    def test_an_epic_lists_its_sub_issues_and_their_blocked_by_edges(self) -> None:
        children = {c["key"]: c for c in self.epics["opengwasdb-stores#385"]["children"]}
        self.assertEqual(
            list(children),
            ["opengwasdb#333", "opengwasdb-stores#386", "opengwasdb-stores#387", "opengwasdb-stores#388",
             "opengwasdb-stores#389", "opengwasdb-stores#390", "opengwasdb-stores#391", "agent-skills#1"],
        )
        self.assertEqual(children["opengwasdb-stores#389"]["blocked_by"], [])
        self.assertEqual(
            children["opengwasdb-stores#391"]["blocked_by"],
            [
                {"key": "opengwasdb-stores#390", "state": "OPEN"},
                {"key": "opengwasdb-stores#389", "state": "OPEN"},
                {"key": "opengwasdb-stores#388", "state": "OPEN"},
            ],
        )
        self.assertEqual(
            children["opengwasdb-stores#387"],
            {
                "key": "opengwasdb-stores#387",
                "title": "Pin opengwasdb by release tag",
                "url": "https://github.com/opengwas/opengwasdb-stores/issues/387",
                "state": "OPEN",
                "cited": ["src/ogstores/paths.py"],
                "blocked_by": [{"key": "opengwasdb#333", "state": "OPEN"}],
            },
        )

    def test_a_milestone_checklist_is_read_from_its_boxes_only(self) -> None:
        lines = self.milestones["opengwasdb#292"]["lines"]
        self.assertEqual(len(lines), 10)
        self.assertEqual([line["checked"] for line in lines].count(True), 6)
        self.assertEqual(
            lines[1],
            {
                "checked": True,
                "text": "opengwas/opengwasdb-stores#282 stage 1 merged to `dev` (opengwas/opengwasdb-stores#299). Stage 2 is not required.",
                "refs": ["opengwasdb-stores#282", "opengwasdb-stores#299"],
            },
        )
        self.assertEqual(lines[0]["refs"], [])
        self.assertEqual(
            lines[5],
            {
                "checked": False,
                "text": "Hybrid: OGS-00011 (GWAS Catalog EUR) rebuilt with its 3,169 Analyses, opengwas/opengwasdb-stores#225",
                "refs": ["opengwasdb-stores#225"],
            },
        )

    def test_checklist_lines_follow_the_box_syntax_and_resolve_bare_refs(self) -> None:
        body = "\n".join([
            "Prose with a #5 reference and no box.",
            "- plain bullet #6",
            "* [x] star bullet #7",
            "- [X] upper #8 and other/repo#9 and opengwas/agent-skills#1",
            "- [ ] open",
            "  - [x] nested #10",
            "- [] no space",
        ])
        self.assertEqual(
            board.checklist(body, "opengwasdb-stores"),
            [
                {"checked": True, "text": "upper #8 and other/repo#9 and opengwas/agent-skills#1",
                 "refs": ["opengwasdb-stores#8", "agent-skills#1"]},
                {"checked": False, "text": "open", "refs": []},
                {"checked": True, "text": "nested #10", "refs": ["opengwasdb-stores#10"]},
            ],
        )


def repo_of(name: str = "opengwasdb-stores") -> dict:
    return {"nameWithOwner": f"opengwas/{name}"}


def child(number: int, blocked: list[tuple[int, bool]] | None = None, *, more: str | None = None) -> dict:
    """A sub-issue node; `more` is the cursor of a second page of its blockedBy edges."""
    nodes = [{"number": n, "state": "OPEN", "repository": repo_of()} for n, _ in (blocked or [])]
    return {
        "number": number, "title": f"T{number}", "url": f"https://x/{number}", "state": "OPEN",
        "repository": repo_of(),
        "blockedBy": {"pageInfo": {"hasNextPage": more is not None, "endCursor": more}, "nodes": nodes},
    }


def paged(nodes: list[dict], more: str | None = None) -> dict:
    return {"pageInfo": {"hasNextPage": more is not None, "endCursor": more}, "nodes": nodes}


class PagingGh:
    """A `gh` runner over a two-page project: the epic's sub-issues, and one sub-issue's blockers, each in two pages."""

    def __init__(self) -> None:
        self.queries: list[dict] = []

    def __call__(self, args: list[str], stdin: str | None = None) -> str:
        request = json.loads(stdin)
        variables = request["variables"]
        self.queries.append(variables)
        after = variables.get("after")
        if "projectV2" in request["query"]:
            epic = {
                "__typename": "Issue", "number": 7, "title": "Epic: paged", "url": "https://x/7", "state": "OPEN",
                "repository": repo_of(), "issueType": {"name": "Epic"}, "labels": {"nodes": []},
                "subIssuesSummary": {"total": 3, "completed": 0}, "closedAt": None, "parent": None,
            }
            node = {"content": epic, "fieldValues": {"nodes": []}}
            return json.dumps({"data": {"organization": {"projectV2": {"items": {
                "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [node]}}}}})
        if "e0:" in request["query"]:  # the aliased first look at every epic
            first = child(10, [(1, False)], more="b1")
            return json.dumps({"data": {"e0": {"issue": {"number": 7, "subIssues": paged([first, child(11)], "s1")}}}})
        if "subIssues" in request["query"]:
            assert after == "s1" and variables["number"] == 7, variables
            return json.dumps({"data": {"repository": {"issue": {"subIssues": paged([child(12)])}}}})
        assert after == "b1" and variables["number"] == 10, variables
        blockers = [{"number": 2, "state": "CLOSED", "repository": repo_of()}]
        return json.dumps({"data": {"repository": {"issue": {"blockedBy": paged(blockers)}}}})


class TestBoardEpicPurpose(unittest.TestCase):
    """An Epic's first paragraph is kept as `purpose`, and the rest of its body is dropped (#391)."""

    def test_an_epic_keeps_its_first_paragraph_and_no_later_one(self) -> None:
        raw = json.loads((FIXTURES / "board-graphql.json").read_text())
        key = raw["epics"][0]
        node = next(
            node
            for page in raw["project"]
            for node in page["data"]["organization"]["projectV2"]["items"]["nodes"]
            if f"{node['content']['repository']['nameWithOwner'].split('/')[-1]}#{node['content']['number']}" == key
        )
        node["content"]["body"] = (
            "## Why\n\nWhere OpenGWASDB stands, at a glance, for the owner.\n\n"
            "## Detail\n\nA later paragraph nobody needs on a page.\n"
        )

        data = board.parse(raw)

        epic = next(item for item in data["epics"] if item["key"] == key)
        self.assertEqual(epic["purpose"], "Where OpenGWASDB stands, at a glance, for the owner.")
        self.assertNotIn("A later paragraph nobody needs", json.dumps(data))
        self.assertNotIn('"body"', json.dumps(data))

    def test_a_body_of_headings_and_boxes_has_no_purpose(self) -> None:
        self.assertIsNone(board.purpose_of("## Exit criteria\n\n- [ ] one\n- [x] two\n"))
        self.assertIsNone(board.purpose_of(None))

    def test_a_fenced_block_is_skipped_whole_however_its_blank_lines_fall(self) -> None:
        """A code fence is not prose, and a blank line inside it does not end the fence (#391 review, item 3)."""
        body = (
            "```python\n"
            "def example():\n"
            "\n"
            "    print(\"example\")\n"
            "```\n"
            "\n"
            "The epic makes the example run on every render.\n"
        )
        self.assertEqual(board.purpose_of(body), "The epic makes the example run on every render.")

    def test_a_body_of_fences_alone_has_no_purpose(self) -> None:
        for body in (
            "```python\n\nprint(\"one\")\n```\n",
            "~~~\n\nprint(\"two\")\n~~~\n",
            "````\n```\n\nprint(\"three\")\n```\n````\n\n- [ ] a box, not prose\n",
            "```\nunclosed fence\n\nprint(\"four\")\n",
        ):
            with self.subTest(body=body):
                self.assertIsNone(board.purpose_of(body))

    def test_a_long_first_paragraph_is_cut_at_a_sentence(self) -> None:
        body = "The catalog lists every validated Store. " * 30
        purpose = board.purpose_of(body)
        self.assertLessEqual(len(purpose), board.PURPOSE_LIMIT)
        self.assertTrue(purpose.startswith("The catalog lists every validated Store."))
        self.assertTrue(purpose.endswith("validated Store."))

    def test_a_paragraph_with_no_sentence_end_is_cut_at_a_word(self) -> None:
        purpose = board.purpose_of("word " * 300)
        self.assertLessEqual(len(purpose), board.PURPOSE_LIMIT + 1)
        self.assertTrue(purpose.endswith("word…"))


class EpicBodyGh:
    """A `gh` runner whose project page holds an Epic, an ordinary issue and a Milestone, each with a body."""

    def __call__(self, args: list[str], stdin: str | None = None) -> str:
        request = json.loads(stdin)
        if "projectV2" in request["query"]:
            def node(number: int, title: str, body: str, **extra) -> dict:
                content = {
                    "__typename": "Issue", "number": number, "title": title, "url": f"https://x/{number}",
                    "state": "OPEN", "closedAt": None, "repository": repo_of(), "parent": None,
                    "labels": {"nodes": []}, "subIssuesSummary": {"total": 0, "completed": 0}, "body": body,
                    **extra,
                }
                return {"content": content, "fieldValues": {"nodes": []}}
            return json.dumps({"data": {"organization": {"projectV2": {"items": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    node(7, "Epic: one", "The epic's first paragraph.\n\nA second one.\n",
                         issueType={"name": "Epic"}),
                    node(8, "An ordinary issue", "Ordinary body.\n"),
                    node(9, "Milestone: one", "## Outcome\n\n- [ ] a line\n"),
                ],
            }}}}})
        return json.dumps({"data": {"e0": {"issue": {"number": 7, "subIssues": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}}}})


class TestBoardKeepsEpicBodiesForPurpose(unittest.TestCase):
    def test_fetch_keeps_an_epics_body_and_drops_every_other_issue_body(self) -> None:
        raw = board.fetch(EpicBodyGh())
        nodes = raw["project"][0]["data"]["organization"]["projectV2"]["items"]["nodes"]

        self.assertEqual(nodes[0]["content"]["body"], "The epic's first paragraph.\n\nA second one.\n")
        self.assertNotIn("body", nodes[1]["content"])
        self.assertIn("body", nodes[2]["content"])  # a Milestone's checklist is read from its body


class TestBoardPagination(unittest.TestCase):
    def test_every_page_of_sub_issues_and_blockers_is_read(self) -> None:
        gh = PagingGh()
        result = board.collect(gh)
        children = result["epics"][0]["children"]
        self.assertEqual([c["key"] for c in children], ["opengwasdb-stores#10", "opengwasdb-stores#11", "opengwasdb-stores#12"])
        self.assertEqual(
            children[0]["blocked_by"],
            [{"key": "opengwasdb-stores#1", "state": "OPEN"}, {"key": "opengwasdb-stores#2", "state": "CLOSED"}],
        )
        self.assertEqual([q.get("after") for q in gh.queries][-2:], ["s1", "b1"])

    def test_a_truncated_relationship_is_never_returned_as_complete(self) -> None:
        raw = json.loads((FIXTURES / "board-graphql.json").read_text())
        alias = next(iter(raw["children"]))
        raw["children"][alias]["issue"]["subIssues"]["pageInfo"] = {"hasNextPage": True, "endCursor": "x"}
        with self.assertRaisesRegex(common.CollectError, "sub-issues.*more pages"):
            board.parse(raw)
        raw = json.loads((FIXTURES / "board-graphql.json").read_text())
        with_edges = next(
            c for a in raw["children"].values() for c in a["issue"]["subIssues"]["nodes"] if c["blockedBy"]["nodes"]
        )
        with_edges["blockedBy"]["pageInfo"] = {"hasNextPage": True, "endCursor": "x"}
        with self.assertRaisesRegex(common.CollectError, "blocked-by.*more pages"):
            board.parse(raw)


# These suites never check manifest figures (`test_stores_view` does, with the real call), and the real one
# imports the engine (1.6 s), so `bundle.manifest_summary` is stubbed.
MANIFEST = {"n_built": 1, "n_excluded": 0, "median_sample_size": None, "n_with_sample_size": 0,
            "n_unparseable_sample_size": 0, "ancestry": {}}


def stub_manifest(case: unittest.TestCase) -> None:
    from ogstores import bundle as release_bundle

    patcher = mock.patch.object(release_bundle, "manifest_summary", return_value=MANIFEST)
    patcher.start()
    case.addCleanup(patcher.stop)


def write_store_bundle(registry: Path, store_id: str, release: dict, build: dict, validation: dict | None) -> None:
    root = registry / store_id
    root.mkdir(parents=True)
    (root / "release.yaml").write_text(yaml.safe_dump({"store_id": store_id, **release}))
    (root / "build.yaml").write_text(yaml.safe_dump({"store_id": store_id, **build}))
    (root / "analyses.tsv").write_text("analysis_id\nA1\n")
    if validation is not None:
        (root / "validation.yaml").write_text(yaml.safe_dump(validation))


class TestStoresCollector(unittest.TestCase):
    def setUp(self) -> None:
        stub_manifest(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.registry = Path(tmp.name) / "stores"
        self.registry.mkdir()
        write_store_bundle(
            self.registry, "OGS-00001",
            {"label": "eqtlgen-cis", "status": "built", "trial": True, "association_coverage": "cis",
             "access_posture": "public", "derived_from": None, "created_at": "2026-09-15T10:00:00Z",
             "description": "Trial eQTLGen.", "notes": "Built at 0.1.0."},
            {"layout": "ragged", "completion_state": "observed_only"},
            None,
        )
        write_store_bundle(
            self.registry, "OGS-00009",
            {"label": "ukb-b-full", "status": "validated", "association_coverage": "gwas",
             "access_posture": "public", "derived_from": None, "created_at": "2026-10-21T22:20:44Z",
             "accepted_at": "2026-10-21T22:23:58Z", "description": "Full UKB-B.",
             "notes": "Release Erratum: n_associations is null."},
            {"layout": "dense", "completion_state": "reference_completed"},
            {"status": "passed", "validated_at": "2026-10-23T19:04:59Z",
             "observed": {"n_analyses": 2514, "n_variants": 11191070, "n_associations": None, "store_bytes": None}},
        )
        # Not Store Releases: the by-label index, a README, and the emitter's staging area.
        (self.registry / "by-label").mkdir()
        (self.registry / ".staging").mkdir()
        (self.registry / "README.md").write_text("x")

    def test_each_registered_store_has_its_bundle_facts(self) -> None:
        result = stores.collect(self.registry)
        self.assertEqual([s["store_id"] for s in result["stores"]], ["OGS-00001", "OGS-00009"])
        first, second = result["stores"]
        self.assertEqual(first, {
            "store_id": "OGS-00001", "label": "eqtlgen-cis", "status": "built", "trial": True,
            "layout": "ragged", "completion_state": "observed_only", "association_coverage": "cis",
            "access_posture": "public", "derived_from": None, "superseded_by": None,
            "created_at": "2026-09-15T10:00:00Z", "accepted_at": None, "validated_at": None,
            "validation_status": None, "observed": None,
            "description": "Trial eQTLGen.", "notes": "Built at 0.1.0.", "problems": [],
        })
        self.assertEqual(second["trial"], False)
        self.assertEqual(second["accepted_at"], "2026-10-21T22:23:58Z")
        self.assertEqual(second["validated_at"], "2026-10-23T19:04:59Z")
        self.assertEqual(second["validation_status"], "passed")
        self.assertEqual(
            second["observed"],
            {"n_analyses": 2514, "n_variants": 11191070, "n_associations": None, "store_bytes": None},
        )

    def test_an_unreadable_fact_is_reported_on_its_store_and_stops_nothing(self) -> None:
        write_store_bundle(
            self.registry, "OGS-00002",
            {"label": "x", "status": "built", "trial": "yes", "association_coverage": "nonsense"},
            {"layout": "dense", "completion_state": "observed_only"}, None,
        )
        result = stores.collect(self.registry)
        bad = next(s for s in result["stores"] if s["store_id"] == "OGS-00002")
        self.assertIsNone(bad["trial"])
        self.assertIsNone(bad["association_coverage"])
        self.assertEqual(len(bad["problems"]), 2)
        self.assertEqual(len(result["stores"]), 3)

    def test_a_registry_that_is_not_a_directory_is_an_error(self) -> None:
        with self.assertRaises(common.CollectError):
            stores.collect(self.registry / "nowhere")


class TestSiteData(unittest.TestCase):
    def setUp(self) -> None:
        stub_manifest(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.data = self.tmp / "data"
        self.registry = self.tmp / "stores"
        self.registry.mkdir()
        # The architecture collector reads git, never the host's clone: a fixture repository for each side.
        self.checkout = self.tmp / "checkout"
        self.engine = self.tmp / "engine"
        for repo, model in ((self.checkout, "repo: opengwas/opengwasdb-stores\ncomponents: []\n"),
                            (self.engine, "repo: opengwas/opengwasdb\nlayers: []\ncomponents: []\n")):
            (repo / "docs" / "architecture").mkdir(parents=True)
            (repo / "docs" / "architecture" / "components.yaml").write_text(model)
            for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                         ["-c", "user.name=t", "-c", "user.email=t@e.org", "commit", "-q", "-m", "x"]):
                subprocess.run(["git", "-C", str(repo), *args], check=True)
        # The two repositories it lists, so no other is cloned (og-dev-hub#9).
        self.system = self.tmp / "system.yaml"
        self.system.write_text(
            "system: {name: S, summary: s}\npeople: []\nexternal: []\ncontainers: []\ncontainer_relations: []\n"
            "repos:\n  - {name: opengwasdb-stores, visibility: public}\n  - {name: opengwasdb, visibility: public}\n")

    def run_all(self, gh: common.GhRunner) -> tuple[list[dict], list[str]]:
        lines: list[str] = []
        results = site_data.run(
            self.data, gh=gh, registry=self.registry, out=lines.append,
            repositories=staging.Repositories(checkouts={"opengwasdb-stores": self.checkout}, git_dirs={"opengwasdb": self.engine}),
            system_file=self.system,
        )
        return results, lines

    def test_one_unavailable_source_is_recorded_and_the_others_are_intact(self) -> None:
        def gh(args: list[str], stdin: str | None = None) -> str:
            raise common.CollectError("gh api graphql exited 4: could not resolve host")

        results, lines = self.run_all(gh)
        by_source = {r["source"]: r for r in results}
        self.assertEqual(list(by_source), ["board", "stores", "architecture", "work"])
        self.assertFalse(by_source["board"]["available"])
        self.assertEqual(by_source["board"]["error"], "CollectError: gh api graphql exited 4: could not resolve host")
        self.assertEqual(
            sorted(k for k in by_source["board"] if k not in ("source", "available", "collected_at", "error")), []
        )
        for source in ("stores", "architecture"):
            self.assertTrue(by_source[source]["available"], source)
            self.assertIsNone(by_source[source]["error"], source)
        self.assertFalse(by_source["work"]["available"])  # the board it reads is down
        # Every source has its file, and the file is the result.
        self.assertEqual(sorted(p.name for p in self.data.iterdir()),
                         ["architecture.json", "board.json", "stores.json", "work.json"])
        self.assertEqual(json.loads((self.data / "board.json").read_text())["available"], False)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "UNAVAILABLE board: CollectError: gh api graphql exited 4: could not resolve host")
        self.assertEqual(lines[1], "stores: 0 stores")

    def test_the_sites_collection_is_the_architecture_and_the_stores_and_needs_no_gh(self) -> None:
        def gh(args: list[str], stdin: str | None = None) -> str:
            raise AssertionError("the site's collection called gh")

        lines: list[str] = []
        results = site_data.run(
            self.data, gh=gh, out=lines.append, public_only=True, system_file=self.system,
            repositories=staging.Repositories(checkouts={"opengwasdb-stores": self.checkout}, git_dirs={"opengwasdb": self.engine}))
        self.assertEqual([r["source"] for r in results], ["architecture", "stores"])
        self.assertTrue(results[0]["available"], results[0]["error"])
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["architecture.json", "stores.json"])

    def test_without_network_or_a_clone_the_registrys_sources_are_unavailable_and_the_rest_are_written(self) -> None:
        # og-dev-hub#7: the registry is read from the site's clone; with no clone and no
        # network, each source that reads it says so, and nothing raises.
        def gh(args: list[str], stdin: str | None = None) -> str:
            raise common.CollectError("gh: offline")

        with mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(self.tmp / "work")}), \
                mock.patch.object(site_paths, "GITHUB", str(self.tmp / "no-network")):
            results = site_data.run(self.data, gh=gh, out=lambda line: None, refresh=True, system_file=self.system)

        by_source = {r["source"]: r for r in results}
        self.assertEqual(list(by_source), ["board", "stores", "architecture", "work"])
        for source in ("stores",):
            self.assertFalse(by_source[source]["available"], source)
            self.assertIn("opengwasdb-stores", by_source[source]["error"], source)
        # og-dev-hub#9: a repository that cannot be cloned is that repository's gap, never the whole architecture.
        self.assertTrue(by_source["architecture"]["available"])
        self.assertIn("no-network", by_source["architecture"]["gaps"]["opengwasdb-stores"]["unreadable"])
        self.assertFalse(by_source["work"]["available"])  # the board it reads is down
        self.assertEqual(sorted(p.name for p in self.data.iterdir()),
                         ["architecture.json", "board.json", "stores.json", "work.json"])

    def test_an_unavailable_source_exits_0_unless_strict(self) -> None:
        down = [common.envelope("board", available=False, error="CollectError: offline"),
                common.envelope("stores", available=True, error=None, stores=[])]
        for argv, status in (([], 0), (["--strict"], 1)):
            with mock.patch.object(site_data, "run", return_value=down):
                self.assertEqual(site_data.main(["--data-dir", str(self.data), *argv]), status, argv)
        up = [common.envelope("stores", available=True, error=None, stores=[])]
        with mock.patch.object(site_data, "run", return_value=up):
            self.assertEqual(site_data.main(["--data-dir", str(self.data), "--strict"]), 0)

    def test_the_envelope_names_the_source_and_when_it_was_collected(self) -> None:
        result = common.collect_source("stores", lambda: {"stores": []})
        self.assertEqual(sorted(result), ["available", "collected_at", "error", "source", "stores"])
        self.assertRegex(result["collected_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_the_data_directory_defaults_to_docs_data_and_is_overridable(self) -> None:
        self.assertEqual(common.data_dir({}), common.DEFAULT_DATA_DIR)
        self.assertEqual(common.DEFAULT_DATA_DIR.parts[-2:], ("docs", "_data"))
        self.assertEqual(common.data_dir({"OPENGWASDB_SITE_DATA": "/x/y"}), Path("/x/y"))


if __name__ == "__main__":
    unittest.main()
