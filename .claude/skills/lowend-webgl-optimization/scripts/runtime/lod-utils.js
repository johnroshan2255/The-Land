// LOD helpers for three.js: load LOD files into THREE.LOD, simplify geometry at runtime
// with meshoptimizer, and cheap per-object distance culling.
//
//   import { loadLOD, simplifyGeometry, buildLOD, DistanceCuller } from './lod-utils.js';
//
// Requires: three, meshoptimizer (npm i meshoptimizer) for simplifyGeometry/buildLOD.

import * as THREE from 'three';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

/**
 * Load make-lods output (name_lod0.glb, name_lod1.glb, ...) into one THREE.LOD.
 * @param {GLTFLoader} loader  configured with setMeshoptDecoder(MeshoptDecoder)
 * @param {string[]} urls      highest detail first
 * @param {number[]} distances switch distance per level, same length as urls (first is 0)
 */
export async function loadLOD(loader, urls, distances, { hysteresis = 0.1, scale = 1 } = {}) {
  const gltfs = await Promise.all(urls.map((url) => loader.loadAsync(url)));
  const lod = new THREE.LOD();
  gltfs.forEach((gltf, i) => lod.addLevel(gltf.scene, distances[i] * scale, hysteresis));
  return lod;
}

let simplifierPromise = null;
function getSimplifier() {
  simplifierPromise ??= import('meshoptimizer').then(async ({ MeshoptSimplifier }) => {
    await MeshoptSimplifier.ready;
    return MeshoptSimplifier;
  });
  return simplifierPromise;
}

/**
 * Simplify a BufferGeometry in the browser with meshoptimizer.
 * Normals are dropped before welding (use material.flatShading = true for low-poly).
 * @param {THREE.BufferGeometry} geometry
 * @param {number} ratio      target fraction of triangles to keep (0..1)
 * @param {number} error      max error as a fraction of mesh extent (0.01 = 1%)
 * @returns {Promise<THREE.BufferGeometry>} new indexed geometry
 */
export async function simplifyGeometry(geometry, ratio, error = 0.02, { lockBorder = false } = {}) {
  const simplifier = await getSimplifier();

  const source = geometry.clone();
  source.deleteAttribute('normal');
  source.deleteAttribute('tangent');
  const welded = mergeVertices(source, 1e-4);
  source.dispose();

  const positionAttr = welded.getAttribute('position');
  const positions = new Float32Array(positionAttr.count * 3);
  for (let i = 0; i < positionAttr.count; i++) {
    positions[i * 3] = positionAttr.getX(i);
    positions[i * 3 + 1] = positionAttr.getY(i);
    positions[i * 3 + 2] = positionAttr.getZ(i);
  }
  const indices = new Uint32Array(welded.index.array);
  const targetCount = Math.max(3, Math.floor((indices.length * ratio) / 3) * 3);
  const [simplified] = simplifier.simplify(indices, positions, 3, targetCount, error, lockBorder ? ['LockBorder'] : []);

  welded.setIndex(new THREE.BufferAttribute(simplified, 1));
  return welded;
}

/**
 * Build a THREE.LOD from one mesh by simplifying it at runtime.
 * @param {THREE.Mesh} mesh
 * @param {{ratio:number, distance:number}[]} levels e.g. [{ratio:0.4,distance:60},{ratio:0.12,distance:150}]
 */
export async function buildLOD(mesh, levels, { hysteresis = 0.1 } = {}) {
  const lod = new THREE.LOD();
  lod.addLevel(mesh, 0, hysteresis);
  for (const { ratio, distance, error = 0.02 } of levels) {
    const geometry = await simplifyGeometry(mesh.geometry, ratio, error);
    lod.addLevel(new THREE.Mesh(geometry, mesh.material), distance, hysteresis);
  }
  return lod;
}

/**
 * Hides objects beyond a per-object max distance. Cheaper than LOD for small props.
 * Call update(camera) every frame; it only does work every `interval` frames.
 */
export class DistanceCuller {
  constructor({ interval = 4, scale = 1 } = {}) {
    this.items = [];
    this.interval = interval;
    this.scale = scale;
    this._frame = 0;
    this._cameraPos = new THREE.Vector3();
    this._objectPos = new THREE.Vector3();
  }

  add(object, maxDistance) {
    this.items.push({ object, maxDistanceSq: maxDistance * maxDistance });
  }

  remove(object) {
    const i = this.items.findIndex((item) => item.object === object);
    if (i !== -1) this.items.splice(i, 1);
  }

  update(camera) {
    if (this._frame++ % this.interval !== 0) return;
    camera.getWorldPosition(this._cameraPos);
    const scaleSq = this.scale * this.scale;
    for (let i = 0; i < this.items.length; i++) {
      const { object, maxDistanceSq } = this.items[i];
      object.getWorldPosition(this._objectPos);
      object.visible = this._objectPos.distanceToSquared(this._cameraPos) <= maxDistanceSq * scaleSq;
    }
  }
}
