"""The import graph between components, within and across the repositories read (#418, #421, og-dev-hub#9).

The edges are not written in any model: they are read from the code. Every
tracked Python module a component claims is parsed, and each import that lands
in another component's module is one import of that edge. An import is counted
per (file, imported name), so one file importing three names of another
component is three imports.

An edge is `within` one repository, or `across` two, and then it records
`from_repo` and `to_repo`. An import within a repository is `upward` when it
goes to a component on a higher layer than the importing one (the model that
declares the layers lists them, top to bottom); the same layer and lower layers
are not.

One seam across repositories is held to a baseline (#421): opengwasdb-stores'
imports of opengwasdb (`SEAM`). `imports_of` yields every import once,
`import_edges` counts them between components, and `engine_imports` keeps the
ones that reach the engine. One pass over the sources, so the page's seam counts
and the baseline cannot disagree about what an import is.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any, Mapping, Sequence

import yaml

from project_site.collect import architecture_model as model_rules
from project_site.collect.common import CollectError

Edge = dict[str, Any]

#: The one seam between repositories held to a baseline (#421): `(from, to)` by repository name,
#: and the package whose names are the engine's. The name alone decides an engine import, so the
#: baseline needs no engine checkout and no engine model.
SEAM = ("opengwasdb-stores", "opengwasdb")
SEAM_PACKAGE = "opengwasdb"
SOURCE_ROOT = "src/"


def source_root(files: Sequence[str]) -> str:
    """Where a repository's modules are named from: `src/` when it has one, else its root."""
    return SOURCE_ROOT if any(path.startswith(SOURCE_ROOT) for path in files) else ""


def module_name(path: str, root: str = "") -> str | None:
    """The dotted module a Python file is, from the source root: `opengwasdb/a/b.py` -> `opengwasdb.a.b`, `src/x/y.py` -> `x.y`."""
    if not path.endswith(".py") or not path.startswith(root):
        return None
    relative = path[len(root):]
    return relative[: -len(".py")].replace("/", ".").removesuffix(".__init__")


def imported_names(source: str, module: str, is_package: bool, path: str = "?") -> set[str]:
    """Every absolute name a module imports; relative imports are resolved against `module`.

    A file that does not parse is an error naming it: dropping its imports would
    leave the graph looking complete.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise CollectError(f"{path} does not parse: {error}") from error
    package = module if is_package else module.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join([*parts, base] if base else parts)
            names.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return names


def modules_of(trees: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Repository -> dotted module -> file, for every tracked Python file of each tree."""
    found: dict[str, dict[str, str]] = {}
    for repo, tree in trees.items():
        root = source_root(tree.files)
        found[repo] = {module: path for path in tree.files if (module := module_name(path, root))}
    return found


def resolve(name: str, home: str, modules: Mapping[str, Mapping[str, Any]]) -> tuple[str, Any] | None:
    """`(repository, value)` of the module a dotted `name` lands in, looking in `home` first.

    Trailing segments are dropped until a module answers, so `a.b.c` (a name
    imported from module `a.b`) lands in `a.b`. The importing repository is
    searched whole before any other, as Python finds its own package first: two
    repositories may hold a module of the same name.
    """
    for repo in (home, *[r for r in modules if r != home]):
        known = modules.get(repo) or {}
        parts = name.split(".")
        while parts:
            if ".".join(parts) in known:
                return repo, known[".".join(parts)]
            parts.pop()
    return None


def imports_of(
    trees: Mapping[str, Any], claims: Mapping[str, Sequence[tuple[str, str]]]
) -> list[dict[str, Any]]:
    """Every import a claimed file of any tree makes, one record per (file, imported name).

    `trees` and `claims` are keyed by repository name. `component` is the
    importing file's owner; `target` is the component the name resolves to (and
    `target_repo` its repository), or `None` for a name no tracked module answers
    to. An unclaimed file is not a source here: it is a gap the ownership check
    fails on, so its imports are reported there rather than hidden in a graph.
    """
    # Every tracked module resolves to its own owner or to none: an unclaimed
    # module is a gap, and must not inherit the owner of the package around it.
    everything = modules_of(trees)
    module_owner = {
        repo: {module: model_rules.owner(claims.get(repo) or [], path) for module, path in found.items()}
        for repo, found in everything.items()
    }
    records: list[dict[str, Any]] = []
    for repo, tree in trees.items():
        mine = claims.get(repo) or []
        sources = [(path, module) for module, path in everything[repo].items() if module_owner[repo][module]]
        # A claimed script (`tools/`, `workflow/`) is not importable, but it imports:
        # it is a source of edges, never a target.
        importable = {path for path, _ in sources}
        sources += [(path, "") for path in tree.files
                    if path.endswith(".py") and path not in importable and model_rules.owner(mine, path)]
        text = tree.read([path for path, _ in sources])
        for path, module in sources:
            source = model_rules.owner(mine, path)
            for name in imported_names(text.get(path, ""), module, path.endswith("__init__.py"), path):
                found = resolve(name, repo, module_owner)
                records.append({
                    "repo": repo, "file": path, "component": source, "name": name,
                    "target": found[1] if found else None, "target_repo": found[0] if found and found[1] else None,
                })
    return records


def is_engine_name(name: str) -> bool:
    """Whether an imported name is one of the engine's: its package, or a module or name under it.

    The rule needs no engine checkout and no engine model, which is what lets
    this repository's own CI hold its engine imports to a baseline on its own.
    `opengwasdbx` is a different package, not the engine's.
    """
    return name == SEAM_PACKAGE or name.startswith(f"{SEAM_PACKAGE}.")


def engine_imports(imports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """opengwasdb-stores' imports of engine names (`SEAM`), sorted by (file, name), one entry per pair.

    `engine_component` is the engine component the name resolves to, and is
    `None` when the engine was not read: the measurement does not need it.
    """
    found = [
        {"file": record["file"], "name": record["name"], "engine_component": record["target"]}
        for record in imports
        if record["repo"] == SEAM[0] and is_engine_name(record["name"])
    ]
    return sorted(found, key=lambda entry: (entry["file"], entry["name"]))


#: Where this repository commits the engine imports it lives with (#416 decision 14).
BASELINE_PATH = "docs/architecture/engine-imports-baseline.yaml"


def load_baseline(text: str, where: str = BASELINE_PATH, key: str = "imports") -> tuple[tuple[str, str], ...]:
    """A baseline file's `(file, name)` entries, sorted; a malformed or duplicated one is an error.

    The one loader of both baselines: this repository's (`imports`) and the engine's
    layering baseline (`allowed`, read by `check`), with the same refusals: YAML that
    cannot be loaded, a mapping without the list, an entry that is not exactly a
    `file` and a `name` of text, and a duplicate.

    A baseline that cannot be read must not pass for an empty one: an empty
    baseline would turn every listed import into a failure, and a silently
    truncated one would let a new import through.
    """
    try:
        document = yaml.safe_load(text)
    except Exception as error:  # a YAMLError, or a constructor's ValueError (`2026-13-32`)
        raise CollectError(f"{where} is not valid YAML: {str(error).splitlines()[0] if str(error) else type(error).__name__}") from error
    if not isinstance(document, dict) or not isinstance(document.get(key), list):
        raise CollectError(f"{where}: a baseline is a mapping with an `{key}` list")
    entries: list[tuple[str, str]] = []
    for number, entry in enumerate(document[key]):
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"file", "name"}
            or not all(isinstance(entry[key], str) and entry[key] for key in ("file", "name"))
        ):
            raise CollectError(f"{where}: entry #{number} must be a mapping with only 'file' and 'name'")
        pair = (entry["file"], entry["name"])
        if pair in entries:
            raise CollectError(f"{where}: {pair[0]} imports {pair[1]} is listed twice")
        entries.append(pair)
    return tuple(sorted(entries))


def check_engine_imports(
    found: Sequence[Mapping[str, Any]], baseline: Sequence[tuple[str, str]]
) -> list[str]:
    """The lines CI fails on: an engine import the baseline does not list, and a listed one that is gone.

    The unit is the pair, so the same name imported by a second file is a new
    import, and an entry whose file still imports something else is stale. The
    engine component is named when the measurement carries it, which is when the
    engine was read.
    """
    listed = set(baseline)
    measured = {(entry["file"], entry["name"]) for entry in found}
    problems = [
        f"{entry['file']}: imports {entry['name']}"
        f"{' from the engine component ' + entry['engine_component'] if entry.get('engine_component') else ''}"
        f", which {BASELINE_PATH} does not list; a new engine import is a coupling nobody decided on,"
        " and that file only shrinks"
        for entry in found
        if (entry["file"], entry["name"]) not in listed
    ]
    problems += [
        f"{file}: imports {name}, listed in {BASELINE_PATH}, is gone; delete the entry"
        for file, name in baseline
        if (file, name) not in measured
    ]
    return problems


def import_edges(
    trees: Mapping[str, Any],
    claims: Mapping[str, Sequence[tuple[str, str]]],
    components: Sequence[Mapping[str, Any]],
    imports: Sequence[Mapping[str, Any]] | None = None,
) -> list[Edge]:
    """Component -> component edges with their import counts, sorted by (from, to).

    `imports` is the measurement, when the caller already made it: the collector
    measures once and hands the same records to the baseline it reports.
    """
    by_id = {c["id"]: c for c in components}
    records = imports_of(trees, claims) if imports is None else imports
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for record in records:
        source, target = record["component"], record["target"]
        if target and target != source:
            counts[(source, target)] += 1

    edges = []
    for (source, target), count in sorted(counts.items()):
        a, b = by_id[source], by_id[target]
        if a["repo"] == b["repo"]:
            edges.append({"from": source, "to": target, "imports": count, "scope": "within", "repo": a["repo"],
                          "upward": _upward(a, b)})
        else:
            edges.append({"from": source, "to": target, "imports": count, "scope": "across",
                          "from_repo": a["repo"], "to_repo": b["repo"], "upward": False})
    return edges


def _upward(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Whether an import from component `a` into `b` of the same repository goes up its layers."""
    return a["repo"] == b["repo"] and None not in (a.get("layer"), b.get("layer")) and b["layer"] > a["layer"]


def upward_imports(imports: Sequence[Mapping[str, Any]], components: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each import within a repository that goes up a layer, sorted by (file, name): file, name, components and layers (#419).

    The layering baseline of the repository that declares the layers lists the
    same (file, name) pairs, so `check` can compare entries rather than counts.
    """
    by_id = {c["id"]: c for c in components}
    found = []
    for record in imports:
        source, target = record["component"], record["target"]
        if not target or target == source:
            continue
        a, b = by_id[source], by_id[target]
        if _upward(a, b):
            found.append({"file": record["file"], "name": record["name"], "from": source, "to": target,
                          "from_layer": a["layer"], "to_layer": b["layer"]})
    return sorted(found, key=lambda u: (u["file"], u["name"]))


def seam_edges(edges: Sequence[Edge]) -> list[Edge]:
    """The across-edges of the one seam held to a baseline (`SEAM`)."""
    return [e for e in edges if e["scope"] == "across" and (e["from_repo"], e["to_repo"]) == SEAM]


def summarise(edges: Sequence[Edge]) -> dict[str, int]:
    """The figures the pages state: upward edges and imports, and the seam's (opengwasdb-stores into opengwasdb)."""
    upward = [e for e in edges if e["upward"]]
    seam = seam_edges(edges)
    return {
        "edges": len(edges),
        "upward_edges": len(upward),
        "upward_imports": sum(e["imports"] for e in upward),
        "registry_to_engine_edges": len(seam),
        "registry_to_engine_imports": sum(e["imports"] for e in seam),
    }
