// Chunked island: 144 terrain chunks with 3 LODs, Rapier trimesh colliders streamed around the car,
// and props as one InstancedMesh per chunk per type, distance-culled per layer (lowend-webgl-optimization skill).
// Prop shadows are fake: soft blobs baked once into an island-wide grayscale texture that the terrain shader reads,
// so they cost one texture fetch per terrain pixel instead of a shadow-map pass over the scene every frame.
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { useFrame, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { CuboidCollider, RigidBody, useBeforePhysicsStep, useRapier } from '@react-three/rapier';
import type { Collider } from '@dimforge/rapier3d-compat';
import { CHUNK, DRACO, HALF, PRESET, telemetry } from './state';
import { sun } from './DayNight';
import { Grass, grassMask } from './Grass';
import { Leaves } from './Leaves';
import { BRUNO_DYNAMIC, BRUNO_STATIC, DynamicProps, useBrunoProps } from './BrunoProps';
import { noiseTexture } from './wind';
import { BROADLEAF, TREES, TreeFoliage, solidTreeGeometry, solidTreeMaterial, useBrunoTrees } from './Trees';

const T = '/models/terrain/';
const LOD_URLS = [`${T}terrain_lod0.glb`, `${T}terrain_lod1.glb`, `${T}terrain_lod2.glb`];
const LOD_DIST = [0, 260 * PRESET.lodScale, 620 * PRESET.lodScale];

// One shared flat-shaded vertex-color material for the whole terrain and every prop (skill: "3-6 materials in the game").
export const flatMaterial = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
// Man-made props are built in the clay style (bevelled edges + smooth normals, like the hero car): smooth Lambert.
const clayMaterial = new THREE.MeshLambertMaterial({ vertexColors: true });

// The terrain's copy of it also darkens the light by the baked prop-shadow texture (white until the bake is done).
const propShadow = { value: new THREE.DataTexture(new Uint8Array([255]), 1, 1, THREE.RedFormat) };
const shadowStrength = { value: 0.8 };
const shadowShift = { value: new THREE.Vector2() };   // uv offset that casts the blobs away from the sun
const SHADOW_HEIGHT = 2.5;   // typical canopy-centre height (m) the shift is computed for
propShadow.value.needsUpdate = true;
// Smooth-shaded (soft clay gradients; the mesh carries normals with creases kept sharp) and with procedural road detail.
const terrainMaterial = flatMaterial.clone();
terrainMaterial.flatShading = false;
terrainMaterial.customProgramCacheKey = () => 'terrain-prop-shadow-road';
// Stone slabs (Bruno Simon's folio-2025 Floor.js, MIT): his slab texture, tinted between two warm stone colours,
// blended into the ground where a mask says "paved" times a large noise, so paving breaks up and fades into the dirt.
// Paved = the highways (UV x offset +20, see island_chunks.py) and plazas baked into uPlaza (camps, stunt park, lift).
const slabsTexture = new THREE.TextureLoader().load('/models/bruno/slabs.png', (t) => {
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 4;
});
const plazaMask = { value: new THREE.DataTexture(new Uint8Array([0]), 1, 1, THREE.RedFormat) };
plazaMask.value.needsUpdate = true;
const SLAB_FREQ = 0.11;   // Bruno 0.175 (his car is ~2 m; our jeep is 4.5 m, so bigger slabs: ~1.1 m each)

terrainMaterial.onBeforeCompile = (shader) => {
  shader.uniforms.uSlabs = { value: slabsTexture };
  shader.uniforms.uPlaza = plazaMask;
  shader.uniforms.uNoise = { value: noiseTexture };
  shader.uniforms.uPropShadow = propShadow;
  shader.uniforms.uShadowStrength = shadowStrength;
  shader.uniforms.uShadowShift = shadowShift;
  shader.vertexShader = shader.vertexShader
    .replace('#include <common>', '#include <common>\nvarying vec2 vShadowUv;\nvarying vec2 vRoad;\nvarying vec2 vWorldXZ;')
    .replace('#include <project_vertex>', `#include <project_vertex>\nvWorldXZ = (modelMatrix * vec4(transformed, 1.0)).xz;\nvShadowUv = vWorldXZ / ${(2 * HALF).toFixed(1)} + 0.5;\nvRoad = uv;`);
  shader.fragmentShader = shader.fragmentShader
    .replace('#include <common>', '#include <common>\nvarying vec2 vShadowUv;\nvarying vec2 vRoad;\nuniform sampler2D uPropShadow;\nuniform float uShadowStrength;\nuniform vec2 uShadowShift;\nvarying vec2 vWorldXZ;\nuniform sampler2D uSlabs; uniform sampler2D uPlaza; uniform sampler2D uNoise;')
    // Roads: the mesh UV is (across the road in half-widths, metres along it); off-road it is >= 4. Draw a clay track:
    // two wandering tyre ruts, darker worn edges and zig-zag streaks (chevrons) pressed into the surface.
    .replace('#include <color_fragment>', `#include <color_fragment>
      float highway = step(10.0, vRoad.x);
      float u = vRoad.x - 20.0 * highway, v = vRoad.y;
      // stone slabs on every road and plaza, coloured from the road's own (biome) colour: brown stone in the forest,
      // red-brown in the desert, blue-grey in the snow, sand by the sea. Large noise patches break the paving into dirt.
      float onRoad = 1.0 - smoothstep(0.85, 1.05, abs(u));
      float plaza = texture2D(uPlaza, vShadowUv).r;
      float patches = smoothstep(0.38, 0.62, texture2D(uNoise, vWorldXZ * 0.0045).r);
      float slab = max(onRoad * mix(0.55, 1.0, patches), plaza * mix(0.35, 1.0, patches));
      if (slab > 0.01) {
        float tile = texture2D(uSlabs, vWorldXZ * ${SLAB_FREQ.toFixed(3)}).r;
        // plazas: warm stone on grass (Bruno's slab colours), else the ground's own colour (snow, sand, desert)
        bool green = diffuseColor.g > diffuseColor.r * 1.05 && diffuseColor.g > diffuseColor.b * 1.2;
        vec3 roadCol = onRoad > 0.5 ? diffuseColor.rgb : (green ? vec3(0.392, 0.184, 0.122) * 1.6 : diffuseColor.rgb * 0.92);
        vec3 slabColor = roadCol * mix(0.62, 1.45, tile) + vec3(0.03, 0.015, 0.0) * tile;   // grout dark, slab tops light
        diffuseColor.rgb = mix(diffuseColor.rgb, slabColor, slab);
      }
      if (abs(u) < 1.0) {   // tyre ruts and worn edges on top of the paving
        float wob = 0.07 * sin(v * 0.31) + 0.03 * sin(v * 1.27);
        float rut = smoothstep(0.17, 0.02, abs(abs(u + wob) - 0.45));
        float edge = smoothstep(0.7, 1.0, abs(u));
        float chevron = sin(v * 1.6 - abs(u) * 5.0 + sin(v * 0.17) * 2.0);
        diffuseColor.rgb *= 1.0 - 0.14 * rut - 0.12 * edge + 0.03 * chevron * (1.0 - slab) + 0.04 * (1.0 - abs(u));
      }`)
    .replace('#include <aomap_fragment>', `#include <aomap_fragment>
      toonDrop = (1.0 - texture2D(uPropShadow, vShadowUv + uShadowShift).r) * uShadowStrength;   // cast shadow -> shade tint`);
};

// Which props leave a shadow, and how dark its centre is (0..1).
const SHADOW_DARKNESS: Record<string, number> = {
  pine: 0.85, pine_snow: 0.85, cactus: 0.5, rock: 0.6, rock_snow: 0.6, bush: 0.45, oak: 0.85, birch: 0.85, cherry: 0.85,
  boulder: 0.7, tent_orange: 0.55, tent_red: 0.55, tent_blue: 0.55, caravan: 0.6, campfire: 0.3,
  palm: 0.5, pillar: 0.6, rock_red: 0.6, log: 0.4, stump: 0.3, picnic_table: 0.35, arch: 0.6, stunt_loop: 0.45,
  quarterpipe: 0.5, wave_ramp: 0.55, lift_station: 0.5, umbrella: 0.4, ice_block: 0.35, cabin: 0.6, shack: 0.6,
  water_tower: 0.45, igloo: 0.5, snowman: 0.4, dead_tree: 0.3, tire_stack: 0.4, b_lantern: 0.3, b_pole: 0.25,
  car_jeep: 0.6, car_buggy: 0.6, car_van: 0.6, car_hatch: 0.6,
};

/** Paints a soft blob per prop into a size x size single-channel texture covering the island (255 = lit). */
function bakePropShadows(data: PropsFile, footprint: Record<string, number>, size: number) {
  const px = new Uint8Array(size * size).fill(255);   // 1 byte per texel: 4 MB at 2048, 16 MB at 4096
  const perM = size / (2 * HALF);
  for (const types of Object.values(data.placements)) {
    for (const [type, arr] of Object.entries(types)) {
      const dark = SHADOW_DARKNESS[type];
      const foot = footprint[type];
      if (!dark || !foot) continue;
      for (let o = 0; o < arr.length; o += data.stride) {
        const r = foot * arr[o + 4] * 1.2 * perM;   // radius in texels, a bit wider than the canopy for a soft edge
        const cx = (arr[o] + HALF) * perM - 0.5;
        const cy = (arr[o + 2] + HALF) * perM - 0.5;
        const x0 = Math.max(0, Math.floor(cx - r)), x1 = Math.min(size - 1, Math.ceil(cx + r));
        const y0 = Math.max(0, Math.floor(cy - r)), y1 = Math.min(size - 1, Math.ceil(cy + r));
        for (let y = y0; y <= y1; y++) {
          for (let x = x0; x <= x1; x++) {
            const d2 = ((x - cx) ** 2 + (y - cy) ** 2) / (r * r);
            if (d2 >= 1) continue;
            const f = (1 - d2) * (1 - d2);   // smooth falloff to 0 at the rim
            px[y * size + x] *= 1 - dark * f;   // multiply: overlapping canopies darken further, never below 0
          }
        }
      }
    }
  }
  const tex = new THREE.DataTexture(px, size, size, THREE.RedFormat, THREE.UnsignedByteType);
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.needsUpdate = true;
  return tex;
}

/** Paved plazas (1024^2 mask over the island): around every camp fire, the stunt park loop and the ski lift stations. */
const PLAZAS: Record<string, number> = { campfire: 15, stunt_loop: 58, lift_station: 14 };
function bakePlazas(data: PropsFile) {
  const size = 1024, perM = size / (2 * HALF);
  const px = new Uint8Array(size * size);
  for (const types of Object.values(data.placements)) {
    for (const [type, radius] of Object.entries(PLAZAS)) {
      const arr = types[type];
      if (!arr) continue;
      for (let o = 0; o < arr.length; o += data.stride) {
        const cx = (arr[o] + HALF) * perM, cy = (arr[o + 2] + HALF) * perM, r = radius * perM;
        for (let y = Math.max(0, Math.floor(cy - r)); y <= Math.min(size - 1, Math.ceil(cy + r)); y++) {
          for (let x = Math.max(0, Math.floor(cx - r)); x <= Math.min(size - 1, Math.ceil(cx + r)); x++) {
            const d = Math.hypot(x - cx, y - cy) / r;
            if (d < 1) px[y * size + x] = Math.max(px[y * size + x], 255 * Math.min(1, (1 - d) * 3));
          }
        }
      }
    }
  }
  const t = new THREE.DataTexture(px, size, size, THREE.RedFormat, THREE.UnsignedByteType);
  t.magFilter = t.minFilter = THREE.LinearFilter;
  t.needsUpdate = true;
  return t;
}

/** Grass beds: a soft disc of grass around every tree, bush, rock and piece of furniture (radius in m at scale 1). */
const GRASS_BED: Record<string, number> = {
  pine: 4.5, pine_snow: 4.5, oak: 5, birch: 5, cherry: 5, bush: 3.5, rock: 2.6, boulder: 5.5, stump: 2.2, log: 2.6,
  b_lantern: 2.6, b_bench: 3.2, b_pole: 2.2, picnic_table: 3, signpost: 2,
};
function bakeGrassBeds(data: PropsFile) {
  const size = PRESET.tier === 'low' ? 1024 : 2048, perM = size / (2 * HALF);
  const px = new Uint8Array(size * size);
  for (const types of Object.values(data.placements)) {
    for (const [type, radius] of Object.entries(GRASS_BED)) {
      const arr = types[type];
      if (!arr) continue;
      for (let o = 0; o < arr.length; o += data.stride) {
        const cx = (arr[o] + HALF) * perM, cy = (arr[o + 2] + HALF) * perM, r = radius * Math.min(arr[o + 4], 1.6) * perM;
        for (let y = Math.max(0, Math.floor(cy - r)); y <= Math.min(size - 1, Math.ceil(cy + r)); y++) {
          for (let x = Math.max(0, Math.floor(cx - r)); x <= Math.min(size - 1, Math.ceil(cx + r)); x++) {
            const d = Math.hypot(x - cx, y - cy) / r;
            if (d < 1) px[y * size + x] = Math.max(px[y * size + x], 255 * Math.min(1, (1 - d) * 2.2));
          }
        }
      }
    }
  }
  const t = new THREE.DataTexture(px, size, size, THREE.RedFormat, THREE.UnsignedByteType);
  t.magFilter = t.minFilter = THREE.LinearFilter;
  t.needsUpdate = true;
  return t;
}

type PropsFile = {
  chunkSize: number; stride: number; types: string[]; placements: Record<string, Record<string, number[]>>;
  clay?: string[];
  features?: { lift?: number[][]; waterfalls?: { top: number[]; bottom: number[]; width: number }[] };
};

// Prop placements are needed by both the renderer (instancing) and the physics (tree/rock colliders): load once.
let PROPS: PropsFile | null = null;
const propsReady = fetch(`${T}props.json`).then((r) => r.json()).then((d: PropsFile) => (PROPS = broadleaf(thinned(d))));

/** Turn a share of the forest pines into Bruno's oak / birch / cherry trees (stable per-tree hash). */
function broadleaf(d: PropsFile) {
  for (const types of Object.values(d.placements)) {
    const pines = types.pine;
    if (!pines) continue;
    const keep: number[] = [];
    for (let o = 0; o < pines.length; o += d.stride) {
      const h = Math.abs((Math.sin(pines[o] * 3.17 + pines[o + 2] * 7.31) * 9137.53) % 1);
      const inst = pines.slice(o, o + d.stride);
      if (h >= BROADLEAF.share) keep.push(...inst);
      else {
        const k = h / BROADLEAF.share;
        const type = k < BROADLEAF.oak ? 'oak' : k < BROADLEAF.birch ? 'birch' : 'cherry';
        (types[type] ??= []).push(...inst);
      }
    }
    types.pine = keep;
  }
  return d;
}

/** Low tier: keep PRESET.propDensity of the dense small props (same instances for drawing, colliders and shadows). */
const THINNED = new Set(['pine', 'pine_snow', 'bush', 'grass_tuft']);
function thinned(d: PropsFile) {
  if (PRESET.propDensity >= 1) return d;
  for (const types of Object.values(d.placements)) {
    for (const [type, arr] of Object.entries(types)) {
      if (!THINNED.has(type)) continue;
      const keep: number[] = [];
      for (let o = 0; o < arr.length; o += d.stride) {
        const h = (Math.sin(arr[o] * 12.9898 + arr[o + 2] * 78.233) * 43758.5453) % 1;   // stable per instance
        if (Math.abs(h) < PRESET.propDensity) keep.push(...arr.slice(o, o + d.stride));
      }
      types[type] = keep;
    }
  }
  return d;
}

// Solid props get primitive colliders (skill: props use primitives, never trimesh); grass and bushes stay drive-through.
// 'box' = the model's bounding box, 'hull' = convex hull of its vertices (ramps you drive up, boulder clusters).
// 'mesh' = exact trimesh from the model's <type>_col node (loop, quarter-pipe, bridge deck: hollow / curved shapes you
// drive on or through); 'arch' = the two pillars of a rock arch (the opening stays drivable).
type Solid = 'trunk' | 'rock' | 'box' | 'hull' | 'mesh' | 'arch';
const SOLID: Record<string, Solid> = {
  pine: 'trunk', pine_snow: 'trunk', cactus: 'trunk', rock: 'rock', rock_snow: 'rock', oak: 'trunk', birch: 'trunk', cherry: 'trunk',
  tent_orange: 'box', tent_red: 'box', tent_blue: 'box', caravan: 'box', campfire: 'box', fence: 'box',
  lamp_post: 'trunk', flag: 'trunk', boulder: 'hull', ramp: 'hull',
  palm: 'trunk', barrel: 'trunk', signpost: 'trunk', rock_red: 'rock', pillar: 'hull', log: 'box', stump: 'box',
  picnic_table: 'box', crate: 'box', car_jeep: 'box', car_buggy: 'box', car_van: 'box', car_hatch: 'box',
  stunt_loop: 'mesh', quarterpipe: 'mesh', wave_ramp: 'mesh', bridge: 'mesh', dock: 'mesh', gate: 'mesh',
  ramp_snow: 'hull', ramp_log: 'hull', ice_block: 'box', lift_station: 'box', lift_tower: 'trunk', arch: 'arch',
  tire_stack: 'trunk', cabin: 'box', shack: 'box', water_tower: 'box', windmill: 'trunk', snowman: 'trunk', igloo: 'hull',
  dead_tree: 'trunk', b_lantern: 'box', b_pole: 'box',
};
// rock_arch in island_chunks.py: pillars 3.2 x 3.4 x 10 m centred at x = +-6.5
const ARCH_PILLAR = { x: 6.5, half: new THREE.Vector3(1.6, 5, 1.7) };
// Pines swap to a few-triangle far model (<type>_far in props.glb) for chunks further than this from the camera.
const FAR_FROM = { low: CHUNK * 0.6, medium: CHUNK * 0.9, high: CHUNK * 1.1 }[PRESET.tier];
// Prop colliders are created at most this many per physics step, so entering a dense forest chunk never hitches.
const COLLIDERS_PER_STEP = 150;
type PropShape = { center: THREE.Vector3; half: THREE.Vector3; points: Float32Array; index?: Uint32Array };

const PQ = new THREE.Quaternion();
const PV = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);

// Per-layer draw distances (skill: rocks 80-120 m, trees 200-450 m by tier).
const LAYER_DIST: Record<string, number> = {
  pine: PRESET.treeDistance, pine_snow: PRESET.treeDistance, cactus: PRESET.treeDistance,
  oak: PRESET.treeDistance, birch: PRESET.treeDistance, cherry: PRESET.treeDistance,
  rock: PRESET.propDistance * 1.6, rock_snow: PRESET.propDistance * 1.6, bush: PRESET.propDistance * 1.2,
  grass_tuft: PRESET.propDistance * 0.7, boulder: PRESET.propDistance * 2,
  tent_orange: PRESET.propDistance * 1.6, tent_red: PRESET.propDistance * 1.6, tent_blue: PRESET.propDistance * 1.6,
  caravan: PRESET.propDistance * 1.6, campfire: PRESET.propDistance * 1.6, lamp_post: PRESET.propDistance * 1.6,
  flag: PRESET.propDistance * 1.6, fence: PRESET.propDistance * 1.4, ramp: PRESET.propDistance * 2.5,
  palm: PRESET.treeDistance, pillar: PRESET.treeDistance, rock_red: PRESET.propDistance * 1.6,
  log: PRESET.propDistance * 1.2, stump: PRESET.propDistance * 1.2, picnic_table: PRESET.propDistance * 1.4,
  camp_chair: PRESET.propDistance, crate: PRESET.propDistance * 1.2, barrel: PRESET.propDistance * 1.2,
  signpost: PRESET.propDistance * 1.4, car_jeep: PRESET.propDistance * 1.6, car_buggy: PRESET.propDistance * 1.6,
  car_van: PRESET.propDistance * 1.6, car_hatch: PRESET.propDistance * 1.6,
  // play areas are landmarks: visible from far
  stunt_loop: PRESET.treeDistance, quarterpipe: PRESET.treeDistance, wave_ramp: PRESET.treeDistance, gate: PRESET.treeDistance,
  bridge: PRESET.treeDistance, arch: PRESET.treeDistance, lift_tower: PRESET.treeDistance, lift_station: PRESET.treeDistance,
  gallery: PRESET.treeDistance, dock: PRESET.propDistance * 2, boat: PRESET.propDistance * 2, ramp_snow: PRESET.propDistance * 2.5,
  ramp_log: PRESET.propDistance * 2.5, umbrella: PRESET.propDistance * 1.4, towel: PRESET.propDistance, ice_block: PRESET.propDistance * 1.6,
  tire_stack: PRESET.propDistance * 1.6, cabin: PRESET.treeDistance, shack: PRESET.treeDistance, water_tower: PRESET.treeDistance,
  windmill: PRESET.treeDistance, snowman: PRESET.propDistance * 2, igloo: PRESET.propDistance * 2.5, dead_tree: PRESET.treeDistance,
  b_lantern: PRESET.propDistance * 1.4, b_pole: PRESET.propDistance * 2,
};

export function World() {
  const lods = useGLTF(LOD_URLS, DRACO);
  const { nodes } = useGLTF(`${T}props.glb`, DRACO);
  const brunoProps = useBrunoProps();
  // collider shapes of the box / hull props, from their models (unscaled, three.js axes)
  const shapes = useMemo(() => {
    const out: Record<string, PropShape> = {};
    for (const [type, kind] of Object.entries(SOLID)) {
      const g = brunoProps.geometries[type] ?? ((kind === 'mesh' ? nodes[`${type}_col`] : nodes[type]) as THREE.Mesh | undefined)?.geometry;
      if (!g || (kind !== 'box' && kind !== 'hull' && kind !== 'mesh')) continue;
      if (!g.boundingBox) g.computeBoundingBox();
      const b = g.boundingBox!;
      out[type] = {
        center: b.getCenter(new THREE.Vector3()), half: b.getSize(new THREE.Vector3()).multiplyScalar(0.5),
        points: Float32Array.from(g.getAttribute('position').array),
        index: g.index ? Uint32Array.from(g.index.array) : undefined,
      };
    }
    return out;
  }, [nodes, brunoProps]);
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
        const mesh = new THREE.Mesh(src.geometry, terrainMaterial);
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
      <ColliderStreamer chunks={chunks} shapes={shapes} />
      <Grass chunks={chunks} />
      <Leaves />
      <Props />
      <GpuWarmup />
      <Water />
      <Waterfalls />
      <SkiLift />
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
function ColliderStreamer({ chunks, shapes }: { chunks: { key: string; lod0: THREE.Mesh }[]; shapes: Record<string, PropShape> }) {
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

  // chunk props waiting for colliders: [chunk key, its colliders, type list, type index, offset in that type's array]
  const queue = useRef<{ key: string; cols: Collider[]; types: [string, number[]][]; t: number; o: number }[]>([]);
  const buildProps = (key: string) => {
    const cols: Collider[] = [];
    props.current.set(key, cols);
    queue.current.push({ key, cols, types: Object.entries(PROPS!.placements[key] ?? {}).filter(([type, arr]) => SOLID[type] && arr.length), t: 0, o: 0 });
  };
  const drainQueue = () => {
    const stride = PROPS!.stride;
    let budget = COLLIDERS_PER_STEP;
    while (budget > 0 && queue.current.length) {
      const job = queue.current[0];
      if (props.current.get(job.key) !== job.cols || job.t >= job.types.length) {   // unloaded meanwhile, or done
        queue.current.shift();
        continue;
      }
      const [type, arr] = job.types[job.t];
      const kind = SOLID[type];
      const shape = shapes[type];
      const o = job.o;
      job.o += stride;
      if (job.o >= arr.length) {
        job.t++;
        job.o = 0;
      }
      budget--;
      const s = arr[o + 4];
      let d;
      try {
      if (kind === 'trunk') d = rapier.ColliderDesc.cylinder(1.6 * s, 0.35 * s).setTranslation(arr[o], arr[o + 1] + 1.6 * s, arr[o + 2]);
      else if (kind === 'rock') d = rapier.ColliderDesc.ball(0.95 * s).setTranslation(arr[o], arr[o + 1] + 0.25 * s, arr[o + 2]);
      else if (kind === 'arch') {
        const q = PQ.setFromAxisAngle(UP, arr[o + 3]);
        for (const sx of [-1, 1]) {
          const c = PV.set(sx * ARCH_PILLAR.x * s, ARCH_PILLAR.half.y * s, 0).applyQuaternion(q);
          job.cols.push(world.createCollider(rapier.ColliderDesc.cuboid(ARCH_PILLAR.half.x * s, ARCH_PILLAR.half.y * s, ARCH_PILLAR.half.z * s)
            .setTranslation(arr[o] + c.x, arr[o + 1] + c.y, arr[o + 2] + c.z).setRotation({ x: q.x, y: q.y, z: q.z, w: q.w })));
        }
        continue;
      } else {
        if (!shape) continue;
        const q = PQ.setFromAxisAngle(UP, arr[o + 3]);   // same yaw as the instance
        if (kind === 'box') {
          const c = PV.copy(shape.center).multiplyScalar(s).applyQuaternion(q);
          d = rapier.ColliderDesc.cuboid(shape.half.x * s, shape.half.y * s, shape.half.z * s).setTranslation(arr[o] + c.x, arr[o + 1] + c.y, arr[o + 2] + c.z);
        } else if (kind === 'mesh' && shape.index) {
          d = rapier.ColliderDesc.trimesh(shape.points.map((v) => v * s), shape.index).setTranslation(arr[o], arr[o + 1], arr[o + 2]);
        } else {
          const pts = shape.points.map((v) => v * s);
          d = rapier.ColliderDesc.convexHull(pts)?.setTranslation(arr[o], arr[o + 1], arr[o + 2]);
          if (!d) continue;
        }
        d.setRotation({ x: q.x, y: q.y, z: q.z, w: q.w });
      }
      } catch (err) {   // a model without a usable shape: skip it rather than leave the physics world in a bad state
        if (import.meta.env.DEV) console.warn('collider skipped:', type, kind, shape?.center, shape?.half, (err as Error).message);
        continue;
      }
      job.cols.push(world.createCollider(d.setFriction(0.6)));
    }
  };

  useBeforePhysicsStep(() => {
    if (!PROPS) return;
    drainQueue();
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
  const bruno = useBrunoTrees();
  const brunoProps = useBrunoProps();
  const [placed, setPlaced] = useState<PropsFile | null>(null);
  // trees (TREES in Trees.tsx) are built here instead of taken from props.glb: solid near + far versions per type
  const trees = useMemo(() => Object.fromEntries(Object.keys(TREES).map((type) => [type, {
    near: solidTreeGeometry(type, bruno.trunks, false), far: solidTreeGeometry(type, bruno.trunks, true),
    material: solidTreeMaterial(type, bruno.palette),
  }])), [bruno]);
  const { camera, scene } = useThree();
  const groups = useRef<{ obj: THREE.InstancedMesh; far?: THREE.InstancedMesh; maxSq: number }[]>([]);
  const root = useMemo(() => new THREE.Group(), []);

  useEffect(() => {
    let cancelled = false;
    propsReady.then((data) => {
      if (cancelled) return;
      // shadow blob radius per prop type = half the model's average horizontal extent at scale 1
      const footprint: Record<string, number> = {};
      for (const [type, t] of Object.entries(TREES)) {   // tree shadow = the crown's widest blob reach
        footprint[type] = Math.max(...t.blobs.map(([x, , z, sz]) => Math.hypot(x, z) + 1.15 * sz));
      }
      for (const type of Object.keys(SHADOW_DARKNESS)) {
        if (footprint[type]) continue;
        const g = (nodes[type] as THREE.Mesh | undefined)?.geometry;
        if (!g) continue;
        if (!g.boundingBox) g.computeBoundingBox();
        const b = g.boundingBox!;
        footprint[type] = (b.max.x - b.min.x + b.max.z - b.min.z) / 4;
      }
      propShadow.value.dispose();
      propShadow.value = bakePropShadows(data, footprint, PRESET.shadowTexSize);
      plazaMask.value.dispose();
      plazaMask.value = bakePlazas(data);
      grassMask.value.dispose();
      grassMask.value = bakeGrassBeds(data);
      setPlaced(data);
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
          if (BRUNO_DYNAMIC[type]) continue;   // drawn + simulated by DynamicProps
          const tree = trees[type];
          const brunoGeo = BRUNO_STATIC.has(type) ? brunoProps.geometries[type] : undefined;
          const src = tree || brunoGeo ? null : (nodes[type] as THREE.Mesh | undefined);
          if (!tree && !brunoGeo && !src) continue;
          const n = arr.length / data.stride;
          if (!n) continue;
          const material = tree ? tree.material : brunoGeo ? brunoProps.material : data.clay?.includes(type) ? clayMaterial : flatMaterial;
          const instanced = (geometry: THREE.BufferGeometry) => {
            const im = new THREE.InstancedMesh(geometry, material, n);
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
            im.matrixAutoUpdate = false;
            im.updateMatrix();
            root.add(im);
            return im;
          };
          const farGeo = tree ? tree.far : (nodes[`${type}_far`] as THREE.Mesh | undefined)?.geometry;
          const reach = (LAYER_DIST[type] ?? 150) + CHUNK * 0.71;   // compare against the chunk centre
          groups.current.push({ obj: instanced(tree ? tree.near : brunoGeo ?? src!.geometry), far: farGeo && instanced(farGeo), maxSq: reach * reach });
        }
      }
    });
    scene.add(root);
    return () => {
      cancelled = true;
      scene.remove(root);
      for (const g of groups.current) {
        g.obj.dispose();
        g.far?.dispose();
      }
      groups.current = [];
      root.clear();
    };
  }, [nodes, scene, root, trees, brunoProps]);

  // per-layer distance culling every 4th frame
  const frame = useRef(0);
  useFrame(() => {
    // a prop's shadow lands sunXZ / sunY * height away from it, so this pixel shows the blob of the prop that far sunward
    shadowStrength.value = sun.shadow;
    const reach = Math.min(SHADOW_HEIGHT / Math.max(sun.y, 0.25), 8) / (2 * HALF);
    shadowShift.value.set(sun.x * reach, sun.z * reach);
    if (frame.current++ % 4) return;
    const cp = camera.position;
    for (let k = 0; k < groups.current.length; k++) {
      const g = groups.current[k];
      const dx = g.obj.position.x - cp.x;
      const dz = g.obj.position.z - cp.z;
      const d2 = dx * dx + dz * dz;
      const shown = d2 <= g.maxSq;
      if (g.far) {   // whole chunk switches between the full and the far model
        g.obj.visible = shown && d2 <= FAR_FROM * FAR_FROM;
        g.far.visible = shown && !g.obj.visible;
      } else g.obj.visible = shown;
    }
  });
  return (
    <>
      <TreeFoliage placements={placed?.placements ?? null} stride={placed?.stride ?? 5} />
      <DynamicProps placements={placed?.placements ?? null} stride={placed?.stride ?? 5} />
    </>
  );
}

/** Sea level plane (covers the sea, the river gorge) with gentle vertex waves on medium+ tiers. */
function Water() {
  const mat = useMemo(() => {
    // unlit vivid turquoise (water reflects the sky: no toon shade), fog still applies; the sand shows through
    const m = new THREE.MeshBasicMaterial({ color: '#19c6d6', transparent: true, opacity: 0.62 });
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

/** Animated waterfalls pouring down the canyon walls (refs 02/04/09): a streaked sheet scrolling downward + foam. */
function Waterfalls() {
  const [falls, setFalls] = useState<NonNullable<NonNullable<PropsFile['features']>['waterfalls']>>([]);
  useEffect(() => {
    propsReady.then((d) => setFalls(d.features?.waterfalls ?? []));
  }, []);
  const tex = useMemo(() => {
    const cv = document.createElement('canvas');
    cv.width = 32;
    cv.height = 128;
    const ctx = cv.getContext('2d')!;
    ctx.fillStyle = '#9fe0ec';
    ctx.fillRect(0, 0, 32, 128);
    for (let k = 0; k < 40; k++) {   // vertical white streaks
      ctx.fillStyle = `rgba(255,255,255,${0.35 + Math.random() * 0.5})`;
      ctx.fillRect(Math.random() * 32, Math.random() * 128, 1 + Math.random() * 3, 10 + Math.random() * 40);
    }
    const t = new THREE.CanvasTexture(cv);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    return t;
  }, []);
  const mat = useMemo(() => new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthWrite: false }), [tex]);
  const foamMat = useMemo(() => new THREE.MeshLambertMaterial({ color: '#f4fbff', flatShading: true }), []);
  const geos = useMemo(() => falls.map((f) => {
    const top = new THREE.Vector3(...f.top), bot = new THREE.Vector3(...f.bottom);
    const across = new THREE.Vector3(bot.x - top.x, 0, bot.z - top.z).normalize().cross(UP).multiplyScalar(f.width / 2);
    const g = new THREE.BufferGeometry();
    const p = [top.clone().add(across), top.clone().sub(across), bot.clone().add(across), bot.clone().sub(across)];
    g.setAttribute('position', new THREE.Float32BufferAttribute(p.flatMap((v) => [v.x, v.y, v.z]), 3));
    const rep = Math.max(1, top.distanceTo(bot) / 12);
    g.setAttribute('uv', new THREE.Float32BufferAttribute([0, rep, 1, rep, 0, 0, 1, 0], 2));
    g.setIndex([0, 2, 1, 1, 2, 3]);
    return { g, bot, width: f.width };
  }), [falls]);
  const foam = useRef<THREE.Group>(null);
  useFrame((st, dt) => {
    tex.offset.y += dt * 1.6;
    const t = st.clock.elapsedTime;
    foam.current?.children.forEach((c, k) => c.scale.setScalar(1 + 0.15 * Math.sin(t * 3 + k)));
  });
  return (
    <>
      {geos.map(({ g }, k) => <mesh key={k} geometry={g} material={mat} />)}
      <group ref={foam}>
        {geos.map(({ bot, width }, k) => (
          <mesh key={k} position={[bot.x, 0.4, bot.z]} scale={[width * 0.45, 1, width * 0.45]} material={foamMat}>
            <icosahedronGeometry args={[1, 1]} />
          </mesh>
        ))}
      </group>
    </>
  );
}

/** Ski lift (refs 08/09): two cables over the tower tops and red gondolas looping up one side and down the other. */
function SkiLift() {
  const { nodes } = useGLTF(`${T}props.glb`, DRACO);
  const [pts, setPts] = useState<THREE.Vector3[]>([]);
  useEffect(() => {
    propsReady.then((d) => setPts((d.features?.lift ?? []).map((q) => new THREE.Vector3(q[0], q[1], q[2]))));
  }, []);
  const path = useMemo(() => {
    if (pts.length < 2) return null;
    const dir = pts[pts.length - 1].clone().sub(pts[0]).setY(0).normalize();
    const side = new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(1.8);
    const up = pts.map((q) => q.clone().add(side));
    const down = pts.slice().reverse().map((q) => q.clone().sub(side));
    const loop = [...up, ...down];
    const lens = [0];
    for (let k = 1; k < loop.length; k++) lens.push(lens[k - 1] + loop[k].distanceTo(loop[k - 1]));
    const cable = new THREE.BufferGeometry().setFromPoints([...up, ...down, up[0]]);
    return { loop, lens, total: lens[lens.length - 1] + loop[0].distanceTo(loop[loop.length - 1]), cable };
  }, [pts]);
  const N = 8;
  const gondolas = useRef<THREE.InstancedMesh>(null);
  const cable = useMemo(() => path && new THREE.Line(path.cable, new THREE.LineBasicMaterial({ color: '#2b2b30' })), [path]);
  const m = useMemo(() => new THREE.Matrix4(), []);
  const pos = useMemo(() => new THREE.Vector3(), []);
  useFrame((st) => {
    const g = gondolas.current;
    if (!g || !path) return;
    for (let k = 0; k < N; k++) {
      const d = (st.clock.elapsedTime * 3 + (k / N) * path.total) % path.total;
      let i = 0;
      while (i < path.lens.length - 1 && path.lens[i + 1] < d) i++;
      const a = path.loop[i], b = path.loop[(i + 1) % path.loop.length];
      const seg = (i + 1 < path.lens.length ? path.lens[i + 1] : path.total) - path.lens[i];
      pos.copy(a).lerp(b, seg > 0 ? (d - path.lens[i]) / seg : 0);
      g.setMatrixAt(k, m.makeTranslation(pos.x, pos.y, pos.z));
    }
    g.instanceMatrix.needsUpdate = true;
  });
  const gondola = nodes.gondola as THREE.Mesh | undefined;
  if (!path || !gondola) return null;
  return (
    <>
      {cable && <primitive object={cable} />}
      <instancedMesh ref={gondolas} args={[gondola.geometry, clayMaterial, N]} frustumCulled={false} />
    </>
  );
}
