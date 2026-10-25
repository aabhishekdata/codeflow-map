# Writing for stakeholders

The map is read by people who do not read code: business owners, risk and audit, leadership. The
technical names stay available behind the **Technical** switch and in each box's details, so the default
text can be fully plain.

## Labels (`label`)

- 2-5 words, named after the **job it does**, not the technology: "Claims service", not "FastAPI app".
- Same name for the same thing in every view.
- Nouns for boxes ("Customer database"); verbs for arrows ("saves the claim").
- No acronyms unless the audience uses them daily (it is fine to say "API" to an IT steering group).

## Arrow labels

Say **what moves** and, if useful, why: "sends sign-in details", "asks for a fraud score", "nightly copy
of claims". Avoid "calls", "uses", "connects to".

## Descriptions (`description`, `why`)

One or two sentences. First what it does, then why it matters. Active voice, present tense.

| Instead of | Write |
|---|---|
| Handles JWT issuance via HS256 | Gives the browser a signed pass so the customer stays signed in. |
| ORM repository layer abstracting persistence | The only code that reads from and writes to the database. |
| Kafka producer emitting to claims.submitted | Sends a message each time a claim is filed so other systems can react. |
| Calls OpenAI chat completions endpoint | Asks an outside AI service to flag claims that look unusual. |
| ETL job, pandas, scheduled via cron | Runs every night to build the daily claims report. |

## Translation glossary

| Technical | Plain |
|---|---|
| API, endpoint, route | entry point, the service's front door |
| Frontend, SPA, client | website / app screens |
| Backend, microservice | service |
| Database, table, schema | database, record store, "Claims table" |
| Cache (Redis) | short-term memory for speed |
| Queue, topic, event bus | message / alert sent to other systems |
| Authentication | checking who you are |
| Authorization, RBAC | checking what you're allowed to do |
| Token, JWT, session | access pass |
| Hashing | scrambling a password so it cannot be read |
| Encryption in transit (TLS) | sent over a secure, private connection |
| Validation | checking the information is complete and sensible |
| ETL, pipeline, job | process that moves and reshapes data |
| Join | combines with … |
| Webhook | automatic notice to/from another system |
| LLM / model call | asks the AI service |
| Retry, fallback | tries again / backup route |
| Log, audit table | record kept for checking later |

## Module and function notes

The module map starts with folder names ("api", "core", "utils"). Your notes turn them into a story.

| Folder name | Better `label` | `description` |
|---|---|---|
| `api` | Web API | Receives every request from the website, checks who is asking and passes the work on. |
| `crud.py` / `repository` | Data access | The only code that reads and writes the database. |
| `core` | Settings and security | Configuration, password hashing and sign-in tokens used by the rest of the code. |
| `utils` | Shared helpers | Small functions used everywhere: dates, formatting, emails. |
| `components/ui` | Screen building blocks | Buttons, menus and forms that every screen reuses. |

For a function, say what it achieves and the decision that matters: "Lets an administrator change a
user's details, refusing an email address someone else already uses", not "Updates user via PATCH and
validates uniqueness".

## Walkthrough text

The walkthrough is the script someone reads aloud in a meeting.

- First step: one sentence on what this view shows, no target.
- Then follow the flow in order, one idea per step, 1-2 sentences each.
- Point out sensitive data and anything leaving the company as you pass it.
- End with what happens last (the result for the customer or business) or with a drill-down.
- 5-10 steps per view. Write `technical` variants only if engineers will also be walked through it.

## Tone for risks and controls

Factual and neutral; describe what the code does, not judgments. "Claim details are sent to an outside
AI vendor; the response is not stored." rather than "Insecure data leak". Only list a control if you saw
it in the code; otherwise raise it as an open question.
