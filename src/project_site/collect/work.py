"""Where live work meets: the `work` source (#419, epic #416).

It reads what the `board` and `architecture` collectors wrote to the same data
directory, so it is unavailable, naming which, when either is. From those it
places every piece of live work on the components that code claims:

- `building`: a branch's diff against the merge-base with `main`;
- `active`: a file cited by an open ticket of an Active epic;
- `scope`: a file cited by an epic's body;
- `waiting`: a file cited by an open ticket blocked by an open ticket;
- `planned` / `paused`: a file cited by an open ticket of a Todo / Paused epic;
- `stale`: a branch whose epic or ticket is closed.

A meet is a component on which two or more owners (epics, or a branch or ticket
off the board) have `building` or `active` work. It is coordinated only when,
for every pair of those owners, a blocking edge links two specific tickets of
the pair, in either direction. Sharing an epic or having an edge elsewhere
between the epics does not count. The output is documented, and versioned by
`schema_version`, in `docs/spec/project-site.md`.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from project_site import staging
from project_site.collect import architecture_model as model_rules, branches as branch_reader, citations, plans as plan_reader
from project_site.collect.common import CollectError

SCHEMA_VERSION = 1
LIVE_STATUSES = ("Active", "Todo", "Paused")
LIVE_STATES = ("building", "active")
STATUS_STATE = {"Active": "active", "Todo": "planned", "Paused": "paused"}


def compute(
    board: Mapping[str, Any],
    architecture: Mapping[str, Any],
    branch_sets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The work output from the two collectors' documents and the branches read; no I/O."""
    components = [c for c in architecture.get("components") or [] if isinstance(c, Mapping)]
    repos = {name: r for name, r in (architecture.get("repos") or {}).items() if isinstance(r, Mapping)}
    claims = model_rules.claims_by_repository(components, repos)
    by_id = {c["id"]: c for c in components}
    # Without a repository's model no file of it belongs to any component, so its work is
    # unknown: it is said to be, never turned into "no work" or "no meets".
    unmeasured: dict[str, str] = {
        name: str(r.get("note") or r.get("error") or f"no architecture model at {r.get('ref')}")
        for name, r in repos.items() if not r.get("planned") and not r.get("model")
    }

    listed = architecture.get("files")
    listings = {k: v for k, v in listed.items() if isinstance(v, list)} if isinstance(listed, Mapping) else {}

    is_code = {repo: model_rules.code_rule(claims[repo]) for repo in claims}
    roots = {repo: _source_root(repos.get(repo) or {}, claims[repo]) for repo in claims}

    def place(strings: Sequence[str], home: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, list[str]]]]:
        """`(component, cited string, path status)` for each placed citation, and the ambiguous ones.

        The status is `found` (a tracked file), `not found` (a code path no tracked file
        is, nor ends with: attributed by its claim all the same), `unchecked` (no file
        inventory, or not a code path, so existence is not known) or `n/a` (a dotted module).
        """
        placed: list[tuple[str, str, str]] = []
        unresolved: list[tuple[str, list[str]]] = []
        order = (home, *[k for k in claims if k != home])
        for text in strings:
            status = "n/a"
            if "/" in text:
                got = citations.resolve_path(text, home, listings)
                if got.candidates:
                    unresolved.append((text, sorted(path for _, path in got.candidates)))
                    continue
                if got.found:
                    status, targets = "found", [got.found]
                else:
                    targets = [(kind, citations.without_line(text)) for kind in order]
            else:
                targets = [(kind, path) for kind in order for path in _modules(text, roots[kind])]
            for kind, path in targets:
                if cid := model_rules.owner(claims.get(kind) or [], path):
                    if "/" in text and status != "found":
                        status = "not found" if kind in listings and is_code[kind](path) else "unchecked"
                    placed.append((cid, text, status))
                    break
        return placed, unresolved

    epics = {e["key"]: e for e in board.get("epics") or [] if e.get("state") == "OPEN" and e.get("status") in LIVE_STATUSES}
    every_epic = {e["key"]: e for e in board.get("epics") or []}
    ticket_epic = {c["key"]: e["key"] for e in every_epic.values() for c in e.get("children") or []}
    ticket_state = {c["key"]: c["state"] for e in every_epic.values() for c in e.get("children") or []}
    owners: dict[str, dict[str, Any]] = {
        key: {"key": key, "kind": "epic", "title": _title(e), "url": e.get("url"), "status": e["status"],
              "workstream": e.get("workstream")}
        for key, e in epics.items()
    }
    waits: list[tuple[str, str]] = []
    for e in epics.values():
        for child in e.get("children") or []:
            waits += [(child["key"], b["key"]) for b in child.get("blocked_by") or [] if b.get("state") == "OPEN"]
    blocked = {item for item, _ in waits}

    signals: dict[tuple[str, str, str, str, str, str], set[str]] = defaultdict(set)
    not_found_rows: set[tuple[str, str, str, str]] = set()
    unresolved_rows: set[tuple[str, str, str, tuple[str, ...]]] = set()

    def signal(cid: str, owner: str, item: str, via: str, state: str, what: Sequence[str], path: str = "found") -> None:
        signals[(cid, owner, item, via, state, path)].update(what)

    def cited_signals(owner: str, item: str, via: str, state: str, placed: Sequence[tuple[str, str, str]]) -> None:
        for cid, text, path in placed:
            signal(cid, owner, item, via, state, [text], path)
            if path == "not found":
                not_found_rows.add((owner, item, text, cid))

    for key, e in epics.items():
        home = _home(key, claims)
        # An epic of a repository without a model has no claims to cite against.
        placed, ambiguous = place(e.get("cited") or [], home) if home else ([], [])
        unresolved_rows |= {(key, key, text, tuple(paths)) for text, paths in ambiguous}
        cited_signals(key, key, "scope", "scope", placed)
        for child in e.get("children") or []:
            if child["state"] != "OPEN":
                continue
            state = "waiting" if child["key"] in blocked else STATUS_STATE[e["status"]]
            child_home = _home(child["key"], claims)
            placed, ambiguous = place(child.get("cited") or [], child_home) if child_home else ([], [])
            unresolved_rows |= {(key, child["key"], text, tuple(paths)) for text, paths in ambiguous}
            cited_signals(key, child["key"], "cited", state, placed)

    # A branch can be read from two clones (pushed, and a host's own): it counts once, and the
    # copy further ahead wins, because it holds commits the other lacks; a tie keeps the first read.
    chosen: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
    sources = []
    for found in branch_sets:
        sources.append({k: found.get(k) for k in ("repo", "git_dir", "main", "days", "fetch", "error")}
                       | {"local": any(b.get("local") for b in found["branches"]), "count": len(found["branches"]),
                          # What the reader left out, by name and reason: an orphan branch is no work against main.
                          "skipped": list(found.get("skipped") or [])})
        for b in found["branches"]:
            key = (found["repo"], b["name"])
            if key not in chosen or b["ahead"] > chosen[key][1]["ahead"]:
                chosen[key] = (found["repo"], b)
    listed: list[dict[str, Any]] = []
    for repo, b in chosen.values():
        owner, item, state, unknown = _branch_owner(b, repo, list(repos), epics, every_epic, ticket_epic, ticket_state, owners)
        cids = sorted({cid for f in b["files"] if (cid := model_rules.owner(claims.get(repo) or [], f))})
        for cid in cids:
            signal(cid, owner, item, "branch", state, [f"{repo}:{b['name']}"])
        listed.append({**b, "owner": owner, "item": item, "components": cids, "owner_unknown": unknown})

    rows = [
        {"component": cid, "owner": owner, "item": item, "via": via, "state": state, "path": path, "what": sorted(what)}
        for (cid, owner, item, via, state, path), what in sorted(signals.items())
    ]
    live: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        if row["state"] in LIVE_STATES:
            live[row["component"]][row["owner"]].add(row["item"])
    meets = []
    for cid, by_owner in sorted(live.items()):
        if len(by_owner) < 2:
            continue
        names = sorted(by_owner)
        pairs = []
        for a, b in combinations(names, 2):
            pair = classify_pair(waits, by_owner[a], by_owner[b])
            pairs.append({"owners": [a, b], "coordinated": pair["coordination"] == "coordinated", **pair})
        kinds = {p["coordination"] for p in pairs}
        meets.append({"component": cid, "owners": names, "items": {o: sorted(by_owner[o]) for o in names},
                      "pairs": pairs, "coordinated": kinds == {"coordinated"},
                      "coordination": "uncoordinated" if "uncoordinated" in kinds
                      else "unlinkable" if "unlinkable" in kinds else "coordinated"})
    with_signals = {row["owner"] for row in rows}
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "board": {"collected_at": board.get("collected_at")},
            "architecture": {
                "collected_at": architecture.get("collected_at"),
                "repos": {name: {k: r.get(k) for k in ("ref", "commit", "visibility")} for name, r in repos.items()},
            },
        },
        "owners": [owners[k] for k in sorted(owners) if k in with_signals],
        "components": [
            {"id": cid, "name": by_id[cid]["name"], "repo": by_id[cid]["repo"]}
            for cid in sorted({r["component"] for r in rows})
        ],
        "unmeasured": unmeasured,
        "signals": rows,
        "unresolved": [
            {"owner": o, "item": i, "cited": text, "candidates": list(paths)}
            for o, i, text, paths in sorted(unresolved_rows)
        ],
        "not_found": [
            {"owner": o, "item": i, "cited": text, "component": c} for o, i, text, c in sorted(not_found_rows)
        ],
        "meets": meets,
        "plans": plan_reader.listed(board, architecture),
        "tickets": {c["key"]: key for key, e in epics.items() for c in e.get("children") or [] if c["state"] == "OPEN"},
        "waits": [{"item": x, "on": y} for x, y in waits],
        "branches": {"sources": sources, "list": sorted(listed, key=lambda b: (b["repo"], b["name"]))},
        "summary": {
            "owners": len(with_signals),
            "meets": len(meets),
            "coordinated": sum(1 for m in meets if m["coordinated"]),
            "uncoordinated": sum(1 for m in meets if m["coordination"] == "uncoordinated"),
            "unlinkable": sum(1 for m in meets if m["coordination"] == "unlinkable"),
            "branches": len(listed),
            "unresolved": len(unresolved_rows),
            "not_found": len(not_found_rows),
        },
    }


def classify_pair(waits: Sequence[tuple[str, str]], one: Sequence[str], other: Sequence[str]) -> dict[str, Any]:
    """How two owners' items on one component are coordinated: the one classifier the collector and the CLI share.

    `coordination` is `coordinated` when a blocking edge `(waiting, on)` links an item of
    one with an item of the other, in either direction; else `unlinkable` when one side's
    work is an epic's integration branch (no ticket an edge could link); else `uncoordinated`.
    `edges` are the `{waiting, on}` links, and `epic_branches` the integration branches
    involved, empty when an edge coordinates the pair.
    """
    one_set, other_set = set(one), set(other)
    edges = [
        {"waiting": x, "on": y} for x, y in waits
        if (x in one_set and y in other_set) or (x in other_set and y in one_set)
    ]
    # An epic's integration branch belongs to the epic as a whole: no ticket for an edge to link.
    epic_branches = epic_level_branches([*one_set, *other_set])
    kind = "coordinated" if edges else "unlinkable" if epic_branches else "uncoordinated"
    return {"coordination": kind, "edges": edges, "epic_branches": [] if edges else epic_branches}


def epic_level_branches(items: Sequence[str]) -> list[str]:
    """`repo:name` of each item that is an epic's integration branch, sorted.

    The one classifier the collector and the CLI share. A branch item
    (`branch:<repo>:<name>`) is epic-level when its name maps to an epic and to no
    ticket (`orch/<epic>-slug`): it belongs to the epic as a whole, so no blocking
    edge can link it to a ticket. That is decided by the branch's own name, never by
    whether the board happens to list the epic.
    """
    found = []
    for item in items:
        if not item.startswith("branch:"):
            continue
        label = item[len("branch:"):]
        repo, _, name = label.partition(":")
        epic, ticket = branch_reader.named_for(name, repo)
        if epic and not ticket:
            found.append(label)
    return sorted(found)


def _title(epic: Mapping[str, Any]) -> str:
    title = str(epic.get("title") or epic["key"])
    return title[len("Epic:"):].strip() if title.lower().startswith("epic:") else title


def _home(key: str, claims: Mapping[str, Any]) -> str | None:
    """The repository a `repo#n` key is in, when it has a model to place citations by."""
    repo = key.split("#")[0]
    return repo if repo in claims else None


def _source_root(repo: Mapping[str, Any], claims: Sequence[tuple[str, str]]) -> str:
    """Where a repository's modules are named from, as the collector read it; else as its claims say."""
    if isinstance(repo.get("source_root"), str):
        return repo["source_root"]
    return "src/" if any(path.startswith("src/") for path, _ in claims) else ""


def _modules(cited: str, root: str) -> list[str]:
    """The files a dotted module name can mean in a repository whose modules are named from `root`, longest first."""
    parts = cited.split(".")
    paths = []
    while parts:
        base = root + "/".join(parts)
        paths += [f"{base}.py", f"{base}/__init__.py"]
        parts.pop()
    return paths


def _branch_owner(
    b: Mapping[str, Any], repo: str, names: Sequence[str], epics: Mapping[str, Any], every_epic: Mapping[str, Any],
    ticket_epic: Mapping[str, str], ticket_state: Mapping[str, str], owners: dict[str, dict[str, Any]],
) -> tuple[str, str, str, str | None]:
    """`(owner, item, state, why the owner is unknown)` of a branch, adding an owner that is not a live epic of the board.

    An epic's lanes live in each repository whose files it changes, so the
    numbers a lane's name gives (`orch/<epic>/<ticket>`) may be another listed
    repository's. They are that repository's whose epic `#<epic>` holds the
    ticket `#<ticket>` on the board. Else they are the repository's whose files
    the branch changes, which is the branch's own, never another found by
    `system.yaml`'s order; a branch that changes no file has no such repository,
    so its owner is unknown, and it is its own owner, saying so.
    """
    epic, ticket = b.get("epic"), b.get("ticket")
    unknown = None
    if epic:
        number = epic.split("#")[1]
        owned = None
        if ticket:
            child = ticket.split("#")[1]
            order = [repo, *[name for name in names if name != repo]]
            owned = next((name for name in order if ticket_epic.get(f"{name}#{child}") == f"{name}#{number}"), None)
            if owned:
                ticket = f"{owned}#{child}"
        if owned:
            epic = f"{owned}#{number}"
        elif not b.get("files"):
            unknown = f"it changes no file, so which repository's epic #{number} it is is not known"
            epic = ticket = None
        else:
            epic = f"{repo}#{number}"
    if not epic and ticket:
        epic = ticket_epic.get(ticket)
    owner = epic or ticket
    item = ticket or f"branch:{repo}:{b['name']}"
    if owner is None:
        owner = f"branch:{repo}:{b['name']}"
        owners[owner] = {"key": owner, "kind": "branch", "title": b["name"], "url": None,
                         "status": "Owner unknown" if unknown else "Unlinked branch", "workstream": None}
        return owner, item, "building", unknown
    if owner not in owners:
        known = every_epic.get(owner)
        status = known.get("status") or "Closed" if known else "Off board"
        owners[owner] = {"key": owner, "kind": "epic" if known else "issue", "title": _title(known) if known else owner,
                         "url": (known or {}).get("url"), "status": status, "workstream": (known or {}).get("workstream")}
    stale = (owner in every_epic and owner not in epics) or ticket_state.get(ticket or "") == "CLOSED"
    return owner, item, "stale" if stale else "building", unknown


# ---------------------------------------------------------------------------
# Reading the other collectors and git
# ---------------------------------------------------------------------------


def _read(data_dir: Path, source: str) -> tuple[dict[str, Any] | None, str]:
    try:
        document = json.loads((data_dir / f"{source}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"{source}.json was not written"
    except (OSError, ValueError) as error:
        return None, f"{source}.json cannot be read: {error}"
    if not isinstance(document, dict) or not document.get("available"):
        return None, f"{source} is unavailable: {(document or {}).get('error') if isinstance(document, dict) else 'not an object'}"
    return document, ""


def repo_of(git_dir: Path, names: Sequence[str]) -> str:
    """Which listed repository a git directory is a clone of, by its `origin` URL; an error when it is none."""
    done = subprocess.run(["git", "-C", str(git_dir), "remote", "get-url", "origin"], capture_output=True, text=True, check=False)
    url = done.stdout.strip().removesuffix(".git").rstrip("/")
    name = url.rsplit("/", 1)[-1] if done.returncode == 0 and url else ""
    if name in names:
        return name
    raise CollectError(
        f"{git_dir} is not a clone of a repository system.yaml lists: its origin is {url or 'not set'}")


def _main_of(git_dir: Path) -> str:
    """The `main` a checkout or a developer's clone measures its branches against: `origin/main`, else `main`, else `HEAD`."""
    return next((ref for ref in ("origin/main", "main") if staging.resolve_ref(git_dir, ref)[0]), "HEAD")


def read_branches(
    repositories: staging.Repositories, names: Sequence[str], *, local: Sequence[Path] = (),
    listed: Sequence[str] | None = None, days: int = branch_reader.WINDOW_DAYS, now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    """The pushed branches of each repository `names` gives, then those of each local git directory given.

    Each is read through its run's read handle, so the one fetch a refresh made
    (and its result) is the architecture's too, and both read the same `main`. A
    bare clone holds pushed branches as `refs/heads/*`; a checkout named instead
    (`--registry`) as `refs/remotes/origin/*`. A repository whose branches cannot
    be read is recorded with the error, and the others are still read. A local git
    directory must be a clone of a listed repository (`listed`, by default `names`).
    """
    sets = []
    for name in names:
        handle = repositories.get(name)
        if handle.clone:
            main, prefixes = "main", ("refs/heads/",)
        else:
            main = _main_of(handle.git_dir)
            prefixes = ("refs/remotes/origin/",)
        try:
            handle.require()
            found = branch_reader.collect(handle.git_dir, name, main_ref=main, prefixes=prefixes, days=days, now=now)
        except CollectError as error:
            found = {"repo": name, "git_dir": str(handle.git_dir), "main": main, "days": days, "branches": [],
                     "skipped": [], "error": str(error)}
        sets.append(found | {"fetch": handle.fetch})
    for git_dir in local:
        main = _main_of(git_dir)
        sets.append(branch_reader.collect(git_dir, repo_of(git_dir, listed if listed is not None else names), main_ref=main,
                                          prefixes=("refs/heads/", "refs/remotes/origin/"), days=days, now=now, local=True))
    return sets


def collect(
    data_dir: Path,
    repositories: staging.Repositories | None = None,
    *,
    local: Sequence[Path] = (),
    days: int = branch_reader.WINDOW_DAYS,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """The `work` source: the board and architecture files of `data_dir`, and the branches read now.

    The branches are those of every repository the architecture read (listed,
    not planned, and readable), through `repositories`, the run's read handles
    (by default each repository's clone).
    """
    data_dir = Path(data_dir)
    board, board_why = _read(data_dir, "board")
    architecture, architecture_why = _read(data_dir, "architecture")
    if board is None or architecture is None:
        problems = [why for doc, why in ((board, board_why), (architecture, architecture_why)) if doc is None]
        raise CollectError("; ".join(problems))
    repos = architecture.get("repos") or {}
    names = [name for name, r in repos.items() if isinstance(r, Mapping) and r.get("commit")]
    sets = read_branches(repositories or staging.Repositories(), names, local=local, listed=list(repos), days=days, now=now)
    return compute(board, architecture, sets)
