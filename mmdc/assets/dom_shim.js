"use strict";
globalThis.console = {
  log: (...a) => globalThis.__log && globalThis.__log(a.map(String).join(" ")),
  warn: (...a) => globalThis.__log && globalThis.__log("WARN: " + a.map(String).join(" ")),
  error: (...a) => globalThis.__log && globalThis.__log("ERROR: " + a.map(String).join(" ")),
  debug: () => {}, info: () => {},
};
// Minimal fake browser environment for mermaid.js layout-only rendering.
// getBBox / getComputedTextLength call back into Python (via __measureText)
// which uses Cairo for real font metrics.

const SVG_NS = "http://www.w3.org/2000/svg";
const XHTML_NS = "http://www.w3.org/1999/xhtml";

function CSSStyleDecl() {
  const store = {};
  return new Proxy(store, {
    get(t, p) {
      if (p === "cssText") return Object.entries(t).map(([k,v])=>`${k}:${v}`).join(";");
      if (p === "setProperty") return (k,v) => { t[k]=v; };
      if (p === "removeProperty") return (k) => { delete t[k]; };
      return t[p] || "";
    },
    set(t, p, v) { t[p] = v; return true; }
  });
}

class ClassList {
  constructor(el) { this.el = el; }
  _set() { return new Set((this.el.getAttribute("class")||"").split(/\s+/).filter(Boolean)); }
  _save(s) { this.el.setAttribute("class", Array.from(s).join(" ")); }
  add(...names) { const s=this._set(); names.forEach(n=>s.add(n)); this._save(s); }
  remove(...names) { const s=this._set(); names.forEach(n=>s.delete(n)); this._save(s); }
  contains(n) { return this._set().has(n); }
  toggle(n) { const s=this._set(); s.has(n)?s.delete(n):s.add(n); this._save(s); return s.has(n); }
}

class Node {
  constructor() {
    this.childNodes = [];
    this.parentNode = null;
  }
  appendChild(c) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    this.childNodes.push(c);
    return c;
  }
  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    const i = ref ? this.childNodes.indexOf(ref) : -1;
    if (i === -1) this.childNodes.push(c); else this.childNodes.splice(i, 0, c);
    return c;
  }
  removeChild(c) {
    const i = this.childNodes.indexOf(c);
    if (i !== -1) this.childNodes.splice(i, 1);
    c.parentNode = null;
    return c;
  }
  get ownerDocument() { return globalThis.__document; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length-1] || null; }
  get nextSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return this.parentNode.childNodes[i+1] || null;
  }
  cloneNode(deep) {
    const c = Object.create(Object.getPrototypeOf(this));
    Object.assign(c, this, { childNodes: [], parentNode: null, _attrs: {...(this._attrs||{})} });
    if (deep) for (const ch of this.childNodes) c.appendChild(ch.cloneNode(true));
    return c;
  }
}

class TextNode extends Node {
  constructor(text) { super(); this.nodeType = 3; this.textContent = text; }
}

class Element extends Node {
  constructor(tagName, ns) {
    super();
    this.nodeType = 1;
    this.tagName = tagName;
    this.namespaceURI = ns || XHTML_NS;
    this._attrs = {};
    this.style = CSSStyleDecl();
    this._listeners = {};
  }
  get classList() { return new ClassList(this); }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs,k) ? this._attrs[k] : null; }
  hasAttribute(k) { return k in this._attrs; }
  removeAttribute(k) { delete this._attrs[k]; }
  getAttributeNS(ns, local) { return this.getAttribute(local); }
  setAttributeNS(ns, local, v) { this.setAttribute(local, v); }
  removeAttributeNS(ns, local) { this.removeAttribute(local); }
  hasAttributeNS(ns, local) { return this.hasAttribute(local); }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t]||[]).push(fn); }
  removeEventListener(t, fn) {
    if (this._listeners[t]) this._listeners[t] = this._listeners[t].filter(f=>f!==fn);
  }
  querySelector(sel) { return __querySelector(this, sel); }
  querySelectorAll(sel) { return __querySelectorAll(this, sel); }
  get textContent() {
    return this.childNodes.map(c => c.nodeType===3 ? c.textContent : c.textContent).join("");
  }
  set textContent(v) {
    this.childNodes = [];
    if (v) this.appendChild(new TextNode(v));
  }
  get innerHTML() { return __serialize(this, true); }
  set innerHTML(html) { this.childNodes = []; __parseInto(this, html); }
  get outerHTML() { return __serialize(this, false); }
  // ---- SVG geometry: the important part ----
  getBBox() { return __computeBBox(this); }
  getComputedTextLength() {
    if (this.tagName !== "text" && this.tagName !== "tspan") return 0;
    const font = __resolveFont(this);
    return globalThis.__measureText(this.textContent, font.size, font.family, font.weight, font.style);
  }
  getScreenCTM() { return { a:1,b:0,c:0,d:1,e:0,f:0, inverse(){return this;}, multiply(){return this;} }; }
  createSVGMatrix() { return this.getScreenCTM(); }
}

// --- bbox computation --------------------------------------------------
function __resolveFont(el) {
  // Walk up for inherited font properties (very small cascade: inline style + attrs)
  let size = 16, family = "sans-serif", weight = "normal", style = "normal";
  let n = el;
  while (n && n.nodeType === 1) {
    const s = n.style;
    if (s && s.cssText) {
      const fs = /font-size:\s*([0-9.]+)px/.exec(s.cssText); if (fs) size = parseFloat(fs[1]);
      const ff = /font-family:\s*([^;]+)/.exec(s.cssText); if (ff) family = ff[1].trim();
      const fw = /font-weight:\s*([^;]+)/.exec(s.cssText); if (fw) weight = fw[1].trim();
    }
    if (n.hasAttribute && n.hasAttribute("font-size")) size = parseFloat(n.getAttribute("font-size"));
    if (n.hasAttribute && n.hasAttribute("font-family")) family = n.getAttribute("font-family");
    n = n.parentNode;
  }
  return { size, family, weight, style };
}

function __computeBBox(el) {
  if (el.tagName === "text" || el.tagName === "tspan") {
    const font = __resolveFont(el);
    const m = globalThis.__measureTextFull(el.textContent, font.size, font.family, font.weight, font.style);
    const x = parseFloat(el.getAttribute("x")) || 0;
    const y = parseFloat(el.getAttribute("y")) || 0;
    return { x, y: y - m.ascent, width: m.width, height: m.ascent + m.descent };
  }
  if (el.tagName === "rect") {
    return { x: parseFloat(el.getAttribute("x"))||0, y: parseFloat(el.getAttribute("y"))||0,
             width: parseFloat(el.getAttribute("width"))||0, height: parseFloat(el.getAttribute("height"))||0 };
  }
  if (el.tagName === "circle") {
    const cx=parseFloat(el.getAttribute("cx"))||0, cy=parseFloat(el.getAttribute("cy"))||0, r=parseFloat(el.getAttribute("r"))||0;
    return { x: cx-r, y: cy-r, width: 2*r, height: 2*r };
  }
  if (el.tagName === "line") {
    const x1=parseFloat(el.getAttribute("x1"))||0, x2=parseFloat(el.getAttribute("x2"))||0;
    const y1=parseFloat(el.getAttribute("y1"))||0, y2=parseFloat(el.getAttribute("y2"))||0;
    return { x: Math.min(x1,x2), y: Math.min(y1,y2), width: Math.abs(x2-x1), height: Math.abs(y2-y1) };
  }
  if (el.tagName === "path") {
    return globalThis.__pathBBox(el.getAttribute("d") || "");
  }
  // group / unknown: union of children
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity, any=false;
  for (const c of el.childNodes) {
    if (c.nodeType !== 1) continue;
    const b = c.getBBox ? c.getBBox() : null;
    if (!b || (b.width===0 && b.height===0 && b.x===0 && b.y===0)) continue;
    any = true;
    minX = Math.min(minX, b.x); minY = Math.min(minY, b.y);
    maxX = Math.max(maxX, b.x+b.width); maxY = Math.max(maxY, b.y+b.height);
  }
  if (!any) return { x:0,y:0,width:0,height:0 };
  return { x:minX, y:minY, width:maxX-minX, height:maxY-minY };
}

// --- selector engine (tiny, tag/#id/.class/attr/descendant only) -------
function __matches(el, sel) {
  sel = sel.trim();
  for (const part of sel.split(",")) {
    if (__matchesSimple(el, part.trim())) return true;
  }
  return false;
}
function __matchesSimple(el, sel) {
  const chain = sel.split(/\s+/);
  let cur = el, i = chain.length - 1;
  if (!__matchesCompound(cur, chain[i])) return false;
  i--;
  while (i >= 0) {
    cur = cur.parentNode;
    while (cur && cur.nodeType === 1 && !__matchesCompound(cur, chain[i])) cur = cur.parentNode;
    if (!cur || cur.nodeType !== 1) return false;
    i--;
  }
  return true;
}
function __matchesCompound(el, part) {
  const re = /(#[\w-]+|\.[\w-]+|\[[^\]]+\]|[\w-]+|\*)/g;
  let m;
  while ((m = re.exec(part))) {
    const t = m[0];
    if (t === "*") continue;
    if (t[0] === "#") { if (el.getAttribute("id") !== t.slice(1)) return false; }
    else if (t[0] === ".") { if (!el.classList.contains(t.slice(1))) return false; }
    else if (t[0] === "[") {
      const am = /\[([\w-]+)(?:([~^$*|]?=)"?([^"\]]*)"?)?\]/.exec(t);
      if (am) {
        const val = el.getAttribute(am[1]);
        if (am[2] === undefined) { if (val === null) return false; }
        else if (val !== am[3]) return false;
      }
    } else { if (el.tagName !== t) return false; }
  }
  return true;
}
function __walk(root, cb) {
  for (const c of root.childNodes) { if (c.nodeType===1) { cb(c); __walk(c, cb); } }
}
function __querySelector(root, sel) {
  let found = null;
  __walk(root, (el) => { if (!found && __matches(el, sel)) found = el; });
  return found;
}
function __querySelectorAll(root, sel) {
  const out = [];
  __walk(root, (el) => { if (__matches(el, sel)) out.push(el); });
  out.item = (i) => out[i];
  return out;
}

// --- serialize / parse (very small, enough for mermaid's own output) ---
function __esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
function __serialize(el, innerOnly) {
  function ser(n) {
    if (n.nodeType === 3) return __esc(n.textContent);
    const attrs = Object.entries(n._attrs||{}).map(([k,v])=>` ${k}="${__esc(v)}"`).join("");
    const styleText = n.style && n.style.cssText;
    const styleAttr = styleText ? ` style="${__esc(styleText)}"` : "";
    const inner = n.childNodes.map(ser).join("");
    return `<${n.tagName}${attrs}${styleAttr}>${inner}</${n.tagName}>`;
  }
  if (innerOnly) return el.childNodes.map(ser).join("");
  return ser(el);
}
function __parseInto(parent, html) {
  const doc = globalThis.__document;
  const s = String(html == null ? "" : html);
  const tagRe = /<!--[\s\S]*?-->|<\/([a-zA-Z][\w:-]*)\s*>|<([a-zA-Z][\w:-]*)((?:\s+[\w:-]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>/g;
  const VOID = new Set(["br","hr","img","input","meta","link","area","base","col","embed","param","source","track","wbr"]);
  let stack = [parent];
  let last = 0;
  let m;
  function pushText(text) {
    if (!text) return;
    const t = text.replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,"&");
    if (t.length) stack[stack.length-1].appendChild(doc.createTextNode(t));
  }
  while ((m = tagRe.exec(s))) {
    pushText(s.slice(last, m.index));
    last = tagRe.lastIndex;
    if (m[0].startsWith("<!--")) continue;
    if (m[1]) { // closing tag
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tagName === m[1]) { stack = stack.slice(0, i); break; }
      }
      continue;
    }
    const tag = m[2], attrStr = m[3] || "", selfClose = m[4] === "/";
    const el = doc.createElement(tag);
    const attrRe = /([\w:-]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|[^\s>]+))?/g;
    let am;
    while ((am = attrRe.exec(attrStr))) {
      const name = am[1];
      const val = am[3] !== undefined ? am[3] : (am[4] !== undefined ? am[4] : (am[2] || ""));
      el.setAttribute(name, val.replace(/&quot;/g,'"').replace(/&amp;/g,"&"));
    }
    stack[stack.length-1].appendChild(el);
    if (!selfClose && !VOID.has(tag)) stack.push(el);
  }
  pushText(s.slice(last));
}

// --- document / window --------------------------------------------------
class Document extends Node {
  constructor() { super(); this.nodeType = 9; this.documentElement = null; this.head=null; this.body=null; }
  createElement(tag) { return new Element(tag, XHTML_NS); }
  createElementNS(ns, tag) { return new Element(tag, ns); }
  createTextNode(t) { return new TextNode(t); }
  getElementById(id) { return __querySelector(this, "#"+id); }
  querySelector(sel) { return __querySelector(this, sel); }
  querySelectorAll(sel) { return __querySelectorAll(this, sel); }
  createDocumentFragment() { const f = new Element("#fragment"); return f; }
}

const document_ = new Document();
document_.documentElement = document_.appendChild(new Element("html"));
document_.head = document_.documentElement.appendChild(new Element("head"));
document_.body = document_.documentElement.appendChild(new Element("body"));
globalThis.document = document_;
globalThis.__document = document_;

globalThis.window = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.dispatchEvent = () => true;
globalThis.navigator = { userAgent: "mmdc-quickjs" };
globalThis.getComputedStyle = (el) => el.style;
globalThis.requestAnimationFrame = (fn) => { fn(0); return 0; };
globalThis.cancelAnimationFrame = () => {};
globalThis.setTimeout = (fn, t) => { fn(); return 0; };
globalThis.clearTimeout = () => {};
globalThis.setInterval = () => 0;
globalThis.clearInterval = () => {};
class ResizeObserverStub { observe(){} unobserve(){} disconnect(){} }
globalThis.ResizeObserver = ResizeObserverStub;
class MutationObserverStub { observe(){} disconnect(){} takeRecords(){return [];} }
globalThis.MutationObserver = MutationObserverStub;
globalThis.performance = { now: () => Date.now() };
globalThis.matchMedia = () => ({ matches:false, addListener(){}, removeListener(){} });
globalThis.SVGElement = Element;
globalThis.Element = Element;
globalThis.Node = Node;

// console.log("dom shim loaded ok");

globalThis.__resetDocument = function() {
  document_.body.childNodes = [];
  document_.head.childNodes = [];
};
