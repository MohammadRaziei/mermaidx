import React, { useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';
import Link from '@docusaurus/Link';
import { useColorMode } from '@docusaurus/theme-common';
import { COLOR_VARS, chartLabel, fmtMs, fmtTick, fmtTimes } from './bench-utils';
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

// Builds a chart from buildConfig(theme) and rebuilds it when the colour mode or the inputs change.
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
              labels: rows.map((r) => `${fmtMs(r.median)}${r.speedup ? `  ·  ${fmtTimes(r.speedup)} faster` : ''}`),
            },
            tooltip: {
              ...tooltipBase(theme),
              callbacks: {
                title: (items) => rows[items[0].dataIndex].label,
                label: (item) => {
                  const r = rows[item.dataIndex];
                  const out = [`Median per diagram: ${fmtMs(r.median)}`, `First render: ${fmtMs(r.startup_ms)}`, `Drew ${r.ok} of ${r.total} diagrams`];
                  if (r.speedup) out.push(`${fmtTimes(r.speedup)} faster than ${r.reference.label}`);
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

function CoverageChart({ rows }) {
  const ref = useChart(
    (theme) => ({
      type: 'bar',
      data: {
        labels: rows.map(chartLabel),
        datasets: [
          { label: 'Produced an image', data: rows.map((r) => r.ok), backgroundColor: rows.map((r) => theme.color(r.id)), barThickness: 26 },
          { label: 'No image', data: rows.map((r) => r.total - r.ok), backgroundColor: theme.line, barThickness: 26 },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: { stacked: true, max: rows[0].total, grid: { color: theme.line }, border: { display: false }, ticks: { precision: 0, maxRotation: 0 } },
          y: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { color: theme.text, font: { size: 13, weight: 600 } } },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            ...tooltipBase(theme),
            callbacks: { label: (item) => `${item.dataset.label}: ${item.raw} of ${rows[item.dataIndex].total}` },
          },
        },
      },
    }),
    [rows],
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

export default function BenchCharts({ data, rows, log, onLogChange }) {
  const ref = rows[0].reference;
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
            <span>Shorter is faster. Compared with {ref.label}.</span>
          </figcaption>
          <div className={styles.canvasWrap} style={{ height: 36 + rows.length * 48 }} role="img"
            aria-label={`Median time per diagram: ${rows.map((r) => `${r.label} ${fmtMs(r.median)}`).join(', ')}`}>
            <MedianChart rows={rows} log={log} />
          </div>
        </figure>
        <figure className={styles.figure}>
          <figcaption>
            <strong>Diagrams that produced an image</strong>
            <span>Out of {rows[0].total}. An image is not always a correct one: check the gallery.</span>
          </figcaption>
          <div className={styles.canvasWrap} style={{ height: 36 + rows.length * 48 }} role="img"
            aria-label={`Diagrams that produced an image: ${rows.map((r) => `${r.label} ${r.ok} of ${r.total}`).join(', ')}`}>
            <CoverageChart rows={rows} />
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

      <details className={styles.numbers}>
        <summary>Show the numbers</summary>
        <div className={styles.numbersScroll}>
          <table>
            <thead>
              <tr><th>Renderer</th><th>Median per diagram</th><th>Faster than {ref.label}</th><th>Produced an image</th><th>First render</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <th scope="row">{r.label}</th>
                  <td>{fmtMs(r.median)}</td>
                  <td>{r.speedup ? fmtTimes(r.speedup) : r.id === ref.id ? 'reference' : '–'}</td>
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
