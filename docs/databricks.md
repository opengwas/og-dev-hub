# Databricks for distributing and querying Store Releases

Date: 2026-11-26. All web pages and price lists were read on this date. Prices are list
prices in USD and exclude tax. Figures marked "my arithmetic" are calculations from the cited
prices, not quoted figures.

Note: Databricks' docs now call Delta Sharing "OpenSharing" in many places. Both names mean
the same thing here.

## Answer

- **(1) Can ogquery run inside Databricks? Probably yes, if the release is copied in, but
  the current catalogue needs opengwasdb rather than ogquery, and nothing has been tested.**
  ogquery needs only numpy, zarr and numcodecs on Python 3.12 or later. Serverless
  environment versions 3 to 6 ship Python 3.12.3. But ogquery opens local paths only.
  The catalogue lists all 13 Store Releases as format 0.2.x, which ogquery refuses on its
  own, but on disk every one was rewritten to 0.3.0 on 25–26 Nov 2026 (see below), so
  ogquery alone should read them once the catalogue catches up.
- **Untested risks on `/Volumes`:** reading through the FUSE path should work for
  sequential and ranged reads. Databricks does not document mmap or SQLite on volumes. Both
  are on the read path (`np.load(mmap_mode="r")` and `index.sqlite`), so both need a test.
- **Delta Sharing can share the Store directory itself only to other Databricks customers.**
  Volume sharing is Databricks-to-Databricks only. Open sharing, and the open Delta Sharing
  protocol, carry tables only. Recipients outside Databricks would need a tabular (Delta)
  export of the data, which is new work.
- **(2) Cheap hosting: Databricks adds no cheap storage.** The data sits in the provider's
  own S3/ADLS/GCS account, or in Databricks "default storage" billed per DSU. The provider
  pays for storage and egress, and each recipient pays for its own compute.
- **Cost comparison for 800 GB:** about $12/month on Cloudflare R2 with zero egress, against
  about $19/month on S3 London plus $0.09/GB egress (my arithmetic). Oracle Cloud costs
  about $20/month, and its first 10 TB of egress each month is free.
- **R2 can feed Delta Sharing for tables.** Databricks documents R2 as an egress-free
  source. Whether a *volume* on R2 can be shared is not documented (unverified).
- **(3) Cost recovery: Marketplace can list the data but does not take payment.** It
  supports paid and private listings, approval of each request, and terms and licence URLs.
  Databricks takes no revenue share, and all payment happens directly between provider and
  consumer, outside Databricks. That suits OpenGWAS's commercial licence: the licence stays
  OpenGWAS's own contract, and Marketplace is only a delivery channel.
- **Recommendation:** keep authenticated downloads from OpenGWAS's own host, with R2 (or
  OCI's free 10 TB) for egress, as the primary channel. Treat Databricks as an optional
  channel for Databricks-using licensees: a private, approval-only Marketplace listing of a
  shared volume. Do this only after testing ogquery and opengwasdb on `/Volumes`.

## 1. Running ogquery / opengwasdb inside Databricks

### What the code needs

- **ogquery** (branch `orch/520/497`; `main` holds only the initial commit) depends on
  `numpy>=2.0,<2.5`, `zarr>=3.4,<4` and `numcodecs>=0.17`, on Python `>=3.12`
  (`ogquery/pyproject.toml`, `dependencies`). It imports no pysam or `sqlite3`
  (`ogquery/README.md`, "Dependencies"). Paths are relative to
  `/data/opengwasdb/work/orchestrate/opengwasdb-stores-520/worktrees/497-ogquery`.
- **ogquery reads local paths only.** Its one Zarr open is
  `LocalStore.open(root=Path(path), ...)` (`ogquery/arrays.py:169`). Sidecars and indexes are
  memory-mapped with `np.load(..., mmap_mode="r")` (`ogquery/npy_sidecar.py:187,202`,
  `ogquery/variant_axis.py:242`, `ogquery/release.py:223`). `analyses.tsv` and
  `manifest.json` are opened as `Path` objects. Nothing in it accepts a URL or an fsspec
  path.
- **ogquery refuses 0.2.x and 0.1.0 releases on its own.** It raises
  `VariantTableReaderRequired` (`ogquery/release.py:63`) because those formats answer
  variants from `variants.tsv.gz` through pysam. Only a 0.2.3 release can be rewritten to
  0.3.0 with `ogdb rewrite-release`. Earlier ones must be rebuilt (`ogquery/README.md`).
- **The current catalogue is all 0.2.x.** Catalogue `c11c4f5b333f08d6`, built 2026-11-26,
  lists 13 Store Releases: eight 0.2.0, four 0.2.1 and one 0.2.3. Together they hold
  797.7 GB, from 0.17 GB to 167.8 GB each
  (`/data/opengwasdb/stores/catalog/current/stores.tsv`, columns `format_version` and
  `store_bytes`). **This is stale:** every listed store was rewritten in place to format
  0.3.0 on 25–26 Nov 2026 (`opengwasdb rewrite-release --convert-legacy`; each
  `store.opengwasdb/manifest.json` now says `format_version` 0.3.0, checked 2026-11-26),
  after this catalogue was built. So ogquery alone should read today's stores; the
  opengwasdb notes below apply to copies made before the rewrite.
- **opengwasdb** (`pip install opengwasdb`, Linux; `opengwasdb/README.md:39`)
  adds pysam, scipy, pandas, scikit-learn, pyliftover, fsspec and aiohttp
  (`opengwasdb/pyproject.toml`, `dependencies`).
  - `query_store(path)` (`opengwasdb/query/__init__.py:27`) calls `open_store`
    (`opengwasdb/store/open.py:853`), which is documented as opening "a local Store Release
    directory".
  - It opens `index.sqlite` as a `file:` URI with `?mode=ro`
    (`opengwasdb/variants/legacy_table.py:79-80`) and the tabix file with
    `pysam.TabixFile(str(path))` (`legacy_table.py:133`).
  - Reads take no `flock`. Only writers lock (`opengwasdb/store/open.py:449-480`).
- **Only LD Stores can be opened from a URL today.** They open from a local path or an
  HTTP(S) URL through fsspec's HTTP filesystem (`opengwasdb/ld/store/location.py:1-7`). No
  GWAS Store reader goes through that code, so **a GWAS Store opens only from a local
  path.**

### What Databricks provides

- **Python version:** serverless environment versions 3 to 6 run Python 3.12.3, and 1 and 2
  run 3.10 and 3.11 ([env versions](https://docs.databricks.com/aws/en/release-notes/serverless/environment-version/)).
  So ogquery's `>=3.12` floor needs environment 3 or later.
- **Installing packages:** serverless installs dependencies in "any format that is valid in
  a requirements.txt file", including from private indexes through `index-url`. Wheels with C
  extensions must match the architecture, `aarch64` or `x86_64`
  ([serverless dependencies](https://docs.databricks.com/aws/en/compute/serverless/dependencies)).
  - numpy, numcodecs and pysam all have C extensions. Whether pysam has a wheel for every
  serverless architecture is unverified.
  - Do not install anything that pulls in PySpark (same page).
  - Notebook-scoped `%pip` installs must be repeated in each new session
    ([serverless limitations](https://docs.databricks.com/aws/en/compute/serverless/limitations)).
- **Network:** serverless egress follows a workspace network policy, either "Full access" or
  "Restricted access". Under restricted access, package indexes and storage hosts must be
  allow-listed
  ([network policies](https://docs.databricks.com/aws/en/security/network/serverless-network-security/manage-network-policies)).
- **Volumes give POSIX-style `/Volumes/<catalog>/<schema>/<volume>/...` paths** for tools
  that need FUSE ([files](https://docs.databricks.com/aws/en/files/);
  [volume files](https://docs.databricks.com/aws/en/volumes/volume-files)). Documented
  limits:
  - "Direct-append or non-sequential (random) writes are not supported", and sparse files
    are not supported. Neither matters for read-only queries.
  - Uploads through the UI are limited to 5 GB per file. Otherwise files can be "up to the
    maximum size supported by the underlying cloud storage".
  - No file-count limit is documented.
  - **No page mentions mmap or SQLite on volumes (unverified).**
- **Where FUSE works:** on standard access mode, FUSE on volumes from executors needs
  Runtime 14.3 or later. Older runtimes allow it from the driver only.
  "Unity Catalog UDFs can't access volume file paths." Volumes cannot be read from RDDs
  ([volumes](https://docs.databricks.com/aws/en/volumes/)).
  - Serverless supports only Spark Connect APIs, with no RDDs.
  - PySpark UDFs on serverless have a fixed 1 GiB memory limit per sandbox
    ([serverless limitations](https://docs.databricks.com/aws/en/compute/serverless/limitations)).
- **Cloud URIs:** "File operations requiring FUSE data access cannot directly access cloud
  object storage using URIs". Databricks recommends volumes instead. DBFS root and mounts are
  deprecated ([files](https://docs.databricks.com/aws/en/files/)).
- **Files API:** volumes can be read over the REST Files API
  (`GET /api/2.0/fs/files{path}`), which supports `Range`
  ([Files API](https://docs.databricks.com/api/workspace/files/download)). It is a workspace
  API, so a caller needs a workspace identity (inferred from the API's scope, not stated).
  Databricks bills Files API egress to clients when the transfer crosses regions or goes to
  the public internet
  ([networking costs](https://docs.databricks.com/aws/en/security/network/serverless-network-security/cost-management)).

### Delta Sharing and non-tabular files

- **Volume sharing is supported only in Databricks-to-Databricks sharing.** It needs SQL
  warehouse 2023.50 or later, or Runtime 14.1 or later
  ([create share](https://docs.databricks.com/aws/en/delta-sharing/create-share)).
  "Databricks-to-Databricks also supports notebook, volume, model … sharing, which is not
  available in Databricks-to-Open sharing"
  ([Delta Sharing](https://docs.databricks.com/aws/en/delta-sharing/)).
- **The open protocol covers tables only.** Its REST API has share, schema and table
  endpoints and nothing for files or volumes
  ([PROTOCOL.md](https://github.com/delta-io/delta-sharing/blob/main/PROTOCOL.md),
  "REST APIs").
- **What recipients can do with a shared volume** is listed as `DESCRIBE VOLUME`, `LIST`,
  `SELECT * FROM <format>.'<path>'` and `COPY INTO`. It is read-only
  ([read shared data](https://docs.databricks.com/aws/en/delta-sharing/read-data-databricks)).
  **Whether a recipient's Python can `open()` or mmap a shared volume through `/Volumes` is
  not documented (unverified).** ogquery depends on exactly that.

### What would have to change in OpenGWAS code

From least to most work:

1. **Nothing, if a user copies or downloads a release into a volume** and FUSE behaves like
   a local disk for mmap. Test this first, on one small release (0.17 GB),
   on serverless and on a classic cluster.
2. **SQLite on FUSE.** Open `index.sqlite` with `immutable=1` as well as `mode=ro`
   (`legacy_table.py:79`). SQLite "skips all file locking and change detection on immutable
   database files" ([SQLite URI](https://www.sqlite.org/uri.html)). That avoids any FUSE
   locking problem, and a published release is immutable. The fallback is to copy
   `index.sqlite` to local disk.
3. **Done on disk, pending in the catalogue:** the stores are already 0.3.0, so ogquery alone
   (no pysam, no SQLite) reads them; the catalogue just needs rebuilding to say so
   (`ogquery/release.py:55-69`).
4. **Read from object storage or HTTPS without FUSE.** Give ogquery a store opener that
   accepts a URL, as `opengwasdb/ld/store/location.py` does:
   - `zarr.storage.FsspecStore` in place of `LocalStore` (`ogquery/arrays.py:169`);
   - ranged reads in place of `np.load(mmap_mode="r")` for the `.npy` sidecars;
   - fsspec opens for `manifest.json` and `analyses.tsv`.
   This only makes sense for 0.3.0 releases, because tabix and SQLite cannot run over HTTP.
   It would also let any client read straight from R2 or OpenGWAS's gateway, not just
   Databricks.
5. **Scale out across Spark (optional).** Add a `mapInPandas`/pandas-UDF wrapper that opens
   a release per executor on DBR 14.3 or later. It cannot be a Unity Catalog UDF, and on
   serverless the 1 GiB UDF memory limit applies.
6. **Open sharing to non-Databricks users.** Export associations to Delta/Parquet tables:
   long format, partitioned by Store and chromosome. This is a second, much larger
   representation of the data, and ogquery's query shapes would have to be re-expressed in
   SQL. It is a new product, not an adapter.

## 2. Hosting about 800 GB (and growing) on or beside Databricks

### Who pays for what

| Channel | Storage | Egress | Compute | Recipient must be a Databricks customer? |
|---|---|---|---|---|
| UC volume (external, own bucket) | provider, to its cloud | provider's cloud, cross-region or internet | the reader | n/a |
| UC default storage | provider, billed by Databricks in DSUs for storage and API operations; cloud credits do not apply ([default storage costs](https://docs.databricks.com/aws/en/admin/usage/default-storage)) | not stated | the reader | n/a |
| Delta Sharing, Databricks-to-Databricks | provider | provider, charged by the storage vendor; none within a region | the recipient, on its own serverless or classic compute ([Delta Sharing FAQ](https://docs.databricks.com/aws/en/delta-sharing/)) | yes, with a Unity Catalog workspace |
| Delta Sharing, open | provider | provider | the recipient's own tool; the provider pays for any filtering or views it computes ([Delta Sharing](https://docs.databricks.com/aws/en/delta-sharing/)) | no, but tables only |
| Marketplace | as for the share underneath | as for the share underneath | as above | the request is made in a workspace; volumes need a Unity Catalog consumer ([create listing](https://docs.databricks.com/aws/en/marketplace/create-listing), [Marketplace](https://docs.databricks.com/aws/en/marketplace/)) |

- **Provider requirements:** at least one Unity Catalog workspace
  ([Delta Sharing](https://docs.databricks.com/aws/en/delta-sharing/)). Marketplace also
  needs the Premium plan or above
  ([provider setup](https://docs.databricks.com/aws/en/marketplace/get-started-provider)).
- **Databricks' own pricing page** bills compute and says "Storage, networking and related
  costs will vary depending on the services you choose and your cloud service provider"
  ([pricing](https://www.databricks.com/product/pricing)).
- **The default storage rate could not be read.** The page renders its numbers client-side
  ([storage pricing](https://www.databricks.com/product/pricing/storage)), so the DSU rate is
  unverified.
- **Default storage limits sharing.** Assets other than tables can be shared only with
  Databricks recipients on the same cloud, using serverless compute
  ([default storage](https://docs.databricks.com/aws/en/storage/default-storage)). That
  rules it out for a cross-cloud volume share.
- **Cloudflare R2:**
  - "Databricks supports sharing from Cloudflare R2, which incurs no egress fees". Tables
    with V2 checkpoints or liquid clustering cannot be shared from R2
    ([Delta Sharing](https://docs.databricks.com/aws/en/delta-sharing/),
    [manage egress](https://docs.databricks.com/aws/en/delta-sharing/manage-egress)).
  - R2 can be a Unity Catalog external location for external tables and **external
    volumes**, on Runtime 14.3+ or SQL warehouse 2024.15+
    ([R2 external location](https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/external-locations-r2)).
  - **The egress guidance covers tables only. Sharing an R2-backed volume is not documented
    (unverified).**

### List prices (read 2026-11-26)

| Store | Region | Storage, per GB-month | Internet egress, per GB | Source |
|---|---|---|---|---|
| AWS S3 Standard | eu-west-2 London | $0.024 (first 50 TB) | first 100 GB/month free across all regions, then $0.09 (first 10 TB); $0.02 to another AWS region | AWS Price List API, `AmazonS3/current/eu-west-2` (published 2026-11-25) and `AWSDataTransfer/current/eu-west-2` (published 2026-11-19), [S3 pricing](https://aws.amazon.com/s3/pricing/) |
| AWS S3 Standard | us-east-1 | $0.023 (first 50 TB) | as above | same |
| Azure Blob / ADLS Gen2 Hot LRS | UK South | $0.0192 (first 50 TB) | first 100 GB free, then $0.087 (Microsoft network routing) or $0.08 (internet routing) | [Azure Retail Prices API](https://prices.azure.com/api/retail/prices) |
| Google Cloud Storage | — | not read: the page renders client-side (unverified) | not read (unverified) | [GCS pricing](https://cloud.google.com/storage/pricing) |
| Cloudflare R2 Standard | global | $0.015; 10 GB-month free | "no charges for egress bandwidth"; Class A $4.50 and Class B $0.36 per million requests | [R2 pricing](https://developers.cloudflare.com/r2/pricing/) |
| OCI Object Storage Standard | NA, Europe, UK | $0.0255; first 10 GB free | first 10 TB/month free, then $0.0085; requests $0.0034 per 10,000 after the first 50,000 | Oracle price list API (`apexapps.oracle.com/pls/apex/cetools/api/v1/products/`, parts B91628, B88327, B91627), [OCI networking pricing](https://www.oracle.com/cloud/networking/pricing/) |

Costs for 800 GB (my arithmetic, list prices, before tax):

| Store | Storage per month | One full 800 GB download | Ten full downloads a month (8 TB) |
|---|---|---|---|
| S3 London | about $19 | about $63 | about $711 |
| Azure UK South | about $15 | about $61 | not calculated |
| R2 | about $12 | $0 egress (pennies in requests) | $0 egress |
| OCI | about $20 | $0 | $0, inside the free 10 TB/month |

- **OCI:** the legacy OpenGWAS service already runs on an OCI VM
  (`docs/decisions.md:373-374`), so OCI's free 10 TB/month is an existing account's
  allowance.
- **On-premises university host:** cloud providers do not charge per GB for this. The costs
  are hardware, staff time and the university's network policy, and none of them are
  measured here (unverified).
  - The Bristol host that holds the catalogue is reachable only inside the University
    network and over VPN (`docs/decisions.md:365`). Public downloads from it would need a
    public proxy, which is already listed as a launch option (`docs/decisions.md:381`).

## 3. Cost recovery with commercial users

- **Listing types:**
  - **Public listings** need an application to the Data Partner Program. **Private
    exchanges** can be set up by an account admin, and "only consumers who are members of a
    private exchange" see their listings
    ([provider setup](https://docs.databricks.com/aws/en/marketplace/get-started-provider),
    [create listing](https://docs.databricks.com/aws/en/marketplace/create-listing)).
  - A listing is either instant, where consumers accept the terms and get access, or
    personalized. With a personalized listing the provider approves each request in the
    Provider Console and "must manage the business agreement with consumers outside of
    Databricks Marketplace" ([create listing](https://docs.databricks.com/aws/en/marketplace/create-listing)).
- **Price and payment:** Databricks hosts "both free and paid listings, but we don't take a
  cut of the revenue". There is "no fee for providers to list", and "Transactions for paid
  listings happen between consumers and providers directly"
  ([Databricks blog, 2024-11-11](https://www.databricks.com/blog/top-10-marketplace-questions-answered)).
  - The listing API has a `cost` field (free or paid) and a `pricing_model` field, such as
    subscription. It is Public Preview
    ([create-listing API](https://docs.databricks.com/api/marketplaces/v1/create-listing)).
  - **No Databricks checkout, price setting or payout exists.** The provider invoices the
    consumer itself.
- **Commit drawdown:** customers with a Databricks Universal Commit can put up to 10% of it
  toward eligible partner products through Marketplace, against a partner invoice
  ([Marketplace](https://docs.databricks.com/aws/en/marketplace/)). This is a Databricks
  partner programme. **Whether an academic provider could join is unverified.**
- **Terms and licence:** a listing can carry a public terms-of-service URL and a licence URL
  ([create listing](https://docs.databricks.com/aws/en/marketplace/create-listing)).
  - Provider policies require "Provider/Consumer Terms of use, such as those describing the
    license grant", ban Sensitive Personal Data, and let Databricks remove listings
    ([provider policies](https://docs.databricks.com/aws/en/marketplace/provider-policies)).
  - GWAS summary statistics are aggregate data. Each source's own licence still applies,
    and 72% of listed Analyses have no licence recorded (`docs/decisions.md:85-86`).
- **Who can consume:** table listings reach consumers outside Databricks through open
  sharing. Volume listings reach only consumers with Unity Catalog workspaces
  ([create listing](https://docs.databricks.com/aws/en/marketplace/create-listing)).
- **Fit with OpenGWAS's model:** non-commercial use is free, commercial users take a licence
  ("subscribe, download, keep, within source terms"; `docs/decisions.md:70-77`), and access
  goes through OpenGWAS's own gateway.
  - A personalized listing in a private exchange copies that model. OpenGWAS approves the
    request after the licence is signed and paid, outside Databricks, then grants the share.
  - Marketplace adds discovery among Databricks customers and in-platform delivery. It does
    not add billing, and it cannot replace the gateway for non-Databricks users of the
    Store format.

## Options for OpenGWAS

1. **Own gateway plus cheap object storage (recommended baseline).** Serve releases as
   authenticated downloads from R2 or OCI behind the OpenGWAS gateway. Users on Databricks
   download into their own volume and run opengwasdb/ogquery there.
   - Cost: about $12–20/month for 800 GB, with no egress fees within OCI's 10 TB or on R2.
   - Effort: low. The only code change is to test FUSE and add `immutable=1`.
   - Trade-off: Databricks users carry the copy (their storage, one-off ingress), and
     OpenGWAS keeps full control of licensing.
2. **Option 1 plus a private, approval-only Marketplace listing of a shared volume** for
   Databricks-using licensees.
   - Cost: the storage of option 1, plus a Premium Databricks account with a Unity Catalog
     workspace (DBU cost of a mostly idle account not quoted).
   - Effort: medium. Set up the Databricks account and provider policies, test volume
     sharing and recipient FUSE reads, and possibly R2-backed volume sharing.
   - Trade-off: recipients pay their own compute, but OpenGWAS pays egress unless the volume
     can sit on R2 or in the recipient's region. Billing stays offline.
3. **Remote reads (fsspec/HTTPS) in ogquery** (the stores are already 0.3.0).
   Databricks, laptops and the Data API would all query R2 or the gateway directly, with no
   bulk download.
   - Cost: as option 1, plus request charges on R2 (Class B $0.36 per million).
   - Effort: high. Rebuild twelve releases, add an fsspec opener and non-mmap sidecar reads,
     and pass gateway auth headers.
   - Trade-off: it helps every platform, not just Databricks, and interactive latency is
     unmeasured.
4. **Tabular Delta export with open sharing**, from Databricks or the open-source Delta
   Sharing server.
   - Cost: a second copy of the data in Parquet (size unmeasured), plus a sharing server.
   - Effort: very high, a new schema and query layer.
   - Trade-off: it reaches pandas, Spark and Power BI users without Databricks, but gives up
     the Store format's encoding and the ogquery contract. Not advised unless commercial
     demand for SQL access is shown.

## Open questions

- Does `np.load(mmap_mode="r")` work on `/Volumes` FUSE, on serverless and on classic? What
  latency do zarr shard reads get there compared with local disk?
- Does SQLite open `index.sqlite` on `/Volumes` with `mode=ro`, or does it need
  `immutable=1`?
- Can a Databricks-to-Databricks *recipient* read a shared volume through `/Volumes` with
  Python `open()` and mmap, or only through `LIST`, `SELECT` and `COPY INTO`?
- Can a volume on an R2 external location be shared through Delta Sharing, and is it then
  free of egress?
- Is the pysam wheel available for every serverless architecture (`aarch64`, `x86_64`)?
- What does an idle Premium Databricks account with a Unity Catalog workspace cost? The
  DBU and DSU rates were not readable from the pricing pages.
- Are any Store files larger than 5 GiB? That is the Files API and UI upload limit. Bulk
  loads would go through cloud-native copies instead.
- How many prospective commercial users run Databricks? Without that number, option 2's
  value is unknown.

## Sources

Local code (read 2026-11-26):

- ogquery, branch `orch/520/497`, at
  `/data/opengwasdb/work/orchestrate/opengwasdb-stores-520/worktrees/497-ogquery`:
  `README.md`, `pyproject.toml`, `ogquery/arrays.py`, `ogquery/release.py`,
  `ogquery/npy_sidecar.py` and `ogquery/variant_axis.py`.
- `opengwasdb`: `pyproject.toml`, `README.md`,
  `opengwasdb/query/__init__.py`, `opengwasdb/store/open.py`,
  `opengwasdb/variants/legacy_table.py` and `opengwasdb/ld/store/location.py`.
- `/data/opengwasdb/stores/catalog/current/stores.tsv` and `report.md` (catalogue
  `c11c4f5b333f08d6`).
- `opengwasdb-website/docs/decisions.md`.

Databricks:

- https://docs.databricks.com/aws/en/files/
- https://docs.databricks.com/aws/en/volumes/
- https://docs.databricks.com/aws/en/volumes/volume-files
- https://docs.databricks.com/aws/en/compute/serverless/limitations
- https://docs.databricks.com/aws/en/compute/serverless/dependencies
- https://docs.databricks.com/aws/en/release-notes/serverless/environment-version/
- https://docs.databricks.com/aws/en/security/network/serverless-network-security/manage-network-policies
- https://docs.databricks.com/aws/en/security/network/serverless-network-security/cost-management
- https://docs.databricks.com/api/workspace/files/download
- https://docs.databricks.com/aws/en/delta-sharing/
- https://docs.databricks.com/aws/en/delta-sharing/share-data-open
- https://docs.databricks.com/aws/en/delta-sharing/create-share
- https://docs.databricks.com/aws/en/delta-sharing/read-data-databricks
- https://docs.databricks.com/aws/en/delta-sharing/manage-egress
- https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/external-locations-r2
- https://docs.databricks.com/aws/en/storage/default-storage
- https://docs.databricks.com/aws/en/admin/usage/default-storage
- https://docs.databricks.com/aws/en/marketplace/
- https://docs.databricks.com/aws/en/marketplace/get-started-provider
- https://docs.databricks.com/aws/en/marketplace/create-listing
- https://docs.databricks.com/aws/en/marketplace/provider-policies
- https://docs.databricks.com/api/marketplaces/v1/create-listing
- https://www.databricks.com/product/pricing
- https://www.databricks.com/product/pricing/storage
- https://www.databricks.com/blog/top-10-marketplace-questions-answered

Protocol and SQLite:

- https://github.com/delta-io/delta-sharing/blob/main/PROTOCOL.md
- https://www.sqlite.org/uri.html

Cloud pricing:

- AWS Price List API:
  - https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/eu-west-2/index.json
  - https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-east-1/index.json
  - https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSDataTransfer/current/eu-west-2/index.json
- https://prices.azure.com/api/retail/prices (filters `armRegionName eq 'uksouth'`)
- https://developers.cloudflare.com/r2/pricing/
- https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD
- https://www.oracle.com/cloud/networking/pricing/
- https://cloud.google.com/storage/pricing (prices not readable)
