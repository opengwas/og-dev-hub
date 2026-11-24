"""Where the site build reads and writes, and what it renders (#388).

Nothing the site build writes goes under `/home` or `/tmp`: the work root is
`/data/opengwasdb/work/site`, and the output sits under it, one directory per
checkout. Each path is overridable by an environment variable so a publish run
can keep its scratch tree apart from a developer's.

The site lives in og-dev-hub (og-dev-hub#7) and reads two other repositories:
opengwasdb-stores (the registry: its Release Bundles, docs, epic records and
architecture) and opengwasdb (the engine). Each is read from a bare clone under
the work root, `<work root>/<name>.git`, which `staging.ensure_clone` keeps.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ogstores import engine

# The repositories the site shows: this hub, the registry whose docs and
# Release Bundles it renders, and the engine whose docs it stages at the
# revision the registry pins.
GITHUB = "https://github.com/opengwas"
HUB = "og-dev-hub"
REGISTRY = "opengwasdb-stores"
ENGINE = "opengwasdb"
HUB_URL = f"{GITHUB}/{HUB}"
REGISTRY_URL = f"{GITHUB}/{REGISTRY}"
ENGINE_URL = f"{GITHUB}/{ENGINE}"

# Defaults, all under /data. `git clone` keeps each repository's history here;
# the checkout being rendered names its own output directory.
WORK_ROOT = Path("/data/opengwasdb/work/site")
WORK_ROOT_ENV = "OPENGWASDB_SITE_ROOT"
OUTPUT_ENV = "OPENGWASDB_SITE_OUT"
CLONE_ENV = "OPENGWASDB_SITE_ENGINE_CLONE"
# A clone named here is used instead of `<work root>/<name>.git`.
CLONE_ENVS = {ENGINE: CLONE_ENV, REGISTRY: "OPENGWASDB_SITE_REGISTRY_CLONE"}

# The ref `site-publish` renders: every merge lands on `main`, and each is a
# version (#386), so that is what the site publishes; `--ref` names another.
DEFAULT_PUBLISH_REF = "origin/main"


def repo_root() -> Path:
    """The og-dev-hub checkout being rendered: the one this package is installed from.

    It holds the site's Quarto project (`site/`) and the hub's own docs. The
    registry the site documents is `staging.registry_root`'s, never this.
    """
    return Path(__file__).resolve().parents[2]


def work_root() -> Path:
    return Path(os.environ.get(WORK_ROOT_ENV) or WORK_ROOT)


def checkout_name(repo: Path) -> str:
    return repo.resolve().name


def output_dir(repo: Path) -> Path:
    """Where a render puts the site: `$OPENGWASDB_SITE_OUT`, else under the work root."""
    configured = os.environ.get(OUTPUT_ENV)
    if configured:
        return Path(configured)
    return work_root() / checkout_name(repo) / "_site"


def staging_dir(repo: Path) -> Path:
    """The mirror of `docs/` the render reads, beside the output.

    Rendering a mirror, rather than `docs/` itself, is what lets the build
    rewrite links and spell Mermaid fences without editing a source file.
    """
    return work_root() / checkout_name(repo) / "_stage"


def preview_dir(repo: Path) -> Path:
    """The tree the live preview serves: the mirror, synced file by file.

    `quarto preview` renders into `_site/` inside the tree it serves, so the
    preview serves a synced copy. Re-staging then never removes a file the
    preview is writing, which is what a rebuild of the mirror itself would do.
    """
    return work_root() / checkout_name(repo) / "_preview"


def clone_dir(name: str) -> Path:
    """Where the site keeps its bare clone of the opengwas repository `name`.

    `<work root>/<name>.git`, unless the repository's variable in `CLONE_ENVS`
    names another git directory.
    """
    configured = os.environ.get(CLONE_ENVS.get(name, ""), "")
    return Path(configured) if configured.strip() else work_root() / f"{name}.git"


def registry_tree_dir(repo: Path) -> Path:
    """Where the registry's files are extracted for a render of `repo`, beside its mirror."""
    return work_root() / checkout_name(repo) / "_registry"


def pinned_opengwasdb_revision(lock: Path) -> str:
    """The opengwasdb commit `pixi.lock` resolves; the site documents that runtime."""
    return engine.locked_commit(lock)


def commit_of(repo: Path) -> str:
    """The commit `repo` has checked out; the one its docs are rendered from."""
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
