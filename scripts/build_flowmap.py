#!/usr/bin/env python3
"""Build a single, fully offline, interactive HTML flow map from a flowmap JSON spec.

Usage:
    python build_flowmap.py <flowmap.json> [--out codeflow-map.html] [--offline | --split] [--check]

  (default) small HTML (~0.1 MB) that loads Mermaid from cdn.jsdelivr.net, pinned to one
            version and protected by a Subresource Integrity hash
  --offline one self-contained ~3.6 MB HTML; no internet needed (use if the CDN is blocked)
  --split   offline, as viewer + mermaid.min.js + flowmap-data.js kept side by side
  --check   validate the spec only (no HTML written)

Standard library only (Python 3.8+). The spec format is documented in
references/spec-schema.md.
"""
import argparse
import base64
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
TEMPLATE = ASSETS / "viewer.html"
MERMAID = ASSETS / "vendor" / "mermaid.min.js"
MERMAID_VERSION = "11.17.2"   # must match assets/vendor/mermaid.min.js (the integrity hash is computed from it)
CDN_HOST = "https://cdn.jsdelivr.net"
MERMAID_CDN = f"{CDN_HOST}/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"

KINDS = {"user", "ui", "process", "service", "store", "external", "decision",
         "event", "file", "control", "ai", "schedule"}
VIEW_KINDS = {"architecture", "journey", "dataflow", "detail", "other"}
TYPES = {"flowchart", "sequence", "mermaid"}
DIRECTIONS = {"LR", "RL", "TB", "TD", "BT"}
SIMPLE_LABEL_MAX_WORDS = 6
SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(?:jdbc|postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s\"']*:[^\s\"'@]+@"),
]
PII_PATTERNS = [
    re.compile(r"(?i)\b(?:[a-z0-9._%+-]+)@(?:[a-z0-9-]+\.)+[a-z]{2,}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
]


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"ERROR   {where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"WARNING {where}: {msg}")


def _ids(items, where, rep, label="id"):
    seen = set()
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            rep.err(f"{where}[{i}]", "must be an object")
            continue
        _id = it.get("id")
        if not _id or not isinstance(_id, str):
            rep.err(f"{where}[{i}]", f"missing '{label}'")
            continue
        if _id in seen:
            rep.err(f"{where}[{i}]", f"duplicate id '{_id}'")
        seen.add(_id)
    return seen


def _check_label(obj, where, rep, need_desc=True):
    lab = obj.get("label") or obj.get("technical")
    if not lab:
        rep.err(where, "needs a 'label' (plain English) or 'technical'")
        return
    if obj.get("label") and len(str(obj["label"]).split()) > SIMPLE_LABEL_MAX_WORDS:
        rep.warn(where, f"label '{obj['label']}' is long; keep simple labels to <= {SIMPLE_LABEL_MAX_WORDS} words "
                        "and move detail into 'description'")
    if need_desc and not obj.get("description"):
        rep.warn(where, "no 'description' - stakeholders who click it will see little")


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
    if spec.get("start_view") and spec["start_view"] not in view_ids:
        rep.err("spec.start_view", f"'{spec['start_view']}' is not a view id")
    gen = spec.get("generated") or {}
    if not gen.get("date"):
        rep.warn("spec.generated", "add 'date' so readers know how current the map is")
    if not gen.get("commit"):
        rep.warn("spec.generated", "add 'commit' (git rev-parse --short HEAD) for traceability")

    tab_views = 0
    for vi, v in enumerate(views):
        if not isinstance(v, dict):
            continue
        W = f"views[{v.get('id', vi)}]"
        vtype = v.get("type", "flowchart")
        if vtype not in TYPES:
            rep.err(W, f"type '{vtype}' must be one of {sorted(TYPES)}")
            continue
        if v.get("kind", "other") not in VIEW_KINDS:
            rep.err(W, f"kind '{v.get('kind')}' must be one of {sorted(VIEW_KINDS)}")
        if v.get("kind") != "detail" and v.get("show_in_tabs", True):
            tab_views += 1
        if not v.get("title"):
            rep.err(W, "missing 'title'")
        if not v.get("summary"):
            rep.warn(W, "no 'summary' - add 1-2 plain-English sentences shown above the diagram")
        if v.get("direction") and v["direction"] not in DIRECTIONS:
            rep.err(W, f"direction must be one of {sorted(DIRECTIONS)}")

        groups = v.get("groups") or []
        group_ids = _ids(groups, W + ".groups", rep)
        for g in groups:
            if isinstance(g, dict):
                if g.get("parent") and g["parent"] not in group_ids:
                    rep.err(f"{W}.groups[{g.get('id')}]", f"parent '{g['parent']}' not found")
                if g.get("drilldown") and g["drilldown"] not in view_ids:
                    rep.err(f"{W}.groups[{g.get('id')}]", f"drilldown '{g['drilldown']}' is not a view id")
                if not (g.get("label") or g.get("technical")):
                    rep.err(f"{W}.groups[{g.get('id')}]", "needs a 'label'")

        if vtype == "mermaid":
            if not v.get("mermaid"):
                rep.err(W, "type 'mermaid' needs a 'mermaid' string")
            continue

        if vtype == "flowchart":
            nodes = v.get("nodes") or []
            if not nodes:
                rep.err(W, "flowchart needs 'nodes'")
            node_ids = _ids(nodes, W + ".nodes", rep)
            if len(nodes) > 40:
                rep.warn(W, f"{len(nodes)} boxes is a lot for one picture; split into drill-down views (aim for 5-15)")
            for n in nodes:
                if not isinstance(n, dict) or not n.get("id"):
                    continue
                NW = f"{W}.nodes[{n['id']}]"
                _check_label(n, NW, rep)
                if n.get("kind") and n["kind"] not in KINDS:
                    rep.err(NW, f"kind '{n['kind']}' must be one of {sorted(KINDS)}")
                if n.get("group") and n["group"] not in group_ids:
                    rep.err(NW, f"group '{n['group']}' not found")
                if n.get("drilldown") and n["drilldown"] not in view_ids:
                    rep.err(NW, f"drilldown '{n['drilldown']}' is not a view id")
                if n.get("confidence") not in (None, "verified", "inferred"):
                    rep.err(NW, "confidence must be 'verified' or 'inferred'")
                if not n.get("files") and n.get("confidence") != "inferred" and n.get("kind") not in ("user", "external"):
                    rep.warn(NW, "no 'files' evidence; add file:line refs or mark confidence 'inferred'")
            edges = v.get("edges") or []
            linked = set()
            for i, e in enumerate(edges):
                EW = f"{W}.edges[{i}]"
                if not isinstance(e, dict):
                    rep.err(EW, "must be an object")
                    continue
                for end in ("from", "to"):
                    if e.get(end) not in node_ids:
                        rep.err(EW, f"'{end}' = '{e.get(end)}' is not a node id in this view")
                linked.update([e.get("from"), e.get("to")])
                if e.get("style", "solid") not in ("solid", "dashed", "thick", "both"):
                    rep.err(EW, "style must be solid | dashed | thick | both")
                if not (e.get("label") or e.get("technical")):
                    rep.warn(EW, "unlabelled arrow; say what moves along it (e.g. 'sends claim details')")
            for nid in node_ids - linked:
                if len(node_ids) > 1:
                    rep.warn(f"{W}.nodes[{nid}]", "is not connected to anything")
            _check_walk(v, W, rep, node_ids, group_ids, view_ids, edges)

        if vtype == "sequence":
            parts = v.get("participants") or []
            if len(parts) < 2:
                rep.err(W, "sequence needs at least 2 'participants'")
            part_ids = _ids(parts, W + ".participants", rep)
            for p in parts:
                if isinstance(p, dict) and p.get("id"):
                    _check_label(p, f"{W}.participants[{p['id']}]", rep)
                    if p.get("kind") and p["kind"] not in KINDS:
                        rep.err(f"{W}.participants[{p['id']}]", f"kind '{p['kind']}' unknown")
                    if p.get("group") and p["group"] not in group_ids:
                        rep.err(f"{W}.participants[{p['id']}]", f"group '{p['group']}' not found")
            steps = v.get("steps") or []
            if not steps:
                rep.err(W, "sequence needs 'steps'")
            msgs = 0
            for i, s in enumerate(steps):
                SW = f"{W}.steps[{i}]"
                if not isinstance(s, dict):
                    rep.err(SW, "must be an object")
                    continue
                if s.get("section") or (s.get("note") and not s.get("from")):
                    if s.get("over") and s["over"] not in part_ids:
                        rep.err(SW, f"over '{s['over']}' not a participant")
                    continue
                msgs += 1
                for end in ("from", "to"):
                    if s.get(end) not in part_ids:
                        rep.err(SW, f"'{end}' = '{s.get(end)}' is not a participant id")
                if not (s.get("label") or s.get("technical")):
                    rep.warn(SW, "step has no label")
            if msgs > 30:
                rep.warn(W, f"{msgs} steps; consider splitting the journey into phases / views")
            for i, w in enumerate(v.get("walkthrough") or []):
                st = w.get("step")
                if st is not None and (not isinstance(st, int) or st < 0 or st >= len(steps)):
                    rep.err(f"{W}.walkthrough[{i}]", f"step {st} out of range (0-based index into steps)")

    if tab_views == 0:
        rep.err("spec", "every view is kind 'detail'; at least one top-level view is needed")
    # crude secret / personal-data sweep over all strings
    blob = json.dumps(spec, ensure_ascii=False)
    for pat in SECRET_PATTERNS:
        m = pat.search(blob)
        if m:
            rep.err("spec", f"looks like a secret or credential is embedded ('{m.group(0)[:12]}...'); "
                            "describe it instead of copying values")
    for pat in PII_PATTERNS:
        m = pat.search(blob)
        if m:
            rep.warn("spec", f"possible personal data ('{m.group(0)[:3]}...'); use field names, not real values")
    return rep


def _check_walk(v, W, rep, node_ids, group_ids, view_ids, edges):
    pairs = {(e.get("from"), e.get("to")) for e in edges if isinstance(e, dict)}
    for i, w in enumerate(v.get("walkthrough") or []):
        WW = f"{W}.walkthrough[{i}]"
        if not isinstance(w, dict) or not (w.get("text") or w.get("technical")):
            rep.err(WW, "each walkthrough step needs 'text'")
            continue
        if w.get("target") and w["target"] not in node_ids:
            rep.err(WW, f"target '{w['target']}' is not a node id")
        if w.get("group") and w["group"] not in group_ids:
            rep.err(WW, f"group '{w['group']}' not found")
        if w.get("edge") and tuple(w["edge"]) not in pairs:
            rep.err(WW, f"edge {w['edge']} does not exist in this view")
        if w.get("drill") and w["drill"] not in view_ids:
            rep.err(WW, f"drill '{w['drill']}' is not a view id")


def js_safe(text):
    # prevent an inlined script from closing its <script> element early
    return re.sub(r"</(script)", r"<\\/\1", text, flags=re.I)


def mermaid_sri():
    digest = hashlib.sha384(MERMAID.read_bytes()).digest()
    return "sha384-" + base64.b64encode(digest).decode()


def build(spec, out, mode="cdn"):
    """mode: 'cdn' (small file, Mermaid from jsDelivr), 'offline' (one big self-contained file),
    'split' (viewer + mermaid.min.js + flowmap-data.js side by side, all offline)."""
    tpl = TEMPLATE.read_text(encoding="utf-8")
    spec = dict(spec, _build={"mode": mode, "mermaid": MERMAID_VERSION})
    data = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if mode == "split":
        html = tpl.replace("<script>/*__MERMAID_JS__*/</script>", "").replace("/*__FLOWMAP_DATA__*/null", "null")
        out.write_text(html, encoding="utf-8")
        shutil.copyfile(MERMAID, out.parent / "mermaid.min.js")
        (out.parent / "flowmap-data.js").write_text("window.FLOWMAP = " + data + ";\n", encoding="utf-8")
        return [out, out.parent / "mermaid.min.js", out.parent / "flowmap-data.js"]
    if mode == "cdn":
        tag = (f'<script src="{MERMAID_CDN}" integrity="{mermaid_sri()}" crossorigin="anonymous" '
               f'referrerpolicy="no-referrer"></script>')
        html = tpl.replace("<script>/*__MERMAID_JS__*/</script>", tag, 1)
        # allow scripts from the CDN host only; data requests (fetch/XHR) stay blocked
        html = html.replace("default-src 'self' 'unsafe-inline' data: blob:;",
                            "default-src 'self' 'unsafe-inline' data: blob:; script-src 'self' 'unsafe-inline' "
                            + CDN_HOST + ";", 1)
    else:
        mer = js_safe(MERMAID.read_text(encoding="utf-8"))
        # str.replace (not re.sub) so backslashes in the library are kept verbatim
        html = tpl.replace("/*__MERMAID_JS__*/", mer, 1)
    html = html.replace("/*__FLOWMAP_DATA__*/null", data, 1)
    out.write_text(html, encoding="utf-8")
    return [out]


def main(argv=None):
    # Windows consoles may not be UTF-8; never crash on an emoji in a label
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out", default="codeflow-map.html")
    ap.add_argument("--check", action="store_true")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--offline", action="store_true", help="embed Mermaid: one ~3.6 MB file that needs no internet")
    g.add_argument("--split", action="store_true", help="offline, as three small files kept side by side")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    a = ap.parse_args(argv)
    try:
        spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR   {a.spec} is not valid JSON: line {e.lineno} col {e.colno}: {e.msg}")
        return 2
    rep = validate(spec)
    for line in rep.errors + rep.warnings:
        print(line)
    if rep.errors or (a.strict and rep.warnings):
        print(f"\n{len(rep.errors)} error(s), {len(rep.warnings)} warning(s). Fix the errors and run again.")
        return 1
    nviews = len(spec["views"])
    if a.check:
        print(f"OK  spec is valid: {nviews} view(s), {len(rep.warnings)} warning(s).")
        return 0
    mode = "offline" if a.offline else "split" if a.split else "cdn"
    files = build(spec, a.out, mode)
    size = sum(f.stat().st_size for f in files) / 1e6
    how = ("loads the Mermaid library from " + CDN_HOST + " when opened (needs internet; if the diagram "
           "does not appear, rebuild with --offline)") if mode == "cdn" else "works fully offline"
    print(f"OK  wrote {', '.join(str(f) for f in files)}  ({size:.2f} MB, {nviews} view(s), "
          f"{len(rep.warnings)} warning(s)). Open it in any browser; it {how}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
