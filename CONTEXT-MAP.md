# Context map

Each repository's own terms are in its `CONTEXT.md`. Terms that cross
repositories are in this hub's [CONTEXT.md](./CONTEXT.md).

| Repository (after the rename) | Today | Glossary |
|---|---|---|
| og-gwas | opengwasdb | `CONTEXT.md`: Store, Store Release, Analysis, Store Encoding, LD Reference Panel, ... |
| og-gwas-stores | opengwasdb-stores | `CONTEXT.md`: Store Release, Release Bundle, Manifest Generation, Analysis Resolution, Reference Completion, ... |
| og-ld | ogld | `CONTEXT.md`: LD Store, Source Panel, Near Band, Proxy Index, Far Pairs, ... |
| og-ld-stores | *(new)* | *missing* |
| og-data-api | ogdb-api | *missing* |
| og-gateway | opengwas-gateway | *missing* |
| og-website | opengwasdb-website | *missing* |
| og-ops-dashboard | ogdb-dashboard | *missing* |
| og-agent-skills | agent-skills | *missing* |
| opengwaspy | opengwaspy | *missing* |
| opengwasr | opengwasr | *missing* |

## Where contexts meet

- **og-gwas ↔ og-gwas-stores:** og-gwas owns the GWAS Store format. og-gwas-stores reads the engine's CLI, its JSON, its manifest columns and its artifact formats, so a change to any of these carries its og-gwas-stores update in the same epic.
- **og-ld ↔ og-ld-stores:** og-ld owns the LD Store format. og-ld-stores builds LD Stores with it and records them in the LD Store Registry.
- **og-gwas ↔ og-ld:** two LD artefacts come from the same HGDP+1kGP panels: og-gwas's LD Reference Panel, used for Reference Completion, and og-ld's LD Stores. The two share panels and nothing else.
- **og-data-api ↔ both engines:** it serves GWAS Store and LD Store queries as jobs ([ADR 0003](docs/adr/0003-one-data-api-serves-gwas-and-ld.md)).
