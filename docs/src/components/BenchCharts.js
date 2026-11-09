import React, { useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';
import Link from '@docusaurus/Link';
import { useColorMode } from '@docusaurus/theme-common';
import { COLOR_VARS, chartLabel, fmtBytes, fmtMs, fmtSpeed, fmtTick } from './bench-utils';
import styles from './BenchCharts.module.css';

Chart.register(...registerables);

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function readTheme() {
  const color = (id) => cssVar(COLOR_VARS[id] || '--mx-muted');
  return {
    text: cssVar('--ifm-font-color-base'),
    muted: cssVar('--mx-muted'),
    line: cssVar('--mx-line'),
    surface: cssVar('--mx-surface'),
    font: getComputedStyle(document.body).fontFamily,
    color,
  };
}

// Builds a chart from buildConfig(theme) and rebuilds it when the color mode or the inputs change.
function useChart(buildConfig, deps) {
  const canvas = useRef(null);
  const { colorMode } = useColorMode();
  useEffect(() => {
    let chart;
    // Wait one frame so the new theme's CSS variables are in place.
    const frame = requestAnimationFrame(() => {
      if (!canvas.current) return;
      const theme = readTheme();
      Chart.defaults.font.family = theme.font;
      Chart.defaults.color = theme.muted;
      chart = new Chart(canvas.current, buildConfig(theme));
    });
    return () => {
      cancelAnimationFrame(frame);
      if (chart) chart.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colorMode, ...deps]);
  return canvas;
}

const tooltipBase = (theme) => ({
  backgroundColor: theme.surface,
  titleColor: theme.text,
  bodyColor: theme.text,
  borderColor: theme.line,
  borderWidth: 1,
  padding: 10,
  boxPadding: 4,
});

// Draws the value at the end of every bar.
const valueLabels = {
  id: 'valueLabels',
  afterDatasetsDraw(chart, _args, opts) {
    const { ctx } = chart;
    ctx.save();
    ctx.font = `600 13px ${Chart.defaults.font.family}`;
    ctx.fillStyle = opts.color;
    ctx.textBaseline = 'middle';
    chart.getDatasetMeta(opts.dataset || 0).data.forEach((bar, i) => {
      const text = opts.labels[i];
      if (text) ctx.fillText(text, bar.x + 8, bar.y);
    });
    ctx.restore();
  },
};

function MedianChart({ rows, log }) {
  const ref = useChart(
    (theme) => {
      const values = rows.map((r) => r.median || 0);
      const positive = values.filter((v) => v > 0);
      const lo = Math.min(...positive);
      const hi = Math.max(...positive);
      return {
        type: 'bar',
        data: {
          labels: rows.map(chartLabel),
          datasets: [{ data: values, backgroundColor: rows.map((r) => theme.color(r.id)), borderRadius: 3, barThickness: 26 }],
        },
        plugins: [valueLabels],
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          layout: { padding: { right: 170 } },
          scales: {
            x: {
              type: log ? 'logarithmic' : 'linear',
              min: log ? Math.pow(10, Math.floor(Math.log10(lo))) : 0,
              max: log ? Math.pow(10, Math.ceil(Math.log10(hi))) : undefined,
              grid: { color: theme.line },
              border: { display: false },
              ticks: { maxRotation: 0, callback: (v) => (log && ![1, 10, 100, 1000, 10000].includes(v) ? '' : fmtTick(v)) },
            },
            y: { grid: { display: false }, border: { display: false }, ticks: { color: theme.text, font: { size: 13, weight: 600 } } },
          },
          plugins: {
            legend: { display: false },
            valueLabels: {
              color: theme.text,
              labels: rows.map((r) => `${fmtMs(r.median)}${r.speedup ? `  ·  ${fmtSpeed(r.speedup)}` : ''}`),
            },
            tooltip: {
              ...tooltipBase(theme),
              callbacks: {
                title: (items) => rows[items[0].dataIndex].label,
                label: (item) => {
                  const r = rows[item.dataIndex];
                  const out = [`Median per diagram: ${fmtMs(r.median)}`, `First render: ${fmtMs(r.startup_ms)}`, `Drew ${r.ok} of ${r.total} diagrams`];
                  if (r.speedup) out.push(`${fmtSpeed(r.speedup)} than ${r.reference.label}`.replace('about the same than', 'about the same as'));
                  return out;
                },
              },
            },
          },
        },
      };
    },
    [rows, log],
  );
  return <canvas ref={ref} />;
}

function PerDiagramChart({ data, log }) {
  const { renderers } = data.meta;
  const ref = useChart(
    (theme) => ({
      type: 'line',
      data: {
        labels: data.samples.map((s) => s.title),
        datasets: renderers.map((r) => ({
          label: r.label,
          data: data.samples.map((s) => (s.results[r.id] && s.results[r.id].status === 'ok' ? s.results[r.id].time_ms : null)),
          borderColor: theme.color(r.id),
          backgroundColor: theme.color(r.id),
          borderWidth: 1.75,
          pointRadius: 2.5,
          pointHoverRadius: 5,
          tension: 0,
          spanGaps: false,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: 'index', intersect: false },
        onClick: (_e, _els, chart) => {
          const active = chart.getActiveElements();
          if (!active.length) return;
          const id = data.samples[active[0].index].id;
          window.history.replaceState(null, '', `#${id}`);
          document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
        },
        scales: {
          x: { grid: { color: theme.line }, border: { display: false }, ticks: { autoSkip: false, maxRotation: 70, minRotation: 70, font: { size: 10 } } },
          y: {
            type: log ? 'logarithmic' : 'linear',
            min: log ? undefined : 0,
            grid: { color: theme.line },
            border: { display: false },
            ticks: { callback: (v) => (log && ![1, 10, 100, 1000, 10000].includes(v) ? '' : fmtTick(v)) },
          },
        },
        plugins: {
          legend: { position: 'top', align: 'start', labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10, color: theme.text, font: { size: 13 } } },
          tooltip: {
            ...tooltipBase(theme),
            itemSort: (a, b) => (b.raw ?? -1) - (a.raw ?? -1),
            callbacks: { label: (item) => ` ${item.dataset.label}: ${item.raw == null ? 'no image' : fmtMs(item.raw)}` },
          },
        },
      },
    }),
    [data, log],
  );
  return <canvas ref={ref} />;
}

// ---------------------------------------------------------------------------------------------------------------
// More measurements. They come from run.py too, and every one of them is left out when its data is missing (a
// benchmark file made by an older run.py, or a machine that could not measure it).

const median = (values) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

const barOptions = (theme, { right = 170, scale = {} } = {}) => ({
  indexAxis: 'y',
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  layout: { padding: { right } },
  scales: {
    x: { grid: { color: theme.line }, border: { display: false }, ticks: { maxRotation: 0 }, ...scale },
    y: { grid: { display: false }, border: { display: false }, ticks: { color: theme.text, font: { size: 13, weight: 600 } } },
  },
});

function FootprintChart({ rows, footprint }) {
  const ref = useChart(
    (theme) => {
      const values = rows.map((r) => footprint[r.id].bytes);
      return {
        type: 'bar',
        data: {
          labels: rows.map(chartLabel),
          datasets: [{ data: values, backgroundColor: rows.map((r) => theme.color(r.id)), borderRadius: 3, barThickness: 26 }],
        },
        plugins: [valueLabels],
        options: {
          ...barOptions(theme, { right: 90, scale: { min: 0, ticks: { maxRotation: 0, callback: (v) => fmtBytes(v) } } }),
          plugins: {
            legend: { display: false },
            valueLabels: { color: theme.text, labels: values.map(fmtBytes) },
            tooltip: {
              ...tooltipBase(theme),
              callbacks: {
                title: (items) => rows[items[0].dataIndex].label,
                label: (item) => {
                  const info = footprint[rows[item.dataIndex].id];
                  const out = info.parts.map((part) => `${part.name}: ${fmtBytes(part.bytes)}`);
                  if (info.js_bytes) out.push(`JavaScript one render loads: ${fmtBytes(info.js_bytes)}`);
                  return out;
                },
              },
            },
          },
        },
      };
    },
    [rows, footprint],
  );
  return <canvas ref={ref} />;
}

function FirstRenderChart({ rows, log }) {
  const ref = useChart(
    (theme) => {
      const first = rows.map((r) => r.startup_ms || 0);
      const warm = rows.map((r) => r.median || 0);
      const positive = [...first, ...warm].filter((v) => v > 0);
      const lo = Math.min(...positive);
      const hi = Math.max(...positive);
      return {
        type: 'bar',
        data: {
          labels: rows.map(chartLabel),
          datasets: [
            { label: 'First render', data: first, backgroundColor: theme.muted, borderRadius: 3, barThickness: 14 },
            { label: 'Median after that', data: warm, backgroundColor: cssVar('--ifm-color-primary'), borderRadius: 3, barThickness: 14 },
          ],
        },
        options: {
          ...barOptions(theme, {
            right: 20,
            scale: {
              type: log ? 'logarithmic' : 'linear',
              min: log ? Math.pow(10, Math.floor(Math.log10(lo))) : 0,
              max: log ? Math.pow(10, Math.ceil(Math.log10(hi))) : undefined,
              ticks: { maxRotation: 0, callback: (v) => (log && ![1, 10, 100, 1000, 10000].includes(v) ? '' : fmtTick(v)) },
            },
          }),
          plugins: {
            legend: { display: true, position: 'bottom', labels: { color: theme.text, boxWidth: 12 } },
            tooltip: { ...tooltipBase(theme), callbacks: { label: (item) => `${item.dataset.label}: ${fmtMs(item.parsed.x)}` } },
          },
        },
      };
    },
    [rows, log],
  );
  return <canvas ref={ref} />;
}

function ScalingChart({ scaling }) {
  const ref = useChart(
    (theme) => {
      const counts = scaling.series[0].points.map((p) => p.workers);
      return {
        type: 'line',
        data: {
          labels: counts.map(String),
          datasets: [
            ...scaling.series.map((s) => ({
              label: s.label,
              data: s.points.map((p) => p.speedup),
              borderColor: theme.color(s.id),
              backgroundColor: theme.color(s.id),
              borderWidth: 3,
              pointRadius: 5,
              tension: 0,
            })),
            { label: 'Perfect scaling', data: counts, borderColor: theme.muted, borderDash: [6, 6], borderWidth: 1.5, pointRadius: 0 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { title: { display: true, text: 'Worker processes', color: theme.muted }, grid: { display: false }, border: { display: false } },
            y: { min: 0, title: { display: true, text: 'Faster than one worker', color: theme.muted }, grid: { color: theme.line }, border: { display: false }, ticks: { callback: (v) => `${v}×` } },
          },
          plugins: {
            legend: { position: 'bottom', labels: { color: theme.text, boxWidth: 12 } },
            tooltip: {
              ...tooltipBase(theme),
              callbacks: {
                label: (item) => {
                  const s = scaling.series[item.datasetIndex];
                  if (!s) return `${item.dataset.label}: ${item.parsed.y}×`;
                  const point = s.points[item.dataIndex];
                  return `${s.label}: ${point.speedup}× (${fmtMs(point.ms)} for ${scaling.items} diagrams)`;
                },
              },
            },
          },
        },
      };
    },
    [scaling],
  );
  return <canvas ref={ref} />;
}

function SizeChart({ data, renderers, log }) {
  const ref = useChart(
    (theme) => {
      // The diagrams from the shortest Mermaid text to the longest, one line for every renderer.
      const sized = data.samples.filter((s) => s.chars).sort((a, b) => a.chars - b.chars);
      return {
        type: 'line',
        data: {
          labels: sized.map((s) => String(s.chars)),
          datasets: renderers.map((r) => ({
            label: chartLabel(r),
            data: sized.map((s) => (s.results[r.id] && s.results[r.id].status === 'ok' ? s.results[r.id].time_ms : null)),
            borderColor: theme.color(r.id),
            backgroundColor: theme.color(r.id),
            borderWidth: 1.75,
            pointRadius: 2.5,
            pointHoverRadius: 5,
            tension: 0,
            spanGaps: true,
          })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          scales: {
            x: {
              title: { display: true, text: 'Characters in the Mermaid text, from the shortest diagram to the longest', color: theme.muted },
              grid: { display: false },
              border: { display: false },
              ticks: { autoSkip: true, maxTicksLimit: 14, maxRotation: 0 },
            },
            y: {
              type: log ? 'logarithmic' : 'linear',
              min: log ? undefined : 0,
              title: { display: true, text: 'Time per diagram', color: theme.muted },
              grid: { color: theme.line },
              border: { display: false },
              ticks: { callback: (v) => (log && ![1, 10, 100, 1000, 10000].includes(v) ? '' : fmtTick(v)) },
            },
          },
          plugins: {
            legend: { position: 'bottom', labels: { color: theme.text, boxWidth: 12 } },
            tooltip: {
              ...tooltipBase(theme),
              itemSort: (a, b) => (b.raw ?? -1) - (a.raw ?? -1),
              callbacks: {
                title: (items) => {
                  const s = sized[items[0].dataIndex];
                  return s ? `${s.title}, ${s.chars} characters` : '';
                },
                label: (item) => ` ${item.dataset.label}: ${item.raw == null ? 'no image' : fmtMs(item.raw)}`,
              },
            },
          },
        },
      };
    },
    [data, renderers, log],
  );
  return <canvas ref={ref} />;
}

// The labels row of every renderer that has the data: the share of the reference's words that its picture has.
export default function BenchCharts({ data, rows, log, onLogChange }) {
  const ref = rows[0].reference;
  const footprintRows = data.footprint ? rows.filter((r) => data.footprint[r.id]) : [];
  const hasSizes = data.samples.some((s) => s.chars);
  return (
    <section aria-labelledby="charts">
      <div className={styles.head}>
        <h2 id="charts">Results at a glance</h2>
        <div className={styles.segment} role="group" aria-label="Time axis">
          <button type="button" aria-pressed={log} onClick={() => onLogChange(true)}>Log scale</button>
          <button type="button" aria-pressed={!log} onClick={() => onLogChange(false)}>Linear</button>
        </div>
      </div>

      <div className={styles.grid}>
        <figure className={styles.figure}>
          <figcaption>
            <strong>Median time per diagram</strong>
            <span>Shorter is faster. Compared with {ref.label}. Core Mermaid diagrams only; ELK and ZenUML are in the table below.</span>
          </figcaption>
          <div className={styles.canvasWrap} style={{ height: 36 + rows.length * 48 }} role="img"
            aria-label={`Median time per diagram: ${rows.map((r) => `${r.label} ${fmtMs(r.median)}`).join(', ')}`}>
            <MedianChart rows={rows} log={log} />
          </div>
        </figure>
      </div>

      <figure className={styles.figure}>
        <figcaption>
          <strong>Time for each diagram</strong>
          <span>Click a point to jump to that diagram in the gallery below.</span>
        </figcaption>
        <div className={styles.scroll}>
          <div className={styles.wide} role="img" aria-label="Time in milliseconds for each of the diagrams, one line per renderer">
            <PerDiagramChart data={data} log={log} />
          </div>
        </div>
      </figure>

      <h3 id="more">More measurements</h3>
      <div className={styles.grid}>
        {footprintRows.length > 0 && (
          <figure className={styles.figure}>
            <figcaption>
              <strong>Download size</strong>
              <span>What installing each renderer downloads, compressed. mermaidx: the wheel built from this commit and the wheels of its dependencies, measured with pip-size. mmdc: the npm tarballs of mermaid-cli and everything it installed, plus the headless Chrome that puppeteer fetches. Shorter is lighter.</span>
            </figcaption>
            <div className={styles.canvasWrap} style={{ height: 36 + footprintRows.length * 48 }} role="img"
              aria-label={`Download size: ${footprintRows.map((r) => `${r.label} ${fmtBytes(data.footprint[r.id].bytes)}`).join(', ')}`}>
              <FootprintChart rows={footprintRows} footprint={data.footprint} />
            </div>
          </figure>
        )}
        <figure className={styles.figure}>
          <figcaption>
            <strong>First render and the ones after it</strong>
            <span>The first render of mermaidx starts its engine; later renders are warm. Shorter is faster.</span>
          </figcaption>
          <div className={styles.canvasWrap} style={{ height: 70 + rows.length * 58 }} role="img"
            aria-label="Time of the first render and the median of the next ones, for each renderer">
            <FirstRenderChart rows={rows} log={log} />
          </div>
        </figure>
        {data.scaling && data.scaling.series.length > 0 && (
          <figure className={styles.figure}>
            <figcaption>
              <strong>Rendering many diagrams in parallel</strong>
              <span>
                <code>render_many()</code> with more worker {data.scaling.executor === 'thread' ? 'threads' : 'processes'}: {data.scaling.items} diagrams from text to SVG, on {data.scaling.cores}{' '}
                {data.scaling.cores === 1 ? 'core' : 'cores'}. Higher is better; it cannot pass the number of cores.
              </span>
            </figcaption>
            <div className={styles.canvasWrap} style={{ height: 300 }} role="img"
              aria-label={`Speed-up of render_many with more workers: ${data.scaling.series.map((s) => `${s.label} ${s.points.map((p) => `${p.workers} workers ${p.speedup} times`).join(', ')}`).join('; ')}`}>
              <ScalingChart scaling={data.scaling} />
            </div>
          </figure>
        )}
      </div>

      {hasSizes && (
        <figure className={styles.figure}>
          <figcaption>
            <strong>Time against the size of the diagram</strong>
            <span>The diagrams from the shortest Mermaid text to the longest, one line for every renderer. The longer the text, the more there is to lay out. Characters are a rough size.</span>
          </figcaption>
          <div className={styles.canvasWrap} style={{ height: 360 }} role="img" aria-label="Time per diagram, with the diagrams ordered by the number of characters of their Mermaid text, one line per renderer">
            <SizeChart data={data} renderers={rows} log={log} />
          </div>
        </figure>
      )}

      <details className={styles.numbers}>
        <summary>Show the numbers</summary>
        <div className={styles.numbersScroll}>
          <table>
            <thead>
              <tr><th>Renderer</th><th>Median per diagram</th><th>Compared with {ref.label}</th><th>Produced an image</th><th>First render</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <th scope="row">{r.label}</th>
                  <td>{fmtMs(r.median)}</td>
                  <td>{r.speedup ? fmtSpeed(r.speedup) : r.id === ref.id ? 'reference' : '–'}</td>
                  <td>{r.ok} of {r.total}</td>
                  <td>{fmtMs(r.startup_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className={styles.note}>
        Medians over the diagrams each renderer handled. mermaidx runs in one Python process and <code>mmdc</code> is
        started for every diagram, so read the comparison as "per diagram in a script".{' '}
        <Link to="/docs/benchmarks-method">How the benchmarks work</Link>.
      </p>
    </section>
  );
}
