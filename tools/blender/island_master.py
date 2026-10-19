# Master island terrain: ONE continuous 2400 x 2400 m mesh (no chunks), clay/toy look, vertex colors only.
#   node tools/blender/headless.mjs tools/blender/island_master.py [PREVIEW_PATH=x.png] [BLEND_PATH=x.blend] [GRID_N=86]
# Blender coords: X east, Y north, Z up, sea level z = 0. Quadrants: NW snow + frozen lake, NE red desert + mesas,
# SW sunset beach + ocean, SE forest + S-shaped river gorge. A recessed road loop links all four.
# The mesh is a coarse grid Delaunay-triangulated together with constraint lines along road edges, river banks,
# the lake shore and the coastline, so those features get clean edges while the total stays ~20k triangles.
import bpy, bmesh, math, random
from mathutils import Vector, noise, kdtree
from mathutils.geometry import delaunay_2d_cdt

HALF = 1200.0
GRID_N = int(globals().get("GRID_N", "86"))      # grid quads per side before feature lines are added
SEA_FLOOR = -14.0
LAKE_C, LAKE_R, LAKE_Z = Vector((-680.0, 700.0)), 230.0, 45.0
COAST = 880.0                                    # coast distance from the SW corner (elliptical, noise-warped)
RIVER_BED, RIVER_W0, RIVER_W1 = -18.0, 16.0, 50.0
ROAD_SHOULDER = 16.0
LOOP_HW, SPUR_HW = 5.0, 4.0     # road half widths (m): 10 m asphalt/dirt loop, 8 m dirt trails

PAL = {"snow": "#EBF2FA", "ice": "#4EE3E3", "terracotta": "#C85A32", "desert_sand": "#E8A868",
       "beach": "#F2D492", "forest": "#60993E", "cliff": "#825234", "asphalt": "#3A3D40", "dirt": "#966844"}


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return Vector([v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c])


C = {k: lin(v) for k, v in PAL.items()}


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def sstep(a, b, x):
    t = clamp01((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def n2(x, y, s, seed):
    return noise.noise(Vector((x / s + seed * 17.31, y / s - seed * 9.17, seed * 3.7)))


def fbm(x, y, s, octaves, seed):
    v, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        v += amp * n2(x, y, s / 2 ** o, seed + o * 0.37)
        tot += amp
        amp *= 0.5
    return v / tot


# ------------------------------------------------------------------ paths (Catmull-Rom)
def spline(points, step, closed):
    pts = [Vector(p) for p in points]
    n = len(pts)
    out = []
    for i in range(n if closed else n - 1):
        p0 = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        p1, p2 = pts[i], pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed else pts[min(i + 2, n - 1)]
        k = max(2, int((p2 - p1).length / step))
        for j in range(k):
            t = j / k
            t2, t3 = t * t, t * t * t
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(pts[-1])
    return out


def normals(samples, closed):
    n = len(samples)
    out = []
    for i in range(n):
        a = samples[(i - 1) % n] if closed or i > 0 else samples[i]
        b = samples[(i + 1) % n] if closed or i < n - 1 else samples[i]
        t = (b - a).normalized()
        out.append(Vector((-t.y, t.x)))
    return out


ROAD_LOOP = [(-400, -200), (-150, 200), (60, 700), (420, 620), (600, 150), (450, -330), (100, -560), (-200, -500)]
SPURS = [[(420, 620), (700, 690), (860, 650)],          # dirt trail between the mesas
         [(-400, -200), (-500, -280), (-580, -330)]]    # dirt trail down to the beach
RIVER = [(1260, -400), (1000, -380), (840, -500), (900, -690), (780, -850), (590, -790), (500, -640), (330, -700),
         (250, -880), (120, -1010), (-60, -1080), (-260, -1130), (-420, -1260)]

river_s = spline(RIVER, 4.0, False)
river_kd = kdtree.KDTree(len(river_s))
for i, p in enumerate(river_s):
    river_kd.insert((p.x, p.y, 0), i)
river_kd.balance()


# ------------------------------------------------------------------ biome height fields
def weights(x, y, soft=140):
    wx = sstep(-soft, soft, x + 300 * n2(x, y, 320, 1) + 70 * n2(x, y, 110, 12))
    wy = sstep(-soft, soft, y + 300 * n2(x, y, 320, 2) + 70 * n2(x, y, 110, 13))
    return {"snow": (1 - wx) * wy, "desert": wx * wy, "beach": (1 - wx) * (1 - wy), "forest": wx * (1 - wy)}


def lake_reff(x, y):
    d = Vector((x, y)) - LAKE_C
    th = math.atan2(d.y, d.x)
    return d.length / (1 + 0.15 * math.sin(3 * th + 1) + 0.08 * math.sin(5 * th + 2))


rnd = random.Random(11)
SNOW_PEAKS = []
for k in range(30):
    a = 2 * math.pi * k / 30 + rnd.uniform(-0.2, 0.2)
    rr = rnd.uniform(320, 620)
    SNOW_PEAKS.append((LAKE_C.x + rr * math.cos(a), LAKE_C.y + rr * math.sin(a), rnd.uniform(45, 110), rnd.uniform(55, 95)))


def snow_h(x, y):
    r = (Vector((x, y)) - LAKE_C).length + 35 * n2(x, y, 250, 3)
    h = 50 + 60 * math.exp(-((r - 450) / 180) ** 2)
    for px, py, ph, ps in SNOW_PEAKS:
        h += ph * math.exp(-((x - px) ** 2 + (y - py) ** 2) / (2 * ps * ps))
    h += 30 * sstep(600, 1150, max(-x, y)) + 12 * fbm(x, y, 140, 2, 4)
    h = lerp(30, h, sstep(-60, 380, min(-x, y) + 120 * n2(x, y, 300, 14)))   # foothills toward the other biomes
    return lerp(LAKE_Z, h, sstep(LAKE_R, LAKE_R + 80, lake_reff(x, y)))


MESAS = [(870, 920, 280, 210, 75), (1010, 420, 190, 230, 62), (500, 1060, 210, 140, 52)]


def dune(x, y):
    return math.sin((x * 0.6 + y * 0.8) / 95 + 2.2 * n2(x, y, 300, 5))


def mesa_t(x, y):
    best = 0.0
    for mx, my, rx, ry, _ in MESAS:
        r = math.hypot((x - mx) / rx, (y - my) / ry) + 0.12 * n2(x, y, 120, 6)
        t = sstep(1.5, 0.7, r)
        best = max(best, 0.5 * sstep(0.0, 0.45, t) + 0.5 * sstep(0.55, 1.0, t))   # two soft terraces
    return best


def desert_h(x, y):
    h = 32 + 15 * dune(x, y) + 10 * fbm(x, y, 220, 3, 6)
    for mx, my, rx, ry, top in MESAS:
        r = math.hypot((x - mx) / rx, (y - my) / ry) + 0.12 * n2(x, y, 120, 6)
        t = sstep(1.5, 0.7, r)
        t = 0.5 * sstep(0.0, 0.45, t) + 0.5 * sstep(0.55, 1.0, t)
        h = lerp(h, 28 + top, t)
    return h


def coast_val(x, y):
    dc = 0.85 * math.hypot(x + HALF, y + HALF) + 70 * n2(x, y, 300, 7) + 25 * n2(x, y, 90, 8)
    return dc - COAST


def beach_h(x, y):
    c = coast_val(x, y)
    if c < 0:
        return SEA_FLOOR * sstep(0, -350, c) + 1.2 * n2(x, y, 60, 9) * sstep(0, -60, c)
    t = clamp01(c / 600)
    return 30 * t ** 1.2 + 5.0 * math.sin(c / 60) * t     # gentle shelf with soft terraced ridges


def forest_h(x, y):
    return 50 + 55 * fbm(x, y, 240, 4, 9) + 14 * n2(x, y, 90, 10)


def base_h(x, y):
    w = weights(x, y, 45)
    h = 0.0
    for k, fn in (("snow", snow_h), ("desert", desert_h), ("beach", beach_h), ("forest", forest_h)):
        if w[k] > 1e-4:
            h += w[k] * fn(x, y)
    return h


def river_carve(x, y, h):
    _, i, d = river_kd.find((x, y, 0))
    s = sstep(RIVER_W1, RIVER_W0, d)
    return lerp(h, min(h, RIVER_BED), s) if s > 0 else h


# ------------------------------------------------------------------ roads (height profile smoothed along the path)
def smooth_along(vals, win, closed, passes=3):
    n = len(vals)
    for _ in range(passes):
        out = []
        for i in range(n):
            acc, cnt = 0.0, 0
            for j in range(i - win, i + win + 1):
                if closed:
                    acc += vals[j % n]
                    cnt += 1
                elif 0 <= j < n:
                    acc += vals[j]
                    cnt += 1
            out.append(acc / cnt)
        vals = out
    return vals


roads = []   # (samples, heights, half_width, kind_per_sample, closed)
loop_s = spline(ROAD_LOOP, 4.0, True)
loop_h = smooth_along([max(2.0, river_carve(p.x, p.y, base_h(p.x, p.y))) for p in loop_s], 25, True)
loop_h = [h - 1.0 for h in loop_h]   # recessed 1 m into the surrounding ground
roads.append((loop_s, loop_h, LOOP_HW, ["asphalt" if p.x > -30 and p.y < 30 else "dirt" for p in loop_s], True))
loop_kd = kdtree.KDTree(len(loop_s))
for i, p in enumerate(loop_s):
    loop_kd.insert((p.x, p.y, 0), i)
loop_kd.balance()
for pts in SPURS:
    s = spline(pts, 4.0, False)
    h = smooth_along([max(2.0, river_carve(p.x, p.y, base_h(p.x, p.y))) - 1.0 for p in s], 20, False)
    _, j0, _ = loop_kd.find((s[0].x, s[0].y, 0))
    delta, fade = loop_h[j0] - h[0], 30
    h = [v + delta * (1 - min(i, fade) / fade) for i, v in enumerate(h)]
    roads.append((s, h, SPUR_HW, ["dirt"] * len(s), False))

road_meta = []
for samples, hs, w, kinds, closed in roads:
    for p, h, k in zip(samples, hs, kinds):
        if closed or loop_kd.find((p.x, p.y, 0))[2] > LOOP_HW + 4:   # the loop owns the junction area
            road_meta.append((p, h, w, k))
road_kd = kdtree.KDTree(len(road_meta))
for i, (p, *_rest) in enumerate(road_meta):
    road_kd.insert((p.x, p.y, 0), i)
road_kd.balance()


def height(x, y):
    h = river_carve(x, y, base_h(x, y))
    _, i, d = road_kd.find((x, y, 0))
    _, rh, w, _ = road_meta[i]
    s = sstep(w + ROAD_SHOULDER, w, d)
    return lerp(h, rh, s) if s > 0 else h


# ------------------------------------------------------------------ constraint lines + grid
cverts, cedges = [], []


def inside(p, m=1.0):
    return abs(p.x) < HALF - m and abs(p.y) < HALF - m


def add_line(points, closed):
    idx = []
    for p in points:
        if inside(p):
            cverts.append(Vector((p.x, p.y)))
            idx.append(len(cverts) - 1)
        else:
            idx.append(None)
    n = len(idx)
    for i in range(n if closed else n - 1):
        a, b = idx[i], idx[(i + 1) % n]
        if a is not None and b is not None:
            cedges.append((a, b))


def offset_lines(samples, closed, offsets, stride, skip=None):
    nrm = normals(samples, closed)
    keep = [i for i in range(0, len(samples), stride) if not (skip and skip(samples[i]))]
    for off in offsets:
        add_line([samples[i] + nrm[i] * off for i in keep], closed and skip is None)


for k, (samples, _, w, _, closed) in enumerate(roads):
    near_loop = None
    if not closed:   # spur lines start once clear of the loop corridor
        near_loop = lambda p: loop_kd.find((p.x, p.y, 0))[2] < LOOP_HW + ROAD_SHOULDER + 10
    offset_lines(samples, closed, (-w, w, -(w + 3), w + 3, -(w + ROAD_SHOULDER), w + ROAD_SHOULDER), 4, near_loop)
offset_lines(river_s, False, (-RIVER_W0, RIVER_W0, -33, 33, -RIVER_W1, RIVER_W1), 5)
for rr in (LAKE_R, LAKE_R + 40):
    pts = []
    for i in range(110):
        th = 2 * math.pi * i / 110
        g = 1 + 0.15 * math.sin(3 * th + 1) + 0.08 * math.sin(5 * th + 2)
        pts.append(LAKE_C + Vector((math.cos(th), math.sin(th))) * rr * g)
    add_line(pts, True)
SHORE_BAND = 35.0   # sand -> water color band between the coastline and a parallel line out at sea
for level in (0.0, -SHORE_BAND):
    coast = []
    for i in range(85):
        phi = math.radians(2 + 86 * i / 84)
        d = Vector((math.cos(phi), math.sin(phi)))
        corner = Vector((-HALF, -HALF))
        lo, hi = 200.0, 2000.0
        for _ in range(40):
            mid = (lo + hi) / 2
            p = corner + d * mid
            if coast_val(p.x, p.y) < level:
                lo = mid
            else:
                hi = mid
        coast.append(corner + d * lo)
    add_line(coast, False)

step = 2 * HALF / GRID_N
grid = []
for i in range(GRID_N + 1):
    for j in range(GRID_N + 1):
        p = Vector((-HALF + i * step, -HALF + j * step))
        edge = i in (0, GRID_N) or j in (0, GRID_N)
        if not edge:
            _, ri, rd = road_kd.find((p.x, p.y, 0))
            if rd < road_meta[ri][2] + ROAD_SHOULDER + 8:
                continue
            if river_kd.find((p.x, p.y, 0))[2] < RIVER_W1 + 8:
                continue
            lr = lake_reff(p.x, p.y)
            if LAKE_R - 10 < lr < LAKE_R + 50:
                continue
            if -SHORE_BAND - 9 < coast_val(p.x, p.y) < 9:
                continue
        grid.append(p)

all_pts = grid + cverts
off = len(grid)
vco, _, faces, _, _, _ = delaunay_2d_cdt(all_pts, [(a + off, b + off) for a, b in cedges], [], 0, 0.5)

# ------------------------------------------------------------------ mesh
for o in list(bpy.data.objects):
    if o.name.startswith("Island_Master"):
        bpy.data.objects.remove(o, do_unlink=True)
bm = bmesh.new()
bv = [bm.verts.new((v.x, v.y, height(v.x, v.y))) for v in vco]
for f in faces:
    try:
        bm.faces.new([bv[i] for i in f])
    except ValueError:
        pass
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
bm.normal_update()
for f in bm.faces:
    if f.normal.z < 0:
        f.normal_flip()
bm.normal_update()
for f in bm.faces:
    f.smooth = True
sharp = 0
for e in bm.edges:   # Smooth by Angle 35 deg
    if e.is_manifold and e.calc_face_angle() > math.radians(35):
        e.smooth = False
        sharp += 1


def vertex_color(v):
    x, y, z = v.co
    slope = 1 - max(0.0, v.normal.z)
    w = weights(x, y, 45)
    mt = mesa_t(x, y)
    flank = sstep(0.0, 0.2, mt) * (1 - sstep(0.8, 0.97, mt))   # red mesa sides, sandy flat tops
    desert = C["desert_sand"].lerp(C["terracotta"], clamp01(max(sstep(0.10, 0.30, slope), flank,
                                                                0.75 * sstep(0.1, -0.7, dune(x, y)) * (1 - mt))))
    forest = C["forest"].lerp(C["cliff"], sstep(0.3, 0.5, slope))
    beach = C["beach"]
    snow = C["snow"]
    c = snow * w["snow"] + desert * w["desert"] + beach * w["beach"] + forest * w["forest"]
    if lake_reff(x, y) <= LAKE_R + 1 and abs(z - LAKE_Z) < 1.0:
        c = C["ice"]
    elif z < -0.05 and (w["beach"] < 0.5 or coast_val(x, y) < -SHORE_BAND + 1):
        c = C["ice"]          # sea + river water (turquoise)
    _, i, d = road_kd.find((x, y, 0))
    _, _, rw, kind = road_meta[i]
    s = sstep(rw + 3.0, rw, d)
    if s > 0:
        c = c.lerp(C[kind], s)
    return c


me = bpy.data.meshes.new("Island_Master")
cols = [vertex_color(v) for v in bm.verts]
bm.to_mesh(me)
bm.free()
attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
attr.data.foreach_set("color", [c for col in cols for c in (col.x, col.y, col.z, 1.0)])
me.color_attributes.active_color = attr
me.color_attributes.render_color_index = me.color_attributes.active_color_index

mat = bpy.data.materials.get("M_Terrain_Clay") or bpy.data.materials.new("M_Terrain_Clay")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes.get("Principled BSDF")
vc = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeVertexColor"), None) or nt.nodes.new("ShaderNodeVertexColor")
vc.layer_name = "Col"
nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.5
bsdf.inputs["Metallic"].default_value = 0.0
me.materials.append(mat)

obj = bpy.data.objects.new("Island_Master", me)
bpy.context.scene.collection.objects.link(obj)
obj.location = (0, 0, 0)
with bpy.context.temp_override(active_object=obj, object=obj, selected_objects=[obj], selected_editable_objects=[obj]):
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

me.calc_loop_triangles()
zs = [v.co.z for v in me.vertices]
xs = [v.co.x for v in me.vertices]
ys = [v.co.y for v in me.vertices]
stats = {"tris": len(me.loop_triangles), "verts": len(me.vertices), "sharp_edges": sharp,
         "x": [round(min(xs), 1), round(max(xs), 1)], "y": [round(min(ys), 1), round(max(ys), 1)],
         "z": [round(min(zs), 1), round(max(zs), 1)]}
print("terrain: island " + str(stats), flush=True)


# ------------------------------------------------------------------ preview render + save
def preview(path):
    sc = bpy.context.scene
    sun_data = bpy.data.lights.new("IslandSun", "SUN")
    sun_data.energy, sun_data.angle, sun_data.color = 4.5, math.radians(6), (1.0, 0.94, 0.85)
    sun = bpy.data.objects.new("IslandSun", sun_data)
    sc.collection.objects.link(sun)
    sun.rotation_euler = Vector((0.6, -0.5, -0.42)).to_track_quat("-Z", "Y").to_euler()
    cam_data = bpy.data.cameras.new("IslandCam")
    cam_data.lens, cam_data.clip_end = 40, 20000
    cam = bpy.data.objects.new("IslandCam", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (0, -2750, 2500)
    cam.rotation_euler = (Vector((0, 80, 0)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    if sc.world is None:
        sc.world = bpy.data.worlds.new("IslandWorld")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = tuple(lin("#F3E6CC")) + (1.0,)
    bg.inputs[1].default_value = 0.35
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1050
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


if globals().get("BLEND_PATH"):
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
if globals().get("GLB_PATH"):   # Draco-compressed, vertex colors as COLOR_0
    import os
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=GLB_PATH, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_normals=True, export_texcoords=False, export_tangents=False, export_cameras=False,
              export_lights=False, export_animations=False, export_materials="EXPORT", export_vertex_color="ACTIVE",
              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
              export_draco_position_quantization=16, export_draco_normal_quantization=10,
              export_draco_color_quantization=10)
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})
    stats["glb_bytes"] = os.path.getsize(GLB_PATH)
if globals().get("PREVIEW_PATH"):
    preview(PREVIEW_PATH)
    if globals().get("TOP_PATH"):   # orthographic map view, north up
        cam = bpy.context.scene.camera
        cam.data.type, cam.data.ortho_scale = "ORTHO", 2450
        cam.location, cam.rotation_euler = (0, 0, 3000), (0, 0, 0)
        bpy.context.scene.render.resolution_x = bpy.context.scene.render.resolution_y = 1024
        bpy.context.scene.render.filepath = TOP_PATH
        bpy.ops.render.render(write_still=True)
result = {"island": stats}
