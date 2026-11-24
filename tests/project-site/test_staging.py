#!/usr/bin/env python3
"""Stage the engine's docs at the pinned revision, and read that revision from the lock (#388).

The engine section of the site is opengwasdb's own documentation at the
revision `pixi.lock` pins, so it describes the runtime the registry actually
imports. Only its Markdown and its self-contained HTML are documentation: its
`docs/` also holds 26 logs, 89 JSON and 8 JSONL files, and 21 `.qmd` sources
whose reports are published beside them as HTML, so those are not staged.

Run from the repository root:
    python3 tests/project-site/test_staging.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from project_site import build, paths, staging
from project_site.collect.common import CollectError
from project_site.staging import stage_docs

REGISTRY_LOCK = Path(__file__).resolve().parent / "fixtures" / "registry-pixi.lock"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


class StageDocsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="project-site-staging-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "engine"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "dev")
        git(self.repo, "config", "user.email", "test@example.org")
        git(self.repo, "config", "user.name", "Test")
        docs = self.repo / "docs"
        (docs / "spec").mkdir(parents=True)
        (docs / "a.md").write_text("# A\n", encoding="utf-8")
        (docs / "b.html").write_text("<html><body>B</body></html>\n", encoding="utf-8")
        (docs / "spec" / "c.md").write_text("# C\n", encoding="utf-8")
        # Not documentation, and not staged: a log, a data file, a qmd source.
        (docs / "run.log").write_text("log\n", encoding="utf-8")
        (docs / "stats.json").write_text("{}\n", encoding="utf-8")
        (docs / "report.qmd").write_text("# qmd\n", encoding="utf-8")
        (self.repo / "README.md").write_text("# engine\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "first")
        self.first = git(self.repo, "rev-parse", "HEAD")

        (docs / "later.md").write_text("# Later\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "second")

    def test_staging_a_revision_yields_exactly_that_revision_s_docs(self) -> None:
        dest = self.root / "staged"
        staged = stage_docs(self.repo, self.first, dest)

        self.assertEqual(staged, ["a.md", "b.html", "spec/c.md"])
        self.assertEqual(
            sorted(str(path.relative_to(dest)) for path in dest.rglob("*") if path.is_file()),
            ["a.md", "b.html", "spec/c.md"],
        )

    def test_staging_the_newer_revision_adds_its_file(self) -> None:
        dest = self.root / "staged-newer"
        staged = stage_docs(self.repo, "HEAD", dest)

        self.assertEqual(staged, ["a.md", "b.html", "later.md", "spec/c.md"])
        self.assertEqual((dest / "later.md").read_text(encoding="utf-8"), "# Later\n")


class StageIntoTheMirrorTest(unittest.TestCase):
    """A render stages into the mirror, never into the checkout (#388 review).

    The registry is a checkout named as `--registry` names one, and the hub has
    nothing of its own to stage, so the mirror is the registry's docs, the
    engine's and the glossary, exactly as it was in opengwasdb-stores.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="project-site-stage-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "registry"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "dev")
        git(self.repo, "config", "user.email", "test@example.org")
        git(self.repo, "config", "user.name", "Test")
        (self.repo / "docs" / "adr").mkdir(parents=True)
        (self.repo / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
        (self.repo / "docs" / "adr" / "x.md").write_text("# X\n", encoding="utf-8")
        (self.repo / "CONTEXT.md").write_text("# Glossary\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "docs")
        self.commit = git(self.repo, "rev-parse", "HEAD")

        self.engine = self.root / "engine"
        self.engine.mkdir()
        git(self.engine, "init", "-q", "-b", "dev")
        git(self.engine, "config", "user.email", "test@example.org")
        git(self.engine, "config", "user.name", "Test")
        (self.engine / "docs").mkdir()
        (self.engine / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
        git(self.engine, "add", "-A")
        git(self.engine, "commit", "-q", "-m", "docs")
        self.engine_commit = git(self.engine, "rev-parse", "HEAD")

        self.hub = self.root / "og-dev-hub"
        self.hub.mkdir()
        git(self.hub, "init", "-q", "-b", "main")
        git(self.hub, "-c", "user.email=t@e.org", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "hub")
        self.registry = staging.registry_root(self.repo)

        self.work = self.root / "work"
        self.environ = mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(self.work)})
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def stage(self) -> build.Stage:
        return build.stage_everything(self.hub, registry=self.registry, clone=self.engine, revision=self.engine_commit)

    def status_of_checkout(self) -> str:
        """Every file git knows about or would ignore: the checkout's whole shape."""
        return git(self.repo, "status", "--porcelain", "--ignored")

    def test_staging_leaves_the_checkout_untouched(self) -> None:
        before = self.status_of_checkout()

        stage = self.stage()

        self.assertEqual(self.status_of_checkout(), before)
        self.assertFalse((self.repo / "docs" / "opengwasdb").exists())
        self.assertFalse((self.repo / "docs" / "glossary.md").exists())
        self.assertEqual(
            sorted(path.relative_to(stage.mirror).as_posix() for path in stage.mirror.rglob("*") if path.is_file()),
            ["a.md", "adr/x.md", "glossary.md", "opengwasdb/guide.md", "opengwasdb/index.qmd"],
        )
        # The records the render reports still name the commits it documented.
        self.assertEqual(stage.registry_commit, self.commit)
        self.assertEqual(stage.engine_commit, self.engine_commit)

    def test_two_work_roots_stage_independently(self) -> None:
        first = self.stage()
        other = self.root / "other-work"
        with mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(other)}):
            second = self.stage()

        self.assertNotEqual(first.mirror, second.mirror)
        self.assertEqual((first.mirror / "a.md").read_text(encoding="utf-8"), "# A\n")
        self.assertEqual((second.mirror / "a.md").read_text(encoding="utf-8"), "# A\n")

    def test_the_hubs_site_goes_over_the_registrys_docs_and_its_docs_under_dev_hub(self) -> None:
        # og-dev-hub#7: the registry's docs, then the hub's site/ over them, then
        # the engine's docs, then the hub's own docs/ under dev-hub/.
        for relative, text in {
            "site/_quarto.yml": "project:\n  type: website\n",
            "site/a.md": "# A, from the hub\n",
            "site/index.qmd": "# Overview\n",
            "docs/adr/0001-x.md": "# Hub ADR\n",
            "docs/site.md": "# The site\n",
        }.items():
            (self.hub / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.hub / relative).write_text(text, encoding="utf-8")
        (self.hub / "site" / "pre-render.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (self.hub / "site" / "pre-render.sh").chmod(0o755)
        git(self.hub, "add", "-A")
        git(self.hub, "-c", "user.email=t@e.org", "-c", "user.name=T", "commit", "-q", "-m", "site")

        stage = self.stage()

        self.assertEqual(
            sorted(path.relative_to(stage.mirror).as_posix() for path in stage.mirror.rglob("*") if path.is_file()),
            ["_quarto.yml", "a.md", "adr/x.md", "dev-hub/adr/0001-x.md", "dev-hub/site.md", "glossary.md",
             "index.qmd", "opengwasdb/guide.md", "opengwasdb/index.qmd", "pre-render.sh"],
        )
        self.assertEqual((stage.mirror / "a.md").read_text(encoding="utf-8"), "# A, from the hub\n")
        self.assertEqual((stage.mirror / "adr" / "x.md").read_text(encoding="utf-8"), "# X\n")
        self.assertTrue(os.access(stage.mirror / "pre-render.sh", os.X_OK), "the hook stays runnable")
        self.assertEqual(stage.registry_commit, self.commit)
        self.assertEqual(stage.hub_commit, git(self.hub, "rev-parse", "HEAD"))

    def test_a_hub_page_links_out_to_the_hub_at_its_commit(self) -> None:
        (self.hub / "docs").mkdir()
        (self.hub / "docs" / "site.md").write_text(
            "# The site\n\nSee [the pages](../src/project_site/pages.py) and [a sibling](adr/0001-x.md).\n",
            encoding="utf-8",
        )
        (self.hub / "src" / "project_site").mkdir(parents=True)
        (self.hub / "src" / "project_site" / "pages.py").write_text("\n", encoding="utf-8")
        git(self.hub, "add", "-A")
        git(self.hub, "-c", "user.email=t@e.org", "-c", "user.name=T", "commit", "-q", "-m", "docs")
        hub_commit = git(self.hub, "rev-parse", "HEAD")

        stage = self.stage()
        report = build.rewrite(stage)

        self.assertEqual(
            (stage.mirror / "dev-hub" / "site.md").read_text(encoding="utf-8"),
            "# The site\n\nSee [the pages]"
            f"(https://github.com/opengwas/og-dev-hub/blob/{hub_commit}/src/project_site/pages.py)"
            " and [a sibling](adr/0001-x.md).\n",
        )
        self.assertEqual(report.missing, [])


class MermaidPageReachabilityTest(unittest.TestCase):
    """A `.md` staged as `.qmd` for its Mermaid cell stays reachable (#388 review)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="project-site-mermaid-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "registry"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "dev")
        git(self.repo, "config", "user.email", "test@example.org")
        git(self.repo, "config", "user.name", "Test")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "site.md").write_text(
            "# The site\n\n```mermaid\ngraph TD; A-->B;\n```\n", encoding="utf-8"
        )
        (self.repo / "docs" / "reference.md").write_text(
            "# Reference\n\nSee [the site page](site.md#publishing).\n", encoding="utf-8"
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "docs")
        self.commit = git(self.repo, "rev-parse", "HEAD")

        self.engine = self.root / "engine"
        self.engine.mkdir()
        git(self.engine, "init", "-q", "-b", "dev")
        git(self.engine, "config", "user.email", "test@example.org")
        git(self.engine, "config", "user.name", "Test")
        (self.engine / "docs").mkdir()
        (self.engine / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
        git(self.engine, "add", "-A")
        git(self.engine, "commit", "-q", "-m", "docs")
        self.engine_commit = git(self.engine, "rev-parse", "HEAD")

    def test_a_link_to_the_mermaid_page_reaches_its_rendered_page(self) -> None:
        mirror = self.root / "mirror"
        staging.mirror_docs(self.repo, mirror)

        report = staging.rewrite_mirror(
            mirror,
            registry=self.repo,
            commit=self.commit,
            registry_url="https://github.com/opengwas/opengwasdb-stores",
            engine=self.engine,
            engine_commit=self.engine_commit,
            engine_url="https://github.com/opengwas/opengwasdb",
            engine_prefix="opengwasdb/",
        )

        self.assertTrue((mirror / "site.qmd").is_file())
        self.assertFalse((mirror / "site.md").exists())
        self.assertEqual(
            (mirror / "reference.md").read_text(encoding="utf-8"),
            "# Reference\n\nSee [the site page](site.html#publishing).\n",
        )
        self.assertEqual([page for page, _ in report.raw_pages], ["site.md"])
        self.assertIn("```{mermaid}", report.raw_pages[0][1])
        self.assertEqual(report.unparsed, [])


class GithubFixture:
    """A stand-in for github.com/opengwas: bare repositories under one directory (og-dev-hub#7).

    `paths.GITHUB` is pointed at it, so the site clones from here exactly as it
    would from GitHub; a test of the network being gone points it nowhere.
    """

    def __init__(self, test: unittest.TestCase) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="project-site-github-")
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.github = self.root / "github"
        self.work = self.root / "work"
        for patch in (mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(self.work)}),
                      mock.patch.object(paths, "GITHUB", str(self.github))):
            patch.start()
            test.addCleanup(patch.stop)
        self.authors: dict[str, Path] = {}
        self.test = test

    def repository(self, name: str, files: dict[str, str]) -> str:
        """`opengwas/<name>`, with `files` committed on `main`; returns the commit."""
        origin = self.github / name
        origin.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        author = self.root / "authors" / name
        subprocess.run(["git", "clone", "-q", str(origin), str(author)], check=True, capture_output=True)
        git(author, "config", "user.email", "test@example.org")
        git(author, "config", "user.name", "Test")
        self.authors[name] = author
        return self.commit(name, files)

    def commit(self, name: str, files: dict[str, str], branch: str = "main") -> str:
        author = self.authors[name]
        for relative, text in files.items():
            (author / relative).parent.mkdir(parents=True, exist_ok=True)
            (author / relative).write_text(text, encoding="utf-8")
        git(author, "add", "-A")
        git(author, "commit", "-q", "-m", "change")
        git(author, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        return git(author, "rev-parse", "HEAD")

    def offline(self) -> None:
        """No network: every origin is gone, and a new clone is pointed at a path that does not exist."""
        self.github.rename(self.root / "unreachable")
        patch = mock.patch.object(paths, "GITHUB", str(self.root / "no-network"))
        patch.start()
        self.test.addCleanup(patch.stop)


class CloneOwnerTest(unittest.TestCase):
    """One owner clones and fetches every repository the site reads, and never raises (og-dev-hub#7).

    A fetch that fails is recorded, never raised, and the refs already there are
    read (docs/spec/project-site.md, Work).
    """

    def setUp(self) -> None:
        self.hub = GithubFixture(self)
        self.first = self.hub.repository("opengwasdb-stores", {"CONTEXT.md": "# Glossary\n"})
        self.clone = paths.clone_dir("opengwasdb-stores")

    def ensure(self, **kwargs) -> dict | None:
        return staging.ensure_clone(self.clone, url=paths.clone_url("opengwasdb-stores"), **kwargs)

    def test_a_named_repository_is_cloned_bare_under_the_work_root(self) -> None:
        self.assertEqual(self.ensure(), {"ok": True, "error": None})

        self.assertEqual(self.clone, self.hub.work / "opengwasdb-stores.git")
        self.assertEqual(git(self.clone, "rev-parse", "--is-bare-repository"), "true")
        self.assertEqual(git(self.clone, "rev-parse", "main"), self.first)

    def test_a_fetch_brings_what_the_origin_gained_and_prunes_what_it_lost(self) -> None:
        side = self.hub.commit("opengwasdb-stores", {"docs/b.md": "# B\n"}, branch="feature")
        self.ensure()
        newer = self.hub.commit("opengwasdb-stores", {"docs/a.md": "# A\n"})
        git(self.hub.authors["opengwasdb-stores"], "push", "-q", "origin", ":refs/heads/feature")

        self.assertEqual(self.ensure(), {"ok": True, "error": None})

        self.assertEqual(git(self.clone, "rev-parse", "main"), newer)
        self.assertNotIn(side, git(self.clone, "for-each-ref", "--format=%(objectname)"))

    def test_without_fetch_a_clone_it_holds_is_left_as_it_is(self) -> None:
        self.ensure()
        self.hub.commit("opengwasdb-stores", {"docs/a.md": "# A\n"})

        self.assertIsNone(self.ensure(fetch=False))

        self.assertEqual(git(self.clone, "rev-parse", "main"), self.first)

    def test_a_clone_that_cannot_be_made_is_recorded_not_raised(self) -> None:
        self.hub.offline()

        result = self.ensure()

        self.assertFalse(result["ok"])
        self.assertIn("no-network", result["error"])
        self.assertFalse((self.clone / "HEAD").exists())

    def test_a_fetch_that_fails_is_recorded_and_the_clone_is_kept(self) -> None:
        self.ensure()
        self.hub.offline()

        result = self.ensure()

        self.assertFalse(result["ok"])
        self.assertIn("opengwasdb-stores", result["error"], "git's own message, naming the origin it could not reach")
        self.assertEqual(git(self.clone, "rev-parse", "main"), self.first)

    def test_the_engine_clone_can_still_be_named_by_its_variable(self) -> None:
        named = self.hub.root / "elsewhere.git"
        with mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ENGINE_CLONE": str(named)}):
            self.assertEqual(paths.clone_dir("opengwasdb"), named)
        self.assertEqual(paths.clone_dir("opengwasdb"), self.hub.work / "opengwasdb.git")


class RegistryTreeTest(unittest.TestCase):
    """The registry the collectors read: its clone's `main`, extracted, or a checkout named instead (og-dev-hub#7)."""

    FILES = {
        "stores/OGS-00001/release.yaml": "store_id: OGS-00001\n",
        "docs/_epics/opengwasdb-stores-1.yaml": "repo: opengwasdb-stores\n",
        "docs/a.md": "# A\n",
        "CONTEXT.md": "# Glossary\n",
        "pixi.lock": "packages: []\n",
        "src/ogstores/bundle.py": "# not read from a tree\n",
    }

    def setUp(self) -> None:
        self.hub = GithubFixture(self)
        self.commit = self.hub.repository("opengwasdb-stores", self.FILES)
        self.checkout = self.hub.authors["opengwasdb-stores"]
        self.tree = self.hub.root / "tree"

    def test_a_clones_ref_is_extracted_as_the_tree_the_collectors_read(self) -> None:
        clone = paths.clone_dir("opengwasdb-stores")
        staging.ensure_clone(clone, url=paths.clone_url("opengwasdb-stores"))

        commit = staging.extract_tree(clone, "main", self.tree)

        self.assertEqual(commit, self.commit)
        self.assertTrue((self.tree / "stores" / "OGS-00001" / "release.yaml").is_file())
        self.assertTrue((self.tree / "docs" / "_epics" / "opengwasdb-stores-1.yaml").is_file())
        self.assertTrue((self.tree / "CONTEXT.md").is_file())
        self.assertTrue((self.tree / "pixi.lock").is_file())

    def test_a_second_extraction_replaces_the_first(self) -> None:
        clone = paths.clone_dir("opengwasdb-stores")
        staging.ensure_clone(clone, url=paths.clone_url("opengwasdb-stores"))
        staging.extract_tree(clone, "main", self.tree)
        (self.tree / "docs" / "left-behind.md").write_text("# Gone\n", encoding="utf-8")

        staging.extract_tree(clone, "main", self.tree)

        self.assertFalse((self.tree / "docs" / "left-behind.md").exists())

    def test_without_a_checkout_the_registry_is_its_clones_main(self) -> None:
        registry = staging.registry_root(tree=self.tree)

        self.assertEqual(registry.root, self.tree)
        self.assertEqual(registry.git_dir, self.hub.work / "opengwasdb-stores.git")
        self.assertEqual(registry.ref, self.commit)
        self.assertTrue(registry.clone)
        self.assertTrue((self.tree / "docs" / "_epics" / "opengwasdb-stores-1.yaml").is_file())
        self.assertFalse((self.tree / "src").exists(), "only what the site reads is extracted")

    def test_reading_the_registry_fetches_only_when_a_refresh_is_asked_for(self) -> None:
        staging.registry_root(tree=self.tree)
        newer = self.hub.commit("opengwasdb-stores", {"docs/a.md": "# A, again\n"})

        self.assertEqual(staging.registry_root(tree=self.tree).ref, self.commit, "a read is not a fetch")
        refreshed = staging.registry_root(tree=self.tree, refresh=True)

        self.assertEqual(refreshed.ref, newer)
        self.assertEqual(refreshed.fetch, {"ok": True, "error": None})

    def test_a_failed_refresh_is_recorded_and_the_main_it_has_is_read(self) -> None:
        staging.registry_root(tree=self.tree)
        self.hub.offline()

        registry = staging.registry_root(tree=self.tree, refresh=True)

        self.assertEqual(registry.ref, self.commit)
        self.assertFalse(registry.fetch["ok"])

    def test_a_registry_that_cannot_be_cloned_cannot_be_read_and_says_why(self) -> None:
        self.hub.offline()

        with self.assertRaises(CollectError) as caught:
            staging.registry_root(tree=self.tree)

        self.assertIn("opengwasdb-stores", str(caught.exception))
        self.assertIn("no-network", str(caught.exception))

    def test_a_reader_of_git_alone_extracts_nothing(self) -> None:
        registry = staging.registry_root(tree=self.tree, files=False)

        self.assertIsNone(registry.root)
        self.assertEqual((registry.git_dir, registry.ref), (self.hub.work / "opengwasdb-stores.git", self.commit))
        self.assertFalse(self.tree.exists())

    def test_a_named_checkout_is_the_registry_itself(self) -> None:
        registry = staging.registry_root(self.checkout)

        self.assertEqual(registry.root, self.checkout.resolve())
        self.assertEqual(registry.git_dir, self.checkout.resolve())
        self.assertEqual(registry.ref, "HEAD")
        self.assertFalse(registry.clone)
        self.assertFalse((self.hub.work / "opengwasdb-stores.git").exists(), "a named checkout needs no clone")


class EngineRevisionTest(unittest.TestCase):
    """A render stages the engine's docs at the registry's pin, fetching the engine only to get it."""

    def setUp(self) -> None:
        self.hub = GithubFixture(self)
        self.first = self.hub.repository("opengwasdb", {"docs/guide.md": "# Guide\n"})
        self.hub.repository("opengwasdb-stores", {"docs/a.md": "# A\n", "CONTEXT.md": "# Glossary\n"})
        self.hub_checkout = self.hub.root / "og-dev-hub"
        self.hub_checkout.mkdir()
        git(self.hub_checkout, "init", "-q", "-b", "main")
        git(self.hub_checkout, "-c", "user.email=t@e.org", "-c", "user.name=T", "commit", "-q", "--allow-empty", "-m", "hub")

    def stage(self, revision: str) -> build.Stage:
        registry = staging.registry_root(tree=self.hub.root / "tree")
        return build.stage_everything(self.hub_checkout, registry=registry, revision=revision)

    def test_a_pinned_revision_the_clone_lacks_is_fetched(self) -> None:
        self.stage(self.first)
        newer = self.hub.commit("opengwasdb", {"docs/later.md": "# Later\n"})

        stage = self.stage(newer)

        self.assertEqual(stage.engine_commit, newer)
        self.assertTrue((stage.mirror / "opengwasdb" / "later.md").is_file())

    def test_a_revision_the_engine_does_not_have_stops_the_render_naming_it(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            self.stage("f" * 40)

        self.assertIn("f" * 40, str(caught.exception))


class PinnedRevisionTest(unittest.TestCase):
    """The site stages the engine docs at the commit the registry's pixi.lock resolves (#253).

    How the lock is read is opengwasdb-stores' `tests/engine`'s; this is only that
    the site asks it. The lock is a copy of the registry's pin, beside this test.
    """

    def test_the_committed_lock_pins_one_revision(self) -> None:
        from ogstores import engine
        from project_site.paths import pinned_opengwasdb_revision

        revision = pinned_opengwasdb_revision(REGISTRY_LOCK)

        self.assertEqual(revision, engine.locked_commit(REGISTRY_LOCK))

if __name__ == "__main__":
    unittest.main()
