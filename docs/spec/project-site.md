# Dev Hub data

The specification of the Dev Hub's data: the **collectors** that read every
repository `system.yaml` lists, the files they write, and what the site
(og-dev-hub#15) and `pixi run architecture` read from them. It is the contract
between the data and its readers.

The code is og-dev-hub's `src/project_site/`; it moved here from
opengwasdb-stores with its history in og-dev-hub#7, where "this repository"
below meant opengwasdb-stores, the **registry**. From opengwasdb-stores, which
the environment installs as the `ogstores` distribution, it imports
`ogstores.bundle` and `yardstick.result`, and nothing else of it; every call names the
registry root it reads, because an installed package knows no checkout. Of the engine,
`opengwasdb`, it imports `opengwasdb.model.analyses.read_analyses` alone, the one
reader of a Release Manifest (`ogstores.bundle.partition_membership` takes its table). The environment
pins both at a revision (`ogstores` at opengwasdb-stores' epic branch until it merges to `main`).

**Where each repository is read from** (og-dev-hub#9). Every repository
og-dev-hub's `system.yaml` lists in `repos` is read from `main` of the site's
bare clone of it under the work root, `<work root>/<name>.git`, cloned the first
time it is needed and fetched only by `pixi run site` and by `--refresh`
(`site-data`, `architecture`), **once per run**. There are two work roots, each
with its own variable, so setting one never moves the other. The site's is
`$DEV_HUB_SITE_ROOT`, else `.work/site` in the og-dev-hub checkout, the same on
every machine, and holds public repositories only (`paths.site_work_root`,
given to the run's `Repositories` as `root`). `site-data`'s and `pixi run
architecture`'s is `$OPENGWASDB_SITE_ROOT`, else the build host's
`/data/opengwasdb/work/site` (`paths.work_root`), where the private repositories
they read are cloned too. One
read handle per repository per run is the one owner of this
(`project_site.staging.Repositories`: given a name, the handle's clone, ref,
commit and fetch record), so the architecture, the work and the Stores read the
same commit of each. A repository with
`visibility: null` is planned, and never cloned. A repository's files are read
one way, through its handle (`Repository.read(paths, at=...)`, or `tree()` for
all of them, both by object id through git, at the commit read unless another is
named). Only opengwasdb-stores also has its files extracted (`stores/` and
`docs/_yardstick/`, by `git archive` at that commit), because only its readers need files
on disk: the Stores collector is given paths under the run's own extraction
(`staging.registry_files(repositories)`), never one of its own. `--registry
PATH` reads that checkout instead, at its `HEAD`. Whether a ref resolves, and to
which commit, is asked of one owner, `staging.resolve_ref`: by the handle, the
branch reader and the work's choice of `main`.

Every clone and fetch of the site's clones under the work root, and of the git
directories the collectors read, goes through one owner,
`project_site.staging.ensure_clone`: a fetch prunes, and one that fails is
recorded and never raised, so what the clone already holds is read. A failed
refresh of any repository's clone is shown on the Architecture view, and leaves
`architecture check` and `conflicts` undecided (exit 2) unless they find a
problem anyway. A repository that cannot be read at all (no clone, and no
network to make one) is that repository's gap on the Architecture view; for
opengwasdb-stores it also makes the Stores source unavailable, naming why, and
no other source.

## The site

The site (og-dev-hub#15, `docs/site.md`) is one static page of built state, with
five views, in this order: Stores, Benchmarking, Architecture, Decisions and Context (og-dev-hub#19). The masthead's subtitle is "Build status". "Benchmarking" is the visible label of the yardstick view only: code, JSON keys and specs keep the name yardstick, because "benchmark" also names the per-Store release benchmark.
`pixi run site` collects from **public git only**, through
`collect.__main__.run(public_only=True)`: the architecture collector with
`read_private=False`, so a `private` repository is listed (its `note` says
"private: drawn as its container only, never read") and never asked for, so
never cloned; and the Stores collector, over the registry's extracted `stores/`
and `docs/_yardstick/` (public git). The board, the work and the other collectors do not
run. It needs no token, no `/data` and no network access to a private
repository.

`project_site.site.build(data_dir, out)` reads the collected `architecture.json`
and `stores.json` (a file that is missing or unreadable is `available: false` with why),
passes the architecture through `public_view` and the Stores through `stores_view`, and writes
from those alone:

| File | Content |
|---|---|
| `data/architecture.json` | the envelope; `repos` (a list, in `system.yaml`'s order: `name`, `label`, `url`, `state`, `visibility`, `status`, `ref`, `commit`, `committed`, `why` (the error of an `unreadable` one, the note of a `no_model` one, else `null`) and `refresh_error` (`null` unless the refresh failed)); `containers` (with `state`: `public`, `private`, `planned` or `data`); `diagrams` (`id`, `title`, `caption`, `svg`); `stages` (with the `components` serving each); `components` (with `anchor`, `container_name`, `size`, `paths` as `{path, url}` on GitHub at the commit read, and `adrs` placed on it with `via`); `component_repos` (the repositories with a component, for the view's filter); `counts` (`components`, `repos_with_model`); `gaps` (each public repository not planned: `state`, which follows the repository's: `unreadable` or `no_model` (with its `why` as `unreadable` or `no_model`), else `gaps` (an unclaimed file, a stale claim or a system gap), `complete`, or `unknown` when its claims were not measured (no gap record, or `unclaimed` or `stale` unknown), never `complete`; `unclaimed` and `stale` are lists only for `gaps` and `complete`, else `null`; `system`); `layering` (`null` when no model declares layers, else each layered repository's `edges`, `imports` against the layering and its `upward` imports); `seam` (`imports`, `pairs`, `baseline`); `across` (imports per pair of repositories); `summary` |
| `data/decisions.json` | the envelope; `repos` (those with an ADR, in order); `adrs` in `system.yaml`'s order then by number: `repo`, `number`, `title`, `status`, `url`, `components` (`{id, name, via}`) and `cites` (`{repo, number, text, url}`, `url` `null` when the cited ADR was not collected or is a private repository's) |
| `data/stores.json` | the Stores view (see [The Stores view](#the-stores-view)): the envelope; `registry` (`name`, `url`, `commit`, `stores_url`); `inventory` |
| `data/benchmarking.json` | the Benchmarking view (`stores_view.benchmarking_view`): the envelope and `yardstick` (see [The Stores view](#the-stores-view)) |
| `data/context.json` | `html` (the hub's `CONTEXT.md`, rendered by `project_site.markdown`: headings, paragraphs, lists, bold, italics, code spans and links, every character escaped first, a relative link resolved against og-dev-hub's `main` on GitHub, and a link to any other scheme than `http(s)` dropped); `source`; `glossaries`: each public listed repository but og-dev-hub, not planned, with `url` (its `CONTEXT.md` at the commit read) or `null` and a `note` (`no CONTEXT.md at the commit read`, `could not be read`) |

A repository's `state` is decided once, by `site.repo_state`: `planned`,
`private`, `unreadable` (no commit read), `no_model` or `read`; a container's
follows its repository's (`site.container_state`). The diagrams and the view
scripts read these states and never decide them again (a test runs the scripts in
`node` over a built site, `tests/project-site-architecture/view_runner.js`); every figure a view shows
is written by the build, and a script only renders it. Both the build and the
diagrams read the public `architecture.json` through one reader,
`architecture_public.parts`, and every link to a file or directory on GitHub is
`paths.github_url`.

Unknown is `null` in every file, never 0 or an empty list. The view scripts read
nothing else.

## The collectors

```text
pixi run site-data [--data-dir PATH] [--registry PATH] [--refresh] [--strict]
```

`pixi run site-data` runs every collector (the board, the Stores, the
architecture and the work) and prints one line per source; it is the collection
`pixi run architecture --data` reads. `pixi run site` runs the architecture
collector alone, on public git (*The site*, above). Each collector writes
`<data dir>/<source>.json`. The data directory is `docs/_data/` of the
og-dev-hub checkout, which git ignores, unless `OPENGWASDB_SITE_DATA` or
`--data-dir` names another.

Every file starts with the same four keys, then the source's own:

| Key | Meaning |
|---|---|
| `source` | `board`, `stores`, `architecture` or `work` |
| `available` | `true` when the source was read; `false` when it could not be |
| `collected_at` | UTC time, `2026-10-29T12:00:00Z` |
| `error` | `null`, or the failure as `ExceptionType: message` |

A source that fails (`gh` offline, a registry that cannot be read) writes
`available: false` with its error and no other key, and never stops the other
collectors. An **empty** source is not a failure: no Stores yet is
`available: true` with an empty list. A reader reads `available` before it
reads anything else.

### Board (`board.json`)

The board is read by `site-data` and `pixi run architecture` only, never by the
site, which shows no planned state. The board collector has its own GraphQL
query (`project_site.collect.board`);
this repository does not import the board skill. It reads project 1 of the
`opengwas` organisation, every page of it, and then every epic's sub-issues and
their blocked-by edges (`subIssues` and `blockedBy` in the GraphQL API) in one
aliased query, and follows every further page of both relationships (`subIssues`
and `blockedBy` each return `pageInfo`). An issue's body is read for what the work collector
needs and dropped otherwise:

- a Milestone's checklist lines;
- an Epic's `purpose`, the first non-empty paragraph of the body that is prose
  (not a heading, a table, a quote, or a list of bullets and boxes), cut at a
  sentence (or, failing a sentence, at a word and an ellipsis) to at most 600
  characters;
- the paths and module names an Epic or sub-issue cites (`cited`), as written
  (see [Citations](#citations));
- a sub-issue's planned change to the architecture (`plan`; see
  [Planned changes](#planned-changes)).

A fenced block is skipped whole, tracked across the paragraph split: three or more
backticks or tildes open it and the same character in a run at least as long
closes it, so a code sample's own blank lines never end it and its second half is
never read as prose. A relationship that still has a page unread when the
response is parsed is an
error, so the file is `available: false` rather than a short list marked
complete.

| Key | Content |
|---|---|
| `epics` | one row per Epic: `key` (`repo#n`), `title`, `url`, `state` (the issue's, `OPEN` or `CLOSED`), `status`, `workstream`, `next`, `priority`, `sub_issues` (`{total, completed}`), `purpose`, and `children` |
| `epics[].purpose` | the epic's own first prose paragraph, cut as above, or `null` when its body has none |
| `epics[].children` | the epic's sub-issues: `key`, `title`, `url`, `state`, `cited`, and `blocked_by`, a list of `{key, state}` |
| `epics[].children[].plan` | the ticket's planned change to the architecture (#422), present only when its body has an `architecture` block: the parsed plan, or `{invalid: reason}`; see [Planned changes](#planned-changes). The body itself is not kept |
| `epics[].cited`, `epics[].children[].cited` | the code the issue's text cites (#419): a sorted list of paths (`opengwasdb/encoding/se_range.py`, or the path of a GitHub link to a file) and dotted module names (`opengwasdb.encoding.se_range`), as written and not checked against any tree; `[]` when it cites none. The Work map resolves them to files and through the claims ([Citations](#citations)). The text itself is not kept |
| `milestones` | one row per Milestone, with the same fields as an epic (no `children`, no `cited`) and `lines` |
| `milestones[].lines` | each `- [ ]` or `- [x]` line of the body, in order: `checked`, `text`, and `refs` (`repo#n` keys) |
| `items` | every other project item, with the epic's fields |

- `status`, `workstream`, `next` and `priority` are the board's field values as
  written, and `null` where the item has none.
- An Epic is an issue of type Epic, labelled `epic` or `complexity:epic`, or
  titled `Epic:`; a Milestone is of type Milestone or titled `Milestone:`. A
  Milestone is never an Epic. The rule is the board skill's.
- A checklist is read from lines that begin `- [ ]`, `- [x]` or `- [X]`, after
  any indentation, and from nothing else: a bullet without a box is prose. A
  bare `#n` in a line is an issue of the milestone's own repository; a
  reference into another owner is dropped.
- `tests/project-site-data/fixtures/board-graphql.json` is a response recorded
  once from the real API by `board.fetch`.


**Private repositories on the board** (og-dev-hub#9). The board lists issues of
every repository, private ones too, and `board.json` keeps them all: it is read
locally, by `pixi run architecture`, and never published.

### Citations

One extractor and one resolver serve the tickets (Work) and the ADRs
(Architecture): `project_site.collect.architecture_adrs.cited_strings` finds what a
text cites and `project_site.collect.citations` says which tracked file a path means.

- **What is cited.** A path with a directory and a code extension (`.py`, `.smk`,
  `.sh`, `.toml`), the path of a GitHub link to a file, or a dotted module name. A
  trailing `:line` (`:551`, `:10-20`) is not part of the path.
- **Which file a path means.** The file itself when it is tracked (in the issue's own
  repository first); otherwise the one tracked file of any repository read that ends
  with `/<path>`, so `encoding/codec.py` means `opengwasdb/encoding/codec.py`. When
  **more than one** file ends that way the citation is **unresolved**: it places
  nothing, is never guessed, and is listed with its candidates (`work.json`
  `unresolved`).
- **A path that is not found.** A cited *code* path that is no tracked file and has no
  unique suffix match is attributed by the claims all the same, and its signal has
  `path: "not found"`; it is also listed in `work.json` `not_found` (owner, item, cited,
  component), and counted in `summary.not_found`, so a typo is visible. Without
  `files` (an older collection), or for a non-code path (only code files are listed),
  existence was not checked and the signal says `unchecked`, never `found`.
- **Dotted names.** A module name means `a/b/c.py` (`src/a/b/c.py` in this
  repository) or its package's `__init__.py`, shortened a name at a time.

### Stores (`stores.json`)

Every registered Store Release of the registry read
(`stores/`; `--registry` names another), never `/data`. A registered Store is
a directory named `OGS-xxxxx`; `by-label/`, `README.md` and `.staging/` are
not. Each bundle is read with `ogstores.bundle.load`, which never opens a Store.

| Key | Content |
|---|---|
| `registry`, `stores` | the registry read; one row per Store, in id order |
| `stores[]` | `store_id`, `label`, `status`, `trial`, `layout`, `completion_state`, `association_coverage`, `access_posture`, `derived_from`, `superseded_by` |
| lifecycle | `created_at`, `accepted_at` (release.yaml), `validated_at`, `validation_status` (validation.yaml) |
| `observed` | validation.yaml's `observed` mapping as written (`n_analyses`, `n_variants`, `n_associations`, `store_bytes`, ...), or `null` without a Validation Record |
| `description`, `notes` | release.yaml's text as written. `notes` is where Release Errata live |
| `problems` | what the bundle could not state: a `trial` that is not a boolean, a coverage outside the vocabulary, a malformed YAML file. Empty when there is nothing |

Beside `stores`, the file holds `commit` (the registry commit read, `null` for `--registry`),
`inventory` (one row per Store, below) and `yardstick` (the committed results, below).

A fact the bundle does not hold is `null`: a Store with no Validation Record
has `validated_at: null`, never a date borrowed from elsewhere, and a
`n_associations` the record left `null` stays `null` (it is not
`n_variants × n_analyses`). This collector does not run `bundle.check()`;
`pixi run bundle-check` does.

**LD Stores.** `stores.json` holds GWAS Stores only: the LD Store Registry is
not yet in opengwasdb-stores (opengwasdb-stores#496), so LD Stores are not
listed and their number is unknown, never 0. The Stores view says so as `ld_stores.gap`, naming og-dev-hub#10 and opengwasdb-stores#496: unknown, not 0.

**`inventory[]`** (`collect.inventory`, og-dev-hub#16), one row per Release Bundle: `store_id`,
`label`, `description`, and a *cell* (`{value, gap}`, never both set) for each of `layout`,
`completion_state`, `coverage`, `status`, `store_bytes`, `n_variants`, `top_hits`, `has_hm3`,
`has_rho`, `n_clumped`, `n_analyses`, `median_sample_size` and `ancestry`. Each reading rule is
the registry's, called and not re-derived: the bundle through `ogstores.bundle.load` (`layout`,
`completion_state`, `association_coverage`, `status`); the flags and the top-hit encoding through
`bundle.observed_flag` and `bundle.top_hit_counts_text`; the Release Manifest through
`bundle.manifest_summary` (which reads `analyses.tsv` through the engine's `read_analyses` and splits it with
`partition_membership`), **built rows only**: an `exclude_from_build` audit row is in no count, ancestry or median.
A sample size the quantity rule refuses is counted as unparseable, never dropped silently.

**A record with no `observed` block** reads "the Validation Record has no observed block" in every observed cell (the backfill skips such a record). **A Store that is not built has no observed facts.** A Store whose Release Status is `candidate` or `accepted`,
or that has no Validation Record, shows "not built yet (Release Status …)" in every observed cell
(`store_bytes`, `n_variants`, `top_hits`, `has_hm3`, `has_rho`, `n_clumped`); it never names the backfill or
the engine, which have nothing to fill. Its manifest cells still read. Any other status (`built`, `validated`,
`superseded`, `withdrawn`) with a record reads the rules below, and its status is shown as written. A `withdrawn` or
`superseded` Store with no record reads "no Validation Record (Release Status …)": it will never be built.

| Cell | Value | Gap, with what fills it |
|---|---|---|
| `store_bytes` | `observed.store_bytes` | absent or `null`: "recorded from opengwasdb-stores#502's backfill" |
| `n_variants` | `observed.n_variants` | absent: the backfill; `null`: "counts come with opengwasdb#488" |
| `top_hits` | the count at each threshold | the recipe does not declare `post.top_hits` (`ogstores.plan.declared_top_hits`: `top_hits` or the `top-hits` alias; none is not declared): "not computed"; a value that is not a boolean: the owner's message; `n_top_hits` absent: the backfill; `null`: "counts come with opengwasdb#488"; a count that is `null` or not a non-negative integer: "observed.n_top_hits[<threshold>] <value> is not a count" |
| `has_hm3`, `has_rho` | `true` or `false` | absent: the backfill; `has_hm3` `null`: "no record says how the HM3 step ended"; `has_rho` `null`: "the recipe builds no Rho Matrix, so whether the Store holds one is unknown until opengwasdb#488" |
| `n_clumped` | `observed.n_clumped` | absent or `null`: "pending opengwasdb-stores#507" |
| `n_analyses` | the built rows (and how many `excluded` rows were left out) | `analyses.tsv` missing or unreadable, naming which |
| `median_sample_size` | the median of `sample_size` over the built rows that have a number, with `with_sample_size` of `of` and `unparseable` | "the Release Manifest records no sample size for any built row" (and how many values are not numbers) |
| `ancestry` | a count per `assigned_ancestry`, `unassigned` for an empty one | the manifest has no Assigned Ancestry column; or no built row, so there is no ancestry to count |

A value the owner refuses (`observed_flag` on `"yes"`) is a gap carrying its message. **`yardstick`**
(`collect.yardstick_runs`): `available` (`false` with a `reason` when the registry has no
`docs/_yardstick/` at the commit read), `runs` (every valid result, oldest first, reduced to what
the view draws: `file`, `workload_id`, `engine_version`, `started_utc`, `cpu_count`,
`load_average`, `veeam_window`, and per Store its `layout`, `coverage`, `status`, `reason` and
`measures`) and `invalid` (`{file, error}`). Each file is validated by `yardstick.result.validate`;
one it refuses is not read but listed in `invalid` with the validator's message, and never stops the others.

### The Stores view

`data/stores.json` (`project_site.stores_view`, og-dev-hub#16) is decided at build time from
the collected `stores.json`; `static/js/stores.js` only renders it. It holds only the fields
named in `stores_view`, and every text a collector wrote has its host paths cut to the last
name (`architecture_public.reason`), so no `/data/...` path reaches the file, including in an
error.

- **`inventory[]`**: the row above, each cell `{text, gap, detail}`: `text` the figure as
  drawn (`62.1 GB`, `11,191,070`, `AFR 1 · EUR 2 · unassigned 1`, top hits
  `p < 5e-08: 10`), or `gap` the cause. `url` links the Store's bundle on GitHub at the
  commit read.
- **`yardstick`** (in `data/benchmarking.json`, not `stores.json`; `static/js/benchmarking.js` draws it, trends first, under the line "One fixed query workload (the yardstick), run at the finish of every epic that changes the engine.", which is the tab's lede and shows even with no results; the script draws the trends first): `stores` (the latest run per Store), `trends`, `unmeasured`, `invalid`,
  `runs`, `workloads`, `load_rule`, `veeam_rule`. Raw runs are not listed.
  - *The latest run per Store* is the latest run that measured it (a Store `pending` in every run
    says so, with its `reason`). When the newest run leaves the Store out or lists it pending, the
    panel says `not_in_latest`, "not in the latest run (<date>)", above the older run it shows. It gives `engine_version`, `date`, `workload_id`, `flags`,
    `peak_memory` and `size_on_disk` (each a figure, or its state with why), and `measures`: the
    median and p95 of every timed measure the run holds, in `yardstick.result.TIMED`'s order. A
    run of the old workload (`yardstick-3`) has fewer measures and shows exactly those; a
    measure the run does not hold is absent, not zero, and appears once a run carries it.
    `state` is `measured`, `not_applicable` (drawn "not applicable" with its `reason`) or
    `unavailable` (drawn "unavailable" with its `error`); the two are never drawn alike. The build writes each
    state's `label` and `tone`, and a panel's `notice` and `pending` wording (`stores_view.STATE`, which asserts it covers exactly `yardstick.result.STATUSES`,
    plus `absent`, a run that does not hold the measure); the script renders them. A `top_hits` row carries `path`, `index`
    or `scan`, said beside it, because the two differ in kind.
  - *A flagged run* is marked. A run is flagged when `veeam_window` is true, or when any load
    average it recorded (1, 5 or 15 minutes, before or after) is **over a quarter of
    `host.cpu_count`**: 224 CPUs flag a load average over 56. A load exactly a quarter is not flagged.
  - *Trends*: one per measure (the median of a timed measure, `peak_mb` for `peak_rss`, `bytes`
    for `bytes_on_disk`), inline SVG drawn by `stores_view.trend`; no charting library. One line per
    Store, **one point per engine version** (a version run more than once shows that Store's
    latest run of it), versions in the order they were first run, not by number. A flagged run's
    point is ringed (`flag-ring`) and its tooltip says why; **a line never joins an index point to a scan point**
    of `top_hits` (the line breaks, and each tooltip says `via index` or `via scan`); the tooltip also names the workload,
    because a trend across a workload change compares different measures.
  - *`unmeasured`*: registry Stores no committed run lists: "not measured by yardstick".

### Architecture (`architecture.json`)

The architecture of every repository og-dev-hub's `system.yaml` lists (#418, epic
#416, og-dev-hub#9), from that file, each repository's hand-written
`docs/architecture/components.yaml` and the code it claims. It reads **git, not
checkouts**, through each repository's read handle (above): `main` of its clone,
or `HEAD` of the checkout `--registry` names for opengwasdb-stores (tracked
files only). A clone is `<work root>/<name>.git`, so `OPENGWASDB_SITE_ROOT` (or,
for the site, `DEV_HUB_SITE_ROOT`) names another set of clones (the tests'
fixtures); no flag names one repository's git by its kind. `pixi run site` fetches every clone first; a failed fetch leaves
the `main` the clone has and is recorded in `repos.<name>.refresh`.

**Which repositories.** All of `system.yaml`'s `repos`, in its order:

- `visibility: null` is **planned**: listed, drawn as a planned container, never cloned;
- a clone or fetch that fails is **that repository's gap**, with git's message (`gaps.<repo>.unreadable`), and the rest is collected;
- a repository without `docs/architecture/components.yaml`, or with one that cannot be used, is a gap too (`gaps.<repo>.no_model`): its components, code and gaps are **unknown**, never zero. `load_model` checks everything the collector reads: each component is a mapping with an `id` and a `name` of text, ids unique, `paths` and `stages` lists of text, `layer` a whole number, and the model's `layers` and `stages` lists of mappings;
- a component id is one row's address (`#component-<id>`), so it is unique across the models: a model that repeats an id an earlier repository's model (in `system.yaml`'s order) has is that later repository's gap, naming the id and the first repository ("another repository" when that one is private), and its components are unknown. No repository's model ever makes the source unavailable for the others (og-dev-hub ADR 0001);
- og-dev-hub itself is one of them, read through its clone like any other (its `system.yaml` is read from the working tree);
- a `private` repository is collected whole by `site-data` and `pixi run architecture` (orchestration needs its branches), and never read by the site's collection (`read_private=False`, *The site* above); the site draws it as its container only (see *Visibility* below).

The model files. Each has `repo` and `components`: `id`, `name`, `container`,
`stages`, `summary`, `paths`. A model may declare `layers` (top to bottom,
`layer` and `name`, today opengwasdb's), and then every component has a `layer`;
it may hold `stages` (the pipeline's stages stay with opengwasdb-stores). The
system itself (`system`, `people`, `external`, `containers`,
`container_relations`, `repos`) is og-dev-hub's `system.yaml` (#8), read from
this checkout's working tree by its one reader (`architecture_model.read_system`, at
`paths.system_file`, or the file `--system` names): the site is built from a
checkout, so the tree is the published state. `collect/architecture_model.py`'s `load_system` checks
the keys and their shapes, that each person, external system and container has
an `id` and a `name` of text (the same check, with the same rule, as a model's
components: an id that is not text is refused), that ids are unique across
`people`, `external` and `containers`, that every relation names one of them, and that each of `repos`
has a unique `name` and a `visibility` of `public`, `private` or `null`; a
`system.yaml` that fails makes the source unavailable with the error naming the
problem, and the tests read the real file through it. A components file that
still holds a system section has it **ignored and reported as a gap**, never a
failed build; a component whose `container` is no container of `system.yaml` is
a gap naming both. A path ending in `/` claims a directory; any other path
claims one file; the longest claimed prefix wins. Nothing else is written by
hand: edges, counts and ADR placement are measured.

| Key | Content |
|---|---|
| `repos.<name>` | every listed repository, in `system.yaml`'s order: `name`, `visibility`, `status`, `planned`, `url`, `ref`, `commit` read, `committed` (that commit's date), `refresh` (`null` when no fetch was asked for, else `{ok, error}` with git's own message), `source_root` (`src/` when it has one, else `""`), `model` (`true`; `false` with a `note` when the ref has no usable model file; `null` when planned or unreadable) `error` (why it could not be read) and `glossary` (whether `CONTEXT.md` is at the commit read; `null` when not read). The Architecture view shows each commit and its date, and a visible line when a refresh failed |
| `model` | `system`, `people`, `external`, `containers`, `container_relations` (all `system.yaml`'s), `stages` (every model's that holds them, opengwasdb-stores', each with the `repo` it came from), `layers` (`{repo: [...]}`, each model's that declares them; `{}` when none does) |
| `components` | each modelled repository's, in `system.yaml`'s order: the model's keys plus `repo` (the repository's name), `files` and `lines` (claimed code files), `tracked` (every tracked file claimed) |
| `files` | `{<repo>: [...]}` (#422): every tracked code file of each repository with a model at the ref read, sorted, read NUL-safely; `null` for a repository read without a model (what is code is not known). A planned `adds` is told to exist from it |
| `gaps.<repo>` | for each repository not planned: `unreadable` (git's reason, or `null`), `no_model` (why there is no model, or `null`), `unclaimed` (code files no component claims, by path) and `stale` (`{path, component}` claims matching no tracked file), both `null` (unknown, not empty) without a model; `system_sections` (system keys the model file still holds, ignored) and `containers` (`{component, container}` for a container `system.yaml` lacks) |
| `baseline` | `path`, `from` (`opengwasdb-stores`), `entries` (how many imports its committed baseline lists; `null` with a `note` when it is not there at the commit read, never 0) and `measured` (the engine imports its code makes; `null` without its model) |
| `edges` | `from`, `to`, `imports`, `scope` and `upward`: `scope` is `within` (with `repo`) or `across` (with `from_repo` and `to_repo`) |
| `upward_imports` | each import within a repository that goes up its layers (#419), sorted by `file` then `name`: `file` (the importing file), `name` (the absolute imported name, a relative import resolved), `from`, `to` (component ids), `from_layer`, `to_layer`. The layering baseline of the repository that declares the layers lists the same pairs. `null` when no model read declares layers (the layering cannot be measured); never `[]` |
| `adrs` | every `docs/adr/NNNN-*.md` of every repository read: `repo`, `number`, `path`, `title`, `status`, `url` (the file on GitHub at the commit read, from `paths.clone_url`), `components`, `cites` (`[{repo, number}]`, below) |
| `summary` | `edges` (the edges measured), `upward_edges`, `upward_imports`, `registry_to_engine_edges`, `registry_to_engine_imports`, `adrs_total`, `adrs_placed`; what cannot be measured is `null` (see below) |

A code file that cannot be read, or a Python file that does not parse, makes the
source unavailable with an error naming the path; a count is never a guess of 0.
A claimed Python file that is not importable (a script under `tools/` or
`workflow/`) is a source of imports even though no one can import it.

**Code** is derived from the model, never written per repository
(`architecture_model.code_roots`): the roots are the top-level directories of
every path a repository's components claim, and a code file is a tracked `.py`,
`.smk`, `.sh`, `.R`, `.r` or `Snakefile` under one of them (R counts for
ownership and lines, not for the Python import graph). For opengwasdb that is
`opengwasdb/`, and for opengwasdb-stores `src/`, `workflow/`, `tools/` and
`stores/`; a claim of a file under `docs/` makes `docs` a root too. **Gaps never
fail the build** (og-dev-hub ADR 0001). Each repository's own CI fails on its
unclaimed files (opengwasdb-stores' `tests/architecture/test_architecture_ownership.py`
with this rule); the collector only reports them, and the Architecture view draws them.

A **module**'s dotted name is its path from a source root: `src/` when the
repository has one, else its root. An **import** is resolved against every
tracked module of the repositories with a model, the importing repository's
first (two may hold a module of the same name), then to that module's owner: an
unclaimed module gives no edge (it is a gap), and never takes its package's
owner. An import is counted per (file, imported name) between modules that
components claim, relative imports resolved. An edge is `within` one repository
or `across` two. It is `upward` when it is within a repository and goes to a
component on a higher layer; the same layer and lower layers are not.

**The seam** between opengwasdb-stores and opengwasdb is the one pair of
repositories held to a baseline (#421; `architecture_graph.SEAM`). An **engine
import** is a name that is `opengwasdb` or starts with `opengwasdb.`, counted per
(importing file, imported name) over opengwasdb-stores' claimed Python files.
The name alone decides it, so the seam does not need an engine checkout or the
engine's model: `registry_to_engine_imports` is that count, equal to the imports
on the pair's across-edges, and it stands whether or not opengwasdb's model is
there (`null` only without opengwasdb-stores' own). `registry_to_engine_edges`
is the number of component pairs among the pair's across-edges, which
opengwasdb's claims resolve, so it is `null` when opengwasdb has no model at the
ref read — unknown, never 0. `upward_edges` and `upward_imports` are `null` when
no model read declares layers. `baseline` reports
`docs/architecture/engine-imports-baseline.yaml` in opengwasdb-stores, which
lists those imports and only shrinks: opengwasdb-stores'
`tests/architecture/test_engine_imports_baseline.py` fails on an import the file
does not list (naming the file, the name and, when the engine was read, the
engine component it lands in) and on a listed import that is gone. One
measurement feeds both the seam counts and the baseline, so they cannot
disagree.

An **ADR** is placed by the code it cites (a path, a dotted module name such as
`opengwasdb.store.paths`, or a GitHub link to a file, resolved through the
claims; a bare suffix such as `store/paths.py` only when exactly one tracked file
ends with it) and by a component's `name` in its title (case-insensitive, at the start of a word, with no boundary at its end). A
component's name that appears only in the body places nothing, however often.
`components` maps a component id to `code` or `title`; an ADR placed nowhere has
`{}`, and the Decisions view says it is placed on no component. ADRs are collected from every repository read,
and code is placed only into repositories with a model. A citation is resolved
in the ADR's own repository first, then in the repositories with a model; a
GitHub link counts when it names a listed repository read.

An ADR's text citing another decision across repositories in og-dev-hub ADR
0002's form, `<repo> ADR NNNN` where `<repo>` is a listed repository, is
recorded on it as `cites: [{repo, number}]`, and the Decisions view shows it as a link to
that ADR (plain text when that ADR was not collected, or is a private
repository's).

**Visibility** (og-dev-hub#9, og-dev-hub#15). What "private" covers is
**what is collected from a private repository**, or from one `system.yaml` does
not list: its files, paths, components, stages, gaps, commits, branches and work
items, and its ADRs (titles and bodies). The site's own collection never reads
such a repository; whatever collection the build is given, such a repository is
drawn on the public site as its container only, in every view and every data
file. Text **authored in a public repository** is **passed through as written**,
even where it mentions a private repository or one of its ADRs (`ogld ADR 0001`
is shown as text, not a link): the hub's own docs and public ADRs are already
published on GitHub by their own repository; the site never rewrites them.

One function makes the public view of the collected files
(`project_site.architecture_public.public_view`), and every view's data is
written from it alone (`site.build`). It is an **allow-list**: it never starts
from a collected document, but builds `architecture.json` from the fields a
view draws, named in that module, so a field a collector adds reaches no view
until it is named there. Which repositories are private is `system.yaml`'s
`visibility`: through the `architecture.json` collected, else the file in this
checkout; a repository `system.yaml` does not list is treated as private,
because a fallback must be safe. Its container comes from `system.yaml`'s
`containers`, which is public. A gap or reason the collectors write names a
repository, never a private repository's commit, component or path. A host path
in a reason (a clone's git directory, in git's own message) is cut to its last
name (`…/ogld.git`) by `architecture_public.reason`, so where the build's clones
live is never published.

A component's box in a diagram (a Graphviz `URL`) and its name in the Stages,
Layering and Decisions tables link to its row in the Components table,
`#component-<id>`; only an id of lower-case letters, digits and `_`, starting
with a letter, becomes a link.

### Work (`work.json`)

Where live work meets (#419, epic #416). It reads the `board.json` and
`architecture.json` the same run just wrote to the data directory, so it runs
after them and is **unavailable, naming which, when either is**
(`work is unavailable: board is unavailable: ...`). From those two files and the
branches it places every piece of live work on the components the claims name.
Agents and `pixi run architecture conflicts` read this file, which is never published; `schema_version` is `1` and changes when a
key is removed or its meaning changes. Keys are only ever added within a version.

**Owners.** An owner is an open epic whose board `status` is Active, Todo or
Paused (`kind: epic`); otherwise the epic or ticket a branch's name points at
that the board does not list (`kind: issue`, status `Off board`, or the status
of a closed epic); otherwise the branch itself (`kind: branch`, labelled by its
name). A branch's owner is the epic its name gives (`orch/<epic>/<ticket>`, with an
optional `-slug` after the ticket; `orch/<epic>-...`), else its ticket's epic
(`fix/issue-345`, `345-...`), else the ticket, else the branch. An epic's lanes live
in each repository whose files it changes, so a lane's numbers are those of the
listed repository whose epic `#<epic>` holds the ticket `#<ticket>` on the board
(og-dev-hub#9: opengwasdb-stores' `orch/6/7-stores` is og-dev-hub#6's, for
og-dev-hub#7). Otherwise, and for an epic's own branch, they are the repository's
whose files the branch changes, which is its own; never another repository found
by `system.yaml`'s order. A branch that changes no file has no such repository:
its owner is unknown, it is its own owner (`kind: branch`, status `Owner unknown`),
and `branches.list[].owner_unknown` says why.

**Branches.** A branch counts when it is ahead of `main` and its newest commit
is within `days` (21) days. Its files are `git diff --name-only -z main...<branch>`.
The collection reads **pushed** branches only, of every listed repository that
was read (og-dev-hub#9): each bare clone after its run's one
`git fetch origin +refs/heads/*:refs/heads/*`; a registry checkout named by
`--registry` as `refs/remotes/origin/*` after `git fetch origin`. A failed fetch is
recorded in `branches.sources[].fetch`, and the refs already
there are read; a repository whose branches cannot be read at all is recorded in
`branches.sources[].error` and the others are read. The `conflicts` command can add
the local branches of other git directories (`--local`), each a clone of a listed
repository recognised by its `origin` URL. A branch read from two clones
counts once, as the copy further ahead (a tie keeps the pushed one), and
`branches.sources[].count` is what each read found. A branch with no merge base
with `main`, such as the orphan `cla-signatures` the CLA check keeps, is no work
against `main`: it is left out, named in `branches.sources[].skipped` with the
reason, and never makes the source unavailable (og-dev-hub#7).

**Signals.** One row per (component, owner, item, via, state), with `what`, the
branches (`repo:name`) or cited strings behind it. `via` is `branch`, `cited`
(an open ticket) or `scope` (an epic's body). The `state` is:

| State | When |
|---|---|
| `building` | a branch's diff touches a file the component claims |
| `active` | an open ticket of an Active epic cites it, and the ticket is not blocked |
| `waiting` | an open ticket cites it and waits for an open ticket (a blocking edge whose blocker is still open) |
| `scope` | an epic's body cites it |
| `planned`, `paused` | an open ticket of a Todo or Paused epic cites it, not blocked |
| `stale` | a branch whose epic is closed or not live, or whose ticket is closed |

A cited string is placed through the claims, in the repository its text is in first,
after it is resolved to a tracked file as [Citations](#citations) say (from
`architecture.json`'s `files`). A citation that is ambiguous is `unresolved`, and one
no claim covers places nothing. A cited path that matches no tracked file keeps its
signal on the component that claims it (a ticket may mean to create the file), but is
**marked**: see `path` below. Closed tickets add nothing.

**Meets.** A component is a meet when two or more owners have `building` or
`active` signals on it. For every pair of its owners there is a `pairs` entry,
with a `coordination`:

- `coordinated`: a blocking edge `{waiting, on}` links a specific item of one with a
  specific item of the other, in either direction. A shared epic, or an edge between
  other tickets of the same epics, does not coordinate it.
- `unlinkable`: no edge links them, and one side's work is an **epic's integration
  branch** (`orch/<epic>-slug`), whose item is the branch (`branch:<repo>:<name>`; decided by the branch's own name, so it holds whether or not the board lists the epic):
  it belongs to the epic as a whole and has no ticket an edge could link, so the
  absence of an edge proves nothing. `epic_branches` names those branches.
- `uncoordinated`: no edge, and every item is a ticket (or a branch on no epic).

`coordinated` on a pair stays `true` only for `coordinated`. The meet's `coordination`
is `uncoordinated` if any pair is, else `unlinkable` if any pair is, else `coordinated`;
its `coordinated` is `true` only for the last. `conflicts` never calls an
`unlinkable` meet uncoordinated.

**Unmeasured.** Without a repository's architecture model at the ref read (or when
it could not be read) none of its files belongs to a component, so its work is
**unknown**, never "no work": `unmeasured` is `{<repo>: <reason>}` for each such
repository (empty otherwise), its signals and meets are not produced, and `conflicts` on its files or a branch of it exits 2.
The other repositories' meets are still measured.

| Key | Content |
|---|---|
| `schema_version` | `1` |
| `inputs` | `board.collected_at`; `architecture.collected_at` and `architecture.repos.<name>` (`ref`, `commit`, `visibility`) of each listed repository |
| `owners` | the owners with at least one signal: `key`, `kind`, `title`, `url`, `status`, `workstream` |
| `components` | the components with at least one signal: `id`, `name`, `repo` |
| `signals` | as above: `component`, `owner`, `item`, `via`, `state`, `path`, `what`; `path` is `found` (a tracked file, or a branch's file), `not found`, `unchecked` (existence not known) or `n/a` (a dotted module) |
| `unmeasured` | `{}`, or `{<repo>: reason}` for each repository read without a model (see above) |
| `not_found` | the cited code paths no tracked file matches, attributed by claim: `owner`, `item`, `cited`, `component` |
| `unresolved` | the citations of live tickets and epics that more than one tracked file ends with: `owner`, `item`, `cited`, `candidates` (the paths) |
| `meets` | `component`, `owners`, `items` (owner to its items there), `pairs` (`owners`, `coordinated`, `coordination`, `edges`, `epic_branches`), `coordinated`, `coordination` |
| `plans` | the tickets' planned changes and, for a closed ticket, what was checked, as above (#422) |
| `waits` | every open blocking edge among the live epics' tickets: `{item, on}` |
| `tickets` | every open ticket of a live epic, to its owner (what `conflicts --ticket` reads) |
| `branches.sources` | per repository read: `repo`, `git_dir`, `main`, `days`, `fetch` (`null`, or `{ok, error}`), `error` (`null`, or why its branches could not be read), `local`, `count`, `skipped` (each branch left out: `name`, `reason`) |
| `branches.list` | `repo`, `name`, `ahead`, `committed`, `files`, `epic`, `ticket` (from the name), `local`, and the resolved `owner`, `item`, `components`, `owner_unknown` (`null`, or why the owner could not be told) |
| `summary` | `owners`, `meets`, `coordinated`, `uncoordinated`, `unlinkable` (these three add up to `meets`), `branches`, `unresolved`, `not_found` (the lengths of those lists) |


**The command line.** `pixi run architecture` (`python3 -m project_site.architecture`)
runs the same collectors on the spot, or reads a collection with `--data DIR`:

```text
pixi run architecture check [--repo NAME] [--registry PATH] [--system FILE] [--refresh] [--data DIR]
pixi run architecture conflicts (--branch B [--repo NAME] | --files PATH... --repo NAME [--ticket repo#n])
                                [--local GIT_DIR...] [--registry PATH] [--system FILE] [--refresh] [--days N] [--data DIR]
```

`--repo NAME` takes a repository `system.yaml` lists, and nothing else (the
`engine` and `registry` aliases og-dev-hub#9 kept for one release are gone).
`--system FILE` reads another `system.yaml` than this checkout's: its
`repos` are the repositories collected and the names `--repo` accepts, so a
test, or a question about a few repositories, reads only those. `--registry PATH`
reads that opengwasdb-stores checkout instead of its clone, and `--refresh`
fetches every listed repository once first.

- `check [--repo NAME]`: for each repository with a model (or the one `--repo` names), the code files no component claims and the
  claims that match no tracked file, and the `docs/architecture/layering-baseline.yaml`
  of each repository whose model declares layers, at the ref read, entry by entry (importing file and imported name, never a count, so a new import
  cannot hide behind a fixed one): each `new:` import not in the baseline and each `stale:` entry no longer
  imported is named; no baseline file is not a failure. What cannot be measured is
  printed with its reason and is **unknown, never a pass**: the repository `--repo` names having no model or being unreadable, a fetch recorded as failed (what was read may be out of date), a repository or file
  that cannot be read, a file YAML cannot load (any constructor failure too), one with no `allowed` list, an entry that is not
  exactly a `file` and a `name` of text, or an entry listed twice (this repository's own baseline is read by the same loader, with the same refusals). Exit **1** if anything measured has a problem (an unclaimed or stale claim, a new or
  stale baseline entry), whatever else is unknown; otherwise **2** if any part could not be measured;
  otherwise 0. Without `--repo`, a repository with no model is named and is not a failure: it is a gap the site draws (og-dev-hub ADR 0001).
- `conflicts --branch B [--repo NAME]` or `--files PATH... --repo NAME [--ticket repo#n]` (`--files` without `--repo` exits 2: a bare path can mean a file of any repository; a `NAME` `system.yaml` does not list exits 2):
  the components the work touches, the other owners' `building` or `active` work on each
  with its ticket, epic, branch and cited files, and whether a blocking edge links `--ticket`
  (or the branch's ticket) to theirs. Exit 1 when any meet is uncoordinated or unlinkable (asking a person is the safe default; the message says which); 0 when none is;
  **2 when it cannot decide** (a source is unavailable, the branch is not in the
  collection, a git directory or branch diff cannot be read, or the work is in a repository whose model is missing). `--local GIT_DIR...` adds those clones' local branches, `--refresh` fetches first.
  Two more things leave it undecided: code that no component claims (a mistyped path, or
  a new one whose claim does not exist yet, so what it meets is unknown), and a fetch
  recorded as failed in the data read (`--refresh`'s, or the collection's own), since
  what was read may be out of date. Either is 2 unless a meet is found anyway, which
  stays 1 and lists them as `also:`. Given files that are not code a component claims
  (tests, docs) are listed as outside the map and never judged.

### Planned changes

A ticket that changes the structure says so in its body (#422, epic #416), in one
fenced block whose info string is `architecture`, holding YAML. Text outside the
fence is ignored, and a ticket without a block has no plan.

````markdown
```architecture
adds:      # paths that will exist, and the component that will claim them
  - paths: [opengwasdb/encoding/association.py]
    component: encoding          # an existing component id, or a new id ...
    name: Association encoder    # ... which then needs a name (and `container`, `layer` if engine)
moves:     # paths whose claim changes component
  - paths: [opengwasdb/build/eaf_orientation.py]
    to: resolution
drops:     # component imports that should disappear, "from -> to"
  - dense -> encoding
absorbs:   # free text, drawn on the map, never checked (line numbers drift)
  - encoding/codec.py:932
```
````

Every key is optional, but a block with none of them is invalid, and so is any
other key (`{}` is a block with none). Each key present must hold a list; `paths`
are non-empty lists of text; `name` and `container` are text and `layer` a whole
number. A component id (`component`, `to`, either end of a drop) is lower-case
letters, digits and `_`, starting with a letter (the model's form, so it can never
be markup), and must be an existing component or declared in `adds`; a new one needs a
`name`, and a new component of a repository whose model declares layers (paths under
that repository's code roots, today `opengwasdb/`) a `container` and a `layer` too. The board
collector parses the block into `children[].plan` with `adds`, `moves`, `drops`
(each `{from, to}`) and `absorbs`, every key present as a list. A block that
cannot be used is never dropped: `plan` is `{invalid: reason}` (not YAML, unknown
key, empty, a malformed item, more than one block, a block never closed). The board collector does not know the components, so the
`work` collector judges their ids once it knows them, against the union of the
components of every repository with a model (og-dev-hub#9). An id in none of them
makes the plan invalid, unless the plan **touches a repository without a model**:
the ticket's own repository, the repository a path in `adds` or `moves` is in,
or, for such a path that no model's claims or code roots cover, every listed
repository without a model, since any of them could hold it ("without a model"
is read without one, or planned). `repo_of` sees every listed repository for this. Then the id is **unknown**: the checks that name it
are `held: null`, and `why` names that repository.

**Judging a plan.** The `work` collector lists every ticket that has a plan, of
any epic, open or closed, as `work.json`'s `plans` (sorted by epic, ticket):
`ticket`, `epic`, `title`, `url`, `state` (`open` or `closed`), `plan`,
`components` (each component the plan involves: `id`, `name`, `repo`, and `new`,
true for one the plan declares) and `checks`. An open ticket's plan is carried
as planned and `checks` is empty, as it is for an invalid plan; `absorbs` is
carried and never checked. Once the ticket is closed each item is checked
against what the architecture collector read (each repository at its ref).
**Which repository a path is in** is the one repository whose claims cover it,
else the one whose code roots do. When two repositories' claims cover it, or two
repositories' code roots do and no claim settles it, it is not known (`held: null`,
`why` naming both), never the first in `system.yaml`'s order:

- `adds`: for each path, `{kind: adds, path, component, held, why}`; held only when
  the path is a tracked file (in `architecture.files`) **and** the named component
  claims it. A path that does not exist is not held, saying so with the ref.
- `moves`: the same, with `to` as the component.
- `drops`: `{kind: drops, from, to, imports, held, why}`; held when no import goes
  from `from` into `to`, else not held, naming how many remain. Without `architecture.edges`
  (absent or `null`) it is unknown: absence is never zero imports.

Every check also has `repo` (the repository's name), the tree it was read in.

`held` is `true`, `false`, or `null` for **unknown**: a path no model's code
covers while a repository read has no model (the `why` names those repositories,
never with a commit), a path whose existence is not known (no `architecture.files`,
the tree not read, or not a code file, since only code files are listed), a path
two repositories could hold (above), and an item naming an id no model has in a
plan that touches a repository without one, cannot be judged. Missing a model is
never an unmet item. An unmet item is reported, never a failure: the ticket
may have closed on an epic's integration branch whose PR has not merged to the
ref read. The `plans` key is additive, so `schema_version` stays `1`.

No page draws a plan: the site shows no planned state (og-dev-hub#15). The
`architecture` command still judges them.

### The command's output and exit status

One line per source, in this order (the architecture line is longer: components,
gaps (with `, SYSTEM GAPS: …` after the counts when a model file still holds a system section or a component names a container `system.yaml` lacks), upward imports, the seam and ADRs placed; `work` runs last, because it reads the
board and architecture files just written, and adds `BRANCH FETCH FAILED` for a failed fetch), then the files are all written:

```text
board: 24 epics, 3 milestones, 24 milestone lines
stores: 22 stores
architecture: 10 registry + 17 engine components (engine model at main 42850d8b), gaps registry 0/0 engine 0/0 (unclaimed/stale), 8 upward edges (13 imports), 96 registry->engine imports, 58 of 115 ADRs placed
work: 14 owners, 10 meets (1 coordinated, 9 uncoordinated, 0 unlinkable), 11 branches
```

An unavailable source prints `UNAVAILABLE <source>: <error>` in place of its
line. The exit status is **0** all the same: every file is written, and a
reader reads the file's `available` and `error`. `--strict` exits
1 when any source is unavailable (after every file is written), for a caller
that must not go on without it.
