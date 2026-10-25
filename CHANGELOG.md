# Changelog

## 3.0.0 (2026-10-25)

Ideas from [Graphify](https://github.com/Graphify-Labs/graphify), implemented without any installs and
answered in the browser.

### Added
- `scripts/codegraph.py`: one code graph of modules, files, functions, classes, tables, docs and
  rationale comments (contains, imports, calls, inherits, reads, writes, documents, explains, defines,
  renders). Saved in `modules.json` (`graph`) and as `.codeflow/graph.json` (node-link, Graphify-style).
- Viewer **Explore** tab: callers, callees, everything around, impact (up to three steps, folded into
  one box per module when large) and path (B may be any database table); suggested questions; "Explore
  from here" and "What could break if it changes?" in every panel; deep links and Back between questions;
  code-graph hits in search.
- **Groups** tab: functional groups from a pure-Python Louvain; unlinked files collected in one group;
  `--resolution`.
- **Insights** tab and report: most-connected code, surprising links between groups, suggested questions.
- Provenance on every arrow: found in the code or inferred (dotted). Unique-name call matching and
  table reads / writes are marked inferred.
- Rationale: WHY / NOTE / IMPORTANT / DECISION / SECURITY comments, known issues (TODO / FIXME / HACK / XXX / BUG /
  WORKAROUND / DEPRECATED) and ADR / RFC references,
  attached to the enclosing (or following) function, class or file; shown in the panel.
- Docs: README, docs/ and ADR Markdown linked to the modules, files and functions they mention
  (`--no-docs`).
- File cache keyed by content hash (`.codeflow/cache/`, `--no-cache`).
- `scripts/hook.py`: optional git post-commit hook (install / uninstall / status) that repeats the last
  analysis and build in the background.
- Graphify interop: `graphify-out/graph.json` (or `--graphify <file>`) supplies files in languages
  codeflow-map does not parse; `--no-graphify`.

### Changed
- File names that say little on their own are shown with their folder (`conf/__init__.py`).
- `modules.json` schema `codeflow-modules/3` (adds `graph`, `insights`, `args`, `cwd`); v2 files still build.

## 2.0.0 (2026-10-25)

### Added
- `scripts/analyze_modules.py`: module map and per-module deep dives. Detects modules (adaptive, by depth,
  or from a config), the import graph, metrics (size, fan-in / fan-out, instability, complexity, change
  frequency from git, test coverage by import), module and file loops, hotspots, possibly-unused code,
  and `--diff <branch>` impact. Code bases with more than 24 modules get an area level (one module map
  per folder area) so the top picture stays readable.
- Per-module views: Dependencies, Files, Classes, Call graph, Control flow (per function), Sequence
  (draft), Data flow (draft), Data model (ORM, CREATE TABLE, Prisma schema), plus agent-written States.
- `scripts/js_facts.cjs`: JavaScript / TypeScript analysis (imports, exports, classes, functions,
  React components, Express routes, calls, complexity, control-flow graphs) with the vendored Babel parser.
- Spec: `modules` and `functions` notes; view `module`, `facet`, `function`, `draft`, `edge_labels`;
  node `module`, `cfg_view`, `function`, `metrics`, `heat`, `changed`, `impact`; new view types `class`,
  `er`, `state`; new kinds `module`, `function`, `package`, `start`, `end`, `loop`, `error`; `theme`.
- `scripts/pele_check.cjs`: the builder draws every view with Pele (both label modes and the export
  variant) and stops with the offending lines if one cannot be drawn. `--svg-dir` writes SVG files.
- Viewer: Modules tab and facet bar with function picker, hotspot overlay, changed / impact outlines,
  light / dark / auto themes with CSS-variable overrides, phone layout, deep links and browser Back,
  export of all views as Markdown, copy link to a view.

### Changed
- Diagrams are drawn with Pele 1.10.0 instead of Mermaid 11. The default build is offline (Pele ~0.7 MB inlined);
  `--cdn` loads Pele from jsDelivr (pinned, integrity-checked). `--split` was removed.
- Zoom and pan use Pele's built-in zoom; the plain mouse wheel zooms too. The mini-map was removed.
- Drill-down is click → panel → **See inside** (double-click zooms).
- The walkthrough camera centres each step using Pele's zoom-at-point.

### Compatibility
- V1 specs build unchanged.
- Python 3.8+ (tested on 3.8.20 and 3.13). Node.js 14+ for JS/TS analysis, 18+ for the drawing check (tested on 20 and 22); without Node,
  JS/TS gets import analysis only and the drawing check is skipped.

## 1.0.0 (2026-10-22)

First release: stakeholder flow maps (big picture, journeys, data flow) rendered with Mermaid.
