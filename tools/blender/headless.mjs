// Run asset scripts in a separate background Blender process (never touches the live MCP session).
//   node headless.mjs lib.py nature.py [KEY=VALUE ...]
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const BLENDER = process.env.BLENDER_EXE ?? 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe';
const args = process.argv.slice(2);
const header = args.filter((a) => a.includes('=') && !a.endsWith('.py')).map((kv) => {
  const i = kv.indexOf('=');
  return `${kv.slice(0, i)} = ${JSON.stringify(kv.slice(i + 1))}`;
});
const body = args.filter((a) => a.endsWith('.py')).map((f) => fs.readFileSync(f, 'utf8').replace(/^\uFEFF/, ''));
const code = [
  'import bpy, json',
  'for _o in list(bpy.data.objects): bpy.data.objects.remove(_o, do_unlink=True)',
  ...header,
  ...body,
  'print("RESULT_JSON " + json.dumps(globals().get("result", {}), default=str))',
].join('\n');
const tmp = path.join(os.tmpdir(), `headless_${process.pid}.py`);
fs.writeFileSync(tmp, code);
const run = spawnSync(BLENDER, ['-b', '--factory-startup', '--python-exit-code', '1', '-P', tmp], { encoding: 'utf8', maxBuffer: 1 << 28 });
const out = (run.stdout ?? '') + (run.stderr ?? '');
const keep = out.split('\n').filter((l) => /RESULT_JSON|Error|Traceback|^\s+File |^\w+Error/.test(l) || /^(vehicles|nature|props|stunts|structures|env|fx|terrain)/.test(l));
console.log(keep.join('\n'));
fs.unlinkSync(tmp);
process.exitCode = run.status ?? 1;
