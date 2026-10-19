// Build game LODs from a full-detail "showroom" glb (smooth clay models): weld + simplify per mesh, keep node names
// (wheels), then quantize + meshopt.
//   node tools/lods-from-showroom.mjs models/vehicles/car_hero_showroom.glb car_hero 0.3,0.1,0.03
import path from 'node:path';
import fs from 'node:fs';
import { Logger, NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, meshopt, prune, quantize, simplify, weld } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder, MeshoptSimplifier } from 'meshoptimizer';

const [src, name, ratioArg = '0.3,0.1,0.03', startArg = '0', errorArg = '0.01,0.04,0.1'] = process.argv.slice(2);
const errors = errorArg.split(',').map(Number);
const start = Number(startArg); // first LOD index to write (1 = keep the source as lod0)
const ratios = ratioArg.split(',').map(Number);
await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready, MeshoptSimplifier.ready]);
const io = new NodeIO()
  .setLogger(new Logger(Logger.Verbosity.WARN))
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });

const tris = (doc) => doc.getRoot().listMeshes().reduce((n, m) => n + m.listPrimitives()
  .reduce((k, p) => k + (p.getIndices() ? p.getIndices().getCount() : p.getAttribute('POSITION').getCount()) / 3, 0), 0);

// Blender export leaves .001 suffixes, an unnamed body node and duplicate wheel nodes: rebuild a clean tree
// <name> (root) -> <name>_body + named wheels, world transforms preserved.
function cleanHierarchy(doc) {
  // One scene only, and it must be the default one (viewers open the default scene)
  const scenes = doc.getRoot().listScenes();
  const scene = scenes[0];
  for (const extra of scenes.slice(1)) extra.dispose();
  doc.getRoot().setDefaultScene(scene);
  const nodes = doc.getRoot().listNodes();
  const strip = (s) => s.replace(/\.\d+$/, '');
  const keep = new Map();
  for (const n of nodes) {
    if (!n.getMesh()) continue;
    const raw = strip(n.getName());
    const nm = !raw || raw === '_body' ? `${name}_body` : raw;
    const prev = keep.get(nm);
    if (!prev || (!prev.getParentNode() && n.getParentNode())) keep.set(nm, n);
  }
  const root = doc.createNode(name);
  for (const [nm, n] of keep) root.addChild(doc.createNode(nm).setMesh(n.getMesh()).setMatrix(n.getWorldMatrix()));
  for (const n of nodes) n.dispose();
  scene.addChild(root);
  return doc;
}
const read = async () => cleanHierarchy(await io.read(src));

const outDir = path.dirname(src);
const source = await read();
console.log(`${path.basename(src)}: ${tris(source)} tris`);
for (let i = 0; i < ratios.length; i++) {
  const doc = await read();
  await doc.transform(
    dedup(),
    weld(),
    simplify({ simplifier: MeshoptSimplifier, ratio: ratios[i], error: errors[i] ?? 0.1, lockBorder: false }),
    prune(),
    quantize(),
    meshopt({ encoder: MeshoptEncoder, level: 'high' }),
  );
  const out = path.join(outDir, `${name}_lod${i + start}.glb`);
  await io.write(out, doc);
  console.log(`  lod${i + start}: ${tris(doc)} tris, ${(fs.statSync(out).size / 1024).toFixed(0)} KB, nodes: ${doc.getRoot().listNodes().map((n) => n.getName()).filter(Boolean).join(',')}`);
}
// compress the showroom file too
const show = source;
await show.transform(dedup(), weld(), quantize(), meshopt({ encoder: MeshoptEncoder, level: 'high' }));
await io.write(src, show);
console.log(`  showroom compressed: ${(fs.statSync(src).size / 1024).toFixed(0)} KB`);
