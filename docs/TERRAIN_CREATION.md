# Terrain Creation Guide

Source: Gemini chat "3D Bruno Simon Car Design". Reference images: `../reference/`. Asset names: `GLB_ASSET_LIST.md`.

## Reference images

| Image | Shows |
| --- | --- |
| `reference/01_car_model_render.png` | The red 4x4 hero car |
| `reference/02_map_isometric.png` | Isometric map overview |
| `reference/03_gameplay_tpp_openworld.png` | Third-person open-world view |
| `reference/04_map_biomes_forest_desert_canyon.png` | Snow, forest, desert and canyon side by side, with bridges and ramps |
| `reference/05_snow_biome_switchbacks_bridge.png` | Snow switchbacks, frozen ponds, rope bridge |
| `reference/06_beach_coastal_highway.png` | Beach shelf, ocean, cliff and asphalt coastal highway |
| `reference/07_gameplay_tpp_closeup.png` | Close-up gameplay |
| `reference/08_gameplay_social_hangout.png` | Multiplayer hangout |
| `reference/09_map_chunked_6km2_overview.png` | The 6 km² chunked map concept |
| `reference/10_ui_main_menu.png` | Main menu / settings UI |

## World layout

- One 6 km² master terrain, sculpted whole in Blender, then sliced into **144 chunks of 200 m × 200 m** (`terrain_chunk_X_Y`).
- Biomes by area:
  - **NW**: snow, with mountain passes and switchbacks
  - **NE**: desert with sand dunes
  - **SE**: forest, with mountain roads
  - **SW**: beach and coast, with a western coastal ridge and highway
  - A canyon with sheer cliffs and a chasm crossed by a bridge
- Style: low-poly, flat-shaded, vertex colors only. 1,500–3,000 tris per chunk.

## Sculpting the geography (inside the terrain mesh)

All landforms are sculpted into the master terrain **before** it is cut into chunks, so the edges line up seamlessly.

| Feature | How to build it |
| --- | --- |
| Hills and mountain passes | Raise peaks. Carve winding switchback roads as stepped, flat terraces wrapping around the slopes (NW snow, SE forest). |
| Cliffs | Align vertices vertically for sheer rock walls down to the sea or canyon floor (canyon, western ridge). |
| Sand dunes | Rolling wave displacement with no hard drop-offs, for high-speed jumps (NE). |
| Beach shelf | Slope the SW terrain down to elevation 0, flattening into the shoreline. |
| Ocean | One flat plane at Z = −0.5. Terrain dipping below it forms wet sand, tide pools and deep water. |
| Chasms / ravines | Carve a gap through the terrain (e.g. dropping −18 m to a riverbed) where a bridge will go. |
| Natural ramps | Dirt kickers, dune ramps and cliff jumps shaped from the ground itself. No seams, no extra draw calls, collision comes with the chunk. |

## Roads (vertex colors, not separate meshes)

Roads are painted onto the terrain vertices with Blender Color Attributes (Vertex Paint). That means no floating road meshes, no z-fighting, no texture memory and no extra draw calls. Keep enough vertex density along road routes so the paint edges read cleanly.

| Road | Color | Where |
| --- | --- | --- |
| Mud / dirt trail | `#8A5E38` | Across forest grass and orange sand |
| Asphalt coastal highway | `#3D4148` | Western ridge down to the beach |
| Snow drift track | light blue/grey | Hard-packed tracks across white snow plains |

Base ground colors: green for grass, orange for sand, grey for rock, white for snow.

## Ramps and bridges: terrain vs. props

- **In the terrain mesh**: natural ramps, kickers, dune lips and cliff jumps.
- **Separate props** (placed via `data/props.json`, own `_col` mesh): wooden loop, ski-jump kicker, quarter-pipe and `bridge_suspension_rope.glb`.
- Bridges sit across the carved chasm with their ends resting on the cliff edges. Their own Rapier collider lets cars drive off the cliff road, across the planks and onto the far side.

## Slicing, collision, backdrop, export

1. **Backdrop first**: duplicate the finished master terrain, Decimate it to 2,000–4,000 tris and export as `world_backdrop_lod.glb` (~100–200 KB).
2. **Slice** the master into the 200 m grid (144 tiles). Name them `terrain_chunk_X_Y`, with the origin at each chunk's corner or center (pick one and keep it consistent).
3. **Collision**: for each chunk, Shift + D, then a heavy Decimate to bare driving planes and ramps (< 100 polys). Name it `chunk_X_Y_col` and export as `collision_chunk_X_Y.glb`.
4. **Export** each chunk as .glb: Selected Objects, Apply Modifiers, Vertex Colors, Draco/Meshopt compression. No props inside chunks.
5. **Props**: write tree, rock, cactus, ramp and camp positions per chunk into `data/props.json`.

## Runtime streaming (Three.js + Rapier3D)

- Keep a **3×3 grid** (9 chunks) loaded around the car: ~20,000–25,000 tris in total.
- Track which chunk the car is in. When it changes, load the new edge row/column of `.glb` files plus their `_col` colliders, and dispose of the far ones.
- `world_backdrop_lod.glb` stays in the scene permanently. **Distance fog** hides the seam where the detailed chunks meet the backdrop.
- Props per chunk come from `props.json` and render as `InstancedMesh`. Trees are not drawn beyond ~350 m.

## Step-by-step with Blender MCP + Claude

1. **Test slice (1–2 days)**: generate a 3×3 chunk area with snow, dunes and ramps, vertex colors and an export script.
2. Test it in-engine with the car and the chunk loader (2–3 days).
3. **Full map (2–4 days)**: run the batch script to generate the 6 km² terrain, slice it, decimate collision proxies and export all chunks.
4. **Backdrop and props (2–3 days)**: export `world_backdrop_lod.glb` and fill in `props.json`.

Example prompt for the first chunk set:

> Create a 600 m × 600 m low-poly terrain at origin split into a 3×3 grid of 200 m chunks. Include a snow hill with a switchback road terrace, a dune area with a natural ramp, and a sloped beach edge down to Z = 0. Flat shading, vertex colors (grass green, sand orange, rock grey, snow white, dirt road #8A5E38). Create a decimated `_col` duplicate per chunk and export each as .glb with Draco compression.
