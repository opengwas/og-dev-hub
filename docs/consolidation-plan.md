# Consolidating OpenGWASDB

The plan for [ADR 0005](adr/0005-opengwasdb-is-the-data-layer.md), tracked by
epic opengwas/og-dev-hub#2. OpenGWASDB becomes the data layer of OpenGWAS:

| Repository | Holds | After |
|---|---|---|
| **opengwasdb** | the one engine: GWAS Stores and LD Stores, both formats, the one variant identity (`opengwasdb.variants`) | gains ogld as `opengwasdb.ld`; commands `opengwasdb ld …`; `OPENGWASDB_LD_*` |
| **opengwasdb-stores** | both Store Registries, every build recipe and their release evidence | gains the LD recipes and the LD Store Registry |
| **ogquery** *(new)* | the one light read path for both kinds of Store | opengwasdb#450 |
| ogld | — | archived; its open issues move to opengwasdb |
| ogld-api | — | deleted (empty) |
| ogdb-api, opengwas-gateway, ogdb-dashboard, opengwasdb-website, opengwaspy, opengwasr, agent-skills | unchanged | each moves its pins, from `ogld` and `opengwasdb` to `opengwasdb` and later to `ogquery`, when its owner chooses |

## The order

1. **One licence:** opengwas/opengwasdb#452. opengwasdb and opengwasdb-stores
   move from the Sustainable Use License to GPL-3.0-only, with the CLA. This is
   the owner's commit.
2. **ogld merges into opengwasdb:** opengwas/opengwasdb#453. It waits for
   opengwas/ogld#88's Pan-UKB import to finish.
   - The code moves under `opengwasdb/ld/`, with its history kept.
   - `ogld.identity` gives way to `opengwasdb.variants`.
   - ogld's ADRs are renumbered into opengwasdb's sequence.
   - `test-realdata` passes on the IEU compute nodes, and every LD Store
     already built still validates.
3. **The LD builds and the LD Store Registry move to opengwasdb-stores:**
   opengwas/opengwasdb-stores#496.
4. **ogld is archived:** opengwas/ogld#101. Its open issues transfer once no
   orchestrate run names them. Archiving is the owner's setting.
5. **ogquery:** opengwas/opengwasdb#450 reads both kinds of Store, and
   opengwasdb's builder and validator read through it.

## What keeps its name

- `opengwasdb`, `opengwasdb-stores`, the `ogstores` package and its
  `OGSTORES_*` variables.
- The names written inside GWAS Stores: `opengwasdb_version`, `_rev`,
  `_executable`, and the `opengwasdb.*` reader IDs.
- `/data/opengwasdb/`.
- The LD Store key `software.ogld`, until the next LD Store format version,
  when it becomes `software.opengwasdb`.

## What a developer does

Nothing, until #453 merges. After that:
- `ogld …` becomes `opengwasdb ld …`;
- `import ogld` becomes `import opengwasdb.ld`;
- `OGLD_*` becomes `OPENGWASDB_LD_*`.

A clone of ogld stays usable, read-only, once the repository is archived.
