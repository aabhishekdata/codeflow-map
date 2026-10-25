# Flow map spec (flowmap.json), version 3

One JSON file describes your part of the map. `build_flowmap.py` merges it with the module analysis
(`--modules .codeflow/modules.json`, written by `analyze_modules.py`), validates everything, draws every
view with Pele and builds the HTML. Copy the shape of `examples/sample-flowmap.json` (stakeholder views)
or `examples/sample-module-notes.json` (module enrichment). Version 1 and 2 specs build unchanged.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `title` | yes* | Map title, e.g. "Claims Portal: how it works" (*defaults to "<repo>: how the code is organised" with `--modules`) |
| `subtitle` | | One line under the title |
| `description` | | Paragraph shown in *About this map* |
| `default_mode` | | `"simple"` (default) or `"technical"`: which labels show first |
| `start_view` | | id of the view opened first (default: your first top-level view, else `modules`) |
| `icons` | | `false` to hide the small icon at the start of each box |
| `theme` | | `{ "mode": "auto" \| "light" \| "dark", "light": {css vars}, "dark": {css vars} }`, e.g. `{"light": {"--accent": "#00447C"}}` for a corporate colour |
| `repo` | | `{ "name", "path" or "url", "url_base" }`. With `url_base` (e.g. `https://git.company.com/org/repo/blob/main/`) file references become links |
| `generated` | yes* | `{ "date", "commit", "by", "scope", "method", "assumptions": [], "out_of_scope": [], "open_questions": [] }`. *The builder warns without `date` and `commit` |
| `modules` | | Plain-English notes for analysed modules (below) |
| `functions` | | Plain-English notes for analysed functions (below) |
| `views` | yes* | Your views (below). *May be empty when you only add notes to a module analysis |

### Module notes (`modules`)

`{ "id", "label", "description", "why", "risks": [], "controls": [] }`. `id` is a module id from
`modules.json` (e.g. `m-backend-app-api`). The label replaces the folder name in every view; the
description goes into the module's boxes and panels (the measured summary is appended); risks are listed
first under *Watch-outs*.

### Function notes (`functions`)

`{ "id", "label", "description", "why", "risks": [], "controls": [] }`. `id` is a function id from
`modules.json`: `path/to/file.py::function` or `path/to/file.ts::Class.method`. The note appears on the
function's box in every call graph and above its control-flow view.

## View (common fields)

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique, stable, no spaces (e.g. `overview`, `login-journey`) |
| `title` | yes | Tab / breadcrumb name, 1-4 words |
| `kind` | | `architecture` · `journey` · `dataflow` · `detail` · `other` (top-level tabs) · `modules` · `changes` · `communities` · `insights` (written by the analyzer). `detail` views are hidden from the tabs and reached by drill-down or a module's facet bar |
| `type` | | `flowchart` (default) · `sequence` · `class` · `er` · `state` · `mermaid` |
| `module` | | Module id: shows the view in that module's facet bar (use with `kind: "detail"`) |
| `facet` | | Which tab of the facet bar: `deps` · `files` · `classes` · `calls` · `control` · `sequence` · `dataflow` · `datamodel` · `state`, or any other word (its own tab). Several views with the same facet get a picker |
| `function` | | Function id the view is about (control-flow and sequence views) |
| `draft` | | `true` shows a *Draft* badge (drawn automatically; check before relying on it) |
| `summary` | | 1-2 plain-English sentences shown above the diagram |
| `technical_summary` | | Shown instead of `summary` in Technical mode |
| `show_in_tabs` | | `false` to hide a non-detail view from the tabs |
| `icons` | | `false` to hide icons in this view |
| `edge_labels` | | `false` to hide arrow labels (busy pictures); they stay in the click panel |
| `direction` | | `LR` (default for flowcharts) · `TB` · `RL` · `BT`. Narrow screens may switch LR to TB automatically |
| `groups` | | Areas drawn as labelled boxes (flowchart), shaded columns (sequence) or namespaces (class) |
| `walkthrough` | | Ordered presenter steps (below) |

## Flowchart views (`type: "flowchart"`)

| Field | Meaning |
|---|---|
| `nodes` | Boxes (below) |
| `edges` | Arrows (below) |

### Node (box)

| Field | Meaning |
|---|---|
| `id` | Unique within the view. Any string; the builder makes it safe |
| `label` | Plain-English name, ≤ 5 words (Simple mode) |
| `technical` | Real name: file, class, function, endpoint, table (Technical mode) |
| `kind` | Shape and colour, see table below (default `process`) |
| `group` | id of a group to place the box inside |
| `description` | What it does, 1-2 sentences, shown when clicked |
| `why` | Why it matters to the business |
| `data` | List of data it handles, by name ("Customer email") |
| `sensitive_data` | List of personal / confidential data it holds or handles (shown in red) |
| `controls` | Safeguards that exist in the code ("Passwords are stored hashed") |
| `risks` | Factual watch-outs observed ("Claim data is sent to an outside vendor") |
| `technical_detail` | Extra notes for engineers |
| `files` | Evidence: `["path/to/file.py:42", ...]` |
| `key` | Code-graph key of the thing this box stands for (set by the analyzer: a module id, file path, `file::function`, `c:file::Class`, `t:table`). Turns on *Explore from here*, WHY / TODO notes and docs in the panel |
| `confidence` | `verified` (read in code) or `inferred` (drawn with a dashed border) |
| `drilldown` | id of a view opened by the panel's **See inside** button (box gets a **+** badge) |
| `module` | Module id: the panel offers **See inside <module>** (opens its facet bar) |
| `cfg_view` | id of a control-flow view: the panel offers **Show control flow** |
| `function` | Function id (links function notes to this box) |
| `metrics` | `{ "Lines": 42, "Complexity": 7 }` shown as a *Measures* table |
| `heat` | 0-1; colours the box when the reader switches on 🔥 Hotspots |
| `changed` / `impact` | `true`: orange outline (changed) / dashed outline (may be affected) |

### Kinds

| `kind` | Shape | Use for |
|---|---|---|
| `user` | pill | A person or role (customer, underwriter, admin) |
| `ui` | rounded box | Screens, web pages, mobile app, UI components |
| `service` | box | APIs, back-end services, request handlers |
| `process` | box | Business logic, transformation step, plain block of code |
| `store` | cylinder | Database, table, data lake, file share |
| `external` | double-edged box | System owned by another team or vendor |
| `decision` | diamond | A yes/no check that changes the path |
| `event` | flag | Message, queue, topic, email notification |
| `file` | slanted box | File, export, report, document, data shape |
| `control` | hexagon | A safeguard (validation, approval, encryption, audit log); `try` / `finally` in control flow |
| `ai` | box | AI / ML model or LLM call |
| `schedule` | box | Scheduled or batch job, CLI entry point |
| `module` | box | A code module (part) |
| `function` | rounded box | A function or method |
| `package` | double-edged box | Third-party library, generated code |
| `start` / `end` | pill | Where a function starts / returns |
| `loop` | hexagon | A loop in control flow |
| `error` | box | Raised / thrown error, exception handler |

### Edge (arrow)

| Field | Meaning |
|---|---|
| `from`, `to` | Node ids |
| `label` | What moves, in plain words ("sends claim details"). An empty string shows no label in Simple mode |
| `technical` | Endpoint / call / protocol ("POST /api/claims") |
| `description` | Longer explanation shown when clicked |
| `data` | Data items (or imported names) passed |
| `sensitive` | `true` → red line and 🔒 (toggle with the *Sensitive* button) |
| `cycle` | `true` → red dashed line: part of a dependency loop |
| `controls` | Safeguards on this hop ("TLS", "token checked") |
| `protocol` | Shown in the technical section ("HTTPS", "Kafka", "SFTP") |
| `style` | `solid` (default) · `dashed` (optional / background / loop-back) · `thick` (main path) · `both` (two-way) · `plain` (no arrowhead) |
| `weight` | Number of links it stands for (module map) |
| `files` | Evidence for the call |
| `confidence` | `verified` (found in the code) or `inferred` (worked out by matching names or a rule; drawn dotted) |

Define edges **in the order things happen**: the automatic walkthrough follows that order.

### Group

`{ "id", "label", "technical", "description", "parent", "direction", "drilldown", "files" }`.
`parent` nests a group in another. Keep to 2-4 groups per hand-written view.

## Sequence views (`type: "sequence"`): step-by-step journeys

| Field | Meaning |
|---|---|
| `participants` | Columns, left to right, in the order given. Same fields as a node (`id`, `label`, `technical`, `kind`, `group`, `description`, `files`, ...). `kind: "user"` draws a stick figure |
| `groups` | Consecutive participants with the same `group` are shaded together |
| `steps` | Ordered list (below) |
| `numbered` | `false` to hide step numbers |

Step forms (comments are explanation only; JSON itself allows none):

```jsonc
{ "section": "We check who they are" }                       // chapter heading across all columns
{ "from": "svc", "to": "db", "label": "looks up the account",
  "technical": "get_user_by_email()", "reply": false, "async": false,
  "sensitive": false, "note": "Audit trail", "description": "...",
  "data": [], "controls": [], "files": ["backend/app/db/repo.py:3"] }
{ "note": "Retries 3 times", "over": "svc" }                 // free note on one column
```

`reply: true` draws a dashed return arrow; `async: true` an open arrow (fire-and-forget). `;` and `#` in
sequence text are replaced automatically.

## Class views (`type: "class"`)

```json
{ "id": "mod-billing-classes", "title": "Classes", "type": "class", "kind": "detail", "module": "m-billing", "facet": "classes",
  "groups": [ { "id": "inv", "label": "invoices" } ],
  "classes": [ { "id": "Invoice", "label": "Invoice", "technical": "Invoice (billing/models.py:10)", "stereotype": "table",
                 "attributes": ["+id: int PK", "+customer_id: int FK", "+total: Decimal"],
                 "methods": ["+add_line(item) None", "-_recalculate()"], "group": "inv", "kind": "store",
                 "description": "One bill sent to a customer.", "files": ["billing/models.py:10"] } ],
  "relations": [ { "from": "Invoice", "to": "Customer", "type": "association", "label": "customer_id" } ] }
```

Relation `type`: `inheritance` (from = child) · `realization` (from implements to) · `composition` ·
`aggregation` · `association` · `dependency` · `link`. A class with `"external": true` is drawn grey
(defined elsewhere). Up to 14 attributes and 14 methods are drawn; the rest are counted.

## Entity-relationship views (`type: "er"`)

```json
{ "id": "data-model", "title": "Data model", "type": "er",
  "entities": [ { "id": "customer", "label": "customer", "description": "People who hold policies.",
                  "attributes": [ { "name": "id", "type": "int", "key": "PK" },
                                  { "name": "email", "type": "varchar(255)", "sensitive": true } ] } ],
  "relations": [ { "from": "customer", "to": "claim", "card_from": "one", "card_to": "many", "label": "files" } ] }
```

Cardinality: `one` · `zero-one` · `many` · `one-many`. `"identifying": false` draws a dashed line.
Attributes may also be plain strings.

## State views (`type: "state"`)

`states`: `{ "id", "label", "kind": "choice"?, "description", "files" }`.
`transitions`: `{ "from", "to", "label" }`, where `"*"` is the start (as `from`) or end (as `to`).
See the example in `references/module-deep-dive.md`.

## Raw Mermaid views (`type: "mermaid"`)

`{ "id": "gantt", "title": "Release plan", "type": "mermaid", "mermaid": "gantt\n ..." }`. Any diagram
type Pele supports (Mermaid 12.1 syntax). Pan, zoom, export and print work; click panels, search and
walkthrough do not. Prefer the structured types above when they fit.

## Walkthrough steps

```json
"walkthrough": [
  { "text": "Overview sentence; no target shows the whole picture." },
  { "target": "api", "text": "Focus on one box (flowchart node, class, entity or state)." },
  { "edge": ["web", "api"], "text": "Focus on one arrow." },
  { "group": "outside", "text": "Focus on an area." },
  { "step": 4, "text": "Sequence views: 0-based index into steps." },
  { "drill": "service-detail", "text": "Open a detail view and continue there." }
]
```

Each step may also have `technical` text, shown in Technical mode. Put `drill` steps last: steps after a
drill must refer to boxes in the detail view. Views without a walkthrough get one automatically.

## Module analysis file (`modules.json`)

Written by `analyze_modules.py`; do not edit it. Useful fields when writing notes:
`modules[]` → `id`, `label`, `path`, `kind`, `files`, `uses`, `used_by`, `routes`, `tables`, `packages`,
`hotspots`, `unused`, `cycle`, `changed_files`, `changed_functions`, `facets` (its view ids);
`views[]` → the generated views (function ids are in each call-graph node's `function`; every generated
view carries `"generated": true`, which limits validation to structural checks). Large code bases also
get `area-<slug>` views: one module map per folder area, opened from the *Modules* view.

Version 3 adds:
- `graph`: the code graph the *Explore* tab queries, in a compact form: `types` and `rels` (name lists),
  `modules`, `nodes` as `[type, key, label, module, line, group, extra?]` and `edges` as
  `[from, to, relation, prov, line, section?]` (indexes into `nodes`; `prov` 0 = found in the code,
  1 = inferred). Node types: module, file, function, class, table, doc, note. Relations: contains,
  imports, calls, inherits, reads, writes, documents, explains (a WHY / TODO comment → code), defines,
  renders. The same graph is written readably to `.codeflow/graph.json` (node-link format, as Graphify).
- `insights`: `gods` (most-connected code), `surprising` (rare links between groups, with `why` and
  evidence), `questions` (suggested questions with the Explore query that answers them: `op` one of
  callers · callees · neighbours · impact · path, `from`, `to`; `to` may be `type:table`), `groups`
  (group number → label).
- `args`, `cwd`: how the analysis was run (used by `scripts/hook.py`).
- Views `groups` (kind `communities`, one box per group) with a `group-N` detail view each, and
  `insights` (kind `insights`).

A spec may add or override views of any kind, but cannot change the graph; describe what you learned in
module and function notes instead.

## Validation the builder performs

Errors (build stops): missing ids or labels, duplicate ids, references to unknown ids (arrows, groups,
drill-downs, modules, control-flow views, walkthrough targets), unknown kinds / types / relation types,
facets without a module, embedded secrets or credentials, and **any view Pele cannot draw** (the
offending lines are printed).
Warnings: long simple labels, missing descriptions or summaries, boxes without evidence, unconnected
boxes, very large views, possible personal data, module or function notes that match nothing, missing
`generated.date` / `commit`. Generated module views are held to the structural checks only.
