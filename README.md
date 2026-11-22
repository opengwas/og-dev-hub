# og-dev-hub

The developers' view of OpenGWAS. It draws the platform's built state (every
repository's components, how they depend on one another, and the decisions that
govern them), with the board's planned state over it, the epics, and the
inventories of GWAS Stores and LD Stores.

**The hub collects; it owns nothing** ([ADR 0001](docs/adr/0001-dev-hub-collects-and-owns-nothing.md)).
Each repository keeps its own components, glossary, ADRs and epic records, and
each Store Registry stays in the repository that builds its Stores. This
repository writes by hand only what no single repository owns:

| File | What it holds |
|---|---|
| [`system.yaml`](system.yaml) | The people, external systems and containers of OpenGWAS, and how they relate |
| [`CONTEXT.md`](CONTEXT.md) | The terms that cross repositories |
| [`CONTEXT-MAP.md`](CONTEXT-MAP.md) | Where each repository's own glossary lives |
| [`docs/adr/`](docs/adr/) | Decisions that bind more than one repository and that no single repository owns |

## The three kinds of state

| State | One home |
|---|---|
| Planned: what is being built, and where it stands | The [OpenGWAS project board](https://github.com/orgs/opengwas/projects/1) |
| Built: components, imports, decisions | This hub |
| Running: whether each service is up, and how loaded it is | The ops dashboard (ogdb-dashboard) |

## What every repository provides

- `docs/architecture/components.yaml`: its components, and the paths each one claims
- `CONTEXT.md`: its own terms. A term shared with another repository is in this hub's `CONTEXT.md`
- `docs/adr/`: its decisions, which can be empty. A citation that crosses repositories names the repository: `opengwasdb ADR 0039`

A repository missing one is drawn as a gap, never a failed build. Each
repository adds them when its next epic starts.

## Status

**Draft.** The repositories are named here as they are today. ogld is being
merged into opengwasdb ([ADR 0005](docs/adr/0005-opengwasdb-is-the-data-layer.md),
[the consolidation plan](docs/consolidation-plan.md)). The site itself (the
collector and the pages, now in opengwasdb-stores' `project_site`) moves here
afterwards.
