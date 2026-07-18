"""
mermaidx.path_bbox — SVG path `d`-string bounding-box math.

This is pure geometry (no fonts, no Python-specific state), so unlike text
measurement it doesn't need a callback into Python at all. It's kept here in
two faithfully-equivalent forms:

  - `path_bbox()` / `_arc_extrema()` — the Python reference implementation
    (also used directly by tests).
  - `PATH_BBOX_JS` — a hand-ported JS version of the exact same algorithm,
    embedded directly into whichever JS engine is running (QuickJS or V8),
    so `pathBBox()` never has to cross the Python/JS boundary in either
    backend.
"""

from __future__ import annotations

import math
import re

_PATH_CMD_CHARS = set("MmLlHhVvCcSsQqTtAaZz")
_PATH_NUM_RE = re.compile(r"-?\d*\.\d+(?:[eE][-+]?\d+)?|-?\d+(?:[eE][-+]?\d+)?")
_PATH_ARGC = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def _arc_extrema(x1, y1, rx, ry, rot_deg, large_arc, sweep, x2, y2):
    """Points bounding an SVG elliptical-arc segment: the two endpoints plus
    any axis-aligned extrema the arc actually sweeps through, via the
    standard endpoint-to-center parameterization (SVG 1.1 appendix F.6).
    Degenerate/rotated-ellipse edge cases fall back to a padded box around
    the endpoints rather than getting the extrema wrong.
    """
    if rx == 0 or ry == 0:
        return [(x1, y1), (x2, y2)]
    phi = math.radians(rot_deg % 360)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    rxsq, rysq = rx * rx, ry * ry
    num = rxsq * rysq - rxsq * y1p * y1p - rysq * x1p * x1p
    denom = rxsq * y1p * y1p + rysq * x1p * x1p
    if denom == 0:
        return [(x1, y1), (x2, y2)]
    co = math.sqrt(max(0.0, num / denom))
    if large_arc == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        d = math.hypot(ux, uy) * math.hypot(vx, vy)
        if d == 0:
            return 0.0
        c = max(-1.0, min(1.0, (ux * vx + uy * vy) / d))
        a = math.acos(c)
        return -a if ux * vy - uy * vx < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi
    theta2 = theta1 + dtheta

    pts = [(x1, y1), (x2, y2)]
    lo, hi = min(theta1, theta2), max(theta1, theta2)
    for k in range(4):
        ang = k * math.pi / 2
        a = ang
        while a < lo:
            a += 2 * math.pi
        if a <= hi:
            pts.append((cx + rx * math.cos(a) * cos_p - ry * math.sin(a) * sin_p,
                        cy + rx * math.cos(a) * sin_p + ry * math.sin(a) * cos_p))
    return pts


def path_bbox(d: str) -> dict:
    """Bbox from an SVG path's `d` string, via a real (if minimal) parser.

    Exact geometry isn't the goal (this only feeds getBBox() for layout), so
    bezier control points are folded in as extra points around the
    endpoints, but arcs get their true extrema since they're common in
    mermaid's shape library (cylinders, stadiums, rounded corners).
    """
    if not d:
        return {"x": 0, "y": 0, "width": 0, "height": 0}

    xs: list[float] = []
    ys: list[float] = []
    cx = cy = 0.0
    start_x = start_y = 0.0
    cmd = None
    i, n = 0, len(d)
    first_pair_of_cmd = True
    while i < n:
        ch = d[i]
        if ch in _PATH_CMD_CHARS:
            cmd = ch
            first_pair_of_cmd = True
            i += 1
            continue
        if ch.isspace() or ch == ",":
            i += 1
            continue
        if cmd is None:
            i += 1
            continue
        if cmd.upper() == "Z":
            cx, cy = start_x, start_y
            xs.append(cx)
            ys.append(cy)
            cmd = None
            continue

        argc = _PATH_ARGC[cmd.upper()]
        is_rel = cmd.islower()
        group: list[float] = []
        while len(group) < argc:
            m = _PATH_NUM_RE.match(d, i)
            if not m:
                break
            group.append(float(m.group()))
            i = m.end()
            while i < n and (d[i].isspace() or d[i] == ","):
                i += 1
        if len(group) < argc:
            break  # malformed tail -- stop rather than misparse

        effective_cmd = cmd.upper()
        if effective_cmd == "M" and not first_pair_of_cmd:
            effective_cmd = "L"  # subsequent pairs after M are implicit lineto

        if effective_cmd == "H":
            nx = cx + group[0] if is_rel else group[0]
            ny = cy
            xs.append(nx); ys.append(ny)
        elif effective_cmd == "V":
            nx = cx
            ny = cy + group[0] if is_rel else group[0]
            xs.append(nx); ys.append(ny)
        elif effective_cmd == "A":
            rx, ry, rot, laf, sf, ex, ey = group
            nx = cx + ex if is_rel else ex
            ny = cy + ey if is_rel else ey
            rx, ry = abs(rx), abs(ry)
            pts = _arc_extrema(cx, cy, rx, ry, rot, laf, sf, nx, ny)
            xs.extend(p[0] for p in pts)
            ys.extend(p[1] for p in pts)
        else:  # M, L, C, S, Q, T
            for k in range(0, len(group), 2):
                px, py = group[k], group[k + 1]
                if is_rel:
                    px += cx
                    py += cy
                xs.append(px)
                ys.append(py)
            nx, ny = xs[-1], ys[-1]

        cx, cy = nx, ny
        if effective_cmd == "M":
            start_x, start_y = cx, cy
        first_pair_of_cmd = False

    if not xs:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


# Backward-compat alias (this was the name used before path_bbox.py existed).
_path_bbox = path_bbox


# A faithful, hand-checked JS port of the exact same algorithm above.
# Installs itself as `globalThis.__pathBBox`. No Python callback involved --
# usable as-is regardless of which JS engine (QuickJS, V8, ...) is running.
PATH_BBOX_JS = r"""
globalThis.__pathBBox = (function () {
  const CMD_CHARS = "MmLlHhVvCcSsQqTtAaZz";
  const ARGC = {M:2,L:2,T:2,H:1,V:1,C:6,S:4,Q:4,A:7,Z:0};
  const NUM_RE = /-?\d*\.\d+(?:[eE][-+]?\d+)?|-?\d+(?:[eE][-+]?\d+)?/y;

  function arcExtrema(x1, y1, rx, ry, rotDeg, largeArc, sweep, x2, y2) {
    if (rx === 0 || ry === 0) return [[x1, y1], [x2, y2]];
    const phi = ((rotDeg % 360) * Math.PI) / 180;
    const cosP = Math.cos(phi), sinP = Math.sin(phi);
    const dx = (x1 - x2) / 2, dy = (y1 - y2) / 2;
    const x1p = cosP * dx + sinP * dy;
    const y1p = -sinP * dx + cosP * dy;
    const rxsq = rx * rx, rysq = ry * ry;
    const num = rxsq * rysq - rxsq * y1p * y1p - rysq * x1p * x1p;
    const denom = rxsq * y1p * y1p + rysq * x1p * x1p;
    if (denom === 0) return [[x1, y1], [x2, y2]];
    let co = Math.sqrt(Math.max(0, num / denom));
    if (largeArc === sweep) co = -co;
    const cxp = (co * rx * y1p) / ry;
    const cyp = (-co * ry * x1p) / rx;
    const cx = cosP * cxp - sinP * cyp + (x1 + x2) / 2;
    const cy = sinP * cxp + cosP * cyp + (y1 + y2) / 2;

    function angle(ux, uy, vx, vy) {
      const d = Math.hypot(ux, uy) * Math.hypot(vx, vy);
      if (d === 0) return 0;
      let c = (ux * vx + uy * vy) / d;
      c = Math.max(-1, Math.min(1, c));
      const a = Math.acos(c);
      return ux * vy - uy * vx < 0 ? -a : a;
    }

    let theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry);
    let dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry);
    if (!sweep && dtheta > 0) dtheta -= 2 * Math.PI;
    else if (sweep && dtheta < 0) dtheta += 2 * Math.PI;
    const theta2 = theta1 + dtheta;

    const pts = [[x1, y1], [x2, y2]];
    const lo = Math.min(theta1, theta2), hi = Math.max(theta1, theta2);
    for (let k = 0; k < 4; k++) {
      let a = (k * Math.PI) / 2;
      while (a < lo) a += 2 * Math.PI;
      if (a <= hi) {
        pts.push([
          cx + rx * Math.cos(a) * cosP - ry * Math.sin(a) * sinP,
          cy + rx * Math.cos(a) * sinP + ry * Math.sin(a) * cosP,
        ]);
      }
    }
    return pts;
  }

  return function pathBBox(d) {
    if (!d) return { x: 0, y: 0, width: 0, height: 0 };

    const xs = [], ys = [];
    let cx = 0, cy = 0, startX = 0, startY = 0;
    let cmd = null;
    let i = 0;
    const n = d.length;
    let firstPairOfCmd = true;

    while (i < n) {
      const ch = d[i];
      if (CMD_CHARS.indexOf(ch) !== -1) {
        cmd = ch;
        firstPairOfCmd = true;
        i += 1;
        continue;
      }
      if (/\s/.test(ch) || ch === ",") { i += 1; continue; }
      if (cmd === null) { i += 1; continue; }
      if (cmd.toUpperCase() === "Z") {
        cx = startX; cy = startY;
        xs.push(cx); ys.push(cy);
        cmd = null;
        continue;
      }

      const argc = ARGC[cmd.toUpperCase()];
      const isRel = cmd === cmd.toLowerCase();
      const group = [];
      while (group.length < argc) {
        NUM_RE.lastIndex = i;
        const m = NUM_RE.exec(d);
        if (!m || m.index !== i) break;
        group.push(parseFloat(m[0]));
        i = NUM_RE.lastIndex;
        while (i < n && (/\s/.test(d[i]) || d[i] === ",")) i += 1;
      }
      if (group.length < argc) break; // malformed tail -- stop rather than misparse

      let effectiveCmd = cmd.toUpperCase();
      if (effectiveCmd === "M" && !firstPairOfCmd) effectiveCmd = "L";

      let nx, ny;
      if (effectiveCmd === "H") {
        nx = isRel ? cx + group[0] : group[0];
        ny = cy;
        xs.push(nx); ys.push(ny);
      } else if (effectiveCmd === "V") {
        nx = cx;
        ny = isRel ? cy + group[0] : group[0];
        xs.push(nx); ys.push(ny);
      } else if (effectiveCmd === "A") {
        let [rx, ry, rot, laf, sf, ex, ey] = group;
        nx = isRel ? cx + ex : ex;
        ny = isRel ? cy + ey : ey;
        rx = Math.abs(rx); ry = Math.abs(ry);
        const pts = arcExtrema(cx, cy, rx, ry, rot, laf, sf, nx, ny);
        for (const p of pts) { xs.push(p[0]); ys.push(p[1]); }
      } else {
        for (let k = 0; k < group.length; k += 2) {
          let px = group[k], py = group[k + 1];
          if (isRel) { px += cx; py += cy; }
          xs.push(px); ys.push(py);
        }
        nx = xs[xs.length - 1]; ny = ys[ys.length - 1];
      }

      cx = nx; cy = ny;
      if (effectiveCmd === "M") { startX = cx; startY = cy; }
      firstPairOfCmd = false;
    }

    if (xs.length === 0) return { x: 0, y: 0, width: 0, height: 0 };
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  };
})();
"""
