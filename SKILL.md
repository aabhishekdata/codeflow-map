---
name: codeflow-map
argument-hint: "e.g. module map | dig into the billing module | what could break if X changes | how login works | what changed since main"
description: Builds one interactive, offline HTML map of how a codebase works. A module map shows the parts of the code and how they depend on each other; a deep dive into a chosen module adds dependencies, files, classes, call graph, control flow of its functions, sequence, data flow, data model and states, with hotspots and possibly-unused code. A code graph in the browser answers who-uses, what-could-break and how-does-A-reach-B questions, groups code by how it is really connected, links WHY / TODO comments and docs to the code and flags surprising links; Graphify output adds other languages. Also big-picture architecture, user journeys and data lineage in plain English for stakeholders. Use when asked to diagram, visualize, map, document, explain or improve code structure, a module, a function's logic, the impact of a change, or how requests or data flow through a repository (Python, JavaScript/TypeScript, SQL, Prisma, notebooks).
---

# Code Flow Map (v3)

Produce **one HTML file** that explains a codebase visually. It opens in any browser by double-click,
works offline (the Pele drawing library, ~0.7 MB, is inlined; a typical map is 1-2 MB), and keeps file-level evidence behind every box.

It holds two kinds of picture, in any combination:

- **Module map + deep dive** (for understanding or improving the code). The *Modules* tab shows the parts
  of the code and their dependencies. Each part has its own views: Dependencies, Files, Classes, Call
  graph, Control flow (one per function, picked from a list), Sequence, Data flow, Data model and States.
  Most of these are generated from the code by `analyze_modules.py`; you add plain-English explanations
  and the pictures that need judgment.
- **Code graph** (new in v3). Every module, file, function, class, table, doc and WHY / TODO comment with
  the links between them. The *Explore* tab answers questions in the browser (who uses X, what does X
  use, what could break if X changes, how does A reach B); *Groups* shows code grouped by how it is
  actually connected (not by folder); *Insights* shows surprising links and the most-connected code.
  Every arrow is marked as found in the code (solid) or inferred (dotted).
- **Stakeholder pack** (for people who do not read code). Big picture with drill-downs, step-by-step
  journeys ("user signs in") and data flow, written by you in plain English.

What the reader gets: tabs; a facet bar inside each module; click any box, arrow or area for a
plain-English panel (what it does, measures, data, safeguards, watch-outs, source files) with **See inside**
buttons on boxes marked **+**; drag to move, scroll / Ctrl+scroll / pinch to zoom; Simple ↔ Technical
labels; 🔒 sensitive-data highlighting; 🔥 hotspot colouring; light / dark / auto theme; search across
every view; deep links; **▶ Walk me through** presenter mode; export to SVG, Mermaid and Markdown;
print / PDF; a phone-friendly layout.

Files in this skill (paths are relative to this SKILL.md):
- [scripts/analyze_modules.py](scripts/analyze_modules.py): module map and per-module views (Python `ast`; JS/TS through `scripts/js_facts.cjs` + the vendored Babel parser)
- [scripts/scan_repo.py](scripts/scan_repo.py): quick evidence scan for stakeholder views (routes, screens, tables, queues, AI calls, call traces)
- [scripts/codegraph.py](scripts/codegraph.py): code graph, file cache, groups, WHY / TODO comments, docs, Graphify reader (used by the analyzer)
- [scripts/hook.py](scripts/hook.py): optional git post-commit hook that keeps the map fresh
- [scripts/build_flowmap.py](scripts/build_flowmap.py): merges, validates, draws every view with Pele (`scripts/pele_check.cjs`), writes the HTML
- [references/module-deep-dive.md](references/module-deep-dive.md): how to explore, explain and improve a chosen module
- [references/spec-schema.md](references/spec-schema.md): every field of the spec (read before writing one)
- [references/analysis-playbook.md](references/analysis-playbook.md): how to find big picture, journeys and data flows
- [references/plain-language.md](references/plain-language.md): how to write labels, descriptions and walkthroughs
- [examples/](examples/): a stakeholder spec and a module-enrichment spec to copy from

Requirements: Python 3.8+. Node.js 14+ for JavaScript/TypeScript analysis and 18+ for the drawing check
(20 and 22 tested). Without Node everything still runs: JS/TS is scanned for imports only, and the drawing
check is skipped.
No package installs and no internet needed.

## Step 0 - Agree the output (ask once, in one message)

Unless the request already answers these, ask them together and wait. Number them so the user can reply
"1a, 2 billing":

1. **What do you want?**
   a) Module map + deep dive into a module, to understand or improve the code (default when the user asks
      about code, a module or a function)
   b) Stakeholder pack: big picture, journeys, data flow in plain English (default when the user mentions
      stakeholders, business, management or audit)
   c) Both
   d) What changed since a branch or commit, and what it affects (name the branch, e.g. `main`)
2. **Which module?** Name it, or "show me the list first" (default).
3. **Audience?** a) engineers (default for 1a) b) business stakeholders (default for 1b) c) mixed
4. **Scope / save to?** Whole repository (default) or named folders; default output
   `docs/codeflow/<repo-name>-flow-map.html`

If the user says "just do it" or does not answer, use the defaults, state them at the top of your reply
and, for 1a, deep-dive the first module in the analyzer's *Suggested modules* list.

## Step 1 - Analyse the modules (1a, 1c, 1d)

Find a Python 3.8+ interpreter (`python`, then `python3`, then `py -3` on Windows) and locate this skill's
folder (usually `.github/skills/codeflow-map/` in the repo or `~/.copilot/skills/codeflow-map/`). From the
repository root run:

```
python <skill>/scripts/analyze_modules.py . --out .codeflow/modules.json
```

With more than 24 modules, the *Modules* tab first shows **areas** (the next folder level), each opening
its own module map. The command prints a Markdown table of modules (files, lines, used by / uses, highest
complexity, notes such as routes, tables, loops, hotspots, changed) followed by loops, hotspots, possibly-unused code and
*Suggested modules to explore first*. If the user has not named a module, **show them the table and
suggestions, ask which module(s) to explore, and wait.**

| Option | Use it to |
|---|---|
| `--select billing,claims` | Give the chosen modules more depth (3× control-flow diagrams, more sequences) |
| `--cfg path/file.py:function` | Add the control flow of a specific function (repeatable; `Class.method` works) |
| `--diff main` | Mark what changed since a branch or commit and add a *What changed* view (1d) |
| `--module-depth 3` / `--modules-config m.json` | Fix modules that come out too coarse or too fine; the config maps names to path globs, e.g. `{"Billing": ["src/billing/**"]}` |
| `--path src/` / `--include-tests` | Limit the scope / treat tests as code |
| `--no-drafts` | Skip the automatic sequence and data-flow drafts (when you write verified ones) |
| `--report .codeflow/module-report.md` | Save the printed summary |
| `--no-docs` | Do not link README / docs / ADR files to the code |
| `--graphify <graph.json>` / `--no-graphify` | Use (or ignore) a Graphify graph; by default `graphify-out/graph.json` is read if present |
| `--resolution 1.0` | Larger → more, smaller groups in the *Groups* tab |
| `--no-cache` | Re-read every file (normally unchanged files come from `.codeflow/cache/`) |

The summary also lists the most-connected code, the groups, surprising links, WHY / TODO notes found,
docs linked to code and *Suggested questions* (they become one-click questions in the *Explore* tab).

Besides `modules.json` the analyzer writes `.codeflow/graph.json` (the code graph in the node-link format
Graphify uses, for other tools) and `.codeflow/cache/` (facts per file, keyed by content hash). Add
`.codeflow/` to `.gitignore` if the user does not want it committed. Re-running is cheap (unchanged files
come from the cache) and replaces `modules.json`; never edit that file by hand.

**Other languages.** codeflow-map parses Python, JavaScript / TypeScript, SQL and Prisma itself. If the
repository has a Graphify output (`graphify-out/graph.json`, made by the user with the separate Graphify
tool), files in other languages (Go, Java, Rust, ...) are taken from it: functions, classes, imports, calls
and rationale comments. Do not install or run Graphify yourself; just mention it if most of the code is in
a language codeflow-map does not parse.

## Step 2 - Deep dive the chosen module (1a, 1c)

Re-run Step 1 with `--select <module>` (plus `--cfg` for any function the user named). Then follow
[references/module-deep-dive.md](references/module-deep-dive.md):

1. Read the module's entry in `modules.json` (files, uses / used_by, routes, tables, hotspots, unused,
   facets) and **open the files** behind the important parts: entry points, the busiest functions in the
   call graph, the hotspots, the data model.
2. Write `.codeflow/flowmap.json` with what the analysis cannot know:
   - `modules`: a plain-English `label`, `description`, `why` and factual `risks` for the module (and its
     neighbours if useful).
   - `functions`: notes for the 3-8 functions that matter most, keyed by the function id from
     `modules.json` (e.g. `backend/app/crud.py::create_user`). They appear in the call graph and above the
     function's control flow.
   - Verified pictures that replace drafts: give your data-flow view the id `mod-<module>-dataflow` to
     replace the draft. Add your own sequence views with new ids (e.g. `mod-<module>-seq-signup`), and
     use `--no-drafts` if the automatic ones add nothing.
   - Views the analyzer cannot draw, attached with `"module"` + `"facet"`: `state` for anything with a
     lifecycle (status fields, workflows), a `sequence` for the module's main use case.
3. Use the code graph to check your understanding before writing: `modules.json` → `graph` holds every
   link with `prov` 0 (found in the code) or 1 (inferred), and `insights` holds the most-connected code,
   surprising links and suggested questions. WHY / NOTE / HACK comments are the authors' own reasons:
   use them in `why`, and quote TODO / FIXME in `risks` when they matter.
4. Report improvement findings in your reply, briefly and with evidence (file:line): hotspots, loops,
   possibly-unused code, untested modules, TODO / FIXME clusters, surprising links between groups, risky
   data handling. Do not change code unless asked.

## Step 3 - Stakeholder views (1b, 1c)

1. Scan: `python <skill>/scripts/scan_repo.py . --out .codeflow/scan.json` (and `--focus login,signin` /
   `--trace <handler> --depth 3` for a journey). The scan gives leads, not facts.
2. Read the code behind every box and arrow (follow `references/analysis-playbook.md`). Every box gets
   `files` (`path:line`) and `"confidence": "verified"`, or `"confidence": "inferred"` (drawn dashed).
   Never invent components, vendors, tables or controls; unknowns go in `generated.open_questions`.
3. Design the views:

| View | `kind` / `type` | Size target | Shape |
|---|---|---|---|
| Big picture | `architecture` / flowchart | 5-12 boxes, 2-4 groups | People → screens → services → stores / outside systems |
| Inside a part | `detail` / flowchart | 5-15 boxes | Reached from a box with `drilldown` |
| Journey | `journey` / `sequence` | 4-7 participants, ≤ 20 steps | Numbered steps; `section` steps as chapters |
| Journey with branches | `journey` / flowchart | ≤ 12 boxes | Decisions as `decision` boxes |
| Data flow / lineage | `dataflow` / flowchart | ≤ 15 boxes | Source → transformations → stores → outside; mark personal data `"sensitive": true` |
| Data model / states / classes | `other` / `er`, `state`, `class` | - | Structured types, clickable |

4. Write each top-level view's `walkthrough` (5-10 steps): it is what the user presents from.
   Read `references/plain-language.md`: labels ≤ 5 words, arrows say what moves, descriptions in one or
   two sentences a manager understands.

## Step 4 - Build and fix

```
python <skill>/scripts/build_flowmap.py .codeflow/flowmap.json --modules .codeflow/modules.json --out docs/codeflow/<repo>-flow-map.html
```

Leave out the spec or `--modules` if you only have one of them. The builder merges them (your views and
notes win), validates every reference, then **draws every view with Pele** in Node in both label modes.
Fix every `ERROR`: a "Pele cannot draw it" error prints the offending diagram lines. Treat warnings as a
to-do list. Options: `--check` (validate only), `--strict`, `--cdn` (small file that loads Pele from
cdn.jsdelivr.net, pinned and integrity-checked), `--svg-dir <dir>` (one SVG per view for documents).
Fill `generated.date` and `generated.commit` (`git rev-parse --short HEAD`) in your spec.

## Step 5 - Hand over

Reply briefly with:
- the file path and how to open it (double-click; Edge or Chrome; works offline);
- what is in it: which tabs, which module was explored, which views are drafts;
- how to use it: click a part on *Modules* → **See inside**; use the facet bar; pick a function under
  *Control flow*; *Explore* for questions (one-click suggested questions, or "🔎 Explore from here" on any
  box); *Groups* and *Insights*; 🔥 *Hotspots*; ▶ *Walk me through* for presenting;
- assumptions and open questions that need a human answer;
- improvement findings (Step 2.4).

Do not paste the spec back into chat.

## What each module view answers

| Facet | Question it answers | Source |
|---|---|---|
| Dependencies | What does this part rely on, and who relies on it? Which libraries, tables, services? | imports, SQL, HTTP calls |
| Files | Which files are inside and how do they use each other? | imports |
| Classes | Which classes / data shapes exist, what they hold, how they relate | AST: bases, typed fields, foreign keys |
| Call graph | Which function calls which; what other parts call in / out | AST calls resolved through imports, `self`/`this` |
| Control flow | Step by step, how one function decides what to do (decisions, loops, errors, returns) | AST of the function body |
| Sequence (draft) | In what order calls happen from an entry point, down to the database / outside services | static call trace, depth 3 |
| Data flow (draft) | Where data comes in, which files handle it, where it is stored or sent | routes, ORM / SQL use, file I/O, HTTP |
| Data model | Tables, fields (personal-looking ones flagged), links | ORM models, CREATE TABLE, Prisma schema |
| States | Which states something moves through | written by you |

| Tab | Question it answers |
|---|---|
| Groups | Which code really belongs together (groups found from the links, not the folders), and how the groups connect |
| Insights | Which links between groups are surprising, which code everything depends on |
| Explore | Who uses X? What does X use? What could break if X changes? How does A reach B (or any database table)? Big answers are folded into one box per module |

Drafts are labelled **Draft** in the map. Check them before relying on them; replace them with verified
views when the picture matters.

## Guardrails (work code)

- Everything stays local. The scripts never execute project code, never install packages and never use
  the network; Node only runs the vendored parser and Pele. Do not upload code or the map anywhere.
- Never copy secrets, keys, passwords, tokens, connection strings, real customer records or sample data
  into the spec. Describe fields by name ("email address", "policy number"). The builder blocks obvious
  secrets and warns on anything that looks like personal data.
- Environment variables: names only, never values. Do not open `.env` files.
- Findings are facts with evidence, worded neutrally ("claim details are sent to an outside AI service; the
  response is not stored"). Flag, do not hide, risky findings.

## Updating a map

Re-run `analyze_modules.py` (and `scan_repo.py` if you use it), edit the existing spec rather than
starting over, update `generated.date` / `commit`, rebuild. Only changed files are re-read.

To keep a map fresh automatically, offer (do not install unasked) the optional git hook:
`python <skill>/scripts/hook.py install --modules .codeflow/modules.json`. After each commit it repeats
the last analysis and build in the background (log in `.codeflow/hook.log`); `hook.py uninstall` removes
only its own block, `hook.py status` shows whether it is on. Module ids come from folder paths and view ids
from module ids, so notes keep working. Control-flow and sequence view ids follow ranking and can change,
so key function notes by function id, never by view id.

## Troubleshooting

- *Node.js not found*: JS/TS gets imports only and the drawing check is skipped. Ask the user for the
  path to Node and pass `--node <path>` to both `analyze_modules.py` and `build_flowmap.py`.
- *Some files "could not be parsed"* (listed in the summary): they use syntax newer than the Python
  running the analyzer (e.g. `match` on 3.8/3.9) or have errors; run it with a newer Python if available.
- *Modules too coarse or too fine*: `--module-depth N` or `--modules-config`.
- *A picture is too dense*: lower `--max-call-nodes`, split into `detail` views with `drilldown`, or use
  `--select` for one module at a time. Readers can zoom; the phone layout re-flows automatically.
- *Call graph misses a call*: calls through callbacks, dependency injection or framework wiring are not
  visible statically. Mention it, or add the link in your own view.
- *An Explore answer is huge*: answers over 30 items are folded into one box per module (click it for the
  names). Ask from a narrower starting point (a function rather than a file).
- *Too many or too few groups*: `--resolution 1.5` (more, smaller) or `0.7` (fewer, larger).
- *"This view could not be drawn"* in the browser: rebuild without `--no-node` to see the exact error.
