Reference SVGs produced by the real mermaid-cli (`mmdc`) for every `tests/samples/*.mmd`, used by
`tests/test_mmdc_structural.py`. Regenerate with the same recipe (anything else changes the numbers):

    mmdc -q --no-font-embed -p puppeteer.json -b transparent -c mmdc-config.json -i NN_name.mmd -o NN_name.svg

* mermaid-cli 12.0.0, which bundles mermaid 12.2.0 -- the version in `mermaidx/assets/mermaid.js`
  (`dist/mermaid.min.js` of the npm package)
* mmdc 12 has no `-w`: its page is opened with a 0 px viewport. Use a copy of `src/index.js` whose viewport is
  `width: 1016, height: 600` (a 1000px container, the shim's fallback width; only gantt depends on it)
* mmdc 12 loads Recursive Variable and Open Sans into the page as web fonts (`--no-font-embed` only keeps them out
  of the SVG). They are not what mermaidx measures with, so remove the three `@fontsource...` entries from the
  `cssImports` list in the same copy of `src/index.js`; Chromium then falls back to the fontconfig font below
* fontconfig forcing every family to the bundled `DejaVu Sans` (what mermaidx measures with), without hinting:

      <fontconfig>
        <dir>mermaidx/assets/fonts</dir>
        <match target="pattern"><edit name="family" mode="assign" binding="strong"><string>DejaVu Sans</string></edit></match>
        <match target="font">
          <edit name="antialias" mode="assign"><bool>true</bool></edit>
          <edit name="hinting" mode="assign"><bool>false</bool></edit>
          <edit name="hintstyle" mode="assign"><const>hintnone</const></edit>
          <edit name="autohint" mode="assign"><bool>false</bool></edit>
          <edit name="rgba" mode="assign"><const>none</const></edit>
        </match>
      </fontconfig>

  (`FONTCONFIG_FILE` and `FONTCONFIG_PATH` point at it. Without `hintnone` Chromium rounds text widths to whole pixels.)
* Chromium 153 (the `@sparticuz/chromium` npm package carries one, for a machine that cannot download Chrome), run with
  `--no-sandbox --font-render-hinting=none --enable-font-subpixel-positioning --disable-lcd-text`
* `mmdc-config.json` = `{"handDrawnSeed": 1}` (rough.js is otherwise random per run, also in mmdc)
* `-b transparent`; mmdc writes `background-color: transparent` on the root, and so does mermaidx (compared like everything else)
