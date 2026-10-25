# codeflow-map: a GitHub Copilot agent skill

Turns a codebase into **one interactive HTML file** that explains how it works:

- a **module map** of every part of the code and how the parts depend on each other;
- a **deep dive** into any module you choose: its dependencies, files, classes, call graph, the
  step-by-step **control flow** of its functions, a sequence of calls, data flow, data model and states,
  with hotspots, loops and possibly-unused code flagged;
- a **stakeholder pack** in plain English: big picture with drill-downs, step-by-step journeys (for
  example, "user signs in") and where personal data flows.

Diagrams are drawn with [Pele](https://pele.run) (MIT), a fast Mermaid renderer themed with CSS
variables. The whole map is one file that works offline.

## What's new in v2

| | v1 | v2 |
|---|---|---|
| Diagram engine | Mermaid 11 (3.6 MB offline) | Pele 1.10 (~0.7 MB inlined, offline by default) |
| Module map and deep dive | - | *Modules* tab and per-module facet bar (dependencies, files, classes, call graph, control flow, sequence, data flow, data model, states) |
| Code analysis | regex scan | Python `ast` + Babel parser for JS/TS, call resolution through imports, control-flow graphs |
| Improve the code | - | hotspots (complexity × change frequency), module and file loops, possibly-unused code, untested modules, *What changed* since a branch |
| Diagram types | flowchart, sequence | + class, entity-relationship, state (all clickable) |
| Build check | structure only | every view is drawn with Pele before the HTML is written |
| Themes and devices | light only | light / dark / auto, corporate colours, phone layout |
| Drill-down | double-click | click → panel → **See inside** (double-click now zooms) |
| Exports | SVG, Mermaid | + all views as Markdown, copy link to a view |

V1 specs build unchanged.

## Install

Copy the whole `codeflow-map` folder (keep its sub-folders) to one of:

| Location | Who gets it |
|---|---|
| `<your repo>/.github/skills/codeflow-map/` | Everyone who opens that repository |
| `~/.copilot/skills/codeflow-map/` (Windows: `%USERPROFILE%\.copilot\skills\codeflow-map\`) | Just you, in every repository |

Requirements: VS Code with GitHub Copilot in **Agent** mode (choose a Claude model), a VS Code version
that supports Agent Skills, **Python 3.8+**, and **Node.js 18+** (20+ tested). Node is used for JavaScript /
TypeScript analysis and to check every diagram draws; without it the skill still works (JS/TS imports
only, no drawing check). No pip or npm installs, no internet. Reload VS Code after copying the folder;
`codeflow-map` then appears in the `/` menu of Copilot Chat.

## Use

In Copilot Chat (Agent mode), open the repository and ask, for example:

- "Use codeflow-map to show me the modules of this repo." (Copilot shows the module list and asks which
  one to explore)
- "Dig into the billing module: how does it work and what should we improve?"
- "Show the control flow of `create_user`."
- "What changed since main, and what does it affect?"
- "Show how this repo works, for business stakeholders." / "Map what happens when a user logs in."

or type `/codeflow-map`. Copilot runs the analysis, reads the code of the module you pick, adds
plain-English explanations, and builds `docs/codeflow/<repo>-flow-map.html`. Approve the Python / Node
terminal commands when prompted, then open the HTML by double-clicking it.

## In the map

- **Modules tab**: every part of the code and who uses whom (large code bases show areas first, each
  opening its own module map). Red dashed arrows are loops. Click a part, then **See inside**.
- **Facet bar** inside a module: Dependencies · Files · Classes · Call graph · Control flow (pick a
  function) · Sequence · Data flow · Data model · States. *Draft* marks views drawn automatically.
- **Click** any box, arrow or area for a plain-English panel: what it does, measures, data, safeguards,
  watch-outs, source files. Boxes with a **+** badge open more detail.
- **Drag** to move; **scroll**, **Ctrl + scroll** or **pinch** to zoom; double-click to zoom in or reset.
- **Simple / Technical** labels · **🔒 Sensitive** data in red · **🔥 Hotspots** colouring · **◐** light / dark / auto.
- **Search** (`/`) across every view, module and function; **▶ Walk me through** presenter mode (arrow
  keys / space).
- **More**: About (scope, assumptions, open questions), full screen, print / PDF, SVG of the view,
  Mermaid of the view, **all views as Markdown** (for wikis), copy a link to the current view.

## Try it without Copilot

```
# stakeholder example (insurance claims portal)
python scripts/build_flowmap.py examples/sample-flowmap.json --out sample.html

# module map + deep dives of any repository
python scripts/analyze_modules.py path/to/repo --select api
python scripts/build_flowmap.py --modules path/to/repo/.codeflow/modules.json --out repo-map.html

# the same, with plain-English notes (example written for fastapi/full-stack-fastapi-template)
python scripts/build_flowmap.py examples/sample-module-notes.json --modules path/to/repo/.codeflow/modules.json --out repo-map.html
```

Builder options: `--check` (validate only), `--strict`, `--cdn` (small file that loads Pele from
cdn.jsdelivr.net, pinned and integrity-checked), `--svg-dir <dir>` (one SVG per view). Analyzer options:
`--select`, `--cfg file:function`, `--diff <branch>`, `--module-depth`, `--modules-config`, `--report`;
see `python scripts/analyze_modules.py --help`.

## Files

```
codeflow-map/
├── SKILL.md                          instructions Copilot follows
├── scripts/analyze_modules.py        module map + deep-dive views (Python ast; JS/TS via js_facts.cjs)
├── scripts/js_facts.cjs              JavaScript / TypeScript facts with the vendored Babel parser
├── scripts/scan_repo.py              quick evidence scan for stakeholder views
├── scripts/build_flowmap.py          merges, validates, draws (pele_check.cjs) and builds the HTML
├── scripts/pele_check.cjs            draws every view with Pele in Node
├── assets/viewer.html                the interactive viewer
├── assets/flowmap-gen.js             spec → Mermaid text (shared by viewer and checker)
├── assets/vendor/pele.global.js      Pele 1.10.0 (MIT, see PELE-LICENSE.txt)
├── assets/vendor/babel-parser.js     @babel/parser 7.29 (MIT, see BABEL-PARSER-LICENSE.txt)
├── references/                       module deep dive, spec schema, analysis playbook, plain language
└── examples/                         sample-flowmap.json, sample-module-notes.json
```

## Privacy

Everything runs locally. The scripts never execute project code, never install packages, never use the
network, skip `.env` files and report environment variables by name only. The HTML contains only the
analysis and what is written in the spec; its Content Security Policy blocks all data requests. The
default build downloads nothing; a `--cdn` build downloads only the pinned Pele library. The builder
refuses specs that appear to embed secrets and warns about anything that looks like personal data.

## Licence

MIT, see [LICENSE](LICENSE). The bundled Pele and Babel parser keep their own MIT licences
(`assets/vendor/`).
