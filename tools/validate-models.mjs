// Run the Khronos glTF validator over every .glb in a folder (default: models_preview and models).
//   node tools/validate-models.mjs [dir ...]
import fs from 'node:fs';
import path from 'node:path';
import validator from 'gltf-validator';

const dirs = process.argv.slice(2).length ? process.argv.slice(2) : ['../models', '../models_preview'].map((d) => path.join(import.meta.dirname, d));
let files = 0;
let bad = 0;
for (const dir of dirs) {
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : e.name.endsWith('.glb') ? [path.join(d, e.name)] : []));
  for (const f of walk(dir)) {
    files++;
    const r = await validator.validateBytes(new Uint8Array(fs.readFileSync(f)), { maxIssues: 5 });
    if (r.issues.numErrors) {
      bad++;
      console.log(`${path.relative(path.dirname(dir), f)}: ${r.issues.messages.filter((m) => m.severity === 0).map((m) => `${m.code} ${m.pointer ?? ''}`).join('; ')}`);
    }
  }
}
console.log(`${files} files checked, ${bad} with errors`);
