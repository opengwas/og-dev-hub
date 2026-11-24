"""The Architecture view's diagrams: Graphviz DOT text, drawn to SVG at build time (og-dev-hub#15).

Three kinds, each from the public view of `architecture.json` alone
(`architecture_public.public_view`), so nothing of a private repository is ever
drawn but its container:

- the containers of `system.yaml`, with the people and external systems they talk to;
- a repository whose model declares layers, one row per layer, with the imports
  that go against the layering;
- every other repository with a model, its components by container.

A component's box links to its row in the view (`#component-<id>`). `render_svg`
is the one place Graphviz runs.
"""

from __future__ import annotations

import html
import re
import subprocess
import textwrap
from collections import defaultdict
from itertools import pairwise
from typing import Any, Mapping

from project_site.shapes import mapping

UPWARD = "#c0392b"
GREY = "#7f8c8d"
HEAD = (
    'graph [fontname="Helvetica" bgcolor="transparent" pad="0.2" nodesep="0.35" ranksep="0.55"];\n'
    'node [fontname="Helvetica" shape=box style="rounded,filled" fillcolor="white" fontcolor="black" margin="0.15,0.08"];\n'
    f'edge [fontname="Helvetica" fontsize=9 arrowsize=0.6 color="{GREY}" fontcolor="{GREY}"];\n'
)

# A component id becomes an address only in the model's own form: it can then never be markup.
LINKABLE = re.compile(r"[a-z][a-z0-9_]*\Z")
ANCHOR = "component-"


class DiagramError(RuntimeError):
    """Graphviz could not draw a diagram; its own message says why."""


def render_svg(dot: str) -> str:
    """`dot` drawn by Graphviz as an SVG element, without the XML prolog, so a page can hold it inline."""
    try:
        done = subprocess.run(["dot", "-Tsvg"], input=dot, capture_output=True, text=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiagramError(f"dot could not run: {type(error).__name__}: {error}") from error
    if done.returncode != 0:
        raise DiagramError(f"dot exited {done.returncode}: {done.stderr.strip()}")
    start = done.stdout.find("<svg")
    if start < 0:
        raise DiagramError("dot wrote no <svg> element")
    return done.stdout[start:].strip() + "\n"


def linkable(cid: Any) -> bool:
    return isinstance(cid, str) and bool(LINKABLE.match(cid))


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _dq(text: Any) -> str:
    """A string for a quoted DOT identifier or attribute: `\\` and `"` escaped, so it cannot end the string."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _label(name: str, tech: str | None, summary: str | None, width: int = 30) -> str:
    rows = [f'<FONT POINT-SIZE="12"><B>{_esc(name)}</B></FONT>']
    if tech:
        rows.append(f'<FONT POINT-SIZE="9">[{_esc(tech)}]</FONT>')
    if summary:
        rows.extend(f'<FONT POINT-SIZE="9">{_esc(line)}</FONT>' for line in textwrap.wrap(summary, width)[:4])
    return "<" + "<BR/>".join(rows) + ">"


def size(component: Mapping[str, Any]) -> str:
    """A component's measured size, as the view and the diagrams say it."""
    if component.get("files"):
        return f"{component['files']:,} files, {component['lines']:,} lines"
    return f"{component.get('tracked', 0):,} tracked files"


def repo_label(model: Mapping[str, Any], name: str) -> str:
    """A repository's name, with its container's name or id where that says more: `opengwasdb (the engine)`.

    Drawn from `system.yaml`'s containers, never written here: a repository with
    one container whose name is not the repository's is labelled with that name;
    one whose container's name is its own, with the container's id.
    """
    mine = [c for c in model.get("containers") or [] if isinstance(c, Mapping) and c.get("repo") == name]
    if len(mine) != 1:
        return name
    container = mine[0]
    if str(container.get("name")) != name:
        return str(container["name"]) if str(container["name"]).startswith(name) else f"{name} ({container['name']})"
    if str(container.get("id")) != name:
        return f"{name} (the {str(container['id']).replace('_', ' ')})"
    return name


def containers(model: Mapping[str, Any], boxes: list[Mapping[str, Any]]) -> str:
    """The containers, each drawn as its `state` says (the build decides it): `planned` dashed, `private` grey, `data` a cylinder."""
    system = model.get("system") or {}
    lines = ["digraph containers {", HEAD, "rankdir=TB; compound=true;"]
    for p in model.get("people") or []:
        lines.append(f'"{_dq(p["id"])}" [label={_label(p["name"], "Person", None)} fillcolor="#dbe9f7"];')
    lines.append(f'subgraph cluster_system {{ label="{_dq(system.get("name", "System"))}"; fontname="Helvetica"; '
                 f'fontsize=11; margin=16; color="{GREY}";')
    styles = {"data": ' shape=cylinder style="filled" fillcolor="#c5dcf2"',
              "planned": ' style="rounded,filled,dashed" fillcolor="#ffffff"',
              "private": ' fillcolor="#e5e5e5"', "public": ' fillcolor="#c5dcf2"'}
    for c in boxes:
        state, tech = c.get("state"), c.get("tech")
        if state in ("planned", "private"):
            tech = f"{state}; {tech}" if tech else state
        lines.append(f'"{_dq(c["id"])}" [{styles.get(str(state), styles["public"]).strip()} '
                     f'label={_label(c["name"], tech, c.get("summary"), 28)}];')
    lines.append("}")
    for x in model.get("external") or []:
        lines.append(f'"{_dq(x["id"])}" [label={_label(x["name"], "External", None)} fillcolor="#eeeeee"];')
    for a, b, text in model.get("container_relations") or []:
        lines.append(f'"{_dq(a)}" -> "{_dq(b)}" [label="{_dq(textwrap.fill(text, 22))}"];')
    lines.append("}")
    return "\n".join(lines)


def _node(component: Mapping[str, Any]) -> str:
    """A component's box, which links to its row in the view when its id can be an address."""
    cid = component["id"]
    link = ""
    if linkable(cid):
        link = f' URL="#{ANCHOR}{cid}" tooltip="{_dq(component["name"])}"'
    return (
        f'"{_dq(cid)}" [label=<<FONT POINT-SIZE="12"><B>{_esc(component["name"])}</B></FONT><BR/>'
        f'<FONT POINT-SIZE="9">{_esc(size(component))}</FONT>>{link}];'
    )


def _across(name: str, components: list, edges: list, mine: Mapping[str, Any], model: Mapping[str, Any],
            repos: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """One node per repository `name`'s components import, and an arrow from each importing component, with its count."""
    lines: list[str] = []
    into: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in edges:
        if e.get("scope") == "across" and e.get("from_repo") == name and e["from"] in mine:
            into[str(e.get("to_repo"))][e["from"]] += e["imports"]
    for target, sources in sorted(into.items()):
        theirs = [c for c in components if c.get("repo") == target]
        reached = {e["to"] for e in edges
                   if e.get("scope") == "across" and e.get("from_repo") == name and e.get("to_repo") == target}
        summary = (f"{len(reached)} of {len(theirs)} components" if (repos.get(target) or {}).get("state") == "read"
                   else "no architecture model yet")
        node = f"repo:{target}"
        lines.append(f'"{_dq(node)}" [fillcolor="#eeeeee" label='
                     + _label(repo_label(model, target), "imported directly", summary, 28) + "];")
        for source, n in sorted(sources.items()):
            lines.append(f'"{_dq(source)}" -> "{_dq(node)}" [label="{n}" penwidth={0.6 + min(n, 30) / 30:.2f}];')
    return lines


def layered(name: str, components: list, edges: list, layers: list, repos: Mapping[str, Mapping[str, Any]],
            model: Mapping[str, Any]) -> str:
    """Repository `name`'s components, one row per layer, with the imports that go against the layering."""
    mine = [c for c in components if c["repo"] == name]
    by_id = {c["id"]: c for c in mine}
    lines = [f"digraph {_dq(name).replace('-', '_')} {{", HEAD, "rankdir=TB; newrank=true; ranksep=0.45;"]
    for layer in layers:
        lines.append(
            f'"L{layer["layer"]}" [shape=plaintext style="" fontcolor="{GREY}" '
            f'label=<<FONT POINT-SIZE="10">{layer["layer"]} · {_esc(str(layer["name"]).upper())}</FONT>>];'
        )
    for upper, lower in pairwise(layers):
        lines.append(f'"L{upper["layer"]}" -> "L{lower["layer"]}" [style=invis];')
    for layer in layers:
        members = [c["id"] for c in mine if c["layer"] == layer["layer"]]
        lines.append("{ rank=same; " + f'"L{layer["layer"]}"; ' + "".join(f'"{_dq(i)}"; ' for i in members) + "}")
    lines += [_node(c) for c in mine]
    # An invisible spine from each layer to the next keeps the rows in order.
    for upper, lower in pairwise(layers):
        top = next((c["id"] for c in mine if c["layer"] == upper["layer"]), None)
        bottom = next((c["id"] for c in mine if c["layer"] == lower["layer"]), None)
        if top and bottom:
            lines.append(f'"{_dq(top)}" -> "{_dq(bottom)}" [style=invis weight=0];')
    for e in edges:
        if e.get("scope") != "within" or e["from"] not in by_id or e["to"] not in by_id:
            continue
        a, b, n = by_id[e["from"]], by_id[e["to"]], e["imports"]
        if e.get("upward"):
            lines.append(
                f'"{_dq(e["from"])}" -> "{_dq(e["to"])}" [color="{UPWARD}" fontcolor="{UPWARD}" penwidth=1.4 '
                f'constraint=false label=" {n}" tooltip="{_dq(a["name"])} imports {_dq(b["name"])}, a higher layer ({n})"];'
            )
        elif a["layer"] == b["layer"]:
            lines.append(f'"{_dq(e["from"])}" -> "{_dq(e["to"])}" [style=dashed constraint=false label=" {n}"];')
    lines += _across(name, components, edges, by_id, model, repos)
    lines.append("}")
    return "\n".join(lines)


def by_container(name: str, components: list, edges: list, model: Mapping[str, Any],
                 repos: Mapping[str, Mapping[str, Any]]) -> str:
    """Repository `name`'s components by container, the imports between them, and its imports of other repositories."""
    mine = [c for c in components if c["repo"] == name]
    known = {c["id"]: c for c in model.get("containers") or []}
    grouped: dict[str, list[str]] = defaultdict(list)
    for c in mine:
        grouped[c["container"]].append(c["id"])
    by_id = {c["id"]: c for c in mine}
    lines = [f"digraph {_dq(name).replace('-', '_')} {{", HEAD, "rankdir=TB; newrank=true;"]
    for container, ids in grouped.items():
        label = known.get(container, {}).get("name", container)
        lines.append(f'subgraph "cluster_{_dq(container)}" {{ label="{_dq(label)}"; fontname="Helvetica"; '
                     f'fontsize=11; margin=12; color="{GREY}";')
        lines += [_node(by_id[i]) for i in ids]
        lines.append("}")
    for e in edges:
        if e.get("scope") == "within" and e["from"] in by_id and e["to"] in by_id:
            lines.append(f'"{_dq(e["from"])}" -> "{_dq(e["to"])}";')
    lines += _across(name, components, edges, by_id, model, repos)
    lines.append("}")
    return "\n".join(lines)


def architecture(parts: Any, repos: Mapping[str, Mapping[str, Any]], boxes: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Every diagram of the Architecture view: `{id, title, caption, dot}`.

    `parts` is `architecture_public.parts` of the public view; `repos` (name to
    record) and `boxes` (the containers) carry the `state` the build decided. The
    containers first; then each repository read whose model declares layers, then
    the other repositories read, each in `system.yaml`'s order.
    """
    model, components, edges = parts.model, parts.components, parts.edges
    layers = mapping(model.get("layers"))
    out = [{
        "id": "containers",
        "title": "Containers",
        "caption": "The containers of system.yaml and how they relate. A dashed box is a planned repository's; "
                   "a grey one is a private repository's, drawn as its container only; a cylinder is data.",
        "dot": containers(model, boxes),
    }]
    for name, repo in sorted(repos.items(), key=lambda item: not layers.get(item[0])):
        if repo.get("state") != "read" or not any(c.get("repo") == name for c in components):
            continue
        label = repo_label(model, name)
        if layers.get(name):
            out.append({
                "id": name, "title": f"{label} by layer",
                "caption": "Each row is a layer, the top layer first; a component may import from its own layer or "
                           "below. Red arrows are imports that go against that layering, labelled with their count. "
                           "Dashed arrows are imports within a layer. Imports that follow the layering are not drawn.",
                "dot": layered(name, components, edges, layers[name], repos, model),
            })
        else:
            out.append({
                "id": name, "title": f"{label}, and its imports of other repositories",
                "caption": "Its components by container. Numbers on the arrows into another repository are imports "
                           "of its modules.",
                "dot": by_container(name, components, edges, model, repos),
            })
    return out
