"""`python3 -m project_site.architecture`: ask the architecture map from a terminal (#419, epic #416, og-dev-hub#9).

    check      [--repo NAME] [--registry P] [--data DIR] [--system FILE] [--refresh]
    conflicts  (--branch B [--repo NAME] | --files PATH... --repo NAME [--ticket repo#n])
               [--local GIT_DIR...] [--data DIR] [--refresh] [--days N]

`NAME` is a repository `system.yaml` lists.

`check` reports the code files no component claims and the claims that match no
file, in each repository with a model (or the one `--repo` names), and compares
the layering baseline of each repository whose model declares layers with the
upward imports measured, entry by entry (file and imported name), naming new and
stale ones. It exits 1 on any of them, else 2 when a part could not be checked
(the repository `--repo` names has no model or cannot be read, an unreadable
baseline, a failed fetch), else 0. Without `--repo`, a repository with no model
is named and is not a failure: it is a gap the site draws (og-dev-hub ADR 0001).

`conflicts` says which components a piece of work touches, which other owners have
live work (`building` or `active`) on each, and whether a blocking edge links its
ticket to theirs. It exits 1 when any such meet is uncoordinated, naming the other
work: its ticket, epic, branch and the files cited. Exit 2 means it could not decide
(a branch the collection does not hold, a source that is unavailable, code that no
component claims, work in a repository with no model, a fetch that failed): never
read that as "no conflict".

A fetch recorded as failed in the data read (`--refresh`, or the collection's own)
leaves `check` and `conflicts` undecided unless they find a problem anyway: what
was read may be out of date.

Both run from data collected on the spot with the site's own collectors, or from an
existing collection with `--data DIR`. Every repository is read from the site's
bare clone of it, fetched once first with `--refresh`; opengwasdb-stores from the
checkout `--registry` names instead. `--local GIT_DIR` adds the local branches of a
clone of any listed repository, recognised by its `origin` (an orchestrate host's
lanes live there), which the published page never shows.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO


from project_site import paths as site_paths
from project_site import staging
from project_site.collect import architecture, architecture_graph, architecture_model, board, branches, common, work

BASELINE_PATH = "docs/architecture/layering-baseline.yaml"
LIVE = ("building", "active")
UNDECIDED = 2


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


class Unavailable(RuntimeError):
    """The data needed to answer is not there; the command exits 2 and says why."""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def _architecture(args: argparse.Namespace) -> dict[str, Any]:
    if args.data:
        document, why = work._read(Path(args.data), "architecture")
        if document is None:
            raise Unavailable(why)
        return document
    result = common.collect_source("architecture", lambda: architecture.collect(args.repositories, system_file=args.system))
    if not result["available"]:
        raise Unavailable(f"architecture is unavailable: {result['error']}")
    return result


def _work(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(work, architecture)`: a collection's own, or collected now, plus any `--local` branches."""
    if args.data and not args.local:
        document, why = work._read(Path(args.data), "work")
        if document is None:
            raise Unavailable(why)
        return document, _architecture(args)
    if args.data:
        return _collected(args, Path(args.data))
    # Collecting on the spot needs scratch under the site's work root (/data), never the host's /tmp
    # (CONTRIBUTING, Worktrees). A host without it can still ask over a collection with --data.
    scratch_root = site_paths.work_root()
    try:
        scratch_root.mkdir(parents=True, exist_ok=True)
        scratch = tempfile.TemporaryDirectory(prefix="architecture-cli-", dir=scratch_root)
    except OSError as error:
        raise Unavailable(
            f"cannot make scratch under {scratch_root} ({error.strerror or type(error).__name__}); "
            f"set {site_paths.WORK_ROOT_ENV} to a writable directory, or read a collection with --data") from error
    with scratch:
        directory = Path(scratch.name)
        for source, collect in (("board", lambda: board.collect(common.gh_runner)),
                                ("architecture", lambda: architecture.collect(
                                    args.repositories, system_file=args.system))):
            common.write_source(directory, common.collect_source(source, collect))
        return _collected(args, directory)


def _collected(args: argparse.Namespace, directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """`(work, architecture)` computed from the collection in `directory` and the branches read now."""
    try:
        document = work.collect(directory, args.repositories, local=[Path(p) for p in args.local], days=args.days)
    except common.CollectError as error:
        raise Unavailable(f"work is unavailable: {error}") from error
    architecture_doc, why = work._read(directory, "architecture")
    if architecture_doc is None:
        raise Unavailable(why)
    return document, architecture_doc


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def check(args: argparse.Namespace, out: TextIO) -> int:
    document = _architecture(args)
    failed = unknown = False
    repos, gaps = document.get("repos") or {}, document.get("gaps") or {}
    if args.repo and args.repo not in repos:
        raise Unavailable(f"{args.repo} is not a repository system.yaml lists")
    names = [args.repo] if args.repo else list(repos)
    for failure in _fetch_failures(None, document, names):
        print(f"cannot check: the fetch failed for {failure}, so what was read may be out of date", file=out)
        unknown = True
    for name in names:
        repo = repos[name]
        at = f" ({repo.get('ref')} {str(repo.get('commit'))[:8]})"
        if repo.get("planned"):
            print(f"{name}: planned (not created yet), so nothing to check", file=out)
            unknown |= bool(args.repo)
            continue
        if repo.get("error"):
            print(f"{name}: cannot be read: {repo['error']}", file=out)
            unknown |= bool(args.repo)
            continue
        if not repo.get("model"):
            print(f"{name}{at}: no architecture model there, so nothing to check", file=out)
            unknown |= bool(args.repo)
            continue
        gap = gaps[name]
        print(f"{name}{at}: {len(gap['unclaimed'])} unclaimed, {len(gap['stale'])} stale", file=out)
        for path in gap["unclaimed"]:
            print(f"  unclaimed: {path}", file=out)
        for claim in gap["stale"]:
            print(f"  stale: {claim['path']} (claimed by {claim['component']})", file=out)
        failed |= bool(gap["unclaimed"] or gap["stale"])
    for name in (document.get("model") or {}).get("layers") or {}:
        if name not in names:
            continue
        try:
            failed |= _baseline(args, document, name, out)
        except Unavailable as error:
            print(f"cannot check: {error}", file=out)
            unknown = True
    # A problem in anything measured is 1; otherwise a part that could not be measured is 2, never a pass.
    return 1 if failed else UNDECIDED if unknown else 0


def _baseline(args: argparse.Namespace, document: Mapping[str, Any], name: str, out: TextIO) -> bool:
    """Print how repository `name`'s layering baseline compares with its measured upward imports; True when it does not match."""
    repo = document["repos"][name]
    try:
        handle = args.repositories.get(name).require()
        text = architecture.Tree(handle.git_dir, repo["commit"]).read([BASELINE_PATH]).get(BASELINE_PATH)
    except (common.CollectError, OSError) as error:
        # An unreadable repository is not an absent baseline: never certify the check.
        raise Unavailable(f"{name} layering baseline: not read ({error})") from error
    if text is None:
        print(f"{name}: no layering baseline at {repo['ref']} ({BASELINE_PATH} is not there)", file=out)
        return False
    try:
        listed = set(architecture_graph.load_baseline(text, BASELINE_PATH, key="allowed"))
    except common.CollectError as error:
        raise Unavailable(f"{name}: {error}") from error
    if document.get("upward_imports") is None:
        raise Unavailable(f"{name} layering baseline: the upward imports were not measured, so there is nothing to compare it with")
    repo_of = {c["id"]: c["repo"] for c in document["components"]}
    found = {(u["file"], u["name"]): u for u in document.get("upward_imports") or [] if repo_of.get(u["from"]) == name}
    print(f"{name} layering baseline: {len(listed)} allowed, {len(found)} measured upward imports", file=out)
    names = {c["id"]: c["name"] for c in document["components"]}
    for key in sorted(set(found) - listed):
        u = found[key]
        print(f"  new: {key[0]} {key[1]} ({names.get(u['from'], u['from'])}, layer {u['from_layer']} -> "
              f"{names.get(u['to'], u['to'])}, layer {u['to_layer']}): not in the baseline", file=out)
    for key in sorted(listed - set(found)):
        print(f"  stale: {key[0]} {key[1]}: listed but no longer imported upward", file=out)
    return listed != set(found)


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------


def conflicts(args: argparse.Namespace, out: TextIO) -> int:
    if args.files and not args.repo:
        raise Unavailable("--files needs --repo NAME (a repository system.yaml lists): a bare path can mean a file of any repository")
    document, architecture_doc = _work(args)
    components = {c["id"]: c for c in architecture_doc["components"]}
    own_owner, own_items, touched, label, unplaced, outside = _candidate(args, document, architecture_doc)
    print(label, file=out)
    if outside:
        print(f"outside the map (not code a component claims): {', '.join(outside)}", file=out)
    waits = [(w["item"], w["on"]) for w in document["waits"]]
    owners = {o["key"]: o for o in document["owners"]}
    failed = False
    any_meet = False
    for cid in sorted(touched):
        name = components[cid]["name"] if cid in components else cid
        others: dict[str, list[Mapping[str, Any]]] = {}
        for signal in document["signals"]:
            if signal["component"] == cid and signal["state"] in LIVE and signal["owner"] != own_owner:
                others.setdefault(signal["owner"], []).append(signal)
        if not others:
            continue
        any_meet = True
        print(f"{name} ({cid}) meets {len(others)} other owner{'s' if len(others) != 1 else ''}:", file=out)
        for owner, signals in sorted(others.items()):
            title = (owners.get(owner) or {}).get("title", "")
            print(f"  {owner} {title}".rstrip(), file=out)
            for s in signals:
                print(f"    {s['item']} [{s['state']}, {s['via']}] {', '.join(s['what'])}", file=out)
            theirs = {s["item"] for s in signals}
            pair = work.classify_pair(waits, sorted(own_items), sorted(theirs))
            if pair["coordination"] == "coordinated":
                print("    coordinated: " + "; ".join(f"{e['waiting']} waits for {e['on']}" for e in pair["edges"]), file=out)
                continue
            failed = True
            mine = ", ".join(sorted(own_items)) or "this work"
            if pair["coordination"] == "unlinkable":
                print("    UNLINKABLE: " + "; ".join(
                    f"{name} belongs to an epic as a whole, so no blocking edge can link it to a single ticket"
                    for name in pair["epic_branches"]) + "; asking a person is the safe default", file=out)
            else:
                print(f"    UNCOORDINATED: no blocking edge links {mine} and {', '.join(sorted(theirs))}", file=out)
    # Anything the map could not judge: a meet found is still 1, otherwise it is 2, never "no conflict".
    undecided = []
    if unplaced:
        undecided.append(f"no component claims {', '.join(unplaced)}, so what "
                         f"{'it meets' if len(unplaced) == 1 else 'they meet'} is unknown")
    if failures := _fetch_failures(document, architecture_doc):
        undecided.append(f"the fetch failed for {'; '.join(failures)}, so what was read may be out of date")
    if failed:
        for reason in undecided:
            print(f"also: {reason}", file=out)
        return 1
    if undecided:
        raise Unavailable("; and ".join(undecided))
    if not any_meet:
        print("meets no other work", file=out)
    return 0


def _fetch_failures(
    document: Mapping[str, Any] | None, architecture_doc: Mapping[str, Any], names: Sequence[str] | None = None,
) -> list[str]:
    """Each fetch the data read records as failed, of the repositories `names` (default every one).

    A repository's clone is fetched once per run for both its `main` and its
    branches (og-dev-hub#7, #9), so that one failure is named once.
    """
    def said(error: Any) -> str:
        return " ".join(str(error).split())[:200]

    failures = []
    named = set()
    for name, repo in (architecture_doc.get("repos") or {}).items():
        refresh = repo.get("refresh") if isinstance(repo, Mapping) else None
        if (names is None or name in names) and isinstance(refresh, Mapping) and refresh.get("ok") is False:
            failures.append(f"{possessive(name)} {repo.get('ref') or 'main'} ({said(refresh.get('error'))})")
            named.add(name)
    for source in ((document or {}).get("branches") or {}).get("sources") or []:
        fetch = source.get("fetch")
        if isinstance(fetch, Mapping) and fetch.get("ok") is False and source.get("repo") not in named:
            failures.append(f"the {source.get('repo')} branches ({said(fetch.get('error'))})")
            named.add(source.get("repo"))
    return failures


def _candidate(
    args: argparse.Namespace, document: Mapping[str, Any], architecture_doc: Mapping[str, Any]
) -> tuple[str | None, set[str], set[str], str, list[str], list[str]]:
    """`(owner, items, components touched, a heading, unplaced, outside)` of the work being asked about.

    `unplaced` is code no component claims, so the map cannot say what it meets (a mistyped path, or a
    new one whose claim does not exist yet); `outside` is the given files that are not code the
    model claims (tests, docs), which the map never judges.
    """
    ticket = args.ticket
    unmeasured = document.get("unmeasured") or {}
    claims: dict[str, list[tuple[str, str]]] = {}
    for c in architecture_doc["components"]:
        if c.get("paths"):
            claims.setdefault(c["repo"], []).extend(architecture_model.claims_of([c]))

    def is_code(repo: str) -> Any:
        return architecture_model.code_rule(claims.get(repo) or [])

    def unclaimed_code(repo: str, files: Sequence[str]) -> list[str]:
        rule = is_code(repo)
        return [f for f in files if rule(f) and architecture_model.owner(claims.get(repo) or [], f) is None]

    if args.branch:
        found = [b for b in document["branches"]["list"]
                 if b["name"] == args.branch and (not args.repo or b["repo"] == args.repo)]
        if not found:
            raise Unavailable(
                f"{args.branch}: no live branch of that name in the collection (ahead of main, within its window); "
                "add its git directory with --local, or give --files")
        b = found[0]
        if reason := unmeasured.get(b["repo"]):
            raise Unavailable(f"work on {b['repo']} was not measured: {reason}")
        items = {ticket} if ticket else {b["item"]}
        owner = document["tickets"].get(ticket) if ticket else b["owner"]
        return owner, items, set(b["components"]), (
            f"{b['repo']}:{b['name']}: {b['item']} of {b['owner']}, {len(b['files'])} files on "
            f"{len(b['components'])} components"), unclaimed_code(b["repo"], b["files"]), []
    if args.repo not in (architecture_doc.get("repos") or {}):
        raise Unavailable(f"{args.repo} is not a repository system.yaml lists")
    if reason := unmeasured.get(args.repo):
        raise Unavailable(f"work on {args.repo} was not measured: {reason}")
    mine = claims.get(args.repo) or []
    touched = {cid for f in args.files if (cid := architecture_model.owner(mine, f))}
    owner = document["tickets"].get(ticket) if ticket else None
    rule = is_code(args.repo)
    outside = [f for f in args.files if not rule(f) and architecture_model.owner(mine, f) is None]
    return owner, {ticket} if ticket else set(), touched, (
        f"{len(args.files)} files on {len(touched)} components" + (f" for {ticket}" if ticket else "")
    ), unclaimed_code(args.repo, args.files), outside


# ---------------------------------------------------------------------------


def _listed(args: argparse.Namespace) -> list[str]:
    """The repository names `system.yaml` lists, from the file the command reads."""
    system = args.system or site_paths.repo_root() / architecture.SYSTEM_FILE
    try:
        loaded = architecture_model.load_system(Path(system).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unavailable(f"{architecture.SYSTEM_FILE} cannot be read: {error}") from error
    return [entry["name"] for entry in loaded.get("repos") or []]


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    out = stdout or sys.stdout
    parser = argparse.ArgumentParser(prog="project_site.architecture", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "conflicts"):
        p = sub.add_parser(name)
        p.add_argument("--data", type=Path, default=None, help="read this collection (docs/_data) instead of collecting now")
        p.add_argument("--registry", type=Path, default=None,
                       help="an opengwasdb-stores checkout or git directory (default: the site's clone of it, at main)")
        p.add_argument("--system", type=Path, default=None, help="the system.yaml to read (default: this checkout's)")
        p.add_argument("--refresh", action="store_true", help="fetch every listed repository once first")
        p.add_argument("--repo", help="a repository system.yaml lists")
    conflict = sub.choices["conflicts"]
    what = conflict.add_mutually_exclusive_group(required=True)
    what.add_argument("--branch")
    what.add_argument("--files", nargs="+", metavar="PATH")
    conflict.add_argument("--ticket", help="the ticket the work is for (repo#n), to look for a blocking edge")
    conflict.add_argument("--local", nargs="+", default=[], metavar="GIT_DIR",
                          help="add the local branches of these clones of listed repositories")
    conflict.add_argument("--days", type=int, default=branches.WINDOW_DAYS)
    args = parser.parse_args(argv)
    # One read handle per repository for the whole command, by its one owner.
    args.repositories = staging.Repositories(refresh=args.refresh, checkouts={site_paths.REGISTRY: args.registry})
    try:
        if args.repo and args.repo not in _listed(args):
            raise Unavailable(f"{args.repo} is not a repository system.yaml lists")
        # The repository asked about must be readable to answer at all; a collection read with --data alone needs none.
        if args.repo and not (args.data and not getattr(args, "local", None)):
            handle = args.repositories.get(args.repo)
            if not handle.readable:
                raise Unavailable(str(handle.error))
        return (check if args.command == "check" else conflicts)(args, out)
    except Unavailable as error:
        print(f"cannot decide: {error}", file=out)
        return UNDECIDED


if __name__ == "__main__":
    sys.exit(main())
