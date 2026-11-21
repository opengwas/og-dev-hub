# Working in og-dev-hub

Read [README.md](./README.md) first. This repository holds only what no single
OpenGWAS repository owns. Before adding anything here, check whether a
repository owns it ([ADR 0001](docs/adr/0001-dev-hub-collects-and-owns-nothing.md),
[ADR 0002](docs/adr/0002-adrs-and-glossaries-live-with-their-owner.md)). If one
does, the change goes there.

- `CONTEXT.md` holds only terms that cross repositories. A term one repository owns stays in that repository's `CONTEXT.md`.
- An ADR here binds more than one repository and has no single owner.
- `system.yaml` has one container per thing that is deployed or published. A new service is a pull request here; a new module is a pull request in its own repository.
- Never commit to `main` directly. Open a pull request.
