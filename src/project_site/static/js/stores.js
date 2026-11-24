/* The Stores view (og-dev-hub#16, #21), from data/stores.json: every GWAS Store in the registry, one tile each.
 *
 * The build decides every figure and every gap and writes it as text; this script
 * only renders it. A field the registry does not hold yet is drawn as a gap that
 * names what fills it, never as 0. The trend charts are SVG drawn at build time. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

  /* One tile per Store: a <details>, so it opens and closes by click, Enter or Space with no state here. The build wrote
   * every text, including `n/a` for a gap and the short description; the reasons are in the open tile. */
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
    var node = el("details", { class: "panel tile", id: "store-" + row.store_id },
      el("summary", {},
        el("span", { class: "tile-head" },
          el("span", { class: "tile-id" }, D.link(row.store_id, row.url)),
          el("strong", { class: "tile-label" }, row.label || ""),
          D.tag(status.display, status.gap ? null : "ok")),
        row.summary ? el("span", { class: "tile-summary" }, row.summary) : null),
      facts,
      el("div", { class: "tile-more" }, row.description ? el("p", {}, row.description) : null, why));
    return node;
  }

  function tiles(data) {
    if (!data.inventory.length) return el("p", { class: "none-note" }, "None.");
    return el("div", { class: "tiles" }, data.inventory.map(tile));
  }

  /* Escape closes the tile the focus is in. */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var open = e.target && e.target.closest ? e.target.closest("details.tile[open]") : null;
    if (open) { open.open = false; var s = open.querySelector("summary"); if (s) s.focus(); }
  });

  D.register("stores", function () {
    return D.json("stores").then(function (data) {
      if (!data.available) return D.unavailable(data, "The Stores");
      return [D.collected(data), D.alert("note", el("p", {}, data.ld_stores.gap)), tiles(data)];
    });
  });
})();
