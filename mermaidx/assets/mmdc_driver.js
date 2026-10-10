// What mermaid-cli's renderMermaid() does, inside its page, for one diagram when the output is SVG:
// render into #container, put the SVG text through the HTML parser (container.innerHTML = ...), set the
// background colour through CSSOM, and serialize with XMLSerializer. Same steps, same order -- the
// parts of the result that come from the browser (self-closing tags, namespace declarations, how the
// style attribute is written back) then come from the DOM shim being a faithful browser, not from
// touching the SVG string.
globalThis.__renderLikeMmdc = async function (svgId, definition, backgroundColor) {
  const container = document.getElementById("container");
  const { svg: svgText } = await mermaid.render(svgId, definition, container);
  container.innerHTML = svgText;
  const svg = container.getElementsByTagName("svg")[0];
  svg.style.backgroundColor = backgroundColor;
  return new XMLSerializer().serializeToString(svg);
};
