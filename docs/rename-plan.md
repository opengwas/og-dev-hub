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

**Not in this rename:** the host directory `/data/opengwasdb/`. It moves to
`/data/opengwas/` separately, once no run is writing there.

## The order

1. **Agree a quiet window.** No orchestrate run has an integration branch open,
   and nobody has unpushed work they cannot rebase. Open pull requests survive
   a repository rename, but not a package rename underneath them: anything open
   is merged or parked first.
2. **Rename the repositories** on GitHub, all in one sitting. GitHub redirects
   git remotes, issues and pull requests from an old name until another
   repository takes it, so nothing breaks in this step. Delete ogld-api.
3. **Rename the packages, one pull request per repository, engines first.**
   og-gwas, then og-gwas-stores, which depends on og-gwas by git URL and pins
   its package name. Then og-ld, then og-data-api, which imports both engines.
   Then the rest, in any order. Each pull request renames the distribution,
   the import package, the command, the environment variables and the text,
   and passes its own CI.
4. **Update og-agent-skills** (`board`, `orchestrate`, `create-store`) and the
   board.
5. **Close the window.**

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
only if you want to. Nothing depends on where a clone sits.

## Open for the developers

- A date for the quiet window.
- Anything this plan breaks that it does not list, such as deployment configs,
  cron jobs, services that import by the old name, or notebooks.
