# Every public Store downloads whole, as one Store Archive, through a signed link

OpenGWAS's pitch is "subscribe, download, keep, within source terms"
(opengwasdb-website decision 3), and a Local Source is "a directory holding one
or more Store Releases" (opengwasr ADR 0002). But no Store can be downloaded:
opengwasr "does not download Stores until an upstream distribution channel
exists", and ogdb-api's `gwasinfo/files` deliberately returns no links. This
decision is that channel. It binds opengwasdb-stores, ogdb-api, the build
server's deployment, opengwasr, opengwaspy and the website, and no one of them
owns it. Decided by the owner on 26 November 2026.

## Decision

**What is downloadable.** Every public GWAS Store Release, Genotype Store, LD
Store and LD Reference Panel, each as one **Store Archive**: a plain, uncompressed
`.tar` that holds the resource exactly as currently published, plus a
`release.json` stating its identity, release, source, the catalogue version it
was recorded in, and each source licence with a link to the provider's terms
(website decision 3: link the terms, never paraphrase them). A resource is
downloadable when its catalogue row says `access_posture = public`; the
`stores` table already has that column, and `ld_resources` gains it. No licence
string is parsed to decide.

**What an archive holds and how it unpacks.**
- A GWAS Store Release: `OGS-<id>-<release_id>.tar`, unpacking to
  `OGS-<id>/store.opengwasdb/` and `OGS-<id>/release.json`. `release_id` is
  the one in the Store's `manifest.json`, so a rewrite under the same OGS id
  (as on 25–26 November 2026) gives a new archive name. Only the current
  release has an archive; a rewrite builds the new one and deletes the old.
  Only `store.opengwasdb/` is archived, never `records/`, `replaced/`, `work/`
  or `tmp/`.
- An LD resource: `OGL-<id>.tar`, unpacking to `OGL-<id>/…` and
  `OGL-<id>/release.json`. These are immutable and a rebuild gets a new OGL
  id, so the id alone names the bytes.
- A Genotype Store's pgen filesets live beside its sidecar, not inside it
  (`../pgen/chr1.pgen`, recorded relative to the sidecar root; opengwasdb
  ADR 0100). Its archive holds the sidecar and the files it names, at the same
  relative paths, so it resolves after unpacking.
- The reader checks each pgen's size and nanosecond mtime on open (ADR 0100),
  so archives are written in the **pax** format, which keeps sub-second
  mtimes; GNU tar's default format keeps whole seconds and would make every
  unpacked Genotype Store refuse to open.
- Unpacking several archives into one directory never collides, and that
  directory is a Local Source.

**Who does what.**
- **opengwasdb-stores** builds each archive from the resource's stable,
  read-only copy (never a work or scratch directory) into
  `/data/opengwasdb/downloads/<id>/`, a directory that holds nothing but
  archives, with its SHA-256. It records each in the Analysis Catalog's
  `store_archives` table: `id` (OGS or OGL), `release_id` (NULL for an LD
  resource), `file`, `bytes`, `sha256`, `created_at`.
- **ogdb-api**, behind the gateway like every other call, hands an
  authenticated user a link to one archive: it checks the resource is public
  and has an archive, reports the request's cost to the gateway, and signs a
  URL with a secret it shares with the download host. Whether a download
  counts against a user's allowance is the gateway's call. The link lasts
  24 hours, long enough for the largest archive on a modest connection.
- **The download host** is an nginx on the build server, at a hostname of its
  own, that serves `/data/opengwasdb/downloads/` and nothing else. Its
  `secure_link` module checks each request's signature and expiry against the
  shared secret, then serves the file from disk with byte ranges, so `curl -C -`
  and `wget -c` resume until the link expires and a fresh link resumes the
  same file. The secret rotates the way ogdb-api's gateway key does, with an
  old and a new secret accepted for a while. A short request id in the signed
  URL lets the host's log say which request downloaded what, with no personal
  data in the URL.
- **opengwasr and opengwaspy** gain a function that asks ogdb-api for a link,
  downloads, verifies the SHA-256 and unpacks into a Local Source.
- **The website** shows each archive's file, size, release, date and SHA-256 on
  the page of the resource it holds, from `store_archives`, and says on its
  Download tab how downloading works. It names no endpoint, function or token
  (website decision 15).

**The LD resources, before any archive.** The five HGDP+1kGP LD Stores are
retired: their Genotype Stores answer as well at a fraction of the size. They
and the Partner Rows reference built from the EUR one are deleted from
`ld_resources` and the remaining rows renumbered, which is safe because
nothing has been released yet. panukb-EUR-k15 stays. The UK Biobank LD
Reference Panel carries the same licence as panukb-EUR-k15: per-block
eigendecompositions hold no individual-level data.

## Consequences

- **Disk.** Each archive is a second copy, about 1.7 TB for what is listed
  today (GWAS Store Releases 794 GB, panukb-EUR-k15 675 GB, LD Reference
  Panels about 200 GB, Genotype Stores about 30 GB), on a filesystem with
  16 TB free. Store data is already zstd-compressed, so the tar is not.
- **The build server must be reachable from the internet** at the download
  host's name: DNS, a TLS certificate and a firewall opening from University
  IT. Every download leaves through the University's network.
- **A link works for whoever holds it until it expires**, as the legacy
  service's Object Storage links do. Locking it to an IP address would break
  users behind changing addresses and proxies.
- **opengwasdb ADR 0094's static-Zarr ruling** applied to the HGDP+1kGP LD
  Stores, which are retired; reading a Store in place over HTTP, without
  downloading it, stays a separate question.
- **opengwasdb ADR 0100** said publishing individual-level data was not
  authorised by that ADR. Publishing Genotype Stores, whose pgens are
  individual-level genotypes of a public panel, is authorised here.
- **Moving the website** (website decision 14, #5) moves no archive: the
  links point at the download host, not at opengwas.io.

## Considered options

- **Object Storage with pre-authenticated links**, as the legacy service
  serves GWAS-VCFs (Oracle Cloud, links of 2 hours). It needs an upload of
  every archive, cloud storage and egress costs, and object-storage tooling the
  build server lacks. The contract here, an API that returns an expiring URL,
  lets a bucket replace the download host later without changing clients.
- **Serving the Store directories as they are**, with a file list. No second
  copy, but up to 30,000 files a Store and a fetch tool no client has.
- **A zip streamed on the fly** (nginx `mod_zip`). No second copy, but the
  container's nginx lacks the module, and a 675 GB stream is fragile to
  resume.
- **nginx `auth_request`**, asking ogdb-api on every request. It puts the API
  in the path of every resumed range and needs the user's token on each
  request.
- **Public downloads with no account.** Simpler, but the platform's terms and
  allowance apply to downloads as to queries.
- **Databricks** (Delta Sharing, Marketplace) was researched
  ([`docs/databricks.md`](../databricks.md)): it adds no cheap storage, shares
  Store directories only with other Databricks customers, and leaves billing
  to the provider. It may be an extra channel for licensees later, not this one.
