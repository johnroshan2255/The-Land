# Camp, beach and roadside props (refs 02/03/06/07/08/09). Origin at base center, front = +Y.


def tent(lod, color="tent_orange", name="tent_orange"):
    p = Part()
    w, l, h = 2.4, 2.8, 1.9
    p.prism(color, [(-l / 2, 0), (l / 2, 0), (l / 2, 0.01), (-l / 2, 0.01)], w, loc=(0, 0, 0))
    p.poly(color, [(-w / 2, -l / 2, 0), (w / 2, -l / 2, 0), (0, -l / 2, h), (-w / 2, l / 2, 0), (w / 2, l / 2, 0), (0, l / 2, h)],
           [[0, 1, 2], [3, 5, 4], [0, 2, 5, 3], [1, 4, 5, 2], [0, 3, 4, 1]])
    if lod < 2:
        p.prism("black", [(0, 0), (0.9, 0), (0.45, 1.2)], 0.02, loc=(0, l / 2 + 0.01, 0), rot=(0, 0, 90))
    if lod == 0:
        p.cyl("wood_dark", 0.04, h + 0.25, 4, loc=(0, l / 2 + 0.02, (h + 0.25) / 2))
        p.cyl("wood_dark", 0.04, h + 0.25, 4, loc=(0, -l / 2 - 0.02, (h + 0.25) / 2))
        p.box(color, (0.05, l + 0.1, 0.05), loc=(0, 0, h + 0.02))
        for sy in (1, -1):
            p.box("rope", (0.03, 0.9, 0.03), loc=(0, sy * (l / 2 + 0.45), h * 0.55), rot=(sy * 62, 0, 0))
    return p.finish(name)


def tent_orange(lod):
    return tent(lod, "tent_orange", "tent_orange")


def tent_blue(lod):
    return tent(lod, "tent_blue", "tent_blue")


def tent_red(lod):
    return tent(lod, "tent_red", "tent_red")


def campfire(lod, big=False, name="campfire"):
    p = Part()
    k = 2.2 if big else 1.0
    n_logs = seg_for(lod, 5, 4, 3)
    for i in range(n_logs):
        a = 360 * i / n_logs
        ar = math.radians(a)
        p.cyl("trunk", 0.09 * k, 1.1 * k, 5, loc=(math.cos(ar) * 0.2 * k, math.sin(ar) * 0.2 * k, 0.3 * k), rot=(0, 62, a))
    if lod < 2:
        stones = 8 if lod == 0 else 6
        for i in range(stones):
            ar = 2 * math.pi * i / stones
            p.ico("rock", 0.14 * k, 0, loc=(math.cos(ar) * 0.65 * k, math.sin(ar) * 0.65 * k, 0.08 * k), scale=(1, 1, 0.7), seed=i)
    p.cone("fire_orange", 0.36 * k, 0.85 * k, 5, loc=(0, 0, 0.5 * k))
    p.cone("fire_yellow", 0.2 * k, 1.15 * k, 4, loc=(0.04 * k, 0.03 * k, 0.65 * k), rot=(0, 0, 36))
    if lod == 0:
        p.cone("ember", 0.18 * k, 0.6 * k, 4, loc=(0.25 * k, -0.15 * k, 0.4 * k), rot=(0, 10, 0))
        p.cone("fire_orange", 0.16 * k, 0.55 * k, 4, loc=(-0.22 * k, 0.15 * k, 0.4 * k), rot=(0, -10, 0))
    return p.finish(name)


def campfire_big(lod):
    return campfire(lod, big=True, name="campfire_big")


def caravan_trailer(lod):
    """Retro white camping trailer (refs 02/06/09)."""
    p = Part()
    L, W = 4.2, 2.1
    p.box("white", (W, L - 1.0, 1.6), loc=(0, -0.1, 1.35))
    p.cyl("white", W / 2 * 0.98, L - 1.0, seg_for(lod, 10, 8, 6), loc=(0, -0.1, 2.1), rot=(90, 0, 0), scale=(1, 0.45, 1))
    p.cyl("white", 0.95, W, seg_for(lod, 10, 8, 6), loc=(0, (L - 1.0) / 2 - 0.1, 1.55), rot=(0, 90, 0), scale=(1.2, 0.55, 1))
    p.cyl("white", 0.95, W, seg_for(lod, 10, 8, 6), loc=(0, -(L - 1.0) / 2 - 0.1, 1.55), rot=(0, 90, 0), scale=(1.2, 0.55, 1))
    p.box("trailer_stripe", (W + 0.02, L - 0.6, 0.18), loc=(0, -0.1, 1.15))
    p.cyl("tire", 0.33, 0.25, seg_for(lod, 8, 6, 6), loc=(W / 2 - 0.05, -0.2, 0.33), rot=(0, 90, 0))
    p.cyl("tire", 0.33, 0.25, seg_for(lod, 8, 6, 6), loc=(-W / 2 + 0.05, -0.2, 0.33), rot=(0, 90, 0))
    if lod < 2:
        p.box("glass_blue", (0.06, 1.0, 0.5), loc=(W / 2 + 0.01, 0.4, 1.75))
        p.box("glass_blue", (0.06, 1.0, 0.5), loc=(-W / 2 - 0.01, 0.4, 1.75))
        p.box("glass_blue", (1.2, 0.06, 0.4), loc=(0, (L - 1.0) / 2 + 0.45, 1.85), rot=(-20, 0, 0))
        p.box("trailer_stripe", (0.06, 0.65, 1.4), loc=(-W / 2 - 0.01, -0.9, 1.25))
    if lod == 0:
        p.box("metal_dark", (0.12, 1.0, 0.12), loc=(0, (L - 1.0) / 2 + 0.9, 0.65))
        p.cyl("metal_dark", 0.06, 0.6, 4, loc=(0, (L - 1.0) / 2 + 1.3, 0.35))
        p.box("lamp_glow", (0.25, 0.06, 0.25), loc=(-W / 2 - 0.02, -0.3, 2.05))
        p.box("canvas", (0.08, 1.6, 0.05), loc=(-W / 2 - 0.7, -0.3, 2.2), rot=(0, 15, 0))
    return p.finish("caravan_trailer")


def camp_chair(lod):
    p = Part()
    p.box("chair_blue", (0.6, 0.55, 0.06), loc=(0, 0, 0.42))
    p.box("chair_blue", (0.6, 0.06, 0.6), loc=(0, -0.3, 0.72), rot=(-12, 0, 0))
    for sx in (1, -1):
        p.box("metal_dark", (0.04, 0.75, 0.04), loc=(sx * 0.28, 0, 0.22), rot=(55, 0, 0))
        p.box("metal_dark", (0.04, 0.75, 0.04), loc=(sx * 0.28, 0, 0.22), rot=(-55, 0, 0))
    return p.finish("camp_chair")


def picnic_table(lod):
    p = Part()
    p.box("wood", (2.0, 0.8, 0.08), loc=(0, 0, 0.76))
    for sy in (1, -1):
        p.box("wood", (2.0, 0.3, 0.06), loc=(0, sy * 0.7, 0.45))
    for sx in (0.75, -0.75):
        p.box("wood_dark", (0.08, 1.7, 0.08), loc=(sx, 0, 0.4), rot=(0, 0, 0))
        p.box("wood_dark", (0.08, 0.08, 0.8), loc=(sx, 0.25, 0.4), rot=(-25, 0, 0))
        p.box("wood_dark", (0.08, 0.08, 0.8), loc=(sx, -0.25, 0.4), rot=(25, 0, 0))
    return p.finish("picnic_table")


def beach_umbrella(lod):
    p = Part()
    p.cyl("white", 0.04, 2.4, 4, loc=(0, 0, 1.2), rot=(0, 6, 0))
    seg = seg_for(lod, 8, 8, 6)
    verts = p.cone("umbrella_a", 1.3, 0.5, seg, loc=(0.13, 0, 2.3))
    side = sorted({f for v in verts for f in v.link_faces if len(f.verts) == 3}, key=lambda f: math.atan2(f.calc_center_median().y, f.calc_center_median().x - 0.13))
    for i, f in enumerate(side):
        if i % 2:
            for loop in f.loops:
                loop[p.col] = C["umbrella_b"]
    return p.finish("beach_umbrella")


def beach_towel(lod):
    p = Part()
    p.box("towel", (0.9, 1.8, 0.02), loc=(0, 0, 0.01))
    p.box("white", (0.9, 0.2, 0.021), loc=(0, 0.5, 0.01))
    return p.finish("beach_towel")


def lamp_post(lod):
    p = Part()
    p.cyl("metal_dark", 0.08, 4.0, seg_for(lod, 6, 5, 4), loc=(0, 0, 2.0))
    p.cyl("metal_dark", 0.2, 0.2, 6, loc=(0, 0, 0.1))
    p.box("metal_dark", (0.08, 0.7, 0.08), loc=(0, 0.3, 3.95))
    p.box("lamp_glow", (0.3, 0.3, 0.35), loc=(0, 0.6, 3.75), taper=(1.2, 1.2))
    if lod == 0:
        p.cone("metal_dark", 0.3, 0.2, 4, loc=(0, 0.6, 4.02), rot=(0, 0, 45))
    return p.finish("lamp_post")


def flag_rainbow(lod):
    """Rainbow banner flag on a pole (start point, refs 06/07/08/09)."""
    p = Part()
    p.cyl("metal_dark", 0.06, 4.2, seg_for(lod, 6, 5, 4), loc=(0, 0, 2.1))
    stripes = ["flag_purple", "flag_blue", "flag_green", "flag_yellow", "flag_orange", "flag_red"]
    if lod == 2:
        stripes = ["flag_purple", "flag_yellow", "flag_red"]
    h = 2.2 / len(stripes)
    for i, c in enumerate(stripes):
        p.box(c, (0.03, 0.9, h), loc=(0, 0.48, 1.9 + i * h + h / 2))
    if lod == 0:
        p.ico("flag_yellow", 0.1, 0, loc=(0, 0, 4.25))
    return p.finish("flag_rainbow")


def wooden_crate(lod):
    p = Part()
    p.box("crate", (1.0, 1.0, 1.0), loc=(0, 0, 0.5))
    if lod == 0:
        for sx in (1, -1):
            p.box("wood_dark", (0.03, 1.02, 0.12), loc=(sx * 0.5, 0, 0.5), rot=(45, 0, 0))
            p.box("wood_dark", (1.02, 0.03, 0.12), loc=(0, sx * 0.5, 0.5), rot=(0, 45, 0))
    return p.finish("wooden_crate")


def barrel(lod):
    p = Part()
    seg = seg_for(lod, 8, 6, 6)
    p.cyl("wood", 0.4, 1.1, seg, loc=(0, 0, 0.55), scale=(1, 1, 1))
    if lod == 0:
        for z in (0.2, 0.9):
            p.cyl("metal_dark", 0.41, 0.07, seg, loc=(0, 0, z))
    return p.finish("barrel")


def signpost(lod):
    p = Part()
    p.cyl("wood_dark", 0.08, 2.4, 5, loc=(0, 0, 1.2))
    p.box("wood_light", (0.06, 1.1, 0.3), loc=(0, 0.35, 2.1), rot=(0, 0, 0))
    p.box("wood_light", (0.06, 1.0, 0.28), loc=(0, -0.3, 1.7), rot=(0, 0, 20))
    if lod == 0:
        p.prism("wood_light", [(0.9, 1.95), (1.12, 2.1), (0.9, 2.25)], 0.06)
    return p.finish("signpost")


def boat_small(lod):
    """Small red/white speedboat at the beach dock (refs 06/07/09)."""
    p = Part()
    profile = [(-2.0, 0.6), (2.2, 0.9), (2.6, 0.95), (2.0, 0.15), (-2.0, 0.1)]
    p.prism("boat_red", profile, 1.6)
    p.prism("white", [(-2.0, 0.9), (2.4, 0.95), (2.6, 0.97), (-2.0, 0.6)], 1.62)
    if lod < 2:
        p.box("white", (1.3, 2.6, 0.2), loc=(0, -0.2, 0.85))
        p.box("glass_blue", (1.1, 0.06, 0.4), loc=(0, 0.6, 1.15), rot=(-25, 0, 0))
    if lod == 0:
        p.box("black", (0.35, 0.3, 0.5), loc=(0, -2.15, 0.6))
        p.box("chair_blue", (0.5, 0.5, 0.3), loc=(0.35, -0.3, 1.05))
        p.box("chair_blue", (0.5, 0.5, 0.3), loc=(-0.35, -0.3, 1.05))
    return p.finish("boat_small")


def soccer_ball_giant(lod):
    """Giant football physics toy on the frozen lake (ref 08). Diameter 3 m."""
    p = Part()
    verts = p.ico("ball_white", 1.5, 2 if lod == 0 else 1, loc=(0, 0, 1.5))
    faces = list({f for v in verts for f in v.link_faces})
    faces.sort(key=lambda f: tuple(round(c, 3) for c in f.calc_center_median()))
    rnd = random.Random(5)
    for f in faces:
        if rnd.random() < 0.28:
            for loop in f.loops:
                loop[p.col] = C["ball_black"]
    return p.finish("soccer_ball_giant")


def picnic_cooler(lod):
    p = Part()
    p.box("flag_blue", (0.7, 0.45, 0.4), loc=(0, 0, 0.2))
    p.box("white", (0.72, 0.47, 0.08), loc=(0, 0, 0.44))
    return p.finish("picnic_cooler")


CAMP = [
    ("tent_orange", tent_orange, (0, 1, 2)),
    ("tent_blue", tent_blue, (0, 1, 2)),
    ("tent_red", tent_red, (0, 1, 2)),
    ("campfire", campfire, (0, 1, 2)),
    ("campfire_big", campfire_big, (0, 1, 2)),
    ("caravan_trailer", caravan_trailer, (0, 1, 2)),
    ("camp_chair", camp_chair, (0,)),
    ("picnic_table", picnic_table, (0,)),
    ("picnic_cooler", picnic_cooler, (0,)),
    ("beach_umbrella", beach_umbrella, (0, 2)),
    ("beach_towel", beach_towel, (0,)),
    ("lamp_post", lamp_post, (0, 1)),
    ("flag_rainbow", flag_rainbow, (0, 2)),
    ("wooden_crate", wooden_crate, (0, 1)),
    ("barrel", barrel, (0, 1)),
    ("signpost", signpost, (0, 1)),
    ("boat_small", boat_small, (0, 1, 2)),
    ("soccer_ball_giant", soccer_ball_giant, (0, 1)),
]

if globals().get("MODE") == "preview":
    preview([b for _, b, _ in CAMP], globals().get("PREVIEW_PATH"), lod=int(globals().get("LOD", "0")), cols=6)
    result = {"preview": "written"}
elif globals().get("MODE") == "library":   # only define the builders (island_chunks.py places them)
    pass
else:
    for name, build, lods in CAMP:
        make_asset("props", name, build, lods=lods)
    result = {"report": REPORT}
