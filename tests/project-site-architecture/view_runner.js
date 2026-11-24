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
  constructor(tag) { super(); this.tagName = tag.toUpperCase(); this.attributes = {}; this.hidden = false; }
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
  querySelectorAll: () => [],
  addEventListener: (event, handler) => { if (event === "DOMContentLoaded") global.ready = handler; },
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

const views = ["architecture", "decisions", "context"];
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
  process.stdout.write(JSON.stringify(drawn));
})();
