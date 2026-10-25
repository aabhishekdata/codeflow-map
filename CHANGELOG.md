# Changelog

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
- Diagrams are drawn with Pele 1.10.0 instead of Mermaid 11. The default build is offline (~1 MB);
  `--cdn` loads Pele from jsDelivr (pinned, integrity-checked). `--split` was removed.
- Zoom and pan use Pele's built-in zoom; the plain mouse wheel zooms too. The mini-map was removed.
- Drill-down is click → panel → **See inside** (double-click zooms).
- The walkthrough camera centres each step using Pele's zoom-at-point.

### Compatibility
- V1 specs build unchanged.
- Python 3.8+ (tested on 3.8.20 and 3.13). Node.js 18+ recommended (tested on 20 and 22); without Node,
  JS/TS gets import analysis only and the drawing check is skipped.

## 1.0.0 (2026-10-22)

First release: stakeholder flow maps (big picture, journeys, data flow) rendered with Mermaid.
