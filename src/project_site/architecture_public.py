"""What the public site may draw of `architecture.json` and `work.json` (og-dev-hub#9).

A `private` repository is collected like any other, because orchestration needs
its branches, but the public site draws it as its container only: no component
names, paths, files, ADR titles, commits or work items, in the pages or in the
component panel's embedded JSON. `public_view` is the one function that makes
that view; every architecture renderer reads only what it returns
(`architecture_pages`, and through it `architecture_panel`).

The container comes from `system.yaml`'s `containers`, which is public, so
nothing private is needed to draw it.
"""

from __future__ import annotations

from typing import Any, Mapping

Document = Mapping[str, Any]

# What a private repository keeps in `repos`: that it is listed, and how to draw its container.
PRIVATE_KEYS = ("name", "visibility", "status", "planned", "url")


def private_repositories(documents: Mapping[str, Document | None]) -> set[str]:
    """The names of the repositories `system.yaml` marks private, from either collected file."""
    names: set[str] = set()
    for document, repos in (
        (documents.get("architecture"), lambda d: d.get("repos")),
        (documents.get("work"), lambda d: ((d.get("inputs") or {}).get("architecture") or {}).get("repos")),
    ):
        if isinstance(document, Mapping):
            for name, repo in (repos(document) or {}).items():
                if isinstance(repo, Mapping) and repo.get("visibility") == "private":
                    names.add(str(name))
    return names


def public_view(documents: Mapping[str, Document | None]) -> dict[str, Document | None]:
    """`documents` with every private repository's detail removed from `architecture` and `work`.

    The view is idempotent, and the other sources are passed through as they are.
    """
    private = private_repositories(documents)
    view = dict(documents)
    if not private:
        return view
    architecture = documents.get("architecture")
    private_files: set[str] = set()
    hidden: set[str] = set()
    if isinstance(architecture, Mapping):
        hidden = {str(c.get("id")) for c in architecture.get("components") or []
                  if isinstance(c, Mapping) and c.get("repo") in private}
        for name in private:
            private_files.update((architecture.get("files") or {}).get(name) or [])
        if architecture.get("available"):
            view["architecture"] = _architecture(architecture, private, hidden)
    work = documents.get("work")
    if isinstance(work, Mapping) and work.get("available"):
        view["work"] = _work(work, private, hidden, private_files)
    return view


def _of_private(key: Any, private: set[str]) -> bool:
    """Whether a work item or owner (`repo#n`, `branch:repo:name`) belongs to a private repository."""
    text = str(key or "")
    if text.startswith("branch:"):
        return text[len("branch:"):].split(":", 1)[0] in private
    return text.split("#", 1)[0] in private if "#" in text else False


def _architecture(doc: Document, private: set[str], hidden: set[str]) -> dict[str, Any]:
    out = dict(doc)
    out["repos"] = {
        name: ({k: repo.get(k) for k in PRIVATE_KEYS} | {"model": None, "private": True} if name in private else repo)
        for name, repo in (doc.get("repos") or {}).items()
    }
    out["components"] = [c for c in doc.get("components") or [] if isinstance(c, Mapping) and c.get("repo") not in private]
    for key in ("files", "gaps"):
        if isinstance(doc.get(key), Mapping):
            out[key] = {name: value for name, value in doc[key].items() if name not in private}
    edges = [e for e in doc.get("edges") or [] if isinstance(e, Mapping) and e.get("from") not in hidden and e.get("to") not in hidden]
    out["edges"] = edges
    if isinstance(doc.get("upward_imports"), list):
        out["upward_imports"] = [u for u in doc["upward_imports"] if u.get("from") not in hidden and u.get("to") not in hidden]
    adrs = []
    for adr in doc.get("adrs") or []:
        if not isinstance(adr, Mapping) or adr.get("repo") in private:
            continue
        adrs.append({**adr, "components": {cid: via for cid, via in (adr.get("components") or {}).items() if cid not in hidden}})
    out["adrs"] = adrs
    model = dict(doc.get("model") or {})
    if isinstance(model.get("layers"), Mapping):
        model["layers"] = {name: layers for name, layers in model["layers"].items() if name not in private}
    out["model"] = model
    baseline = doc.get("baseline")
    if isinstance(baseline, Mapping) and baseline.get("from") in private:
        out["baseline"] = None
    summary = dict(doc.get("summary") or {})
    summary |= {"edges": len(edges), "adrs_total": len(adrs), "adrs_placed": sum(1 for a in adrs if a["components"])}
    if summary.get("upward_edges") is not None:
        upward = [e for e in edges if e.get("upward")]
        summary |= {"upward_edges": len(upward), "upward_imports": sum(e.get("imports") or 0 for e in upward)}
    out["summary"] = summary
    return out


def _work(doc: Document, private: set[str], hidden: set[str], private_files: set[str]) -> dict[str, Any]:
    out = dict(doc)

    def hide(*keys: Any) -> bool:
        return any(_of_private(k, private) for k in keys)

    signals = [s for s in doc.get("signals") or [] if isinstance(s, Mapping)
               and s.get("component") not in hidden and not hide(s.get("owner"), s.get("item"))]
    out["signals"] = signals
    with_signals = {s["owner"] for s in signals}
    out["owners"] = [o for o in doc.get("owners") or [] if isinstance(o, Mapping) and o.get("key") in with_signals]
    out["components"] = [c for c in doc.get("components") or [] if isinstance(c, Mapping)
                         and c.get("id") not in hidden and c.get("repo") not in private]
    meets = []
    for meet in doc.get("meets") or []:
        if not isinstance(meet, Mapping) or meet.get("component") in hidden:
            continue
        owners = [o for o in meet.get("owners") or [] if not hide(o)]
        items = {o: [i for i in (meet.get("items") or {}).get(o, []) if not hide(i)] for o in owners}
        owners = [o for o in owners if items[o]]
        if len(owners) < 2:
            continue
        pairs = [p for p in meet.get("pairs") or [] if all(o in owners for o in p.get("owners") or [])]
        kinds = {p.get("coordination") for p in pairs}
        coordination = "uncoordinated" if "uncoordinated" in kinds else "unlinkable" if "unlinkable" in kinds else "coordinated"
        meets.append({**meet, "owners": owners, "items": items, "pairs": pairs,
                      "coordination": coordination, "coordinated": coordination == "coordinated"})
    out["meets"] = meets
    out["unresolved"] = [r for r in doc.get("unresolved") or [] if isinstance(r, Mapping)
                         and not hide(r.get("owner"), r.get("item"))
                         and not set(r.get("candidates") or []) & private_files]
    out["not_found"] = [r for r in doc.get("not_found") or [] if isinstance(r, Mapping)
                        and r.get("component") not in hidden and not hide(r.get("owner"), r.get("item"))]
    if isinstance(doc.get("plans"), list):
        out["plans"] = [p for p in doc["plans"] if isinstance(p, Mapping) and not hide(p.get("ticket"), p.get("epic"))
                        and not any(c.get("id") in hidden for c in p.get("components") or [])
                        and not any(c.get("repo") in private for c in p.get("checks") or [])]
    out["tickets"] = {k: v for k, v in (doc.get("tickets") or {}).items() if not hide(k, v)}
    out["waits"] = [w for w in doc.get("waits") or [] if isinstance(w, Mapping) and not hide(w.get("item"), w.get("on"))]
    branches = dict(doc.get("branches") or {})
    branches["sources"] = [s for s in branches.get("sources") or [] if isinstance(s, Mapping) and s.get("repo") not in private]
    branches["list"] = [b for b in branches.get("list") or [] if isinstance(b, Mapping) and b.get("repo") not in private
                        and not hide(b.get("owner"), b.get("item"))]
    out["branches"] = branches
    inputs = dict(doc.get("inputs") or {})
    architecture = dict(inputs.get("architecture") or {})
    if isinstance(architecture.get("repos"), Mapping):
        architecture["repos"] = {name: r for name, r in architecture["repos"].items() if name not in private}
    inputs["architecture"] = architecture
    out["inputs"] = inputs
    out["unmeasured"] = {name: why for name, why in (doc.get("unmeasured") or {}).items() if name not in private}
    out["summary"] = {
        **(doc.get("summary") or {}),
        "owners": len(with_signals), "meets": len(meets),
        "coordinated": sum(1 for m in meets if m["coordinated"]),
        "uncoordinated": sum(1 for m in meets if m["coordination"] == "uncoordinated"),
        "unlinkable": sum(1 for m in meets if m["coordination"] == "unlinkable"),
        "branches": len(branches["list"]), "unresolved": len(out["unresolved"]), "not_found": len(out["not_found"]),
    }
    return out
