"""Stage what the site renders: the repositories it reads, their docs, the glossary (#388).

The site is one Quarto project over several repositories' documentation, so a
render needs a tree it may alter. This module builds that tree:

- a bare clone of each repository under the work root (`ensure_clone`), read
  through one handle per repository (`Repositories`), and the registry's files
  extracted from its clone (`extract_tree`);
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
from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Any, Mapping, Sequence

from project_site import paths
from project_site.collect.architecture_model import split_nul
from project_site.collect.common import CollectError
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
    _extract(repo, revision, files, dest, strip="docs/")
    return sorted(path.relative_to(dest).as_posix() for path in dest.rglob("*") if path.is_file())


def _extract(repo: Path, revision: str, names: list[str], dest: Path, *, strip: str = "") -> None:
    """Extract the files `names` of `repo` at `revision` into `dest` with `git archive`, less a `strip` prefix."""
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", revision, "--", *names], capture_output=True, check=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = []
        for member in tar.getmembers():
            if not member.isfile():
                continue
            member.name = member.name[len(strip):]
            members.append(member)
        tar.extractall(dest, members=members, filter="data")


# Every branch of the origin, as a bare clone holds them.
BRANCHES = "+refs/heads/*:refs/heads/*"


def ensure_clone(
    git_dir: Path, *, url: str | None = None, fetch: bool = True, refspec: str = BRANCHES, remote: str = "origin"
) -> dict[str, Any] | None:
    """The one owner of cloning and fetching the repositories the site reads (og-dev-hub#7).

    With `url`, a `git_dir` that is not a repository yet is cloned from it,
    bare. Otherwise, with `fetch`, `refspec` is fetched from `remote`, pruning
    what the remote no longer has. Returns `{ok, error}` for the clone or fetch
    that ran, with git's own message on failure, or `None` when neither ran.
    It never raises: a failure is recorded, and whatever the git directory
    already holds is still read (docs/spec/project-site.md, Work).
    """
    git_dir = Path(git_dir)
    if url is not None and not (git_dir / "HEAD").exists():
        try:
            git_dir.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}
        return _recorded(["git", "clone", "--bare", "--quiet", url, str(git_dir)])
    if not fetch:
        return None
    return _recorded(["git", "-C", str(git_dir), "fetch", "--quiet", "--prune", remote, refspec])


def _recorded(command: list[str]) -> dict[str, Any]:
    try:
        done = subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    if done.returncode != 0:
        return {"ok": False, "error": done.stderr.strip() or f"git {command[1]} exited {done.returncode}"}
    return {"ok": True, "error": None}


# What the site reads from the registry's files, as opposed to through git: the
# Release Bundles, the docs it mirrors (with the epic records and the yardstick
# results), the glossary, the lock that pins the engine, and the configuration
# `ogstores.paths.artifact_root` reads the catalog's root from.
REGISTRY_TREE = ("stores", "docs", "CONTEXT.md", "pixi.lock", "ogstores.yaml")


def extract_tree(clone: Path, ref: str, dest: Path) -> str:
    """Extract the registry's `REGISTRY_TREE` of `clone` at `ref` into `dest`; return the commit.

    `dest` is rebuilt, so a file the ref no longer has is never left behind. A
    path the ref does not hold is left out rather than failing the archive.
    """
    commit, why = resolve_ref(clone, ref)
    if commit is None:
        raise CollectError(f"{clone} cannot be extracted at {ref}: {why}")
    present = [path for path in REGISTRY_TREE if _git(clone, "ls-tree", "--name-only", commit, "--", path).strip()]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    _extract(clone, commit, present, dest)
    return commit


# A named checkout's pushed branches, as `git fetch origin` keeps them; a bare clone's are `BRANCHES`.
CHECKOUT_FETCH = "+refs/heads/*:refs/remotes/origin/*"


@dataclass(frozen=True)
class Repository:
    """One repository as the site reads it (og-dev-hub#9): its git at `ref`, and its files when asked for.

    `git_dir` is the site's bare clone (`clone` true: pushed branches are
    `refs/heads/*`), or a checkout named instead (`clone` false: they are
    `refs/remotes/origin/*`). `commit` is what `ref` names there, or `None` when
    the repository cannot be read at all, and then `error` says why, with git's
    own message. `fetch` is this run's one fetch, `{ok, error}`, or `None` when
    none was asked for. `root` holds its files: a named checkout's own, or the
    tree extracted from the clone (opengwasdb-stores only, `extract_tree`), else
    `None`.
    """

    name: str
    git_dir: Path
    ref: str
    commit: str | None
    root: Path | None = None
    clone: bool = True
    fetch: dict[str, Any] | None = None
    error: str | None = None

    @property
    def readable(self) -> bool:
        return self.commit is not None

    def resolve(self, ref: str) -> str | None:
        """The commit `ref` names in this repository's git, or `None` (`resolve_ref`)."""
        return resolve_ref(self.git_dir, ref)[0]

    def tree(self, at: str | None = None) -> Tree:
        """Every file of this repository at `at` (by default the commit read): the one way its files are read."""
        return Tree(self.git_dir, at or str(self.require().commit))

    def read(self, paths: Sequence[str], *, at: str | None = None) -> dict[str, str]:
        """The files `paths` at `at` (by default the commit read), listing only those; a path not there is absent."""
        return Tree(self.git_dir, at or str(self.require().commit), only=list(paths)).read(list(paths))

    def require(self) -> "Repository":
        """This handle, or a `CollectError` saying why the repository cannot be read."""
        if self.commit is None:
            raise CollectError(str(self.error))
        return self


class Repositories:
    """The one owner of where the site reads every repository from (og-dev-hub#7, og-dev-hub#9).

    `get(name)` is a repository's read handle. Each repository is cloned the
    first time (bare, under the work root, `paths.clone_dir`) and fetched at
    most once per run: on a `refresh`, or when a `revision` is asked for that
    the clone lacks. Every later `get` of it is the same handle, so every reader
    of one run (the architecture, the work, the build's engine docs) reads the
    same commit. A clone or fetch that fails never raises: it is in the handle,
    and whatever the clone already holds is read.

    `checkouts` names a checkout to read instead of a clone (`--registry PATH`),
    at `HEAD` with its own files; a refresh fetches its remote-tracking branches
    only. `git_dirs` names another git directory to read a repository from,
    never cloned into, and `refs` another ref than `main` (a caller's, such as
    a test's fixture repositories). `tree` is where opengwasdb-stores' files are extracted, by
    default beside this hub checkout's mirror: only its readers need files
    (`stores/`, `docs/_epics`, `CONTEXT.md`).
    """

    def __init__(
        self,
        *,
        refresh: bool = False,
        checkouts: Mapping[str, Path | None] | None = None,
        git_dirs: Mapping[str, Path | None] | None = None,
        refs: Mapping[str, str | None] | None = None,
        tree: Path | None = None,
    ) -> None:
        self.refresh = refresh
        self.checkouts = {name: Path(path).resolve() for name, path in (checkouts or {}).items() if path is not None}
        self.git_dirs = {name: Path(path) for name, path in (git_dirs or {}).items() if path is not None}
        self.refs = {name: ref for name, ref in (refs or {}).items() if ref}
        self.tree = tree
        self.handles: dict[str, Repository] = {}
        self.fetched: set[str] = set()

    def get(self, name: str, *, files: bool = False, revision: str | None = None) -> Repository:
        """`name`'s read handle; `files` extracts opengwasdb-stores' files; `revision` must be in the clone."""
        if files and name != paths.REGISTRY:
            raise ValueError(f"only {paths.REGISTRY}'s files are extracted, not {name}'s")
        handle = self.handles.get(name)
        if handle is None:
            handle = self.handles[name] = self._read(name, revision)
        elif revision is not None and handle.clone and name not in self.fetched and not has_revision(handle.git_dir, revision):
            handle = self.handles[name] = replace(handle, fetch=self._fetch(name, handle.git_dir, url=None, fetch=True))
        if files and handle.root is None and handle.readable:
            root = Path(self.tree) if self.tree is not None else paths.registry_tree_dir(paths.staging_dir(paths.repo_root()))
            extract_tree(handle.git_dir, str(handle.commit), root)
            handle = self.handles[name] = replace(handle, root=root)
        return handle

    def _fetch(self, name: str, git_dir: Path, *, url: str | None, fetch: bool, refspec: str = BRANCHES) -> dict[str, Any] | None:
        done = ensure_clone(git_dir, url=url, fetch=fetch and name not in self.fetched, refspec=refspec)
        if done is not None:
            self.fetched.add(name)
        return done

    def _read(self, name: str, revision: str | None) -> Repository:
        if name in self.checkouts:
            checkout = self.checkouts[name]
            fetched = self._fetch(name, checkout, url=None, fetch=self.refresh, refspec=CHECKOUT_FETCH)
            commit, why = resolve_ref(checkout, "HEAD")
            return Repository(name=name, git_dir=checkout, ref="HEAD", commit=commit, root=checkout, clone=False,
                              fetch=fetched, error=None if commit else f"{name} cannot be read from {checkout}: {why}")
        named = name in self.git_dirs
        git_dir = self.git_dirs.get(name) or paths.clone_dir(name)
        ref = self.refs.get(name, "main")
        url = None if named else paths.clone_url(name)
        wanted = revision is not None and (git_dir / "HEAD").exists() and not has_revision(git_dir, revision)
        fetched = self._fetch(name, git_dir, url=url, fetch=self.refresh or wanted)
        commit, why = resolve_ref(git_dir, ref)
        if commit is None and fetched and not fetched["ok"]:
            why = fetched["error"]
        return Repository(
            name=name, git_dir=git_dir, ref=ref, commit=commit, clone=True, fetch=fetched if self.refresh or wanted else None,
            error=None if commit else f"{name} cannot be read from its clone at {git_dir}: {str(why).strip()}",
        )


def registry_files(repositories: Repositories) -> Path:
    """opengwasdb-stores' files, extracted through the run's own handle of it."""
    root = repositories.get(paths.REGISTRY, files=True).require().root
    assert root is not None
    return root


def resolve_ref(git_dir: Path, ref: str) -> tuple[str | None, str]:
    """The one owner of "does this ref resolve": `(commit, "")` that `ref` names in `git_dir`, or `(None, why)`.

    `why` is git's own message, or says the ref is not there. It never raises.
    """
    try:
        done = subprocess.run(["git", "-C", str(git_dir), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                              capture_output=True, text=True, check=False)
    except OSError as error:
        return None, f"{type(error).__name__}: {error}"
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip(), ""
    return None, done.stderr.strip() or f"{git_dir} has no {ref}"


class Tree:
    """The files of one repository at one ref, read through git and nothing else.

    `only` lists just those paths rather than the whole tree, for a reader of a few files.
    """

    def __init__(self, git_dir: Path, ref: str, only: Sequence[str] | None = None) -> None:
        self.git = ["git", "-C", str(git_dir)]
        self.ref = ref
        commit, why = resolve_ref(git_dir, ref)
        if commit is None:
            raise CollectError(f"{git_dir} has no ref {ref}: {why}")
        self.commit = commit
        # `<mode> <type> <oid>\t<path>` per NUL-terminated record: the object id is how a file is read
        # back, because a path can hold a newline and an id cannot.
        self.oids: dict[str, str] = {}
        listing = ["ls-tree", "-r", "-z", self.commit, *(["--", *only] if only is not None else [])]
        if only is None or only:
            for record in split_nul(self._run(listing).decode()):
                meta, path = record.split("\t", 1)
                mode, kind, oid = meta.split()
                if kind == "blob":
                    self.oids[path] = oid
        self.files = list(self.oids)

    @cached_property
    def committed(self) -> str:
        """The commit's date, read when it is asked for."""
        return self._run(["show", "-s", "--format=%cI", self.commit]).decode().strip()

    def _run(self, args: list[str], stdin: bytes | None = None) -> bytes:
        done = subprocess.run([*self.git, *args], input=stdin, capture_output=True, check=False)
        if done.returncode != 0:
            raise CollectError(f"git {args[0]} exited {done.returncode}: {done.stderr.decode(errors='replace').strip()}")
        return done.stdout

    def read(self, paths: list[str]) -> dict[str, str]:
        """Many files at the ref through one `git cat-file --batch`; a path not in the tree is absent.

        Blobs are requested by object id, one `<oid>` per line: a path is never
        put on a line, because a tracked path may contain a newline.
        """
        wanted = [(path, self.oids[path]) for path in paths if path in self.oids]
        if not wanted:
            return {}
        out = self._run(["cat-file", "--batch"], "".join(f"{oid}\n" for _, oid in wanted).encode())
        found: dict[str, str] = {}
        position = 0
        for path, oid in wanted:
            newline = out.index(b"\n", position)
            header = out[position:newline].split()
            if header[0].decode() != oid or header[1] != b"blob":
                raise CollectError(f"git cat-file answered {header!r} for {oid} ({path!r})")
            size = int(header[2])
            found[path] = out[newline + 1 : newline + 1 + size].decode("utf-8", "replace")
            position = newline + 1 + size + 1
        return found


def has_revision(clone: Path, revision: str) -> bool:
    return resolve_ref(clone, revision)[0] is not None


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


