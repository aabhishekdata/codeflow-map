#!/usr/bin/env python3
"""Static, read-only scan of a code repository to ground a flow map in evidence.

Covers Python (incl. Jupyter / Fabric notebooks), JavaScript / TypeScript and SQL.
It never executes project code, never reads .env files and never prints secret values
(environment variables are listed by NAME only).

Usage:
    python scan_repo.py <repo_dir> [--out .codeflow/scan.json]
    python scan_repo.py <repo_dir> --focus login,signin,auth      # where a journey lives
    python scan_repo.py <repo_dir> --trace login_user --depth 3   # who calls what, from one function
    python scan_repo.py <repo_dir> --path src/billing             # limit to a sub-folder

Prints a Markdown summary to stdout and writes the full JSON to --out.
Standard library only (Python 3.8+).
"""
import argparse
import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", ".next",
             ".nuxt", "coverage", ".pytest_cache", ".mypy_cache", ".tox", "site-packages", ".idea",
             ".vscode", "target", "bin", "obj", ".terraform", ".codeflow", "vendor", ".angular"}
SKIP_FILES = re.compile(r"(\.min\.js$|\.map$|\.lock$|package-lock\.json$|yarn\.lock$|pnpm-lock|^\.env)", re.I)
LANG = {".py": "python", ".ipynb": "notebook", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
        ".ts": "ts", ".tsx": "ts", ".sql": "sql", ".vue": "js", ".svelte": "js"}
CONFIG_NAMES = {"package.json", "requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg",
                "docker-compose.yml", "docker-compose.yaml", "Dockerfile", "serverless.yml", "host.json",
                "function.json", "dbt_project.yml", "azure-pipelines.yml", "manage.py", "next.config.js",
                "next.config.mjs", "vite.config.ts", "vite.config.js", "angular.json"}
MAX_BYTES = 1_500_000

# ---------------------------------------------------------------- patterns
PY_ROUTE = re.compile(r"@\s*(\w+)\.(get|post|put|delete|patch|route|api_route|websocket)\(\s*[rfu]?['\"]([^'\"]*)['\"]([^)]*)", re.I)
DJANGO_PATH = re.compile(r"\b(?:re_)?path\(\s*r?['\"]([^'\"]*)['\"]\s*,\s*([\w.]+)")
JS_ROUTE = re.compile(r"\b(app|router|server|api|fastify|r)\.(get|post|put|delete|patch|all)\(\s*['\"`]([^'\"`]+)['\"`]")
JS_USE = re.compile(r"\b(app|router|server)\.use\(\s*['\"`]([^'\"`]+)['\"`]\s*,\s*([\w.]+)")
REACT_ROUTE = re.compile(r"<Route\b[^>]*?\bpath=\{?['\"`]([^'\"`]+)['\"`]")
REACT_ELEM = re.compile(r"(?:element=\{\s*<\s*(\w+)|component=\{\s*(\w+))")
FETCH = re.compile(r"\b(fetch|axios(?:\.(?:get|post|put|delete|patch))?|http\.(?:get|post|put|delete)|api\.(?:get|post|put|delete|patch)|\$http\.(?:get|post))\(\s*['\"`]([^'\"`]+)['\"`]")
PY_HTTP = re.compile(r"\b(requests|httpx|session|client)\.(get|post|put|delete|patch|request)\(\s*[rf]?['\"]([^'\"]+)['\"]")
URL = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\d+)?")
ENV = re.compile(r"os\.environ(?:\.get)?\(?\[?\s*['\"]([A-Z0-9_]+)['\"]|os\.getenv\(\s*['\"]([A-Z0-9_]+)['\"]|process\.env\.([A-Z0-9_]+)|import\.meta\.env\.([A-Z0-9_]+)")
SQL_DDL = re.compile(r"\bCREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:TEMP(?:ORARY)?\s+)?(TABLE|VIEW|MATERIALIZED\s+VIEW|PROC(?:EDURE)?|FUNCTION|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\[\]\"`]+)", re.I)
SQL_WRITE = re.compile(r"\b(INSERT\s+(?:INTO|OVERWRITE(?:\s+TABLE)?)|UPDATE|MERGE\s+INTO|DELETE\s+FROM|TRUNCATE\s+TABLE)\s+([\w.\[\]\"`]+)", re.I)
SQL_READ = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.\[\]\"`]*)", re.I)
SQL_READ_CODE = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.\[\]\"`]*)")  # upper-case only inside code strings
SQL_EXEC = re.compile(r"\bEXEC(?:UTE)?\s+([\w.\[\]]+)", re.I)
DATA_IO = re.compile(r"\b(read_csv|read_excel|read_parquet|read_json|read_sql(?:_query|_table)?|read_table|to_csv|to_excel|to_parquet|to_sql|to_json|saveAsTable|insertInto|spark\.read|spark\.table|spark\.sql|\.write\.(?:mode|format|save|parquet|csv|json|delta)|\.load\(|DeltaTable\.forPath|notebookutils\.\w+|mssparkutils\.\w+|open)\(\s*[rf]?['\"]?([^'\"),]*)", re.I)
ORM = re.compile(r"__tablename__\s*=\s*['\"](\w+)|class\s+(\w+)\((?:[^)]*,\s*)?(?:Base|DeclarativeBase|models\.Model|db\.Model)\s*[,)]|class\s+(\w+)\([^)]*\btable\s*=\s*True[^)]*\)|mongoose\.model\(\s*['\"](\w+)|@Entity\(\s*['\"]?(\w*)|\bmodel\s+(\w+)\s*\{")  # database tables only
MESSAGING = re.compile(r"\b(KafkaProducer|KafkaConsumer|kafka|EventHub\w*|ServiceBus\w*|sqs|sns|pubsub|PubSub|rabbit\w*|amqp|celery|@shared_task|\.delay\(|BlobServiceClient|S3Client|boto3\.client\(\s*['\"](\w+))", re.I)
AI_USE = re.compile(r"\b(openai|anthropic|AzureOpenAI|langchain|llama_index|transformers|bedrock|vertexai|ChatCompletion|chat\.completions|messages\.create|embeddings?)\b")
SCHED = re.compile(r"(@periodic_task|crontab\(|schedule\.every|cron\s*:|\bAPScheduler\b|BackgroundScheduler|@app\.schedule|TimerTrigger|setInterval\(|node-cron|\"schedule\"\s*:)", re.I)
SENSITIVE = re.compile(r"\b(password|passwd|pwd|secret|token|jwt|oauth|otp|ssn|social_security|dob|date_of_birth|"
                       r"email|phone|mobile|address|postcode|zip_code|aadhaar|pan_number|passport|license_number|"
                       r"card_number|cvv|iban|account_number|policy_number|claim_id|salary|medical|diagnosis|"
                       r"customer_id|first_name|last_name|full_name)\b", re.I)
AUTH = re.compile(r"\b(login|log_in|signin|sign_in|logout|authenticate|authorize|auth|session|jwt|oauth|sso|saml|mfa|permission|role|rbac|is_admin)\b", re.I)
PY_MAIN = re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]")
APP_CREATE = re.compile(r"(?<![\w.])(FastAPI|Flask|express|Koa|NestFactory\.create|createServer|func\.FunctionApp|dash\.Dash|gr\.Interface|gr\.Blocks|st\.set_page_config|uvicorn\.run|app\.listen)\s*\(|\bdef\s+(lambda_handler|main)\s*\(")
APIROUTER_PREFIX = re.compile(r"(\w+)\s*=\s*APIRouter\(\s*[^)]*?prefix\s*=\s*['\"]([^'\"]+)['\"]")
TEST_DIRS = {"tests", "test", "__tests__", "e2e", "cypress", "playwright", "spec", "testing"}
TEST_FILE = re.compile(r"(^test_.*\.py$|_test\.py$|^conftest\.py$|\.(test|spec)\.[jt]sx?$)")
PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([\w*, ()]+)|import\s+([\w., ]+))", re.M)
JS_IMPORT = re.compile(r"(?:import\s[^'\"]*?from\s*|import\s*\(\s*|require\(\s*|export\s[^'\"]*?from\s*)['\"]([^'\"]+)['\"]")
SQL_SKIP = {"select", "the", "a", "an", "where", "dual", "unnest", "lateral", "values", "json_table", "openjson", "string_split", "generate_series", "information_schema"}


def rel(p, root):
    return str(Path(p).relative_to(root)).replace(os.sep, "/")


def read_text(path):
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        txt = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return None
    if path.suffix == ".ipynb":
        try:
            nb = json.loads(txt)
            cells = []
            for c in nb.get("cells", []):
                src = c.get("source", "")
                src = "".join(src) if isinstance(src, list) else src
                if c.get("cell_type") == "code":
                    # Fabric/Synapse %%sql magic cells are SQL
                    cells.append(src)
                else:
                    cells.append("\n" * src.count("\n"))
                cells.append("")
            return "\n".join(cells)
        except (ValueError, AttributeError):
            return None
    return txt


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


INCLUDE_TESTS = False


def walk(root, sub=None):
    base = root / sub if sub else root
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")
                  and (INCLUDE_TESTS or d.lower() not in TEST_DIRS)]
        for fn in fns:
            if SKIP_FILES.search(fn) or (not INCLUDE_TESTS and TEST_FILE.search(fn)):
                continue
            yield Path(dp) / fn


def module_area(path, depth=2):
    parts = path.split("/")
    if len(parts) <= 1:
        return "(root)"
    return "/".join(parts[:min(depth, len(parts) - 1)])


def adaptive_areas(paths, max_share=0.25, max_depth=5):
    """Group files into folder 'areas', splitting any folder that holds too large a share
    of the code so the dependency picture has meaningful parts (Emerge-style)."""
    def key(p, d):
        return module_area(p, d)
    depth_of = {p: 1 for p in paths}
    total = max(1, len(paths))
    for _ in range(max_depth):
        groups = defaultdict(list)
        for p in paths:
            groups[key(p, depth_of[p])].append(p)
        changed = False
        for g, members in groups.items():
            big = len(members) / total > max_share or len(members) >= 15
            if not big or len(groups) >= 20:
                continue
            d = depth_of[members[0]]
            nd = d + 1
            while nd <= max_depth and len({key(p, nd) for p in members}) < 2:
                nd += 1   # walk through single-child folders like backend/app
            if nd <= max_depth:
                for p in members:
                    depth_of[p] = nd
                changed = True
        if not changed:
            break
    return {p: key(p, depth_of[p]) for p in paths}


# ---------------------------------------------------------------- scan
def scan(root, sub=None, area_depth=0):
    R = {"root": str(root), "languages": Counter(), "config_files": [], "frameworks": set(), "entry_points": [],
         "routes": [], "frontend_routes": [], "outbound_calls": [], "external_hosts": Counter(), "env_vars": set(),
         "sql_objects": [], "table_writes": [], "table_reads": Counter(), "data_io": [], "orm_models": [],
         "messaging": [], "ai_usage": [], "schedulers": [], "auth_files": Counter(), "sensitive_fields": Counter(),
         "sensitive_files": Counter(), "imports": [], "file_count": 0}
    files = list(walk(root, sub))
    py_modules = {}
    js_files = set()
    for f in files:
        r = rel(f, root)
        if f.suffix == ".py":
            mod = r[:-3].replace("/", ".")
            if mod.endswith(".__init__"):
                mod = mod[:-9]
            py_modules[mod] = r
        if f.suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"):
            js_files.add(r)

    for f in files:
        r = rel(f, root)
        if f.name in CONFIG_NAMES:
            R["config_files"].append(r)
            _frameworks(f, R)
        lang = LANG.get(f.suffix.lower())
        if not lang:
            continue
        text = read_text(f)
        if text is None:
            continue
        R["file_count"] += 1
        R["languages"][lang] += 1
        _scan_text(text, r, lang, R)
        if lang in ("python", "notebook"):
            _py_imports(text, r, py_modules, R)
        elif lang in ("js", "ts"):
            _js_imports(text, r, js_files, R)
        # Next.js file-system routes
        m = re.search(r"(?:^|/)pages/api/(.+)\.(?:js|ts)x?$", r) or re.search(r"(?:^|/)app/(.+)/route\.(?:js|ts)$", r)
        if m:
            R["routes"].append({"method": "ANY", "path": "/" + m.group(1).replace("index", "").rstrip("/"), "file": r, "line": 1, "framework": "next.js"})

    # module dependency summary (folder level, Emerge-style)
    code_paths = [rel(f, root) for f in files if LANG.get(f.suffix.lower())]
    if area_depth:
        amap = {p: module_area(p, area_depth) for p in code_paths}
    else:
        amap = adaptive_areas(code_paths)
    edges = Counter()
    for a, b in R["imports"]:
        A, B = amap.get(a, module_area(a)), amap.get(b, module_area(b))
        if A != B:
            edges[(A, B)] += 1
    areas = Counter(amap.values())
    R["areas"] = [{"area": a, "files": n} for a, n in areas.most_common()]
    R["area_dependencies"] = [{"from": a, "to": b, "imports": n} for (a, b), n in edges.most_common(80)]
    # tidy for JSON
    out = {}
    for k, v in R.items():
        if isinstance(v, Counter):
            out[k] = dict(v.most_common(60))
        elif isinstance(v, set):
            out[k] = sorted(v)
        elif k == "imports":
            out["import_edge_count"] = len(v)
        else:
            out[k] = v
    for k in ("routes", "frontend_routes", "outbound_calls", "data_io", "table_writes", "sql_objects", "messaging", "ai_usage", "schedulers", "entry_points", "orm_models"):
        out[k] = _dedupe(out[k])[:300]
    return out


def _dedupe(items):
    seen, res = set(), []
    for it in items:
        key = json.dumps(it, sort_keys=True)
        if key not in seen:
            seen.add(key)
            res.append(it)
    return res


def _frameworks(f, R):
    txt = read_text(f) or ""
    low = txt.lower()
    names = ["fastapi", "flask", "django", "streamlit", "dash", "gradio", "sqlalchemy", "pandas", "pyspark", "polars",
             "celery", "kafka", "azure-functions", "boto3", "openai", "anthropic", "langchain", "pydantic",
             "express", "next", "react", "vue", "angular", "nestjs", "@nestjs/core", "koa", "fastify", "prisma",
             "mongoose", "sequelize", "typeorm", "axios", "jsonwebtoken", "passport", "next-auth", "dbt", "msal",
             "@azure/msal-browser", "redux", "graphql", "apollo", "socket.io", "kafkajs", "azure-eventhub", "semantic-kernel"]
    if f.name == "package.json":
        try:
            pj = json.loads(txt)
            deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
            for d in deps:
                if d.lower() in names or d.lower().split("/")[-1] in names:
                    R["frameworks"].add(d)
            for k in ("main", "module"):
                if pj.get(k):
                    R["entry_points"].append({"kind": f"package.json {k}", "file": pj[k], "line": 0})
            for s, cmd in (pj.get("scripts") or {}).items():
                if s in ("start", "dev", "serve"):
                    R["entry_points"].append({"kind": f"npm run {s}", "file": rel(f, Path(R['root'])), "line": 0, "detail": cmd[:120]})
        except ValueError:
            pass
        return
    for n in names:
        if re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", low):
            R["frameworks"].add(n)


def _scan_text(text, r, lang, R):
    is_sql = lang == "sql"
    is_code = lang in ("python", "notebook", "js", "ts")
    if is_code:
        for m in APP_CREATE.finditer(text):
            R["entry_points"].append({"kind": (m.group(1) or m.group(2)), "file": r, "line": line_of(text, m.start())})
    if lang in ("python", "notebook"):
        for m in PY_MAIN.finditer(text):
            R["entry_points"].append({"kind": "__main__", "file": r, "line": line_of(text, m.start())})
        prefixes = {mm.group(1): mm.group(2) for mm in APIROUTER_PREFIX.finditer(text)}
        for m in PY_ROUTE.finditer(text):
            meth = m.group(2).upper()
            if meth == "ROUTE" or meth == "API_ROUTE":
                mm = re.search(r"methods\s*=\s*\[([^\]]*)\]", m.group(4))
                meth = ",".join(x.strip(" '\"").upper() for x in mm.group(1).split(",")) if mm else "GET"
            handler = _next_def(text, m.end())
            path = prefixes.get(m.group(1), "").rstrip("/") + m.group(3) if m.group(1) in prefixes else m.group(3)
            R["routes"].append({"method": meth, "path": path or "/", "file": r, "line": line_of(text, m.start()), "handler": handler})
        for m in DJANGO_PATH.finditer(text):
            R["routes"].append({"method": "ANY", "path": "/" + m.group(1), "file": r, "line": line_of(text, m.start()), "handler": m.group(2), "framework": "django"})
        for m in PY_HTTP.finditer(text):
            R["outbound_calls"].append({"call": f"{m.group(1)}.{m.group(2)}", "target": m.group(3)[:160], "file": r, "line": line_of(text, m.start())})
    if lang in ("js", "ts"):
        for m in JS_ROUTE.finditer(text):
            R["routes"].append({"method": m.group(2).upper(), "path": m.group(3), "file": r, "line": line_of(text, m.start())})
        for m in JS_USE.finditer(text):
            R["routes"].append({"method": "MOUNT", "path": m.group(2), "file": r, "line": line_of(text, m.start()), "handler": m.group(3)})
        for m in REACT_ROUTE.finditer(text):
            em = REACT_ELEM.search(text, m.end(), m.end() + 200)
            comp = (em.group(1) or em.group(2)) if em else ""
            R["frontend_routes"].append({"path": m.group(1), "component": comp, "file": r, "line": line_of(text, m.start())})
        for m in FETCH.finditer(text):
            R["outbound_calls"].append({"call": m.group(1), "target": m.group(2)[:160], "file": r, "line": line_of(text, m.start())})
    if is_code or is_sql:
        for m in URL.finditer(text):
            host = m.group(1).lower()
            if not re.search(r"(w3\.org|schemas\.|example\.(com|org)|localhost|github\.com/.+/issues|json-schema\.org|mozilla\.org|npmjs)", host):
                R["external_hosts"][host] += 1
        for m in ENV.finditer(text):
            R["env_vars"].add(next(g for g in m.groups() if g))
        for m in MESSAGING.finditer(text):
            R["messaging"].append({"hint": m.group(1)[:40], "file": r, "line": line_of(text, m.start())})
        for m in AI_USE.finditer(text):
            R["ai_usage"].append({"hint": m.group(1), "file": r, "line": line_of(text, m.start())})
        for m in SCHED.finditer(text):
            R["schedulers"].append({"hint": m.group(1)[:40], "file": r, "line": line_of(text, m.start())})
        for m in ORM.finditer(text):
            name = next((g for g in m.groups() if g), None)
            if name:
                R["orm_models"].append({"model": name, "file": r, "line": line_of(text, m.start())})
        auth_hits = len(AUTH.findall(text))
        if auth_hits >= 3:
            R["auth_files"][r] += auth_hits
        for m in SENSITIVE.finditer(text):
            R["sensitive_fields"][m.group(1).lower()] += 1
            R["sensitive_files"][r] += 1
    if is_code:
        for m in DATA_IO.finditer(text):
            fn = m.group(1)
            if fn == "open" and not re.search(r"\.(csv|xlsx?|json|parquet|txt|xml)", m.group(2) or "", re.I):
                continue
            R["data_io"].append({"op": fn, "arg": (m.group(2) or "")[:120], "file": r, "line": line_of(text, m.start())})
    # SQL anywhere: .sql files, and SQL strings inside code / notebooks
    if is_sql or re.search(r"\b(SELECT|INSERT|MERGE|CREATE\s+TABLE|UPDATE)\b", text):
        for m in SQL_DDL.finditer(text):
            R["sql_objects"].append({"type": re.sub(r"\s+", " ", m.group(1).upper()), "name": _clean(m.group(2)), "file": r, "line": line_of(text, m.start())})
        for m in SQL_WRITE.finditer(text):
            if not is_sql and m.group(1).upper() == "UPDATE" and not re.search(r"\bSET\b", text[m.end():m.end() + 200], re.I):
                continue
            R["table_writes"].append({"op": re.sub(r"\s+", " ", m.group(1).upper()), "table": _clean(m.group(2)), "file": r, "line": line_of(text, m.start())})
        for m in (SQL_READ if is_sql else SQL_READ_CODE).finditer(text):
            t = _clean(m.group(1))
            if t.lower() not in SQL_SKIP and not t[0].isdigit() and (is_sql or "." in t or "_" in t or t.isupper()):
                R["table_reads"][t] += 1
        for m in SQL_EXEC.finditer(text):
            R["table_writes"].append({"op": "EXEC", "table": _clean(m.group(1)), "file": r, "line": line_of(text, m.start())})


def _clean(name):
    return re.sub(r"[\[\]\"`]", "", name).strip(".;,()")


def _next_def(text, pos):
    m = re.compile(r"(?:async\s+)?def\s+(\w+)").search(text, pos, pos + 600)
    return m.group(1) if m else ""


def _py_imports(text, r, py_modules, R):
    pkg = r.rsplit("/", 1)[0].replace("/", ".") if "/" in r else ""
    for m in PY_IMPORT.finditer(text):
        targets = []
        if m.group(1) is not None:
            mod = m.group(1)
            if mod.startswith("."):
                dots = len(mod) - len(mod.lstrip("."))
                base = pkg.split(".") if pkg else []
                base = base[:len(base) - (dots - 1)] if dots > 1 else base
                mod = ".".join([p for p in base + [mod.lstrip(".")] if p])
            names = [n.strip(" ()") for n in m.group(2).split(",")]
            targets = [mod + "." + n for n in names if n and n != "*"] + [mod]
        else:
            targets = [t.strip().split(" as ")[0] for t in m.group(3).split(",")]
        for t in targets:
            parts = t.split(".")
            for i in range(len(parts), 0, -1):
                cand = ".".join(parts[:i])
                hit = py_modules.get(cand) or next((v for k, v in py_modules.items() if k.endswith("." + cand)), None) if i > 0 else None
                if hit:
                    if hit != r:
                        R["imports"].append((r, hit))
                    break


def _js_imports(text, r, js_files, R):
    d = r.rsplit("/", 1)[0] if "/" in r else ""
    for m in JS_IMPORT.finditer(text):
        spec = m.group(1)
        if spec.startswith("."):
            path = os.path.normpath(os.path.join(d, spec)).replace(os.sep, "/")
        elif spec.startswith("@/") or spec.startswith("~/"):
            # alias for the nearest src/ folder (works for monorepos like frontend/src)
            src = r[:r.index("src/") + 4] if "src/" in r else "src/"
            path = os.path.normpath(src + spec[2:]).replace(os.sep, "/")
        else:
            continue
        for cand in [path] + [path + e for e in (".ts", ".tsx", ".js", ".jsx", ".vue", "/index.ts", "/index.tsx", "/index.js")]:
            if cand in js_files:
                if cand != r:
                    R["imports"].append((r, cand))
                break


# ---------------------------------------------------------------- focus & trace
def focus(root, terms, sub=None, limit=80):
    rx = re.compile("|".join(re.escape(t) for t in terms), re.I)
    hits = []
    for f in walk(root, sub):
        if not LANG.get(f.suffix.lower()):
            continue
        text = read_text(f)
        if not text:
            continue
        r = rel(f, root)
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append({"file": r, "line": i, "text": line.strip()[:140]})
    by_file = Counter(h["file"] for h in hits)
    return {"terms": terms, "files_ranked": [{"file": f, "hits": n} for f, n in by_file.most_common(40)], "hits": hits[:limit]}


class _PyIndex(ast.NodeVisitor):
    def __init__(self):
        self.defs = defaultdict(list)   # name -> [(file, line, node)]

    def index(self, root, sub=None):
        for f in walk(root, sub):
            if f.suffix not in (".py", ".ipynb"):
                continue
            text = read_text(f)
            if not text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            r = rel(f, root)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs[node.name].append((r, node.lineno, node))
                elif isinstance(node, ast.ClassDef):
                    self.defs[node.name].append((r, node.lineno, node))
        return self


def _call_names(fn_node):
    names = []
    for n in ast.walk(fn_node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.append((f.id, n.lineno))
            elif isinstance(f, ast.Attribute):
                names.append((f.attr, n.lineno))
    return names


JS_FN = re.compile(r"(?:function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{)", re.M)
JS_CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
JS_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "new", "await", "super", "import", "require"}


def _js_index(root, sub=None):
    defs = defaultdict(list)
    for f in walk(root, sub):
        if f.suffix not in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            continue
        text = read_text(f)
        if not text:
            continue
        r = rel(f, root)
        for m in JS_FN.finditer(text):
            name = next((g for g in m.groups() if g), None)
            if not name or name in JS_KEYWORDS:
                continue
            body = _brace_body(text, m.end())
            defs[name].append((r, line_of(text, m.start()), body, line_of(text, m.start())))
    return defs


def _brace_body(text, pos):
    i = text.find("{", pos, pos + 400)
    if i < 0:
        end = text.find("\n", pos)
        return text[pos:end if end > 0 else pos + 200]
    depth = 0
    for j in range(i, min(len(text), i + 20000)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return text[i:i + 2000]


def trace(root, start, depth=3, sub=None):
    """Approximate downstream call tree from a function name (code2flow-style, best effort)."""
    py = _PyIndex().index(root, sub).defs
    js = _js_index(root, sub)
    lines = []
    seen = set()

    def visit(name, d, prefix):
        targets = [("py", t) for t in py.get(name, [])] + [("js", t) for t in js.get(name, [])]
        if not targets:
            return
        for kind, t in targets[:3]:
            key = (name, t[0], t[1])
            loc = f"{t[0]}:{t[1]}"
            if key in seen:
                lines.append(f"{prefix}{name}()  [{loc}]  (already shown)")
                continue
            seen.add(key)
            lines.append(f"{prefix}{name}()  [{loc}]")
            if d >= depth:
                continue
            if kind == "py":
                calls = _call_names(t[2])
            else:
                calls = [(m.group(1), 0) for m in JS_CALL.finditer(t[2]) if m.group(1) not in JS_KEYWORDS]
            done = set()
            for c, _ in calls:
                if c in done or c == name or c not in py and c not in js:
                    continue
                done.add(c)
                visit(c, d + 1, prefix + "  ")

    visit(start, 0, "")
    callers = []
    for name, defs in py.items():
        for f, ln, node in defs:
            if any(c == start for c, _ in _call_names(node)) and name != start:
                callers.append(f"{name}()  [{f}:{ln}]")
    for name, defs in js.items():
        for f, ln, body, _ in defs:
            if name != start and re.search(r"\b" + re.escape(start) + r"\s*\(", body):
                callers.append(f"{name}()  [{f}:{ln}]")
    return {"start": start, "depth": depth, "tree": lines, "called_by": sorted(set(callers))[:40],
            "note": "Best-effort static trace: matches functions by name, so dynamic dispatch, decorators "
                    "and same-named functions can create false links. Confirm by reading the code."}


# ---------------------------------------------------------------- output
def summary_md(R):
    o = []
    add = o.append
    add(f"# Repo scan: {R['root']}")
    add(f"Files scanned: {R['file_count']} | languages: " + ", ".join(f"{k} {v}" for k, v in R["languages"].items()))
    if R["frameworks"]:
        add("Frameworks/libraries: " + ", ".join(R["frameworks"]))

    def section(title, items, fmt, n=25):
        if items:
            add(f"\n## {title} ({len(items)})")
            for it in items[:n]:
                add("- " + fmt(it))
            if len(items) > n:
                add(f"- ... {len(items) - n} more in the JSON")
    section("Entry points", R["entry_points"], lambda e: f"{e['kind']} - {e['file']}:{e['line']}" + (f" ({e['detail']})" if e.get('detail') else ""), 15)
    section("Areas (folders) by size", R["areas"], lambda a: f"{a['area']} ({a['files']} files)", 20)
    section("Area dependencies (who imports whom)", R["area_dependencies"], lambda d: f"{d['from']} -> {d['to']} ({d['imports']})", 30)
    section("Backend routes / endpoints", R["routes"], lambda r: f"{r['method']} {r['path']} - {r['file']}:{r['line']}" + (f" -> {r['handler']}" if r.get('handler') else ""), 40)
    section("Frontend routes (screens)", R["frontend_routes"], lambda r: f"{r['path']} -> {r.get('component') or '?'} - {r['file']}:{r['line']}", 25)
    section("Outbound calls (frontend->API, service->service)", R["outbound_calls"], lambda c: f"{c['call']} {c['target']} - {c['file']}:{c['line']}", 30)
    if R["external_hosts"]:
        add("\n## External hosts referenced\n- " + "\n- ".join(f"{h} ({n})" for h, n in list(R["external_hosts"].items())[:25]))
    section("Database objects defined", R["sql_objects"], lambda s: f"{s['type']} {s['name']} - {s['file']}:{s['line']}", 30)
    section("ORM table models", R["orm_models"], lambda m: f"{m['model']} - {m['file']}:{m['line']}", 25)
    section("Tables written / procedures executed", R["table_writes"], lambda w: f"{w['op']} {w['table']} - {w['file']}:{w['line']}", 30)
    if R["table_reads"]:
        add("\n## Tables read (top)\n- " + "\n- ".join(f"{t} ({n})" for t, n in list(R["table_reads"].items())[:30]))
    section("File / dataframe reads & writes", R["data_io"], lambda d: f"{d['op']} {d['arg']} - {d['file']}:{d['line']}", 30)
    section("Messaging / queues / cloud storage", R["messaging"], lambda m: f"{m['hint']} - {m['file']}:{m['line']}", 15)
    section("AI / model usage", R["ai_usage"], lambda m: f"{m['hint']} - {m['file']}:{m['line']}", 15)
    section("Scheduled jobs", R["schedulers"], lambda m: f"{m['hint']} - {m['file']}:{m['line']}", 10)
    if R["env_vars"]:
        add("\n## Config / environment variable NAMES (values not read)\n" + ", ".join(R["env_vars"][:60]))
    if R["auth_files"]:
        add("\n## Files most concerned with login / access\n- " + "\n- ".join(f"{f} ({n})" for f, n in list(R["auth_files"].items())[:15]))
    if R["sensitive_fields"]:
        add("\n## Sensitive-looking field names (count)\n" + ", ".join(f"{k} {v}" for k, v in list(R["sensitive_fields"].items())[:30]))
    add("\nNote: regex/AST based and approximate. Treat as leads; confirm by reading the files.")
    return "\n".join(o)


def main(argv=None):
    # Windows consoles may not be UTF-8; never crash on an emoji in a label
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--out", default=None, help="JSON output path (default <repo>/.codeflow/scan.json)")
    ap.add_argument("--path", default=None, help="only scan this sub-folder (relative to repo)")
    ap.add_argument("--focus", default=None, help="comma-separated words, e.g. login,signin,auth")
    ap.add_argument("--trace", default=None, help="function name to trace calls from")
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--include-tests", action="store_true", help="also scan test files (skipped by default)")
    ap.add_argument("--area-depth", type=int, default=0, help="fixed folder depth for grouping files into areas (default: adaptive)")
    a = ap.parse_args(argv)
    global INCLUDE_TESTS
    INCLUDE_TESTS = a.include_tests
    root = Path(a.repo).resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}")
        return 2
    if a.focus:
        res = focus(root, [t.strip() for t in a.focus.split(",") if t.strip()], a.path)
        print(f"# Focus: {', '.join(res['terms'])}\n\n## Files ranked by matches")
        for f in res["files_ranked"]:
            print(f"- {f['file']} ({f['hits']})")
        print("\n## First matches")
        for h in res["hits"]:
            print(f"- {h['file']}:{h['line']}  {h['text']}")
        return 0
    if a.trace:
        res = trace(root, a.trace, a.depth, a.path)
        if not res["tree"]:
            print(f"No function named '{a.trace}' found. Try --focus {a.trace} to locate it.")
            return 1
        print(f"# Call trace from {a.trace} (depth {a.depth})\n")
        print("\n".join(res["tree"]))
        if res["called_by"]:
            print("\n## Called by\n- " + "\n- ".join(res["called_by"]))
        print("\n" + res["note"])
        return 0
    R = scan(root, a.path, a.area_depth)
    out = Path(a.out) if a.out else root / ".codeflow" / "scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(R, indent=1, default=list), encoding="utf-8")
    print(summary_md(R))
    print(f"\nFull results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
