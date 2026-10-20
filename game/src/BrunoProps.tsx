// Street furniture and knockable props from Bruno Simon's folio-2025 (MIT licence, models in models/bruno):
// lanterns and pole lights (static, glowing at night) and crates, bricks and benches that are real physics objects -
// drive into a crate pyramid or a brick wall and it scatters, like on his site (his ExplosiveCrates / Bricks / Benches).
//
// Placements come from props.json (types b_*). Static ones render through the chunk instancing in World.tsx. Dynamic
// ones are drawn here, one instanced mesh per type, from a per-object transform; a Rapier body exists only while the
// object is near the car (and sleeps when still), so hundreds of them cost little. Wherever an object was knocked to,
// it stays there.
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useLoader } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { useRapier } from '@react-three/rapier';
import type { RigidBody } from '@dimforge/rapier3d-compat';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { DRACO, PRESET, telemetry } from './state';
import { isNight } from './DayNight';

const B = '/models/bruno/';
const SCALE = 1.5;   // his car is ~2.7 m, our jeep 4.5 m
const FILES: Record<string, string> = {
  b_lantern: 'lanterns.glb', b_pole: 'poleLights.glb', b_bench: 'benches.glb', b_crate: 'explosiveCrates.glb',
  b_brick: 'bricks.glb', b_fence: 'fences.glb',
};
export const BRUNO_DYNAMIC: Record<string, { mass: number }> = { b_crate: { mass: 18 }, b_brick: { mass: 12 }, b_bench: { mass: 35 }, b_fence: { mass: 20 } };
const ACTIVE_R = 80, RELEASE_R = 110, PER_FRAME = 24;
const DRAW_R = PRESET.propDistance * 1.3;   // only draw the ones this close (crate pyramids are ~200 triangles each)

const glowColor = { value: new THREE.Color('#ffb257') };
const glowAmount = { value: 0.4 };

/** One geometry per prop type (the first instance in his file, all its meshes merged, base on the ground, x1.5), with
 *  a `glow` attribute on his emissive parts (lantern / pole-light glass). */
export function useBrunoProps() {
  const names = Object.keys(FILES);
  const gltfs = useGLTF(names.map((n) => B + FILES[n]), DRACO);
  const palette = useLoader(THREE.TextureLoader, `${B}palette.png`);
  return useMemo(() => {
    palette.colorSpace = THREE.SRGBColorSpace;
    palette.magFilter = palette.minFilter = THREE.NearestFilter;
    const geometries: Record<string, THREE.BufferGeometry> = {};
    names.forEach((name, k) => {
      const scene = gltfs[k].scene;
      scene.updateMatrixWorld(true);
      // the first mesh's top-level ancestor = the first instance
      let first: THREE.Object3D | null = null;
      scene.traverse((o) => {
        if (!first && (o as THREE.Mesh).isMesh) first = o;
      });
      let root = first as unknown as THREE.Object3D;
      while (root.parent && root.parent !== scene) root = root.parent;
      const inv = root.matrixWorld.clone().invert();
      const parts: THREE.BufferGeometry[] = [];
      root.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh || !m.geometry.getAttribute('uv')) return;   // skip his collision cuboids
        let g = m.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv, m.matrixWorld));
        g = g.index ? g.toNonIndexed() : g;
        for (const a of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(a)) g.deleteAttribute(a);
        const glow = (m.material as THREE.MeshStandardMaterial).name.startsWith('emissive') ? 1 : 0;
        g.setAttribute('glow', new THREE.Float32BufferAttribute(new Float32Array(g.getAttribute('position').count).fill(glow), 1));
        parts.push(g);
      });
      const g = mergeGeometries(parts)!;
      g.computeBoundingBox();
      const b = g.boundingBox!;
      g.translate(-(b.min.x + b.max.x) / 2, -b.min.y, -(b.min.z + b.max.z) / 2).scale(SCALE, SCALE, SCALE);
      g.computeBoundingBox();
      g.computeBoundingSphere();
      geometries[name] = g;
    });
    const material = new THREE.MeshLambertMaterial({ map: palette });
    material.customProgramCacheKey = () => 'bruno-props';
    material.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, { uGlowColor: glowColor, uGlow: glowAmount });
      s.vertexShader = s.vertexShader.replace('#include <common>', '#include <common>\nattribute float glow; varying float vGlow;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvGlow = glow;');
      s.fragmentShader = s.fragmentShader.replace('#include <common>', '#include <common>\nvarying float vGlow; uniform vec3 uGlowColor; uniform float uGlow;')
        .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance += uGlowColor * vGlow * uGlow;');
    };
    return { geometries, material };
  }, [gltfs, palette]);
}

type Placements = Record<string, Record<string, number[]>>;
type Obj = { type: string; p: THREE.Vector3; q: THREE.Quaternion; body: RigidBody | null };

/** The knockable props: all placements of the dynamic types, drawn here, simulated near the car. */
export function DynamicProps({ placements, stride }: { placements: Placements | null; stride: number }) {
  const { world, rapier } = useRapier();
  const { geometries, material } = useBrunoProps();
  const objs = useMemo(() => {
    const out: Obj[] = [];
    if (!placements) return out;
    const up = new THREE.Vector3(0, 1, 0);
    for (const types of Object.values(placements)) {
      for (const type of Object.keys(BRUNO_DYNAMIC)) {
        const arr = types[type];
        if (!arr) continue;
        for (let o = 0; o < arr.length; o += stride) {
          out.push({ type, p: new THREE.Vector3(arr[o], arr[o + 1], arr[o + 2]), q: new THREE.Quaternion().setFromAxisAngle(up, arr[o + 3]), body: null });
        }
      }
    }
    return out;
  }, [placements, stride]);
  const meshes = useMemo(() => {
    const out: Record<string, { mesh: THREE.InstancedMesh; ids: number[] }> = {};
    for (const type of Object.keys(BRUNO_DYNAMIC)) {
      const ids = objs.map((o, i) => (o.type === type ? i : -1)).filter((i) => i >= 0);
      if (!ids.length) continue;
      const mesh = new THREE.InstancedMesh(geometries[type], material, ids.length);
      mesh.frustumCulled = false;
      out[type] = { mesh, ids };
    }
    return out;
  }, [objs, geometries, material]);
  useEffect(() => () => {
    for (const { mesh } of Object.values(meshes)) mesh.dispose();
    for (const o of objs) if (o.body) world.removeRigidBody(o.body);
  }, [meshes, objs, world]);

  const ray = useMemo(() => new rapier.Ray({ x: 0, y: 0, z: 0 }, { x: 0, y: -1, z: 0 }), [rapier]);
  const tmp = useMemo(() => ({ m: new THREE.Matrix4(), one: new THREE.Vector3(1, 1, 1), v: new THREE.Vector3(), half: new THREE.Vector3() }), []);
  /** o.p is the object's base centre; the body sits at its box centre, half its height up along its own up axis. */
  const centreFromBase = (o: Obj, out: THREE.Vector3) => out.set(0, geometries[o.type].boundingBox!.max.y / 2, 0).applyQuaternion(o.q).add(o.p);
  const baseFromBody = (o: Obj) => {
    const t = o.body!.translation(), r = o.body!.rotation();
    o.q.set(r.x, r.y, r.z, r.w);
    o.p.set(0, -geometries[o.type].boundingBox!.max.y / 2, 0).applyQuaternion(o.q).add(tmp.v.set(t.x, t.y, t.z));
  };
  useFrame(() => {
    glowAmount.value = isNight() ? 2.2 : 0.35;
    const cx = telemetry.x, cz = telemetry.z;
    let created = 0;
    for (const o of objs) {
      const d = Math.hypot(o.p.x - cx, o.p.z - cz);
      if (!o.body && d < ACTIVE_R && created < PER_FRAME) {
        // only once the terrain collider under it is there, or it would fall through the world
        ray.origin = { x: o.p.x, y: o.p.y + 6, z: o.p.z };
        const hit = world.castRay(ray, 40, true, undefined, undefined, undefined, undefined, (c) => c.shapeType() === rapier.ShapeType.TriMesh);
        if (!hit) continue;
        const half = geometries[o.type].boundingBox!.getSize(tmp.half).multiplyScalar(0.5);
        const c = centreFromBase(o, tmp.v);
        const body = world.createRigidBody(rapier.RigidBodyDesc.dynamic()
          .setTranslation(c.x, c.y + 0.02, c.z).setRotation(o.q).setCanSleep(true).setAngularDamping(0.4).setLinearDamping(0.1));
        const vol = 8 * half.x * half.y * half.z;
        world.createCollider(rapier.ColliderDesc.cuboid(half.x, half.y, half.z).setDensity(BRUNO_DYNAMIC[o.type].mass / vol).setFriction(0.7).setRestitution(0.15), body);
        body.sleep();
        o.body = body;
        created++;
      } else if (o.body && d > RELEASE_R) {
        baseFromBody(o);   // remember where it ended up
        world.removeRigidBody(o.body);
        o.body = null;
      }
    }
    for (const { mesh, ids } of Object.values(meshes)) {
      let n = 0;
      for (let k = 0; k < ids.length; k++) {
        const o = objs[ids[k]];
        if (o.body) baseFromBody(o);
        if (Math.abs(o.p.x - cx) > DRAW_R || Math.abs(o.p.z - cz) > DRAW_R) continue;
        mesh.setMatrixAt(n++, tmp.m.compose(o.p, o.q, tmp.one));
      }
      mesh.count = n;
      mesh.instanceMatrix.needsUpdate = true;
    }
  });

  return (
    <>
      {Object.values(meshes).map(({ mesh }) => <primitive key={mesh.uuid} object={mesh} />)}
    </>
  );
}

export const BRUNO_STATIC = new Set(['b_lantern', 'b_pole']);
