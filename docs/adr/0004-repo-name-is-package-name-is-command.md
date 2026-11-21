# Repository name = package name = command, and OpenGWASDB is retired

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
names to new. There are two exceptions.

- **The host directory `/data/opengwasdb/`.** It moves separately, once no run
  is writing there.
- **Names written inside the data.** These are labels that code looks up in
  Stores already built, not prose: the LD Store key `software.ogld`; the GWAS
  Store record keys `opengwasdb_version`, `opengwasdb_rev` and
  `opengwasdb_executable`; and the `opengwasdb.*` reader IDs in Release
  Bundles and inventories. Renaming them changes the format: every Store on
  `/data` would fail validation or lose its provenance. They keep their names
  in the current format versions, and each changes in its engine's next format
  version, when the Stores are rebuilt anyway.

## Considered options

- **`og-*-engine` repositories holding shorter package names.** Rejected: one exception per engine.
- **Renaming the repositories but not the packages.** Rejected: it leaves the mismatch the rename was meant to remove.
