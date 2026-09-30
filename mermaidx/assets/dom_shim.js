"use strict";
globalThis.console = {
  log: (...a) => globalThis.__log && globalThis.__log(a.map(String).join(" ")),
  warn: (...a) => globalThis.__log && globalThis.__log("WARN: " + a.map(String).join(" ")),
  error: (...a) => globalThis.__log && globalThis.__log("ERROR: " + a.map(String).join(" ")),
  debug: () => {}, info: () => {},
};

// Legacy RegExp static match properties ($1-$9, $&, $_, $`, $') -- a very old,
// non-standard (but still widely relied upon) feature that real browser JS
// engines keep for backward compatibility. QuickJS-ng does not implement it,
// but mermaid bundles a roughjs-derived SVG path-data parser that reads
// RegExp.$1 after every match() call (e.g. for the "stadium" node shape, and
// state-diagram start/end circles) -- without this, that parser silently
// gets `undefined` and crashes with "cannot read property 'length' of
// undefined". Patching RegExp.prototype.exec covers match()/test() too,
// since both route through it per spec.
(function () {
  const origExec = RegExp.prototype.exec;
  RegExp.prototype.exec = function (str) {
    const result = origExec.call(this, str);
    if (result) {
      for (let i = 1; i <= 9; i++) {
        RegExp["$" + i] = result[i] !== undefined ? result[i] : "";
      }
      RegExp["$&"] = result[0];
      RegExp.$_ = str;
      RegExp["$`"] = str.slice(0, result.index);
      RegExp["$'"] = str.slice(result.index + result[0].length);
    }
    return result;
  };
})();

// Minimal CSSStyleSheet -- mermaid >=11.13ish builds its base CSS via the
// real CSSOM constructor (`new CSSStyleSheet()` + insertRule/replaceSync)
// instead of plain string concatenation. Only the two methods mermaid
// actually calls, plus the `.cssRules` / `.cssText` shape its own
// `cssStyleSheetToString()` reads back out, are implemented here.
class CSSStyleSheet {
  constructor() { this.cssRules = []; }
  insertRule(ruleText, index) {
    const i = index === undefined ? this.cssRules.length : index;
    this.cssRules.splice(i, 0, { cssText: ruleText });
    return i;
  }
  replaceSync(text) { this.cssRules = [{ cssText: text }]; }
}
globalThis.CSSStyleSheet = CSSStyleSheet;

// Minimal crypto.getRandomValues polyfill -- QuickJS has no Web Crypto API
// at all, but mermaid bundles the `uuid` library (used for mindmap node IDs,
// among other things) which requires it to exist. Mermaid only needs these
// IDs to be unique within one render, not cryptographically secure, so
// Math.random() is a perfectly fine source here.
// Minimal TextEncoder/TextDecoder -- QuickJS has neither. mermaid 11.15's
// preprocessing (toBase64, used for diagram frontmatter handling) and a
// transitively-bundled dependency both call `new TextEncoder()`/
// `new TextDecoder()` directly, so a ReferenceError here aborts every
// render, not just the "info" diagram that happened to surface it first.
class TextEncoder {
  encode(str) {
    str = str ?? "";
    const bytes = [];
    for (let i = 0; i < str.length; i++) {
      let code = str.codePointAt(i);
      if (code > 0xffff) i++; // consumed a surrogate pair
      if (code < 0x80) bytes.push(code);
      else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
      else if (code < 0x10000) bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
      else bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
    }
    return new Uint8Array(bytes);
  }
}
class TextDecoder {
  constructor(encoding) { this.encoding = (encoding || "utf-8").toLowerCase(); }
  decode(input) {
    if (!input) return "";
    const arr = input instanceof Uint8Array ? input : new Uint8Array(input);
    if (this.encoding === "ascii" || this.encoding === "latin1") {
      let s = "";
      for (let i = 0; i < arr.length; i++) s += String.fromCharCode(arr[i]);
      return s;
    }
    let s = "", i = 0;
    while (i < arr.length) {
      const b0 = arr[i++];
      if (b0 < 0x80) { s += String.fromCharCode(b0); continue; }
      let n, cp;
      if ((b0 & 0xe0) === 0xc0) { n = 1; cp = b0 & 0x1f; }
      else if ((b0 & 0xf0) === 0xe0) { n = 2; cp = b0 & 0x0f; }
      else if ((b0 & 0xf8) === 0xf0) { n = 3; cp = b0 & 0x07; }
      else { s += "\ufffd"; continue; }
      for (let k = 0; k < n; k++) cp = (cp << 6) | (arr[i++] & 0x3f);
      s += String.fromCodePoint(cp);
    }
    return s;
  }
}
globalThis.TextEncoder = TextEncoder;
globalThis.TextDecoder = TextDecoder;

const __B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
globalThis.btoa = function (str) {
  str = String(str);
  let out = "";
  for (let i = 0; i < str.length; i += 3) {
    const c0 = str.charCodeAt(i) & 0xff;
    const has1 = i + 1 < str.length, has2 = i + 2 < str.length;
    const c1 = has1 ? str.charCodeAt(i + 1) & 0xff : 0;
    const c2 = has2 ? str.charCodeAt(i + 2) & 0xff : 0;
    out += __B64[c0 >> 2];
    out += __B64[((c0 & 3) << 4) | (c1 >> 4)];
    out += has1 ? __B64[((c1 & 15) << 2) | (c2 >> 6)] : "=";
    out += has2 ? __B64[c2 & 63] : "=";
  }
  return out;
};
globalThis.atob = function (str) {
  str = String(str).replace(/=+$/, "");
  let out = "";
  let bits = 0, value = 0;
  for (let i = 0; i < str.length; i++) {
    value = (value << 6) | __B64.indexOf(str[i]);
    bits += 6;
    if (bits >= 8) { bits -= 8; out += String.fromCharCode((value >> bits) & 0xff); }
  }
  return out;
};

globalThis.crypto = {
  getRandomValues(typedArray) {
    const max = Math.pow(2, 8 * typedArray.BYTES_PER_ELEMENT);
    for (let i = 0; i < typedArray.length; i++) {
      typedArray[i] = Math.floor(Math.random() * max);
    }
    return typedArray;
  },
};

// Minimal structuredClone polyfill -- QuickJS has no built-in Structured
// Clone algorithm, but mermaid's pie chart (cloning its default config) and
// C4 diagram (deep-copying point arrays while laying out arrows) both call
// it directly. Every call site here only needs a deep copy of plain data
// (objects/arrays/Maps/Sets/Dates/RegExps), never the transferable-object or
// cross-realm parts of the real algorithm, so a straightforward recursive
// clone with cycle tracking (via a Map, same as the spec) is enough.
globalThis.structuredClone = function structuredClone(value, _seen) {
  const seen = _seen || new Map();
  if (value === null || typeof value !== "object") return value;
  if (seen.has(value)) return seen.get(value);
  if (value instanceof Date) return new Date(value.getTime());
  if (value instanceof RegExp) return new RegExp(value.source, value.flags);
  if (Array.isArray(value)) {
    const out = [];
    seen.set(value, out);
    for (const item of value) out.push(structuredClone(item, seen));
    return out;
  }
  if (value instanceof Map) {
    const out = new Map();
    seen.set(value, out);
    for (const [k, v] of value) out.set(structuredClone(k, seen), structuredClone(v, seen));
    return out;
  }
  if (value instanceof Set) {
    const out = new Set();
    seen.set(value, out);
    for (const item of value) out.add(structuredClone(item, seen));
    return out;
  }
  const out = {};
  seen.set(value, out);
  for (const key of Object.keys(value)) out[key] = structuredClone(value[key], seen);
  return out;
};

// mermaid's internal debug logging (Z.debug(...)) builds template-literal
// strings that call JSON.stringify() on internal layout state (e.g. block
// diagram node/size objects) purely to print it -- the string is built
// eagerly regardless of whether debug logging is even enabled. Some of that
// internal state legitimately contains circular references (e.g. a size
// object reachable from more than one place through a cycle in the layout
// graph), which QuickJS-ng's native JSON.stringify rejects with "TypeError:
// circular reference". Since this stringification is debug-only output,
// never data that ends up in the rendered SVG, swap in a safe replacer
// instead of throwing whenever the native call rejects a cycle.
(function () {
  const nativeStringify = JSON.stringify;
  JSON.stringify = function (value, replacer, space) {
    try {
      return nativeStringify(value, replacer, space);
    } catch (e) {
      if (!(e instanceof TypeError)) throw e;
      const seen = new WeakSet();
      const safeReplacer = function (key, val) {
        if (val !== null && typeof val === "object") {
          if (seen.has(val)) return "[Circular]";
          seen.add(val);
        }
        return typeof replacer === "function" ? replacer.call(this, key, val) : val;
      };
      return nativeStringify(value, safeReplacer, space);
    }
  };
})();

globalThis.Intl = {};

// Minimal URL polyfill -- QuickJS has no built-in URL. mermaid's click-handler
// code path (sanitizing `click nodeId "https://..."` href targets, via the
// bundled sanitize-url helper) calls `URL.canParse(str)` and `new URL(str)`,
// then lower-cases `.protocol`/`.hostname` and reads `.toString()` back. Every
// call site only ever passes an absolute http(s) URL (other schemes like
// mailto:/javascript:/custom:// are handled before reaching `new URL`), so a
// regex-based parser covering scheme/userinfo/host/port/path/query/hash --
// not the full WHATWG URL spec -- is enough.
const _URL_RE = /^([a-zA-Z][a-zA-Z\d+\-.]*:)(\/\/(?:([^/?#@]*)@)?([^/?#:]*)(?::(\d*))?)?([^?#]*)(\?[^#]*)?(#.*)?$/;
class URL {
  constructor(url, base) {
    const src = base !== undefined ? new URL(base).toString().replace(/[^/]*$/, "") + String(url) : String(url);
    const m = _URL_RE.exec(src);
    if (!m) throw new TypeError(`Invalid URL: ${src}`);
    this.protocol = m[1] || "";
    this.username = "";
    this.password = "";
    if (m[3]) {
      const [u, p] = m[3].split(":");
      this.username = u || "";
      this.password = p || "";
    }
    this.hostname = m[4] || "";
    this.port = m[5] || "";
    this.pathname = m[6] || "";
    this.search = m[7] || "";
    this.hash = m[8] || "";
  }
  get host() { return this.port ? `${this.hostname}:${this.port}` : this.hostname; }
  get origin() { return this.hostname ? `${this.protocol}//${this.host}` : this.protocol; }
  get href() { return this.toString(); }
  set href(v) { Object.assign(this, new URL(v)); }
  toString() {
    let auth = "";
    if (this.username) auth = this.username + (this.password ? `:${this.password}` : "") + "@";
    const authority = this.hostname ? `//${auth}${this.host}` : "";
    return `${this.protocol}${authority}${this.pathname}${this.search}${this.hash}`;
  }
  toJSON() { return this.toString(); }
  static canParse(url, base) {
    try { new URL(url, base); return true; } catch { return false; }
  }
}
globalThis.URL = URL;

// Minimal CSS.supports("color", value) polyfill. QuickJS has no `CSS`
// global at all. mermaid's sequenceDiagram box-color parsing (`box Purple
// Alice & John`) tries `window?.CSS.supports("color", name)` first to
// check whether the leading word is a real CSS color, and only falls back
// to a `new Option().style.color = ...` trick (which needs a live
// rendering engine to validate) when `window.CSS` is absent -- so
// providing `CSS.supports` lets mermaid take its normal modern-browser
// path instead of hitting that unimplementable fallback.
const _CSS_NAMED_COLORS = new Set([
  "transparent", "currentcolor", "inherit", "initial", "unset", "revert",
  "aliceblue","antiquewhite","aqua","aquamarine","azure","beige","bisque","black",
  "blanchedalmond","blue","blueviolet","brown","burlywood","cadetblue","chartreuse",
  "chocolate","coral","cornflowerblue","cornsilk","crimson","cyan","darkblue","darkcyan",
  "darkgoldenrod","darkgray","darkgreen","darkgrey","darkkhaki","darkmagenta",
  "darkolivegreen","darkorange","darkorchid","darkred","darksalmon","darkseagreen",
  "darkslateblue","darkslategray","darkslategrey","darkturquoise","darkviolet","deeppink",
  "deepskyblue","dimgray","dimgrey","dodgerblue","firebrick","floralwhite","forestgreen",
  "fuchsia","gainsboro","ghostwhite","gold","goldenrod","gray","green","greenyellow","grey",
  "honeydew","hotpink","indianred","indigo","ivory","khaki","lavender","lavenderblush",
  "lawngreen","lemonchiffon","lightblue","lightcoral","lightcyan","lightgoldenrodyellow",
  "lightgray","lightgreen","lightgrey","lightpink","lightsalmon","lightseagreen",
  "lightskyblue","lightslategray","lightslategrey","lightsteelblue","lightyellow","lime",
  "limegreen","linen","magenta","maroon","mediumaquamarine","mediumblue","mediumorchid",
  "mediumpurple","mediumseagreen","mediumslateblue","mediumspringgreen","mediumturquoise",
  "mediumvioletred","midnightblue","mintcream","mistyrose","moccasin","navajowhite","navy",
  "oldlace","olive","olivedrab","orange","orangered","orchid","palegoldenrod","palegreen",
  "paleturquoise","palevioletred","papayawhip","peachpuff","peru","pink","plum","powderblue",
  "purple","rebeccapurple","red","rosybrown","royalblue","saddlebrown","salmon","sandybrown",
  "seagreen","seashell","sienna","silver","skyblue","slateblue","slategray","slategrey",
  "snow","springgreen","steelblue","tan","teal","thistle","tomato","turquoise","violet",
  "wheat","white","whitesmoke","yellow","yellowgreen",
]);
const _CSS_COLOR_FN_RE = /^(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(.*\)$/i;
const _CSS_HEX_COLOR_RE = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
globalThis.CSS = {
  supports(prop, value) {
    if (typeof prop !== "string") return false;
    if (value === undefined) return false; // 1-arg "prop: value" form -- not used by mermaid
    if (prop.toLowerCase() !== "color") return false; // only color checks are needed here
    const v = String(value).trim();
    return _CSS_NAMED_COLORS.has(v.toLowerCase()) || _CSS_HEX_COLOR_RE.test(v) || _CSS_COLOR_FN_RE.test(v);
  },
};

// Minimal fake browser environment for mermaid.js layout-only rendering.
// getBBox / getComputedTextLength call back into Python (via __measureText),
// which reads real glyph widths from a bundled font (see font_metrics.py).

const SVG_NS = "http://www.w3.org/2000/svg";
const XHTML_NS = "http://www.w3.org/1999/xhtml";

const _ZERO_PX_PROPS = new Set([
  "padding-left", "padding-right", "padding-top", "padding-bottom",
  "margin-left", "margin-right", "margin-top", "margin-bottom",
  "border-left-width", "border-right-width", "border-top-width", "border-bottom-width",
]);
// Parses a `"key: value; key2: value2"` style-attribute string into a
// plain {key: value} object (hyphenated CSS property names, matching what
// d3's .style(name) getter/setter and getPropertyValue()/setProperty() use
// -- d3 never goes through the camelCase el.style.fontSize form).
function __parseStyleAttr(str) {
  const out = {};
  if (!str) return out;
  for (const part of str.split(";")) {
    const i = part.indexOf(":");
    if (i === -1) continue;
    const k = part.slice(0, i).trim();
    if (k) out[k] = part.slice(i + 1).trim();
  }
  return out;
}
function CSSStyleDecl(el) {
  const store = {};
  // A real browser's el.style reflects the element's `style="..."` attribute
  // live -- properties set via setAttribute("style", "a: 1; b: 2") are just
  // as visible through el.style.getPropertyValue("a") as ones set directly
  // via el.style.setProperty(...). mermaid relies on exactly this: e.g. the
  // treemap renderer sets a full style string via d3's `.attr("style", ...)`
  // (which lands only in the element's _attrs, not this store) and later
  // reads the font-size back via `.style("font-size")` to compute the value
  // label's vertical offset. Without this fallback that read comes back
  // empty, parseFloat("") is NaN, and the value label ends up at y="NaN".
  const fromAttr = (k) => __parseStyleAttr(el && el._attrs && el._attrs.style)[k];
  return new Proxy(store, {
    get(t, p) {
      if (p === "cssText") return Object.entries(t).map(([k,v])=>`${k}:${v}`).join(";");
      if (p === "__entries") return Object.entries(t);
      if (p === "setProperty") return (k,v) => __cssSet(t, k, v);
      if (p === "removeProperty") return (k) => { delete t[k]; };
      if (p === "getPropertyValue") return (k) => {
        if (Object.prototype.hasOwnProperty.call(t, k)) return t[k];
        return fromAttr(k) ?? (_ZERO_PX_PROPS.has(k) ? "0px" : "");
      };
      if (Object.prototype.hasOwnProperty.call(t, p)) return t[p];
      return fromAttr(p) ?? "";
    },
    set(t, p, v) {
      if (p === "cssText") return true;
      __cssSet(t, String(p).replace(/[A-Z]/g, (c) => "-" + c.toLowerCase()), v);
      return true;
    }
  });
}
// A CSSOM property setter accepts exactly ONE declaration value: null/undefined/""
// removes the property, and a value that isn't a valid single value (e.g. it has
// a top-level ";" -- mermaid's own fontFamily config ends in one) is silently
// ignored and leaves the previous value untouched. Chrome does exactly that,
// which is why real mermaid output has no inline font-family on sequence text.
function __cssValueIsSingle(v) {
  let q = null, depth = 0;
  for (const ch of v) {
    if (q) { if (ch === q) q = null; continue; }
    if (ch === '"' || ch === "'") { q = ch; continue; }
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    else if (depth === 0 && (ch === ";" || ch === "{" || ch === "}")) return false;
  }
  return true;
}
function __cssSet(store, k, v) {
  if (v == null || String(v).trim() === "") { delete store[k]; return; }
  v = String(v).trim();
  if (!__cssValueIsSingle(v)) return;
  // `font-size: 14` (mermaid's journey does this on SVG <text>): Chrome accepts a bare
  // number as px for SVG elements and serializes it as "14px".
  if (k === "font-size" && /^-?[\d.]+$/.test(v)) v += "px";
  store[k] = __cssCanonCommas(__cssCanonColors(v));
}
// Chrome serializes an sRGB color that went through the CSSOM as rgb()/rgba():
// "#ECECFF" -> "rgb(236, 236, 255)", "hsl(80, 100%, 56.27%)" -> "rgb(181, 255, 32)".
// Named colors, "none", "currentColor", "url(...)" etc. are left alone.
function __cssCanonColors(v) {
  const hex = /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(v);
  if (hex) {
    let h = hex[1];
    if (h.length <= 4) h = h.split("").map((c) => c + c).join("");
    const n = [0, 2, 4, 6].map((i) => (h.length > i ? parseInt(h.slice(i, i + 2), 16) : null));
    return n[3] === null || n[3] === 255
      ? `rgb(${n[0]}, ${n[1]}, ${n[2]})`
      : `rgba(${n[0]}, ${n[1]}, ${n[2]}, ${+(n[3] / 255).toFixed(3)})`;
  }
  const hsl = /^hsla?\(\s*([-\d.]+)(?:deg)?\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*(?:,\s*([\d.]+)\s*)?\)$/i.exec(v);
  if (hsl) {
    const h = ((parseFloat(hsl[1]) % 360) + 360) % 360, sat = parseFloat(hsl[2]) / 100, l = parseFloat(hsl[3]) / 100;
    const a = sat * Math.min(l, 1 - l);
    const f = (n) => { const k = (n + h / 30) % 12; return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
    const rgb = [f(0), f(8), f(4)].map((x) => Math.round(x * 255));
    return hsl[4] === undefined || parseFloat(hsl[4]) === 1
      ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
      : `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${parseFloat(hsl[4])})`;
  }
  return v;
}
// Chrome serializes comma-separated values with ", " ("1,0" -> "1, 0"),
// except inside quoted strings.
function __cssCanonCommas(v) {
  let out = "", q = null;
  for (let i = 0; i < v.length; i++) {
    const ch = v[i];
    if (q) { out += ch; if (ch === q) q = null; continue; }
    if (ch === '"' || ch === "'") { q = ch; out += ch; continue; }
    if (ch === ",") { out += ", "; while (v[i + 1] === " ") i++; continue; }
    out += ch;
  }
  return out;
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
  // JSON.stringify(node) -- needed because some diagrams (e.g. block) stash
  // a live d3 selection wrapping a DOM node inside a data object that later
  // gets JSON.stringify'd for a debug-log line. In a real browser this is
  // harmless: Node.prototype.parentNode/childNodes are non-enumerable
  // prototype getters, so JSON.stringify(element) just serializes to "{}".
  // Here, parentNode/childNodes are plain own enumerable instance
  // properties (needed so the rest of this shim can read/write them
  // directly), so without this, JSON.stringify would walk the whole
  // parent<->child graph and hit a genuine cycle. toJSON() short-circuits
  // that the same way real DOM serialization does.
  toJSON() { return {}; }
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
  // compareDocumentPosition() -- needed by d3 selection's .order() (used by
  // e.g. the sankey diagram to reorder <g> layers so links draw under/over
  // nodes correctly). Only the PRECEDING(2)/FOLLOWING(4)/CONTAINS(8)/
  // CONTAINED_BY(16)/DISCONNECTED(1) bits are computed -- enough for the
  // sibling-ordering checks d3/mermaid actually perform; the bookkeeping-only
  // IMPLEMENTATION_SPECIFIC(32) bit real browsers also set is omitted.
  compareDocumentPosition(other) {
    if (other === this) return 0;
    if (!other) return 1;
    const pathA = [];
    for (let n = this; n; n = n.parentNode) pathA.unshift(n);
    const pathB = [];
    for (let n = other; n; n = n.parentNode) pathB.unshift(n);
    if (pathA[0] !== pathB[0]) return 1; // disconnected trees
    let i = 0;
    const len = Math.min(pathA.length, pathB.length);
    while (i < len && pathA[i] === pathB[i]) i++;
    if (i === pathA.length) return 20; // other is a descendant of this (16|4)
    if (i === pathB.length) return 10; // other is an ancestor of this (8|2)
    const parent = pathA[i - 1];
    const idxA = parent.childNodes.indexOf(pathA[i]);
    const idxB = parent.childNodes.indexOf(pathB[i]);
    return idxA < idxB ? 4 : 2;
  }
  // ParentNode.append()/prepend(): newer DOM API distinct from
  // appendChild() -- accepts multiple args and plain strings (which get
  // wrapped in a text node). Some diagrams (e.g. venn, via a d3-style
  // text-wrapping helper) call element.append(node) directly instead of
  // appendChild(), which the old-style shim never implemented.
  append(...nodes) {
    for (const n of nodes) this.appendChild(typeof n === "string" ? new TextNode(n) : n);
  }
  prepend(...nodes) {
    for (const n of nodes.reverse()) {
      this.insertBefore(typeof n === "string" ? new TextNode(n) : n, this.firstChild);
    }
  }
  get ownerDocument() { return globalThis.__document; }
  // DOM spec: parentElement is parentNode, but only when that parent is
  // itself an Element (nodeType 1) -- e.g. a node whose parent is the
  // Document has parentNode set but parentElement === null. Mermaid's
  // gantt renderer reads `document.getElementById(id).parentElement
  // .offsetWidth` to size the chart, and the state-diagram renderer walks
  // `.parentElement` while positioning divider lines; without this getter
  // both read `undefined` off the plain Node class and throw
  // "cannot read property '...' of undefined".
  get parentElement() {
    return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null;
  }
  getRootNode() {
    let n = this;
    while (n.parentNode) n = n.parentNode;
    return n;
  }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length-1] || null; }
  get children() { return this.childNodes.filter(c => c.nodeType === 1); }
  get firstElementChild() { return this.children[0] || null; }
  get lastElementChild() { const c = this.children; return c[c.length-1] || null; }
  get childElementCount() { return this.children.length; }
  get nextSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return this.parentNode.childNodes[i+1] || null;
  }
  get previousSibling() {
    if (!this.parentNode) return null;
    const i = this.parentNode.childNodes.indexOf(this);
    return i > 0 ? this.parentNode.childNodes[i-1] : null;
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
    this.style = CSSStyleDecl(this);
    this._listeners = {};
  }
  get classList() { return new ClassList(this); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
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
  matches(sel) { return __matches(this, sel); }
  getElementsByTagName(tag) {
    const out = [];
    __walk(this, (el) => { if (el !== this && (tag === "*" || el.tagName === tag)) out.push(el); });
    return out;
  }
  get clientWidth() { return __resolveElementSizePx(this, "width"); }
  get clientHeight() { return __resolveElementSizePx(this, "height"); }
  get offsetWidth() { return __resolveElementSizePx(this, "width"); }
  get offsetHeight() { return __resolveElementSizePx(this, "height"); }
  getContext(type) {
    if (this.tagName !== "canvas" || type !== "2d") return null;
    if (!this._ctx2d) this._ctx2d = __makeCanvas2dContext(this);
    return this._ctx2d;
  }
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
  getBBox() { return __f32rect(__computeBBox(this)); }
  getBoundingClientRect() { return __f32rect(this.__boundingClientRect()); }
  __boundingClientRect() {
    // HTML content (foreignObject labels): __measureForeignObject mirrors
    // novasvg's own ForeignObjectSimple::render() line-counting/line-height
    // logic exactly (see mermaidx.font_metrics.Font.foreign_object_metrics()
    // and novasvg.measure_foreign_object()'s docstrings), so a box sized
    // from this never disagrees with what novasvg then actually paints
    // into it -- including growing correctly for multi-line content (e.g.
    // a `<br>`-separated label), which a plain textContent-based single-line
    // measurement (this method's own previous implementation) couldn't.
    // Falls back to that simpler path for the innerHTML-serialization
    // failing (nodeType!==1) or -- a pure SVG <text>/<tspan> node, where
    // "innerHTML" has no meaning and getComputedTextLength() is the right
    // call instead, not this one.
    const fontSize = __resolveHtmlFontSizePx(this);
    if (this.nodeType === 1 && this.tagName !== "text" && this.tagName !== "tspan") {
      // outerHTML, not innerHTML: mermaid measures the wrapping <div> itself,
      // and that div's own style="line-height:1.5" is what novasvg's
      // foreignObjectLineHeight() has to see -- innerHTML drops it and the
      // height silently falls back to font.height()*1.2 (22.35 vs the 24 a
      // browser gives).
      const html = __serialize(this, false);
      const m = globalThis.__measureForeignObject(html, fontSize, "DejaVu Sans",
        __resolveHtmlFontWeight(this), __resolveHtmlFontStyle(this));
      // A browser gives a block with no text (and no <br>) zero height and
      // zero width -- e.g. mermaid's empty edge labels. novasvg paints
      // nothing for it either (ForeignObjectSimple::render() returns early),
      // so 0x0 is also what paint agrees with.
      const hasContent = /\S/.test(html.replace(/<[^>]*>/g, "")) || /<br\b/i.test(html);
      if (!hasContent) return { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 };
      // Browsers lay out in 1/64px LayoutUnits and round a shrink-to-fit
      // width UP to the next one.
      let w = Math.ceil(m.width * 64) / 64;
      // CSS box width: an explicit px `width` IS the box's width (mermaid's wrap mode
      // is `display:table; white-space:break-spaces; width:200px` and a browser
      // reports exactly 200 for it, not the widest line); and a natural width is
      // clamped to `max-width`. That clamp is what mermaid keys off: it sets
      // max-width:<wrappingWidth> on the label, and only when the measured width
      // comes back EQUAL to it does it switch the label into wrap mode.
      const px = (v) => { const mm = v && /^([\d.]+)px$/.exec(v); return mm ? parseFloat(mm[1]) : null; };
      const declW = px(__inlineStyleProp(this, "width")), maxW = px(__inlineStyleProp(this, "max-width"));
      if (declW !== null) w = declW;
      if (maxW !== null && w > maxW) w = maxW;
      return { x: 0, y: 0, width: w, height: m.height, top: 0, left: 0, right: w, bottom: m.height };
    }
    const m = globalThis.__measureTextFull(this.textContent, fontSize, "DejaVu Sans", "normal", "normal");
    // layout-unit rounding: a text box's width rounds UP to the next 1/64px
    const width = Math.ceil(m.width * 64) / 64, height = m.ascent + m.descent + 4; // +line-box slack
    return { x: 0, y: 0, width, height, top: 0, left: 0, right: width, bottom: height };
  }
  getComputedTextLength() {
    if (this.tagName !== "text" && this.tagName !== "tspan") return 0;
    const font = __resolveFont(this);
    return globalThis.__measureText(__svgTextForMeasure(this), font.size, font.family, font.weight, font.style);
  }
  getScreenCTM() { return { a:1,b:0,c:0,d:1,e:0,f:0, inverse(){return this;}, multiply(){return this;} }; }
  createSVGMatrix() { return this.getScreenCTM(); }
}

// --- bbox computation --------------------------------------------------
// DejaVu Sans x-height / em (1120 / 2048) -- what a browser's `ex` unit resolves to
// for the only font this shim measures with.
const __X_HEIGHT = 1120 / 2048;

// A CSS <length> to px. Relative units resolve against `parentPx` (the parent's font
// size, which is what em/ex/% mean *inside a font-size declaration*); a bare number
// is px, as it is for SVG presentation attributes.
function __lenToPx(v, parentPx) {
  const m = /^\s*(-?[\d.]+)\s*(px|em|ex|rem|%|pt)?\s*$/i.exec(String(v));
  if (!m) return null;
  const n = parseFloat(m[1]);
  switch ((m[2] || "px").toLowerCase()) {
    case "px": return n;
    case "em": return n * parentPx;
    case "ex": return n * parentPx * __X_HEIGHT;
    case "rem": return n * 16;
    case "%": return (n * parentPx) / 100;
    case "pt": return (n * 4) / 3;
  }
  return null;
}

function __resolveFont(el) {
  // Walk up for inherited font properties. Nearer (more specific) values
  // must win over farther ancestors' -- e.g. the diagram title only carries
  // class="flowchartTitleText" (font-size: 18px via CSS), while some
  // ancestor group carries a generic inline font-size for the rest of the
  // diagram; since we walk from the element up to the root, the FIRST
  // match found for each property is the closest and must not be
  // overwritten by a later (farther) one. Within a single node, inline
  // style/attribute still outrank that node's own CSS class rule.
  let size, sizeNode, family, weight, style = "normal";
  let n = el;
  while (n && n.nodeType === 1) {
    let nSize, nFamily, nWeight;

    const cssSize = __resolveCssProp(n, "font-size");
    if (cssSize) nSize = cssSize.trim();
    const cssFamily = __resolveCssProp(n, "font-family");
    if (cssFamily) nFamily = cssFamily.trim();
    const cssWeight = __resolveCssProp(n, "font-weight");
    if (cssWeight) nWeight = cssWeight.trim();

    const s = n.style;
    if (s && s.cssText) {
      const fs = /font-size:\s*([^;]+)/.exec(s.cssText); if (fs) nSize = fs[1].trim();
      const ff = /font-family:\s*([^;]+)/.exec(s.cssText); if (ff) nFamily = ff[1].trim();
      const fw = /font-weight:\s*([^;]+)/.exec(s.cssText); if (fw) nWeight = fw[1].trim();
    }
    if (n.hasAttribute && n.hasAttribute("font-size")) nSize = n.getAttribute("font-size");
    if (n.hasAttribute && n.hasAttribute("font-family")) nFamily = n.getAttribute("font-family");

    if (size === undefined && nSize !== undefined && __lenToPx(nSize, 16) !== null) { size = nSize; sizeNode = n; }
    if (family === undefined && nFamily !== undefined) family = nFamily;
    if (weight === undefined && nWeight !== undefined) weight = nWeight;
    n = n.parentNode;
  }
  if (size === undefined) size = 16;
  else {
    // em/ex/% are relative to the PARENT's resolved font size.
    const p = sizeNode.parentNode;
    const parentPx = p && p.nodeType === 1 ? __resolveFont(p).size : 16;
    size = __lenToPx(size, parentPx);
  }
  if (family === undefined) family = "sans-serif";
  if (weight === undefined) weight = "normal";
  return { size, family, weight, style };
}

let __cssRulesCache = null;
let __cssRulesCacheText = null;

// Best-effort parse of the single <style> block mermaid writes into the
// document: split on top-level `selector { decl; decl; ... }` blocks.
// @keyframes bodies produce a few harmless bogus "rules" (selectors like
// "from"/"to" that never match a real SVG element) since this doesn't
// track nesting, which is fine for our purposes -- this only needs to
// answer "what does the stylesheet say for this element", not fully
// parse CSS.
function __getCssRules() {
  const doc = globalThis.__document;
  const styleEl = doc && doc.querySelector ? doc.querySelector("style") : null;
  const text = styleEl ? styleEl.textContent : "";
  // The shim's Document is created once and reused for the engine's whole
  // lifetime (only rebuilt per render), so caching by document identity
  // would silently keep serving a previous render's rules forever -- key
  // on the actual stylesheet text, which does change each render.
  if (__cssRulesCacheText === text && __cssRulesCache) return __cssRulesCache;
  const rules = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let m;
  while ((m = re.exec(text || ""))) {
    const selectors = m[1].trim();
    if (!selectors || selectors[0] === "@") continue;
    const decls = {};
    for (const part of m[2].split(";")) {
      const idx = part.indexOf(":");
      if (idx === -1) continue;
      const prop = part.slice(0, idx).trim();
      const val = part.slice(idx + 1).trim();
      if (prop) decls[prop] = val;
    }
    rules.push({ selectors, decls });
  }
  __cssRulesCache = rules;
  __cssRulesCacheText = text;
  return rules;
}

// Last matching rule wins -- an approximation of the cascade (source
// order, no specificity weighing) that's good enough for mermaid's own
// generated stylesheet, which doesn't lean on specificity tricks.
function __resolveCssProp(el, prop) {
  let value = null;
  for (const rule of __getCssRules()) {
    if (prop in rule.decls && __matches(el, rule.selectors)) value = rule.decls[prop];
  }
  return value;
}

function __resolveElementSizePx(el, dim) {
  const styleProp = dim === "width" ? "width" : "height";
  const s = el.style;
  if (s && s.cssText) {
    const m = new RegExp(styleProp + ":\\s*([\\d.]+)px").exec(s.cssText);
    if (m) return parseFloat(m[1]);
  }
  // <canvas>/<img> etc. use the width/height IDL attribute directly,
  // not CSS -- and a mindmap has no real container to measure, so this
  // is the fallback cytoscape's layout bounding box ends up using.
  if (el[dim] !== undefined && el[dim] !== null) return el[dim];
  return 1000;
}

// Inline declaration of `prop` on el: the live CSSOM store (el.style.x = ...) wins over a
// raw setAttribute("style", ...) string, exactly as a later write would in a browser.
function __inlineStyleProp(el, prop) {
  const re = new RegExp("(?:^|;)\\s*" + prop + ":\\s*([^;]+)");
  const live = el.style && el.style.cssText;
  let m = live && re.exec(live);
  if (m) return m[1].trim();
  const attr = el._attrs && el._attrs.style;
  m = attr && re.exec(attr);
  return m ? m[1].trim() : null;
}
function __resolveHtmlFontSizePx(el) {
  // font-size inherits, so the NEAREST ancestor that declares one wins; on a
  // single node inline style outranks the stylesheet. The stylesheet matters:
  // e.g. mermaid's ER theme sets `.edgeLabel .label{font-size:14px}` on the
  // <g> that wraps the label's foreignObject, and a browser lays the text out
  // at 14px, not the 16px default.
  let n = el;
  while (n && n.nodeType === 1) {
    const inl = __inlineStyleProp(n, "font-size");
    if (inl) {
      const m = /^([\d.]+)px$/.exec(inl);
      if (m) return parseFloat(m[1]);
    }
    const css = __resolveCssProp(n, "font-size");
    if (css) {
      const m = /^\s*([\d.]+)px\s*$/.exec(css);
      if (m) return parseFloat(m[1]);
    }
    n = n.parentNode;
  }
  return 16;
}

// Nearest-ancestor lookup of an inherited font property for HTML (foreignObject)
// content: inline style first, then the stylesheet, per node, walking up.
function __resolveHtmlFontProp(el, prop) {
  let n = el;
  while (n && n.nodeType === 1) {
    const inl = __inlineStyleProp(n, prop);
    if (inl) return inl;
    const css = __resolveCssProp(n, prop);
    if (css) return css.replace(/!important/i, "").trim();
    n = n.parentNode;
  }
  return null;
}
function __resolveHtmlFontWeight(el) {
  const v = __resolveHtmlFontProp(el, "font-weight");
  if (!v) return "normal";
  if (v === "bold" || v === "bolder") return "bold";
  const num = parseInt(v, 10);
  return !Number.isNaN(num) && num >= 600 ? "bold" : "normal";
}
function __resolveHtmlFontStyle(el) {
  const v = __resolveHtmlFontProp(el, "font-style");
  return v === "italic" || v === "oblique" ? "italic" : "normal";
}

function __makeCanvas2dContext(canvasEl) {
  const noop = () => {};
  const ctx = {
    canvas: canvasEl,
    // Paint state -- plain read/write properties, nothing reads them back.
    fillStyle: "#000", strokeStyle: "#000", lineWidth: 1, lineCap: "butt",
    lineJoin: "miter", miterLimit: 10, globalAlpha: 1, globalCompositeOperation: "source-over",
    font: "10px sans-serif", textAlign: "start", textBaseline: "alphabetic",
    shadowColor: "rgba(0,0,0,0)", shadowBlur: 0, shadowOffsetX: 0, shadowOffsetY: 0,
    lineDashOffset: 0, imageSmoothingEnabled: true,
    // Path/paint methods: pixels are never read back for mindmap (the
    // final SVG comes from cytoscape's computed node positions), so
    // these only need to not throw.
    save: noop, restore: noop, beginPath: noop, closePath: noop,
    moveTo: noop, lineTo: noop, arc: noop, arcTo: noop, ellipse: noop,
    rect: noop, quadraticCurveTo: noop, bezierCurveTo: noop,
    fill: noop, stroke: noop, clip: noop,
    fillRect: noop, strokeRect: noop, clearRect: noop,
    translate: noop, rotate: noop, scale: noop, transform: noop,
    setTransform: noop, resetTransform: noop,
    setLineDash: noop, getLineDash: () => [],
    drawImage: noop, createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
    createPattern: () => null,
    fillText: noop, strokeText: noop,
    getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(Math.max(0, w) * Math.max(0, h) * 4), width: w, height: h }),
    putImageData: noop, createImageData: (w, h) => ({ data: new Uint8ClampedArray(Math.max(0, w) * Math.max(0, h) * 4), width: w, height: h }),
    // The one method whose real answer actually matters: cytoscape sizes
    // and positions labels/nodes using this during layout.
    measureText(str) {
      const fpx = (() => {
        const m = /(\d+(?:\.\d+)?)px/.exec(ctx.font || "");
        return m ? parseFloat(m[1]) : 10;
      })();
      const w = globalThis.__measureText(String(str), fpx, "DejaVu Sans", "normal", "normal");
      return { width: w, actualBoundingBoxLeft: 0, actualBoundingBoxRight: w,
                actualBoundingBoxAscent: fpx * 0.8, actualBoundingBoxDescent: fpx * 0.2 };
    },
  };
  return ctx;
}

function __resolveTextAnchor(el) {
  let n = el;
  while (n && n.nodeType === 1) {
    const s = n.style;
    if (s && s.cssText) {
      const ta = /text-anchor:\s*([a-z]+)/.exec(s.cssText);
      if (ta) return ta[1];
    }
    n = n.parentNode;
  }
  // External stylesheet rules (e.g. mermaid's own
  // "#gd1 .node .label text{text-anchor:middle}") outrank a plain
  // text-anchor="..." presentation attribute in real CSS, so they're
  // checked before falling back to that attribute below.
  const css = __resolveCssProp(el, "text-anchor");
  if (css) return css.trim();
  n = el;
  while (n && n.nodeType === 1) {
    if (n.hasAttribute && n.hasAttribute("text-anchor")) return n.getAttribute("text-anchor");
    n = n.parentNode;
  }
  return "start";
}

// Parses an SVG <length>, honoring a trailing "em" (relative to the given
// font-size) since mermaid's own tspans position themselves with e.g.
// y="-0.1em" dy="1.1em" rather than plain user-unit numbers.
function __parseLen(str, fontSize) {
  if (str === null || str === undefined) return null;
  const m = /^\s*(-?[\d.]+(?:[eE][-+]?\d+)?)\s*(em)?\s*$/.exec(str);
  if (!m) return null;
  const v = parseFloat(m[1]);
  return m[2] === "em" ? v * fontSize : v;
}

// Accumulates the effective x/y across a chain of ancestor->descendant
// nodes, honoring x/y (absolute) and dx/dy (relative, "em"-aware via
// __parseLen) at each step -- the same rule real SVG rendering uses when
// resolving a tspan's painted position from its own attributes plus
// whatever it inherited on the way down from its ancestors.
function __accumulatePos(chain, fontSize) {
  let x = 0, y = 0;
  for (const n of chain) {
    const xAttr = n.getAttribute && n.getAttribute("x");
    const yAttr = n.getAttribute && n.getAttribute("y");
    const dxAttr = n.getAttribute && n.getAttribute("dx");
    const dyAttr = n.getAttribute && n.getAttribute("dy");
    if (xAttr !== null) { const v = __parseLen(xAttr, fontSize); if (v !== null) x = v; }
    if (yAttr !== null) { const v = __parseLen(yAttr, fontSize); if (v !== null) y = v; }
    if (dxAttr !== null) { const v = __parseLen(dxAttr, fontSize); if (v !== null) x += v; }
    if (dyAttr !== null) { const v = __parseLen(dyAttr, fontSize); if (v !== null) y += v; }
  }
  return { x, y };
}

// The chain of nodes from `root` down to `target` (inclusive of both),
// found by walking target's parentNode pointers back up to root. Used to
// resolve a specific descendant's position (e.g. a particular line's row
// tspan) rather than whatever single-child chain __resolveTextPos would
// otherwise follow.
function __chainTo(root, target) {
  const chain = [];
  let n = target;
  while (n) { chain.unshift(n); if (n === root) break; n = n.parentNode; }
  return chain;
}

// Finds the effective x/y that will actually be used to paint this text
// element. mermaid always writes its "real" position (y="-0.1em"
// dy="1.1em", x="0") on the single positioning tspan wrapping the actual
// runs, and puts a vestigial, unrelated y (plain user units, no dy) on the
// outer <text> that gets overridden the moment that tspan is reached.
// Reading the outer element's own y/x directly (as if it were the one SVG
// actually uses) silently disagreed with the real paint position by
// exactly that difference -- which is what put backgrounds and text out of
// alignment. This walks down through single-child chains to find the
// element that really carries the position, honoring dy accumulation.
function __resolveTextPos(el, fontSize) {
  let n = el;
  const chain = [n];
  while (true) {
    const kids = n.childNodes ? n.childNodes.filter(c => c.nodeType === 1) : [];
    if (kids.length !== 1) break;
    n = kids[0];
    chain.push(n);
  }
  return __accumulatePos(chain, fontSize);
}

// Collect the per-line tspans of a multi-line label. mermaid wraps each visual
// line in a `<tspan class="text-outer-tspan row" ...>` (the words within are
// `text-inner-tspan`), one such row per line and positioned with dy="1.1em".
// A single-line label has exactly one row, so callers treat >1 rows as multi-line.
function __rowTspans(el) {
  const rows = [];
  const walk = (n) => {
    for (const c of (n.childNodes || [])) {
      if (c.nodeType !== 1) continue;
      const cls = (c.getAttribute && c.getAttribute("class")) || "";
      if (/(^|\s)(row|text-outer-tspan)(\s|$)/.test(cls)) rows.push(c);
      else walk(c);
    }
  };
  walk(el);
  return rows;
}

const __BBOX_SKIP = new Set(["defs","marker","style","script","title","desc","metadata","clipPath","mask","symbol","pattern","linearGradient","radialGradient","filter"]);
// SVG <text> default white-space handling (xml:space="default"): newlines/tabs become
// spaces, runs of spaces collapse to one, and leading/trailing space is dropped -- a
// browser measures "Design      " as "Design". Left alone under xml:space="preserve"
// or a `white-space: pre*` style.
function __svgTextForMeasure(el) {
  const raw = el.textContent;
  for (let n = el; n && n.nodeType === 1; n = n.parentNode) {
    if (n.getAttribute && n.getAttribute("xml:space") === "preserve") return raw;
    const ws = __inlineStyleProp(n, "white-space");
    if (ws && /^(pre|pre-wrap|break-spaces)$/.test(ws)) return raw;
  }
  return raw.replace(/[\t\n\r ]+/g, " ").replace(/^ | $/g, "");
}

// Browsers hand these boxes back as single-precision floats. Layout code
// (dagre) then does its double-precision math on those, so feeding it the
// f32-rounded values -- not our exact doubles -- is what makes downstream
// coordinates agree with a browser's to the last digit.
function __f32rect(r) {
  const o = {};
  for (const k in r) o[k] = typeof r[k] === "number" ? Math.fround(r[k]) : r[k];
  return o;
}

function __computeBBox(el) {
  if (el.tagName === "text" || el.tagName === "tspan") {
    const font = __resolveFont(el);
    const m = globalThis.__measureTextFull(__svgTextForMeasure(el), font.size, font.family, font.weight, font.style);
    const pos = __resolveTextPos(el, font.size);
    const anchor = __resolveTextAnchor(el);
    // Chrome sizes a text's box from font metrics rounded to whole pixels
    // (ascent 14.85 -> 15, descent 3.78 -> 4: a 19px line, not 18.625).
    const asc = Math.round(m.ascent), desc = Math.round(m.descent);

    // Multi-line: measuring the whole textContent as one line (below) under-reports the
    // height, so mermaid sizes the node for a single line and lines 2+ overflow the box.
    // Width = the widest line; height = one line box + (n-1) line steps (dy="1.1em").
    const rows = __rowTspans(el);
    if (rows.length > 1) {
      let maxW = 0;
      for (const r of rows) {
        const rm = globalThis.__measureTextFull(
          r.textContent, font.size, font.family, font.weight, font.style);
        if (rm.width > maxW) maxW = rm.width;
      }
      const height = asc + desc + (rows.length - 1) * 1.1 * font.size;
      // The outer <text>'s own y is a vestigial placeholder (see
      // __resolveTextPos above) that only gets overridden once a *single*
      // positioning tspan is reached -- but a multi-line label has one row
      // tspan PER LINE, so that single-child-chain walk stops at <text>
      // itself and would silently use the wrong, non-"em" y here. Resolve
      // position via the first row's own y="...em" dy="1.1em" instead.
      const pos = __accumulatePos(__chainTo(el, rows[0]), font.size);
      let lx = pos.x;
      if (anchor === "middle") lx -= maxW / 2;
      else if (anchor === "end") lx -= maxW;
      const top = pos.y - asc;
      return { x: lx, y: top, width: maxW, height, top, left: lx, right: lx + maxW, bottom: top + height };
    }

    let x = pos.x;
    if (anchor === "middle") x -= m.width / 2;
    else if (anchor === "end") x -= m.width;
    return { x, y: pos.y - asc, width: m.width, height: asc + desc };
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
  if (el.tagName === "polygon" || el.tagName === "polyline") {
    const raw = el.getAttribute("points") || "";
    const nums = raw.trim().split(/[\s,]+/).filter(s => s.length).map(Number);
    const xs = [], ys = [];
    for (let k = 0; k + 1 < nums.length; k += 2) { xs.push(nums[k]); ys.push(nums[k+1]); }
    if (!xs.length) return { x: 0, y: 0, width: 0, height: 0 };
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  }
  if (el.tagName === "ellipse") {
    const cx=parseFloat(el.getAttribute("cx"))||0, cy=parseFloat(el.getAttribute("cy"))||0;
    const rx=parseFloat(el.getAttribute("rx"))||0, ry=parseFloat(el.getAttribute("ry"))||0;
    return { x: cx-rx, y: cy-ry, width: 2*rx, height: 2*ry };
  }
  if (el.tagName === "foreignObject") {
    // Its own width/height attributes (set from getBoundingClientRect()
    // above, itself backed by novasvg.measure_foreign_object() -- see
    // that function's docstring) ARE its bbox; falling through to the
    // generic "union of children" case below instead would try to call
    // .getBBox() on its HTML children (<div>, <span>, <p>...), which
    // don't have one -- silently reporting an empty/zero bbox and, for
    // any diagram/label wide enough for that to matter, under-sizing the
    // *overall* diagram bbox mermaid computes the final SVG viewBox
    // from, clipping that content at the canvas edge despite the
    // foreignObject's own box being sized and positioned correctly.
    return { x: 0, y: 0,
             width: parseFloat(el.getAttribute("width")) || 0,
             height: parseFloat(el.getAttribute("height")) || 0 };
  }
  // group / unknown: union of children, each mapped through its own
  // transform first. getBBox() is defined to return a bbox in the
  // element's OWN local coordinate space (i.e. excluding its own
  // transform) -- so when unioning children into the parent's space we
  // must apply each child's transform ourselves. mermaid positions
  // essentially every node/edge group via `transform="translate(x,y)"`,
  // so skipping this made every computed bbox (including the one used
  // for the final SVG viewBox) far too small, clipping the diagram.
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity, any=false;
  for (const c of el.childNodes) {
    if (c.nodeType !== 1) continue;
    if (__BBOX_SKIP.has(c.tagName)) continue;
    const b = c.getBBox ? c.getBBox() : null;
    if (!b || (b.width===0 && b.height===0 && b.x===0 && b.y===0)) continue;
    const [dx, dy] = __translateOf(c);
    any = true;
    minX = Math.min(minX, b.x+dx); minY = Math.min(minY, b.y+dy);
    maxX = Math.max(maxX, b.x+b.width+dx); maxY = Math.max(maxY, b.y+b.height+dy);
  }
  if (!any) return { x:0,y:0,width:0,height:0 };
  return { x:minX, y:minY, width:maxX-minX, height:maxY-minY };
}

// Extracts the (dx, dy) translation from an element's `transform` attribute.
// Only translate(...) is handled -- the only form mermaid actually emits
// for node/edge positioning -- other transform functions (rotate, scale,
// matrix) are ignored (treated as 0,0) rather than attempted, since a wrong
// partial transform is worse than a clearly-incomplete one.
function __translateOf(el) {
  const t = el.getAttribute && el.getAttribute("transform");
  if (!t) return [0, 0];
  const m = /translate\(\s*(-?[\d.]+)(?:[,\s]+(-?[\d.]+))?\s*\)/.exec(t);
  if (!m) return [0, 0];
  return [parseFloat(m[1]) || 0, m[2] !== undefined ? (parseFloat(m[2]) || 0) : 0];
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
  // :not(...) wraps its own compound selector (itself possibly a
  // pseudo-class, as in mermaid's own "g:not(:first-child)") that the
  // flat tokenizer below can't parse through parens -- pull each
  // :not(...) clause out and evaluate it recursively first, then
  // tokenize whatever's left as an ordinary compound selector.
  const notRe = /:not\(([^()]*)\)/g;
  const notClauses = [];
  let notMatch;
  while ((notMatch = notRe.exec(part))) notClauses.push(notMatch[1]);
  for (const inner of notClauses) {
    if (__matchesCompound(el, inner)) return false;
  }
  const rest = part.replace(notRe, "");
  const re = /(#[\w-]+|\.[\w-]+|\[[^\]]+\]|:[\w-]+|[\w-]+|\*)/g;
  let m;
  while ((m = re.exec(rest))) {
    const t = m[0];
    if (t === "*") continue;
    if (t[0] === "#") { if (el.getAttribute("id") !== t.slice(1)) return false; }
    else if (t[0] === ".") { if (!el.classList.contains(t.slice(1))) return false; }
    else if (t[0] === ":") {
      // Pseudo-classes. Only the ones mermaid/d3 actually rely on (mainly
      // ':first-child', used by `.insert(tag, ':first-child')` to place a
      // shape's background behind an already-created label) are handled;
      // an unrecognized pseudo-class fails the match rather than silently
      // matching everything, matching real querySelector semantics.
      const siblings = el.parentNode
        ? el.parentNode.childNodes.filter((c) => c.nodeType === 1)
        : [];
      if (t === ":first-child") { if (siblings[0] !== el) return false; }
      else if (t === ":last-child") { if (siblings[siblings.length - 1] !== el) return false; }
      else { return false; }
    }
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
// Attribute values additionally escape \n \r \t (as XMLSerializer does): a raw newline in an
// attribute is turned into a space by any XML parser, silently changing the value
// (e.g. mermaid's multi-line path data).
function __escAttr(s) { return __esc(s).replace(/\n/g,"&#10;").replace(/\r/g,"&#13;").replace(/\t/g,"&#9;"); }

// mermaid.js's non-HTML-labels tspan builder (the `Mse` helper in the
// bundle, at the time of writing) only decodes &amp;/&lt;/&gt; when it
// builds label text -- everything else, including &nbsp; (commonly used
// to force visible width in an otherwise-empty label, e.g. block-arrow
// shapes), passes through as literal text instead of becoming the
// character it names. In mermaid's HTML-labels path (its default, what a
// real browser / mmdc-cli uses) this never comes up, since label markup
// goes through actual HTML parsing there, which decodes any named
// entity; this DOM shim's own tspan text builder doesn't do that HTML
// entity decoding, so any diagram/config that still reaches it (see
// mermaidx.engines.quickjs_engine/v8_engine's base_config -- journey/
// timeline section headers and score labels always do, htmlLabels:false
// opt-ins do for everything) needs it done here instead. Decode the
// common ones here, on raw text content before __esc() runs -- scoped to entities outside
// the 5 XML-reserved ones (&amp; &lt; &gt; &quot; &apos;), since
// decoding those would hand __esc() a bare "&" or "<" and produce
// invalid XML; they're real XML/SVG markup escapes, not just HTML
// entities mermaid forgot.
const _EXTRA_TEXT_ENTITIES = {
  nbsp: "\u00A0", copy: "\u00A9", reg: "\u00AE", trade: "\u2122",
  mdash: "\u2014", ndash: "\u2013", hellip: "\u2026",
};
function __decodeStrayLabelEntities(s) {
  return String(s).replace(/&([a-zA-Z]+);/g, (m0, name) =>
    name in _EXTRA_TEXT_ENTITIES ? _EXTRA_TEXT_ENTITIES[name] : m0);
}
const __SER_VOID = new Set(["br","hr","img","input","meta","link","area","base","col","embed","param","source","track","wbr"]);
function __serialize(el, innerOnly) {
  function ser(n) {
    if (n.nodeType === 3) return __esc(__decodeStrayLabelEntities(n.textContent));
    const attrEntries = Object.entries(n._attrs||{}).filter(([k]) => k !== "style");
    const attrs = attrEntries.map(([k,v])=>` ${k}="${__escAttr(v)}"`).join("");
    // A "style" set via setAttribute("style", ...) and properties set via
    // the live el.style.foo = ... API both need to end up in the SAME
    // style="..." attribute -- emitting two separate style= attributes
    // (one from _attrs, one from n.style.cssText) is invalid SVG/XML and
    // novasvg (and any strict XML parser) rejects it outright ("attribute 'style' ... already defined").
    const attrStyle = n._attrs && n._attrs.style;
    const live = (n.style && n.style.__entries) || [];
    let styleAttr = "";
    if (live.length === 0) {
      // Only setAttribute("style", ...) touched it: a browser keeps that string
      // verbatim -- including an explicitly empty style="".
      if (attrStyle !== undefined) styleAttr = ` style="${__escAttr(attrStyle)}"`;
    } else {
      // Live CSSOM writes re-serialize the WHOLE attribute canonically
      // ("k: v; k2: v2;"), attribute-declared properties first, a repeated
      // property keeping its original position.
      const merged = new Map(Object.entries(__parseStyleAttr(attrStyle)));
      for (const [k, v] of live) merged.set(k, v);
      styleAttr = ` style="${__escAttr(Array.from(merged, ([k, v]) => `${k}: ${v};`).join(" "))}"`;
    }
    const inner = n.childNodes.map(ser).join("");
    if (!inner && __SER_VOID.has(n.tagName)) return `<${n.tagName}${attrs}${styleAttr}/>`;
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
  // mermaid's own label entity-decoding (Rje/"entityDecode") works by
  // setting innerHTML on a scratch element and reading textContent back --
  // the same trick a real browser's parser performs, which decodes any
  // named or numeric HTML entity, not just the 5 XML ones. A named entity
  // mermaidx doesn't know here (e.g. &nbsp; -- reported as issue: it's a
  // real, meaningful non-breaking space character in a label, not visible
  // text that should read literally "&nbsp;") passes through unchanged and
  // ends up serialized back out as literal "&nbsp;" text in the SVG.
  const NAMED_ENTITIES = {
    nbsp: "\u00A0", copy: "\u00A9", reg: "\u00AE", trade: "\u2122",
    mdash: "\u2014", ndash: "\u2013", hellip: "\u2026",
    larr: "\u2190", uarr: "\u2191", rarr: "\u2192", darr: "\u2193",
    deg: "\u00B0", plusmn: "\u00B1", times: "\u00D7", divide: "\u00F7",
    sect: "\u00A7", para: "\u00B6", middot: "\u00B7",
    laquo: "\u00AB", raquo: "\u00BB",
    euro: "\u20AC", pound: "\u00A3", yen: "\u00A5", cent: "\u00A2",
  };
  function pushText(text) {
    if (!text) return;
    const t = text
      .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
      .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
      .replace(/&([a-zA-Z]+);/g, (m0, name) =>
        name in NAMED_ENTITIES ? NAMED_ENTITIES[name] :
        name === "lt" ? "<" : name === "gt" ? ">" :
        name === "quot" ? '"' : name === "apos" ? "'" :
        name === "amp" ? "&" : m0);
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
  constructor() { super(); this.nodeType = 9; this.documentElement = null; this.head=null; this.body=null; this._listeners = {}; }
  createElement(tag) { return new Element(tag, XHTML_NS); }
  createElementNS(ns, tag) { return new Element(tag, ns); }
  createTextNode(t) { return new TextNode(t); }
  getElementById(id) { return __querySelector(this, "#"+id); }
  querySelector(sel) { return __querySelector(this, sel); }
  querySelectorAll(sel) { return __querySelectorAll(this, sel); }
  createDocumentFragment() { const f = new Element("#fragment"); return f; }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t]||[]).push(fn); }
  removeEventListener(t, fn) {
    if (this._listeners[t]) this._listeners[t] = this._listeners[t].filter(f=>f!==fn);
  }
  dispatchEvent() { return true; }
}

const document_ = new Document();
document_.documentElement = document_.appendChild(new Element("html"));
document_.head = document_.documentElement.appendChild(new Element("head"));
document_.body = document_.documentElement.appendChild(new Element("body"));
globalThis.document = document_;
globalThis.__document = document_;

globalThis.window = globalThis;
document_.defaultView = globalThis;
globalThis.self = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.dispatchEvent = () => true;
globalThis.navigator = { userAgent: "mermaidx-quickjs" };
globalThis.screen = { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040, colorDepth: 24, pixelDepth: 24 };
globalThis.getComputedStyle = (el) => el.style;
globalThis.requestAnimationFrame = (fn) => { Promise.resolve().then(() => fn(0)); return 0; };
globalThis.cancelAnimationFrame = () => {};
globalThis.setTimeout = (fn, t) => { Promise.resolve().then(() => fn()); return 0; };
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