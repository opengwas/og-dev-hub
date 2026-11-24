"""The architecture pages: Pipeline, Structure and health (#418) and the Work map (#419), epic #416.

Both are written from `architecture.json`, the architecture collector's file
(`docs/spec/project-site.md`). Like every page of `pages.py` they read
`available` first and show the site's usual notice when the source could not be
read, and every figure traces to one collector field.

The diagrams are Quarto `{dot}` cells, which Quarto draws at render time with
its own bundled Graphviz. A `{dot}` cell is a diagram, not code: it needs no
kernel and no new dependency, so `pages.py`'s promise of no executable code
cells still holds, and nothing generated is ever committed.

The Work map is written from `work.json`, the work collector's file, and is
the one page that is not about the code alone: it says where live work meets,
so it states when it was measured and that branches existing only on a build
host are not shown (the `conflicts` command, run there, shows them).

Each page states what is written by hand (the models: stages, layers, claims,
the context and containers) and what is measured (code size, imports, ADR
placement, gaps), so a reader knows which part can drift and which cannot.

On every page a component, its box in a diagram or its name in a list or
table, opens the component panel (#435, `architecture_panel.py`): its code,
the work on it, its imports each way and its ADRs.

Every repository `system.yaml` lists is drawn (og-dev-hub#9): a planned one as
a planned container, one that could not be read or has no model as a gap, and a
private one as its container only. Each page renders from
`architecture_public.public_view` of the collected files, and from nothing
else, so nothing of a private repository reaches a page or the panel.
"""

from __future__ import annotations

import html
import textwrap
from collections import defaultdict
from itertools import pairwise
from typing import Any, Mapping

from project_site import architecture_panel, architecture_public, pages
from project_site.collect import architecture_graph, architecture_model as model_rules

Document = Mapping[str, Any]

UPWARD = "#c0392b"
GREY = "#7f8c8d"
HEAD = (
    'graph [fontname="Arial" bgcolor="transparent" pad="0.2" nodesep="0.35" ranksep="0.55"];\n'
    'node [fontname="Arial" shape=box style="rounded,filled" fillcolor="white" fontcolor="black" margin="0.15,0.08"];\n'
    f'edge [fontname="Arial" fontsize=9 arrowsize=0.6 color="{GREY}" fontcolor="{GREY}"];\n'
)

PIPELINE_INTRO = (
    "The path data takes through the system, from a source file to a query: the stages, the "
    "components that do each one in every repository with a model, and the architecture decisions (ADRs) "
    "that govern them."
)
STRUCTURE_INTRO = (
    "How the system fits together at three levels (C4): who and what it talks to, its "
    "containers, and the components inside each repository with a model, with the imports "
    "within and between them."
)


def render_pipeline(documents: Mapping[str, Document | None]) -> str:
    """The landing page: each stage with its components and their ADRs."""
    documents = architecture_public.public_view(documents)
    lines = [pages.GENERATED, "", PIPELINE_INTRO, "", "See also [Structure and health](architecture-structure.qmd).", ""]
    data = pages.available(documents, "architecture")
    if data is None:
        return "\n".join(lines + pages.notices(documents, ("architecture",))).rstrip() + "\n"
    panel = _panel(documents)
    lines += _hand_and_measured(
        hand="the stages and their order, which stages each component serves, each component's name, "
        "summary and the code paths it claims",
        measured="each component's code size, the ADRs placed on it (by the code an ADR cites and by "
        "component names in its title), and the commit read in each repository",
    )
    lines += _read_notice(data)
    lines += ["## The stages", ""]
    components = [c for c in data.get("components") or [] if isinstance(c, Mapping)]
    stages = list((data.get("model") or {}).get("stages") or [])
    ordered = [s for s in stages if s["id"] != "cross"] + [s for s in stages if s["id"] == "cross"]
    for number, stage in enumerate(ordered, 1):
        members = [c for c in components if stage["id"] in c.get("stages", [])]
        lines += [f"### {number}. {pages.escape(str(stage['name']))}", "", pages.escape(str(stage.get("summary") or "")), ""]
        if not members:
            lines += ["_No component serves this stage._", ""]
            continue
        for c in members:
            lines.append(f"- **{panel.link(c['name'], c['id'])}** ({c['repo']}; {_size(c)}): {pages.escape(str(c['summary']))}")
            lines += [f"  - {_adr_link(a, [c], data)}" for a in _adrs_for(data, {c["id"]})]
        lines.append("")
    lines += ["## ADRs the map cannot place", ""]
    unplaced = [a for a in data.get("adrs") or [] if not a["components"]]
    summary = data.get("summary") or {}
    lines.append(
        f"{pages._figure(summary.get('adrs_placed'))} of {pages._figure(summary.get('adrs_total'))} ADRs are placed on a "
        "component. These cite no code a component claims and name none in their title:"
    )
    lines.append("")
    lines += [f"- [{pages.escape(str(a['title']))}]({a['url']}) ({a['repo']}){_cites(data, a)}" for a in unplaced] or ["_None._"]
    lines += ["", _as_of(data), ""]
    lines += panel.block()
    return "\n".join(lines).rstrip() + "\n"


def render_structure(documents: Mapping[str, Document | None]) -> str:
    """The structure of every listed repository, and the measured health of the claims and layering."""
    documents = architecture_public.public_view(documents)
    lines = [pages.GENERATED, "", STRUCTURE_INTRO, "", "See also the [Pipeline](architecture.qmd).", ""]
    data = pages.available(documents, "architecture")
    if data is None:
        return "\n".join(lines + pages.notices(documents, ("architecture",))).rstrip() + "\n"
    panel = _panel(documents)
    lines += _hand_and_measured(
        hand="the system context, the containers and how they relate, the layers a model declares (the "
        "intended layering, a decision rather than a measurement) and the code each component claims",
        measured="the imports between components (counts, read from the code of every repository with a model), "
        "which of them go against the layering, the imports across repositories, and the gaps in the claims",
        where="The system context, the containers and the list of repositories are og-dev-hub's `system.yaml`; "
        "the layers and claims are in each repository's `docs/architecture/components.yaml`.",
    )
    lines += _read_notice(data)
    model = data.get("model") or {}
    components = [c for c in data.get("components") or [] if isinstance(c, Mapping)]
    edges = [e for e in data.get("edges") or [] if isinstance(e, Mapping)]
    summary = data.get("summary") or {}
    repos = _repos(data)
    layers = model.get("layers") if isinstance(model.get("layers"), Mapping) else {}

    lines += ["## System context", "", _cell(_context(model)), "## Containers", "", _container_key(), "",
              _cell(_containers(model, repos))]
    # The layered repositories first (the engine), then the others, each in system.yaml's order.
    for name, repo in sorted(repos.items(), key=lambda item: not layers.get(item[0])):
        mine = [c for c in components if c.get("repo") == name]
        if not repo.get("model") or not mine:
            continue
        label = repo_label(model, name)
        if layers.get(name):
            lines += [
                f"## {pages.escape(label)} by layer",
                "",
                "Each row is a layer, the top layer first; a component may import from its own layer or "
                f"below. <span style=\"color:{UPWARD}\">Red</span> arrows are imports that go **against** "
                "that layering, labelled with their import count. Dashed arrows are imports within a "
                "layer. Imports that follow the layering are not drawn.",
                "",
                _cell(_layered(name, components, edges, layers[name], repos, model)),
            ]
        else:
            lines += [
                f"## {pages.escape(label)}, and its imports of other repositories",
                "",
                "Its components by container. Numbers on the arrows into another repository are imports of its modules.",
                "",
                _cell(_by_container(name, components, edges, model, repos)),
            ]
    lines += _health(data, components, edges, summary, panel)
    lines += _planned(documents)
    lines += [_as_of(data), ""]
    lines += panel.block()
    return "\n".join(lines).rstrip() + "\n"


WORK_INTRO = (
    "Which work is changing which part of the system right now, and where two owners' work meets on "
    "one component. An owner is an epic, or a branch or ticket that is on no epic of the board."
)
STATE_ORDER = ("building", "active", "waiting", "scope", "planned", "paused", "stale")
STATE_MEANING = (
    ("building", "a branch's diff against the merge-base with `main`"),
    ("active", "a file cited by an open ticket of an Active epic"),
    ("waiting", "a file cited by an open ticket that waits for another open ticket"),
    ("scope", "a file cited by an epic's body"),
    ("planned", "a file cited by an open ticket of a Todo epic"),
    ("paused", "a file cited by an open ticket of a Paused epic"),
    ("stale", "a branch whose epic or ticket is closed"),
)


def render_work(documents: Mapping[str, Document | None]) -> str:
    """The Work map: tiles, where work meets, the components by owner, and the branches."""
    documents = architecture_public.public_view(documents)
    lines = [pages.GENERATED, "", WORK_INTRO, "", "See also the [Pipeline](architecture.qmd).", ""]
    data = pages.available(documents, "work")
    if data is None:
        return "\n".join(lines + pages.notices(documents, ("work",))).rstrip() + "\n"
    lines += _hand_and_measured(
        hand="which code each component owns (the claims in each repository's `docs/architecture/components.yaml`), "
        "the epics and tickets on the board and the blocking edges between them, and the files a ticket's text cites",
        where="The claims are in the repositories, the rest on the project board.",
        measured="the files each live branch changes, which component each file and each cited file falls on, "
        "the state of each piece of work there, and the meets between owners",
    )
    lines += _measured_at(data)
    lines += _fetch_failures(data)
    lines += _unmeasured(data)
    lines += _unresolved(data)
    lines += _not_found(data)
    summary = data.get("summary") or {}
    lines += [
        "| Owners | Meets | Coordinated | Uncoordinated | Unlinkable | Branches |",
        "|---:|---:|---:|---:|---:|---:|",
        "| " + " | ".join(
            pages._figure(summary.get(k))
            for k in ("owners", "meets", "coordinated", "uncoordinated", "unlinkable", "branches")
        ) + " |",
        "",
    ]
    owners = {o["key"]: o for o in data.get("owners") or [] if isinstance(o, Mapping)}
    names = {c["id"]: c["name"] for c in data.get("components") or [] if isinstance(c, Mapping)}
    panel = _panel(documents)
    lines += ["## Where work meets", ""]
    lines += _meets(data, owners, names, panel)
    lines += ["## Components by owner", ""]
    lines += _matrix(data, owners, names, panel)
    lines += ["## Branches", ""]
    lines += _branches(data, owners, names, panel)
    lines += ["## What the states mean", ""]
    lines += [f"- **{state}**: {meaning}" for state, meaning in STATE_MEANING]
    lines += [
        "",
        "A meet is two or more owners with `building` or `active` work on one component. It is "
        "**coordinated** only when a blocking edge links two specific tickets of the owners, in either "
        "direction; sharing an epic, or an edge between other tickets of the same epics, does not count. "
        "A meet that involves an epic's integration branch is **unlinkable**: the branch belongs to the epic "
        "as a whole, so no edge can link it to one ticket, and \"uncoordinated\" would claim more than was checked.",
        "",
    ]
    lines += panel.block()
    return "\n".join(lines).rstrip() + "\n"


def _measured_at(data: Document) -> list[str]:
    inputs = data.get("inputs") or {}
    architecture = inputs.get("architecture") or {}
    unmeasured = data.get("unmeasured") or {}
    read = [f"{pages.escape(str(name))} {pages._code(r.get('ref'))} ({pages._code(str(r.get('commit'))[:12])})"
            for name, r in (architecture.get("repos") or {}).items()
            if isinstance(r, Mapping) and r.get("commit") and name not in unmeasured]
    days = next((s.get("days") for s in (data.get("branches") or {}).get("sources") or [] if s.get("days")), None)
    return [
        f"Measured {pages._cell(data.get('collected_at'))}, from the board (collected {pages._cell((inputs.get('board') or {}).get('collected_at'))}) "
        f"and the claims at {', '.join(read) or 'no repository with a model'}. "
        f"Branches are pushed ones ahead of `main` whose newest commit is within {pages._figure(days)} days; branches that "
        "exist only on a build host are not shown. On that host, `pixi run architecture conflicts --branch NAME --local GIT_DIR` includes them.",
        "",
    ]


def _fetch_failures(data: Document) -> list[str]:
    lines = []
    for source in (data.get("branches") or {}).get("sources") or []:
        fetch = source.get("fetch")
        if isinstance(fetch, Mapping) and fetch.get("ok") is False:
            lines += [
                f"> **The branch fetch for {pages.escape(str(source.get('repo')))} failed**: {pages._cell(fetch.get('error'))}. "
                "The branches shown are the ones already there, so they may be out of date.",
                "",
            ]
        if source.get("error"):
            lines += [
                f"> **The branches of {pages.escape(str(source.get('repo')))} could not be read**: {pages._cell(source.get('error'))}.",
                "",
            ]
    return lines


def _unmeasured(data: Document) -> list[str]:
    """Work that could not be placed: unknown, so the page says so instead of showing no meets."""
    unmeasured = data.get("unmeasured") or {}
    if not unmeasured:
        return []
    names = ", ".join(pages.escape(str(name)) for name in unmeasured)
    lines = [
        f"> **Work was not measured in {names}**: without a repository's claims none of its files belongs to a "
        "component, so the meets shown are the other repositories' only; a meet there is not ruled out.",
        "",
    ]
    return lines + [f"- {pages.escape(str(name))}: {pages._cell(why)}" for name, why in unmeasured.items()] + [""]


def _unresolved(data: Document) -> list[str]:
    """Cited paths that matched more than one tracked file: counted and listed, never guessed."""
    rows = [r for r in data.get("unresolved") or [] if isinstance(r, Mapping)]
    if not rows:
        return []
    plural = "citation" if len(rows) == 1 else "citations"
    lines = [
        f"> **{len(rows)} {plural} could not be placed**: each names a path that more than one tracked file ends with, "
        "so it is not guessed, and the work that cites it is not on the map. Cite the full path to place it.",
        "",
    ]
    for r in rows:
        candidates = ", ".join(pages._code(str(c)) for c in r.get("candidates") or [])
        lines.append(f"- {pages.escape(str(r.get('item')))} cites {pages._code(r.get('cited'))}: {candidates}")
    return lines + [""]


def _not_found(data: Document) -> list[str]:
    """Cited code paths no tracked file matches: still attributed by claim, but a typo must be visible."""
    rows = [r for r in data.get("not_found") or [] if isinstance(r, Mapping)]
    if not rows:
        return []
    names = {c["id"]: c["name"] for c in data.get("components") or [] if isinstance(c, Mapping)}
    plural = "path was" if len(rows) == 1 else "paths were"
    lines = [
        f"> **{len(rows)} cited {plural} not found**: no tracked file is, or ends with, each path. The work is "
        "still shown on the component that claims the path, in case the ticket means to create the file.",
        "",
        "Cited paths not found (attributed to a component by its claim):",
        "",
    ]
    for r in rows:
        cid = str(r.get("component"))
        lines.append(f"- {pages.escape(str(r.get('item')))} cites {pages._code(r.get('cited'))}: {pages.escape(str(names.get(cid, cid)))}")
    return lines + [""]


def _owner(key: str, owners: Mapping[str, Mapping[str, Any]]) -> str:
    found = owners.get(key) or {}
    link = pages._link(key, found.get("url"))
    title = found.get("title")
    return f"{link} {pages.escape(str(title))}" if title and title != key else link


_ORDER = {"uncoordinated": 0, "unlinkable": 1, "coordinated": 2}


def _meets(data: Document, owners: Mapping[str, Any], names: Mapping[str, str], panel: architecture_panel.Panel) -> list[str]:
    meets = [m for m in data.get("meets") or [] if isinstance(m, Mapping)]
    if not meets:
        return ["No two owners have building or active work on the same component.", ""]
    signals = [s for s in data.get("signals") or [] if isinstance(s, Mapping)]
    lines: list[str] = []
    for meet in sorted(meets, key=lambda m: (_ORDER.get(m.get("coordination"), 0), str(m.get("component")))):
        cid = meet["component"]
        lines += [f"### {panel.link(names.get(cid, cid), cid)}", ""]
        for owner in meet["owners"]:
            lines.append(f"- {_owner(owner, owners)}")
            for item in meet["items"].get(owner, []):
                found = [s for s in signals if s["component"] == cid and s["owner"] == owner and s["item"] == item
                         and s["state"] in ("building", "active")]
                detail = "; ".join(f"{s['state']}: " + ", ".join(pages._code(w) for w in s["what"]) for s in found)
                lines.append(f"  - {pages.escape(item)} ({detail})")
        lines.append("")
        for pair in meet.get("pairs") or []:
            a, b = pair["owners"]
            kind = pair.get("coordination") or ("coordinated" if pair.get("coordinated") else "uncoordinated")
            if kind == "coordinated":
                edges = "; ".join(f"{pages.escape(e['waiting'])} waits for {pages.escape(e['on'])}" for e in pair["edges"])
                lines.append(f"**Coordinated**: {edges}.")
            elif kind == "unlinkable":
                why = "; ".join(
                    f"{pages._code(name)} belongs to an epic as a whole, so no blocking edge can link it to a single ticket"
                    for name in pair.get("epic_branches") or [])
                lines.append(f"**Unlinkable**: {why}. Whether {pages.escape(a)} and {pages.escape(b)} are coordinated "
                             "can't be checked ticket by ticket, so ask a person.")
            else:
                mine, theirs = (", ".join(pages.escape(i) for i in meet["items"].get(o, [])) for o in (a, b))
                lines.append(f"**Uncoordinated**: no blocking edge links {mine} ({pages.escape(a)}) and {theirs} ({pages.escape(b)}).")
            lines.append("")
    return lines


def _matrix(data: Document, owners: Mapping[str, Any], names: Mapping[str, str], panel: architecture_panel.Panel) -> list[str]:
    signals = [s for s in data.get("signals") or [] if isinstance(s, Mapping)]
    columns = sorted({s["owner"] for s in signals})
    if not columns:
        return ["No component has any work on it.", ""]
    lines = [
        "| Component | " + " | ".join(pages._link(o, (owners.get(o) or {}).get("url")) for o in columns) + " |",
        "|---|" + "---|" * len(columns),
    ]
    for cid in sorted({s["component"] for s in signals}):
        row = []
        for owner in columns:
            states = {s["state"] for s in signals if s["component"] == cid and s["owner"] == owner}
            row.append(", ".join(s for s in STATE_ORDER if s in states))
        lines.append(f"| {panel.link(names.get(cid, cid), cid)} | " + " | ".join(row) + " |")
    return lines + [""]


def _branches(data: Document, owners: Mapping[str, Any], names: Mapping[str, str], panel: architecture_panel.Panel) -> list[str]:
    listed = [b for b in (data.get("branches") or {}).get("list") or [] if isinstance(b, Mapping)]
    if not listed:
        return ["No branch is ahead of `main` within the window.", ""]
    lines = ["| Branch | Repository | Ahead | Newest commit | Files | Ticket | Owner | Components |", "|---|---|---:|---|---:|---|---|---|"]
    for b in listed:
        lines.append(
            f"| {pages._code(b['name'])} | {pages.escape(str(b['repo']))} | {pages._figure(b.get('ahead'))} | "
            f"{pages._cell(b.get('committed'))} | {pages._figure(len(b.get('files') or []))} | {pages.escape(str(b.get('item')))} | "
            f"{'unknown' if b.get('owner_unknown') else pages.escape(str(b.get('owner')))} | "
            f"{', '.join(panel.link(names.get(c, c), c) for c in b.get('components') or [])} |"
        )
    return lines + [""]


# ---------------------------------------------------------------------------
# Planned changes (#422)
# ---------------------------------------------------------------------------

VERDICT = {True: "held", False: "not held", None: "unknown"}
ACTION = {"adds": "added", "moves": "moved"}


def _planned(documents: Mapping[str, Document | None]) -> list[str]:
    """The tickets' planned changes, from `work.json`: a diagram per plan, and what a closed one achieved."""
    lines = [
        "## Planned changes",
        "",
        "A ticket that changes the structure says how in an `architecture` block of its body. The plan is "
        "**written by hand** in the ticket; whether a closed ticket's plan **held** is **measured** against the "
        "claims and imports on the ref read. An open ticket's plan is drawn as planned and not checked. In the "
        "diagrams `+` marks a path added to a component, `→` a path moved into it, a dashed box a component the "
        "plan declares, and a dashed arrow an import the plan drops. `absorbs` is listed, never checked.",
        "",
    ]
    data = pages.available(documents, "work")
    if data is None:
        return lines + pages.notices(documents, ("work",))
    if "plans" not in data:
        return lines + ["> This `work.json` predates planned changes (no `plans` key), so none were measured.", ""]
    plans = [p for p in data["plans"] if isinstance(p, Mapping)]
    if not plans:
        return lines + ["No ticket carries an `architecture` block yet.", ""]
    reads = ((data.get("inputs") or {}).get("architecture") or {}).get("repos") or {}
    for plan in plans:
        lines += [f"### {pages._link(plan.get('ticket'), plan.get('url'))} {pages.escape(str(plan.get('title') or ''))} ({pages.escape(str(plan.get('state')))})", ""]
        body = plan.get("plan") or {}
        if "invalid" in body:
            lines += [f"**Invalid plan**, not drawn or checked: {pages._code(body['invalid'])}", ""]
            continue
        lines += [_cell(_plan_dot(plan)), *_plan_items(plan)]
        if body.get("absorbs"):
            lines += ["Absorbs (drawn here, not checked): " + "; ".join(pages._code(a) for a in body["absorbs"]), ""]
        for repo in dict.fromkeys(str(c.get("repo")) for c in plan.get("checks") or []):
            unmet = [c for c in plan.get("checks") or [] if c.get("held") is False and str(c.get("repo")) == repo]
            if unmet:
                n = len(unmet)
                read = reads.get(repo) or {}
                lines += [
                    f"> **Warning**: {pages._figure(n)} item{'s' if n != 1 else ''} of this closed ticket "
                    f"{'are' if n != 1 else 'is'} not held on the ref read ({repo} {pages._code(read.get('ref'))}, "
                    f"{pages._code(str(read.get('commit'))[:12])}). The ticket may have closed on an epic's "
                    "integration branch whose pull request has not merged to that ref yet.",
                    "",
                ]
    return lines


def _plan_items(plan: Mapping[str, Any]) -> list[str]:
    body = plan["plan"]
    if plan.get("state") != "closed":
        lines = ["**Planned**: not checked until the ticket closes.", ""]
        for a in body.get("adds") or []:
            lines += [f"- added {', '.join(pages._code(p) for p in a['paths'])} to {pages._code(a['component'])}"]
        for m in body.get("moves") or []:
            lines += [f"- moved {', '.join(pages._code(p) for p in m['paths'])} to {pages._code(m['to'])}"]
        for d in body.get("drops") or []:
            lines += [f"- drop the import from {pages._code(d['from'])} into {pages._code(d['to'])}"]
        return lines + [""]
    lines = []
    for c in plan.get("checks") or []:
        what = (
            f"drop the import from {pages._code(c['from'])} into {pages._code(c['to'])}" if c["kind"] == "drops"
            else f"{ACTION[c['kind']]} {pages._code(c['path'])} to {pages._code(c['component'])}"
        )
        lines.append(f"- **{VERDICT[c.get('held')]}** — {what}: {pages._code(c.get('why'))}")
    return lines + [""]


def _dq(text: Any) -> str:
    """A string for a quoted DOT identifier or attribute: `\\` and `"` escaped, so it cannot end the string."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _plan_dot(plan: Mapping[str, Any]) -> str:
    body = plan["plan"]
    added: dict[str, list[str]] = defaultdict(list)
    moved: dict[str, list[str]] = defaultdict(list)
    for a in body.get("adds") or []:
        added[a["component"]] += a["paths"]
    for m in body.get("moves") or []:
        moved[m["to"]] += m["paths"]
    lines = ["digraph plan {", HEAD, "rankdir=LR;"]
    for c in plan.get("components") or []:
        rows = [f'<FONT POINT-SIZE="12"><B>{_esc(c["name"])}</B></FONT>']
        if c.get("new"):
            rows.append('<FONT POINT-SIZE="9">new</FONT>')
        rows += [f'<FONT POINT-SIZE="9">+ {_esc(p)}</FONT>' for p in added.get(c["id"], [])]
        rows += [f'<FONT POINT-SIZE="9">→ {_esc(p)}</FONT>' for p in moved.get(c["id"], [])]
        style = ' style="rounded,filled,dashed" fillcolor="#e8f5e9"' if c.get("new") else ""
        lines.append(f'"{_dq(c["id"])}" [label=<{"<BR/>".join(rows)}>{style}];')
    for d in body.get("drops") or []:
        lines.append(f'"{_dq(d["from"])}" -> "{_dq(d["to"])}" [style=dashed color="{UPWARD}" fontcolor="{UPWARD}" label="dropped"];')
    lines.append("}")
    return "\n".join(lines)


# Text parts
# ---------------------------------------------------------------------------


def _hand_and_measured(*, hand: str, measured: str, where: str = "Each is in a repository's `docs/architecture/components.yaml`.") -> list[str]:
    return [
        f"> **Written by hand:** {hand}. {where}",
        ">",
        f"> **Measured:** {measured}. Nothing measured is written by hand, so it cannot drift from the code.",
        "",
    ]


def _repos(data: Document) -> dict[str, Mapping[str, Any]]:
    """`architecture.json`'s repositories, in `system.yaml`'s order."""
    return {str(name): r for name, r in (data.get("repos") or {}).items() if isinstance(r, Mapping)}


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


def _read_notice(data: Document) -> list[str]:
    """Which commit of each repository was read, and every repository that could not be, or has no model."""
    repos = _repos(data)
    read = [f"{pages.escape(name)} {pages._code(r.get('ref'))} at {pages._code(str(r.get('commit'))[:12])} "
            f"(committed {pages._cell(r.get('committed'))})" for name, r in repos.items() if r.get("model")]
    lines = [f"Read from {', '.join(read) or 'no repository with a model'}.", ""]
    for name, r in repos.items():
        refresh = r.get("refresh")
        if isinstance(refresh, Mapping) and refresh.get("ok") is False:
            lines += [
                f"> **The {pages.escape(name)} refresh failed**: {pages._cell(refresh.get('error'))}. "
                f"This is the {pages._code(r.get('ref'))} its clone already had ({pages._code(str(r.get('commit'))[:12])}), "
                "so it may be behind.",
                "",
            ]
    for name, r in repos.items():
        if r.get("error"):
            lines += [f"> **{pages.escape(name)} could not be read**: {pages._cell(r['error'])}. It is drawn as its "
                      "containers only.", ""]
    missing = [name for name, r in repos.items() if r.get("model") is False]
    if missing:
        lines += [
            f"> **{len(missing)} {'repository has' if len(missing) == 1 else 'repositories have'} no architecture model "
            f"yet**: {', '.join(pages.escape(n) for n in missing)}. Their components, layers and imports are unknown, "
            "not none, and each is drawn as its containers only.",
            "",
        ]
    return lines


def _size(component: Mapping[str, Any]) -> str:
    if component.get("files"):
        return f"{component['files']:,} files, {component['lines']:,} lines"
    return f"{component.get('tracked', 0):,} tracked files"


def _adrs_for(data: Document, ids: set[str]) -> list[Mapping[str, Any]]:
    return [a for a in data.get("adrs") or [] if ids & set(a["components"])]


def _adr_link(adr: Mapping[str, Any], members: list[Mapping[str, Any]], data: Document | None = None) -> str:
    """An ADR as a link, with how it was placed on `members` (code it cites, or a name in its title), and what it cites."""
    note = "" if adr.get("status") in (None, "current") else f" _{adr['status']}_"
    via = sorted({adr["components"][c["id"]] for c in members if c["id"] in adr["components"]})
    return (f"[{pages.escape(str(adr['title']))}]({adr['url']}) ({adr['repo']}; placed by {' and '.join(via)}){note}"
            f"{_cites(data or {}, adr)}")


def cited_adrs(data: Document, adr: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """`(text, url)` of each ADR another repository's ADR cites (`<repo> ADR NNNN`); `url` is `None` when it was not collected."""
    urls = {(str(a.get("repo")), str(a.get("number"))): a.get("url") for a in data.get("adrs") or [] if isinstance(a, Mapping)}
    return [(f"{c['repo']} ADR {c['number']}", urls.get((str(c["repo"]), str(c["number"]))))
            for c in adr.get("cites") or [] if isinstance(c, Mapping)]


def _cites(data: Document, adr: Mapping[str, Any]) -> str:
    found = cited_adrs(data, adr)
    if not found:
        return ""
    return "; cites " + ", ".join(pages._link(text, url) if url else pages.escape(text) for text, url in found)


def _as_of(data: Document) -> str:
    read = [f"{pages.escape(name)} at {pages._code(r.get('ref'))} ({pages._code(str(r.get('commit'))[:12])})"
            for name, r in _repos(data).items() if r.get("model")]
    return f"Read from {', '.join(read) or 'no repository with a model'}; collected {pages._cell(data.get('collected_at'))}."


def _seam(summary: Mapping[str, Any]) -> str:
    """The seam's import count, and the component pairs when its target's model says which they are (#421).

    The count is measured from the names, so it stands without opengwasdb's
    model; the pairs are resolved through opengwasdb's claims, and an unknown
    number of them is said to be unknown, never 0.
    """
    source, target = architecture_graph.SEAM
    if summary.get("registry_to_engine_imports") is None:
        return f"The imports from {source} into {target} are unknown: {source} has no model at the ref read."
    imports = f"{pages._figure(summary.get('registry_to_engine_imports'))} imports from {source} into {target}"
    pairs = summary.get("registry_to_engine_edges")
    if pairs is None:
        return imports + f"; the component pairs cannot be drawn until {target}'s model is at the ref read."
    return imports + f", across {pages._figure(pairs)} component pairs."


def _baseline(baseline: Any) -> list[str]:
    """The engine-import baseline's size, and what opengwasdb-stores makes, as one line (#421).

    The size is the committed file's entry count, which the collector read from
    opengwasdb-stores; a file that is not there is unknown, never zero.
    """
    if not isinstance(baseline, Mapping):
        return []
    source = baseline.get("from") or architecture_graph.SEAM[0]
    entries, measured = baseline.get("entries"), baseline.get("measured")
    if not isinstance(entries, int) or isinstance(entries, bool):
        return [
            f"**The engine-import baseline is unknown**: {pages._cell(baseline.get('note'))}. "
            f"{source} makes {pages._figure(measured)} imports of engine modules.",
            "",
        ]
    return [
        f"**The engine-import baseline** ({pages._code(baseline.get('path'))}, in {source}) lists "
        f"{pages._figure(entries)} imports of engine modules, one per importing file and imported name; "
        f"{source} makes {pages._figure(measured)} of them.",
        "",
    ]


def _system_gap_lines(found: Mapping[str, Any]) -> list[str]:
    """One repository's system gaps (#8) as list items, each followed by a blank line."""
    lines = [f"- {sentence[0].upper()}{sentence[1:]}" for sentence in model_rules.describe_system_gaps(found, pages._code)]
    return lines + [""] if lines else []


def _health(
    data: Document, components: list, edges: list, summary: Mapping[str, Any], panel: architecture_panel.Panel
) -> list[str]:
    lines = ["## Health", "", "### Claims", ""]
    gaps = data.get("gaps") or {}
    model = data.get("model") or {}
    for name, repo in _repos(data).items():
        label = pages.escape(repo_label(model, name))
        found = gaps.get(name) or {}
        if repo.get("planned"):
            lines += [f"- **{label}**: planned, not created yet.", ""]
            continue
        if repo.get("private"):
            lines += [f"- **{label}**: private, so drawn as its container only.", ""]
            continue
        if found.get("unreadable") or repo.get("error"):
            lines += [f"- **{label}**: could not be read: {pages._cell(found.get('unreadable') or repo.get('error'))}.", ""]
            continue
        if not repo.get("model"):
            why = found.get("no_model") or repo.get("note")
            lines += [f"- **{label}**: no model, so its components are unknown: {pages._cell(why)}.", ""]
            continue
        unclaimed, stale = found.get("unclaimed") or [], found.get("stale") or []
        lines.append(f"- **{label}**: {len(unclaimed)} code files no component claims; {len(stale)} claims that match no tracked file.")
        lines += [f"  - Unclaimed: {pages._code(path)}" for path in unclaimed]
        lines += [f"  - Stale: {pages._code(c['path'])} (claimed by {pages._code(c['component'])})" for c in stale]
        lines += [f"  {line}" for line in _system_gap_lines(found) if line]
        lines.append("")
    by_id = {c["id"]: c for c in components}
    layers = model.get("layers") if isinstance(model.get("layers"), Mapping) else {}
    lines += ["### Layering", ""]
    if not layers:
        lines += [
            "The layering cannot be measured until a model that declares layers is at the ref read: a component "
            "without a layer has no upward for an import to cross, so there is no figure to give.",
            "",
        ]
    for name in layers:
        mine = [e for e in edges if e.get("scope") == "within" and e.get("repo") == name]
        upward = [e for e in mine if e.get("upward")]
        lines.append(
            f"{pages.escape(repo_label(model, name))}: {len(upward)} edges ({sum(e['imports'] for e in upward)} imports) "
            f"go against the layering, of {len(mine)} edges between its components."
        )
        lines.append("")
        if upward:
            lines += ["| From | To | Imports |", "|---|---|---:|"]
            for e in sorted(upward, key=lambda e: -e["imports"]):
                a, b = by_id[e["from"]], by_id[e["to"]]
                lines.append(f"| {panel.link(a['name'], a['id'])} (layer {a['layer']}) | {panel.link(b['name'], b['id'])} (layer {b['layer']}) | {e['imports']} |")
            lines.append("")
    lines += ["### Imports across repositories", ""]
    lines.append(_seam(summary))
    lines.append("")
    lines += _baseline(data.get("baseline"))
    pairs: dict[tuple[str, str], list[int]] = defaultdict(list)
    for e in edges:
        if e.get("scope") == "across":
            pairs[(str(e.get("from_repo")), str(e.get("to_repo")))].append(e["imports"])
    if pairs:
        lines += ["| From | Into | Imports | Component pairs |", "|---|---|---:|---:|"]
        for (a, b), counts in sorted(pairs.items()):
            lines.append(f"| {pages.escape(a)} | {pages.escape(b)} | {sum(counts)} | {len(counts)} |")
        lines.append("")
    lines += ["### ADRs", ""]
    lines.append(f"{summary.get('adrs_placed', 0)} of {summary.get('adrs_total', 0)} ADRs are placed on a component.")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Diagrams: Graphviz source for Quarto's {dot} cells
# ---------------------------------------------------------------------------


def _cell(source: str) -> str:
    return f"```{{dot}}\n//| fig-width: 9\n{source}\n```\n"


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _label(name: str, tech: str | None, summary: str | None, width: int = 30) -> str:
    rows = [f'<FONT POINT-SIZE="12"><B>{_esc(name)}</B></FONT>']
    if tech:
        rows.append(f'<FONT POINT-SIZE="9">[{_esc(tech)}]</FONT>')
    if summary:
        rows.extend(f'<FONT POINT-SIZE="9">{_esc(line)}</FONT>' for line in textwrap.wrap(summary, width)[:4])
    return "<" + "<BR/>".join(rows) + ">"


def _context(model: Mapping[str, Any]) -> str:
    inside = {c["id"] for c in model.get("containers") or []}
    system = model.get("system") or {}
    lines = ["digraph context {", HEAD, "rankdir=TB;"]
    for p in model.get("people") or []:
        lines.append(f'"{_dq(p["id"])}" [label={_label(p["name"], "Person", p.get("summary"))} fillcolor="#dbe9f7"];')
    lines.append(f'"system" [label={_label(system.get("name", "System"), "Software system", system.get("summary"), 36)} fillcolor="#c5dcf2"];')
    for x in model.get("external") or []:
        lines.append(f'"{_dq(x["id"])}" [label={_label(x["name"], "External system", x.get("summary"))} fillcolor="#eeeeee"];')
    seen = set()
    for a, b, text in model.get("container_relations") or []:
        a, b = ("system" if a in inside else a), ("system" if b in inside else b)
        if a != b and (a, b) not in seen:
            seen.add((a, b))
            lines.append(f'"{_dq(a)}" -> "{_dq(b)}" [label="{_dq(text)}"];')
    lines.append("}")
    return "\n".join(lines)


def _container_key() -> str:
    return ("A dashed box is a container whose repository is **planned** (not created yet); a grey one is a "
            "**private** repository's, drawn as its container only; a cylinder is data.")


def _containers(model: Mapping[str, Any], repos: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    system = model.get("system") or {}
    repos = repos or {}
    lines = ["digraph containers {", HEAD, "rankdir=TB; compound=true;"]
    for p in model.get("people") or []:
        lines.append(f'"{_dq(p["id"])}" [label={_label(p["name"], "Person", None)} fillcolor="#dbe9f7"];')
    lines.append(f'subgraph cluster_system {{ label="{_dq(system.get("name", "System"))}"; fontname="Arial"; fontsize=11; margin=16; color="{GREY}";')
    for c in model.get("containers") or []:
        repo = repos.get(str(c.get("repo"))) or {}
        tech = c.get("tech")
        if c.get("repo") is None:
            style = ' shape=cylinder style="filled" fillcolor="#c5dcf2"'
        elif repo.get("planned"):
            style, tech = ' style="rounded,filled,dashed" fillcolor="#ffffff"', f"planned; {tech}" if tech else "planned"
        elif repo.get("private"):
            style, tech = ' fillcolor="#e5e5e5"', f"private; {tech}" if tech else "private"
        else:
            style = ' fillcolor="#c5dcf2"'
        lines.append(f'"{_dq(c["id"])}" [{style.strip()} label={_label(c["name"], tech, c.get("summary"), 28)}];')
    lines.append("}")
    for x in model.get("external") or []:
        lines.append(f'"{_dq(x["id"])}" [label={_label(x["name"], "External", None)} fillcolor="#eeeeee"];')
    for a, b, text in model.get("container_relations") or []:
        lines.append(f'"{_dq(a)}" -> "{_dq(b)}" [label="{_dq(textwrap.fill(text, 22))}"];')
    lines.append("}")
    return "\n".join(lines)


def _node(component: Mapping[str, Any]) -> str:
    """A component's box, which links to its panel (#435) when its id can be an address."""
    sub = _size(component)
    cid = component["id"]
    link = ""
    if architecture_panel.linkable(cid):
        link = (f' URL="#{architecture_panel.ANCHOR}{cid}" tooltip="{_dq(component["name"])}: open its details"'
                f' class="arch-node arch-c-{cid}"')
    return (
        f'"{_dq(cid)}" [label=<<FONT POINT-SIZE="12"><B>{_esc(component["name"])}</B></FONT><BR/>'
        f'<FONT POINT-SIZE="9">{_esc(sub)}</FONT>>{link}];'
    )


def _panel(documents: Mapping[str, Document | None]) -> architecture_panel.Panel:
    return architecture_panel.Panel(documents, states=STATE_MEANING, size=_size)


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
        reached = {e["to"] for e in edges if e.get("scope") == "across" and e.get("from_repo") == name and e.get("to_repo") == target}
        summary = (f"{len(reached)} of {len(theirs)} components" if (repos.get(target) or {}).get("model")
                   else "no architecture model yet")
        node = f"repo:{target}"
        lines.append(f'"{_dq(node)}" [fillcolor="#eeeeee" label=' + _label(repo_label(model, target), "imported directly", summary, 28) + "];")
        for source, n in sorted(sources.items()):
            lines.append(f'"{_dq(source)}" -> "{_dq(node)}" [label="{n}" penwidth={0.6 + min(n, 30) / 30:.2f}];')
    return lines


def _layered(name: str, components: list, edges: list, layers: list, repos: Mapping[str, Mapping[str, Any]],
             model: Mapping[str, Any]) -> str:
    """Repository `name`'s components, one row per layer, with the imports that go against the layering."""
    engine = [c for c in components if c["repo"] == name]
    by_id = {c["id"]: c for c in engine}
    lines = [f"digraph {_dq(name).replace('-', '_')} {{", HEAD, "rankdir=TB; newrank=true; ranksep=0.45;"]
    for layer in layers:
        lines.append(
            f'"L{layer["layer"]}" [shape=plaintext style="" fontcolor="{GREY}" '
            f'label=<<FONT POINT-SIZE="10">{layer["layer"]} · {_esc(str(layer["name"]).upper())}</FONT>>];'
        )
    for upper, lower in pairwise(layers):
        lines.append(f'"L{upper["layer"]}" -> "L{lower["layer"]}" [style=invis];')
    for layer in layers:
        members = [c["id"] for c in engine if c["layer"] == layer["layer"]]
        lines.append("{ rank=same; " + f'"L{layer["layer"]}"; ' + "".join(f'"{_dq(i)}"; ' for i in members) + "}")
    lines += [_node(c) for c in engine]
    # An invisible spine from each layer to the next keeps the rows in order.
    for upper, lower in pairwise(layers):
        top = next((c["id"] for c in engine if c["layer"] == upper["layer"]), None)
        bottom = next((c["id"] for c in engine if c["layer"] == lower["layer"]), None)
        if top and bottom:
            lines.append(f'"{_dq(top)}" -> "{_dq(bottom)}" [style=invis weight=0];')
    for e in edges:
        if e.get("scope") != "within" or e["from"] not in by_id or e["to"] not in by_id:
            continue
        a, b, n = by_id[e["from"]], by_id[e["to"]], e["imports"]
        if e.get("upward"):
            lines.append(
                f'"{_dq(e["from"])}" -> "{_dq(e["to"])}" [color="{UPWARD}" fontcolor="{UPWARD}" penwidth=1.4 constraint=false '
                f'label=" {n}" tooltip="{_dq(a["name"])} imports {_dq(b["name"])}, a higher layer ({n})"];'
            )
        elif a["layer"] == b["layer"]:
            lines.append(f'"{_dq(e["from"])}" -> "{_dq(e["to"])}" [style=dashed constraint=false label=" {n}"];')
    lines += _across(name, components, edges, by_id, model, repos)
    lines.append("}")
    return "\n".join(lines)


def _by_container(name: str, components: list, edges: list, model: Mapping[str, Any],
                  repos: Mapping[str, Mapping[str, Any]]) -> str:
    """Repository `name`'s components by container, the imports between them, and the imports they make of other repositories."""
    mine = [c for c in components if c["repo"] == name]
    containers = {c["id"]: c for c in model.get("containers") or []}
    by_container: dict[str, list[str]] = defaultdict(list)
    for c in mine:
        by_container[c["container"]].append(c["id"])
    by_id = {c["id"]: c for c in mine}
    lines = [f"digraph {_dq(name).replace('-', '_')} {{", HEAD, "rankdir=TB; newrank=true;"]
    for container, ids in by_container.items():
        label = containers.get(container, {}).get("name", container)
        lines.append(f'subgraph "cluster_{_dq(container)}" {{ label="{_dq(label)}"; fontname="Arial"; fontsize=11; margin=12; color="{GREY}";')
        lines += [_node(by_id[i]) for i in ids]
        lines.append("}")
    for e in edges:
        if e.get("scope") == "within" and e["from"] in by_id and e["to"] in by_id:
            lines.append(f'"{_dq(e["from"])}" -> "{_dq(e["to"])}";')
    lines += _across(name, components, edges, by_id, model, repos)
    lines.append("}")
    return "\n".join(lines)
