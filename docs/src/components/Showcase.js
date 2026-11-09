import React, { useEffect, useMemo, useState } from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import CodeBlock from '@theme/CodeBlock';
import data from '../data/showcase.json';
import styles from './Showcase.module.css';

const { slides, backends } = data;
const DEFAULT_BACKEND = backends[0];

// How long each backend stays on screen. A diagram stays for the sum of the times of the backends that drew it,
// and that sum is also what fills the progress line under its tab.
const SECONDS = { 'js:mermaid': 3, 'js:pele': 3, 'rust:merman': 3, 'rust:mermaid-rs-renderer': 3 };
const secondsOf = (backend) => SECONDS[backend] ?? 3;

const imageOf = (slide, backend) => slide.variants.find((v) => v.backend === backend);
// For each diagram: the backends that drew it, in the order of the rail, and how long they take together.
const plan = slides.map((slide) => {
  const drawn = backends.filter((b) => imageOf(slide, b)?.image);
  return { drawn, seconds: drawn.reduce((sum, b) => sum + secondsOf(b), 0) };
});

// The colors of the benchmark charts, so a backend looks the same on both pages.
const BACKEND_COLOR = {
  'js:mermaid': 'var(--mx-quickjs)',
  'js:pele': 'var(--mx-pele-quickjs)',
  'rust:merman': 'var(--mx-merman)',
  'rust:mermaid-rs-renderer': 'var(--mx-rust)',
};
const colorOf = (backend) => BACKEND_COLOR[backend] || 'var(--mx-muted)';

// The Python on the left: the default backend is not named, the others are one argument.
function pythonFor(source, backend) {
  const call = backend === DEFAULT_BACKEND ? '"""' : `""", backend="${backend}"`;
  return `import mermaidx\n\ndiagram = mermaidx.render("""\n${source}\n${call})\ndiagram.save("diagram.png")`;
}

// What comes after the backend on screen: the next one that drew this diagram, else the next diagram.
function after({ s, b }) {
  const { drawn } = plan[s];
  const i = drawn.indexOf(b);
  if (i >= 0 && i < drawn.length - 1) return { s, b: drawn[i + 1] };
  const nextSlide = (s + 1) % slides.length;
  return { s: nextSlide, b: plan[nextSlide].drawn[0] ?? DEFAULT_BACKEND };
}

const start = (s) => ({ s, b: plan[s].drawn[0] ?? DEFAULT_BACKEND });

export default function Showcase() {
  const base = useBaseUrl('/');
  const [pos, setPos] = useState(() => start(0));
  const [playing, setPlaying] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => {
      setReducedMotion(query.matches);
      if (query.matches) setPlaying(false);
    };
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  // Fetch the pictures of this diagram and of the next one ahead of time, so the switch never waits for a download.
  useEffect(() => {
    [slides[pos.s], slides[(pos.s + 1) % slides.length]].forEach((slide) =>
      slide.variants.forEach((v) => {
        if (v.image) new Image().src = `${base}${v.image}`;
      }),
    );
  }, [pos.s, base]);

  const slide = slides[pos.s];
  const variant = imageOf(slide, pos.b);
  const auto = playing && !reducedMotion;
  const running = auto && !hovered && !focused;
  const code = useMemo(() => pythonFor(slide.source, pos.b), [slide.source, pos.b]);
  const block = useMemo(() => <CodeBlock language="python">{code}</CodeBlock>, [code]);
  const playState = running ? 'running' : 'paused';

  // Choosing a diagram or a backend yourself stops the rotation.
  const chooseSlide = (s) => {
    setPos(start(s));
    setPlaying(false);
  };
  const chooseBackend = (b) => {
    setPos({ s: pos.s, b });
    setPlaying(false);
  };
  // Play starts the diagram on screen again from its first backend, so its two progress lines begin together.
  const togglePlay = () => {
    if (!playing) setPos(start(pos.s));
    setPlaying(!playing);
  };

  const onTabKeyDown = (e) => {
    const last = slides.length - 1;
    let target = null;
    if (e.key === 'ArrowRight') target = pos.s === last ? 0 : pos.s + 1;
    if (e.key === 'ArrowLeft') target = pos.s === 0 ? last : pos.s - 1;
    if (e.key === 'Home') target = 0;
    if (e.key === 'End') target = last;
    if (target === null) return;
    e.preventDefault();
    chooseSlide(target);
    document.getElementById(`tab-${slides[target].id}`)?.focus();
  };

  const onRailKeyDown = (e) => {
    const at = backends.indexOf(pos.b);
    const last = backends.length - 1;
    let target = null;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') target = at === last ? 0 : at + 1;
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') target = at === 0 ? last : at - 1;
    if (e.key === 'Home') target = 0;
    if (e.key === 'End') target = last;
    if (target === null) return;
    e.preventDefault();
    chooseBackend(backends[target]);
    document.getElementById(`backend-${backends[target].replace(/\W+/g, '-')}`)?.focus();
  };

  return (
    <div
      className={styles.showcase}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}>
      <div className={styles.bar}>
        <div role="tablist" aria-label="Example diagrams" className={styles.tabs} onKeyDown={onTabKeyDown}>
          {slides.map((s, i) => {
            const selected = i === pos.s;
            return (
              <button
                key={s.id}
                id={`tab-${s.id}`}
                role="tab"
                type="button"
                aria-selected={selected}
                aria-controls="showcase-panel"
                tabIndex={selected ? 0 : -1}
                className={selected ? `${styles.tab} ${styles.tabActive}` : styles.tab}
                onClick={() => chooseSlide(i)}>
                {s.label}
                {selected && auto && (
                  <span
                    key={pos.s}
                    className={styles.tabProgress}
                    style={{ animationDuration: `${plan[pos.s].seconds}s`, animationPlayState: playState }}
                    aria-hidden="true"
                  />
                )}
              </button>
            );
          })}
        </div>
        {!reducedMotion && (
          <button type="button" className={styles.toggle} onClick={togglePlay} aria-pressed={!playing}>
            {playing ? 'Pause' : 'Play'}
          </button>
        )}
      </div>

      <div className={styles.body}>
        <div role="radiogroup" aria-label="Backend" className={styles.rail} onKeyDown={onRailKeyDown}>
          {backends.map((name) => {
            const selected = name === pos.b;
            const drawn = Boolean(imageOf(slide, name)?.image);
            const [kind, ...rest] = name.split(':');
            const classes = [styles.railItem, selected && styles.railItemActive, !drawn && styles.railItemMissing];
            return (
              <button
                key={name}
                id={`backend-${name.replace(/\W+/g, '-')}`}
                role="radio"
                type="button"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                className={classes.filter(Boolean).join(' ')}
                style={{ '--chip': colorOf(name) }}
                onClick={() => chooseBackend(name)}>
                <span className={styles.railName}>{rest.join(':')}</span>
                <span className={styles.railKind}>{drawn ? kind : 'not drawn'}</span>
                {selected && auto && (
                  <span
                    key={`${pos.s}-${pos.b}`}
                    className={styles.railProgress}
                    style={{ animationDuration: `${secondsOf(name)}s`, animationPlayState: playState }}
                    onAnimationEnd={() => setPos(after)}
                    aria-hidden="true"
                  />
                )}
              </button>
            );
          })}
        </div>

        <div id="showcase-panel" role="tabpanel" aria-labelledby={`tab-${slide.id}`} className={styles.content}>
          <div className={styles.source}>{block}</div>
          <div className={styles.image}>
            <span className={styles.chip} style={{ '--chip': colorOf(pos.b) }}>
              {pos.b}
            </span>
            {variant?.image ? (
              <img
                key={variant.image}
                className={styles.picture}
                src={`${base}${variant.image}`}
                width={variant.width}
                height={variant.height}
                alt={`${slide.label} diagram rendered by ${pos.b}`}
              />
            ) : (
              <div className={styles.missing} title={variant?.error}>
                <strong>{pos.b}</strong>
                <span>could not render this diagram.</span>
              </div>
            )}
          </div>
        </div>
      </div>
      <p className={styles.caption}>
        Top: the diagram. Left: the backend, which is one argument in the Python. Right: the diagram.png it produces,
        with no browser involved.
      </p>
    </div>
  );
}
