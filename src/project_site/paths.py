"""Where the Dev Hub reads and writes (og-dev-hub#7, og-dev-hub#9, og-dev-hub#15).

Every repository og-dev-hub's `system.yaml` lists is read from a bare clone under
the work root, `<work root>/<name>.git`, through one read handle per run
(`staging.Repositories`), which `staging.ensure_clone` clones and fetches.

There are two work roots, and `$OPENGWASDB_SITE_ROOT` names either. The site's
(`site_work_root`) is `.work/site` in this checkout, the same on every machine,
and only ever holds public repositories. `pixi run architecture`'s
(`work_root`) is the build host's `/data/opengwasdb/work/site`, where it also
keeps the private repositories it reads.
"""

from __future__ import annotations

import os
from pathlib import Path

# The repositories named in code: this hub, the registry whose Release Bundles the
# Stores collector reads, and the engine. Every other repository is a name in
# `system.yaml`, read the same way (`clone_dir`, `clone_url`).
GITHUB = "https://github.com/opengwas"
HUB = "og-dev-hub"
REGISTRY = "opengwasdb-stores"
ENGINE = "opengwasdb"

# `pixi run architecture`'s default: the build host's, where `git clone` keeps each repository's history.
WORK_ROOT = Path("/data/opengwasdb/work/site")
WORK_ROOT_ENV = "OPENGWASDB_SITE_ROOT"
# The site's default, under this checkout (git-ignored).
SITE_WORK_ROOT = Path(".work") / "site"


# og-dev-hub's system model (#8), read from this checkout's working tree.
SYSTEM_FILE = "system.yaml"


def system_file() -> Path:
    """This checkout's `system.yaml`: the one path the hub's system model is read from by default."""
    return repo_root() / SYSTEM_FILE


def repo_root() -> Path:
    """The og-dev-hub checkout this package is installed from: its `system.yaml`, `CONTEXT.md` and `_site/`."""
    return Path(__file__).resolve().parents[2]


def _configured() -> Path | None:
    configured = os.environ.get(WORK_ROOT_ENV, "")
    return Path(configured) if configured.strip() else None


def work_root() -> Path:
    """`pixi run architecture`'s clones: `$OPENGWASDB_SITE_ROOT`, else `/data/opengwasdb/work/site`."""
    return _configured() or WORK_ROOT


def site_work_root() -> Path:
    """The site's clones (og-dev-hub#15): `$OPENGWASDB_SITE_ROOT`, else `.work/site` in this checkout, on every machine."""
    return _configured() or repo_root() / SITE_WORK_ROOT


def checkout_name(repo: Path) -> str:
    return repo.resolve().name


def clone_dir(name: str, root: Path | None = None) -> Path:
    """The bare clone of the opengwas repository `name`: `<root>/<name>.git`, `root` by default `work_root()`."""
    return (root or work_root()) / f"{name}.git"


def clone_url(name: str) -> str:
    """Where the opengwas repository `name` is cloned from: GitHub."""
    return f"{GITHUB}/{name}"


def github_url(name: str, commit: object, path: str) -> str:
    """The one owner of a link to a repository's file or directory on GitHub, at `commit`.

    A path ending in `/` is a directory (`tree`); any other is a file (`blob`).
    """
    return f"{clone_url(name)}/{'tree' if path.endswith('/') else 'blob'}/{commit}/{path}"


def registry_tree_dir(root: Path | None = None) -> Path:
    """Where opengwasdb-stores' files are extracted for this checkout's run: `<root>/<checkout>-registry`."""
    return (root or work_root()) / f"{checkout_name(repo_root())}-registry"
