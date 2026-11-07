# 1. Record architecture decisions

- Status: Accepted
- Date: 2026-11-07

## Context

The reasons behind several choices in mermaidx lived only in code comments, changelog entries and conversations: why
every render builds a new JavaScript context, why `mermaid.js` is loaded from a cache of compiled bytecode, why
`tools/quickjs_ng_bytecode` exists, why CI installs a patched `quickjs-ng`. Anyone who reads `tools/` or `wheel.yml`
without that background has to guess, and a decision nobody can find the reason for is easy to undo by accident.

## Decision

Decisions that are hard to undo, that change what users or CI get, or that have rejected alternatives people will ask
about again are recorded as short records in `docs/adr/`, one per decision, numbered `NNNN-short-title.md`, following
[`template.md`](template.md): status, date, context, decision, alternatives considered, consequences.

A record is not edited after it is accepted, apart from its status line and links. A decision that changes gets a new
record that supersedes the old one, so the history of why stays readable.

## Alternatives considered

- **Keep explaining in `architecture.md` and the changelog.** `architecture.md` describes how the code works today and
  the changelog describes what changed in a release; neither keeps the rejected options or says when to revisit a
  choice.
- **Long design documents.** More than a page per decision is rarely read, and is rarely kept up to date.

## Consequences

- Writing a record is part of making such a decision, and the index in `docs/adr/README.md` has to be kept in step.
- Records state their measurements with where they were taken, so a later reader can tell a number from a CI runner
  from one taken on a slow machine.
- The records are in English, like the rest of the project's documentation.
