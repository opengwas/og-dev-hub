# The site

How the Dev Hub's site is built, previewed and extended (og-dev-hub#15). It is one
static page of OpenGWAS's **built state**, with a tab per view (Stores, Benchmarking, Architecture, Decisions, Context), rendered in the
browser from JSON the build writes. It is built from public git alone: no token,
no `/data`, no private repository and no board. It is published at
<https://blog.opengwas.io/og-dev-hub/>.

## The commands

| Command | What it does |
| --- | --- |
| `pixi run site` | Collect from public git, then write the site into `_site/`. `--out DIR` writes it elsewhere, `--registry PATH` reads that opengwasdb-stores checkout instead of its clone, and `--no-refresh` reads the clones as they are. |
| `pixi run site-preview` | Serve the built `_site/` at <http://localhost:4200/og-dev-hub/>, the sub-path it is published at (`--port N` for another port). |
| `pixi run site-data` | Run every collector, the board and the private repositories included, into `docs/_data/`. The site does not read it; it stays because `pixi run architecture check\|conflicts --data DIR` reads that collection. |

## The views

| Tab | What it shows | Its data |
| --- | --- | --- |
| Architecture | Every repository `system.yaml` lists and the commit read; the containers; each repository's components by layer or by container (Graphviz, drawn at build time); the stages; every component with its size, claims and the ADRs placed on it; the gaps in the claims; the imports against the layering; and the imports across repositories, with the `opengwasdb-stores` to `opengwasdb` seam and its baseline | `data/architecture.json` |
| Decisions | Every public repository's ADRs in one table: number, title, status, repository, the components each governs, and the ADRs it cites in another repository, each linking to GitHub; filtered by repository | `data/decisions.json` |
| Context | The hub's `CONTEXT.md`, rendered at build time, and a link to each public repository's own `CONTEXT.md` at the commit read (or why there is none) | `data/context.json` |
| Stores | Every Release Bundle in the registry as one inventory row (layout, completion, coverage, Release Status, storage, variants, top hits, HM3, Rho, clumped, Analyses, median sample size, ancestry), each field a value or a gap that names what fills it; the table is full width with its header pinned and the description wrapped | `data/stores.json` |
| Benchmarking | yardstick's results: a trend per measure across engine versions first, then the latest run per Store, the runs taken under load or in the Veeam window marked. The label is Benchmarking; the thing, its code and its JSON keep the name yardstick | `data/benchmarking.json` |

It shows no planned state (the project board's) and no running state (the
operations dashboard's).

## How it is published

`.github/workflows/site.yml` builds and publishes the site; nobody publishes by hand.

- **Triggers:** a push to `main`, a nightly run at 05:17 UTC (so the built state
  follows the other repositories' `main`), and `workflow_dispatch`.
- **Build job:** `pixi install --locked`, `pixi run site`, then the `_site/` upload
  (`actions/upload-pages-artifact`). It needs no secret and no token.
- **Deploy job:** `actions/deploy-pages`, with `pages: write` and `id-token: write`
  on that job alone. It runs only from `main`: a pull request, or a dispatch on
  another branch, builds but never deploys.
- **Ordering:** the workflow's `concurrency` group is `site-<ref>` with
  `cancel-in-progress: false`, so runs on `main` queue one at a time and a running
  deploy finishes. A pull request has its own ref, so it never waits on a deploy.
- **Pull requests** run the build job only, so a build error fails the check. One
  workflow serves both, so the pull-request build cannot drift from the published one.

**The 60-day pause.** GitHub disables a scheduled workflow after 60 days without
activity in the repository, and the site then goes stale without warning. Re-enable
it with `gh workflow enable site.yml -R opengwas/og-dev-hub`.

### One-time switch to Actions (2026-11-24; the owner removes this list once done)

The Pages source is still the `gh-pages` branch. In order:

1. Switch the source: `gh api -X PUT repos/opengwas/og-dev-hub/pages -f build_type=workflow`
2. Allow `main` to deploy: `gh api -X POST repos/opengwas/og-dev-hub/environments/github-pages/deployment-branch-policies -f name=main -f type=branch`
3. Merge.
4. After the first successful deploy, delete `gh-pages`: `gh api -X DELETE repos/opengwas/og-dev-hub/git/refs/heads/gh-pages`

## What a build reads

`pixi run site` runs the architecture collector in its public mode
(`collect.__main__.run(public_only=True)`):

- every repository `system.yaml` lists as `public` is cloned anonymously from
  GitHub into the site's work root and read at `main`, one fetch each per run;
- a `private` one is listed and drawn as its container from `system.yaml`, and
  is never cloned;
- a planned one (`visibility: null`) is drawn as planned;
- the board is not read.

It also runs the Stores collector, over the registry clone's `stores/` and
`docs/_yardstick/` at `main` (extracted by `git archive` into the work root; public git too),
and `site.build` turns it into `data/stores.json` and `data/benchmarking.json` (`project_site.stores_view`). The registry
at `main` is behind what the view can draw: the Validation Records that lack
opengwasdb-stores#502's fields, and the yardstick results of the old workload, render as gaps and
as the measures those runs hold. Neither is a failure. The charts are inline SVG drawn
at build time (`stores_view.trend`); there is no charting library.

The site's work root is `$DEV_HUB_SITE_ROOT`, else `.work/site` in the
checkout, the same on every machine; it only ever holds public repositories.
(`pixi run architecture` and `site-data` keep their own: `$OPENGWASDB_SITE_ROOT`,
else the build host's `/data/opengwasdb/work/site`, where they also clone the
private repositories they read. Setting one variable never moves the other
root.) The collection goes to `docs/_data/` (`$OPENGWASDB_SITE_DATA` or `--data-dir` names
another), and the site to `_site/`; both are git-ignored.

A repository that cannot be read, or has no model, is a gap the page draws, and
never fails the build (og-dev-hub ADR 0001).

## How a build writes the site

`project_site.site.build(data_dir, out)` reads the collection, passes it through
`architecture_public.public_view` (the one filter: nothing of a private
repository but its container, and no host path), and writes:

```text
_site/
  index.html          the tabs and an empty section per view
  style.css           light and dark, from prefers-color-scheme or the toggle
  js/app.js           the tabs, the theme and what every view shares
  js/architecture.js  one script per view, each reading its own data file
  js/decisions.js
  js/context.js
  js/stores.js
  data/architecture.json
  data/decisions.json
  data/context.json
  data/stores.json
```

`index.html`, `style.css` and `js/` are copied from `src/project_site/static/`.
There is no framework, no bundler and no CDN, and every path is relative, so the
page works from any sub-path. The Stores charts are SVG from `project_site.stores_view`, held in `data/stores.json`. Each diagram is DOT text from
`project_site.diagrams`, drawn to SVG by Graphviz's `dot` at build time
(`diagrams.render_svg`) and held in `data/architecture.json`. A component's box in
a diagram links to its row in the Components table (`#component-<id>`).

## Adding a view

1. Add what it reads to a collector, or a new collector run by
   `collect.__main__.run(public_only=True)`, reading public git only.
2. Name every field it draws in `architecture_public` (an allow-list: a field
   no view names never reaches the site).
3. Write `data/<view>.json` in `site.build`, from the public view alone.
4. Add a tab and a section to `static/index.html`, and `static/js/<view>.js`,
   which calls `DevHub.register("<view>", render)`. Decide every state and figure
   in the build and write it to the JSON; the script only renders what it is given.
   Set every fact as text (`DevHub.el`), never as markup.
5. Test it in `tests/project-site-architecture/test_site.py`: the data file, that
   nothing of the private fixture repository reaches any file of `_site/`, and
   that its script draws in `node` over a built site (`view_runner.js`, with the
   few DOM calls the scripts make; `nodejs` is in the environment for this alone).

## The look

The page follows the OpenGWAS website (`opengwas/opengwasdb-website`): `style.css` carries its colour
tokens under the same names (`--teal`, `--ink`, `--wash`, `--rule`, `--wide`, `--gutter`), `fonts/` its
Atkinson Hyperlegible Next and Mono (SIL OFL, licence files beside them) and `img/` its logo and favicons;
a comment at the top of `style.css` says where each came from. Dark tokens are the hub's own (the website
has none): the same hues, lifted. A faint 24 px grid marks it as a developer environment; it is on the page
only, and every panel, table and the masthead sits on solid paper. Architecture diagrams fill the width, and
"Enlarge" opens one over the page with zoom buttons (plain JS, `DevHub.zoomable`).
