#!/usr/bin/env node
/* codeflow-map: validate every view of a flow map with Pele, exactly as the viewer will draw it.
 *
 * Usage: node pele_check.cjs <flowmap.json> [--svg-dir DIR]
 * Prints JSON: { "pele": "1.10.0", "checked": N, "errors": [{view, mode, message, line, column, snippet, source}], "svgs": [...] }
 * Loads ../assets/vendor/pele.global.js and ../assets/flowmap-gen.js in a sandbox; no network, no project code. Node 18+.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const args = process.argv.slice(2);
const specPath = args.find((a) => !a.startsWith('--'));
const svgIdx = args.indexOf('--svg-dir');
const svgDir = svgIdx >= 0 ? args[svgIdx + 1] : null;
if (!specPath) { console.log(JSON.stringify({ error: 'usage: node pele_check.cjs <flowmap.json> [--svg-dir DIR]' })); process.exit(2); }

const ctx = { console };
ctx.globalThis = ctx;
vm.createContext(ctx);
const assets = path.join(__dirname, '..', 'assets');
vm.runInContext(fs.readFileSync(path.join(assets, 'vendor', 'pele.global.js'), 'utf8'), ctx, { filename: 'pele.global.js' });
vm.runInContext(fs.readFileSync(path.join(assets, 'flowmap-gen.js'), 'utf8'), ctx, { filename: 'flowmap-gen.js' });
const pele = ctx.pele, G = ctx.FlowmapGen;
const version = (fs.readFileSync(path.join(assets, 'vendor', 'pele.global.js'), 'utf8').match(/Pele (\d+\.\d+\.\d+)/) || [])[1] || '?';

let spec;
try { spec = JSON.parse(fs.readFileSync(specPath, 'utf8')); } catch (e) { process.stdout.write(JSON.stringify({ error: 'cannot read spec: ' + e.message })); process.exit(2); }
const out = { pele: version, checked: 0, errors: [], svgs: [] };
if (svgDir) fs.mkdirSync(svgDir, { recursive: true });
for (const v of (Array.isArray(spec.views) ? spec.views : [])) {
  const variants = [['simple', false], ['technical', false], ['simple', true]];
  for (const [mode, portable] of variants) {
    let g = { code: '' };
    out.checked++;
    try {
      g = G.gen(v, { mode, portable, sens: true, icons: spec.icons === false ? false : undefined });
      const r = pele.render(g.code, { idPrefix: 'chk', limit: 200000, maxEdges: 5000 });
      if (svgDir && portable) {
        const safe = String(v.id).replace(/[^A-Za-z0-9_-]+/g, '_');
        const svg = pele.render(g.code, { idPrefix: safe, limit: 200000, maxEdges: 5000, fontFamily: 'Segoe UI, system-ui, sans-serif' }).svg;
        const file = path.join(svgDir, safe + '.svg');
        fs.writeFileSync(file, svg);
        out.svgs.push(file);
      }
      if (!r.svg) throw new Error('empty drawing');
    } catch (e) {
      const lines = g.code.split('\n');
      const ln = e.line || 0;
      out.errors.push({ view: v.id, mode: mode + (portable ? ' (export)' : ''), message: String(e.message || e).split('\n')[0],
        code: e.code || '', line: ln, column: e.column || 0, snippet: e.snippet || '',
        source: ln ? lines.slice(Math.max(0, ln - 3), ln + 2).join('\n') : lines.slice(0, 6).join('\n') });
      break; // one error per view is enough
    }
  }
}
process.stdout.write(JSON.stringify(out));
