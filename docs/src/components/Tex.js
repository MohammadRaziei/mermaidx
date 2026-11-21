import React from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

// A formula in LaTeX, set by KaTeX. renderToString also works while the site is built, so the page ships the finished
// markup. The strings given are the ones in this file, never text a visitor typed, which is what makes it safe to put
// the result into the page as HTML.
export default function Tex({ children }) {
  const html = katex.renderToString(String(children), { throwOnError: false });
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

// The two numbers under every time on the benchmark page.
export const T0 = 't_0';
export const T_MED = 't_{\\mathrm{med}}';
