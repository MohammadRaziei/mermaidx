import React, { useEffect, useRef, useState } from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import CodeBlock from '@theme/CodeBlock';
import slides from '../data/showcase.json';
import styles from './Showcase.module.css';

const SLIDE_SECONDS = 7;

function Slide({ slide, active }) {
  const src = useBaseUrl(`/${slide.image}`);
  return (
    <div
      id={`slide-${slide.id}`}
      role="tabpanel"
      aria-labelledby={`tab-${slide.id}`}
      aria-hidden={!active}
      className={active ? `${styles.slide} ${styles.slideActive}` : styles.slide}>
      <div className={styles.source}>
        <CodeBlock language="python">{slide.code}</CodeBlock>
      </div>
      <div className={styles.image}>
        <img
          src={src}
          width={slide.width}
          height={slide.height}
          alt={`${slide.label} diagram rendered by mermaidx`}
          loading={active ? 'eager' : 'lazy'}
        />
      </div>
    </div>
  );
}

export default function Showcase() {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const tabRefs = useRef([]);

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

  const auto = playing && !reducedMotion;
  const paused = hovered || focused;
  const next = () => setIndex((i) => (i + 1) % slides.length);

  const choose = (i) => {
    setIndex(i);
    setPlaying(false); // choosing a slide yourself stops the rotation
  };

  const onKeyDown = (e) => {
    const last = slides.length - 1;
    let target = null;
    if (e.key === 'ArrowRight') target = index === last ? 0 : index + 1;
    if (e.key === 'ArrowLeft') target = index === 0 ? last : index - 1;
    if (e.key === 'Home') target = 0;
    if (e.key === 'End') target = last;
    if (target === null) return;
    e.preventDefault();
    choose(target);
    tabRefs.current[target]?.focus();
  };

  return (
    <div
      className={styles.showcase}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}>
      <div className={styles.bar}>
        <div role="tablist" aria-label="Example diagrams" className={styles.tabs} onKeyDown={onKeyDown}>
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
                onClick={() => choose(i)}>
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
      <div className={styles.stage}>
        {slides.map((slide, i) => (
          <Slide key={slide.id} slide={slide} active={i === index} />
        ))}
      </div>
      <p className={styles.caption}>Left: the Python you write. Right: the diagram.png it produces, with no browser involved.</p>
    </div>
  );
}
