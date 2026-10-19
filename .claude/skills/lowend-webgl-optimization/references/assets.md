# Assets: Blender → .glb pipeline for low-end

## Modeling rules (Blender)

- **Triangle budgets**: car LOD0 ≤ 2,500, LOD1 ≤ 300; terrain chunk 1,500–3,000; tree ≤ 150–300; rock ≤ 40–80; ramp ≤ 300; bridge ≤ 800.
- Fewest segments that read at gameplay distance: wheels 8–12 sides, trees 5–7 sided cones.
- **No hidden faces**: delete bottoms of props sitting on the ground and faces inside other meshes.
- **Vertex colors, not textures**: Color Attribute (byte color, face corner) → Principled BSDF Base Color. Zero texture memory, no UVs needed.
- **Bake lighting/AO into vertex colors** (Cycles → Bake → Ambient Occlusion or Diffuse → Output: Active Color Attribute). Then you can use cheaper materials and skip shadow maps.
- **Origins**: props at their base center (so scale/rotation in `props.json` behaves). Wheels at the axle center. Chunks at a consistent corner/center.
- **Apply transforms** (Ctrl+A → All Transforms) before export. Scale 1 = 1 m.
- **One material per chunk/prop** where possible; join objects that share material and never move separately.
- **Names**: `_col` suffix for collision proxies, `_lod1`/`_lod2` for LODs. gltfpack/gltf-transform must be told to keep names (`-kn`, `--join-named false`) or they merge them.

## Export (Blender glTF 2.0)

- Format **glTF Binary (.glb)**. Include: Selected Objects, Custom Properties (for tags), no cameras/lights.
- Mesh: Apply Modifiers ✓, UVs off if unused, **Normals off for flat-shaded vertex-color meshes** (three.js `flatShading` derives them), Vertex Colors ✓, Tangents off.
- Compression: you can enable Draco in Blender, but prefer exporting uncompressed and running gltfpack/gltf-transform (meshopt) as a separate step, so all assets are processed uniformly.

## Post-processing the .glb (pick one tool per pipeline)

### gltfpack (meshoptimizer CLI, fastest)

```
gltfpack -i in.glb -o out.glb -cc            # meshopt compression + quantization (default) + extra compression
gltfpack -i in.glb -o out.glb -cc -si 0.5    # + simplify to 50% triangles
gltfpack -i in.glb -o out.glb -cc -kn -km    # keep named nodes and materials (collision, wheels)
gltfpack -i in.glb -o out.glb -cc -mi        # repeated meshes → EXT_mesh_gpu_instancing
gltfpack -i in.glb -o out.glb -cc -tc        # textures → KTX2 (Basis)
```

Run `gltfpack -h` for every flag. Install: `npm i -g gltfpack`, or a binary from the meshoptimizer GitHub releases.

### glTF-Transform CLI (`@gltf-transform/cli`, v4.x)

```
gltf-transform optimize in.glb out.glb --compress meshopt --texture-compress ktx2 \
  --simplify false --join-named false --palette false
gltf-transform simplify in.glb out.glb --ratio 0.5 --error 0.001
gltf-transform weld in.glb out.glb
gltf-transform inspect out.glb        # vertex/triangle/size report
```

- `optimize` defaults: `--compress meshopt`, `--simplify true` (error 0.0001), `--join true`, `--instance true`, `--palette true`, `--texture-size 2048`, `--flatten true`.
- Set `--join-named false` so `_col`, wheel and chunk names survive. Set `--palette false` for vertex-colored models (otherwise it may create a palette texture).

### Draco vs meshopt

| | meshopt (`EXT_meshopt_compression`) | Draco |
| --- | --- | --- |
| Decode speed | Very fast, tiny decoder | Slower, ~300 KB WASM decoder |
| Size | Slightly larger raw, close after gzip/brotli | Smallest geometry |
| Animation/morphs | Yes | Geometry only |
| Use here | **Default** | Only if download size is critical |

They're mutually exclusive per file. Loader setup:

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
const loader = new GLTFLoader()
  .setMeshoptDecoder(MeshoptDecoder)
  .setKTX2Loader(new KTX2Loader().setTranscoderPath('/basis/').detectSupport(renderer));
```

## Quantization

`KHR_mesh_quantization` stores positions as 16-bit, normals/colors as 8-bit: about half the vertex memory and bandwidth. gltfpack does it by default; gltf-transform via `quantize` (part of `optimize`). For huge chunks, check for visible cracks between chunk borders. If you see any, raise position bits (`gltfpack -vp 16`) or snap border vertices.

## Textures (only if you add any)

- **KTX2/Basis**: ETC1S for color (small), UASTC for normal maps (quality). Stays compressed in VRAM, unlike PNG/JPG/WebP, which decode to full RGBA.
- Power-of-two sizes, max 1024 on low tier (512 for props). Mipmaps on for 3D surfaces.
- One small palette/gradient atlas beats many textures.
- Avoid RGB formats (often emulated). Use RGBA8.

## Collision meshes

- Terrain: per-chunk decimated `_col` trimesh (< 100–300 tris). Ramps/loops: clean simplified trimesh. Props: **primitives** (cuboid, cylinder, ball) or convex hulls, never trimesh.
- Store collision meshes in a separate .glb (or as named nodes) and never add them to the render scene.

## Checklist per asset

- [ ] Triangle count within budget (`gltf-transform inspect`)
- [ ] One material, vertex colors, no unused UV/normal/tangent attributes
- [ ] LOD1/LOD2 generated (`lod.md`) where the asset is seen from > 80 m
- [ ] `_col` proxy generated and named
- [ ] meshopt-compressed + quantized
- [ ] Loads without console warnings; `renderer.info` checked in the test scene
