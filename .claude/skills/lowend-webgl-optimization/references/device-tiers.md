# Device tiers

## What "low-end" means here

GPU names below are from memory of public spec sheets and are approximate. Always confirm on the device (`chrome://gpu`, or the `WEBGL_debug_renderer_info` string).

| SoC (Snapdragon 6xx) | GPU | Rough class |
| --- | --- | --- |
| 625 / 626 | Adreno 506 | Weakest target. WebGL2 OK, very little fill rate |
| 630 | Adreno 508 | Weakest target |
| 636 | Adreno 509 | Low |
| 660 | Adreno 512 | Low |
| 662 / 665 / 680 / 685 | Adreno 610 | Low |
| 675 / 678 | Adreno 612 | Low–mid |
| 690 / 695 | Adreno 619L / 619 | Mid |
| 6 Gen 1 | Adreno 710 | Mid |

| Laptop integrated GPU | Rough class |
| --- | --- |
| Intel HD 520/620, UHD 620 | Low (desktop-class features, weak fill rate) |
| Intel Iris Plus / Iris Xe (80–96 EU) | Mid |
| AMD Radeon Vega 6/8 (Ryzen 3000–5000 U) | Mid |
| AMD 680M/780M, Intel Arc iGPU | High |

**Common traits of the weak end**: low fill rate and memory bandwidth (so pixels matter more than triangles), tile-based rendering on Adreno (full-screen passes and render-target switches are expensive), thermal throttling after 2–5 minutes, 2–4 GB RAM shared with the OS, weak single-core JS speed (draw-call and physics cost hits hard).

**Laptop-specific**: on dual-GPU laptops, `powerPreference: 'high-performance'` asks for the discrete GPU. On battery, Windows may still pick the iGPU. Browser zoom/Windows scaling of 125–150% silently raises `devicePixelRatio`.

## API baseline

- **WebGL2** is the baseline: supported on every GPU above. Don't depend on WebGPU for this audience; treat it as an optional upgrade path.
- Check extensions before use: `EXT_color_buffer_float`, `EXT_disjoint_timer_query_webgl2` (usually missing on Android/Chrome), `WEBGL_compressed_texture_etc` / `_astc` (Android), `_s3tc` (desktop).
- Never assume limits above the guaranteed minimums (`MAX_TEXTURE_SIZE` 4096 is safe).

## Tier detection

Use two signals, then correct at runtime with measured frame time:

1. **`@pmndrs/detect-gpu`**: `const { tier, isMobile, gpu } = await getGPUTier()`. Tier 0 = blocklisted/<15 fps, 1 = ≥15, 2 = ≥30, 3 = ≥60. Self-host the benchmarks (`benchmarksURL: '/benchmarks'`) to avoid a CDN dependency. Upstream data stopped updating in Dec 2025, so new GPUs may fall back.
2. **Renderer string** via `WEBGL_debug_renderer_info` → regex for `Adreno \(TM\) (\d+)`, `Mali-G(\d+)`, `Intel.*(UHD|HD|Iris)`.
3. **Runtime correction**: after 3–5 s of play, if the 95th-percentile frame time is over budget, drop a tier (and remember it in `localStorage`).

`scripts/runtime/QualityManager.js` implements all three.

## Quality presets

| Setting | low | medium | high |
| --- | --- | --- | --- |
| Pixel ratio (min–max, adaptive) | 0.6–1.0 | 0.85–1.25 | 1.0–2.0 |
| Antialias | off | off (FXAA optional) | MSAA on |
| Target fps | 30 | 60 | 60 |
| Shadows | blob quads | 1 directional, 1024², car only | 2048², car + props |
| Chunk grid loaded | 3×3 | 3×3 | 5×5 |
| Fog/camera far | 350 m | 450 m | 650 m |
| Tree draw distance | 200 m | 300 m | 450 m |
| Small prop distance | 80 m | 120 m | 200 m |
| Smoke puffs max | 20 | 40 | 60 |
| Bots | 3 | 6 | 10 |
| Car LOD distances | 40 / 150 m | 80 / 300 m | 120 / 400 m |
| Water | flat color plane | flat + vertex wave | shader waves |
