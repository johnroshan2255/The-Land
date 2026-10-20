# Master island terrain: ONE continuous 2400 x 2400 m mesh (no chunks), clay/toy look, vertex colors only.
#   node tools/blender/headless.mjs tools/blender/island_master.py [PREVIEW_PATH=x.png] [BLEND_PATH=x.blend] [GRID_N=86]
# Blender coords: X east, Y north, Z up, sea level z = 0. Quadrants: NW snow + frozen lake, NE red desert + mesas,
# SW sunset beach + ocean, SE forest + S-shaped river gorge. A recessed road loop links all four, with a coastal
# highway and a network of trails branching off it (road colour follows the biome the road runs through).
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
RIVER_BED, RIVER_W0, RIVER_W1 = -18.0, 14.0, 30.0   # steep-walled canyon (refs 02/04/09): 60 m rim to rim
ROAD_SHOULDER = 16.0
LOOP_HW, SPUR_HW = 5.0, 4.0     # road half widths (m): 10 m asphalt/dirt loop, 8 m dirt trails

PAL = {"snow": "#EBF2FA", "ice": "#4EE3E3", "terracotta": "#C85A32", "desert_sand": "#E8A868",
       "beach": "#F2D492", "forest": "#60993E", "cliff": "#825234", "asphalt": "#3A3D40", "dirt": "#966844",
       "snow_track": "#ADBFD1", "desert_track": "#A0623A", "beach_track": "#D2B07C", "snow_rock": "#8C8A96"}


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


def _oval(cx, cy, a, b, n=16, rot=0.0):
    return [(cx + a * math.cos(t) * math.cos(rot) - b * math.sin(t) * math.sin(rot),
             cy + a * math.cos(t) * math.sin(rot) + b * math.sin(t) * math.cos(rot)) for t in [2 * math.pi * k / n for k in range(n)]]


def _eight(cx, cy, a, n=24):
    return [(cx + a * math.sin(t), cy + a * math.sin(t) * math.cos(t)) for t in [2 * math.pi * k / n for k in range(n)]]


# Closed play tracks (refs 02/04: dirt ovals and figure-8s in the desert, a pump track in the forest). "track" gets
# raised berms on its edges, "pump" gets rollers along its length.
TRACKS = [
    ("desert_oval", "track", _oval(180, 930, 95, 55)),
    ("desert_eight", "track", _eight(390, 820, 75)),
    ("forest_pump", "pump", _oval(860, -140, 32, 18, 12, 0.5)),
]
# Every other road: (name, class, control points), built in this order. A road may start or end on any road listed
# before it: that end is snapped onto it and the heights are blended in. Every road joins the network at both ends
# or ends at a destination (dock, park, canyon jump), so there are no dead ends. "highway" = 10 m wide, asphalt on
# the coast; "trail" = 8 m. Roads crossing the river canyon get a rope bridge (see BRIDGES). The surface colour comes
# from the biome under the road (see road_color).
ROADS = [
    ("forest_east", "trail", [(450, -330), (620, -260), (780, -300), (900, -250), (1060, -200)]),
    ("forest_north", "trail", [(620, -260), (680, -130), (800, -40), (960, 10)]),
    ("forest_ne_loop", "trail", [(1060, -200), (1110, -90), (1050, 0), (960, 10)]),
    ("desert_edge", "trail", [(600, 150), (760, 120), (920, 100), (1040, 40), (1050, 0)]),
    ("mesa_trail", "trail", [(420, 620), (700, 690), (860, 650), (790, 540), (720, 420), (740, 250), (760, 120)]),
    ("river_bend", "trail", [(780, -300), (730, -420), (690, -560), (705, -690), (690, -830), (690, -960)]),
    ("forest_far", "trail", [(1060, -200), (1150, -300), (1130, -470), (1090, -600), (1060, -800), (960, -990), (820, -1030), (690, -960)]),
    ("forest_south", "trail", [(100, -560), (200, -650), (150, -760), (20, -830), (-120, -820), (-250, -700), (-200, -500)]),
    ("forest_to_desert", "trail", [(290, -460), (230, -300), (140, -150), (180, 30), (320, 170), (260, 340), (400, 440), (560, 430)]),
    ("lake_road", "trail", [(-150, 200), (-300, 300), (-360, 440), (-330, 600), (-360, 800), (-470, 960), (-640, 1030)]),
    ("snow_north", "trail", [(60, 700), (-80, 860), (-220, 960), (-330, 1000), (-470, 960)]),
    ("coast_highway", "highway", [(-400, -200), (-560, -150), (-720, -110), (-880, -60), (-1050, -10), (-1110, 120), (-1080, 300),
                                  (-1020, 480), (-1010, 680), (-950, 880), (-800, 1040), (-640, 1030)]),
    # beach trail: down to the dock on the sand, along the beach and back up to the coast highway
    ("beach_trail", "trail", [(-400, -200), (-500, -280), (-570, -325), (-690, -312), (-800, -235), (-880, -60)]),
    ("bend_to_loop", "trail", [(690, -560), (580, -500), (470, -470), (390, -410)]),
    ("forest_west", "trail", [(140, -150), (20, -230), (-90, -350), (-200, -500)]),
    # access roads to the play areas
    ("stunt_spur", "trail", [(600, 150), (500, 215), (430, 222), (360, 215), (320, 170)]),   # past the stunt park gate
    ("snowpark_spur", "trail", [(-345, 700), (-318, 700), (-300, 700)]),
    ("jump_spur", "trail", [(470, -470), (460, -560), (445, -603), (395, -590), (330, -555), (290, -460)]),   # past the canyon jump
    ("oval_spur", "trail", [(60, 700), (150, 800), (180, 872)]),
    ("eight_spur", "trail", [(420, 620), (400, 700), (345, 785)]),
    ("pump_spur", "trail", [(800, -40), (840, -100), (850, -122)]),
]
ROAD_HW = {"highway": LOOP_HW, "trail": SPUR_HW, "track": 6.0, "pump": 3.5}
ROAD_SNAP = 40.0   # a road end this close to an earlier road joins it
MAX_GRADE = {"highway": 0.15, "trail": 0.2, "track": 0.2, "pump": 0.3}   # steeper ground is cut / filled (shelves)


def limit_grade(h, g, step=4.0, pin_start=False, pin_end=False):
    """Clamp the slope between consecutive samples to g: the road cuts into rises and fills dips instead of
    climbing terrace risers straight up (refs 05/08: switchback shelves cut into the slope). Pinned ends (junctions)
    keep their height."""
    d = g * step
    h = list(h)
    n = len(h)
    for _ in range(4):
        for i in range(1, n):
            if not (pin_end and i == n - 1):
                h[i] = min(max(h[i], h[i - 1] - d), h[i - 1] + d)
        for i in range(n - 2, -1, -1):
            if not (pin_start and i == 0):
                h[i] = min(max(h[i], h[i + 1] - d), h[i + 1] + d)
    return h

# Flattened play-area pads and pond basins: (name, x, y, radius, kind). "flat" = levelled ground, "pond" = a basin
# that renders as water / ice (frozen ponds in the snow, the oasis in the desert).
PADS = [
    ("stunt_park", 430, 290, 52, "flat"),
    ("snow_park", -252, 700, 46, "flat"),   # a flat bench cut into the slope at the lake road's level (ref 08)
    ("oasis", 810, 190, 34, "pond"),
    ("pond_north", -280, 1080, 46, "pond"),
    ("pond_west", -900, 360, 52, "pond"),
    ("summit", 0, 0, 22, "flat"),   # position set from the snow peak picked for the ski lift (see below)
]
# Natural jumps shaped into the ground: (x, y, heading deg (0 = +y), lip height m, length m, width m)
JUMPS = [
    (-760, -330, 225, 2.2, 14, 8), (-880, -230, 220, 2.6, 16, 9), (-560, -560, 235, 2.0, 12, 8),   # beach dunes
    (60, 1040, 90, 2.4, 14, 9), (300, 980, 270, 2.0, 12, 8), (130, 770, 45, 1.8, 12, 8),            # desert near the tracks
    (980, 280, 200, 2.2, 14, 9),
]
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
    h = lerp(h, terrace(h, 16.0, 40.0), 0.75 * sstep(LAKE_Z + 5, LAKE_Z + 25, h))   # stepped shelves + cliff bands (refs 05/08)
    h = lerp(30, h, sstep(-60, 380, min(-x, y) + 120 * n2(x, y, 300, 14)))   # foothills toward the other biomes
    return lerp(LAKE_Z, h, sstep(LAKE_R, LAKE_R + 80, lake_reff(x, y)))


def terrace(h, step, base):
    """Flat shelves joined by steep risers: each `step` m band is ~55% flat, then climbs to the next."""
    q = (h - base) / step
    k = math.floor(q)
    return base + (k + sstep(0.55, 1.0, q - k)) * step


MESAS = [(870, 920, 280, 210, 75), (1010, 420, 190, 230, 62), (500, 1060, 210, 140, 52)]


def dune(x, y):
    return math.sin((x * 0.6 + y * 0.8) / 95 + 2.2 * n2(x, y, 300, 5))


MESA_TOP, MESA_SHELF = (1.0, 1.08), (1.34, 1.42)   # wall bands in mesa radius units: top cliff, lower shelf cliff


def mesa_r(x, y, m):
    mx, my, rx, ry, _ = m
    return math.hypot((x - mx) / rx, (y - my) / ry) + 0.06 * n2(x, y, 120, 6)


def mesa_parts(x, y):
    """(shelf, top) 0..1 for the strongest mesa here: steep-walled buttes with a lower shelf (refs 04/09)."""
    best = (0.0, 0.0, None)
    for m in MESAS:
        r = mesa_r(x, y, m)
        shelf, top = sstep(MESA_SHELF[1], MESA_SHELF[0], r), sstep(MESA_TOP[1], MESA_TOP[0], r)
        if shelf + top > best[0] + best[1]:
            best = (shelf, top, m)
    return best


def mesa_t(x, y):
    shelf, top, _ = mesa_parts(x, y)
    return 0.5 * shelf + 0.5 * top


def desert_h(x, y):
    h = 32 + 15 * dune(x, y) + 10 * fbm(x, y, 220, 3, 6)
    shelf, top, m = mesa_parts(x, y)
    if m:
        h = lerp(h, 28 + 0.45 * m[4], shelf)
        h = lerp(h, 28 + m[4], top)
    return h


def coast_val(x, y):
    dc = 0.85 * math.hypot(x + HALF, y + HALF) + 70 * n2(x, y, 300, 7) + 25 * n2(x, y, 90, 8)
    return dc - COAST


def beach_h(x, y):
    c = coast_val(x, y)
    if c < 0:
        return SEA_FLOOR * sstep(0, -350, c) + 1.2 * n2(x, y, 60, 9) * sstep(0, -60, c)
    t = clamp01(c / 600)
    cliff = 9.0 * sstep(70, 92, c + 6 * n2(x, y, 40, 15))   # rock cliff between the beach and the coast highway shelf
    return 30 * t ** 1.2 + 5.0 * math.sin(c / 60) * t + cliff


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


roads = []   # (samples, heights, half_width, class, closed)
road_names = ["loop"]   # parallel to roads
loop_s = spline(ROAD_LOOP, 4.0, True)
# road heights follow the uncarved ground (base_h), so a road reaches the canyon rim at bank height on both sides and
# the bridge deck between them is level
loop_h = smooth_along([max(2.0, base_h(p.x, p.y)) for p in loop_s], 25, True)
loop_h = limit_grade([h - 1.0 for h in loop_h], MAX_GRADE["highway"])   # recessed 1 m into the surrounding ground
roads.append((loop_s, loop_h, LOOP_HW, "highway", True))
for _name, cls, ctrl in TRACKS:
    s_t = spline(ctrl, 4.0, True)
    roads.append((s_t, smooth_along([max(2.0, base_h(p.x, p.y)) - 0.5 for p in s_t], 6, True), ROAD_HW[cls], cls, True))
    road_names.append(_name)


def samples_kd(rs):
    """KD-tree over every sample of the given roads -> (kd, [(point, height, half_width)])."""
    pts = [(p, h, w) for s, hs, w, *_ in rs for p, h in zip(s, hs)]
    kd = kdtree.KDTree(len(pts))
    for i, (p, *_rest) in enumerate(pts):
        kd.insert((p.x, p.y, 0), i)
    kd.balance()
    return kd, pts


# ski lift + switchback road: the highest snow peak within reach of the lake road becomes the summit
LIFT_BASE = Vector((-380, 500))
_cands = [Vector((px, py)) for px, py, _ph, _ps in SNOW_PEAKS
          if 220 < (Vector((px, py)) - LIFT_BASE).length < 460 and lake_reff(px, py) > LAKE_R + 140]
SUMMIT = max(_cands, key=lambda q: base_h(q.x, q.y))
PADS = [(n, SUMMIT.x, SUMMIT.y, r, k) if n == "summit" else (n, x, y, r, k) for n, x, y, r, k in PADS]


def switchback(a, b, legs=4, swing=55.0):
    """Zig-zag control points from a to b: `legs` traverses swinging `swing` m either side of the straight line."""
    d = b - a
    n = Vector((-d.y, d.x)).normalized()
    pts = [a]
    for k in range(1, legs):
        pts.append(a + d * (k / legs) + n * swing * (1 if k % 2 else -1))
    return pts + [b - d.normalized() * 22]


ROADS.append(("summit_road", "trail", [tuple(q) for q in switchback(Vector((-345, 520)), SUMMIT, legs=6, swing=75.0)]))
# and down the far side to the coast highway, so the summit is a pass, not a dead end
_top = switchback(Vector((-345, 520)), SUMMIT, legs=6, swing=75.0)[-1]
ROADS.append(("summit_west", "trail", [tuple(q) for q in switchback(_top, Vector((-1015, 470)), legs=6, swing=70.0)]))
GRADED = {"summit_road", "summit_west"}   # heights climb evenly from start to end (a shelf cut into the slope) instead of following it

for _name, cls, ctrl in ROADS:
    kd, pts = samples_kd(roads)
    ctrl = [Vector(c) for c in ctrl]
    join = [None, None]   # height of the road each end joins
    for e in (0, -1):
        _, i, d = kd.find((ctrl[e].x, ctrl[e].y, 0))
        if d < ROAD_SNAP:
            ctrl[e] = pts[i][0].copy()
            join[e] = pts[i][1]
    s = spline(ctrl, 4.0, False)
    if _name in GRADED:
        h0 = join[0] if join[0] is not None else base_h(s[0].x, s[0].y) - 1.0
        h1 = join[-1] if join[-1] is not None else base_h(s[-1].x, s[-1].y) - 1.0
        h = [lerp(h0, h1, i / (len(s) - 1)) for i in range(len(s))]
    else:
        h = limit_grade(smooth_along([max(2.0, base_h(p.x, p.y)) - 1.0 for p in s], 20, False), MAX_GRADE[cls])
    n, fade = len(h), 30
    if join[0] is not None:
        d0 = join[0] - h[0]
        h = [v + d0 * (1 - min(i, fade) / fade) for i, v in enumerate(h)]
    if join[-1] is not None:
        d1 = join[-1] - h[-1]
        h = [v + d1 * (1 - min(n - 1 - i, fade) / fade) for i, v in enumerate(h)]
    if _name not in GRADED:   # the junction blends can re-steepen the ends: cap again with the joined ends held
        h = limit_grade(h, MAX_GRADE[cls], pin_start=join[0] is not None, pin_end=join[-1] is not None)
    roads.append((s, h, ROAD_HW[cls], cls, False))
    road_names.append(_name)

def in_canyon(x, y, margin=2.0):
    return river_kd.find((x, y, 0))[2] < RIVER_W1 + margin


# Rope bridges (refs 02/04/05/09): every run of road samples over the canyon becomes a bridge from the last sample
# on one rim to the first on the other. Those samples are left out of road_meta, so the canyon stays open below.
BRIDGES = []   # (rim point a, rim point b, deck height)
for ri, (samples, hs, w, cls, closed) in enumerate(roads):
    k = 0
    while k < len(samples):
        if in_canyon(samples[k].x, samples[k].y):
            j = k
            while j < len(samples) and in_canyon(samples[j].x, samples[j].y):
                j += 1
            a, b = samples[max(k - 1, 0)], samples[min(j, len(samples) - 1)]
            deck = (hs[max(k - 1, 0)] + hs[min(j, len(samples) - 1)]) / 2
            BRIDGES.append((a, b, deck))
            # level the approaches: ease the road onto the deck height over 40 m on both sides
            hs2 = list(hs)
            for q in range(len(hs2)):
                dist = min(abs(q - (k - 1)), abs(q - j)) * 4.0 if not (k - 1 <= q <= j) else 0.0
                hs2[q] = lerp(deck, hs2[q], sstep(0, 40, dist))
            roads[ri] = (samples, hs2, w, cls, closed)
            hs = hs2
            k = j
        k += 1

road_meta = []   # (point, height, half width, class, metres along its road)
for k, (samples, hs, w, cls, closed) in enumerate(roads):
    kd, pts = samples_kd(roads[:k]) if k else (None, None)
    for i_s, (p, h) in enumerate(zip(samples, hs)):
        if in_canyon(p.x, p.y):
            continue
        if kd:
            _, i, d = kd.find((p.x, p.y, 0))
            if d <= pts[i][2] + 4:   # an earlier road owns the junction area
                continue
        road_meta.append((p, h, w, cls, 4.0 * i_s))
road_kd = kdtree.KDTree(len(road_meta))
for i, (p, *_rest) in enumerate(road_meta):
    road_kd.insert((p.x, p.y, 0), i)
road_kd.balance()


# ------------------------------------------------------------------ water erosion (refs 04/06/09: gullies, rills, fans)
# Rain droplets run downhill over a height grid of the base terrain, carving gullies on the slopes and dropping their
# sediment where the slope eases off. The result is a height offset applied in height(); roads (blended over it
# below), the river gorge, the lake and the sea are left out. Vectorised: one batch of droplets moves per numpy step.
import numpy as np

ER_N = int(globals().get("ER_N", "384"))            # erosion grid resolution (6.25 m cells)
ER_DROPS, ER_STEPS, ER_UNIT = 160000, 28, 6.0       # droplets, max path length (cells), metres per height unit
ER_INERTIA, ER_CAPACITY, ER_MIN_CAP, ER_ERODE, ER_DEPOSIT, ER_EVAP, ER_GRAVITY = 0.3, 2.0, 0.01, 0.15, 0.3, 0.035, 4.0
ER_DETAIL = 6      # keep only erosion features smaller than ~2 x this many cells (gullies, rills, ridges)
ER_GAIN = 1.0
ER_CELL = 2 * HALF / (ER_N - 1)


def _bilinear(H, x, y):
    ix, iy = x.astype(int), y.astype(int)
    fx, fy = x - ix, y - iy
    return (H[iy, ix] * (1 - fx) * (1 - fy) + H[iy, ix + 1] * fx * (1 - fy)
            + H[iy + 1, ix] * (1 - fx) * fy + H[iy + 1, ix + 1] * fx * fy)


def erode(H, drops=ER_DROPS, steps=ER_STEPS, seed=5):
    rng_e = np.random.default_rng(seed)
    n = H.shape[0]
    Hs = H.copy()
    batch = 20000
    for _ in range(drops // batch):
        px, py = rng_e.uniform(1, n - 3, batch), rng_e.uniform(1, n - 3, batch)
        dx, dy = np.zeros(batch), np.zeros(batch)
        speed, water, sed = np.ones(batch), np.ones(batch), np.zeros(batch)
        alive = np.ones(batch, bool)
        for _s in range(steps):
            ix, iy = px.astype(int), py.astype(int)
            fx, fy = px - ix, py - iy
            h00, h10, h01, h11 = Hs[iy, ix], Hs[iy, ix + 1], Hs[iy + 1, ix], Hs[iy + 1, ix + 1]
            gx = (h10 - h00) * (1 - fy) + (h11 - h01) * fy
            gy = (h01 - h00) * (1 - fx) + (h11 - h10) * fx
            h = h00 * (1 - fx) * (1 - fy) + h10 * fx * (1 - fy) + h01 * (1 - fx) * fy + h11 * fx * fy
            dx, dy = dx * ER_INERTIA - gx * (1 - ER_INERTIA), dy * ER_INERTIA - gy * (1 - ER_INERTIA)
            ln = np.hypot(dx, dy)
            alive &= ln > 1e-6
            ln = np.maximum(ln, 1e-6)
            dx, dy = dx / ln, dy / ln
            nx, ny = px + dx, py + dy
            alive &= (nx >= 1) & (nx < n - 3) & (ny >= 1) & (ny < n - 3)
            nh = _bilinear(Hs, np.clip(nx, 1, n - 3.001), np.clip(ny, 1, n - 3.001))
            dh = nh - h
            cap = np.maximum(-dh * speed * water * ER_CAPACITY, ER_MIN_CAP)
            dep = (sed > cap) | (dh > 0)
            change = np.where(dep, np.where(dh > 0, np.minimum(dh, sed), (sed - cap) * ER_DEPOSIT),
                              -np.minimum((cap - sed) * ER_ERODE, -dh))
            change = np.where(alive, change, 0.0)
            # droplets move in parallel: share each cell's change among the droplets in it, or a crowded cell would be
            # dug once per droplet from the same starting height (runaway pits)
            cell = iy * n + ix
            change = change / np.bincount(cell, minlength=n * n)[cell]
            sed -= change
            for oy, ox, wgt in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
                np.add.at(Hs, (iy + oy, ix + ox), change * wgt)
            speed = np.sqrt(np.maximum(speed * speed - dh * ER_GRAVITY, 0.0))
            water *= 1 - ER_EVAP
            px, py = np.where(alive, nx, px), np.where(alive, ny, py)
            if not alive.any():
                break
    D = Hs - H
    for _ in range(2):   # soften the single-cell pits and spikes of corner-only erosion
        D = (D + np.roll(D, 1, 0) + np.roll(D, -1, 0) + np.roll(D, 1, 1) + np.roll(D, -1, 1)) / 5.0
    return D - _box_blur(D, ER_DETAIL)   # high-pass: the big landforms stay as designed, only the carving is added


def _box_blur(D, r, passes=3):
    for _ in range(passes):
        c = np.cumsum(np.pad(D, ((r + 1, r), (0, 0)), mode="edge"), 0)
        D = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
        c = np.cumsum(np.pad(D, ((0, 0), (r + 1, r)), mode="edge"), 1)
        D = (c[:, 2 * r + 1:] - c[:, :-2 * r - 1]) / (2 * r + 1)
    return D


def _erosion_grid():
    xs = np.linspace(-HALF, HALF, ER_N)
    H = np.array([[river_carve(x, y, base_h(x, y)) for x in xs] for y in xs]) / ER_UNIT
    return erode(H) * ER_UNIT * ER_GAIN


EROSION = _erosion_grid()   # metres; EROSION[row = y index, col = x index]


def erosion_at(x, y):
    """Height offset from water erosion at (x, y), faded out at the river, lake and sea."""
    gx = min(max((x + HALF) / ER_CELL, 0.0), ER_N - 1.001)
    gy = min(max((y + HALF) / ER_CELL, 0.0), ER_N - 1.001)
    ix, iy = int(gx), int(gy)
    fx, fy = gx - ix, gy - iy
    e = (EROSION[iy, ix] * (1 - fx) * (1 - fy) + EROSION[iy, ix + 1] * fx * (1 - fy)
         + EROSION[iy + 1, ix] * (1 - fx) * fy + EROSION[iy + 1, ix + 1] * fx * fy)
    keep = sstep(RIVER_W1 + 5, RIVER_W1 + 40, river_kd.find((x, y, 0))[2])
    keep *= sstep(LAKE_R + 20, LAKE_R + 90, lake_reff(x, y)) * sstep(0, 60, coast_val(x, y))
    return max(-9.0, min(5.0, e)) * keep


PAD_EDGE, POND_DEPTH = 25.0, 3.0
PAD_LEVEL = {n: base_h(x, y) - (POND_DEPTH if k == "pond" else 0.0) for n, x, y, r, k in PADS}
_sp = samples_kd([roads[road_names.index("snowpark_spur")]])
PAD_LEVEL["snow_park"] = _sp[1][_sp[0].find((-300, 700, 0))[1]][1]   # level with the end of its access road


def pad_at(x, y):
    """(name, kind, radius, distance) of the pad whose blend zone covers (x, y), else None."""
    for n, px, py, r, k in PADS:
        d = math.hypot(x - px, y - py)
        if d < r + PAD_EDGE:
            return n, k, r, d
    return None


def jump_at(x, y):
    h = 0.0
    for jx, jy, hd, lip, ln, wd in JUMPS:
        a = math.radians(hd)
        u = (x - jx) * math.sin(a) + (y - jy) * math.cos(a)   # along the run-up
        v = (x - jx) * math.cos(a) - (y - jy) * math.sin(a)
        if abs(u) > ln / 2 or abs(v) > wd / 2 + 3:
            continue
        t = (u + ln / 2) / ln
        h += lip * sstep(0.0, 0.8, t) * (1 - sstep(0.9, 1.0, t)) * sstep(wd / 2 + 3, wd / 2, abs(v))
    return h


def height(x, y):
    h = river_carve(x, y, base_h(x, y)) + erosion_at(x, y) + jump_at(x, y)
    pad = pad_at(x, y)
    if pad:
        h = lerp(h, PAD_LEVEL[pad[0]], sstep(pad[2] + PAD_EDGE, pad[2], pad[3]))
    if in_canyon(x, y):
        return h
    _, i, d = road_kd.find((x, y, 0))
    _, rh, w, cls, along = road_meta[i]
    s = sstep(w + ROAD_SHOULDER, w, d)
    if s <= 0:
        return h
    if cls == "pump":
        rh += 0.9 * math.sin(along * 2 * math.pi / 11.0)   # rollers
    h = lerp(h, rh, s)
    if cls == "track":   # raised berm along both edges, like a dirt race track
        h += 1.3 * math.exp(-((d - (w + 2.5)) / 1.6) ** 2)
    return h


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
    near_earlier = None
    if k:   # a branch's lines start once clear of the corridor of the roads before it
        kd, pts = samples_kd(roads[:k])

        def near_earlier(p, kd=kd, pts=pts):
            _, i, d = kd.find((p.x, p.y, 0))
            return d < pts[i][2] + ROAD_SHOULDER + 10
    offset_lines(samples, closed, (-w, w, -(w + 3), w + 3, -(w + ROAD_SHOULDER), w + ROAD_SHOULDER), 4, near_earlier)
offset_lines(river_s, False, (-RIVER_W0, RIVER_W0, -22, 22, -RIVER_W1, RIVER_W1), 5)
for rr in (LAKE_R, LAKE_R + 40):
    pts = []
    for i in range(110):
        th = 2 * math.pi * i / 110
        g = 1 + 0.15 * math.sin(3 * th + 1) + 0.08 * math.sin(5 * th + 2)
        pts.append(LAKE_C + Vector((math.cos(th), math.sin(th))) * rr * g)
    add_line(pts, True)
# crisp cliff walls on the mesas: edge lines along each wall band (found by bisection along rays from the centre)
for m in MESAS:
    for target in MESA_TOP + MESA_SHELF:
        pts = []
        for i in range(96):
            th = 2 * math.pi * i / 96
            dvec = Vector((m[2] * math.cos(th), m[3] * math.sin(th)))
            lo, hi = 0.3, 2.5
            for _ in range(30):
                mid = (lo + hi) / 2
                q = Vector((m[0], m[1])) + dvec * mid
                if mesa_r(q.x, q.y, m) < target:
                    lo = mid
                else:
                    hi = mid
            pts.append(Vector((m[0], m[1])) + dvec * lo)
        add_line(pts, True)
# pad and pond rims
for n, px, py, r, k in PADS:
    for rr in ((r * 0.85, r) if k == "pond" else (r,)):
        add_line([Vector((px + rr * math.cos(2 * math.pi * i / 48), py + rr * math.sin(2 * math.pi * i / 48))) for i in range(48)], True)
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


def road_color(x, y, cls):
    """Road surface for the biome under it: dirt in the forest, red-brown track in the desert, packed snow in the
    snow, and on the coast asphalt (highways) or packed sand (trails). Blended by the same soft biome weights as the
    ground, so the colour changes gradually where a road crosses from one biome into the next."""
    w = weights(x, y, 45)
    coast = C["beach_track"]   # sandy road by the sea (both the highway and the trails)
    return C["dirt"] * w["forest"] + C["desert_track"] * w["desert"] + C["snow_track"] * w["snow"] + coast * w["beach"]


def vertex_color(v):
    x, y, z = v.co
    slope = 1 - max(0.0, v.normal.z)
    w = weights(x, y, 45)
    mt = mesa_t(x, y)
    flank = sstep(0.0, 0.2, mt) * (1 - sstep(0.8, 0.97, mt))   # red mesa sides, sandy flat tops
    desert = C["desert_sand"].lerp(C["terracotta"], clamp01(max(sstep(0.10, 0.30, slope), flank,
                                                                0.18 * sstep(0.1, -0.7, dune(x, y)) * (1 - mt))))   # red only on slopes + mesa walls; flats stay golden sand (ref 04)
    forest = C["forest"].lerp(C["cliff"], sstep(0.3, 0.5, slope))
    beach = C["beach"]
    snow = C["snow"].lerp(C["snow_rock"], sstep(0.25, 0.5, slope))   # bare grey rock on steep snow faces
    c = snow * w["snow"] + desert * w["desert"] + beach * w["beach"] + forest * w["forest"]
    if lake_reff(x, y) <= LAKE_R + 1 and abs(z - LAKE_Z) < 1.0:
        c = C["ice"]
    elif z < -0.05 and (w["beach"] < 0.5 or coast_val(x, y) < -SHORE_BAND + 1):
        c = C["ice"]          # sea + river water (turquoise)
    _, i, d = road_kd.find((x, y, 0))
    _, _, rw, cls, _a = road_meta[i]
    s = sstep(rw + 3.0, rw, d)
    if s > 0 and not in_canyon(x, y):
        c = c.lerp(road_color(x, y, cls), s)
    pad = pad_at(x, y)
    if pad and pad[1] == "pond" and pad[3] < pad[2] * 0.85:
        c = C["ice"]   # frozen pond / oasis water
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
