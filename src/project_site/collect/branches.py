"""The live branches of one repository, for the Work map (#419, epic #416).

A branch is live work when it is ahead of `main` and its newest commit is no
older than a window (21 days by default). Its files are the diff against the
merge-base with `main` (`git diff --name-only -z main...<branch>`), read
NUL-delimited so a path holding a newline stays whole.

Which refs are read is the caller's choice, because the published page and a
build host see different things: the engine's bare clone holds pushed branches
as `refs/heads/*` after a fetch of `+refs/heads/*:refs/heads/*`; this
repository's checkout holds them as `refs/remotes/origin/*` after
`git fetch origin`; a developer's clone also has local ones in `refs/heads/*`.
This reader never fetches: the repository's read handle fetched it, once per run
(`staging.Repositories`), and the refs already there are read.

A branch with no merge base with `main` (an orphan, such as the CLA check's
`cla-signatures`) is no work against `main`: it has nothing to diff from. It is
skipped and named in `skipped` with the reason, never fatal (og-dev-hub#7).
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from project_site import staging
from project_site.collect.architecture_model import split_nul
from project_site.collect.common import CollectError

WINDOW_DAYS = 21
SKIPPED = frozenset({"main", "HEAD", "gh-pages"})

# `orch/<epic>/<ticket>` (optionally `-slug`); `orch/<epic>-...` and `orch/<epic>/...` (an epic's lane or integration
# branch); and a ticket number after a slash or an `issue-`, as `fix/issue-345` or `345-thing`.
LANE = re.compile(r"orch/(\d+)/(\d+)(?:-[\w.-]*)?$")
EPIC_LANE = re.compile(r"orch/(\d+)(?:[-/]|$)")
TICKET = re.compile(r"(?:^|/)(?:issue-)?(\d{2,4})(?=[-/]|$)")


def named_for(name: str, repo: str) -> tuple[str | None, str | None]:
    """The `(epic, ticket)` a branch name points at, as `repo#n` of the branch's own repository.

    The epic may really live in the other repository; the work collector, which
    knows the board's epics, settles that.
    """
    if match := LANE.match(name):
        return f"{repo}#{match[1]}", f"{repo}#{match[2]}"
    if match := EPIC_LANE.match(name):
        return f"{repo}#{match[1]}", None
    if match := TICKET.search(name):
        return None, f"{repo}#{match[1]}"
    return None, None


def _git(git_dir: Path, *args: str, accept: tuple[int, ...] = (0,)) -> str:
    """git's output; an exit status outside `accept` is the collector's error, naming the command."""
    done = subprocess.run(["git", "-C", str(git_dir), *args], capture_output=True, check=False)
    if done.returncode not in accept:
        raise CollectError(f"git {args[0]} exited {done.returncode}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout.decode("utf-8", "replace")


def collect(
    git_dir: Path,
    repo: str,
    *,
    main_ref: str = "main",
    prefixes: Sequence[str] = ("refs/heads/",),
    days: int = WINDOW_DAYS,
    now: dt.datetime | None = None,
    local: bool = False,
) -> dict[str, Any]:
    """`{"repo", "git_dir", "main", "days", "branches", "skipped"}` for one repository, as its git holds it now.

    `local` marks the branches as read from a developer's own clone rather than
    pushed ones.
    """
    git_dir = Path(git_dir)
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=days)
    main_commit, why = staging.resolve_ref(git_dir, main_ref)
    if main_commit is None:
        raise CollectError(f"{git_dir} has no {main_ref}: {why}")
    listing = _git(
        git_dir, "for-each-ref", "--format=%(refname)%09%(committerdate:iso-strict)%00", *prefixes
    )
    candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for record in split_nul(listing):
        if not record.strip("\n"):  # for-each-ref ends every record with a newline after the NUL
            continue
        ref, date = record.strip("\n").split("\t")
        name = next((ref[len(p):] for p in prefixes if ref.startswith(p)), ref)
        if name not in SKIPPED:
            candidates[name].append((ref, date))
    found = []
    skipped = []
    for name, refs in candidates.items():
        best = None
        for ref, date in refs:
            if dt.datetime.fromisoformat(date) < cutoff:
                continue
            ahead = int(_git(git_dir, "rev-list", "--count", f"{main_commit}..{ref}"))
            if ahead and (best is None or ahead > best[1]):
                best = (ref, ahead, date)
        if best is None:
            continue
        ref, ahead, date = best
        if not _has_merge_base(git_dir, main_commit, ref):
            skipped.append({"name": name, "reason": f"no merge base with {main_ref}"})
            continue
        files = split_nul(_git(git_dir, "diff", "--name-only", "-z", f"{main_commit}...{ref}"))
        epic, ticket = named_for(name, repo)
        found.append({"repo": repo, "name": name, "ahead": ahead, "committed": date, "files": files,
                      "epic": epic, "ticket": ticket, "local": local})
    found.sort(key=lambda b: b["name"])
    skipped.sort(key=lambda s: s["name"])
    return {"repo": repo, "git_dir": str(git_dir), "main": main_ref, "days": days, "branches": found,
            "skipped": skipped}


def _has_merge_base(git_dir: Path, main_commit: str, ref: str) -> bool:
    """Whether `ref` shares history with `main`: `git merge-base` prints one, or exits 1 when there is none."""
    return bool(_git(git_dir, "merge-base", main_commit, ref, accept=(0, 1)).strip())
