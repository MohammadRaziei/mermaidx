Reference SVGs produced by the real mermaid-cli (`mmdc`) for every `tests/samples/*.mmd`, used by
`tests/test_mmdc_reference.py`. Regenerate with the same recipe (anything else changes the numbers):

    mmdc -p puppeteer.json -w 1016 -b transparent -c mmdc-config.json -i NN_name.mmd -o NN_name.svg

* mermaid-cli 11.12.0 with `mermaid` pinned to 11.16.0 (the version bundled in `mermaidx/assets/mermaid.js`)
* Chromium run with `--font-render-hinting=none --enable-font-subpixel-positioning --disable-lcd-text`
* fontconfig forcing every family to the bundled `DejaVu Sans` (what mermaidx measures with)
* `-w 1016` -> a 1000px container (the shim's fallback width; only gantt depends on it)
* `mmdc-config.json` = `{"handDrawnSeed": 1}` (rough.js is otherwise random per run, also in mmdc)
* `-b transparent`; mmdc still writes `background-color: transparent` on the root, which the test ignores
