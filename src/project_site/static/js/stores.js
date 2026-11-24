/* The Stores view (og-dev-hub#16, #21), from data/stores.json: every GWAS Store in the registry, one tile each.
 *
 * The build decides every text, tone and `n/a`; this script only renders it. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

  /* One tile per Store: a <details>, so a click anywhere on the header, short description or facts (all in the <summary>)
   * opens it, and Enter or Space do too, with no state here. The body holds what the closed tile leaves out: the link,
   * the full description and the reason behind each `n/a`. */
  function tile(row) {
    var status = row.status;
    var facts = el("dl", { class: "tile-facts" }, row.facts.map(function (f) {
      return [el("dt", {}, f.label),
        el("dd", { class: f.na ? "gap" : null }, f.display, f.detail ? el("span", { class: "detail" }, f.detail) : null)];
    }));
    var why = row.why_na.length
      ? el("div", {}, el("h3", {}, "Why n/a"),
          el("ul", { class: "tile-why" }, row.why_na.map(function (w) { return el("li", {}, el("strong", {}, w.label + ": "), w.reason); })))
      : null;
    return el("details", { class: "panel tile", id: "store-" + row.store_id },
      el("summary", {},
        el("span", { class: "tile-head" },
          el("span", { class: "tile-id" }, row.store_id),
          el("strong", { class: "tile-label" }, row.label || ""),
          D.tag(status.display, status.tone)),
        row.summary ? el("span", { class: "tile-summary" }, row.summary) : null,
        facts),
      el("div", { class: "tile-more" },
        row.url ? el("p", {}, D.link(row.store_id + " in the registry", row.url)) : null,
        row.description ? el("p", {}, row.description) : null, why));
  }

  function tiles(data) {
    if (!data.inventory.length) return el("p", { class: "none-note" }, "None.");
    return el("div", { class: "tiles" }, data.inventory.map(tile));
  }

  /* Escape closes every open tile, whether or not the focus is inside one (Safari does not focus a <summary> on click). */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    Array.prototype.forEach.call(document.querySelectorAll("details.tile[open]"), function (t) { t.open = false; });
  });

  D.register("stores", function () {
    return D.json("stores").then(function (data) {
      if (!data.available) return D.unavailable(data, "The Stores");
      return [D.collected(data), D.alert("note", el("p", {}, data.ld_stores.gap)), tiles(data)];
    });
  });
})();
