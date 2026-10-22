# Flow map spec (flowmap.json)

One JSON file describes the whole map. `build_flowmap.py` validates it and builds the HTML.
`examples/sample-flowmap.json` is a complete, working example; copy its shape.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | Map title, e.g. "Claims Portal: how it works" |
| `subtitle` | | One line under the title |
| `description` | | Paragraph shown in *About this map* |
| `default_mode` | | `"simple"` (default) or `"technical"`: which labels show first |
| `start_view` | | id of the view opened first (default: first top-level view) |
| `icons` | | `false` to hide the small icon at the start of each box |
| `repo` | | `{ "name", "path" or "url", "url_base" }`. If `url_base` is set (e.g. `https://git.company.com/org/repo/blob/main/`), file references become links |
| `generated` | yes* | `{ "date", "commit", "by", "scope", "method", "assumptions": [], "out_of_scope": [], "open_questions": [] }`. *The builder warns without `date` and `commit` |
| `views` | yes | List of views (below) |

## View (common fields)

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique, stable, no spaces (e.g. `overview`, `login-journey`) |
| `title` | yes | Tab / breadcrumb name, 1-4 words |
| `kind` | | `architecture` · `journey` · `dataflow` · `detail` · `other`. `detail` views are hidden from tabs and reached by drill-down |
| `type` | | `flowchart` (default) · `sequence` · `mermaid` |
| `summary` | | 1-2 plain-English sentences shown above the diagram |
| `technical_summary` | | Shown instead of `summary` in Technical mode |
| `show_in_tabs` | | `false` to hide a non-detail view from the tabs |
| `icons` | | `false` to hide icons in this view |
| `groups` | | Areas drawn as labelled boxes (flowchart) or shaded columns (sequence) |
| `walkthrough` | | Ordered presenter steps (see below) |

## Flowchart views (`type: "flowchart"`)

| Field | Meaning |
|---|---|
| `direction` | `LR` (default, left to right) · `TB` (top to bottom) · `RL` · `BT` |
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
| `confidence` | `verified` (read in code) or `inferred` (drawn with a dashed border) |
| `drilldown` | id of a view to open on double-click / "See inside" |

### Kinds

| `kind` | Shape | Use for |
|---|---|---|
| `user` | pill | A person or role (customer, underwriter, admin) |
| `ui` | rounded box | Screens, web pages, mobile app, reports UI |
| `service` | box | APIs, back-end services, functions |
| `process` | box | Business logic, transformation step, module |
| `store` | cylinder | Database, table, data lake, file share |
| `external` | double-edged box | System owned by another team or vendor |
| `decision` | diamond | A yes/no check that changes the path |
| `event` | flag | Message, queue, topic, email notification |
| `file` | slanted box | File, export, report, document |
| `control` | hexagon | A safeguard: validation, approval, encryption, audit log |
| `ai` | box | AI / ML model or LLM call |
| `schedule` | box | Scheduled or batch job |

### Edge (arrow)

| Field | Meaning |
|---|---|
| `from`, `to` | Node ids |
| `label` | What moves, in plain words ("sends claim details") |
| `technical` | Endpoint / call / protocol ("POST /api/claims") |
| `description` | Longer explanation shown when clicked |
| `data` | Data items passed |
| `sensitive` | `true` → red line and 🔒 (toggle with the *Sensitive data* button) |
| `controls` | Safeguards on this hop ("TLS", "token checked") |
| `protocol` | Shown in the technical section ("HTTPS", "Kafka", "SFTP") |
| `style` | `solid` (default) · `dashed` (optional/background) · `thick` (main path) · `both` (two-way) |
| `files` | Evidence for the call |

Define edges **in the order things happen**: the auto-walkthrough follows that order.

### Group

`{ "id", "label", "technical", "description", "parent", "direction", "drilldown", "files" }`.
`parent` nests a group in another. Keep to 2-4 groups per view.

## Sequence views (`type: "sequence"`) - step-by-step journeys

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

`reply: true` draws a dashed return arrow; `async: true` an open arrow (fire-and-forget).
Avoid `;` and `#` in sequence text (they are replaced automatically).

## Raw Mermaid views (`type: "mermaid"`)

`{ "id": "data-model", "title": "Data model", "type": "mermaid", "mermaid": "erDiagram\n ..." }`.
Pan, zoom, export and print work; click panels, search and walkthrough do not. Use only for diagram kinds
the other types cannot express (ER, class, state, Gantt). Keep the syntax simple and test it.

## Walkthrough steps

```json
"walkthrough": [
  { "text": "Overview sentence; no target fits the whole picture to screen." },
  { "target": "api", "text": "Focus on one box." },
  { "edge": ["web", "api"], "text": "Focus on one arrow." },
  { "group": "outside", "text": "Focus on an area." },
  { "step": 4, "text": "Sequence views: 0-based index into steps." },
  { "drill": "service-detail", "text": "Open a detail view and continue there." }
]
```

Each step may also have `technical` text, shown in Technical mode. Put `drill` steps last: steps after
a drill must refer to boxes in the detail view.

## Validation the builder performs

Errors (build stops): missing ids or labels, duplicate ids, arrows or walkthrough steps pointing at
unknown ids, unknown kinds or drill-down targets, embedded secrets or credentials.
Warnings: long simple labels, missing descriptions or summaries, boxes without evidence, unconnected
boxes, very large views, possible personal data, missing `generated.date` / `commit`.
