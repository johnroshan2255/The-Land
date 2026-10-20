# Game build of the master island: chunked, faceted, LOD'd terrain + scattered props + obstacles + map image.
# Runs after lib.py, the camp/structure builders and island_master.py in the same Blender process (reuses the
# height/biome/road/river functions and the prop builders):
#   node tools/blender/headless.mjs tools/blender/lib.py tools/blender/camp.py tools/blender/structures.py \
#     tools/blender/island_master.py tools/blender/island_chunks.py MODE=library CLAY=0 GRID_N=200 \
#     OUT_DIR=models/terrain/game SRC_DIR=models/terrain/source
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
    amp = 2.4 * w4["snow"] + 1.9 * w4["desert"] + 1.6 * w4["beach"] + 1.6 * w4["forest"]   # sand humps + dune ripples (refs 06/09)
    return amp * (1 - road) * (1 - river)


def relief(x, y, z):
    a = 0.6 * relief_amp(x, y, z)   # soft, broad facets (the refs read as big gentle planes, not crumpled paper)
    # plus rolling mounds ~80 m across: gentle rises and dips that catch the sun (refs 06/09) on otherwise flat ground
    return a * (0.75 * n2(x, y, 34, 31) + 0.25 * n2(x, y, 14, 32) + 2.2 * n2(x, y, 80, 33)) if a else 0.0


# Game color theme. These are vertex colours chosen so that, after the game's warm sun + sky light and tone mapping,
# the rendered surfaces match colours measured from the reference images (median sunlit pixels: grass #8A973D, dirt
# road #9A5736, snow road #ADBFD1, snow #E6E1E0, sand #E6A75D). The warm light removes much of the blue, so several
# of these look cooler/greyer here than on screen. (The master mesh keeps the original spec palette.)
THEME = {"snow": "#F3F6FF", "ice": "#8FE3EA", "terracotta": "#D9733F", "desert_sand": "#F0BE74", "beach": "#F3D597",
         "forest": "#94B45E", "cliff": "#A06C45", "asphalt": "#5B5E64", "dirt": "#9F6F55",
         "snow_track": "#ADC6E4", "desert_track": "#B68460", "beach_track": "#CDA58E", "snow_rock": "#A7A3AC"}
GRASS_DARK, GRASS_LIGHT = lin("#76A048"), lin("#B2CC6C")   # meadow patches, fresh green like refs 02-04
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
    # erosion tint: carved gullies expose red rock in the desert and grey rock in the snow, and are darker grass;
    # sediment fans are a touch lighter (refs 04/09: shades that follow the rises and dips)
    if road_info(x, y)[0] > road_info(x, y)[1] + 1:
        carve = clamp01(-erosion_at(x, y) / 6.0)
        fan = clamp01(erosion_at(x, y) / 4.0)
        c = c.lerp(C["terracotta"], 0.45 * carve * w4["desert"]).lerp(C["snow_rock"], 0.5 * carve * w4["snow"])
        c = c * (1.0 - 0.18 * carve * (w4["forest"] + w4["beach"]) + 0.06 * fan)
    if z < -0.05 and lake_reff(x, y) > LAKE_R + 1:   # sea + river floor: sand in the shallows, teal in the deep
        c = SHALLOW.lerp(DEEP, sstep(-0.3, -9.0, z))
    v[col_layer] = (c.x, c.y, c.z, 1.0)

# one color per face: average of its vertex colors, +-2.5% value jitter, a little darker on steep faces
def on_road(v):
    d, w = road_info(v.co.x, v.co.y)
    return d <= w + 0.5


# A face is road only if all its corners are on the road; faces straddling the edge take the ground colour of their
# off-road corners. The road edge then follows the edge constraint line exactly instead of a jagged blend band.
road_vert = [on_road(v) for v in bm.verts]
face_cols = []
for f in bm.faces:
    corners = [v for v in f.verts if not road_vert[v.index]] or list(f.verts)
    c = Vector((0, 0, 0))
    for v in corners:
        c += Vector(v[col_layer][:3])
    c /= len(corners)
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


# Road-local coordinates for the game's road shader (tyre ruts, darker edges, clay streaks): UV x = signed distance
# across the road in half-widths (-1..1 on the road surface, ROAD_UV_OFF elsewhere), UV y = metres along the road.
ROAD_UV_OFF = 4.0
# Highways (the loop + coast highway) are offset by +20 in UV x so the game can pave them with stone slabs.
HIGHWAY_UV = 20.0
road_frames = []   # (point, left normal, metres along, half width, uv x offset) for every road sample
for _s, _h, _w, _cls, _closed in roads:
    _n = normals(_s, _closed)
    road_frames += [(p, _n[k], 4.0 * k, _w, HIGHWAY_UV if _cls == "highway" else 0.0) for k, p in enumerate(_s)]
frame_kd = kdtree.KDTree(len(road_frames))
for _i, (p, *_rest) in enumerate(road_frames):
    frame_kd.insert((p.x, p.y, 0), _i)
frame_kd.balance()


def road_uv(x, y):
    if in_canyon(x, y):
        return (ROAD_UV_OFF, 0.0)   # trail-class 'off road' (no slabs under bridges)
    _, i, d = frame_kd.find((x, y, 0))
    p, n, along, w, cls_off = road_frames[i]
    across = (Vector((x, y)) - p).dot(n) / w
    if d > w + 0.5:   # off the road: keep the side, so a face spanning the edge never interpolates back across 0
        return (math.copysign(ROAD_UV_OFF, across) + cls_off, 0.0)   # (constant along-value compresses better)
    return (across + cls_off, along)


SHARP_ANGLE = math.radians(40)   # smooth shading (soft clay gradients) except across creases sharper than this


def smooth_with_creases(me, angle=SHARP_ANGLE):
    b = bmesh.new()
    b.from_mesh(me)
    for e in b.edges:
        e.smooth = not (e.is_manifold and e.calc_face_angle() > angle)
    for f in b.faces:
        f.smooth = True
    b.to_mesh(me)
    b.free()


def chunk_mesh(name, faces, center):
    verts, idx, polys, cols, uvs = [], {}, [], [], []
    for f in faces:
        poly = []
        for v in f.verts:
            if v.index not in idx:
                idx[v.index] = len(verts)
                verts.append((v.co.x - center.x, v.co.y - center.y, v.co.z))
                uvs.append(road_uv(v.co.x, v.co.y))
            poly.append(idx[v.index])
        polys.append(poly)
        cols.append(face_cols[f.index])
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], polys)
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", [c for l in me.loops for c in uvs[l.vertex_index]])
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
        smooth_with_creases(o.data)
        o.data.calc_loop_triangles()
        tri_totals[lod] += len(o.data.loop_triangles)
        lod_objs[lod].append(o)


def export(objs, path, terrain=False, normals=False):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_normals=terrain or normals, export_texcoords=terrain, export_tangents=False, export_cameras=False,
              export_lights=False, export_animations=False, export_materials="EXPORT", export_vertex_color="ACTIVE",
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
              export_draco_position_quantization=14, export_draco_color_quantization=8,
              export_draco_normal_quantization=10, export_draco_texcoord_quantization=14)
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})


sizes = {}
for lod in (0, 1, 2):
    for o in lod_objs[lod]:
        o.name = o.name.split("__")[0]   # node name "chunk_i_j" in every LOD file
    p = f"{OUT_DIR}/terrain_lod{lod}.glb"
    export(lod_objs[lod], p, terrain=True)   # terrain: smooth normals + road UVs; props stay flat-shaded
    sizes[f"lod{lod}"] = os.path.getsize(p)
    for o in lod_objs[lod]:
        o.name = o.name + f"__lod{lod}"
print(f"terrain: chunks={len(chunk_faces)} tris={tri_totals} bytes={sizes}", flush=True)

# ------------------------------------------------------------------ props (vertex-colored, flat, origin at base)
def rgb(h):
    return tuple(lin(h)) + (1.0,)


# Foliage greens. The game's warm sun + cool, weak sky fill turns these into a bright yellow-green lit side and a
# dark green shadow side per facet, like the reference pines (#B3AD33 lit, #293C0A in shade).
PINE_GREENS = ("#4E7A28", "#5C8A2C", "#6C9A32")   # bottom, middle, top tier
BUSH_GREENS = ("#6A8A30", "#7A9A36", "#5C7A2A")
TUFT_GREENS = ("#88B044", "#76A03C")


def build_prop(name):
    p = Part()
    if name in ("pine", "pine_snow"):
        p.cyl(rgb("#6E4630"), r=0.28, depth=1.4, seg=5, loc=(0, 0, 0.7))
        for k, (r, h, z) in enumerate(((2.3, 2.7, 1.1), (1.8, 2.3, 2.5), (1.2, 1.9, 3.7))):
            p.cone(rgb(PINE_GREENS[k]), r=r, depth=h, seg=7, loc=(0, 0, z + h / 2), rot=(0, 0, 25 * k))
            if name == "pine_snow":
                p.cone(rgb("#F3F7FB"), r=r * 0.93, depth=h * 0.78, seg=7, loc=(0, 0, z + h * 0.64), rot=(0, 0, 25 * k + 12))   # heavy snow load
    elif name in ("pine_far", "pine_snow_far"):
        p.cone(rgb(PINE_GREENS[1]), r=2.3, depth=5.4, seg=5, loc=(0, 0, 1.0 + 2.7))
        if name == "pine_snow_far":
            p.cone(rgb("#F3F7FB"), r=1.7, depth=3.6, seg=5, loc=(0, 0, 2.6 + 1.8), rot=(0, 0, 36))
    elif name in ("rock", "rock_snow"):
        p.ico(rgb("#7E766F" if name == "rock_snow" else "#A89A8A"), r=1.0, sub=1, loc=(0, 0, 0.35), scale=(1.5, 1.15, 0.85), jitter=0.12, seed=4)
        if name == "rock_snow":
            p.ico(rgb("#F1F5FA"), r=0.95, sub=1, loc=(0, 0, 0.62), scale=(1.35, 1.0, 0.45), jitter=0.06, seed=5)
    elif name == "bush":
        for k, (x, y, r) in enumerate(((0, 0, 0.9), (0.75, 0.3, 0.65), (-0.6, 0.45, 0.7))):
            p.ico(rgb(BUSH_GREENS[k]), r=r, sub=0, loc=(x, y, r * 0.7), jitter=0.08, seed=k)
    elif name == "grass_tuft":
        for k in range(5):
            a = 2 * math.pi * k / 5
            p.cone(rgb(TUFT_GREENS[k % 2]), r=0.09, depth=0.75, seg=3, loc=(0.16 * math.cos(a), 0.16 * math.sin(a), 0.33),
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


# ------------------------------------------------------------------ reference obstacles (refs 02-09)
# Camps (tents, campfire, caravan, lamp post, flag), wooden fences along road edges, kicker ramps on the desert tracks
# and boulder clusters. All but the boulders come from the procedural builders in camp.py / structures.py (run them
# before this script with MODE=library). The boulder cluster was generated with Hunyuan3D-2mv (local, shape only) from
# a masked crop of reference 04 (source/boulder_cluster_input.png -> run_mv.py -> colorize.py) and is decimated here.
# Low-poly for phones: the builders run at their LOD1 detail and the boulder is cut to ~BOULDER_TRIS triangles.
SRC_DIR = globals().get("SRC_DIR", os.path.join(os.path.dirname(OUT_DIR), "source"))
BOULDER_TRIS = 300
OBSTACLES = {   # prop type -> (builder function, LOD, extra builder args)
    "tent_orange": ("tent_orange", 1, {}), "tent_red": ("tent_red", 1, {}), "tent_blue": ("tent_blue", 1, {}),
    "campfire": ("campfire", 1, {}), "caravan": ("caravan_trailer", 1, {}), "lamp_post": ("lamp_post", 1, {}),
    "flag": ("flag_rainbow", 1, {}), "fence": ("fence_wood", 1, {}), "ramp": ("ramp_kicker", 1, {}),
    "picnic_table": ("picnic_table", 0, {}), "camp_chair": ("camp_chair", 0, {}), "crate": ("wooden_crate", 1, {}),
    "barrel": ("barrel", 1, {}), "signpost": ("signpost", 1, {}),
    "palm": ("tree_palm", 1, {}), "log": ("log", 0, {}), "stump": ("stump", 0, {}),
    "pillar": ("rock_pillar_red", 1, {}), "rock_red": ("rock_red", 1, {}),
    # play areas (refs 02-09): stunt park, tracks, beach, snow, canyon
    "stunt_loop": ("stunt_loop", 1, {}), "quarterpipe": ("ramp_quarterpipe", 1, {}), "wave_ramp": ("ramp_wave_big", 1, {}),
    "gate": ("gate_arch", 1, {}), "bridge": ("bridge_suspension", 1, {}), "dock": ("dock_pier", 1, {}),
    "boat": ("boat_small", 1, {}), "umbrella": ("beach_umbrella", 1, {}), "towel": ("beach_towel", 0, {}),
    "lift_tower": ("ski_lift_tower", 1, {}), "gondola": ("gondola_cabin", 1, {}), "ice_block": ("ice_block", 0, {}),
    "ramp_snow": ("ramp_snow", 1, {}), "ramp_log": ("ramp_log", 1, {}), "arch": ("rock_arch", 1, {}),
    "lift_station": ("lift_station", 1, {}), "gallery": ("snow_gallery", 1, {}),
    # parked cars (refs 02-09 show them at every camp): LOD1 body + wheels merged into one mesh
    "car_jeep": ("car_jeep_open", 1, {"color": "blue"}), "car_buggy": ("car_buggy", 1, {}),
    "car_van": ("car_van", 1, {}), "car_hatch": ("car_hatch", 1, {}),
}
CARS = ["car_jeep", "car_buggy", "car_van", "car_hatch"]


def ramp_snow(lod):
    """Packed-snow kicker for the snow park (ref 08): the stunt kicker in snow and ice."""
    p = Part()
    prof = kicker_profile(seg_for(lod, 8, 5, 3))
    p.prism("snow", prof, 4.4)
    for sx in (1, -1):
        p.prism("snow_shade", [(y, z + 0.1) for y, z in prof[1:-1]] + [(3.0, 0.0), (-3.0, 0.0)], 0.3, loc=(sx * 2.3, 0, 0))
    return p.finish("ramp_snow")


def ramp_log(lod):
    """Plank kicker on log rails for the forest trails (refs 02/03)."""
    p = Part()
    prof = kicker_profile(seg_for(lod, 8, 5, 3))
    p.prism("wood", prof, 4.0)
    for sx in (1, -1):
        p.cyl("trunk", 0.22, 6.4, 6, loc=(sx * 2.15, 0, 0.9), rot=(-18, 0, 0))
    return p.finish("ramp_log")


def rock_arch(lod):
    """Red sandstone arch (refs 04/09): two pillars and a lintel, 10 m opening you can drive through."""
    p = Part()
    for sx, col in ((-6.5, "red_rock"), (6.5, "red_rock_dark")):
        p.box(col, (3.2, 3.4, 10.0), loc=(sx, 0, 5.0), taper=(0.85, 0.9))
        p.ico("red_rock", 2.0, 0, loc=(sx, 0, 1.0), scale=(1.4, 1.3, 0.8), jitter=0.15, seed=int(sx))
    p.box("red_rock", (16.4, 3.6, 3.2), loc=(0, 0, 11.4))
    p.ico("red_rock_dark", 2.2, 0, loc=(-3.0, 0, 12.6), scale=(2.0, 1.0, 0.6), jitter=0.2, seed=7)
    p.ico("red_rock", 2.0, 0, loc=(3.5, 0, 12.5), scale=(1.8, 1.0, 0.6), jitter=0.2, seed=8)
    return p.finish("rock_arch")


def lift_station(lod):
    """Small ski-lift hut with a bull wheel (refs 08/09)."""
    p = Part()
    p.box("white", (5.0, 4.0, 3.0), loc=(0, 0, 1.5))
    p.box("gondola_red", (5.6, 4.6, 0.5), loc=(0, 0, 3.25), taper=(0.75, 0.75))
    p.box("glass_blue", (5.02, 2.4, 1.0), loc=(0, 0, 1.9))
    p.cyl("metal_dark", 2.4, 0.3, seg_for(lod, 12, 10, 8), loc=(0, 0, 4.2))
    p.cyl("metal_dark", 0.2, 1.0, 6, loc=(0, 0, 3.7))
    return p.finish("lift_station")


def snow_gallery(lod):
    """12 m timber snow-shed over a road cut (refs 02/05): posts on both sides and a snow-covered roof, open ends."""
    p = Part()
    for sx in (1, -1):
        for y in (-5.5, 0.0, 5.5):
            p.box("wood_dark", (0.5, 0.5, 5.0), loc=(sx * 5.6, y, 2.5))
        p.box("wood", (0.4, 12.0, 0.5), loc=(sx * 5.6, 0, 4.9))
    p.box("wood", (12.4, 12.0, 0.5), loc=(0, 0, 5.4))
    p.box("snow", (12.8, 12.4, 0.8), loc=(0, 0, 6.0), taper=(0.9, 0.95))
    return p.finish("snow_gallery")


def merged(root, name):
    """Join a builder's object tree (a car body + its wheel objects) into one flat-shaded mesh object."""
    bpy.context.view_layer.update()
    inv = root.matrix_world.inverted()
    bm = bmesh.new()
    parts = descendants(root)
    for o in parts:
        me = evaluated_copy(o)   # with the clay bevel modifiers applied
        me.transform(inv @ o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    remove(parts)
    o = bpy.data.objects.new(name, me)
    work_collection().objects.link(o)
    col = me.color_attributes.get("Col")
    if col:
        me.color_attributes.active_color = col
        me.color_attributes.render_color_index = me.color_attributes.active_color_index
    me.materials.append(vc_material())
    return o


CLAY_PROPS = set()   # man-made props built in the clay style (rounded bevels, smooth normals) like the hero car


def build_obstacle(name, spec, clay=True):
    """Builder -> one merged mesh. clay=True: the lib.py clay style (bevelled edges, smooth shading), like our car;
    clay=False: faceted (trees, rocks: the refs draw those with flat facets)."""
    global CLAY
    builder, lod, kw = spec
    CURRENT_LOD[0] = lod
    CLAY = clay
    o = merged(globals()[builder](lod, **kw), name)
    CLAY = False
    if clay:
        smooth_with_creases(o.data, math.radians(55))
        CLAY_PROPS.add(name)
    else:
        o.data.polygons.foreach_set("use_smooth", [False] * len(o.data.polygons))
    return o


def import_boulder(path, size=5.0):
    """Hunyuan mesh -> decimated, base at z=0, `size` m across, one linear colour per face in "Col"."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    o = next(o for o in new if o.type == "MESH")
    mw = o.matrix_world.copy()
    for x in new:
        if x is not o:
            bpy.data.objects.remove(x, do_unlink=True)
    o.parent = None
    o.data.transform(mw)
    o.matrix_world = Matrix()
    o.data.calc_loop_triangles()
    d = o.modifiers.new("Dec", "DECIMATE")
    d.ratio = min(1.0, BOULDER_TRIS / len(o.data.loop_triangles))
    me = evaluated_copy(o)
    o.modifiers.clear()
    o.data = me
    xs, ys, zs = zip(*[v.co[:] for v in me.vertices])
    k = size / max(max(xs) - min(xs), max(ys) - min(ys))
    off = Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, min(zs)))
    me.transform(Matrix.Diagonal((k, k, k, 1.0)) @ Matrix.Translation(-off))
    # colorize.py writes sRGB values into COLOR_0, which glTF readers take as linear: convert, then flatten per face
    src = me.color_attributes[0]
    per_vertex = src.domain == "POINT"
    to_lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    data = []
    for poly in me.polygons:
        acc = Vector((0, 0, 0))
        for li in poly.loop_indices:
            acc += Vector(src.data[me.loops[li].vertex_index if per_vertex else li].color[:3])
        c = [to_lin(v / poly.loop_total) for v in acc]
        data += (c + [1.0]) * poly.loop_total
    for a in list(me.color_attributes):
        me.color_attributes.remove(a)
    col = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    col.data.foreach_set("color", data)
    me.color_attributes.active_color = col
    me.color_attributes.render_color_index = me.color_attributes.active_color_index
    me.polygons.foreach_set("use_smooth", [False] * len(me.polygons))
    me.materials.clear()
    me.materials.append(vc_material())
    o.name = me.name = "boulder"
    return o


TERRAIN_C = C
C = {k: hexcol(v) for k, v in PAL_HEX.items()}   # the builders paint by lib.py colour names; island_master.py reused C
FACETED = {"palm", "log", "stump", "pillar", "rock_red", "ice_block", "arch"}
prop_objs += [build_obstacle(n, spec, clay=n not in FACETED) for n, spec in OBSTACLES.items()]
# exact drivable collision shapes for the curved / hollow structures (never drawn: they have no placements)
COL_SHAPES = {"stunt_loop_col": "stunt_loop_col", "quarterpipe_col": "ramp_quarterpipe_col", "wave_ramp_col": "ramp_wave_big_col",
              "bridge_col": "bridge_suspension_col", "dock_col": "dock_pier_col", "gate_col": "gate_arch_col"}
for n, b in COL_SHAPES.items():
    CURRENT_LOD[0] = 2
    prop_objs.append(merged(globals()[b](), n))
C = TERRAIN_C
prop_objs.append(import_boulder(f"{SRC_DIR}/boulder_cluster_hunyuan.glb"))
PROP_TYPES += list(OBSTACLES) + ["boulder"] + list(COL_SHAPES)
# far versions of the pines (one or two cones, ~10-20 triangles): the game swaps whole chunks to them past ~120 m
prop_objs += [build_prop("pine_far"), build_prop("pine_snow_far")]
PROP_TYPES += ["pine_far", "pine_snow_far"]


def road_samples(name):
    return roads[road_names.index(name)][0]


def other_roads_kd(name):
    k = road_names.index(name)
    return samples_kd([r for i, r in enumerate(roads) if i != k])


def road_frame(name, metres):
    """Point, unit tangent and left normal on a road, `metres` along it (negative = from the end)."""
    s = road_samples(name)
    k = int(metres / 4.0) if metres >= 0 else len(s) - 1 + int(metres / 4.0)
    k = max(0, min(len(s) - 2, k))
    t = (s[k + 1] - s[k]).normalized()
    return s[k], t, Vector((-t.y, t.x))


def flat_side(p, n, dist):
    """Side of the road (+1 / -1) where a spot `dist` away is flattest and dry."""
    best, side = None, 1
    for sd in (1, -1):
        c = p + n * sd * dist
        z, nz = surface(c.x, c.y)
        if z is None or z < 2 or river_kd.find((c.x, c.y, 0))[2] < RIVER_W1 + 15 or lake_reff(c.x, c.y) < LAKE_R + 40:
            continue
        rd, rw = road_info(c.x, c.y)
        if rd < rw + 20:   # too close to this or another road (junctions)
            continue
        score = sum(surface(c.x + dx, c.y + dy)[1] for dx, dy in ((0, 0), (8, 0), (-8, 0), (0, 8), (0, -8)))
        if best is None or score > best:
            best, side = score, sd
    return side


# (road, metres along it, distance from the road centre, kit). Each kit is laid out around a campfire.
CAMPS = [("river_bend", 420, 26, "forest"), ("forest_east", 340, 26, "forest"), ("forest_to_desert", 230, 26, "forest"),
         ("forest_south", 420, 26, "forest"), ("lake_road", 560, 24, "snow"), ("snow_north", 300, 24, "snow"),
         ("coast_highway", 320, 26, "beach"), ("desert_edge", 300, 26, "desert")]
CAMP_CLEAR = 17.0   # no trees/rocks this close to a camp centre
CAMP_EVERY, CAMP_GAP = 320.0, 150.0   # extra camps along every trail; minimum distance between two camps


def biome_kit(pt):
    w = weights(pt.x, pt.y)
    return max(("forest", "snow", "beach", "desert"), key=lambda k: w[k])


# the refs have a camp on nearly every trail: add one every CAMP_EVERY m, away from junctions and other camps
for k, (samples, _, w, cls, closed) in enumerate(roads):
    if cls != "trail":
        continue
    kd, pts = other_roads_kd(road_names[k])
    fixed = [road_frame(r, m)[0] for r, m, _, _ in CAMPS]
    for m in range(150, int(len(samples) * 4) - 100, int(CAMP_EVERY)):
        p, _, _ = road_frame(road_names[k], m)
        if kd.find((p.x, p.y, 0))[2] < 70 or any((p - q).length < CAMP_GAP for q in fixed):
            continue
        CAMPS.append((road_names[k], m, 26, biome_kit(p)))
        fixed.append(p)

camp_sites = []   # (centre, road point, road tangent, unit vector road -> camp, kit, road name, side)
for road, metres, dist, kit in CAMPS:
    p, t, n = road_frame(road, metres)
    side = flat_side(p, n, dist)
    camp_sites.append((p + n * side * dist, p, t, n * side, kit, road, side))
camp_centres = [c[0] for c in camp_sites]
KEEP_CLEAR = []   # extra spots kept free of scatter (set by the play-area layout below, before the scatter runs)


def sea_dir(pt):
    """Unit vector from land toward the sea at pt (down the coast_val gradient)."""
    e = 4.0
    g = Vector((coast_val(pt.x + e, pt.y) - coast_val(pt.x - e, pt.y), coast_val(pt.x, pt.y + e) - coast_val(pt.x, pt.y - e)))
    return -g.normalized()


def to_coast(pt, level):
    """Walk from pt along the sea direction to where coast_val == level."""
    q = Vector(pt)
    for _ in range(200):
        c = coast_val(q.x, q.y)
        if abs(c - level) < 0.5:
            break
        q += sea_dir(q) * (1.0 if c > level else -1.0) * min(4.0, abs(c - level))
    return q


# beach (refs 06/07): dock at the end of the beach trail, a wave-slide ramp beside it, umbrellas along the sand
_bt = road_samples("beach_trail")[-1]
DOCK = to_coast(_bt, 1.0)
DOCK_DIR = sea_dir(DOCK)
WAVE = to_coast(DOCK + Vector((-DOCK_DIR.y, DOCK_DIR.x)) * 45, 22.0)
LIFT_TOP = SUMMIT + (LIFT_BASE - SUMMIT).normalized() * 16
CANYON_JUMP = road_samples("jump_spur")[-1]
_, _ji, _ = river_kd.find((CANYON_JUMP.x, CANYON_JUMP.y, 0))
CANYON_PT = river_s[_ji]
ARCHES = [Vector((950, 170)), Vector((250, 1120)), Vector((1120, 760))]
KEEP_CLEAR += [DOCK, WAVE, LIFT_BASE, LIFT_TOP, CANYON_JUMP] + ARCHES


def clear_of_features(x, y, z, margin):
    d, w = road_info(x, y)
    if d < w + ROAD_SHOULDER * 0.5 + margin:
        return False
    if river_kd.find((x, y, 0))[2] < RIVER_W1 + margin:
        return False
    if lake_reff(x, y) < LAKE_R + 20 + margin:
        return False
    if any((Vector((x, y)) - c).length < CAMP_CLEAR + margin for c in camp_centres):
        return False
    pad = pad_at(x, y)   # play areas, ponds and their blend rims stay clear
    if pad and pad[3] < pad[2] + 10 + margin:
        return False
    if jump_at(x, y) > 0.05 or any((Vector((x, y)) - q).length < 30 for q in KEEP_CLEAR):
        return False
    return z > 1.0


def clump(x, y):
    """Grove mask: > 0 inside the pine groves (~35% of the forest), < 0 in the open meadows you can drive across."""
    return n2(x, y, 150, 40) + 0.35 * n2(x, y, 45, 41) - 0.1


RULES = [   # (type, spacing m, keep probability, scale range, road margin m, test(w, x, y, z, nz)); a type may repeat
    ("pine", 6.5, 0.85, (1.0, 1.9), 1, lambda w, x, y, z, nz: w["forest"] > 0.5 and nz > 0.78 and clump(x, y) > 0.0),
    ("pine", 30, 0.45, (1.1, 2.0), 1, lambda w, x, y, z, nz: w["forest"] > 0.5 and nz > 0.8 and clump(x, y) <= 0.0),
    ("pine_snow", 8.5, 0.8, (1.0, 1.9), 1, lambda w, x, y, z, nz: w["snow"] > 0.55 and z < 260 and nz > 0.72 and clump(x, y) > 0.05),
    ("pine_snow", 32, 0.45, (1.0, 1.9), 1, lambda w, x, y, z, nz: w["snow"] > 0.55 and z < 260 and nz > 0.75 and clump(x, y) <= 0.05),
    ("rock", 28, 0.45, (0.5, 1.7), 3, lambda w, x, y, z, nz: w["snow"] < 0.4 and w["desert"] < 0.5 and nz > 0.6),
    ("rock_red", 30, 0.5, (0.6, 1.6), 3, lambda w, x, y, z, nz: w["desert"] > 0.5 and nz > 0.6),
    ("rock_snow", 22, 0.55, (0.5, 1.6), 3, lambda w, x, y, z, nz: w["snow"] > 0.5),
    ("bush", 10, 0.5, (0.7, 1.4), 1, lambda w, x, y, z, nz: (w["forest"] + 0.5 * w["beach"]) > 0.5 and nz > 0.8 and z > 3),
    ("grass_tuft", 5.5, 0.5, (0.8, 1.5), 0, lambda w, x, y, z, nz: (w["forest"] + 0.6 * w["beach"]) > 0.45 and nz > 0.85 and z > 2),
    ("cactus", 22, 0.5, (0.8, 1.4), 3, lambda w, x, y, z, nz: w["desert"] > 0.6 and nz > 0.85 and mesa_t(x, y) < 0.2),
    ("pillar", 85, 0.5, (0.5, 0.9), 8, lambda w, x, y, z, nz: w["desert"] > 0.7 and nz > 0.85 and mesa_t(x, y) < 0.3),
    ("palm", 30, 0.55, (0.9, 1.3), 3, lambda w, x, y, z, nz: w["beach"] > 0.6 and 15 < coast_val(x, y) < 260 and nz > 0.85),
    ("log", 40, 0.5, (0.8, 1.2), 3, lambda w, x, y, z, nz: w["forest"] > 0.6 and nz > 0.85),
    ("stump", 34, 0.5, (0.8, 1.3), 2, lambda w, x, y, z, nz: w["forest"] > 0.6 and nz > 0.85),
    ("boulder", 75, 0.4, (0.6, 1.2), 4, lambda w, x, y, z, nz: w["snow"] < 0.3 and nz > 0.8 and z > 2),
]
rng = random.Random(77)
placed = {}
counts = {}
for name, spacing, keep, (s0, s1), margin, test in RULES:
    n = 0
    steps = int(2 * HALF / spacing)
    for a in range(steps):
        for b in range(steps):
            x = -HALF + (a + rng.random()) * spacing
            y = -HALF + (b + rng.random()) * spacing
            if rng.random() > keep:
                continue
            z, nz = surface(x, y)
            if z is None or not clear_of_features(x, y, z, margin):
                continue
            if not test(weights(x, y), x, y, z, nz):
                continue
            i, j = int((x + HALF) // CHUNK), int((y + HALF) // CHUNK)
            yaw, s = rng.uniform(0, 2 * math.pi), rng.uniform(s0, s1)
            # three.js coords: (x, z, -y)
            placed.setdefault(f"{i}_{j}", {}).setdefault(name, []).extend(
                [round(x, 1), round(z - 0.15 * s, 2), round(-y, 1), round(yaw, 2), round(s, 2)])   # 10 cm is plenty
            n += 1
    counts[name] = counts.get(name, 0) + n


ON_ROAD_OK = {"ramp", "ramp_log", "gate", "gallery", "bridge"}   # built to stand on or span a road


def put(name, pos, yaw, s=1.0, sink=0.05, z=None):
    """Place one obstacle at a 2D Blender position on the ground (yaw about +Z, radians), or at height z. Never on a
    road surface unless built for it: camp kits and signposts near junctions would otherwise block the other road."""
    if z is None:
        z, _ = surface(pos.x, pos.y)
        if z is None:
            return
    else:
        sink = 0.0
    d, w = road_info(pos.x, pos.y)
    if name not in ON_ROAD_OK and d < w + 1.5:
        return
    i, j = int((pos.x + HALF) // CHUNK), int((pos.y + HALF) // CHUNK)
    placed.setdefault(f"{i}_{j}", {}).setdefault(name, []).extend(
        [round(pos.x, 2), round(z - sink, 2), round(-pos.y, 2), round(yaw, 3), round(s, 3)])   # exact: fences line up
    counts[name] = counts.get(name, 0) + 1


def facing(frm, to):
    """Yaw that turns a builder's +Y (tent door, caravan nose, ramp run-up) from `frm` toward `to`."""
    d = to - frm
    return math.atan2(-d.x, d.y)


def fence_run(road, m0, m1, side=None, extra=2.0):
    """Wooden fence segments (4 m, origin at the left post, run along +X) along a road edge from m0 to m1 metres.
    side None = the downhill side (sea, lake or valley), like a guard rail. Gaps where another road joins."""
    s = road_samples(road)
    w = roads[road_names.index(road)][2]
    kd, pts = other_roads_kd(road)
    k0, k1 = max(0, int(m0 / 4)), min(len(s) - 2, int(m1 / 4))
    nrm = normals(s, False)
    if side is None:
        drop = 0.0
        for k in range(k0, k1, 5):
            a = surface(*(s[k] + nrm[k] * (w + 10)))[0] or 0
            b = surface(*(s[k] - nrm[k] * (w + 10)))[0] or 0
            drop += a - b
        side = -1 if drop > 0 else 1
    off = w + extra
    for k in range(k0, k1):
        a, b = s[k] + nrm[k] * side * off, s[k + 1] + nrm[k + 1] * side * off
        _, i, d = kd.find((a.x, a.y, 0))
        if d < pts[i][2] + ROAD_SHOULDER:   # junction with another road: leave it open
            continue
        put("fence", a, math.atan2((b - a).y, (b - a).x), sink=0.15)


for (c, p, t, out, kit, road, side) in camp_sites:
    rng2 = random.Random(int(c.x * 7 + c.y * 13))
    put("campfire", c, rng2.uniform(0, 6.28))
    tents = {"forest": ("tent_orange", "tent_red", "tent_blue"), "snow": ("tent_orange", "tent_blue"),
             "beach": ("tent_red", "tent_orange"), "desert": ("tent_blue", "tent_orange")}[kit]
    base = math.atan2(-out.y, -out.x)   # angle pointing back toward the road
    for k, tent in enumerate(tents):
        a = base + math.radians(70 + 110 * k)
        pos = c + Vector((math.cos(a), math.sin(a))) * 6.5
        put(tent, pos, facing(pos, c))
    if kit in ("forest", "beach", "desert"):
        put("caravan", c + out * 10.5 + t * 3, facing(Vector((0, 0)), t))
    # camp clutter (refs 02/07/08): parked car, picnic table, chairs or log seats round the fire, crates and barrels
    put(CARS[rng2.randrange(len(CARS))], c - out * 3 - t * 10, facing(Vector((0, 0)), t if rng2.random() < 0.5 else -t))
    put("picnic_table", c + t * 7 - out * 2, facing(Vector((0, 0)), out))
    for k in range(2):
        a = base + math.radians(-40 + 80 * k)
        pos = c + Vector((math.cos(a), math.sin(a))) * 2.6
        put("camp_chair" if kit in ("beach", "snow") else "log", pos, facing(pos, c) if kit in ("beach", "snow") else a)
    put("crate", c + out * 8 + t * 7, rng2.uniform(0, 6.28))
    put("barrel", c + out * 7 + t * 8.6, 0.0)
    put("lamp_post", c - out * 7 + t * 5, facing(c - out * 7, c))
    put("flag", p + out * (roads[0][2] + 5) - t * 9, facing(Vector((0, 0)), -out))
    m = 4.0 * road_samples(road).index(p)   # metres along the road; fence the roadside either side of the camp gap
    fence_run(road, m - 30, m - 6, side)
    fence_run(road, m + 6, m + 30, side)

# signposts where a trail leaves another road (24 m in, beside the road)
for k, (samples, _, w, cls, closed) in enumerate(roads):
    if closed or len(samples) < 10:
        continue
    kd, pts = other_roads_kd(road_names[k])
    nrm = normals(samples, False)
    for e, i in ((0, 6), (-1, len(samples) - 7)):
        if kd.find((samples[e].x, samples[e].y, 0))[2] < 6:
            pos = samples[i] + nrm[i] * (w + 3)
            put("signpost", pos, facing(Vector((0, 0)), samples[i + 1] - samples[i]))

# long guard-rail fences: coast highway (sea side), lake road and the snow road (valley side)
fence_run("coast_highway", 60, 640)
fence_run("lake_road", 160, 520)
fence_run("lake_road", 620, 980)
fence_run("snow_north", 40, 360)

# kicker ramps on the desert tracks, run-up along the direction of travel
for road, metres in (("desert_edge", 150), ("desert_edge", 420), ("mesa_trail", 230), ("forest_to_desert", -140)):
    p, t, _ = road_frame(road, metres)
    put("ramp", p, facing(Vector((0, 0)), t), sink=0.02)

# ------------------------------------------------------------------ play areas (refs 02-09)
def ring(c, r, n, start=0.0):
    return [(c + Vector((math.cos(start + 2 * math.pi * k / n), math.sin(start + 2 * math.pi * k / n))) * r, start + 2 * math.pi * k / n)
            for k in range(n)]


def pad_centre(name):
    n, x, y, r, k = next(q for q in PADS if q[0] == name)
    return Vector((x, y)), r


# stunt park: gate at the entrance, loop straight ahead, quarter-pipes on both sides, a kicker line, flags, fence
C0, R0 = pad_centre("stunt_park")
entry = road_samples("stunt_spur")[-1]
din = (C0 - entry).normalized()
side = Vector((-din.y, din.x))
put("gate", entry + din * 3, facing(Vector((0, 0)), din))
put("stunt_loop", C0 + din * 18 + side * 10, facing(Vector((0, 0)), din))
for sd in (1, -1):
    qp = C0 + side * sd * 36
    put("quarterpipe", qp, facing(C0, qp))
for k in range(3):
    put("ramp", C0 - side * 14 + din * (-18 + 16 * k), facing(Vector((0, 0)), din))
for pos, a in ring(C0, R0 - 2, 8, 0.3):
    put("flag", pos, a)
for k in range(28):   # fence the park, leaving the entrance open
    a0, a1 = 2 * math.pi * k / 28, 2 * math.pi * (k + 1) / 28
    pa = C0 + Vector((math.cos(a0), math.sin(a0))) * (R0 + 6)
    pb = C0 + Vector((math.cos(a1), math.sin(a1))) * (R0 + 6)
    if (pa - entry).length > 18:
        put("fence", pa, math.atan2((pb - pa).y, (pb - pa).x), sink=0.15)

# race tracks: start/finish gate, tyre-barrel markers on the inside of the turns, flags
for name in ("desert_oval", "desert_eight", "forest_pump"):
    smp = road_samples(name)
    w = roads[road_names.index(name)][2]
    nrm = normals(smp, True)
    if name != "forest_pump":
        put("gate", smp[2], facing(smp[1], smp[3]))
    for k in range(6, len(smp), 7):
        put("barrel", smp[k] + nrm[k] * (w + 1.5) * (1 if k % 2 else -1), 0.0)
    for k in range(0, len(smp), max(1, len(smp) // 4)):
        put("flag", smp[k] - nrm[k] * (w + 5), 0.0)
for road, metres in (("forest_far", 620), ("forest_south", 300), ("forest_west", 200), ("river_bend", 260), ("pump_spur", 40)):
    q, t, _ = road_frame(road, metres)
    put("ramp_log", q, facing(Vector((0, 0)), t), sink=0.02)

# oasis: palms and rocks round the pond
C1, R1 = pad_centre("oasis")
for pos, a in ring(C1, R1 + 6, 9, 0.2):
    put("palm", pos, a, 1.0 + 0.1 * math.sin(a * 3))
for pos, a in ring(C1, R1 + 14, 5, 0.9):
    put("rock_red", pos, a, 1.3)

# snow park: snow kickers, ice blocks, flags and a fence; ice blocks round the frozen ponds
C2, R2 = pad_centre("snow_park")
e2 = road_samples("snowpark_spur")[-1]
d2 = (C2 - e2).normalized()
s2 = Vector((-d2.y, d2.x))
for k, off in enumerate((-16, 0, 16)):
    put("ramp_snow", C2 + s2 * off + d2 * (4 if k == 1 else -6), facing(Vector((0, 0)), d2))
for pos, a in ring(C2, R2 - 4, 10, 0.4):
    put("ice_block", pos, a, 1.2)
for pos, a in ring(C2, R2 + 3, 6, 0.0):
    put("flag", pos, a)
for name in ("pond_north", "pond_west"):
    Cp, Rp = pad_centre(name)
    for pos, a in ring(Cp, Rp + 3, 9, 0.5):
        put("ice_block", pos, a, 1.0 + 0.3 * math.sin(a * 5))
    put("flag", Cp + Vector((Rp + 8, 0)), 0.0)

# summit lookout + ski lift: stations at both ends, towers every ~60 m, the cable runs over the tower tops
put("lift_station", LIFT_TOP, facing(LIFT_TOP, LIFT_BASE))
put("lift_station", LIFT_BASE, facing(LIFT_BASE, LIFT_TOP))
put("flag", SUMMIT + Vector((6, 6)), 0.0)
put("signpost", SUMMIT + Vector((-8, 4)), 0.0)
lift_pts = []
span = (LIFT_TOP - LIFT_BASE).length
n_towers = max(2, int(span / 60))
for k in range(n_towers + 1):
    q = LIFT_BASE.lerp(LIFT_TOP, k / n_towers)
    zt, _ = surface(q.x, q.y)
    if 0 < k < n_towers:
        put("lift_tower", q, facing(LIFT_BASE, LIFT_TOP))
    lift_pts.append([round(q.x, 2), round((zt or 0) + (11.6 if 0 < k < n_towers else 4.2), 2), round(-q.y, 2)])

# snow galleries where the summit road cuts deepest into the slope
smp = road_samples("summit_road")
hs = roads[road_names.index("summit_road")][1]
cut = sorted(((river_carve(q.x, q.y, base_h(q.x, q.y)) - h, k) for k, (q, h) in enumerate(zip(smp, hs)) if 8 < k < len(smp) - 8), reverse=True)
used = []
for depth, k in cut:
    if depth < 4 or len(used) >= 2:
        break
    if all(abs(k - u) > 25 for u in used):
        used.append(k)
        for j in (-3, 0, 3):   # three 12 m sections = a 36 m shed
            q = smp[k + j]
            put("gallery", q, facing(smp[k + j - 1], smp[k + j + 1]), z=hs[k + j])

# canyon: rope bridges where the roads cross, a canyon jump with a landing ramp on the far rim, two waterfalls
for a, b, hdeck in BRIDGES:
    put("bridge", (a + b) / 2, facing(a, b), (b - a).length / 48.0, z=hdeck)
jump_dir = (CANYON_PT - CANYON_JUMP).normalized()
put("ramp", CANYON_JUMP, facing(CANYON_JUMP, CANYON_PT), 1.3, sink=0.02)
landing = CANYON_PT + jump_dir * (RIVER_W1 + 10)
put("ramp", landing, facing(landing, CANYON_PT), 1.3, sink=0.02)
waterfalls = []
river_n = normals(river_s, False)
for frac, sd in ((0.22, 1), (0.5, -1)):
    k = int(frac * len(river_s))
    top = river_s[k] + river_n[k] * sd * (RIVER_W1 + 1)
    bot = river_s[k] + river_n[k] * sd * (RIVER_W0 * 0.7)
    zt, _ = surface(top.x, top.y)
    waterfalls.append({"top": [round(top.x, 2), round(zt or 0, 2), round(-top.y, 2)], "bottom": [round(bot.x, 2), 0.0, round(-bot.y, 2)], "width": 9})
    KEEP_CLEAR.append(top)

# beach: dock + boats, wave-slide ramp, umbrellas / towels / chairs, sea stacks in the surf
put("dock", DOCK, facing(Vector((0, 0)), DOCK_DIR), z=0.2)
for sd in (1, -1):
    put("boat", DOCK + DOCK_DIR * 9 + Vector((-DOCK_DIR.y, DOCK_DIR.x)) * sd * 4.5, facing(Vector((0, 0)), DOCK_DIR), z=-0.25)
put("wave_ramp", WAVE, facing(Vector((0, 0)), sea_dir(WAVE)))
rngb = random.Random(5)
for k in range(12):
    q = to_coast(DOCK + Vector((-DOCK_DIR.y, DOCK_DIR.x)) * rngb.uniform(-120, 120), rngb.uniform(18, 55))
    put("umbrella", q, rngb.uniform(0, 6.28))
    put("towel", q + Vector((2.2, 0.8)), rngb.uniform(0, 6.28))
    if k % 2:
        put("camp_chair", q + Vector((-1.8, 1.2)), rngb.uniform(0, 6.28))
for k in range(9):
    q = to_coast(DOCK + Vector((-DOCK_DIR.y, DOCK_DIR.x)) * (-260 + 65 * k), -rngb.uniform(18, 50))
    put("rock", q, rngb.uniform(0, 6.28), rngb.uniform(3.0, 5.5), z=-1.0)

# desert rock arches, with a pillar beside each
for q in ARCHES:
    put("arch", q, rngb.uniform(0, 6.28))
    put("pillar", q + Vector((14, 6)), rngb.uniform(0, 6.28), 0.8)

features = {"lift": lift_pts, "waterfalls": waterfalls}

with open(f"{OUT_DIR}/props.json", "w") as fh:
    json.dump({"chunkSize": CHUNK, "chunks": NCH, "half": HALF, "stride": 5, "types": PROP_TYPES, "placements": placed,
               "features": features, "clay": sorted(CLAY_PROPS)}, fh, separators=(",", ":"))
export(prop_objs, f"{OUT_DIR}/props.glb", normals=True)
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
