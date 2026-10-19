# Terrain: 12 x 12 chunks of 200 m (2.4 km square, world centered on 0,0), collision chunks, world backdrop,
# ocean/pond/smoke meshes, plus data/props.json (prop placement) and data/world.json (roads, river, spawns).
#
# Blender coords: X east, Y north, Z up. JSON files use three.js coords: [x, height, -y].
# Chunk "i_j": i = column (west -> east), j = row (south -> north); chunk covers
#   x in [-1200 + 200 i, -1000 + 200 i], y in [-1200 + 200 j, -1000 + 200 j].

DATA_DIR = globals().get("DATA_DIR", r"C:/project/New Game/data")
GRID = 32          # quads per chunk side (6.25 m)
CHUNKS = 12
SIZE = 200.0
HALF = CHUNKS * SIZE / 2
BACKDROP_GRID = 48

# ------------------------------------------------------------------ layout
PEAKS = [(-1000, 1050, 250, 190), (-780, 1120, 210, 160), (-1100, 780, 190, 170), (-560, 1140, 170, 150), (-880, 880, 120, 140)]
MESAS = [(720, 980, 70, 55), (1020, 420, 60, 45), (380, 1050, 50, 40)]
LAKES = [(-650, 690, 105), (-860, 520, 70)]                       # frozen lakes (ice)
OASIS = (680, 690, 55)
CAMPS = [("forest", 230, -560, 45), ("hub", 0, 0, 55), ("snow", -330, 980, 40), ("beach", -880, -330, 50),
         ("desert", 1000, 980, 40), ("cliff", -560, -80, 35)]
RIVER = [(350, 300), (520, -60), (700, -450), (820, -800), (900, -1150), (930, -1300)]

ROADS = [  # name, type, width, points
    ("coastal_highway", "asphalt", 12, [(-700, -1060), (-720, -700), (-660, -300), (-560, -80), (-480, 180), (-300, 380), (-150, 420)]),
    ("hub_to_beach", "dirt", 10, [(0, 0), (-300, -40), (-560, -80)]),
    ("hub_to_snow", "dirt", 10, [(0, 0), (-120, 220), (-150, 420)]),
    ("snow_switchbacks", "snow", 9, [(-150, 420), (-380, 600), (-260, 760), (-560, 840), (-330, 980), (-700, 1000), (-560, 1120)]),
    ("hub_to_desert", "dirt", 10, [(0, 0), (230, 260), (440, 520)]),
    ("desert_loop", "dirt", 11, [(680 + 260 * math.cos(a), 690 + 170 * math.sin(a)) for a in [2 * math.pi * k / 24 for k in range(25)]]),
    ("desert_to_mesas", "dirt", 9, [(940, 690), (1000, 980), (760, 1060)]),
    ("forest_loop", "dirt", 10, [(0, 0), (250, -200), (600, -270), (900, -310), (1000, -600), (800, -900), (500, -950), (230, -700), (100, -400), (0, 0)]),
    ("beach_track", "sand", 9, [(-560, -80), (-760, -200), (-880, -330), (-900, -620), (-820, -900)]),
]
ROAD_COLORS = {"asphalt": "asphalt", "dirt": "dirt", "snow": "snow_shade", "sand": "sand_dark"}


def clamp01(t):
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def sstep(a, b, x):
    t = clamp01((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def n2(x, y, s, seed=0.0):
    return noise.noise(Vector((x / s, y / s, seed)))


def fbm(x, y, s, octaves=3, seed=0.0):
    v, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        v += amp * n2(x, y, s / (2 ** o), seed + o * 3.1)
        tot += amp
        amp *= 0.5
    return v / tot


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-9
    t = clamp01(((px - ax) * dx + (py - ay) * dy) / L2)
    qx, qy = ax + dx * t, ay + dy * t
    return math.hypot(px - qx, py - qy), qx, qy


class Polyline:
    def __init__(self, pts, margin):
        self.pts = pts
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.box = (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)

    def nearest(self, x, y):
        if not (self.box[0] <= x <= self.box[2] and self.box[1] <= y <= self.box[3]):
            return 1e9, x, y
        best = (1e9, x, y)
        for (ax, ay), (bx, by) in zip(self.pts, self.pts[1:]):
            d = seg_dist(x, y, ax, ay, bx, by)
            if d[0] < best[0]:
                best = d
        return best


ROAD_LINES = [(name, kind, w, Polyline(pts, w / 2 + 14)) for name, kind, w, pts in ROADS]
RIVER_LINE = Polyline(RIVER, 40)


def biome_weights(x, y):
    wn = sstep(-110, 110, y + 260 * n2(x, y, 480, 9) + 60 * n2(x, y, 140, 29))
    we = sstep(-110, 110, x + 260 * n2(x, y, 480, 19) + 60 * n2(x, y, 140, 39))
    return {"snow": (1 - we) * wn, "desert": we * wn, "beach": (1 - we) * (1 - wn), "forest": we * (1 - wn)}


def coast_dist(x, y):
    xc = lerp(-1020 + 40 * math.sin(y / 170), -1150, sstep(400, 650, y))
    yc = -1110 + 25 * math.sin(x / 120)
    return min(x - xc, y - yc)


def biome_height(x, y, w):
    snow = 70 + 26 * fbm(x, y, 170, 3, 1) + 60 * sstep(950, 1150, y + 60 * n2(x, y, 120, 12)) * (1 + 0.5 * n2(x, y, 90, 13))
    for px, py, ph, sig in PEAKS:
        d2 = (x - px) ** 2 + (y - py) ** 2
        snow += ph * math.exp(-d2 / (2 * sig * sig)) * (1 + 0.18 * n2(x, y, 60, 2))
    desert = 32 + 6.5 * math.sin((x + y) / 38 + 2.2 * n2(x, y, 260, 3)) + 5 * fbm(x, y, 110, 2, 4)
    for mx, my, r, mh in MESAS:
        d = math.hypot(x - mx, y - my) + 10 * n2(x, y, 40, 5)
        desert += mh * sstep(r + 22, r, d)
    desert += 75 * sstep(1020, 1070, x + 25 * n2(x, y, 90, 6)) + 75 * sstep(1060, 1110, y + 25 * n2(x, y, 90, 7))
    forest = 24 + 20 * fbm(x, y, 260, 3, 8) + 5 * fbm(x, y, 70, 2, 10)
    beach = 26 + 3 * fbm(x, y, 200, 2, 11)
    return w["snow"] * snow + w["desert"] * desert + w["forest"] * forest + w["beach"] * beach


def flatten_disc(h, x, y, cx, cy, r, level, edge=22):
    d = math.hypot(x - cx, y - cy)
    return lerp(level, h, sstep(r, r + edge, d))


def base_height(x, y):
    """Height before roads and canyon."""
    w = biome_weights(x, y)
    h = biome_height(x, y, w)
    for cx, cy, r in LAKES:
        h = flatten_disc(h, x, y, cx, cy, r, biome_height(cx, cy, biome_weights(cx, cy)) - 4, 25)
    ox, oy, orad = OASIS
    oasis_level = biome_height(ox, oy, biome_weights(ox, oy)) - 5
    h = flatten_disc(h, x, y, ox, oy, orad, oasis_level - 2.5, 30)
    for _, cx, cy, r in CAMPS:
        h = flatten_disc(h, x, y, cx, cy, r, biome_height(cx, cy, biome_weights(cx, cy)), 25)
    # coast: sea floor, beach band, then cliffs up to the land height
    c = coast_dist(x, y)
    beach_w = lerp(28, 190, (1 - sstep(350, 650, y)) * (1 - sstep(100, 400, x)))
    if c < 0:
        return max(-14.0, -0.8 + c * 0.06)
    if c < beach_w:
        return lerp(-0.8, 4.0, (c / beach_w) ** 0.8)
    return lerp(4.0, h, sstep(beach_w, beach_w + 28, c))


def road_info(x, y):
    """(weight 0..1, flatten height, road kind, distance) of the strongest road at x,y."""
    best = (0.0, None, None, 1e9)
    for name, kind, w, line in ROAD_LINES:
        d, qx, qy = line.nearest(x, y)
        if d > w / 2 + 14:
            continue
        k = 1.0 - sstep(w / 2, w / 2 + 14, d)
        if k > best[0]:
            best = (k, (qx, qy), kind, d - w / 2)
    return best


_road_h_cache = {}


def road_height(q):
    key = (round(q[0], 1), round(q[1], 1))
    if key not in _road_h_cache:
        _road_h_cache[key] = max(1.5, base_height(*q))
    return _road_h_cache[key]


def canyon(x, y):
    d, _, _ = RIVER_LINE.nearest(x, y)
    return d


def height(x, y):
    h = base_height(x, y)
    k, q, kind, _ = road_info(x, y)
    if q is not None:
        h = lerp(h, road_height(q), k)
    d = canyon(x, y)
    if d < 24 and coast_dist(x, y) > -5:
        t = clamp01((d - 10) / 14)
        h = lerp(-3.0, h, t ** 0.7)
    return h


def face_color(x, y, h, nz):
    c = coast_dist(x, y)
    if h < -0.4:
        return "water_deep" if canyon(x, y) < 10 else "sand_dark"
    w = biome_weights(x, y)
    d_canyon = canyon(x, y)
    if d_canyon < 10:
        return "rock_dark"
    if d_canyon < 38 + 6 * n2(x, y, 25, 37) and h > 2:
        return "red_rock_dark" if h < 12 else "red_rock"
    k, q, kind, dist = road_info(x, y)
    if kind and dist < 0:
        return ROAD_COLORS[kind]
    beach_w = lerp(28, 190, (1 - sstep(350, 650, y)) * (1 - sstep(100, 400, x)))
    if c < beach_w + 2 and h < 6:
        return "sand" if n2(x, y, 25, 30) > -0.5 else "sand_dark"
    dom = max(w, key=w.get)
    if dom == "beach" and w["beach"] < 0.6 and w["forest"] > w["snow"]:
        dom = "forest"
    steep = nz < 0.72
    if steep:
        if dom in ("desert",) or d_canyon < 20 or (dom == "forest" and w["desert"] > 0.2):
            return "red_rock" if int(h // 6) % 2 == 0 else "red_rock_dark"
        if dom == "snow" and h > 140 and nz > 0.55:
            return "snow_shade"
        return "rock" if int(h // 8) % 2 == 0 else "rock_dark"
    for cx, cy, r in LAKES:
        if math.hypot(x - cx, y - cy) < r:
            return "ice" if n2(x, y, 30, 31) > -0.3 else "ice_dark"
    for name, cx, cy, r in CAMPS:
        if math.hypot(x - cx, y - cy) + 6 * n2(x, y, 12, 36) < r * 0.45:
            return {"snow": "snow_shade", "desert": "desert_dark", "beach": "sand"}.get(name, "dirt")
    if math.hypot(x - OASIS[0], y - OASIS[1]) < OASIS[2] + 12:
        return "grass"
    if dom == "snow":
        return "snow" if nz > 0.9 or n2(x, y, 35, 32) > 0.1 else "snow_shade"
    if dom == "desert":
        return "desert" if n2(x, y, 45, 33) > -0.35 else "desert_dark"
    if dom == "forest":
        v = n2(x, y, 60, 34)
        return "forest_floor" if v > 0.15 else "grass_dark" if v > -0.35 else "grass"
    return "grass" if n2(x, y, 50, 35) > -0.2 else "grass_dark"


# ------------------------------------------------------------------ mesh building
def low_height(x, y, r=26.0):
    """Conservative height for the far backdrop: never above the detailed terrain around it."""
    return min(height(x + dx, y + dy) for dx in (-r, -r / 2, 0, r / 2, r) for dy in (-r, -r / 2, 0, r / 2, r)) - 1.5


def grid_mesh(name, x0, y0, size, n, colored=True, hfn=None):
    """Clay-style terrain tile: heights smoothed once (padded grid, so neighbouring chunks match), per-vertex
    colors that blend softly, smooth shading."""
    step = size / n
    cx, cy = x0 + size / 2, y0 + size / 2
    hfn = hfn or height
    PAD = 3
    raw = [[hfn(x0 + (i - PAD) * step, y0 + (j - PAD) * step) for i in range(n + 1 + 2 * PAD)] for j in range(n + 1 + 2 * PAD)]
    near = [[canyon(x0 + (i - PAD) * step, y0 + (j - PAD) * step) < 45 for i in range(n + 1 + 2 * PAD)] for j in range(n + 1 + 2 * PAD)]
    G = raw
    for k in range(PAD):
        size_k = len(G) - 2
        nxt = [[0.0] * size_k for _ in range(size_k)]
        for j in range(size_k):
            for i in range(size_k):
                gj, gi = j + 1, i + 1
                ring = (G[gj - 1][gi] + G[gj + 1][gi] + G[gj][gi - 1] + G[gj][gi + 1]) / 4
                wgt = 0.5 if (k == 0 or near[j + k + 1][i + k + 1]) else 0.0
                nxt[j][i] = G[gj][gi] * (1 - wgt) + ring * wgt
        G = nxt
    H = G
    P = [[0.0] * (n + 3) for _ in range(n + 3)]
    for j in range(n + 3):
        for i in range(n + 3):
            P[j][i] = raw[j + PAD - 1][i + PAD - 1]
    for j in range(n + 1):
        for i in range(n + 1):
            P[j + 1][i + 1] = H[j][i]
    verts = [(i * step - size / 2, j * step - size / 2, H[j][i]) for j in range(n + 1) for i in range(n + 1)]
    faces = []
    for j in range(n):
        for i in range(n):
            a, b, c, d = j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i
            faces += [(a, b, c), (a, c, d)] if (i + j) % 2 == 0 else [(a, b, d), (b, c, d)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if colored:
        flat = []
        for j in range(n + 1):
            for i in range(n + 1):
                pj, pi = j + 1, i + 1
                gx = (P[pj][pi + 1] - P[pj][pi - 1]) / (2 * step)
                gy = (P[pj + 1][pi] - P[pj - 1][pi]) / (2 * step)
                nz = 1 / math.sqrt(1 + gx * gx + gy * gy)
                flat += list(C[face_color(x0 + i * step, y0 + j * step, H[j][i], nz)])
        attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        attr.data.foreach_set("color", flat)
        me.color_attributes.active_color = attr
    obj = bpy.data.objects.new(name, me)
    obj.location = (cx, cy, 0)
    work_collection().objects.link(obj)
    if colored:
        me.materials.append(vc_material())
        if size <= SIZE:
            road_ribbons(name, obj, x0, y0, size, H, step)
    return obj, H


def road_ribbons(name, chunk_obj, x0, y0, size, H, step):
    """Smooth crowned road strips over the terrain (child of the chunk), sampled every 3 m."""
    n = len(H) - 1

    def h_at(x, y):
        fx = min(max((x - x0) / step, 0), n - 1e-6)
        fy = min(max((y - y0) / step, 0), n - 1e-6)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        return (H[j][i] * (1 - tx) * (1 - ty) + H[j][i + 1] * tx * (1 - ty) + H[j + 1][i] * (1 - tx) * ty + H[j + 1][i + 1] * tx * ty)

    verts, faces, cols = [], [], []
    margin = 3.0
    for rname, kind, w, pts in ROADS:
        dense = []
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            k = max(1, int(L / 3.0))
            dense += [(ax + (bx - ax) * s / k, ay + (by - ay) * s / k) for s in range(k)]
        dense.append(pts[-1])
        run = []
        for p in dense + [None]:
            inside = p is not None and x0 - margin <= p[0] <= x0 + size + margin and y0 - margin <= p[1] <= y0 + size + margin and canyon(*p) > 24
            if inside:
                run.append(p)
                continue
            if len(run) >= 2:
                base = len(verts)
                for idx, (x, y) in enumerate(run):
                    a, b = run[max(idx - 1, 0)], run[min(idx + 1, len(run) - 1)]
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    L = math.hypot(dx, dy) or 1
                    nx, ny = -dy / L, dx / L
                    for off, lift, col in ((-w / 2, 0.12, "dirt_dark" if kind != "asphalt" else "asphalt"), (0, 0.3, ROAD_COLORS[kind]), (w / 2, 0.12, "dirt_dark" if kind != "asphalt" else "asphalt")):
                        px, py = x + nx * off, y + ny * off
                        verts.append((px - x0 - size / 2, py - y0 - size / 2, h_at(px, py) + lift))
                        cols.append(col)
                for idx in range(len(run) - 1):
                    r0, r1 = base + idx * 3, base + (idx + 1) * 3
                    faces += [(r0, r1, r1 + 1, r0 + 1), (r0 + 1, r1 + 1, r1 + 2, r0 + 2)]
                if kind == "asphalt":
                    for idx in range(0, len(run) - 1, 3):
                        x, y = run[idx]
                        a, b = run[idx], run[idx + 1]
                        dx, dy = b[0] - a[0], b[1] - a[1]
                        L = math.hypot(dx, dy) or 1
                        ux, uy, nx, ny = dx / L, dy / L, -dy / L * 0.12, dx / L * 0.12
                        q = len(verts)
                        z = h_at(x, y) + 0.33
                        for sx, sy in ((-nx, -ny), (nx, ny)):
                            verts.append((x + sx - x0 - size / 2, y + sy - y0 - size / 2, z))
                            verts.append((x + sx + ux * 2.0 - x0 - size / 2, y + sy + uy * 2.0 - y0 - size / 2, z))
                            cols += ["road_line", "road_line"]
                        faces.append((q, q + 1, q + 3, q + 2))
            run = []
    if not faces:
        return None
    me = bpy.data.meshes.new(name + "_roads")
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    flat = []
    for col in cols:
        flat += list(C[col])
    attr.data.foreach_set("color", flat)
    me.color_attributes.active_color = attr
    me.materials.append(vc_material())
    obj = bpy.data.objects.new(name + "_roads", me)
    work_collection().objects.link(obj)
    obj.parent = chunk_obj
    return obj


def three(x, y, z):
    return [round(x, 2), round(z, 2), round(-y, 2)]


def chunk_key(x, y):
    i = int((x + HALF) // SIZE)
    j = int((y + HALF) // SIZE)
    return f"{min(max(i, 0), CHUNKS - 1)}_{min(max(j, 0), CHUNKS - 1)}"


# ------------------------------------------------------------------ props placement
PROPS = []


def place(kind, x, y, yaw=0.0, scale=1.0, z=None):
    z = height(x, y) if z is None else z
    PROPS.append({"type": kind, "chunk": chunk_key(x, y), "position": three(x, y, z),
                  "rotation": [0, round(yaw, 1), 0], "scale": [round(scale, 2)] * 3})


def yaw_for(dx, dy):
    return math.degrees(math.atan2(-dx, dy))


def clear_of_features(x, y, road_margin=6):
    k, q, kind, dist = road_info(x, y)
    if kind and dist < road_margin:
        return False
    if canyon(x, y) < 36:
        return False
    for _, cx, cy, r in CAMPS:
        if math.hypot(x - cx, y - cy) < r + 8:
            return False
    for cx, cy, r in LAKES:
        if math.hypot(x - cx, y - cy) < r + 6:
            return False
    if math.hypot(x - OASIS[0], y - OASIS[1]) < OASIS[2] + 6:
        return False
    return True


def slope_ok(x, y, limit=0.35):
    e = 3.0
    gx = (height(x + e, y) - height(x - e, y)) / (2 * e)
    gy = (height(x, y + e) - height(x, y - e)) / (2 * e)
    return math.hypot(gx, gy) < limit


def scatter():
    rnd = random.Random(42)
    step = 10.0
    yv = -HALF + step / 2
    while yv < HALF:
        xv = -HALF + step / 2
        while xv < HALF:
            x, y = xv + rnd.uniform(-6, 6), yv + rnd.uniform(-6, 6)
            xv += step
            c = coast_dist(x, y)
            if c < 10:
                continue
            w = biome_weights(x, y)
            dom = max(w, key=w.get)
            h = height(x, y)
            dens = n2(x, y, 140, 50)
            r = rnd.random()
            if not clear_of_features(x, y) or not slope_ok(x, y, 0.55):
                continue
            beach_w = lerp(28, 190, (1 - sstep(350, 650, y)) * (1 - sstep(100, 400, x)))
            if c < beach_w:
                if r < 0.01 and c > 20:
                    place("tree_palm", x, y, rnd.uniform(0, 360), rnd.uniform(0.9, 1.2))
                elif r < 0.016:
                    place("rock_large", x, y, rnd.uniform(0, 360), rnd.uniform(0.6, 1.3))
                continue
            if dom == "forest" or (dom == "beach" and w["forest"] > 0.2):
                if (dens > -0.2 and r < 0.62) or r < 0.06:
                    place("tree_pine", x, y, rnd.uniform(0, 360), rnd.uniform(0.8, 1.4))
                elif r < 0.66:
                    place(rnd.choice(["bush", "rock_small", "stump", "log", "grass_tuft"]), x, y, rnd.uniform(0, 360), rnd.uniform(0.8, 1.3))
            elif dom == "beach":
                if r < 0.06:
                    place("tree_pine", x, y, rnd.uniform(0, 360), rnd.uniform(0.8, 1.2))
                elif r < 0.09:
                    place(rnd.choice(["bush", "grass_tuft", "rock_small"]), x, y, rnd.uniform(0, 360))
            elif dom == "snow":
                if h < 150 and ((dens > -0.1 and r < 0.3) or r < 0.03):
                    place("tree_pine_snow", x, y, rnd.uniform(0, 360), rnd.uniform(0.8, 1.3))
                elif r < 0.33:
                    place("rock_snow", x, y, rnd.uniform(0, 360), rnd.uniform(0.6, 1.4))
            elif dom == "desert":
                if r < 0.02:
                    place("cactus_saguaro", x, y, rnd.uniform(0, 360), rnd.uniform(0.8, 1.3))
                elif r < 0.03:
                    place("rock_red", x, y, rnd.uniform(0, 360), rnd.uniform(0.5, 1.5))
        yv += step


def road_point(name, t):
    pts = dict((n, p) for n, _, _, p in ROADS)[name]
    seg_lens = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    target = t * sum(seg_lens)
    for (a, b), L in zip(zip(pts, pts[1:]), seg_lens):
        if target <= L:
            f = target / L
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, b[0] - a[0], b[1] - a[1]
        target -= L
    a, b = pts[-2], pts[-1]
    return b[0], b[1], b[0] - a[0], b[1] - a[1]


def seg_intersect(p1, p2, p3, p4):
    d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0])
    if abs(d) < 1e-9:
        return None
    t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d
    u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d
    if 0 <= t <= 1 and 0 <= u <= 1:
        return p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]), p2[0] - p1[0], p2[1] - p1[1]
    return None


BRIDGES = []


def place_landmarks():
    rnd = random.Random(7)
    # bridges where roads cross the river canyon
    for name, kind, w, pts in ROADS:
        for a, b in zip(pts, pts[1:]):
            for r1, r2 in zip(RIVER, RIVER[1:]):
                hit = seg_intersect(a, b, r1, r2)
                if hit:
                    x, y, dx, dy = hit
                    L = math.hypot(dx, dy)
                    ux, uy = dx / L, dy / L
                    zr = max(road_height((x - ux * 20, y - uy * 20)), road_height((x + ux * 20, y + uy * 20)))
                    place("bridge_suspension", x, y, yaw_for(dx, dy), 1.0, z=zr)
                    BRIDGES.append({"road": name, "position": three(x, y, zr), "yaw": round(yaw_for(dx, dy), 1)})
    # hub: start gate, flag, signposts, lamps
    place("gate_arch", 60, 40, yaw_for(230, 260))
    place("flag_rainbow", -20, 25)
    for nm in ("hub_to_beach", "hub_to_snow", "hub_to_desert"):
        x, y, dx, dy = road_point(nm, 0.12)
        place("signpost", x + 8, y + 2, yaw_for(dx, dy))
    # camps
    for name, cx, cy, r in CAMPS:
        n_tents = 4 if name != "hub" else 3
        for k in range(n_tents):
            a = 2 * math.pi * (k + 0.3) / n_tents
            place(["tent_orange", "tent_blue", "tent_red"][k % 3], cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55,
                  math.degrees(a) + 90)
        place("campfire_big" if name in ("beach", "snow") else "campfire", cx, cy)
        for k in range(5):
            a = 2 * math.pi * k / 5 + 0.4
            place("camp_chair", cx + math.cos(a) * 5, cy + math.sin(a) * 5, math.degrees(a) + 90)
        if name in ("forest", "hub", "beach", "cliff"):
            place("caravan_trailer", cx + r * 0.75, cy - r * 0.2, rnd.uniform(0, 360))
            place("caravan_trailer", cx - r * 0.7, cy + r * 0.35, rnd.uniform(0, 360))
            place("picnic_table", cx + 10, cy + 12, 20)
            place("picnic_cooler", cx + 12, cy + 9)
        for k in range(2):
            a = 2 * math.pi * k / 2 + 0.9
            place("lamp_post", cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.9)
        place("wooden_crate", cx - 8, cy - 10, 15)
        place("barrel", cx - 9, cy - 8)
    # beach hangout (ref 07): wave ramp into the sea, pier, boats, umbrellas, towels
    place("ramp_wave_big", -985, -560, yaw_for(-1, 0.15), 1.0, z=0.0)
    place("dock_pier", -985, -760, yaw_for(-1, 0), 1.0, z=0.0)
    place("boat_small", -1012, -770, yaw_for(0, 1), 1.0, z=-0.5)
    place("boat_small", -1030, -735, yaw_for(0.3, 1), 1.0, z=-0.5)
    for k in range(14):
        x, y = -950 + rnd.uniform(-25, 30), -700 + k * 30 + rnd.uniform(-8, 8)
        if coast_dist(x, y) > 12:
            place("beach_umbrella", x, y, rnd.uniform(0, 360))
            place("beach_towel", x + 2.5, y + 1, rnd.uniform(0, 360))
    for k in range(10):
        x, y, dx, dy = road_point("coastal_highway", 0.05 + k * 0.05)
        place("fence_wood", x - 9, y, yaw_for(dx, dy) - 90)
    # desert stunt park (refs 02/09): loop, kickers, quarter pipe, oasis
    place("stunt_loop", 780, 910, yaw_for(1, 0.2))
    for t in (0.1, 0.3, 0.55, 0.8):
        x, y, dx, dy = road_point("desert_loop", t)
        place("ramp_kicker", x, y, yaw_for(dx, dy))
    place("ramp_quarterpipe", 860, 1040, yaw_for(0, 1))
    place("water_pond", OASIS[0], OASIS[1], 0, OASIS[2] + 4, z=base_height(*OASIS[:2]) + 2.0)
    for k in range(8):
        a = 2 * math.pi * k / 8
        place("tree_palm", OASIS[0] + math.cos(a) * (OASIS[2] + 14), OASIS[1] + math.sin(a) * (OASIS[2] + 14), rnd.uniform(0, 360), rnd.uniform(0.9, 1.2))
    for mx, my in ((520, 860), (900, 560), (1100, 760), (600, 1120)):
        place("rock_pillar_red", mx, my, rnd.uniform(0, 360), rnd.uniform(0.8, 1.4))
    # forest/canyon stunts (refs 02/03): kickers, plank bridges on the forest loop, quarter pipe
    for t in (0.18, 0.62, 0.86):
        x, y, dx, dy = road_point("forest_loop", t)
        place("ramp_kicker", x, y, yaw_for(dx, dy))
    for t in (0.35, 0.75):
        x, y, dx, dy = road_point("forest_loop", t)
        place("bridge_plank_small", x, y, yaw_for(dx, dy))
    place("ramp_quarterpipe", 1040, -420, yaw_for(1, 0))
    # tunnel portals in the cliff/mountain foot (ref 02)
    place("tunnel_portal", -820, 260, yaw_for(1, -0.4))
    place("tunnel_portal", -1050, 560, yaw_for(1, 0))
    # snow: frozen lake toys (ref 08), ski lift up the mountain (refs 05/08/09)
    lx, ly, lr = LAKES[0]
    place("soccer_ball_giant", lx + 20, ly - 10, 0, 1.0, z=height(lx, ly))
    for k in range(10):
        a = rnd.uniform(0, 2 * math.pi)
        place("ice_block", lx + math.cos(a) * (lr - 8), ly + math.sin(a) * (lr - 8), rnd.uniform(0, 360), rnd.uniform(0.8, 1.6))
    lift = [(-420 + (-980 + 420) * k / 8, 700 + (1020 - 700) * k / 8) for k in range(9)]
    for k, (x, y) in enumerate(lift):
        place("ski_lift_tower", x, y, yaw_for(-560, 320))
        if 0 < k < 8:
            nx, ny = lift[k + 1] if k + 1 < len(lift) else (x, y)
            place("gondola_cabin", (x + nx) / 2, (y + ny) / 2, yaw_for(-560, 320), 1.0, z=(height(x, y) + height(nx, ny)) / 2 + 9.5)
    place("flag_rainbow", -330, 1000)
    place("signpost", -150, 440, yaw_for(-1, 1))


def export_backdrop():
    out = f"{OUT_ROOT}/terrain"
    back, _ = grid_mesh("world_backdrop_lod", -HALF, -HALF, 2 * HALF, BACKDROP_GRID, hfn=low_height)
    bt = tris([back])
    export_objs([back], f"{out}/world_backdrop_lod.glb")
    remove([back])
    REPORT.append(f"backdrop {bt} tris")


def export_terrain():
    out = f"{OUT_ROOT}/terrain"
    counts = []
    for i in range(CHUNKS):
        for j in range(CHUNKS):
            x0, y0 = -HALF + i * SIZE, -HALF + j * SIZE
            obj, _ = grid_mesh(f"terrain_chunk_{i}_{j}", x0, y0, SIZE, GRID)
            parts = descendants(obj)
            counts.append(tris(parts))
            export_objs(parts, f"{out}/chunks/terrain_chunk_{i}_{j}.glb")
            remove(parts)
            col, _ = grid_mesh(f"collision_chunk_{i}_{j}", x0, y0, SIZE, GRID, colored=False)
            export_objs([col], f"{out}/collision/collision_chunk_{i}_{j}.glb")
            remove([col])
    REPORT.append(f"terrain: {len(counts)} chunks x {counts[0]} tris (+ collision)")
    export_backdrop()


def export_env():
    def ocean(lod):
        p = Part()
        p.box("water", (12000, 12000, 0.2), loc=(0, 0, -0.6))
        return p.finish("ocean_plane")

    def water_pond(lod):
        p = Part()
        p.cyl("water", 1.0, 0.1, seg_for(lod, 16, 12, 8), loc=(0, 0, -0.05))
        return p.finish("water_pond")

    def smoke_puff(lod):
        p = Part()
        p.ico("smoke", 0.35, 1, jitter=0.03, seed=3)
        return p.finish("smoke_puff")

    make_asset("env", "ocean_plane", ocean, lods=(0,))
    make_asset("env", "water_pond", water_pond, lods=(0, 1))
    make_asset("fx", "smoke_puff", smoke_puff, lods=(0,))


def export_data():
    scatter()
    place_landmarks()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(f"{DATA_DIR}/props.json", "w") as f:
        json.dump({"coordinateSystem": "three.js (x, y=up, z=-north), meters", "count": len(PROPS), "props": PROPS}, f, separators=(",", ":"))
    world = {
        "coordinateSystem": "three.js (x, y=up, z=-north), meters",
        "chunkSize": SIZE, "chunks": CHUNKS, "origin": "world center; chunk i_j spans x=[-1200+200i, -1000+200i], z=[1000-200j, 1200-200j]",
        "seaLevel": -0.5,
        "roads": [{"name": n, "type": k, "width": w, "points": [three(x, y, road_height((x, y))) for x, y in pts]} for n, k, w, pts in ROADS],
        "river": [three(x, y, -0.5) for x, y in RIVER],
        "bridges": BRIDGES,
        "lakes": [{"center": three(x, y, height(x, y)), "radius": r, "surface": "ice"} for x, y, r in LAKES],
        "oasis": {"center": three(OASIS[0], OASIS[1], base_height(*OASIS[:2]) + 2.0), "radius": OASIS[2]},
        "camps": [{"name": n, "center": three(x, y, height(x, y)), "radius": r} for n, x, y, r in CAMPS],
        "spawns": {"player": three(30, 20, height(30, 20) + 1.5), "playerYaw": round(yaw_for(230, 260), 1)},
    }
    with open(f"{DATA_DIR}/world.json", "w") as f:
        json.dump(world, f, indent=1)
    counts = {}
    for p_ in PROPS:
        counts[p_["type"]] = counts.get(p_["type"], 0) + 1
    REPORT.append(f"props.json: {len(PROPS)} placements {counts}")
    REPORT.append(f"bridges auto-placed: {len(BRIDGES)}")


STEP = globals().get("STEP", "all")
if STEP == "clay_preview":
    # Perspective EEVEE look at a 600 m area under the clay studio lighting (+ ocean plane).
    px, py = [float(v) for v in globals().get("CENTER", "230,-560").split(",")]
    area = float(globals().get("AREA", "600"))
    obj, _ = grid_mesh("terrain_area", px - area / 2, py - area / 2, area, int(area / 6.25))
    rd = road_ribbons("terrain_area", obj, px - area / 2, py - area / 2, area, _, area / int(area / 6.25))
    sea = Part()
    sea.box("water", (6000, 6000, 0.2), loc=(px, py, -0.6))
    sea_obj = sea.finish("sea_preview")
    sc = bpy.context.scene
    for lname, color, energy, rot, shadow in (("key", (1.0, 0.9, 0.78), 3.5, (45, 0, -40), True), ("fill", (0.72, 0.82, 1.0), 1.0, (60, 0, 150), False)):
        L = bpy.data.lights.new(lname, "SUN")
        L.color, L.energy, L.angle, L.use_shadow = color, energy, math.radians(10), shadow
        o = bpy.data.objects.new(lname, L)
        sc.collection.objects.link(o)
        o.rotation_euler = [math.radians(a) for a in rot]
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.74, 0.9, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.7
    sc.world = w
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = Vector((px, py - area * 0.55, height(px, py) + area * 0.42))
    cam.rotation_euler = (Vector((px, py + area * 0.1, height(px, py))) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 30
    cam.data.clip_end = 8000
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    sc.view_settings.view_transform = "AgX"
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.filepath = globals().get("PREVIEW_PATH")
    bpy.ops.render.render(write_still=True)
    result = {"preview": "written"}
elif STEP == "preview":
    obj, _ = grid_mesh("terrain_preview", -HALF, -HALF, 2 * HALF, int(globals().get("PREVIEW_GRID", "128")))
    obj.location = (0, 0, 0)
    sea = Part()
    sea.box("water", (3000, 3000, 0.2), loc=(0, 0, -0.6))
    sea_obj = sea.finish("sea_preview")
    sc = bpy.data.scenes.get("Preview") or bpy.data.scenes.new("Preview")
    for o in list(sc.collection.objects):
        sc.collection.objects.unlink(o)
    sc.collection.objects.link(obj)
    sc.collection.objects.link(sea_obj)
    cam_data = bpy.data.cameras.get("PreviewCam") or bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.get("PreviewCam") or bpy.data.objects.new("PreviewCam", cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 3000
    cam_data.clip_end = 20000
    cam.location = (0, -2600, 2600)
    cam.rotation_euler = (math.radians(45), 0, 0)
    if sc.world is None:
        sc.world = bpy.data.worlds.new("PreviewWorld")
    sc.world.color = (0.25, 0.45, 0.7)
    sc.view_settings.view_transform = "Standard"
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "VERTEX"
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1100
    sc.render.filepath = globals().get("PREVIEW_PATH")
    bpy.ops.render.render(write_still=True, scene=sc.name)
    remove([obj, sea_obj])
    result = {"preview": "written"}
else:
    if STEP in ("all", "env"):
        export_env()
    if STEP in ("all", "terrain"):
        export_terrain()
    if STEP == "backdrop":
        export_backdrop()
    if STEP in ("all", "data"):
        export_data()
    result = {"report": REPORT}
