# Turn the Hunyuan3D car scan (source_models/hunyuan/car_hero_hunyuan_raw.glb, ~529k tris, untextured, on a base slab)
# into the game car. Run headless, one STEP at a time:
#   node tools/blender/headless.mjs tools/blender/hunyuan_car.py STEP=inspect OUT=<dir>
import bpy, bmesh, math, os, json
from mathutils import Vector, Matrix, Euler

SRC = r"C:/project/New Game/source_models/hunyuan/car_hero_hunyuan_raw.glb"
OUT = globals().get("OUT", r"C:/project/New Game/source_models/hunyuan")


def load_raw():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=SRC)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    sc = bpy.context.scene
    for o in new:
        if o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
    obj = new[0]
    # bake the import transform into the mesh so object space == world space
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    return obj


def ortho_render(path, direction, up=(0, 0, 1), res=900, objs=None):
    sc = bpy.context.scene
    objs = objs or [o for o in sc.objects if o.type == "MESH"]
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center, size = (lo + hi) / 2, (hi - lo).length
    cam = bpy.data.objects.get("InspectCam") or bpy.data.objects.new("InspectCam", bpy.data.cameras.new("InspectCam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    d = Vector(direction).normalized()
    cam.location = center + d * size * 2
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y" if abs(d.z) < 0.9 else "Y").to_euler()
    if abs(d.z) > 0.9:
        cam.rotation_euler = (0, 0, 0) if d.z > 0 else (math.pi, 0, 0)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = size * 0.85
    cam.data.clip_end = size * 10
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.show_cavity = True
    sc.display.shading.color_type = "OBJECT"
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def step_inspect():
    obj = load_raw()
    me = obj.data
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    zmin = min(zs)
    # height histogram near the bottom to find the slab top
    hist = {}
    for z in zs:
        b = round((z - zmin) / 0.01)
        if b <= 30:
            hist[b] = hist.get(b, 0) + 1
    os.makedirs(OUT, exist_ok=True)
    ortho_render(f"{OUT}/inspect_front_+y.png", (0, 1, 0.0001))
    ortho_render(f"{OUT}/inspect_side_+x.png", (1, 0, 0.0001))
    ortho_render(f"{OUT}/inspect_top.png", (0, 0, 1))
    return {"verts": len(me.vertices), "tris": sum(len(p.vertices) - 2 for p in me.polygons),
            "x": [round(min(xs), 3), round(max(xs), 3)], "y": [round(min(ys), 3), round(max(ys), 3)],
            "z": [round(zmin, 3), round(max(zs), 3)], "bottom_hist_per_cm": hist}


PREP_BLEND = f"{OUT}/car_hero_prep.blend"


def fit_wheel(me, cx, cz, side, r_guess=0.2):
    """Refine a wheel centre (x, z) and radius from tread vertices on one side (side = +1 / -1 along Y)."""
    pts = [v.co for v in me.vertices if side * v.co.y > 0.24 and abs(v.co.x - cx) < r_guess * 1.6 and v.co.z < cz + r_guess * 1.6]
    xs, zs = [p.x for p in pts], [p.z for p in pts]
    x0, z0 = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    r = max(max(xs) - min(xs), max(zs) - min(zs)) / 2
    ys = [p.y for p in pts]
    return x0, z0, r, min(ys, key=abs), max(ys, key=abs)


def step_prep():
    obj = load_raw()
    me = obj.data
    # 1. drop the base slab
    zmin = min(v.co.z for v in me.vertices)
    bm = bmesh.new()
    bm.from_mesh(me)
    cut = zmin + 0.028
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, cut), plane_no=(0, 0, 1), clear_inner=True)
    bm.to_mesh(me)
    bm.free()
    # 2. front (-X) -> +Y, ground at z=0, centred, scaled to 4.0 m long
    me.transform(Matrix.Rotation(math.radians(-90), 4, "Z"))
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    length = max(ys) - min(ys)
    s = float(globals().get("LENGTH", "4.0")) / length
    me.transform(Matrix.Diagonal((s, s, s, 1)) @ Matrix.Translation((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs))))
    me.update()
    # 3. find the wheels (after rotation the axles run along X; wheels sit at the four lower corners)
    vs = me.vertices
    ys = [v.co.y for v in vs]
    zs = [v.co.z for v in vs]
    zlow = min(zs) + (max(zs) - min(zs)) * 0.33
    wheels = {}
    for tag, sx, sy in (("FL", 1, 1), ("FR", -1, 1), ("RL", 1, -1), ("RR", -1, -1)):
        pts = [v.co for v in vs if sx * v.co.x > 0.45 and sy * v.co.y > 0.25 and v.co.z < zlow]
        px, py, pz = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
        cy, cz = (min(py) + max(py)) / 2, (min(pz) + max(pz)) / 2
        r = max(max(py) - min(py), max(pz) - min(pz)) / 2
        x_in, x_out = min(px, key=abs), max(px, key=abs)
        wheels[tag] = {"center": (round((x_in + x_out) / 2, 3), round(cy, 3), round(cz, 3)), "r": round(r, 3), "x_in": round(x_in, 3), "x_out": round(x_out, 3)}
    obj.name = obj.data.name = "car_hero_hi"
    bpy.ops.wm.save_as_mainfile(filepath=PREP_BLEND, copy=True)
    ortho_render(f"{OUT}/prep_side.png", (1, 0.0001, 0.0001))
    ortho_render(f"{OUT}/prep_front.png", (0.0001, 1, 0.0001))
    return {"scale": round(s, 3), "dims": [round(max(v.co.x for v in vs) - min(v.co.x for v in vs), 2), round(max(ys) - min(ys), 2), round(max(zs), 2)], "wheels": wheels}


SPLIT_BLEND = f"{OUT}/car_hero_split.blend"
WHEEL_GUESS = {"FL": (1, 1.06), "FR": (-1, 1.06), "RL": (1, -0.93), "RR": (-1, -0.93)}


def step_split():
    """Cut the 4 tires (+ rims/hubs) out of the scan into their own objects, origin at the axle."""
    bpy.ops.wm.open_mainfile(filepath=PREP_BLEND)
    hi = bpy.data.objects["car_hero_hi"]
    me = hi.data
    info = {}
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    for tag, (sx, ygs) in WHEEL_GUESS.items():
        # outer sidewall: only the tires reach past |x| = 1.6 m -> clean axle centre
        side = [v.co for v in bm.verts if sx * v.co.x > 1.6 and abs(v.co.y - ygs) < 0.9]
        yc = sum(p.y for p in side) / len(side)
        zc = sum(p.z for p in side) / len(side)
        # radius from the ground contact under that centre
        under = [v.co for v in bm.verts if sx * v.co.x > 0.95 and abs(v.co.y - yc) < 0.15 and v.co.z < zc]
        r = float(globals().get("WHEEL_CUT_R", "0.83"))  # tread bulges to ~0.8 m from the axle (measured)
        x_out = max((p.x for p in side), key=abs)
        info[tag] = {"center_yz": (round(yc, 3), round(zc, 3)), "r": round(r, 3), "x_out": round(x_out, 3)}
        info[tag]["sx"] = sx
    # RR sidewall is malformed in the scan: mirror RL (the car is symmetric)
    info["RR"]["center_yz"] = info["RL"]["center_yz"]
    wheel_faces = {tag: [] for tag in info}
    for f in bm.faces:
        c = f.calc_center_median()
        for tag, w in info.items():
            yc, zc = w["center_yz"]
            near_spring = abs(c.y - yc) < 0.3 and c.z > zc + 0.12 and w["sx"] * c.x < 0.97
            if w["sx"] * c.x > 0.8 and not near_spring and c.z < zc + 0.86 and math.hypot(c.y - yc, c.z - zc) < w["r"]:
                wheel_faces[tag].append(f)
                break
    created = {}
    for tag, faces in wheel_faces.items():
        wbm = bmesh.new()
        vmap = {}
        for f in faces:
            vs = []
            for v in f.verts:
                if v not in vmap:
                    vmap[v] = wbm.verts.new(v.co)
                vs.append(vmap[v])
            try:
                wbm.faces.new(vs)
            except ValueError:
                pass
        w = info[tag]
        xs = [v.co.x for v in wbm.verts]
        cx = (min(xs) + max(xs)) / 2
        center = Vector((cx, w["center_yz"][0], w["center_yz"][1]))
        bmesh.ops.translate(wbm, verts=wbm.verts, vec=-center)
        wme = bpy.data.meshes.new(f"car_hero_wheel_{tag}")
        wbm.to_mesh(wme)
        wbm.free()
        o = bpy.data.objects.new(f"car_hero_wheel_{tag}", wme)
        bpy.context.scene.collection.objects.link(o)
        o.location = center
        created[tag] = {"center": [round(c, 3) for c in center], "r": w["r"], "tris": len(wme.polygons)}
    bmesh.ops.delete(bm, geom=list({f for fs in wheel_faces.values() for f in fs}), context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    bpy.ops.wm.save_as_mainfile(filepath=SPLIT_BLEND, copy=True)
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.color = (0.85, 0.3, 0.25, 1) if o.name == "car_hero_hi" else (0.15, 0.15, 0.16, 1)
    ortho_render(f"{OUT}/split_side.png", (1, 0.0001, 0.0001))
    ortho_render(f"{OUT}/split_front34.png", (-0.8, 1, 0.6))
    return {"wheels": created, "body_tris": len(me.polygons)}


GAME_BLEND = f"{OUT}/car_hero_game.blend"


def decimate_to(obj, target_tris):
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    d = obj.modifiers.new("Decimate", "DECIMATE")
    d.ratio = min(1.0, target_tris / max(tris, 1))
    d.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    me.name = obj.name
    bpy.data.meshes.remove(old)
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.set_sharp_from_angle(angle=math.radians(float(globals().get("SHARP_ANGLE", "50"))))
    return sum(len(p.vertices) - 2 for p in me.polygons)


def studio(sc):
    """Warm key sun 45 deg (#FFF2DD), cool fill, cream background - same look as the reference."""
    for name, color, energy, rot, shadow in (("key", (1.0, 0.949, 0.867), 3.6, (45, 0, -140), True), ("fill", (0.72, 0.82, 1.0), 0.8, (60, 0, 30), False)):
        L = bpy.data.lights.get(name) or bpy.data.lights.new(name, "SUN")
        L.color, L.energy, L.angle, L.use_shadow = color, energy, math.radians(15), shadow
        o = bpy.data.objects.get(name) or bpy.data.objects.new(name, L)
        if o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
        o.rotation_euler = [math.radians(a) for a in rot]
    w = bpy.data.worlds.new("cream")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.905, 0.855, 0.71, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.75
    sc.world = w
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    sc.view_settings.view_transform = "AgX"


def persp_render(path, cam_loc, target=(0, 0, 1.6), lens=40, res=(1000, 800)):
    sc = bpy.context.scene
    cam = bpy.data.objects.get("ViewCam") or bpy.data.objects.new("ViewCam", bpy.data.cameras.new("ViewCam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = cam_loc
    cam.rotation_euler = (Vector(target) - Vector(cam_loc)).to_track_quat("-Z", "Y").to_euler()
    cam.data.type, cam.data.lens = "PERSP", lens
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def step_game():
    bpy.ops.wm.open_mainfile(filepath=SPLIT_BLEND)
    body = bpy.data.objects["car_hero_hi"]
    body.name = "car_hero_body"
    counts = {"body": decimate_to(body, int(globals().get("BODY_TRIS", "1900")))}
    for tag in ("FL", "FR", "RL", "RR"):
        counts[tag] = decimate_to(bpy.data.objects[f"car_hero_wheel_{tag}"], int(globals().get("WHEEL_TRIS", "240")))
    bpy.ops.wm.save_as_mainfile(filepath=GAME_BLEND, copy=True)
    sc = bpy.context.scene
    studio(sc)
    for o in sc.objects:
        if o.type == "MESH":
            o.data.materials.clear()
            m = bpy.data.materials.new("grey")
            m.use_nodes = True
            m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.5
            o.data.materials.append(m)
    persp_render(f"{OUT}/game_front34.png", (-6.5, 8.0, 5.2))
    counts["total"] = sum(counts.values())
    return counts


def step_measure():
    """Exact-scale ortho views of the split hi model with a 0.5 m grid: 900 px = 5 m, image centre = (0, 0, 1.9)."""
    bpy.ops.wm.open_mainfile(filepath=SPLIT_BLEND)
    sc = bpy.context.scene
    # grid of thin bars every 0.5 m on the three planes behind the model
    gm = bpy.data.materials.new("grid")
    gm.diffuse_color = (0.1, 0.6, 1.0, 1)
    bm = bmesh.new()
    for k in range(-5, 6):
        v = k * 0.5
        for size, loc in (((0.012, 6, 0.012), (v, 0, -0.2)), ((6, 0.012, 0.012), (0, v, -0.2)),       # floor (top view)
                          ((0.012, 0.012, 6), (v, -3.0, 1.9)), ((6, 0.012, 0.012), (0, -3.0, 1.9 + v)),  # back wall (front view)
                          ((0.012, 0.012, 6), (-3.0, v, 1.9)), ((0.012, 6, 0.012), (-3.0, 0, 1.9 + v))):  # side wall
            vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
            bmesh.ops.transform(bm, matrix=Matrix.LocRotScale(Vector(loc), None, Vector(size)), verts=vs)
    gme = bpy.data.meshes.new("grid")
    bm.to_mesh(gme)
    bm.free()
    g = bpy.data.objects.new("grid", gme)
    g.color = (0.1, 0.6, 1.0, 1)
    sc.collection.objects.link(g)
    for o in sc.objects:
        if o.type == "MESH" and o.name != "grid":
            o.color = (0.85, 0.85, 0.85, 1)
    cam = bpy.data.objects.new("MCam", bpy.data.cameras.new("MCam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type, cam.data.ortho_scale, cam.data.clip_end = "ORTHO", 5.0, 50
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.show_cavity = True
    sc.display.shading.color_type = "OBJECT"
    sc.render.resolution_x = sc.render.resolution_y = 900
    views = {"front": ((0, 10, 1.9), (math.radians(90), 0, math.radians(180))),
             "side_left": ((10, 0, 1.9), (math.radians(90), 0, math.radians(90))),
             "top": ((0, 0, 12), (0, 0, 0))}
    for name, (loc, rot) in views.items():
        cam.location, cam.rotation_euler = loc, rot
        if name == "top":
            cam.location = (0, 0, 12)
            cam.data.shift_y = -0.38   # keep z=1.9 framing convention irrelevant for top: centre on (0,0)
            cam.data.shift_y = 0.0
        sc.render.filepath = f"{OUT}/measure_{name}.png"
        bpy.ops.render.render(write_still=True)
    return {"scale": "180 px per metre, image centre = (x=0 or y=0, z=1.9); top view centre = (0,0)"}


PAINT_BLEND = f"{OUT}/car_hero_painted.blend"


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c) + (1.0,)


PAL = {k: lin(v) for k, v in {
    "body": "#E5553F", "plum": "#5E464C", "window": "#3A4047", "tire": "#232325", "rim": "#F4EDE0",
    "eye": "#F7F1E1", "pupil": "#1F1D22", "decal": "#F3E8D0", "amber": "#F2A23A", "chassis": "#3A3034",
    "coil": "#C9CBD0", "copper": "#B9773F", "olive": "#6E7444", "tan": "#D3BA8C", "wood": "#BE8B57",
}.items()}


def body_zone(c, n):
    """Colour zone for a face centre c / normal n on the car body (front = +Y, ground z = 0, metres)."""
    ax, y, z = abs(c.x), c.y, c.z
    # roof cargo (above the rack floor)
    if z > 3.1 and -1.75 < y < -0.2:
        if math.hypot(c.x + 0.17, y + 1.2) < 0.44:
            return "rim" if math.hypot(c.x + 0.17, y + 1.2) < 0.15 else "tire"
        if 0.08 < c.x < 0.97 and -0.97 < y < -0.33:
            return "tan" if (abs(y + 0.53) < 0.05 or abs(y + 0.8) < 0.05) else "olive"
        if 0.33 < c.x < 1.08 and -1.62 < y < -0.96:
            return "wood"
    if z > 3.0:
        # roof rack sits over the rear 2/3 of the roof (x -0.67..1.06, y -1.72..-0.22); the roof itself stays red
        if -0.78 < c.x < 1.15 and -1.82 < y < -0.12 and (z > 3.08 or n.z < 0.8):
            return "plum"
        return "body"
    # windows (recessed glass)
    if n.y > 0.45 and y > 0.0 and ax < 0.85 and 2.45 < z < 3.05:
        return "window"
    if n.y < -0.45 and y < -1.4 and ax < 0.8 and 2.2 < z < 2.95:
        return "window"
    if abs(n.x) > 0.45 and ax > 0.82:
        # rear side window: y -1.5..-0.89, z 2.12..2.84; front door window has a slanted A-pillar edge
        if -1.48 < y < -0.91 and 2.14 < z < 2.82:
            return "window"
        if -0.67 < y < 0.16 - (z - 2.21) * 0.19 and 2.23 < z < 2.96:
            return "window"
    # front end
    if y > 1.35 and n.y > 0.2:
        for ex in (0.69, -0.69):
            d = math.hypot(c.x - ex, z - 2.09)
            if d < 0.27:
                return "pupil" if math.hypot(c.x - ex * 0.93, z - 2.12) < 0.09 else "eye"
        if ax < 0.39 and 1.9 < z < 2.29:
            return "plum"                               # grille
    if y > 1.55 and ax < 0.32 and 1.38 < z < 1.95:
        return "copper"                                 # winch
    if y > 1.45 and 1.48 < z < 1.84:
        return "amber" if ax > 1.05 and z > 1.6 else "plum"   # bumper + turn signals
    if y < -1.6 and 0.95 < z < 1.4:
        return "plum"                                   # rear bumper
    # mirrors, door handles
    if 1.1 < ax < 1.5 and 2.22 < z < 2.58 and -0.05 < y < 0.45:
        return "plum"
    if ax > 0.95 and abs(y + 0.5) < 0.12 and abs(z - 1.98) < 0.06:
        return "plum"
    # "0" door roundel
    if abs(n.x) > 0.6 and ax > 0.95:
        d = math.hypot(y + 0.3, z - 1.68)
        if d < 0.3:
            return "pupil" if 0.11 < math.hypot((y + 0.3) * 1.25, z - 1.68) < 0.17 else "decal"
    # suspension + chassis
    if 0.55 < ax < 0.97 and 0.82 < z < 1.55 and (abs(y - 1.05) < 0.35 or abs(y + 0.95) < 0.35):
        return "coil"
    if z < 1.08 and ax < 1.0:
        return "chassis"
    return "body"


def wheel_zone(c, n, outward):
    """Wheel in local axle space (axle along X). outward = +1 when +X faces away from the car."""
    rr = math.hypot(c.y, c.z)
    outer = c.x * outward > 0.05
    if outer and rr < 0.13:
        return "plum"
    if outer and rr < 0.43:
        return "rim"
    return "tire"


def paint(obj, zone_fn):
    me = obj.data
    attr = me.color_attributes.get("Col") or me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    cols = []
    for p in me.polygons:
        col = PAL[zone_fn(p.center, p.normal)]
        cols += list(col) * len(p.loop_indices)
    attr.data.foreach_set("color", cols)
    me.color_attributes.active_color = attr


def vc_material(name="clay_vc"):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        nt.links.new(vc.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.5
    return m


def step_paint():
    bpy.ops.wm.open_mainfile(filepath=SPLIT_BLEND)
    body = bpy.data.objects["car_hero_hi"]
    paint(body, body_zone)
    # one clean wheel for all four: +X wheel (car's right side), outward = +X
    src = bpy.data.objects["car_hero_wheel_FL"]
    paint(src, lambda c, n: wheel_zone(c, n, 1))
    for o in (body, src):
        o.data.materials.clear()
        o.data.materials.append(vc_material())
    bpy.ops.wm.save_as_mainfile(filepath=PAINT_BLEND, copy=True)
    sc = bpy.context.scene
    studio(sc)
    # preview: put a copy of the clean wheel at every corner (mirrored on the left)
    for tag in ("FR", "RL", "RR"):
        w = bpy.data.objects[f"car_hero_wheel_{tag}"]
        w.data = src.data
        w.scale.x = 1 if w.location.x > 0 else -1
    persp_render(f"{OUT}/paint_front34.png", (-6.5, 8.0, 5.2))
    persp_render(f"{OUT}/paint_rear34.png", (6.0, -7.5, 5.5))
    return {"painted": True}


MODELS = globals().get("MODELS_DIR", r"C:/project/New Game/models/vehicles")


def repair_topology(obj):
    """The AI scan has ~1,500 non-manifold edges (3+ faces) and open borders where the wheels were cut out; the
    decimator can't collapse either. Keep the two largest faces on every over-shared edge, then close the holes."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    extra = set()
    for e in bm.edges:
        if len(e.link_faces) > 2:
            faces = sorted(e.link_faces, key=lambda f: f.calc_area(), reverse=True)
            extra.update(faces[2:])
    bmesh.ops.delete(bm, geom=list(extra), context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    stats = {"removed_faces": len(extra), "non_manifold_left": sum(1 for e in bm.edges if not e.is_manifold),
             "boundary_left": sum(1 for e in bm.edges if e.is_boundary)}
    bm.to_mesh(obj.data)
    bm.free()
    return stats


def meshopt_simplify(obj, tris):
    """Round-trip the geometry through meshoptimizer (tools/simplify-mesh.mjs) to get below Blender's decimate floor."""
    import subprocess, tempfile
    tmp = tempfile.mkdtemp()
    src, dst = os.path.join(tmp, "in.glb"), os.path.join(tmp, "out.glb")
    vl = bpy.context.view_layer
    for o in vl.objects:
        if o is not None:
            o.select_set(False)
    obj.select_set(True)
    vl.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=src, export_format="GLB", use_selection=True, export_yup=True, export_normals=False,
                              export_texcoords=False, export_materials="NONE", export_apply=True)
    tools = r"C:/project/New Game/tools"
    out = subprocess.run(["node", f"{tools}/simplify-mesh.mjs", src, dst, str(tris), globals().get("MESHOPT_ERROR", "0.08")],
                         cwd=tools, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=dst)
    new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    if new.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(new)
    new.data.transform(new.matrix_world)
    new.matrix_world = obj.matrix_world.copy()
    name = obj.name
    old_mesh = obj.data
    obj.data = new.data
    bpy.data.objects.remove(new, do_unlink=True)
    bpy.data.meshes.remove(old_mesh)
    obj.name = name
    obj.data.polygons.foreach_set("use_smooth", [True] * len(obj.data.polygons))
    obj.data.set_sharp_from_angle(angle=math.radians(float(globals().get("SHARP_ANGLE", "50"))))
    return obj


def drop_debris(obj, min_share=0.01):
    """Delete loose islands smaller than min_share of the mesh (stray triangles left by simplification)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    seen, kill = set(), []
    total = len(bm.faces)
    for f in bm.faces:
        if f.index in seen:
            continue
        island, stack = [], [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            island.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        if len(island) < total * min_share:
            kill += island
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()


def game_wheel(name, lod=0):
    """Clean low-poly balloon wheel in the scan's proportions (r 0.8 m, 0.86 m wide), vertex-coloured, axle along X,
    rim facing +X. About 200 tris at lod0."""
    steps = (12, 8, 6)[lod]
    r_out, hw, r_in = 0.8, 0.43, 0.46
    half = [(0.0, r_out), (hw - 0.02, r_out - 0.06), (hw + 0.03, (r_out + r_in) / 2), (hw - 0.03, r_in + 0.02)]
    prof = [(-x, r) for x, r in reversed(half)] + half[1:]
    bm = bmesh.new()
    col = bm.loops.layers.float_color.new("Col")
    verts = [bm.verts.new((x, 0, r)) for x, r in prof]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(1, 0, 0), angle=2 * math.pi, steps=steps, use_merge=True)
    tire_faces = list(bm.faces)
    def paint_new(new_verts, name_):
        # paint through the returned verts: after spin/merge, new faces reuse freed slots, so index slices miss some
        for f in {f for v in new_verts for f in v.link_faces}:
            for l in f.loops:
                l[col] = PAL[name_]
    for f in tire_faces:
        for l in f.loops:
            l[col] = PAL["tire"]
    # deep-dish rim on the outer side, hub in the middle
    rim = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=steps, radius1=r_in + 0.01, radius2=r_in * 0.55, depth=0.12,
                                matrix=Matrix.LocRotScale(Vector((hw - 0.1, 0, 0)), Matrix.Rotation(math.radians(90), 3, "Y").to_quaternion(), None))["verts"]
    paint_new(rim, "rim")
    hub = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=max(6, steps // 2), radius1=0.14, radius2=0.11, depth=0.1,
                                matrix=Matrix.LocRotScale(Vector((hw - 0.02, 0, 0)), Matrix.Rotation(math.radians(90), 3, "Y").to_quaternion(), None))["verts"]
    paint_new(hub, "plum")
    if lod == 0:
        # chunky alternating tread lugs (read as chevrons at game distance)
        for i in range(8):
            side = 1 if i % 2 else -1
            vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
            bmesh.ops.transform(bm, matrix=Matrix.LocRotScale(Vector((side * 0.14, 0, r_out - 0.01)), Euler((0, 0, math.radians(side * 28))),
                                                                Vector((0.34, 0.16, 0.08))), verts=vs)
            bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(45 * i), 3, "X"))
            paint_new(vs, "tire")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.set_sharp_from_angle(angle=math.radians(45))
    me.color_attributes.active_color = me.color_attributes["Col"]
    me.materials.append(vc_material("car_hero_wheel_clay"))
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def lowpoly_copy(hi, name, tris):
    lo = hi.copy()
    lo.data = hi.data.copy()
    lo.name = name
    bpy.context.scene.collection.objects.link(lo)
    repair_topology(lo)
    decimate_to(lo, max(tris, 2200))
    if tris < 1900:
        lo = meshopt_simplify(lo, tris)
    drop_debris(lo)
    return lo


def unwrap(obj):
    vl = bpy.context.view_layer
    for o in vl.objects:
        if o is not None:
            o.select_set(False)
    obj.select_set(True)
    vl.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.015)
    bpy.ops.object.mode_set(mode="OBJECT")


def bake_maps(hi, lo, size, prefix):
    """Bake base colour + tangent normal from hi (vertex-painted scan) onto lo. Returns the lo material."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 4
    lod = globals().get("LOD_TAG", "lod0")
    col = bpy.data.images.new(f"{prefix}_{lod}_color", size, size, alpha=False)
    nor = bpy.data.images.new(f"{prefix}_{lod}_normal", size, size, alpha=False)
    nor.colorspace_settings.name = "Non-Color"
    mat = bpy.data.materials.new(f"{prefix}_clay")
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.5
    tc = nt.nodes.new("ShaderNodeTexImage")
    tc.image = col
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = nor
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tc.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    lo.data.materials.clear()
    lo.data.materials.append(mat)
    vl = bpy.context.view_layer
    for img_node, kind in ((tc, "DIFFUSE"), (tn, "NORMAL")):
        nt.nodes.active = img_node
        for o in vl.objects:
            if o is not None:
                o.select_set(False)
        hi.select_set(True)
        lo.select_set(True)
        vl.objects.active = lo
        kw = dict(type=kind, use_selected_to_active=True, cage_extrusion=0.05, max_ray_distance=0.15, margin=6)
        if kind == "DIFFUSE":
            kw["pass_filter"] = {"COLOR"}
        bpy.ops.object.bake(**kw)
    os.makedirs(f"{OUT}/textures", exist_ok=True)
    for img in (col, nor):
        img.filepath_raw = f"{OUT}/textures/{img.name}.png"
        img.file_format = "PNG"
        img.save()
        img.pack()
    return mat


def export_glb(objs, path):
    vl = bpy.context.view_layer
    for o in vl.objects:
        if o is not None:
            o.select_set(False)
    for o in objs:
        o.select_set(True)
    vl.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_normals=True, export_texcoords=True, export_tangents=False, export_cameras=False,
                              export_lights=False, export_animations=False, export_materials="EXPORT",
                              export_image_format=globals().get("IMAGE_FORMAT", "WEBP"))


def step_bake():
    bpy.ops.wm.open_mainfile(filepath=PAINT_BLEND)
    sc = bpy.context.scene
    hi_body = bpy.data.objects["car_hero_hi"]
    hi_wheel = bpy.data.objects["car_hero_wheel_FL"]          # the clean wheel (+X side), local axle space
    centers = {t: bpy.data.objects[f"car_hero_wheel_{t}"].location.copy() for t in ("FL", "FR", "RL", "RR")}
    for t in ("FR", "RL", "RR"):
        bpy.data.objects.remove(bpy.data.objects[f"car_hero_wheel_{t}"], do_unlink=True)
    # put the source wheel at the origin for baking
    hi_wheel.location = (0, 0, 0)
    lo_body = lowpoly_copy(hi_body, "car_hero_body", int(globals().get("BODY_TRIS", "2200")))
    lo_wheel = game_wheel("car_hero_wheel", {"lod0": 0, "lod1": 1, "lod2": 2}[globals().get("LOD_TAG", "lod0")])
    unwrap(lo_body)
    bake_maps(hi_body, lo_body, int(globals().get("BODY_TEX", "1024")), "car_hero_body")
    hi_body.hide_render = hi_wheel.hide_render = True
    hi_body.hide_set(True)
    hi_wheel.hide_set(True)
    # assemble: +X is the car's right side (front = +Y)
    root = bpy.data.objects.new("car_hero", None)
    sc.collection.objects.link(root)
    lo_body.parent = root
    wheels = []
    for src_tag, c in centers.items():
        side = "R" if c.x > 0 else "L"
        end = "F" if c.y > 0 else "R"
        w = bpy.data.objects.new(f"car_hero_wheel_{end}{side}", lo_wheel.data)
        sc.collection.objects.link(w)
        w.parent = root
        w.location = c
        w.scale.x = 1 if c.x > 0 else -1        # tread/rim face outward on both sides
        wheels.append(w)
    bpy.data.objects.remove(lo_wheel, do_unlink=True)
    os.makedirs(MODELS, exist_ok=True)
    counts = {}
    # LOD1/LOD2 are made from lod0 with meshoptimizer (tools/lods-from-showroom.mjs) - Blender's decimate stops at UV seams
    for tag, body_t, wheel_t in ((globals().get("LOD_TAG", "lod0"), None, None),):
        if body_t:
            for o, t in ((lo_body, body_t), (wheels[0], wheel_t)):
                d = o.modifiers.new("LOD", "DECIMATE")
                d.ratio = t / max(1, sum(len(p.vertices) - 2 for p in o.data.polygons))
            for w in wheels[1:]:
                for m in list(w.modifiers):
                    w.modifiers.remove(m)
                d = w.modifiers.new("LOD", "DECIMATE")
                d.ratio = wheels[0].modifiers["LOD"].ratio
        export_glb([root, lo_body] + wheels, f"{MODELS}/car_hero_{tag}.glb")
        dg = bpy.context.evaluated_depsgraph_get()
        total = 0
        for o in [lo_body] + wheels:
            em = o.evaluated_get(dg).to_mesh()
            em.calc_loop_triangles()
            total += len(em.loop_triangles)
            o.evaluated_get(dg).to_mesh_clear()
        counts[tag] = total
        for o in [lo_body] + wheels:
            for m in list(o.modifiers):
                o.modifiers.remove(m)
    # collision: one box around the body
    xs = [v.co.x for v in lo_body.data.vertices]; ys = [v.co.y for v in lo_body.data.vertices]; zs = [v.co.z for v in lo_body.data.vertices]
    cbm = bmesh.new()
    vs = bmesh.ops.create_cube(cbm, size=1.0)["verts"]
    bmesh.ops.transform(cbm, matrix=Matrix.LocRotScale(Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (1.1 + max(zs)) / 2)), None,
                                                       Vector((max(xs) - min(xs), max(ys) - min(ys), max(zs) - 1.1))), verts=vs)
    cme = bpy.data.meshes.new("car_hero_col")
    cbm.to_mesh(cme)
    cbm.free()
    col = bpy.data.objects.new("car_hero_col", cme)
    sc.collection.objects.link(col)
    export_glb([col], f"{MODELS}/car_hero_col.glb")
    bpy.data.objects.remove(col, do_unlink=True)
    tag = globals().get("LOD_TAG", "lod0")
    bpy.ops.wm.save_as_mainfile(filepath=GAME_BLEND.replace(".blend", f"_{tag}.blend"), copy=True)
    studio(sc)
    persp_render(f"{OUT}/game_{tag}_front34.png", (-6.5, 8.0, 5.2))
    persp_render(f"{OUT}/game_{tag}_rear34.png", (6.0, -7.5, 5.5))
    return counts


STEPS = {"inspect": step_inspect, "prep": step_prep, "split": step_split, "game": step_game, "measure": step_measure,
         "paint": step_paint, "bake": step_bake}
result = {}
for s in globals().get("STEP", "inspect").split(","):
    result[s] = STEPS[s]()
