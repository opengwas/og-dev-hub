/* The Stores view (og-dev-hub#16), from data/stores.json: every GWAS Store, and yardstick's results.
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
        { label: "Store", cell: function (r) {
          return [D.link(r.store_id, r.url), el("strong", {}, " " + (r.label || "")), r.description ? el("span", { class: "detail" }, r.description) : null];
        } },
        column("Layout", "layout"), column("Completion", "completion_state"), column("Coverage", "coverage"),
        column("Release Status", "status"), column("Storage", "store_bytes"), column("Variants", "n_variants"),
        column("Top hits", "top_hits"), column("HM3", "has_hm3"), column("Rho", "has_rho"), column("Clumped", "n_clumped"),
        column("Analyses", "n_analyses"), column("Median sample size", "median_sample_size"), column("Ancestry", "ancestry")
      ], data.inventory, function (r) { return "store-" + r.store_id; }));
  }

  function measures(rows) {
    return D.table([
      { label: "Measure", cell: function (m) {
        return [el("span", { class: "code-face" }, m.name), m.path ? el("span", { class: "detail" }, "answered by its " + m.path) : null];
      } },
      { label: "Median", count: true, cell: function (m) { return m.median || ""; } },
      { label: "p95", count: true, cell: function (m) { return m.p95 || ""; } },
      { label: "", cell: function (m) {
        if (m.state === "measured") return "";
        return [D.tag([m.label, m.tone]), m.note ? el("span", { class: "detail" }, m.note) : null];
      } }
    ], rows);
  }

  function fact(label, f) {
    return el("div", { class: "fact" }, el("div", { class: "fact-label" }, label),
      f.text ? el("div", { class: "fact-value" }, f.text)
        : el("div", { class: "fact-value gap" }, [D.tag([f.label, f.tone]), " ", f.note || ""]));
  }

  function storePanel(s) {
    var title = [s.store_id, " ", s.label || ""];
    var newer = s.not_in_latest ? D.alert("", el("p", {}, el("strong", {}, s.not_in_latest),
      s.state === "measured" ? ": this is the latest run that measured it." : ".")) : null;
    if (s.state !== "measured") {
      return D.panel(title, null, newer, D.alert("", el("p", {}, el("strong", {}, "Pending in its latest run"), ": " + (s.reason || "no reason recorded") + ".")));
    }
    return D.panel(title, null, newer,
      el("div", { class: "tag-row" }, D.tag(s.layout), D.tag(s.coverage),
        s.flags.map(function (f) { return D.tag([f, "caution"]); })),
      el("div", { class: "facts" },
        el("div", { class: "fact" }, el("div", { class: "fact-label" }, "engine"), el("div", { class: "fact-value" }, s.engine_version)),
        el("div", { class: "fact" }, el("div", { class: "fact-label" }, "run"), el("div", { class: "fact-value" }, s.date + " · " + s.workload_id)),
        fact("peak memory", s.peak_memory), fact("size on disk", s.size_on_disk)),
      measures(s.measures));
  }

  function trends(y) {
    if (!y.trends.length) return D.panel("Trends", "No measure has been recorded at two engine versions yet.");
    return D.panel("Trends across engine versions",
      "One chart per measure, the median over the warm reads (peak memory and size on disk for those two), one point per engine version in the order they were first run, " +
      "one line per Store. A ringed point is a run taken in the Veeam window or under load; hover for why.",
      el("div", { class: "trends" }, y.trends.map(function (t) {
        var frame = el("div", { class: "trend-frame" });
        frame.innerHTML = t.svg; // SVG drawn at build time, every figure escaped
        return el("div", { class: "trend" },
          el("h3", {}, el("span", { class: "code-face" }, t.measure), " ", el("span", { class: "detail" }, t.unit)),
          el("div", { class: "tag-row" }, t.series.map(function (s) {
            return el("span", { class: "tag key " + s.class }, s.store_id);
          })),
          frame);
      })));
  }

  function yardstick(y) {
    if (!y.available) return D.alert("", el("p", {}, el("strong", {}, "No yardstick results"), ": " + y.reason + "."));
    return [
      el("h2", { class: "section-heading" }, "Yardstick"),
      el("p", { class: "pane-lede" }, "The fixed query workload, run once per engine version, " + y.runs + " runs committed (" +
        y.workloads.join(", ") + "). It records; it is not a gate. Each Store shows its latest run only. " +
        "A run is marked when " + y.veeam_rule + ", or when it recorded " + y.load_rule + "."),
      y.invalid.map(function (i) {
        return D.alert("severe", el("p", {}, el("strong", {}, i.file + " is not a valid result"), ": " + i.error + "."));
      }),
      y.stores.map(storePanel),
      y.unmeasured.length ? D.panel("Not measured by yardstick",
        "The workload names one representative Store per layout; these are not measured.",
        el("p", {}, y.unmeasured.map(function (s) { return s.store_id; }).join(", "))) : null,
      trends(y)
    ];
  }

  D.register("stores", function () {
    return D.json("stores").then(function (data) {
      if (!data.available) return D.unavailable(data, "The Stores");
      return [D.collected(data), inventory(data), yardstick(data.yardstick)];
    });
  });
})();
