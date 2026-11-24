// Run the site's view scripts against a built `_site/` in node, with the little DOM they use (og-dev-hub#15).
//
//   node view_runner.js <_site>
//
// Prints one JSON object: each view's name to the text it drew. A view that throws
// is drawn by app.js as "This view could not be drawn: ...", which the test looks for.
"use strict";
const fs = require("fs");
const path = require("path");

const site = process.argv[2];
const byId = {};
const all = [];
const listeners = {};

class Base {
  constructor() { this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
  get textContent() { return this.children.map((c) => c.textContent).join(" "); }
  set textContent(value) { this.children = value ? [new Text(String(value))] : []; }
}
class Text extends Base {
  constructor(text) { super(); this.text = text; }
  get textContent() { return this.text; }
}
class Element extends Base {
  constructor(tag) { super(); this.tagName = tag.toUpperCase(); this.attributes = {}; this.hidden = false; this.open = false; all.push(this); }
  get classes() { return String(this.attributes.class || "").split(" "); }
  setAttribute(key, value) { this.attributes[key] = value; if (key === "id") byId[value] = this; }
  getAttribute(key) { return this.attributes[key]; }
  removeAttribute(key) { delete this.attributes[key]; }
  set className(value) { this.attributes.class = value; }
  addEventListener() {}
  scrollIntoView() {}
  set innerHTML(markup) { this.children = [new Text("[markup]")]; }
}

global.Node = Base;
global.document = {
  documentElement: new Element("html"),
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => new Text(text),
  getElementById: (id) => byId[id] || null,
  // Only the one selector the Stores script uses: an open tile.
  querySelectorAll: (selector) => selector === "details.tile[open]"
    ? all.filter((e) => e.tagName === "DETAILS" && e.classes.includes("tile") && e.open) : [],
  addEventListener: (event, handler) => {
    if (event === "DOMContentLoaded") global.ready = handler;
    else (listeners[event] = listeners[event] || []).push(handler);
  },
};
global.window = {
  location: { hash: "" },
  localStorage: { getItem: () => null, setItem: () => {} },
  matchMedia: () => ({ matches: false }),
  addEventListener: () => {},
};
global.fetch = async (url) => {
  const file = path.join(site, url);
  return { ok: fs.existsSync(file), status: 404, json: async () => JSON.parse(fs.readFileSync(file, "utf8")) };
};

const views = ["architecture", "decisions", "context", "stores", "benchmarking"];
for (const view of views) {
  byId[`pane-${view}`] = new Element("section");
  byId[`${view}-content`] = new Element("div");
}
byId["theme-switch"] = new Element("button");
for (const script of ["app", ...views]) {
  new Function(fs.readFileSync(path.join(site, "js", `${script}.js`), "utf8"))();
}

(async () => {
  for (const view of views) {
    window.location.hash = `#${view}`;
    global.ready();
  }
  await new Promise((resolve) => setTimeout(resolve, 200));
  const drawn = {};
  for (const view of views) drawn[view] = byId[`${view}-content`].textContent;
  // The Stores tab's structure, which the text alone cannot show: each tile a <details> whose <summary> holds the
  // facts, and what Escape does to an open one.
  const tiles = all.filter((e) => e.tagName === "DETAILS" && e.classes.includes("tile"));
  const summaryOf = (t) => t.children.find((c) => c.tagName === "SUMMARY");
  const tagOf = (t) => (function find(n) { return n.classes && n.classes.includes("tag") ? n : (n.children || []).map(find).find(Boolean); })(summaryOf(t));
  const hasLink = (n) => n.tagName === "A" || (n.children || []).some(hasLink);
  drawn._tiles = tiles.map((t) => {
    const summary = summaryOf(t);
    return {
      id: t.attributes.id, summary: !!summary, summaryText: summary ? summary.textContent : "",
      linkInSummary: summary ? hasLink(summary) : null, linkInBody: hasLink(t) && !(summary && hasLink(summary)),
      tagClass: tagOf(t) ? tagOf(t).attributes.class : null,
    };
  });
  if (tiles.length) {
    tiles[0].open = true; tiles[1].open = true;
    const before = tiles.filter((t) => t.open).length;
    (listeners.keydown || []).forEach((h) => h({ key: "Escape", target: null }));
    drawn._escape = { before, after: tiles.filter((t) => t.open).length };
    tiles[0].open = true;
    (listeners.keydown || []).forEach((h) => h({ key: "a", target: null }));
    drawn._otherKey = tiles[0].open;
  }
  process.stdout.write(JSON.stringify(drawn));
})();
