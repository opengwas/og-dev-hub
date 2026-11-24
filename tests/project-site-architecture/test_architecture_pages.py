#!/usr/bin/env python3
"""The Pipeline and Structure and health pages (#418).

Both pages are written from `architecture.json`, the architecture collector's
file, so the fixture here is a small literal in the shape
`docs/spec/project-site.md` documents. One test renders the Structure page with
Quarto to see that the `{dot}` cells become drawings; it is skipped without it.

Run from the repository root:
    python3 tests/project-site-architecture/test_architecture_pages.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from project_site import pages

QUARTO = shutil.which("quarto")
COLLECTED = "2026-11-02T12:00:00Z"
ENGINE_COMMIT = "abcdef0123456789abcdef0123456789abcdef01"


def comp(cid: str, name: str, repo: str, stages: list[str], *, layer: int | None = None,
         container: str = "engine", files: int = 3, lines: int = 100) -> dict:
    return {"id": cid, "name": name, "repo": repo, "container": container, "layer": layer, "stages": stages,
            "summary": f"{name} summary.", "paths": [], "files": files, "lines": lines, "tracked": files}


ENGINE, STORES = "opengwasdb", "opengwasdb-stores"


def edge(src: str, dst: str, imports: int, scope: str, upward: bool = False) -> dict:
    """An edge within the engine (`engine`), within opengwasdb-stores (`registry`), or across the seam (`registry_to_engine`)."""
    if scope == "registry_to_engine":
        return {"from": src, "to": dst, "imports": imports, "scope": "across", "from_repo": STORES, "to_repo": ENGINE,
                "upward": upward}
    return {"from": src, "to": dst, "imports": imports, "scope": "within", "repo": ENGINE if scope == "engine" else STORES,
            "upward": upward}


def adr(repo: str, number: str, title: str, components: dict[str, str], cites: list[dict] | None = None) -> dict:
    return {"repo": repo, "number": number, "path": f"docs/adr/{number}-x.md", "title": title,
            "status": "current", "url": f"https://github.com/opengwas/{repo}/blob/main/docs/adr/{number}-x.md",
            "components": components, "cites": cites or []}


def repo(name: str, *, ref: str = "main", commit: str | None = None, model: bool | None = True, **more) -> dict:
    return {"name": name, "visibility": "public", "status": None, "planned": False, "url": f"https://github.com/opengwas/{name}",
            "ref": ref, "commit": commit, "committed": None, "refresh": None, "source_root": "", "model": model,
            "note": None, "error": None, **more}


def architecture(*, engine_model: bool = True) -> dict:
    engine = [
        comp("query", "Query", ENGINE, ["query"], layer=2),
        comp("check", "Checks", ENGINE, ["build"], layer=2),
        comp("store", "Store envelope", ENGINE, ["build"], layer=1),
        comp("model", "Store contract model", ENGINE, ["build", "query"], layer=0),
    ] if engine_model else []
    return {
        "source": "architecture", "available": True, "collected_at": COLLECTED, "error": None,
        "repos": {
            STORES: repo(STORES, ref="HEAD", commit="1111111111111111"),
            ENGINE: repo(ENGINE, commit=ENGINE_COMMIT, committed="2026-11-01T09:30:00+00:00", refresh={"ok": True, "error": None},
                         model=engine_model,
                         note=None if engine_model else f"docs/architecture/components.yaml is not in opengwasdb at main ({ENGINE_COMMIT[:12]})"),
            "ogquery": repo("ogquery", model=None, planned=True, visibility=None, ref=None),
            "opengwaspy": repo("opengwaspy", commit="2" * 40, model=False,
                               note="docs/architecture/components.yaml is not in opengwaspy at main (222222222222)"),
        },
        "model": {
            "system": {"name": "OpenGWASDB", "summary": "The system."},
            "people": [{"id": "curator", "name": "Curator", "summary": "Runs builds."}],
            "external": [{"id": "sources", "name": "Sources", "summary": "Summary statistics."}],
            "containers": [
                {"id": "engine", "name": "opengwasdb", "repo": "opengwasdb", "tech": "Python", "summary": "Builds."},
                {"id": "generation", "name": "Manifest Generation", "repo": "opengwasdb-stores", "tech": "Python", "summary": "Makes manifests."},
                {"id": "ogquery", "name": "ogquery", "repo": "ogquery", "tech": "Python", "summary": "Reads."},
            ],
            "container_relations": [["curator", "generation", "runs"], ["generation", "engine", "builds with"]],
            "stages": [
                {"id": "build", "name": "Build", "summary": "Build a store", "repo": STORES},
                {"id": "query", "name": "Query", "summary": "Look values up", "repo": STORES},
            ],
            "layers": {ENGINE: [{"layer": 2, "name": "Use"}, {"layer": 1, "name": "Storage"}, {"layer": 0, "name": "Foundations"}]}
            if engine_model else {},
        },
        "components": [comp("gen", "Manifest Generation", STORES, ["build"], container="generation"), *engine],
        "gaps": {STORES: {"unreadable": None, "no_model": None, "unclaimed": [], "stale": [], "containers": [], "system_sections": []},
                 ENGINE: {"unreadable": None, "no_model": None, "unclaimed": ["opengwasdb/orphan.py"],
                          "stale": [{"path": "opengwasdb/gone/", "component": "model"}], "containers": [], "system_sections": []}
                 if engine_model else {"unreadable": None, "no_model": "no model", "unclaimed": None, "stale": None,
                                       "containers": [], "system_sections": []},
                 "opengwaspy": {"unreadable": None, "no_model": "docs/architecture/components.yaml is not in opengwaspy at main (222222222222)",
                                "unclaimed": None, "stale": None, "containers": [], "system_sections": []}},
        "edges": [
            edge("check", "query", 1, "engine"),
            edge("model", "store", 2, "engine", upward=True),
            edge("query", "store", 4, "engine"),
            edge("store", "query", 3, "engine", upward=True),
            edge("gen", "store", 7, "registry_to_engine"),
            edge("gen", "model", 1, "registry_to_engine"),
        ] if engine_model else [],
        "adrs": [
            adr(STORES, "0001", "0001. Manifest Generation is one pipeline", {"gen": "code"}),
            adr(ENGINE, "0001", "0001. Query is layer free", {"query": "title"}),
            adr(ENGINE, "0003", "0003. Nothing", {}),
        ],
        "summary": {"edges": 6, "upward_edges": 2, "upward_imports": 5, "registry_to_engine_edges": 2 if engine_model else None,
                    "registry_to_engine_imports": 8, "adrs_total": 3, "adrs_placed": 2},
    }


def failed_refresh() -> dict:
    doc = architecture()
    doc["repos"][ENGINE]["refresh"] = {"ok": False, "error": "fatal: unable to access 'https://github.com/opengwas/opengwasdb/'"}
    return doc


def render(function, doc: dict | None) -> str:
    return function({"architecture": doc})


def section(page: str, heading: str) -> str:
    """The text under a `### N. heading` until the next heading of that level or above."""
    match = re.search(rf"^### \d+\. {re.escape(heading)}\n(.*?)(?=^#{{2,3}} |\Z)", page, re.S | re.M)
    assert match, f"no section {heading!r}"
    return match.group(1)


def dot_cells(page: str) -> list[str]:
    return re.findall(r"```\{dot\}\n(.*?)\n```", page, re.S)


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = render(pages.render_pipeline, architecture())

    def test_each_stage_lists_its_components_and_each_components_own_adrs(self) -> None:
        build = section(self.page, "Build")
        for name in ("Manifest Generation", "Checks", "Store envelope", "Store contract model"):
            self.assertIn(name, build)
        link = "[0001. Manifest Generation is one pipeline](https://github.com/opengwas/opengwasdb-stores/blob/main/docs/adr/0001-x.md)"
        # nested under its component, before the next component starts
        # Each name opens the component's panel (#435).
        self.assertIn(f"- **[Manifest Generation](#component-gen)** (opengwasdb-stores; 3 files, 100 lines): Manifest Generation summary.\n  - {link}", build)
        self.assertLess(build.index(link), build.index("**[Checks](#component-check)**"))
        self.assertNotIn("Query is layer free", build)
        query = section(self.page, "Query")
        self.assertIn("- **[Query](#component-query)** (opengwasdb; 3 files, 100 lines): Query summary.\n  - [0001. Query is layer free]", query)
        self.assertIn("Store contract model", query)

    def test_an_adr_placed_nowhere_is_listed(self) -> None:
        # Up to the component panel's data (#435), which holds every ADR placed on a component.
        tail = self.page.split("## ADRs the map cannot place", 1)[1].split("```{=html}", 1)[0]
        self.assertIn("0003. Nothing", tail)
        self.assertNotIn("Query is layer free", tail)

    def test_the_page_says_what_is_written_by_hand_and_what_is_measured(self) -> None:
        self.assertIn("Written by hand", self.page)
        self.assertIn("Measured", self.page)
        self.assertIn("stages", self.page.split("Written by hand", 1)[1].split("Measured", 1)[0])

    def test_an_engine_without_a_model_says_so_and_keeps_the_other_repositorys_components(self) -> None:
        page = render(pages.render_pipeline, architecture(engine_model=False))
        self.assertIn("> **2 repositories have no architecture model yet**: opengwasdb, opengwaspy. Their components, "
                      "layers and imports are unknown, not none", page)
        self.assertIn("Manifest Generation", section(page, "Build"))

    def test_the_engine_commit_and_its_date_are_stated(self) -> None:
        for function in (pages.render_pipeline, pages.render_structure):
            page = render(function, architecture())
            self.assertIn("opengwasdb `main` at `abcdef012345` (committed 2026-11-01T09:30:00+00:00)", page)
            self.assertNotIn("refresh failed", page)

    def test_a_failed_refresh_is_a_visible_line_with_gits_error(self) -> None:
        for function in (pages.render_pipeline, pages.render_structure):
            page = render(function, failed_refresh())
            self.assertIn("> **The opengwasdb refresh failed**: fatal: unable to access", page)
            self.assertIn("the `main` its clone already had", page)

    def test_a_failed_registry_refresh_is_a_visible_line_too(self) -> None:
        # og-dev-hub#7: the registry is read from the site's clone, refreshed like the engine's.
        doc = architecture()
        doc["repos"][STORES]["refresh"] = {"ok": False, "error": "fatal: unable to access 'https://github.com/opengwas/opengwasdb-stores/'"}
        for function in (pages.render_pipeline, pages.render_structure):
            page = render(function, doc)
            self.assertIn("> **The opengwasdb-stores refresh failed**: fatal: unable to access", page)
            self.assertIn("the `HEAD` its clone already had (`111111111111`)", page)
            self.assertNotIn("The opengwasdb refresh failed", page)

    def test_an_unavailable_source_is_the_sites_usual_notice(self) -> None:
        failed = {"source": "architecture", "available": False, "collected_at": COLLECTED,
                  "error": "CollectError: no ref main"}
        self.assertIn("> **Architecture data unavailable**: CollectError: no ref main; collected 2026-11-02T12:00:00Z.",
                      render(pages.render_pipeline, failed))
        self.assertIn("> **Architecture data unavailable**: `architecture.json` was not written",
                      render(pages.render_structure, None))


class StructureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page = render(pages.render_structure, architecture())
        self.cells = dot_cells(self.page)

    def test_it_draws_four_dot_cells(self) -> None:
        self.assertEqual(len(self.cells), 4)

    def test_the_engine_is_drawn_with_a_row_per_layer(self) -> None:
        engine = self.cells[2]
        self.assertIn('{ rank=same; "L2"; "query"; "check"; }', engine)
        self.assertIn('{ rank=same; "L1"; "store"; }', engine)
        self.assertIn('{ rank=same; "L0"; "model"; }', engine)

    def test_each_upward_edge_is_coloured_and_labelled_with_its_import_count(self) -> None:
        engine = self.cells[2]
        self.assertRegex(engine, r'"model" -> "store" \[[^\]]*color="#c0392b"[^\]]*label=" 2"')
        self.assertRegex(engine, r'"store" -> "query" \[[^\]]*color="#c0392b"[^\]]*label=" 3"')

    def test_same_layer_imports_are_dashed_and_downward_ones_are_not_drawn(self) -> None:
        engine = self.cells[2]
        self.assertRegex(engine, r'"check" -> "query" \[[^\]]*style=dashed[^\]]*label=" 1"')
        self.assertNotRegex(engine, r'"query" -> "store" \[(?![^\]]*invis)')  # 2 -> 1 follows the layering

    def test_the_seam_between_the_repositories_is_drawn_as_counts(self) -> None:
        registry = self.cells[3]
        self.assertRegex(registry, r'"gen" -> "repo:opengwasdb" \[[^\]]*label="8"')
        # The node is labelled from system.yaml's container, never written here (og-dev-hub#9).
        self.assertIn("opengwasdb (the engine)", registry)
        self.assertIn("## opengwasdb (the engine) by layer", self.page)
        self.assertIn("## opengwasdb-stores (Manifest Generation), and its imports of other repositories", self.page)

    def test_every_listed_repository_is_in_health_planned_and_without_a_model_as_gaps(self) -> None:
        claims = self.page.split("### Claims", 1)[1].split("### Layering", 1)[0]
        self.assertIn("- **ogquery**: planned, not created yet.", claims)
        self.assertIn("- **opengwaspy**: no model, so its components are unknown: docs/architecture/components.yaml "
                      "is not in opengwaspy at main (222222222222).", claims)
        self.assertIn("- **opengwasdb (the engine)**: 1 code files no component claims; 1 claims that match no tracked file.", claims)

    def test_a_planned_repositorys_container_is_drawn_dashed_and_marked(self) -> None:
        containers = self.cells[1]
        self.assertRegex(containers, r'"ogquery" \[style="rounded,filled,dashed"[^\]]*planned; Python')

    def test_imports_across_repositories_are_tabled_by_pair(self) -> None:
        self.assertIn("| opengwasdb-stores | opengwasdb | 8 | 2 |", self.page)

    def test_an_adr_citing_another_repositorys_adr_links_to_it(self) -> None:
        doc = architecture()
        doc["adrs"][1]["cites"] = [{"repo": STORES, "number": "0001"}, {"repo": "ogld", "number": "0004"}]
        page = render(pages.render_pipeline, doc)
        self.assertIn("; cites [opengwasdb-stores ADR 0001](https://github.com/opengwas/opengwasdb-stores/blob/main/"
                      "docs/adr/0001-x.md), ogld ADR 0004", page)

    def test_the_page_says_what_is_written_by_hand_and_what_is_measured(self) -> None:
        by_hand, measured = self.page.split("Written by hand", 1)[1].split("Measured", 1)
        self.assertIn("layers", by_hand)
        self.assertIn("imports", measured)

    def test_the_containers_diagram_draws_system_yamls_containers(self) -> None:
        doc = architecture()
        doc["model"]["containers"].append(
            {"id": "ld_registry", "name": "LD Store Registry", "repo": "opengwasdb-stores", "tech": "in git", "summary": "Records LD Stores."})
        doc["model"]["system"] = {"name": "OpenGWAS", "summary": "The system."}
        containers = dot_cells(render(pages.render_structure, doc))[1]
        self.assertIn('"ld_registry" [', containers)
        self.assertIn('subgraph cluster_system { label="OpenGWAS"', containers)

    def test_system_gaps_are_listed_in_health_and_do_not_stop_the_page(self) -> None:
        doc = architecture()
        doc["gaps"][STORES] |= {"system_sections": ["containers", "people"],
                                    "containers": [{"component": "yardstick", "container": "site"}]}
        page = render(pages.render_structure, doc)
        self.assertIn("  - System sections ignored: `containers`, `people` "
                      "(system sections belong in og-dev-hub's `system.yaml`)", page)
        self.assertIn("  - `yardstick` names container `site`, which `system.yaml` does not have", page)
        self.assertNotIn("System sections ignored", render(pages.render_structure, architecture()))

    def test_engine_gaps_are_listed_and_do_not_stop_the_page(self) -> None:
        self.assertIn("`opengwasdb/orphan.py`", self.page)
        self.assertIn("`opengwasdb/gone/` (claimed by `model`)", self.page)

    def test_an_engine_without_a_model_still_draws_the_other_repositorys_half(self) -> None:
        page = render(pages.render_structure, architecture(engine_model=False))
        self.assertIn("- **opengwasdb (the engine)**: no model, so its components are unknown", page)
        self.assertEqual(len(dot_cells(page)), 3)
        self.assertIn('"gen"', dot_cells(page)[2])

    def test_the_headline_numbers_are_stated(self) -> None:
        self.assertIn("opengwasdb (the engine): 2 edges (5 imports) go against the layering, of 4 edges between its components.", self.page)
        self.assertIn("8 imports from opengwasdb-stores into opengwasdb, across 2 component pairs.", self.page)


class HostileFactTests(unittest.TestCase):
    """A ref, path or error is data: shown as text, never obeyed as Markdown or HTML (docs/site.md, Adding a page 8)."""

    def pages(self) -> list[str]:
        doc = architecture()
        doc["repos"][ENGINE]["ref"] = "ma`in"
        doc["gaps"][ENGINE]["unclaimed"] = ["opengwasdb/a`|<b>.py"]
        doc["gaps"][ENGINE]["stale"] = [{"path": "opengwasdb/<i>x`/", "component": "mo`del"}]
        doc["repos"][ENGINE]["refresh"] = {"ok": False, "error": "bad `<b>` | thing"}
        return [re.sub(r"```\{dot\}.*?```", "", render(f, doc), flags=re.S)
                for f in (pages.render_pipeline, pages.render_structure)]

    def test_no_fact_reaches_the_page_as_raw_html(self) -> None:
        for page in self.pages():
            self.assertNotIn("<b>", page)
            self.assertNotIn("<i>", page)

    def test_a_path_with_a_backtick_and_a_pipe_is_shown_whole(self) -> None:
        structure = self.pages()[1]
        self.assertIn("<code>opengwasdb/a&#96;&#124;&lt;b&gt;.py</code>", structure)
        self.assertIn("opengwasdb <code>ma&#96;in</code> at", structure)


DOT = shutil.which("dot")


class DotEscapingTests(unittest.TestCase):
    """A fact inside a quoted DOT string or identifier is escaped for DOT, not for HTML (docs/site.md, Adding a page 8)."""

    def cells(self) -> list[str]:
        doc = architecture()
        doc["model"]["system"]["name"] = 'Sys "x" \\'
        doc["model"]["containers"][0]["id"] = 'en"g\\'
        doc["model"]["containers"][0]["name"] = 'Eng \\ "q"'
        doc["model"]["container_relations"] = [["curator", "generation", "ends in a backslash \\"],
                                               ["generation", 'en"g\\', 'says "hi" & <b>']]
        doc["components"][0]["container"] = 'en"g\\'
        return dot_cells(render(pages.render_structure, doc))

    def test_a_relation_label_ending_in_a_backslash_or_holding_a_quote_is_escaped_for_dot(self) -> None:
        containers = self.cells()[1]
        self.assertIn('label="ends in a backslash \\\\"', containers)
        self.assertIn('label="says \\"hi\\" & <b>"', containers)
        self.assertNotIn("&amp;", containers)
        self.assertIn('label="Sys \\"x\\" \\\\"', containers)

    def test_a_cluster_name_made_from_an_id_is_quoted_and_escaped(self) -> None:
        self.assertIn('subgraph "cluster_en\\"g\\\\" {', self.cells()[3])
        self.assertIn('"en\\"g\\\\" [', self.cells()[1])

    @unittest.skipUnless(DOT, "Graphviz `dot` is not on PATH")
    def test_every_diagram_is_valid_dot(self) -> None:
        for cell in self.cells():
            done = subprocess.run([DOT, "-Tcanon"], input=cell, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)


@unittest.skipUnless(QUARTO, "Quarto is not on PATH; the render assertion needs it")
class QuartoRenderTests(unittest.TestCase):
    def test_the_dot_cells_become_drawings(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="arch-pages-"))
        self.addCleanup(shutil.rmtree, root, True)
        docs = root / "docs"
        docs.mkdir()
        (docs / "_quarto.yml").write_text("project:\n  type: website\n", encoding="utf-8")
        (docs / "index.qmd").write_text(pages._page("Structure", render(pages.render_structure, architecture())),
                                        encoding="utf-8")
        subprocess.run([QUARTO, "render", str(docs), "--output-dir", str(root / "out")],
                       check=True, capture_output=True, text=True)
        html = (root / "out" / "index.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(html.count("<svg"), 4)
        self.assertIn("FOUNDATIONS", html)
        self.assertIn(" 3", html)


if __name__ == "__main__":
    unittest.main()
