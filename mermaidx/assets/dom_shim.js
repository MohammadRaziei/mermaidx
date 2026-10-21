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
    this.cssRules.splice(i, 0, { cssText: __cssCanonRule(ruleText) });
    return i;
  }
  replaceSync(text) {
    // one CSSRule per top-level `{...}` block, each serialized the way the CSSOM does
    const rules = []; let depth = 0, cur = "";
    for (const ch of text) {
      cur += ch;
      if (ch === "{") depth++;
      else if (ch === "}" && --depth === 0) { rules.push(cur.trim()); cur = ""; }
    }
    if (cur.trim()) rules.push(cur.trim());
    this.cssRules = rules.map((r) => ({ cssText: __cssCanonRule(r) }));
  }
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
      if (p === "cssText") return Object.entries(t).filter(([, v]) => v !== null).map(([k,v])=>`${k}:${v}`).join(";");
      if (p === "__entries") return Object.entries(t);
      if (p === "setProperty") return (k,v,priority) => __cssSet(t, k, __cssWithPriority(v, priority), fromAttr(k));
      if (p === "removeProperty") return (k) => __cssRemove(t, k, fromAttr(k));
      if (p === "getPropertyValue") return (k) => {
        if (Object.prototype.hasOwnProperty.call(t, k)) return t[k] ?? "";
        return fromAttr(k) ?? (_ZERO_PX_PROPS.has(k) ? "0px" : "");
      };
      if (Object.prototype.hasOwnProperty.call(t, p)) return t[p] ?? "";
      return fromAttr(p) ?? "";
    },
    set(t, p, v) {
      if (p === "cssText") return true;
      const k = String(p).replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
      __cssSet(t, k, v, fromAttr(k));
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
// One declaration value as the CSSOM serializes it (an "!important" flag is split off, canonicalized
// around, and put back). Custom properties (--x) keep their text exactly.
// Chrome writes CSS numbers with at most 6 significant digits: 360.890625px -> 360.891px.
function __cssCanonNumbers(v) {
  return v.replace(/(^|[\s,(:/])(-?(?:\d+\.\d*|\.\d+|\d+))(?=[a-z%]*(?:[\s,);/]|$))/gi,
    (m0, lead, num) => lead + String(parseFloat(Number(num).toPrecision(6))));
}
function __cssCanonValue(k, v) {
  if (k.startsWith("--")) return v;
  let important = "";
  const imp = /\s*!\s*important\s*$/i.exec(v);
  if (imp) { important = " !important"; v = v.slice(0, imp.index); }
  // `font-size: 14` (mermaid's journey does this on SVG <text>): Chrome accepts a bare
  // number as px for SVG elements and serializes it as "14px".
  if (k === "font-size" && /^-?[\d.]+$/.test(v)) v += "px";
  // stroke-dasharray is a list; Chrome writes it comma-separated: "5 5" -> "5, 5".
  if (k === "stroke-dasharray" && /^[\d.\s,%a-z-]+$/i.test(v) && v !== "none") v = v.trim().split(/[\s,]+/).join(",");
  return __cssCanonNumbers(__cssCanonCommas(__cssCanonColors(v))) + important;
}
// Removing a property. One the style="..." attribute declares has to be recorded as removed (null), because
// the attribute is not rewritten until it is read; removing one that was never declared changes nothing.
function __cssRemove(store, k, inAttribute) {
  if (inAttribute !== undefined && inAttribute !== "") store[k] = null;
  else delete store[k];
}
// setProperty(name, value, "important") is the value with its priority flag.
function __cssWithPriority(v, priority) {
  return v != null && String(priority).toLowerCase() === "important" ? String(v).trim() + " !important" : v;
}
// `inAttribute` is what the element's style="..." already declares for this property (raw text), if anything.
// A browser changes nothing when the value written is the one already in effect -- compared parsed, so
// "#ffffff" is "rgb(255, 255, 255)" -- and then leaves the attribute exactly as it was written. Without
// this every write, however redundant, would make __styleValue rewrite the whole attribute.
function __cssSet(store, k, v, inAttribute) {
  if (v == null || String(v).trim() === "") { __cssRemove(store, k, inAttribute); return; }
  v = String(v).trim();
  if (!__cssValueIsSingle(v)) return;
  const canon = __cssCanonValue(k, v);
  const inEffect = Object.prototype.hasOwnProperty.call(store, k) ? (store[k] === null ? undefined : store[k]) : inAttribute;
  if (inEffect !== undefined && __cssCanonValue(k, inEffect) === canon) return;
  store[k] = canon;
}
// `a: b; c: d !important` -> the rule text Chrome's CSSOM gives back (`.x { a: b; c: d !important; }`).
function __cssSplitTop(text, sep) {
  const out = []; let q = null, depth = 0, cur = "";
  for (const ch of text) {
    if (q) { cur += ch; if (ch === q) q = null; continue; }
    if (ch === '"' || ch === "'") { q = ch; cur += ch; continue; }
    if (ch === "(") depth++; else if (ch === ")") depth--;
    if (depth === 0 && ch === sep) { out.push(cur); cur = ""; continue; }
    cur += ch;
  }
  out.push(cur);
  return out;
}
function __cssCanonRule(text) {
  const m = /^\s*([^{}@][^{}]*)\{([^{}]*)\}\s*$/.exec(text);
  if (!m) return text; // at-rules / nested blocks: left exactly as written
  const decls = new Map();
  for (const d of __cssSplitTop(m[2], ";")) {
    const i = d.indexOf(":");
    if (i < 0) continue;
    let name = d.slice(0, i).trim();
    const value = d.slice(i + 1).trim();
    if (!name || value === "" || !__cssValueIsSingle(value)) continue;
    if (!name.startsWith("--")) name = name.toLowerCase();
    const canon = __cssCanonValue(name, value);
    const prev = decls.get(name);
    if (prev && /!important$/.test(prev) && !/!important$/.test(canon)) continue; // important wins
    decls.delete(name); decls.set(name, canon);
  }
  const body = [...decls].map(([k, v]) => `${k}: ${v};`).join(" ");
  return `${m[1].trim()} { ${body}${body ? " " : ""}}`;
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
    for (const it of __liveNodeIterators) it._preRemove(c);
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
    // Blink keeps a property written through el.style as pending state and only turns it into the
    // `style` attribute when the attribute list is read -- cloning is such a read -- so the clone's
    // `style` comes before any attribute set on it afterwards (mermaid's colored marker copies).
    if (this.nodeType === 1) __materializeStyle(this);
    const c = Object.create(Object.getPrototypeOf(this));
    Object.assign(c, this, { childNodes: [], parentNode: null, _attrs: {...(this._attrs||{})}, _attrNs: {...(this._attrNs||{})} });
    if (this.nodeType === 1) c.style = CSSStyleDecl(c);
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
    this._attrNs = {}; // namespace of the attributes set with setAttributeNS, by name
    this.style = CSSStyleDecl(this);
    this._listeners = {};
  }
  get classList() { return new ClassList(this); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
  // `id` reflects the attribute (mermaid clones a marker and re-ids it with `clone.id = ...`).
  get id() { return this.getAttribute("id") || ""; }
  set id(v) { this.setAttribute("id", v); }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs,k) ? this._attrs[k] : null; }
  hasAttribute(k) { return k in this._attrs; }
  removeAttribute(k) { delete this._attrs[k]; delete this._attrNs[k]; }
  getAttributeNS(ns, local) { return this.getAttribute(local); }
  setAttributeNS(ns, name, v) { this.setAttribute(name, v); if (ns) this._attrNs[name] = ns; }
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
    // DOM: null -> "", everything else is stringified (so `0` is the text "0", not nothing -- the
    // packet diagram labels its first bit with a number 0), and "" leaves the element childless.
    const text = v === null ? "" : String(v);
    if (text !== "") this.appendChild(new TextNode(text));
  }
  get innerHTML() { return __serialize(this, true); }
  set innerHTML(html) { this.childNodes = []; __parseInto(this, html, { namespaces: true }); }
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
      const declW = __pxValue(__inlineStyleProp(this, "width")), maxW = __pxValue(__inlineStyleProp(this, "max-width"));
      if (declW !== null) w = declW;
      if (maxW !== null && w > maxW) w = maxW;
      return { x: 0, y: 0, width: w, height: m.height, top: 0, left: 0, right: w, bottom: m.height };
    }
    if (this.nodeType === 1 && (this.tagName === "text" || this.tagName === "tspan")) {
      // An SVG text's client rect is its bounding box (ink rule included), moved into screen space.
      const b = __computeBBox(this);
      return { x: b.x, y: b.y, width: b.width, height: b.height, top: b.y, left: b.x, right: b.x + b.width, bottom: b.y + b.height };
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

// --- lengths ----------------------------------------------------------------------------------
// A <length> -- CSS or an SVG attribute -- is a number and optionally a unit, with nothing around them but space:
// "10 px", "10abc" and "5." are errors. Units are case-insensitive.
const __SVG_NUMBER = String.raw`[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?`;
const __LENGTH_RE = new RegExp(`^\\s*(${__SVG_NUMBER})(px|pt|pc|mm|cm|in|em|ex|rem|%)?\\s*$`, "i");
const __UNIT_PX = { px: 1, pt: 4 / 3, pc: 16, mm: 96 / 25.4, cm: 96 / 2.54, in: 96 };

// A CSS <length> to px. Relative units resolve against `parentPx` (the parent's font
// size, which is what em/ex/% mean *inside a font-size declaration*); a bare number
// is px, as it is for SVG presentation attributes.
function __lenToPx(v, parentPx) {
  const m = __LENGTH_RE.exec(String(v));
  if (!m) return null;
  const n = parseFloat(m[1]), unit = (m[2] || "px").toLowerCase();
  switch (unit) {
    case "em": return n * parentPx;
    case "ex": return n * parentPx * __X_HEIGHT;
    case "rem": return n * 16;
    case "%": return (n * parentPx) / 100;
    default: return n * __UNIT_PX[unit];
  }
}

// The numbers at the start of an SVG number list ("0,0 10,5", "10-5", "1.5.5"), up to the first thing that is
// not one -- which is where a browser stops reading a `points` or `viewBox` too -- as float32s.
function __parseNumberList(str) {
  const re = new RegExp(`[\\s,]*(${__SVG_NUMBER})`, "y");
  const out = [];
  for (let m; (m = re.exec(str)) !== null;) out.push(globalThis.__parseSvgNumber(m[1]));
  return out;
}

// The size percentages of an SVG length resolve against: the viewBox of the nearest <svg> above the element,
// else its width and height. Nothing known (a detached element, a percentage width): 0.
function __viewportOf(el) {
  for (let n = el.parentNode; n && n.nodeType === 1; n = n.parentNode) {
    if (n.tagName !== "svg") continue;
    const vb = __parseNumberList(n.getAttribute("viewBox") || "");
    if (vb.length === 4) return [vb[2], vb[3]];
    const side = (name) => { const m = __LENGTH_RE.exec(n.getAttribute(name) || ""); return m ? __lengthPx(m, n, name) : 0; };
    return [side("width"), side("height")];
  }
  return [0, 0];
}

const __LENGTH_AXIS = { x: "x", cx: "x", x1: "x", x2: "x", dx: "x", width: "x", rx: "x",
                        y: "y", cy: "y", y1: "y", y2: "y", dy: "y", height: "y", ry: "y", r: "diagonal" };

// A matched length (a __LENGTH_RE result) in px, a float32, the way Blink reads an SVGLength: em and ex are
// the element's font size, rem the root's 16px, % is a share of the viewport -- its width for x-like
// attributes, its height for y-like ones, the normalized diagonal for `r`.
function __lengthPx(m, el, name) {
  const n = globalThis.__parseSvgNumber(m[1]), unit = (m[2] || "px").toLowerCase();
  switch (unit) {
    case "em": return Math.fround(n * Math.fround(__resolveFont(el).size));
    case "ex": return Math.fround(n * Math.fround(__resolveFont(el).size) * __X_HEIGHT);
    case "rem": return Math.fround(n * 16);
    case "%": {
      const [w, h] = __viewportOf(el), axis = __LENGTH_AXIS[name];
      const whole = axis === "x" ? w : axis === "y" ? h : Math.sqrt((w * w + h * h) / 2);
      return Math.fround((n * whole) / 100);
    }
    default: return Math.fround(n * Math.fround(__UNIT_PX[unit])); // the factor is a float32 too
  }
}

// An element's length attribute in px, or null when it has none or it is not a valid length.
function __svgLength(el, name) {
  const raw = el.getAttribute(name);
  const m = raw === null ? null : __LENGTH_RE.exec(raw);
  return m ? __lengthPx(m, el, name) : null;
}

// A shape's length attribute for its box: absent or invalid is 0, and so is a negative size.
function __shapeLength(el, name) {
  const v = __svgLength(el, name) ?? 0;
  return v < 0 && (name === "width" || name === "height" || name === "r" || name === "rx" || name === "ry") ? 0 : v;
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

    const inlSize = __inlineStyleProp(n, "font-size"); if (inlSize) nSize = inlSize;
    const inlFamily = __inlineStyleProp(n, "font-family"); if (inlFamily) nFamily = inlFamily;
    const inlWeight = __inlineStyleProp(n, "font-weight"); if (inlWeight) nWeight = inlWeight;
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
  const declared = __pxValue(__inlineStyleProp(el, dim));
  if (declared !== null) return declared;
  // <canvas>/<img> etc. use the width/height IDL attribute directly,
  // not CSS -- and a mindmap has no real container to measure, so this
  // is the fallback cytoscape's layout bounding box ends up using.
  if (el[dim] !== undefined && el[dim] !== null) return el[dim];
  return 1000;
}

// Inline declaration of `prop` on el, or null: the style="..." attribute as written with any CSSOM write
// applied on top (and any removal), exactly as the browser's el.style reflects it. The one reader of an
// element's inline style -- __resolveTextProp and __isDisplayNone go through it too.
function __inlineStyleProp(el, prop) {
  const style = __styleValue(el);
  const v = style === null ? undefined : __parseStyleAttr(style)[prop];
  return v === undefined ? null : v;
}
// "12px" / "12.5px" -> 12 / 12.5. Any other value (%, em, calc(), a negative length, empty, absent) -> null.
function __pxValue(v) {
  const m = v && __LENGTH_RE.exec(v);
  return m && (m[2] || "").toLowerCase() === "px" && parseFloat(m[1]) >= 0 ? parseFloat(m[1]) : null;
}
function __resolveHtmlFontSizePx(el) {
  // font-size inherits, so the NEAREST ancestor that declares one wins; on a
  // single node inline style outranks the stylesheet. The stylesheet matters:
  // e.g. mermaid's ER theme sets `.edgeLabel .label{font-size:14px}` on the
  // <g> that wraps the label's foreignObject, and a browser lays the text out
  // at 14px, not the 16px default.
  let n = el;
  while (n && n.nodeType === 1) {
    const px = __pxValue(__inlineStyleProp(n, "font-size"));
    if (px !== null) return px;
    const cssPx = __pxValue(__resolveCssProp(n, "font-size"));
    if (cssPx !== null) return cssPx;
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

// An inherited text property (text-anchor, dominant-baseline): walking up from the element, the first node that
// declares it wins. A node's own declaration is its style="" value (the attribute as written, plus anything set
// through the CSSOM), else a stylesheet rule that matches it (e.g. mermaid's own
// "#gd1 .node .label text{text-anchor:middle}", which outranks a plain presentation attribute in real CSS), else
// its presentation attribute. Nothing declares it: the initial value.
function __resolveTextProp(el, name, initial) {
  for (let n = el; n && n.nodeType === 1; n = n.parentNode) {
    const inline = __inlineStyleProp(n, name);
    if (inline !== null) return inline;
    const rule = __resolveCssProp(n, name);
    if (rule) return rule.trim();
    if (n.hasAttribute && n.hasAttribute(name)) return n.getAttribute(name);
  }
  return initial;
}

function __resolveTextAnchor(el) {
  return __resolveTextProp(el, "text-anchor", "start");
}

// How far Chrome moves a text's box down for `dominant-baseline` (probed against Chrome 153 for DejaVu Sans:
// 7 sizes, normal and bold). `asc` / `desc` are the box's whole-pixel ascent and descent; `xHeight` is the font's.
// auto, alphabetic, text-top and text-bottom do not move it.
function __baselineShift(el, asc, desc, xHeight) {
  switch (__resolveTextProp(el, "dominant-baseline", "auto")) {
    case "middle": return Math.fround(xHeight / 2);
    case "central": return (asc - desc) / 2;
    case "mathematical": return asc / 2;
    case "text-before-edge": return asc;
    case "text-after-edge": case "ideographic": return -desc;
    case "hanging": return Math.round(0.8 * asc * 64) / 64; // a LayoutUnit: whole 1/64ths
    default: return 0;
  }
}

const __BBOX_SKIP = new Set(["defs","marker","style","script","title","desc","metadata","clipPath","mask","symbol","pattern","linearGradient","radialGradient","filter"]);
// xml:space="preserve" or a `white-space: pre*` style on the element or an ancestor.
function __preservesSpace(el) {
  for (let n = el; n && n.nodeType === 1; n = n.parentNode) {
    if (n.getAttribute && n.getAttribute("xml:space") === "preserve") return true;
    const ws = __inlineStyleProp(n, "white-space");
    if (ws && /^(pre|pre-wrap|break-spaces)$/.test(ws)) return true;
  }
  return false;
}

// SVG <text> default white-space handling (xml:space="default"), applied over the whole text: newlines and
// tabs become spaces, runs of spaces collapse to one -- also across the end of one run and the start of the
// next -- and leading/trailing space is dropped (a browser measures "Design      " as "Design").
// Takes the text's pieces in document order and returns them collapsed.
function __collapseSpace(pieces, preserve) {
  if (preserve) return pieces;
  let afterSpace = true; // nothing before the first character: a leading space has no place to go
  const out = pieces.map((raw) => {
    let t = raw.replace(/[\t\n\r ]+/g, " ");
    if (afterSpace && t[0] === " ") t = t.slice(1);
    if (t !== "") afterSpace = t[t.length - 1] === " ";
    return t;
  });
  for (let i = out.length - 1; i >= 0; i--) {
    if (out[i] === "") continue;
    if (out[i][out[i].length - 1] === " ") out[i] = out[i].slice(0, -1);
    break;
  }
  return out;
}

// The content of a <text>/<tspan> in document order: each piece of character data as {text, el} (el is the
// element it sits in), each element as {at: el} just before its content -- where its x/y/dx/dy apply.
// <title>, <desc> and the like are not text.
function __svgTextItems(root) {
  const items = [{ at: root }];
  const walk = (n) => {
    for (const c of n.childNodes) {
      if (c.nodeType === 3) items.push({ text: c.textContent, el: n });
      else if (c.nodeType === 1 && !__BBOX_SKIP.has(c.tagName)) { items.push({ at: c }); walk(c); }
    }
  };
  walk(root);
  return items;
}

function __svgTextForMeasure(el) {
  const pieces = __svgTextItems(el).filter((i) => i.text !== undefined).map((i) => i.text);
  return __collapseSpace(pieces, __preservesSpace(el)).join("");
}

// Lays out the text of a <text>/<tspan> the way SVG does (SVG 1.1, 10.5): a current text position moves along
// the content; an absolute x or y on an element puts it there AND starts a new text chunk; dx/dy shift it.
// A tspan with x="0" dy="1.2em" is therefore a new line. Returns the chunks as
// {x0, end, runs: [{text, el, font, m, x, y}]}: x0 / end are where the chunk begins and ends along x, and each
// run's x / y is its origin before the chunk's text-anchor is applied. No characters, no chunks.
function __layoutSvgText(root) {
  const items = __svgTextItems(root);
  const texts = items.filter((i) => i.text !== undefined);
  const collapsed = __collapseSpace(texts.map((i) => i.text), __preservesSpace(root));
  texts.forEach((t, i) => { t.text = collapsed[i]; });

  const fonts = new Map();
  const fontOf = (el) => { if (!fonts.has(el)) fonts.set(el, __resolveFont(el)); return fonts.get(el); };
  const measure = (text, font) => globalThis.__measureTextFull(text, font.size, font.family, font.weight, font.style);

  const chunks = [];
  let chunk = null, x = 0, y = 0;
  for (const it of items) {
    if (it.at) {
      const el = it.at;
      const ax = __svgLength(el, "x"), ay = __svgLength(el, "y"), dx = __svgLength(el, "dx"), dy = __svgLength(el, "dy");
      if (ax !== null) { x = ax; chunk = null; }
      if (ay !== null) { y = ay; chunk = null; }
      if (dx !== null) x = Math.fround(x + dx);
      if (dy !== null) y = Math.fround(y + dy);
    } else if (it.text !== "") {
      const font = fontOf(it.el), m = measure(it.text, font);
      if (!chunk) { chunk = { x0: x, end: x, runs: [] }; chunks.push(chunk); }
      chunk.runs.push({ text: it.text, el: it.el, font, m, x, y });
      x += m.width;
      chunk.end = x;
    }
  }
  return chunks;
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

// Chrome's getBBox() on an SVG <text> is not the advance width: each glyph contributes its outline's
// ink box, rounded OUT to whole pixels relative to where that glyph is painted, and the result is
// the union of those boxes with the advance box [0, advance rounded UP to 1/64px (LayoutUnit)]. So
// "PK" at 16px (advance 20.141) is
// 20.648 wide -- K's ink ends at 10.828 -> 11, painted at 9.648 -- and a leading "T" (ink starts at
// -0.047) pushes the left edge to -1. (Verified against Chrome on PK, Toy, Design, Implement, Test.)
// getComputedTextLength() and HTML text still use the plain advance, as in Chrome.
// Returns the box's left edge and right edge relative to the text's start-of-run origin.
// Vertically the same rule applies: the box is the font's (rounded) [-ascent, descent] around the
// baseline, grown by each glyph's ink rounded OUT to whole pixels. That only shows at small sizes,
// where e.g. 10px DejaVu has descent 2.36 -> 2 but a "g" reaches 2.08 below the baseline -> 3.
// Returns edges relative to the run's origin / baseline (y grows downward).
function __inkExtent(text, font, advance, asc, desc) {
  let left = 0, right = Math.ceil(advance * 64) / 64, top = -asc, bottom = desc;
  if (typeof globalThis.__measureGlyphs !== "function") return { left, right, top, bottom };
  for (const [pen, inkL, inkR, inkT, inkB] of globalThis.__measureGlyphs(text, font.size, font.family, font.weight, font.style)) {
    left = Math.min(left, pen + Math.floor(inkL));
    right = Math.max(right, pen + Math.ceil(inkR));
    top = Math.min(top, Math.floor(inkT));
    bottom = Math.max(bottom, Math.ceil(inkB));
  }
  return { left, right, top, bottom };
}

// `display: none` -- from the style attribute / CSSOM (which wins) or the presentation attribute. Such an
// element has no layout object, so it has no box and takes no room in its group's box.
function __isDisplayNone(el) {
  const fromStyle = __inlineStyleProp(el, "display");
  return (fromStyle !== null ? fromStyle : el.getAttribute("display")) === "none";
}

function __computeBBox(el) {
  if (__isDisplayNone(el)) return { x: 0, y: 0, width: 0, height: 0 };
  if (el.tagName === "text" || el.tagName === "tspan") {
    // The box is the union of every run's box. Each chunk is anchored on its own advance; a run's box is
    // the font's (whole-pixel) ascent and descent around its baseline -- moved by the run's own
    // `dominant-baseline` (the nearest declaration, a tspan's included; Chrome probed, see __baselineShift) --
    // grown by the glyphs' ink (__inkExtent).
    const chunks = __layoutSvgText(el);
    if (chunks.length === 0) return { x: 0, y: 0, width: 0, height: 0 }; // no characters: Chrome's empty box
    let lx = Infinity, rx = -Infinity, top = Infinity, bot = -Infinity;
    for (const chunk of chunks) {
      const advance = chunk.end - chunk.x0;
      const anchor = __resolveTextAnchor(chunk.runs[0].el);
      const origin = anchor === "middle" ? -advance / 2 : anchor === "end" ? -advance : 0;
      for (const r of chunk.runs) {
        const asc = Math.round(r.m.ascent), desc = Math.round(r.m.descent);
        const ink = __inkExtent(r.text, r.font, r.m.width, asc, desc);
        const base = r.y + __baselineShift(r.el, asc, desc, r.m.xHeight);
        lx = Math.min(lx, r.x + origin + ink.left);
        rx = Math.max(rx, r.x + origin + ink.right);
        top = Math.min(top, base + ink.top);
        bot = Math.max(bot, base + ink.bottom);
      }
    }
    return { x: lx, y: top, width: rx - lx, height: bot - top };
  }
  const L = (name) => __shapeLength(el, name);
  if (el.tagName === "rect") return { x: L("x"), y: L("y"), width: L("width"), height: L("height") };
  if (el.tagName === "circle") {
    const cx = L("cx"), cy = L("cy"), r = L("r");
    return { x: cx - r, y: cy - r, width: 2 * r, height: 2 * r };
  }
  if (el.tagName === "line") {
    const x1 = L("x1"), x2 = L("x2"), y1 = L("y1"), y2 = L("y2");
    return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) };
  }
  if (el.tagName === "path") {
    return globalThis.__pathBBox(el.getAttribute("d") || "");
  }
  if (el.tagName === "polygon" || el.tagName === "polyline") {
    const nums = __parseNumberList(el.getAttribute("points") || "");
    const xs = [], ys = [];
    for (let k = 0; k + 1 < nums.length; k += 2) { xs.push(nums[k]); ys.push(nums[k + 1]); }
    if (!xs.length) return { x: 0, y: 0, width: 0, height: 0 };
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  }
  if (el.tagName === "ellipse") {
    const cx = L("cx"), cy = L("cy"), rx = L("rx"), ry = L("ry");
    return { x: cx - rx, y: cy - ry, width: 2 * rx, height: 2 * ry };
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
    return { x: 0, y: 0, width: L("width"), height: L("height") };
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
    if (__BBOX_SKIP.has(c.tagName) || __isDisplayNone(c)) continue;
    const b = c.getBBox ? c.getBBox() : null;
    if (!b || (b.width===0 && b.height===0 && b.x===0 && b.y===0)) continue;
    any = true;
    const M = __transformMatrix(c);
    if (M && (M[0] !== 1 || M[1] !== 0 || M[2] !== 0 || M[3] !== 1)) {
      // rotate / scale / skew / matrix: the child's box becomes the bounding box of its 4 mapped corners
      const xs = [], ys = [];
      for (const [px, py] of [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]]) {
        xs.push(Math.fround(M[0] * px + M[2] * py + M[4]));
        ys.push(Math.fround(M[1] * px + M[3] * py + M[5]));
      }
      minX = Math.min(minX, ...xs); maxX = Math.max(maxX, ...xs);
      minY = Math.min(minY, ...ys); maxY = Math.max(maxY, ...ys);
      continue;
    }
    const [dx, dy] = M ? [M[4], M[5]] : [0, 0];
    // Blink unions FloatRects: every coordinate, edge and extent is a single-precision value.
    const cx = Math.fround(b.x + dx), cy = Math.fround(b.y + dy);
    minX = Math.min(minX, cx); minY = Math.min(minY, cy);
    maxX = Math.max(maxX, Math.fround(cx + b.width)); maxY = Math.max(maxY, Math.fround(cy + b.height));
  }
  if (!any) return { x:0,y:0,width:0,height:0 };
  return { x:minX, y:minY, width:Math.fround(maxX-minX), height:Math.fround(maxY-minY) };
}

// The element's whole `transform` list as one matrix [a, b, c, d, e, f] (x' = a*x + c*y + e,
// y' = b*x + d*y + f), composed left to right like the SVG spec says. null = no/identity transform.
function __transformMatrix(el) {
  const t = el.getAttribute && el.getAttribute("transform");
  if (!t) return null;
  const mul = (m, n) => [m[0]*n[0] + m[2]*n[1], m[1]*n[0] + m[3]*n[1],
                         m[0]*n[2] + m[2]*n[3], m[1]*n[2] + m[3]*n[3],
                         m[0]*n[4] + m[2]*n[5] + m[4], m[1]*n[4] + m[3]*n[5] + m[5]];
  const rad = (d) => d * Math.PI / 180;
  let M = [1, 0, 0, 1, 0, 0], any = false;
  const re = /([a-zA-Z]+)\s*\(([^)]*)\)/g;
  let m;
  while ((m = re.exec(t))) {
    const a = m[2].trim().split(/[\s,]+/).filter(Boolean).map(Number);
    let n = null;
    switch (m[1]) {
      case "translate": n = [1, 0, 0, 1, a[0] || 0, a[1] || 0]; break;
      case "scale": n = [a[0], 0, 0, a.length > 1 ? a[1] : a[0], 0, 0]; break;
      case "rotate": {
        const c = Math.cos(rad(a[0])), s = Math.sin(rad(a[0])), cx = a[1] || 0, cy = a[2] || 0;
        n = [c, s, -s, c, cx - c * cx + s * cy, cy - s * cx - c * cy]; break;
      }
      case "skewX": n = [1, 0, Math.tan(rad(a[0])), 1, 0, 0]; break;
      case "skewY": n = [1, Math.tan(rad(a[0])), 0, 1, 0, 0]; break;
      case "matrix": n = a.length === 6 ? a : null; break;
    }
    if (n && n.every(Number.isFinite)) { M = mul(M, n); any = true; }
  }
  return any ? M : null;
}

// --- selector engine (tag/#id/.class/attr/:first-child/:last-child/:not, and the four combinators) ---
// A selector list is split at top-level commas; each complex selector is parsed into compound selectors
// joined by combinators (" " descendant, ">" child, "+" next sibling, "~" later sibling) and matched from
// the right-hand compound back to the left, as a browser does.
function __splitTopLevel(text, isSeparator) {
  const parts = [];
  let depth = 0, start = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "[" || c === "(") depth++;
    else if (c === "]" || c === ")") depth--;
    else if (depth === 0 && isSeparator(c)) { parts.push([text.slice(start, i), c]); start = i + 1; }
  }
  parts.push([text.slice(start), ""]);
  return parts;
}
function __matches(el, sel) {
  for (const [part] of __splitTopLevel(sel.trim(), (c) => c === ",")) {
    if (__matchesSimple(el, part.trim())) return true;
  }
  return false;
}
function __parseComplex(sel) {
  // [{ compound, combinator }]: `combinator` joins this compound to the one on its left.
  const out = [];
  let pending = " ";
  for (const [piece, sep] of __splitTopLevel(sel, (c) => /[\s>+~]/.test(c))) {
    if (piece !== "") { out.push({ compound: piece, combinator: out.length ? pending : "" }); pending = " "; }
    if (sep === ">" || sep === "+" || sep === "~") { pending = sep; }
  }
  return out;
}
function __matchesChain(el, chain, i) {
  if (!__matchesCompound(el, chain[i].compound)) return false;
  if (i === 0) return true;
  const combinator = chain[i].combinator;
  if (combinator === ">") {
    const parent = el.parentNode;
    return !!parent && parent.nodeType === 1 && __matchesChain(parent, chain, i - 1);
  }
  if (combinator === "+" || combinator === "~") {
    const siblings = el.parentNode ? el.parentNode.childNodes.filter((c) => c.nodeType === 1) : [];
    const at = siblings.indexOf(el);
    for (let k = at - 1; k >= 0; k--) {
      if (__matchesChain(siblings[k], chain, i - 1)) return true;
      if (combinator === "+") break;
    }
    return false;
  }
  for (let anc = el.parentNode; anc && anc.nodeType === 1; anc = anc.parentNode) {
    if (__matchesChain(anc, chain, i - 1)) return true;
  }
  return false;
}
function __matchesSimple(el, sel) {
  const chain = __parseComplex(sel);
  return chain.length > 0 && __matchesChain(el, chain, chain.length - 1);
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
    } else { if ((el.tagName || "").toLowerCase() !== t.toLowerCase()) return false; }
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
// Text content escapes only & < > (what a browser's serializer does -- a literal " in text,
// e.g. inside <style>, stays a "); attribute values additionally escape the quote.
function __escText(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function __esc(s) { return __escText(s).replace(/"/g,"&quot;"); }
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
// The value of an element's `style` attribute as a browser would write it, or null if it has none.
// A "style" set via setAttribute("style", ...) and properties set via the live el.style.foo = ... API
// both end up in the SAME attribute: two separate style= attributes are invalid SVG/XML.
function __styleValue(n) {
  const attrStyle = n._attrs && n._attrs.style;
  const live = (n.style && n.style.__entries) || [];
  // Only setAttribute("style", ...) touched it: a browser keeps that string verbatim --
  // including an explicitly empty style="".
  if (live.length === 0) return attrStyle !== undefined ? attrStyle : null;
  // Live CSSOM writes re-serialize the WHOLE attribute canonically ("k: v; k2: v2;"),
  // attribute-declared properties first, a repeated property keeping its original position.
  // The attribute-declared values are parsed (and so canonicalized) in that same pass.
  const merged = new Map();
  for (const [k, v] of Object.entries(__parseStyleAttr(attrStyle)))
    if (v !== "" && __cssValueIsSingle(v)) merged.set(k, __cssCanonValue(k, v));
  for (const [k, v] of live) { if (v === null) merged.delete(k); else merged.set(k, v); }
  return Array.from(merged, ([k, v]) => `${k}: ${v};`).join(" ");
}
// Turn a pending CSSOM style into the real `style` attribute (a new attribute goes last).
function __materializeStyle(n) {
  const style = __styleValue(n);
  if (style !== null) n._attrs.style = style;
}
// An element's attributes in document order. `style` keeps the position setAttribute gave it; a style
// that only exists through the live CSSOM is a new attribute, so it comes last.
const __XLINK_NS = "http://www.w3.org/1999/xlink";
// The prefix a serializer writes for an attribute that has a namespace but no prefix of its own (d3's
// attr("xlink:href", v) calls setAttributeNS(XLINK, "href", v)): the namespace's well-known one.
const __ATTR_PREFIX = { [__XLINK_NS]: "xlink", "http://www.w3.org/XML/1998/namespace": "xml" };
function __attrEntries(n) {
  const entries = Object.entries(n._attrs || {}).map(([k, v]) => {
    const prefix = __ATTR_PREFIX[(n._attrNs || {})[k]];
    return [prefix && !k.includes(":") ? `${prefix}:${k}` : k, v];
  });
  const style = __styleValue(n);
  if (style === null) return entries;
  const at = entries.findIndex(([k]) => k === "style");
  if (at >= 0) entries[at] = ["style", style]; else entries.push(["style", style]);
  return entries;
}
function __attrString(n) {
  return __attrEntries(n).map(([k, v]) => ` ${k}="${__escAttr(v)}"`).join("");
}
function __serialize(el, innerOnly) {
  function ser(n) {
    if (n.nodeType === 3) return __escText(__decodeStrayLabelEntities(n.textContent));
    const attrs = __attrString(n);
    const inner = n.childNodes.map(ser).join("");
    if (!inner && __SER_VOID.has(n.tagName)) return `<${n.tagName}${attrs}/>`;
    return `<${n.tagName}${attrs}>${inner}</${n.tagName}>`;
  }
  if (innerOnly) return el.childNodes.map(ser).join("");
  return ser(el);
}

// XMLSerializer, after the DOM Parsing spec's "XML serialization of a Node": what mermaid-cli calls
// to turn the rendered <svg> into the file it writes. Differs from the HTML serialization used by
// innerHTML/outerHTML in that an empty element in a foreign namespace is self-closing (<path/>), an
// empty HTML void element is <br />, namespaces are declared where they change, and a prefixed
// attribute (xlink:href) gets its xmlns:prefix declaration if none is in scope.
class XMLSerializer {
  serializeToString(root) {
    const ser = (n, inheritedNs, declared) => {
      if (n.nodeType === 3) return __escText(n.textContent);
      const ns = n.namespaceURI || null;
      let markup = "<" + n.tagName;
      if (ns !== inheritedNs && ns !== null && (n._attrs || {}).xmlns !== ns) markup += ` xmlns="${ns}"`;
      let scope = declared;
      const entries = __attrEntries(n);
      for (const [k] of entries) {
        if (k.startsWith("xmlns:")) { if (scope === declared) scope = new Set(declared); scope.add(k.slice(6)); }
      }
      let attrs = "";
      for (const [k, v] of entries) {
        if (k.startsWith("xlink:") && !scope.has("xlink")) {
          if (scope === declared) scope = new Set(declared);
          scope.add("xlink");
          attrs += ` xmlns:xlink="${__XLINK_NS}"`;
        }
        attrs += ` ${k}="${__escAttr(v)}"`;
      }
      markup += attrs;
      if (n.childNodes.length === 0) {
        if (ns === XHTML_NS) return __SER_VOID.has(n.tagName) ? markup + " />" : markup + `></${n.tagName}>`;
        return markup + "/>";
      }
      const inner = n.childNodes.map((c) => ser(c, ns, scope)).join("");
      return `${markup}>${inner}</${n.tagName}>`;
    };
    return ser(root, root.parentNode ? (root.parentNode.namespaceURI || null) : null, new Set());
  }
}
globalThis.XMLSerializer = XMLSerializer;
// Named entities beyond the five XML ones that mermaid's own label decoding
// (innerHTML on a scratch element, read back as textContent) relies on a real
// parser to resolve. mermaid's own label entity-decoding ("entityDecode") sets
// innerHTML on a scratch element and reads textContent back -- the trick a
// browser's parser makes work for any named/numeric entity. A named entity not
// listed here (e.g. &nbsp; is a real non-breaking space in a label, not visible
// text that should read "&nbsp;") would pass through unchanged.
const __NAMED_ENTITIES = {
  nbsp: "\u00A0", copy: "\u00A9", reg: "\u00AE", trade: "\u2122",
  mdash: "\u2014", ndash: "\u2013", hellip: "\u2026",
  larr: "\u2190", uarr: "\u2191", rarr: "\u2192", darr: "\u2193",
  deg: "\u00B0", plusmn: "\u00B1", times: "\u00D7", divide: "\u00F7",
  sect: "\u00A7", para: "\u00B6", middot: "\u00B7",
  laquo: "\u00AB", raquo: "\u00BB",
  euro: "\u20AC", pound: "\u00A3", yen: "\u00A5", cent: "\u00A2",
};
// One pass, so "&amp;lt;" decodes to the text "&lt;" (not to "<"), as a browser does.
function __decodeEntities(text) {
  return text.replace(/&(?:#x([0-9a-fA-F]+)|#(\d+)|([a-zA-Z]+));/g, (m0, hex, dec, name) => {
    if (hex !== undefined) return String.fromCodePoint(parseInt(hex, 16));
    if (dec !== undefined) return String.fromCodePoint(parseInt(dec, 10));
    if (name in __NAMED_ENTITIES) return __NAMED_ENTITIES[name];
    return name === "lt" ? "<" : name === "gt" ? ">" : name === "quot" ? '"' :
           name === "apos" ? "'" : name === "amp" ? "&" : m0;
  });
}

// Namespace a parsed element gets when parsing like an HTML document does: <svg> starts
// the SVG namespace, which its descendants inherit except under an HTML integration
// point (<foreignObject>, <desc>, <title>), where content is XHTML again.
function __parsedNamespace(tag, parent) {
  if (tag.toLowerCase() === "svg") return SVG_NS;
  const pns = parent && parent.namespaceURI;
  if (pns === SVG_NS) {
    const pt = parent.tagName;
    return pt === "foreignObject" || pt === "desc" || pt === "title" ? XHTML_NS : SVG_NS;
  }
  return pns || XHTML_NS;
}

// opts.doc: owner document for created nodes (default: the global one);
// opts.namespaces: assign SVG/XHTML namespaces by HTML-parsing rules (DOMParser path).
function __parseInto(parent, html, opts) {
  const doc = (opts && opts.doc) || globalThis.__document;
  const s = String(html == null ? "" : html);
  const tagRe = /<!--[\s\S]*?-->|<\/([a-zA-Z][\w:-]*)\s*>|<([a-zA-Z][\w:-]*)((?:\s+[\w:-]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>/g;
  const VOID = new Set(["br","hr","img","input","meta","link","area","base","col","embed","param","source","track","wbr"]);
  let stack = [parent];
  let last = 0;
  let m;
  function pushText(text) {
    if (!text) return;
    const t = __decodeEntities(text);
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
    const el = opts && opts.namespaces
      ? new Element(tag, __parsedNamespace(tag, stack[stack.length-1]))
      : doc.createElement(tag);
    const attrRe = /([\w:-]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|[^\s>]+))?/g;
    let am;
    while ((am = attrRe.exec(attrStr))) {
      const name = am[1];
      const val = am[3] !== undefined ? am[3] : (am[4] !== undefined ? am[4] : (am[2] || ""));
      el.setAttribute(name, __decodeEntities(val));
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


// ===== what DOMPurify (bundled inside mermaid.js) needs from a browser =====================
// mermaid.render() ends with DOMPurify.sanitize(svg, ...), which in a real browser drops
// every attribute outside its allowlist (mermaid's own layout scratch attributes such as
// `label-offset-y`, `text-height`, journey's `position`) and trims attribute values.
// DOMPurify switches itself off (`isSupported = false`) unless the page provides an HTML
// parser (DOMParser / document.implementation), NodeFilter + NodeIterator, and a handful of
// DOM interfaces and accessors -- so those are provided here and DOMPurify itself does the
// sanitizing, exactly as in a browser.

// DOMPurify reads parentNode/childNodes/nextSibling/cloneNode/remove from Element.prototype
// (lookupGetter) and, when it can't find one, silently does nothing -- including NOT removing
// a node it decided to remove. This shim keeps parentNode/childNodes as own data properties
// (the rest of the shim reads and writes them directly), so also expose them as prototype
// accessors that defer to the own property.
for (const prop of ["parentNode", "childNodes"]) {
  Object.defineProperty(Node.prototype, prop, {
    configurable: true,
    get() { const d = Object.getOwnPropertyDescriptor(this, prop); return d ? d.value : (prop === "childNodes" ? [] : null); },
    set(v) { Object.defineProperty(this, prop, { value: v, writable: true, enumerable: true, configurable: true }); },
  });
}
Object.defineProperties(Node.prototype, {
  nodeName: { configurable: true, get() { return this.nodeType === 3 ? "#text" : this.nodeType === 9 ? "#document" : this.tagName; } },
});
Node.prototype.hasChildNodes = function () { return this.childNodes.length > 0; };
Node.prototype.remove = function () { if (this.parentNode) this.parentNode.removeChild(this); };
Object.defineProperty(Element.prototype, "attributes", {
  configurable: true,
  get() {
    // a snapshot is fine: DOMPurify walks it backwards while removing/updating attributes
    return Object.keys(this._attrs).map((name) => ({ name, localName: name, value: this._attrs[name], namespaceURI: this._attrNs[name] || null, specified: true }));
  },
});

const NodeFilter = {
  FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3,
  SHOW_ALL: 0xFFFFFFFF, SHOW_ELEMENT: 0x1, SHOW_ATTRIBUTE: 0x2, SHOW_TEXT: 0x4, SHOW_CDATA_SECTION: 0x8,
  SHOW_PROCESSING_INSTRUCTION: 0x40, SHOW_COMMENT: 0x80, SHOW_DOCUMENT: 0x100,
};

// DOM Standard NodeIterator (traverse + pre-removing steps): DOMPurify removes and inserts
// nodes while iterating, and the iterator has to keep a valid position through that.
const __liveNodeIterators = new Set();
function __followingNode(node, root, skipChildren) {
  if (!skipChildren && node.childNodes.length) return node.childNodes[0];
  for (let n = node; n && n !== root; n = n.parentNode) {
    const sib = n.nextSibling;
    if (sib) return sib;
  }
  return null;
}
function __lastInclusiveDescendant(n) {
  while (n.childNodes.length) n = n.childNodes[n.childNodes.length - 1];
  return n;
}
class NodeIterator {
  constructor(root, whatToShow) {
    this.root = root;
    this.whatToShow = whatToShow === undefined ? 0xFFFFFFFF : whatToShow >>> 0;
    this.referenceNode = root;
    this.pointerBeforeReferenceNode = true;
    __liveNodeIterators.add(this);
  }
  _accepts(node) { return ((1 << (node.nodeType - 1)) & this.whatToShow) !== 0; }
  nextNode() {
    let node = this.referenceNode, before = this.pointerBeforeReferenceNode;
    for (;;) {
      if (!before) {
        node = __followingNode(node, this.root, false);
        if (!node) { __liveNodeIterators.delete(this); return null; }
      } else before = false;
      if (this._accepts(node)) {
        this.referenceNode = node; this.pointerBeforeReferenceNode = false;
        return node;
      }
    }
  }
  detach() { __liveNodeIterators.delete(this); }
  _preRemove(removed) {
    if (removed === this.root) return;
    let inside = false;
    for (let n = this.referenceNode; n; n = n.parentNode) if (n === removed) { inside = true; break; }
    if (!inside) return;
    if (this.pointerBeforeReferenceNode) {
      const next = __followingNode(removed, this.root, true);
      if (next) { this.referenceNode = next; return; }
      this.pointerBeforeReferenceNode = false;
    }
    const prev = removed.previousSibling;
    this.referenceNode = prev ? __lastInclusiveDescendant(prev) : removed.parentNode;
  }
}

function __makeDocument() {
  const d = new Document();
  d.documentElement = d.appendChild(new Element("html"));
  d.head = d.documentElement.appendChild(new Element("head"));
  d.body = d.documentElement.appendChild(new Element("body"));
  return d;
}
Document.prototype.createNodeIterator = function (root, whatToShow) { return new NodeIterator(root, whatToShow); };
Document.prototype.importNode = function (node, deep) { return node.cloneNode(!!deep); };
Document.prototype.getElementsByTagName = function (tag) {
  const out = [], want = String(tag).toLowerCase();
  (function walk(n) {
    for (const c of n.childNodes) {
      if (c.nodeType !== 1) continue;
      if (want === "*" || c.tagName.toLowerCase() === want) out.push(c);
      walk(c);
    }
  })(this);
  return out;
};
Object.defineProperty(Document.prototype, "implementation", {
  configurable: true,
  get() {
    return {
      createHTMLDocument() { return __makeDocument(); },
      createDocument(ns, qualifiedName) {
        const d = new Document();
        d.documentElement = d.appendChild(new Element(qualifiedName || "html", ns));
        return d;
      },
    };
  },
});

// A document parsed like an HTML document: <svg> content in the SVG namespace, children of
// <foreignObject> back in XHTML.
class DOMParser {
  parseFromString(markup) {
    const d = __makeDocument();
    __parseInto(d.body, markup, { doc: d, namespaces: true });
    return d;
  }
}
// Interfaces DOMPurify names (instanceof / destructuring); never instantiated here.
class HTMLFormElement extends Element {}
class NamedNodeMap {}
class DocumentFragment extends Node {}
globalThis.NodeFilter = NodeFilter;
globalThis.NodeIterator = NodeIterator;
globalThis.DOMParser = DOMParser;
globalThis.HTMLFormElement = HTMLFormElement;
globalThis.NamedNodeMap = NamedNodeMap;
globalThis.DocumentFragment = DocumentFragment;

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
// mmdc's page has an 800x600 viewport, which sizes the screen too; mermaid's C4 diagram wraps its rows at
// screen.availWidth (the other three are the same emulation, not read by mermaid).
globalThis.screen = { width: 800, height: 600, availWidth: 800, availHeight: 600, colorDepth: 24, pixelDepth: 24 };
globalThis.getComputedStyle = (el) => el.style;
// Timers are a browser's macrotask queue, on virtual time. setTimeout / setInterval / requestAnimationFrame
// callbacks run one at a time, the one due first first (a tie: in the order they were scheduled), with every
// promise job drained between two of them. Nothing waits: the clock jumps to the next due time. The engine runs
// them with __runNextTimer() until what it is waiting for has happened -- a page that asks for a frame in every
// frame (cytoscape does) never goes idle by itself.
(() => {
  const FRAME_MS = 16;
  const queue = []; // {id, due, order, fn, args, every}
  let now = 0, lastId = 0, lastOrder = 0;
  const delay = (ms) => { const n = Number(ms); return n > 0 ? n : 0; }; // NaN, negative, missing: 0
  const schedule = (id, due, fn, args, every) => queue.push({ id, due, order: ++lastOrder, fn, args, every });
  const cancel = (id) => { const i = queue.findIndex((t) => t.id === Number(id)); if (i >= 0) queue.splice(i, 1); };
  const nextFrame = () => (Math.floor(now / FRAME_MS) + 1) * FRAME_MS;

  globalThis.setTimeout = (fn, ms, ...args) => { const id = ++lastId; schedule(id, now + delay(ms), fn, args, null); return id; };
  globalThis.setInterval = (fn, ms, ...args) => { const id = ++lastId, every = Math.max(1, delay(ms)); schedule(id, now + every, fn, args, every); return id; };
  globalThis.requestAnimationFrame = (fn) => { const id = ++lastId; schedule(id, nextFrame(), () => fn(now), [], null); return id; };
  globalThis.clearTimeout = globalThis.clearInterval = globalThis.cancelAnimationFrame = cancel;

  // Runs the next timer; false when there is none.
  globalThis.__runNextTimer = () => {
    if (queue.length === 0) return false;
    let k = 0;
    for (let i = 1; i < queue.length; i++) {
      if (queue[i].due < queue[k].due || (queue[i].due === queue[k].due && queue[i].order < queue[k].order)) k = i;
    }
    const [t] = queue.splice(k, 1);
    now = Math.max(now, t.due);
    if (t.every !== null) schedule(t.id, now + t.every, t.fn, t.args, t.every); // before the callback, so it can clear itself
    try { if (typeof t.fn === "function") t.fn(...t.args); }
    catch (e) { if (globalThis.__log) globalThis.__log("uncaught in a timer callback: " + e); }
    return true;
  };
})();
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
  // mermaid-cli's page (dist/index.html) is <body><div id="container"></div></body>
  const container = document_.body.appendChild(new Element("div"));
  container.setAttribute("id", "container");
};