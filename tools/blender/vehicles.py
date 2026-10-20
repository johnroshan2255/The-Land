# Vehicles. Forward = +Y in Blender (-Z in three.js), ground at z=0, origin at the chassis center on the ground.
# Each vehicle exports a body node + 4 wheel nodes ("<name>_wheel_FL/FR/RL/RR", origin at the axle) for LOD0/1;
# LOD2 is a single merged mesh.


def wheel(name, parent, pos, lod, r=0.55, w=0.45, rim_r=0.28, tread=True, rim_color="rim"):
    p = Part()
    seg = seg_for(lod, 12, 8, 6)
    p.cyl("tire", r, w, seg, rot=(0, 90, 0))
    p.cyl(rim_color, rim_r, w + 0.03, seg_for(lod, 8, 6, 6), rot=(0, 90, 0))
    if lod == 0:
        p.cyl("chassis", rim_r * 0.35, w + 0.06, 6, rot=(0, 90, 0))
        if tread:
            n = 12
            for i in range(n):
                a = 360 * (i + 0.5) / n
                ar = math.radians(a)
                p.box("tire_side", (w * 0.92, 0.17, 0.09), loc=(0, math.cos(ar) * (r + 0.02), math.sin(ar) * (r + 0.02)), rot=(a + 90, 0, 0))
    obj = p.finish(name, parent=parent)
    obj.location = pos
    return obj


def add_wheels(name, body, lod, track, base, r, w, rim_r, z=None, rear_base=None, rear_r=None, rear_w=None, tread=True, rim_color="rim"):
    z = r if z is None else z
    for tag, sx, sy in (("FL", 1, 1), ("FR", -1, 1), ("RL", 1, -1), ("RR", -1, -1)):
        rr = rear_r if (sy < 0 and rear_r) else r
        ww = rear_w if (sy < 0 and rear_w) else w
        yy = (rear_base if (sy < 0 and rear_base) else base) * sy
        wheel(f"{name}_wheel_{tag}", body, (sx * track, yy, rr if z == r else z), lod, rr, ww, rim_r * rr / r, tread, rim_color)


def merged_wheels(p, track, base, r, w, rear_base=None, rear_r=None):
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        rr = rear_r if (sy < 0 and rear_r) else r
        yy = (rear_base if (sy < 0 and rear_base) else base) * sy
        p.cyl("tire", rr, w, 6, loc=(sx * track, yy, rr), rot=(0, 90, 0))


def eyes(p, lod, y, z, x, r=0.24):
    for s in (1, -1):
        p.cyl("eye_white", r, 0.1, seg_for(lod, 10, 8, 6), loc=(s * x, y, z), rot=(90, 0, 0))
        p.cyl("pupil", r * 0.45, 0.06, 6, loc=(s * (x - 0.03), y + 0.06, z + 0.02), rot=(90, 0, 0))


# ------------------------------------------------------------------ hero jeep (reference 01)
def car_hero(lod, color="car_red", dark="car_red_dark", name="car_hero", rack=True):
    p = Part()
    if lod == 2:
        p.box(color, (1.9, 3.9, 0.75), loc=(0, 0, 1.3))
        p.box(color, (1.75, 2.0, 0.8), loc=(0, -0.55, 2.05), taper=(0.92, 0.9))
        p.box("window", (1.8, 1.7, 0.4), loc=(0, -0.55, 2.05))
        p.box("maroon", (2.0, 0.3, 0.3), loc=(0, 1.95, 1.0))
        if rack:
            p.box("crate", (1.0, 1.0, 0.4), loc=(0, -0.5, 2.65))
        merged_wheels(p, 0.98, 1.3, 0.55, 0.45)
        return p.finish(name)
    # body
    p.box(color, (1.9, 3.6, 0.55), loc=(0, 0, 1.28))
    p.box(color, (1.8, 1.35, 0.3), loc=(0, 1.1, 1.67), taper=(0.97, 0.95))
    p.box(color, (1.8, 2.0, 0.85), loc=(0, -0.55, 1.98), taper=(0.93, 0.9))
    # glass
    p.box("window", (1.5, 0.06, 0.58), loc=(0, 0.42, 2.03), rot=(9, 0, 0))
    p.box("window", (1.45, 0.06, 0.5), loc=(0, -1.55, 2.03))
    for s in (1, -1):
        p.box("window", (0.06, 0.78, 0.5), loc=(s * 0.875, -0.05, 2.03))
        p.box("window", (0.06, 0.62, 0.5), loc=(s * 0.875, -1.05, 2.03))
    # fender arches, bumpers, grille
    for s in (1, -1):
        for y in (1.3, -1.3):
            p.box(dark, (0.22, 1.25, 0.24), loc=(s * 0.98, y, 1.5))
    p.box("maroon", (2.05, 0.32, 0.26), loc=(0, 1.95, 1.0))
    p.box("maroon", (2.0, 0.26, 0.26), loc=(0, -1.92, 1.05))
    p.box("maroon", (1.25, 0.08, 0.42), loc=(0, 1.81, 1.36))
    eyes(p, lod, 1.83, 1.52, 0.62)
    # rear spare tire
    p.cyl("tire", 0.45, 0.26, seg_for(lod, 12, 8, 6), loc=(0, -2.0, 1.75), rot=(90, 0, 0))
    p.cyl("rim", 0.22, 0.28, 6, loc=(0, -2.0, 1.75), rot=(90, 0, 0))
    # chassis + axles
    p.box("chassis", (1.2, 3.2, 0.3), loc=(0, 0, 0.88))
    for y in (1.3, -1.3):
        p.cyl("chassis", 0.09, 1.75, 6, loc=(0, y, 0.55), rot=(0, 90, 0))
    if rack:
        if lod == 0:
            for s in (1, -1):
                p.box("maroon", (0.07, 1.9, 0.07), loc=(s * 0.78, -0.55, 2.5))
            for y in (-1.45, -0.55, 0.35):
                p.box("maroon", (1.62, 0.07, 0.07), loc=(0, y, 2.5))
            for s in (1, -1):
                for y in (-1.4, 0.3):
                    p.box("maroon", (0.06, 0.06, 0.12), loc=(s * 0.78, y, 2.44))
        else:
            p.box("maroon", (1.62, 1.9, 0.07), loc=(0, -0.55, 2.5))
        p.box("crate", (0.6, 0.55, 0.42), loc=(-0.3, -0.3, 2.95), rot=(0, 0, 8))
        p.box("olive", (0.6, 0.5, 0.36), loc=(-0.28, -0.25, 2.72))
        p.cyl("tire", 0.4, 0.22, seg_for(lod, 10, 8, 6), loc=(0.35, -0.85, 2.65))
        if lod == 0:
            p.cyl("rim", 0.18, 0.24, 6, loc=(0.35, -0.85, 2.65))
            p.box("crate", (0.62, 0.08, 0.03), loc=(-0.3, -0.3, 3.17))
    if lod == 0:
        for z in (1.28, 1.38, 1.48):
            p.box("chassis", (1.1, 0.04, 0.04), loc=(0, 1.86, z))
        p.cyl("copper", 0.13, 0.5, 6, loc=(0, 2.13, 1.0), rot=(0, 90, 0))
        p.box("rim", (0.3, 0.06, 0.18), loc=(0, 2.13, 0.82))
        for s in (1, -1):
            p.box("maroon", (0.14, 0.1, 0.16), loc=(s * 0.95, 0.38, 1.8))
            p.cyl("eye_white", 0.32, 0.04, 10, loc=(s * 0.955, 0.05, 1.28), rot=(0, 90, 0))
            p.ring("pupil", 0.15, 0.035, 10, 4, loc=(s * 0.975, 0.05, 1.28), rot=(0, 90, 0), scale=(1.3, 1, 1))
            for y in (1.3, -1.3):
                p.cyl("spring", 0.12, 0.5, 6, loc=(s * 0.62, y, 0.85))
    body = p.finish(name)
    add_wheels(name, body, lod, 0.98, 1.3, 0.55, 0.45, 0.28)
    return body


def car_hero_col():
    p = Part()
    p.box("black", (1.95, 4.0, 1.5), loc=(0, 0, 1.6))
    return p.finish("car_hero_col")


# ------------------------------------------------------------------ open-top jeep with roll bar (refs 03/07: yellow, blue, purple)
def car_jeep_open(lod, color="yellow", name="car_jeep_open"):
    p = Part()
    track, base, r = 0.9, 1.2, 0.48
    if lod == 2:
        p.box(color, (1.75, 3.5, 0.8), loc=(0, 0, 1.1))
        p.box("black", (1.5, 0.08, 0.7), loc=(0, -0.5, 1.85))
        merged_wheels(p, track, base, r, 0.42)
        return p.finish(name)
    p.box(color, (1.75, 3.4, 0.6), loc=(0, 0, 1.1))
    p.box(color, (1.7, 1.2, 0.25), loc=(0, 1.05, 1.5), taper=(0.97, 0.95))
    for s in (1, -1):
        for y in (base, -base):
            p.box(color, (0.22, 1.1, 0.2), loc=(s * 0.92, y, 1.32))
    p.box("black", (1.55, 0.08, 0.06), loc=(0, 0.42, 2.0))
    for s in (1, -1):
        p.box("black", (0.06, 0.06, 0.6), loc=(s * 0.75, 0.42, 1.7), rot=(10, 0, 0))
    seg = seg_for(lod, 6, 4, 4)
    for s in (1, -1):
        p.cyl("metal_dark", 0.05, 0.95, seg, loc=(s * 0.75, -0.45, 1.85))
        p.cyl("metal_dark", 0.05, 1.3, seg, loc=(s * 0.75, -0.95, 2.3), rot=(90, 0, 0))
    p.cyl("metal_dark", 0.05, 1.5, seg, loc=(0, -0.45, 2.32), rot=(0, 90, 0))
    p.box("chassis", (0.6, 0.6, 0.45), loc=(0.42, 0.0, 1.55))
    p.box("chassis", (0.6, 0.6, 0.45), loc=(-0.42, 0.0, 1.55))
    p.box("maroon", (1.85, 0.28, 0.22), loc=(0, 1.8, 0.9))
    p.box("maroon", (1.8, 0.22, 0.22), loc=(0, -1.78, 0.95))
    p.box("chassis", (1.1, 3.0, 0.28), loc=(0, 0, 0.72))
    eyes(p, lod, 1.66, 1.38, 0.55, 0.2)
    p.cyl("tire", 0.4, 0.22, seg_for(lod, 10, 8, 6), loc=(0, -1.85, 1.45), rot=(90, 0, 0))
    if lod == 0:
        p.box("maroon", (1.15, 0.07, 0.35), loc=(0, 1.71, 1.18))
        p.box("crate", (0.55, 0.5, 0.35), loc=(0.35, -1.25, 1.55))
        for s in (1, -1):
            p.box("chassis", (0.55, 0.12, 0.6), loc=(s * 0.42, -0.28, 1.95))
            for y in (base, -base):
                p.cyl("spring", 0.1, 0.4, 6, loc=(s * 0.55, y, 0.7))
    body = p.finish(name)
    add_wheels(name, body, lod, track, base, r, 0.42, 0.24)
    return body


def car_jeep_open_col():
    p = Part()
    p.box("black", (1.8, 3.6, 1.3), loc=(0, 0, 1.3))
    return p.finish("car_jeep_open_col")


# ------------------------------------------------------------------ dune buggy (refs 08/07: pink / orange, exposed tube frame)
def car_buggy(lod, color="pink", name="car_buggy"):
    p = Part()
    track, base, r = 0.85, 1.05, 0.42
    if lod == 2:
        p.box(color, (1.3, 2.9, 0.5), loc=(0, 0, 0.8))
        p.box("metal_dark", (1.1, 1.0, 0.7), loc=(0, -0.3, 1.4))
        merged_wheels(p, track, base, r, 0.38, rear_r=0.5)
        return p.finish(name)
    p.box(color, (1.25, 2.8, 0.35), loc=(0, 0, 0.75))
    p.box(color, (1.1, 0.9, 0.35), loc=(0, 1.05, 0.95), taper=(0.8, 0.8))
    p.box(color, (1.1, 0.8, 0.45), loc=(0, -1.0, 1.05))
    for s in (1, -1):
        p.box(color, (0.25, 0.9, 0.12), loc=(s * 0.78, base, 1.0))
        p.box(color, (0.3, 1.1, 0.14), loc=(s * 0.78, -base, 1.15))
    seg = seg_for(lod, 6, 4, 4)
    for s in (1, -1):
        p.cyl("metal_dark", 0.045, 1.0, seg, loc=(s * 0.5, 0.25, 1.3), rot=(-25, 0, 0))
        p.cyl("metal_dark", 0.045, 0.85, seg, loc=(s * 0.5, -0.55, 1.35), rot=(15, 0, 0))
        p.cyl("metal_dark", 0.045, 0.8, seg, loc=(s * 0.5, -0.15, 1.75), rot=(90, 0, 0))
    p.cyl("metal_dark", 0.045, 1.0, seg, loc=(0, -0.55, 1.75), rot=(0, 90, 0))
    p.box("chassis", (0.5, 0.5, 0.45), loc=(0, -0.25, 1.1))
    eyes(p, lod, 1.45, 1.05, 0.33, 0.16)
    if lod == 0:
        p.cyl("metal", 0.12, 0.35, 6, loc=(0.25, -1.45, 1.15), rot=(90, 0, 0))
        p.cyl("metal", 0.12, 0.35, 6, loc=(-0.25, -1.45, 1.15), rot=(90, 0, 0))
        p.box("black", (0.9, 0.3, 0.06), loc=(0, -1.35, 1.6))
    body = p.finish(name)
    add_wheels(name, body, lod, track, base, r, 0.38, 0.2, rear_r=0.5, rear_w=0.45)
    return body


def car_buggy_col():
    p = Part()
    p.box("black", (1.6, 3.0, 1.1), loc=(0, 0, 1.0))
    return p.finish("car_buggy_col")


# ------------------------------------------------------------------ camper van (refs 07/08: teal + cream two-tone, luggage on roof)
def car_van(lod, color="teal", name="car_van"):
    p = Part()
    track, base, r = 0.85, 1.55, 0.4
    if lod == 2:
        p.box(color, (1.9, 4.4, 1.0), loc=(0, 0, 1.0))
        p.box("cream", (1.85, 4.3, 0.9), loc=(0, -0.05, 1.95))
        p.box("glass_blue", (1.95, 3.6, 0.4), loc=(0, -0.2, 2.0))
        merged_wheels(p, track, base, r, 0.36)
        return p.finish(name)
    p.box(color, (1.9, 4.4, 0.95), loc=(0, 0, 0.98))
    p.box("cream", (1.88, 4.3, 0.95), loc=(0, -0.05, 1.93), taper=(0.97, 0.98))
    p.box("cream", (1.85, 0.6, 0.55), loc=(0, 2.1, 1.25), taper=(1, 0.6))
    p.box("glass_blue", (1.6, 0.08, 0.6), loc=(0, 2.07, 1.98), rot=(12, 0, 0))
    for s in (1, -1):
        for y in (1.25, 0.15, -0.95):
            p.box("glass_blue", (0.06, 0.9, 0.55), loc=(s * 0.94, y, 2.0))
    p.box("glass_blue", (1.5, 0.06, 0.55), loc=(0, -2.18, 2.0))
    p.box(color, (1.95, 0.25, 0.22), loc=(0, 2.25, 0.78))
    p.box(color, (1.95, 0.22, 0.22), loc=(0, -2.25, 0.8))
    for s in (1, -1):
        p.cyl("eye_white", 0.17, 0.08, seg_for(lod, 8, 6, 6), loc=(s * 0.65, 2.2, 1.2), rot=(90, 0, 0))
    p.box("maroon", (1.5, 2.2, 0.08), loc=(0, -0.3, 2.45))
    p.box("crate", (0.7, 0.6, 0.4), loc=(-0.3, -0.6, 2.69))
    p.box("flag_red", (0.6, 0.55, 0.35), loc=(0.35, 0.2, 2.66))
    if lod == 0:
        p.box("trailer_stripe", (1.92, 4.32, 0.12), loc=(0, -0.05, 1.5))
        p.box("chassis", (0.9, 0.06, 0.3), loc=(0, 2.37, 1.1))
        p.box("olive", (0.5, 0.5, 0.3), loc=(0.35, -1.0, 2.64))
    body = p.finish(name)
    add_wheels(name, body, lod, track, base, r, 0.36, 0.2, tread=False)
    return body


def car_van_col():
    p = Part()
    p.box("black", (1.95, 4.6, 2.3), loc=(0, 0, 1.4))
    return p.finish("car_van_col")


# ------------------------------------------------------------------ small hatchback (ref 08: green / red / yellow city cars)
def car_hatch(lod, color="green_car", name="car_hatch"):
    p = Part()
    track, base, r = 0.78, 1.2, 0.36
    if lod == 2:
        p.box(color, (1.7, 3.6, 0.7), loc=(0, 0, 0.75))
        p.box("glass_blue", (1.5, 2.0, 0.55), loc=(0, -0.3, 1.35), taper=(0.85, 0.8))
        merged_wheels(p, track, base, r, 0.3)
        return p.finish(name)
    p.box(color, (1.7, 3.6, 0.65), loc=(0, 0, 0.75))
    p.box(color, (1.55, 2.1, 0.6), loc=(0, -0.35, 1.37), taper=(0.88, 0.78))
    p.box("glass_blue", (1.4, 0.06, 0.48), loc=(0, 0.6, 1.37), rot=(35, 0, 0))
    p.box("glass_blue", (1.3, 0.06, 0.42), loc=(0, -1.33, 1.37), rot=(-25, 0, 0))
    for s in (1, -1):
        p.box("glass_blue", (0.06, 1.5, 0.38), loc=(s * 0.74, -0.35, 1.38))
        p.cyl("eye_white", 0.13, 0.08, seg_for(lod, 8, 6, 6), loc=(s * 0.55, 1.8, 0.85), rot=(90, 0, 0))
    p.box("chassis", (1.75, 0.2, 0.18), loc=(0, 1.82, 0.55))
    p.box("chassis", (1.75, 0.2, 0.18), loc=(0, -1.82, 0.55))
    if lod == 0:
        p.box("ember", (0.3, 0.05, 0.12), loc=(0.6, -1.81, 0.85))
        p.box("ember", (0.3, 0.05, 0.12), loc=(-0.6, -1.81, 0.85))
    body = p.finish(name)
    add_wheels(name, body, lod, track, base, r, 0.3, 0.18, tread=False)
    return body


def car_hatch_col():
    p = Part()
    p.box("black", (1.75, 3.7, 1.5), loc=(0, 0, 0.95))
    return p.finish("car_hatch_col")


VEHICLES = [
    # car_hero is built by hero_car.py (detailed clay model) — not here
    ("car_jeep_open", car_jeep_open, car_jeep_open_col),
    ("car_buggy", car_buggy, car_buggy_col),
    ("car_van", car_van, car_van_col),
    ("car_hatch", car_hatch, car_hatch_col),
]

if globals().get("MODE") == "preview":
    preview([b for _, b, _ in VEHICLES], globals().get("PREVIEW_PATH"), lod=int(globals().get("LOD", "0")), cols=5)
    result = {"preview": "written"}
elif globals().get("MODE") == "library":   # only define the builders (island_chunks.py places them)
    pass
else:
    for name, build, col in VEHICLES:
        make_asset("vehicles", name, build, col=col)
    result = {"report": REPORT}

