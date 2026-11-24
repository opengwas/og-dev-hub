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
        self.assertEqual(stage.commit, self.commit)
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
        self.assertEqual(stage.commit, self.commit)
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


class CloneOwnerTest(unittest.TestCase):
    """One owner keeps a bare clone of each opengwas repository under the work root (og-dev-hub#7)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="project-site-clone-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # The origin a clone is made from: a bare repository, as GitHub would be.
        self.origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.author = self.root / "author"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.author)], check=True, capture_output=True)
        git(self.author, "config", "user.email", "test@example.org")
        git(self.author, "config", "user.name", "Test")
        self.first = self._commit("CONTEXT.md", "# Glossary\n")
        self.work = self.root / "work"
        self.environ = mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(self.work)})
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def _commit(self, relative: str, text: str, branch: str = "main") -> str:
        path = self.author / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.author, "add", "-A")
        git(self.author, "commit", "-q", "-m", relative)
        git(self.author, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        return git(self.author, "rev-parse", "HEAD")

    def test_a_named_repository_is_cloned_bare_under_the_work_root(self) -> None:
        clone = staging.ensure_clone("opengwasdb-stores", url=str(self.origin))

        self.assertEqual(clone, self.work / "opengwasdb-stores.git")
        self.assertEqual(git(clone, "rev-parse", "--is-bare-repository"), "true")
        self.assertEqual(git(clone, "rev-parse", "main"), self.first)

    def test_a_second_call_fetches_what_the_origin_gained(self) -> None:
        clone = staging.ensure_clone("opengwasdb-stores", url=str(self.origin))
        newer = self._commit("docs/a.md", "# A\n")
        side = self._commit("docs/b.md", "# B\n", branch="feature")

        self.assertEqual(staging.ensure_clone("opengwasdb-stores", url=str(self.origin)), clone)

        self.assertEqual(git(clone, "rev-parse", "main"), newer)
        self.assertEqual(git(clone, "rev-parse", "refs/heads/feature"), side)

    def test_a_held_revision_is_not_fetched_again_and_a_missing_one_is(self) -> None:
        clone = staging.ensure_clone("opengwasdb", url=str(self.origin), revision=self.first)
        newer = self._commit("docs/a.md", "# A\n")

        staging.ensure_clone("opengwasdb", url=str(self.origin), revision=self.first)
        self.assertEqual(git(clone, "rev-parse", "main"), self.first, "a pinned revision it holds needs no fetch")

        staging.ensure_clone("opengwasdb", url=str(self.origin), revision=newer)
        self.assertEqual(git(clone, "rev-parse", "main"), newer)

    def test_a_revision_the_origin_does_not_have_stops_the_build(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            staging.ensure_clone("opengwasdb", url=str(self.origin), revision="f" * 40)

        self.assertIn("f" * 40, str(caught.exception))

    def test_the_engine_clone_can_still_be_named_by_its_variable(self) -> None:
        named = self.root / "elsewhere.git"
        with mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ENGINE_CLONE": str(named)}):
            self.assertEqual(paths.clone_dir("opengwasdb"), named)
        self.assertEqual(paths.clone_dir("opengwasdb"), self.work / "opengwasdb.git")


class RegistryTreeTest(unittest.TestCase):
    """The registry the collectors read: its clone's `main`, extracted, or a checkout named instead (og-dev-hub#7)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="project-site-registry-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.origin = self.root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.checkout = self.root / "opengwasdb-stores"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.checkout)], check=True, capture_output=True)
        git(self.checkout, "config", "user.email", "test@example.org")
        git(self.checkout, "config", "user.name", "Test")
        files = {
            "stores/OGS-00001/release.yaml": "store_id: OGS-00001\n",
            "docs/_epics/opengwasdb-stores-1.yaml": "repo: opengwasdb-stores\n",
            "docs/a.md": "# A\n",
            "CONTEXT.md": "# Glossary\n",
            "pixi.lock": "packages: []\n",
            "src/ogstores/bundle.py": "# not read from a tree\n",
        }
        for relative, text in files.items():
            (self.checkout / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / relative).write_text(text, encoding="utf-8")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "registry")
        git(self.checkout, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.commit = git(self.checkout, "rev-parse", "HEAD")
        self.work = self.root / "work"
        self.environ = mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(self.work)})
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def test_a_clones_ref_is_extracted_as_the_tree_the_collectors_read(self) -> None:
        clone = staging.ensure_clone("opengwasdb-stores", url=str(self.origin))
        tree = self.root / "tree"

        commit = staging.extract_tree(clone, "main", tree)

        self.assertEqual(commit, self.commit)
        self.assertTrue((tree / "stores" / "OGS-00001" / "release.yaml").is_file())
        self.assertTrue((tree / "docs" / "_epics" / "opengwasdb-stores-1.yaml").is_file())
        self.assertTrue((tree / "CONTEXT.md").is_file())
        self.assertTrue((tree / "pixi.lock").is_file())

    def test_a_second_extraction_replaces_the_first(self) -> None:
        clone = staging.ensure_clone("opengwasdb-stores", url=str(self.origin))
        tree = self.root / "tree"
        staging.extract_tree(clone, "main", tree)
        (tree / "docs" / "left-behind.md").write_text("# Gone\n", encoding="utf-8")

        staging.extract_tree(clone, "main", tree)

        self.assertFalse((tree / "docs" / "left-behind.md").exists())

    def test_without_a_checkout_the_registry_is_its_clones_main(self) -> None:
        tree = self.root / "tree"

        registry = staging.registry_root(tree=tree, url=str(self.origin))

        self.assertEqual(registry.root, tree)
        self.assertEqual(registry.git_dir, self.work / "opengwasdb-stores.git")
        self.assertEqual(registry.ref, self.commit)
        self.assertTrue((tree / "docs" / "_epics" / "opengwasdb-stores-1.yaml").is_file())
        self.assertFalse((tree / "src").exists(), "only what the site reads is extracted")

    def test_a_reader_of_git_alone_extracts_nothing(self) -> None:
        tree = self.root / "tree"

        registry = staging.registry_root(tree=tree, url=str(self.origin), files=False)

        self.assertIsNone(registry.root)
        self.assertEqual((registry.git_dir, registry.ref), (self.work / "opengwasdb-stores.git", self.commit))
        self.assertFalse(tree.exists())

    def test_a_named_checkout_is_the_registry_itself(self) -> None:
        registry = staging.registry_root(self.checkout)

        self.assertEqual(registry.root, self.checkout.resolve())
        self.assertEqual(registry.git_dir, self.checkout.resolve())
        self.assertEqual(registry.ref, "HEAD")
        self.assertFalse((self.work / "opengwasdb-stores.git").exists(), "a named checkout needs no clone")


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
