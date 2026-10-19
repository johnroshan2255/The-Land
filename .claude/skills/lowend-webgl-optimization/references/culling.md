# Culling: don't draw what can't be seen

Culling is a cascade. Each stage is cheaper than the next and removes work before it:

1. **Streaming / world partition**: the object isn't loaded at all (3×3 chunk grid).
2. **Distance culling**: loaded but too far to matter (fog end, per-layer distances).
3. **Occlusion culling (coarse)**: behind a hill or cliff (chunk PVS, horizon test).
4. **Frustum culling**: outside the camera's view cone.
5. **Per-instance culling**: inside an instanced batch.
6. **GPU-side**: back-face culling, early-Z (opaque front-to-back), small-triangle avoidance via LOD.

## 1. Streaming

See `runtime.md` → Chunk streaming. Load the 3×3 grid around the car, unload with a hysteresis margin, and keep the decimated `world_backdrop_lod.glb` always loaded.

## 2. Distance culling

- **Fog-matched far plane**: `scene.fog = new THREE.Fog(color, near, far)` and `camera.far = far + small margin`. Three.js frustum culling then drops everything past the fog for free. The fog color must match the sky/clear color.
- **Per-category draw distances** (cheaper than LOD for small things): rocks 80–120 m, fences 150 m, trees 200–350 m, bots render as LOD2 or are hidden past 400 m. Do it per chunk, not per object (`lod-utils.js` → `DistanceCuller`).
- Check distances against squared distance (`distanceToSquared`), not `distanceTo`.
- Update distance culling every 3–6 frames, not every frame.

## 3. Occlusion culling

Three.js **WebGLRenderer has no occlusion culling**. A WebGL2 occlusion-query PR was closed. `WebGPURenderer` has an occlusion test (see the `webgpu_occlusion` example), but WebGPU isn't a baseline for low-end Android, and forum reports show `isOccluded` returning null when called the wrong way.

Options, best first for this game:

### a. Precomputed chunk PVS (recommended)

Offline (or at load), for each chunk A, cast rays from sample eye points (driver height ~2 m and camera height ~6 m over A's driveable area) to sample points on every chunk B within the view distance. If any ray reaches B unobstructed by terrain, B is visible from A. Store `pvs[A] = [B…]` as a bitset JSON (144 × 144 bits ≈ 2.6 KB).

At runtime: visible chunks = loaded chunks ∩ `pvs[currentChunk]`. Hide the rest (`chunk.visible = false`). Mountains, canyon walls and cliffs then cost nothing. `scripts/runtime/ChunkPVS.js` has the bake and the runtime.

- Be conservative: add a one-chunk dilation, and include chunks above the occluder (tall peaks).
- Rebake when the terrain changes. It's one script run.

### b. Horizon culling (heightfield terrain)

For terrain viewed from near ground level, keep a 1D "horizon" of max elevation angle per screen column while walking chunks front-to-back. A chunk whose top silhouette is under the horizon is hidden. It's good for rolling hills, but more code than PVS.

### c. Hardware occlusion queries (WebGL2, DIY)

`gl.createQuery()` → `beginQuery(gl.ANY_SAMPLES_PASSED_CONSERVATIVE, q)` → draw the bounding box (color/depth writes off) → `endQuery` → read `QUERY_RESULT` **1–2 frames later** (never block). Objects pop in for a frame when they become visible, so use them only for big, expensive objects (a whole town or camp cluster). On tile-based mobile GPUs, query results are slow to come back. Usually not worth it here.

### d. Manual portals/zones

For interiors (tunnels, caves, garage): mark zones and only draw a zone when the camera is in it or sees its portal. Trivial and very effective for tunnels.

## 4. Frustum culling (built in)

- Three.js tests each object's **bounding sphere** against the frustum (`object.frustumCulled = true` by default).
- **Make objects cullable**: split big meshes. One giant terrain mesh is never culled; 200 m chunks are. Don't merge across chunks.
- **InstancedMesh pitfall**: the whole set is culled as one sphere covering all instances. A world-wide tree InstancedMesh is never culled. Use **one InstancedMesh per chunk per prop type**, and call `instancedMesh.computeBoundingSphere()` after setting matrices.
- **SkinnedMesh/morph pitfall**: the bounding sphere is from the bind pose, so animated parts may wrongly cull. Enlarge it or set `frustumCulled = false` only on that object.
- Never set `frustumCulled = false` globally to "fix" popping. Fix the bounds instead.

## 5. Per-instance culling

- **`InstancedMesh2`** (`@three.ez/instanced-mesh`): per-instance frustum culling (on by default), optional BVH (`computeBVH()`), per-instance LOD (`addLOD(geometry, material, distance)`), shadow LOD (`addShadowLOD`), and sorting. Ideal for trees/rocks scattered over a chunk.
- **`BatchedMesh`** (core three.js): different geometries, one draw call, per-instance frustum culling (`perObjectFrustumCulled`). Relies on `WEBGL_multi_draw`, with fallback. Benchmark on the Adreno target, since there are reports of multi-draw being slow on some WebGL drivers. `@three.ez/batched-mesh-extensions` adds BVH + LOD.
- **BVH for raycasts**: `three-mesh-bvh` (`computeBoundsTree`, `acceleratedRaycast`) for camera-collision rays, bot line-of-sight and mouse picking. A raycast against a 3,000-triangle chunk without a BVH is a linear scan.

## 6. GPU-side culling

- Keep `material.side = THREE.FrontSide` (the default). `DoubleSide` doubles fragment work for closed meshes. Only use it for thin cards (flags, leaves).
- Opaque objects are sorted front-to-back by three.js (`renderer.sortObjects = true`), so early-Z rejects hidden pixels. Keep it on.
- Draw the sky/backdrop last or with depth test, never as a huge transparent sphere.
- Tiny triangles (under ~4 px) waste rasterizer quads → that's what LOD fixes (`lod.md`).
