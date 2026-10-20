# Export the island as a fixed map for the DARK engine (../Dark, "Select map" -> Island). Runs after island_master.py
# and island_chunks.py in the same Blender process (needs their roads, BRIDGES, the relief-applied BVH and props):
#   node tools/blender/headless.mjs tools/blender/lib.py tools/blender/camp.py tools/blender/structures.py \
#     tools/blender/nature.py tools/blender/vehicles.py tools/blender/island_master.py tools/blender/island_chunks.py \
#     tools/blender/export_dark_map.py MODE=library CLAY=0 GRID_N=250 OUT_DIR=models/terrain/game \
#     SRC_DIR=models/terrain/source DARK_OUT=../Dark/public/maps/island
# Writes to DARK_OUT:
#   heights.bin   Uint16 grid N x N (row = z from -HALF northward... see map.json "grid"), metres = v / 65535 * range + min
#   biome.bin     Uint8 grid M x M x 2: desert weight (desert + beach), snow weight, 0..255
#   map.json      grid metadata, roads (three.js x / z, heights, half widths, bridge flags), spawn, water level
#   props.json    copy of the game's placements (three.js coordinates)
# Coordinates are three.js world metres (x = Blender x, z = -Blender y); heights are the game's (sea level 0). Dark's
# water sits at -6, so map.json carries "heightOffset": -6 for the loader to add.
import json, os, shutil, struct

DARK_OUT = globals().get("DARK_OUT")
GRID_STEP = float(globals().get("DARK_STEP", "2"))      # height samples every 2 m (Dark's chunk vertex spacing)
BIOME_STEP = 4.0
N = int(round(2 * HALF / GRID_STEP)) + 1
M = int(round(2 * HALF / BIOME_STEP)) + 1


def export_dark_map(out):
    os.makedirs(out, exist_ok=True)
    # heights: row j = three z from -HALF to +HALF (Blender y = -z), column i = x from -HALF to +HALF
    hs = []
    lo, hi = 1e9, -1e9
    for j in range(N):
        y = HALF - j * GRID_STEP   # three z = -HALF + j*step  ->  Blender y = -z
        row = []
        for i in range(N):
            x = -HALF + i * GRID_STEP
            z, _ = surface(x, y)
            z = SEA_FLOOR if z is None else z
            row.append(z)
            lo, hi = min(lo, z), max(hi, z)
        hs.append(row)
    rng = hi - lo
    with open(f"{out}/heights.bin", "wb") as fh:
        for row in hs:
            fh.write(struct.pack(f"<{N}H", *[int(round((v - lo) / rng * 65535)) for v in row]))
    with open(f"{out}/biome.bin", "wb") as fh:
        for j in range(M):
            y = HALF - j * BIOME_STEP
            buf = bytearray()
            for i in range(M):
                w = weights(-HALF + i * BIOME_STEP, y)
                buf += bytes((int(min(1, w["desert"] + w["beach"]) * 255), int(w["snow"] * 255)))
            fh.write(buf)
    out_roads = []
    for name, (smp, hh, w, cls, closed) in zip(road_names, roads):
        out_roads.append({
            "name": name, "class": cls, "halfWidth": w, "closed": closed,
            "x": [round(p.x, 2) for p in smp], "z": [round(-p.y, 2) for p in smp], "h": [round(v, 2) for v in hh],
            "bridge": [1 if in_canyon(p.x, p.y) else 0 for p in smp],
        })
    meta = {
        "id": "island", "name": "The Island", "size": 2 * HALF, "half": HALF, "heightOffset": -6.0,
        "grid": {"n": N, "step": GRID_STEP, "min": round(lo, 3), "range": round(rng, 3), "origin": [-HALF, -HALF]},
        "biomeGrid": {"n": M, "step": BIOME_STEP, "origin": [-HALF, -HALF]},
        "seaLevel": 0.0, "spawn": [450.0, 330.0, 2.124],   # x, z, heading (rad) - the game's start on the forest road
        "roads": out_roads,
        "bridges": [{"a": [round(a.x, 2), round(-a.y, 2)], "b": [round(b.x, 2), round(-b.y, 2)], "deck": round(h, 2)} for a, b, h in BRIDGES],
    }
    with open(f"{out}/map.json", "w") as fh:
        json.dump(meta, fh, separators=(",", ":"))
    shutil.copy(f"{OUT_DIR}/props.json", f"{out}/props.json")
    print(f"terrain: dark map {N}x{N} heights [{lo:.1f}, {hi:.1f}] m, {len(out_roads)} roads, {len(BRIDGES)} bridges -> {out}", flush=True)


if DARK_OUT:
    export_dark_map(DARK_OUT)
