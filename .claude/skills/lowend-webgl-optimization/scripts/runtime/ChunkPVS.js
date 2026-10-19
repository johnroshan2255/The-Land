// Chunk-level potentially-visible-set (PVS) occlusion culling for a chunked terrain.
//
// Bake once (dev tool / build step) with all chunk meshes loaded, save the JSON,
// then at runtime hide loaded chunks that can't be seen from the current chunk.
//
//   // bake (dev only; use three-mesh-bvh on the meshes to make this fast)
//   const pvs = bakeChunkPVS(chunks, { maxDistance: 600 });
//   download(JSON.stringify(pvs));
//
//   // runtime
//   const culler = new ChunkPVS(pvsJson);
//   culler.apply(currentChunkKey, loadedChunks); // Map<key, Object3D>

import * as THREE from 'three';

/**
 * @param {Map<string, THREE.Mesh>} chunks key "x_y" -> terrain chunk mesh (world space)
 * @param {object} options
 * @param {number} options.maxDistance  ignore chunks farther than this (fog distance)
 * @param {number[]} options.eyeHeights heights above ground to test from (driver, chase camera)
 * @param {number} options.samples      sample grid per chunk side (3 => 9 points)
 * @param {number} options.dilate       also mark neighbours of visible chunks (safety margin)
 * @returns {{keys: string[], visible: Record<string, string[]>}}
 */
export function bakeChunkPVS(chunks, { maxDistance = 600, eyeHeights = [2, 6], samples = 3, dilate = 1 } = {}) {
  const keys = [...chunks.keys()];
  const meshes = [...chunks.values()];
  const boxes = new Map(keys.map((k) => [k, new THREE.Box3().setFromObject(chunks.get(k))]));
  const raycaster = new THREE.Raycaster();
  const down = new THREE.Vector3(0, -1, 0);
  const dir = new THREE.Vector3();
  const centerA = new THREE.Vector3();
  const centerB = new THREE.Vector3();

  const groundPoints = (key) => {
    const box = boxes.get(key);
    const points = [];
    for (let i = 0; i < samples; i++) {
      for (let j = 0; j < samples; j++) {
        const x = THREE.MathUtils.lerp(box.min.x, box.max.x, (i + 0.5) / samples);
        const z = THREE.MathUtils.lerp(box.min.z, box.max.z, (j + 0.5) / samples);
        raycaster.set(new THREE.Vector3(x, box.max.y + 10, z), down);
        const hit = raycaster.intersectObject(chunks.get(key), false)[0];
        points.push(new THREE.Vector3(x, hit ? hit.point.y : box.min.y, z));
      }
    }
    return points;
  };
  const ground = new Map(keys.map((k) => [k, groundPoints(k)]));

  const visible = {};
  for (const a of keys) {
    boxes.get(a).getCenter(centerA);
    const eyes = ground.get(a).flatMap((p) => eyeHeights.map((h) => p.clone().setY(p.y + h)));
    const seen = new Set([a]);
    for (const b of keys) {
      if (b === a) continue;
      boxes.get(b).getCenter(centerB);
      if (centerA.distanceTo(centerB) > maxDistance) continue;
      // Targets: ground samples plus the top of the chunk's bounds (peaks stick out)
      const targets = ground.get(b).concat([centerB.clone().setY(boxes.get(b).max.y)]);
      outer: for (const eye of eyes) {
        for (const target of targets) {
          const distance = dir.subVectors(target, eye).length();
          raycaster.set(eye, dir.normalize());
          raycaster.far = distance - 0.5;
          if (raycaster.intersectObjects(meshes, false).length === 0) {
            seen.add(b);
            break outer;
          }
        }
      }
    }
    visible[a] = [...seen];
  }

  if (dilate > 0) {
    const parse = (k) => k.split('_').map(Number);
    for (const a of keys) {
      const grown = new Set(visible[a]);
      for (const b of visible[a]) {
        const [bx, by] = parse(b);
        for (let dx = -dilate; dx <= dilate; dx++) {
          for (let dy = -dilate; dy <= dilate; dy++) {
            const n = `${bx + dx}_${by + dy}`;
            if (chunks.has(n)) grown.add(n);
          }
        }
      }
      visible[a] = [...grown];
    }
  }
  return { keys, visible };
}

export class ChunkPVS {
  /** @param {{visible: Record<string, string[]>}} data output of bakeChunkPVS */
  constructor(data) {
    this.visible = new Map(Object.entries(data.visible).map(([k, list]) => [k, new Set(list)]));
  }

  isVisible(fromKey, toKey) {
    const set = this.visible.get(fromKey);
    return !set || set.has(toKey); // unknown chunk: be conservative and draw it
  }

  /** @param {Map<string, THREE.Object3D>} loadedChunks */
  apply(currentKey, loadedChunks) {
    for (const [key, object] of loadedChunks) object.visible = this.isVisible(currentKey, key);
  }
}
