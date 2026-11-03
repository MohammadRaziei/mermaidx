import React, { useEffect, useMemo, useRef, useState } from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import BenchCharts from '../components/BenchCharts';
import SupportMatrix, { FEATURES, ignoresElk } from '../components/SupportMatrix';
import { colorOf, fmtMs } from '../components/bench-utils';
import styles from './benchmarks.module.css';

// One broken section (a chart that does not like some value in results.json) must not take the whole page down. The
// message and the stack are shown, so a report of the problem says where it happened.
class Section extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className={styles.sectionError} role="alert">
        <strong>{this.props.name} could not be drawn.</strong> {String(error && error.message)}
        <details>
          <summary>Details</summary>
          <pre>{String((error && error.stack) || error)}</pre>
        </details>
      </div>
    );
  }
}

function Charts({ data, log, onLogChange }) {
  return <BenchCharts data={data} rows={summarize(data)} log={log} onLogChange={onLogChange} />;
}

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
        // The times and the speed-up are for the core diagrams: ELK and ZenUML have their own row in the table below.
        if (s.feature) continue;
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

function SourceDownload({ sample }) {
  const base = useBaseUrl('/benchmarks/');
  const href = base + (sample.source || `mmd/${sample.id}.mmd`);
  return (
    <div className={styles.rowFoot}>
      <a className={styles.download} href={href} download={`${sample.id}.mmd`} aria-label={`Download the Mermaid source of ${sample.title}`}>
        Download .mmd
      </a>
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
  const [filter, setFilter] = useState('all');
  const [open, setOpen] = useState(null);

  const hasFeature = (name) => data.samples.some((s) => s.feature === name);
  const hasFailure = (s) => renderers.some((r) => !s.results[r.id] || s.results[r.id].status !== 'ok');

  const samples = useMemo(() => {
    const q = query.trim().toLowerCase();
    const passesFilter = (s) => {
      if (filter === 'all') return true;
      if (filter === 'complete') return !hasFailure(s);
      if (filter === 'incomplete') return hasFailure(s);
      return s.feature === filter; // 'elk' or 'zenuml'
    };
    let list = data.samples.filter((s) => (!q || `${s.id} ${s.type} ${s.feature || ''}`.toLowerCase().includes(q)) && passesFilter(s));
    const refTime = (s) => {
      const res = s.results[reference.id];
      return res && res.status === 'ok' ? res.time_ms : -1;
    };
    if (sort === 'slowest') list = [...list].sort((a, b) => refTime(b) - refTime(a));
    if (sort === 'failures') list = [...list].sort((a, b) => Number(hasFailure(b)) - Number(hasFailure(a)));
    return list;
  }, [data, query, sort, filter]);

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
        <label>
          Filter
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All diagrams</option>
            <option value="complete">Drawn by every renderer</option>
            <option value="incomplete">Not supported by at least one renderer</option>
            {hasFeature('elk') && <option value="elk">ELK layout only</option>}
            {hasFeature('zenuml') && <option value="zenuml">ZenUML only</option>}
          </select>
        </label>
        <span className={styles.count} aria-live="polite">{samples.length} of {data.samples.length} diagrams</span>
      </div>

      {samples.length === 0 && <p>No diagram matches. Clear the search to see all of them.</p>}

      <ol className={styles.list}>
        {samples.map((s) => {
          const times = renderers.map((r) => (s.results[r.id] && s.results[r.id].status === 'ok' ? s.results[r.id].time_ms : Infinity));
          const best = Math.min(...times);
          const number = (s.id.match(/^\d+/) || [''])[0];
          return (
            <li key={s.id} id={s.id} className={styles.row}>
              <div className={styles.rowHead}>
                <h3>
                  {number && <span className={styles.num}>{number}</span>}
                  {s.title}
                  <a className="hash-link" href={`#${s.id}`} aria-label={`Link to ${s.title}`} />
                </h3>
                <code>{s.type}</code>
                {s.feature && FEATURES[s.feature] && <span className={styles.badge}>{FEATURES[s.feature].short}</span>}
              </div>
              {s.feature === 'elk' && renderers.some((r) => ignoresElk(r.id) && s.results[r.id] && s.results[r.id].status === 'ok') && (
                <p className={styles.rowNote}>
                  js:pele has no ELK layout: its picture is drawn with its own layout, so it is not an ELK picture.
                </p>
              )}
              <div className={styles.cells} style={{ '--cols': renderers.length }}>
                {renderers.map((r) => (
                  <Cell key={r.id} renderer={r} res={s.results[r.id]} sample={s} fastest={s.results[r.id] && s.results[r.id].time_ms === best} onOpen={setOpen} />
                ))}
              </div>
              <SourceDownload sample={s} />
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
          Median of {meta.repeats} runs per diagram for mermaidx and {meta.mmdc_repeats} for mmdc. White background. The
          medians and speed-ups at the top are for the diagrams of core Mermaid; ELK and ZenUML are in their own rows.
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
          The same {state.status === 'ok' ? state.data.samples.length : 49} Mermaid diagrams, rendered by the official mermaid-cli and by every
          mermaidx backend, including the ELK layout and ZenUML, which mermaid.js does not draw by itself. Compare the pictures,
          the time each renderer needed to produce them, and which diagrams a renderer cannot draw at all.
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
            <Section name="The charts">
              <Charts data={state.data} log={log} onLogChange={setLog} />
            </Section>
            <Section name="The table of what each renderer can draw">
              <SupportMatrix data={state.data} />
            </Section>
            <Section name="The gallery">
              <Gallery data={state.data} />
            </Section>
            <Section name="The details of this run">
              <Meta meta={state.data.meta} />
            </Section>
          </>
        )}
      </main>
    </Layout>
  );
}
