"""What the public site may draw of the collected files: one view, built from an allow-list (og-dev-hub#9).

What the site collects from a `private` repository (or one `system.yaml` does
not list) is hidden: it is collected like any other, because orchestration
needs its branches, but the public site draws it as its container only: no
component names, paths, files, stages, ADRs, commits or work items, and no epic,
ticket or milestone of the board, in the pages or in the component panel's
embedded JSON. Text authored in a public repository or on a public item passes
through as written, even where it names a private repository's issue: it is
already published by its own repository.

`public_view` is the one function that makes that view; every page renderer
reads only what it returns. It never starts from a collected document: it
builds each one from the fields a page or the panel draws, named here, so a
field a collector adds later reaches no page until it is named.

Which repositories are private comes from `system.yaml`: through the
`architecture.json` the same run collected from it, else through `work.json`'s
record of it, else from the file in this checkout.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from project_site import paths

Document = Mapping[str, Any]

ENVELOPE = ("source", "available", "collected_at", "error")

# architecture.json
REPO_KEYS = ("name", "visibility", "status", "planned", "ref", "commit", "committed", "model", "note", "error")
PRIVATE_REPO_KEYS = ("name", "visibility", "status", "planned")
COMPONENT_KEYS = ("id", "name", "repo", "container", "layer", "stages", "summary", "paths", "files", "lines", "tracked")
ENTITY_KEYS = ("id", "name", "summary")
CONTAINER_KEYS = ("id", "name", "repo", "tech", "summary")
STAGE_KEYS = ("id", "name", "summary", "repo")
LAYER_KEYS = ("layer", "name")
GAP_KEYS = ("unreadable", "no_model", "unclaimed", "system_sections")
BASELINE_KEYS = ("path", "from", "entries", "measured", "note")
EDGE_KEYS = ("from", "to", "imports", "scope", "repo", "from_repo", "to_repo", "upward")
ADR_KEYS = ("repo", "number", "title", "status", "url")
SUMMARY_KEYS = ("edges", "upward_edges", "upward_imports", "registry_to_engine_edges", "registry_to_engine_imports",
                "adrs_total", "adrs_placed")
# work.json
OWNER_KEYS = ("key", "kind", "title", "url", "status", "workstream")
SIGNAL_KEYS = ("component", "owner", "item", "via", "state", "path")
SOURCE_KEYS = ("repo", "days", "error")
BRANCH_KEYS = ("name", "repo", "ahead", "committed", "item", "owner", "owner_unknown")
CHECK_KEYS = ("kind", "path", "component", "held", "why", "repo", "from", "to", "imports")
PLAN_KEYS = ("ticket", "epic", "title", "url", "state")
# board.json
ISSUE_KEYS = ("key", "title", "url", "state", "status", "workstream", "next", "priority")
EPIC_KEYS = (*ISSUE_KEYS, "purpose")
CHILD_KEYS = ("key", "title", "url", "state")


def _pick(source: Any, keys: Iterable[str]) -> dict[str, Any]:
    """The named fields of `source`, and nothing else; a source that is not a mapping gives none."""
    return {k: source[k] for k in keys if isinstance(source, Mapping) and k in source}


def _maps(values: Any) -> list[Mapping[str, Any]]:
    return [v for v in values if isinstance(v, Mapping)] if isinstance(values, list) else []


def _texts(values: Any) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


def visibility(listed: Mapping[str, Any]) -> Callable[[Any], bool]:
    """The one visibility predicate: whether a repository is private, given `listed` (each name `system.yaml` lists, to its `visibility`).

    A repository `system.yaml` marks private is private, and so is one it does
    not list, because a fallback must be safe.
    """
    def private(repo: Any) -> bool:
        return str(repo) not in listed or listed[str(repo)] == "private"
    return private


def listed_visibility(documents: Mapping[str, Document | None]) -> dict[str, Any]:
    """Each repository `system.yaml` lists, to its `visibility`, as the collected files recorded it."""
    architecture = documents.get("architecture")
    if isinstance(architecture, Mapping) and isinstance(architecture.get("repos"), Mapping) and architecture["repos"]:
        return {str(n): r.get("visibility") for n, r in architecture["repos"].items() if isinstance(r, Mapping)}
    work = documents.get("work")
    recorded = ((work or {}).get("inputs") or {}).get("architecture") if isinstance(work, Mapping) else None
    if isinstance(recorded, Mapping) and isinstance(recorded.get("repos"), Mapping) and recorded["repos"]:
        return {str(n): r.get("visibility") for n, r in recorded["repos"].items() if isinstance(r, Mapping)}
    from project_site.collect import architecture_model

    try:
        system = architecture_model.load_system((paths.repo_root() / "system.yaml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(entry["name"]): entry.get("visibility") for entry in system.get("repos") or []}


def public_view(documents: Mapping[str, Document | None]) -> dict[str, Document | None]:
    """`documents` as the public site may draw them: `architecture`, `work`, `board` and `records` rebuilt from the allow-list.

    The other sources are passed through as they are. The view is idempotent.
    """
    private = visibility(listed_visibility(documents))

    view: dict[str, Document | None] = dict(documents)
    architecture = documents.get("architecture")
    hidden: set[str] = set()
    private_files: set[str] = set()
    if isinstance(architecture, Mapping):
        hidden = {str(c.get("id")) for c in _maps(architecture.get("components")) if private(c.get("repo"))}
        for name, files in (architecture.get("files") or {}).items() if isinstance(architecture.get("files"), Mapping) else ():
            if private(name):
                private_files.update(_texts(files))
    builders: dict[str, Callable[..., dict[str, Any]]] = {
        "architecture": lambda doc: _architecture(doc, private, hidden),
        "work": lambda doc: _work(doc, private, hidden, private_files),
        "board": lambda doc: _board(doc, private),
        "records": lambda doc: _records(doc, private),
    }
    for source, build in builders.items():
        document = documents.get(source)
        if not isinstance(document, Mapping):
            continue
        view[source] = build(document) if document.get("available") else _pick(document, ENVELOPE)
    return view


def _repo_of_key(key: Any) -> str | None:
    """The repository of a work item or owner (`repo#n`, `branch:repo:name`), or `None` for anything else."""
    text = str(key or "")
    if text.startswith("branch:"):
        return text[len("branch:"):].split(":", 1)[0]
    return text.split("#", 1)[0] if "#" in text else None


def _hides(private: Callable[[Any], bool]) -> Callable[..., bool]:
    def hide(*keys: Any) -> bool:
        return any((repo := _repo_of_key(k)) is not None and private(repo) for k in keys)
    return hide


# ---------------------------------------------------------------------------
# architecture.json
# ---------------------------------------------------------------------------


def _architecture(doc: Document, private: Callable[[Any], bool], hidden: set[str]) -> dict[str, Any]:
    out = _pick(doc, ENVELOPE)
    repos: dict[str, Any] = {}
    for name, repo in (doc.get("repos") or {}).items() if isinstance(doc.get("repos"), Mapping) else ():
        if private(name):
            repos[name] = _pick(repo, PRIVATE_REPO_KEYS) | {"model": None, "private": True}
        else:
            repos[name] = _pick(repo, REPO_KEYS) | {"refresh": _pick(repo.get("refresh"), ("ok", "error")) or None}
    out["repos"] = repos
    model = doc.get("model") if isinstance(doc.get("model"), Mapping) else {}
    layers = model.get("layers") if isinstance(model.get("layers"), Mapping) else {}
    out["model"] = {
        "system": _pick(model.get("system"), ("name", "summary")),
        "people": [_pick(p, ENTITY_KEYS) for p in _maps(model.get("people"))],
        "external": [_pick(x, ENTITY_KEYS) for x in _maps(model.get("external"))],
        "containers": [_pick(c, CONTAINER_KEYS) for c in _maps(model.get("containers"))],
        "container_relations": [[str(a), str(b), str(text)] for a, b, text in
                                (r for r in model.get("container_relations") or [] if isinstance(r, list) and len(r) == 3)],
        "stages": [_pick(st, STAGE_KEYS) for st in _maps(model.get("stages")) if not private(st.get("repo"))],
        "layers": {name: [_pick(layer, LAYER_KEYS) for layer in _maps(value)]
                   for name, value in layers.items() if not private(name)},
    }
    out["components"] = [
        _pick(c, COMPONENT_KEYS) | {"stages": _texts(c.get("stages")), "paths": _texts(c.get("paths"))}
        for c in _maps(doc.get("components")) if not private(c.get("repo"))
    ]
    gaps = doc.get("gaps") if isinstance(doc.get("gaps"), Mapping) else {}
    out["gaps"] = {
        name: _pick(gap, GAP_KEYS)
        | {"stale": [_pick(st, ("path", "component")) for st in _maps(gap.get("stale"))] if gap.get("stale") is not None else None,
           "containers": [_pick(g, ("component", "container")) for g in _maps(gap.get("containers"))]}
        for name, gap in gaps.items() if isinstance(gap, Mapping) and not private(name)
    }
    baseline = doc.get("baseline")
    out["baseline"] = _pick(baseline, BASELINE_KEYS) if isinstance(baseline, Mapping) and not private(baseline.get("from")) else None
    edges = [_pick(e, EDGE_KEYS) for e in _maps(doc.get("edges")) if e.get("from") not in hidden and e.get("to") not in hidden]
    out["edges"] = edges
    adrs = [
        _pick(a, ADR_KEYS)
        | {"components": {str(cid): via for cid, via in (a.get("components") or {}).items() if cid not in hidden},
           "cites": [_pick(c, ("repo", "number")) for c in _maps(a.get("cites"))]}
        for a in _maps(doc.get("adrs")) if not private(a.get("repo"))
    ]
    out["adrs"] = adrs
    summary = _pick(doc.get("summary"), SUMMARY_KEYS)
    summary |= {"edges": len(edges), "adrs_total": len(adrs), "adrs_placed": sum(1 for a in adrs if a["components"])}
    if summary.get("upward_edges") is not None:
        upward = [e for e in edges if e.get("upward")]
        summary |= {"upward_edges": len(upward), "upward_imports": sum(e.get("imports") or 0 for e in upward)}
    out["summary"] = summary
    return out


# ---------------------------------------------------------------------------
# work.json
# ---------------------------------------------------------------------------


def _plan(plan: Any) -> dict[str, Any]:
    """A ticket's plan as the page draws it: the four lists, or why it is invalid."""
    if not isinstance(plan, Mapping):
        return {}
    if "invalid" in plan:
        return {"invalid": str(plan["invalid"])}
    return {
        "adds": [_pick(a, ("component", "name", "container", "layer")) | {"paths": _texts(a.get("paths"))}
                 for a in _maps(plan.get("adds"))],
        "moves": [_pick(m, ("to",)) | {"paths": _texts(m.get("paths"))} for m in _maps(plan.get("moves"))],
        "drops": [_pick(d, ("from", "to")) for d in _maps(plan.get("drops"))],
        "absorbs": _texts(plan.get("absorbs")),
    }


def _work(doc: Document, private: Callable[[Any], bool], hidden: set[str], private_files: set[str]) -> dict[str, Any]:
    hide = _hides(private)
    out = _pick(doc, (*ENVELOPE, "schema_version"))
    inputs = doc.get("inputs") if isinstance(doc.get("inputs"), Mapping) else {}
    recorded = (inputs.get("architecture") or {}) if isinstance(inputs.get("architecture"), Mapping) else {}
    out["inputs"] = {
        "board": _pick(inputs.get("board"), ("collected_at",)),
        "architecture": _pick(recorded, ("collected_at",)) | {
            "repos": {name: _pick(r, ("ref", "commit", "visibility"))
                      for name, r in (recorded.get("repos") or {}).items() if not private(name)}},
    }
    signals = [
        _pick(s, SIGNAL_KEYS) | {"what": _texts(s.get("what"))}
        for s in _maps(doc.get("signals"))
        if s.get("component") not in hidden and not hide(s.get("owner"), s.get("item"))
    ]
    out["signals"] = signals
    with_signals = {s.get("owner") for s in signals}
    out["owners"] = [_pick(o, OWNER_KEYS) for o in _maps(doc.get("owners")) if o.get("key") in with_signals]
    out["components"] = [_pick(c, ("id", "name", "repo")) for c in _maps(doc.get("components"))
                         if c.get("id") not in hidden and not private(c.get("repo"))]
    meets = []
    for meet in _maps(doc.get("meets")):
        if meet.get("component") in hidden:
            continue
        owners = [str(o) for o in meet.get("owners") or [] if not hide(o)]
        items = {o: [str(i) for i in (meet.get("items") or {}).get(o, []) if not hide(i)] for o in owners}
        owners = [o for o in owners if items[o]]
        if len(owners) < 2:
            continue
        pairs = []
        for pair in _maps(meet.get("pairs")):
            if not all(o in owners for o in pair.get("owners") or []):
                continue
            pairs.append(_pick(pair, ("coordinated", "coordination")) | {
                "owners": [str(o) for o in pair.get("owners") or []],
                "edges": [_pick(e, ("waiting", "on")) for e in _maps(pair.get("edges")) if not hide(e.get("waiting"), e.get("on"))],
                "epic_branches": [str(b) for b in pair.get("epic_branches") or [] if not private(str(b).split(":", 1)[0])],
            })
        kinds = {p.get("coordination") for p in pairs}
        coordination = "uncoordinated" if "uncoordinated" in kinds else "unlinkable" if "unlinkable" in kinds else "coordinated"
        meets.append({"component": meet.get("component"), "owners": owners, "items": items, "pairs": pairs,
                      "coordination": coordination, "coordinated": coordination == "coordinated"})
    out["meets"] = meets
    out["unresolved"] = [
        _pick(r, ("owner", "item", "cited")) | {"candidates": _texts(r.get("candidates"))}
        for r in _maps(doc.get("unresolved"))
        if not hide(r.get("owner"), r.get("item")) and not set(_texts(r.get("candidates"))) & private_files
    ]
    out["not_found"] = [_pick(r, ("owner", "item", "cited", "component")) for r in _maps(doc.get("not_found"))
                        if r.get("component") not in hidden and not hide(r.get("owner"), r.get("item"))]
    if isinstance(doc.get("plans"), list):
        out["plans"] = [
            _pick(p, PLAN_KEYS) | {
                "plan": _plan(p.get("plan")),
                "components": [_pick(c, ("id", "name", "repo", "new")) for c in _maps(p.get("components"))],
                "checks": [_pick(c, CHECK_KEYS) for c in _maps(p.get("checks"))],
            }
            for p in _maps(doc["plans"])
            if not hide(p.get("ticket"), p.get("epic"))
            and not any(c.get("id") in hidden for c in _maps(p.get("components")))
            and not any(private(c.get("repo")) for c in _maps(p.get("checks")) if c.get("repo") is not None)
        ]
    branches = doc.get("branches") if isinstance(doc.get("branches"), Mapping) else {}
    listed = [
        _pick(b, BRANCH_KEYS) | {"files": _texts(b.get("files")), "components": _texts(b.get("components"))}
        for b in _maps(branches.get("list"))
        if not private(b.get("repo")) and not hide(b.get("owner"), b.get("item"))
    ]
    out["branches"] = {
        "sources": [_pick(s, SOURCE_KEYS) | {"fetch": _pick(s.get("fetch"), ("ok", "error")) or None}
                    for s in _maps(branches.get("sources")) if not private(s.get("repo"))],
        "list": listed,
    }
    out["unmeasured"] = {str(name): str(why) for name, why in (doc.get("unmeasured") or {}).items() if not private(name)}
    out["summary"] = {
        "owners": len(with_signals), "meets": len(meets),
        "coordinated": sum(1 for m in meets if m["coordinated"]),
        "uncoordinated": sum(1 for m in meets if m["coordination"] == "uncoordinated"),
        "unlinkable": sum(1 for m in meets if m["coordination"] == "unlinkable"),
        "branches": len(listed), "unresolved": len(out["unresolved"]), "not_found": len(out["not_found"]),
    }
    return out


# ---------------------------------------------------------------------------
# board.json and records.json
# ---------------------------------------------------------------------------


def _board(doc: Document, private: Callable[[Any], bool]) -> dict[str, Any]:
    """The board as the pages draw it; an epic, ticket or milestone of a private repository is only counted (`private`)."""
    hide = _hides(private)
    out = _pick(doc, (*ENVELOPE, "project"))
    counts = {"epics": 0, "active_epics": 0, "tickets": 0, "milestones": 0}
    epics = []
    for epic in _maps(doc.get("epics")):
        if hide(epic.get("key")) or _repo_of_key(epic.get("key")) is None:
            counts["epics"] += 1
            counts["active_epics"] += epic.get("status") == "Active"
            continue
        children = []
        hidden_children = 0
        for ticket in _maps(epic.get("children")):
            if hide(ticket.get("key")) or _repo_of_key(ticket.get("key")) is None:
                hidden_children += 1
                continue
            children.append(_pick(ticket, CHILD_KEYS) | {
                "blocked_by": [_pick(b, ("key", "state")) for b in _maps(ticket.get("blocked_by")) if not hide(b.get("key"))]})
        counts["tickets"] += hidden_children
        epics.append(_pick(epic, EPIC_KEYS) | {
            "sub_issues": _pick(epic.get("sub_issues"), ("total", "completed")),
            "children": children,
            "private_children": hidden_children,
        })
    out["epics"] = epics
    milestones = []
    for item in _maps(doc.get("milestones")):
        if hide(item.get("key")) or _repo_of_key(item.get("key")) is None:
            counts["milestones"] += 1
            continue
        milestones.append(_pick(item, ISSUE_KEYS) | {
            "sub_issues": _pick(item.get("sub_issues"), ("total", "completed")),
            "lines": [_pick(line, ("checked", "text")) | {"refs": [r for r in _texts(line.get("refs")) if not hide(r)]}
                      for line in _maps(item.get("lines"))],
        })
    out["milestones"] = milestones
    out["items"] = [_pick(item, ISSUE_KEYS) | {"sub_issues": _pick(item.get("sub_issues"), ("total", "completed"))}
                    for item in _maps(doc.get("items")) if not hide(item.get("key")) and _repo_of_key(item.get("key"))]
    out["private"] = counts
    return out


def _records(doc: Document, private: Callable[[Any], bool]) -> dict[str, Any]:
    """The epic records, less any of a private repository's epic, which has no page.

    A record is committed in a public repository, so what it says is not held
    back; only which epics get a page follows the board's rule.
    """
    out = dict(doc)
    out["epics"] = [r for r in _maps(doc.get("epics")) if not private(r.get("repo"))]
    return out
