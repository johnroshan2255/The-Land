# Nature props (refs 02/03/04/05/06/09). Origin at the base center on the ground.


def tree_pine(lod, snow=False, name="tree_pine"):
    p = Part()
    seg = seg_for(lod, 7, 6, 5)
    p.cyl("trunk", 0.28, 1.6, seg_for(lod, 6, 5, 4), loc=(0, 0, 0.8))
    tiers = [(2.2, 3.0, 1.3), (1.75, 2.6, 2.9), (1.25, 2.3, 4.4), (0.8, 2.0, 5.8)]
    if lod == 1:
        tiers = [(2.1, 3.4, 1.3), (1.5, 3.0, 3.3), (0.95, 2.6, 5.2)]
    if lod == 2:
        tiers = [(2.1, 6.4, 1.1)]
    for i, (r, h, z) in enumerate(tiers):
        color = "pine" if i % 2 == 0 else "pine_dark"
        p.cone(color, r, h, seg, loc=(0, 0, z + h / 2), rot=(0, 0, i * 25))
        if snow:
            p.cone("snow", r * 0.9, h * 0.8, seg, loc=(0, 0, z + h * 0.6 + 0.05), rot=(0, 0, i * 25))
    return p.finish(name)


def tree_pine_snow(lod):
    return tree_pine(lod, snow=True, name="tree_pine_snow")


def tree_palm(lod):
    p = Part()
    n = seg_for(lod, 6, 4, 3)
    x = 0.0
    for i in range(n):
        h = 5.5 / n
        p.cyl("palm_trunk", 0.32 - i * 0.03, h, seg_for(lod, 6, 5, 4), loc=(x, 0, i * h + h / 2), rot=(0, 4 + i * 3, 0))
        x += h * math.sin(math.radians(4 + i * 3))
    top = (x, 0, 5.5)
    leaves = seg_for(lod, 7, 6, 5)
    for i in range(leaves):
        a = 360 * i / leaves
        ar = math.radians(a)
        cx, cy = top[0] + math.cos(ar) * 1.4, math.sin(ar) * 1.4
        p.box("palm_leaf" if i % 2 else "pine", (2.8, 0.7, 0.08), loc=(cx, cy, top[2] - 0.3), rot=(0, 25, a), taper=None)
    if lod == 0:
        for i in range(3):
            ar = math.radians(120 * i)
            p.ico("palm_trunk", 0.18, 0, loc=(top[0] + math.cos(ar) * 0.3, math.sin(ar) * 0.3, top[2] - 0.35))
    return p.finish("tree_palm")


def cactus_saguaro(lod):
    p = Part()
    seg = seg_for(lod, 8, 6, 5)
    p.cyl("cactus", 0.42, 4.2, seg, loc=(0, 0, 2.1))
    p.cone("cactus", 0.42, 0.5, seg, loc=(0, 0, 4.45))
    arms = [((0.95, 0, 1.9), 1), ((-0.85, 0, 2.6), -1)] if lod < 2 else [((0.95, 0, 1.9), 1)]
    for (ax, ay, az), s in arms:
        p.cyl("cactus_dark", 0.27, 0.75, seg, loc=(ax / 2 + 0.1 * s, 0, az), rot=(0, 90, 0))
        p.cyl("cactus", 0.27, 1.5, seg, loc=(ax, ay, az + 0.75))
        p.cone("cactus", 0.27, 0.3, seg, loc=(ax, ay, az + 1.65))
    if lod == 0:
        for i in range(4):
            a = math.radians(90 * i + 45)
            p.box("cactus_dark", (0.06, 0.06, 3.6), loc=(math.cos(a) * 0.4, math.sin(a) * 0.4, 2.1))
    return p.finish("cactus_saguaro")


def bush(lod):
    p = Part()
    sub = 1 if lod == 0 else 0
    blobs = [((0, 0, 0.55), 0.8), ((0.6, 0.2, 0.4), 0.55), ((-0.5, -0.25, 0.4), 0.6)]
    for i, (loc, r) in enumerate(blobs if lod < 2 else blobs[:1]):
        p.ico("bush" if i else "grass_dark", r, sub, loc=loc, jitter=0.08 * r, seed=i)
    return p.finish("bush")


def grass_tuft(lod):
    p = Part()
    for i in range(5):
        a = 72 * i
        ar = math.radians(a)
        p.box("grass_dark" if i % 2 else "grass", (0.08, 0.02, 0.45), loc=(math.cos(ar) * 0.08, math.sin(ar) * 0.08, 0.2),
              rot=(0, 18, a), taper=(0.2, 1))
    return p.finish("grass_tuft")


def rock(lod, name, color, dark, r, scale, seed, sub_hi=1):
    p = Part()
    sub = sub_hi if lod == 0 else 0
    p.ico(color, r, sub, loc=(0, 0, r * scale[2] * 0.6), scale=scale, jitter=r * 0.15, seed=seed)
    if lod == 0 and r > 1:
        p.ico(dark, r * 0.55, 0, loc=(r * 0.9, r * 0.3, r * 0.3), scale=(1.1, 0.9, 0.7), jitter=r * 0.1, seed=seed + 1)
    return p.finish(name)


def rock_small(lod):
    return rock(lod, "rock_small", "rock", "rock_dark", 0.5, (1.2, 1.0, 0.75), 3, sub_hi=0)


def rock_large(lod):
    return rock(lod, "rock_large", "rock", "rock_dark", 2.0, (1.3, 1.0, 0.8), 7)


def rock_red(lod):
    """Red sandstone boulder (desert / canyon)."""
    return rock(lod, "rock_red", "red_rock", "red_rock_dark", 1.8, (1.4, 1.1, 0.85), 11)


def rock_snow(lod):
    p = Part()
    sub = 1 if lod == 0 else 0
    p.ico("rock_dark", 1.6, sub, loc=(0, 0, 0.9), scale=(1.3, 1.0, 0.8), jitter=0.25, seed=21)
    p.ico("snow", 1.2, sub, loc=(0, 0, 1.55), scale=(1.3, 1.0, 0.45), jitter=0.12, seed=22)
    return p.finish("rock_snow")


def rock_pillar_red(lod):
    """Stacked red-rock hoodoo/mesa pillar seen in the desert (refs 02/09)."""
    p = Part()
    layers = [(6.0, 5.0, 3.0), (5.2, 4.4, 3.0), (5.6, 4.6, 2.2), (4.6, 3.8, 2.6)]
    if lod == 2:
        layers = [(5.6, 4.6, 10.8)]
    z = 0.0
    for i, (sx, sy, h) in enumerate(layers):
        p.box("red_rock" if i % 2 == 0 else "red_rock_dark", (sx, sy, h), loc=(0.2 * (i % 2), 0.15 * i, z + h / 2),
              rot=(0, 0, 8 * i), taper=(0.92, 0.92))
        z += h
    if lod == 0:
        p.box("red_rock_dark", (2.0, 1.6, 1.2), loc=(2.8, 1.6, 0.6), rot=(0, 0, 20))
        p.box("red_rock", (1.4, 1.2, 0.8), loc=(-2.6, -1.8, 0.4), rot=(0, 0, -15))
    return p.finish("rock_pillar_red")


def log(lod):
    p = Part()
    seg = seg_for(lod, 7, 6, 5)
    p.cyl("trunk", 0.32, 4.0, seg, loc=(0, 0, 0.32), rot=(0, 90, 0))
    p.cyl("wood_light", 0.26, 4.04, seg, loc=(0, 0, 0.32), rot=(0, 90, 0), caps=True)
    return p.finish("log")


def stump(lod):
    p = Part()
    p.cyl("trunk", 0.45, 0.7, seg_for(lod, 7, 6, 5), loc=(0, 0, 0.35), r2=0.38)
    p.cyl("wood_light", 0.36, 0.04, seg_for(lod, 7, 6, 5), loc=(0, 0, 0.71))
    return p.finish("stump")


def ice_block(lod):
    p = Part()
    p.box("ice", (1.0, 1.0, 1.0), loc=(0, 0, 0.5), rot=(0, 0, 10))
    if lod == 0:
        p.box("ice_dark", (0.7, 0.7, 0.6), loc=(0.75, 0.2, 0.3), rot=(0, 0, -15))
    return p.finish("ice_block")


NATURE = [
    ("tree_pine", tree_pine, (0, 1, 2)),
    ("tree_pine_snow", tree_pine_snow, (0, 1, 2)),
    ("tree_palm", tree_palm, (0, 1, 2)),
    ("cactus_saguaro", cactus_saguaro, (0, 1, 2)),
    ("bush", bush, (0, 1, 2)),
    ("grass_tuft", grass_tuft, (0,)),
    ("rock_small", rock_small, (0,)),
    ("rock_large", rock_large, (0, 1)),
    ("rock_red", rock_red, (0, 1)),
    ("rock_snow", rock_snow, (0, 1)),
    ("rock_pillar_red", rock_pillar_red, (0, 1, 2)),
    ("log", log, (0,)),
    ("stump", stump, (0,)),
    ("ice_block", ice_block, (0,)),
]

if globals().get("MODE") == "preview":
    preview([b for _, b, _ in NATURE], globals().get("PREVIEW_PATH"), lod=int(globals().get("LOD", "0")), cols=7)
    result = {"preview": "written"}
else:
    for name, build, lods in NATURE:
        make_asset("nature", name, build, lods=lods)
    result = {"report": REPORT}
