# One Data API serves GWAS and LD

The Data API (ogdb-api) serves GWAS Store queries and LD Store queries (clump, proxies,
matrices) as jobs in one queue, with one results cache, behind one gateway
route. There is no separate LD API; the empty ogld-api repository is deleted. LD
queries are often one step of a GWAS query (clumping top hits, finding proxies
for missing variants), and two services would have meant two queues, two
caches and two sets of credentials for one analysis.

If LD lookups ever need answers faster than a job queue gives, the fast path is
added inside the Data API, not as a second service. Both read through one
query package, ogquery ([ADR 0005](./0005-opengwasdb-is-the-data-layer.md)).
