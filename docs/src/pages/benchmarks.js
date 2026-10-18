import React, { useEffect, useMemo, useRef, useState } from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import BenchCharts from '../components/BenchCharts';
import { colorOf, fmtMs } from '../components/bench-utils';
import styles from './benchmarks.module.css';

function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function summarize(data) {
  const { renderers } = data.meta;
  const reference = renderers.find((r) => r.id === 'mmdc') || renderers[0];
  return renderers.map((r) => {
    const times = [];
    const ratios = [];
    let ok = 0;
    for (const s of data.samples) {
      const res = s.results[r.id];
      if (res && res.status === 'ok') {
        ok += 1;
        times.push(res.time_ms);
        const ref = s.results[reference.id];
        if (ref && ref.status === 'ok' && r.id !== reference.id) ratios.push(ref.time_ms / res.time_ms);
      }
    }
    return {
      ...r,
      ok,
      total: data.samples.length,
      median: median(times),
      speedup: r.id === reference.id ? null : median(ratios),
      reference,
    };
  });
}

function Cell({ renderer, res, fastest, onOpen, sample }) {
  const base = useBaseUrl('/benchmarks/');
  if (!res || res.status !== 'ok') {
    return (
      <div className={styles.cell}>
        <div className={styles.failed} title={res && res.error ? res.error : 'No image was produced'}>
          Not supported
        </div>
        <div className={styles.cellLabel}>
          <span className={styles.swatch} style={{ background: colorOf(renderer.id) }} aria-hidden="true" />
          {renderer.label}
        </div>
        <div className={styles.cellMeta}>{res && res.error ? res.error.slice(0, 90) : 'no result'}</div>
      </div>
    );
  }
  return (
    <div className={styles.cell}>
      <button
        type="button"
        className={styles.thumb}
        onClick={() => onOpen({ sample, renderer, res, src: base + res.png })}
        aria-label={`Enlarge ${sample.title}, rendered by ${renderer.label}`}>
        <img src={base + res.png} alt={`${sample.title}, rendered by ${renderer.label}`} loading="lazy" width={res.width} height={res.height} />
      </button>
      <div className={styles.cellLabel}>
        <span className={styles.swatch} style={{ background: colorOf(renderer.id) }} aria-hidden="true" />
        {renderer.label}
      </div>
      <div className={styles.cellMeta}>
        <span className={fastest ? styles.fastest : undefined}>{fmtMs(res.time_ms)}</span>
        {res.width ? ` · ${res.width}×${res.height}` : ''}
      </div>
    </div>
  );
}

function Lightbox({ item, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (el && item && !el.open) el.showModal();
    if (el && !item && el.open) el.close();
  }, [item]);
  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}>
      {item && (
        <div className={styles.dialogBody}>
          <div className={styles.dialogHead}>
            <strong>{item.sample.title}</strong>
            <span>
              {item.renderer.label} · {fmtMs(item.res.time_ms)}
            </span>
            <a href={item.src} download>Download PNG</a>
            <button type="button" onClick={onClose}>Close</button>
          </div>
          <div className={styles.dialogImage}>
            <img src={item.src} alt={`${item.sample.title}, rendered by ${item.renderer.label}`} />
          </div>
        </div>
      )}
    </dialog>
  );
}

function Gallery({ data }) {
  const { renderers } = data.meta;
  const reference = renderers[0];
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('name');
  const [onlyFailures, setOnlyFailures] = useState(false);
  const [open, setOpen] = useState(null);

  const hasFailure = (s) => renderers.some((r) => !s.results[r.id] || s.results[r.id].status !== 'ok');

  const samples = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = data.samples.filter(
      (s) => (!q || `${s.id} ${s.type}`.toLowerCase().includes(q)) && (!onlyFailures || hasFailure(s)),
    );
    const refTime = (s) => {
      const res = s.results[reference.id];
      return res && res.status === 'ok' ? res.time_ms : -1;
    };
    if (sort === 'slowest') list = [...list].sort((a, b) => refTime(b) - refTime(a));
    if (sort === 'failures') list = [...list].sort((a, b) => Number(hasFailure(b)) - Number(hasFailure(a)));
    return list;
  }, [data, query, sort, onlyFailures]);

  // Jump to a sample linked as /benchmarks#31_venn once the list has rendered.
  useEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (id) document.getElementById(id)?.scrollIntoView();
  }, [data]);

  return (
    <section aria-labelledby="gallery">
      <h2 id="gallery">Every diagram, every renderer</h2>
      <div className={styles.controls}>
        <label>
          Search
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="For example: sankey" />
        </label>
        <label>
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="name">Name</option>
            <option value="slowest">Slowest first ({reference.label})</option>
            <option value="failures">Failures first</option>
          </select>
        </label>
        <label className={styles.check}>
          <input type="checkbox" checked={onlyFailures} onChange={(e) => setOnlyFailures(e.target.checked)} />
          Only diagrams some renderer could not draw
        </label>
        <span className={styles.count} aria-live="polite">{samples.length} of {data.samples.length} diagrams</span>
      </div>

      {samples.length === 0 && <p>No diagram matches. Clear the search to see all of them.</p>}

      <ol className={styles.list}>
        {samples.map((s) => {
          const times = renderers.map((r) => (s.results[r.id] && s.results[r.id].status === 'ok' ? s.results[r.id].time_ms : Infinity));
          const best = Math.min(...times);
          return (
            <li key={s.id} id={s.id} className={styles.row}>
              <div className={styles.rowHead}>
                <h3>
                  {s.title}
                  <a className="hash-link" href={`#${s.id}`} aria-label={`Link to ${s.title}`} />
                </h3>
                <code>{s.type}</code>
              </div>
              <div className={styles.cells} style={{ '--cols': renderers.length }}>
                {renderers.map((r) => (
                  <Cell key={r.id} renderer={r} res={s.results[r.id]} sample={s} fastest={s.results[r.id] && s.results[r.id].time_ms === best} onOpen={setOpen} />
                ))}
              </div>
            </li>
          );
        })}
      </ol>
      <Lightbox item={open} onClose={() => setOpen(null)} />
    </section>
  );
}

function Meta({ meta }) {
  const when = new Date(meta.generated_at);
  const commit = meta.commit ? meta.commit.slice(0, 7) : null;
  return (
    <footer className={styles.meta}>
      <h2>Where these numbers come from</h2>
      <dl>
        <dt>Generated</dt>
        <dd>{when.toISOString().slice(0, 16).replace('T', ' ')} UTC{commit ? ` from commit ${commit}` : ''}</dd>
        <dt>Machine</dt>
        <dd>{meta.machine.cpu}, {meta.machine.cores} cores, {meta.machine.os}</dd>
        <dt>Software</dt>
        <dd>
          mermaidx {meta.versions.mermaidx}
          {meta.versions.novasvg ? `, novasvg ${meta.versions.novasvg}` : ''}
          {meta.versions.mmdc ? `, mmdc ${meta.versions.mmdc}` : ''}, Python {meta.machine.python}
          {meta.machine.node ? `, Node.js ${meta.machine.node}` : ''}
        </dd>
        <dt>Runs</dt>
        <dd>
          Median of {meta.repeats} runs per diagram for mermaidx and {meta.mmdc_repeats} for mmdc. White background.
        </dd>
      </dl>
      <p><a href={useBaseUrl('/benchmarks/results.json')}>Download the raw results (JSON)</a></p>
    </footer>
  );
}

export default function Benchmarks() {
  const url = useBaseUrl('/benchmarks/results.json');
  const [state, setState] = useState({ status: 'loading' });
  const [log, setLog] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => !cancelled && setState({ status: 'ok', data }))
      .catch(() => !cancelled && setState({ status: 'missing' }));
    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <Layout title="Benchmarks" description="The same diagrams rendered by mermaid-cli and every mermaidx backend, with the time each one took.">
      <main className={styles.page}>
        <h1>Benchmarks</h1>
        <p className={styles.intro}>
          The same {state.status === 'ok' ? state.data.samples.length : 43} Mermaid diagrams, rendered by the official mermaid-cli and by every
          mermaidx backend. Compare the pictures, and the time each renderer needed to produce them.
        </p>
        {state.status === 'loading' && <p>Loading results…</p>}
        {state.status === 'missing' && (
          <div className="admonition admonition-caution alert alert--warning">
            <p>
              There are no results on this build yet. They are generated by the benchmark job in CI. To produce them
              locally, run <code>python benchmarks/run.py</code> and rebuild the site.{' '}
              <Link to="/docs/benchmarks-method">How the benchmarks work</Link>.
            </p>
          </div>
        )}
        {state.status === 'ok' && (
          <>
            {state.data.meta.skipped && state.data.meta.skipped.length > 0 && (
              <div className="alert alert--warning" role="status">
                <strong>Not measured in this run:</strong>{' '}
                {state.data.meta.skipped.map((r) => `${r.label} (${r.error})`).join('; ')}
              </div>
            )}
            <BenchCharts data={state.data} rows={summarize(state.data)} log={log} onLogChange={setLog} />
            <Gallery data={state.data} />
            <Meta meta={state.data.meta} />
          </>
        )}
      </main>
    </Layout>
  );
}
