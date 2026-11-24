# Project site data

The specification of the project site's data (#389, epic #385): the **epic
record** an orchestrated epic commits when it finishes, and the **collectors**
`pixi run site-data` runs to gather everything else the site's pages read. The
pages themselves (#391) and the site build (#388) are specified elsewhere; this
file is the contract between the data and them.

The code is og-dev-hub's `src/project_site/`; it moved here from
opengwasdb-stores with its history in og-dev-hub#7, where "this repository"
below meant opengwasdb-stores, the **registry**. From opengwasdb-stores, which
the environment installs as the `ogstores` distribution, it imports
`ogstores.bundle`, `ogstores.paths`, `ogstores.engine` (the lock's engine pin)
and `yardstick.result`, and nothing else; every call names the registry root it
reads, because an installed package knows no checkout. It reads
`/data/opengwasdb/stores` only through read-only SQLite URIs.

**Where each repository is read from** (og-dev-hub#9). Every repository
og-dev-hub's `system.yaml` lists in `repos` is read from `main` of the site's
bare clone of it, `/data/opengwasdb/work/site/<name>.git`, cloned the first time
it is needed and fetched only by a render (`pixi run site`, `site-preview`,
`site-publish`) and by `--refresh` (`site-data`, `architecture`), **once per
run**. One read handle per repository per run is the one
owner of this (`project_site.staging.Repositories`: given a name, the handle's
clone, ref, commit and fetch record), so the architecture, the work and the
render's engine docs read the same commit of each. A repository with
`visibility: null` is planned, and never cloned. A repository's files are read
one way, through its handle (`Repository.read(paths, at=...)`, or `tree()` for
all of them, both by object id through git, at the commit read unless another is
named). Only opengwasdb-stores also has its files extracted (`stores/`, `docs/`,
`CONTEXT.md`, `pixi.lock`, `ogstores.yaml`, by `git archive` at that commit),
because only its readers need files on disk: the Stores, Records and Catalog
collectors are given paths under the run's own extraction
(`staging.registry_files(repositories)`), never one of their own. `--registry
PATH` reads that checkout instead, at its `HEAD`. Whether a ref resolves, and to
which commit, is asked of one owner, `staging.resolve_ref`: by the handle, the
branch reader, the work's choice of `main` and the publish.

Every clone and fetch of the site's clones under the work root, and of the git
directories the collectors read, goes through one owner,
`project_site.staging.ensure_clone`: a fetch prunes, and one that fails is
recorded and never raised, so what the clone already holds is read. A failed
refresh of any repository's clone is shown on the architecture pages, and leaves
`architecture check` and `conflicts` undecided (exit 2) unless they find a
problem anyway. A repository that cannot be read at all (no clone, and no
network to make one) is that repository's gap on the architecture pages; for
opengwasdb-stores it also makes each source that reads its files unavailable,
naming why, and no other source. The engine's clone, when no refresh fetched
it, is fetched only when it lacks the revision the registry's `pixi.lock` pins;
if it still lacks it, there is no older engine to stage instead, so the render
stops with git's message and exits 2. A publish's own `git fetch` of og-dev-hub's
`origin`, which decides the commit it publishes, is not one of these: it must
succeed, or the publish is refused.

## The site

The site (og-dev-hub#15, `docs/site.md`) is one static page of built state, with
three views: Architecture, Decisions and Context (Stores is og-dev-hub#16's).
`pixi run site` collects from **public git only**, through
`collect.__main__.run(public_only=True)`: the architecture collector with
`read_private=False`, so a `private` repository is listed (its `note` says
"private: drawn as its container only, never read") and never asked for, so
never cloned; the board, the Stores, the work and the other collectors do not
run. It needs no token, no `/data` and no network access to a private
repository.

`project_site.site.build(data_dir, out)` reads the collected `architecture.json`
(a file that is missing or unreadable is `available: false` with why), passes it
through `public_view`, and writes from that alone:

| File | Content |
|---|---|
| `data/architecture.json` | the envelope; `repos` (a list, in `system.yaml`'s order: `name`, `label`, `url`, `private`, `planned`, `visibility`, `status`, `ref`, `commit`, `committed`, `model`, `note`, `error`, `refresh`); `containers` (with `state`: `public`, `private`, `planned` or `data`); `diagrams` (`id`, `title`, `caption`, `svg`); `stages` (with the `components` serving each); `components` (with `anchor`, `container_name`, `size`, `paths` as `{path, url}` on GitHub at the commit read, and `adrs` placed on it with `via`); `gaps` (each public repository not planned: `unreadable`, `no_model`, `unclaimed`, `stale`, `system`); `layering` (`null` when no model declares layers, else each layered repository's `edges` and `upward` imports); `seam` (`imports`, `pairs`, `baseline`); `across` (imports per pair of repositories); `summary` |
| `data/decisions.json` | the envelope; `repos` (those with an ADR, in order); `adrs` in `system.yaml`'s order then by number: `repo`, `number`, `title`, `status`, `url`, `components` (`{id, name, via}`) and `cites` (`{repo, number, text, url}`, `url` `null` when the cited ADR was not collected or is a private repository's) |
| `data/context.json` | `html` (the hub's `CONTEXT.md`, rendered by `project_site.markdown`: headings, paragraphs, lists, bold, italics, code spans and links, every character escaped first, a relative link resolved against og-dev-hub's `main` on GitHub, and a link to any other scheme than `http(s)` dropped); `source`; `glossaries`: each public listed repository but og-dev-hub, not planned, with `url` (its `CONTEXT.md` at the commit read) or `null` and a `note` (`no CONTEXT.md at the commit read`, `could not be read`) |

Unknown is `null` in every file, never 0 or an empty list. The view scripts read
nothing else.

## The served-path baseline

The build's served-path check reads one fixed list,
`resources/site/legacy-served-paths.txt` (#388, #397), one path per line with
`#` for comments. At opengwasdb-stores' address it was the 90 paths under
`docs/` at `ff204b6`, the commit the legacy Pages deployment was built from. At
og-dev-hub's address (og-dev-hub#7) it starts fresh: the file is absent until it
is written from the first publish there, and an absent file checks nothing,
because no reader holds a link yet. Once written it is fixed, because it protects
the links readers hold: a page the site generates may come and go without being
added to it, and a path in it only goes when a published URL is retired
deliberately, by a reviewed change to the file. An empty or unreadable file fails
the build rather than passing a render nothing checked.

## The epic record

One YAML file per epic, `docs/_epics/<repo>-<number>.yaml`, named for the
epic's repository and issue number. The leading underscore keeps Quarto from
rendering it. An epic record exists only for an issue the board counts as an
Epic (a ticket is not one). The orchestrator writes it from the run's
`state.json`, and an agent writes it in one pass, because every field is a
scalar, a list of flat rows, or a mapping of two keys. `status` and `finished`
follow the **epic issue**, not the run: open means `active` with `finished:
null`, closed means `finished` with the date the issue closed. A run finishing
does not finish its epic.

**An unknown value is `null`, never an estimate.** Every field is required, so
that a field left out is distinguishable from a field not known. A typed value
that is not the real thing is refused: a date that is not an ISO date, a number
that is not a number, a commit, `repo#n` key, `docs/_yardstick/` path or catalog
version that does not have its form. **Prose is free text**: `title`, `summary`,
decision text and follow-up text only have to be non-empty, so history that
says "Estimated N for eQTLGen" is not mistaken for a guess.

```yaml
repo: opengwasdb-stores            # the epic's repository, without the owner
number: 313                        # the epic's issue number
title: Analysis catalog across all Stores
status: active                     # active while the epic issue is open, finished once closed
workstream: Analyses               # a board Workstream, or null
started: 2026-10-21                # ISO date, or null
finished: null                     # ISO date the issue closed; null exactly while active
summary: >-                        # 2 to 4 sentences, or null
  The Analysis Catalog lists every validated Store. ...
prs:                               # repo#n keys, in merge order
  - opengwasdb-stores#353
versions: []                       # tags the PRs shipped; empty until the cutover
tickets:
  - key: opengwasdb-stores#319     # repo#n, or null for work with no issue of its own
    title: analysis_id never contains ':'
    pr: null                       # repo#n, or null
    merge: 7832deb                 # 7 to 40 hex commit on the integration branch, or null
decisions:
  - date: 2026-10-21
    text: Integration branch cut from dev, not stacked on #299.
    link: null                     # http(s) URL, or null
test_time:                         # always a mapping; each member null when never measured
  baseline: {commit: e6e829d, wall_s: 158.4, suites: null}
  final: {commit: a84ecfb, wall_s: 162.05, suites: null}
yardstick:                         # always a mapping; each member a docs/_yardstick/*.json path (#390) or null
  before: null
  after: null
catalog:                           # always a mapping; each member a 16-hex catalog version, or null
  before: null
  after: 1b3a155d449bb84a
followups:
  - key: opengwasdb#294            # repo#n, or null
    text: builders print n_associations
```

Rules `validate_epic` applies, and the order of the fields above:

| Field | Rule |
|---|---|
| `repo`, `number` | a repository name; an integer of 1 or more. The file name is `<repo>-<number>.yaml` |
| `title` | non-empty text, never null |
| `status` | `active` or `finished`: open or closed, as the epic issue is |
| `workstream` | one of the board's twelve workstreams (GWAS Store architecture, LD Store architecture, Builds, Interface, Website, Clients, Tool integration, Analyses, Engineering, Data API, Gateway, Dashboard), a name the board retired on 24 Nov 2026 (Data architecture, Build architecture, LD, Store builds, Python client; valid in a record committed before then), or null |
| `started`, `finished` | an ISO date (`2026-10-21`, unquoted or quoted) or null. A finished epic has a `finished` date, the day the issue closed; an active one has none |
| `summary` | non-empty text of 2 to 4 sentences, or null |
| `prs`, `tickets[].key`, `tickets[].pr`, `followups[].key` | `repo#n`: a repository name, `#`, an integer of 1 or more |
| `versions` | tag names. Empty until each repository merges to `main` and tags every merge (#386) |
| `tickets[].merge` | a hex commit of 7 to 40 characters, or null. A ticket with no recorded merge commit is null, never its PR's head |
| `decisions[].date`, `.text` | an ISO date and non-empty text, both required; `link` is an `http(s)` URL or null |
| `test_time` | always a mapping with `baseline` and `final`; each is null, or `{commit, wall_s, suites}`: a hex commit or null, seconds as a number or null, and `suites` null or a mapping of suite name to seconds. A run state records one total, so `suites` is null for every backfilled record |
| `yardstick` | always a mapping with `before` and `after`; each is null, or a relative path that starts `docs/_yardstick/`, ends `.json` and has no `..`. Validated as a reference only; the result file is #390's |
| `catalog` | always a mapping with `before` and `after`; each is null, or a 16-hex catalog version directory name |
| `followups[].text` | non-empty text, never null |
| any other field | refused, by name |

`records.load_epics(directory)` reads every `*.yaml` of a directory and returns
the valid records and the errors by file name; an invalid file never stops the
others.

## The collectors

```text
pixi run site-data [--data-dir PATH] [--catalog-root PATH] [--registry PATH] [--refresh] [--strict]
```

`pixi run site-data` runs every collector and prints one line per source. Each
collector writes `<data dir>/<source>.json`. The data directory is
`docs/_data/` of the og-dev-hub checkout, which git ignores, unless
`OPENGWASDB_SITE_DATA` or `--data-dir` names another. Nothing is ever written
under `/data/opengwasdb/stores`.

Every file starts with the same four keys, then the source's own:

| Key | Meaning |
|---|---|
| `source` | `board`, `catalog`, `releases`, `stores`, `records`, `architecture` or `work` |
| `available` | `true` when the source was read; `false` when it could not be |
| `collected_at` | UTC time, `2026-10-29T12:00:00Z` |
| `error` | `null`, or the failure as `ExceptionType: message` |

A source that fails (`gh` offline, a catalog root that does not exist) writes
`available: false` with its error and no other key, and never stops the other
collectors. An **empty** source is not a failure: no Releases yet is
`available: true` with empty lists. A page reads `available` before it reads
anything else.

### Board (`board.json`)

The board collector has its own GraphQL query (`project_site.collect.board`);
this repository does not import the board skill. It reads project 1 of the
`opengwas` organisation, every page of it, and then every epic's sub-issues and
their blocked-by edges (`subIssues` and `blockedBy` in the GraphQL API) in one
aliased query, and follows every further page of both relationships (`subIssues`
and `blockedBy` each return `pageInfo`). An issue's body is read for what the site
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
every repository, private ones too. Its public view (above, *Visibility*) keeps
an epic, ticket or milestone of a private repository, or of one `system.yaml`
does not list, only as a count in `private` (`epics`, `active_epics`,
`tickets`, `milestones`) and an epic's `private_children`: no title, number,
link or Next text, and no blocked-by edge to it. No page is generated for such
an epic. The Epics index, the Overview and an epic's page each say how many
they leave out ("2 epics in private repositories are not shown."). A public
epic's own title, Next line and purpose, and a public ticket's title, are drawn
as written, even where they name a private repository's issue.

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
  `unresolved`, a count on the Work page).
- **A path that is not found.** A cited *code* path that is no tracked file and has no
  unique suffix match is attributed by the claims all the same, and its signal has
  `path: "not found"`; it is also listed in `work.json` `not_found` (owner, item, cited,
  component), counted in `summary.not_found`, and listed on the Work page as "cited paths
  not found (attributed to a component by its claim)", so a typo is visible. Without
  `files` (an older collection), or for a non-code path (only code files are listed),
  existence was not checked and the signal says `unchecked`, never `found`.
- **Dotted names.** A module name means `a/b/c.py` (`src/a/b/c.py` in this
  repository) or its package's `__init__.py`, shortened a name at a time.

### Catalog history (`catalog.json`)

Every version directory under `<artifact root>/catalog/versions/`
(`/data/opengwasdb/stores/catalog/versions/` here); `--catalog-root` names
another root. Each `catalog.sqlite` is opened through a `file:...?mode=ro` URI.
A root that does not exist is an error; a root with no versions is `versions: []`.

| Key | Content |
|---|---|
| `root`, `current` | the root read, and the name of the version `current` points at, or `null` |
| `versions` | oldest `built_at` first, one row per version |
| `versions[].version`, `.current` | the directory name (16 hex), and whether `current` names it |
| `versions[].catalog_meta` | the `catalog_meta` table as a mapping: `built_at`, `registry_commit`, `builder_version`, `serving_policy` (JSON text), as written |
| `versions[].counts` | the `counts` table's rows as they are, in table order: `dimension`, `value`, `n_analyses` |
| `versions[].totals` | `analyses`: `count(*)` of `listed_analyses`; `stores`: the Stores those rows belong to |
| `versions[].changes` | `changes.tsv`'s rows tallied by change (`{added: n, ...}`), or `null` for a version without the file |
| `versions[].selection` | the `selection` table's rows in `store_id` order -- `store_id`, `decision` (`listed`, `excluded`, `refused` or `placeholder`) and `reason` -- for the version `current` names; `null` for every other version, whose decisions the site does not show |

`counts` rows are per dimension and **overlap**: an Analysis is counted once in
each dimension, and `NULL` is a category, so a dimension's rows sum to the
total only when none is missing. `totals.analyses` comes from SQL on the
listed Analyses, never from summing dimension rows.

### Releases (`releases.json`)

Both repositories' tags and GitHub Releases, from `gh api repos/opengwas/<repo>/tags`
and `.../releases`.

| Key | Content |
|---|---|
| `repos` | `opengwasdb`, then `opengwasdb-stores` |
| `repos[].tags` | `name` and the tagged `commit` |
| `repos[].releases` | `tag`, `name`, `published_at`, `draft`, `prerelease`, `url` |

A repository with no Release has `releases: []` and the file is still
`available: true`. A tag is not a Release: until #386 each repository's
Releases are empty, and `opengwasdb` has one tag, `v0.2.0`.

### Stores (`stores.json`)

Every registered Store Release of the registry being rendered
(`stores/`; `--registry` names another), never `/data`. A registered Store is
a directory named `OGS-xxxxx`; `by-label/`, `README.md` and `.staging/` are
not. Each bundle is read with `ogstores.bundle.load`, which never opens a Store.

| Key | Content |
|---|---|
| `registry`, `stores` | the registry read; one row per Store, in id order |
| `stores[]` | `store_id`, `label`, `status`, `trial`, `layout`, `completion_state`, `association_coverage`, `access_posture`, `derived_from`, `superseded_by` |
| lifecycle | `created_at`, `accepted_at` (release.yaml), `validated_at`, `validation_status` (validation.yaml) |
| `observed` | validation.yaml's `observed` mapping as written (`n_analyses`, `n_variants`, `n_associations`, `store_bytes`, ...), or `null` without a Validation Record |
| `description`, `notes` | release.yaml's text as written. `notes` is where Release Errata live, and the catalog shows it |
| `problems` | what the bundle could not state: a `trial` that is not a boolean, a coverage outside the vocabulary, a malformed YAML file. Empty when there is nothing |

A fact the bundle does not hold is `null`: a Store with no Validation Record
has `validated_at: null`, never a date borrowed from elsewhere, and a
`n_associations` the record left `null` stays `null` (it is not
`n_variants × n_analyses`). This collector does not run `bundle.check()`;
`pixi run bundle-check` does.

**The Stores page and LD Stores.** `stores.json` holds GWAS Stores only, and the
Stores page heads its listing "GWAS Stores". It ends with an "LD Stores" section
that is a gap: the LD Store Registry is not yet in opengwasdb-stores
(opengwasdb-stores#496), so LD Stores are not listed and their number is
unknown, never 0. The Overview names its Store figure "GWAS Stores" and shows
"LD Stores" as `unknown`, even when the catalog data is unavailable. The gap is static text with no collector; og-dev-hub#10's
second half replaces it with a collector that reads the registry once #496 lands.

### Records (`records.json`)

| Key | Content |
|---|---|
| `epics` | the valid epic records of `docs/_epics/*.yaml`, dates as ISO text |
| `invalid` | each invalid file's name, and its errors (`validate_epic`'s, or `could not be read: ...`) |
| `yardstick.results` | each valid `docs/_yardstick/*.json` as `{name, result}` |
| `yardstick.invalid` | each invalid file's name and errors |

An invalid file is reported by name and never stops the others. An absent or
empty `docs/_epics/` or `docs/_yardstick/` is not an error. The yardstick's
result schema and validator are #390's (`docs/spec/yardstick.md`): the collector
reads each result through `yardstick.result.validate`, and reports a refused one
under `yardstick.invalid` with its `ResultError` message. Any *other* exception
from validating one file -- a validator that raises rather than refuses -- is
that file's error too, recorded as `ExceptionType: message`, and the other
results are still read: one bad file never makes the source unavailable. The
same holds for the epic records above. `records.collect`
takes another validator as an argument, for tests.

### Architecture (`architecture.json`)

The architecture of every repository og-dev-hub's `system.yaml` lists (#418, epic
#416, og-dev-hub#9), from that file, each repository's hand-written
`docs/architecture/components.yaml` and the code it claims. It reads **git, not
checkouts**, through each repository's read handle (above): `main` of its clone,
or `HEAD` of the checkout `--registry` names for opengwasdb-stores (tracked
files only). A clone is `<work root>/<name>.git`, so `OPENGWASDB_SITE_ROOT` names
another set of clones (the tests' fixtures); no flag names one repository's git
by its kind. `pixi run site` fetches every clone first; a failed fetch leaves
the `main` the clone has and is recorded in `repos.<name>.refresh`. The site's
*docs* mirror stays at the engine revision `pixi.lock` pins; the map shows
current work, so it does not.

**Which repositories.** All of `system.yaml`'s `repos`, in its order:

- `visibility: null` is **planned**: listed, drawn as a planned container, never cloned;
- a clone or fetch that fails is **that repository's gap**, with git's message (`gaps.<repo>.unreadable`), and the rest is collected;
- a repository without `docs/architecture/components.yaml`, or with one that cannot be used, is a gap too (`gaps.<repo>.no_model`): its components, code and gaps are **unknown**, never zero. `load_model` checks everything the collector reads: each component is a mapping with an `id` and a `name` of text, ids unique, `paths` and `stages` lists of text, `layer` a whole number, and the model's `layers` and `stages` lists of mappings;
- a component id is one panel's address, so it is unique across the models: a model that repeats an id an earlier repository's model (in `system.yaml`'s order) has is that later repository's gap, naming the id and the first repository ("another repository" when that one is private), and its components are unknown. No repository's model ever makes the source unavailable for the others (og-dev-hub ADR 0001);
- og-dev-hub itself is one of them, read through its clone like any other (its `system.yaml` is read from the working tree);
- a `private` repository is collected whole (orchestration needs its branches), and the pages draw it as its container only (see *Visibility* below).

The model files. Each has `repo` and `components`: `id`, `name`, `container`,
`stages`, `summary`, `paths`. A model may declare `layers` (top to bottom,
`layer` and `name`, today opengwasdb's), and then every component has a `layer`;
it may hold `stages` (the pipeline's stages stay with opengwasdb-stores). The
system itself (`system`, `people`, `external`, `containers`,
`container_relations`, `repos`) is og-dev-hub's `system.yaml` (#8), read from
this checkout's working tree by its one reader (`architecture_model.read_system`, at
`paths.system_file`, or the file `--system` names): publishing renders a clean checkout, so the tree
is the published state. `collect/architecture_model.py`'s `load_system` checks
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
| `repos.<name>` | every listed repository, in `system.yaml`'s order: `name`, `visibility`, `status`, `planned`, `url`, `ref`, `commit` read, `committed` (that commit's date), `refresh` (`null` when no fetch was asked for, else `{ok, error}` with git's own message), `source_root` (`src/` when it has one, else `""`), `model` (`true`; `false` with a `note` when the ref has no usable model file; `null` when planned or unreadable) `error` (why it could not be read) and `glossary` (whether `CONTEXT.md` is at the commit read; `null` when not read). The pages show each commit and its date, and a visible line when a refresh failed |
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
with this rule); the collector only reports them, on the page.

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
`{}` and is listed on the page. ADRs are collected from every repository read,
and code is placed only into repositories with a model. A citation is resolved
in the ADR's own repository first, then in the repositories with a model; a
GitHub link counts when it names a listed repository read.

An ADR's text citing another decision across repositories in og-dev-hub ADR
0002's form, `<repo> ADR NNNN` where `<repo>` is a listed repository, is
recorded on it as `cites: [{repo, number}]`, and the pages show it as a link to
that ADR (plain text when that ADR was not collected, or is a private
repository's).

**Visibility** (og-dev-hub#9). What "private" covers is **what the site
collects from a private repository**, or from one `system.yaml` does not list:
its files, paths, components, stages, gaps, commits, branches and work items,
its ADRs (titles and bodies), its board items (epics, tickets and milestones:
their titles, numbers, links, Next lines and purposes) and their pages. All of
that is **hidden**: such a repository is drawn on the public site as its
container only, in the pages and in the component panel's embedded JSON. Text
**authored in a public repository or on a public item** is **passed through as
written**, even where it mentions a private repository or one of its issue
numbers: the hub's own docs, a public epic's title, body, Next line and purpose,
public records and public ADRs. That text is already published on GitHub by its
own repository; the site never rewrites it.

One function makes the public view of the collected files
(`project_site.architecture_public.public_view`), and every page and the panel
render from it alone: `pages.generate` applies it to everything it loads, and
each architecture page applies it again. It is an **allow-list**: it never
starts from a collected document, but builds `architecture.json`, `work.json`
and `board.json` from the fields a page or the panel draws, named in that
module, so a field a collector adds reaches no page until it is named there.
`records.json`, committed in a public repository, passes through less any
private repository's epic, which gets no page. Which repositories are private is
`system.yaml`'s `visibility`: through the `architecture.json` the same run
collected, else `work.json`'s record of it, else the file in this checkout; a
repository the board names that `system.yaml` does not list is treated as
private, because a fallback must be safe. Its container comes from
`system.yaml`'s `containers`, which is public. A gap or reason the collectors
write names a repository, never a private repository's commit, component or path. A host path in a reason (a clone's git directory, in git's own message) is cut to its last name (`…/ogld.git`) by `architecture_public.reason`, so where the build's clones live is never published.

**The component panel** (#435). On Pipeline, Structure and health and the Work
map, a component's box in the engine and registry diagrams (a Graphviz `URL`),
and its name in the pages' lists and tables, is a link to `#component-<id>`.
Following it opens a panel beside the page. Close, Escape or Back closes it,
and an address ending in `#component-<id>` opens it on load. For the component,
the panel shows:

- its name, repository, container, layer and summary;
- its size and stages;
- the paths it claims, each linked to GitHub at the commit read (`repos.<repo>.commit`);
- the work on it now, from `work.json`'s `signals`: by owner, each item with its state and `what`;
- its imports each way, from `edges`, with their counts, an upward one marked;
- the ADRs placed on it, with how each was placed (`code`: cites its code; `title`: names it in its title), and the ADRs each cites across repositories.

Each page embeds the panel's data as JSON built from those fields only, never
a collected document whole, because the collected files hold host paths, which
are never published. Facts are JSON-encoded with `<`, `>`, `&` and the backtick
written as `\u` escapes, so none becomes markup or ends the page's raw block.
The script sets every fact as text.

Unknown is never "none":
- Without `work.json`, every component's work is unknown, with the reason.
- So is each component's of a repository named in `work.json`'s `unmeasured`.
- While a repository read has no model, every component's imports into it are said not to be placed on components.

Without `architecture.json` there is no panel, and no name is a link. Only an
id of lower-case letters, digits and `_`, starting with a letter, becomes a
link.

### Work (`work.json`)

Where live work meets (#419, epic #416). It reads the `board.json` and
`architecture.json` the same run just wrote to the data directory, so it runs
after them and is **unavailable, naming which, when either is**
(`work is unavailable: board is unavailable: ...`). From those two files and the
branches it places every piece of live work on the components the claims name.
Agents read this file, not the page; `schema_version` is `1` and changes when a
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
The published page reads **pushed** branches only, of every listed repository that
was read (og-dev-hub#9): each bare clone after its run's one
`git fetch origin +refs/heads/*:refs/heads/*`; a registry checkout named by
`--registry` as `refs/remotes/origin/*` after `git fetch origin`. A failed fetch is
recorded in `branches.sources[].fetch` and shown on the page, and the refs already
there are read; a repository whose branches cannot be read at all is recorded in
`branches.sources[].error` and the others are read. The `conflicts` command can add
the local branches of other git directories (`--local`), each a clone of a listed
repository recognised by its `origin` URL, which the page never shows. A branch read from two clones
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
its `coordinated` is `true` only for the last. The page and `conflicts` never call an
`unlinkable` meet uncoordinated.

**Unmeasured.** Without a repository's architecture model at the ref read (or when
it could not be read) none of its files belongs to a component, so its work is
**unknown**, never "no work": `unmeasured` is `{<repo>: <reason>}` for each such
repository (empty otherwise), its signals and meets are not produced, the page says
its work was not measured, and `conflicts` on its files or a branch of it exits 2.
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

The page's tiles are `summary`; every other figure on it is a count of these rows.

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
key, empty, a malformed item, more than one block, a block never closed) and the
page shows the reason. The board collector does not know the components, so the
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

Every check also has `repo` (the repository's name), the tree it was read in;
the page's warning names that repository's ref and commit.

`held` is `true`, `false`, or `null` for **unknown**: a path no model's code
covers while a repository read has no model (the `why` names those repositories,
never with a commit), a path whose existence is not known (no `architecture.files`,
the tree not read, or not a code file, since only code files are listed), a path
two repositories could hold (above), and an item naming an id no model has in a
plan that touches a repository without one, cannot be judged. Missing a model is
never an unmet item. An unmet item is a warning on the page, never a build failure: the ticket
may have closed on an epic's integration branch whose PR has not merged to the
ref read. The `plans` key is additive, so `schema_version` stays `1`.

**The page.** The Structure and health page ends with a `## Planned changes`
section, written from `plans` alone. Each valid plan has a heading (the ticket,
its title and state), a Quarto `{dot}` diagram of the components it involves
(added paths marked `+`, moved paths `→`, a declared component dashed and
labelled `new`, a dropped import a dashed arrow), and its items: an open
ticket's as planned, a closed one's as `held`, `not held` or `unknown` with
`why`. `absorbs` is listed as text. A closed plan with unmet items carries a
warning, naming the ref read and that the ticket may have closed on an
integration branch not yet merged. An invalid plan shows its reason and no
diagram. A `work.json` without `plans` is said to predate planned changes, never
shown as "no plans"; with `plans` empty the page says no ticket carries a block.

### The command's output and exit status

One line per source, in this order (the architecture line is longer: components,
gaps (with `, SYSTEM GAPS: …` after the counts when a model file still holds a system section or a component names a container `system.yaml` lacks), upward imports, the seam and ADRs placed; `work` runs last, because it reads the
board and architecture files just written, and adds `BRANCH FETCH FAILED` for a failed fetch), then the files are all written:

```text
board: 24 epics, 3 milestones, 24 milestone lines
catalog: 5 versions, current 88da43e2534cc126
releases: 26 releases, 27 tags
stores: 22 stores
records: 6 epics, 0 invalid, 5 yardstick results, 0 invalid
architecture: 10 registry + 17 engine components (engine model at main 42850d8b), gaps registry 0/0 engine 0/0 (unclaimed/stale), 8 upward edges (13 imports), 96 registry->engine imports, 58 of 115 ADRs placed
work: 14 owners, 10 meets (1 coordinated, 9 uncoordinated, 0 unlinkable), 11 branches
```

An unavailable source prints `UNAVAILABLE <source>: <error>` in place of its
line. The exit status is **0** all the same: every file is written, and the
pages show the notice from the file's `available` and `error`. `--strict` exits
1 when any source is unavailable (after every file is written), for a caller
that must not go on without it.

## Backfill

The records under `docs/_epics/` are written from the orchestrate run states
on the host (`~/.cache/orchestrate/*/state.json`,
`/data/opengwasdb/work/epic*/orchestrate/*/state.json`), read-only. A run state
holds no start or finish date, no PR merge date and no per-suite test time, so
from a state:

- `status` and `finished` come from the epic **issue**, not the state: while the
  issue is open the record is `active` with `finished: null`, however many of
  its PRs the run has merged, and once it is closed the record is `finished`
  with the date it closed;
- `started` is the earliest `decisions[].when`;
- `tickets` are the state's ticket entries, with `merge` the merge commit where
  one is recorded and `null` where only a PR is named;
- `decisions` are the state's `decisions[]`, each with its date and no link;
- `test_time` is the state's `baseline` and `final`, with `suites: null`;
- `yardstick` is `{before: null, after: null}` and `versions` is `[]`: the
  yardstick (#390) and the versions (#386) do not exist yet;
- a ticket's `key` is its issue number under the run's repository, or the
  sibling repository's when the entry is named for it (`opengwasdb#298`), and
  `null` for work with no issue of its own (a split part, an operation, a
  review pass). Its `pr` is the PR the entry names, and its `merge` is the
  commit it records, `null` where the entry records none or only a pin;
- a run in stages (#282) has an archive per stage beside its `state.json`
  (`state-stage1.json`, `state-stage2.json`): `tickets`, `decisions` and `prs`
  cover all of them, a ticket a later stage finished replaces its earlier entry,
  and `test_time` is the last stage's, whose baseline and final are measured on
  the same test runner;
- `catalog` is `{before: null, after: null}` where the run state does not name
  the versions.

An epic record exists only for an issue the board counts as an Epic. A run on a
ticket (#241, a follow-up run on a ticket branch) is not an epic and has no
record. The backfilled records are #313, #282 and #302, all still open and so
`active`; #313 also waits on OGS-00011, which is not validated. Runs still in
flight (#232, #371, #385) and #312's partial run were not backfilled.
