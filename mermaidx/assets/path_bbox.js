// getBBox() of an SVG <path>, the way Chrome computes it, in float32 like Chrome does.
//
//   Blink  parses `d` and builds an SkPath: relative coordinates are turned absolute, H/V become lines, S/T
//          reflect the previous control point, an elliptical arc is handed to SkPath::arcTo (conics).
//   Skia   SkPath::computeTightBounds() then takes the end points plus the derivative-root extrema of every
//          quad/cubic/conic (SkFindQuadExtrema, SkFindCubicExtrema, SkFindUnitQuadRoots, SkEval*At, SkConic).
//
// Skia and Blink geometry is float32: every value is rounded with Math.fround where Chrome stores a float.
// Installs itself as globalThis.__pathBBox (and __parseSvgNumber); nothing here calls back into the host.
globalThis.__pathBBox = (function () {
  "use strict";
  const F = Math.fround;
  const CMD_CHARS = "MmLlHhVvCcSsQqTtAaZz";
  const ARGC = { M: 2, L: 2, T: 2, H: 1, V: 1, C: 6, S: 4, Q: 4, A: 7, Z: 0 };
  const NUM_RE = /[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?/y;

  // Blink's number parser (svg_parser_utilities.cc) accumulates digits in float32, not a correctly rounded
  // decimal-to-float conversion: the last bit can differ from parseFloat.
  function parseNumber(text) {
    let i = 0, sign = 1;
    if (text[i] === "+") i++; else if (text[i] === "-") { sign = -1; i++; }
    let integer = 0, decimal = 0, frac = 1;
    while (i < text.length && text[i] >= "0" && text[i] <= "9") integer = F(F(integer * 10) + (text.charCodeAt(i++) - 48));
    if (text[i] === ".") {
      i++;
      while (i < text.length && text[i] >= "0" && text[i] <= "9") {
        frac = F(frac * F(0.1));
        decimal = F(decimal + F((text.charCodeAt(i++) - 48) * frac));
      }
    }
    let number = F(sign * F(integer + decimal));
    if (text[i] === "e" || text[i] === "E") {
      i++;
      let expSign = 1;
      if (text[i] === "+") i++; else if (text[i] === "-") { expSign = -1; i++; }
      let exponent = 0;
      while (i < text.length) exponent = exponent * 10 + (text.charCodeAt(i++) - 48);
      number = F(number * F(Math.pow(10, expSign * exponent)));
    }
    return number;
  }
  // Shared with the DOM shim: SVGLength attributes (x, y, dx, dy, ...) go through the same parser in Blink.
  globalThis.__parseSvgNumber = parseNumber;
  const WS_RE = /[\s,]/;

  // ---- Skia (SkGeometry.cpp) --------------------------------------------------------------------------

  // Returns t in (0, 1) for numer/denom, or -1 when there is none.
  function validUnitDivide(numer, denom) {
    if (numer < 0) { numer = -numer; denom = -denom; }
    if (denom === 0 || numer === 0 || numer >= denom) return -1;
    const r = F(numer / denom);
    if (r !== r || r === 0) return -1;
    return r;
  }

  function findUnitQuadRoots(A, B, C) {
    const roots = [];
    const push = (t) => { if (t >= 0) roots.push(t); };
    if (A === 0) { push(validUnitDivide(-C, B)); return roots; }
    let dr = B * B - 4 * A * C; // doubles, like Skia
    if (dr < 0) return roots;
    dr = Math.sqrt(dr);
    const R = F(dr);
    if (!isFinite(R)) return roots;
    const Q = B < 0 ? F(-F(B - R) / 2) : F(-F(B + R) / 2);
    push(validUnitDivide(Q, A));
    push(validUnitDivide(C, Q));
    if (roots.length === 2) {
      if (roots[0] > roots[1]) roots.reverse();
      else if (roots[0] === roots[1]) roots.pop();
    }
    return roots;
  }

  function quadExtremaTs(a, b, c) {
    const t = validUnitDivide(F(a - b), F(F(F(a - b) - b) + c));
    return t >= 0 ? [t] : [];
  }

  function cubicExtremaTs(a, b, c, d) {
    const A = F(F(d - a) + F(3 * F(b - c)));
    const B = F(2 * F(F(F(a - b) - b) + c));
    const C = F(b - a);
    return findUnitQuadRoots(A, B, C);
  }

  function evalQuad(p0, p1, p2, t) {
    const A = F(F(p2 - F(2 * p1)) + p0), B = F(2 * F(p1 - p0));
    return F(F(F(F(A * t) + B) * t) + p0);
  }

  function evalCubic(p0, p1, p2, p3, t) {
    const A = F(F(p3 + F(3 * F(p1 - p2))) - p0);
    const B = F(3 * F(F(p2 - F(2 * p1)) + p0));
    const C = F(3 * F(p1 - p0));
    return F(F(F(F(F(F(A * t) + B) * t) + C) * t) + p0);
  }

  // Conic (rational quadratic) with weight w: derivative-root extremum and evaluation (SkConic).
  function conicExtremumT(p0, p1, p2, w) {
    const P20 = F(p2 - p0), P10 = F(p1 - p0), wP10 = F(w * P10);
    const roots = findUnitQuadRoots(F(F(w * P20) - P20), F(P20 - F(2 * wP10)), wP10);
    return roots.length === 1 ? roots[0] : -1;
  }

  function evalConic(p0, p1, p2, w, t) {
    const p1w = F(p1 * w);
    const nA = F(F(p2 - F(2 * p1w)) + p0), nB = F(2 * F(p1w - p0)), nC = p0;
    const dB = F(2 * F(w - 1)), dA = F(0 - dB), dC = 1;
    const numer = F(F(F(F(nA * t) + nB) * t) + nC);
    const denom = F(F(F(F(dA * t) + dB) * t) + dC);
    return F(numer / denom);
  }

  // ---- SkPath::arcTo (SVG endpoint arc) ---------------------------------------------------------------

  const NEARLY_ZERO = 1 / 4096;
  const snap = (v) => (Math.abs(v) <= NEARLY_ZERO ? 0 : v);
  // SkMatrix is float32 [sx, ky, kx, sy]: x' = sx*x + kx*y, y' = ky*x + sy*y.
  function rotM(deg) {
    const rad = F(F(deg * F(Math.PI)) / 180);
    const sin = snap(F(Math.sin(rad))), cos = snap(F(Math.cos(rad)));
    return [cos, sin, F(-sin), cos];
  }
  const mulM = (m, n) => [
    F(F(m[0] * n[0]) + F(m[2] * n[1])), F(F(m[1] * n[0]) + F(m[3] * n[1])),
    F(F(m[0] * n[2]) + F(m[2] * n[3])), F(F(m[1] * n[2]) + F(m[3] * n[3])),
  ];
  const mapM = (m, x, y) => [F(F(m[0] * x) + F(m[2] * y)), F(F(m[1] * x) + F(m[3] * y))];

  // Calls conicTo(x1, y1, x2, y2, w) per piece; returns false when the arc is just a line.
  function arcTo(x0, y0, rxIn, ryIn, angle, large, sweep, x, y, conicTo) {
    let rx = F(Math.abs(rxIn)), ry = F(Math.abs(ryIn));
    if (!rx || !ry) return false;
    if (x0 === x && y0 === y) return false;

    const mid = mapM(rotM(-angle), F(F(x0 - x) * 0.5), F(F(y0 - y) * 0.5));
    const radiiScale = F(F(F(mid[0] * mid[0]) / F(rx * rx)) + F(F(mid[1] * mid[1]) / F(ry * ry)));
    if (radiiScale > 1) { const sq = F(Math.sqrt(radiiScale)); rx = F(rx * sq); ry = F(ry * sq); }

    const toUnit = mulM([F(1 / rx), 0, 0, F(1 / ry)], rotM(-angle));
    const u0 = mapM(toUnit, x0, y0), u1 = mapM(toUnit, x, y);
    let dx = F(u1[0] - u0[0]), dy = F(u1[1] - u0[1]);
    const dd = F(F(dx * dx) + F(dy * dy));
    let scale = F(Math.sqrt(Math.max(F(F(1 / dd) - 0.25), 0)));
    if (large === sweep) scale = -scale;
    dx = F(dx * scale); dy = F(dy * scale);
    const cx = F(F(F(u0[0] + u1[0]) * 0.5) - dy), cy = F(F(F(u0[1] + u1[1]) * 0.5) + dx);

    const theta1 = F(Math.atan2(F(u0[1] - cy), F(u0[0] - cx)));
    const theta2 = F(Math.atan2(F(u1[1] - cy), F(u1[0] - cx)));
    let thetaArc = F(theta2 - theta1);
    if (thetaArc < 0 && sweep) thetaArc = F(thetaArc + F(2 * F(Math.PI)));
    else if (thetaArc > 0 && !sweep) thetaArc = F(thetaArc - F(2 * F(Math.PI)));
    if (Math.abs(thetaArc) < F(F(Math.PI) / 1000000)) return false;

    const toEllipse = mulM(rotM(angle), [rx, 0, 0, ry]);
    const segments = Math.ceil(Math.abs(F(thetaArc / F(F(2 * F(Math.PI)) / 3))));
    const thetaWidth = F(thetaArc / segments);
    const t = F(Math.tan(F(0.5 * thetaWidth)));
    if (!isFinite(t)) return true;
    const w = F(Math.sqrt(F(0.5 + F(F(Math.cos(thetaWidth)) * 0.5))));
    let startTheta = theta1;
    for (let i = 0; i < segments; i++) {
      const endTheta = F(startTheta + thetaWidth);
      const sinE = snap(F(Math.sin(endTheta))), cosE = snap(F(Math.cos(endTheta)));
      const ex = F(cosE + cx), ey = F(sinE + cy);
      const c = mapM(toEllipse, F(ex + F(t * sinE)), F(ey - F(t * cosE)));
      const e = i === segments - 1 ? [x, y] : mapM(toEllipse, ex, ey); // the arc ends exactly on its target
      conicTo(c[0], c[1], e[0], e[1], w);
      startTheta = endTheta;
    }
    return true;
  }

  // ---- path building + SkPath::computeTightBounds -----------------------------------------------------

  return function pathBBox(d) {
    const empty = { x: 0, y: 0, width: 0, height: 0 };
    if (!d) return empty;

    let minX = NaN, minY = NaN, maxX = NaN, maxY = NaN;
    const add = (x, y) => {
      if (minX !== minX) { minX = maxX = x; minY = maxY = y; return; }
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    };

    const lineTo = (x, y) => add(x, y);
    const quadTo = (x0, y0, x1, y1, x2, y2) => {
      for (const t of quadExtremaTs(x0, x1, x2)) add(evalQuad(x0, x1, x2, t), evalQuad(y0, y1, y2, t));
      for (const t of quadExtremaTs(y0, y1, y2)) add(evalQuad(x0, x1, x2, t), evalQuad(y0, y1, y2, t));
      add(x2, y2);
    };
    const conicTo = (x0, y0, x1, y1, x2, y2, w) => {
      const tx = conicExtremumT(x0, x1, x2, w), ty = conicExtremumT(y0, y1, y2, w);
      if (tx >= 0) add(evalConic(x0, x1, x2, w, tx), evalConic(y0, y1, y2, w, tx));
      if (ty >= 0) add(evalConic(x0, x1, x2, w, ty), evalConic(y0, y1, y2, w, ty));
      add(x2, y2);
    };
    const cubicTo = (x0, y0, x1, y1, x2, y2, x3, y3) => {
      for (const t of cubicExtremaTs(x0, x1, x2, x3)) add(evalCubic(x0, x1, x2, x3, t), evalCubic(y0, y1, y2, y3, t));
      for (const t of cubicExtremaTs(y0, y1, y2, y3)) add(evalCubic(x0, x1, x2, x3, t), evalCubic(y0, y1, y2, y3, t));
      add(x3, y3);
    };

    let cx = 0, cy = 0, startX = 0, startY = 0;
    let cmd = null, prevType = null, lastCtrlX = 0, lastCtrlY = 0;
    let firstPairOfCmd = true;
    let i = 0;
    const n = d.length;

    while (i < n) {
      const ch = d[i];
      if (CMD_CHARS.indexOf(ch) !== -1) { cmd = ch; firstPairOfCmd = true; i += 1; continue; }
      if (WS_RE.test(ch)) { i += 1; continue; }
      if (cmd === null) { i += 1; continue; }
      if (cmd === "Z" || cmd === "z") {
        cx = startX; cy = startY; prevType = "Z"; cmd = null;
        continue;
      }

      const upper = cmd.toUpperCase();
      const isRel = cmd !== upper;
      const group = [];
      while (group.length < ARGC[upper]) {
        NUM_RE.lastIndex = i;
        const m = NUM_RE.exec(d);
        if (!m) break;
        group.push(parseNumber(m[0]));
        i = NUM_RE.lastIndex;
        while (i < n && WS_RE.test(d[i])) i += 1;
      }
      if (group.length < ARGC[upper]) break; // malformed tail: keep what was built so far

      const type = upper === "M" && !firstPairOfCmd ? "L" : upper;
      const absX = (v) => (isRel ? F(cx + v) : v);
      const absY = (v) => (isRel ? F(cy + v) : v);
      let nx, ny;

      if (type === "M") {
        nx = absX(group[0]); ny = absY(group[1]);
        add(nx, ny);
        startX = nx; startY = ny;
      } else if (type === "L") {
        nx = absX(group[0]); ny = absY(group[1]);
        lineTo(nx, ny);
      } else if (type === "H") {
        nx = absX(group[0]); ny = cy;
        lineTo(nx, ny);
      } else if (type === "V") {
        nx = cx; ny = absY(group[0]);
        lineTo(nx, ny);
      } else if (type === "C") {
        const x1 = absX(group[0]), y1 = absY(group[1]), x2 = absX(group[2]), y2 = absY(group[3]);
        nx = absX(group[4]); ny = absY(group[5]);
        cubicTo(cx, cy, x1, y1, x2, y2, nx, ny);
        lastCtrlX = x2; lastCtrlY = y2;
      } else if (type === "S") {
        const x2 = absX(group[0]), y2 = absY(group[1]);
        nx = absX(group[2]); ny = absY(group[3]);
        const smooth = prevType === "C" || prevType === "S";
        const x1 = smooth ? F(F(2 * cx) - lastCtrlX) : cx, y1 = smooth ? F(F(2 * cy) - lastCtrlY) : cy;
        cubicTo(cx, cy, x1, y1, x2, y2, nx, ny);
        lastCtrlX = x2; lastCtrlY = y2;
      } else if (type === "Q") {
        const x1 = absX(group[0]), y1 = absY(group[1]);
        nx = absX(group[2]); ny = absY(group[3]);
        quadTo(cx, cy, x1, y1, nx, ny);
        lastCtrlX = x1; lastCtrlY = y1;
      } else if (type === "T") {
        nx = absX(group[0]); ny = absY(group[1]);
        const smooth = prevType === "Q" || prevType === "T";
        const x1 = smooth ? F(F(2 * cx) - lastCtrlX) : cx, y1 = smooth ? F(F(2 * cy) - lastCtrlY) : cy;
        quadTo(cx, cy, x1, y1, nx, ny);
        lastCtrlX = x1; lastCtrlY = y1;
      } else { // A
        nx = absX(group[5]); ny = absY(group[6]);
        let px = cx, py = cy;
        const drawn = arcTo(cx, cy, group[0], group[1], group[2], group[3] !== 0, group[4] !== 0, nx, ny,
          (x1, y1, x2, y2, w) => { conicTo(px, py, x1, y1, x2, y2, w); px = x2; py = y2; });
        if (!drawn) lineTo(nx, ny);
      }

      prevType = type;
      cx = nx; cy = ny;
      firstPairOfCmd = false;
    }

    if (minX !== minX) return empty;
    return { x: minX, y: minY, width: F(maxX - minX), height: F(maxY - minY) };
  };
})();
