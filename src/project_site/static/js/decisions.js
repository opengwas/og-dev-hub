/* The Decisions view (og-dev-hub#15), from data/decisions.json: one index of every public repository's ADRs. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

  // How each status the collector wrote is shown: [label, tone].
  var STATUS = { current: ["current", "ok"], superseded: ["superseded", "caution"], amended: ["amended", "link"] };

  D.register("decisions", function () {
    return D.json("decisions").then(function (data) {
      if (!data.available) return D.unavailable(data, "The decisions");
      var shown = el("p", { class: "panel-note" });
      var holder = el("div", {});
      function draw(repo) {
        var rows = data.adrs.filter(function (a) { return !repo || a.repo === repo; });
        shown.textContent = rows.length + " ADRs, " + rows.filter(function (a) { return a.components.length; }).length +
          " placed on a component.";
        holder.textContent = "";
        holder.appendChild(D.table([
          { label: "ADR", cell: function (a) { return el("span", { class: "code-face" }, a.number); } },
          { label: "Title", cell: function (a) { return D.link(a.title, a.url); } },
          { label: "Status", cell: function (a) { return D.tag(STATUS[a.status] || [a.status]); } },
          { label: "Repository", cell: function (a) { return a.repo; } },
          { label: "Governs", cell: function (a) {
            if (!a.components.length) return el("span", { class: "none-note" }, "placed on no component");
            return el("div", { class: "tag-row" }, a.components.map(function (c) {
              return el("a", { class: "tag tag-link", href: "#component-" + c.id,
                title: c.via === "code" ? "cites its code" : "names it in its title" }, c.name);
            }));
          } },
          { label: "Cites", cell: function (a) {
            return a.cites.length ? el("ul", {}, a.cites.map(function (c) { return el("li", {}, D.link(c.text, c.url)); })) : "";
          } }
        ], rows));
      }
      draw("");
      return [
        D.collected(data),
        D.panel(null, "Each ADR is placed on the components whose code it cites, or whose name is in its title. " +
          "A citation of another repository's decision (“opengwasdb ADR 0039”) links to it.",
          D.repoFilter("decision-repo", data.repos, draw), shown, holder)
      ];
    });
  });
})();
