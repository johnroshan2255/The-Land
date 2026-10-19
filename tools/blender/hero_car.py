# Clay-style hero jeep (reference 01), built with real modifiers (boolean arches, bevels, smooth shading).
# Lives in its own scene "HeroCar". Run steps one at a time:
#   STEP=setup   materials, lights, camera, ground disc
#   STEP=body    body shell with cut-in arches, flares, cabin, windows, grille, eyes, bumpers, decals
#   STEP=wheels  balloon tires, deep-dish rims, springs, axles
#   STEP=roof    roof rack, cargo, spare tires
#   STEP=render  EEVEE preview to PREVIEW_PATH
# Forward = +Y, ground z = 0.
import bpy, bmesh, math
from mathutils import Vector, Matrix, Euler

SCENE = "HeroCar"
# LOW=1 builds the mobile game version (< 3,000 tris): 12-segment curves, 1-segment bevels, fewer parts.
LOW = globals().get("LOW", "0") == "1"


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c) + (1.0,)


MATS = {  # name: (hex, roughness, metallic, subsurface weight)
    "clay_body": ("#E5553F", 0.5, 0.0, 0.08),
    "clay_plum": ("#5E464C", 0.52, 0.0, 0.0),
    "window_slate": ("#3A4047", 0.45, 0.0, 0.0),
    "rubber_gasket": ("#26282C", 0.55, 0.0, 0.0),
    "tire_rubber": ("#232325", 0.55, 0.0, 0.0),
    "rim_white": ("#F4EDE0", 0.45, 0.0, 0.0),
    "eye_cream": ("#F7F1E1", 0.45, 0.0, 0.0),
    "pupil": ("#1F1D22", 0.45, 0.0, 0.0),
    "decal_cream": ("#F3E8D0", 0.5, 0.0, 0.0),
    "amber": ("#F2A23A", 0.45, 0.0, 0.0),
    "chassis": ("#3A3034", 0.55, 0.0, 0.0),
    "metal_coil": ("#C9CBD0", 0.4, 0.6, 0.0),
    "copper": ("#B9773F", 0.45, 0.6, 0.0),
    "bag_olive": ("#6E7444", 0.55, 0.0, 0.0),
    "strap_tan": ("#D3BA8C", 0.5, 0.0, 0.0),
    "wood_crate": ("#BE8B57", 0.55, 0.0, 0.0),
    "wood_dark": ("#8E6238", 0.55, 0.0, 0.0),
    "grass": ("#8DBA55", 0.55, 0.0, 0.0),
    "dirt": ("#7C5434", 0.55, 0.0, 0.0),
}


def scene():
    sc = bpy.data.scenes.get(SCENE)
    if sc is None:
        sc = bpy.data.scenes.new(SCENE)
    return sc


def material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        hexc, rough, metal, sss = MATS[name]
        rough = 0.5 if metal == 0 else rough  # satin toy finish
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = lin(hexc)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if sss:
            b.inputs["Subsurface Weight"].default_value = sss
            b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
            b.inputs["Subsurface Scale"].default_value = 0.05
        m.diffuse_color = lin(hexc)
    return m


def collection(name):
    sc = scene()
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)
    return c


def clear(coll_name):
    c = bpy.data.collections.get(coll_name)
    if c:
        for o in list(c.objects):
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if me is not None and getattr(me, "users", 1) == 0:
                if isinstance(me, bpy.types.Mesh):
                    bpy.data.meshes.remove(me)
                elif isinstance(me, bpy.types.Curve):
                    bpy.data.curves.remove(me)


def link(obj, coll="Car", parent=None):
    collection(coll).objects.link(obj)
    if parent is not None:
        obj.parent = parent
    return obj


def M(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    return Matrix.LocRotScale(Vector(loc), Euler([math.radians(a) for a in rot]), Vector(scale))


def smooth(me):
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))


def finish_mesh(name, bm, mat, coll="Car", parent=None, bevel=0.0, seg=4, angle=35, weighted=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    me.materials.append(material(mat))
    obj = bpy.data.objects.new(name, me)
    link(obj, coll, parent)
    if bevel:
        bv = obj.modifiers.new("Bevel", "BEVEL")
        bv.width = bevel
        bv.segments = seg
        bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(angle)
        bv.use_clamp_overlap = True
        bv.profile = 0.5
    if weighted:
        wn = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        wn.keep_sharp = False
    return obj


def rbox(name, size, loc, mat, bevel=0.1, seg=4, rot=(0, 0, 0), taper=None, coll="Car", parent=None):
    if LOW:
        seg = 1
        if min(size) < 0.15 or max(size) < 0.35:
            bevel = 0.0
    bm = bmesh.new()
    verts = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    if taper:
        for v in verts:
            if v.co.z > 0:
                v.co.x *= taper[0]
                v.co.y *= taper[1]
    bmesh.ops.transform(bm, matrix=M((0, 0, 0), (0, 0, 0), size), verts=verts)
    obj = finish_mesh(name, bm, mat, coll, parent, bevel, seg)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    return obj


def cyl(name, r, depth, loc, mat, rot=(0, 0, 0), seg=32, bevel=0.0, bseg=3, r2=None, coll="Car", parent=None, scale=(1, 1, 1)):
    if LOW:
        seg, bseg = min(seg, 12 if r > 0.25 else 10 if r > 0.1 else 6), 1
        if r <= 0.15:
            bevel = 0.0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=depth)
    obj = finish_mesh(name, bm, mat, coll, parent, bevel, bseg)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    obj.scale = scale
    return obj


def sphere(name, r, loc, mat, scale=(1, 1, 1), rot=(0, 0, 0), seg=24, rings=12, coll="Car", parent=None):
    if LOW:
        seg, rings = min(seg, 8), min(rings, 4)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
    obj = finish_mesh(name, bm, mat, coll, parent, 0, weighted=False)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = [math.radians(a) for a in rot]
    return obj


def r_max(profile):
    return max(r for _, r in profile)


def lathe(name, profile, loc, mat, rot=(0, 0, 0), steps=40, coll="Car", parent=None, extra=None):
    """Spin a profile [(x_axial, radius), ...] around the X axis."""
    if LOW:
        steps = 10 if r_max(profile) > 0.44 else 8
    bm = bmesh.new()
    verts = [bm.verts.new((x, 0.0, r)) for x, r in profile]
    edges = [bm.edges.new((a, b)) for a, b in zip(verts, verts[1:])]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(1, 0, 0), angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    if extra:
        extra(bm)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = finish_mesh(name, bm, mat, coll, parent, 0, weighted=False)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    return obj


def torus(name, R, r, loc, mat, rot=(0, 0, 0), seg=32, sides=12, arc=360.0, start=0.0, coll="Car", parent=None):
    if LOW:
        seg, sides = min(seg, 10), min(sides, 4)
    bm = bmesh.new()
    closed = arc >= 360
    n = seg if closed else seg + 1
    rings = []
    for i in range(n):
        a = math.radians(start + arc * i / seg)
        ring = []
        for j in range(sides):
            b = 2 * math.pi * j / sides
            d = R + r * math.cos(b)
            ring.append(bm.verts.new((d * math.cos(a), d * math.sin(a), r * math.sin(b))))
        rings.append(ring)
    for i in range(n if closed else n - 1):
        a, b = rings[i], rings[(i + 1) % n]
        for j in range(sides):
            bm.faces.new((a[j], a[(j + 1) % sides], b[(j + 1) % sides], b[j]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = finish_mesh(name, bm, mat, coll, parent, 0, weighted=False)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    return obj


def helix(name, radius, height, turns, wire, loc, mat, coll="Car", parent=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = wire
    cu.bevel_resolution = 0 if LOW else 3
    sp = cu.splines.new("POLY")
    n = int(turns * (5 if LOW else 16))
    sp.points.add(n - 1)
    for i in range(n):
        a = 2 * math.pi * turns * i / (n - 1)
        sp.points[i].co = (radius * math.cos(a), radius * math.sin(a), height * i / (n - 1), 1)
    obj = bpy.data.objects.new(name, cu)
    cu.materials.append(material(mat))
    link(obj, coll, parent)
    obj.location = loc
    return obj


def rounded_rect_curve(name, w, d, r, wire, loc, mat, coll="Car", parent=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = wire
    cu.bevel_resolution = 0 if LOW else 3
    sp = cu.splines.new("POLY")
    pts = []
    corner = 1 if LOW else 6
    for cx, cy, a0 in ((w / 2 - r, d / 2 - r, 0), (-w / 2 + r, d / 2 - r, 90), (-w / 2 + r, -d / 2 + r, 180), (w / 2 - r, -d / 2 + r, 270)):
        for k in range(corner + 1):
            a = math.radians(a0 + 90 * k / corner)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), 0))
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    sp.use_cyclic_u = True
    obj = bpy.data.objects.new(name, cu)
    cu.materials.append(material(mat))
    link(obj, coll, parent)
    obj.location = loc
    return obj


def depsgraph():
    """Evaluated depsgraph of the HeroCar view layer (not the scene shown in the UI)."""
    sc = scene()
    with bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0]):
        dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return dg


def boolean(target, cutter, op="DIFFERENCE"):
    cutter.display_type = "BOUNDS"
    cutter.hide_render = True
    mod = target.modifiers.new(f"Bool_{cutter.name}", "BOOLEAN")
    mod.object = cutter
    mod.operation = op
    mod.solver = "EXACT"
    return mod


def text_mesh(name, body, size, depth, loc, rot, mat, coll="Car", parent=None):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = depth
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.bevel_depth = depth * 0.6
    cu.bevel_resolution = 2
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    scene().collection.objects.link(tmp)
    dg = depsgraph()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.curves.remove(cu)
    me.materials.clear()
    me.materials.append(material(mat))
    smooth(me)
    obj = bpy.data.objects.new(name, me)
    link(obj, coll, parent)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    return obj


# ------------------------------------------------------------------ dimensions
TRACK, BASE, WHEEL_Z, TIRE_R, TIRE_W = 0.98, 1.32, 0.6, 0.6, 0.5


def root():
    r = bpy.data.objects.get("car_hero")
    if r is None:
        r = bpy.data.objects.new("car_hero", None)
        link(r, "Car")
    return r


def step_setup():
    sc = scene()
    for name in MATS:
        material(name)
    # studio lights: warm key sun at 45 deg, cool soft fill from the opposite side
    for lname, ltype, color, energy, rot, angle, shadow in (
        ("KeySun", "SUN", lin("#FFF2DD")[:3], 3.6, (45, 0, -40), 15, True),
        ("FillSky", "SUN", (0.72, 0.82, 1.0), 0.8, (60, 0, 150), 30, False),
    ):
        L = bpy.data.lights.get(lname) or bpy.data.lights.new(lname, ltype)
        L.color, L.energy = color, energy
        L.angle = math.radians(angle)
        L.use_shadow = shadow
        o = bpy.data.objects.get(lname) or bpy.data.objects.new(lname, L)
        if o.name not in collection("Studio").objects:
            collection("Studio").objects.link(o)
        o.rotation_euler = [math.radians(a) for a in rot]
    if sc.world is None:
        sc.world = bpy.data.worlds.new("HeroWorld")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = lin("#F4EEDB")
    bg.inputs[1].default_value = 0.75
    # ground disc like the reference (grass top, dirt rim)
    clear("Studio_ground")
    cyl("ground_dirt", 3.4, 0.35, (0, 0, -0.2), "dirt", seg=64, bevel=0.08, coll="Studio_ground")
    cyl("ground_grass", 3.25, 0.12, (0, 0, -0.02), "grass", seg=64, bevel=0.05, coll="Studio_ground")
    cam_data = bpy.data.cameras.get("HeroCam") or bpy.data.cameras.new("HeroCam")
    cam = bpy.data.objects.get("HeroCam") or bpy.data.objects.new("HeroCam", cam_data)
    if cam.name not in collection("Studio").objects:
        collection("Studio").objects.link(cam)
    cam_data.lens = 50
    cam.location = (-6.4, 7.6, 5.0)
    cam.rotation_euler = (Vector((0.1, 0.1, 1.25)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    return {"materials": len(MATS)}


def _vol_box(bm, size, loc, taper=None, rot=(0, 0, 0)):
    vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    if taper:
        for v in vs:
            if v.co.z > 0:
                v.co.x *= taper[0]
                v.co.y *= taper[1]
    bmesh.ops.transform(bm, matrix=M(loc, rot, size), verts=vs)


def _vol_cyl(bm, r, depth, loc, rot=(0, 90, 0), seg=40):
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r, depth=depth, matrix=M(loc, rot))


def snap(obj, origin, direction, offset=0.0, body=None):
    """Move obj onto the evaluated body surface hit by a ray (origin, direction), pushed out by offset."""
    dg = depsgraph()
    body = body or bpy.data.objects["car_hero_body"]
    ok, loc, nrm, _ = body.ray_cast(Vector(origin), Vector(direction).normalized(), depsgraph=dg)
    if ok:
        obj.location = loc + nrm * offset
    return ok


CAB_Z0, CAB_H, CAB_HALF_W, CAB_TAPER = 1.64, 0.98, 0.9, 0.84


def cab_half_width(z):
    t = (z - CAB_Z0) / CAB_H
    return CAB_HALF_W * (1 - (1 - CAB_TAPER) * t)


def build_low_shell(body, cut):
    """Game body: deliberate low-poly cage instead of decimating the sculpt. Volumes are boolean-unioned into one
    solid (fenders are part of the shell, not glued on), arches/grille cut with 12-sided cutters, then a 1-segment
    bevel with hardened normals softens every edge and junction."""
    body.modifiers.clear()
    bm = bmesh.new()
    _vol_box(bm, (1.86, 3.7, 0.72), (0, 0, 1.33))
    me = body.data
    bm.to_mesh(me)
    bm.free()
    def vol(name, fn):
        vbm = bmesh.new()
        fn(vbm)
        vme = bpy.data.meshes.new(name)
        vbm.to_mesh(vme)
        vbm.free()
        o = bpy.data.objects.new(name, vme)
        cut.objects.unlink(o) if o.name in cut.objects else None
        collection("LowVolumes").objects.link(o)
        o.hide_render = True
        o.display_type = "BOUNDS"
        return o
    adds = [vol("lv_hood", lambda b: _vol_box(b, (1.84, 1.55, 0.36), (0, 1.0, 1.72), taper=(0.96, 0.93))),
            vol("lv_cabin", lambda b: _vol_box(b, (2 * CAB_HALF_W, 2.05, CAB_H), (0, -0.55, CAB_Z0 + CAB_H / 2), taper=(CAB_TAPER, 0.86)))]
    for sx in (1, -1):
        for sy in (1, -1):
            adds.append(vol(f"lv_flare_{sx}_{sy}", lambda b, sx=sx, sy=sy: _vol_cyl(b, 0.92, 0.32, (sx * 0.96, sy * BASE, WHEEL_Z + 0.02), seg=8)))
    for o in adds:
        m = body.modifiers.new(f"U_{o.name}", "BOOLEAN")
        m.object, m.operation, m.solver = o, "UNION", "EXACT"
    low_cut = collection("LowCutters")
    for sx in (1, -1):
        for sy in (1, -1):
            o = vol(f"lc_arch_{sx}_{sy}", lambda b, sx=sx, sy=sy: _vol_cyl(b, 0.75, 1.3, (sx * 1.0, sy * BASE, WHEEL_Z), seg=8))
            collection("LowVolumes").objects.unlink(o)
            low_cut.objects.link(o)
    for name, fn in (("lc_under", lambda b: _vol_box(b, (6, 8, 2), (0, 0, WHEEL_Z + 0.12 - 1.0))),
                     ("lc_grille", lambda b: _vol_box(b, (1.0, 0.2, 0.42), (0, 1.85, 1.38)))):
        o = vol(name, fn)
        collection("LowVolumes").objects.unlink(o)
        low_cut.objects.link(o)
    d = body.modifiers.new("Cuts", "BOOLEAN")
    d.operand_type, d.collection, d.operation, d.solver = "COLLECTION", low_cut, "DIFFERENCE", "EXACT"
    bv = body.modifiers.new("Soften", "BEVEL")
    bv.width, bv.segments, bv.limit_method, bv.angle_limit = 0.12, 1, "ANGLE", math.radians(30)
    bv.harden_normals, bv.use_clamp_overlap = False, True
    body.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    if not body.data.materials:
        body.data.materials.append(material("clay_body"))
    smooth(body.data)


def step_body():
    """One fused clay shell: overlapping volumes -> voxel remesh (fuses + fillets) -> cut arches, window recesses,
    grille recess and hood grooves -> fine remesh + smoothing (soft edges) -> decimate."""
    clear("Car")
    clear("Cutters")
    r = root()
    bm = bmesh.new()
    _vol_box(bm, (1.86, 3.7, 0.72), (0, 0, 1.33))                                   # lower body
    _vol_box(bm, (1.84, 1.55, 0.36), (0, 1.0, 1.72), taper=(0.96, 0.93))            # hood
    _vol_box(bm, (2 * CAB_HALF_W, 2.05, CAB_H), (0, -0.55, CAB_Z0 + CAB_H / 2), taper=(CAB_TAPER, 0.86))  # cabin, tumblehome
    _vol_box(bm, (0.5, 1.2, 0.08), (0, 1.0, 1.92), taper=(0.8, 0.9))                # raised hood centre bulge
    for sx in (1, -1):
        for sy in (1, -1):
            _vol_cyl(bm, 0.93, 0.34, (sx * 0.96, sy * BASE, WHEEL_Z + 0.02))          # flare volume (fused, then cut)
    me = bpy.data.meshes.new("car_hero_body")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material("clay_body"))
    body = bpy.data.objects.new("car_hero_body", me)
    link(body, "Car", r)

    rm = body.modifiers.new("Fuse", "REMESH")
    rm.mode, rm.voxel_size, rm.use_smooth_shade = "VOXEL", 0.035, True

    cut = collection("Cutters")
    def cutter(name, bm_fn):
        cbm = bmesh.new()
        bm_fn(cbm)
        cme = bpy.data.meshes.new(name)
        cbm.to_mesh(cme)
        cbm.free()
        o = bpy.data.objects.new(name, cme)
        cut.objects.link(o)
        o.display_type = "BOUNDS"
        o.hide_render = True
        return o
    for sx in (1, -1):
        for sy in (1, -1):
            cutter(f"cut_arch_{sx}_{sy}", lambda b, sx=sx, sy=sy: _vol_cyl(b, 0.75, 1.3, (sx * 1.0, sy * BASE, WHEEL_Z)))
    cutter("cut_under", lambda b: _vol_box(b, (6, 8, 2), (0, 0, WHEEL_Z + 0.12 - 1.0)))
    if not LOW:
        cutter("cut_grille", lambda b: _vol_box(b, (1.0, 0.2, 0.42), (0, 1.85, 1.38)))
    for gx in ((-0.42, 0.42) if not LOW else ()):
        cutter(f"cut_hood_groove_{gx}", lambda b, gx=gx: _vol_box(b, (0.07, 1.2, 0.08), (gx, 0.98, 1.9)))
    zc = 2.17
    hw = cab_half_width(zc)
    tilt = math.degrees(math.atan((1 - CAB_TAPER) * CAB_HALF_W / CAB_H))
    for sx in ((1, -1) if not LOW else ()):
        for y, w in ((-0.08, 0.8), (-1.02, 0.6)):
            cutter(f"cut_win_{sx}_{y}", lambda b, sx=sx, y=y, w=w: _vol_box(b, (0.06, w, 0.46), (sx * hw, y, zc), rot=(0, -tilt * sx, 0)))
    yf = -0.55 + 1.025 - 1.025 * (1 - 0.86) * (zc - CAB_Z0) / CAB_H
    yr = -0.55 - 1.025 + 1.025 * (1 - 0.86) * (zc - CAB_Z0) / CAB_H
    slope = math.degrees(math.atan(1.025 * (1 - 0.86) / CAB_H))
    if not LOW:
        cutter("cut_windshield", lambda b: _vol_box(b, (1.3, 0.06, 0.52), (0, yf, zc), rot=(slope, 0, 0)))
        cutter("cut_rearwin", lambda b: _vol_box(b, (1.2, 0.06, 0.44), (0, yr, zc), rot=(-slope, 0, 0)))

    bo = body.modifiers.new("Cuts", "BOOLEAN")
    bo.operand_type, bo.collection, bo.operation, bo.solver = "COLLECTION", cut, "DIFFERENCE", "EXACT"
    rm2 = body.modifiers.new("Soften", "REMESH")
    rm2.mode, rm2.voxel_size, rm2.use_smooth_shade = "VOXEL", 0.03 if LOW else 0.02, True
    sm = body.modifiers.new("Smooth", "SMOOTH")
    sm.factor, sm.iterations = 0.6, 6
    if LOW:
        build_low_shell(body, cut)
    else:
        dec = body.modifiers.new("Decimate", "DECIMATE")
        dec.use_symmetry, dec.symmetry_axis = True, "X"
        dec.ratio = float(globals().get("BODY_DECIMATE", "0.12"))

    # recessed glass + soft rubber gaskets sitting in the recesses
    inset = -0.012 if LOW else 0.028   # LOW: no recess, glass sits proud of the panel on a rubber border
    for sx in (1, -1):
        for y, w in ((-0.08, 0.8), (-1.02, 0.6)):
            g = rbox(f"window_{sx}_{y}", (0.012, w - 0.02, 0.44), (sx * (hw - inset), y, zc), "window_slate", bevel=0.004, seg=2, rot=(0, -tilt * sx, 0), parent=r)
            if LOW:
                rbox(f"gasket_{sx}_{y}", (0.012, w + 0.06, 0.52), (sx * (hw + 0.002), y, zc), "rubber_gasket", bevel=0.0, rot=(0, -tilt * sx, 0), parent=r)
                continue
            rr = rounded_rect_curve(f"gasket_{sx}_{y}", w - 0.01, 0.45, 0.08, 0.028, (sx * (hw - 0.02), y, zc), "rubber_gasket", parent=r)
            rr.rotation_mode = "XYZ"
            rr.rotation_euler = (math.radians(90), math.radians(-tilt * sx), math.radians(90))
    rbox("windshield", (1.28, 0.012, 0.5), (0, yf - inset, zc), "window_slate", bevel=0.004, seg=2, rot=(slope, 0, 0), parent=r)
    if LOW:
        rbox("gasket_front", (1.36, 0.012, 0.58), (0, yf + 0.002, zc), "rubber_gasket", bevel=0.0, rot=(slope, 0, 0), parent=r)
    else:
        ws = rounded_rect_curve("gasket_front", 1.3, 0.51, 0.09, 0.03, (0, yf - 0.02, zc), "rubber_gasket", parent=r)
        ws.rotation_euler = (math.radians(90 + slope), 0, 0)
    rbox("window_rear", (1.18, 0.012, 0.42), (0, yr + inset, zc), "window_slate", bevel=0.004, seg=2, rot=(-slope, 0, 0), parent=r)
    if LOW:
        rbox("gasket_rear", (1.26, 0.012, 0.5), (0, yr - 0.002, zc), "rubber_gasket", bevel=0.0, rot=(-slope, 0, 0), parent=r)
    else:
        wr = rounded_rect_curve("gasket_rear", 1.2, 0.43, 0.08, 0.028, (0, yr + 0.02, zc), "rubber_gasket", parent=r)
        wr.rotation_euler = (math.radians(90 - slope), 0, 0)

    # grille in the recess, eyes / signals / decals snapped onto the evaluated shell
    rbox("grille_back", (0.96, 0.05, 0.4), (0, 1.77, 1.38), "clay_plum", bevel=0.04, parent=r)
    for z in ((1.26, 1.38, 1.5) if not LOW else (1.3, 1.46)):
        cyl(f"grille_slat_{z}", 0.035, 0.88, (0, 1.8, z), "clay_plum", rot=(0, 90, 0), seg=12, parent=r)
    for sx in (1, -1):
        bez = torus(f"eye_bezel_{sx}", 0.2, 0.055, (0, 0, 0), "clay_body", rot=(90, 0, 0), parent=r)
        snap(bez, (sx * 0.68, 3.0, 1.48), (0, -1, 0), 0.01)
        if LOW:
            bez.hide_render = True
        eye = sphere(f"eye_{sx}", 0.19, (0, 0, 0), "eye_cream", scale=(1, 0.55, 1), seg=8, rings=3, parent=r)
        eye.location = bez.location + Vector((0, -0.02, 0))
        pup = sphere(f"pupil_{sx}", 0.085, (0, 0, 0), "pupil", scale=(1, 0.45, 1), seg=6, rings=3, parent=r)
        pup.location = bez.location + Vector((-sx * 0.04, 0.085, 0.02))
        sig = rbox(f"turn_signal_{sx}", (0.16, 0.06, 0.09), (0, 0, 0), "amber", bevel=0.025, parent=r)
        snap(sig, (sx * 0.84, 3.0, 1.22), (0, -1, 0), 0.01)
        mir = rbox(f"mirror_{sx}", (0.1, 0.18, 0.14), (sx * 1.0, 0.36, 1.98), "clay_plum", bevel=0.045, parent=r)
        cyl(f"mirror_arm_{sx}", 0.025, 0.16, (sx * 0.91, 0.36, 1.9), "clay_plum", rot=(0, 90, 0), seg=8, parent=r)
        disc = cyl(f"decal_disc_{sx}", 0.3, 0.02, (0, 0, 0), "decal_cream", rot=(0, 90, 0), seg=10 if LOW else 40, bevel=0.0 if LOW else 0.006, bseg=2, parent=r)
        snap(disc, (sx * 2.0, 0.1, 1.3), (-sx, 0, 0), 0.004)
        if LOW:
            zero = torus(f"decal_zero_{sx}", 0.12, 0.028, (0, 0, 0), "pupil", rot=(0, 90, 0), seg=6, sides=3, parent=r)
            zero.scale = (1.35, 1, 1)
        else:
            zero = text_mesh(f"decal_zero_{sx}", "0", 0.42, 0.008, (0, 0, 0), (90, 0, 90 * sx), "pupil", parent=r)
        zero.location = disc.location + Vector((sx * 0.014, 0, 0))
    fb = rbox("bumper_front", (2.1, 0.34, 0.3), (0, 2.0, 1.0), "clay_plum", bevel=0.12, seg=5, parent=r)
    bend = fb.modifiers.new("Bend", "SIMPLE_DEFORM")
    bend.deform_method, bend.deform_axis, bend.angle = "BEND", "Z", math.radians(-28)
    fb.modifiers.move(fb.modifiers.find("Bend"), 0)
    cyl("winch_drum", 0.13, 0.46, (0, 2.2, 1.0), "copper", rot=(0, 90, 0), seg=24, bevel=0.02, parent=r)
    for sx in ((1, -1) if not LOW else ()):
        cyl(f"winch_cap_{sx}", 0.16, 0.05, (sx * 0.25, 2.2, 1.0), "clay_plum", rot=(0, 90, 0), seg=24, bevel=0.015, parent=r)
    if not LOW:
        torus("winch_hook", 0.07, 0.022, (0, 2.36, 0.9), "metal_coil", rot=(0, 90, 0), arc=270, start=90, parent=r)
    rbox("bumper_rear", (2.0, 0.3, 0.28), (0, -1.96, 1.05), "clay_plum", bevel=0.11, seg=5, parent=r)
    if not LOW:
        rbox("chassis_rail", (1.1, 3.1, 0.26), (0, 0, 0.92), "chassis", bevel=0.08, parent=r)
    dg = depsgraph()
    ev = body.evaluated_get(dg)
    return {"objects": len(collection("Car").objects), "body_faces": len(ev.data.polygons)}

def wheel(name, loc, outward, parent, r_out=TIRE_R, width=TIRE_W, with_lugs=True):
    """Plump balloon tire: bulging sidewalls, round shoulders, chevron lugs that wrap over the shoulders,
    deep-dish warm-white rim. outward = +1 (right) / -1 (left)."""
    k = r_out / 0.6
    hw = width / 2
    r_in = r_out * 0.57
    half = [(0.0, r_out + 0.005 * k), (0.12 * k, r_out - 0.002 * k), (0.2 * k, r_out - 0.02 * k), (hw + 0.01 * k, r_out - 0.07 * k),
            (hw + 0.04 * k, r_out - 0.14 * k), (hw + 0.045 * k, (r_out + r_in) / 2), (hw + 0.025 * k, r_in + 0.06 * k), (hw - 0.04 * k, r_in)]
    if LOW:
        half = [(0.0, r_out + 0.005 * k), (hw + 0.02 * k, r_out - 0.06 * k), (hw + 0.04 * k, (r_out + r_in) / 2 + 0.03 * k), (hw - 0.04 * k, r_in)]
        if not with_lugs:
            half = [(0.0, r_out), (hw + 0.03 * k, r_out - 0.08 * k), (hw - 0.04 * k, r_in)]
    prof = [(-x, rr) for x, rr in reversed(half)] + half[1:]

    def lugs(bm):
        if not with_lugs:
            return
        if LOW:
            # one chunky lug per step, alternating sides -> reads as a chevron tread at game distance
            for i in range(6):
                side = 1 if i % 2 else -1
                v = bmesh.ops.create_cube(bm, size=1.0)["verts"]
                bmesh.ops.transform(bm, matrix=M((side * 0.08 * k, 0, r_out - 0.012 * k), (0, 0, side * 30), (0.24 * k, 0.1 * k, 0.06 * k)), verts=v)
                bmesh.ops.rotate(bm, verts=v, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(60 * i), 3, "X"))
            return
        n = 18
        for i in range(n):
            a = 360 * i / n
            vs = []
            for side in (-1, 1):
                v = bmesh.ops.create_cube(bm, size=1.0)["verts"]
                bmesh.ops.transform(bm, matrix=M((side * 0.1 * k, 0, r_out + 0.015 * k), (0, 0, side * 32), (0.2 * k, 0.1 * k, 0.07 * k)), verts=v)
                vs += v
                w = bmesh.ops.create_cube(bm, size=1.0)["verts"]
                bmesh.ops.transform(bm, matrix=M((side * (hw + 0.005 * k), side * 0.05 * k, r_out - 0.08 * k), (0, side * 55, 0), (0.15 * k, 0.1 * k, 0.065 * k)), verts=w)
                vs += w
            bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(a), 3, "X"))

    tire = lathe(name, prof, loc, "tire_rubber", rot=(0, 0, 0 if outward > 0 else 180), steps=48, parent=parent, extra=lugs)
    if not LOW:
        bv = tire.modifiers.new("Bevel", "BEVEL")
        bv.width, bv.segments, bv.limit_method, bv.angle_limit = 0.018 * k, 2, "ANGLE", math.radians(40)
    rim_prof = [(hw - 0.01 * k, r_in + 0.015 * k), (hw + 0.02 * k, r_in - 0.005 * k), (hw - 0.02 * k, r_in - 0.05 * k),
                (0.06 * k, r_in * 0.6), (0.03 * k, r_in * 0.25), (0.05 * k, 0.001)]
    if LOW:
        rim_prof = [(hw + 0.02 * k, r_in - 0.005 * k), (0.06 * k, r_in * 0.55), (0.05 * k, 0.001)]
    lathe(name + "_rim", rim_prof, (0, 0, 0), "rim_white", steps=40, parent=tire)
    if not LOW:
        cyl(name + "_hub", r_in * 0.26, 0.08, (0.07 * k, 0, 0), "clay_plum", rot=(0, 90, 0), seg=20, bevel=0.015, bseg=2, parent=tire)
    for j in range(0 if LOW else 5):
        a = 2 * math.pi * j / 5
        sphere(name + f"_nut{j}", 0.022 * k, (0.11 * k, math.cos(a) * r_in * 0.42, math.sin(a) * r_in * 0.42), "rim_white", seg=10, rings=6, parent=tire)
    return tire

def step_wheels():
    r = root()
    for o in [o for o in collection("Car").objects if o.name.startswith(("car_hero_wheel", "spring", "axle"))]:
        bpy.data.objects.remove(o, do_unlink=True)
    for tag, sx, sy in (("FL", 1, 1), ("FR", -1, 1), ("RL", 1, -1), ("RR", -1, -1)):
        wheel(f"car_hero_wheel_{tag}", (sx * TRACK, sy * BASE, WHEEL_Z), sx, r)
        # thick visible coil spring between axle and frame, just inboard of each wheel
        sy_pos = sy * (BASE + 0.42)   # outboard of the axle, toward the bumpers, so the coils show like the ref
        helix(f"spring_{tag}", 0.14, 0.48, 2 if LOW else 5, 0.045, (sx * 0.5, sy_pos, WHEEL_Z), "metal_coil", parent=r)
        if LOW:
            continue
        cyl(f"spring_seat_{tag}", 0.18, 0.06, (sx * 0.5, sy_pos, WHEEL_Z - 0.02), "chassis", seg=20, bevel=0.02, bseg=2, parent=r)
        cyl(f"spring_cap_{tag}", 0.18, 0.06, (sx * 0.5, sy_pos, WHEEL_Z + 0.5), "chassis", seg=20, bevel=0.02, bseg=2, parent=r)
        if not LOW:
            cyl(f"spring_arm_{tag}", 0.05, 0.42, (sx * 0.5, sy * (BASE + 0.21), WHEEL_Z - 0.02), "chassis", rot=(90, 0, 0), seg=10, parent=r)
    for sy in (1, -1):
        if LOW:
            continue
        cyl(f"axle_{sy}", 0.08, 1.7, (0, sy * BASE, WHEEL_Z), "chassis", rot=(0, 90, 0), seg=16, parent=r)
        if not LOW:
            rbox(f"axle_diff_{sy}", (0.34, 0.3, 0.28), (0, sy * BASE, WHEEL_Z), "chassis", bevel=0.1, parent=r)
    return {"objects": len(collection("Car").objects)}


def step_roof():
    r = root()
    for o in [o for o in collection("Car").objects if o.name.startswith(("rack_", "cargo_", "crate_", "car_hero_spare_rear", "spare_mount"))]:
        bpy.data.objects.remove(o, do_unlink=True)
    zr = 2.72
    rounded_rect_curve("rack_rail", 1.62, 1.95, 0.18, 0.04, (0, -0.55, zr), "clay_plum", parent=r)
    for y in ((-1.15, -0.55, 0.05) if not LOW else (-1.15, 0.05)):
        cyl(f"rack_bar_{y}", 0.035, 1.6, (0, y, zr), "clay_plum", rot=(0, 90, 0), seg=12, parent=r)
    for sx in ((1, -1) if not LOW else ()):
        for y in (-1.35, 0.25):
            cyl(f"rack_leg_{sx}_{y}", 0.04, 0.16, (sx * 0.72, y, zr - 0.08), "clay_plum", seg=12, parent=r)
    # olive canvas bag with tan straps, wooden crate on top, spare tire lying flat
    rbox("cargo_bag", (0.66, 0.58, 0.36), (-0.3, -0.25, zr + 0.2), "bag_olive", bevel=0.16, seg=6, rot=(0, 0, 4), parent=r)
    for dy in (-0.14, 0.14):
        rbox(f"cargo_strap_{dy}", (0.69, 0.05, 0.385), (-0.3, -0.25 + dy, zr + 0.2), "strap_tan", bevel=0.03, rot=(0, 0, 4), parent=r)
    rbox("cargo_crate", (0.58, 0.5, 0.4), (-0.28, -0.25, zr + 0.58), "wood_crate", bevel=0.04, seg=3, rot=(0, 0, -6), parent=r)
    for z in ((-0.09, 0.09) if not LOW else ()):
        rbox(f"crate_plank_{z}", (0.6, 0.52, 0.025), (-0.28, -0.25, zr + 0.58 + z), "wood_dark", bevel=0.01, seg=2, rot=(0, 0, -6), parent=r)
    t = wheel("cargo_spare", (0.42, -0.45, zr + 0.14), 1, r, r_out=0.4, width=0.24, with_lugs=not LOW)
    t.rotation_euler = (0, math.radians(-90), 0)
    t2 = wheel("car_hero_spare_rear", (0, -2.16, 1.72), 1, r, r_out=0.46, width=0.3, with_lugs=not LOW)
    t2.rotation_euler = (0, 0, math.radians(-90))
    rbox("spare_mount", (0.3, 0.12, 0.3), (0, -2.02, 1.72), "clay_plum", bevel=0.08, parent=r)
    return {"objects": len(collection("Car").objects)}


def step_render():
    sc = scene()
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = int(globals().get("RES_X", "1024")), int(globals().get("RES_Y", "768"))
    sc.view_settings.view_transform = "AgX"
    sc.render.film_transparent = False
    try:
        sc.eevee.use_shadows = True
        sc.eevee.taa_render_samples = 32
    except Exception:
        pass
    sc.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return {"render": PREVIEW_PATH}


def vc_materials():
    """Game materials: colors live in vertex colors, so the whole body is 2 draw calls (clay + metal)."""
    out = []
    for name, metal, rough in (("game_clay", 0.0, 0.5), ("game_metal", 0.6, 0.4)):
        m = bpy.data.materials.get(name)
        if m is None:
            m = bpy.data.materials.new(name)
            m.use_nodes = True
            nt = m.node_tree
            b = nt.nodes.get("Principled BSDF")
            vc = nt.nodes.new("ShaderNodeVertexColor")
            vc.layer_name = "Col"
            nt.links.new(vc.outputs["Color"], b.inputs["Base Color"])
            b.inputs["Metallic"].default_value = metal
            b.inputs["Roughness"].default_value = rough
        out.append(m)
    return out


def merged(name, objs, origin, coll, bake_colors=False):
    """Bake objs (modifiers applied, world transforms) into one mesh, origin at `origin`.
    bake_colors=True: material colors -> vertex colors, materials reduced to clay + metal."""
    dg = depsgraph()
    bm = bmesh.new()
    col = bm.loops.layers.float_color.new("Col") if bake_colors else None
    slots = []
    for o in objs:
        if o.type not in ("MESH", "CURVE", "FONT") or o.hide_render:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        remap = []
        for m in me.materials:
            if m not in slots:
                slots.append(m)
            remap.append(slots.index(m))
        vbefore, fbefore = len(bm.verts), len(bm.faces)
        bm.from_mesh(me)
        ev.to_mesh_clear()
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        mat = Matrix.Translation(-Vector(origin)) @ o.matrix_world
        bmesh.ops.transform(bm, matrix=mat, verts=bm.verts[vbefore:])
        new_faces = bm.faces[fbefore:]
        for f in new_faces:
            f.material_index = remap[f.material_index] if remap else 0
        if o.matrix_world.determinant() < 0:
            bmesh.ops.reverse_faces(bm, faces=new_faces)
    if bake_colors:
        for f in bm.faces:
            src = slots[f.material_index] if slots else None
            b = src.node_tree.nodes.get("Principled BSDF") if src and src.use_nodes else None
            color = tuple(b.inputs["Base Color"].default_value) if b else (0.8, 0.8, 0.8, 1)
            metal = b.inputs["Metallic"].default_value if b else 0.0
            for loop in f.loops:
                loop[col] = color
            f.material_index = 1 if metal > 0.3 else 0
    out = bpy.data.meshes.new(name)
    bm.to_mesh(out)
    bm.free()
    smooth(out)
    if bake_colors:
        for m in vc_materials():
            out.materials.append(m)
        attr = out.color_attributes.get("Col")
        if attr:
            out.color_attributes.active_color = attr
    else:
        for m in slots:
            out.materials.append(m)
    obj = bpy.data.objects.new(name, out)
    collection(coll).objects.link(obj)
    obj.location = origin
    return obj


def descend(o):
    out = [o]
    for ch in o.children:
        out += descend(ch)
    return out


def step_export():
    """car_hero (empty root) -> car_hero_body + car_hero_wheel_FL/FR/RL/RR (origin at axle).
    EXPORT_TAGS="name:decimate_ratio,..." e.g. "showroom:1" (full materials) or "lod0:1,lod1:0.5,lod2:0.22" with BAKE=1."""
    out_dir = globals().get("OUT_DIR", r"C:/project/New Game/models/vehicles")
    tags = [(t.split(":")[0], float(t.split(":")[1])) for t in globals().get("EXPORT_TAGS", "showroom:1").split(",")]
    bake = globals().get("BAKE", "0") == "1"
    clear("Export")
    r = root()
    wheels = [o for o in r.children if o.name.startswith("car_hero_wheel_")]
    wheel_set = set(x for w in wheels for x in descend(w))
    sources = descend(r)
    for o in sources:                     # free the export names
        o.name = o.name + "_src"
    exp_root = bpy.data.objects.new("car_hero", None)
    collection("Export").objects.link(exp_root)
    body = merged("car_hero_body", [o for o in sources[1:] if o not in wheel_set], (0, 0, 0), "Export", bake)
    body.parent = exp_root
    parts = [exp_root, body]
    for w in wheels:
        wo = merged(w.name[:-4], descend(w), tuple(w.matrix_world.translation), "Export", bake)
        wo.parent = exp_root
        wo.location = w.matrix_world.translation
        parts.append(wo)
    sc = bpy.context.scene
    for o in parts:
        if o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
    report = {}
    try:
        for tag, ratio in tags:
            for o in parts[1:]:
                for m in list(o.modifiers):
                    o.modifiers.remove(m)
                if ratio < 1:
                    d = o.modifiers.new("Decimate", "DECIMATE")
                    d.ratio = ratio
                    d.use_collapse_triangulate = True
            dg = depsgraph()
            total = 0
            for o in parts[1:]:
                em = o.evaluated_get(dg).to_mesh()
                em.calc_loop_triangles()
                total += len(em.loop_triangles)
                o.evaluated_get(dg).to_mesh_clear()
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            for o in parts:
                o.select_set(True)
            bpy.context.view_layer.objects.active = exp_root
            kw = dict(filepath=f"{out_dir}/car_hero_{tag}.glb", export_format="GLB", use_selection=True, export_apply=True,
                      export_yup=True, export_normals=True, export_texcoords=False, export_tangents=False,
                      export_cameras=False, export_lights=False, export_animations=False, export_materials="EXPORT")
            props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
            if bake and "export_vertex_color" in props:
                kw["export_vertex_color"] = "ACTIVE"
            bpy.ops.export_scene.gltf(**kw)
            report[tag] = total
    finally:
        for o in sources:
            o.name = o.name[:-4]
    return report

def step_bake():
    """Game body with the sculpt's detail: build the high clay shell, then the low cage, UV-unwrap the cage and bake
    a tangent-space normal map (high -> low) so the 1k-tri body shades like the sculpt."""
    global LOW
    size = int(globals().get("BAKE_SIZE", "512"))
    LOW = False
    step_body()
    hi = bpy.data.objects["car_hero_body"]
    hi_me = bpy.data.meshes.new_from_object(hi.evaluated_get(depsgraph()))
    hi_obj = bpy.data.objects.new("body_hi", hi_me)
    collection("BakeSrc").objects.link(hi_obj)
    hi_obj.hide_render = True
    LOW = True
    step_body()
    lo = bpy.data.objects["car_hero_body"]
    lo_me = bpy.data.meshes.new_from_object(lo.evaluated_get(depsgraph()))
    old = lo.data
    lo.modifiers.clear()
    lo.data = lo_me
    bpy.data.meshes.remove(old)
    # operators need the objects in the context scene/view layer: borrow the default scene for unwrap + bake
    ctx_sc = bpy.context.scene
    vl = bpy.context.view_layer
    for o in (lo, hi_obj):
        if o.name not in ctx_sc.collection.objects:
            ctx_sc.collection.objects.link(o)
    for o in vl.objects:
        o.select_set(False)
    lo.select_set(True)
    vl.objects.active = lo
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    img = bpy.data.images.new("car_hero_body_normal", size, size, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    mat = material("clay_body").copy()
    mat.name = "clay_body_baked"
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    nt.nodes.active = tex
    lo.data.materials.clear()
    lo.data.materials.append(mat)
    ctx_sc.render.engine = "CYCLES"
    ctx_sc.cycles.samples = 1
    ctx_sc.cycles.device = "CPU"
    hi_obj.hide_render = False
    hi_obj.select_set(True)
    lo.select_set(True)
    vl.objects.active = lo
    bpy.ops.object.bake(type="NORMAL", use_selected_to_active=True, cage_extrusion=0.06, max_ray_distance=0.25, margin=8)
    hi_obj.hide_render = True
    for o in (lo, hi_obj):
        ctx_sc.collection.objects.unlink(o)
    img.filepath_raw = globals().get("NORMAL_PATH", r"C:/project/New Game/tools/blender/car_hero_body_normal.png")
    img.file_format = "PNG"
    img.save()
    img.pack()
    return {"normal_map": img.filepath_raw, "lo_tris": sum(len(p.vertices) - 2 for p in lo.data.polygons)}


def step_save():
    path = globals().get("BLEND_PATH", r"C:/project/New Game/tools/blender/hero_car.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    return {"saved": path}


def step_stats():
    dg = depsgraph()
    rows = []
    for o in descend(root())[1:]:
        if o.type not in ("MESH", "CURVE", "FONT") or o.hide_render:
            continue
        em = o.evaluated_get(dg).to_mesh()
        em.calc_loop_triangles()
        rows.append((len(em.loop_triangles), o.name))
        o.evaluated_get(dg).to_mesh_clear()
    rows.sort(reverse=True)
    groups = {}
    for n, name in rows:
        key = name.split("_")[0] + "_" + (name.split("_")[1] if "_" in name else "")
        groups[key] = groups.get(key, 0) + n
    return {"total": sum(n for n, _ in rows), "top": rows[:15], "groups": sorted(groups.items(), key=lambda kv: -kv[1])[:15]}


STEPS = {"bake": step_bake, "stats": step_stats, "save": step_save, "export": step_export, "setup": step_setup, "body": step_body, "wheels": step_wheels, "roof": step_roof, "render": step_render}
result = {}
for s in globals().get("STEP", "setup").split(","):
    result[s] = STEPS[s]()
