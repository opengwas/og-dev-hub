"""The architecture of every repository `system.yaml` lists, drawn from their claims (#418, #421, og-dev-hub#9).

Each repository may keep a hand-written `docs/architecture/components.yaml`
whose components claim code paths (`architecture_model` holds the one ownership
rule, and derives which files are code from the claims). This collector reads
every repository og-dev-hub's `system.yaml` lists, through git and one read
handle each (`staging.Repositories`), without a checkout of any:

- a repository with `visibility: null` is planned: it is listed, never cloned;
- each other one is read at `main` of the site's bare clone (or the checkout
  `--registry` names, for opengwasdb-stores, at `HEAD`), tracked files only;
- a clone or fetch that fails is that repository's gap, with git's message, and
  the rest is still collected;
- a repository without a model file is a gap too: its components are unknown,
  never zero.

It reports the components of every repository with a model, with their
measured size, the files nobody claims and the claims that match nothing (gaps,
reported never raised), the commit read in each repository, the import graph
within and across them, every ADR, and the baseline of opengwasdb-stores'
imports of engine modules (#421). The site's *docs* mirror stays at the
opengwasdb revision `pixi.lock` pins; the map shows current work, so this reads
`main`.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

from project_site import architecture_public, paths, staging
from project_site.staging import Tree
from project_site.collect import architecture_adrs, architecture_graph, architecture_model as model_rules
from project_site.collect.common import CollectError

MODEL_PATH = "docs/architecture/components.yaml"


def collect(
    repositories: staging.Repositories | None = None,
    *,
    system_file: Path | None = None,
) -> dict[str, Any]:
    """Every listed repository's components, gaps, import graph and ADRs, as the site's `architecture` source.

    `repositories` is the run's read handles (`staging.Repositories`; by default
    each repository's clone at `main`, unfetched); `system_file` the hub's
    `system.yaml` (by default the one in this checkout's working tree).
    """
    system = model_rules.read_system(system_file)
    repositories = repositories or staging.Repositories()
    container_ids = {str(c["id"]) for c in system["containers"]}

    repos: dict[str, dict[str, Any]] = {}
    trees: dict[str, Tree] = {}
    models: dict[str, dict[str, Any]] = {}
    gaps: dict[str, dict[str, Any]] = {}
    for entry in system.get("repos") or []:
        name = entry["name"]
        record: dict[str, Any] = {
            "name": name, "visibility": entry.get("visibility"), "status": entry.get("status"),
            "planned": entry.get("visibility") is None, "url": paths.clone_url(name),
            "ref": None, "commit": None, "committed": None, "refresh": None, "source_root": None,
            "model": None, "note": None, "error": None,
        }
        repos[name] = record
        if record["planned"]:
            continue  # not created yet: drawn as planned, never cloned
        handle = repositories.get(name)
        record["refresh"] = handle.fetch
        tree = None
        if handle.readable:
            try:
                tree = handle.tree()
            except CollectError as error:
                record["error"] = f"{name} cannot be read at {handle.ref}: {error}"
        else:
            record["error"] = handle.error
        if tree is None:
            gaps[name] = _gap(unreadable=record["error"])
            continue
        trees[name] = tree
        record |= {"ref": handle.ref, "commit": tree.commit, "committed": tree.committed,
                   "source_root": architecture_graph.source_root(tree.files)}
        text = tree.read([MODEL_PATH]).get(MODEL_PATH)
        model, why = None, f"{MODEL_PATH} is not in {name} at {handle.ref} ({tree.commit[:12]})"
        if text is not None:
            try:
                model, why = model_rules.load_model(text), None
            except ValueError as error:
                why = f"{MODEL_PATH} of {name} at {handle.ref} ({tree.commit[:12]}) cannot be used: {error}"
        record |= {"model": model is not None, "note": why}
        if model is None:
            gaps[name] = _gap(no_model=why)
        else:
            models[name] = model

    private = architecture_public.visibility({str(e["name"]): e.get("visibility") for e in system.get("repos") or []})
    components, refused = _components(models, private)
    for name, why in refused.items():
        # A component id another model already has: this repository's components are unknown, the rest stand.
        del models[name]
        repos[name] |= {"model": False, "note": why}
        gaps[name] = _gap(no_model=why)
    claims = model_rules.claims_by_repository(components, {repo: {"model": True} for repo in models})
    is_code = {repo: model_rules.code_rule(claims[repo]) for repo in models}
    for repo in models:
        gaps[repo] = _gap() | model_rules.check_claims(claims[repo], trees[repo].files, is_code[repo]) | _system_gaps(
            repo, models[repo], components, container_ids)
    _measure(components, trees, claims, is_code)

    # One measurement of the imports, for both the graph's counts and the
    # baseline opengwasdb-stores is held to (#421): they can never disagree.
    modelled = {repo: trees[repo] for repo in models}
    imports = architecture_graph.imports_of(modelled, claims)
    edges = architecture_graph.import_edges(modelled, claims, components, imports)
    found = architecture_graph.engine_imports(imports)
    layers = {repo: list(model.get("layers") or []) for repo, model in models.items() if model.get("layers")}
    seam_from, seam_to = architecture_graph.SEAM
    # The seam's import count is the name-based measurement the baseline holds, so it
    # stands without opengwasdb's model; its component pairs are resolved through
    # opengwasdb's claims, so without that model they are unknown, never 0 (#421 review).
    # The layering is measured only where a model declares layers; with none, unknown.
    summary = architecture_graph.summarise(edges) | {
        "registry_to_engine_imports": len(found) if seam_from in models else None,
    }
    if seam_to not in models or seam_from not in models:
        summary["registry_to_engine_edges"] = None
    if not layers:
        summary |= {"upward_edges": None, "upward_imports": None}
    baseline_path = architecture_graph.BASELINE_PATH
    baseline_text = trees[seam_from].read([baseline_path]).get(baseline_path) if seam_from in trees else None
    baseline = architecture_graph.load_baseline(baseline_text) if baseline_text is not None else None
    names = [entry["name"] for entry in system.get("repos") or []]
    adrs = architecture_adrs.place(trees, claims, components, architecture_graph.modules_of(trees), names)
    return {
        "repos": repos,
        "baseline": {
            "path": baseline_path,
            "from": seam_from,
            "entries": len(baseline) if baseline is not None else None,
            "measured": len(found) if seam_from in models else None,
            "note": None if baseline is not None else (
                f"{baseline_path} is not in {seam_from} at {repos[seam_from]['ref']} ({str(repos[seam_from]['commit'])[:12]})"
                if seam_from in trees else f"{seam_from} was not read"
            ),
        },
        "model": {
            key: system[key] for key in model_rules.SYSTEM_SECTIONS if key != "system"
        } | {
            # Each stage names the repository whose model holds it, so a private one's can be left out (og-dev-hub#9).
            "stages": [{**stage, "repo": repo} for repo, model in models.items() for stage in model.get("stages") or []],
            "system": system["system"],
            "layers": layers,
        },
        "components": components,
        # Every tracked code file of each repository with a model (#422), so a plan's `adds` can be
        # told to exist; unknown (`null`) where there is no model to say what is code.
        "files": {
            repo: sorted(f for f in trees[repo].files if is_code[repo](f)) if repo in models else None
            for repo in repos if not repos[repo]["planned"]
        },
        "gaps": gaps,
        "edges": edges,
        # Unknown where no model declares layers, like `summary.upward_imports`: never an empty list.
        "upward_imports": architecture_graph.upward_imports(imports, components) if layers else None,
        "adrs": adrs,
        "summary": summary
        | {"adrs_total": len(adrs), "adrs_placed": sum(1 for a in adrs if a["components"])},
    }


def _gap(*, unreadable: str | None = None, no_model: str | None = None) -> dict[str, Any]:
    """One repository's gaps: why it could not be read, or why it has no model, and then nothing is judged.

    `unclaimed` and `stale` are `None` (unknown, never empty) until a model is read.
    """
    return {"unreadable": unreadable, "no_model": no_model, "unclaimed": None, "stale": None,
            "containers": [], "system_sections": []}


def _system_gaps(
    repo: str, model: Mapping[str, Any] | None, components: list[dict[str, Any]], container_ids: set[str]
) -> dict[str, Any]:
    """What a components file says about the system that `system.yaml` does not back (#8).

    `system_sections`: system keys it still holds, ignored (they belong to og-dev-hub's
    `system.yaml`). `containers`: components naming a container `system.yaml` lacks.
    """
    return {
        "containers": [
            {"component": c["id"], "container": c["container"]}
            for c in components
            if c["repo"] == repo and c["container"] not in container_ids
        ],
        "system_sections": [key for key in model_rules.SYSTEM_SECTIONS if key in (model or {})],
    }


def _components(
    models: Mapping[str, Mapping[str, Any]], private: Callable[[Any], bool] = lambda repo: False,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Each modelled repository's components, in `system.yaml`'s order, each tagged with its repository.

    A component id is one panel's address, so it is unique across the models. A
    repository whose model repeats an id an earlier repository's has is refused
    whole, `{repository: why}`, and never stops the others (og-dev-hub ADR 0001).
    The reason is public, so it never names a `private` repository: that one is
    "another repository".
    """
    components: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    refused: dict[str, str] = {}
    for repo, source in models.items():
        raws = source.get("components") or []
        clash = next((raw["id"] for raw in raws if raw["id"] in seen), None)
        if clash is not None:
            first = "another repository" if private(seen[clash]) else seen[clash]
            refused[repo] = (f"component id {clash!r} of {repo}'s model is also {first}'s, "
                             f"so {repo}'s components are unknown")
            continue
        for raw in raws:
            seen[raw["id"]] = repo
            components.append(
                {
                    "id": raw["id"],
                    "name": raw["name"],
                    "repo": repo,
                    "container": raw.get("container"),
                    "layer": raw.get("layer"),
                    "stages": list(raw.get("stages") or []),
                    "summary": raw.get("summary") or "",
                    "paths": list(raw.get("paths") or []),
                    "files": 0,
                    "lines": 0,
                    "tracked": 0,
                }
            )
    return components, refused


def _measure(components: list[dict[str, Any]], trees: Mapping[str, Tree], claims: Mapping[str, Any], is_code: Mapping[str, Any]) -> None:
    """Code files, their lines, and every tracked file each component owns."""
    by_id = {c["id"]: c for c in components}
    for repo in claims:
        tree = trees[repo]
        code = [f for f in tree.files if is_code[repo](f)]
        text = tree.read(code)
        for path in tree.files:
            cid = model_rules.owner(claims[repo], path)
            if cid:
                by_id[cid]["tracked"] += 1
        for path in code:
            cid = model_rules.owner(claims[repo], path)
            if cid:
                by_id[cid]["files"] += 1
                if path not in text:
                    raise CollectError(f"{path} is a code file of {repo} but git could not read it")
                by_id[cid]["lines"] += len(text[path].splitlines())
