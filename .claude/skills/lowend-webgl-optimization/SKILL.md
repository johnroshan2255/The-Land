---
name: lowend-webgl-optimization
description: Optimization playbook and LOD tools for Three.js/WebGL games that must run on low-end hardware — Snapdragon 600-series phones (Adreno 5xx/6xx) and laptops with integrated graphics (Intel UHD/Iris Xe, AMD Vega). Use when building, profiling or reviewing rendering, culling (frustum, distance, occlusion, chunk/PVS), LODs, draw calls, instancing, .glb asset pipelines (Blender, gltfpack, gltf-transform, meshopt, KTX2), shaders, shadows, resolution scaling, memory, streaming or Rapier physics cost; or when asked to generate LODs or collision meshes for models.
---

# Low-end WebGL optimization

Target: a stable **30 fps on Snapdragon 6xx phones** and **60 fps on integrated-GPU laptops**, in a browser, with Three.js + Rapier3D. The project's art style (flat-shaded, vertex-colored, low-poly, chunked 6 km² world) is already the cheapest possible style — protect that.

## How to use this skill

1. **Measure first** (`references/profiling.md`). Know whether you are CPU-bound (draw calls, JS, physics) or GPU-bound (pixels, overdraw, shaders, bandwidth). Change one thing, re-measure.
2. Check the budgets below. Over budget → open the reference for that area.
3. For any new model, run the LOD tools (`references/lod.md`, `scripts/`).

| Reference | Covers |
| --- | --- |
| `references/device-tiers.md` | Which GPUs "low-end" means, tier detection, quality presets |
| `references/culling.md` | Frustum, distance, chunk, occlusion (PVS, horizon, queries), BVH, instance culling |
| `references/rendering.md` | Draw calls, instancing, batching, materials, shaders/precision, lights, shadows, post, resolution, overdraw, tile GPUs |
| `references/assets.md` | Blender modeling rules, glTF pipeline, compression, quantization, textures |
| `references/lod.md` | LOD strategy, every LOD tool, how to run the scripts in `scripts/` |
| `references/runtime.md` | JS/GC, memory & disposal, chunk streaming, Rapier physics, loading, thermal/battery, context loss |
| `references/profiling.md` | Tools and how to profile on a real phone |

## Budgets (starting points — tune on real devices)

| Metric | Low phone (Adreno 506–610) | Mid phone / iGPU laptop | Notes |
| --- | --- | --- | --- |
| Target fps | 30 (locked) | 60 | Lock low tier to 30 to avoid thermal throttling |
| Draw calls / frame | ≤ 80–100 | ≤ 200–300 | `renderer.info.render.calls` |
| Visible triangles | ≤ 100–150k | ≤ 300–500k | `renderer.info.render.triangles` |
| Pixel ratio | 0.75–1.0 | 1.0–1.5 | Never raw `devicePixelRatio` (often 2.5–3 on phones) |
| GPU memory (textures + buffers) | ≤ 150 MB | ≤ 300 MB | Vertex colors keep this tiny |
| JS per frame (logic + physics) | ≤ 6–8 ms | ≤ 4–6 ms | Performance panel |
| Shadow maps | none (blob shadow) | 1 × 1024² directional | |
| Post-processing | none | FXAA or nothing | Every full-screen pass costs bandwidth |
| Lights | 1 hemi + 1 directional | same | No dynamic point/spot lights |
| Download per chunk | ≤ 100 KB | same | meshopt-compressed .glb |

## Top 20 wins for this project (in rough order of payoff)

1. Cap pixel ratio by tier and add adaptive resolution (`scripts/runtime/QualityManager.js`).
2. `antialias: false` on low tier; no post-processing.
3. Stream a 3×3 chunk grid; never keep 144 chunks in the scene (`references/runtime.md`).
4. `scene.fog` + `camera.far` = fog end → everything beyond is culled for free.
5. One `InstancedMesh` **per chunk per prop type** so frustum culling works per chunk (a single world-wide InstancedMesh is never culled).
6. Repeated props (trees, rocks, fences) → `InstancedMesh` or `InstancedMesh2` with per-instance culling + LOD.
7. Merge each chunk's static, same-material geometry into one mesh → 1 draw call per chunk.
8. One shared `MeshLambertMaterial({ vertexColors: true, flatShading: true })` for almost everything; no textures.
9. Car LOD 0/1/2 with `THREE.LOD` + hysteresis; remote cars use LOD 1 by default.
10. Blob shadow quad under cars instead of shadow maps on low tier; bake terrain AO/shadows into vertex colors in Blender.
11. Static objects: `matrixAutoUpdate = false` + `updateMatrix()` once.
12. Precompile shaders at load (`renderer.compileAsync(scene, camera)`) to avoid first-sight hitches.
13. meshopt-compress + quantize every .glb (gltfpack `-cc` / gltf-transform `optimize`); `GLTFLoader.setMeshoptDecoder`.
14. Rapier: terrain chunks as **fixed** trimesh colliders added/removed with the chunk; props as cuboids/convex hulls; let bodies sleep; CCD only on the player car.
15. Fixed physics step (1/60) with an accumulator and a max of 2–3 substeps per frame.
16. Zero allocations in the frame loop (reuse vectors, pool particles).
17. Dispose geometry/material/texture of unloaded chunks; watch `renderer.info.memory`.
18. Distance-cull small props per layer (rocks at 120 m, trees at 350 m) — cheaper than LOD.
19. Precomputed chunk visibility (PVS) for hills/cliffs — the only occlusion culling that is cheap on WebGL (`references/culling.md`).
20. Pause rendering when `document.hidden`; drop to 30 fps when idle in menus.

## Tools in this skill

| Tool | Run | Does |
| --- | --- | --- |
| `scripts/blender_generate_lods.py` | Blender MCP / Text Editor / `blender -b file.blend -P` | LOD1/LOD2/collision via Decimate for selected objects, exports .glb per level |
| `scripts/make-lods.mjs` | `node make-lods.mjs in.glb --out dir` | glTF-Transform + meshoptimizer: LOD0/1/2 + `_col`, weld, simplify, quantize, meshopt |
| `scripts/make-lods.ps1` | `./make-lods.ps1 -In assets/props` | Same with the gltfpack CLI, batch over a folder |
| `scripts/runtime/QualityManager.js` | import in game | Tier detection + quality presets + adaptive pixel ratio |
| `scripts/runtime/lod-utils.js` | import in game | Build `THREE.LOD` from LOD files; runtime meshopt simplify; distance culling |
| `scripts/runtime/ChunkPVS.js` | import in game + bake step | Chunk-level potentially-visible-set occlusion culling |

Setup for the Node tools: see `scripts/README.md`. All three LOD tools were tested on 2026-10-19 (Blender 5.2, gltf-transform 4.5.1, meshoptimizer 0.22).

## Sources (checked 2026-10-19)

- [MDN: WebGL best practices](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices)
- [Qualcomm: Adreno GPU mobile best practices](https://docs.qualcomm.com/bundle/publicresource/80-78185-2/topics/mobile_best_practices.md)
- [gltfpack README](https://github.com/zeux/meshoptimizer/blob/master/gltf/README.md) · [glTF-Transform CLI](https://gltf-transform.dev/cli)
- [Rapier JS: rigid bodies (sleeping, CCD)](https://rapier.rs/docs/user_guides/javascript/rigid_bodies)
- [InstancedMesh2 (@three.ez/instanced-mesh)](https://github.com/agargaro/instanced-mesh) · [batched-mesh-extensions](https://github.com/agargaro/batched-mesh-extensions/) · [three.js BatchedMesh LOD+BVH example](https://threejs.org/examples/webgl_batch_lod_bvh.html)
- [detect-gpu](https://github.com/pmndrs/detect-gpu)
- three.js forum: [occlusion culling](https://discourse.threejs.org/t/in-three-js-have-occlusion-culling/15076), [isOccluded on WebGPU](https://discourse.threejs.org/t/renderer-isoccluded-returns-null-is-my-setup-correct/88356), [meshoptimizer simplification](https://discourse.threejs.org/t/mesh-simplification-using-meshoptimizer/63002), [BatchedMesh LOD](https://discourse.threejs.org/t/batchedmesh-lod/82449)
- [webglfundamentals: shader precision](https://webglfundamentals.org/webgl/lessons/webgl-qna-when-to-choose-highp--mediump--lowp-in-shaders.html)
