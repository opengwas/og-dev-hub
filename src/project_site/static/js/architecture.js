/* The Architecture view (og-dev-hub#15), from data/architecture.json.
 *
 * What is written by hand (system.yaml's containers; each repository's
 * docs/architecture/components.yaml: its components, layers and claims) and what
 * is measured from the code (sizes, imports, the layering, the gaps, ADR
 * placement) are said apart. Unknown is said to be unknown, never 0. */
(function () {
  "use strict";
  var D = window.DevHub, h = D.h;

  function repoState(r) {
    if (r.planned) return D.pill("planned");
    if (r.private) return D.pill("private: container only");
    if (r.error || !r.commit) return D.pill("unreadable", "bad");
    if (r.model === false) return D.pill("no model", "warn");
    return D.pill("read", "good");
  }

  function repositories(data) {
    var failed = data.repos.filter(function (r) { return r.refresh && r.refresh.ok === false; });
    return D.card("Repositories", "Every repository system.yaml lists, and the commit of each that was read. " +
      "A private repository is drawn as its container only, and is never read.",
      failed.map(function (r) {
        return D.notice("", h("p", {}, h("strong", {}, "The " + r.name + " refresh failed"),
          ": " + (r.refresh.error || "") + ". This is the " + r.ref + " its clone already had, so it may be behind."));
      }),
      D.table([
        { label: "Repository", cell: function (r) { return [D.link(r.name, r.url), r.status ? h("span", { class: "sub" }, r.status) : null]; } },
        { label: "State", cell: repoState },
        { label: "Commit read", cell: function (r) {
          return r.commit ? [h("a", { class: "mono", href: r.url + "/commit/" + r.commit }, D.short(r.commit)), " on " + r.ref] : "";
        } },
        { label: "Committed", cell: function (r) { return r.committed || ""; } },
        { label: "Note", cell: function (r) { return r.error || (r.model === false ? r.note : "") || ""; } }
      ], data.repos));
  }

  function tiles(data) {
    var s = data.summary || {}, read = data.repos.filter(function (r) { return r.model; }).length;
    var upward = data.layering === null ? "unknown" : D.figure(s.upward_imports);
    return h("div", { class: "tiles" },
      D.tile(D.figure(data.components.length), "components in " + read + " repositories with a model"),
      D.tile(D.figure(s.edges), "import edges between components"),
      D.tile(upward, "imports against the layering"),
      D.tile(D.figure(data.seam.imports), data.seam.from + " → " + data.seam.to + " imports"),
      D.tile(D.figure(s.adrs_placed) + " / " + D.figure(s.adrs_total), "ADRs placed on a component"));
  }

  function diagram(d) {
    var figure = h("div", { class: "diagram" });
    figure.innerHTML = d.svg; // Graphviz's SVG, drawn at build time from the public view
    return D.card(d.title, d.caption, figure);
  }

  function containers(data) {
    var state = { data: ["data"], planned: ["planned"], "private": ["private"], "public": null };
    return D.card("Containers", "Written by hand in og-dev-hub's system.yaml: one per thing that is deployed or published.",
      D.table([
        { label: "Container", cell: function (c) { return [h("strong", {}, c.name), h("span", { class: "sub" }, c.summary || "")]; } },
        { label: "Repository", cell: function (c) { return c.repo || ""; } },
        { label: "Technology", cell: function (c) { return c.tech || ""; } },
        { label: "", cell: function (c) { return state[c.state] ? D.pill(state[c.state][0]) : ""; } }
      ], data.containers));
  }

  function stages(data) {
    if (!data.stages.length) return null;
    var names = {};
    data.components.forEach(function (c) { names[c.id] = c; });
    return D.card("Stages", "The path data takes through the system, and the components that serve each stage. " +
      "Written by hand in the models.",
      D.table([
        { label: "Stage", cell: function (st) { return [h("strong", {}, st.name), h("span", { class: "sub" }, st.summary || "")]; } },
        { label: "Components", cell: function (st) {
          return st.components.length ? h("div", { class: "chips" }, st.components.map(function (id) {
            var c = names[id];
            return c && c.anchor ? h("a", { class: "pill pill-accent", href: "#component-" + c.anchor }, c.name) : D.pill(c ? c.name : id);
          })) : h("span", { class: "empty" }, "No component serves this stage.");
        } }
      ], data.stages));
  }

  function components(data) {
    var repos = [];
    data.components.forEach(function (c) { if (repos.indexOf(c.repo) < 0) repos.push(c.repo); });
    var select = h("select", { id: "component-repo" }, h("option", { value: "" }, "every repository"),
      repos.map(function (r) { return h("option", { value: r }, r); }));
    var holder = h("div", {});
    function draw() {
      var rows = data.components.filter(function (c) { return !select.value || c.repo === select.value; });
      holder.textContent = "";
      holder.appendChild(D.table([
        { label: "Component", cell: function (c) {
          return [h("strong", {}, c.name), " ", h("span", { class: "mono sub" }, c.id), h("span", { class: "sub" }, c.summary || "")];
        } },
        { label: "Repository", cell: function (c) { return [c.repo, h("span", { class: "sub" }, c.container_name || "")]; } },
        { label: "Layer", cell: function (c) { return c.layer === null || c.layer === undefined ? "" : String(c.layer); }, num: true },
        { label: "Size", cell: function (c) { return c.size; } },
        { label: "Claims", cell: function (c) {
          return h("ul", {}, c.paths.map(function (p) { return h("li", {}, h("a", { class: "mono", href: p.url }, p.path)); }));
        } },
        { label: "Governed by", cell: function (c) {
          if (!c.adrs.length) return h("span", { class: "empty" }, "no ADR placed");
          return h("ul", {}, c.adrs.map(function (a) {
            return h("li", {}, D.link(a.repo + " " + a.number, a.url), " ", h("span", { class: "sub" }, a.title + " (" +
              (a.via === "code" ? "cites its code" : "names it in the title") + (a.status !== "current" ? "; " + a.status : "") + ")"));
          }));
        } }
      ], rows, function (c) { return c.anchor ? "component-" + c.anchor : null; }));
    }
    select.addEventListener("change", draw);
    draw();
    return D.card("Components", "Each component a repository's model claims, with its measured size, the paths it claims " +
      "(at the commit read) and the ADRs placed on it: by the code an ADR cites, or by the component's name in its title.",
      h("div", { class: "toolbar" }, h("label", { for: "component-repo" }, "Repository"), select), holder);
  }

  function gaps(data) {
    var rows = data.gaps.map(function (g) {
      var what;
      if (g.unreadable) what = [D.pill("unreadable", "bad"), " ", g.unreadable];
      else if (g.no_model) what = [D.pill("no model", "warn"), " Its components, code and imports are unknown, not none: ", g.no_model];
      else {
        var unclaimed = g.unclaimed || [], stale = g.stale || [];
        what = [
          unclaimed.length || stale.length ? D.pill("gaps", "warn") : D.pill("claims complete", "good"), " ",
          unclaimed.length + " code files no component claims; " + stale.length + " claims that match no tracked file.",
          unclaimed.length || stale.length || g.system.length ? h("ul", {},
            unclaimed.map(function (p) { return h("li", {}, "Unclaimed: ", h("code", {}, p)); }),
            stale.map(function (st) { return h("li", {}, "Stale: ", h("code", {}, st.path), " (claimed by " + st.component + ")"); }),
            g.system.map(function (s) { return h("li", {}, s); })) : null
        ];
      }
      return { label: g.label, what: what };
    });
    return D.card("Gaps", "What each public repository's claims leave out, measured against its tracked files. " +
      "A gap is drawn, and never fails the build.",
      D.table([
        { label: "Repository", cell: function (r) { return h("strong", {}, r.label); } },
        { label: "Claims", cell: function (r) { return r.what; } }
      ], rows));
  }

  function layering(data) {
    if (data.layering === null) {
      return D.card("Layering", null, h("p", {}, "The layering cannot be measured until a model that declares layers is " +
        "read: a component without a layer has no upward for an import to cross, so there is no figure to give."));
    }
    return D.card("Layering", "Imports that go up a repository's declared layers, against the layering.",
      data.layering.map(function (l) {
        var n = l.upward.reduce(function (sum, e) { return sum + (e.imports || 0); }, 0);
        return [h("p", {}, h("strong", {}, l.label), ": " + l.upward.length + " edges (" + n + " imports) go against the " +
          "layering, of " + l.edges + " edges between its components."),
          l.upward.length ? D.table([
            { label: "From", cell: function (e) { return [D.link(e.from_name, "#component-" + e.from), " (layer " + e.from_layer + ")"]; } },
            { label: "To", cell: function (e) { return [D.link(e.to_name, "#component-" + e.to), " (layer " + e.to_layer + ")"]; } },
            { label: "Imports", cell: function (e) { return D.figure(e.imports); }, num: true }
          ], l.upward) : null];
      }));
  }

  function seam(data) {
    var s = data.seam, b = s.baseline, lines = [];
    if (s.imports === null || s.imports === undefined) {
      lines.push(h("p", {}, "The imports from " + s.from + " into " + s.to + " are unknown: " + s.from + " has no model at the ref read."));
    } else {
      lines.push(h("p", {}, D.figure(s.imports) + " imports from " + s.from + " into " + s.to +
        (s.pairs === null || s.pairs === undefined
          ? "; the component pairs cannot be drawn until " + s.to + "'s model is at the ref read."
          : ", across " + D.figure(s.pairs) + " component pairs.")));
    }
    if (b) {
      lines.push(typeof b.entries === "number"
        ? h("p", {}, "The engine-import baseline (", h("code", {}, b.path), ", in " + b.from + ") lists " + D.figure(b.entries) +
            " imports of engine modules, one per importing file and imported name; " + b.from + " makes " + D.figure(b.measured) + " of them.")
        : h("p", {}, "The engine-import baseline is unknown: " + (b.note || "") + ". " + b.from + " makes " + D.figure(b.measured) +
            " imports of engine modules."));
    }
    return D.card("Imports across repositories", "Measured from the code of every repository with a model. The seam between " +
      s.from + " and " + s.to + " is held to a baseline that only shrinks.", lines,
      D.table([
        { label: "From", cell: function (a) { return a.from_repo; } },
        { label: "Into", cell: function (a) { return a.to_repo; } },
        { label: "Imports", cell: function (a) { return D.figure(a.imports); }, num: true },
        { label: "Component pairs", cell: function (a) { return D.figure(a.pairs); }, num: true }
      ], data.across));
  }

  D.register("architecture", function () {
    return D.json("architecture").then(function (data) {
      if (!data.available) return D.unavailable(data, "The architecture");
      return [
        D.collected(data),
        tiles(data),
        repositories(data),
        h("h2", { class: "section-title" }, "Diagrams"),
        data.diagrams.map(diagram),
        containers(data),
        stages(data),
        components(data),
        h("h2", { class: "section-title" }, "Health"),
        gaps(data),
        layering(data),
        seam(data)
      ];
    });
  });
})();
