"""Where the Dev Hub reads and writes (og-dev-hub#7, og-dev-hub#9, og-dev-hub#15).

Every repository og-dev-hub's `system.yaml` lists is read from a bare clone under
the work root, `<work root>/<name>.git`, through one read handle per run
(`staging.Repositories`), which `staging.ensure_clone` clones and fetches. The
work root is `$OPENGWASDB_SITE_ROOT`, else `/data/opengwasdb/work/site` on the
host that has `/data`, else `.work/` in this checkout.
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

# The build host's default: `git clone` keeps each repository's history here.
WORK_ROOT = Path("/data/opengwasdb/work/site")
WORK_ROOT_ENV = "OPENGWASDB_SITE_ROOT"
CLONE_ENV = "OPENGWASDB_SITE_ENGINE_CLONE"
# A clone named here is used instead of `<work root>/<name>.git`.
CLONE_ENVS = {ENGINE: CLONE_ENV, REGISTRY: "OPENGWASDB_SITE_REGISTRY_CLONE"}


# og-dev-hub's system model (#8), read from this checkout's working tree.
SYSTEM_FILE = "system.yaml"


def system_file() -> Path:
    """This checkout's `system.yaml`: the one path the hub's system model is read from by default."""
    return repo_root() / SYSTEM_FILE


def repo_root() -> Path:
    """The og-dev-hub checkout this package is installed from: its `system.yaml`, `CONTEXT.md` and `_site/`."""
    return Path(__file__).resolve().parents[2]


def work_root() -> Path:
    """Where the clones live: `$OPENGWASDB_SITE_ROOT`, else `/data/opengwasdb/work/site` on a host that has
    `/data/opengwasdb/work`, else `.work/` in this checkout (git-ignored), so a machine without `/data`
    (CI, a laptop) builds the site too (og-dev-hub#15)."""
    configured = os.environ.get(WORK_ROOT_ENV)
    if configured and configured.strip():
        return Path(configured)
    return WORK_ROOT if WORK_ROOT.parent.is_dir() else repo_root() / ".work"


def checkout_name(repo: Path) -> str:
    return repo.resolve().name


def clone_dir(name: str) -> Path:
    """Where the site keeps its bare clone of the opengwas repository `name`.

    `<work root>/<name>.git`, unless the repository's variable in `CLONE_ENVS`
    names another git directory.
    """
    configured = os.environ.get(CLONE_ENVS.get(name, ""), "")
    return Path(configured) if configured.strip() else work_root() / f"{name}.git"


def clone_url(name: str) -> str:
    """Where the site clones the opengwas repository `name` from: GitHub."""
    return f"{GITHUB}/{name}"


def registry_tree_dir() -> Path:
    """Where opengwasdb-stores' files are extracted for this checkout's run: `<work root>/<checkout>-registry`."""
    return work_root() / f"{checkout_name(repo_root())}-registry"
