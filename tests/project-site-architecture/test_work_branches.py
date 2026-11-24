#!/usr/bin/env python3
"""Branches for the Work map, read from a fixture git repository (#419).

A branch counts when it is ahead of `main` and its newest commit is inside the
window; its files are the diff against the merge-base, read NUL-delimited, and
its ticket comes from its name. Expected values are literals written from the
fixture built in `Fixture`.

Run from the repository root:
    python3 tests/project-site-architecture/test_work_branches.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import architecture_fixtures as fx

from project_site import staging
from project_site.collect import branches, common, work
from project_site.collect.common import CollectError

NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)


def commit(repo: Path, files: dict[str, str], when: str, message: str = "work") -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    fx.git(repo, "add", "--", *files)
    env = {**os.environ, "GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@e.org", "commit", "-q", "-m", message],
        check=True, env=env, capture_output=True,
    )


class Fixture:
    """`main` with one commit; branches cut from it at fixed dates (window: 21 days before NOW)."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="branches-"))
        test.addCleanup(shutil.rmtree, self.root, True)
        self.repo = self.root / "repo"
        fx.make_repo(self.repo, {"src/a.py": "a = 1\n", "src/b.py": "b = 1\n"})
        fx.git(self.repo, "branch", "-m", "main")
        # 29 Oct 2026: inside the window, ahead of main by two commits.
        fx.git(self.repo, "checkout", "-q", "-b", "orch/416/419", "main")
        commit(self.repo, {"src/a.py": "a = 2\n"}, "2026-10-28T10:00:00+00:00")
        commit(self.repo, {"src/new dir/c.py": "c = 1\n", "src/odd\nname.py": "x = 1\n"}, "2026-10-29T10:00:00Z")
        # 1 Sep 2026: older than 21 days.
        fx.git(self.repo, "checkout", "-q", "-b", "stale-work", "main")
        commit(self.repo, {"src/b.py": "b = 2\n"}, "2026-09-01T10:00:00+00:00")
        # Recent, but nothing ahead of main.
        fx.git(self.repo, "branch", "caught-up", "main")
        # An issue number after a slash, and a lane of an epic with no ticket in its name.
        fx.git(self.repo, "checkout", "-q", "-b", "fix/issue-345", "main")
        commit(self.repo, {"src/b.py": "b = 3\n"}, "2026-11-01T10:00:00+00:00")
        fx.git(self.repo, "checkout", "-q", "-b", "orch/302-integration", "main")
        commit(self.repo, {"src/a.py": "a = 9\n"}, "2026-11-01T11:00:00+00:00")
        fx.git(self.repo, "checkout", "-q", "main")

    def collect(self, **kwargs):
        return branches.collect(self.repo, "opengwasdb-stores", main_ref="main",
                                prefixes=("refs/heads/",), now=NOW, **kwargs)


class BranchTests(unittest.TestCase):
    def test_a_branch_ahead_of_main_within_the_window_is_listed_with_its_files_and_ticket(self) -> None:
        result = Fixture(self).collect()
        lane = next(b for b in result["branches"] if b["name"] == "orch/416/419")
        self.assertEqual(
            {k: lane[k] for k in ("repo", "ahead", "ticket", "epic")},
            {"repo": "opengwasdb-stores", "ahead": 2, "ticket": "opengwasdb-stores#419", "epic": "opengwasdb-stores#416"},
        )
        self.assertEqual(lane["files"], ["src/a.py", "src/new dir/c.py", "src/odd\nname.py"])
        self.assertEqual(lane["committed"], "2026-10-29T10:00:00Z")

    def test_a_branch_older_than_the_window_or_not_ahead_is_not_listed(self) -> None:
        names = [b["name"] for b in Fixture(self).collect()["branches"]]
        self.assertEqual(names, ["fix/issue-345", "orch/302-integration", "orch/416/419"])

    def test_the_window_is_a_parameter(self) -> None:
        names = [b["name"] for b in Fixture(self).collect(days=90)["branches"]]
        self.assertIn("stale-work", names)

    def test_a_ticket_number_after_a_slash_names_a_ticket_and_an_epic_lane_names_only_the_epic(self) -> None:
        by_name = {b["name"]: b for b in Fixture(self).collect()["branches"]}
        self.assertEqual((by_name["fix/issue-345"]["epic"], by_name["fix/issue-345"]["ticket"]), (None, "opengwasdb-stores#345"))
        self.assertEqual((by_name["orch/302-integration"]["epic"], by_name["orch/302-integration"]["ticket"]),
                         ("opengwasdb-stores#302", None))

    def test_a_lane_whose_ticket_number_is_followed_by_a_slug_still_names_its_ticket(self) -> None:
        fixture = Fixture(self)
        fx.git(fixture.repo, "checkout", "-q", "-b", "orch/58/354-guard", "main")
        commit(fixture.repo, {"src/b.py": "b = 5\n"}, "2026-11-02T08:00:00+00:00")
        by_name = {b["name"]: b for b in fixture.collect()["branches"]}
        self.assertEqual((by_name["orch/58/354-guard"]["epic"], by_name["orch/58/354-guard"]["ticket"]),
                         ("opengwasdb-stores#58", "opengwasdb-stores#354"))

    def test_a_branch_that_names_no_ticket_has_neither(self) -> None:
        fixture = Fixture(self)
        fx.git(fixture.repo, "checkout", "-q", "-b", "scratch", "main")
        commit(fixture.repo, {"src/b.py": "b = 4\n"}, "2026-11-02T08:00:00+00:00")
        by_name = {b["name"]: b for b in fixture.collect()["branches"]}
        self.assertEqual((by_name["scratch"]["epic"], by_name["scratch"]["ticket"]), (None, None))

    def mirror(self, fixture: "Fixture", origin: Path) -> Path:
        """A bare clone of the fixture, as the site keeps one, fetching from `origin`."""
        mirror = fixture.root / "mirror.git"
        fx.git(fixture.root, "clone", "-q", "--bare", str(fixture.repo), str(mirror))
        fx.git(mirror, "remote", "set-url", "origin", str(origin))
        return mirror

    def read(self, mirror: Path) -> dict:
        """The branches as a run reads them: through the repository's handle, which fetched it once (og-dev-hub#6)."""
        repositories = staging.Repositories(refresh=True, git_dirs={"opengwasdb-stores": mirror})
        (found,) = work.read_branches(repositories, ["opengwasdb-stores"], now=NOW)
        return found

    def test_a_failed_fetch_is_recorded_and_the_branches_already_there_are_read(self) -> None:
        fixture = Fixture(self)
        result = self.read(self.mirror(fixture, fixture.root / "no-such-origin"))
        self.assertFalse(result["fetch"]["ok"])
        self.assertIn("no-such-origin", result["fetch"]["error"])
        self.assertEqual(len(result["branches"]), 3)

    def test_a_fetch_that_works_brings_a_pushed_branch(self) -> None:
        fixture = Fixture(self)
        mirror = self.mirror(fixture, fixture.repo)
        for name in ("orch/416/419", "stale-work", "caught-up", "fix/issue-345", "orch/302-integration"):
            fx.git(mirror, "branch", "-D", name)
        result = self.read(mirror)
        self.assertEqual(result["fetch"], {"ok": True, "error": None})
        self.assertEqual([b["name"] for b in result["branches"]], ["fix/issue-345", "orch/302-integration", "orch/416/419"])


class OneHandlePerRepositoryTests(unittest.TestCase):
    """Each listed repository's clone is fetched once per run, and work reads the `main` the architecture read (og-dev-hub#7, #9)."""

    NAMES = ("opengwasdb-stores", "opengwasdb", "ogquery")

    def test_a_refresh_fetches_each_clone_once_and_reads_the_branches_of_every_repository(self) -> None:
        fixture = Fixture(self)
        github = fixture.root / "github"
        github.mkdir()
        for name in self.NAMES:
            fx.git(fixture.root, "clone", "-q", "--bare", str(fixture.repo), str(github / name))
        with mock.patch.dict(os.environ, {"OPENGWASDB_SITE_ROOT": str(fixture.root / "work")}), \
                mock.patch.object(staging.paths, "GITHUB", str(github)):
            first = staging.Repositories()
            for name in self.NAMES:
                first.get(name)  # the first read clones each
            calls = []
            real = staging.ensure_clone

            def counted(git_dir, **kwargs):
                calls.append(Path(git_dir))
                return real(git_dir, **kwargs)

            with mock.patch.object(staging, "ensure_clone", counted):
                repositories = staging.Repositories(refresh=True)
                read = {name: repositories.get(name) for name in self.NAMES}  # as the architecture collector reads them
                sets = work.read_branches(repositories, list(self.NAMES), now=NOW)
            clones = {name: staging.paths.clone_dir(name) for name in self.NAMES}

        self.assertEqual(sorted(calls), sorted(clones.values()), "one fetch per repository, none for the work")
        for name in self.NAMES:
            found = next(s for s in sets if s["repo"] == name)
            self.assertEqual(found["fetch"], {"ok": True, "error": None})
            self.assertIs(read[name], repositories.get(name))
        # A third repository's branches are read like the two the site always read.
        third = next(s for s in sets if s["repo"] == "ogquery")
        self.assertEqual([b["name"] for b in third["branches"]], ["fix/issue-345", "orch/302-integration", "orch/416/419"])
        self.assertEqual({b["repo"] for b in third["branches"]}, {"ogquery"})

    def test_a_repository_whose_branches_cannot_be_read_is_recorded_and_the_others_are_read(self) -> None:
        fixture = Fixture(self)
        repositories = staging.Repositories(git_dirs={"opengwasdb": fixture.repo, "ogld": fixture.root / "nowhere.git"})
        sets = work.read_branches(repositories, ["opengwasdb", "ogld"], now=NOW)
        broken = next(s for s in sets if s["repo"] == "ogld")
        self.assertIn("ogld cannot be read", broken["error"])
        self.assertEqual(broken["branches"], [])
        self.assertEqual(len(next(s for s in sets if s["repo"] == "opengwasdb")["branches"]), 3)

    def test_a_local_clone_is_recognised_by_its_origin_and_one_of_no_listed_repository_is_refused(self) -> None:
        fixture = Fixture(self)
        fx.git(fixture.repo, "remote", "add", "origin", "https://github.com/opengwas/ogquery.git")
        self.assertEqual(work.repo_of(fixture.repo, ["opengwasdb", "ogquery"]), "ogquery")
        with self.assertRaises(CollectError) as caught:
            work.repo_of(fixture.repo, ["opengwasdb"])
        self.assertIn("is not a clone of a repository system.yaml lists", str(caught.exception))


class GitFailureTests(unittest.TestCase):
    """A git failure is the collector's error, so the CLI exits 2 and a collector run marks `work` unavailable."""

    def test_a_directory_that_is_not_a_repository_raises_the_collectors_error(self) -> None:
        missing = Path(tempfile.mkdtemp(prefix="branches-")) / "no-such-repo"
        self.addCleanup(shutil.rmtree, missing.parent, True)
        with self.assertRaises(CollectError) as caught:
            branches.collect(missing, "opengwasdb-stores", main_ref="main", now=NOW)
        self.assertIn("no-such-repo", str(caught.exception))



class OrphanBranchTests(unittest.TestCase):
    """A branch with no merge base with `main` is no work against it (og-dev-hub#7).

    Since 22 Nov 2026 opengwasdb and opengwasdb-stores each keep the CLA check's
    signatures on an orphan branch, `cla-signatures`. `git diff main...<branch>`
    has no merge base to diff from and exits 128, which made the whole `work`
    source unavailable and every `architecture conflicts` undecided. It is
    skipped, and named with the reason, and never fatal.
    """

    def orphan(self) -> Fixture:
        fixture = Fixture(self)
        fx.git(fixture.repo, "checkout", "-q", "--orphan", "cla-signatures")
        fx.git(fixture.repo, "rm", "-rq", "--cached", ".")
        commit(fixture.repo, {"signatures/cla.json": "[]\n"}, "2026-11-22T08:00:00+00:00")
        fx.git(fixture.repo, "checkout", "-q", "-f", "main")
        return fixture

    def test_an_orphan_branch_is_skipped_and_named_and_the_others_are_read(self) -> None:
        result = self.orphan().collect()

        self.assertEqual([b["name"] for b in result["branches"]], ["fix/issue-345", "orch/302-integration", "orch/416/419"])
        self.assertEqual(result["skipped"], [{"name": "cla-signatures", "reason": "no merge base with main"}])

    def test_a_repository_without_one_skips_nothing(self) -> None:
        self.assertEqual(Fixture(self).collect()["skipped"], [])

    def test_a_merge_base_that_fails_otherwise_is_an_error_not_a_skip(self) -> None:
        # Only "no merge base" (exit 1) means an orphan; any other failure of
        # `git merge-base` (exit 128, here a ref that cannot be resolved) is the
        # collector's error, as every other git failure is.
        fixture = self.orphan()
        real = branches._git

        def unresolvable(git_dir, *args, **kwargs):
            if args[0] == "merge-base":
                args = (*args[:-1], "refs/heads/no-such-branch")
            return real(git_dir, *args, **kwargs)

        with mock.patch.object(branches, "_git", unresolvable), self.assertRaises(CollectError) as caught:
            fixture.collect()
        self.assertIn("git merge-base exited 128", str(caught.exception))

    def test_the_work_source_stays_available_and_says_what_it_left_out(self) -> None:
        fixture = self.orphan()
        data = fixture.root / "data"
        data.mkdir()
        (data / "board.json").write_text(json.dumps({"source": "board", "available": True, "epics": []}))
        (data / "architecture.json").write_text(json.dumps({
            "source": "architecture", "available": True, "components": [],
            "repos": {"opengwasdb": {"ref": "main", "commit": "0" * 40, "model": True}},
        }))

        result = common.collect_source("work", lambda: work.collect(
            data, staging.Repositories(git_dirs={"opengwasdb": fixture.repo}), now=NOW))

        self.assertTrue(result["available"], result["error"])
        # The fixture stands in for the engine's clone, whose branches are read as `refs/heads/*`.
        engine = next(s for s in result["branches"]["sources"] if s["repo"] == "opengwasdb")
        self.assertEqual(engine["skipped"], [{"name": "cla-signatures", "reason": "no merge base with main"}])
        self.assertNotIn("cla-signatures", [b["name"] for b in result["branches"]["list"]])


if __name__ == "__main__":
    unittest.main()
