# ADRs and glossaries live with their owner

An ADR lives in the repository that owns what it decides, as a component lives
in the repository that owns its code. A decision binding opengwasdb-stores to the
GWAS Store format lives in opengwasdb, which owns the format. og-dev-hub holds
only:
- decisions with no single owner;
- the glossary of terms that cross repositories;
- a map of every repository's `CONTEXT.md`;
- a generated index of every ADR in every repository.

A citation that crosses repositories names the repository (`opengwasdb ADR 0039`),
because the same number means different things in different repositories.

Agents work in one checkout. They load that repository's `CONTEXT.md` and ADRs
from the clone they already have, and a decision changes in the same pull
request as the code it governs. Putting every ADR in the hub would mean a
second clone for every lane and a second pull request for every decision.
`hub-audit` and the hub's index are how an agent finds a decision held in
another repository.

## Considered options

- **Every ADR and glossary in the hub.** Rejected for the reasons above.
- **A cross-repository decision recorded in each repository it touches.** Rejected: the copies drift apart.
