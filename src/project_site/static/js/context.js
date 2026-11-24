/* The Context view (og-dev-hub#15), from data/context.json: the hub's CONTEXT.md, and each repository's own glossary. */
(function () {
  "use strict";
  var D = window.DevHub, h = D.h;

  D.register("context", function () {
    return D.json("context").then(function (data) {
      var prose = h("div", { class: "prose" });
      prose.innerHTML = data.html; // rendered at build time from the hub's CONTEXT.md, every character escaped
      var glossaries = data.available
        ? D.table([
            { label: "Repository", cell: function (g) { return g.repo; } },
            { label: "Glossary", cell: function (g) { return g.url ? D.link("CONTEXT.md", g.url) : h("span", { class: "empty" }, g.note); } }
          ], data.glossaries)
        : D.unavailable(data, "The repositories");
      return [
        D.card(null, null, prose, h("p", { class: "caption" }, "From ", D.link("og-dev-hub's CONTEXT.md", data.source), ".")),
        D.card("Each repository's own terms", "A term one repository owns stays in that repository's CONTEXT.md, " +
          "at the commit read.", glossaries)
      ];
    });
  });
})();
