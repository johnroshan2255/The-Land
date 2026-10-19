// Puffy smoke/dust: one pooled InstancedMesh of opaque flat-shaded icospheres that grow, drift up and shrink to 0
// (skill: opaque puffs instead of alpha sprites, count capped by tier, instancedMesh.count = active count, no per-frame allocation).
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame } from '@react-three/fiber';
import { PRESET } from './state';

type Puff = { x: number; y: number; z: number; vx: number; vy: number; vz: number; age: number; life: number; size: number; r: number; g: number; b: number };

const MAX = PRESET.smokePuffs;
const pool: Puff[] = Array.from({ length: MAX }, () => ({ x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, age: 1, life: 1, size: 1, r: 1, g: 1, b: 1 }));
let active = 0;

/** Spawn one puff (drops it silently when the pool is full). */
export function emitPuff(x: number, y: number, z: number, vx: number, vy: number, vz: number, size: number, color: THREE.Color, life = 1.3) {
  if (active >= MAX) return;
  const p = pool[active++];
  p.x = x; p.y = y; p.z = z; p.vx = vx; p.vy = vy; p.vz = vz;
  p.age = 0; p.life = life * (0.8 + Math.random() * 0.4); p.size = size * (0.8 + Math.random() * 0.4);
  p.r = color.r; p.g = color.g; p.b = color.b;
}

const dummy = new THREE.Object3D();
const c = new THREE.Color();

export function Smoke() {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const geo = useMemo(() => new THREE.IcosahedronGeometry(1, 1), []);   // 80 tris: reads as a soft puff, not a rock
  const mat = useMemo(() => new THREE.MeshLambertMaterial({ flatShading: true }), []);

  useFrame((_, dtRaw) => {
    const m = mesh.current;
    if (!m) return;
    const dt = Math.min(dtRaw, 0.05);
    for (let i = 0; i < active; i++) {
      const p = pool[i];
      p.age += dt;
      if (p.age >= p.life) {   // swap-remove keeps the active puffs packed at the front
        const last = pool[--active];
        pool[active] = p;
        pool[i] = last;
        i--;
        continue;
      }
      p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt;
      p.vx *= 0.96; p.vz *= 0.96;
      const t = p.age / p.life;
      const s = p.size * (t < 0.25 ? 0.4 + 2.4 * t : 1 - (t - 0.25) / 0.75) ;   // grow fast, shrink to 0
      dummy.position.set(p.x, p.y, p.z);
      dummy.rotation.set(p.age * 0.7, p.age * 0.5, 0);
      dummy.scale.setScalar(Math.max(s, 0.001));
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
      m.setColorAt(i, c.setRGB(p.r, p.g, p.b));
    }
    m.count = active;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  });

  // create instanceColor up front so the shader is compiled with it once (no recompile when the first puff spawns)
  const init = (m: THREE.InstancedMesh | null) => {
    mesh.current = m;
    if (m && !m.instanceColor) {
      m.setColorAt(0, c.set('#ffffff'));
      m.count = 0;
    }
  };
  return <instancedMesh ref={init} args={[geo, mat, MAX]} frustumCulled={false} />;
}
