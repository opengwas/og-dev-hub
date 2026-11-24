"""A ticket's planned change to the architecture: read it, and judge it once the ticket closes (#422, epic #416).

A ticket body may hold one fenced block whose info string is `architecture`,
holding YAML; the format is documented in `docs/spec/project-site.md`
(`### Planned changes`). `parse` reads it into the plan the board file carries,
`check_components` re-judges its component ids against the model once that is
known, and `evaluate` (from the `work` collector) checks a closed ticket's items
against what the architecture collector read.

A block that cannot be used is never dropped: it becomes `{"invalid": reason}`
and the page shows it. A ticket without a block has no plan at all.
"""

from __future__ import annotations

import re
from typing import Any, Collection, Mapping

import yaml

KEYS = ("adds", "moves", "drops", "absorbs")
ADD_KEYS = {"paths", "component", "name", "container", "layer"}
MOVE_KEYS = {"paths", "to"}
DROP = re.compile(r"\s*([a-z][a-z0-9_]*)\s*->\s*([a-z][a-z0-9_]*)\s*")
_FENCE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*(?P<info>[^`]*?)\s*$")


class Invalid(ValueError):
    """The block cannot be used; the message is the reason the page shows."""


def blocks(body: str | None) -> list[str]:
    """The text of every `architecture` fenced block of `body`; anything outside a fence is ignored."""
    found: list[str] = []
    current: list[str] | None = None
    opening = ""
    for line in (body or "").splitlines():
        fence = _FENCE.match(line)
        if opening:
            if fence and not fence.group("info") and fence.group("fence")[0] == opening[0] and len(fence.group("fence")) >= len(opening):
                if current is not None:
                    found.append("\n".join(current))
                opening, current = "", None
            elif current is not None:
                current.append(line)
            continue
        if fence:
            opening = fence.group("fence")
            current = [] if fence.group("info") == "architecture" else None
    if opening and current is not None:
        raise Invalid("the `architecture` block is never closed")
    return found


def parse(
    body: str | None, known: Collection[str] | None = None, layered: Mapping[str, Collection[str]] | None = None,
) -> dict[str, Any] | None:
    """The plan in `body`: `None` without a block, `{"invalid": reason}` when unusable, else the plan.

    `known` is the ids of the components that exist; without it a component's
    existence is not judged (`check_components` does that later). `layered` maps
    each repository whose model declares layers to its code roots.
    """
    try:
        found = blocks(body)
        if not found:
            return None
        if len(found) > 1:
            raise Invalid("more than one `architecture` block")
        plan = _read(found[0])
        return plan if known is None else _checked(plan, known, layered or {})
    except Invalid as error:
        return {"invalid": str(error)}
    except Exception as error:  # whatever else a strange block does, it stays that ticket's problem
        return {"invalid": f"the block could not be read: {type(error).__name__}: {error}"}


def check_components(
    plan: Mapping[str, Any], known: Collection[str], layered: Mapping[str, Collection[str]] | None = None,
) -> dict[str, Any]:
    """`plan`, or `{"invalid": reason}` when it names a component that is neither in `known` nor declared in `adds`."""
    if "invalid" in plan:
        return dict(plan)
    try:
        return _checked(dict(plan), known, layered or {})
    except Invalid as error:
        return {"invalid": str(error)}


def _read(text: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(text)
    except Exception as error:  # YAML errors, and the ValueError of a date that cannot exist
        first = (str(error).splitlines() or [type(error).__name__])[0]
        raise Invalid(f"the block is not valid YAML: {first}") from error
    if document is None:
        raise Invalid("the block is empty")
    if not isinstance(document, dict):
        raise Invalid("the block must be a mapping of `adds`, `moves`, `drops` and `absorbs`")
    for key in sorted(document, key=str):
        if key not in KEYS:
            raise Invalid(f"unknown key `{key}`")
    if not document:
        raise Invalid("the block has none of `adds`, `moves`, `drops` or `absorbs`")
    for key in KEYS:
        if key in document and not isinstance(document[key], list):
            raise Invalid(f"`{key}` must be a list")
    return {
        "adds": [_add(item) for item in document.get("adds", [])],
        "moves": [_move(item) for item in document.get("moves", [])],
        "drops": [_drop(item) for item in document.get("drops", [])],
        "absorbs": [_text(item) for item in document.get("absorbs", [])],
    }


ID_FORM = re.compile(r"[a-z][a-z0-9_]*")


def _id(value: Any, missing: str) -> str:
    """A component id: text in the model's form, so it can never be markup."""
    if not isinstance(value, str) or not value:
        raise Invalid(missing)
    if not ID_FORM.fullmatch(value):
        raise Invalid("component id must be lower-case letters, digits and `_`, starting with a letter")
    return value


def _item(item: Any, *, what: str, label: str, target: str, allowed: set[str]) -> dict[str, Any]:
    """An `adds` or `moves` item: one validator, so the two cannot refuse differently."""
    if not isinstance(item, dict):
        raise Invalid(f"{what} must be a mapping with `paths` and `{target}`")
    for key in sorted(item, key=str):
        if key not in allowed:
            raise Invalid(f"unknown key `{key}` in {what}")
    paths = item.get("paths")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
        raise Invalid(f"{what} needs a non-empty `paths` list")
    out: dict[str, Any] = {"paths": list(paths), target: _id(item.get(target), f"{what} needs {label}")}
    for key in ("name", "container"):
        if key in item:
            if not isinstance(item[key], str) or not item[key]:
                raise Invalid(f"`{key}` of {what} must be text")
            out[key] = item[key]
    if "layer" in item:
        if not isinstance(item["layer"], int) or isinstance(item["layer"], bool):
            raise Invalid(f"`layer` of {what} must be a whole number")
        out["layer"] = item["layer"]
    return out


def _add(item: Any) -> dict[str, Any]:
    return _item(item, what="an add", label="a `component`", target="component", allowed=ADD_KEYS)


def _move(item: Any) -> dict[str, Any]:
    return _item(item, what="a move", label="a `to` component", target="to", allowed=MOVE_KEYS)


def _drop(item: Any) -> dict[str, str]:
    match = DROP.fullmatch(item) if isinstance(item, str) else None
    if not match:
        raise Invalid(f"drop `{item}` is not `from -> to`")
    return {"from": match.group(1), "to": match.group(2)}


def _text(item: Any) -> str:
    if not isinstance(item, str):
        raise Invalid("an `absorbs` entry must be text")
    return item


def _checked(plan: dict[str, Any], known: Collection[str], layered: Mapping[str, Collection[str]]) -> dict[str, Any]:
    """`plan` when every component it names exists or is declared, and a new one in a layered repository has a layer."""
    declared = {a["component"] for a in plan["adds"]}
    for add in plan["adds"]:
        if add["component"] in known:
            continue
        if not add.get("name"):
            raise Invalid(f"component `{add['component']}` is new, so its add needs a `name`")
        repo = next((r for r, roots in layered.items() for p in add["paths"] if p.split("/", 1)[0] in roots), None)
        if repo and not ("container" in add and "layer" in add):
            raise Invalid(f"component `{add['component']}` is a new component of {repo}, whose model declares layers, "
                          "so its add needs a `container` and a `layer`")
    mentioned = [m["to"] for m in plan["moves"]] + [d[k] for d in plan["drops"] for k in ("from", "to")]
    for cid in mentioned:
        if cid not in known and cid not in declared:
            raise Invalid(f"component `{cid}` is neither an existing component nor declared in `adds`")
    return plan


# ---------------------------------------------------------------------------
# Judging a plan against what the architecture collector read
# ---------------------------------------------------------------------------


def listed(board: Mapping[str, Any], architecture: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every ticket's plan for the `work` source: the plan, the components it involves, and, once closed, its checks.

    A closed ticket's items are `held` true or false, or `None` (unknown) when
    the repository a path or component is in has no model at the ref read, or no
    model covers it at all: absence of a model is not an unmet item. An open
    ticket's plan is carried and nothing is checked, and so is an invalid one.
    `absorbs` is carried and never checked.

    Which repository a path is in (og-dev-hub#9) is the one repository whose
    claims cover it, else the one whose code roots do; when two do, or two code
    roots do and no claim settles it, it is not known, never the first listed.

    A component id is judged against every component of the repositories with a
    model. One in none of them makes the plan invalid, unless the plan touches a
    repository without a model (the ticket's own, the one a path in `adds` or
    `moves` is in, or, for a path no model covers, any listed one without a
    model): then its items naming that id are unknown, naming it.
    """
    from project_site.collect import architecture_model as rules

    components = [c for c in architecture.get("components") or [] if isinstance(c, Mapping)]
    by_id = {c["id"]: c for c in components}
    repos = {name: r for name, r in (architecture.get("repos") or {}).items() if isinstance(r, Mapping)}
    claims = rules.claims_by_repository(components, repos)
    names = list(claims)
    roots = {repo: rules.code_roots(claims[repo]) for repo in names}
    layers = (architecture.get("model") or {}).get("layers")
    layered = {repo: roots[repo] for repo in (layers if isinstance(layers, Mapping) else {}) if repo in roots}
    # A repository read with no model: nothing in it can be judged, so what is unplaced may be its.
    unmodelled = [name for name, r in repos.items() if not r.get("planned") and not r.get("model")]
    # A repository whose components are not known at all: read without a model, or planned.
    without_model = {name for name, r in repos.items() if not r.get("model")}
    # Named, never with a commit: a private repository's commit is not the public site's (og-dev-hub#9).
    missing = (f"{', '.join(unmodelled)} {'has' if len(unmodelled) == 1 else 'have'} no model at the ref read"
               if unmodelled else "")
    files = architecture.get("files")
    edge_list = architecture.get("edges")
    edges = None if not isinstance(edge_list, list) else {
        (e["from"], e["to"]): e["imports"] for e in edge_list if isinstance(e, Mapping)}

    def repo_of(path: str) -> tuple[str | None, str, list[str]]:
        """`(repository, "", [])` a path is in, seen against every listed repository.

        `(None, why, [])` when two repositories could hold it; `(None, "", candidates)`
        when no model's claims or code roots cover it, and `candidates` are the listed
        repositories without a model, any of which could.
        """
        owned = [r for r in names if rules.owner(claims[r], path)]
        if len(owned) == 1:
            return owned[0], "", []
        rooted = [r for r in names if rules.is_code(path, roots[r])]
        if len(owned) > 1:
            return None, f"both {' and '.join(owned)} claim it, so which repository it is in is not known", []
        if len(rooted) > 1:
            return None, (f"both {' and '.join(rooted)} count it as code and neither claims it, "
                          "so which repository it is in is not known"), []
        if rooted:
            return rooted[0], "", []
        return None, "", sorted(without_model)

    def exists(path: str, repo: str | None, ambiguous: str = "") -> tuple[bool | None, str]:
        """Whether `path` is a tracked file: only code files are listed, and only where the tree was read."""
        if not isinstance(files, Mapping):
            return None, "this architecture collection lists no tracked files"
        if ambiguous:
            return None, ambiguous
        if repo is None:
            # Under a model's code roots it is a non-code path; elsewhere it may be a repository's without one.
            if unmodelled and not any(path.split("/", 1)[0] in roots[r] for r in names):
                return None, f"no model read covers it, so whether it exists is not known: {missing}"
            return None, "only code files are listed, so a non-code path's existence is not known"
        listing = files.get(repo)
        if listing is None:
            return None, f"the {repo} tree was not read"
        if path in listing:
            return True, ""
        read = repos.get(repo) or {}
        return False, f"no such file at {read.get('ref')} ({str(read.get('commit'))[:12]})"

    def unknown(cid: str, touched: list[str]) -> str:
        return (f"`{cid}` is in no model read, and the plan touches {', '.join(touched)}, which "
                f"{'has' if len(touched) == 1 else 'have'} no model at the ref read")

    def claimed(path: str, target: str, kind: str, declared: Collection[str], touched: list[str]) -> dict[str, Any]:
        repo, ambiguous, _ = repo_of(path)
        present, why = exists(path, repo, ambiguous)
        found = rules.owner(claims[repo], path) if repo else None
        if target not in by_id and target not in declared and touched:
            present, why = None, unknown(target, touched)
        if present is False:
            held = False
        elif found and found != target:
            held, why = False, f"claimed by `{found}`, not `{target}`"
        elif present is None:
            held = None
        elif found == target:
            held, why = True, f"claimed by `{target}`"
        else:
            held, why = False, "no component claims it"
        return {"kind": kind, "path": path, "component": target, "held": held, "why": why,
                "repo": repo or (by_id.get(target) or {}).get("repo")}

    def dropped(a: str, b: str, touched: list[str]) -> dict[str, Any]:
        repo = (by_id.get(a) or by_id.get(b) or {}).get("repo")
        if edges is None:
            return {"kind": "drops", "from": a, "to": b, "imports": None, "held": None, "repo": repo,
                    "why": "this architecture collection lists no import edges"}
        if touched and not all(x in by_id for x in (a, b)):
            return {"kind": "drops", "from": a, "to": b, "imports": None, "held": None, "repo": repo,
                    "why": unknown(next(x for x in (a, b) if x not in by_id), touched)}
        n = edges.get((a, b), 0)
        why = f"no import from `{a}` into `{b}`" if not n else f"{n} import{'s' if n != 1 else ''} from `{a}` into `{b}` remain{'s' if n == 1 else ''}"
        return {"kind": "drops", "from": a, "to": b, "imports": n, "held": not n, "why": why, "repo": repo}

    found: list[dict[str, Any]] = []
    for epic in board.get("epics") or []:
        for ticket in epic.get("children") or []:
            plan = ticket.get("plan")
            if plan is None:
                continue
            # A component of a repository with no model is unknown, never absent: an id no model
            # read has is invalid unless the plan touches such a repository (og-dev-hub#9).
            touched = _touched(plan, ticket["key"], without_model, repo_of)
            if not touched:
                plan = check_components(plan, set(by_id), layered)
            closed = ticket.get("state") == "CLOSED"
            checks: list[dict[str, Any]] = []
            involved: list[dict[str, Any]] = []
            if "invalid" not in plan:
                declared = {a["component"]: a for a in plan["adds"]}
                ids = sorted({*declared, *(m["to"] for m in plan["moves"]), *(x for d in plan["drops"] for x in (d["from"], d["to"]))})
                involved = [
                    {"id": i, "name": by_id[i]["name"], "repo": by_id[i]["repo"], "new": False} if i in by_id
                    else {"id": i, "name": declared[i].get("name") or i if i in declared else i, "repo": None, "new": i in declared}
                    for i in ids
                ]
                if closed:
                    checks = (
                        [claimed(p, a["component"], "adds", declared, touched) for a in plan["adds"] for p in a["paths"]]
                        + [claimed(p, m["to"], "moves", declared, touched) for m in plan["moves"] for p in m["paths"]]
                        + [dropped(d["from"], d["to"], touched) for d in plan["drops"]]
                    )
            found.append({
                "ticket": ticket["key"], "epic": epic["key"], "title": ticket.get("title"), "url": ticket.get("url"),
                "state": "closed" if closed else "open", "plan": plan, "components": involved, "checks": checks,
            })
    return sorted(found, key=lambda p: (p["epic"], p["ticket"]))


def _touched(plan: Mapping[str, Any], ticket: str, without_model: Collection[str], repo_of: Any) -> list[str]:
    """The repositories without a model a plan touches: its ticket's own, any a path in `adds` or `moves` is in,
    and, for a path no model's claims or code roots cover, every listed repository without a model."""
    found = {str(ticket).split("#")[0]}
    if "invalid" not in plan:
        for item in [*plan.get("adds", []), *plan.get("moves", [])]:
            for path in item.get("paths") or []:
                repo, _, candidates = repo_of(path)
                found |= {repo, *candidates}
    return sorted(r for r in found if r in without_model)
