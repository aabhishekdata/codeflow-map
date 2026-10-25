#!/usr/bin/env python3
"""Build one interactive HTML flow map from a flowmap spec and/or a module analysis.

Usage:
    python build_flowmap.py <flowmap.json> [--out map.html]                        # hand-written views only
    python build_flowmap.py --modules .codeflow/modules.json [--out map.html]      # module map + deep dives only
    python build_flowmap.py <flowmap.json> --modules .codeflow/modules.json        # both, merged (spec wins on ids)

Options:
  (default)    one self-contained HTML (~1 MB + your data) with the Pele drawing library inlined; works offline
  --cdn        smaller HTML that loads Pele from cdn.jsdelivr.net (pinned version + integrity hash)
  --check      validate only, write nothing
  --strict     treat warnings as errors
  --svg-dir D  also write one SVG file per view into D (needs Node 18+)
  --no-node    skip the Pele check in Node (structure is still validated)

Every view is drawn with Pele (via Node) before the HTML is written, so a map that builds is a map that
renders. Standard library only (Python 3.8+); Node 18+ recommended for the drawing check.
The spec format is documented in references/spec-schema.md.
"""
import argparse
import base64
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
TEMPLATE = ASSETS / "viewer.html"
GEN = ASSETS / "flowmap-gen.js"
PELE = ASSETS / "vendor" / "pele.global.js"
PELE_VERSION = "1.10.0"   # must match assets/vendor/pele.global.js (the integrity hash is computed from it)
CDN_HOST = "https://cdn.jsdelivr.net"
PELE_CDN = "%s/npm/pele@%s/dist/pele.global.js" % (CDN_HOST, PELE_VERSION)

KINDS = {"user", "ui", "process", "service", "store", "external", "decision", "event", "file", "control", "ai",
         "schedule", "module", "function", "package", "start", "end", "loop", "error"}
VIEW_KINDS = {"architecture", "journey", "dataflow", "detail", "other", "modules", "changes"}
TYPES = {"flowchart", "sequence", "class", "er", "state", "mermaid"}
FACETS = {"deps", "files", "classes", "calls", "control", "sequence", "dataflow", "datamodel", "state"}
DIRECTIONS = {"LR", "RL", "TB", "TD", "BT"}
REL_TYPES = {"inheritance", "realization", "composition", "aggregation", "association", "dependency", "link"}
CARDS = {"one", "zero-one", "many", "one-many"}
SIMPLE_LABEL_MAX_WORDS = 6
SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(?:jdbc|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s\"']*:[^\s\"'@]+@"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
]
PII_PATTERNS = [
    re.compile(r"(?i)\b(?:[a-z0-9._%+-]+)@(?:[a-z0-9-]+\.)+[a-z]{2,}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
]
PII_ALLOW = re.compile(r"(?i)(noreply|no-reply|example\.(com|org|net)|users\.noreply\.github\.com|@(localhost|test)\b)")


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append("ERROR   %s: %s" % (where, msg))

    def warn(self, where, msg):
        self.warnings.append("WARNING %s: %s" % (where, msg))


# ====================================================================== merge
def merge(spec, mods):
    """Spec (hand-written) + module analysis -> one map. Spec views replace generated views with the same id;
    spec `modules` entries add plain-English notes to the generated modules."""
    if not mods:
        return spec
    spec = spec or {}
    out = copy.deepcopy(spec)
    gen_views = mods.get("views", [])
    spec_views = spec.get("views", [])
    spec_ids = {v.get("id") for v in spec_views if isinstance(v, dict)}
    top = [v for v in spec_views if isinstance(v, dict) and v.get("kind") != "detail"]
    detail = [v for v in spec_views if isinstance(v, dict) and v.get("kind") == "detail"]
    merged = list(top)
    for v in gen_views:
        if v.get("id") in spec_ids:
            merged.append(next(s for s in spec_views if s.get("id") == v["id"]))
        else:
            merged.append(v)
    merged_ids = {v.get("id") for v in merged}
    merged += [v for v in detail if v.get("id") not in merged_ids]
    out["views"] = merged
    notes = {m.get("id"): m for m in spec.get("modules", []) if isinstance(m, dict)}
    records = []
    for m in mods.get("modules", []):
        n = notes.get(m["id"], {})
        r = dict(m)
        for k in ("label", "description", "why", "risks", "controls", "summary"):
            if n.get(k):
                r[k] = n[k]
        records.append(r)
    out["modules"] = records
    # a renamed module keeps its new name in the generated summaries too
    old_labels = {m["id"]: m.get("label") for m in mods.get("modules", [])}
    for v in out["views"]:
        mid = v.get("module")
        if mid in notes and notes[mid].get("label") and old_labels.get(mid) and v.get("id") not in spec_ids:
            for k in ("summary", "title"):
                if isinstance(v.get(k), str):
                    v[k] = v[k].replace(old_labels[mid], notes[mid]["label"])
    # carry the notes into the boxes that stand for a module
    rec = {r["id"]: r for r in records}
    for v in out["views"]:
        for node in v.get("nodes", []) if v.get("type", "flowchart") == "flowchart" else []:
            mid = v.get("module") if node.get("id") == "self" else node.get("module")
            n = notes.get(mid)
            if not n:
                continue
            if n.get("label"):
                node["label"] = n["label"]
            whole = v.get("kind") in ("modules", "changes") or node.get("id") == "self"
            if whole and n.get("description"):
                node["description"] = n["description"] + ("  (" + rec[mid]["summary"] + ")" if rec.get(mid, {}).get("summary") else "")
            if whole:
                for k in ("why", "controls"):
                    if n.get(k):
                        node[k] = n[k]
                if n.get("risks"):
                    node["risks"] = list(n["risks"]) + [r for r in node.get("risks", []) if r not in n["risks"]]
    # plain-English notes for individual functions: {"id": "path/file.py::Class.method", "description", "why", "risks"}
    fnotes = {f.get("id"): f for f in spec.get("functions", []) if isinstance(f, dict) and f.get("id")}
    if fnotes:
        for v in out["views"]:
            if v.get("function") in fnotes and v.get("facet") == "control":
                fn = fnotes[v["function"]]
                if fn.get("description"):
                    v["summary"] = fn["description"] + " " + v.get("summary", "")
            for node in v.get("nodes", []) if v.get("type", "flowchart") == "flowchart" else []:
                fn = fnotes.get(node.get("function"))
                if not fn:
                    continue
                if fn.get("label"):
                    node["label"] = fn["label"]
                if fn.get("description"):
                    node["description"] = fn["description"] + ("  (" + node["description"] + ")" if node.get("description") else "")
                for k in ("why", "controls"):
                    if fn.get(k):
                        node[k] = fn[k]
                if fn.get("risks"):
                    node["risks"] = list(fn["risks"]) + [r for r in node.get("risks", []) if r not in fn["risks"]]
    repo = mods.get("repo", {})
    out.setdefault("title", "%s: how the code is organised" % repo.get("name", "Code base"))
    out.setdefault("repo", repo)
    g = dict(mods.get("generated", {}))
    g.update(spec.get("generated", {}) or {})
    if mods.get("generated", {}).get("notes"):
        g["notes"] = list(dict.fromkeys((spec.get("generated", {}) or {}).get("notes", []) + mods["generated"]["notes"]))
    out["generated"] = g
    if not spec.get("start_view"):
        out["start_view"] = top[0]["id"] if top else mods.get("start_view", "modules")
    return out


# ====================================================================== validation
def _ids(items, where, rep):
    seen = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            rep.err("%s[%d]" % (where, i), "must be an object")
            continue
        _id = it.get("id")
        if _id is None or _id == "" or not isinstance(_id, (str, int)):
            rep.err("%s[%d]" % (where, i), "missing 'id'")
            continue
        if _id in seen:
            rep.err("%s[%d]" % (where, i), "duplicate id '%s'" % _id)
        seen.add(_id)
    return seen


def _check_label(obj, where, rep, need_desc=True):
    if not (obj.get("label") or obj.get("technical")):
        rep.err(where, "needs a 'label' (plain English) or 'technical'")
        return
    if need_desc and obj.get("label") and len(str(obj["label"]).split()) > SIMPLE_LABEL_MAX_WORDS:
        rep.warn(where, "label '%s' is long; keep simple labels to <= %d words and move detail into 'description'" % (obj["label"], SIMPLE_LABEL_MAX_WORDS))
    if need_desc and not obj.get("description"):
        rep.warn(where, "no 'description' - stakeholders who click it will see little")


def _check_common_node(n, W, rep, view_ids, group_ids, module_ids, generated):
    if n.get("kind") and n["kind"] not in KINDS:
        rep.err(W, "kind '%s' must be one of %s" % (n["kind"], sorted(KINDS)))
    if n.get("group") and n["group"] not in group_ids:
        rep.err(W, "group '%s' not found" % n["group"])
    for key in ("drilldown", "cfg_view"):
        if n.get(key) and n[key] not in view_ids:
            rep.err(W, "%s '%s' is not a view id" % (key, n[key]))
    if n.get("module") and module_ids is not None and n["module"] not in module_ids:
        rep.err(W, "module '%s' is not a module id" % n["module"])
    if n.get("confidence") not in (None, "verified", "inferred"):
        rep.err(W, "confidence must be 'verified' or 'inferred'")
    if n.get("heat") is not None and not isinstance(n["heat"], (int, float)):
        rep.err(W, "heat must be a number between 0 and 1")
    if n.get("metrics") is not None and not isinstance(n["metrics"], dict):
        rep.err(W, "metrics must be an object of name: value")
    if not generated and not n.get("files") and n.get("confidence") != "inferred" and n.get("kind") not in ("user", "external", "package", "start", "end"):
        rep.warn(W, "no 'files' evidence; add file:line refs or mark confidence 'inferred'")


def validate(spec):
    rep = Report()
    if not isinstance(spec, dict):
        rep.err("spec", "top level must be a JSON object")
        return rep
    if not spec.get("title"):
        rep.warn("spec", "no 'title'")
    views = spec.get("views")
    if not isinstance(views, list) or not views:
        rep.err("spec", "'views' must be a non-empty list")
        return rep
    view_ids = _ids(views, "views", rep)
    module_ids = {m.get("id") for m in spec.get("modules", []) if isinstance(m, dict)} if spec.get("modules") else None
    if spec.get("start_view") and spec["start_view"] not in view_ids:
        rep.err("spec.start_view", "'%s' is not a view id" % spec["start_view"])
    gen = spec.get("generated") or {}
    if not isinstance(gen, dict):
        rep.err("spec.generated", "must be an object like {\"date\": ..., \"commit\": ...}")
        gen = {}
    for key in ("modules", "functions"):
        if spec.get(key) is not None and not isinstance(spec[key], list):
            rep.err("spec." + key, "must be a list")
    if not gen.get("date"):
        rep.warn("spec.generated", "add 'date' so readers know how current the map is")
    if not gen.get("commit"):
        rep.warn("spec.generated", "add 'commit' (git rev-parse --short HEAD) for traceability")
    theme = spec.get("theme")
    if theme is not None and (not isinstance(theme, dict) or theme.get("mode") not in (None, "auto", "light", "dark")):
        rep.err("spec.theme", "theme must be an object; mode is auto | light | dark")

    tab_views = 0
    for vi, v in enumerate(views):
        if not isinstance(v, dict):
            continue
        W = "views[%s]" % v.get("id", vi)
        generated = bool(v.get("generated")) or (bool(v.get("module")) and v.get("kind") == "detail" and v.get("draft")) or v.get("kind") in ("modules", "changes")
        vtype = v.get("type", "flowchart")
        if vtype not in TYPES:
            rep.err(W, "type '%s' must be one of %s" % (vtype, sorted(TYPES)))
            continue
        if v.get("kind", "other") not in VIEW_KINDS:
            rep.err(W, "kind '%s' must be one of %s" % (v.get("kind"), sorted(VIEW_KINDS)))
        if v.get("kind") != "detail" and v.get("show_in_tabs", True):
            tab_views += 1
        if v.get("facet") and v["facet"] not in FACETS:
            rep.warn(W, "facet '%s' is not a standard one (%s); it will show as its own tab" % (v["facet"], ", ".join(sorted(FACETS))))
        if v.get("facet") and not v.get("module"):
            rep.err(W, "a view with 'facet' also needs 'module'")
        if v.get("module") and module_ids is not None and v["module"] not in module_ids:
            rep.err(W, "module '%s' is not a module id (run analyze_modules.py and pass --modules)" % v["module"])
        if not v.get("title"):
            rep.err(W, "missing 'title'")
        if not v.get("summary"):
            rep.warn(W, "no 'summary' - add 1-2 plain-English sentences shown above the diagram")
        if v.get("direction") and v["direction"] not in DIRECTIONS:
            rep.err(W, "direction must be one of %s" % sorted(DIRECTIONS))
        groups = v.get("groups") or []
        group_ids = _ids(groups, W + ".groups", rep)
        for g in groups:
            if isinstance(g, dict):
                if g.get("parent") and g["parent"] not in group_ids:
                    rep.err("%s.groups[%s]" % (W, g.get("id")), "parent '%s' not found" % g["parent"])
                if g.get("drilldown") and g["drilldown"] not in view_ids:
                    rep.err("%s.groups[%s]" % (W, g.get("id")), "drilldown '%s' is not a view id" % g["drilldown"])
                if not (g.get("label") or g.get("technical")):
                    rep.err("%s.groups[%s]" % (W, g.get("id")), "needs a 'label'")

        if vtype == "mermaid":
            if not v.get("mermaid"):
                rep.err(W, "type 'mermaid' needs a 'mermaid' string")
            continue

        if vtype == "flowchart":
            nodes = v.get("nodes") or []
            if not nodes:
                rep.err(W, "flowchart needs 'nodes'")
            node_ids = _ids(nodes, W + ".nodes", rep)
            if len(nodes) > 60:
                rep.warn(W, "%d boxes is a lot for one picture; split into drill-down views (aim for 5-15)" % len(nodes))
            for n in nodes:
                if not isinstance(n, dict) or n.get("id") is None:
                    continue
                NW = "%s.nodes[%s]" % (W, n["id"])
                _check_label(n, NW, rep, need_desc=not generated)
                _check_common_node(n, NW, rep, view_ids, group_ids, module_ids, generated)
            edges = v.get("edges") or []
            linked = set()
            for i, e in enumerate(edges):
                EW = "%s.edges[%d]" % (W, i)
                if not isinstance(e, dict):
                    rep.err(EW, "must be an object")
                    continue
                for end in ("from", "to"):
                    if e.get(end) not in node_ids:
                        rep.err(EW, "'%s' = '%s' is not a node id in this view" % (end, e.get(end)))
                linked.update([e.get("from"), e.get("to")])
                if e.get("style", "solid") not in ("solid", "dashed", "thick", "both", "plain"):
                    rep.err(EW, "style must be solid | dashed | thick | both | plain")
                if not generated and not (e.get("label") or e.get("technical")):
                    rep.warn(EW, "unlabelled arrow; say what moves along it (e.g. 'sends claim details')")
            if not generated:
                for nid in node_ids - linked:
                    if len(node_ids) > 1:
                        rep.warn("%s.nodes[%s]" % (W, nid), "is not connected to anything")
            _check_walk(v, W, rep, node_ids, group_ids, view_ids, edges)

        elif vtype == "sequence":
            parts = v.get("participants") or []
            if len(parts) < 2:
                rep.err(W, "sequence needs at least 2 'participants'")
            part_ids = _ids(parts, W + ".participants", rep)
            for p in parts:
                if isinstance(p, dict) and p.get("id") is not None:
                    _check_label(p, "%s.participants[%s]" % (W, p["id"]), rep, need_desc=not generated)
                    if p.get("kind") and p["kind"] not in KINDS:
                        rep.err("%s.participants[%s]" % (W, p["id"]), "kind '%s' unknown" % p["kind"])
                    if p.get("group") and p["group"] not in group_ids:
                        rep.err("%s.participants[%s]" % (W, p["id"]), "group '%s' not found" % p["group"])
            steps = v.get("steps") or []
            if not steps:
                rep.err(W, "sequence needs 'steps'")
            msgs = 0
            for i, s in enumerate(steps):
                SW = "%s.steps[%d]" % (W, i)
                if not isinstance(s, dict):
                    rep.err(SW, "must be an object")
                    continue
                if s.get("section") or (s.get("note") and not s.get("from")):
                    if s.get("over") and s["over"] not in part_ids:
                        rep.err(SW, "over '%s' not a participant" % s["over"])
                    continue
                msgs += 1
                for end in ("from", "to"):
                    if s.get(end) not in part_ids:
                        rep.err(SW, "'%s' = '%s' is not a participant id" % (end, s.get(end)))
                if not (s.get("label") or s.get("technical")):
                    rep.warn(SW, "step has no label")
            if msgs > 40:
                rep.warn(W, "%d steps; consider splitting the journey into phases / views" % msgs)
            for i, w in enumerate(v.get("walkthrough") or []):
                st = w.get("step") if isinstance(w, dict) else None
                if st is not None and (not isinstance(st, int) or st < 0 or st >= len(steps)):
                    rep.err("%s.walkthrough[%d]" % (W, i), "step %s out of range (0-based index into steps)" % st)

        elif vtype == "class":
            classes = v.get("classes") or []
            if not classes:
                rep.err(W, "class view needs 'classes'")
            cids = _ids(classes, W + ".classes", rep)
            for c in classes:
                if isinstance(c, dict) and c.get("id") is not None:
                    CW = "%s.classes[%s]" % (W, c["id"])
                    _check_label(c, CW, rep, need_desc=False)
                    _check_common_node(c, CW, rep, view_ids, group_ids, module_ids, True)
                    for key in ("attributes", "methods"):
                        if c.get(key) is not None and not isinstance(c[key], list):
                            rep.err(CW, "'%s' must be a list of strings" % key)
            for i, r in enumerate(v.get("relations") or []):
                RW = "%s.relations[%d]" % (W, i)
                if not isinstance(r, dict):
                    rep.err(RW, "must be an object")
                    continue
                if r.get("from") not in cids or r.get("to") not in cids:
                    rep.err(RW, "from/to must be class ids in this view")
                if r.get("type", "association") not in REL_TYPES:
                    rep.err(RW, "type must be one of %s" % sorted(REL_TYPES))
            _check_walk(v, W, rep, cids, group_ids, view_ids, v.get("relations") or [])

        elif vtype == "er":
            ents = v.get("entities") or []
            if not ents:
                rep.err(W, "er view needs 'entities'")
            eids = _ids(ents, W + ".entities", rep)
            for e in ents:
                if isinstance(e, dict) and e.get("id") is not None:
                    _check_label(e, "%s.entities[%s]" % (W, e["id"]), rep, need_desc=False)
            for i, r in enumerate(v.get("relations") or []):
                RW = "%s.relations[%d]" % (W, i)
                if not isinstance(r, dict):
                    rep.err(RW, "must be an object")
                    continue
                if r.get("from") not in eids or r.get("to") not in eids:
                    rep.err(RW, "from/to must be entity ids in this view")
                for k in ("card_from", "card_to"):
                    if r.get(k) and r[k] not in CARDS:
                        rep.err(RW, "%s must be one of %s" % (k, sorted(CARDS)))
            _check_walk(v, W, rep, eids, group_ids, view_ids, v.get("relations") or [])

        elif vtype == "state":
            states = v.get("states") or []
            if not states:
                rep.err(W, "state view needs 'states'")
            sids = _ids(states, W + ".states", rep)
            for i, t in enumerate(v.get("transitions") or []):
                TW = "%s.transitions[%d]" % (W, i)
                if not isinstance(t, dict):
                    rep.err(TW, "must be an object")
                    continue
                for end in ("from", "to"):
                    if t.get(end) != "*" and t.get(end) not in sids:
                        rep.err(TW, "'%s' = '%s' must be a state id or '*' (start / end)" % (end, t.get(end)))
            _check_walk(v, W, rep, sids, group_ids, view_ids, v.get("transitions") or [])

    if tab_views == 0:
        rep.err("spec", "every view is kind 'detail'; at least one top-level view is needed")
    known_fns = {v.get("function") for v in views if isinstance(v, dict)} | \
        {n.get("function") for v in views if isinstance(v, dict) for n in (v.get("nodes") or []) if isinstance(n, dict)}
    for i, f in enumerate(spec.get("functions", []) or []):
        if not isinstance(f, dict) or not f.get("id"):
            rep.err("spec.functions[%d]" % i, "needs an 'id' like 'path/file.py::function'")
        elif f["id"] not in known_fns:
            rep.warn("spec.functions[%d]" % i, "'%s' does not match any function in the map (check modules.json for the exact id)" % f["id"])
    for i, m in enumerate(spec.get("modules", []) or []):
        if isinstance(m, dict) and module_ids is not None and m.get("id") not in module_ids:
            rep.warn("spec.modules[%d]" % i, "'%s' is not a module id from the analysis; the note is ignored" % m.get("id"))
    strings = []

    def collect(o):
        if isinstance(o, str):
            strings.append(o)
        elif isinstance(o, dict):
            for k, x in o.items():
                strings.append(str(k))
                collect(x)
        elif isinstance(o, list):
            for x in o:
                collect(x)
    collect(spec)
    secret_hit = pii_hit = False
    for text in strings:
        for pat in SECRET_PATTERNS:
            m = pat.search(text)
            if m and not secret_hit:
                secret_hit = True
                rep.err("spec", "looks like a secret or credential is embedded ('%s...'); describe it instead of copying values" % m.group(0)[:12])
        for pat in PII_PATTERNS:
            for m in pat.finditer(text):
                if not pii_hit and not PII_ALLOW.search(m.group(0)):
                    pii_hit = True
                    rep.warn("spec", "possible personal data ('%s...'); use field names, not real values" % m.group(0)[:3])
    return rep


def _check_walk(v, W, rep, node_ids, group_ids, view_ids, edges):
    pairs = {(e.get("from"), e.get("to")) for e in (edges if isinstance(edges, list) else []) if isinstance(e, dict)}
    if not isinstance(v.get("walkthrough") or [], list):
        rep.err(W + ".walkthrough", "must be a list of steps")
        return
    for i, w in enumerate(v.get("walkthrough") or []):
        WW = "%s.walkthrough[%d]" % (W, i)
        if not isinstance(w, dict) or not (w.get("text") or w.get("technical")):
            rep.err(WW, "each walkthrough step needs 'text'")
            continue
        if w.get("drill"):
            if w["drill"] not in view_ids:
                rep.err(WW, "drill '%s' is not a view id" % w["drill"])
            continue
        if w.get("target") and w["target"] not in node_ids:
            rep.err(WW, "target '%s' is not a box id in this view" % w["target"])
        if w.get("group") and w["group"] not in group_ids:
            rep.err(WW, "group '%s' not found" % w["group"])
        if w.get("edge") and (not isinstance(w["edge"], list) or len(w["edge"]) != 2):
            rep.err(WW, "edge must be [from, to]")
        elif w.get("edge") and tuple(w["edge"]) not in pairs:
            rep.err(WW, "edge %s does not exist in this view" % w["edge"])


# ====================================================================== Pele check (Node)
NODE_OVERRIDE = None


def find_node():
    exe = NODE_OVERRIDE or shutil.which("node") or shutil.which("nodejs")
    if not exe:
        return None, None
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
        return exe, int(re.match(r"v?(\d+)", v).group(1))
    except Exception:
        return None, None


def pele_check(spec, svg_dir=None):
    """Draw every view with Pele exactly as the viewer will. Returns (errors, note)."""
    node, major = find_node()
    if not node:
        return [], "Node.js not found: skipped the drawing check (structure was still validated)."
    if major < 18:
        return [], "Node.js %d is too old for the drawing check (18+ needed): skipped." % major
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "spec.json"
        p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        cmd = [node, str(HERE / "pele_check.cjs"), str(p)]
        if svg_dir:
            cmd += ["--svg-dir", str(svg_dir)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, encoding="utf-8")
            res = json.loads(r.stdout or "{}")
        except (subprocess.SubprocessError, ValueError, OSError) as e:
            return ["ERROR   the Pele drawing check failed to run (%s). Fix it, or pass --no-node to skip the check." % e], ""
        if r.returncode != 0 or res.get("error") or "checked" not in res:
            detail = res.get("error") or (r.stderr or "").strip().splitlines()[-1:] or ["no output"]
            return ["ERROR   the Pele drawing check failed (exit %d): %s. Fix it, or pass --no-node to skip the check." % (
                r.returncode, detail if isinstance(detail, str) else detail[0])], ""
    errs = []
    for e in res.get("errors", []):
        errs.append("ERROR   views[%s] (%s): Pele cannot draw it: %s%s\n%s" % (
            e["view"], e["mode"], e["message"], " (line %d, col %d)" % (e["line"], e["column"]) if e.get("line") else "",
            "\n".join("          | " + ln for ln in (e.get("source") or "").split("\n"))))
    note = "Pele %s drew %d view variant(s)%s." % (res.get("pele", "?"), res.get("checked", 0),
                                                  ", %d SVG file(s) in %s" % (len(res.get("svgs", [])), svg_dir) if svg_dir else "")
    return errs, note


# ====================================================================== HTML
def js_safe(text):
    return re.sub(r"</(script)", r"<\\/\1", text, flags=re.I)


def pele_sri():
    return "sha384-" + base64.b64encode(hashlib.sha384(PELE.read_bytes()).digest()).decode()


def build(spec, out, mode="offline"):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    spec = dict(spec, _build={"mode": mode, "pele": PELE_VERSION})
    data = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    # every <, > and & as a JSON escape: repository text can never open or close a tag or comment here
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026") \
        .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if mode == "cdn":
        tag = ('<script src="%s" integrity="%s" crossorigin="anonymous" referrerpolicy="no-referrer"></script>' % (PELE_CDN, pele_sri()))
        tpl = tpl.replace("default-src 'self' 'unsafe-inline' data: blob:;",
                          "default-src 'self' 'unsafe-inline' data: blob:; script-src 'self' 'unsafe-inline' %s;" % CDN_HOST, 1)
    else:
        tag = "<script>" + js_safe(PELE.read_text(encoding="utf-8")) + "</script>"
    # str.replace (not re.sub) so backslashes in the libraries are kept verbatim
    html = tpl.replace("<!--__PELE__-->", tag, 1)
    html = html.replace("/*__GEN__*/", js_safe(GEN.read_text(encoding="utf-8")), 1)
    html = html.replace("/*__FLOWMAP_DATA__*/null", data, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def load_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("ERROR   %s file not found: %s" % (what, path))
    except json.JSONDecodeError as e:
        print("ERROR   %s is not valid JSON: line %d col %d: %s" % (path, e.lineno, e.colno, e.msg))
    return None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="flowmap spec (hand-written views)")
    ap.add_argument("--modules", help="module analysis from analyze_modules.py (.codeflow/modules.json)")
    ap.add_argument("--out", default="codeflow-map.html")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--cdn", action="store_true", help="load Pele from cdn.jsdelivr.net (smaller file, needs internet)")
    ap.add_argument("--offline", action="store_true", help="(default) inline Pele; kept for compatibility")
    ap.add_argument("--svg-dir", help="also write one SVG per view here")
    ap.add_argument("--no-node", action="store_true", help="skip the Pele drawing check in Node")
    ap.add_argument("--node", help="path to the node executable (default: node on PATH)")
    ap.add_argument("--quiet-generated", action="store_true", help="do not list warnings for generated module views")
    a = ap.parse_args(argv)
    if not a.spec and not a.modules:
        ap.error("give a spec file, --modules, or both")
    global NODE_OVERRIDE
    NODE_OVERRIDE = a.node
    spec = load_json(a.spec, "spec") if a.spec else {}
    if spec is None:
        return 2
    if not isinstance(spec, dict):
        print("ERROR   spec: top level must be a JSON object")
        return 1
    mods = load_json(a.modules, "modules") if a.modules else None
    if a.modules and mods is None:
        return 2
    if mods and mods.get("schema", "").split("/")[0] != "codeflow-modules":
        print("ERROR   %s is not an analyze_modules.py output" % a.modules)
        return 2
    full = merge(spec, mods)
    rep = validate(full)
    errors = list(rep.errors)
    warnings = rep.warnings
    if a.quiet_generated:
        warnings = [w for w in warnings if not re.search(r"views\[(modules|changes|mod-[^\]]+)\]", w)]
    if not errors and not a.no_node:
        perr, note = pele_check(full, a.svg_dir)
        errors += perr
    else:
        note = "Pele drawing check not run." if a.no_node else ""
    for line in errors + warnings:
        print(line)
    if errors or (a.strict and warnings):
        print("\n%d error(s), %d warning(s). Fix the errors and run again." % (len(errors), len(warnings)))
        return 1
    nviews = len(full["views"])
    if a.check:
        print("OK  spec is valid: %d view(s), %d warning(s). %s" % (nviews, len(warnings), note))
        return 0
    mode = "cdn" if a.cdn else "offline"
    f = build(full, a.out, mode)
    size = f.stat().st_size / 1e6
    how = "loads the Pele library from %s when opened (needs internet; rebuild without --cdn for an offline file)" % CDN_HOST \
        if mode == "cdn" else "works fully offline"
    nmods = len(full.get("modules", []))
    print("OK  wrote %s  (%.2f MB, %d view(s)%s, %d warning(s)). %s Open it in any browser; it %s." % (
        f, size, nviews, ", %d module(s)" % nmods if nmods else "", len(warnings), note, how))
    return 0


if __name__ == "__main__":
    sys.exit(main())
