"""`pixi run site-data`: run every collector, write `<data dir>/<source>.json`, print a line each (#389).

    pixi run site-data [--data-dir PATH] [--registry PATH] [--refresh] [--strict]

The collectors are the board, the Stores, the architecture and the work: the
collection `pixi run architecture --data` reads, private repositories and the
board included. The site's own collection is `run(public_only=True)`: the
architecture of public git alone (og-dev-hub#15).

Every repository `system.yaml` lists is read from `main` of a bare clone of it
under the work root, through one read handle each (`staging.Repositories`),
fetched once with `--refresh`; opengwasdb-stores from the checkout `--registry`
names instead.

A source that fails is written as `available: false` with its error, printed as
`UNAVAILABLE <source>: <error>`, and the others still run. The exit status is 0
anyway, because a reader reads `available` first; `--strict` exits 1 when any source
is unavailable, after every file is written, for a caller that must not go on.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from project_site import paths, staging
from project_site.collect import architecture, architecture_model, board, common, stores, work


def describe(result: dict[str, Any]) -> str:
    source = result["source"]
    if not result["available"]:
        return f"UNAVAILABLE {source}: {result['error']}"
    if source == "board":
        lines = sum(len(m["lines"]) for m in result["milestones"])
        return f"board: {len(result['epics'])} epics, {len(result['milestones'])} milestones, {lines} milestone lines"
    if source == "stores":
        return f"stores: {len(result['stores'])} stores"
    if source == "architecture":
        return _describe_architecture(result)
    return _describe_work(result)


def _describe_architecture(result: dict[str, Any]) -> str:
    repos, summary, gaps = result["repos"], result["summary"], result["gaps"]

    def gap(found: dict[str, Any] | None) -> str:
        if not found or found.get("unclaimed") is None:
            return "unknown"
        return f"{len(found['unclaimed'])}/{len(found['stale'])}"

    read = []
    for name, repo in repos.items():
        if repo.get("model"):
            count = sum(1 for c in result["components"] if c["repo"] == name)
            failed = " REFRESH FAILED" if (repo.get("refresh") or {}).get("ok") is False else ""
            read.append(f"{name} {count} components at {repo['ref']} {str(repo['commit'])[:8]}{failed} "
                        f"(gaps {gap(gaps.get(name))} unclaimed/stale)")
    no_model = [name for name, repo in repos.items() if repo.get("model") is False]
    unreadable = [f"{name} ({repo['error']})" for name, repo in repos.items() if repo.get("error")]
    planned = [name for name, repo in repos.items() if repo.get("planned")]
    # Without a model declaring layers the layering is unknown (`null`), and says so rather than reading 0 (#421 review).
    upward = "layering unknown" if summary["upward_edges"] is None else (
        f"{summary['upward_edges']} upward edges ({summary['upward_imports']} imports)")
    system = [f"{repo} {sentence}" for repo, found in gaps.items() if found
              for sentence in architecture_model.describe_system_gaps(found)]
    seam = "unknown" if summary["registry_to_engine_imports"] is None else summary["registry_to_engine_imports"]
    return (
        f"architecture: {', '.join(read) or 'no repository with a model'}"
        + (f", NO MODEL: {', '.join(no_model)}" if no_model else "")
        + (f", UNREADABLE: {'; '.join(unreadable)}" if unreadable else "")
        + (f", PLANNED: {', '.join(planned)}" if planned else "")
        + (f", SYSTEM GAPS: {'; '.join(system)}" if system else "")
        + f", {upward}, {seam} registry->engine imports, "
        f"{summary['adrs_placed']} of {summary['adrs_total']} ADRs placed"
    )


def _describe_work(result: dict[str, Any]) -> str:
    summary = result["summary"]
    failed = [s["repo"] for s in result["branches"]["sources"] if (s.get("fetch") or {}).get("ok") is False]
    return (
        f"work: {summary['owners']} owners, {summary['meets']} meets ({summary['coordinated']} coordinated, "
        f"{summary['uncoordinated']} uncoordinated, {summary['unlinkable']} unlinkable), {summary['branches']} branches"
        + (f", NOT MEASURED for {', '.join(sorted(result['unmeasured']))}" if result.get("unmeasured") else "")
        + (f", BRANCH FETCH FAILED for {', '.join(failed)}" if failed else "")
    )


def run(
    data_dir: Path,
    *,
    gh: common.GhRunner = common.gh_runner,
    registry: Path | None = None,
    repositories: staging.Repositories | None = None,
    refresh: bool = False,
    out: Callable[[str], Any] = print,
    checkout: Path | None = None,
    system_file: Path | None = None,
    public_only: bool = False,
) -> list[dict[str, Any]]:
    """Run every collector into `data_dir`.

    `repositories` is the run's read handles; left out, they are made here, with
    opengwasdb-stores read from `checkout` when one is named, and every
    repository fetched once when `refresh` asks. `registry` names another directory of Release
    Bundles to read instead.
    `system_file` is the `system.yaml` read (by default this checkout's). A
    registry that cannot be read makes each source that needs its files
    unavailable, and no other.

    `public_only` is the site's collection (og-dev-hub#15): the architecture of
    public git alone, a private repository never read, and no board.
    """
    repositories = repositories or staging.Repositories(refresh=refresh, checkouts={paths.REGISTRY: checkout})

    def files(*parts: str) -> Path:
        return staging.registry_files(repositories).joinpath(*parts)

    collectors: list[tuple[str, Callable[[], dict[str, Any]]]]
    if public_only:
        collectors = [("architecture", lambda: architecture.collect(repositories, system_file=system_file, read_private=False))]
    else:
        collectors = [
            ("board", lambda: board.collect(gh)),
            ("stores", lambda: stores.collect(registry or files("stores"))),
            ("architecture", lambda: architecture.collect(repositories, system_file=system_file)),
            # After board and architecture: it reads the files those two just wrote to `data_dir`.
            ("work", lambda: work.collect(data_dir, repositories)),
        ]
    results = []
    for source, collect in collectors:
        result = common.collect_source(source, collect)
        common.write_source(data_dir, result)
        out(describe(result))
        results.append(result)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="project_site.collect", description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", type=Path, default=None,
                        help=f"where the JSON files go (default: ${common.DATA_DIR_ENV_VAR}, else docs/_data/)")
    parser.add_argument("--registry", type=Path, default=None,
                        help="an opengwasdb-stores checkout to read (default: its main, from its clone)")
    parser.add_argument("--refresh", action="store_true",
                        help="fetch every listed repository once first (`main` and its branches), and record whether that worked")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any source is unavailable")
    args = parser.parse_args(argv)
    results = run(args.data_dir or common.data_dir(), checkout=args.registry, refresh=args.refresh)
    return 1 if args.strict and not all(r["available"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
