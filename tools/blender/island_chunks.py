# Game build of the master island: chunked, faceted, LOD'd terrain + scattered props + map image.
# Runs after lib.py + island_master.py in the same Blender process (reuses its height/biome/road/river functions):
#   node tools/blender/headless.mjs tools/blender/lib.py tools/blender/island_master.py tools/blender/island_chunks.py CLAY=0 GRID_N=300
# Writes to OUT_DIR (default models/terrain/game):
#   terrain_lod0.glb / _lod1.glb / _lod2.glb  one node per 200 m chunk ("chunk_i_j", i = column W->E, j = row S->N),
#                                             node origin = chunk centre; LOD1/2 have skirts to hide cracks
#   props.glb                                 one node per prop type, origin at the base
#   props.json                                per-chunk instance lists in three.js coords
#   map.png                                   top-down map, north up, exactly 2400 m across
# Faceted look: small-scale relief + one color per triangle (corner-domain colors) for flat-shaded rendering.
import json, os
from mathutils.bvhtree import BVHTree

OUT_DIR = globals().get("OUT_DIR", r"C:/project/New Game/models/terrain/game")
CHUNK, NCH = 200.0, 12
LOD_RATIOS = (1.0, 0.22, 0.06)
SKIRT = 6.0


def road_info(x, y):
    _, i, d = road_kd.find((x, y, 0))
    return d, road_meta[i][2]


def relief_amp(x, y, z):
    """Small-scale relief strength: 0 on roads, water, ice and the river gorge."""
    if z < 0.3 or lake_reff(x, y) < LAKE_R + 15:
        return 0.0
    d, w = road_info(x, y)
    road = sstep(w + ROAD_SHOULDER + 6, w + ROAD_SHOULDER, d)
    river = sstep(RIVER_W1 + 10, RIVER_W1, river_kd.find((x, y, 0))[2])
    w4 = weights(x, y)
    amp = 2.4 * w4["snow"] + 1.3 * w4["desert"] + 0.7 * w4["beach"] + 1.6 * w4["forest"]
    return amp * (1 - road) * (1 - river)


def relief(x, y, z):
    a = 0.6 * relief_amp(x, y, z)   # soft, broad facets (the refs read as big gentle planes, not crumpled paper)
    return a * (0.75 * n2(x, y, 34, 31) + 0.25 * n2(x, y, 14, 32)) if a else 0.0


# Game color theme matched to the in-game reference shots: warm golden-hour palette, bright yellow-green grass,
# golden sand, warm terracotta. (The master mesh keeps the original spec palette.)
THEME = {"snow": "#F4F8FC", "ice": "#8FE3EA", "terracotta": "#D9733F", "desert_sand": "#F0BE74", "beach": "#F3D597",
         "forest": "#86C84A", "cliff": "#A06C45", "asphalt": "#5B5E64", "dirt": "#C99C63"}
GRASS_DARK, GRASS_LIGHT = lin("#6EB040"), lin("#A2D65A")
SHALLOW, DEEP = lin("#EED49A"), lin("#2BA6B5")


def face_hash(f):
    c = f.calc_center_median()
    return (math.sin(c.x * 12.9898 + c.y * 78.233) * 43758.5453) % 1.0


src = bpy.data.objects["Island_Master"]
bm = bmesh.new()
bm.from_mesh(src.data)
col_layer = bm.verts.layers.float_color.get("Col")
for v in bm.verts:
    v.co.z += relief(v.co.x, v.co.y, v.co.z)
bm.normal_update()
bvh = BVHTree.FromBMesh(bm)

# recolor every vertex with the game theme (same biome/slope/road rules as the master mesh)
for k, h in THEME.items():
    C[k] = lin(h)
for v in bm.verts:
    x, y, z = v.co
    c = vertex_color(v)
    w4 = weights(x, y)
    # big soft light/dark grass patches like the refs
    patch = 0.5 + 0.5 * n2(x, y, 140, 41)
    grass = GRASS_DARK.lerp(GRASS_LIGHT, patch)
    if w4["forest"] > 0 and c.y > c.x:   # only green-dominant vertices (keeps cliffs/roads)
        c = c.lerp(grass, 0.45 * w4["forest"])
    if z < -0.05 and lake_reff(x, y) > LAKE_R + 1:   # sea + river floor: sand in the shallows, teal in the deep
        c = SHALLOW.lerp(DEEP, sstep(-0.3, -9.0, z))
    v[col_layer] = (c.x, c.y, c.z, 1.0)

# one color per face: average of its vertex colors, +-2.5% value jitter, a little darker on steep faces
face_cols = []
for f in bm.faces:
    c = Vector((0, 0, 0))
    for v in f.verts:
        c += Vector(v[col_layer][:3])
    c /= len(f.verts)
    k = 0.975 + 0.05 * face_hash(f) - 0.08 * sstep(0.35, 0.8, 1 - f.normal.z)
    face_cols.append(c * k)

chunk_faces = {}
for f in bm.faces:
    cen = f.calc_center_median()
    i = min(NCH - 1, max(0, int((cen.x + HALF) // CHUNK)))
    j = min(NCH - 1, max(0, int((cen.y + HALF) // CHUNK)))
    chunk_faces.setdefault((i, j), []).append(f)

terrain_mat = bpy.data.materials["M_Terrain_Clay"]
os.makedirs(OUT_DIR, exist_ok=True)


def chunk_mesh(name, faces, center):
    verts, idx, polys, cols = [], {}, [], []
    for f in faces:
        poly = []
        for v in f.verts:
            if v.index not in idx:
                idx[v.index] = len(verts)
                verts.append((v.co.x - center.x, v.co.y - center.y, v.co.z))
            poly.append(idx[v.index])
        polys.append(poly)
        cols.append(face_cols[f.index])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], polys)
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    data = []
    for p, c in zip(me.polygons, cols):
        data += [c.x, c.y, c.z, 1.0] * p.loop_total
    attr.data.foreach_set("color", data)
    me.color_attributes.active_color = attr
    me.color_attributes.render_color_index = me.color_attributes.active_color_index
    me.materials.append(terrain_mat)
    return me


def add_skirt(me):
    """Hang a 6 m strip down from every open border edge so decimated neighbours never show cracks."""
    b = bmesh.new()
    b.from_mesh(me)
    cl = b.loops.layers.float_color.get("Col")
    border = [e for e in b.edges if e.is_boundary]
    out = bmesh.ops.extrude_edge_only(b, edges=border)
    new_verts = [g for g in out["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(b, verts=new_verts, vec=(0, 0, -SKIRT))
    for f in (g for g in out["geom"] if isinstance(g, bmesh.types.BMFace)):
        for loop in f.loops:
            loop[cl] = (0.25, 0.2, 0.16, 1.0)
    b.to_mesh(me)
    b.free()


def evaluated_copy(o):
    dg = bpy.context.evaluated_depsgraph_get()
    return bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg)


lod_objs = {0: [], 1: [], 2: []}
tri_totals = [0, 0, 0]
for (i, j), faces in sorted(chunk_faces.items()):
    center = Vector((-HALF + (i + 0.5) * CHUNK, -HALF + (j + 0.5) * CHUNK, 0))
    base = chunk_mesh(f"chunk_{i}_{j}", faces, center)
    for lod, ratio in enumerate(LOD_RATIOS):
        name = f"chunk_{i}_{j}"
        me = base if lod == 0 else base.copy()
        o = bpy.data.objects.new(f"{name}__lod{lod}", me)
        bpy.context.scene.collection.objects.link(o)
        o.location = center
        if ratio < 1:
            d = o.modifiers.new("Dec", "DECIMATE")
            d.ratio = ratio
            me2 = evaluated_copy(o)
            o.modifiers.clear()
            o.data = me2
            add_skirt(me2)
        o.data.polygons.foreach_set("use_smooth", [False] * len(o.data.polygons))
        o.data.calc_loop_triangles()
        tri_totals[lod] += len(o.data.loop_triangles)
        lod_objs[lod].append(o)


def export(objs, path, colors=True):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_normals=False, export_texcoords=False, export_tangents=False, export_cameras=False,
              export_lights=False, export_animations=False, export_materials="EXPORT", export_vertex_color="ACTIVE",
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
              export_draco_position_quantization=14, export_draco_color_quantization=8)
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})


sizes = {}
for lod in (0, 1, 2):
    for o in lod_objs[lod]:
        o.name = o.name.split("__")[0]   # node name "chunk_i_j" in every LOD file
    p = f"{OUT_DIR}/terrain_lod{lod}.glb"
    export(lod_objs[lod], p)
    sizes[f"lod{lod}"] = os.path.getsize(p)
    for o in lod_objs[lod]:
        o.name = o.name + f"__lod{lod}"
print(f"terrain: chunks={len(chunk_faces)} tris={tri_totals} bytes={sizes}", flush=True)

# ------------------------------------------------------------------ props (vertex-colored, flat, origin at base)
def rgb(h):
    return tuple(lin(h)) + (1.0,)


def build_prop(name):
    p = Part()
    if name in ("pine", "pine_snow"):
        p.cyl(rgb("#6E4630"), r=0.28, depth=1.4, seg=5, loc=(0, 0, 0.7))
        for k, (r, h, z) in enumerate(((2.3, 2.7, 1.1), (1.8, 2.3, 2.5), (1.2, 1.9, 3.7))):
            p.cone(rgb(("#4E9A3A", "#62AE45", "#78BE50")[k]), r=r, depth=h, seg=7, loc=(0, 0, z + h / 2), rot=(0, 0, 25 * k))
            if name == "pine_snow":
                p.cone(rgb("#F3F7FB"), r=r * 0.93, depth=h * 0.78, seg=7, loc=(0, 0, z + h * 0.64), rot=(0, 0, 25 * k + 12))   # heavy snow load
    elif name in ("rock", "rock_snow"):
        p.ico(rgb("#7E766F" if name == "rock_snow" else "#A89A8A"), r=1.0, sub=1, loc=(0, 0, 0.35), scale=(1.5, 1.15, 0.85), jitter=0.12, seed=4)
        if name == "rock_snow":
            p.ico(rgb("#F1F5FA"), r=0.95, sub=1, loc=(0, 0, 0.62), scale=(1.35, 1.0, 0.45), jitter=0.06, seed=5)
    elif name == "bush":
        for k, (x, y, r) in enumerate(((0, 0, 0.9), (0.75, 0.3, 0.65), (-0.6, 0.45, 0.7))):
            p.ico(rgb(("#5FA33E", "#72B548", "#4F9136")[k]), r=r, sub=0, loc=(x, y, r * 0.7), jitter=0.08, seed=k)
    elif name == "grass_tuft":
        for k in range(5):
            a = 2 * math.pi * k / 5
            p.cone(rgb(("#8FC651", "#7AB646")[k % 2]), r=0.09, depth=0.75, seg=3, loc=(0.16 * math.cos(a), 0.16 * math.sin(a), 0.33),
                   rot=(18 * math.sin(a), 18 * math.cos(a), 0))
    elif name == "cactus":
        p.cyl(rgb("#5E9E3A"), r=0.32, depth=3.2, seg=6, loc=(0, 0, 1.6))
        p.cyl(rgb("#4F8A32"), r=0.22, depth=1.3, seg=6, loc=(0.55, 0, 1.9))
        p.cyl(rgb("#4F8A32"), r=0.2, depth=0.6, seg=6, loc=(0.32, 0, 1.4), rot=(0, 90, 0))
        p.cyl(rgb("#4F8A32"), r=0.2, depth=1.0, seg=6, loc=(-0.5, 0, 2.3))
        p.cyl(rgb("#4F8A32"), r=0.18, depth=0.5, seg=6, loc=(-0.3, 0, 1.9), rot=(0, 90, 0))
    o = p.finish(name)
    o.data.polygons.foreach_set("use_smooth", [False] * len(o.data.polygons))
    return o


PROP_TYPES = ["pine", "pine_snow", "rock", "rock_snow", "bush", "grass_tuft", "cactus"]
prop_objs = [build_prop(n) for n in PROP_TYPES]


def surface(x, y):
    hit = bvh.ray_cast(Vector((x, y, 2000)), Vector((0, 0, -1)), 4000)
    return (hit[0].z, hit[1].z) if hit[0] is not None else (None, 0)


def clear_of_features(x, y, z, margin):
    d, w = road_info(x, y)
    if d < w + ROAD_SHOULDER * 0.5 + margin:
        return False
    if river_kd.find((x, y, 0))[2] < RIVER_W1 + margin:
        return False
    if lake_reff(x, y) < LAKE_R + 20 + margin:
        return False
    return z > 1.0


RULES = {   # type: (spacing m, keep probability, scale range, test(w, x, y, z, nz))
    "pine": (13, 0.75, (1.1, 2.0), lambda w, x, y, z, nz: w["forest"] > 0.55 and nz > 0.8 and n2(x, y, 180, 40) > -0.25),
    "pine_snow": (20, 0.6, (1.0, 1.9), lambda w, x, y, z, nz: w["snow"] > 0.55 and z < 260 and nz > 0.75),
    "rock": (40, 0.45, (0.6, 1.8), lambda w, x, y, z, nz: w["snow"] < 0.4 and nz > 0.6),
    "rock_snow": (30, 0.55, (0.5, 1.6), lambda w, x, y, z, nz: w["snow"] > 0.5),
    "bush": (18, 0.45, (0.7, 1.4), lambda w, x, y, z, nz: (w["forest"] + 0.5 * w["beach"]) > 0.5 and nz > 0.8 and z > 3),
    "grass_tuft": (8, 0.45, (0.8, 1.5), lambda w, x, y, z, nz: (w["forest"] + 0.6 * w["beach"]) > 0.45 and nz > 0.85 and z > 2),
    "cactus": (38, 0.4, (0.8, 1.4), lambda w, x, y, z, nz: w["desert"] > 0.6 and nz > 0.85 and mesa_t(x, y) < 0.2),
}
rng = random.Random(77)
placed = {}
counts = {}
for name in PROP_TYPES:
    spacing, keep, (s0, s1), test = RULES[name]
    n = 0
    steps = int(2 * HALF / spacing)
    for a in range(steps):
        for b in range(steps):
            x = -HALF + (a + rng.random()) * spacing
            y = -HALF + (b + rng.random()) * spacing
            if rng.random() > keep:
                continue
            z, nz = surface(x, y)
            if z is None or not clear_of_features(x, y, z, 2 if name == "grass_tuft" else 5):
                continue
            if not test(weights(x, y), x, y, z, nz):
                continue
            i, j = int((x + HALF) // CHUNK), int((y + HALF) // CHUNK)
            yaw, s = rng.uniform(0, 2 * math.pi), rng.uniform(s0, s1)
            # three.js coords: (x, z, -y)
            placed.setdefault(f"{i}_{j}", {}).setdefault(name, []).extend(
                [round(x, 2), round(z - 0.15 * s, 2), round(-y, 2), round(yaw, 3), round(s, 3)])
            n += 1
    counts[name] = n

with open(f"{OUT_DIR}/props.json", "w") as fh:
    json.dump({"chunkSize": CHUNK, "chunks": NCH, "half": HALF, "stride": 5, "types": PROP_TYPES, "placements": placed}, fh, separators=(",", ":"))
export(prop_objs, f"{OUT_DIR}/props.glb")
prop_tris = {}
for o in prop_objs:
    o.data.calc_loop_triangles()
    prop_tris[o.name] = len(o.data.loop_triangles)
print(f"terrain: props={counts} prop_tris={prop_tris}", flush=True)

# ------------------------------------------------------------------ map image (top-down, north up, 2400 m square)
sc = bpy.context.scene
for o in sc.objects:
    o.hide_render = not (o.name.endswith("__lod0"))
cam_data = bpy.data.cameras.new("MapCam")
cam = bpy.data.objects.new("MapCam", cam_data)
sc.collection.objects.link(cam)
cam_data.type, cam_data.ortho_scale, cam_data.clip_end = "ORTHO", 2 * HALF, 5000
cam.location, cam.rotation_euler = (0, 0, 2500), (0, 0, 0)
sc.camera = cam
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "VERTEX"
sc.display.shading.show_shadows = False
sc.display.shading.show_cavity = True
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.render.filepath = f"{OUT_DIR}/map.png"
bpy.ops.render.render(write_still=True)
result = {"chunks": len(chunk_faces), "tris": tri_totals, "bytes": sizes, "props": counts}
