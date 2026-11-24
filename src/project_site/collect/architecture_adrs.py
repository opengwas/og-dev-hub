"""Place each ADR on the architecture (#418), from every repository read (og-dev-hub#9).

An ADR belongs to a component for one of two reasons, and no other:

- **code**: it cites code the component claims, by a file path, a dotted module
  name (`opengwasdb.store.paths`, `project_site.pages`) or a GitHub link to a file.
  A bare suffix such as `store/paths.py` counts only when exactly one tracked file
  ends with it; an ambiguous one is skipped, never guessed;
- **title**: a component's `name` appears in the ADR's title, case-insensitive,
  at the start of a word and with no boundary at its end ("Analysis Catalog" places
  "Analysis Catalogue ..."; "Query" does not match inside "subquery").

A component's name that appears only in the body, however often, places
nothing: counting words rewarded long ADRs and wrongly placed ones that merely
discuss a neighbour. An ADR placed nowhere is still listed, with no components,
so the page can say which decisions the map cannot reach. Code is placed only
into a repository with a model: only its claims say which component owns a file.

An ADR that names another decision across repositories (`<repo> ADR NNNN`,
og-dev-hub ADR 0002, where `<repo>` is a listed repository) records it in
`cites`, which the pages show as a link to that ADR.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from project_site.collect import architecture_graph, architecture_model as model_rules, citations

ADR_PATH = re.compile(r"docs/adr/(\d{4})-.*\.md$")
PATH_CITE = re.compile(r"(?<![\w./:-])((?:[\w.-]+/)+[\w.-]+\.(?:py|smk|sh|toml))\b")
# A GitHub link to a file of any opengwas repository; the collector keeps the ones of a listed repository it read.
URL_CITE = re.compile(
    r"github\.com/opengwas/([\w.-]+)/(?:blob|tree)/[^/\s]+/([^\s#)?\]>`'\"]+)"
)
GITHUB = "https://github.com/opengwas"


def adr_citations(text: str, repos: Sequence[str]) -> list[dict[str, str]]:
    """Every `<repo> ADR NNNN` of `text` whose `<repo>` is one of `repos`, as `{repo, number}`, sorted, once each.

    The form is og-dev-hub ADR 0002's: a citation that crosses repositories names
    the repository, because the same number means different things in each.
    """
    if not repos:
        return []
    names = "|".join(re.escape(r) for r in sorted(repos, key=len, reverse=True))
    found = {
        (repo, number.zfill(4))
        for repo, number in re.findall(r"(?<![\w./-])(" + names + r")(?![\w-])\s+ADR[\s-]?(\d{1,4})\b", text)
    }
    return [{"repo": repo, "number": number} for repo, number in sorted(found)]


def place(
    trees: Mapping[str, Any],
    claims: Mapping[str, Sequence[tuple[str, str]]],
    components: Sequence[Mapping[str, Any]],
    modules: Mapping[str, Mapping[str, str]],
    repos: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Every ADR of every tree, with `components` as `{component id: "code" | "title"}` and `cites`.

    `trees` and `modules` are keyed by repository name, every repository read;
    `claims` only the repositories with a model, the only ones code is placed in.
    A citation is resolved in the ADR's own repository first, then in those.
    `repos` is every listed repository name, which `cites` recognises.
    """
    names = {
        c["id"]: re.compile(r"(?<!\w)" + re.escape(c["name"]), re.IGNORECASE) for c in components
    }
    adrs: list[dict[str, Any]] = []
    for repo, tree in trees.items():
        reach = [repo, *[r for r in claims if r != repo]]
        reach_modules = {r: modules.get(r) or {} for r in reach}
        packages = sorted({module.split(".")[0] for found in reach_modules.values() for module in found})
        dotted = re.compile(r"\b((?:" + "|".join(map(re.escape, packages)) + r")(?:\.[A-Za-z_0-9]+)+)") if packages else None
        reach_trees = {r: trees[r] for r in reach if r in trees}
        paths = sorted(f for f in tree.files if ADR_PATH.search(f))
        texts = tree.read(paths)
        for path in paths:
            text = texts.get(path, "")
            title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path)
            placed = {
                cid: "code"
                for found_repo, found in _cited_files(text, repo, reach_trees, reach_modules, dotted)
                if (cid := model_rules.owner(claims.get(found_repo) or [], found))
            }
            for cid, pattern in names.items():
                if cid not in placed and pattern.search(title):
                    placed[cid] = "title"
            adrs.append(
                {
                    "repo": repo,
                    "number": ADR_PATH.search(path).group(1),  # type: ignore[union-attr]
                    "path": path,
                    "title": title,
                    "status": _status(text),
                    "url": f"{GITHUB}/{repo}/blob/main/{path}",
                    "components": dict(sorted(placed.items())),
                    "cites": adr_citations(text, repos),
                }
            )
    return adrs


def _status(text: str) -> str:
    head = "\n".join(text.splitlines()[:25])
    if re.search(r"[Ss]uperseded by", head):
        return "superseded"
    if re.search(r"[Aa]mended (?:by|in)|[Aa]mendment", head):
        return "amended"
    return "current"


# A dotted name whose first segment may be any package: the board collector keeps these
# unresolved, and the Work map keeps only the ones its claims cover. A name ending in a
# file extension or a domain (`pixi.toml`, `github.com`) is not a module.
GENERIC_DOTTED = re.compile(r"(?<![\w./-])([a-z_][a-z0-9_]{2,}(?:\.[A-Za-z_][A-Za-z_0-9]*)+)")
NOT_MODULE_SUFFIX = frozenset(
    "py md yaml yml json toml txt sh smk qmd html tsv gz csv lock com org io net ai uk".split()
)


def _extract(text: str, dotted: re.Pattern | None) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """What a text cites, unresolved: dotted names, `(repository slug, path)` links, and paths."""
    names = list(dotted.findall(text)) if dotted else []
    return names, URL_CITE.findall(text), PATH_CITE.findall(text)


def cited_strings(text: str | None) -> list[str]:
    """The paths and dotted module names a text cites, sorted, as the board collector keeps them.

    A path is as written (a GitHub link to a file gives its path); a dotted name is any
    that is not a file name or a domain. Whether each names real code is decided later,
    against the claims, by the work collector.
    """
    names, urls, paths = _extract(text or "", GENERIC_DOTTED)
    names = [n for n in names if n.rsplit(".", 1)[1] not in NOT_MODULE_SUFFIX]
    return sorted({*names, *(path.rstrip(".,;:!") for _, path in urls), *paths})


def _cited_files(
    text: str, home: str, trees: Mapping[str, Any], modules: Mapping[str, Mapping[str, str]], dotted: re.Pattern | None
) -> set[tuple[str, str]]:
    """The `(repository, file)` pairs a text cites, by dotted module, GitHub link or path."""
    return _resolve(*_extract(text, dotted), home, trees, modules)


def _resolve(
    names: Sequence[str], urls: Sequence[tuple[str, str]], paths: Sequence[str], home: str,
    trees: Mapping[str, Any], modules: Mapping[str, Mapping[str, str]],
) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for name in names:
        if hit := architecture_graph.resolve(name, home, modules):
            found.add(hit)
    for slug, path in urls:
        if slug in trees and path in set(trees[slug].files):
            found.add((slug, path))
    listings = {repo: tree.files for repo, tree in trees.items()}
    for raw in paths:
        resolved = citations.resolve_path(raw, home, listings)
        if resolved.found:
            found.add(resolved.found)
    return found
