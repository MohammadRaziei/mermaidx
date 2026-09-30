"""Attribute allowlist filtering that real mermaid.js applies to its final SVG.

In a browser, `mermaid.render()` ends with

    DOMPurify.sanitize(svg, {ADD_TAGS: ["foreignobject"], ADD_ATTR: ["dominant-baseline"], ...})

(skipped only for `securityLevel: "sandbox"`), which drops every attribute
outside DOMPurify's allowlist -- e.g. the layout scratch attributes mermaid
leaves on shapes (`label-offset-y`, `text-height`, journey's `position`).
DOMPurify refuses to run inside mermaidx's DOM shim (its `isSupported` needs a
real `document.implementation.createHTMLDocument`), so `sanitize()` there is a
no-op and those attributes leak into the output; a browser's output doesn't
have them. This module applies the same attribute filter to the finished SVG
string so the result matches what mmdc / a browser produces.

`ALLOWED_ATTRS` is DOMPurify 3.4.0's own html + svg + mathMl + xml attribute
lists, extracted from the copy bundled in assets/mermaid.js (not retyped),
plus mermaid's own ADD_ATTR entry. `data-*` and `aria-*` attributes are allowed
by DOMPurify's ALLOW_DATA_ATTR / ALLOW_ARIA_ATTR defaults.
"""

from __future__ import annotations

import re

ALLOWED_ATTRS = frozenset((
"accent", "accent-height", "accentunder", "accept", "accumulate", "action", "additive", "align",
"alignment-baseline", "alt", "amplitude", "ascent", "attributename", "attributetype",
"autocapitalize", "autocomplete", "autopictureinpicture", "autoplay", "azimuth", "background",
"basefrequency", "baseline-shift", "begin", "bevelled", "bgcolor", "bias", "border", "by",
"capture", "cellpadding", "cellspacing", "checked", "cite", "class", "clear", "clip", "clip-path",
"clip-rule", "clippathunits", "close", "color", "color-interpolation",
"color-interpolation-filters", "color-profile", "color-rendering", "cols", "colspan", "columnalign",
"columnlines", "columnspacing", "columnspan", "controls", "controlslist", "coords", "crossorigin",
"cx", "cy", "d", "datetime", "decoding", "default", "denomalign", "depth", "diffuseconstant", "dir",
"direction", "disabled", "disablepictureinpicture", "disableremoteplayback", "display",
"displaystyle", "divisor", "dominant-baseline", "download", "draggable", "dur", "dx", "dy",
"edgemode", "elevation", "encoding", "enctype", "end", "enterkeyhint", "exponent", "exportparts",
"face", "fence", "fill", "fill-opacity", "fill-rule", "filter", "filterunits", "flood-color",
"flood-opacity", "font-family", "font-size", "font-size-adjust", "font-stretch", "font-style",
"font-variant", "font-weight", "for", "frame", "fx", "fy", "g1", "g2", "glyph-name", "glyphref",
"gradienttransform", "gradientunits", "headers", "height", "hidden", "high", "href", "hreflang",
"id", "image-rendering", "in", "in2", "inert", "inputmode", "integrity", "intercept", "ismap", "k",
"k1", "k2", "k3", "k4", "kernelmatrix", "kernelunitlength", "kerning", "keypoints", "keysplines",
"keytimes", "kind", "label", "lang", "largeop", "length", "lengthadjust", "letter-spacing",
"lighting-color", "linethickness", "list", "loading", "local", "loop", "low", "lquote", "lspace",
"marker-end", "marker-mid", "marker-start", "markerheight", "markerunits", "markerwidth", "mask",
"mask-type", "maskcontentunits", "maskunits", "mathbackground", "mathcolor", "mathsize",
"mathvariant", "max", "maxlength", "maxsize", "media", "method", "min", "minlength", "minsize",
"mode", "movablelimits", "multiple", "muted", "name", "nonce", "noshade", "notation", "novalidate",
"nowrap", "numalign", "numoctaves", "offset", "opacity", "open", "operator", "optimum", "order",
"orient", "orientation", "origin", "overflow", "paint-order", "part", "path", "pathlength",
"pattern", "patterncontentunits", "patterntransform", "patternunits", "placeholder", "playsinline",
"points", "popover", "popovertarget", "popovertargetaction", "poster", "preload", "preservealpha",
"preserveaspectratio", "primitiveunits", "pubdate", "r", "radiogroup", "radius", "readonly", "refx",
"refy", "rel", "repeatcount", "repeatdur", "required", "restart", "result", "rev", "reversed",
"role", "rotate", "rowalign", "rowlines", "rows", "rowspacing", "rowspan", "rquote", "rspace", "rx",
"ry", "scale", "scope", "scriptlevel", "scriptminsize", "scriptsizemultiplier", "seed", "selected",
"selection", "separator", "separators", "shape", "shape-rendering", "size", "sizes", "slope",
"slot", "span", "specularconstant", "specularexponent", "spellcheck", "spreadmethod", "src",
"srclang", "srcset", "start", "startoffset", "stddeviation", "step", "stitchtiles", "stop-color",
"stop-opacity", "stretchy", "stroke", "stroke-dasharray", "stroke-dashoffset", "stroke-linecap",
"stroke-linejoin", "stroke-miterlimit", "stroke-opacity", "stroke-width", "style", "subscriptshift",
"summary", "supscriptshift", "surfacescale", "symmetric", "systemlanguage", "tabindex",
"tablevalues", "targetx", "targety", "text-anchor", "text-decoration", "text-rendering",
"textlength", "title", "transform", "transform-origin", "translate", "type", "u1", "u2", "unicode",
"usemap", "valign", "value", "values", "version", "vert-adv-y", "vert-origin-x", "vert-origin-y",
"viewbox", "visibility", "voffset", "width", "word-spacing", "wrap", "writing-mode", "x", "x1",
"x2", "xchannelselector", "xlink:href", "xlink:title", "xml:id", "xml:space", "xmlns",
"xmlns:xlink", "y", "y1", "y2", "ychannelselector", "z", "zoomandpan",
))

# One start tag: name, then attributes (quoted values may contain '>').
_TAG_RE = re.compile(r"<([A-Za-z][^\s/>]*)((?:\s+[^\s=/>]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?)*)(\s*/?>)")
_ATTR_RE = re.compile(r"(\s+)([^\s=/>]+)((?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?)")
_DATA_ARIA_RE = re.compile(r"^(?:data-[\-\w.\u00B7-\uFFFF]+|aria-[\-\w]+)$")


_VALUE_RE = re.compile(r"^(\s*=\s*)(\"|')(.*)\2$", re.S)


def _trim_value(assign: str, name: str) -> str:
    """DOMPurify also trims each kept attribute's value (except `value`)."""
    m = _VALUE_RE.match(assign)
    if not m or name.lower() == "value":
        return assign
    return f"{m.group(1)}{m.group(2)}{m.group(3).strip()}{m.group(2)}"


def _keep(name: str) -> bool:
    lc = name.lower()
    return lc in ALLOWED_ATTRS or bool(_DATA_ARIA_RE.match(lc))


def sanitize_attributes(svg: str) -> str:
    """Drop every attribute DOMPurify's default allowlist would drop, and trim the rest's values."""
    def fix_attr(a: "re.Match[str]") -> str:
        if not _keep(a.group(2)):
            return ""
        return f"{a.group(1)}{a.group(2)}{_trim_value(a.group(3), a.group(2))}"

    def fix_tag(m: "re.Match[str]") -> str:
        return f"<{m.group(1)}{_ATTR_RE.sub(fix_attr, m.group(2))}{m.group(3)}"
    return _TAG_RE.sub(fix_tag, svg)
