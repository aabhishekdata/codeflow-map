#!/usr/bin/env python3
"""codeflow-map v3: the code graph behind the map.

Used by analyze_modules.py. Standard library only (Python 3.8+); no network, never executes project code.

- FactCache        per-file parse results keyed by content hash, so re-runs only parse changed files
- scan_rationale   WHY / NOTE / TODO / FIXME / HACK ... comments and ADR / RFC references in code
- scan_docs        README / docs / ADR Markdown linked to the files, modules, functions and classes they mention
- load_graphify    reads graphify-out/graph.json (if present) for languages codeflow-map does not parse itself
- louvain          community detection (modularity, Louvain method), deterministic
- build_graph      typed graph with EXTRACTED / INFERRED provenance, communities, most-connected items,
                   surprising links and suggested questions; written into modules.json and .codeflow/graph.json
"""
import gzip
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

CACHE_VERSION = "codeflow-3.0"
DOC_EXT = {".md", ".mdx", ".rst"}
CODE_EXT_GRAPHIFY = {".java", ".kt", ".kts", ".scala", ".go", ".rs", ".cs", ".vb", ".fs", ".cpp", ".cc", ".cxx", ".c", ".h",
                     ".hpp", ".rb", ".php", ".swift", ".m", ".mm", ".dart", ".lua", ".r", ".jl", ".ex", ".exs", ".erl",
                     ".hs", ".ml", ".clj", ".groovy", ".pl", ".pas", ".tf", ".sh", ".ps1", ".zig", ".nim", ".sol"}

# ---------------------------------------------------------------------------------------------- cache


class FactCache:
    """Parse results per file, keyed by a hash of the file's content and the analysis settings."""

    def __init__(self, path, settings, enabled=True):
        self.path, self.enabled = Path(path), enabled
        self.settings = hashlib.sha1((CACHE_VERSION + json.dumps(settings, sort_keys=True)).encode()).hexdigest()[:12]
        self.data, self.hits, self.misses, self.dirty = {}, 0, 0, False
        if enabled and self.path.is_file():
            try:
                with gzip.open(str(self.path), "rt", encoding="utf-8") as f:
                    raw = json.load(f)
                if raw.get("settings") == self.settings:
                    self.data = raw.get("files", {})
            except (OSError, ValueError, EOFError):
                self.data = {}

    @staticmethod
    def digest(text):
        return hashlib.sha1((text or "").encode("utf-8", "replace")).hexdigest()

    def get(self, rel, text):
        if not self.enabled:
            return None
        hit = self.data.get(rel)
        if hit and hit.get("h") == self.digest(text):
            self.hits += 1
            return hit["f"]
        self.misses += 1
        return None

    def put(self, rel, text, facts):
        if self.enabled:
            # an untouched copy: the analysis later adds per-run results (links, scores) to the live object
            self.data[rel] = {"h": self.digest(text), "f": json.loads(json.dumps(facts))}
            self.dirty = True

    def save(self, keep):
        if not self.enabled:
            return
        keep = set(keep)
        stale = [k for k in self.data if k not in keep]
        for k in stale:
            del self.data[k]
        if not (self.dirty or stale):
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with gzip.open(str(tmp), "wt", encoding="utf-8") as f:
            json.dump({"settings": self.settings, "files": self.data}, f, separators=(",", ":"))
        os.replace(str(tmp), str(self.path))


# ---------------------------------------------------------------------------------------------- rationale

WHY_TAGS = {"WHY", "NOTE", "IMPORTANT", "DECISION", "SECURITY", "REF", "RATIONALE"}
ISSUE_TAGS = {"TODO", "FIXME", "HACK", "XXX", "BUG", "WORKAROUND", "DEPRECATED"}
TAG_RE = re.compile(r"(?:#|//|/\*+|^\s*\*|--|\"\"\"|''')\s*(WHY|NOTE|IMPORTANT|DECISION|SECURITY|RATIONALE|TODO|FIXME|HACK|XXX|BUG|WORKAROUND|DEPRECATED)\b"
                    r"(?:\([^)]{0,40}\))?\s*[:\-–—]?\s*(.*)$")
REF_RE = re.compile(r"\b(ADR[-_ ]?\d{1,4}|RFC[-_ ]?\d{2,5}|(?:docs|adr|decisions?)/[\w./-]+\.md)\b", re.I)
COMMENT_START = re.compile(r"^\s*(#|//|\*|/\*|--)")


def scan_rationale(text, redact=None):
    """Tagged comments and ADR / RFC references. Returns [{line, tag, text, refs}]."""
    out = []
    lines = (text or "").split("\n")
    for i, ln in enumerate(lines):
        if len(ln) > 400:
            continue
        m = TAG_RE.search(ln)
        refs = []
        if m:
            tag, body = m.group(1), m.group(2).strip().rstrip("*/").strip()
            j = i + 1   # continuation lines of the same comment
            while body and j < len(lines) and j <= i + 3 and COMMENT_START.match(lines[j]) and not TAG_RE.search(lines[j]):
                more = re.sub(r"^\s*(#|//|\*|/\*|--)\s?", "", lines[j]).strip().rstrip("*/").strip()
                if not more:
                    break
                body += " " + more
                j += 1
            refs = [r.group(1) for r in REF_RE.finditer(ln + " " + body)]
        elif COMMENT_START.match(ln) and REF_RE.search(ln):
            tag, body = "REF", re.sub(r"^\s*(#|//|\*|/\*|--)\s?", "", ln).strip().rstrip("*/").strip()
            refs = [r.group(1) for r in REF_RE.finditer(ln)]
        else:
            continue
        body = re.sub(r"\s+", " ", body)[:220]
        if redact:
            body = redact(body)
        if not body and not refs:
            continue
        out.append({"line": i + 1, "tag": tag.upper(), "text": body, "refs": refs[:4]})
        if len(out) >= 300:
            break
    return out


def note_group(tag):
    return "issue" if tag in ISSUE_TAGS else "why"


# ---------------------------------------------------------------------------------------------- docs

HEADING_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
PATH_TOKEN = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|ipynb|ts|tsx|js|jsx|mjs|cjs|vue|svelte|sql|prisma|java|go|cs|rb|php|kt|rs))\b")
DIR_TOKEN = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+)/?(?![\w/.-])")
TICK_TOKEN = re.compile(r"`([A-Za-z_$][\w$.]*)(?:\(\))?`")
IDENT_TOKEN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{5,})\b")
COMMON_WORDS = {"default", "return", "string", "number", "object", "function", "boolean", "import", "export", "public",
                "private", "static", "config", "settings", "request", "response", "session", "service", "client",
                "server", "update", "delete", "create", "select", "insert", "result", "values", "options", "params",
                "handler", "handlers", "router", "routes", "models", "schema", "schemas", "utils", "helpers", "logger",
                "context", "message", "messages", "status", "errors", "events", "global", "module", "modules", "package",
                "version", "example", "examples", "testing", "pytest", "python", "typescript", "javascript", "docker",
                "github", "readme", "license", "install", "deploy", "backend", "frontend", "database", "migrations"}


def is_doc(rel):
    p = rel.lower()
    name = p.rsplit("/", 1)[-1]
    if Path(p).suffix not in DOC_EXT or name.startswith(("license", "copying", "code_of_conduct", "changelog", "security")):
        return False
    return True


def doc_kind(rel):
    p = rel.lower()
    if re.search(r"(^|/)(adr|adrs|decisions?|architecture[-_ ]decision)", p) or re.match(r".*/\d{3,4}[-_].+\.md$", p):
        return "adr"
    if p.rsplit("/", 1)[-1].startswith("readme"):
        return "readme"
    return "doc"


def scan_docs(root, walk, A, max_docs=400):
    """Link documentation to code. Returns [{path, kind, title, links: [{key, type, section, line, prov}]}]."""
    files = A.files
    file_set = set(files)
    by_base = defaultdict(list)
    for r in files:
        by_base[r.rsplit("/", 1)[-1]].append(r)
    mod_paths = {M["path"]: M["id"] for M in A.modules.values() if M["path"] not in ("(root)", "")}
    names = defaultdict(set)    # unqualified name -> keys
    quals = defaultdict(set)    # Class.method / qual -> keys
    for key, fn in A.fns.items():
        if A.facts.get(fn["file"], {}).get("lang") is None or fn["file"] in A.generated:
            continue
        quals[fn["qual"]].add(key)
        names[fn["name"]].add(key)
    for ckey, c in A.cls_index.items():
        if c["file"] in A.generated:
            continue
        names[c["name"]].add("c:" + ckey)
        quals[c["name"]].add("c:" + ckey)
    docs = []
    for p in walk:
        rel = str(Path(p).relative_to(root)).replace(os.sep, "/")
        if not is_doc(rel):
            continue
        try:
            if p.stat().st_size > 300000:
                continue
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
        except OSError:
            continue
        title, section, links, seen = None, "", [], set()
        in_code = False
        for i, ln in enumerate(text.split("\n")):
            if ln.strip().startswith("```"):
                in_code = not in_code
            h = HEADING_MD.match(ln) if not in_code else None
            if h:
                section = h.group(2).strip()[:80]
                if title is None:
                    title = section
                continue

            def add(key, typ, prov):
                if (key, section) in seen or len(links) >= 200:
                    return
                seen.add((key, section))
                links.append({"key": key, "type": typ, "section": section, "line": i + 1, "prov": prov})
            for m in PATH_TOKEN.finditer(ln):
                t = m.group(1).lstrip("./")
                if t in file_set:
                    add(t, "file", "E")
                else:
                    c = [r for r in by_base.get(t.rsplit("/", 1)[-1], []) if r.endswith("/" + t) or r == t]
                    if len(c) == 1:
                        add(c[0], "file", "E")
            for m in DIR_TOKEN.finditer(ln):
                t = m.group(1).strip("./")
                if t in mod_paths:
                    add(mod_paths[t], "module", "E")
            for m in TICK_TOKEN.finditer(ln):
                t = m.group(1)
                hit = quals.get(t) or names.get(t.split(".")[-1])
                if hit and len(hit) == 1:
                    k = next(iter(hit))
                    add(k, "class" if k.startswith("c:") else "function", "E")
            if not in_code:
                for m in IDENT_TOKEN.finditer(ln):
                    t = m.group(1)
                    if t.lower() in COMMON_WORDS or not ("_" in t or re.search(r"[a-z][A-Z]", t)):
                        continue
                    hit = names.get(t)
                    if hit and len(hit) == 1:
                        k = next(iter(hit))
                        add(k, "class" if k.startswith("c:") else "function", "I")
        if links:
            docs.append({"path": rel, "kind": doc_kind(rel), "title": (title or Path(rel).stem)[:100], "links": links})
        if len(docs) >= max_docs:
            break
    return docs


# ---------------------------------------------------------------------------------------------- graphify interop

def find_graphify(root, explicit=None):
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for c in (root / "graphify-out" / "graph.json", root / ".graphify" / "graph.json"):
        if c.is_file():
            return c
    return None


def load_graphify(gpath, root, native_ext):
    """Read Graphify's graph.json (NetworkX node-link) and turn it into codeflow facts for files whose language
    codeflow-map does not parse itself. Returns {"files": {rel: facts}, "notes": {rel: [...]}, "version": str}."""
    try:
        data = json.loads(Path(gpath).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    nodes = {n.get("id"): n for n in data.get("nodes", []) if isinstance(n, dict) and n.get("id") is not None}
    links = [l for l in (data.get("links") or data.get("edges") or []) if isinstance(l, dict)]

    def rel_of(sf):
        if not sf:
            return None
        sf = str(sf).replace("\\", "/").lstrip("./")
        parts = sf.split("/")
        for i in range(len(parts)):   # graph built from a parent folder: strip leading parts until the file exists
            cand = "/".join(parts[i:])
            if (root / cand).is_file():
                return cand
        return None

    def line_of(n):
        m = re.match(r"L(\d+)", str(n.get("source_location") or ""))
        return int(m.group(1)) if m else 1

    out = defaultdict(lambda: {"imports": [], "classes": [], "functions": [], "gfy": True})
    rel_cache = {}
    for nid, n in nodes.items():
        sf = n.get("source_file")
        if sf not in rel_cache:
            rel_cache[sf] = rel_of(sf)
        n["_rel"] = rel_cache[sf]
    contains = defaultdict(list)
    methods_of = defaultdict(list)
    for l in links:
        rel = l.get("relation")
        if rel == "contains":
            contains[l.get("source")].append(l.get("target"))
        elif rel == "method":
            methods_of[l.get("source")].append(l.get("target"))
    file_ids = {}
    for nid, n in nodes.items():
        r = n["_rel"]
        if not r or Path(r).suffix.lower() in native_ext or n.get("file_type", "code") != "code":
            continue
        lab = str(n.get("label", ""))
        if lab == r.rsplit("/", 1)[-1] or (line_of(n) == 1 and contains.get(nid) and "(" not in lab):
            file_ids[nid] = r
    method_ids = {m for ms in methods_of.values() for m in ms}
    cls_name, fn_key = {}, {}
    for nid, n in nodes.items():
        r = n["_rel"]
        if not r or nid in file_ids or Path(r).suffix.lower() in native_ext or n.get("file_type", "code") != "code":
            continue
        lab = str(n.get("label", ""))
        if lab.endswith("()") and nid not in method_ids:
            name = lab.lstrip(".")[:-2]
            fn = {"name": name, "qual": name, "kind": "function", "line": line_of(n), "endLine": line_of(n), "loc": 1,
                  "params": [], "complexity": 1, "calls": [], "renders": [], "gfy_id": nid}
            out[r]["functions"].append(fn)
            fn_key[nid] = (r, name)
        elif not lab.endswith("()"):
            c = {"name": lab, "line": line_of(n), "endLine": line_of(n), "bases": [], "methods": [], "props": [], "decorators": [],
                 "gfy_id": nid}
            out[r]["classes"].append(c)
            cls_name[nid] = (r, lab)
            for mid in methods_of.get(nid, []):
                mn = nodes.get(mid)
                if not mn:
                    continue
                mname = str(mn.get("label", "")).lstrip(".").rstrip("()") or "method"
                c["methods"].append({"name": mname, "line": line_of(mn), "params": [], "returns": "", "access": "public"})
                out[r]["functions"].append({"name": mname, "qual": lab + "." + mname, "kind": "method", "cls": lab,
                                            "line": line_of(mn), "endLine": line_of(mn), "loc": 1, "params": [],
                                            "complexity": 1, "calls": [], "renders": [], "gfy_id": mid})
                fn_key[mid] = (r, lab + "." + mname)
    notes = defaultdict(list)
    for l in links:
        s, t, rel = l.get("source"), l.get("target"), l.get("relation")
        prov = "I" if str(l.get("confidence", "EXTRACTED")).upper() != "EXTRACTED" else "E"
        if rel == "calls" and s in fn_key and t in fn_key:
            r, q = fn_key[s]
            for fn in out[r]["functions"]:
                if fn["qual"] == q:
                    fn.setdefault("gfy_calls", []).append({"to_file": fn_key[t][0], "to_qual": fn_key[t][1],
                                                          "line": line_of({"source_location": l.get("source_location")}), "prov": prov})
                    break
        elif rel in ("imports", "imports_from") and s in file_ids:
            tn = nodes.get(t)
            tr = file_ids.get(t) or (tn or {}).get("_rel")
            if tr and tr != file_ids[s]:
                out[file_ids[s]]["imports"].append({"file": tr, "prov": prov})
        elif rel == "inherits" and s in cls_name and t in nodes:
            r, cn = cls_name[s]
            for c in out[r]["classes"]:
                if c["name"] == cn:
                    c["bases"].append(str(nodes[t].get("label", "")))
        elif rel == "rationale_for":
            sn, tn = nodes.get(s), nodes.get(t)
            if sn and tn and tn.get("_rel") and Path(tn["_rel"]).suffix.lower() not in native_ext:
                notes[tn["_rel"]].append({"line": line_of(sn), "tag": "NOTE", "text": str(sn.get("label", ""))[:220], "refs": []})
    for r, f in out.items():
        try:
            text = (root / r).read_text(encoding="utf-8-sig", errors="ignore")
            f["loc"] = sum(1 for x in text.split("\n") if x.strip())
            ends = sorted(fn["line"] for fn in f["functions"]) + [text.count("\n") + 1]
            for fn in f["functions"]:   # rough end line: up to the next definition
                nxt = [e for e in ends if e > fn["line"]]
                fn["endLine"] = (nxt[0] - 1) if nxt else fn["line"]
                fn["loc"] = max(1, fn["endLine"] - fn["line"] + 1)
        except OSError:
            f["loc"] = 0
        f["lang"] = Path(r).suffix.lower().lstrip(".") or "code"
    ver = (data.get("graph") or {}).get("graphify_version") or "?"
    return {"files": dict(out), "notes": dict(notes), "version": ver, "path": str(gpath)}


# ---------------------------------------------------------------------------------------------- communities

def _one_level(G, res):
    k = {i: sum(w for j, w in G[i].items() if j != i) + 2 * G[i].get(i, 0.0) for i in G}
    m = sum(k.values()) / 2.0
    comm = {i: i for i in G}
    if m <= 0:
        return comm, False
    tot = dict(k)
    improved, moved, rounds = False, True, 0
    order = sorted(G, key=str)
    while moved and rounds < 40:
        moved, rounds = False, rounds + 1
        for i in order:
            ci = comm[i]
            wts = defaultdict(float)
            for j, w in G[i].items():
                if j != i:
                    wts[comm[j]] += w
            tot[ci] -= k[i]
            best, best_gain = ci, wts.get(ci, 0.0) - res * tot[ci] * k[i] / (2 * m)
            for c in sorted(wts, key=str):
                g = wts[c] - res * tot[c] * k[i] / (2 * m)
                if g > best_gain + 1e-12:
                    best, best_gain = c, g
            tot[best] += k[i]
            comm[i] = best
            if best != ci:
                moved = improved = True
    return comm, improved


def _aggregate(G, comm):
    H = defaultdict(lambda: defaultdict(float))
    for i in G:
        for j, w in G[i].items():
            ci, cj = comm[i], comm[j]
            if i == j:
                H[ci][ci] += w
            elif ci == cj:
                H[ci][ci] += w / 2.0
            else:
                H[ci][cj] += w
    for c in set(comm.values()):
        H[c]   # keep isolated communities
    return {c: dict(v) for c, v in H.items()}


def louvain(adj, resolution=1.0, levels=10):
    """Communities of an undirected weighted graph {node: {neighbour: weight}} (Louvain method, deterministic).
    Returns {node: community index}, communities numbered by size (largest first)."""
    G = {n: {m: float(w) for m, w in nb.items() if m in adj} for n, nb in adj.items()}
    for n in list(G):   # make symmetric
        for m, w in list(G[n].items()):
            G.setdefault(m, {})
            if G[m].get(n, 0) < w:
                G[m][n] = w
    top = {n: n for n in G}
    for _ in range(levels):
        part, improved = _one_level(G, resolution)
        if not improved:
            break
        top = {n: part[c] for n, c in top.items()}
        G = _aggregate(G, part)
    sizes = Counter(top.values())
    order = {c: i for i, (c, _) in enumerate(sorted(sizes.items(), key=lambda x: (-x[1], str(x[0]))))}
    return {n: order[c] for n, c in top.items()}


# ---------------------------------------------------------------------------------------------- graph

REL_NAMES = ["contains", "imports", "calls", "inherits", "reads", "writes", "documents", "explains", "defines", "renders"]
TYPE_NAMES = ["module", "file", "function", "class", "table", "doc", "note"]
COMMON_CALLS = {"get", "set", "add", "run", "update", "delete", "save", "load", "create", "close", "open", "read", "write",
                "init", "start", "stop", "send", "call", "apply", "build", "parse", "format", "validate", "render",
                "execute", "process", "handle", "filter", "map", "find", "remove", "append", "extend", "items", "keys",
                "values", "copy", "clear", "join", "split", "strip", "lower", "upper", "replace", "encode", "decode",
                "dump", "dumps", "loads", "commit", "flush", "query", "fetch", "emit", "log", "info", "debug", "warning",
                "warn", "error", "exception", "then", "catch", "push", "pop", "shift", "includes", "toString", "forEach",
                "reduce", "some", "every", "json", "text", "next", "main", "setup", "teardown", "test", "reset",
                "result", "results", "check", "wait", "list", "show", "hide", "toggle", "use", "exec", "first", "all",
                "count", "exists", "path", "name", "value", "data", "item", "node", "edge", "size", "length", "index",
                "on", "off", "emit", "default", "inner", "wrapper", "decorator", "handler", "callback", "hook"}


class Graph:
    def __init__(self):
        self.nodes, self.idx, self.edges, self.eseen = [], {}, [], set()

    def node(self, typ, key, label, module=None, line=0, extra=None):
        if key in self.idx:
            return self.idx[key]
        i = len(self.nodes)
        self.idx[key] = i
        self.nodes.append({"type": typ, "key": key, "label": label, "module": module, "line": line or 0, "extra": extra})
        return i

    def edge(self, a, b, rel, prov="E", line=0, note=None):
        if a is None or b is None or a == b:
            return
        k = (a, b, rel)
        if k in self.eseen:
            return
        self.eseen.add(k)
        self.edges.append([a, b, rel, prov, line or 0, note])


def build_graph(A, docs, notes_by_file, redact=None):
    """Assemble the typed graph and the insights from a finished Analysis A."""
    g = Graph()
    for M in sorted(A.modules.values(), key=lambda M: M["path"]):
        g.node("module", M["id"], M["label"], M["id"])
    for r in A.files:
        g.node("file", r, file_label(r), A.mod_of.get(r), 1)
        g.edge(g.idx[A.mod_of[r]], g.idx[r], "contains")
    for ckey, c in sorted(A.cls_index.items()):
        ci = g.node("class", "c:" + ckey, c["name"], c.get("module"), c.get("line", 0))
        g.edge(g.idx[c["file"]], ci, "contains")
    for key, fn in sorted(A.fns.items()):
        fi = g.node("function", key, A.fn_title(fn), fn.get("module"), fn.get("line", 0))
        owner = g.idx.get("c:" + fn["file"] + "::" + fn["cls"]) if fn.get("cls") else None
        g.edge(owner if owner is not None else g.idx[fn["file"]], fi, "contains")
    # imports
    for a, deps in A.file_deps.items():
        for b in deps:
            if a in g.idx and b in g.idx:
                g.edge(g.idx[a], g.idx[b], "imports", A.import_prov.get((a, b), "E"))
    # calls / renders (provenance from call resolution)
    for key, fn in A.fns.items():
        for c in fn.get("resolved", []):
            if c.get("to") in g.idx:
                g.edge(g.idx[key], g.idx[c["to"]], "renders" if c.get("render") else "calls", c.get("prov", "E"), c.get("line", 0))
    # inheritance
    for ckey, c in A.cls_index.items():
        bases = c.get("bases") or ([x.strip() for x in c.get("extends", "").split(",")] if c.get("extends") else [])
        for b in bases:
            b = (b or "").split(".")[-1].split("<")[0].split("[")[0].strip()
            tf = A._class_file(c["file"], b) if b else None
            if tf and ("c:" + tf + "::" + b) in g.idx:
                g.edge(g.idx["c:" + ckey], g.idx["c:" + tf + "::" + b], "inherits", "E", c.get("line", 0))
    # tables: definitions (extracted) and reads / writes (inferred from database calls + model names)
    table_cls = {}
    for M in A.modules.values():
        for t in M.get("tables", []):
            tk = "t:" + A.table_name(t).lower()
            ti = g.node("table", tk, A.table_name(t), M["id"], t.get("line", 0))
            if not t.get("sql") and ("c:" + t["file"] + "::" + t["name"]) in g.idx:
                g.edge(g.idx["c:" + t["file"] + "::" + t["name"]], ti, "defines", "E", t.get("line", 0))
                table_cls[t["name"]] = ti
            else:
                g.edge(g.idx[t["file"]], ti, "defines", "E", t.get("line", 0))
    if table_cls:
        for key, fn in A.fns.items():
            if fn["file"] in A.generated:
                continue
            names = set(fn.get("names", [])) | {c["name"] for c in fn.get("calls", [])} | {(c.get("obj") or "").split(".")[-1] for c in fn.get("calls", [])}
            touched = [table_cls[n] for n in names if n in table_cls]
            if not touched:
                continue
            dbw = any(c.get("ext") == "db" and c.get("write") for c in fn.get("resolved", []))
            dbr = any(c.get("ext") == "db" and not c.get("write") for c in fn.get("resolved", [])) or \
                any(c["name"] in ("select", "query", "get", "findMany", "findUnique", "findFirst") for c in fn.get("calls", []))
            for ti in touched:
                if dbw:
                    g.edge(g.idx[key], ti, "writes", "I")
                if dbr:
                    g.edge(g.idx[key], ti, "reads", "I")
    # rationale notes
    fn_by_file = defaultdict(list)
    for key, fn in A.fns.items():
        fn_by_file[fn["file"]].append(fn)
    cls_by_file = defaultdict(list)
    for ckey, c in A.cls_index.items():
        cls_by_file[c["file"]].append(c)
    note_count = Counter()
    for r, notes in notes_by_file.items():
        if r not in g.idx:
            continue
        for n in notes:
            # innermost enclosing function or class; else the one that starts just below the comment
            inside = [(x["line"], x["key"]) for x in fn_by_file.get(r, []) if x["line"] <= n["line"] <= x.get("endLine", x["line"])]
            inside += [(c.get("line", 0), "c:" + r + "::" + c["name"]) for c in cls_by_file.get(r, [])
                       if c.get("line", 0) <= n["line"] <= c.get("endLine", c.get("line", 0))]
            above = [(x["line"], x["key"]) for x in fn_by_file.get(r, []) if 0 < x["line"] - n["line"] <= 3]
            above += [(c.get("line", 0), "c:" + r + "::" + c["name"]) for c in cls_by_file.get(r, []) if 0 < c.get("line", 0) - n["line"] <= 3]
            target = min(above)[1] if above else (max(inside)[1] if inside else None)
            tgt = g.idx.get(target) if target else g.idx[r]
            ni = g.node("note", "n:%s:%d" % (r, n["line"]), n["text"] or ", ".join(n["refs"]), A.mod_of.get(r), n["line"],
                        {"tag": n["tag"], "group": note_group(n["tag"]), "refs": n["refs"]})
            g.edge(ni, tgt, "explains", "E", n["line"])
            note_count[A.mod_of.get(r)] += 1
    # docs
    for d in docs:
        di = g.node("doc", "doc:" + d["path"], d["title"], None, 1, {"kind": d["kind"], "path": d["path"]})
        for l in d["links"]:
            if l["key"] in g.idx:
                g.edge(di, g.idx[l["key"]], "documents", l["prov"], l["line"], l["section"])
    return g, note_count


def communities_of(A, g, resolution=1.0):
    """File-level communities from imports, calls and inheritance."""
    adj = defaultdict(lambda: defaultdict(float))
    files = [r for r in A.files if r in g.idx]
    fidx = {g.idx[r]: r for r in files}
    owner = {}
    for i, n in enumerate(g.nodes):
        if n["type"] in ("function", "class"):
            k = n["key"][2:] if n["key"].startswith("c:") else n["key"]
            owner[i] = k.split("::")[0]
    for a, b, rel, prov, _ln, _n in g.edges:
        if rel == "imports" and a in fidx and b in fidx:
            fa, fb, w = fidx[a], fidx[b], 1.0
        elif rel in ("calls", "inherits", "renders") and a in owner and b in owner:
            fa, fb, w = owner[a], owner[b], (0.5 if prov == "I" else 1.0)
        else:
            continue
        if fa != fb:
            adj[fa][fb] += w
            adj[fb][fa] += w
    for r in files:
        adj[r]
    if not adj:
        return {}, None
    comm = louvain(adj, resolution)
    sizes = Counter(comm.values())
    big = sorted({c for c, n in sizes.items() if n > 1}, key=lambda c: (-sizes[c], c))
    remap = {c: i for i, c in enumerate(big)}
    alone = len(big)   # files with no links to anything else share one "Standalone files" group
    out = {r: remap.get(c, alone) for r, c in comm.items()}
    return out, (alone if alone in out.values() else None)


def community_labels(A, comm, g, alone=None):
    """Name each community after its most central files (no LLM)."""
    deg = Counter()
    for a, b, rel, _p, _l, _n in g.edges:
        if rel == "imports":
            ka, kb = g.nodes[a]["key"], g.nodes[b]["key"]
            if comm.get(ka) is not None and comm.get(ka) == comm.get(kb):
                deg[ka] += 1
                deg[kb] += 1
    members = defaultdict(list)
    for r, c in comm.items():
        members[c].append(r)
    labels, used = {}, Counter()
    for c, fs in members.items():
        if c == alone:
            labels[c] = "Standalone files"
            continue
        fs = sorted(fs, key=lambda r: (-deg[r], -A.facts.get(r, {}).get("loc", 0), r))
        stems = []
        for r in fs:
            s = re.sub(r"[_\-.]+", " ", Path(r).stem).strip()
            if s.lower() in ("index", "init", "main", "__init__", "mod", "utils") and len(fs) > 1:
                s = Path(r).parent.name or s
            s = s[:1].upper() + s[1:]
            if s and s not in stems:
                stems.append(s)
            if len(stems) == 2:
                break
        lab = " · ".join(stems) if stems else "Group %d" % (c + 1)
        used[lab] += 1
        if used[lab] > 1:
            lab += " (%d)" % used[lab]
        labels[c] = lab
    return labels, members


def most_connected(A, g, n=12):
    deg = defaultdict(set)
    for a, b, rel, _p, _l, _n in g.edges:
        if rel in ("calls", "imports", "inherits", "renders", "reads", "writes"):
            deg[a].add(b)
            deg[b].add(a)
    out = []
    for i, nb in sorted(deg.items(), key=lambda x: -len(x[1])):
        node = g.nodes[i]
        if node["type"] not in ("function", "class", "file"):
            continue
        f = node["key"][2:].split("::")[0] if node["key"].startswith("c:") else node["key"].split("::")[0]
        if f in A.generated:
            continue
        out.append({"key": node["key"], "label": node["label"], "type": node["type"], "connections": len(nb)})
        if len(out) >= n:
            break
    return out


def surprising_links(A, g, comm, labels, n=10):
    """Cross-community links that are the only (or nearly only) tie between two distant parts of the code."""
    owner = {}
    for i, node in enumerate(g.nodes):
        if node["type"] == "file":
            owner[i] = node["key"]
        elif node["type"] in ("function", "class"):
            owner[i] = (node["key"][2:] if node["key"].startswith("c:") else node["key"]).split("::")[0]
    pair_w = Counter()
    pair_links = defaultdict(list)
    for a, b, rel, prov, line, _n in g.edges:
        if rel not in ("calls", "imports", "inherits", "renders"):
            continue
        fa, fb = owner.get(a), owner.get(b)
        if not fa or not fb or fa == fb or fa in A.generated or fb in A.generated:
            continue
        ca, cb = comm.get(fa), comm.get(fb)
        if ca is None or cb is None or ca == cb:
            continue
        key = (min(ca, cb), max(ca, cb))
        pair_w[key] += 1
        pair_links[key].append((a, b, rel, prov, line))

    def distance(fa, fb):
        pa, pb = fa.split("/")[:-1], fb.split("/")[:-1]
        common = 0
        for x, y in zip(pa, pb):
            if x != y:
                break
            common += 1
        return (len(pa) - common) + (len(pb) - common)
    cands = []
    for key, w in pair_w.items():
        if w > 2:
            continue
        a, b, rel, prov, line = sorted(pair_links[key], key=lambda x: (x[2] != "calls", x[4]))[0]
        fa, fb = owner[a], owner[b]
        d = distance(fa, fb)
        if d < 2:
            continue
        cands.append((d / w, a, b, rel, prov, line, w))
    cands.sort(key=lambda x: (-x[0], g.nodes[x[1]]["key"]))
    out = []
    for score, a, b, rel, prov, line, w in cands[:n]:
        na, nb = g.nodes[a], g.nodes[b]
        fa, fb = owner[a], owner[b]
        out.append({"from": na["key"], "to": nb["key"], "from_label": na["label"], "to_label": nb["label"], "relation": rel,
                    "prov": prov, "evidence": "%s:%d" % (fa, line or na["line"] or 1),
                    "why": "%s between '%s' and '%s', two groups of code that are otherwise not connected." % (
                        "The only link" if w == 1 else "One of only two links", labels.get(comm[fa], "?"), labels.get(comm[fb], "?"))})
    return out


GENERIC_FILES = re.compile(r"^(__init__|__main__|index|main|mod|lib|base|utils?|helpers?|types|models|views|urls|apps|admin|"
                           r"settings|config|constants|routes|api|app|server|client|common|core|shared|exceptions|errors)\.[A-Za-z0-9]+$")


def file_label(rel):
    """File name, with its folder when the name alone says little (__init__.py → db/__init__.py)."""
    parts = rel.split("/")
    if len(parts) > 1 and GENERIC_FILES.match(parts[-1]):
        return parts[-2] + "/" + parts[-1]
    return parts[-1]


def suggested_questions(A, g, gods, surprising):
    """Questions a reader can run in the Explore tab (each carries the query that answers it)."""
    qs = []
    tables = [n for n in g.nodes if n["type"] == "table"]
    routes = [fn for fn in A.fns.values() if fn.get("route") and fn["file"] not in A.generated]
    if routes and tables:
        tset = {g.idx[t["key"]] for t in tables}
        reach = set()
        for a, b, rel, _p, _l, _n in g.edges:
            if rel in ("writes", "reads") and b in tset:
                reach.add(a)
        for fn in sorted(routes, key=lambda f: (f["route"]["method"] != "POST", f["file"], f["line"])):
            if _reaches(g, g.idx[fn["key"]], reach, 4):
                qs.append({"text": "How does %s %s reach the database?" % (fn["route"]["method"], fn["route"]["path"]),
                           "op": "path", "from": fn["key"], "to": "type:table"})
                break
    for gd in gods[:2]:
        qs.append({"text": "What could break if %s changes?" % gd["label"], "op": "impact", "from": gd["key"]})
    hot = sorted([fn for fn in A.fns.values() if fn.get("heat", 0) > 0.4 and fn["file"] not in A.generated], key=lambda f: -f["heat"])
    if hot:
        qs.append({"text": "What does %s rely on?" % A.fn_title(hot[0]), "op": "callees", "from": hot[0]["key"]})
    for s in surprising[:2]:
        qs.append({"text": "Why does %s use %s?" % (s["from_label"], s["to_label"]), "op": "path", "from": s["from"], "to": s["to"]})
    if A.cycles:
        c = A.cycles[0]
        qs.append({"text": "How are %s and %s tied together?" % (A.modules[c[0]]["label"], A.modules[c[1]]["label"]),
                   "op": "path", "from": c[0], "to": c[1]})
    unused = [fn for fn in A.fns.values() if fn.get("unused")]
    if unused:
        qs.append({"text": "Is %s still used anywhere?" % A.fn_title(unused[0]), "op": "callers", "from": unused[0]["key"]})
    if tables:
        t = tables[0]
        qs.append({"text": "Which code reads or writes the %s table?" % t["label"], "op": "callers", "from": t["key"]})
    return qs[:8]


def _reaches(g, start, targets, depth):
    out = defaultdict(list)
    for a, b, rel, _p, _l, _n in g.edges:
        if rel in ("calls", "writes", "reads"):
            out[a].append(b)
    seen, frontier = {start}, [start]
    for _ in range(depth):
        nxt = []
        for x in frontier:
            if x in targets:
                return True
            for y in out[x]:
                if y not in seen:
                    seen.add(y)
                    nxt.append(y)
        frontier = nxt
    return any(x in targets for x in frontier)


def compact(g, comm):
    """Graph for the HTML: short arrays, shared string tables."""
    mods = sorted({n["module"] for n in g.nodes if n["module"]})
    midx = {m: i for i, m in enumerate(mods)}
    nodes = []
    for n in g.nodes:
        f = n["key"][2:] if n["key"].startswith("c:") else n["key"]
        c = comm.get(f.split("::")[0]) if n["type"] in ("file", "function", "class") else None
        row = [TYPE_NAMES.index(n["type"]), n["key"], n["label"], midx.get(n["module"], -1), n["line"], -1 if c is None else c]
        if n["extra"]:
            row.append(n["extra"])
        nodes.append(row)
    edges = []
    for a, b, rel, prov, line, note in g.edges:
        row = [a, b, REL_NAMES.index(rel), 1 if prov == "I" else 0, line]
        if note:
            row.append(note)
        edges.append(row)
    return {"v": 3, "types": TYPE_NAMES, "rels": REL_NAMES, "modules": mods, "nodes": nodes, "edges": edges}


def node_link(g, comm, A):
    """Readable graph (.codeflow/graph.json), NetworkX node-link shaped like Graphify's."""
    nodes = []
    for n in g.nodes:
        f = n["key"][2:] if n["key"].startswith("c:") else n["key"]
        src = f.split("::")[0] if n["type"] in ("file", "function", "class") else (n["extra"] or {}).get("path") if n["type"] == "doc" else \
            n["key"].split(":")[1] if n["type"] == "note" else None
        d = {"id": n["key"], "label": n["label"], "type": n["type"]}
        if src:
            d["source_file"] = src
            d["source_location"] = "L%d" % (n["line"] or 1)
        if n["module"]:
            d["module"] = n["module"]
        if n["type"] in ("file", "function", "class") and comm.get(f.split("::")[0]) is not None:
            d["community"] = comm[f.split("::")[0]]
        if n["extra"]:
            d.update({k: v for k, v in n["extra"].items() if k != "path"})
        nodes.append(d)
    links = []
    for a, b, rel, prov, line, note in g.edges:
        l = {"source": g.nodes[a]["key"], "target": g.nodes[b]["key"], "relation": rel,
             "confidence": "INFERRED" if prov == "I" else "EXTRACTED"}
        if line:
            l["source_location"] = "L%d" % line
        if note:
            l["context"] = note
        links.append(l)
    return {"directed": True, "multigraph": True,
            "graph": {"tool": "codeflow-map", "schema_version": 1, "commit": A.commit},
            "nodes": nodes, "links": links}
