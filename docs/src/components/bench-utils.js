// Shared by the benchmark page and its charts.
export const COLOR_VARS = {
  mmdc: '--mx-mmdc',
  'mermaidx-quickjs': '--mx-quickjs',
  'mermaidx-v8': '--mx-v8',
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

// Two-line axis label: "mermaidx" over the backend name, or just "mmdc".
export function chartLabel(r) {
  return r.id.startsWith('mermaidx-') ? ['mermaidx', r.id.slice('mermaidx-'.length)] : r.label;
}

// "23× faster", "1.4× slower" or "about the same", for a ratio of reference time / own time.
export function fmtSpeed(ratio) {
  if (ratio >= 1.05) return `${fmtTimes(ratio)} faster`;
  if (ratio <= 0.95) return `${fmtTimes(1 / ratio)} slower`;
  return 'about the same';
}
