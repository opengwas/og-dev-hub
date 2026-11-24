/* The Context view (og-dev-hub#15), from data/context.json: the hub's CONTEXT.md, and each repository's own glossary. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

  D.register("context", function () {
    return D.json("context").then(function (data) {
      var text = el("div", { class: "glossary-text" });
      text.innerHTML = data.html; // rendered at build time from the hub's CONTEXT.md, every character escaped
      var glossaries = data.available
        ? D.table([
            { label: "Repository", cell: function (g) { return g.repo; } },
            { label: "Glossary", cell: function (g) { return g.url ? D.link("CONTEXT.md", g.url) : el("span", { class: "none-note" }, g.note); } }
          ], data.glossaries)
        : D.unavailable(data, "The repositories");
      return [
        D.panel(null, null, text, el("p", { class: "panel-note" }, "From ", D.link("og-dev-hub's CONTEXT.md", data.source), ".")),
        D.panel("Each repository's own terms", "A term one repository owns stays in that repository's CONTEXT.md, " +
          "at the commit read.", glossaries)
      ];
    });
  });
})();
