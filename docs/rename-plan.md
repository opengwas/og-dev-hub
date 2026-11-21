# The OpenGWAS rename

**For the developers to review before anything is renamed.** The rule and the
reasons are in [ADR 0004](adr/0004-repo-name-is-package-name-is-command.md):
**the repository name is the package name and the command**, the import name is
the same with `_`, and "OpenGWASDB" is retired. OpenGWAS is pre-release, so
nothing is kept for the old names: no redirect pages, no compatibility imports,
no alias table.

## What changes

| Repository now | Repository | Package (pip) | Import | Command | Env prefix |
|---|---|---|---|---|---|
| ogld | **og-ld** | og-ld | `og_ld` (was `ogld`) | `og-ld` (was `ogld`) | `OG_LD_` (was `OGLD_`; `OGDB_STORE_TIMEOUT_SECONDS` becomes `OG_LD_STORE_TIMEOUT_SECONDS`) |
| *(new)* | **og-ld-stores** | og-ld-stores | `og_ld_stores` | `og-ld-stores` | `OG_LD_STORES_` |
| opengwasdb | **og-gwas** | og-gwas | `og_gwas` (was `opengwasdb`) | `og-gwas` (was `opengwasdb`) | `OG_GWAS_` (was `OPENGWASDB_`) |
| opengwasdb-stores | **og-gwas-stores** | og-gwas-stores (was `ogstores`) | `og_gwas_stores` (was `ogstores`) | `og-gwas-stores` | `OG_GWAS_STORES_` (was `OGSTORES_`) |
| ogdb-api | **og-data-api** | og-data-api (was `ogdb-api`) | `og_data_api` | — | `OG_DATA_API_` |
| opengwas-gateway | **og-gateway** | — | — | — | `OG_GATEWAY_` |
| opengwasdb-website | **og-website** | — | — | — | — |
| ogdb-dashboard | **og-ops-dashboard** | og-ops-dashboard | `og_ops_dashboard` | — | `OG_OPS_DASHBOARD_` |
| agent-skills | **og-agent-skills** | — | — | — | — |
| ogld-api | *deleted* (empty; og-data-api serves LD, [ADR 0003](adr/0003-one-data-api-serves-gwas-and-ld.md)) | | | | |
| opengwaspy, opengwasr | unchanged | unchanged | unchanged | — | — |

Also in the same rename:

- **og-gwas-stores' other top-level packages move under its own name.**
  `analysis_catalog`, `curation`, `manifest_generation` and `yardstick` become
  `og_gwas_stores.*`. `project_site` is not renamed: it moves to og-dev-hub
  after the rename.
- **Every old name in text is rewritten**: code, READMEs, `CONTEXT.md`, specs,
  `CLAUDE.md`, `AGENTS.md`, epic records (`repo#n` keys) and ADR bodies.
- **The board** is titled OpenGWAS, its README names the new repositories, and
  its Workstream field becomes the twelve workstreams the owner settled.

## Four kinds of name

A name is held in four kinds of place, and each kind changes differently.

| Kind | Examples | How it changes |
|---|---|---|
| **1. Repositories** | `opengwas/ogld` | A rename in GitHub's settings. GitHub redirects git remotes, issues and pull requests from the old name until another repository takes it |
| **2. Packages, imports, commands, environment variables** | `import ogld`, `ogld build`, `OGLD_BCFTOOLS` | Code: one pull request per repository, in dependency order |
| **3. Names written inside the data** | the LD Store key `software.ogld`, which validation requires (`ogld/store/validation.py`); `opengwasdb_version`, `opengwasdb_rev` and `opengwasdb_executable` in every GWAS Store's `records/build.json`; the `opengwasdb.besd`, `opengwasdb.gwas-ssf` and `opengwasdb.finngen-r` reader IDs in about 25,000 lines of Release Bundles and inventories | **Not in this rename** ([ADR 0004](adr/0004-repo-name-is-package-name-is-command.md)). They are labels that code looks up in Stores already built. Each changes in its engine's next format version, when the Stores are rebuilt |
| **4. Deployments and what services send each other** | the `x-ogdb-user` header and the `ogdb` service key between og-gateway and og-data-api; the dashboard's system user `ogdb-dashboard`, `/etc/ogdb-ops/` and its container | In pairs, both sides in one sitting (gateway and Data API). Deployment names change at the next redeploy |

**Not in this rename:**
- the host directory `/data/opengwasdb/`, which moves to `/data/opengwas/` separately, once no run is writing there;
- the names written inside the data (kind 3);
- release notes for versions already tagged, and git history.

## The order

### Before the window (nothing disrupted)

1. **Prepare every package rename as a pull request, on branches cut from today's
   repositories.** A branch survives a repository rename, so the window only has
   to merge them, not write them. Each pull request:
   - moves the package directory (`git mv ogld og_ld`);
   - renames the distribution and the command in `pyproject.toml`;
   - updates every import, the environment variables, the CI and release workflows,
     and the text;
   - adds a `breaking` changelog fragment.
2. **The quality-gate files are the owner's commit.** `quality.json` and the
   baselines under `quality/` in og-ld and og-gwas name the packages (27
   references in ogld, among them `public-api-ogld.json`). Agents may not edit
   them, so the owner makes that commit, or authorises it for this rename in
   writing.
3. **Agree the window.** No orchestrate run is in flight: no integration branch
   is open, and no build is running from a run's worktree. Anything else open
   is merged or parked, since a package rename lands under it.

### The window

4. **Rename the repositories** on GitHub, in one sitting (about ten minutes).
   Delete ogld-api and create og-ld-stores. GitHub Pages sites move with their
   repositories (`blog.opengwas.io/opengwasdb/` becomes `/og-gwas/`); OpenGWAS is
   pre-release, so only `site-url` changes.
5. **Merge the package renames in dependency order.** Each merge to `main` is a
   tagged release, and the version carries on from the existing `v*` tags.
   1. **og-gwas and og-ld**, in parallel: neither depends on another OpenGWAS
      repository. Before merging each one, run `test-realdata` on the IEU compute
      nodes, because both read panels from `/data`.
   2. **og-gwas-stores.** Its pixi dependency moves from
      `opengwasdb = { git = …/opengwasdb }` to `og-gwas` from `…/og-gwas`;
      `ogstores` becomes `og_gwas_stores`, with the other four packages under it;
      its 27 `OGSTORES_` variables and its Snakemake workflows change. Its
      Release Bundles and inventories keep their kind-3 names.
   3. **og-data-api and og-gateway, in one sitting.** og-data-api's pins
      (`opengwasdb @ git+…`, `ogld @ git+…`) move to step 5.1's merge commits,
      under the new names. The header and service key change on both sides.
   4. **The rest, in any order:** og-ops-dashboard (the package now, its
      deployment names at the next redeploy), og-website, opengwaspy (its docs),
      og-agent-skills (`preflight.py --repo`, `$ORCH_STORES`, the default
      `~/repo/opengwasdb-stores`, and `board`'s repository list), and og-dev-hub
      (`system.yaml`'s `formerly:` fields go).
6. **The board.** Rename it to OpenGWAS, set the twelve workstreams, reassign the
   existing epics, and update the README.

### After the window

7. **Check it worked:**
   - CI is green in every repository;
   - a search of every repository for the old names finds only the exceptions above;
   - one GWAS query and one LD query succeed through the gateway, and the
     dashboard reads the Data API.
8. **Each developer updates their machine** (below).

## What each developer does afterwards

```bash
# in each clone, once its repository is renamed
git remote set-url origin git@github.com:opengwas/<new-name>.git
git fetch origin && git rebase origin/main    # or your branch's new base
pixi reinstall --locked                       # the old package name is gone
# rename any OPENGWASDB_*, OGSTORES_*, OGLD_*, OGDB_* variables in your shell profile and job scripts
```

Worktrees share their clone's remote, so a worktree needs nothing more than
the rebase. Rename local directories (`~/repo/opengwasdb` to `~/repo/og-gwas`)
only if you want to. **If you use Claude Code, its memory follows the
directory's path:** after renaming `~/repo/ogld`, move
`~/.claude/projects/-home-<you>-repo-ogld/` to the new path's name, or that
project's memory is left behind. The same goes for worktrees and orchestrate
run directories.

## Open for the developers

- A date for the window.
- Anything this plan breaks that it does not list, such as deployment configs,
  cron jobs, services that import by the old name, or notebooks.
