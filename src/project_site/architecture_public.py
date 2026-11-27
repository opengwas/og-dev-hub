"""What the public site may draw of the collected files: one view, built from an allow-list (og-dev-hub#9, og-dev-hub#15).

What is collected from a `private` repository (or one `system.yaml` does not
list) is hidden: `pixi run architecture` collects it whole, because orchestration
needs it, and the site's own collection never reads it, but whichever was
collected, the public site draws such a repository as its container only: no
component names, paths, files, stages, ADRs or commits. Text authored in a public
repository passes through as written, even where it names a private repository:
it is already published by its own repository.

`public_view` is the one function that makes that view; every view of the site
is written only from what it returns. It never starts from a collected
document: it builds `architecture.json` from the fields a view draws, named
here, so a field a collector adds later reaches no view until it is named. A
host path in a reason a collector wrote is cut to its last name (`reason`).

Which repositories are private comes from `system.yaml`: through the
`architecture.json` the same run collected from it, else from the file in this
checkout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from project_site.shapes import mapping

Document = Mapping[str, Any]

ENVELOPE = ("source", "available", "collected_at", "error")

# architecture.json
REPO_KEYS = ("name", "visibility", "status", "planned", "ref", "commit", "committed", "model", "note", "error", "glossary")
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


# Match a whole file URL, an absolute path starting a word, or a `/data/` path after e.g. a colon or inside an HTTP URL.
# A relative `resources/data/` continues a word; `…/` is a cut already made.
HOST_PATH = re.compile(
    r"(?P<file_url>(?i:file://)[^\s'\"`,;()]*)"
    r"|(?<![\w.:/~…-])/[^\s'\"`,;()]+|(?<![\w.~…-])/data/[^\s'\"`,;()]*"
)


def reason(text: Any) -> Any:
    """A reason a collector wrote, as the public site may show it: each host path cut to its last name (`…/x.git`).

    The site is published, and where the build's clones live is the build host's
    business; which repository could not be read, and why, stays.
    """
    if not isinstance(text, str):
        return text

    def cut(match: re.Match[str]) -> str:
        path = match.group(0)
        if match.group("file_url"):
            # Discard the authority, query and fragment as well as the machine's directories.
            path = re.split(r"[?#]", path, maxsplit=1)[0][len("file://"):].partition("/")[2]
        name = path.rstrip("/").rsplit("/", 1)[-1]
        return f"…/{name}" if name else "…"

    return HOST_PATH.sub(cut, text)


def _pick(source: Any, keys: Iterable[str]) -> dict[str, Any]:
    """The named fields of `source`, and nothing else; a source that is not a mapping gives none."""
    return {k: source[k] for k in keys if isinstance(source, Mapping) and k in source}


def _maps(values: Any) -> list[Mapping[str, Any]]:
    return [v for v in values if isinstance(v, Mapping)] if isinstance(values, list) else []


def _texts(values: Any) -> list[str]:
    return [str(v) for v in values] if isinstance(values, list) else []


@dataclass(frozen=True)
class Parts:
    """The parts of a public `architecture.json` the site's views and diagrams read, each in `system.yaml`'s order."""

    model: Mapping[str, Any]
    repos: dict[str, Mapping[str, Any]]
    components: list[Mapping[str, Any]]
    edges: list[Mapping[str, Any]]
    adrs: list[Mapping[str, Any]]


def parts(doc: Document) -> Parts:
    """The one reader of a public `architecture.json`'s parts: what is not a mapping is left out, never guessed."""
    repos = mapping(doc.get("repos"))
    model = mapping(doc.get("model"))
    return Parts(model=model, repos={str(n): r for n, r in repos.items() if isinstance(r, Mapping)},
                 components=_maps(doc.get("components")), edges=_maps(doc.get("edges")), adrs=_maps(doc.get("adrs")))


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
    from project_site.collect import architecture_model

    try:
        system = architecture_model.read_system()
    except ValueError:
        return {}
    return {str(entry["name"]): entry.get("visibility") for entry in system.get("repos") or []}


def public_view(documents: Mapping[str, Document | None]) -> dict[str, Document | None]:
    """`documents` as the public site may draw them: `architecture` rebuilt from the allow-list.

    Another source is passed through as it is. The view is idempotent.
    """
    private = visibility(listed_visibility(documents))
    view: dict[str, Document | None] = dict(documents)
    architecture = documents.get("architecture")
    if isinstance(architecture, Mapping):
        hidden = {str(c.get("id")) for c in _maps(architecture.get("components")) if private(c.get("repo"))}
        built = _architecture(architecture, private, hidden) if architecture.get("available") else _pick(architecture, ENVELOPE)
        view["architecture"] = {**built, "error": reason(architecture.get("error"))}
    return view


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
            refresh = _pick(repo.get("refresh"), ("ok", "error"))
            repos[name] = _pick(repo, REPO_KEYS) | {
                "error": reason(repo.get("error")), "note": reason(repo.get("note")),
                "refresh": refresh | {"error": reason(refresh.get("error"))} if refresh else None}
    out["repos"] = repos
    model = mapping(doc.get("model"))
    layers = mapping(model.get("layers"))
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
    gaps = mapping(doc.get("gaps"))
    out["gaps"] = {
        name: _pick(gap, GAP_KEYS)
        | {"unreadable": reason(gap.get("unreadable")), "no_model": reason(gap.get("no_model")),
           "stale": [_pick(st, ("path", "component")) for st in _maps(gap.get("stale"))] if gap.get("stale") is not None else None,
           "containers": [_pick(g, ("component", "container")) for g in _maps(gap.get("containers"))]}
        for name, gap in gaps.items() if isinstance(gap, Mapping) and not private(name)
    }
    baseline = doc.get("baseline")
    out["baseline"] = (_pick(baseline, BASELINE_KEYS) | {"note": reason(baseline.get("note"))}
                       if isinstance(baseline, Mapping) and not private(baseline.get("from")) else None)
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
