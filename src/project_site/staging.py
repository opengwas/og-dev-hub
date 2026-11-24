"""Stage what the site renders: the repositories it reads, their docs, the glossary (#388).

The site is one Quarto project over several repositories' documentation, so a
render needs a tree it may alter. This module builds that tree:

- a bare clone of each repository under the work root (`ensure_clone`), and the
  registry's files extracted from its clone (`extract_tree`, `registry_root`);
- the engine's `docs/` at the revision the registry's `pixi.lock` pins, keeping
  only its Markdown and self-contained HTML;
- the registry's `CONTEXT.md` as the glossary page;
- a mirror of the registry's `docs/` without `reports/`, whose `.qmd` sources
  are report sources the site does not execute, with og-dev-hub's `site/` and
  `docs/` staged into it the same way;
- over the mirror, the link rewrite and the Mermaid fence spelling from
  `project_site.links`, so no source file is ever edited.

`git archive` is what stages a revision, so the tree is exactly that commit's,
not whatever a working checkout happens to hold.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from project_site import paths
from project_site.links import convert_mermaid_fences, rewrite_document

# Documentation, not data: the engine's `docs/` also holds logs, JSON, JSONL and
# the `.qmd` sources whose reports are published as HTML beside them.
DOCUMENT_SUFFIXES = frozenset({".md", ".html"})

# Directories under `docs/` the mirror leaves out: report sources (the site
# copies their committed HTML instead), Quarto's own cache, and the engine
# section, which is staged into the mirror from the engine repository rather
# than from this checkout.
MIRROR_SKIP_DIRECTORIES = frozenset({"reports", ".quarto", "_site", "opengwasdb"})

# A file the mirror never copies from `docs/`, for the same reason.
MIRROR_SKIP_FILES = frozenset({"glossary.md"})

# Files at the top of the engine's docs tree that are not a page of the engine
# section's index.
ENGINE_INDEX = "index.qmd"


@dataclass
class LinkReport:
    """What the link rewrite did to the mirror, for the build's summary.

    `raw_pages` are pages the render could not read as Markdown: Quarto only
    accepts an executable cell (`{mermaid}`) in a `.qmd`, so a `.md` page with a
    Mermaid fence is staged as `.qmd` and its rewritten Markdown is kept here, to
    be copied to its own published `.md` path after the render.

    `unparsed` are destinations the link pattern cannot read, such as one holding
    its own parentheses: they are left alone and reported rather than silently
    publishing a link nobody knows is broken.
    """

    pages: int = 0
    rewritten: int = 0
    missing: list[tuple[str, str, str]] = field(default_factory=list)
    raw_pages: list[tuple[str, str]] = field(default_factory=list)
    unparsed: list[tuple[str, str]] = field(default_factory=list)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def _documentation_files(repo: Path, revision: str) -> list[str]:
    names = _git(repo, "ls-tree", "-r", "--name-only", revision, "--", "docs").splitlines()
    return [
        name
        for name in names
        if name.startswith("docs/") and Path(name).suffix.lower() in DOCUMENT_SUFFIXES
    ]


def stage_docs(repo: Path, revision: str, dest: Path) -> list[str]:
    """Extract `repo`'s `docs/` at `revision` into `dest`, keeping documentation only.

    Returns the staged paths relative to `dest`, sorted. `dest` is rebuilt, so a
    change of pinned revision never leaves a page behind that the revision no
    longer has.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    files = _documentation_files(repo, revision)
    if not files:
        return []
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", revision, "--", *files],
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = []
        for member in tar.getmembers():
            if not member.isfile():
                continue
            member.name = member.name[len("docs/"):]
            members.append(member)
        tar.extractall(dest, members=members, filter="data")
    return sorted(path.relative_to(dest).as_posix() for path in dest.rglob("*") if path.is_file())


def ensure_clone(name: str, *, revision: str | None = None, url: str | None = None) -> Path:
    """The site's bare clone of the opengwas repository `name`, cloned and fetched as needed.

    It lives at `paths.clone_dir(name)`, `<work root>/<name>.git`, and is cloned
    from `url` (GitHub's `opengwas/<name>` unless a test names another) the first
    time. With `revision`, it is fetched only when it does not hold that commit,
    because a pinned commit never moves; without one, it is always fetched, so
    its branches are the origin's now. Branches are fetched as `refs/heads/*`,
    the same refs a fresh bare clone has.
    """
    clone = paths.clone_dir(name)
    if not (clone / "HEAD").exists():
        clone.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--bare", "--quiet", url or f"{paths.GITHUB}/{name}", str(clone)], check=True)
    if revision is None or not _has_revision(clone, revision):
        subprocess.run(
            ["git", "-C", str(clone), "fetch", "--quiet", "origin", "+refs/heads/*:refs/heads/*"], check=True
        )
    if revision is not None and not _has_revision(clone, revision):
        raise SystemExit(f"the {name} clone at {clone} does not have revision {revision}")
    return clone


# What the site reads from the registry's files, as opposed to through git: the
# Release Bundles, the docs it mirrors (with the epic records and the yardstick
# results), the glossary, the lock that pins the engine, and the configuration
# `ogstores.paths.artifact_root` reads the catalog's root from.
REGISTRY_TREE = ("stores", "docs", "CONTEXT.md", "pixi.lock", "ogstores.yaml")


def extract_tree(clone: Path, ref: str, dest: Path, members: tuple[str, ...] = REGISTRY_TREE) -> str:
    """Extract `members` of `clone` at `ref` into `dest` with `git archive`; return the commit.

    `dest` is rebuilt, so a file the ref no longer has is never left behind. A
    path the ref does not hold is left out rather than failing the archive.
    """
    commit = _git(clone, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    present = [path for path in members if _git(clone, "ls-tree", "--name-only", commit, "--", path).strip()]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(clone), "archive", "--format=tar", commit, "--", *present], capture_output=True, check=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")
    return commit


@dataclass(frozen=True)
class Registry:
    """opengwasdb-stores as the site reads it: files from `root`, history from `git_dir` at `ref`."""

    root: Path
    git_dir: Path
    ref: str


def registry_root(checkout: Path | None = None, *, tree: Path | None = None, url: str | None = None) -> Registry:
    """The one owner of where the site reads opengwasdb-stores from (og-dev-hub#7).

    A named `checkout` (`--registry PATH`) is read as it is: its files, and its
    git at `HEAD`. Otherwise the registry is `main` of the site's bare clone,
    fetched now, with the files the site reads extracted into `tree` (by
    default beside this hub checkout's mirror) and git read at that same commit.
    """
    if checkout is not None:
        checkout = Path(checkout).resolve()
        return Registry(root=checkout, git_dir=checkout, ref="HEAD")
    clone = ensure_clone(paths.REGISTRY, url=url)
    tree = Path(tree) if tree is not None else paths.registry_tree_dir(paths.repo_root())
    commit = extract_tree(clone, "main", tree)
    return Registry(root=tree, git_dir=clone, ref=commit)


def _has_revision(clone: Path, revision: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(clone), "cat-file", "-e", f"{revision}^{{commit}}"],
            capture_output=True,
        ).returncode
        == 0
    )


def stage_glossary(context: Path, dest: Path) -> Path:
    """Copy `CONTEXT.md` to the page the site publishes as its glossary."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(context, dest)
    return dest


def mirror_docs(repo: Path, dest: Path, *, docs: str = "docs", replace: bool = True) -> list[str]:
    """Copy `repo`'s `docs/` to `dest`, leaving out the directories the site builds.

    `docs` names another directory of `repo` to copy, as og-dev-hub's `site/` is.
    With `replace` false, `dest` is copied over rather than rebuilt: a file both
    hold is `repo`'s. A `repo` without the directory copies nothing.
    """
    if replace and dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (repo / docs).is_dir():
        dest.mkdir(exist_ok=True)
        return sorted(path.relative_to(dest).as_posix() for path in dest.rglob("*") if path.is_file())

    def ignore(directory: str, names: list[str]) -> set[str]:
        skipped = set()
        for name in names:
            if name in MIRROR_SKIP_FILES and Path(directory, name).is_file():
                skipped.add(name)
            elif name in MIRROR_SKIP_DIRECTORIES and Path(directory, name).is_dir():
                skipped.add(name)
        return skipped

    shutil.copytree(repo / docs, dest, ignore=ignore, dirs_exist_ok=not replace)
    return sorted(path.relative_to(dest).as_posix() for path in dest.rglob("*") if path.is_file())


def rewrite_mirror(
    dest: Path,
    *,
    registry: Path,
    commit: str,
    registry_url: str,
    engine: Path,
    engine_commit: str,
    engine_url: str,
    engine_prefix: str,
    sections: Sequence[tuple[str, Path, str, str]] = (),
) -> LinkReport:
    """Rewrite the mirror's outbound links, spelling Mermaid fences for Quarto.

    A page under `engine_prefix` came from the engine at `engine_commit`; a page
    under the prefix of one of `sections`, each `(prefix, git directory, commit,
    url)`, came from that repository (og-dev-hub's own docs, og-dev-hub#7); every
    other page came from the registry at `commit`. A rewritten target that the
    commit does not have is reported rather than hidden: its GitHub link will 404
    exactly as the relative one would have.

    A `.md` page holding a Mermaid fence is staged as `.qmd`, because Quarto
    refuses an executable cell in a `.md`. `rendered` carries that change of name
    into the same pass, so every link *to* such a page, and the page itself, still
    reach the rendered HTML rather than the source.
    """
    # Each tree a page can come from: its prefix in the mirror, its URL and commit,
    # the paths that commit has, and the pages of it staged under another name.
    trees = [
        (prefix, url, at, set(_git(git_dir, "ls-tree", "-r", "--name-only", at).splitlines()), {})
        for prefix, git_dir, at, url in [(engine_prefix, engine, engine_commit, engine_url), *sections]
    ]
    registry_tree = ("", registry_url, commit, set(_git(registry, "ls-tree", "-r", "--name-only", commit).splitlines()), {})

    def tree_of(page: str) -> tuple[str, str, str, set[str], dict[str, str]]:
        return next((tree for tree in trees if page.startswith(tree[0])), registry_tree)

    report = LinkReport()
    pages: list[tuple[Path, str, str]] = []  # the staged file, its docs path, its tree path
    renamed: set[str] = set()
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".qmd"}:
            continue
        page = path.relative_to(dest).as_posix()
        prefix, *_, rendered = tree_of(page)
        relative = page[len(prefix):]
        text = convert_mermaid_fences(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".md" and _has_mermaid_cell(text):
            staged = path.with_suffix(".qmd")
            staged.write_text(text, encoding="utf-8")
            path.unlink()
            rendered[relative] = f"{relative[: -len('.md')]}.html"
            renamed.add(page)
            pages.append((staged, page, relative))
        else:
            pages.append((path, page, relative))

    for path, page, relative in pages:
        _, repo_url, page_commit, known, rendered = tree_of(page)
        text, targets, unparsed = rewrite_document(
            path.read_text(encoding="utf-8"),
            page=relative,
            repo_url=repo_url,
            commit=page_commit,
            rendered=rendered,
        )
        path.write_text(text, encoding="utf-8")
        report.pages += 1
        report.unparsed.extend((page, target) for target in unparsed)
        for target in targets:
            report.rewritten += 1
            if target.repo_path and known and target.repo_path not in known:
                report.missing.append((page, target.target, target.repo_path))
        if page in renamed:
            # Its own published `.md` path, rewritten the same way, is filled in
            # after the render by `project_site.build`.
            report.raw_pages.append((page, text))
    return report


def _has_mermaid_cell(text: str) -> bool:
    """Whether the text holds a `{mermaid}` cell after the fence conversion."""
    return any(line.strip() == "```{mermaid}" for line in text.splitlines())


