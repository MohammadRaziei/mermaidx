// Shared by the benchmark page and its charts.
export const COLOR_VARS = {
  mmdc: '--mx-mmdc',
  'mermaidx-quickjs': '--mx-quickjs',
  'mermaidx-v8': '--mx-v8',
  'mermaidx-pele-quickjs': '--mx-pele-quickjs',
  'mermaidx-pele-v8': '--mx-pele-v8',
  'mermaidx-merman': '--mx-merman',
  'mermaidx-mermaid-rs-renderer': '--mx-rust',
};

// For CSS (swatches). Charts read the computed value instead, see cssColor().
export const colorOf = (id) => (COLOR_VARS[id] ? `var(${COLOR_VARS[id]})` : 'var(--mx-muted)');

export function fmtMs(ms) {
  if (ms == null) return '–';
  if (ms >= 10000) return `${(ms / 1000).toFixed(1)} s`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${ms < 100 ? ms.toFixed(1) : Math.round(ms)} ms`;
}

export function fmtTimes(x) {
  return `${x.toFixed(x >= 10 ? 0 : 1)}×`;
}

// Compact axis tick: 10 ms, 100 ms, 1 s.
export function fmtTick(v) {
  return v >= 1000 ? `${+(v / 1000).toFixed(1)} s` : `${+v.toFixed(1)} ms`;
}

// Axis label: the renderer's own label ("@mermaid-js/mermaid-cli", "js:mermaid | quickjs", "rust:merman").
export function chartLabel(r) {
  return r.label;
}

// "23× faster", "1.4× slower" or "about the same", for a ratio of reference time / own time.
export function fmtSpeed(ratio) {
  if (ratio >= 1.05) return `${fmtTimes(ratio)} faster`;
  if (ratio <= 0.95) return `${fmtTimes(1 / ratio)} slower`;
  return 'about the same';
}

// 21.6 MB, 4.1 GB, 730 KB.
export function fmtBytes(b) {
  if (b == null) return '–';
  if (b >= 1e9) return `${(b / 1e9).toFixed(1)} GB`;
  if (b >= 1e6) return `${b >= 1e8 ? Math.round(b / 1e6) : (b / 1e6).toFixed(1)} MB`;
  return `${Math.round(b / 1e3)} KB`;
}

// 0.973 -> "97%"
export function fmtPercent(x) {
  return x == null ? '–' : `${Math.round(x * 100)}%`;
}

// What mermaid.js itself does not draw. A sample that uses one of these is marked in the gallery and can be filtered.
export const FEATURES = {
  elk: { label: 'Flowchart, ELK layout', short: 'ELK layout' },
  zenuml: { label: 'ZenUML', short: 'ZenUML' },
};

// pele has no ELK layout: it ignores the request and draws the flowchart with its own layout.
export const ignoresElk = (rendererId) => rendererId.includes('pele');
