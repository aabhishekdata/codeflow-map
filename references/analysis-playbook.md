# Analysis playbook

How to turn a repository into accurate views. The approach combines the strongest ideas from open-source
code-visualization tools (all MIT-licensed; ideas only, no code copied):

| Idea | From | How this skill uses it |
|---|---|---|
| Ground the diagram in static analysis before the LLM summarises | CodeBoarding | Run `scan_repo.py` first; every box carries `files` evidence or is marked `inferred` |
| Several levels of abstraction with click-to-expand | CodeBoarding | Big picture → `detail` views via `drilldown` |
| Two passes: explain in words first, then draw | GitDiagram | Write the plain-English story (Step A below) before writing nodes/edges |
| Click a component to reach its source | GitDiagram | `files` become links when `repo.url_base` is set |
| Trace the call chain from one function, limited depth | code2flow | `scan_repo.py --trace <fn> --depth 3` |
| One page per component plus data-flow diagrams | DeepWiki-Open | Click panel per box; dedicated `dataflow` views |
| Folder-level dependency graph and metrics | Emerge | `area_dependencies` in the scan output; the full module map from `analyze_modules.py` |
| Control-flow graphs of single functions | code2flow, pyflowchart | *Control flow* facet: decisions, loops, errors, returns from the AST |
| Hotspots = complexity × change frequency | "code as a crime scene" idea | 🔥 *Hotspots* switch and the analyzer report |

This playbook covers the **stakeholder views** (big picture, journeys, data flow). For exploring a single
module in depth, follow `references/module-deep-dive.md`. The module analysis is also a good starting
point for the big picture: its *Modules* view and `uses` / `used_by` show which folders form the real parts.

## Step A - write the story first (2 minutes, not shown to the user)

Before any JSON, write 5-8 sentences in your own notes: who uses the system, what they do, which parts
handle it, where data is kept, what goes outside the company, what runs on a schedule. If you cannot
write a sentence from the code, it is an open question, not a box.

## Big picture (architecture)

1. **Entry points** (scan: *Entry points*, *Backend routes*, *Frontend routes*, *Scheduled jobs*). Each
   distinct way in becomes a box: web UI, API, job, notebook pipeline, queue consumer.
2. **Areas** (scan: *Areas* and *Area dependencies*). Folders that import each other become one or two
   service/process boxes. Do not draw one box per folder; merge by business purpose.
3. **Stores** (scan: *Database objects*, *ORM models*, *Tables written/read*, *File reads & writes*).
   Group tables into one or two "database" boxes; list key tables in `technical` and `data`.
4. **Outside systems** (scan: *External hosts*, *Outbound calls*, *Messaging*, *AI usage*, env var names
   such as `*_URL`, `*_ENDPOINT`). Each vendor or other team's system is an `external` (or `ai`/`event`) box.
5. **People**. Who triggers things: customers, staff roles, admins, schedulers.
6. Arrows follow the main path left to right; background or optional flows are `dashed`.
7. Add `drilldown` on any box that hides 4 or more meaningful parts, and build that `detail` view.

## Journey (one user action, end to end)

1. Find the starting screen or trigger: `--focus` with the user's words and synonyms (login: `login,signin,
   sign_in,auth,authenticate,session,token`; claim: `claim,submit,fnol`).
2. Frontend: route → page component → the API call it makes (scan: *Frontend routes*, *Outbound calls*).
3. Backend: match the called path to *Backend routes*, take the handler, then
   `--trace <handler> --depth 3` for what it calls. Read each function in the trace and keep the ones that
   change what happens (checks, writes, calls outside); drop helpers and logging.
4. For each step note: who → who, what is passed (`data`), whether it is personal data (`sensitive`),
   any check or safeguard (`controls`), and where it is in code (`files`).
5. Include the unhappy path that matters most (wrong password, validation failure) as a `decision` (in a
   flowchart journey) or a `note` / extra step (in a sequence).
6. Use `section` steps to split long journeys into 2-4 chapters a stakeholder can follow.

Pick **sequence** when the order of calls between systems is the point; pick a **flowchart journey** when
there are branches or the audience is non-technical.

## Data flow / lineage

1. Name the data in business terms (e.g. "customer contact details", "claim amount").
2. Find where it **enters**: forms (frontend fields), API request bodies, file loads (`read_csv`,
   `spark.read`), upstream tables.
3. Follow every **write**: `INSERT`/`MERGE`/`UPDATE`, ORM saves, `to_sql`, `saveAsTable`, `.write`, events
   sent, files exported, AI/vendor calls. Each destination is a box.
4. Follow **transformations**: SQL views and stored procedures (scan: *Database objects*), dataframe
   steps, dbt models. Show a transformation as a `process` box only if it changes meaning (joins customer
   data in, masks, aggregates); otherwise label the arrow ("nightly copy + customer info").
5. Mark every arrow and box that carries personal or confidential data (`sensitive`, `sensitive_data`).
   Note masking, encryption or deletion only if you saw it in code (`controls`).
6. End at every place the data rests or leaves: tables, files, reports, dashboards, outside vendors.

## Stack-specific hints

**Python web (FastAPI / Flask / Django)**: routers are registered in the app factory (`include_router`,
`register_blueprint`, `urls.py`); dependencies (`Depends(...)`) often hold auth checks; models live in
`models.py`; settings in `settings.py` / `config.py`.

**JavaScript / TypeScript**: React routes in `App.tsx` / router config; API clients in `api/`,
`services/`, or hooks (`useQuery`, `fetch`, `axios`); Next.js routes are files under `pages/api` or
`app/**/route.ts`; Express routers are mounted with `app.use('/prefix', router)`, so prefix + route = path.
State stores (Redux, Zustand) are not systems; leave them out of the big picture.

**SQL / data platform (Fabric, Synapse, Databricks, notebooks, dbt)**: stored procedures and notebooks are
the "services"; `CREATE TABLE/VIEW` and `MERGE` show stores and lineage; pipeline JSON (Data Factory,
Fabric pipelines) and schedules show the order. Bronze/silver/gold or raw/staging/curated layers make good
groups. Notebook `%%sql` cells are scanned as SQL.

**AI features**: show the model call as an `ai` box, what is sent to it (`sensitive` if it includes
customer data), what comes back, and whether the result is stored or acted on automatically.

## Before you build: a quick self-check

- Could a manager say, from the big picture alone, what the system does and where data goes?
- Does every arrow say what moves?
- Is every box either `verified` with `files` or honestly `inferred`?
- Are personal data flows red, and outside-company hops visible?
- Is anything in the diagram that you could not point to in code? Remove it or mark it `inferred`.
