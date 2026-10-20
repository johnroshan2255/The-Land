// Shared tiling noise texture + wind, after Bruno Simon's folio-2025 Noises.js / Wind.js (MIT licence,
// github.com/brunosimon/folio-2025). His version renders a perlin texture on the GPU; here it is built once on the CPU
// (128 x 128, single channel, tiling). Wind = two scrolling noise lookups along a fixed direction, exactly his
// offsetNode, exposed as a GLSL function that every animated shader (grass, foliage, leaves) includes.
import * as THREE from 'three';

const N = 128;

/** Tiling gradient noise, 0..1 in the red channel, repeat-wrapped. */
function perlinTexture() {
  const cells = 8, rnd = (i: number, j: number) => {
    const s = Math.sin(((i % cells) + cells) % cells * 127.1 + (((j % cells) + cells) % cells) * 311.7) * 43758.5453;
    const a = (s - Math.floor(s)) * Math.PI * 2;
    return [Math.cos(a), Math.sin(a)];
  };
  const fade = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
  const data = new Uint8Array(N * N);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      let v = 0, amp = 1, tot = 0;
      for (let o = 0; o < 3; o++) {   // 3 octaves, each tiling at the texture edge
        const c = cells << o, fx = (x / N) * c, fy = (y / N) * c;
        const ix = Math.floor(fx), iy = Math.floor(fy), tx = fx - ix, ty = fy - iy;
        const g = (i: number, j: number) => {
          const [gx, gy] = rnd(((i % c) + c) % c + o * 17, ((j % c) + c) % c + o * 31);
          return gx * (fx - i) + gy * (fy - j);
        };
        const a = g(ix, iy) + (g(ix + 1, iy) - g(ix, iy)) * fade(tx);
        const b = g(ix, iy + 1) + (g(ix + 1, iy + 1) - g(ix, iy + 1)) * fade(tx);
        v += (a + (b - a) * fade(ty)) * amp;
        tot += amp;
        amp *= 0.5;
      }
      data[y * N + x] = Math.max(0, Math.min(255, (v / tot * 0.75 + 0.5) * 255));
    }
  }
  const t = new THREE.DataTexture(data, N, N, THREE.RedFormat, THREE.UnsignedByteType);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.magFilter = t.minFilter = THREE.LinearFilter;
  t.needsUpdate = true;
  return t;
}

export const noiseTexture = perlinTexture();

const ANGLE = Math.PI * 0.6;
/** Uniforms shared by every wind-animated material (one object, so updating it once updates them all). */
export const windUniforms = {
  uNoise: { value: noiseTexture },
  uWindDir: { value: new THREE.Vector2(Math.sin(ANGLE), Math.cos(ANGLE)) },
  uWindTime: { value: 0 },
  uWindStrength: { value: 0.5 },
};

/** GLSL: declarations + windOffset(worldXZ) -> vec2 (metres), Bruno's Wind.offsetNode. */
export const windGLSL = /* glsl */ `
uniform sampler2D uNoise; uniform vec2 uWindDir; uniform float uWindTime; uniform float uWindStrength;
vec2 windOffset(vec2 p) {
  vec2 q = p * 0.5;
  float n1 = texture2D(uNoise, q * 0.2 + uWindDir * uWindTime).r - 0.5;
  float n2 = texture2D(uNoise, q * 0.1 + uWindDir * uWindTime * 0.2).r - 0.5;
  return uWindDir * (n1 + n2) * uWindStrength;
}`;

/** Advance the wind clock (call once per frame). */
export function updateWind(dt: number) {
  windUniforms.uWindTime.value += dt * 0.1 * windUniforms.uWindStrength.value;
}
