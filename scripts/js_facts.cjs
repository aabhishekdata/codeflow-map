#!/usr/bin/env node
/* codeflow-map: read-only static facts for JavaScript / TypeScript files, for analyze_modules.py.
 *
 * Usage:  node js_facts.cjs < request.json > facts.json
 *   request: { "root": "/abs/repo", "files": ["src/a.ts", ...], "cfg": true, "maxCfgNodes": 60 }
 *
 * Parses each file with the vendored Babel parser (MIT, ../assets/vendor/babel-parser.js). Never executes
 * project code, never follows network or package resolution. Node 14+.
 * Output: { "files": { "<path>": { imports, reexports, exports, classes, functions, error? } } }
 */
'use strict';
const fs = require('fs');
const path = require('path');
const babel = require(path.join(__dirname, '..', 'assets', 'vendor', 'babel-parser.js'));

const MAX_BYTES = 1500000;
const SKIP_KEYS = new Set(['loc', 'start', 'end', 'leadingComments', 'trailingComments', 'innerComments', 'extra', 'range', 'tokens', 'comments']);
const FN_TYPES = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression', 'ClassMethod', 'ClassPrivateMethod', 'ObjectMethod', 'TSDeclareFunction', 'TSDeclareMethod']);
const ROUTE_METHODS = new Set(['get', 'post', 'put', 'delete', 'patch', 'all', 'options', 'head']);
const ROUTER_NAMES = /^(app|router|server|api|fastify|r|routes?)$/i;

function readStdin() {
  return new Promise((resolve) => { let s = ''; process.stdin.setEncoding('utf8'); process.stdin.on('data', (d) => { s += d; }); process.stdin.on('end', () => resolve(s)); });
}

function children(node) {
  const out = [];
  for (const k in node) {
    if (SKIP_KEYS.has(k)) continue;
    const v = node[k];
    if (Array.isArray(v)) { for (const x of v) if (x && typeof x.type === 'string') out.push(x); }
    else if (v && typeof v.type === 'string') out.push(v);
  }
  return out;
}
function walk(node, fn, parent) { // fn returns false to skip children
  if (!node || typeof node.type !== 'string') return;
  if (fn(node, parent) === false) return;
  for (const c of children(node)) walk(c, fn, node);
}
const line = (n) => (n && n.loc ? n.loc.start.line : 0);
const endLine = (n) => (n && n.loc ? n.loc.end.line : 0);

function scriptBlock(text, ext) { // .vue / .svelte: analyse the <script> block, keep line numbers
  if (ext !== '.vue' && ext !== '.svelte') return { code: text, lang: ext };
  const m = /<script\b([^>]*)>([\s\S]*?)<\/script>/i.exec(text);
  if (!m) return { code: '', lang: '.js' };
  const before = text.slice(0, m.index + m[0].indexOf('>') + 1);
  const pad = '\n'.repeat((before.match(/\n/g) || []).length);
  return { code: pad + m[2], lang: /lang=["']ts/.test(m[1]) ? '.ts' : '.js' };
}

function parse(code, ext) {
  const ts = ext === '.ts' || ext === '.tsx' || ext === '.mts' || ext === '.cts';
  const jsx = ext !== '.ts' && ext !== '.mts' && ext !== '.cts';
  const plugins = ['decorators-legacy', 'classProperties', 'classPrivateProperties', 'classPrivateMethods', 'dynamicImport',
    'importAttributes', 'topLevelAwait', 'optionalChaining', 'nullishCoalescingOperator', 'objectRestSpread', 'exportDefaultFrom'];
  if (ts) plugins.push('typescript'); else plugins.push('flow');
  if (jsx) plugins.push('jsx');
  return babel.parse(code, { sourceType: 'unambiguous', errorRecovery: true, allowReturnOutsideFunction: true,
    allowImportExportEverywhere: true, allowAwaitOutsideFunction: true, plugins });
}

function srcOf(code, n) { return n && typeof n.start === 'number' ? code.slice(n.start, n.end) : ''; }
function oneLine(s, max) {
  const t = String(s || '').replace(/\s+/g, ' ').trim();
  return t.length > max ? t.slice(0, max - 1) + '…' : t;
}
function nameOfKey(k) {
  if (!k) return '';
  if (k.type === 'Identifier') return k.name;
  if (k.type === 'PrivateName') return '#' + (k.id ? k.id.name : '');
  if (k.type === 'StringLiteral' || k.type === 'NumericLiteral') return String(k.value);
  return '[computed]';
}
function exprName(n) { // a.b.c -> "a.b.c", this.x -> "this.x"
  if (!n) return '';
  if (n.type === 'Identifier') return n.name;
  if (n.type === 'ThisExpression') return 'this';
  if (n.type === 'Super') return 'super';
  if (n.type === 'MemberExpression' || n.type === 'OptionalMemberExpression') {
    const o = exprName(n.object); const p = n.computed ? '[]' : nameOfKey(n.property);
    return o ? o + '.' + p : p;
  }
  if (n.type === 'CallExpression' || n.type === 'OptionalCallExpression') return exprName(n.callee) + '()';
  if (n.type === 'TSNonNullExpression' || n.type === 'TSAsExpression') return exprName(n.expression);
  return '';
}
function typeText(code, t) { return t ? oneLine(srcOf(code, t.typeAnnotation || t), 40) : ''; }
function params(code, ps) {
  return (ps || []).map((p) => {
    if (p.type === 'Identifier') return p.name + (p.typeAnnotation ? ': ' + typeText(code, p.typeAnnotation) : '');
    if (p.type === 'AssignmentPattern' && p.left.type === 'Identifier') return p.left.name + '?';
    if (p.type === 'RestElement') return '...' + (p.argument.name || 'args');
    if (p.type === 'TSParameterProperty') return params(code, [p.parameter])[0];
    if (p.type === 'ObjectPattern') return '{' + p.properties.map((x) => nameOfKey(x.key) || '...').slice(0, 4).join(', ') + '}';
    return oneLine(srcOf(code, p), 20);
  });
}

// ---------------------------------------------------------------- complexity
function complexity(fnNode) {
  let c = 1;
  walk(fnNode.body, (n) => {
    if (n !== fnNode.body && FN_TYPES.has(n.type)) return false; // nested functions count separately
    switch (n.type) {
      case 'IfStatement': case 'ConditionalExpression': case 'ForStatement': case 'ForInStatement': case 'ForOfStatement':
      case 'WhileStatement': case 'DoWhileStatement': case 'CatchClause': c++; break;
      case 'SwitchCase': if (n.test) c++; break;
      case 'LogicalExpression': if (n.operator === '&&' || n.operator === '||' || n.operator === '??') c++; break;
      default:
    }
    return true;
  });
  return c;
}

// ---------------------------------------------------------------- control-flow graph
function buildCfg(code, fnNode, title, maxNodes) {
  for (let depth = 6; depth >= 1; depth--) {
    const g = cfgAtDepth(code, fnNode, title, depth);
    if (g.nodes.length <= maxNodes || depth === 1) { g.depth = depth; return g; }
  }
  return null;
}
function cfgAtDepth(code, fnNode, title, maxDepth) {
  const nodes = [], edges = [];
  const add = (t, label, ln) => { const id = 'c' + nodes.length; nodes.push({ id, t, label, line: ln }); return id; };
  const link = (preds, to) => { for (const [p, l] of preds) edges.push({ from: p, to, label: l || '' }); };
  const label = (n) => oneLine(srcOf(code, n).split('\n')[0], 46);
  const start = add('start', title, line(fnNode));
  const loops = []; // { node, breaks: [] }
  const tries = []; // handler ids for throw edges

  const isCompound = (s) => /^(IfStatement|ForStatement|ForInStatement|ForOfStatement|WhileStatement|DoWhileStatement|TryStatement|SwitchStatement|ReturnStatement|ThrowStatement|BreakStatement|ContinueStatement|BlockStatement|LabeledStatement)$/.test(s.type);

  function blockLabel(buf) {
    const shown = buf.slice(0, 3).map((s) => {
      if (s.type === 'IfStatement' || /^(For|While|DoWhile|Switch|Try)/.test(s.type)) return label(s).replace(/\{.*$/, '').trim() + ' { … }';
      return label(s);
    });
    const more = buf.length - shown.length;
    return shown.join('\n') + (more > 0 ? '\n… +' + more + ' more' : '');
  }
  function seq(stmts, preds, depth) {
    let buf = [];
    const flush = () => {
      if (!buf.length) return;
      const n = add('block', blockLabel(buf), line(buf[0]));
      link(preds, n); preds = [[n, '']]; buf = [];
    };
    for (const s of stmts) {
      if (!preds.length) break; // unreachable code after return / throw
      const simple = !isCompound(s) || (depth >= maxDepth && !/^(ReturnStatement|ThrowStatement|BreakStatement|ContinueStatement)$/.test(s.type));
      if (simple) { buf.push(s); continue; }
      flush();
      preds = stmt(s, preds, depth);
    }
    if (preds.length) flush();
    return preds;
  }
  function stmt(s, preds, depth) {
    switch (s.type) {
      case 'BlockStatement': return seq(s.body, preds, depth);
      case 'LabeledStatement': return stmt(s.body, preds, depth);
      case 'IfStatement': {
        const c = add('cond', oneLine(srcOf(code, s.test), 46) + '?', line(s)); link(preds, c);
        const t = stmt(s.consequent, [[c, 'yes']], depth + 1);
        const f = s.alternate ? stmt(s.alternate, [[c, 'no']], depth + 1) : [[c, 'no']];
        return t.concat(f);
      }
      case 'ForStatement': case 'ForInStatement': case 'ForOfStatement': case 'WhileStatement': case 'DoWhileStatement': {
        let head;
        if (s.type === 'ForOfStatement' || s.type === 'ForInStatement') head = 'for ' + oneLine(srcOf(code, s.left), 20) + (s.type === 'ForOfStatement' ? ' of ' : ' in ') + oneLine(srcOf(code, s.right), 24);
        else if (s.type === 'ForStatement') head = 'for (' + oneLine(srcOf(code, s.test), 30) + ')';
        else head = (s.type === 'DoWhileStatement' ? 'do … while ' : 'while ') + oneLine(srcOf(code, s.test), 30);
        const l = add('loop', head, line(s)); link(preds, l);
        loops.push({ node: l, breaks: [] });
        const b = stmt(s.body, [[l, s.type.indexOf('For') === 0 ? 'each' : 'repeat']], depth + 1);
        link(b, l);
        const lp = loops.pop();
        return [[l, 'done']].concat(lp.breaks);
      }
      case 'SwitchStatement': {
        const c = add('cond', 'switch ' + oneLine(srcOf(code, s.discriminant), 36), line(s)); link(preds, c);
        loops.push({ node: null, breaks: [], isSwitch: true });
        let out = [], fall = [], hasDefault = false;
        for (const cs of s.cases) {
          const cl = cs.test ? 'case ' + oneLine(srcOf(code, cs.test), 24) : 'default';
          if (!cs.test) hasDefault = true;
          const preds2 = [[c, cl]].concat(fall);
          fall = cs.consequent.length ? seq(cs.consequent, preds2, depth + 1) : preds2;
        }
        out = out.concat(fall);
        const sw = loops.pop();
        out = out.concat(sw.breaks);
        if (!hasDefault) out.push([c, 'no match']);
        return out;
      }
      case 'TryStatement': {
        const t = add('try', 'try', line(s)); link(preds, t);
        tries.push(t);
        let out = stmt(s.block, [[t, '']], depth + 1);
        tries.pop();
        if (s.handler) {
          const h = add('catch', 'catch' + (s.handler.param ? ' (' + oneLine(srcOf(code, s.handler.param), 20) + ')' : ''), line(s.handler));
          edges.push({ from: t, to: h, label: 'error' });
          out = out.concat(stmt(s.handler.body, [[h, '']], depth + 1));
        }
        if (s.finalizer) {
          const f = add('finally', 'finally', line(s.finalizer)); link(out, f);
          out = stmt(s.finalizer, [[f, '']], depth + 1);
        }
        return out;
      }
      case 'ReturnStatement': {
        const r = add('return', s.argument ? 'return ' + oneLine(srcOf(code, s.argument), 40) : 'return', line(s)); link(preds, r);
        return [];
      }
      case 'ThrowStatement': {
        const r = add('raise', 'throw ' + oneLine(srcOf(code, s.argument), 40), line(s)); link(preds, r);
        return [];
      }
      case 'BreakStatement': { const lp = loops[loops.length - 1]; if (lp) lp.breaks.push(...preds); return []; }
      case 'ContinueStatement': {
        let lp = null; for (let i = loops.length - 1; i >= 0; i--) if (!loops[i].isSwitch) { lp = loops[i]; break; }
        if (lp) link(preds.map(([p, l]) => [p, l ? l + ', next' : 'next']), lp.node); return [];
      }
      default: return preds;
    }
  }
  const body = fnNode.body;
  let ends;
  if (body && body.type === 'BlockStatement') ends = seq(body.body, [[start, '']], 0);
  else if (body) { const r = add('return', 'return ' + oneLine(srcOf(code, body), 40), line(body)); link([[start, '']], r); ends = []; }
  else ends = [[start, '']];
  if (ends.length) { const e = add('end', 'end', endLine(fnNode)); link(ends, e); }
  return { nodes, edges };
}

// ---------------------------------------------------------------- per file
function analyse(root, rel, opts) {
  const abs = path.join(root, rel);
  const st = fs.statSync(abs);
  if (st.size > MAX_BYTES) return { skipped: 'too large' };
  const raw = fs.readFileSync(abs, 'utf8');
  const ext = path.extname(rel).toLowerCase();
  const { code, lang } = scriptBlock(raw, ext);
  let ast;
  try { ast = parse(code, lang); } catch (e) { return { error: String(e.message || e).split('\n')[0] }; }
  const out = { imports: [], reexports: [], exports: [], classes: [], functions: [], loc: raw.split('\n').filter((l) => l.trim()).length };
  if (ast.errors && ast.errors.length) out.warnings = ast.errors.length;
  const prog = ast.program;

  const addImport = (source, names, ln, typeOnly) => out.imports.push({ source, names, line: ln, typeOnly: !!typeOnly });
  // imports, requires, exports
  walk(prog, (n, parent) => {
    if (n.type === 'ImportDeclaration') {
      const names = n.specifiers.map((s) => s.type === 'ImportDefaultSpecifier' ? { imported: 'default', local: s.local.name }
        : s.type === 'ImportNamespaceSpecifier' ? { imported: '*', local: s.local.name }
          : { imported: nameOfKey(s.imported), local: s.local.name, typeOnly: s.importKind === 'type' });
      addImport(n.source.value, names, line(n), n.importKind === 'type');
      return false;
    }
    if (n.type === 'ExportAllDeclaration') { out.reexports.push({ source: n.source.value, names: ['*'], line: line(n) }); return false; }
    if (n.type === 'ExportNamedDeclaration') {
      if (n.source) out.reexports.push({ source: n.source.value, names: n.specifiers.map((s) => nameOfKey(s.exported)), line: line(n) });
      else n.specifiers.forEach((s) => out.exports.push(nameOfKey(s.exported)));
      const d = n.declaration;
      if (d) {
        if (d.id) out.exports.push(d.id.name);
        if (d.declarations) d.declarations.forEach((x) => { if (x.id && x.id.name) out.exports.push(x.id.name); });
      }
    }
    if (n.type === 'ExportDefaultDeclaration') out.exports.push('default' + (n.declaration && n.declaration.id ? ':' + n.declaration.id.name : n.declaration && n.declaration.type === 'Identifier' ? ':' + n.declaration.name : ''));
    if (n.type === 'CallExpression') {
      const c = n.callee;
      const arg = n.arguments[0];
      const lit = arg && (arg.type === 'StringLiteral' ? arg.value : arg.type === 'TemplateLiteral' && !arg.expressions.length ? arg.quasis[0].value.cooked : null);
      if (lit && ((c.type === 'Identifier' && c.name === 'require') || c.type === 'Import')) {
        let names = [{ imported: '*', local: '' }];
        if (parent && parent.type === 'VariableDeclarator' && parent.id) {
          if (parent.id.type === 'Identifier') names = [{ imported: '*', local: parent.id.name }];
          else if (parent.id.type === 'ObjectPattern') names = parent.id.properties.filter((p) => p.key).map((p) => ({ imported: nameOfKey(p.key), local: p.value && p.value.name ? p.value.name : nameOfKey(p.key) }));
        }
        addImport(lit, names, line(n), false);
      }
    }
    if (n.type === 'TSImportEqualsDeclaration' && n.moduleReference && n.moduleReference.expression) addImport(n.moduleReference.expression.value, [{ imported: '*', local: n.id.name }], line(n), false);
    return true;
  });
  const exported = new Set(out.exports.map((e) => e.replace(/^default:/, '')));

  // functions and classes
  const fnRecord = (fnNode, name, qual, kind, extra) => {
    const calls = [], jsx = new Set();
    let returnsJsx = false;
    walk(fnNode.body, (n) => {
      if (n !== fnNode.body && FN_TYPES.has(n.type) && n.type !== 'ArrowFunctionExpression' && n.type !== 'FunctionExpression') return false;
      if (n.type === 'CallExpression' || n.type === 'OptionalCallExpression' || n.type === 'NewExpression') {
        const c = n.callee;
        if (c.type === 'Identifier') calls.push({ name: c.name, line: line(n), new: n.type === 'NewExpression' });
        else if (c.type === 'MemberExpression' || c.type === 'OptionalMemberExpression') {
          const obj = exprName(c.object);
          calls.push({ name: c.computed ? '[]' : nameOfKey(c.property), obj: obj.length > 60 ? obj.slice(0, 60) : obj, line: line(n), new: n.type === 'NewExpression' });
        }
      }
      if (n.type === 'JSXOpeningElement') {
        returnsJsx = true;
        const nm = n.name.type === 'JSXIdentifier' ? n.name.name : n.name.type === 'JSXMemberExpression' ? srcOf(code, n.name) : '';
        if (/^[A-Z]/.test(nm)) jsx.add(nm);
      }
      if (n.type === 'JSXFragment') returnsJsx = true;
      return true;
    });
    const isComponent = returnsJsx && /^[A-Z]/.test(name);
    const rec = Object.assign({
      name, qual, kind: isComponent ? 'component' : kind, line: line(fnNode), endLine: endLine(fnNode),
      loc: Math.max(1, endLine(fnNode) - line(fnNode) + 1), params: params(code, fnNode.params),
      async: !!fnNode.async, complexity: complexity(fnNode), calls: calls.slice(0, 400), renders: Array.from(jsx).slice(0, 60),
      exported: exported.has(name) || exported.has(qual.split('.')[0])
    }, extra || {});
    if (opts.cfg && fnNode.body) rec.cfg = buildCfg(code, fnNode, (rec.async ? 'async ' : '') + qual + '(' + rec.params.map((p) => p.split(':')[0]).join(', ') + ')', opts.maxCfgNodes || 60);
    out.functions.push(rec);
  };

  const topLevel = (stmtNode) => {
    let n = stmtNode;
    if (n.type === 'ExportNamedDeclaration' || n.type === 'ExportDefaultDeclaration') n = n.declaration;
    if (!n) return;
    if (n.type === 'FunctionDeclaration' && n.id) fnRecord(n, n.id.name, n.id.name, 'function');
    else if ((n.type === 'FunctionDeclaration' || n.type === 'ArrowFunctionExpression' || n.type === 'FunctionExpression') && stmtNode.type === 'ExportDefaultDeclaration')
      fnRecord(n, 'default', 'default', 'function');
    else if (n.type === 'VariableDeclaration') {
      n.declarations.forEach((d) => {
        if (!d.id || d.id.type !== 'Identifier' || !d.init) return;
        let init = d.init;
        while (init && (init.type === 'TSAsExpression' || init.type === 'CallExpression' && init.arguments.length && /^(memo|forwardRef|observer|React\.memo|React\.forwardRef|useCallback|withRouter|connect\(\))$/.test(exprName(init.callee)))) init = init.type === 'TSAsExpression' ? init.expression : init.arguments[0];
        if (init && (init.type === 'ArrowFunctionExpression' || init.type === 'FunctionExpression')) fnRecord(init, d.id.name, d.id.name, 'function');
        else if (init && init.type === 'ObjectExpression') { // const api = { list() {}, get: async () => {} }
          init.properties.forEach((p) => {
            const v = p.type === 'ObjectMethod' ? p : p.value;
            if (v && (p.type === 'ObjectMethod' || v.type === 'ArrowFunctionExpression' || v.type === 'FunctionExpression')) fnRecord(v, nameOfKey(p.key), d.id.name + '.' + nameOfKey(p.key), 'method');
          });
        }
      });
    } else if (n.type === 'ClassDeclaration' || n.type === 'ClassExpression') {
      const cname = n.id ? n.id.name : 'default';
      const cls = { name: cname, line: line(n), endLine: endLine(n), extends: n.superClass ? exprName(n.superClass) : '',
        implements: (n.implements || []).map((i) => srcOf(code, i.expression || i.id || i)).slice(0, 6),
        decorators: (n.decorators || []).map((d) => oneLine(srcOf(code, d.expression), 40)), exported: exported.has(cname) || stmtNode.type === 'ExportDefaultDeclaration',
        methods: [], props: [], abstract: !!n.abstract };
      n.body.body.forEach((m) => {
        if (m.type === 'ClassMethod' || m.type === 'ClassPrivateMethod' || m.type === 'TSDeclareMethod') {
          const mname = nameOfKey(m.key);
          cls.methods.push({ name: mname, line: line(m), static: !!m.static, kind: m.kind, access: m.accessibility || (mname[0] === '#' ? 'private' : 'public'), params: params(code, m.params), returns: m.returnType ? typeText(code, m.returnType) : '' });
          if (m.body) fnRecord(m, mname, cname + '.' + mname, m.kind === 'constructor' ? 'constructor' : 'method', { cls: cname });
          if (m.kind === 'constructor') m.params.forEach((p) => { if (p.type === 'TSParameterProperty' && p.parameter.type === 'Identifier') cls.props.push({ name: p.parameter.name, type: p.parameter.typeAnnotation ? typeText(code, p.parameter.typeAnnotation) : '', access: p.accessibility || 'public' }); });
        } else if (m.type === 'ClassProperty' || m.type === 'ClassPrivateProperty' || m.type === 'ClassAccessorProperty') {
          const pname = nameOfKey(m.key);
          if (m.value && (m.value.type === 'ArrowFunctionExpression' || m.value.type === 'FunctionExpression')) {
            cls.methods.push({ name: pname, line: line(m), static: !!m.static, kind: 'method', access: m.accessibility || 'public', params: params(code, m.value.params), returns: '' });
            fnRecord(m.value, pname, cname + '.' + pname, 'method', { cls: cname });
          } else {
            cls.props.push({ name: pname, type: m.typeAnnotation ? typeText(code, m.typeAnnotation) : '', access: m.accessibility || 'public', static: !!m.static,
              decorators: (m.decorators || []).map((d) => oneLine(srcOf(code, d.expression), 60)) });
          }
        }
      });
      out.classes.push(cls);
    } else if (n.type === 'TSInterfaceDeclaration' || n.type === 'TSTypeAliasDeclaration') {
      const props = [];
      const body = n.type === 'TSInterfaceDeclaration' ? n.body.body : (n.typeAnnotation && n.typeAnnotation.type === 'TSTypeLiteral' ? n.typeAnnotation.members : []);
      (body || []).forEach((m) => { if (m.key) props.push({ name: nameOfKey(m.key), type: m.typeAnnotation ? typeText(code, m.typeAnnotation) : '', optional: !!m.optional }); });
      if (n.type === 'TSInterfaceDeclaration' || props.length)
        out.classes.push({ name: n.id.name, line: line(n), endLine: endLine(n), interface: true, extends: (n.extends || []).map((e) => srcOf(code, e.expression)).join(', '),
          implements: [], decorators: [], exported: exported.has(n.id.name) || (stmtNode.type === 'ExportNamedDeclaration'), methods: [], props: props.slice(0, 40) });
    } else if (n.type === 'ExpressionStatement') {
      // express / fastify style: app.get('/path', handler) with an inline function
      const c = n.expression;
      if (c && c.type === 'CallExpression' && c.callee.type === 'MemberExpression') {
        const meth = nameOfKey(c.callee.property), obj = exprName(c.callee.object);
        const first = c.arguments[0];
        if (ROUTE_METHODS.has(meth) && ROUTER_NAMES.test(obj) && first && (first.type === 'StringLiteral' || first.type === 'TemplateLiteral')) {
          const p = first.type === 'StringLiteral' ? first.value : srcOf(code, first).slice(1, -1);
          const h = c.arguments[c.arguments.length - 1];
          if (h && (h.type === 'ArrowFunctionExpression' || h.type === 'FunctionExpression')) fnRecord(h, meth.toUpperCase() + ' ' + p, meth.toUpperCase() + ' ' + p, 'route', { route: { method: meth.toUpperCase(), path: p } });
        }
      }
    }
  };
  prog.body.forEach(topLevel);
  return out;
}

(async function main() {
  let req;
  try { req = JSON.parse(await readStdin()); } catch (e) { process.stdout.write(JSON.stringify({ error: 'bad request: ' + e.message })); process.exit(2); }
  const res = { files: {}, parser: 'babel-parser ' + (babel.version || '7') };
  for (const rel of req.files || []) {
    try { res.files[rel] = analyse(req.root, rel, { cfg: req.cfg !== false, maxCfgNodes: req.maxCfgNodes || 60 }); }
    catch (e) { res.files[rel] = { error: String(e && e.message || e).split('\n')[0] }; }
  }
  process.stdout.write(JSON.stringify(res));
})();
