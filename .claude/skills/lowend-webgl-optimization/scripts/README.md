# LOD and optimization tools

| File | What | Run |
| --- | --- | --- |
| `blender_generate_lods.py` | LOD1/LOD2/`_col` via Decimate + per-level .glb export | Blender MCP, Text Editor, or `blender -b scene.blend -P blender_generate_lods.py -- --all --out <dir>` |
| `make-lods.mjs` | glTF-Transform + meshoptimizer LOD files, collision proxy, quantize, meshopt | `npm install` once here, then `node make-lods.mjs <file.glb or folder> --out <dir> [--ratios 1,0.4,0.12] [--error 0.01] [--col 0.05] [--keep-normals] [--no-compress]` |
| `make-lods.ps1` | Same with gltfpack (`-si` + `-sa`), batch over a folder | `./make-lods.ps1 -In <folder or file> -Out <dir> [-Ratios 0.4,0.12] [-KeepNames] [-KeepTopology]` |
| `runtime/QualityManager.js` | Tier detection, presets, adaptive pixel ratio, 30 fps cap | import into the game |
| `runtime/lod-utils.js` | `loadLOD`, `simplifyGeometry`, `buildLOD`, `DistanceCuller` | import into the game (`npm i meshoptimizer`) |
| `runtime/ChunkPVS.js` | Bake + apply chunk visibility (occlusion culling) | bake in a dev page, ship the JSON |

Tested (2026-10-19) on a 3,072-triangle flat-shaded, vertex-colored sphere:

- `make-lods.mjs` → lod0 3,072 / lod1 1,227 / lod2 550 tris, col 154 tris (13.7 / 6.9 / 4.1 KB)
- `make-lods.ps1` → lod0 3,024 / lod1 1,120 / lod2 604 tris (needs `-sa`; without it, flat-shaded split normals block simplification)

- `blender_generate_lods.py` (Blender 5.2, headless) → 1,280-tri flat icosphere: lod1 448 / lod2 152 / col 46 tris, 4 .glb files exported

Loading the output in three.js:

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
// Normals were dropped: use flat-shaded materials
const material = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
```
