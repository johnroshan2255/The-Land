// Simplify raw geometry (positions only, before UVs) with meshoptimizer - used for low LODs of AI scans,
// where Blender's decimator stalls on non-manifold edges.
//   node tools/simplify-mesh.mjs in.glb out.glb <targetTris> [error]
import { Logger, NodeIO } from '@gltf-transform/core';
import { prune, simplify, weld } from '@gltf-transform/functions';
import { MeshoptSimplifier } from 'meshoptimizer';

const [src, dst, targetArg, errorArg = '0.05'] = process.argv.slice(2);
await MeshoptSimplifier.ready;
const io = new NodeIO().setLogger(new Logger(Logger.Verbosity.WARN));
const doc = await io.read(src);
const count = () => doc.getRoot().listMeshes().reduce((n, m) => n + m.listPrimitives()
  .reduce((k, p) => k + (p.getIndices() ? p.getIndices().getCount() : p.getAttribute('POSITION').getCount()) / 3, 0), 0);
for (const mesh of doc.getRoot().listMeshes()) {
  for (const prim of mesh.listPrimitives()) {
    for (const semantic of prim.listSemantics()) if (semantic !== 'POSITION') prim.setAttribute(semantic, null);
  }
}
await doc.transform(weld());
const before = count();
await doc.transform(simplify({ simplifier: MeshoptSimplifier, ratio: Number(targetArg) / before, error: Number(errorArg), lockBorder: false }), prune());
await io.write(dst, doc);
console.log(JSON.stringify({ before, after: count() }));
