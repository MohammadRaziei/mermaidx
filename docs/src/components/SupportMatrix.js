import React, { useMemo } from 'react';
import Link from '@docusaurus/Link';
import { colorOf, fmtMs } from './bench-utils';
import styles from './SupportMatrix.module.css';

// What mermaid.js itself does not draw. Samples that use these are listed apart from the core diagram types.
export const FEATURES = {
  elk: { label: 'Flowchart, ELK layout', short: 'ELK layout' },
  zenuml: { label: 'ZenUML', short: 'ZenUML' },
};

// pele has no ELK layout: it ignores the request and draws the flowchart with its own layout.
export const ignoresElk = (rendererId) => rendererId.includes('pele');

const isOk = (res) => Boolean(res && res.status === 'ok');

function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// One group per diagram type, plus one per feature (ELK, ZenUML).
function groupSamples(samples) {
  const groups = new Map();
  for (const s of samples) {
    const type = s.type === 'graph' ? 'flowchart' : s.type; // `graph` is the older keyword for the same diagram
    const key = s.feature ? `feature:${s.feature}` : `type:${type}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        feature: s.feature || null,
        label: s.feature ? FEATURES[s.feature]?.label || s.feature : type,
        samples: [],
      });
    }
    groups.get(key).samples.push(s);
  }
  // Array.from, not [...map.values()]: the docs build compiles a spread to [].concat(), which does not spread a Map iterator.
  const all = Array.from(groups.values());
  const byLabel = (a, b) => a.label.localeCompare(b.label);
  return {
    core: all.filter((g) => !g.feature).sort(byLabel),
    extra: all.filter((g) => g.feature).sort(byLabel),
  };
}

function cellFor(group, renderer) {
  const results = group.samples.map((s) => s.results[renderer.id]);
  const ok = results.filter(isOk).length;
  const total = results.length;
  const firstError = results.find((r) => !isOk(r) && r && r.error);
  const time = median(results.filter(isOk).map((r) => r.time_ms));
  return { ok, total, error: firstError ? firstError.error : null, time };
}

function Cell({ group, renderer }) {
  const { ok, total, error, time } = cellFor(group, renderer);
  if (ok === 0) {
    return (
      <td>
        <span className={styles.no} title={error || 'No image was produced'}>Not supported</span>
      </td>
    );
  }
  if (group.feature === 'elk' && ignoresElk(renderer.id) && ok === total) {
    return (
      <td>
        <span className={styles.own} title="This renderer has no ELK layout. It draws the diagram with its own layout, so the picture is not an ELK picture.">
          Own layout
        </span>
        <small> {fmtMs(time)}</small>
      </td>
    );
  }
  if (ok < total) {
    return (
      <td>
        <span className={styles.part} title={error || undefined}>{ok} of {total}</span>
        <small> {fmtMs(time)}</small>
      </td>
    );
  }
  return (
    <td>
      <span className={styles.yes}>{total > 1 ? `All ${total}` : 'Drawn'}</span>
      <small> {fmtMs(time)}</small>
    </td>
  );
}

// Every error message of a renderer, with the diagrams it happened on.
function collectFailures(data) {
  return data.meta.renderers
    .map((renderer) => {
      const byMessage = new Map();
      for (const s of data.samples) {
        const res = s.results[renderer.id];
        if (isOk(res)) continue;
        const message = (res && res.error) || 'No image was produced';
        if (!byMessage.has(message)) byMessage.set(message, []);
        byMessage.get(message).push(s);
      }
      const failed = Array.from(byMessage.values()).reduce((n, list) => n + list.length, 0);
      return { renderer, failed, messages: Array.from(byMessage.entries()).sort((a, b) => b[1].length - a[1].length) };
    })
    .filter((entry) => entry.failed > 0);
}

export default function SupportMatrix({ data }) {
  const { renderers } = data.meta;
  const { core, extra } = useMemo(() => groupSamples(data.samples), [data]);
  const failures = useMemo(() => collectFailures(data), [data]);
  const columns = renderers.length + 1;

  return (
    <section className={styles.section} aria-labelledby="support">
      <h2 id="support">What each renderer can draw</h2>
      <p className={styles.lead}>
        One row per kind of diagram. A renderer that cannot draw one is not left out of the comparison: it shows up here as
        “Not supported”, with the error it gave. Times are the median of the diagrams in the row.
      </p>

      <div className={styles.scroll}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col" style={{ textAlign: 'left' }}>Diagram</th>
              {renderers.map((r) => (
                <th scope="col" key={r.id}>
                  <span className={styles.swatch} style={{ background: colorOf(r.id) }} aria-hidden="true" />
                  {r.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {core.map((g) => (
              <tr key={g.key}>
                <th scope="row">
                  <code>{g.label}</code>
                  {g.samples.length > 1 && <small>{g.samples.length} diagrams</small>}
                </th>
                {renderers.map((r) => (
                  <Cell key={r.id} group={g} renderer={r} />
                ))}
              </tr>
            ))}
            {extra.length > 0 && (
              <tr className={styles.groupRow}>
                <th colSpan={columns} scope="colgroup">Beyond mermaid.js: ELK layout and ZenUML</th>
              </tr>
            )}
            {extra.map((g) => (
              <tr key={g.key}>
                <th scope="row">
                  {g.label}
                  <small>{g.samples.length} {g.samples.length === 1 ? 'diagram' : 'diagrams'}</small>
                </th>
                {renderers.map((r) => (
                  <Cell key={r.id} group={g} renderer={r} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {extra.length > 0 && (
        <p className={styles.note}>
          mermaid.js does not draw ELK layouts or ZenUML by itself. mermaidx adds them: it loads the ELK layout (2.4 MB of
          JavaScript) only for a diagram that asks for it, and draws a ZenUML diagram with the renderer of @zenuml/core, without
          a browser. That is why these diagrams take longer than the same flowchart with the default layout. “Own layout” means
          the renderer drew the diagram but ignored the ELK request. See <Link to="/docs/backends">the backends</Link> and{' '}
          <Link to="/docs/benchmarks-method">how the benchmarks work</Link>.
        </p>
      )}

      {failures.length > 0 && (
        <div className={styles.failures}>
          <h3 id="failures">Why a diagram was not drawn</h3>
          {failures.map(({ renderer, failed, messages }) => (
            <details key={renderer.id}>
              <summary>
                <span className={styles.swatch} style={{ background: colorOf(renderer.id) }} aria-hidden="true" />
                {renderer.label}: {failed} {failed === 1 ? 'diagram' : 'diagrams'} not drawn
              </summary>
              <ul>
                {messages.map(([message, list]) => (
                  <li key={message}>
                    <code>{message}</code>
                    <div className={styles.ids}>
                      {list.map((s) => (
                        <a key={s.id} href={`#${s.id}`}>{s.id}</a>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
