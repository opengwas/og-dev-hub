# OpenGWAS

The whole platform: its data systems, the services that serve them, and the
clients and sites that read them. This glossary holds only the terms that cross
repositories; each repository's `CONTEXT.md` holds its own.

## The platform

**OpenGWAS**:
The whole platform: every data system, service, client and site the
organisation builds.
_Avoid_: OpenGWASDB (a retired name with no referent); "the platform" in
writing that will outlive the conversation.

**Legacy OpenGWAS**:
The OpenGWAS service in production today, which ieugwasr and ieugwaspy call,
until OpenGWAS replaces it.
_Avoid_: bare "OpenGWAS" for the production service; "the old API".

**Dev Hub**:
The developers' view of OpenGWAS: its built state with the planned state drawn
over it, the epics, and the inventories of GWAS Stores and LD Stores. It
collects all of these from the repositories that own them and owns none.
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
Reference Assembly (defined in ogld's `CONTEXT.md`). Not a kind of GWAS Store:
the two share a word and nothing else.
_Avoid_: bare "Store" in writing that crosses repositories; LD panel; LD
Reference Panel, which is the engine's per-block resource for reference
completion.

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
