# packages/aui — vendored assistant-ui

The assistant-ui packages the web client's import graph actually touches,
vendored as **built dist** so this repo builds the web client with no sibling
monorepo checkout and no network beyond npm for the external deps.

Provenance: <https://github.com/assistant-ui/assistant-ui> (MIT, see
`LICENSE`), copied from the `feat/acp-thread-list` fork branch's `dist/`.
Sourcemaps are stripped and every internal dependency is rewritten to
`workspace:*` so bun links these copies, never npm's.

Members: `acp`, `core`, `react`, `react-markdown`, `store`,
`assistant-stream`, `tap`, `cloud`, `safe-content-frame`.

## Refreshing

Rebuild the upstream monorepo, then re-copy each member's `dist/` (minus
`*.map`, minus `sourceMappingURL` comments) and its `package.json` reduced to
the consumer fields (name, version, license, type, exports, main, types,
sideEffects, deps/peers, homepage, repository). Do not hand-edit dist here;
this directory is a snapshot, not a fork.
