// Compress every .glb under models/ in place: dedup + weld + quantize + meshopt.
// Node names are kept (wheels, _col nodes). Load in three.js with GLTFLoader.setMeshoptDecoder(MeshoptDecoder).
//   node tools/compress-models.mjs [models-dir]
import fs from 'node:fs';
import path from 'node:path';
import { Logger, NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, meshopt, prune, quantize, weld } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';

const root = path.resolve(process.argv[2] ?? path.join(import.meta.dirname, '..', 'models'));
await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready]);
const io = new NodeIO()
  .setLogger(new Logger(Logger.Verbosity.WARN))
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });

const files = [];
(function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name.endsWith('.glb')) files.push(full);
  }
})(root);

let before = 0;
let after = 0;
for (const file of files) {
  const size = fs.statSync(file).size;
  const doc = await io.read(file);
  // Blender can export an extra empty scene (and make it the default); viewers then show nothing.
  const scenes = doc.getRoot().listScenes();
  const filled = scenes.filter((s) => s.listChildren().length);
  let fixedScenes = false;
  if (filled.length && (scenes.length > filled.length || doc.getRoot().getDefaultScene() !== filled[0])) {
    for (const s of scenes) if (!filled.includes(s)) s.dispose();
    doc.getRoot().setDefaultScene(filled[0]);
    fixedScenes = true;
  }
  if (doc.getRoot().listExtensionsUsed().some((e) => e.extensionName === 'EXT_meshopt_compression')) {
    if (fixedScenes) await io.write(file, doc);
    continue;
  }
  await doc.transform(dedup(), weld(), prune(), quantize(), meshopt({ encoder: MeshoptEncoder, level: 'high' }));
  await io.write(file, doc);
  before += size;
  after += fs.statSync(file).size;
}
console.log(`${files.length} files: ${(before / 1048576).toFixed(2)} MB -> ${(after / 1048576).toFixed(2)} MB`);
