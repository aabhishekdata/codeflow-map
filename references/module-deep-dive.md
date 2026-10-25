# Module deep dive

How to explore one module (part) of a code base, explain it, and find what to improve. The analyzer does
the counting and drawing; you add judgment: what the module is *for*, which functions matter, and whether
the drafts are right.

## 1. Pick the module with the user

Show the table `analyze_modules.py` printed and ask which module to explore. Help them choose:

| If the user wants to... | Suggest |
|---|---|
| understand the system fastest | the module most others use (high *Used by*), or the one handling web requests |
| fix bugs / reduce risk | hotspots: high complexity that changes often |
| refactor / untangle | modules *in a loop*, or high *Uses* (depends on many) |
| review a change | `--diff <branch>`, then the changed modules |
| learn the data | modules with *tables* |

Then re-run with `--select <module>` so it gets more control-flow and sequence views.

## 2. Read in this order

Use `modules.json` (the module's entry under `modules`, and its views under `views` with
`"module": "<id>"`) as your map, then open the code:

1. **Dependencies view / `uses`, `used_by`.** Who depends on this module tells you its role: many users
   means a shared foundation; a module nobody imports is an entry point, a script or dead.
2. **Entry points (`routes`, functions marked `route` / `entry`).** What the outside world can ask it to
   do. Open each handler.
3. **Call graph.** The functions with many arrows in are the module's real API; the ones with arrows out to
   other parts are where it hands work over. Read the top 3-8.
4. **Control flow** of those functions (pick them under *Control flow*; add missing ones with
   `--cfg file:function`). Note the decisions that change outcomes (permission checks, validation, error
   paths) because these are what readers care about.
5. **Classes / Data model.** What the module stores and how records link. Personal-looking fields are
   flagged; confirm them.
6. **Drafts (Sequence, Data flow).** Compare with what you read. Keep, correct or replace them.

## 3. Write the enrichment spec

One file, usually `.codeflow/flowmap.json`. It can hold only notes; views are optional. See
`examples/sample-module-notes.json`.

```json
{
  "title": "Claims platform: how the code works",
  "generated": { "date": "2026-10-25", "commit": "a1b2c3d", "by": "Copilot with codeflow-map",
                 "assumptions": [], "open_questions": [] },
  "modules": [
    { "id": "m-backend-app-api", "label": "Web API",
      "description": "Receives every request from the website, checks who is asking, and hands the work to the data layer.",
      "why": "Every user action passes through here.",
      "risks": ["Deleting a user also deletes their items; there is no undo."] }
  ],
  "functions": [
    { "id": "backend/app/api/routes/users.py::update_user",
      "description": "Lets an administrator change a user's details, refusing an email address someone else already uses." }
  ],
  "views": [ ]
}
```

- **Module ids** (`m-...`) and **function ids** (`path/file.py::Class.method`) come from `modules.json`.
  The builder warns if one does not match.
- `label` replaces the folder name everywhere the module appears. Keep it to 2-4 words named after the
  job ("Web API", "Billing rules", "Customer data").
- `description` is one or two sentences, what it does and for whom. The measured summary (files, lines,
  dependencies) is appended automatically.
- `risks` are factual and neutral, with evidence. Hotspot and loop findings are added automatically;
  add what only reading reveals (missing checks, data sent outside, no undo).

### Replacing or adding views

Attach views to a module with `"kind": "detail"`, `"module": "<module id>"`, `"facet": "<facet>"`. They
appear in that module's facet bar.

| You want to | Do this |
|---|---|
| Replace the draft data flow | A flowchart view with id `mod-<slug>-dataflow` (same id = replaced), facet `dataflow` |
| Add a verified sequence | A sequence view with a new id, e.g. `mod-<slug>-seq-signup`, facet `sequence`; run the analyzer with `--no-drafts` if the drafts add nothing |
| Show a lifecycle | A `state` view, facet `state` (e.g. claim: Draft → Submitted → Approved / Rejected) |
| Explain one tricky function better | A `functions` note; for a business-level picture, a flowchart journey with facet `control` and `"function": "<function id>"` |
| Add something else | Any facet name you like; it becomes its own tab |

`<slug>` is the module id without the `m-` prefix. Write labels in plain English
(`references/plain-language.md`); the technical names live in `technical`.

### State views (lifecycles)

Look for: status / state fields and enums, `if status == ...` branches, functions named `approve`,
`submit`, `cancel`, `activate`. Each value is a state; each function or branch that changes it is a
transition. Use `"*"` for the start and end:

```json
{ "id": "mod-claims-states", "title": "Claim states", "kind": "detail", "module": "m-src-claims", "facet": "state",
  "type": "state", "summary": "The stages a claim moves through.",
  "states": [ { "id": "draft", "label": "Draft", "description": "Saved but not sent", "files": ["src/claims/model.py:12"] },
              { "id": "check", "label": "Valid?", "kind": "choice" },
              { "id": "submitted", "label": "Submitted" }, { "id": "rejected", "label": "Rejected" } ],
  "transitions": [ { "from": "*", "to": "draft" }, { "from": "draft", "to": "check", "label": "customer submits" },
                   { "from": "check", "to": "submitted", "label": "yes" }, { "from": "check", "to": "rejected", "label": "no" },
                   { "from": "submitted", "to": "*" } ] }
```

## 4. Find what to improve

The analyzer flags candidates; you confirm them by reading the code. Report them as a short list, each
with file:line and one sentence of evidence. Do not change code unless asked.

| Signal | Where | What it suggests |
|---|---|---|
| **Hotspot**: high complexity × frequent change | 🔥 Hotspots, module *Watch-outs*, report | Highest risk of new bugs; first candidate for tests and simplification |
| **High complexity** (≥ 10 decision points) | Control flow, call-graph *Measures* | Split into smaller functions; test each path |
| **Long function** (≥ 100 lines) | call-graph *Measures* | Does several jobs; extract the steps |
| **Loop between modules** (red dashed arrows) | Modules, Dependencies | Parts cannot change independently; extract the shared piece or invert one dependency |
| **Files importing each other in a loop** | report | A true import cycle; often a barrel `index` file or misplaced helper |
| **Depends on many** (instability near 1, many *Uses*) | Dependencies, Measures | Sensitive to changes elsewhere; consider a narrower interface |
| **Used by many** (high *Used by*) | Modules | Changes ripple widely; keep it stable and well tested |
| **Possibly unused** | panel *Watch-outs*, report | The name appears nowhere else; confirm (dynamic use, frameworks, external callers) before removing |
| **No test file imports it** | Measures, report | Untested; prioritise if it is also a hotspot |
| **Personal data** in tables or flows | Data model, Data flow | Check masking, retention and who receives it |

Wording: factual, neutral, specific. "`update_article()` (article.service.ts:289) has 12 decision points
and is the most-changed function in the module; it has no tests." Not "this code is bad".

## 5. Limits to state honestly

Static analysis cannot see: calls through callbacks, dependency injection, dynamic imports, decorators
that register handlers, ORMs that build queries from strings, message consumers wired in config, and
code in other repositories. When a picture depends on these, say so in `generated.assumptions` or mark
the box `"confidence": "inferred"`.
