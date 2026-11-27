# OpenGWAS

The whole platform: its data systems, the services that serve them, and the
clients and sites that read them. This glossary holds only the terms that cross
repositories; each repository's `CONTEXT.md` holds its own.

## The platform

**OpenGWAS**:
The whole platform: every data system, service, client and site the
organisation builds.
_Avoid_: OpenGWASDB, when the whole platform is meant; "the platform" in
writing that will outlive the conversation.

**OpenGWASDB**:
The data layer of OpenGWAS: the engine that builds and validates GWAS Stores
and LD Stores and owns both formats, the Stores themselves, and their
registries. Not the services, clients or sites that read it.
_Avoid_: OpenGWASDB for the whole platform; OpenGWASDB for the GWAS side alone.

**Legacy OpenGWAS**:
The OpenGWAS service in production today, which ieugwasr and ieugwaspy call,
until OpenGWAS replaces it.
_Avoid_: bare "OpenGWAS" for the production service; "the old API".

**Dev Hub**:
The developers' view of OpenGWAS's built state: the GWAS Stores and LD Stores,
the architecture, and the decisions and terms that shape them. It collects all
of these from the repositories that own them and owns none. It shows no planned
state, which is the project board's, and no running state, which is the
operations dashboard's.
_Avoid_: project site, architecture site.

## Data

**GWAS Store**:
Short for OpenGWAS GWAS Store: a published, versioned body of harmonised GWAS
summary statistics, one `OGS-*` Store Release (defined in opengwasdb's
`CONTEXT.md`, where it is a bare "Store").
_Avoid_: bare "Store", OGS Store, Summary Store, in writing that crosses
repositories.

**LD Store**:
Short for OpenGWAS LD Store: the published LD of one Source Panel on one
Reference Assembly (defined in ogld's `CONTEXT.md` until ogld merges into
opengwasdb). Not a kind of GWAS Store:
the two share a word and nothing else.
_Avoid_: bare "Store" in writing that crosses repositories; LD panel; LD
Reference Panel, which is the engine's per-block resource for reference
completion.

**Store Archive**:
The single file that holds one public GWAS Store Release, LD Store, Genotype
Store or LD Reference Panel exactly as currently published, with a file stating
its identity, provenance and licences. There is at most one current Store
Archive per resource ([ADR 0006](docs/adr/0006-every-public-store-downloads-whole-through-a-signed-link.md)).
_Avoid_: store tarball, whole-store download, store bundle (a Release Bundle
is something else).

**ALID**:
Short for Alphabetic Variant ID: the variant key every GWAS Store and LD Store
shares, `chr:pos:A1:A2`, defined in opengwasdb's `CONTEXT.md` (Variant
Identity). Identity across repositories is the pair (Reference Assembly, ALID),
and `A1` is the allele every effect and every LD r is signed against. The name
comes from pleiodb, where `A1` was always the alphabetically first allele. That
still holds for two alleles of one length, but a GWAS Store's indel puts the
source's reference allele first (opengwasdb ADR 0079), so "alphabetic" names
where the key came from, not a rule every ALID follows.
_Avoid_: variant id, SNP id, chrpos, in writing that crosses repositories.

## The three kinds of state

**Planned state**:
What is being built, and where each thread stands. Recorded only on the
OpenGWAS project board.

**Built state**:
The components each repository holds and how they depend on one another,
claimed by each repository and measured from its code.

**Running state**:
Whether each deployed service is up, and how loaded it is. Shown only by the
operations dashboard.
