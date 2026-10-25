/* codeflow-map: turns flowmap spec views into Mermaid text for Pele.
 * Shared by the viewer (inlined into the HTML) and by scripts/pele_check.cjs (build-time validation),
 * so what the builder validates is exactly what the browser draws.
 * No dependencies. Works in browsers and in Node (via vm). MIT licence (same as the skill).
 */
(function (root) {
  'use strict';

  // Node kinds: name and icon are shown in the legend and panel; shape is the Mermaid flowchart shape.
  // Colours live in the viewer's CSS (themeable); `light` is only used for portable .mmd exports.
  var KINDS = {
    user:     { name: 'Person / role',        icon: '👤', shape: ['([', '])'], light: ['#FDE7D3', '#C2662D'] },
    ui:       { name: 'Screen / app',         icon: '🖥️', shape: ['(', ')'],   light: ['#DCEBFB', '#2F6FB3'] },
    process:  { name: 'Process / logic',      icon: '⚙️', shape: ['[', ']'],   light: ['#E8E6FA', '#5B4FC4'] },
    service:  { name: 'Service / API',        icon: '🔌', shape: ['[', ']'],   light: ['#E8E6FA', '#5B4FC4'] },
    store:    { name: 'Data store',           icon: '🗄️', shape: ['[(', ')]'], light: ['#DDF3E6', '#2E8B57'] },
    external: { name: 'External system',      icon: '🌐', shape: ['[[', ']]'], light: ['#EFEFEC', '#77736A'] },
    decision: { name: 'Decision / check',     icon: '❓', shape: ['{', '}'],   light: ['#FFF4CC', '#B08900'] },
    event:    { name: 'Message / event',      icon: '📨', shape: ['>', ']'],   light: ['#FBE3EF', '#B03A7A'] },
    file:     { name: 'File / report',        icon: '📄', shape: ['[/', '/]'], light: ['#EEF0F4', '#56607A'] },
    control:  { name: 'Control / safeguard',  icon: '🛡️', shape: ['{{', '}}'], light: ['#DFF3F1', '#00796B'] },
    ai:       { name: 'AI / model',           icon: '✨', shape: ['[', ']'],   light: ['#F3E8FF', '#8B3FC9'] },
    schedule: { name: 'Scheduled job',        icon: '⏱️', shape: ['[', ']'],   light: ['#E8EEF9', '#4A64A8'] },
    module:   { name: 'Code module',          icon: '🧩', shape: ['[', ']'],   light: ['#E6F0FA', '#3A6EA5'] },
    function: { name: 'Function / method',    icon: 'ƒ',  shape: ['(', ')'],   light: ['#F1EEFB', '#6A5ACD'] },
    package:  { name: 'Third-party library',  icon: '📦', shape: ['[[', ']]'], light: ['#F3F1EC', '#8A7F6A'] },
    start:    { name: 'Start',                icon: '▶',  shape: ['([', '])'], light: ['#DDF3E6', '#2E8B57'] },
    end:      { name: 'End / return',         icon: '■',  shape: ['([', '])'], light: ['#ECEEF2', '#5F6B7A'] },
    loop:     { name: 'Loop',                 icon: '🔁', shape: ['{{', '}}'], light: ['#E8EEF9', '#4A64A8'] },
    error:    { name: 'Error / exception',    icon: '⚠️', shape: ['[', ']'],   light: ['#FDE8E4', '#C2410C'] }
  };
  var VIEW_TYPES = ['flowchart', 'sequence', 'class', 'er', 'state', 'mermaid'];

  function kindOf(k) { return KINDS[k] ? k : 'process'; }
  function pick(o, mode) {
    if (!o) return '';
    var t = mode === 'technical' ? (o.technical || o.label) : (o.label || o.technical);
    return t == null || t === '' ? (o.id == null ? '' : String(o.id)) : String(t);
  }
  function heatClass(h) {
    if (typeof h !== 'number' || !(h > 0.12)) return '';
    return 'heat' + (h > 0.75 ? 4 : h > 0.5 ? 3 : h > 0.3 ? 2 : 1);
  }

  // ---------------------------------------------------------------- text escaping
  // Quoted flowchart label: entity codes for characters Mermaid treats specially, <br/> for newlines.
  function fcText(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '#amp;').replace(/"/g, '#quot;').replace(/</g, '#lt;').replace(/>/g, '#gt;')
      .replace(/\|/g, '#124;').replace(/`/g, '#96;')
      .replace(/\r?\n|\\n/g, '<br/>');
  }
  // Sequence messages, aliases and notes: no quoting exists, so drop the characters that end a statement.
  function seqText(s) {
    var t = String(s == null ? '' : s).replace(/;/g, ',').replace(/#/g, 'No.').replace(/\r?\n|\\n/g, ' ')
      .replace(/[<>]/g, '').replace(/%%/g, '%').trim();
    return t || ' ';
  }
  // Identifier-ish words (class member types, ER attribute names/types, namespaces).
  function word(s, fallback) {
    var t = String(s == null ? '' : s).replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
    if (!t) t = fallback || 'x';
    if (/^[0-9]/.test(t)) t = '_' + t;
    return t;
  }
  function plain(s, max) { // one line, no Mermaid-structural characters
    var t = String(s == null ? '' : s).replace(/\r?\n|\\n/g, ' ').replace(/["{}]/g, "'").replace(/[;#]/g, ' ').trim();
    return max && t.length > max ? t.slice(0, max - 1) + '…' : t;
  }

  // ---------------------------------------------------------------- flowchart
  function genFlowchart(v, o) {
    var nodes = v.nodes || [], edges = v.edges || [], groups = v.groups || [];
    var idMap = {}, rev = {}, gMap = {}, gRev = {};
    nodes.forEach(function (n, i) { idMap[n.id] = 'n' + i; rev['n' + i] = n.id; });
    groups.forEach(function (g, i) { gMap[g.id] = 'g' + i; gRev['g' + i] = g.id; });
    var icons = o.icons !== false && v.icons !== false;
    var lines = ['flowchart ' + (v.direction || 'LR')];
    var nodeLine = function (n) {
      var k = kindOf(n.kind), sh = KINDS[k].shape;
      var txt = (icons ? KINDS[k].icon + ' ' : '') + pick(n, o.mode);
      return idMap[n.id] + sh[0] + '"' + fcText(txt) + '"' + sh[1];
    };
    var kids = {}, inGroup = {};
    groups.forEach(function (g) { var p = g.parent && gMap[g.parent] ? g.parent : ''; (kids[p] = kids[p] || []).push(g); });
    nodes.forEach(function (n) { if (n.group && gMap[n.group]) (inGroup[n.group] = inGroup[n.group] || []).push(n); });
    var emit = function (g, depth) {
      var pad = new Array(depth + 1).join('  ');
      lines.push(pad + 'subgraph ' + gMap[g.id] + '["' + fcText(pick(g, o.mode)) + '"]');
      if (g.direction) lines.push(pad + '  direction ' + g.direction);
      (kids[g.id] || []).forEach(function (c) { emit(c, depth + 1); });
      (inGroup[g.id] || []).forEach(function (n) { lines.push(pad + '  ' + nodeLine(n)); });
      lines.push(pad + 'end');
    };
    (kids[''] || []).forEach(function (g) { emit(g, 1); });
    nodes.forEach(function (n) { if (!(n.group && gMap[n.group])) lines.push('  ' + nodeLine(n)); });
    var pairKeys = [], sensIdx = [];
    edges.forEach(function (e, i) {
      var a = idMap[e.from], b = idMap[e.to];
      pairKeys.push('L_' + a + '_' + b);
      var lbl = (o.edgeLabels === false || v.edge_labels === false) ? '' : (o.mode === 'technical' ? (e.technical || e.label) : (e.label != null ? e.label : e.technical)) || '';
      if (e.sensitive && o.sens) { lbl = '🔒 ' + lbl; sensIdx.push(i); }
      var st = e.style || 'solid';
      var arrow = st === 'dashed' ? '-.->' : st === 'thick' ? '==>' : st === 'both' ? '<-->' : st === 'plain' ? '---' : '-->';
      lines.push('  ' + a + ' ' + arrow + (lbl ? '|"' + fcText(lbl.trim()) + '"|' : '') + ' ' + b);
    });
    // classes: the viewer styles these with CSS variables (themes); portable exports add classDef colours
    var byClass = {};
    var add = function (cls, id) { (byClass[cls] = byClass[cls] || []).push(id); };
    nodes.forEach(function (n) {
      var id = idMap[n.id];
      add('k_' + kindOf(n.kind), id);
      if (n.confidence === 'inferred') add('inferred', id);
      var h = heatClass(n.heat); if (h) add(h, id);
      if (n.changed) add('changed', id);
      if (n.impact) add('impact', id);
      if (n.drilldown || n.module) add('drill', id);
    });
    if (o.portable) {
      Object.keys(KINDS).forEach(function (k) {
        if (byClass['k_' + k]) lines.push('  classDef k_' + k + ' fill:' + KINDS[k].light[0] + ',stroke:' + KINDS[k].light[1] + ',stroke-width:1.6px,color:#1F2328');
      });
      if (byClass.inferred) lines.push('  classDef inferred stroke-dasharray:6 4');
      if (byClass.changed) lines.push('  classDef changed stroke:#D97706,stroke-width:3px');
      if (byClass.impact) lines.push('  classDef impact stroke-dasharray:4 3');
    }
    Object.keys(byClass).forEach(function (c) {
      if (o.portable && /^(heat|drill)/.test(c)) return;
      lines.push('  class ' + byClass[c].join(',') + ' ' + c);
    });
    if (o.portable && sensIdx.length) lines.push('  linkStyle ' + sensIdx.join(',') + ' stroke:#C2410C,stroke-width:2.6px');
    return { code: lines.join('\n'), meta: { type: 'flowchart', idMap: idMap, rev: rev, gMap: gMap, gRev: gRev, pairKeys: pairKeys } };
  }

  // ---------------------------------------------------------------- sequence
  function genSequence(v, o) {
    var parts = v.participants || [];
    var idMap = {};
    parts.forEach(function (p, i) { idMap[p.id] = 'p' + i; });
    var lines = ['%%{init: {"sequence": {"mirrorActors": false}}}%%', 'sequenceDiagram'];
    if (v.numbered !== false) lines.push('  autonumber');
    var icons = o.icons !== false && v.icons !== false;
    var groups = {};
    (v.groups || []).forEach(function (g) { groups[g.id] = g; });
    var boxes = [], open = null;
    parts.forEach(function (p) {
      var g = groups[p.group] ? p.group : null;
      if (open && g !== open) { lines.push('  end'); open = null; }
      if (g && g !== open) { lines.push('  box transparent ' + seqText(pick(groups[g], o.mode))); boxes.push(g); open = g; }
      var k = kindOf(p.kind);
      var txt = (icons && k !== 'user' ? KINDS[k].icon + ' ' : '') + pick(p, o.mode);
      lines.push((open ? '    ' : '  ') + (k === 'user' ? 'actor ' : 'participant ') + idMap[p.id] + ' as ' + seqText(txt));
    });
    if (open) lines.push('  end');
    var msgToStep = [], noteToStep = [];
    var first = parts.length ? idMap[parts[0].id] : 'p0', last = parts.length ? idMap[parts[parts.length - 1].id] : 'p0';
    (v.steps || []).forEach(function (s, i) {
      if (s.section) { lines.push('  Note over ' + first + (last !== first ? ',' + last : '') + ': ' + seqText(s.section)); noteToStep.push(i); return; }
      if (!s.from) { if (s.note) { lines.push('  Note over ' + (idMap[s.over] || first) + ': ' + seqText(s.note)); noteToStep.push(i); } return; }
      var lbl = (o.mode === 'technical' ? (s.technical || s.label) : (s.label || s.technical)) || '';
      if (s.sensitive && o.sens) lbl = '🔒 ' + lbl;
      var arrow = s.reply ? '-->>' : (s.async ? '-)' : '->>');
      lines.push('  ' + idMap[s.from] + arrow + idMap[s.to] + ': ' + seqText(lbl));
      msgToStep.push(i);
      if (s.note) { lines.push('  Note right of ' + idMap[s.to] + ': ' + seqText(s.note)); noteToStep.push(-1); }
    });
    return { code: lines.join('\n'), meta: { type: 'sequence', idMap: idMap, msgToStep: msgToStep, noteToStep: noteToStep, boxes: boxes } };
  }

  // ---------------------------------------------------------------- class diagram
  var REL = { inheritance: ['<|--', true], realization: ['..|>', false], composition: ['*--', false],
              aggregation: ['o--', false], association: ['-->', false], dependency: ['..>', false], link: ['--', false] };
  function member(s) {
    return plain(s, 70).replace(/[<>]/g, '~').replace(/:/g, ' : ').replace(/\s+/g, ' ').replace(/^\s*([+\-#~])\s+/, '$1').trim();
  }
  function genClass(v, o) {
    var classes = v.classes || [], rels = v.relations || [];
    var idMap = {}, rev = {}, nsMap = {}, nsRev = {}, used = {};
    classes.forEach(function (c, i) { idMap[c.id] = 'c' + i; rev['c' + i] = c.id; });
    (v.groups || []).forEach(function (g) {
      var w = word(pick(g, o.mode), 'area'), k = w, n = 2;
      while (used[k]) k = w + '_' + (n++);
      used[k] = 1; nsMap[g.id] = k; nsRev[k] = g.id;
    });
    var lines = ['classDiagram'];
    if (v.direction) lines.push('  direction ' + v.direction);
    var decl = function (c, pad) {
      var label = pick(c, o.mode).replace(/[<>]/g, '~');
      var body = [];
      if (c.stereotype) body.push('<<' + word(c.stereotype) + '>>');
      (c.attributes || []).slice(0, o.maxMembers || 14).forEach(function (a) { body.push(member(a)); });
      (c.methods || []).slice(0, o.maxMembers || 14).forEach(function (m) {
        var t = member(m); if (!/\(/.test(t)) t += '()'; body.push(t);
      });
      var more = (c.attributes || []).length + (c.methods || []).length - body.length + (c.stereotype ? 1 : 0);
      if (more > 0) body.push('… ' + more + ' more');
      lines.push(pad + 'class ' + idMap[c.id] + '["' + plain(label, 60).replace(/"/g, "'") + '"]' + (body.length ? ' {' : ''));
      if (body.length) { body.forEach(function (b) { lines.push(pad + '  ' + b); }); lines.push(pad + '}'); }
    };
    var byNs = {};
    classes.forEach(function (c) { if (c.group && nsMap[c.group]) (byNs[c.group] = byNs[c.group] || []).push(c); });
    Object.keys(byNs).forEach(function (g) {
      lines.push('  namespace ' + nsMap[g] + ' {');
      byNs[g].forEach(function (c) { decl(c, '    '); });
      lines.push('  }');
    });
    classes.forEach(function (c) { if (!(c.group && nsMap[c.group])) decl(c, '  '); });
    var relIndex = [];
    rels.forEach(function (r, i) {
      var a = idMap[r.from], b = idMap[r.to]; if (!a || !b) return;
      var t = REL[r.type] || REL.association;
      var lbl = (o.mode === 'technical' ? (r.technical || r.label) : (r.label || r.technical)) || '';
      lbl = lbl ? ' : ' + plain(lbl, 40).replace(/:/g, ' ') : '';
      lines.push('  ' + (t[1] ? b + ' ' + t[0] + ' ' + a : a + ' ' + t[0] + ' ' + b) + lbl);
      relIndex.push(i);
    });
    var byClass = {};
    var add = function (cls, id) { (byClass[cls] = byClass[cls] || []).push(id); };
    classes.forEach(function (c) {
      var id = idMap[c.id];
      add('k_' + kindOf(c.kind || 'process'), id);
      if (c.external) add('ext', id);
      if (heatClass(c.heat)) add(heatClass(c.heat), id);
      if (c.changed) add('changed', id);
      if (c.confidence === 'inferred') add('inferred', id);
    });
    Object.keys(byClass).forEach(function (cls) {
      if (o.portable && /^heat/.test(cls)) return;
      lines.push('  cssClass "' + byClass[cls].join(',') + '" ' + cls);
    });
    return { code: lines.join('\n'), meta: { type: 'class', idMap: idMap, rev: rev, nsMap: nsMap, nsRev: nsRev, relIndex: relIndex } };
  }

  // ---------------------------------------------------------------- ER diagram
  var CARD_L = { 'one': '||', 'zero-one': '|o', 'many': '}o', 'one-many': '}|' };
  var CARD_R = { 'one': '||', 'zero-one': 'o|', 'many': 'o{', 'one-many': '|{' };
  function genER(v, o) {
    var ents = v.entities || [], rels = v.relations || [];
    var idMap = {}, rev = {};
    ents.forEach(function (e, i) { idMap[e.id] = 'e' + i; rev['e' + i] = e.id; });
    var lines = ['erDiagram'];
    if (v.direction) lines.push('  direction ' + v.direction);
    ents.forEach(function (e) {
      var head = '  ' + idMap[e.id] + '["' + plain(pick(e, o.mode), 60).replace(/"/g, "'") + '"]';
      var attrs = (e.attributes || []).slice(0, o.maxMembers || 24);
      if (!attrs.length) { lines.push(head); return; }
      lines.push(head + ' {');
      attrs.forEach(function (a) {
        if (typeof a === 'string') a = { name: a };
        var t = String(a.type || 'field').replace(/[^A-Za-z0-9_\-\[\]()]/g, '_').replace(/^[^A-Za-z_]+/, '') || 'field';
        var keys = String(a.key || '').toUpperCase().split(/[\s,]+/).filter(function (k) { return k === 'PK' || k === 'FK' || k === 'UK'; });
        var cm = a.comment || (a.sensitive ? 'sensitive' : '');
        var nm = word(a.name, 'field'); if (/^(pk|fk|uk)$/i.test(nm)) nm += '_';
        if (/^(pk|fk|uk)$/i.test(t)) t += '_';
        lines.push('    ' + t + ' ' + nm + (keys.length ? ' ' + keys.join(', ') : '') + (cm ? ' "' + plain(cm, 40).replace(/"/g, "'") + '"' : ''));
      });
      var extra = (e.attributes || []).length - attrs.length;
      if (extra > 0) lines.push('    more _' + extra + '_fields');
      lines.push('  }');
    });
    var relIndex = [];
    rels.forEach(function (r, i) {
      var a = idMap[r.from], b = idMap[r.to]; if (!a || !b) return;
      var l = CARD_L[r.card_from || 'one'] || '||', rr = CARD_R[r.card_to || 'many'] || 'o{';
      var lbl = (o.mode === 'technical' ? (r.technical || r.label) : (r.label || r.technical)) || 'relates to';
      lines.push('  ' + a + ' ' + l + (r.identifying === false ? '..' : '--') + rr + ' ' + b + ' : "' + plain(lbl, 40).replace(/"/g, "'") + '"');
      relIndex.push(i);
    });
    return { code: lines.join('\n'), meta: { type: 'er', idMap: idMap, rev: rev, relIndex: relIndex } };
  }

  // ---------------------------------------------------------------- state diagram
  function genState(v, o) {
    var states = v.states || [], trans = v.transitions || [];
    var idMap = {}, rev = {};
    states.forEach(function (s, i) { idMap[s.id] = 's' + i; rev['s' + i] = s.id; });
    var lines = ['stateDiagram-v2'];
    if (v.direction) lines.push('  direction ' + v.direction);
    states.forEach(function (s) {
      if (s.kind === 'choice') lines.push('  state ' + idMap[s.id] + ' <<choice>>');
      else lines.push('  ' + idMap[s.id] + ' : ' + plain(pick(s, o.mode), 60).replace(/:/g, ' '));
    });
    var transIndex = [];
    trans.forEach(function (t, i) {
      var a = t.from === '*' ? '[*]' : idMap[t.from], b = t.to === '*' ? '[*]' : idMap[t.to];
      if (!a || !b) return;
      var lbl = (o.mode === 'technical' ? (t.technical || t.label) : (t.label || t.technical)) || '';
      lines.push('  ' + a + ' --> ' + b + (lbl ? ' : ' + plain(lbl, 40).replace(/:/g, ' ') : ''));
      transIndex.push(i);
    });
    return { code: lines.join('\n'), meta: { type: 'state', idMap: idMap, rev: rev, transIndex: transIndex } };
  }

  /** Generate Mermaid for a view.
   * opts: { mode: 'simple'|'technical', sens: true, icons: true, portable: false, edgeLabels: true }
   * returns { code, meta } where meta maps spec ids to the ids Pele puts in the SVG. */
  function gen(view, opts) {
    var o = opts || {};
    o = { mode: o.mode || 'simple', sens: o.sens !== false, icons: o.icons, portable: !!o.portable, edgeLabels: o.edgeLabels, maxMembers: o.maxMembers };
    var t = view.type || 'flowchart';
    if (t === 'sequence') return genSequence(view, o);
    if (t === 'class') return genClass(view, o);
    if (t === 'er') return genER(view, o);
    if (t === 'state') return genState(view, o);
    if (t === 'mermaid') return { code: String(view.mermaid || ''), meta: { type: 'mermaid' } };
    return genFlowchart(view, o);
  }

  root.FlowmapGen = { KINDS: KINDS, VIEW_TYPES: VIEW_TYPES, gen: gen, kindOf: kindOf, heatClass: heatClass, version: '2.0.0' };
})(typeof globalThis !== 'undefined' ? globalThis : this);
