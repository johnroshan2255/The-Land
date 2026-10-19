#!/usr/bin/env node
// Generate LOD .glb files (and optional collision proxies) with glTF-Transform + meshoptimizer.
//
// Usage:
//   node make-lods.mjs <input.glb | folder> [--out dir] [--ratios 1,0.4,0.12] [--error 0.01]
//                      [--col 0.05] [--keep-normals] [--no-compress]
//
// For each input NAME.glb writes NAME_lod0.glb … NAME_lodN.glb (one per ratio) and,
// with --col, NAME_col.glb. Every output is welded, simplified, quantized and
// meshopt-compressed (load with GLTFLoader.setMeshoptDecoder).

import fs from 'node:fs';
import path from 'node:path';
import { Logger, NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, meshopt, prune, quantize, simplify, weld } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder, MeshoptSimplifier } from 'meshoptimizer';

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i === -1 ? fallback : args[i + 1];
};
const flag = (name) => args.includes(name);

const input = args[0];
if (!input || input.startsWith('--')) {
  console.log('usage: node make-lods.mjs <input.glb|folder> [--out dir] [--ratios 1,0.4,0.12] [--error 0.01] [--col 0.05] [--keep-normals] [--no-compress]');
  process.exit(1);
}
const ratios = opt('--ratios', '1,0.4,0.12').split(',').map(Number);
const error = Number(opt('--error', '0.01'));
const colRatio = opt('--col', null);
const keepNormals = flag('--keep-normals');
const compress = !flag('--no-compress');

await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready, MeshoptSimplifier.ready]);
const io = new NodeIO()
  .setLogger(new Logger(Logger.Verbosity.WARN))
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder });

function countTriangles(doc) {
  let tris = 0;
  for (const mesh of doc.getRoot().listMeshes()) {
    for (const prim of mesh.listPrimitives()) {
      const idx = prim.getIndices();
      const pos = prim.getAttribute('POSITION');
      tris += Math.floor((idx ? idx.getCount() : pos ? pos.getCount() : 0) / 3);
    }
  }
  return tris;
}

function dropNormals(doc) {
  // Flat-shaded meshes: three.js flatShading derives facet normals in the shader,
  // and split normals block welding/simplification.
  for (const mesh of doc.getRoot().listMeshes()) {
    for (const prim of mesh.listPrimitives()) {
      const normal = prim.getAttribute('NORMAL');
      if (normal) prim.setAttribute('NORMAL', null);
    }
  }
}

async function buildLevel(srcPath, ratio, errorLimit) {
  const doc = await io.read(srcPath);
  if (!keepNormals) dropNormals(doc);
  const steps = [dedup(), weld()];
  if (ratio < 1) {
    steps.push(simplify({ simplifier: MeshoptSimplifier, ratio, error: errorLimit, lockBorder: false }));
  }
  steps.push(prune());
  if (compress) steps.push(quantize(), meshopt({ encoder: MeshoptEncoder, level: 'high' }));
  await doc.transform(...steps);
  return doc;
}

async function processFile(srcPath, outDir) {
  const name = path.basename(srcPath, path.extname(srcPath));
  const sourceTris = countTriangles(await io.read(srcPath));
  const report = [`${name} (source ${sourceTris} tris)`];

  for (let i = 0; i < ratios.length; i++) {
    const doc = await buildLevel(srcPath, ratios[i], error);
    const outPath = path.join(outDir, `${name}_lod${i}.glb`);
    await io.write(outPath, doc);
    report.push(`lod${i}: ${countTriangles(doc)} tris, ${(fs.statSync(outPath).size / 1024).toFixed(1)} KB`);
  }

  if (colRatio !== null) {
    // Collision proxy: aggressive ratio, loose error bound
    const doc = await buildLevel(srcPath, Number(colRatio), 1);
    const outPath = path.join(outDir, `${name}_col.glb`);
    await io.write(outPath, doc);
    report.push(`col: ${countTriangles(doc)} tris`);
  }
  console.log(report.join('\n  '));
}

const outDir = path.resolve(opt('--out', path.join(path.dirname(path.resolve(input)), 'lod')));
fs.mkdirSync(outDir, { recursive: true });

const stat = fs.statSync(input);
const files = stat.isDirectory()
  ? fs.readdirSync(input)
      .filter((f) => /\.(glb|gltf)$/i.test(f) && !/_(lod\d+|col)\.glb$/i.test(f))
      .map((f) => path.join(input, f))
  : [input];

for (const file of files) await processFile(file, outDir);
console.log(`\nWrote ${files.length} model(s) to ${outDir}`);
