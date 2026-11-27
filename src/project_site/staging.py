"""Where the Dev Hub reads every repository from: one read handle each, through git (og-dev-hub#7, og-dev-hub#9).

- a bare clone of each repository under the work root (`ensure_clone`), read
  through one handle per repository per run (`Repositories`, `Repository`);
- whether a ref resolves, and to which commit (`resolve_ref`);
- a repository's files at a commit, read by object id (`Tree`);
- opengwasdb-stores' files extracted from its clone (`extract_tree`), for the
  readers that need files on disk (the Stores collector, and og-dev-hub#16's yardstick results).

`git archive` is what extracts a revision, so the tree is exactly that commit's,
not whatever a working checkout happens to hold.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path
from typing import Any, Mapping, Sequence

from ogstores.resources import DECLARATION_FILENAME, REFERENCE_RESOURCES_DIR

from project_site import paths
from project_site.collect.architecture_model import split_nul
from project_site.collect.common import CollectError


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


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
    git_dir: Path, *, url: str | None = None, fetch: bool = True, refspec: str = BRANCHES
) -> dict[str, Any] | None:
    """The one owner of cloning and fetching the repositories the site reads (og-dev-hub#7).

    With `url`, a `git_dir` that is not a repository yet is cloned from it,
    bare. Otherwise, with `fetch`, `refspec` is fetched from `origin`, pruning
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
    return _recorded(["git", "-C", str(git_dir), "fetch", "--quiet", "--prune", "origin", refspec])


def _recorded(command: list[str]) -> dict[str, Any]:
    try:
        done = subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}
    if done.returncode != 0:
        return {"ok": False, "error": done.stderr.strip() or f"git {command[1]} exited {done.returncode}"}
    return {"ok": True, "error": None}


# What is read from the registry's files, as opposed to through git: the Release
# Bundles (the Stores collector) and the yardstick's results (og-dev-hub#16).
REGISTRY_TREE = ("stores", "docs/_yardstick")
# And, for the LD panels `ld_registry.index.resource_rows` lists (og-dev-hub#10), the declaration of each Reference Resource
# alone: `resources/reference-resources/<id>/resource.yaml`. The directories beside it hold panel data tables the site never reads.
RESOURCE_DECLARATIONS = REFERENCE_RESOURCES_DIR.as_posix()
DECLARATION = DECLARATION_FILENAME


def extract_tree(clone: Path, ref: str, dest: Path) -> str:
    """Extract the registry's `REGISTRY_TREE` of `clone` at `ref` into `dest`; return the commit.

    `dest` is rebuilt, so a file the ref no longer has is never left behind. A
    path the ref does not hold is left out rather than failing the archive.
    """
    commit, why = resolve_ref(clone, ref)
    if commit is None:
        raise CollectError(f"{clone} cannot be extracted at {ref}: {why}")
    present = [path for path in REGISTRY_TREE if _git(clone, "ls-tree", "--name-only", commit, "--", path).strip()]
    declared = [
        name for name in _git(clone, "ls-tree", "-r", "--name-only", commit, "--", RESOURCE_DECLARATIONS).splitlines()
        if name.endswith(f"/{DECLARATION}") and name.count("/") == RESOURCE_DECLARATIONS.count("/") + 2
    ]
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    _extract(clone, commit, present + declared, dest)
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
    first time (bare, under `root`, by default `paths.work_root()`; `paths.clone_dir`) and fetched at
    most once per run, on a `refresh`. Every later `get` of it is the same
    handle, so every reader of one run (the architecture, the work, the Stores)
    reads the same commit. A clone or fetch that fails never raises: it is in the handle,
    and whatever the clone already holds is read.

    `checkouts` names a checkout to read instead of a clone (`--registry PATH`),
    at `HEAD` with its own files; a refresh fetches its remote-tracking branches
    only. `git_dirs` names another git directory to read a repository from,
    never cloned into, and `refs` another ref than `main` (a caller's, such as
    a test's fixture repositories). `tree` is where opengwasdb-stores' files are extracted, by
    default under `root` (`paths.registry_tree_dir`): only its readers need files
    (`REGISTRY_TREE`).
    """

    def __init__(
        self,
        *,
        refresh: bool = False,
        checkouts: Mapping[str, Path | None] | None = None,
        git_dirs: Mapping[str, Path | None] | None = None,
        refs: Mapping[str, str | None] | None = None,
        tree: Path | None = None,
        root: Path | None = None,
    ) -> None:
        self.refresh = refresh
        self.root = root
        self.checkouts = {name: Path(path).resolve() for name, path in (checkouts or {}).items() if path is not None}
        self.git_dirs = {name: Path(path) for name, path in (git_dirs or {}).items() if path is not None}
        self.refs = {name: ref for name, ref in (refs or {}).items() if ref}
        self.tree = tree
        self.handles: dict[str, Repository] = {}
        self.fetched: set[str] = set()

    def get(self, name: str, *, files: bool = False) -> Repository:
        """`name`'s read handle; `files` extracts opengwasdb-stores' files."""
        if files and name != paths.REGISTRY:
            raise ValueError(f"only {paths.REGISTRY}'s files are extracted, not {name}'s")
        handle = self.handles.get(name)
        if handle is None:
            handle = self.handles[name] = self._read(name)
        if files and handle.root is None and handle.readable:
            root = Path(self.tree) if self.tree is not None else paths.registry_tree_dir(self.root)
            extract_tree(handle.git_dir, str(handle.commit), root)
            handle = self.handles[name] = replace(handle, root=root)
        return handle

    def _fetch(self, name: str, git_dir: Path, *, url: str | None, fetch: bool, refspec: str = BRANCHES) -> dict[str, Any] | None:
        done = ensure_clone(git_dir, url=url, fetch=fetch and name not in self.fetched, refspec=refspec)
        if done is not None:
            self.fetched.add(name)
        return done

    def _read(self, name: str) -> Repository:
        if name in self.checkouts:
            checkout = self.checkouts[name]
            fetched = self._fetch(name, checkout, url=None, fetch=self.refresh, refspec=CHECKOUT_FETCH)
            commit, why = resolve_ref(checkout, "HEAD")
            return Repository(name=name, git_dir=checkout, ref="HEAD", commit=commit, root=checkout, clone=False,
                              fetch=fetched, error=None if commit else f"{name} cannot be read from {checkout}: {why}")
        named = name in self.git_dirs
        git_dir = self.git_dirs.get(name) or paths.clone_dir(name, self.root)
        ref = self.refs.get(name, "main")
        url = None if named else paths.clone_url(name)
        fetched = self._fetch(name, git_dir, url=url, fetch=self.refresh)
        commit, why = resolve_ref(git_dir, ref)
        if commit is None and fetched and not fetched["ok"]:
            why = fetched["error"]
        return Repository(
            name=name, git_dir=git_dir, ref=ref, commit=commit, clone=True, fetch=fetched if self.refresh else None,
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
