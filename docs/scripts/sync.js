// Copies files that live at the repository root into the docs folder, so
// there is a single source of truth for each of them.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const docs = path.resolve(__dirname, '..', 'docs');

const files = [
  {
    from: 'architecture.md',
    to: 'architecture.md',
    front: { title: 'Architecture', sidebar_position: 7, description: 'How mermaidx runs mermaid.js without a browser.' },
  },
  {
    from: 'CHANGELOG.md',
    to: 'changelog.md',
    front: { title: 'Changelog', sidebar_position: 9, description: 'Release notes for every mermaidx version.' },
  },
];

for (const f of files) {
  let text = fs.readFileSync(path.join(root, f.from), 'utf8');
  // Drop the leading H1; the page title comes from the front matter.
  text = text.replace(/^# .*\n+/, '');
  const fm = Object.entries(f.front)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? JSON.stringify(v) : v}`)
    .join('\n');
  fs.writeFileSync(path.join(docs, f.to), `---\n${fm}\n---\n\n${text}`);
  console.log(`synced ${f.from} -> docs/${f.to}`);
}
