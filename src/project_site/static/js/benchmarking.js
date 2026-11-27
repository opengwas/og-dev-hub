/* The Benchmarking tab (og-dev-hub#19), from data/benchmarking.json: yardstick's results.
 *
 * The label is Benchmarking; the thing is the yardstick, and the code, the JSON and the specs keep that name.
 * The build decides every figure and writes it as text; this script only renders it. The trend charts are
 * SVG drawn at build time. */
(function () {
  "use strict";
  var D = window.DevHub, el = D.el;

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
    var newer = s.notice ? D.alert("", el("p", {}, s.notice)) : null;
    if (s.pending) return D.panel(title, null, newer, D.alert("", el("p", {}, s.pending)));
    return D.panel(title, null, newer,
      el("div", { class: "tag-row" }, D.tag(s.layout), D.tag(s.coverage),
        s.flags.map(function (f) { return D.tag([f, "caution"]); })),
      el("div", { class: "facts" },
        el("div", { class: "fact" }, el("div", { class: "fact-label" }, "engine"), el("div", { class: "fact-value" }, s.engine_version)),
        el("div", { class: "fact" }, el("div", { class: "fact-label" }, "run"), el("div", { class: "fact-value" }, s.date + " · " + s.workload_id)),
        fact("peak memory", s.peak_memory), fact("size on disk", s.size_on_disk)),
      measures(s.measures));
  }

  function trends(y, title) {
    if (!y.trends.length) return D.panel(title || "Trends", "No measure has been recorded at two engine versions yet.");
    return D.panel(title || "Trends across engine versions",
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

  /* The LD Stores (opengwasdb-stores#504): a table of one row per Store, each row an anchor its tile links to, then each
   * Store's measures and the trends. Keyed by LD id, apart from the GWAS Stores. */
  function ldYardstick(ld) {
    var head = el("h2", { class: "section-heading" }, "LD Stores");
    if (!ld.available) return [head, D.alert("note", el("p", {}, ld.gap))];
    var notice = ld.notice ? D.alert("", el("p", {}, ld.notice)) : null;
    if (!ld.stores.length) return [head, notice];
    var summary = D.table([
      { label: "LD Store", cell: function (s) { return [el("span", { class: "code-face" }, s.store_id), " ", s.label || ""]; } },
      { label: "Kind", cell: function (s) { return s.kind; } },
      { label: "Versions", cell: function (s) { return s.versions; } },
      { label: "Run", cell: function (s) { return s.run; } },
      { label: "Peak memory", count: true, cell: function (s) { return s.peak_memory.display; } },
      { label: "Size on disk", cell: function (s) {
        return [s.size_on_disk.display].concat(s.size_on_disk.details.map(function (d) { return el("span", { class: "detail" }, d); }));
      } }
    ], ld.stores, function (s) { return s.anchor; });
    return [head, notice, summary,
      ld.stores.map(function (s) {
        return D.panel([s.store_id, " ", s.label || ""], null,
          s.notice ? D.alert("", el("p", {}, s.notice)) : null,
          s.flags.length ? el("div", { class: "tag-row" }, s.flags.map(function (f) { return D.tag([f, "caution"]); })) : null,
          measures(s.measures));
      }),
      trends(ld, "LD trends across engine versions")];
  }

  function yardstick(y) {
    if (!y.available) return D.alert("", el("p", {}, el("strong", {}, "No yardstick results"), ": " + y.reason + "."));
    return [
      el("p", { class: "panel-note" }, y.runs + " runs committed (" + y.workloads.join(", ") + "). It records; it is not a gate. " +
        "A run is marked when " + y.veeam_rule + ", or when it recorded " + y.load_rule + "."),
      y.invalid.map(function (i) {
        return D.alert("severe", el("p", {}, el("strong", {}, i.file + " is not a valid result"), ": " + i.error + "."));
      }),
      trends(y),
      el("h2", { class: "section-heading" }, "Latest run per Store"),
      y.stores.map(storePanel),
      y.unmeasured.length ? D.panel("Not measured by yardstick",
        "The workload names one representative Store per layout; these are not measured.",
        el("p", {}, y.unmeasured.map(function (s) { return s.store_id; }).join(", "))) : null,
      ldYardstick(y.ld)
    ];
  }

  D.register("benchmarking", function () {
    return D.json("benchmarking").then(function (data) {
      if (!data.available) return D.unavailable(data, "The Benchmarking results");
      return [D.collected(data), yardstick(data.yardstick)];
    });
  });
})();
