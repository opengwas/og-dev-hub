"""The Dev Hub site: one static page of OpenGWAS's built state (og-dev-hub#15).

    pixi run site [--out DIR] [--data-dir DIR] [--registry PATH] [--no-refresh]
    pixi run site-preview [--out DIR] [--port N]

`pixi run site` collects what the page draws from public git alone, then builds
`_site/`: `index.html` with a tab per view (Architecture, Decisions, Context, and
Stores, which og-dev-hub#16 fills), `style.css`, one plain-JS file per view under
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

from project_site import architecture_public, diagrams, markdown, paths, staging
from project_site.collect import __main__ as command
from project_site.collect import architecture_model, common

STATIC = Path(__file__).with_name("static")
SOURCES = ("architecture",)
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
    view = architecture_public.public_view(load(data_dir))
    architecture = view["architecture"] or _unavailable("architecture", "architecture.json was not collected")
    shutil.copytree(STATIC, out)
    glossary = Path(context) if context is not None else paths.repo_root() / "CONTEXT.md"
    for name, data in (
        ("architecture", architecture_view(architecture)),
        ("decisions", decisions_view(architecture)),
        ("context", context_view(glossary.read_text(encoding="utf-8"), architecture)),
    ):
        target = out / "data" / f"{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _unavailable(source: str, error: str) -> dict[str, Any]:
    return {"source": source, "available": False, "collected_at": None, "error": error}


def _envelope(doc: Document) -> dict[str, Any]:
    return {k: doc.get(k) for k in architecture_public.ENVELOPE}


def _github(repo: str, commit: Any, path: str) -> str:
    """A file (`blob`) or a directory (`tree`, a path ending in `/`) on GitHub, at `commit`."""
    return f"{paths.clone_url(repo)}/{'tree' if path.endswith('/') else 'blob'}/{commit}/{path}"


def _repos(doc: Document) -> dict[str, Mapping[str, Any]]:
    return {str(n): r for n, r in (doc.get("repos") or {}).items() if isinstance(r, Mapping)}


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


def architecture_view(doc: Document) -> dict[str, Any]:
    """`data/architecture.json`: repositories, containers, diagrams, components, gaps, layering and the seam."""
    out = _envelope(doc)
    if not doc.get("available"):
        return out
    model = doc.get("model") or {}
    repos = _repos(doc)
    components = [c for c in doc.get("components") or [] if isinstance(c, Mapping)]
    edges = [e for e in doc.get("edges") or [] if isinstance(e, Mapping)]
    adrs = [a for a in doc.get("adrs") or [] if isinstance(a, Mapping)]
    summary = doc.get("summary") or {}
    containers = {str(c.get("id")): c for c in model.get("containers") or []}
    commits = {name: r.get("commit") for name, r in repos.items()}

    out["repos"] = [
        {"name": name, "label": diagrams.repo_label(model, name), "url": paths.clone_url(name),
         "private": bool(r.get("private")), "planned": bool(r.get("planned"))}
        | {k: r.get(k) for k in ("visibility", "status", "ref", "commit", "committed", "model", "note", "error", "refresh")}
        for name, r in repos.items()
    ]
    out["containers"] = [
        {k: c.get(k) for k in ("id", "name", "repo", "tech", "summary")}
        | {"state": "data" if c.get("repo") is None else
           "planned" if (repos.get(str(c.get("repo"))) or {}).get("planned") else
           "private" if (repos.get(str(c.get("repo"))) or {}).get("private") else "public"}
        for c in containers.values()
    ]
    out["diagrams"] = [{k: d[k] for k in ("id", "title", "caption")} | {"svg": diagrams.render_svg(d["dot"])}
                       for d in diagrams.architecture(doc)]
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
            "paths": [{"path": p, "url": _github(c["repo"], commits.get(c["repo"]), p)} for p in c.get("paths") or []],
            "adrs": [{k: a.get(k) for k in ("repo", "number", "title", "status", "url")} | {"via": a["components"][c["id"]]}
                     for a in adrs if c["id"] in (a.get("components") or {})],
        }
        for c in components
    ]
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
    """Each public repository's gaps, in `system.yaml`'s order; unknown (`None`) is never an empty list."""
    gaps = doc.get("gaps") or {}
    out = []
    for name, repo in repos.items():
        if repo.get("planned") or repo.get("private"):
            continue
        found = gaps.get(name) or {}
        out.append({
            "repo": name, "label": diagrams.repo_label(model, name),
            "unreadable": found.get("unreadable") or repo.get("error"),
            "no_model": found.get("no_model") or (repo.get("note") if repo.get("model") is False else None),
            "unclaimed": found.get("unclaimed"),
            "stale": found.get("stale"),
            "system": architecture_model.describe_system_gaps(found),
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
    order = {name: i for i, name in enumerate(_repos(doc))}
    names = {c["id"]: c["name"] for c in doc.get("components") or [] if isinstance(c, Mapping)}
    adrs = sorted((a for a in doc.get("adrs") or [] if isinstance(a, Mapping)),
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
    out: dict[str, Any] = {
        "html": markdown.render(text, base=f"{paths.clone_url(paths.HUB)}/blob/main/"),
        "source": f"{paths.clone_url(paths.HUB)}/blob/main/CONTEXT.md",
        "available": bool(doc.get("available")),
        "error": doc.get("error"),
        "glossaries": [],
    }
    for name, repo in _repos(doc).items():
        if repo.get("planned") or repo.get("private") or name == paths.HUB:
            continue
        if repo.get("commit") is None:
            url, note = None, "could not be read"
        elif repo.get("glossary"):
            url, note = _github(name, repo["commit"], "CONTEXT.md"), None
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
