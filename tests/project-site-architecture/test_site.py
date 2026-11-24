#!/usr/bin/env python3
"""The static site: one page of built state, rendered from JSON the collectors write (og-dev-hub#15).

The fixture repositories are `test_architecture_repositories`' world: opengwasdb-stores
and opengwasdb with models, `ogquery` (public, with a model), `ogld` (private, with a
model, a stage and an ADR), `opengwaspy` (public, no model), `opengwas-gateway`
(unreadable) and `ogdb-api` (planned). The private repository is collected whole
here, as `pixi run architecture` collects it, so the build's one filter
(`architecture_public.public_view`) is what keeps it off the site.

Run from the repository root:
    python3 tests/project-site-architecture/test_site.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import architecture_fixtures as fx
from test_architecture_repositories import OGQUERY_FILES, SYSTEM, World

from project_site import site, staging
from project_site.collect import __main__ as command, common

CONTEXT = """\
# OpenGWAS

The whole platform. See [ADR 0001](docs/adr/0001-dev-hub-collects-and-owns-nothing.md)
and [GitHub](https://github.com/opengwas).

## The platform

**Dev Hub**:
The developers' view of _built state_.

- one
- two
"""

# Every string of the private repository the fixtures hold: its paths, component and
# stage, its ADR's title and file name. None may appear anywhere under `_site/`.
SECRETS = ("ogld/genotypes", "Panel readers", "ld_panels", "Secret LD stage", "ld_secret_stage",
           "Secret panel layout", "0001-secret-panel-layout")


def built(cleanup, documents: dict, *, context: str = CONTEXT) -> Path:
    """`_site/` built from `documents` (source name to collected file), in a directory `cleanup` removes."""
    root = Path(tempfile.mkdtemp(prefix="site-"))
    cleanup(shutil.rmtree, root, True)
    data = root / "data"
    for document in documents.values():
        common.write_source(data, document)
    (root / "CONTEXT.md").write_text(context, encoding="utf-8")
    site.build(data, root / "_site", context=root / "CONTEXT.md")
    return root / "_site"


def collected(result: dict) -> dict:
    return {"source": "architecture", "available": True, "collected_at": "2026-11-24T12:00:00Z", "error": None, **result}


def read(out: Path, name: str) -> dict:
    return json.loads((out / "data" / name).read_text(encoding="utf-8"))


class SiteWorld:
    """The fixture repositories once, with an ADR citing another repository's, and a glossary in ogquery."""

    def __init__(self) -> None:
        self.world = World(unittest.TestCase())
        # Two more containers: data (no repository) and a planned repository's, so the build decides those states too.
        self.world.system.write_text(SYSTEM.replace("containers:\n", "containers:\n"
            "  - {id: stores, name: GWAS Stores, repo: null, tech: Zarr, summary: The Stores.}\n"
            "  - {id: data_api, name: Data API, repo: ogdb-api, tech: service, summary: Serves queries.}\n", 1),
            encoding="utf-8")
        engine = {**fx.ENGINE_FILES, **fx.ENGINE_ADRS,
                  "docs/adr/0003-none.md": "# 0003. Nothing\n\nAs opengwasdb-stores ADR 0072 decided; ogld ADR 0001 too.\n"}
        registry = {**fx.REGISTRY_FILES, **fx.REGISTRY_ADRS, "docs/adr/0072-bundles.md": "# 0072. Release Bundles\n",
                    "CONTEXT.md": "# opengwasdb-stores\n"}
        self.architecture = collected(self.world.variant(
            registry=registry, engine=engine, ogquery={**OGQUERY_FILES, "CONTEXT.md": "# ogquery\n"}))
        self.out = built(unittest.addModuleCleanup, {"architecture": self.architecture})


_WORLD: list[SiteWorld] = []


def site_world() -> SiteWorld:
    if not _WORLD:
        _WORLD.append(SiteWorld())
        unittest.addModuleCleanup(shutil.rmtree, _WORLD[0].world.root, True)
    return _WORLD[0]


class BuiltSite(unittest.TestCase):
    """The site built once from the fixture world, for every class that only reads it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = site_world()
        cls.out = cls.world.out


class PageTests(BuiltSite):
    """Seam 1: `build` writes the page, a script per view and `data/*.json`, all by relative paths."""

    def test_the_page_its_stylesheet_and_a_script_per_view_are_written(self) -> None:
        for name in ("index.html", "style.css", "js/app.js", "js/architecture.js", "js/decisions.js", "js/context.js", "js/stores.js"):
            with self.subTest(name=name):
                self.assertTrue((self.out / name).is_file())
        self.assertEqual(sorted(p.name for p in (self.out / "data").iterdir()),
                         ["architecture.json", "context.json", "decisions.json", "stores.json"])

    def test_the_page_has_a_tab_per_view_and_each_view_has_its_own_content_section(self) -> None:
        page = (self.out / "index.html").read_text(encoding="utf-8")
        for view in ("architecture", "decisions", "context", "stores"):
            with self.subTest(view=view):
                self.assertIn(f'href="#{view}"', page)
                self.assertIn(f'id="pane-{view}"', page)
        for view in ("architecture", "decisions", "context", "stores"):
            self.assertIn(f'id="{view}-content"', page)
        self.assertNotIn("coming", page[page.index('id="pane-stores"'):])

    def test_every_script_stylesheet_and_data_path_is_relative(self) -> None:
        page = (self.out / "index.html").read_text(encoding="utf-8")
        for attribute in re.findall(r'(?:src|href)="([^"]*)"', page):
            with self.subTest(attribute=attribute):
                self.assertFalse(attribute.startswith("/"), attribute)
                if not attribute.startswith("#"):
                    self.assertTrue(attribute.startswith("https://github.com/") or "://" not in attribute, attribute)
        for script in (self.out / "js").iterdir():
            text = script.read_text(encoding="utf-8")
            with self.subTest(script=script.name):
                self.assertNotRegex(text, r"""fetch\(\s*["'`]/""")
                self.assertNotRegex(text, r"""["'`]/data/""")
        self.assertNotIn("<link rel=\"stylesheet\" href=\"http", page)
        self.assertNotIn("<script src=\"http", page)

    def test_a_built_site_holds_no_host_path(self) -> None:
        root = str(self.world.world.root)
        for path in self.out.rglob("*"):
            if path.is_file():
                with self.subTest(path=path.name):
                    self.assertNotIn(root, path.read_text(encoding="utf-8"))


class ArchitectureViewTests(BuiltSite):
    """Seam 2: containers, components and gaps; a private repository is its container only."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.data = read(cls.out, "architecture.json")

    def test_every_listed_repository_is_drawn_in_system_yamls_order(self) -> None:
        self.assertEqual([r["name"] for r in self.data["repos"]], [
            "opengwasdb-stores", "opengwasdb", "ogquery", "ogld", "opengwaspy", "opengwas-gateway", "ogdb-api"])
        ogld = next(r for r in self.data["repos"] if r["name"] == "ogld")
        self.assertEqual((ogld["state"], ogld["commit"], ogld["why"]), ("private", None, None))

    def test_each_repositorys_state_is_decided_once_by_the_build(self) -> None:
        self.assertEqual({r["name"]: r["state"] for r in self.data["repos"]}, {
            "opengwasdb-stores": "read", "opengwasdb": "read", "ogquery": "read", "ogld": "private",
            "opengwaspy": "no_model", "opengwas-gateway": "unreadable", "ogdb-api": "planned"})
        why = {r["name"]: r["why"] for r in self.data["repos"]}
        self.assertTrue(why["opengwas-gateway"].startswith("opengwas-gateway cannot be read"))
        self.assertTrue(why["opengwaspy"].startswith("docs/architecture/components.yaml is not in opengwaspy"))
        self.assertIsNone(why["opengwasdb"])
        self.assertEqual({r["refresh_error"] for r in self.data["repos"]}, {None})
        states = {c["id"]: c["state"] for c in self.data["containers"]}
        self.assertEqual({k: states[k] for k in ("ld_lib", "engine", "stores", "data_api")},
                         {"ld_lib": "private", "engine": "public", "stores": "data", "data_api": "planned"})
        containers = next(d for d in self.data["diagrams"] if d["id"] == "containers")["svg"]
        self.assertIn("planned; service", containers)

    def test_the_build_writes_the_figures_the_view_shows(self) -> None:
        self.assertEqual(self.data["counts"], {"components": 9, "repos_with_model": 3})
        self.assertEqual(self.data["component_repos"], ["opengwasdb-stores", "opengwasdb", "ogquery"])
        self.assertEqual([(l["repo"], l["imports"]) for l in self.data["layering"]], [("opengwasdb", 3)])
        self.assertEqual({g["repo"]: g["state"] for g in self.data["gaps"]}, {
            "opengwasdb-stores": "complete", "opengwasdb": "complete", "ogquery": "complete",
            "opengwaspy": "no_model", "opengwas-gateway": "unreadable"})

    def test_the_components_of_every_public_repository_with_a_model_are_listed(self) -> None:
        by_repo: dict[str, set[str]] = {}
        for c in self.data["components"]:
            by_repo.setdefault(c["repo"], set()).add(c["id"])
        self.assertEqual(by_repo, {"opengwasdb-stores": {"gen", "ogs", "tools"},
                                   "opengwasdb": {"cli", "query", "check", "store", "model"}, "ogquery": {"oq_read"}})
        gen = next(c for c in self.data["components"] if c["id"] == "gen")
        commit = next(r for r in self.data["repos"] if r["name"] == "opengwasdb-stores")["commit"]
        self.assertEqual(gen["paths"], [{"path": "src/gen/", "url": f"https://github.com/opengwas/opengwasdb-stores/tree/{commit}/src/gen/"}])
        self.assertEqual(gen["container_name"], "Generation")
        self.assertIn({"repo": "opengwasdb-stores", "number": "0001", "via": "code",
                       "title": "0001. Manifest Generation is one pipeline"},
                      [{k: a[k] for k in ("repo", "number", "via", "title")} for a in gen["adrs"]])

    def test_the_gaps_are_drawn_for_each_public_repository(self) -> None:
        gaps = {g["repo"]: g for g in self.data["gaps"]}
        self.assertIn("opengwas-gateway cannot be read", gaps["opengwas-gateway"]["unreadable"])
        self.assertTrue(gaps["opengwaspy"]["no_model"].startswith("docs/architecture/components.yaml is not in opengwaspy"))
        self.assertEqual(gaps["opengwasdb"]["unclaimed"], [])
        self.assertNotIn("ogld", gaps)

    def test_the_seam_the_baseline_and_the_layering_keep_their_counts(self) -> None:
        self.assertEqual({k: self.data["seam"][k] for k in ("from", "to", "imports", "pairs")},
                         {"from": "opengwasdb-stores", "to": "opengwasdb", "imports": 5, "pairs": 4})
        layering = self.data["layering"]
        self.assertEqual([(l["repo"], len(l["upward"]), l["edges"]) for l in layering], [("opengwasdb", 3, 8)])
        self.assertEqual({(u["from"], u["to"]) for u in layering[0]["upward"]},
                         {("query", "cli"), ("store", "query"), ("model", "store")})
        self.assertIn({"from_repo": "ogquery", "to_repo": "opengwasdb", "imports": 1, "pairs": 1}, self.data["across"])

    def test_the_diagrams_are_svg_drawn_at_build_time(self) -> None:
        diagrams = {d["id"]: d for d in self.data["diagrams"]}
        self.assertEqual(list(diagrams), ["containers", "opengwasdb", "opengwasdb-stores", "ogquery"])
        for d in diagrams.values():
            with self.subTest(diagram=d["id"]):
                self.assertTrue(d["svg"].startswith("<svg"), d["svg"][:40])
                self.assertTrue(d["svg"].rstrip().endswith("</svg>"))
        # The private repository's container is drawn, marked private; a component box links to its row.
        self.assertIn("LD library", diagrams["containers"]["svg"])
        self.assertIn("private", diagrams["containers"]["svg"])
        self.assertIn('href="#component-cli"', diagrams["opengwasdb"]["svg"])

    def test_nothing_of_the_private_repository_reaches_any_file_of_the_site(self) -> None:
        commit = self.world.architecture["repos"]["ogld"]["commit"]
        self.assertIn("ld_panels", {c["id"] for c in self.world.architecture["components"]}, "it was collected whole")
        for path in self.out.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for secret in (*SECRETS, commit[:12]):
                with self.subTest(path=path.relative_to(self.out).as_posix(), secret=secret):
                    self.assertNotIn(secret, text)


class DecisionsViewTests(BuiltSite):
    """Seam 3: one index of every public repository's ADRs, with what they govern and cite."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.data = read(cls.out, "decisions.json")
        cls.by_key = {(a["repo"], a["number"]): a for a in cls.data["adrs"]}

    def test_every_public_repositorys_adrs_are_listed_and_no_private_one(self) -> None:
        self.assertEqual(sorted({repo for repo, _ in self.by_key}), ["opengwasdb", "opengwasdb-stores", "opengwaspy"])
        self.assertEqual(self.data["repos"], ["opengwasdb-stores", "opengwasdb", "opengwaspy"])
        self.assertEqual(list(self.by_key)[:3], [("opengwasdb-stores", "0001"), ("opengwasdb-stores", "0002"),
                                                 ("opengwasdb-stores", "0003")])

    def test_an_adr_links_to_github_and_names_the_components_it_governs(self) -> None:
        adr = self.by_key[("opengwasdb-stores", "0001")]
        self.assertTrue(adr["url"].startswith("https://github.com/opengwas/opengwasdb-stores/blob/"))
        self.assertTrue(adr["url"].endswith("/docs/adr/0001-one-pipeline.md"))
        self.assertEqual(adr["components"], [{"id": "gen", "name": "Manifest Generation", "via": "code"}])
        self.assertEqual(adr["status"], "current")

    def test_a_citation_of_another_repositorys_adr_is_a_link_and_a_private_one_is_text(self) -> None:
        cites = self.by_key[("opengwasdb", "0003")]["cites"]
        target = self.by_key[("opengwasdb-stores", "0072")]["url"]
        self.assertEqual(cites, [{"repo": "ogld", "number": "0001", "text": "ogld ADR 0001", "url": None},
                                 {"repo": "opengwasdb-stores", "number": "0072", "text": "opengwasdb-stores ADR 0072",
                                  "url": target}])


class ContextViewTests(BuiltSite):
    """Seam 4: the hub's CONTEXT.md rendered, and each public repository's glossary linked."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.data = read(cls.out, "context.json")

    def test_the_hubs_glossary_is_rendered_with_its_headings_and_links(self) -> None:
        html = self.data["html"]
        self.assertIn('<h1 id="opengwas">OpenGWAS</h1>', html)
        self.assertIn('<h2 id="the-platform">The platform</h2>', html)
        self.assertIn('<a href="https://github.com/opengwas">GitHub</a>', html)
        self.assertIn('<a href="https://github.com/opengwas/og-dev-hub/blob/main/docs/adr/0001-dev-hub-collects-and-owns-nothing.md">'
                      "ADR 0001</a>", html)
        self.assertIn("<strong>Dev Hub</strong>:", html)
        self.assertEqual(self.data["source"], "https://github.com/opengwas/og-dev-hub/blob/main/CONTEXT.md")
        self.assertIn("<em>built state</em>", html)
        self.assertIn("<ul>\n<li>one</li>\n<li>two</li>\n</ul>", html)

    def test_each_public_repository_has_its_glossary_linked_or_its_gap_named(self) -> None:
        glossaries = {g["repo"]: g for g in self.data["glossaries"]}
        self.assertEqual(list(glossaries), ["opengwasdb-stores", "opengwasdb", "ogquery", "opengwaspy", "opengwas-gateway"])
        commit = self.world.architecture["repos"]["ogquery"]["commit"]
        self.assertEqual(glossaries["ogquery"]["url"], f"https://github.com/opengwas/ogquery/blob/{commit}/CONTEXT.md")
        self.assertIsNotNone(glossaries["opengwasdb-stores"]["url"])
        self.assertIsNone(glossaries["opengwasdb"]["url"])
        self.assertEqual(glossaries["opengwasdb"]["note"], "no CONTEXT.md at the commit read")
        self.assertIsNone(glossaries["opengwas-gateway"]["url"])
        self.assertEqual(glossaries["opengwas-gateway"]["note"], "could not be read")


class GapStateTests(unittest.TestCase):
    """A gap's state follows the repository's (`repo_state`), and an unmeasured one is `unknown`, never `complete`."""

    def view(self, architecture: dict) -> dict:
        from project_site import architecture_public

        return site.architecture_view(architecture_public.public_view({"architecture": architecture})["architecture"])

    def test_a_read_repository_with_no_gap_record_is_unknown_never_complete(self) -> None:
        import copy

        doc = copy.deepcopy(site_world().architecture)
        del doc["gaps"]["ogquery"]
        gaps = {g["repo"]: g for g in self.view(doc)["gaps"]}
        self.assertEqual((gaps["ogquery"]["state"], gaps["ogquery"]["unclaimed"], gaps["ogquery"]["stale"]),
                         ("unknown", None, None))
        self.assertEqual(gaps["opengwasdb"]["state"], "complete")

    def test_an_unclaimed_file_is_a_gap(self) -> None:
        world = World(self)
        result = collected(world.variant(ogquery={**OGQUERY_FILES, "src/stray.py": "import os\n"}))
        gaps = {g["repo"]: g for g in self.view(result)["gaps"]}
        self.assertEqual((gaps["ogquery"]["state"], gaps["ogquery"]["unclaimed"]), ("gaps", ["src/stray.py"]))
        self.assertEqual((gaps["opengwaspy"]["state"], gaps["opengwas-gateway"]["state"]), ("no_model", "unreadable"))


class ViewScriptTests(unittest.TestCase):
    """The view scripts run in node over a built site (`view_runner.js`): each view draws, and none throws."""

    def drawn(self, architecture: dict) -> dict:
        import subprocess

        out = built(self.addCleanup, {"architecture": architecture})
        runner = Path(__file__).with_name("view_runner.js")
        done = subprocess.run(["node", str(runner), str(out)], capture_output=True, text=True, check=True, timeout=60)
        return json.loads(done.stdout)

    def test_every_view_draws_from_the_built_site(self) -> None:
        drawn = self.drawn(site_world().architecture)
        for view, text in drawn.items():
            with self.subTest(view=view):
                self.assertNotIn("could not be drawn", text)
        self.assertIn("claims complete", drawn["architecture"])
        self.assertIn("Release Bundles", drawn["decisions"])
        self.assertIn("ogquery", drawn["context"])

    def test_an_unknown_gap_is_drawn_as_unknown_without_reading_its_unclaimed_files(self) -> None:
        import copy

        doc = copy.deepcopy(site_world().architecture)
        del doc["gaps"]["ogquery"]
        drawn = self.drawn(doc)["architecture"]
        self.assertNotIn("could not be drawn", drawn)
        self.assertIn("Its claims were not measured, so its gaps are unknown, not none.", drawn)


class RefreshErrorTests(unittest.TestCase):
    def test_a_failed_refresh_of_a_public_repository_is_shown_with_its_host_path_cut(self) -> None:
        from project_site import architecture_public

        world = World(self)
        fx.git(world.root / "opengwaspy", "remote", "add", "origin", str(world.root / "elsewhere" / "gone.git"))
        repositories = staging.Repositories(refresh=True, checkouts={fx.REGISTRY: world.root / "registry"},
                                            git_dirs=world.repositories.git_dirs)
        from project_site.collect import architecture as collector

        doc = collected(collector.collect(repositories, system_file=world.system))
        view = site.architecture_view(architecture_public.public_view({"architecture": doc})["architecture"])
        error = next(r for r in view["repos"] if r["name"] == "opengwaspy")["refresh_error"]
        self.assertIn("'…/gone.git' does not appear to be a git repository", error)
        self.assertNotIn(str(world.root), json.dumps(view))
        self.assertIsNone(next(r for r in view["repos"] if r["name"] == "ogld")["refresh_error"], "private: never shown")


class OwnerTests(unittest.TestCase):
    def test_a_link_to_github_is_a_tree_for_a_directory_and_a_blob_for_a_file(self) -> None:
        from project_site import paths

        self.assertEqual(paths.github_url("ogquery", "abc", "src/ogquery/"), "https://github.com/opengwas/ogquery/tree/abc/src/ogquery/")
        self.assertEqual(paths.github_url("ogquery", "abc", "CONTEXT.md"), "https://github.com/opengwas/ogquery/blob/abc/CONTEXT.md")

    def test_the_containers_diagram_draws_the_state_it_is_given(self) -> None:
        from project_site import diagrams

        dot = diagrams.containers({"system": {"name": "S"}}, [
            {"id": "x", "name": "X", "repo": "r", "tech": "T", "summary": "", "state": "private"},
            {"id": "y", "name": "Y", "repo": "q", "tech": "T", "summary": "", "state": "planned"}])
        self.assertIn('"x" [fillcolor="#e5e5e5" label=<', dot)
        self.assertIn("private; T", dot)
        self.assertIn("dashed", dot)
        self.assertIn("planned; T", dot)


class MarkdownTests(unittest.TestCase):
    def test_text_never_becomes_markup_and_only_web_links_are_kept(self) -> None:
        from project_site import markdown

        html = markdown.render("A <script>x</script> & [bad](javascript:alert) and `<b>`.", base="https://x.org/")
        self.assertEqual(html, "<p>A &lt;script&gt;x&lt;/script&gt; &amp; bad and <code>&lt;b&gt;</code>.</p>\n")

    def test_snake_case_is_not_emphasis_and_a_numbered_list_is_a_list(self) -> None:
        from project_site import markdown

        self.assertEqual(markdown.render("a_b_c\n\n1. one\n2. two", base="https://x.org/"),
                         "<p>a_b_c</p>\n<ol>\n<li>one</li>\n<li>two</li>\n</ol>\n")


class UnavailableTests(unittest.TestCase):
    def test_an_unavailable_architecture_is_a_notice_in_every_view_and_the_build_succeeds(self) -> None:
        out = built(self.addCleanup, {"architecture": {"source": "architecture", "available": False, "collected_at": "x",
                                            "error": "ValueError: system.yaml is broken"}})
        for name in ("architecture.json", "decisions.json"):
            data = read(out, name)
            with self.subTest(name=name):
                self.assertEqual((data["available"], data["error"]), (False, "ValueError: system.yaml is broken"))
        self.assertIn("<h1", read(out, "context.json")["html"])

    def test_without_any_collection_the_build_says_so(self) -> None:
        out = built(self.addCleanup, {})
        self.assertEqual(read(out, "architecture.json")["error"], "architecture.json was not collected")


class WorkRootTests(unittest.TestCase):
    """Two work roots, two variables: the site's `$DEV_HUB_SITE_ROOT`, else `<checkout>/.work/site`, on every machine;
    `pixi run architecture`'s and `site-data`'s `$OPENGWASDB_SITE_ROOT`, else the build host's (og-dev-hub#15)."""

    def test_each_root_has_its_own_variable_and_setting_one_never_moves_the_other(self) -> None:
        from project_site import paths

        with mock.patch.dict(os.environ, {"DEV_HUB_SITE_ROOT": "", "OPENGWASDB_SITE_ROOT": ""}):
            self.assertEqual(paths.site_work_root(), paths.repo_root() / ".work" / "site")
            self.assertEqual(paths.work_root(), paths.WORK_ROOT)
        with mock.patch.dict(os.environ, {"DEV_HUB_SITE_ROOT": "/x/site", "OPENGWASDB_SITE_ROOT": ""}):
            self.assertEqual(paths.site_work_root(), Path("/x/site"))
            self.assertEqual(paths.work_root(), paths.WORK_ROOT)
        with mock.patch.dict(os.environ, {"DEV_HUB_SITE_ROOT": "", "OPENGWASDB_SITE_ROOT": "/x/host"}):
            self.assertEqual(paths.site_work_root(), paths.repo_root() / ".work" / "site")
            self.assertEqual(paths.work_root(), Path("/x/host"))

    def test_a_build_clones_into_the_sites_work_root_and_reads_public_git_alone(self) -> None:
        from project_site import paths
        from project_site.collect import __main__ as command

        root = Path(tempfile.mkdtemp(prefix="site-main-"))
        self.addCleanup(shutil.rmtree, root, True)
        with mock.patch.dict(os.environ, {"DEV_HUB_SITE_ROOT": "", "OPENGWASDB_SITE_ROOT": "/x/host"}), \
                mock.patch.object(command, "run", return_value=[]) as run, mock.patch.object(site, "build") as build:
            self.assertEqual(site.main(["--data-dir", str(root / "data"), "--out", str(root / "_site"), "--no-refresh"]), 0)
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["public_only"])
        self.assertEqual(kwargs["repositories"].root, paths.repo_root() / ".work" / "site")
        self.assertFalse(kwargs["repositories"].refresh)
        build.assert_called_once_with(root / "data", root / "_site")


class PublicGitOnlyTests(unittest.TestCase):
    """Seam 5: the site's collection reads no private repository and never the board."""

    def test_the_site_collects_without_cloning_a_private_repository_or_calling_the_board(self) -> None:
        from ogstores import bundle as release_bundle

        # No manifest figure is checked here, and the real call imports the engine.
        patcher = mock.patch.object(release_bundle, "manifest_summary", side_effect=AssertionError("not read here"))
        patcher.start()
        self.addCleanup(patcher.stop)
        world = World(self)
        work_root = world.root / "work"
        data = world.root / "collected"
        refuse = mock.Mock(side_effect=AssertionError("the site build called gh"))
        with mock.patch.dict(os.environ, {"DEV_HUB_SITE_ROOT": str(work_root)}), \
                mock.patch("project_site.collect.board.collect", refuse), \
                mock.patch.object(common, "gh_runner", refuse):
            from project_site import paths

            repositories = staging.Repositories(
                checkouts={fx.REGISTRY: world.root / "registry"}, root=paths.site_work_root(),
                # ogld is left to the site's work root, where a read would clone it from GitHub: it must never be asked for.
                git_dirs={k: v for k, v in world.repositories.git_dirs.items() if k != "ogld"})
            results = command.run(data, repositories=repositories, system_file=world.system, out=lambda line: None,
                                  public_only=True)
        self.assertEqual([r["source"] for r in results], ["architecture", "stores"])
        self.assertNotIn("ogld", repositories.handles)
        self.assertFalse((work_root / "ogld.git").exists())
        refuse.assert_not_called()
        self.assertEqual(sorted(p.name for p in data.iterdir()), ["architecture.json", "stores.json"])
        collected_doc = json.loads((data / "architecture.json").read_text(encoding="utf-8"))
        self.assertTrue(collected_doc["available"], collected_doc["error"])
        self.assertEqual(collected_doc["repos"]["ogld"]["note"], "private: drawn as its container only, never read")
        self.assertNotIn("ld_panels", {c["id"] for c in collected_doc["components"]})

        (world.root / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
        site.build(data, world.root / "_site", context=world.root / "CONTEXT.md")
        containers = next(d for d in read(world.root / "_site", "architecture.json")["diagrams"] if d["id"] == "containers")
        self.assertIn("LD library", containers["svg"])


if __name__ == "__main__":
    unittest.main()
