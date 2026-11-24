"""Who owns which file: the claims of an architecture model (#418, epic #416).

Each repository keeps a `docs/architecture/components.yaml` whose components
claim code paths. A path ending in `/` claims a directory and any other path
claims one file; the longest claimed prefix wins, so a file belongs to exactly
one component. These functions are the one implementation of that rule: this
repository's ownership test fails on what they report, and the site's collector
reports the same things for every repository without failing the build.

They take plain data (a model, a list of tracked paths) and read no repository.
"""

from __future__ import annotations

from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

import yaml

Claims = list[tuple[str, str]]

# What counts as code in every repository, under the roots its claims give (`code_roots`, og-dev-hub#9).
CODE_SUFFIXES = (".py", ".smk", ".sh", ".R", ".r")


def split_nul(listing: str) -> list[str]:
    """The paths of a NUL-separated git listing (`ls-files -z`, `ls-tree -z`), each whole.

    Git quotes a path holding a tab or newline in its line-separated form, which
    would stop it matching any code root; the NUL form never does.
    """
    return listing.split("\0")[:-1] if listing.endswith("\0") else [p for p in listing.split("\0") if p]


def _read_yaml(text: str, what: str) -> Any:
    """`text` as YAML; a syntax error is an error naming `what` (the file)."""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{what} is not valid YAML: {error}") from error


def load_model(text: str) -> dict[str, Any]:
    """A model file's content, checked for everything the collector reads of it; anything else is an error.

    It is a mapping with a `components` list. Each component is a mapping with an
    `id` and a `name` of text, ids unique; `paths` and `stages`, when given, are
    lists of text, and `layer` a whole number. `layers` and `stages`, when given,
    are lists of mappings. The error names the problem, and the collector makes it
    that repository's gap (og-dev-hub ADR 0001).
    """
    model = _read_yaml(text, "the architecture model")
    if not isinstance(model, dict) or not isinstance(model.get("components"), list):
        raise ValueError("the architecture model must be a mapping with a `components` list")
    seen: set[str] = set()
    for number, component in enumerate(model["components"]):
        if not isinstance(component, dict):
            raise ValueError(f"component #{number} is not a mapping")
        for key in ("id", "name"):
            if not isinstance(component.get(key), str) or not component[key]:
                raise ValueError(f"component #{number} has no `{key}` of text")
        if component["id"] in seen:
            raise ValueError(f"component id {component['id']!r} is in the model twice")
        seen.add(component["id"])
        for key in ("paths", "stages"):
            if component.get(key) is not None and not (
                isinstance(component[key], list) and all(isinstance(v, str) for v in component[key])
            ):
                raise ValueError(f"component {component['id']!r}: `{key}` must be a list of text")
        layer = component.get("layer")
        if layer is not None and (not isinstance(layer, int) or isinstance(layer, bool)):
            raise ValueError(f"component {component['id']!r}: `layer` must be a whole number")
    for key in ("layers", "stages"):
        if model.get(key) is not None and not (
            isinstance(model[key], list) and all(isinstance(v, dict) for v in model[key])
        ):
            raise ValueError(f"the architecture model's `{key}` must be a list of mappings")
    return model


# The keys of og-dev-hub's `system.yaml` that make the system model (#8). A components
# file that still holds one has it ignored and reported as a gap. The three lists of
# entities share one id space.
SYSTEM_SECTIONS = ("system", "people", "external", "containers", "container_relations")
SYSTEM_ENTITIES = ("people", "external", "containers")
# A listed repository's `visibility`: `null` is one not created yet (planned), drawn and never cloned (og-dev-hub#9).
VISIBILITIES = ("public", "private", None)


def load_system(text: str) -> dict[str, Any]:
    """`system.yaml`'s content: the five `SYSTEM_SECTIONS` and `repos` checked.

    `system` has a `name` and a `summary`; each person, external system and
    container has an `id` and a `name` (what the pages draw); ids are unique across
    the three lists; every `container_relations` entry is `[from, to, text]` and both
    ends name one of them; each of `repos` has a unique `name` and a `visibility` of
    `public`, `private` or `null`. A file that fails any of this is an error naming the problem.
    """
    doc = _read_yaml(text, "system.yaml")
    if not isinstance(doc, dict):
        raise ValueError("system.yaml must be a mapping")
    for key in SYSTEM_SECTIONS:
        if key not in doc:
            raise ValueError(f"system.yaml: `{key}` is missing")
    system = doc["system"]
    if not isinstance(system, dict) or not all(system.get(k) for k in ("name", "summary")):
        raise ValueError("system.yaml: `system` must be a mapping with a `name` and a `summary`")
    seen: set[str] = set()
    for key in SYSTEM_ENTITIES:
        entries = doc[key]
        if not isinstance(entries, list) or not all(isinstance(e, dict) and e.get("id") and e.get("name") for e in entries):
            raise ValueError(f"system.yaml: `{key}` must be a list of mappings, each with an `id` and a `name`")
        for entry in entries:
            if str(entry["id"]) in seen:
                raise ValueError(f"system.yaml: duplicate id {str(entry['id'])!r} (in `{key}`)")
            seen.add(str(entry["id"]))
    relations = doc["container_relations"]
    if not isinstance(relations, list) or not all(isinstance(r, list) and len(r) == 3 for r in relations):
        raise ValueError("system.yaml: `container_relations` must be a list of [from, to, text]")
    for a, b, _ in relations:
        for end in (a, b):
            if str(end) not in seen:
                raise ValueError(f"system.yaml: `container_relations` names {str(end)!r}, which is no person, external system or container")
    if "repos" in doc and not isinstance(doc["repos"], list):
        raise ValueError("system.yaml: `repos` must be a list")
    names: set[str] = set()
    for entry in doc.get("repos") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
            raise ValueError("system.yaml: each of `repos` must be a mapping with a `name`")
        if entry.get("visibility") not in VISIBILITIES:
            raise ValueError(f"system.yaml: repository {entry['name']!r} has visibility {entry.get('visibility')!r}, "
                             "which is none of public, private or null (planned)")
        if entry["name"] in names:
            raise ValueError(f"system.yaml: repository {entry['name']!r} is listed twice")
        names.add(entry["name"])
    return doc


def describe_system_gaps(
    found: Mapping[str, Any], code: Callable[[Any], str] = str
) -> list[str]:
    """The sentences for one repository's system gaps (`gaps.<repo>`), the page's and the command line's.

    `code` formats a name or id (the page puts it in a code span).
    """
    sections, containers = found.get("system_sections") or [], found.get("containers") or []
    sentences = []
    if sections:
        sentences.append(
            f"system sections ignored: {', '.join(code(k) for k in sections)} "
            "(system sections belong in og-dev-hub's `system.yaml`)"
        )
    sentences += [
        f"{code(g['component'])} names container {code(g['container'])}, which `system.yaml` does not have"
        for g in containers
    ]
    return sentences


def claims_of(components: Iterable[Mapping[str, Any]]) -> Claims:
    """Every `(claimed path, component id)` of `components`, in file order."""
    return [(path, str(component["id"])) for component in components for path in component.get("paths") or []]


def matches(claimed: str, path: str) -> bool:
    return path == claimed or (claimed.endswith("/") and path.startswith(claimed))


def owner(claims: Sequence[tuple[str, str]], path: str) -> str | None:
    """The component whose longest claimed prefix covers `path`, or `None`."""
    best: tuple[str, str] | None = None
    for claimed, component in claims:
        if matches(claimed, path) and (best is None or len(claimed) > len(best[0])):
            best = (claimed, component)
    return best[1] if best else None


def code_roots(claims: Iterable[tuple[str, str]]) -> frozenset[str]:
    """The top-level directories of every path the claims name: where a repository's code is (og-dev-hub#9).

    Which files count as code is derived from the model, never written per
    repository: a claim of `src/x/` or of `workflow/run.sh` makes `src` or
    `workflow` a root. A claim of a top-level file makes no root.
    """
    return frozenset(path.split("/", 1)[0] for path, _ in claims if "/" in path)


def is_code(path: str, roots: Collection[str]) -> bool:
    """A file under one of `roots` with a code suffix, or a `Snakefile`: one that must be claimed."""
    if path.split("/", 1)[0] not in roots:
        return False
    return path.endswith(CODE_SUFFIXES) or path.endswith("/Snakefile")


def code_rule(claims: Iterable[tuple[str, str]]) -> Callable[[str], bool]:
    """`is_code` for the roots of `claims`: the one rule of what a repository's model must cover."""
    roots = code_roots(claims)
    return lambda path: is_code(path, roots)


def check_claims(
    claims: Sequence[tuple[str, str]], tracked: Sequence[str], is_code: Callable[[str], bool]
) -> dict[str, list]:
    """The code files nobody claims and the claims that match no tracked file.

    `unclaimed` is a sorted list of paths; `stale` is a list of
    `{"path", "component"}` sorted by path.
    """
    unclaimed = sorted(path for path in tracked if is_code(path) and owner(claims, path) is None)
    stale = [
        {"path": claimed, "component": component}
        for claimed, component in sorted(claims)
        if not any(matches(claimed, path) for path in tracked)
    ]
    return {"unclaimed": unclaimed, "stale": stale}
