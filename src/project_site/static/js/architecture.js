/* The Architecture view (og-dev-hub#15), from data/architecture.json.
 *
 * The build decides each repository's, container's and gap's state and writes
 * every figure; this script only renders them. What is written by hand
 * (system.yaml's containers; each repository's components, layers and claims) and
 * what is measured from the code are said apart, and unknown is never 0. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

  // How each state the build wrote is shown: [label, tone].
  var REPO = { read: ["read", "ok"], no_model: ["no model", "caution"], unreadable: ["unreadable", "fault"],
    planned: ["planned"], "private": ["private: container only"] };
  var CONTAINER = { data: ["data"], planned: ["planned"], "private": ["private"], "public": null };
  var GAP = { complete: ["claims complete", "ok"], gaps: ["gaps", "caution"], no_model: ["no model", "caution"],
    unreadable: ["unreadable", "fault"], unknown: ["unknown"] };

  function repositories(data) {
    return D.panel("Repositories", "Every repository system.yaml lists, and the commit of each that was read. " +
      "A private repository is drawn as its container only, and is never read.",
      data.repos.filter(function (r) { return r.refresh_error; }).map(function (r) {
        return D.alert("", el("p", {}, el("strong", {}, "The " + r.name + " refresh failed"),
          ": " + r.refresh_error + ". This is the " + r.ref + " its clone already had, so it may be behind."));
      }),
      D.table([
        { label: "Repository", cell: function (r) { return [D.link(r.name, r.url), r.status ? el("span", { class: "detail" }, r.status) : null]; } },
        { label: "State", cell: function (r) { return D.tag(REPO[r.state] || [r.state]); } },
        { label: "Commit read", cell: function (r) {
          return r.commit ? [el("a", { class: "code-face", href: r.url + "/commit/" + r.commit }, D.short(r.commit)), " on " + r.ref] : "";
        } },
        { label: "Committed", cell: function (r) { return r.committed || ""; } },
        { label: "Note", cell: function (r) { return r.why || ""; } }
      ], data.repos));
  }

  function stats(data) {
    var s = data.summary || {};
    return el("div", { class: "stats" },
      D.stat(D.count(data.counts.components), "components in " + data.counts.repos_with_model + " repositories with a model"),
      D.stat(D.count(s.edges), "import edges between components"),
      D.stat(D.count(s.upward_imports), "imports against the layering"),
      D.stat(D.count(data.seam.imports), data.seam.from + " → " + data.seam.to + " imports"),
      D.stat(D.count(s.adrs_placed) + " / " + D.count(s.adrs_total), "ADRs placed on a component"));
  }

  function drawing(d) {
    var frame = el("div", { class: "drawing" });
    frame.innerHTML = d.svg; // Graphviz's SVG, drawn at build time from the public view
    return D.panel(d.title, d.caption, frame);
  }

  function containers(data) {
    return D.panel("Containers", "Written by hand in og-dev-hub's system.yaml: one per thing that is deployed or published.",
      D.table([
        { label: "Container", cell: function (c) { return [el("strong", {}, c.name), el("span", { class: "detail" }, c.summary || "")]; } },
        { label: "Repository", cell: function (c) { return c.repo || ""; } },
        { label: "Technology", cell: function (c) { return c.tech || ""; } },
        { label: "", cell: function (c) { return CONTAINER[c.state] ? D.tag(CONTAINER[c.state]) : ""; } }
      ], data.containers));
  }

  function stages(data) {
    if (!data.stages.length) return null;
    var byId = {};
    data.components.forEach(function (c) { byId[c.id] = c; });
    return D.panel("Stages", "The path data takes through the system, and the components that serve each stage. " +
      "Written by hand in the models.",
      D.table([
        { label: "Stage", cell: function (st) { return [el("strong", {}, st.name), el("span", { class: "detail" }, st.summary || "")]; } },
        { label: "Components", cell: function (st) {
          return st.components.length ? el("div", { class: "tag-row" }, st.components.map(function (id) {
            var c = byId[id];
            return c && c.anchor ? el("a", { class: "tag tag-link", href: "#component-" + c.anchor }, c.name) : D.tag(c ? c.name : id);
          })) : el("span", { class: "none-note" }, "No component serves this stage.");
        } }
      ], data.stages));
  }

  function components(data) {
    var holder = el("div", {});
    function draw(repo) {
      holder.textContent = "";
      holder.appendChild(D.table([
        { label: "Component", cell: function (c) {
          return [el("strong", {}, c.name), " ", el("span", { class: "code-face detail" }, c.id), el("span", { class: "detail" }, c.summary || "")];
        } },
        { label: "Repository", cell: function (c) { return [c.repo, el("span", { class: "detail" }, c.container_name || "")]; } },
        { label: "Layer", cell: function (c) { return c.layer === null || c.layer === undefined ? "" : String(c.layer); }, count: true },
        { label: "Size", cell: function (c) { return c.size; } },
        { label: "Claims", cell: function (c) {
          return el("ul", {}, c.paths.map(function (p) { return el("li", {}, el("a", { class: "code-face", href: p.url }, p.path)); }));
        } },
        { label: "Governed by", cell: function (c) {
          if (!c.adrs.length) return el("span", { class: "none-note" }, "no ADR placed");
          return el("ul", {}, c.adrs.map(function (a) {
            return el("li", {}, D.link(a.repo + " " + a.number, a.url), " ", el("span", { class: "detail" }, a.title + " (" +
              (a.via === "code" ? "cites its code" : "names it in the title") + (a.status !== "current" ? "; " + a.status : "") + ")"));
          }));
        } }
      ], data.components.filter(function (c) { return !repo || c.repo === repo; }),
      function (c) { return c.anchor ? "component-" + c.anchor : null; }));
    }
    draw("");
    return D.panel("Components", "Each component a repository's model claims, with its measured size, the paths it claims " +
      "(at the commit read) and the ADRs placed on it: by the code an ADR cites, or by the component's name in its title.",
      D.repoFilter("component-repo", data.component_repos, draw), holder);
  }

  function gaps(data) {
    return D.panel("Gaps", "What each public repository's claims leave out, measured against its tracked files. " +
      "A gap is drawn, and never fails the build.",
      D.table([
        { label: "Repository", cell: function (g) { return el("strong", {}, g.label); } },
        { label: "Claims", cell: function (g) {
          var head = [D.tag(GAP[g.state] || [g.state]), " "];
          if (g.state === "unreadable") return head.concat(g.unreadable);
          if (g.state === "no_model") return head.concat("Its components, code and imports are unknown, not none: ", g.no_model);
          if (g.state === "unknown") return head.concat("Its claims were not measured, so its gaps are unknown, not none.");
          return head.concat(g.unclaimed.length + " code files no component claims; " + g.stale.length +
            " claims that match no tracked file.", g.state === "gaps" ? el("ul", {},
              g.unclaimed.map(function (p) { return el("li", {}, "Unclaimed: ", el("code", {}, p)); }),
              g.stale.map(function (st) { return el("li", {}, "Stale: ", el("code", {}, st.path), " (claimed by " + st.component + ")"); }),
              g.system.map(function (s) { return el("li", {}, s); })) : null);
        } }
      ], data.gaps));
  }

  function layering(data) {
    if (data.layering === null) {
      return D.panel("Layering", null, el("p", {}, "The layering cannot be measured until a model that declares layers is " +
        "read: a component without a layer has no upward for an import to cross, so there is no figure to give."));
    }
    return D.panel("Layering", "Imports that go up a repository's declared layers, against the layering.",
      data.layering.map(function (l) {
        return [el("p", {}, el("strong", {}, l.label), ": " + l.upward.length + " edges (" + l.imports + " imports) go against the " +
          "layering, of " + l.edges + " edges between its components."),
          l.upward.length ? D.table([
            { label: "From", cell: function (e) { return [D.link(e.from_name, "#component-" + e.from), " (layer " + e.from_layer + ")"]; } },
            { label: "To", cell: function (e) { return [D.link(e.to_name, "#component-" + e.to), " (layer " + e.to_layer + ")"]; } },
            { label: "Imports", cell: function (e) { return D.count(e.imports); }, count: true }
          ], l.upward) : null];
      }));
  }

  function seam(data) {
    var s = data.seam, b = s.baseline, lines = [];
    if (s.imports === null) {
      lines.push(el("p", {}, "The imports from " + s.from + " into " + s.to + " are unknown: " + s.from + " has no model at the ref read."));
    } else {
      lines.push(el("p", {}, D.count(s.imports) + " imports from " + s.from + " into " + s.to +
        (s.pairs === null
          ? "; the component pairs cannot be drawn until " + s.to + "'s model is at the ref read."
          : ", across " + D.count(s.pairs) + " component pairs.")));
    }
    if (b) {
      lines.push(b.entries !== null
        ? el("p", {}, "The engine-import baseline (", el("code", {}, b.path), ", in " + b.from + ") lists " + D.count(b.entries) +
            " imports of engine modules, one per importing file and imported name; " + b.from + " makes " + D.count(b.measured) + " of them.")
        : el("p", {}, "The engine-import baseline is unknown: " + (b.note || "") + ". " + b.from + " makes " + D.count(b.measured) +
            " imports of engine modules."));
    }
    return D.panel("Imports across repositories", "Measured from the code of every repository with a model. The seam between " +
      s.from + " and " + s.to + " is held to a baseline that only shrinks.", lines,
      D.table([
        { label: "From", cell: function (a) { return a.from_repo; } },
        { label: "Into", cell: function (a) { return a.to_repo; } },
        { label: "Imports", cell: function (a) { return D.count(a.imports); }, count: true },
        { label: "Component pairs", cell: function (a) { return D.count(a.pairs); }, count: true }
      ], data.across));
  }

  D.register("architecture", function () {
    return D.json("architecture").then(function (data) {
      if (!data.available) return D.unavailable(data, "The architecture");
      return [
        D.collected(data),
        stats(data),
        repositories(data),
        el("h2", { class: "part-heading" }, "Diagrams"),
        data.diagrams.map(drawing),
        containers(data),
        stages(data),
        components(data),
        el("h2", { class: "part-heading" }, "Health"),
        gaps(data),
        layering(data),
        seam(data)
      ];
    });
  });
})();
