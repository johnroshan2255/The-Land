export type Tier = 'low' | 'medium' | 'high';
export interface Preset {
  tier: Tier; targetFps: number; minPixelRatio: number; maxPixelRatio: number; antialias: boolean;
  shadowTexSize: number; propDensity: number; chunkRadius: number; fogFar: number; treeDistance: number;
  propDistance: number; smokePuffs: number; bots: number; carLodDistances: number[]; lodScale: number;
}
export const PRESETS: Record<Tier, Preset>;
export function tierFromRendererString(name: string, isMobile: boolean): Tier;
export interface RendererLike { getContext(): WebGLRenderingContext | WebGL2RenderingContext; setPixelRatio(v: number): void }
export class QualityManager {
  static create(renderer: RendererLike, opts?: { forceTier?: Tier | null }): Promise<QualityManager>;
  constructor(renderer: RendererLike, tier: Tier, info?: object);
  preset: Preset;
  pixelRatio: number;
  onChange: ((p: Preset) => void) | null;
  setTier(tier: Tier): void;
  shouldSkipFrame(now: number): boolean;
  update(now: number): void;
}
