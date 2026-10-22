# codeflow-map: a GitHub Copilot agent skill

Turns a codebase into one interactive HTML file that explains how it works to non-technical
stakeholders: big picture, step-by-step journeys (for example, "user signs in") and data flow, with
drill-down, zoom, drag, click-for-details, a Simple/Technical switch, sensitive-data highlighting and a
presenter walkthrough.

## Install

Copy the whole `codeflow-map` folder (keep its sub-folders) to one of:

| Location | Who gets it |
|---|---|
| `<your repo>/.github/skills/codeflow-map/` | Everyone who opens that repository |
| `~/.copilot/skills/codeflow-map/` (Windows: `%USERPROFILE%\.copilot\skills\codeflow-map\`) | Just you, in every repository |

Requirements: VS Code with GitHub Copilot in **Agent** mode (choose a Claude model), a VS Code version
that supports Agent Skills, and Python 3.8+ on the machine. No pip installs. Building needs no internet; viewing the default build
needs access to cdn.jsdelivr.net (see *Delivery modes*).
Reload VS Code after copying the folder; `codeflow-map` then appears in the `/` menu of Copilot Chat.

## Use

In Copilot Chat (Agent mode), open the repository and ask, for example:

- "Use codeflow-map to show how this repo works, for business stakeholders."
- "Map what happens when a user logs in."
- "Show where customer personal data flows in this project."

or type `/codeflow-map`. Copilot asks which views you want, scans the repo, reads the relevant code,
writes `.codeflow/flowmap.json` and builds `docs/codeflow/<repo>-flow-map.html`. Approve the Python
terminal commands when prompted. Open the HTML by double-clicking it.

## Delivery modes

| Build | Size | Opens without internet? | When to use |
|---|---|---|---|
| default | ~0.1 MB | No: loads Mermaid 11.17.2 from cdn.jsdelivr.net (integrity-checked) | Normal use; easy to email or upload |
| `--offline` | ~3.6 MB | Yes | The CDN is blocked at work, or the file is viewed offline |
| `--split` | 3 files | Yes | Offline, but a mail filter rejects large HTML files |

If a default build shows "The diagram library could not be loaded", ask Copilot to rebuild with `--offline`.

## In the map

- **Tabs**: Big picture / journeys / data flow. **Double-click** a box to see inside; breadcrumbs go back.
- **Drag** to move, **scroll or pinch** to zoom, **⤢** to fit, mini-map bottom-right to jump around.
- **Click** any box, arrow or area for a plain-English explanation, data involved, safeguards and source files.
- **Simple / Technical** switches labels between business names and code names.
- **🔒 Sensitive data** highlights flows carrying personal or confidential data.
- **▶ Walk me through** is a step-by-step presenter mode (arrow keys / space to advance).
- **More**: About (scope, assumptions, open questions), full screen, print/PDF, SVG, Mermaid code.

## Files

```
codeflow-map/
├── SKILL.md                       instructions Copilot follows
├── scripts/scan_repo.py           read-only static scan (Python, JS/TS, SQL, notebooks)
├── scripts/build_flowmap.py       validates the spec and builds the offline HTML
├── assets/viewer.html             the interactive viewer template
├── assets/vendor/mermaid.min.js   Mermaid 11 (MIT licence, see MERMAID-LICENSE.txt)
├── references/                    spec schema, analysis playbook, plain-language guide
└── examples/sample-flowmap.json   complete example (insurance claims portal)
```

Try it without Copilot: `python scripts/build_flowmap.py examples/sample-flowmap.json --out sample.html`
(add `--offline` for the self-contained version).

## Privacy

Everything runs locally. The scanner never executes project code, skips `.env` files and reports
environment variables by name only. The HTML contains only what is written in the spec. Its Content
Security Policy blocks all data requests; the only thing it may download is the pinned Mermaid library
from cdn.jsdelivr.net (default build), and an `--offline` build downloads nothing. The builder refuses specs that appear to embed
secrets and warns about anything that looks like personal data.

## Licence

MIT, see [LICENSE](LICENSE). The bundled Mermaid library keeps its own MIT licence
([assets/vendor/MERMAID-LICENSE.txt](assets/vendor/MERMAID-LICENSE.txt)).
