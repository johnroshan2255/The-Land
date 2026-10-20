// Trees and bushes in the style of Bruno Simon's folio-2025 (Trees.js + Foliage.js, MIT licence,
// github.com/brunosimon/folio-2025). A tree = a trunk + a few leaf "blobs". Each blob is drawn as a cluster of small
// camera-facing cards cut out by his leaf-shape texture (foliageSDF.png); the cards flutter with the wind and take
// colour A on the side away from the sun and colour B toward it, then the toon shade on top. Cards fade out around the
// car on screen so it is never hidden. Oak, birch and cherry trunks + blob layouts are his models (models/bruno).
//
// Phones can't afford thousands of card clusters, so cards are only drawn for trees near the car (FOLIAGE radius, by
// tier). Every tree, near or far, also has a solid low-poly version per chunk (trunk + one 20-triangle icosphere per
// blob, same colours); within the card radius its blobs shrink away as the cards fade in.
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import { useFrame, useLoader, useThree } from '@react-three/fiber';
import { useGLTF } from '@react-three/drei';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { DRACO, PRESET, telemetry } from './state';
import { windGLSL, windUniforms } from './wind';

const B = '/models/bruno/';
type Blob = [number, number, number, number];   // x, y, z, size (Bruno: card sphere radius 1 x size)
type TreeType = { blobs: Blob[]; far: Blob[]; trunk: 'pine' | 'oak' | 'birch' | 'cherry' | null; a: string; b: string };

// Blob layouts in metres at instance scale 1. Pines: stacked blobs shrinking upward = a fluffy cone like the refs.
const PINE: Blob[] = [[0, 1.9, 0, 1.3], [0, 3.1, 0, 1.05], [0, 4.2, 0, 0.8], [0, 5.1, 0, 0.55]];
const PINE_FAR: Blob[] = [[0, 2.4, 0, 1.4], [0, 4.4, 0, 0.85]];
export const TREES: Record<string, TreeType> = {
  // colours as bright as Bruno's (the toon shade darkens the far side on top of colour A)
  pine: { blobs: PINE, far: PINE_FAR, trunk: 'pine', a: '#3d7f2a', b: '#8fc23c' },
  pine_snow: { blobs: PINE, far: PINE_FAR, trunk: 'pine', a: '#73a064', b: '#ffffff' },
  bush: { blobs: [[0, 0.75, 0, 0.85], [0.75, 0.6, 0.3, 0.62], [-0.6, 0.62, 0.45, 0.66]], far: [[0, 0.7, 0, 1.0]], trunk: null, a: '#4f8a2a', b: '#a8c83c' },
  // Bruno's three trees, his colours (World.js)
  oak: { blobs: [], far: [], trunk: 'oak', a: '#b4b536', b: '#d8cf3b' },
  birch: { blobs: [], far: [], trunk: 'birch', a: '#ff4f2b', b: '#ff903f' },
  cherry: { blobs: [], far: [], trunk: 'cherry', a: '#ff6d6d', b: '#ff9990' },
};
const BRUNO_SCALE = 0.85;   // his trees are ~7 m; ours are placed at scale 1..2
// Forest pines that become broadleaf trees (by a stable per-tree hash): oak / birch / cherry share
export const BROADLEAF = { share: 0.18, oak: 0.55, birch: 0.85 };

// Card-cluster radius around the car, and cards per blob (Bruno: 80), by tier
const FOLIAGE = { low: { r: 48, cards: 24 }, medium: { r: 72, cards: 36 }, high: { r: 100, cards: 52 } }[PRESET.tier];
const FADE = 10;   // m over which blobs shrink / cards fade in at the radius edge

const carUniform = { value: new THREE.Vector3() };
const radiusUniform = { value: FOLIAGE.r };

/** Bruno's blob layouts + trunk geometries, read from his tree models. */
export function useBrunoTrees() {
  const gltfs = useGLTF([`${B}oakTreesVisual.glb`, `${B}birchTreesVisual.glb`, `${B}cherryTreesVisual.glb`], DRACO);
  const palette = useLoader(THREE.TextureLoader, `${B}palette.png`);
  return useMemo(() => {
    palette.colorSpace = THREE.SRGBColorSpace;
    palette.magFilter = palette.minFilter = THREE.NearestFilter;
    const trunks: Record<string, THREE.BufferGeometry> = {};
    (['oak', 'birch', 'cherry'] as const).forEach((name, k) => {
      const blobs: Blob[] = [];
      gltfs[k].scene.updateMatrixWorld(true);
      gltfs[k].scene.traverse((o) => {
        const m = o as THREE.Mesh;
        if (!m.isMesh) return;
        if (m.name.startsWith('treeLeaves')) blobs.push([m.position.x, m.position.y, m.position.z, m.scale.x].map((v, i) => v * (i === 3 ? BRUNO_SCALE * 1.15 : BRUNO_SCALE)) as Blob);
        else if (m.name.startsWith('treeBody')) trunks[name] = m.geometry.clone().applyMatrix4(m.matrixWorld).scale(BRUNO_SCALE, BRUNO_SCALE, BRUNO_SCALE);
      });
      TREES[name].blobs = blobs;
      TREES[name].far = blobs.filter((b) => b[3] > 0.7 * BRUNO_SCALE);
    });
    // our pine trunk, UV-mapped onto the same palette texel as Bruno's oak bark
    const bark = trunks.oak.getAttribute('uv');
    const u0 = bark.getX(0), v0 = bark.getY(0);
    const pine = new THREE.CylinderGeometry(0.12, 0.26, 2.2, 6).translate(0, 1.1, 0);
    pine.setAttribute('uv', new THREE.Float32BufferAttribute(new Array(pine.getAttribute('position').count * 2).fill(0).map((_, i) => (i % 2 ? v0 : u0)), 2));
    trunks.pine = pine;
    return { trunks, palette };
  }, [gltfs, palette]);
}

/** Solid tree geometry: trunk (part 0) + one icosphere per blob (part 1), with each vertex's blob centre. */
export function solidTreeGeometry(type: string, trunks: Record<string, THREE.BufferGeometry>, far: boolean) {
  const t = TREES[type];
  const parts: THREE.BufferGeometry[] = [];
  const tag = (g: THREE.BufferGeometry, part: number, c: THREE.Vector3) => {
    g = g.index ? g.toNonIndexed() : g;
    for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k);
    if (!g.getAttribute('uv')) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.getAttribute('position').count * 2), 2));
    const n = g.getAttribute('position').count;
    g.setAttribute('part', new THREE.Float32BufferAttribute(new Float32Array(n).fill(part), 1));
    g.setAttribute('blobC', new THREE.Float32BufferAttribute(new Float32Array(n * 3).map((_, i) => [c.x, c.y, c.z][i % 3]), 3));
    parts.push(g);
  };
  if (t.trunk && !far) tag(trunks[t.trunk].clone(), 0, new THREE.Vector3());
  for (const [x, y, z, s] of far ? t.far : t.blobs) {
    tag(new THREE.IcosahedronGeometry(1.15 * s, 0).translate(x, y, z), 1, new THREE.Vector3(x, y, z));
  }
  return mergeGeometries(parts)!;
}

/** Material for the solid trees: palette bark, crown coloured A -> B toward the sun (toon shaded), crowns of trees
 *  within the card radius shrink to their blob centres so the card clusters can take over. */
export function solidTreeMaterial(type: string, palette: THREE.Texture) {
  const t = TREES[type];
  const m = new THREE.MeshLambertMaterial({ flatShading: true });
  m.customProgramCacheKey = () => `solid-tree-${type}`;
  m.onBeforeCompile = (s) => {
    Object.assign(s.uniforms, { uPalette: { value: palette }, uColA: { value: new THREE.Color(t.a) }, uColB: { value: new THREE.Color(t.b) }, uCar: carUniform, uR: radiusUniform });
    s.vertexShader = s.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float part; attribute vec3 blobC; varying float vPart; varying vec2 vUv0;\nuniform vec3 uCar; uniform float uR;')
      .replace('#include <begin_vertex>', /* glsl */ `#include <begin_vertex>
        vPart = part; vUv0 = uv;
        #ifdef USE_INSTANCING
        vec3 treeW = (modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
        float keep = smoothstep(uR - ${FADE.toFixed(1)}, uR, distance(treeW.xz, uCar.xz));
        if (part > 0.5) transformed = blobC + (transformed - blobC) * keep;
        #endif`);
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vPart; varying vec2 vUv0;\nuniform sampler2D uPalette; uniform vec3 uColA; uniform vec3 uColB;')
      .replace('#include <emissivemap_fragment>', /* glsl */ `#include <emissivemap_fragment>
        #if NUM_DIR_LIGHTS > 0
        float sunFacing = smoothstep(0.0, 1.0, dot(normal, directionalLights[0].direction));
        diffuseColor.rgb = vPart > 0.5 ? mix(uColA, uColB, sunFacing) : texture2D(uPalette, vUv0).rgb;
        #endif`);
  };
  return m;
}

/** Bruno's Foliage geometry: `count` cards in a unit sphere (denser at the centre), each with a normal bent 85% toward
 *  the sphere's outward direction. Cards are billboarded in the shader: attribute `card` = (card centre, rotation). */
function foliageGeometry(count: number) {
  let seed = 7;
  const rng = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const pos: number[] = [], uv: number[] = [], card: number[] = [], index: number[] = [];
  for (let i = 0; i < count; i++) {
    const r = 1 - Math.pow(rng(), 3), phi = Math.PI * 2 * rng(), theta = Math.PI * rng();
    const c = new THREE.Vector3().setFromSpherical(new THREE.Spherical(r, phi, theta));
    const rot = rng() * Math.PI * 2;
    const h = 0.4 * Math.sqrt(80 / count);   // Bruno: 80 cards of 0.8 m; fewer cards on phones -> larger cards, same cover
    const corners = [[-h, -h, 0, 0], [h, -h, 1, 0], [-h, h, 0, 1], [h, h, 1, 1]];
    for (const [x, y, u, v] of corners) {
      pos.push(x, y, 0);   // corner offset in the card's own plane (rotated + billboarded in the shader)
      uv.push(u, v);
      card.push(c.x, c.y, c.z, rot);
    }
    const b = i * 4;
    index.push(b, b + 1, b + 2, b + 2, b + 1, b + 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setAttribute('card', new THREE.Float32BufferAttribute(card, 4));
  g.setIndex(index);
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e6);
  return g;
}

const carScreen = { value: new THREE.Vector2(0.5, 0.5) };
const seeThrough = { value: new THREE.Vector2(0.11, 0.57) };
const aspect = { value: 1 };

function foliageMaterial(type: string, sdf: THREE.Texture) {
  const t = TREES[type];
  const m = new THREE.MeshLambertMaterial();
  m.defines = { TOON_SHADE_SCALE: '0.85' };   // leaf clusters: Bruno's core shade, a touch lighter so pines stay green
  m.customProgramCacheKey = () => `foliage-${type}`;
  m.onBeforeCompile = (s) => {
    Object.assign(s.uniforms, windUniforms, {
      uSDF: { value: sdf }, uColA: { value: new THREE.Color(t.a) }, uColB: { value: new THREE.Color(t.b) },
      uCar: carUniform, uR: radiusUniform, uCarScreen: carScreen, uSeeThrough: seeThrough, uAspect: aspect,
    });
    s.vertexShader = s.vertexShader
      .replace('#include <common>', `#include <common>\n${windGLSL}\nattribute vec4 card; uniform vec3 uCar; uniform float uR;\nvarying vec2 vCardUv; varying float vFade; varying float vWind; varying vec2 vScreen; varying float vCamNear; varying float vAO;`)
      .replace('#include <beginnormal_vertex>', 'vec3 objectNormal = vec3(0.0, 1.0, 0.0);')
      .replace('#include <defaultnormal_vertex>', '')
      .replace('#include <begin_vertex>', /* glsl */ `
        mat4 inst = modelMatrix * instanceMatrix;
        vec3 blobW = (inst * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
        float size = length(inst[0].xyz);
        vec3 cardW = blobW + card.xyz * size;
        // billboard: the card faces the camera, spun by its own random angle
        vec3 right = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
        vec3 up = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
        float cr = cos(card.w), sr = sin(card.w);
        vec2 off = vec2(position.x * cr - position.y * sr, position.x * sr + position.y * cr) * size;
        vec3 transformed = cardW + right * off.x + up * off.y;
        // Bruno: normal = corner direction blended 85% toward the sphere's outward direction
        vec3 nW = normalize(mix(normalize(right * off.x + up * off.y + card.xyz * size), normalize(card.xyz + 1e-4), 0.85));
        vec3 transformedNormal = normalize((viewMatrix * vec4(nW, 0.0)).xyz);
        vCardUv = uv;
        vWind = length(windOffset(cardW.xz)) * 2.2;
        vFade = 1.0 - smoothstep(uR - ${FADE.toFixed(1)}, uR, distance(blobW.xz, uCar.xz));
        vCamNear = 1.0 - smoothstep(5.0, 11.0, distance(cameraPosition, cardW));   // our chase camera is low: clear the lens
        // fake self-shadowing (Bruno gets this from real cast shadows): cards deep in the cluster are darker, plus a
        // little per-card variation
        vAO = mix(0.5, 1.05, length(card.xyz)) * (0.9 + 0.2 * fract(card.w * 7.31));`)
      .replace('#include <project_vertex>', 'vec4 mvPosition = viewMatrix * vec4(transformed, 1.0);\ngl_Position = projectionMatrix * mvPosition;\nvScreen = gl_Position.xy / gl_Position.w * 0.5 + 0.5;')
      .replace('#include <worldpos_vertex>', '');
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform sampler2D uSDF; uniform vec3 uColA; uniform vec3 uColB; uniform vec2 uCarScreen; uniform vec2 uSeeThrough; uniform float uAspect;\nvarying vec2 vCardUv; varying float vFade; varying float vWind; varying vec2 vScreen; varying float vCamNear; varying float vAO;')
      .replace('#include <alphatest_fragment>', /* glsl */ `
        // leaf shape, fluttering: the card's UV spins with the wind (Bruno: rotateUV(uv, |wind| x 2.2, 0.5))
        float cw = cos(vWind), sw = sin(vWind);
        vec2 q = vCardUv - 0.5;
        float sdf = texture2D(uSDF, vec2(q.x * cw - q.y * sw, q.x * sw + q.y * cw) + 0.5).r;
        // Bruno's see-through: cards near the car on screen keep only their dense core; fade in at the card radius
        float th = 0.3;
        float carFade = smoothstep(uSeeThrough.x, uSeeThrough.y, length((vScreen - uCarScreen) * vec2(uAspect, 1.0)));
        float alpha = sdf * (carFade * (1.0 - th) + th) - th;
        if (alpha < 0.1 + max(1.0 - vFade, vCamNear) * 0.9) discard;`)
      .replace('#include <emissivemap_fragment>', /* glsl */ `#include <emissivemap_fragment>
        #if NUM_DIR_LIGHTS > 0
        diffuseColor.rgb = mix(uColA, uColB, smoothstep(0.0, 1.0, dot(normal, directionalLights[0].direction))) * vAO;
        #endif`);
  };
  return m;
}

type Placements = Record<string, Record<string, number[]>>;

/** Card clusters for every tree / bush blob within the card radius of the car, one instanced draw per tree type.
 *  The set is rebuilt from the chunk placements every few metres of driving. */
export function TreeFoliage({ placements, stride }: { placements: Placements | null; stride: number }) {
  const { scene, camera, size } = useThree();
  const sdf = useLoader(THREE.TextureLoader, `${B}foliageSDF.png`);
  const geo = useMemo(() => foliageGeometry(FOLIAGE.cards), []);
  const mats = useMemo(() => Object.fromEntries(Object.keys(TREES).map((type) => [type, foliageMaterial(type, sdf)])), [sdf]);
  // one instanced mesh per tree type, regrown (x1.5) whenever the near set needs more blobs than it holds
  const meshes = useRef<Record<string, THREE.InstancedMesh>>({});
  const ensure = (type: string, need: number) => {
    const old = meshes.current[type];
    if (old && old.instanceMatrix.count >= need) return old;
    const im = new THREE.InstancedMesh(geo, mats[type], Math.max(256, Math.ceil(need * 1.5)));
    im.count = 0;
    im.frustumCulled = false;
    if (old) {
      scene.remove(old);
      old.dispose();
    }
    scene.add(im);
    meshes.current[type] = im;
    return im;
  };
  useEffect(() => {
    if (import.meta.env.DEV) Object.assign(window, { __foliage: meshes, __trees: TREES });   // debugging hook
  }, []);
  useEffect(() => () => {
    for (const m of Object.values(meshes.current)) {
      scene.remove(m);
      m.dispose();
    }
    meshes.current = {};
  }, [scene]);

  const last = useRef(new THREE.Vector2(1e9, 1e9));
  const tmp = useMemo(() => ({ m: new THREE.Matrix4(), q: new THREE.Quaternion(), p: new THREE.Vector3(), s: new THREE.Vector3(), v: new THREE.Vector3(), up: new THREE.Vector3(0, 1, 0) }), []);
  useFrame(() => {
    carUniform.value.set(telemetry.x, telemetry.y, telemetry.z);
    aspect.value = size.width / size.height;
    tmp.v.set(telemetry.x, telemetry.y + 1, telemetry.z).project(camera);
    carScreen.value.set(tmp.v.x * 0.5 + 0.5, tmp.v.y * 0.5 + 0.5);
    const dist = camera.position.distanceTo(tmp.v.set(telemetry.x, telemetry.y, telemetry.z));
    // Bruno uses 3 / 15 over the camera distance for his small car and far camera; ours is a 4.5 m jeep seen from
    // ~12 m, so the clear circle is sized from the car's on-screen radius (~2.9 / distance of the screen height)
    seeThrough.value.set(2.3 / dist, 6.5 / dist);
    if (!placements || Math.hypot(last.current.x - telemetry.x, last.current.y - telemetry.z) < 4) return;
    last.current.set(telemetry.x, telemetry.z);
    const r = FOLIAGE.r, r2 = r * r;
    // pass 1: the trees within the radius, per type
    const near: Record<string, number[]> = {};
    for (const [key, types] of Object.entries(placements)) {
      const [ci, cj] = key.split('_').map(Number);
      const cx = -1200 + (ci + 0.5) * 200, cz = -(-1200 + (cj + 0.5) * 200);
      if (Math.abs(cx - telemetry.x) > r + 150 || Math.abs(cz - telemetry.z) > r + 150) continue;
      for (const [type, arr] of Object.entries(types)) {
        if (!TREES[type]) continue;
        const list = (near[type] ??= []);
        for (let o = 0; o < arr.length; o += stride) {
          const dx = arr[o] - telemetry.x, dz = arr[o + 2] - telemetry.z;
          if (dx * dx + dz * dz <= r2) list.push(arr[o], arr[o + 1], arr[o + 2], arr[o + 3], arr[o + 4]);
        }
      }
    }
    // pass 2: one instance per blob
    const { m, q, p, s, up } = tmp;
    for (const type of Object.keys(TREES)) {
      const list = near[type] ?? [];
      const blobs = TREES[type].blobs;
      const im = ensure(type, (list.length / 5) * blobs.length);
      let n = 0;
      for (let o = 0; o < list.length; o += 5) {
        q.setFromAxisAngle(up, list[o + 3]);
        const sc = list[o + 4];
        for (const [bx, by, bz, bs] of blobs) {
          p.set(bx, by, bz).multiplyScalar(sc).applyQuaternion(q).add(s.set(list[o], list[o + 1], list[o + 2]));
          im.setMatrixAt(n++, m.compose(p, q, s.setScalar(bs * sc)));
        }
      }
      im.count = n;
      im.instanceMatrix.needsUpdate = true;
    }
  });
  return null;
}
