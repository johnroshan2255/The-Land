// Mutable per-frame state shared between the 3D scene and the HTML HUD (no React re-renders per frame).
import { PRESETS, tierFromRendererString, type Preset, type Tier } from './vendor/QualityManager';

export const DRACO = '/draco/';
export const HALF = 1200;          // island is 2400 x 2400 m centred on the origin
export const CHUNK = 200;          // terrain chunk size (12 x 12 chunks)

export const telemetry = {
  x: 450, y: 0, z: 330,   // car position (three.js world)
  fps: 0, drawCalls: 0, triangles: 0, dpr: 1,   // perf readout (written twice a second)
  heading: 0,             // map angle, radians clockwise from north
  speed: 0,               // m/s (signed, Rapier convention)
  timeOfDay: 15.5,        // hours 0..24 (start in warm afternoon light like the refs)
  timeScale: 1,           // T toggles fast time
};

/** Pick the quality tier before the renderer exists (the skill's renderer-string rules on a throwaway context). */
export function detectTier(): Tier {
  const isMobile = /android|iphone|ipad|mobile/i.test(navigator.userAgent);
  let forced: string | null = null;
  try {
    // ?tier=low|medium|high overrides; a stored tier is ignored so one slow session (or a throttled test tab) can't
    // pin a fast machine to a low preset forever. Adaptive resolution still adjusts within the session.
    forced = new URLSearchParams(location.search).get('tier');
  } catch { /* storage blocked */ }
  if (forced === 'low' || forced === 'medium' || forced === 'high') return forced;
  const gl = document.createElement('canvas').getContext('webgl2') ?? document.createElement('canvas').getContext('webgl');
  if (!gl) return 'low';
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  const name = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
  gl.getExtension('WEBGL_lose_context')?.loseContext();
  let tier = tierFromRendererString(name, isMobile);
  if (((navigator as { deviceMemory?: number }).deviceMemory ?? 8) <= 2) tier = 'low';
  return tier;
}

export const TIER: Tier = detectTier();
export const PRESET: Preset = PRESETS[TIER];

if (import.meta.env.DEV) Object.assign(window, { __tele: telemetry });   // debugging hook
