/* The Dev Hub's page (og-dev-hub#15): the tabs, the theme, and what every view shares.
 *
 * Each view is one script that calls DevHub.register(name, render); render(body)
 * draws the view into its section the first time its tab is shown, from
 * data/<name>.json. Every fact is set as text, never as markup; the only markup
 * a view inserts is what the build wrote (Graphviz's SVG, the rendered glossary).
 * Every path is relative, so the page works from any sub-path. */
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

  /* h("a", {href: url, class: "x"}, "text", node, [more]): an element; strings become text nodes. */
  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") el.className = value;
      else el.setAttribute(key, value === true ? "" : String(value));
    });
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, child) {
    if (child === null || child === undefined || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(el, c); }); return; }
    el.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }

  /* A link when there is a URL, the text alone when there is none. */
  function link(text, url) {
    return url ? h("a", { href: url }, text) : document.createTextNode(text);
  }
  function pill(text, kind) {
    return h("span", { class: "pill" + (kind ? " pill-" + kind : "") }, text);
  }
  /* A count, or "unknown": unknown is never 0. */
  function figure(n) {
    return n === null || n === undefined ? "unknown" : Number(n).toLocaleString("en-GB");
  }
  function short(commit) {
    return commit ? String(commit).slice(0, 12) : "";
  }
  function card(title, caption) {
    var el = h("div", { class: "card" });
    if (title) el.appendChild(h("h2", {}, title));
    if (caption) el.appendChild(h("p", { class: "caption" }, caption));
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function notice(kind) {
    var el = h("div", { class: "card notice" + (kind ? " notice-" + kind : "") });
    for (var i = 1; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function tile(value, label) {
    return h("div", { class: "tile" + (value === "unknown" ? " tile-unknown" : "") },
      h("div", { class: "tile-value" }, value), h("div", { class: "tile-label" }, label));
  }
  /* columns: [{label, cell: function (row) -> node|string, num: bool}]; rowId(row) names a row's anchor. */
  function table(columns, rows, rowId) {
    if (!rows.length) return h("p", { class: "empty" }, "None.");
    var head = h("tr", {}, columns.map(function (c) { return h("th", { class: c.num ? "num" : null }, c.label); }));
    var body = h("tbody", {}, rows.map(function (row) {
      return h("tr", { id: rowId ? rowId(row) : null }, columns.map(function (c) {
        return h("td", { class: c.num ? "num" : null }, c.cell(row));
      }));
    }));
    return h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, head), body));
  }
  function collected(data) {
    return h("p", { class: "caption" }, "Collected " + (data.collected_at || "at an unknown time") + ".");
  }
  /* The source could not be read: say which, and why, instead of drawing nothing. */
  function unavailable(data, what) {
    return notice("bad", h("p", {}, h("strong", {}, what + " could not be collected"), ": " + (data.error || "no reason was recorded") + "."));
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
    return document.getElementById("view-" + hash) ? hash : "architecture";
  }

  function show() {
    var name = current();
    document.querySelectorAll(".view").forEach(function (section) {
      section.hidden = section.id !== "view-" + name;
    });
    document.querySelectorAll(".tab").forEach(function (tab) {
      if (tab.getAttribute("data-view") === name) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });
    var done = drawn[name];
    if (!done && views[name]) {
      var body = document.getElementById(name + "-body");
      done = drawn[name] = Promise.resolve().then(function () { return views[name](body); }).then(function (node) {
        body.textContent = "";
        append(body, node);
      }).catch(function (error) {
        body.textContent = "";
        append(body, notice("bad", h("p", {}, "This view could not be drawn: " + error.message)));
      });
    }
    Promise.resolve(done).then(function () {
      var target = window.location.hash.length > 1 && document.getElementById(window.location.hash.slice(1));
      if (target && target.tagName === "TR") target.scrollIntoView({ block: "center" });
    });
  }

  function themeButton() {
    var button = document.getElementById("theme-toggle");
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
    h: h, append: append, link: link, pill: pill, figure: figure, short: short, card: card, notice: notice,
    tile: tile, table: table, collected: collected, unavailable: unavailable, json: json, register: register
  };

  document.addEventListener("DOMContentLoaded", function () {
    themeButton();
    window.addEventListener("hashchange", show);
    show();
  });
})();
