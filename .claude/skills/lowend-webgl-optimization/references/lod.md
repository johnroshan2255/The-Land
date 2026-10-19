# LOD: levels of detail

## Strategy for this game

| Asset | LOD approach | Distances (medium tier) |
| --- | --- | --- |
| Terrain chunks | **No per-chunk LOD**. 3×3 detailed chunks + one decimated `world_backdrop_lod.glb` under fog | Backdrop always on |
| Car (player, bots, remote) | `THREE.LOD`: LOD0 ~2,500 tris → LOD1 ~300 (wheels merged) → LOD2 box/billboard | 0 / 80 / 300 m |
| Trees, rocks, cacti | `InstancedMesh2.addLOD` per chunk, or distance culling only | LOD1 at 60 m, hidden at 200–350 m |
| Ramps, bridges | LOD0 + LOD1 (≈30%) | 120 m |
| Small props (cones, umbrellas, tents) | Distance cull only, no LOD | 80–120 m |

**Rules of thumb**

- Each LOD level should drop **≥ 50% of triangles**, or it isn't worth the memory and the switch.
- Pick switch distances where the triangles of the next level would be smaller than ~4–8 px on screen.
- Use **hysteresis** to avoid flicker at the boundary: `lod.addLevel(mesh, distance, hysteresis)` (e.g. 0.1 = 10%).
- For flat-shaded low-poly, popping is mostly invisible past 80 m under fog. Don't bother with cross-fading.
- Scale LOD distances by tier (and by FOV/resolution): `lod.levels.forEach(l => l.distance *= quality.lodScale)`.
- `THREE.LOD.autoUpdate` runs per frame per LOD object. For hundreds of LODs, use `InstancedMesh2` (one object) or update LODs manually every few frames.

## Tools

| Tool | Where | Strengths | Use for |
| --- | --- | --- | --- |
| **Blender Decimate modifier** | Blender | Visual control; Collapse / Un-Subdivide / Planar modes; works with Blender MCP | Hero assets, collision proxies, backdrop |
| **`scripts/blender_generate_lods.py`** | Blender (MCP, Text Editor, `blender -b -P`) | Batch LOD1/LOD2/`_col` for selected objects + per-level .glb export | All props and the car |
| **gltfpack `-si R`** | CLI | Fastest; meshoptimizer; plus compression in the same step | Batch LOD files from a folder |
| **glTF-Transform `simplify`** | CLI / Node API | Error-bounded (`--ratio`, `--error`, `--lock-border`); scriptable | Pipeline: `scripts/make-lods.mjs` |
| **meshoptimizer (JS/WASM) `MeshoptSimplifier`** | Runtime / Node | Simplify in the browser; generate LODs on load | Procedural meshes, runtime fallback (`lod-utils.js`) |
| **three.js `SimplifyModifier`** | Runtime | No dependency; slow, lower quality | Quick experiments only |
| **`@three.ez/instanced-mesh` (`InstancedMesh2`)** | Runtime | Per-instance LOD + culling + shadow LOD in one draw call | Trees/rocks |
| **`@three.ez/batched-mesh-extensions`** | Runtime | LOD + BVH for BatchedMesh | Many different props |
| Simplygon / InstaLOD | Commercial | Best quality, impostors, remeshing | Optional, not needed for low-poly |
| **Impostors (billboards)** | Blender render → texture | Replace far trees with 1–2 quads | Forest beyond 200 m on high tier |

## Running the tools

### 1. Blender (via Blender MCP or Text Editor)

Select objects → run `scripts/blender_generate_lods.py`. Defaults: LOD1 = 0.35 ratio, LOD2 = 0.12, COL = planar + 0.05 collapse. It creates `<name>_lod1`, `<name>_lod2`, `<name>_col` objects in a `LODs` collection and exports `<name>_lod0.glb`, `_lod1.glb`, `_lod2.glb`, `_col.glb` to the folder in `EXPORT_DIR`. Edit the `CONFIG` block at the top.

Through Blender MCP, ask Claude: *"Run the script at .claude/skills/lowend-webgl-optimization/scripts/blender_generate_lods.py on the selected objects with EXPORT_DIR = <project>/public/assets/props"*. Or headless: `blender -b scene.blend -P blender_generate_lods.py -- --all`.

### 2. Node pipeline (glTF-Transform + meshoptimizer)

```
cd .claude/skills/lowend-webgl-optimization/scripts
npm install
node make-lods.mjs ../../../../public/assets/props/tree_pine.glb --out ../../../../public/assets/props/lod
node make-lods.mjs ../../../../public/assets/props --out ../../../../public/assets/props/lod --ratios 1,0.4,0.12 --col 0.05
```

Outputs `name_lod0.glb … name_lodN.glb` (+ `name_col.glb` when `--col` is given), meshopt-compressed and quantized, and prints triangle counts per level. `--keep-normals` keeps normals (otherwise they're dropped for flat shading).

### 3. gltfpack batch (PowerShell)

```
./make-lods.ps1 -In public/assets/props -Out public/assets/props/lod -Ratios 0.4,0.12
```

It adds `-sa` (aggressive, ignores topology) by default. Without it, gltfpack can't simplify flat-shaded meshes at all (tested: all levels stayed at 3,024 tris). Pass `-KeepTopology` for smooth-shaded models where borders must hold.

### 4. Runtime

```js
import { loadLOD, simplifyGeometry } from './lod-utils.js';
const car = await loadLOD(loader, ['car_lod0.glb', 'car_lod1.glb', 'car_lod2.glb'], [0, 80, 300], { hysteresis: 0.1 });
scene.add(car);
const low = await simplifyGeometry(mesh.geometry, 0.25, 0.02); // meshopt in the browser
```

## Flat-shaded vertex-color caveat

Flat shading splits every vertex per face (different normals), and vertex-color seams split more. Simplifiers can't collapse split vertices, so simplification stalls. The fix, already in `make-lods.mjs` and the Blender script order: **drop normals → weld → simplify**, and let three.js `flatShading` recompute facets. If color borders get smeared, lower the ratio or raise `--error`.
