"""The Dev Hub site: one static page of OpenGWAS's built state (og-dev-hub#15).

    pixi run site [--out DIR] [--data-dir DIR] [--registry PATH] [--no-refresh]
    pixi run site-preview [--out DIR] [--port N]

`pixi run site` collects what the page draws from public git alone, then builds
`_site/`: `index.html` with a tab per view (Architecture, Decisions, Context and
Stores), `style.css`, one plain-JS file per view under
`js/`, and the JSON each view renders from under `data/`. No framework, no
bundler, no CDN, and every path relative, so the page works from any sub-path
(`/og-dev-hub/`).

**Public git only.** The collection is `collect.__main__.run(public_only=True)`,
over clones in the site's own work root (`paths.site_work_root`): every
repository `system.yaml` lists as `public` is cloned anonymously and read at
`main`; a `private` one is drawn as its container from `system.yaml` and is
never cloned; the board is not read. `pixi run architecture` still reads private
repositories and the board, locally; only the site does not.

**One filter.** `build` reads the collected files, passes them through
`architecture_public.public_view`, and writes each view's JSON from that alone.
The diagrams are Graphviz DOT (`diagrams`), drawn to SVG at build time and held
in `data/architecture.json`.

`pixi run site-preview` serves the built `_site/` at
`http://localhost:<port>/og-dev-hub/`, the sub-path it is published at.
"""

from __future__ import annotations

import argparse
import http.server
import json
import shutil
import sys
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any, Mapping

from project_site import architecture_public, diagrams, markdown, paths, staging, stores_view
from project_site.collect import __main__ as command
from project_site.collect import architecture_model, common

STATIC = Path(__file__).with_name("static")
SOURCES = ("architecture", "stores")
# The sub-path the site is published at, which the preview serves it under too.
PREFIX = "og-dev-hub"

Document = Mapping[str, Any]


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def load(data_dir: Path) -> dict[str, Document]:
    """Each source the site draws, as collected into `data_dir`; one that is missing or unreadable says so."""
    documents: dict[str, Document] = {}
    for source in SOURCES:
        path = Path(data_dir) / f"{source}.json"
        try:
            documents[source] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            documents[source] = _unavailable(source, f"{source}.json was not collected")
        except (OSError, ValueError) as error:
            documents[source] = _unavailable(source, f"{source}.json cannot be read: {type(error).__name__}: {error}")
    return documents


def build(data_dir: Path, out: Path, *, context: Path | None = None) -> None:
    """Write the site into `out` from the collection in `data_dir` and the hub's `CONTEXT.md` (`context`)."""
    out = Path(out)
    if out.exists():
        if any(out.iterdir()) and not (out / "index.html").exists():
            raise SystemExit(f"{out} holds files and no index.html: it is not a site build, so it is left alone")
        shutil.rmtree(out)
    documents = load(data_dir)
    view = architecture_public.public_view(documents)
    architecture = view["architecture"] or _unavailable("architecture", "architecture.json was not collected")
    shutil.copytree(STATIC, out)
    glossary = Path(context) if context is not None else paths.repo_root() / "CONTEXT.md"
    for name, data in (
        ("architecture", architecture_view(architecture)),
        ("decisions", decisions_view(architecture)),
        ("context", context_view(glossary.read_text(encoding="utf-8"), architecture)),
        ("stores", stores_view.stores_view(documents["stores"])),
        ("benchmarking", stores_view.benchmarking_view(documents["stores"])),
    ):
        target = out / "data" / f"{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _unavailable(source: str, error: str) -> dict[str, Any]:
    return {"source": source, "available": False, "collected_at": None, "error": error}


def _envelope(doc: Document) -> dict[str, Any]:
    return {k: doc.get(k) for k in architecture_public.ENVELOPE}


def repo_state(repo: Mapping[str, Any]) -> str:
    """The one place a repository's state is decided, from the public view's record of it.

    `planned` (not created yet), `private` (drawn as its container only),
    `unreadable` (no commit could be read), `no_model` (read, with no usable
    model), or `read`. Every view and diagram reads this, and none decides it again.
    """
    if repo.get("planned"):
        return "planned"
    if repo.get("private"):
        return "private"
    if repo.get("error") or not repo.get("commit"):
        return "unreadable"
    return "read" if repo.get("model") else "no_model"


def container_state(container: Mapping[str, Any], states: Mapping[str, str]) -> str:
    """`data` (no repository), else its repository's `planned` or `private`, else `public`."""
    if container.get("repo") is None:
        return "data"
    state = states.get(str(container.get("repo")))
    return state if state in ("planned", "private") else "public"


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def architecture_view(doc: Document) -> dict[str, Any]:
    """`data/architecture.json`: repositories, containers, diagrams, components, gaps, layering and the seam.

    Every state and figure the view shows is written here; the script only renders it.
    """
    out = _envelope(doc)
    if not doc.get("available"):
        return out
    parts = architecture_public.parts(doc)
    model, components, edges = parts.model, parts.components, parts.edges
    summary = doc.get("summary") or {}
    containers = {str(c.get("id")): c for c in model.get("containers") or []}
    states = {name: repo_state(r) for name, r in parts.repos.items()}

    repos = {
        name: {"name": name, "label": diagrams.repo_label(model, name), "url": paths.clone_url(name), "state": states[name]}
        | {k: r.get(k) for k in ("visibility", "status", "ref", "commit", "committed")}
        | {"why": r.get("error") if states[name] == "unreadable" else r.get("note") if states[name] == "no_model" else None,
           "refresh_error": (r.get("refresh") or {}).get("error") if (r.get("refresh") or {}).get("ok") is False else None}
        for name, r in parts.repos.items()
    }
    boxes = [{k: c.get(k) for k in ("id", "name", "repo", "tech", "summary")} | {"state": container_state(c, states)}
             for c in containers.values()]
    out["repos"] = list(repos.values())
    out["containers"] = boxes
    out["diagrams"] = [{k: d[k] for k in ("id", "title", "caption")} | {"svg": diagrams.render_svg(d["dot"])}
                       for d in diagrams.architecture(parts, repos, boxes)]
    out["stages"] = [
        {k: st.get(k) for k in ("id", "name", "summary", "repo")}
        | {"components": [c["id"] for c in components if st.get("id") in (c.get("stages") or [])]}
        for st in model.get("stages") or []
    ]
    out["components"] = [
        {k: c.get(k) for k in ("id", "name", "repo", "container", "layer", "stages", "summary", "files", "lines", "tracked")}
        | {
            "anchor": c["id"] if diagrams.linkable(c["id"]) else None,
            "container_name": (containers.get(str(c.get("container"))) or {}).get("name", c.get("container")),
            "size": diagrams.size(c),
            "paths": [{"path": p, "url": paths.github_url(c["repo"], repos[c["repo"]]["commit"], p)} for p in c.get("paths") or []],
            "adrs": [{k: a.get(k) for k in ("repo", "number", "title", "status", "url")} | {"via": a["components"][c["id"]]}
                     for a in parts.adrs if c["id"] in (a.get("components") or {})],
        }
        for c in components
    ]
    out["component_repos"] = list(dict.fromkeys(str(c["repo"]) for c in components))
    out["counts"] = {"components": len(components), "repos_with_model": sum(1 for st in states.values() if st == "read")}
    out["gaps"] = _gaps(doc, model, repos)
    out["layering"] = _layering(model, components, edges)
    out["seam"] = {
        "from": "opengwasdb-stores", "to": "opengwasdb",
        "imports": summary.get("registry_to_engine_imports"), "pairs": summary.get("registry_to_engine_edges"),
        "baseline": doc.get("baseline"),
    }
    across: dict[tuple[str, str], list[int]] = defaultdict(list)
    for e in edges:
        if e.get("scope") == "across":
            across[(str(e.get("from_repo")), str(e.get("to_repo")))].append(int(e.get("imports") or 0))
    out["across"] = [{"from_repo": a, "to_repo": b, "imports": sum(n), "pairs": len(n)} for (a, b), n in sorted(across.items())]
    out["summary"] = dict(summary)
    return out


def _gaps(doc: Document, model: Mapping[str, Any], repos: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each public repository's gaps, in `system.yaml`'s order, with its `state`.

    The state follows the repository's, as `repo_state` decided it: `unreadable`
    and `no_model` carry its `why`. A repository read with a model is `gaps` (an
    unclaimed file, a stale claim or a system gap) or `complete`, but only when
    its claims were measured; without a gap record, or with `unclaimed` or `stale`
    unknown (`None`), it is `unknown`, never `complete`.
    """
    gaps = doc.get("gaps") or {}
    out = []
    for name, repo in repos.items():
        if repo["state"] in ("planned", "private"):
            continue
        found = gaps.get(name) if isinstance(gaps.get(name), Mapping) else None
        unclaimed, stale = (found or {}).get("unclaimed"), (found or {}).get("stale")
        system = architecture_model.describe_system_gaps(found or {})
        if repo["state"] in ("unreadable", "no_model"):
            state = repo["state"]
        elif found is None or unclaimed is None or stale is None:
            state = "unknown"
        else:
            state = "gaps" if unclaimed or stale or system else "complete"
        out.append({
            "repo": name, "label": repo["label"], "state": state,
            "unreadable": repo["why"] if state == "unreadable" else None,
            "no_model": repo["why"] if state == "no_model" else None,
            "unclaimed": unclaimed if state in ("gaps", "complete") else None,
            "stale": stale if state in ("gaps", "complete") else None,
            "system": system,
        })
    return out


def _layering(model: Mapping[str, Any], components: list, edges: list) -> list[dict[str, Any]] | None:
    """Each layered repository's imports against its layering; `None` (unknown) when no model declares layers."""
    layers = model.get("layers") if isinstance(model.get("layers"), Mapping) else {}
    if not layers:
        return None
    by_id = {c["id"]: c for c in components}
    out = []
    for name in layers:
        mine = [e for e in edges if e.get("scope") == "within" and e.get("repo") == name]
        upward = sorted((e for e in mine if e.get("upward") and e["from"] in by_id and e["to"] in by_id),
                        key=lambda e: (-int(e.get("imports") or 0), e["from"], e["to"]))
        out.append({
            "repo": name, "label": diagrams.repo_label(model, name), "edges": len(mine),
            "imports": sum(int(e.get("imports") or 0) for e in upward),
            "upward": [{"from": e["from"], "from_name": by_id[e["from"]]["name"], "from_layer": by_id[e["from"]].get("layer"),
                        "to": e["to"], "to_name": by_id[e["to"]]["name"], "to_layer": by_id[e["to"]].get("layer"),
                        "imports": e.get("imports")} for e in upward],
        })
    return out


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def decisions_view(doc: Document) -> dict[str, Any]:
    """`data/decisions.json`: every public repository's ADRs, in `system.yaml`'s order, then by number."""
    out = _envelope(doc)
    if not doc.get("available"):
        return out
    parts = architecture_public.parts(doc)
    order = {name: i for i, name in enumerate(parts.repos)}
    names = {c["id"]: c["name"] for c in parts.components}
    adrs = sorted(parts.adrs,
                  key=lambda a: (order.get(str(a.get("repo")), len(order)), str(a.get("number"))))
    urls = {(str(a.get("repo")), str(a.get("number"))): a.get("url") for a in adrs}
    out["repos"] = list(dict.fromkeys(str(a.get("repo")) for a in adrs))
    out["adrs"] = [
        {k: a.get(k) for k in ("repo", "number", "title", "status", "url")}
        | {
            "components": [{"id": cid, "name": names[cid], "via": via}
                           for cid, via in (a.get("components") or {}).items() if cid in names],
            "cites": [{"repo": c.get("repo"), "number": c.get("number"), "text": f"{c.get('repo')} ADR {c.get('number')}",
                       "url": urls.get((str(c.get("repo")), str(c.get("number"))))} for c in a.get("cites") or []],
        }
        for a in adrs
    ]
    return out


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def context_view(text: str, doc: Document) -> dict[str, Any]:
    """`data/context.json`: the hub's `CONTEXT.md` as HTML, and each public repository's glossary on GitHub."""
    source = paths.github_url(paths.HUB, "main", "CONTEXT.md")
    out: dict[str, Any] = {
        "html": markdown.render(text, base=source),
        "source": source,
        "available": bool(doc.get("available")),
        "error": doc.get("error"),
        "glossaries": [],
    }
    for name, repo in architecture_public.parts(doc).repos.items():
        state = repo_state(repo)
        if state in ("planned", "private") or name == paths.HUB:
            continue
        if state == "unreadable":
            url, note = None, "could not be read"
        elif repo.get("glossary"):
            url, note = paths.github_url(name, repo["commit"], "CONTEXT.md"), None
        else:
            url, note = None, "no CONTEXT.md at the commit read"
        out["glossaries"].append({"repo": name, "url": url, "note": note})
    return out


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


class _Handler(http.server.SimpleHTTPRequestHandler):
    """The built site under `/og-dev-hub/`, as it is published; `/` goes there."""

    def translate_path(self, path: str) -> str:
        prefix = f"/{PREFIX}"
        bare = path.split("?", 1)[0].split("#", 1)[0]
        if bare == prefix or bare.startswith(prefix + "/"):
            return super().translate_path(path[len(prefix):] or "/")
        return str(Path(self.directory) / ".not-served")

    def do_GET(self) -> None:  # noqa: N802 - the http.server name
        if self.path in ("/", f"/{PREFIX}"):
            self.send_response(302)
            self.send_header("Location", f"/{PREFIX}/")
            self.end_headers()
            return
        super().do_GET()


def serve(out: Path, port: int) -> None:
    handler = partial(_Handler, directory=str(out))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"serving {out} at http://localhost:{port}/{PREFIX}/ (Ctrl-C stops)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project_site.site", description=__doc__.split("\n")[0])
    parser.add_argument("command", nargs="?", choices=("build", "serve"), default="build")
    parser.add_argument("--out", type=Path, default=paths.repo_root() / "_site", help="the site (default: _site/)")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help=f"where the collection goes (default: ${common.DATA_DIR_ENV_VAR}, else docs/_data/)")
    parser.add_argument("--registry", type=Path, default=None, help="an opengwasdb-stores checkout to read instead of its clone")
    parser.add_argument("--no-refresh", action="store_true", help="read the clones as they are, without fetching")
    parser.add_argument("--port", type=int, default=4200, help="serve: the port (default 4200)")
    args = parser.parse_args(argv)
    if args.command == "serve":
        if not (args.out / "index.html").exists():
            parser.error(f"{args.out} holds no site: run `pixi run site` first")
        serve(args.out, args.port)
        return 0
    data_dir = args.data_dir or common.data_dir()
    # Public git alone, in the site's own work root: a private repository is never cloned, the board never read.
    repositories = staging.Repositories(refresh=not args.no_refresh, checkouts={paths.REGISTRY: args.registry},
                                        root=paths.site_work_root())
    command.run(data_dir, repositories=repositories, public_only=True)
    build(data_dir, args.out)
    print(f"site: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
