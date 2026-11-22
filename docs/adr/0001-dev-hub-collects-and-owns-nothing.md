# The Dev Hub collects and owns nothing

OpenGWAS spans a dozen repositories, and its architecture, epics and Store
inventories had no one place to be seen. We decided that og-dev-hub *draws*
them, and owns none of them:
- each repository claims its own components (`docs/architecture/components.yaml`);
- the GWAS Store Registry and the LD Store Registry live in opengwasdb-stores,
  where the pull request that builds a Store also records it;
- epic records stay in each epic's own repository;
- the hub measures the rest (size, imports, which ADRs cite what) from the code.

The hub writes by hand only what no single repository owns: `system.yaml` (the
people, external systems, containers and how they relate), the glossary of
terms that cross repositories, and the ADRs with no single owner.

A record of how the system is built that someone has to keep up to date by
hand goes stale while still looking correct. Every gap the hub finds (a
missing file, a path no component claims, a claim that matches no code) is
shown as a gap on the site. It never fails the build, because one repository
falling behind must not stop the others being drawn.

The three kinds of state each have one home:
- planned state is on the OpenGWAS project board;
- built state is in the Dev Hub;
- running state is on the ops dashboard (ogdb-dashboard).

None of them copies another.

## Considered options

- **A repository with the whole architecture written by hand.** Rejected: nothing fails when it drifts.
- **Two hubs, one for engineering and one for data.** Rejected: both would read the same repositories, and readers would have to know which one to open.
- **The site staying inside the GWAS Stores repository.** Rejected: its scope became the whole platform, and the LD side would have had to depend on the GWAS side.
