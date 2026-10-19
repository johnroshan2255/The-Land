// Vendored from .claude/skills/lowend-webgl-optimization/scripts/runtime/QualityManager.js
// (project tweak: medium/high fogFar 600/900 so the 2.4 km island reads as a vista).
// Device tier detection, quality presets and adaptive pixel ratio for low-end WebGL.
//
//   const quality = await QualityManager.create(renderer);
//   renderer.setAnimationLoop((t) => { quality.update(t); ... });
//   quality.onChange = (preset) => applyPreset(preset);
//
// Optional: `npm i @pmndrs/detect-gpu` for benchmark-based tiers (falls back to renderer-string rules).

export const PRESETS = {
  low: {
    tier: 'low', targetFps: 30, minPixelRatio: 0.6, maxPixelRatio: 1.0, antialias: false,
    shadows: 'blob', shadowMapSize: 0, chunkRadius: 1, fogFar: 350, treeDistance: 200,
    propDistance: 80, smokePuffs: 20, bots: 3, carLodDistances: [0, 40, 150], lodScale: 0.6,
  },
  medium: {
    tier: 'medium', targetFps: 60, minPixelRatio: 0.85, maxPixelRatio: 1.25, antialias: false,
    shadows: 'directional', shadowMapSize: 1024, chunkRadius: 1, fogFar: 600, treeDistance: 300,
    propDistance: 120, smokePuffs: 40, bots: 6, carLodDistances: [0, 80, 300], lodScale: 1,
  },
  high: {
    tier: 'high', targetFps: 60, minPixelRatio: 1.0, maxPixelRatio: 2.0, antialias: true,
    shadows: 'directional', shadowMapSize: 2048, chunkRadius: 2, fogFar: 900, treeDistance: 450,
    propDistance: 200, smokePuffs: 60, bots: 10, carLodDistances: [0, 120, 400], lodScale: 1.4,
  },
};

const ORDER = ['low', 'medium', 'high'];
const STORAGE_KEY = 'quality.tier';

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode / blocked storage */ }
}

export function getRendererString(renderer) {
  const gl = renderer.getContext();
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
}

// Rules for when detect-gpu is missing or has no benchmark for this GPU.
export function tierFromRendererString(name, isMobile) {
  const adreno = /adreno\D*(\d{3})/i.exec(name);
  if (adreno) {
    const n = Number(adreno[1]);
    if (n < 615) return 'low';          // 5xx, 610, 612
    if (n < 700) return n >= 640 ? 'high' : 'medium';
    return n >= 730 ? 'high' : 'medium';
  }
  const mali = /mali-g(\d+)/i.exec(name);
  if (mali) return Number(mali[1]) >= 710 ? 'medium' : 'low';
  if (/intel.*(hd|uhd) graphics/i.test(name)) return 'low';
  if (/intel.*(iris|xe)|radeon.*(vega|graphics)/i.test(name)) return 'medium';
  if (/apple|nvidia|geforce|rtx|radeon rx|arc/i.test(name)) return 'high';
  return isMobile ? 'low' : 'medium';
}

export class QualityManager {
  static async create(renderer, { forceTier = null } = {}) {
    const isMobile = /android|iphone|ipad|mobile/i.test(navigator.userAgent);
    const rendererName = getRendererString(renderer);
    let tier = forceTier || storageGet(STORAGE_KEY);

    if (!tier) {
      tier = tierFromRendererString(rendererName, isMobile);
      try {
        const detectGpu = '@pmndrs/detect-gpu';   // optional dependency: resolved at runtime, skipped by the bundler
        const { getGPUTier } = await import(/* @vite-ignore */ detectGpu);
        const result = await getGPUTier();
        if (result.type === 'BENCHMARK') tier = ['low', 'low', 'medium', 'high'][result.tier];
      } catch { /* package not installed or offline: keep rule-based tier */ }
      if ((navigator.deviceMemory ?? 8) <= 2) tier = 'low';
    }
    return new QualityManager(renderer, tier, { isMobile, rendererName });
  }

  constructor(renderer, tier, info = {}) {
    this.renderer = renderer;
    this.info = info;
    this.onChange = null;
    this._frameTimes = new Float32Array(90);
    this._frameIndex = 0;
    this._frameCount = 0;
    this._lastTime = 0;
    this._lastAdjust = 0;
    this._lastRendered = 0;
    this._overBudgetSeconds = 0;
    this.setTier(tier);
  }

  setTier(tier) {
    this.preset = PRESETS[tier] ?? PRESETS.medium;
    this.pixelRatio = Math.min(window.devicePixelRatio || 1, this.preset.maxPixelRatio);
    this.renderer.setPixelRatio(this.pixelRatio);
    this.frameBudgetMs = 1000 / this.preset.targetFps;
    this.onChange?.(this.preset);
  }

  // True when this rAF should be skipped to hold the 30 fps cap on the low tier.
  shouldSkipFrame(now) {
    if (this.preset.targetFps >= 60) return false;
    if (now - this._lastRendered < this.frameBudgetMs - 2) return true;
    this._lastRendered = now;
    return false;
  }

  // Call once per rendered frame with the rAF timestamp.
  update(now) {
    if (this._lastTime) {
      this._frameTimes[this._frameIndex] = now - this._lastTime;
      this._frameIndex = (this._frameIndex + 1) % this._frameTimes.length;
      this._frameCount = Math.min(this._frameCount + 1, this._frameTimes.length);
    }
    this._lastTime = now;
    if (this._frameCount < this._frameTimes.length || now - this._lastAdjust < 1000) return;
    this._lastAdjust = now;

    const avg = this._average();
    const budget = this.frameBudgetMs;
    if (avg > budget * 1.15) {
      this._setPixelRatio(this.pixelRatio - 0.1);
      this._overBudgetSeconds++;
      // Still over budget at minimum resolution for 5 s: drop a tier and remember it.
      if (this.pixelRatio <= this.preset.minPixelRatio && this._overBudgetSeconds >= 5) {
        const lower = ORDER[Math.max(0, ORDER.indexOf(this.preset.tier) - 1)];
        if (lower !== this.preset.tier) {
          storageSet(STORAGE_KEY, lower);
          this.setTier(lower);
        }
        this._overBudgetSeconds = 0;
      }
    } else {
      this._overBudgetSeconds = 0;
      if (avg < budget * 0.7) this._setPixelRatio(this.pixelRatio + 0.05);
    }
  }

  _average() {
    let sum = 0;
    for (let i = 0; i < this._frameTimes.length; i++) sum += this._frameTimes[i];
    return sum / this._frameTimes.length;
  }

  _setPixelRatio(value) {
    const max = Math.min(window.devicePixelRatio || 1, this.preset.maxPixelRatio);
    const next = Math.round(Math.min(max, Math.max(this.preset.minPixelRatio, value)) * 100) / 100;
    if (next === this.pixelRatio) return;
    this.pixelRatio = next;
    this.renderer.setPixelRatio(next);
    // Discard measurements taken at the old resolution
    this._frameCount = 0;
  }
}
