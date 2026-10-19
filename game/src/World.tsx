// Chunked island: 144 terrain chunks with 3 LODs, Rapier trimesh colliders streamed around the car,
// and props as one InstancedMesh per chunk per type, distance-culled per layer (lowend-webgl-optimization skill).
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { CuboidCollider, RigidBody, useBeforePhysicsStep, useRapier } from '@react-three/rapier';
import type { Collider } from '@dimforge/rapier3d-compat';
import { CHUNK, DRACO, HALF, PRESET, telemetry } from './state';

const T = '/models/terrain/';
const LOD_URLS = [`${T}terrain_lod0.glb`, `${T}terrain_lod1.glb`, `${T}terrain_lod2.glb`];
const LOD_DIST = [0, 260 * PRESET.lodScale, 620 * PRESET.lodScale];

// One shared flat-shaded vertex-color material for the whole terrain and every prop (skill: "3-6 materials in the game").
export const flatMaterial = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });

type PropsFile = { chunkSize: number; stride: number; types: string[]; placements: Record<string, Record<string, number[]>> };

// Prop placements are needed by both the renderer (instancing) and the physics (tree/rock colliders): load once.
let PROPS: PropsFile | null = null;
const propsReady = fetch(`${T}props.json`).then((r) => r.json()).then((d: PropsFile) => (PROPS = d));

// Solid props get primitive colliders (skill: props use primitives, never trimesh); grass and bushes stay drive-through.
const SOLID: Record<string, 'trunk' | 'rock'> = { pine: 'trunk', pine_snow: 'trunk', cactus: 'trunk', rock: 'rock', rock_snow: 'rock' };

// Per-layer draw distances (skill: rocks 80-120 m, trees 200-450 m by tier).
const LAYER_DIST: Record<string, number> = {
  pine: PRESET.treeDistance, pine_snow: PRESET.treeDistance, cactus: PRESET.treeDistance,
  rock: PRESET.propDistance * 1.6, rock_snow: PRESET.propDistance * 1.6, bush: PRESET.propDistance * 1.2,
  grass_tuft: PRESET.propDistance * 0.7,
};
const CASTS_SHADOW = new Set(['pine', 'pine_snow', 'cactus', 'rock', 'rock_snow']);

export function World() {
  const lods = useGLTF(LOD_URLS, DRACO);
  const chunks = useMemo(() => {
    const out: { key: string; lod: THREE.LOD; lod0: THREE.Mesh }[] = [];
    const byName = lods.map((g) => {
      const m = new Map<string, THREE.Mesh>();
      g.scene.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) m.set(o.name, o as THREE.Mesh);
      });
      return m;
    });
    for (const [name, mesh0] of byName[0]) {
      const lod = new THREE.LOD();
      lod.position.copy(mesh0.position);
      byName.forEach((m, level) => {
        const src = m.get(name);
        if (!src) return;
        const mesh = new THREE.Mesh(src.geometry, flatMaterial);
        mesh.receiveShadow = level === 0 && PRESET.shadows === 'directional';
        mesh.matrixAutoUpdate = false;
        mesh.updateMatrix();
        lod.addLevel(mesh, LOD_DIST[level], 0.1);
      });
      lod.matrixAutoUpdate = false;
      lod.updateMatrix();
      out.push({ key: name.replace('chunk_', ''), lod, lod0: mesh0 });
    }
    return out;
  }, [lods]);

  return (
    <>
      {chunks.map((c) => <primitive key={c.key} object={c.lod} />)}
      <ColliderStreamer chunks={chunks} />
      <Props />
      <GpuWarmup />
      <Water />
      {/* invisible walls at the island edge */}
      <RigidBody type="fixed">
        <CuboidCollider args={[HALF, 300, 2]} position={[0, 150, -HALF - 2]} />
        <CuboidCollider args={[HALF, 300, 2]} position={[0, 150, HALF + 2]} />
        <CuboidCollider args={[2, 300, HALF]} position={[-HALF - 2, 150, 0]} />
        <CuboidCollider args={[2, 300, HALF]} position={[HALF + 2, 150, 0]} />
      </RigidBody>
    </>
  );
}

/** Fixed colliders streamed around the car (skill: stream colliders with chunks, spread work over frames):
 *  terrain trimeshes within PRESET.chunkRadius, tree/rock primitives only in the 3x3 around the car.
 *  At most ONE chunk is built per physics step, nearest first, so crossing a chunk border never spikes a frame. */
function ColliderStreamer({ chunks }: { chunks: { key: string; lod0: THREE.Mesh }[] }) {
  const { world, rapier } = useRapier();
  const terrain = useRef(new Map<string, Collider>());
  const props = useRef(new Map<string, Collider[]>());
  const last = useRef('');
  const pending = useRef(true);
  const byKey = useMemo(() => new Map(chunks.map((c) => [c.key, c.lod0])), [chunks]);

  const buildTerrain = (key: string, mesh: THREE.Mesh) => {
    const pos = mesh.geometry.getAttribute('position');
    const verts = new Float32Array(pos.count * 3);
    for (let k = 0; k < pos.count; k++) {
      verts[k * 3] = pos.getX(k);
      verts[k * 3 + 1] = pos.getY(k);
      verts[k * 3 + 2] = pos.getZ(k);
    }
    const index = mesh.geometry.index ? new Uint32Array(mesh.geometry.index.array) : Uint32Array.from({ length: pos.count }, (_, k) => k);
    const desc = rapier.ColliderDesc.trimesh(verts, index).setTranslation(mesh.position.x, mesh.position.y, mesh.position.z).setFriction(1);
    terrain.current.set(key, world.createCollider(desc));
  };

  const buildProps = (key: string) => {
    const cols: Collider[] = [];
    const stride = PROPS!.stride;
    for (const [type, arr] of Object.entries(PROPS!.placements[key] ?? {})) {
      const kind = SOLID[type];
      if (!kind) continue;
      for (let o = 0; o < arr.length; o += stride) {
        const s = arr[o + 4];
        const d = kind === 'trunk'
          ? rapier.ColliderDesc.cylinder(1.6 * s, 0.35 * s).setTranslation(arr[o], arr[o + 1] + 1.6 * s, arr[o + 2])
          : rapier.ColliderDesc.ball(0.95 * s).setTranslation(arr[o], arr[o + 1] + 0.25 * s, arr[o + 2]);
        cols.push(world.createCollider(d.setFriction(0.6)));
      }
    }
    props.current.set(key, cols);
  };

  useBeforePhysicsStep(() => {
    if (!PROPS) return;
    const ci = Math.floor((telemetry.x + HALF) / CHUNK);
    const cj = Math.floor((-telemetry.z + HALF) / CHUNK);   // chunk rows run south -> north = -z
    const cur = `${ci}_${cj}`;
    if (cur === last.current && !pending.current) return;
    last.current = cur;
    const r = PRESET.chunkRadius;
    // nearest-first: ring 0 (props + terrain), ring 1, ... ; build one thing and come back next step
    pending.current = false;
    outer: for (let ring = 0; ring <= r; ring++) {
      for (let di = -ring; di <= ring; di++) {
        for (let dj = -ring; dj <= ring; dj++) {
          if (Math.max(Math.abs(di), Math.abs(dj)) !== ring) continue;
          const key = `${ci + di}_${cj + dj}`;
          const mesh = byKey.get(key);
          if (!mesh) continue;
          if (!terrain.current.has(key)) {
            buildTerrain(key, mesh);
            pending.current = true;
            break outer;
          }
          if (ring <= 1 && !props.current.has(key)) {
            buildProps(key);
            pending.current = true;
            break outer;
          }
        }
      }
    }
    // unload with a 1-chunk hysteresis ring
    for (const [key, col] of terrain.current) {
      const [i, j] = key.split('_').map(Number);
      if (Math.abs(i - ci) > r + 1 || Math.abs(j - cj) > r + 1) {
        world.removeCollider(col, false);
        terrain.current.delete(key);
      }
    }
    for (const [key, cols] of props.current) {
      const [i, j] = key.split('_').map(Number);
      if (Math.abs(i - ci) > 2 || Math.abs(j - cj) > 2) {
        for (const col of cols) world.removeCollider(col, false);
        props.current.delete(key);
      }
    }
  });

  useEffect(() => () => {
    for (const col of terrain.current.values()) world.removeCollider(col, false);
    for (const cols of props.current.values()) for (const col of cols) world.removeCollider(col, false);
    terrain.current.clear();
    props.current.clear();
  }, [world]);
  return null;
}

function Props() {
  const { nodes } = useGLTF(`${T}props.glb`, DRACO);
  const { camera, scene } = useThree();
  const groups = useRef<{ obj: THREE.InstancedMesh; maxSq: number }[]>([]);
  const root = useMemo(() => new THREE.Group(), []);

  useEffect(() => {
    let cancelled = false;
    propsReady.then((data) => {
      if (cancelled) return;
      const m = new THREE.Matrix4();
      const q = new THREE.Quaternion();
      const s = new THREE.Vector3();
      const p = new THREE.Vector3();
      const up = new THREE.Vector3(0, 1, 0);
      for (const [key, types] of Object.entries(data.placements)) {
        const [i, j] = key.split('_').map(Number);
        const cx = -HALF + (i + 0.5) * CHUNK;
        const cz = -(-HALF + (j + 0.5) * CHUNK);
        for (const [type, arr] of Object.entries(types)) {
          const src = nodes[type] as THREE.Mesh | undefined;
          if (!src) continue;
          const n = arr.length / data.stride;
          const im = new THREE.InstancedMesh(src.geometry, flatMaterial, n);
          im.position.set(cx, 0, cz);
          for (let k = 0; k < n; k++) {
            const o = k * data.stride;
            p.set(arr[o] - cx, arr[o + 1], arr[o + 2] - cz);
            q.setFromAxisAngle(up, arr[o + 3]);
            s.setScalar(arr[o + 4]);
            im.setMatrixAt(k, m.compose(p, q, s));
          }
          im.instanceMatrix.needsUpdate = true;
          im.computeBoundingSphere();   // per-chunk bounds -> frustum culling works per chunk
          im.castShadow = PRESET.tier === 'high' && CASTS_SHADOW.has(type);
          im.receiveShadow = false;
          im.matrixAutoUpdate = false;
          im.updateMatrix();
          root.add(im);
          const reach = (LAYER_DIST[type] ?? 150) + CHUNK * 0.71;   // compare against the chunk centre
          groups.current.push({ obj: im, maxSq: reach * reach });
        }
      }
    });
    scene.add(root);
    return () => {
      cancelled = true;
      scene.remove(root);
      for (const g of groups.current) g.obj.dispose();
      groups.current = [];
      root.clear();
    };
  }, [nodes, scene, root]);

  // per-layer distance culling every 4th frame
  const frame = useRef(0);
  useFrame(() => {
    if (frame.current++ % 4) return;
    const cp = camera.position;
    for (let k = 0; k < groups.current.length; k++) {
      const g = groups.current[k];
      const dx = g.obj.position.x - cp.x;
      const dz = g.obj.position.z - cp.z;
      g.obj.visible = dx * dx + dz * dz <= g.maxSq;
    }
  });
  return null;
}

/** Sea level plane (covers the sea, the river gorge) with gentle vertex waves on medium+ tiers. */
function Water() {
  const mat = useMemo(() => {
    const m = new THREE.MeshLambertMaterial({ color: '#4fd3d8', transparent: true, opacity: 0.55 });   // shallow sand shows through
    if (PRESET.tier !== 'low') {
      m.onBeforeCompile = (shader) => {
        shader.uniforms.uTime = waterTime;
        shader.vertexShader = shader.vertexShader
          .replace('#include <common>', '#include <common>\nuniform float uTime;')
          .replace('#include <begin_vertex>', '#include <begin_vertex>\ntransformed.z += 0.25 * sin(position.x * 0.05 + uTime) * cos(position.y * 0.04 + uTime * 0.8);');
      };
    }
    return m;
  }, []);
  useFrame((_, dt) => {
    waterTime.value += dt;
  });
  return (
    <mesh rotation-x={-Math.PI / 2} position-y={0} material={mat} renderOrder={1}>
      <planeGeometry args={[HALF * 2 + 4000, HALF * 2 + 4000, 64, 64]} />
    </mesh>
  );
}
const waterTime = { value: 0 };

useGLTF.preload(LOD_URLS, DRACO);
useGLTF.preload(`${T}props.glb`, DRACO);

/**
 * Upload every terrain LOD level and prop batch to the GPU once, behind the first frames, instead of the first time
 * each one scrolls into view mid-drive (that upload is a visible hitch on any GPU; skill: "spread upload cost").
 */
export function GpuWarmup() {
  const { gl, scene, camera } = useThree();
  useEffect(() => {
    let cancelled = false;
    propsReady.then(() => requestAnimationFrame(() => requestAnimationFrame(() => {
      if (cancelled) return;
      const lods: THREE.LOD[] = [];
      const saved: [THREE.Object3D, boolean, boolean][] = [];
      scene.traverse((o) => {
        if ((o as THREE.LOD).isLOD) {
          lods.push(o as THREE.LOD);
          (o as THREE.LOD).autoUpdate = false;
        }
        saved.push([o, o.visible, o.frustumCulled]);
        o.visible = true;
        o.frustumCulled = false;
      });
      const rt = new THREE.WebGLRenderTarget(8, 8);
      gl.setRenderTarget(rt);
      gl.render(scene, camera);
      gl.setRenderTarget(null);
      rt.dispose();
      for (const [o, v, f] of saved) {
        o.visible = v;
        o.frustumCulled = f;
      }
      for (const l of lods) l.autoUpdate = true;
    })));
    return () => {
      cancelled = true;
    };
  }, [gl, scene, camera]);
  return null;
}
