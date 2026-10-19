# Profiling

Always profile on the **real target device**. Desktop Chrome with CPU throttling doesn't reproduce a weak GPU.

## Tools

| Tool | What it shows |
| --- | --- |
| `renderer.info` | `render.calls`, `render.triangles`, `memory.geometries`, `memory.textures`, `programs.length` |
| **stats-gl** (`npm i stats-gl`) | FPS + CPU + GPU time panels for WebGL/WebGPU |
| **Chrome DevTools → Performance** | JS time per frame, GC, long tasks, rAF timing |
| **chrome://inspect** (USB debugging) | Remote DevTools on the Android phone (enable Developer options → USB debugging) |
| **chrome://gpu** (on the phone too) | GPU name, WebGL/WebGPU status, driver bugs/workarounds |
| **Spector.js** (extension) | Captures one frame: every draw call, state change, shader, texture |
| `EXT_disjoint_timer_query_webgl2` | GPU timing of passes. Often unavailable on Android; use where present |
| **Android GPU Inspector / Snapdragon Profiler** | Deep Adreno counters (fragment load, bandwidth) for native/Chrome apps |
| `gltf-transform inspect file.glb` | Per-mesh vertices, triangles, size, extensions |

## Am I CPU- or GPU-bound?

1. Lower the pixel ratio to 0.5. If fps jumps, you're **GPU/fill-bound** → resolution, overdraw, shaders, shadows, post.
2. If it doesn't change, you're **CPU-bound** → draw calls, JS, physics, GC. Check the Performance panel.
3. Hide all chunks but keep logic running. That tells you how much rendering costs vs game logic.

## Debug overlay to keep in dev builds

Show: fps (avg + 1% low), frame ms, draw calls, triangles, geometries/textures, current pixel ratio, quality tier, loaded chunks, physics ms, active bodies. Toggle with a key and with `?debug` in the URL.

## Test matrix

| Device | Why |
| --- | --- |
| Snapdragon 625/660 phone (Adreno 506/512) | Worst-case target |
| Snapdragon 665/680 phone (Adreno 610) | Most common low-end |
| Laptop Intel UHD 620 | Weak iGPU |
| Laptop Iris Xe or Vega 8 | Typical iGPU |
| iPhone 8/XR-class (A11/A12) | Safari/WebKit quirks |

Run a 10-minute drive on each (thermals) and record: fps over time, peak memory, chunk load hitches.
