# Red lifted toy jeep matched to the user's reference screenshot (cherry red, cartoon eyes, roof cargo, diorama base).
# Reuses hero_car.py helpers; run after it with STEP=setup:
#   node tools/blender/headless.mjs tools/blender/hero_car.py tools/blender/jeep_ref.py STEP=setup PREVIEW_PATH=out.png [ENGINE=CYCLES] [BLEND_PATH=x.blend]
# Forward = +Y, ground z = 0.
import random

MATS.update({
    "clay_body": ("#BE2A20", 0.5, 0.0, 0.05),
    "maroon": ("#5E2422", 0.5, 0.0, 0.0),
    "glass_maroon": ("#4E3233", 0.35, 0.0, 0.0),
    "tire_rubber": ("#2A2A2D", 0.6, 0.0, 0.0),
    "rim_white": ("#D9DAE2", 0.45, 0.0, 0.0),
    "eye_cream": ("#F6F4EE", 0.4, 0.0, 0.0),
    "pupil": ("#2B2A2E", 0.4, 0.0, 0.0),
    "decal_cream": ("#F4F1E8", 0.5, 0.0, 0.0),
    "chassis": ("#4A2E2C", 0.55, 0.0, 0.0),
    "metal_coil": ("#C8C9CE", 0.35, 0.7, 0.0),
    "copper": ("#B5703C", 0.4, 0.6, 0.0),
    "bag_olive": ("#6C7743", 0.6, 0.0, 0.0),
    "strap_tan": ("#C9AE7A", 0.5, 0.0, 0.0),
    "wood_crate": ("#B98656", 0.6, 0.0, 0.0),
    "wood_dark": ("#8A5D37", 0.6, 0.0, 0.0),
    "grass": ("#93B94F", 0.7, 0.0, 0.0),
    "grass_dark": ("#7FA543", 0.7, 0.0, 0.0),
    "dirt": ("#8A5A3E", 0.7, 0.0, 0.0),
    "pine": ("#86A646", 0.7, 0.0, 0.0),
    "pine_dark": ("#6F9139", 0.7, 0.0, 0.0),
    "trunk": ("#6E4630", 0.7, 0.0, 0.0),
    "rock": ("#B79C8A", 0.7, 0.0, 0.0),
})
for _n, (_h, _r, _m, _s) in MATS.items():
    _mat = bpy.data.materials.get(_n)
    if _mat:
        _b = _mat.node_tree.nodes.get("Principled BSDF")
        _b.inputs["Base Color"].default_value = lin(_h)
        _b.inputs["Roughness"].default_value = _r
        _b.inputs["Metallic"].default_value = _m

TRACK, BASE, WHEEL_Z, TIRE_R, TIRE_W = 1.04, 1.3, 0.64, 0.64, 0.54
BODY_Z0, BODY_Z1, BODY_HW, BODY_Y = 1.02, 1.78, 0.96, 1.86
CZ0, CZ1, CHW, CTAPER = 1.76, 2.74, 0.92, 0.91
C_REAR0, C_REAR1, C_FRONT1, C_FRONT0 = -1.84, -1.79, -0.02, 0.42   # cabin side profile (y at bottom/top)


def cab_hw(z):
    return CHW * (1 - (1 - CTAPER) * (z - CZ0) / (CZ1 - CZ0))


def front_y(z):
    return C_FRONT0 + (C_FRONT1 - C_FRONT0) * (z - CZ0) / (CZ1 - CZ0)


def cabin_volume(bm):
    pts = []
    for z, yr, yf in ((CZ0, C_REAR0, C_FRONT0), (CZ1, C_REAR1, C_FRONT1)):
        hw = cab_hw(z)
        pts += [(-hw, yr, z), (hw, yr, z), (hw, yf, z), (-hw, yf, z)]
    v = [bm.verts.new(p) for p in pts]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def build_body():
    clear("Car")
    clear("Cutters")
    r = root()
    bm = bmesh.new()
    _vol_box(bm, (2 * BODY_HW, 2 * BODY_Y, BODY_Z1 - BODY_Z0), (0, 0, (BODY_Z0 + BODY_Z1) / 2))
    _vol_box(bm, (0.95, 1.25, 0.1), (0, 1.12, BODY_Z1 + 0.0), taper=(0.85, 0.9))          # raised hood centre panel
    cbm = bmesh.new()
    cabin_volume(cbm)
    for f in cbm.faces:
        bm.faces.new([bm.verts.new(v.co) for v in f.verts])
    cbm.free()
    for sx in (1, -1):
        for sy in (1, -1):
            _vol_cyl(bm, 0.9, 0.26, (sx * (BODY_HW - 0.06), sy * BASE, WHEEL_Z + 0.06), seg=48)   # fender flare lip
    me = bpy.data.meshes.new("car_hero_body")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material("clay_body"))
    body = link(bpy.data.objects.new("car_hero_body", me), "Car", r)
    rm = body.modifiers.new("Fuse", "REMESH")
    rm.mode, rm.voxel_size = "VOXEL", 0.025

    cut = collection("Cutters")

    def cutter(name, fn):
        cb = bmesh.new()
        fn(cb)
        cm = bpy.data.meshes.new(name)
        cb.to_mesh(cm)
        cb.free()
        o = bpy.data.objects.new(name, cm)
        cut.objects.link(o)
        o.display_type, o.hide_render = "BOUNDS", True
        return o

    for sx in (1, -1):
        for sy in (1, -1):
            cutter(f"cut_arch_{sx}_{sy}", lambda b, sx=sx, sy=sy: _vol_cyl(b, 0.76, 1.0, (sx * 1.05, sy * BASE, WHEEL_Z + 0.04), seg=64))
    cutter("cut_under", lambda b: _vol_box(b, (6, 8, 2), (0, 0, BODY_Z0 - 1.0)))
    cutter("cut_grille", lambda b: _vol_box(b, (0.62, 0.12, 0.4), (0, BODY_Y, 1.42)))
    # window recesses
    zc = 2.3
    hw = cab_hw(zc)
    tilt = math.degrees(math.atan(CHW * (1 - CTAPER) / (CZ1 - CZ0)))
    side_wins = ((-0.27, 0.6), (-1.2, 0.86))
    for sx in (1, -1):
        for y, w in side_wins:
            cutter(f"cut_win_{sx}_{y}", lambda b, sx=sx, y=y, w=w: _vol_box(b, (0.08, w, 0.52), (sx * hw, y, zc), rot=(0, -tilt * sx, 0)))
    rake = math.degrees(math.atan((C_FRONT0 - C_FRONT1) / (CZ1 - CZ0)))
    yf = front_y(zc)
    cutter("cut_windshield", lambda b: _vol_box(b, (1.46, 0.08, 0.66), (0, yf, zc), rot=(rake, 0, 0)))
    rr = math.degrees(math.atan((C_REAR1 - C_REAR0) / (CZ1 - CZ0)))
    yr = C_REAR0 + (C_REAR1 - C_REAR0) * (zc - CZ0) / (CZ1 - CZ0)
    cutter("cut_rearwin", lambda b: _vol_box(b, (1.3, 0.08, 0.52), (0, yr, zc), rot=(-rr, 0, 0)))
    # panel seams: door gaps and hood edge
    for sx in (1, -1):
        for y in (0.42, -0.72):
            cutter(f"cut_seam_{sx}_{y}", lambda b, sx=sx, y=y: _vol_box(b, (0.05, 0.022, 0.62), (sx * (BODY_HW + 0.005), y, 1.4)))
        cutter(f"cut_seam_h_{sx}", lambda b, sx=sx: _vol_box(b, (0.05, 1.2, 0.022), (sx * (BODY_HW + 0.005), 0.42 - 0.6 - 0.12, BODY_Z1 - 0.06)))
    bo = body.modifiers.new("Cuts", "BOOLEAN")
    bo.operand_type, bo.collection, bo.operation, bo.solver = "COLLECTION", cut, "DIFFERENCE", "EXACT"
    rm2 = body.modifiers.new("Soften", "REMESH")
    rm2.mode, rm2.voxel_size = "VOXEL", 0.012
    sm = body.modifiers.new("Smooth", "SMOOTH")
    sm.factor, sm.iterations = 0.7, 10
    smooth(body.data)

    # glass sitting inside the recesses
    for sx in (1, -1):
        for y, w in side_wins:
            rbox(f"window_{sx}_{y}", (0.012, w - 0.03, 0.49), (sx * (hw - 0.03), y, zc), "glass_maroon", bevel=0.05, seg=4, rot=(0, -tilt * sx, 0), parent=r)
    rbox("windshield", (1.43, 0.012, 0.63), (0, yf - 0.03, zc), "glass_maroon", bevel=0.06, seg=4, rot=(rake, 0, 0), parent=r)
    rbox("window_rear", (1.27, 0.012, 0.49), (0, yr + 0.03, zc), "glass_maroon", bevel=0.05, seg=4, rot=(-rr, 0, 0), parent=r)

    # grille with horizontal slats
    rbox("grille_back", (0.6, 0.05, 0.38), (0, BODY_Y - 0.04, 1.42), "maroon", bevel=0.03, parent=r)
    for z in (1.29, 1.38, 1.47, 1.56):
        rbox(f"grille_slat_{z}", (0.56, 0.06, 0.045), (0, BODY_Y - 0.01, z), "maroon", bevel=0.02, seg=3, parent=r)

    # cartoon eyes: red bezel, cream ball, round pupil with a catch-light
    for sx in (1, -1):
        ex, ez, ey = sx * 0.62, 1.47, BODY_Y + 0.02
        torus(f"eye_bezel_{sx}", 0.235, 0.05, (ex, ey, ez), "clay_body", rot=(90, 0, 0), seg=48, sides=16, parent=r)
        sphere(f"eye_{sx}", 0.235, (ex, ey, ez), "eye_cream", scale=(1, 0.5, 1), seg=48, rings=24, parent=r)
        px, pz = ex - sx * 0.03, ez + 0.01
        sphere(f"pupil_{sx}", 0.13, (px, ey + 0.1, pz), "pupil", scale=(1, 0.35, 1), seg=32, rings=16, parent=r)
        sphere(f"eye_glint_{sx}", 0.03, (px + 0.045, ey + 0.135, pz + 0.05), "eye_cream", scale=(1, 0.5, 1), seg=16, rings=8, parent=r)
        # mirrors on the A-pillars
        rbox(f"mirror_{sx}", (0.08, 0.16, 0.2), (sx * (BODY_HW + 0.1), 0.28, 2.02), "maroon", bevel=0.035, parent=r)
        cyl(f"mirror_arm_{sx}", 0.025, 0.12, (sx * (BODY_HW + 0.03), 0.28, 1.95), "maroon", rot=(0, 90, 0), seg=10, parent=r)
        # door roundel with the number
        disc = cyl(f"decal_disc_{sx}", 0.27, 0.02, (sx * (BODY_HW + 0.0), -0.18, 1.4), "decal_cream", rot=(0, 90, 0), seg=48, bevel=0.006, bseg=2, parent=r)
        snap(disc, (sx * 2.0, -0.18, 1.4), (-sx, 0, 0), 0.006, body=body)
        zero = text_mesh(f"decal_zero_{sx}", "0", 0.4, 0.006, (0, 0, 0), (90, 0, 90 * sx), "pupil", parent=r)
        zero.location = disc.location + Vector((sx * 0.014, 0, -0.01))
        # door handle
        rbox(f"door_handle_{sx}", (0.03, 0.14, 0.035), (sx * (BODY_HW + 0.005), -0.02, 1.68), "maroon", bevel=0.012, parent=r)

    # front bumper, coil winch, tow hook; rear bumper
    rbox("bumper_front", (1.98, 0.3, 0.26), (0, BODY_Y + 0.12, 1.0), "maroon", bevel=0.09, seg=5, parent=r)
    rbox("bumper_plate", (0.5, 0.2, 0.28), (0, BODY_Y + 0.2, 0.82), "chassis", bevel=0.06, parent=r)
    w = helix("winch_coil", 0.085, 0.42, 7, 0.03, (-0.21, BODY_Y + 0.33, 1.0), "metal_coil", parent=r)
    w.rotation_euler = (0, math.radians(90), 0)
    cyl("winch_core", 0.07, 0.44, (0, BODY_Y + 0.33, 1.0), "copper", rot=(0, 90, 0), seg=24, parent=r)
    for sx in (1, -1):
        cyl(f"winch_cap_{sx}", 0.12, 0.05, (sx * 0.24, BODY_Y + 0.33, 1.0), "maroon", rot=(0, 90, 0), seg=24, bevel=0.012, parent=r)
        torus(f"tow_hook_{sx}", 0.06, 0.022, (sx * 0.7, BODY_Y + 0.3, 0.98), "maroon", rot=(0, 90, 0), seg=16, sides=8, parent=r)
    torus("winch_hook", 0.06, 0.018, (0, BODY_Y + 0.4, 0.86), "metal_coil", rot=(0, 90, 0), arc=270, start=90, seg=16, sides=8, parent=r)
    rbox("bumper_rear", (1.96, 0.26, 0.24), (0, -BODY_Y - 0.08, 1.04), "maroon", bevel=0.08, seg=5, parent=r)
    rbox("chassis_rail", (1.0, 3.3, 0.22), (0, 0, 0.92), "chassis", bevel=0.07, parent=r)
    return body


def build_wheels():
    r = root()
    for tag, sx, sy in (("FL", 1, 1), ("FR", -1, 1), ("RL", 1, -1), ("RR", -1, -1)):
        wheel(f"car_hero_wheel_{tag}", (sx * TRACK, sy * BASE, WHEEL_Z), sx, r, r_out=TIRE_R, width=TIRE_W)
        # coil-over between axle and frame
        sxp, syp = sx * 0.56, sy * (BASE + 0.26)
        helix(f"spring_{tag}", 0.12, 0.42, 6, 0.032, (sxp, syp, WHEEL_Z - 0.02), "metal_coil", parent=r)
        cyl(f"shock_{tag}", 0.045, 0.44, (sxp, syp, WHEEL_Z + 0.2), "copper", seg=12, parent=r)
        cyl(f"spring_seat_{tag}", 0.15, 0.05, (sxp, syp, WHEEL_Z - 0.03), "chassis", seg=20, bevel=0.015, bseg=2, parent=r)
        cyl(f"spring_cap_{tag}", 0.15, 0.05, (sxp, syp, WHEEL_Z + 0.42), "chassis", seg=20, bevel=0.015, bseg=2, parent=r)
        cyl(f"spring_arm_{tag}", 0.045, 0.3, (sxp, sy * (BASE + 0.13), WHEEL_Z - 0.03), "chassis", rot=(90, 0, 0), seg=10, parent=r)
    for sy in (1, -1):
        cyl(f"axle_{sy}", 0.075, 1.8, (0, sy * BASE, WHEEL_Z), "chassis", rot=(0, 90, 0), seg=16, parent=r)
        sphere(f"axle_diff_{sy}", 0.2, (0.12, sy * BASE, WHEEL_Z), "chassis", scale=(1, 0.9, 0.9), parent=r)
    cyl("driveshaft", 0.05, 2.4, (0.12, 0, WHEEL_Z + 0.05), "chassis", rot=(90, 0, 0), seg=12, parent=r)


def build_roof():
    r = root()
    zr = CZ1 + 0.1
    ry, rw, rd = -0.9, 1.56, 1.6
    rbox("rack_floor", (rw - 0.1, rd - 0.1, 0.03), (0, ry, zr - 0.02), "maroon", bevel=0.01, parent=r)
    for i in range(5):
        rbox(f"rack_slat_{i}", (rw - 0.1, 0.07, 0.035), (0, ry - rd / 2 + 0.2 + i * (rd - 0.4) / 4, zr + 0.01), "maroon", bevel=0.012, parent=r)
    rounded_rect_curve("rack_rail_low", rw, rd, 0.14, 0.032, (0, ry, zr), "maroon", parent=r)
    rounded_rect_curve("rack_rail_top", rw, rd, 0.14, 0.032, (0, ry, zr + 0.14), "maroon", parent=r)
    for sx in (1, -1):
        for t in range(4):
            y = ry - rd / 2 + 0.15 + t * (rd - 0.3) / 3
            cyl(f"rack_post_{sx}_{t}", 0.022, 0.14, (sx * rw / 2, y, zr + 0.07), "maroon", seg=8, parent=r)
        for y in (ry - rd / 2 + 0.18, ry + rd / 2 - 0.18):
            cyl(f"rack_leg_{sx}_{y}", 0.035, 0.12, (sx * (rw / 2 - 0.08), y, zr - 0.07), "maroon", seg=10, parent=r)
    for x in (-0.4, 0.4):
        cyl(f"rack_post_f_{x}", 0.022, 0.14, (x, ry + rd / 2, zr + 0.07), "maroon", seg=8, parent=r)
        cyl(f"rack_post_b_{x}", 0.022, 0.14, (x, ry - rd / 2, zr + 0.07), "maroon", seg=8, parent=r)
    # olive canvas bag + tan straps, wooden crate on top, spare tyre standing up behind
    bx, by = -0.2, -0.45
    rbox("cargo_bag", (0.66, 0.5, 0.34), (bx, by, zr + 0.2), "bag_olive", bevel=0.07, seg=5, rot=(0, 0, 5), parent=r)
    for dx in (-0.16, 0.16):
        rbox(f"cargo_strap_{dx}", (0.05, 0.53, 0.36), (bx + dx, by, zr + 0.2), "strap_tan", bevel=0.025, rot=(0, 0, 5), parent=r)
    rbox("cargo_strap_x", (0.69, 0.05, 0.36), (bx, by, zr + 0.2), "strap_tan", bevel=0.025, rot=(0, 0, 5), parent=r)
    rbox("cargo_crate", (0.48, 0.36, 0.26), (bx + 0.04, by - 0.02, zr + 0.5), "wood_crate", bevel=0.025, seg=3, rot=(0, 0, -8), parent=r)
    for z in (-0.07, 0.07):
        rbox(f"crate_plank_{z}", (0.495, 0.375, 0.02), (bx + 0.04, by - 0.02, zr + 0.5 + z), "wood_dark", bevel=0.008, seg=2, rot=(0, 0, -8), parent=r)
    t = wheel("cargo_spare", (0.3, -1.25, zr + 0.38), 1, r, r_out=0.38, width=0.24)
    t.rotation_euler = (0, 0, math.radians(70))


def pine(name, x, y, h, seed):
    rnd = random.Random(seed)
    cyl(name + "_trunk", 0.12, h * 0.2, (x, y, h * 0.1), "trunk", seg=6, coll="Studio_ground")
    tiers = 4
    for i in range(tiers):
        t = i / tiers
        rad = (0.95 - 0.55 * t) * h / 3.2
        z0 = h * (0.15 + 0.2 * i)
        o = cyl(f"{name}_tier{i}", rad, h * 0.34, (x, y, z0 + h * 0.17), "pine" if i % 2 == 0 else "pine_dark", r2=0.0, seg=7, coll="Studio_ground")
        o.rotation_euler = (0, 0, rnd.uniform(0, 6.28))
        o.data.polygons.foreach_set("use_smooth", [False] * len(o.data.polygons))
        for m in list(o.modifiers):
            o.modifiers.remove(m)


def build_scenery():
    clear("Studio_ground")
    cyl("ground_dirt", 3.6, 0.38, (0, 0, -0.21), "dirt", seg=72, bevel=0.06, coll="Studio_ground")
    # faceted low-poly grass top
    from mathutils.geometry import delaunay_2d_cdt
    rnd = random.Random(3)
    pts = [Vector((3.45 * math.cos(2 * math.pi * i / 72), 3.45 * math.sin(2 * math.pi * i / 72))) for i in range(72)]
    while len(pts) < 72 + 90:
        p = Vector((rnd.uniform(-3.2, 3.2), rnd.uniform(-3.2, 3.2)))
        if p.length < 3.15:
            pts.append(p)
    vco, _, faces, _, _, _ = delaunay_2d_cdt(pts, [], [], 0, 1e-5)
    bm = bmesh.new()
    bv = [bm.verts.new((v.x, v.y, 0.0 if v.length > 3.3 else rnd.uniform(-0.035, 0.035))) for v in vco]
    for f in faces:
        bm.faces.new([bv[i] for i in f])
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    vs = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=vs, vec=(0, 0, -0.15))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("ground_grass")
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [False] * len(me.polygons))
    for f in me.polygons:
        if f.normal.z < 0:
            f.flip()
    me.materials.append(material("grass"))
    me.materials.append(material("grass_dark"))
    for f in me.polygons:
        f.material_index = 1 if rnd.random() < 0.3 else 0
    g = bpy.data.objects.new("ground_grass", me)
    link(g, "Studio_ground")
    g.location.z = 0.05
    pine("pine_a", 0.5, -2.75, 3.7, 1)
    pine("pine_b", -1.15, -2.6, 2.8, 2)
    rk = sphere("rock", 0.32, (-2.3, -0.9, 0.12), "rock", scale=(1.2, 0.9, 0.75), seg=6, rings=4, coll="Studio_ground")
    rk.data.polygons.foreach_set("use_smooth", [False] * len(rk.data.polygons))
    for i, (x, y) in enumerate(((-2.3, 0.6), (-1.9, -1.5), (0.3, 2.6), (-0.9, -2.7), (2.4, 1.0))):
        for k in range(3):
            o = cyl(f"tuft_{i}_{k}", 0.05, 0.22, (x + 0.07 * k, y + 0.04 * (k % 2), 0.15), "grass_dark", r2=0.0, seg=4, coll="Studio_ground")
            o.rotation_euler = (math.radians(15 * (k - 1)), math.radians(12 * (k - 1)), 0)


def setup_look():
    sc = scene()
    key = bpy.data.objects["KeySun"]
    key.data.energy, key.data.angle = 4.0, math.radians(8)
    key.data.color = lin("#FFE9CC")[:3]
    key.rotation_euler = [math.radians(a) for a in (50, 0, -125)]
    fill = bpy.data.objects["FillSky"]
    fill.data.energy = 0.6
    nt = sc.world.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs[0].default_value = lin("#E9E2D6")
    bg.inputs[1].default_value = 0.9
    cam = bpy.data.objects["HeroCam"]
    cam.data.lens = 55
    cam.location = (-8.6, 7.4, 7.0)
    cam.rotation_euler = (Vector((0.25, -0.15, 1.35)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    # backdrop so the background reads as a soft studio sweep instead of a void
    cyl("backdrop", 40, 0.02, (0, 0, -0.42), "dirt", seg=8, coll="Studio")
    bd = bpy.data.objects["backdrop"]
    bd.data.materials.clear()
    m = bpy.data.materials.get("backdrop") or bpy.data.materials.new("backdrop")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = lin("#D9D4CC")
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    bd.data.materials.append(m)


def render():
    sc = scene()
    engine = globals().get("ENGINE", "EEVEE")
    if engine == "CYCLES":
        sc.render.engine = "CYCLES"
        sc.cycles.samples = int(globals().get("SAMPLES", "96"))
        sc.cycles.use_denoising = True
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "OPTIX"
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            sc.cycles.device = "GPU"
        except Exception:
            pass
    else:
        engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
        try:
            sc.eevee.taa_render_samples = 48
            sc.eevee.use_raytracing = True
            sc.eevee.use_shadows = True
        except Exception:
            pass
    sc.render.resolution_x, sc.render.resolution_y = int(globals().get("RES_X", "1024")), int(globals().get("RES_Y", "768"))
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast" if engine == "CYCLES" else "None"
    sc.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True, scene=sc.name)


setup_look()
build_body()
build_wheels()
build_roof()
build_scenery()
if globals().get("BLEND_PATH"):
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
if globals().get("NO_RENDER", "0") != "1":
    render()
result["jeep_ref"] = {"objects": len(collection("Car").objects)}
