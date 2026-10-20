// Ground color lookup from the pre-rendered map image (top-down, north up, 2400 m square), so effects like wheel dust
// can match the surface without any extra GPU work: decoded once into a CPU array.
import * as THREE from 'three';
import { HALF } from './state';

let pixels: Uint8ClampedArray | null = null;
let size = 0;

const img = new Image();
img.src = '/models/terrain/map.png';
img.decode().then(() => {
  const cv = document.createElement('canvas');
  cv.width = cv.height = size = 256;   // 9.4 m per pixel is plenty for dust tinting
  const ctx = cv.getContext('2d', { willReadFrequently: true })!;
  ctx.drawImage(img, 0, 0, size, size);
  pixels = ctx.getImageData(0, 0, size, size).data;
}).catch(() => {});

/** Writes the ground color at world (x, z) into `out`; returns false while the map isn't loaded yet. */
export function groundColorAt(x: number, z: number, out: THREE.Color) {
  if (!pixels) return false;
  const u = Math.min(size - 1, Math.max(0, Math.floor(((x + HALF) / (2 * HALF)) * size)));
  const v = Math.min(size - 1, Math.max(0, Math.floor(((z + HALF) / (2 * HALF)) * size)));   // map top = north = -z
  const i = (v * size + u) * 4;
  out.setRGB(pixels[i] / 255, pixels[i + 1] / 255, pixels[i + 2] / 255, THREE.SRGBColorSpace);
  return true;
}

/** Frozen lake / ponds read as pale cyan on the map. */
export function isIce(c: THREE.Color) {
  return c.b > 0.6 && c.g > 0.6 && c.r < c.g * 0.85;
}

/** Grass reads as green-dominant on the map. */
export function isGrass(c: THREE.Color) {
  return c.g > c.r * 1.08 && c.g > c.b * 1.15;
}

/** Paved road reads as a darkish, unsaturated grey (snow is unsaturated too, but bright). */
export function isAsphalt(c: THREE.Color) {
  const max = Math.max(c.r, c.g, c.b);
  return max - Math.min(c.r, c.g, c.b) < 0.07 && max < 0.55;
}
