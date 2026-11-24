/* The Stores view (og-dev-hub#16), from data/stores.json: every GWAS Store in the registry.
 *
 * The build decides every figure and every gap and writes it as text; this script
 * only renders it. A field the registry does not hold yet is drawn as a gap that
 * names what fills it, never as 0. The trend charts are SVG drawn at build time. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

  /* A cell the build wrote: its text, or the gap that names what fills it. */
  function field(cell) {
    if (cell.gap) return el("span", { class: "gap" }, cell.gap);
    return [cell.text, cell.detail ? el("span", { class: "detail" }, cell.detail) : null];
  }
  function column(label, key) {
    return { label: label, cell: function (row) { return field(row[key]); } };
  }

  function inventory(data) {
    return D.panel("Inventory", "One row per Release Bundle in " + data.registry.name + "'s stores/, read at the commit " +
      D.short(data.registry.commit) + ". A field the bundle does not hold yet is a gap that names what fills it; it is never 0.",
      D.table([
        { label: "Store", cell: function (r) { return [D.link(r.store_id, r.url), el("strong", {}, " " + (r.label || ""))]; } },
        { label: "Description", cls: "wide-col", cell: function (r) { return r.description || ""; } },
        column("Layout", "layout"), column("Completion", "completion_state"), column("Coverage", "coverage"),
        column("Release Status", "status"), column("Storage", "store_bytes"), column("Variants", "n_variants"),
        column("Top hits", "top_hits"), column("HM3", "has_hm3"), column("Rho", "has_rho"), column("Clumped", "n_clumped"),
        column("Analyses", "n_analyses"), column("Median sample size", "median_sample_size"), column("Ancestry", "ancestry")
      ], data.inventory, function (r) { return "store-" + r.store_id; }, "scroller-tall"));
  }

  D.register("stores", function () {
    return D.json("stores").then(function (data) {
      if (!data.available) return D.unavailable(data, "The Stores");
      return [D.collected(data), D.alert("note", el("p", {}, data.ld_stores.gap)), inventory(data)];
    });
  });
})();
