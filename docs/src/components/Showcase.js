import React, { useEffect, useMemo, useRef, useState } from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import CodeBlock from '@theme/CodeBlock';
import data from '../data/showcase.json';
import styles from './Showcase.module.css';

const { slides, backends } = data;
const DEFAULT_BACKEND = backends[0];
const SLIDE_SECONDS = 7;

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

function Variant({ slide, variant, active, eager }) {
  const src = useBaseUrl(`/${variant.image || ''}`);
  const className = active ? `${styles.variant} ${styles.variantActive}` : styles.variant;
  return (
    <div className={className} aria-hidden={!active}>
      {variant.image ? (
        <img
          src={src}
          width={variant.width}
          height={variant.height}
          alt={`${slide.label} diagram rendered by ${variant.backend}`}
          loading={eager ? 'eager' : 'lazy'}
        />
      ) : (
        <div className={styles.missing} title={variant.error}>
          <strong>{variant.backend}</strong>
          <span>could not render this diagram.</span>
        </div>
      )}
    </div>
  );
}

function Slide({ slide, active, backend }) {
  // A slide that is not on screen keeps the backend it last showed, so switching the backend does not redo
  // the syntax highlighting of the slides nobody sees.
  const shown = useRef(backend);
  if (active) shown.current = backend;
  const shownBackend = shown.current;
  const code = useMemo(() => pythonFor(slide.source, shownBackend), [slide.source, shownBackend]);
  const block = useMemo(() => <CodeBlock language="python">{code}</CodeBlock>, [code]);
  return (
    <div
      id={`slide-${slide.id}`}
      role="tabpanel"
      aria-labelledby={`tab-${slide.id}`}
      aria-hidden={!active}
      className={active ? `${styles.slide} ${styles.slideActive}` : styles.slide}>
      <div className={styles.source}>{block}</div>
      <div className={styles.image}>
        <span className={styles.chip} style={{ '--chip': colorOf(shownBackend) }}>
          {shownBackend}
        </span>
        {slide.variants.map((variant) => (
          <Variant
            key={variant.backend}
            slide={slide}
            variant={variant}
            active={variant.backend === shownBackend}
            eager={active}
          />
        ))}
      </div>
    </div>
  );
}

export default function Showcase() {
  const [index, setIndex] = useState(0);
  const [backendIndex, setBackendIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const tabRefs = useRef([]);
  const pillRefs = useRef([]);

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

  const backend = backends[backendIndex];
  const auto = playing && !reducedMotion;
  const paused = hovered || focused;
  const next = () => setIndex((i) => (i + 1) % slides.length);

  const chooseSlide = (i) => {
    setIndex(i);
    setPlaying(false); // choosing a slide yourself stops the rotation
  };
  const chooseBackend = (i) => {
    setBackendIndex(i);
    setPlaying(false);
  };

  const onTabKeyDown = (e) => {
    const last = slides.length - 1;
    let target = null;
    if (e.key === 'ArrowRight') target = index === last ? 0 : index + 1;
    if (e.key === 'ArrowLeft') target = index === 0 ? last : index - 1;
    if (e.key === 'Home') target = 0;
    if (e.key === 'End') target = last;
    if (target === null) return;
    e.preventDefault();
    chooseSlide(target);
    tabRefs.current[target]?.focus();
  };

  const onPillKeyDown = (e) => {
    const last = backends.length - 1;
    let target = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') target = backendIndex === last ? 0 : backendIndex + 1;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') target = backendIndex === 0 ? last : backendIndex - 1;
    if (e.key === 'Home') target = 0;
    if (e.key === 'End') target = last;
    if (target === null) return;
    e.preventDefault();
    chooseBackend(target);
    pillRefs.current[target]?.focus();
  };

  const current = slides[index];
  const drawn = (slide, name) => slide.variants.find((v) => v.backend === name)?.image;

  return (
    <div
      className={styles.showcase}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}>
      <div className={styles.bar}>
        <span className={styles.axis} aria-hidden="true">Diagram</span>
        <div role="tablist" aria-label="Example diagrams" className={styles.tabs} onKeyDown={onTabKeyDown}>
          {slides.map((slide, i) => {
            const selected = i === index;
            return (
              <button
                key={slide.id}
                ref={(el) => (tabRefs.current[i] = el)}
                id={`tab-${slide.id}`}
                role="tab"
                type="button"
                aria-selected={selected}
                aria-controls={`slide-${slide.id}`}
                tabIndex={selected ? 0 : -1}
                className={selected ? `${styles.tab} ${styles.tabActive}` : styles.tab}
                onClick={() => chooseSlide(i)}>
                {slide.label}
                {selected && auto && (
                  <span
                    key={index}
                    className={styles.progress}
                    style={{ animationDuration: `${SLIDE_SECONDS}s`, animationPlayState: paused ? 'paused' : 'running' }}
                    onAnimationEnd={next}
                    aria-hidden="true"
                  />
                )}
              </button>
            );
          })}
        </div>
        {!reducedMotion && (
          <button type="button" className={styles.toggle} onClick={() => setPlaying((p) => !p)} aria-pressed={!playing}>
            {playing ? 'Pause' : 'Play'}
          </button>
        )}
      </div>
      <div className={styles.bar}>
        <span className={styles.axis} aria-hidden="true">Backend</span>
        <div role="radiogroup" aria-label="Backend" className={styles.pills} onKeyDown={onPillKeyDown}>
          {backends.map((name, i) => {
            const selected = i === backendIndex;
            const missing = !drawn(current, name);
            const classes = [styles.pill, selected && styles.pillActive, missing && styles.pillMissing].filter(Boolean);
            return (
              <button
                key={name}
                ref={(el) => (pillRefs.current[i] = el)}
                role="radio"
                type="button"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                title={missing ? `${name} could not render this diagram` : undefined}
                className={classes.join(' ')}
                style={{ '--chip': colorOf(name) }}
                onClick={() => chooseBackend(i)}>
                <span className={styles.dot} aria-hidden="true" />
                {name}
              </button>
            );
          })}
        </div>
      </div>
      <div className={styles.stage}>
        {slides.map((slide, i) => (
          <Slide key={slide.id} slide={slide} active={i === index} backend={backend} />
        ))}
      </div>
      <p className={styles.caption}>
        Left: the Python you write, where the backend is one argument. Right: the diagram.png it produces, with no
        browser involved. Pick another diagram or another backend: every picture is rendered by mermaidx.
      </p>
    </div>
  );
}
