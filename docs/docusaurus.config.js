// @ts-check
const { themes } = require('prism-react-renderer');

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'mermaidx',
  tagline: 'Mermaid diagrams to SVG, PNG and PDF from Python, with no browser.',
  favicon: 'img/favicon.svg',

  url: 'https://mohammadraziei.github.io',
  baseUrl: '/mermaidx/',
  organizationName: 'MohammadRaziei',
  projectName: 'mermaidx',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'warn',

  // Plain .md files are parsed as CommonMark, so architecture.md and
  // CHANGELOG.md can be shown as they are. Only .mdx files use MDX.
  markdown: {
    format: 'detect',
    mermaid: true,
    hooks: { onBrokenMarkdownLinks: 'warn' },
  },
  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: 'docs',
          routeBasePath: 'docs',
          sidebarPath: require.resolve('./sidebars.js'),
          editUrl: 'https://github.com/MohammadRaziei/mermaidx/edit/master/docs/',
        },
        blog: false,
        theme: { customCss: require.resolve('./src/css/custom.css') },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: { respectPrefersColorScheme: true },
      navbar: {
        title: 'mermaidx',
        logo: { alt: 'mermaidx', src: 'img/logo.svg' },
        items: [
          { to: '/docs/installation', label: 'Docs', position: 'left' },
          { to: '/benchmarks', label: 'Benchmarks', position: 'left' },
          { to: '/docs/changelog', label: 'Changelog', position: 'left' },
          { href: 'https://pypi.org/project/mermaidx', label: 'PyPI', position: 'right' },
          { href: 'https://github.com/MohammadRaziei/mermaidx', label: 'GitHub', position: 'right' },
        ],
      },
      footer: {
        style: 'dark',
        copyright: `MIT licensed. Mermaid is a trademark of its respective owners; mermaidx is not affiliated with the Mermaid project.`,
      },
      prism: {
        theme: themes.github,
        darkTheme: themes.dracula,
        additionalLanguages: ['bash', 'python', 'json', 'yaml'],
      },
      mermaid: { theme: { light: 'default', dark: 'dark' } },
    }),
};

module.exports = config;
