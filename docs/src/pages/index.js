import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import CodeBlock from '@theme/CodeBlock';
import Showcase from '../components/Showcase';
import styles from './index.module.css';

export default function Home() {
  return (
    <Layout
      title="Mermaid diagrams from Python"
      description="Convert Mermaid diagrams to SVG, PNG, JPEG, PDF or ASCII from Python, with no browser, Node.js or npm.">
      <header className={styles.hero}>
        <div className={styles.heroText}>
          <h1>Render Mermaid diagrams from Python, with no browser</h1>
          <p className={styles.lead}>
            mermaidx runs the real mermaid.js inside a small embedded engine. One <code>pip install</code> gives you
            SVG, PNG, JPEG, PDF and ASCII output, with no Node.js, no Chrome and nothing to compile.
          </p>
          <div className={styles.actions}>
            <CodeBlock language="bash">pip install mermaidx</CodeBlock>
            <Link className="button button--primary button--lg" to="/docs/quickstart">
              Get started
            </Link>
            <Link className="button button--secondary button--lg" to="/benchmarks">
              See the benchmarks
            </Link>
          </div>
        </div>
        <div className={styles.demo}>
          <Showcase />
        </div>
      </header>

      <main className={styles.main}>
        <section>
          <h2>What you do not need to install</h2>
          <p>
            The official mermaid-cli starts a headless Chrome for every diagram, which means installing Node.js and
            around 170 MB of Chromium. In a CI pipeline or a serverless function, that is most of the time spent.
            mermaidx renders the same Mermaid library without a browser, so a diagram is one Python call.
          </p>
        </section>
        <section>
          <h2>Four backends, one API</h2>
          <p>
            <code>quickjs</code> is the default and has no dependencies. <code>v8</code> is faster for large batches.{' '}
            <code>merman</code> and <code>mermaid-rs-renderer</code> are native Rust renderers. Switching is one
            argument: <code>mermaidx.render(source, backend="v8")</code>. The{' '}
            <Link to="/docs/backends">backends page</Link> says when to choose each.
          </p>
        </section>
        <section>
          <h2>Checked against mermaid-cli</h2>
          <p>
            The SVG output is compared with <code>mmdc</code> on 43 reference diagrams using a strict structural
            comparison. The <Link to="/benchmarks">benchmark gallery</Link> shows the same diagrams rendered by all
            five renderers, side by side, with the time each one took.
          </p>
        </section>
      </main>
    </Layout>
  );
}
