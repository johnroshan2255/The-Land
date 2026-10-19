# Runtime: JS, memory, streaming, physics, thermals

## Frame loop

- One loop: `renderer.setAnimationLoop(tick)`. Physics on a fixed step with an accumulator; render once per frame.
- **Low tier, 30 fps lock**: skip every other rAF (`if (now - last < 1000/30 - 1) return`). A stable 30 beats a jittery 45 and keeps the phone cooler.
- Pause everything when `document.hidden` (the `visibilitychange` event).
- Throttle non-critical work: distance culling, LOD, minimap and UI every N frames; bot AI at 10–15 Hz with interpolation.

## Garbage collection

- **Zero allocations per frame**: preallocate `Vector3`/`Quaternion`/`Matrix4` scratch objects at module level. No `new`, no `.clone()`, no array spreads or closures in `tick`.
- Object pools for particles, skid-mark segments, projectiles and network messages.
- Avoid `scene.traverse` per frame. Keep explicit arrays of objects that need updates.
- Avoid `Array.find`/`forEach` with closures in hot paths on low-end phones. Use plain `for` loops.

## Memory and disposal

- On chunk unload: `geometry.dispose()`, `material.dispose()` (if not shared), `texture.dispose()`, remove from scene and **remove its Rapier colliders**.
- Share one material instance across all chunks. Never clone per chunk.
- Watch `renderer.info.memory.geometries/textures`. It must return to baseline after driving away and back.
- Keep a **small LRU cache** (e.g. 4–6 recently unloaded chunks) to avoid re-download/re-parse when driving back and forth at a boundary.
- Respect `navigator.deviceMemory` (≤ 2 → low tier, smaller cache).
- Handle `webglcontextlost`/`webglcontextrestored`. Low-RAM Android kills contexts when backgrounded. Show "Tap to resume" and rebuild GPU resources.

## Chunk streaming

```
current = worldToChunk(car.position)
if current != last:
  wanted = 3x3 (or 5x5 high tier) around current
  load(wanted − loaded)   // priority: the chunk the car moves toward first
  unload(loaded − wanted − hysteresisRing)  // keep a 1-chunk margin to stop thrash
```

- **Preload ahead**: use velocity to prefetch the chunk the car will enter in ~2 s.
- **Spread work over frames**: parse/upload at most 1 chunk per frame; add colliders the next frame; build instanced props the frame after. Use `requestIdleCallback` where available.
- `MeshoptDecoder` decodes fast. For Draco, use the worker-based `DRACOLoader`. Texture decode is off-thread via `ImageBitmap` (`GLTFLoader` does this where supported).
- Serve with **brotli/gzip** and long cache headers. Consider a service worker cache for chunks.
- Upload cost: first render of a new mesh uploads buffers (a hitch on weak GPUs). `renderer.initTexture(tex)` and rendering new chunks while they're still invisible at the edge of fog both spread the cost.

## Rapier3D physics

- **Bodies**: terrain chunks, ramps and bridges = **fixed** bodies (no pair cost among themselves). Car = dynamic. Bots = dynamic, or kinematic when far from the player.
- **Shapes**: cuboid/ball/capsule/cylinder < convex hull < trimesh. Trimesh only for terrain and ramps. Props use primitives or compounds of primitives.
- **Vehicle**: use Rapier's raycast vehicle controller (`world.createVehicleController(chassis)` → `DynamicRayCastVehicleController`) rather than 4 wheel rigid bodies + joints. That's 4 raycasts vs a full joint solve.
- **Sleeping**: on by default. Dynamic props (cones, barrels) fall asleep when still. Keep `wakeUp` true only where needed.
- **CCD**: off by default (expensive). Enable only on the player car (`setCcdEnabled(true)`) for high-speed ramp landings. Alternatively use the cheaper `setSoftCcdPrediction`.
- **Collision groups**: `setCollisionGroups` so props don't test against each other and sensors only test against cars.
- **Stream colliders with chunks**: create on load, `world.removeCollider` on unload. 144 trimesh chunks in the broad phase at once wastes memory and time.
- **Fixed timestep**: `world.timestep = 1/60` (1/30 on low tier if the handling stays stable), accumulator, max 2–3 steps per frame (drop time beyond that rather than spiral).
- **Interpolate** render transforms between physics states, so 30 Hz physics still looks smooth.
- **Bots far away**: no physics. Move them along waypoint splines kinematically and re-enable physics within ~150 m of the player.
- Physics in a Web Worker removes main-thread time but adds a frame of latency and transfer cost. Try it on the low tier only if profiling shows physics > 4 ms.

## Loading

- Ship a tiny first scene (car + 9 chunks + backdrop) under ~2–3 MB; stream the rest.
- `renderer.compileAsync(scene, camera)` behind the loading screen.
- Lazy-load Rapier WASM, the audio and the multiplayer client in parallel with assets.

## Thermal and battery

- Phones throttle after a few minutes at 100% GPU. Design the low tier to run at ~60–70% load at 30 fps.
- Adaptive resolution (`QualityManager.js`) is the main defense: it lowers the pixel ratio as the device heats up.
- Menus/garage: render on demand (only when something changes), or at 30 fps.

## Audio

- Web Audio: decode once, reuse `AudioBuffer`s. Use one engine loop with `playbackRate` instead of many overlapping sources. Limit concurrent sources (~8) on mobile.
