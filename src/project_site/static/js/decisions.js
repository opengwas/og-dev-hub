/* The Decisions view (og-dev-hub#15), from data/decisions.json: one index of every public repository's ADRs. */
(function () {
  "use strict";
  var D = window.DevHub, h = D.h;

  function status(s) {
    return D.pill(s || "current", s === "superseded" ? "warn" : s === "amended" ? "accent" : "good");
  }

  D.register("decisions", function () {
    return D.json("decisions").then(function (data) {
      if (!data.available) return D.unavailable(data, "The decisions");
      var select = h("select", { id: "decision-repo" }, h("option", { value: "" }, "every repository"),
        data.repos.map(function (r) { return h("option", { value: r }, r); }));
      var count = h("span", {});
      var holder = h("div", {});
      function draw() {
        var rows = data.adrs.filter(function (a) { return !select.value || a.repo === select.value; });
        var placed = rows.filter(function (a) { return a.components.length; }).length;
        count.textContent = rows.length + " ADRs, " + placed + " placed on a component.";
        holder.textContent = "";
        holder.appendChild(D.table([
          { label: "ADR", cell: function (a) { return h("span", { class: "mono" }, a.number); } },
          { label: "Title", cell: function (a) { return D.link(a.title, a.url); } },
          { label: "Status", cell: function (a) { return status(a.status); } },
          { label: "Repository", cell: function (a) { return a.repo; } },
          { label: "Governs", cell: function (a) {
            if (!a.components.length) return h("span", { class: "empty" }, "placed on no component");
            return h("div", { class: "chips" }, a.components.map(function (c) {
              return h("a", { class: "pill pill-accent", href: "#component-" + c.id,
                title: c.via === "code" ? "cites its code" : "names it in its title" }, c.name);
            }));
          } },
          { label: "Cites", cell: function (a) {
            return a.cites.length ? h("ul", {}, a.cites.map(function (c) { return h("li", {}, D.link(c.text, c.url)); })) : "";
          } }
        ], rows));
      }
      select.addEventListener("change", draw);
      draw();
      return [
        D.collected(data),
        D.card(null, "Each ADR is placed on the components whose code it cites, or whose name is in its title. " +
          "A citation of another repository's decision (“opengwasdb ADR 0039”) links to it.",
          h("div", { class: "toolbar" }, h("label", { for: "decision-repo" }, "Repository"), select, count), holder)
      ];
    });
  });
})();
