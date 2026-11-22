# OpenGWASDB is the data layer: one engine, one registry, one query package

OpenGWAS has two kinds of Store, GWAS Stores and LD Stores, and they were
built by two engines in two repositories (opengwasdb and ogld). The two
already share their variant identity. ogld's `identity` module reimplemented
opengwasdb's ALID and orientation rules ("ogld must form exactly the engine's
ALID"), so two copies of one rule were kept in step by hand across
repositories. opengwasdb-stores already held LD reference resources and LD
release evidence.

We consolidate the data layer, which is what "OpenGWASDB" now names:

- **opengwasdb** is the one engine. It builds and validates GWAS Stores and
  LD Stores, owns both formats, and holds the one owner of ALIDs and
  orientation (`opengwasdb.variants`). ogld's code becomes the `opengwasdb.ld`
  subpackage, its commands become `opengwasdb ld …`, and its environment
  variables become `OPENGWASDB_LD_*`. ogld's ADRs join opengwasdb's single
  number sequence, each noting its old number. Each format keeps its own
  format version.
- **opengwasdb-stores** is the one registry. It holds the GWAS Store Registry
  and the LD Store Registry, the build recipes for both, and their release
  evidence.
- **ogquery** is the one light query package for both kinds of Store
  (opengwasdb#450). Its core depends on numpy, zarr and numcodecs only. Reading
  over HTTP and Genotype Stores are optional extras. The Data API, opengwaspy
  and opengwasr read through it.
- **ogld is archived, not deleted.** Its open issues move to opengwasdb, and
  its history stays readable.

All of it is licensed GPL-3.0-only with the CLA. opengwasdb and
opengwasdb-stores move from the Sustainable Use License before any code moves.

Names change only where the merge needs them. `opengwasdb`, `opengwasdb-stores`
and `ogstores` keep their names, and so do the names written inside GWAS
Stores (`opengwasdb_version` and the `opengwasdb.*` reader IDs). The LD Store
key `software.ogld` becomes `software.opengwasdb` in the next LD Store format
version. Repositories that other people own (ogdb-api, opengwas-gateway,
ogdb-dashboard, opengwasdb-website, opengwaspy) are not asked to change. They
move their pins when they choose, and `ogdb-api` now reads as "the OpenGWASDB
API".

## Considered options

- **A separate engine and registry for each kind of Store (og-gwas, og-ld,
  og-gwas-stores, og-ld-stores), and every repository renamed (ADR 0004).**
  Rejected. It tidied names but kept the boundary that duplicates variant
  identity. It renamed names written inside the data. And it asked every other
  team to rename.
- **ogld moved to the Sustainable Use License.** Rejected. It contradicts
  opengwasdb#450 ("GPL-3.0-only like all OpenGWAS software"), and it would need
  every CLA signer's agreement.
- **ogld's ADRs kept under their own numbers in `docs/adr/ld/`.** Rejected.
  "ADR 0004" would mean two things in one repository.

## Consequences

- One release cycle covers both engines: an LD change bumps opengwasdb's
  version, and a consumer moves one pin, not two.
- The test suite grows. Each area carries its own test markers, so a change to
  one area runs that area's suite, and the default test tier stays within its
  time budget.
