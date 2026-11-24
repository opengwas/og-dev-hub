# The site

How the Dev Hub's site is built, previewed and extended (og-dev-hub#15). It is one
static page of OpenGWAS's **built state**, with a tab per view, rendered in the
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
| Stores | Coming in og-dev-hub#16 | |

It shows no planned state (the project board's) and no running state (the
operations dashboard's).

## What a build reads

`pixi run site` runs the architecture collector in its public mode
(`collect.__main__.run(public_only=True)`):

- every repository `system.yaml` lists as `public` is cloned anonymously from
  GitHub into the site's work root and read at `main`, one fetch each per run;
- a `private` one is listed and drawn as its container from `system.yaml`, and
  is never cloned;
- a planned one (`visibility: null`) is drawn as planned;
- the board is not read.

The site's work root is `$OPENGWASDB_SITE_ROOT`, else `.work/site` in the
checkout, the same on every machine; it only ever holds public repositories.
(`pixi run architecture` keeps its own, the build host's
`/data/opengwasdb/work/site`, where it also clones the private repositories it
reads.) The collection goes to `docs/_data/` (`$OPENGWASDB_SITE_DATA` or `--data-dir` names
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
  data/architecture.json
  data/decisions.json
  data/context.json
```

`index.html`, `style.css` and `js/` are copied from `src/project_site/static/`.
There is no framework, no bundler and no CDN, and every path is relative, so the
page works from any sub-path. Each diagram is DOT text from
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
   which calls `DevHub.register("<view>", render)`. Set every fact as text
   (`DevHub.h`), never as markup.
5. Test it in `tests/project-site-architecture/test_site.py`: the data file, and
   that nothing of the private fixture repository reaches any file of `_site/`.
