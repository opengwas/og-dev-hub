/* The Dev Hub's page (og-dev-hub#15): the views' links, the theme, and what every view shares.
 *
 * Each view is one script that calls DevHub.register(name, render); render()
 * draws the view into its pane the first time its link is followed, from
 * data/<name>.json. The build decides every state and figure; a script only
 * renders what it is given. Every fact is set as text, never as markup; the only
 * markup a view inserts is what the build wrote (Graphviz's SVG, the rendered
 * glossary). Every path is relative, so the page works from any sub-path. */
(function () {
  "use strict";

  var THEME_KEY = "devhub-theme";

  function stored() {
    try { return window.localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }
  function prefersDark() {
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }
  document.documentElement.setAttribute("data-theme", stored() || (prefersDark() ? "dark" : "light"));

  var views = {};
  var drawn = {};

  /* el("a", {href: url, class: "x"}, "text", node, [more]): an element; strings become text nodes. */
  function el(tag, attrs) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") node.className = value;
      else node.setAttribute(key, value === true ? "" : String(value));
    });
    for (var i = 2; i < arguments.length; i++) add(node, arguments[i]);
    return node;
  }
  function add(node, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { add(node, c); }); return; }
    node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }

  /* A link when there is a URL, the text alone when there is none. */
  function link(text, url) {
    return url ? el("a", { href: url }, text) : document.createTextNode(text);
  }
  /* tag(["read", "ok"]) or tag("planned"): a small label, its second part its tone. */
  function tag(label, tone) {
    if (Array.isArray(label)) { tone = label[1]; label = label[0]; }
    return el("span", { class: "tag" + (tone ? " tag-" + tone : "") }, label);
  }
  /* A count, or "unknown": unknown is never 0. */
  function count(n) {
    return n === null || n === undefined ? "unknown" : Number(n).toLocaleString("en-GB");
  }
  function short(commit) {
    return commit ? String(commit).slice(0, 12) : "";
  }
  function panel(title, note) {
    var node = el("div", { class: "panel" });
    if (title) node.appendChild(el("h2", {}, title));
    if (note) node.appendChild(el("p", { class: "panel-note" }, note));
    for (var i = 2; i < arguments.length; i++) add(node, arguments[i]);
    return node;
  }
  function alert(tone) {
    var node = el("div", { class: "panel alert" + (tone ? " alert-" + tone : "") });
    for (var i = 1; i < arguments.length; i++) add(node, arguments[i]);
    return node;
  }
  function stat(value, label) {
    return el("div", { class: "stat" + (value === "unknown" ? " stat-unknown" : "") },
      el("div", { class: "stat-number" }, value), el("div", { class: "stat-label" }, label));
  }
  /* columns: [{label, cell: function (row) -> node|string, count: bool}]; rowId(row) names a row's anchor. */
  function table(columns, rows, rowId, scrollClass) {
    if (!rows.length) return el("p", { class: "none-note" }, "None.");
    var head = el("tr", {}, columns.map(function (c) { return el("th", { class: (c.count ? "count" : "") + (c.cls ? " " + c.cls : "") || null }, c.label); }));
    var body = el("tbody", {}, rows.map(function (row) {
      return el("tr", { id: rowId ? rowId(row) : null }, columns.map(function (c) {
        return el("td", { class: (c.count ? "count" : "") + (c.cls ? " " + c.cls : "") || null }, c.cell(row));
      }));
    }));
    return el("div", { class: "scroller" + (scrollClass ? " " + scrollClass : "") }, el("table", {}, el("thead", {}, head), body));
  }
  /* A <select> of `values` (plus "every repository"), calling `draw` on each change. */
  function repoFilter(id, values, draw) {
    var select = el("select", { id: id }, el("option", { value: "" }, "every repository"),
      values.map(function (v) { return el("option", { value: v }, v); }));
    select.addEventListener("change", function () { draw(select.value); });
    return el("div", { class: "filters" }, el("label", { for: id }, "Repository"), select);
  }
  function collected(data) {
    return el("p", { class: "panel-note" }, "Collected " + (data.collected_at || "at an unknown time") + ".");
  }
  /* The source could not be read: say which, and why, instead of drawing nothing. */
  function unavailable(data, what) {
    return alert("severe", el("p", {}, el("strong", {}, what + " could not be collected"), ": " + (data.error || "no reason was recorded") + "."));
  }
  /* A drawing that can be enlarged: the SVG fills the width; "Enlarge" opens it over the page, where it can
   * be zoomed (buttons) and scrolled. Escape or "Close" returns. Plain JS; the SVG itself is the build's. */
  function naturalWidth(frame) {
    var svg = frame.querySelector && frame.querySelector("svg");
    var m = svg && /^([\d.]+)(pt|px)?$/.exec(svg.getAttribute("width") || "");
    return m ? Math.round(parseFloat(m[1]) * (m[2] === "pt" ? 4 / 3 : 1)) : 0;
  }
  function zoomable(frame) {
    var level = 1, open = false;
    var bar = el("div", { class: "drawing-bar" });
    var wrap = el("div", { class: "drawing-wrap" }, bar, frame);
    var natural = naturalWidth(frame);
    function apply() {
      var svg = frame.querySelector("svg");
      if (!svg) return;
      svg.style.width = open ? Math.round(level * 100) + "%" : "";
      svg.style.maxWidth = open || !natural ? "none" : natural + "px"; // a small diagram is never stretched past its own size
      if (!open && !natural) svg.style.maxWidth = "";
    }
    function mode(on) {
      open = on; level = 1;
      wrap.classList.toggle("drawing-full", on);
      toggle.textContent = on ? "Close" : "Enlarge";
      zoomControls.hidden = !on;
      apply();
    }
    function button(label, title, click) {
      var b = el("button", { type: "button", class: "button button-plain", title: title, "aria-label": title }, label);
      b.addEventListener("click", click);
      return b;
    }
    var toggle = button("Enlarge", "Open this diagram over the page", function () { mode(!open); });
    var zoomControls = el("span", { class: "zoom-controls", hidden: true },
      button("−", "Zoom out", function () { level = Math.max(0.5, level - 0.25); apply(); }),
      button("+", "Zoom in", function () { level = Math.min(6, level + 0.25); apply(); }),
      button("Fit", "Fit to width", function () { level = 1; apply(); }));
    add(bar, [toggle, zoomControls]);
    document.addEventListener("keydown", function (e) { if (open && e.key === "Escape") mode(false); });
    return wrap;
  }
  function json(name) {
    return fetch("data/" + name + ".json", { cache: "no-cache" }).then(function (response) {
      if (!response.ok) throw new Error("data/" + name + ".json: HTTP " + response.status);
      return response.json();
    });
  }

  function register(name, render) { views[name] = render; }

  function current() {
    var hash = window.location.hash.replace(/^#/, "");
    if (hash.indexOf("component-") === 0) return "architecture";
    return document.getElementById("pane-" + hash) ? hash : "stores";
  }

  function show() {
    var name = current();
    document.querySelectorAll(".pane").forEach(function (pane) {
      pane.hidden = pane.id !== "pane-" + name;
    });
    document.querySelectorAll(".views-link").forEach(function (a) {
      if (a.getAttribute("data-view") === name) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    var done = drawn[name];
    if (!done && views[name]) {
      var content = document.getElementById(name + "-content");
      done = drawn[name] = Promise.resolve().then(function () { return views[name](); }).then(function (node) {
        content.textContent = "";
        add(content, node);
      }).catch(function (error) {
        content.textContent = "";
        add(content, alert("severe", el("p", {}, "This view could not be drawn: " + error.message)));
      });
    }
    Promise.resolve(done).then(function () {
      var target = window.location.hash.length > 1 && document.getElementById(window.location.hash.slice(1));
      if (target && target.tagName === "TR") target.scrollIntoView({ block: "center" });
    });
  }

  function themeSwitch() {
    var button = document.getElementById("theme-switch");
    function label() {
      button.textContent = document.documentElement.getAttribute("data-theme") === "dark" ? "Light mode" : "Dark mode";
    }
    label();
    button.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { window.localStorage.setItem(THEME_KEY, next); } catch (e) { /* a private window keeps no theme */ }
      label();
    });
  }

  window.DevHub = {
    el: el, add: add, link: link, tag: tag, count: count, short: short, panel: panel, alert: alert, stat: stat,
    table: table, zoomable: zoomable, repoFilter: repoFilter, collected: collected, unavailable: unavailable, json: json, register: register
  };

  document.addEventListener("DOMContentLoaded", function () {
    themeSwitch();
    window.addEventListener("hashchange", show);
    show();
  });
})();
