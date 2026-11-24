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
        el("p", {}, y.unmeasured.map(function (s) { return s.store_id; }).join(", "))) : null
    ];
  }

  D.register("benchmarking", function () {
    return D.json("benchmarking").then(function (data) {
      if (!data.available) return D.unavailable(data, "The Benchmarking results");
      return [D.collected(data), yardstick(data.yardstick)];
    });
  });
})();
