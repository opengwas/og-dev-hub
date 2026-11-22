# Context map

Each repository's own terms are in its `CONTEXT.md`. Terms that cross
repositories are in this hub's [CONTEXT.md](./CONTEXT.md).

| Repository | Glossary |
|---|---|
| opengwasdb | `CONTEXT.md`: Store, Store Release, Analysis, Store Encoding, LD Reference Panel, ... Gains ogld's terms when ogld merges in |
| opengwasdb-stores | `CONTEXT.md`: Store Release, Release Bundle, Manifest Generation, Analysis Resolution, Reference Completion, ... |
| ogld *(merging into opengwasdb)* | `CONTEXT.md`: LD Store, Source Panel, Near Band, Proxy Index, Far Pairs, ... |
| ogquery *(new, opengwasdb#450)* | *missing* |
| ogdb-api | *missing* |
| opengwas-gateway | *missing* |
| opengwasdb-website | *missing* |
| ogdb-dashboard | *missing* |
| agent-skills | *missing* |
| opengwaspy | *missing* |
| opengwasr | *missing* |

## Where contexts meet

- **opengwasdb ↔ opengwasdb-stores:** opengwasdb owns both Store formats.
  opengwasdb-stores reads the engine's CLI, its JSON, its manifest columns and
  its artifact formats, so a change to any of them carries its
  opengwasdb-stores update in the same epic.
- **Inside opengwasdb, GWAS ↔ LD:** both kinds of Store use one variant
  identity, owned by `opengwasdb.variants`. Two LD artefacts come from the same
  HGDP+1kGP panels: the LD Reference Panel, used for Reference Completion, and
  the LD Stores. They share panels and nothing else.
- **ogquery ↔ opengwasdb:** ogquery reads both formats. opengwasdb's builder
  and validator read through it, so there is one read path.
- **ogdb-api ↔ ogquery:** the Data API serves GWAS Store and LD Store queries
  as jobs ([ADR 0003](docs/adr/0003-one-data-api-serves-gwas-and-ld.md)).
