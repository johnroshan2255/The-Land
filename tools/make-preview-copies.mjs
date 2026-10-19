// Write plain (uncompressed, unquantized) copies of models/ into models_preview/ so any glTF viewer
// (VS Code, Windows 3D Viewer, online viewers) can open them. The game keeps using the compressed models/.
//   node tools/make-preview-copies.mjs
import fs from 'node:fs';
import path from 'node:path';
import { Logger, NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dequantize } from '@gltf-transform/functions';
import { MeshoptDecoder } from 'meshoptimizer';

const root = path.join(import.meta.dirname, '..');
const src = path.join(root, 'models');
const dst = path.join(root, 'models_preview');
await MeshoptDecoder.ready;
const io = new NodeIO()
  .setLogger(new Logger(Logger.Verbosity.WARN))
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.decoder': MeshoptDecoder });

let count = 0;
(async function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) { await walk(full); continue; }
    if (!entry.name.endsWith('.glb')) continue;
    const doc = await io.read(full);
    await doc.transform(dequantize());
    for (const ext of doc.getRoot().listExtensionsUsed()) {
      if (['EXT_meshopt_compression', 'KHR_mesh_quantization'].includes(ext.extensionName)) ext.dispose();
    }
    const out = path.join(dst, path.relative(src, full));
    fs.mkdirSync(path.dirname(out), { recursive: true });
    await io.write(out, doc);
    count++;
  }
})(src).then(() => console.log(`${count} preview copies written to ${dst}`));
