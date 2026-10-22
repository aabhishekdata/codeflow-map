---
name: codeflow-map
argument-hint: "e.g. big picture for business stakeholders | how login works | where customer data goes"
description: Builds an interactive, offline HTML map of how a codebase works - big-picture architecture, step-by-step journeys (e.g. what happens when a user logs in) and data flow / lineage - with tabs, drill-down, zoom, drag, click-for-details and a plain-English walkthrough for non-technical stakeholders. Use when asked to diagram, visualize, map, document or explain how code, requests or data flow through a repository (Python, JavaScript/TypeScript, SQL, notebooks).
---

# Code Flow Map

Produce **one HTML file** that explains a codebase visually to people who do not read code, while keeping
file-level evidence for engineers and auditors. It opens in any browser by double-click. By default it is
small (~0.1 MB) and loads only the Mermaid drawing library from cdn.jsdelivr.net (pinned version,
integrity-checked); map content never leaves the file. Build with `--offline` for a ~3.6 MB file that
needs no internet.

What the reader gets: view tabs (Big picture / journeys / data flow), double-click drill-down with
breadcrumbs, drag to pan, scroll or pinch to zoom, overview mini-map, click any box or arrow for a
plain-English panel (what it does, data involved, safeguards, source files), a Simple ↔ Technical label
switch, red 🔒 arrows for sensitive data, search, a step-by-step **Walk me through** presenter mode, and
export to SVG / Mermaid / PDF.

You do the analysis and write a JSON **spec**; the bundled builder turns it into the HTML and guarantees
valid Mermaid. Never hand-write the HTML or Mermaid for flowchart/sequence views.

Files in this skill (paths are relative to this SKILL.md):
- [scripts/scan_repo.py](scripts/scan_repo.py) - read-only static scan (routes, screens, tables, files, queues, AI calls, imports, call traces)
- [scripts/build_flowmap.py](scripts/build_flowmap.py) - validates the spec and writes the HTML
- [references/spec-schema.md](references/spec-schema.md) - every field of the spec (read before writing one)
- [references/analysis-playbook.md](references/analysis-playbook.md) - how to find the flows for each view type and stack
- [references/plain-language.md](references/plain-language.md) - how to write labels, descriptions and walkthroughs for stakeholders
- [examples/sample-flowmap.json](examples/sample-flowmap.json) - a complete, valid spec to copy from

## Step 0 - Agree the output (ask once, in one message)

Unless the request already answers these, ask them together and wait. Number them so the user can reply
"1d, 2a":

1. **Which view(s)?**
   a) Big picture - the main parts and how they connect
   b) A journey - name it, e.g. "user signs in", "claim is submitted", "nightly load"
   c) Data flow - which data, e.g. "customer personal data", "premium amounts"
   d) Complete pack - big picture with drill-downs, plus the key journeys and data flows (default)
2. **Audience?** a) business stakeholders (default) b) mixed c) engineers
3. **Scope?** whole repository (default) or named folders; anything to leave out
4. **Where to save?** default `docs/codeflow/<repo-name>-flow-map.html`

If the user says "just do it" or does not answer, use the defaults and state them at the top of your reply.

## Step 1 - Scan for evidence

Find a Python 3.8+ interpreter (`python`, then `python3`, then `py -3` on Windows). Locate this skill's
folder (usually `.github/skills/codeflow-map/` in the repo or `~/.copilot/skills/codeflow-map/`). Then run,
from the repository root:

```
python <skill>/scripts/scan_repo.py . --out .codeflow/scan.json
```

Read the Markdown summary it prints. For a journey, also locate and trace it:

```
python <skill>/scripts/scan_repo.py . --focus login,signin,auth
python <skill>/scripts/scan_repo.py . --trace <handler_function_name> --depth 3
```

Use `--path <folder>` to limit scope. Add `.codeflow/` to `.gitignore` if the user does not want it committed.
If Python is unavailable, do the same discovery with workspace search, following
`references/analysis-playbook.md`.

## Step 2 - Read and confirm

The scan gives leads, not facts. Open the files behind every component and arrow you intend to draw
(entry points, route handlers, services, data-access code, SQL, job definitions, config). Follow
`references/analysis-playbook.md` for the view type. Rules:

- **Evidence or flag it.** Every box gets `files` (`path:line`) and `"confidence": "verified"` if you read
  the code, or `"confidence": "inferred"` (drawn dashed) if it rests on naming, config or docs. People and
  outside systems need no files.
- **Never invent** components, vendors, tables or controls. Unknowns go in `generated.open_questions`.
- **Record what is not shown** (infrastructure, other repos) in `generated.out_of_scope` and anything you
  assumed in `generated.assumptions`.

## Step 3 - Design the views

| View | `kind` / `type` | Size target | Shape |
|---|---|---|---|
| Big picture | `architecture` / flowchart | 5-12 boxes, 2-4 groups | People → screens → services → stores/outside systems, left to right |
| Inside a part | `detail` / flowchart | 5-15 boxes | Reached by double-clicking a box with `drilldown` |
| Journey | `journey` / `sequence` | 4-7 participants, ≤ 20 steps | Step-by-step, numbered; use `section` steps as chapter headings |
| Journey for business readers | `journey` / flowchart | ≤ 12 boxes | Use when there are branches (decisions) or the audience finds sequence diagrams hard |
| Data flow / lineage | `dataflow` / flowchart | ≤ 15 boxes | Source → transformations → stores → reports/outside; mark every arrow carrying personal or sensitive data `"sensitive": true` |
| Data model (technical) | `other` / `mermaid` | - | Raw Mermaid (`erDiagram`, `classDiagram`) for engineers; no click details |

Split instead of cramming: if a picture needs more than ~15 boxes, put a summary box in the parent view
and move the detail into a `detail` view linked with `drilldown`. Groups should be business areas
("Customer-facing", "Claims processing", "Outside services"), not folder names.

Write a `walkthrough` for each top-level view (5-10 steps) telling the story in order. It is what the
user will present from. If omitted, the viewer auto-generates one from the arrows, which is weaker.

## Step 4 - Write the spec

Read `references/spec-schema.md` and `references/plain-language.md`, then copy the structure of
`examples/sample-flowmap.json`. Save as `.codeflow/flowmap.json` (or next to the output). Key habits:

- `label` = plain English, ≤ 5 words ("Claims service"). `technical` = real names ("FastAPI app, backend/app/main.py").
- `description` = one or two sentences a manager understands. Say what it does and why it matters.
- Arrow `label` says **what moves**: "sends claim details", not "calls".
- Fill `generated.date` and `generated.commit` (`git rev-parse --short HEAD`).

## Step 5 - Build and fix

```
python <skill>/scripts/build_flowmap.py .codeflow/flowmap.json --out docs/codeflow/<repo>-flow-map.html
```

Fix every `ERROR` and re-run. Treat warnings as a to-do list: missing descriptions, labels that are too
long, boxes without evidence, unconnected boxes. Use `--check` to validate without writing.

Delivery modes:
- default: small HTML, Mermaid from the CDN. Use this unless the user says otherwise.
- `--offline`: everything embedded in one ~3.6 MB file. Use when the user's network blocks
  cdn.jsdelivr.net (the page then says "The diagram library could not be loaded"), when the file will be
  opened without internet, or when the user asks for offline.
- `--split`: offline, as three files that must stay together (for mail filters that block large HTML).

## Step 6 - Hand over

Reply briefly with: the file path, the views and what each shows, how to open it (double-click; best in
Edge or Chrome; needs internet unless built with `--offline`), assumptions and open questions that need a human answer, and a tip to use
**▶ Walk me through** when presenting. Do not paste the spec back into chat.

## Guardrails (work code)

- Everything stays local: do not upload code or the map anywhere. The only network use is the viewer
  fetching the pinned Mermaid library from the CDN; do not add any other external links or scripts.
- Never copy secrets, keys, passwords, tokens, connection strings, real customer records or sample data
  into the spec. Describe fields by name ("email address", "policy number"). The builder blocks obvious
  secrets and warns on things that look like personal data.
- Environment variables: names only, never values. Do not open `.env` files.
- Flag, do not hide, risky findings you notice (sensitive data sent outside, missing checks) using
  `risks` on the box; keep the wording factual and neutral.

## Updating a map

Re-run the scan, edit the existing spec (do not start over), update `generated.date` / `commit`, rebuild.
Keep ids stable so walkthroughs and drill-downs keep working.

## Troubleshooting

- *"This view could not be drawn"* in the browser: use `type: "mermaid"` views only for diagram kinds
  the builder cannot express, and test them; flowchart/sequence views are generated safely.
- Picture too dense: split into drill-downs; set `direction` to `TB` for tall, narrow flows.
- Labels truncated or wrapped oddly: shorten `label`; move detail to `description`.
