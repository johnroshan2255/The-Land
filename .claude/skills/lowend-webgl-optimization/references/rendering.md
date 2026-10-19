# Rendering: CPU (draw calls) and GPU (pixels)

## Renderer setup

```js
const tier = quality.tier; // 'low' | 'medium' | 'high'
const renderer = new THREE.WebGLRenderer({
  antialias: tier === 'high',          // MSAA is expensive on weak GPUs
  powerPreference: 'high-performance', // picks the dGPU on dual-GPU laptops
  stencil: false,                      // not used → saves memory/bandwidth
  depth: true,
  alpha: false,
  precision: tier === 'low' ? 'mediump' : 'highp',
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, quality.maxPixelRatio));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping; // tone mapping adds ALU per pixel; low-poly vertex colors don't need it
```

Test `precision: 'mediump'` carefully. Large world coordinates (thousands of meters) can jitter in mediump vertex math. Keep the world near the origin (origin rebasing if needed) or use mediump only for fragments.

## Draw calls (CPU-bound on low-end)

Each draw call costs CPU in JS + driver. Budget 80–100 on low phones.

| Technique | When | Notes |
| --- | --- | --- |
| **Merge static geometry** | Same material, never moves, same chunk | `BufferGeometryUtils.mergeGeometries([...])` or do it in Blender (join per chunk). 1 draw per chunk. |
| **InstancedMesh** | Same geometry + material, many copies | Trees, rocks, fences, smoke puffs. One per chunk per type (see culling). |
| **InstancedMesh2** | As above + per-instance culling/LOD | `@three.ez/instanced-mesh` |
| **BatchedMesh** | Different geometries, same material | Per-object culling; benchmark multi-draw on Adreno |
| **Shared materials** | Always | Each unique material = program/state switch. Aim for 3–6 materials in the whole game. |
| **Texture atlas / palette** | If you use textures | One 256² palette texture instead of many materials (gltf-transform `palette`) |
| **Fewer objects** | Car | Body + 4 wheels = 5 draws; LOD1 merges the wheels into the body = 1 draw |

`renderer.info.render.calls` must be read **before** the next render (or set `renderer.info.autoReset = false` and reset manually).

## Materials and shaders

- Cost order (cheapest first): `MeshBasicMaterial` < `MeshLambertMaterial` < `MeshPhongMaterial` < `MeshStandardMaterial` < `MeshPhysicalMaterial`.
- This game's default: `MeshLambertMaterial({ vertexColors: true, flatShading: true })`. With `flatShading`, normals come from screen-space derivatives, so the **normal attribute can be dropped** from flat-shaded meshes (smaller files, less memory).
- Even cheaper: bake lighting/AO into vertex colors in Blender (Cycles → Bake → Target: Color Attributes) and use `MeshBasicMaterial({ vertexColors: true })` for distant terrain and the backdrop.
- Use `MeshStandardMaterial` only for the hero car if at all. Env maps (PMREM) cost a texture fetch and memory.
- `onBeforeCompile` / TSL custom shaders: keep fragment work minimal; move math to the vertex shader (MDN guidance); prefer built-ins (`mix`, `dot`).
- **Precompile**: `await renderer.compileAsync(scene, camera)` after loading, so programs don't compile mid-drive (huge hitch on Adreno). Keep the number of material variants small, because each define combination is a new program.
- Avoid `material.needsUpdate = true` at runtime (recompile).

## Lights and shadows

- Lights: 1 `HemisphereLight` + 1 `DirectionalLight`. Every extra light adds per-fragment cost to every lit material. Headlights = emissive meshes + an additive sprite/cone, not `SpotLight`.
- **Low tier**: no shadow maps. Use a **blob shadow** (a dark, soft circle texture on a quad under each car, raycast to the ground, `depthWrite: false`, `polygonOffset`). Terrain shadows are baked into vertex colors.
- **Medium tier**: one directional shadow, 1024², tight shadow camera that follows the car (`shadow.camera` ±30 m), only the car casts (`castShadow` on car only, `receiveShadow` on near chunks only).
- Static shadows: `renderer.shadowMap.autoUpdate = false`; set `renderer.shadowMap.needsUpdate = true` when something changes. Useful in menus/garage.
- `shadowMap.type = THREE.BasicShadowMap` or `PCFShadowMap`. Avoid `PCFSoftShadowMap` and `VSMShadowMap` on low end.

## Resolution and fill rate (GPU-bound)

- Fragment cost scales with pixels. A phone at DPR 3 renders 9× the pixels of DPR 1.
- **Cap DPR per tier**, then **adaptive resolution**: measure frame time, lower `setPixelRatio` in 0.1 steps when over budget, raise when well under (with cooldown). Implemented in `QualityManager.js`.
- MDN alternative: render to a smaller canvas size and let CSS upscale.
- Snap the canvas to whole device pixels (non-integer DPR on Windows scaling causes moiré). Use `ResizeObserver` with `device-pixel-content-box` where supported.

## Overdraw and transparency

- Transparent objects are drawn back-to-front with blending and no early-Z, so they're expensive on tile GPUs. Keep them few and small.
- Smoke puffs: **opaque**, flat-shaded icospheres that scale to 0 (the Gemini design) cost far less than alpha-blended sprites. Keep it that way.
- Foliage cards: `alphaTest: 0.5` (cutout) instead of `transparent: true`, but alphaTest disables early-Z on some mobile GPUs, so prefer solid low-poly tree meshes (the art style already does this).
- Don't stack full-screen UI overlays over the canvas with CSS `backdrop-filter`, because the compositor cost hits integrated GPUs.

## Post-processing

- Low tier: none. Each pass = a full-screen read + write. On tile GPUs, render-target switches force tile memory flushes.
- Medium: at most one combined pass (FXAA + color grade in one shader). Use `pmndrs/postprocessing`, which merges effects into one pass, rather than chaining `EffectComposer` passes.
- Bloom, SSAO, SSR, DOF: high tier only.

## Tile-based GPU notes (Adreno, Mali, Apple)

- Minimize render-target switches per frame (shadow map, post, minimap = each one costs a full tile load/store).
- **Minimap**: don't render a second 3D camera every frame. Pre-render a 2D map image from Blender and draw markers on a 2D canvas. If a 3D minimap is needed, render it at 128² every 4th frame.
- Clear every render target you use (`renderer.clear()`), so the GPU doesn't load old contents.
- Avoid `readPixels` and `getError()` in the frame loop (they're synchronous stalls).

## Water, sky, particles

- Ocean: a flat plane with vertex-colored shallow/deep bands, fogged. Animate with a tiny vertex shader (sin waves on vertex y) on medium+. No reflections/refraction on low/medium.
- Sky: `scene.background = color` or a gradient on a low-poly dome with `MeshBasicMaterial`, `fog: false`, `depthWrite: false`.
- Particles: pooled `InstancedMesh` (one draw); cap the count by tier; update matrices only for active instances and set `instancedMesh.count` to the active count, instead of hiding inactive ones at y = -9999.
