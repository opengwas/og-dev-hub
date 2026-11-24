# Repository name = package name = command, and OpenGWASDB is retired

> **Superseded by [ADR 0005](./0005-opengwasdb-is-the-data-layer.md)** (owner, 22 November 2026).
> No repository is renamed under this ADR. ogld merges into opengwasdb instead,
> "OpenGWASDB" names the data layer, and the names below were never adopted.

Each repository's name is the name of the package it installs and of the
command it provides, and the import name is the same with `_` in place of `-`.
For example, `og-ld` is installed as `og-ld`, imported as `og_ld` and run as
`og-ld`. Its environment variables start `OG_LD_`. The engines are `og-gwas`
and `og-ld`, each paired with a `-stores` repository. Being an engine is
recorded in `system.yaml`, not in the name. opengwaspy and opengwasr keep their
names, which users already install.

The old names mixed `ogld`, `opengwasdb`, `ogstores` and `ogdb` across
repositories, packages and environment variables. ogld even read one
`OGDB_`-prefixed variable. "OpenGWASDB" named the GWAS data system, the engine
and the whole platform, in different places. Every mismatch between a
repository, its package and its command was something agents and people had to
work out.

"OpenGWASDB" is retired. "OpenGWAS" is the whole platform, and "legacy
OpenGWAS" is the service in production today. OpenGWAS is pre-release, so the
rename rewrites every old name, ADR bodies included, rather than mapping old
names to new. The one exception is the host directory `/data/opengwasdb/`,
which moves separately, once no run is writing there.

## Considered options

- **`og-*-engine` repositories holding shorter package names.** Rejected: one exception per engine.
- **Renaming the repositories but not the packages.** Rejected: it leaves the mismatch the rename was meant to remove.
