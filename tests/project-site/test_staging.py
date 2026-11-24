#!/usr/bin/env python3
"""Where every repository is read from: the clones, the read handles and the registry's files (og-dev-hub#7, og-dev-hub#9).

Run from the repository root:
    python3 tests/project-site/test_staging.py
"""

from __future__ import annotations

import shutil
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from project_site import paths, staging
from project_site.collect.common import CollectError


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


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

    def test_a_run_given_a_root_clones_under_it(self) -> None:
        root = self.hub.root / "site-work"
        handle = staging.Repositories(root=root).get("opengwasdb-stores")
        self.assertEqual(handle.git_dir, root / "opengwasdb-stores.git")
        self.assertEqual(handle.commit, self.first)


class RegistryTreeTest(unittest.TestCase):
    """The registry the collectors read: its clone's `main`, extracted, or a checkout named instead (og-dev-hub#7)."""

    FILES = {
        "stores/OGS-00001/release.yaml": "store_id: OGS-00001\n",
        "docs/archive/old.yaml": "kept: elsewhere\n",
        "docs/_yardstick/2026-11-01.json": "{}\n",
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
        self.assertTrue((self.tree / "docs" / "_yardstick" / "2026-11-01.json").is_file())
        self.assertFalse((self.tree / "docs" / "archive").exists(), "only the Stores' readers' files are extracted")
        self.assertFalse((self.tree / "docs" / "a.md").exists())
        self.assertFalse((self.tree / "CONTEXT.md").exists())
        self.assertFalse((self.tree / "pixi.lock").exists())

    def test_a_second_extraction_replaces_the_first(self) -> None:
        clone = paths.clone_dir("opengwasdb-stores")
        staging.ensure_clone(clone, url=paths.clone_url("opengwasdb-stores"))
        staging.extract_tree(clone, "main", self.tree)
        (self.tree / "docs" / "_yardstick" / "left-behind.json").write_text("{}\n", encoding="utf-8")

        staging.extract_tree(clone, "main", self.tree)

        self.assertFalse((self.tree / "docs" / "_yardstick" / "left-behind.json").exists())

    def test_without_a_checkout_the_registry_is_its_clones_main(self) -> None:
        registry = staging.Repositories(tree=self.tree).get("opengwasdb-stores", files=True)

        self.assertEqual(registry.root, self.tree)
        self.assertEqual(registry.git_dir, self.hub.work / "opengwasdb-stores.git")
        self.assertEqual((registry.ref, registry.commit), ("main", self.commit))
        self.assertTrue(registry.clone)
        self.assertTrue((self.tree / "stores" / "OGS-00001" / "release.yaml").is_file())
        self.assertFalse((self.tree / "src").exists(), "only what the site reads is extracted")

    def test_reading_the_registry_fetches_only_when_a_refresh_is_asked_for(self) -> None:
        staging.Repositories(tree=self.tree).get("opengwasdb-stores")
        newer = self.hub.commit("opengwasdb-stores", {"docs/a.md": "# A, again\n"})

        self.assertEqual(staging.Repositories(tree=self.tree).get("opengwasdb-stores").commit, self.commit, "a read is not a fetch")
        refreshed = staging.Repositories(tree=self.tree, refresh=True).get("opengwasdb-stores")

        self.assertEqual(refreshed.commit, newer)
        self.assertEqual(refreshed.fetch, {"ok": True, "error": None})

    def test_a_failed_refresh_is_recorded_and_the_main_it_has_is_read(self) -> None:
        staging.Repositories(tree=self.tree).get("opengwasdb-stores")
        self.hub.offline()

        registry = staging.Repositories(tree=self.tree, refresh=True).get("opengwasdb-stores")

        self.assertEqual(registry.commit, self.commit)
        self.assertFalse(registry.fetch["ok"])

    def test_a_registry_that_cannot_be_cloned_cannot_be_read_and_says_why(self) -> None:
        self.hub.offline()

        registry = staging.Repositories(tree=self.tree).get("opengwasdb-stores")

        self.assertFalse(registry.readable)
        self.assertIn("opengwasdb-stores", registry.error)
        self.assertIn("no-network", registry.error)
        with self.assertRaises(CollectError) as caught:
            registry.require()
        self.assertIn("no-network", str(caught.exception))

    def test_a_reader_of_git_alone_extracts_nothing(self) -> None:
        registry = staging.Repositories(tree=self.tree).get("opengwasdb-stores")

        self.assertIsNone(registry.root)
        self.assertEqual((registry.git_dir, registry.commit), (self.hub.work / "opengwasdb-stores.git", self.commit))
        self.assertFalse(self.tree.exists())

    def test_a_named_checkout_is_the_registry_itself(self) -> None:
        registry = staging.Repositories(checkouts={"opengwasdb-stores": self.checkout}).get("opengwasdb-stores", files=True)

        self.assertEqual(registry.root, self.checkout.resolve())
        self.assertEqual(registry.git_dir, self.checkout.resolve())
        self.assertEqual((registry.ref, registry.commit), ("HEAD", self.commit))
        self.assertFalse(registry.clone)
        self.assertFalse((self.hub.work / "opengwasdb-stores.git").exists(), "a named checkout needs no clone")

    def test_only_opengwasdb_stores_has_its_files_extracted(self) -> None:
        with self.assertRaises(ValueError):
            staging.Repositories(tree=self.tree).get("opengwasdb", files=True)


class RepositoryReadTest(unittest.TestCase):
    """A repository's files are read one way: through its handle, at the commit read or one named (og-dev-hub#6)."""

    def test_named_files_are_read_at_the_commit_read_or_at_another(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="repo-read-"))
        self.addCleanup(shutil.rmtree, root, True)
        git(root, "init", "-q", "-b", "main")
        for name, text in (("a.txt", "one\n"), ("odd\nname.py", "x = 1\n")):
            (root / name).write_text(text, encoding="utf-8")
        git(root, "add", "-A")
        git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "first")
        first = git(root, "rev-parse", "HEAD")
        (root / "a.txt").write_text("two\n", encoding="utf-8")
        git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qam", "second")
        handle = staging.Repositories(git_dirs={"opengwasdb": root}).get("opengwasdb")

        self.assertEqual(handle.read(["a.txt", "odd\nname.py", "missing.txt"]), {"a.txt": "two\n", "odd\nname.py": "x = 1\n"})
        self.assertEqual(handle.read(["a.txt"], at=first), {"a.txt": "one\n"})
        self.assertEqual(sorted(handle.tree().files), ["a.txt", "odd\nname.py"])


class ReadHandleTest(unittest.TestCase):
    """One read handle per listed repository per run: cloned, fetched once, and a failure recorded (og-dev-hub#9)."""

    def setUp(self) -> None:
        self.hub = GithubFixture(self)
        self.commits = {name: self.hub.repository(name, {"README.md": f"# {name}\n"})
                        for name in ("opengwasdb", "ogquery")}

    def test_a_listed_repository_is_cloned_and_fetched_once_per_run(self) -> None:
        staging.Repositories().get("ogquery")  # the first read clones it
        calls = []
        real = staging.ensure_clone

        def counted(git_dir, **kwargs):
            calls.append((Path(git_dir).name, kwargs.get("fetch")))
            return real(git_dir, **kwargs)

        with mock.patch.object(staging, "ensure_clone", counted):
            run = staging.Repositories(refresh=True)
            first = run.get("ogquery")
            again = run.get("ogquery")

        self.assertIs(first.git_dir, again.git_dir)
        self.assertEqual(calls, [("ogquery.git", True)])
        self.assertEqual((first.commit, first.fetch), (self.commits["ogquery"], {"ok": True, "error": None}))

    def test_a_fetch_that_fails_is_that_repositorys_and_the_others_are_read(self) -> None:
        run = staging.Repositories(refresh=True)
        run.get("ogquery")
        shutil.rmtree(self.hub.github / "ogquery")

        again = staging.Repositories(refresh=True)
        failed, other = again.get("ogquery"), again.get("opengwasdb")

        self.assertFalse(failed.fetch["ok"])
        self.assertEqual(failed.commit, self.commits["ogquery"], "what the clone holds is still read")
        self.assertEqual((other.commit, other.fetch), (self.commits["opengwasdb"], {"ok": True, "error": None}))

    def test_a_repository_that_does_not_exist_cannot_be_read_and_says_why(self) -> None:
        missing = staging.Repositories().get("no-such-repository")

        self.assertFalse(missing.readable)
        self.assertIn("no-such-repository", missing.error)


if __name__ == "__main__":
    unittest.main()
