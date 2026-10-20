# Stunt ramps, loop, bridges and built structures (refs 02/03/04/05/07/09).
# Driving direction = +Y. Ramps start at y<0 on the ground and launch toward +Y.


def curve(fn, n):
    return [fn(i / n) for i in range(n + 1)]


def kicker_profile(n, L=6.0, H=2.0):
    pts = [(-L / 2, 0.0)] + curve(lambda t: (-L / 2 + L * t, H * t * t), n)[1:] + [(L / 2, 0.0)]
    return pts


def ramp_kicker(lod):
    """Orange ski-jump kicker, 4 m wide, 6 m long, 2 m lip (refs 02/04/09)."""
    p = Part()
    n = seg_for(lod, 8, 5, 3)
    prof = kicker_profile(n)
    p.prism("ramp_orange", prof, 4.0)
    if lod < 2:
        for s in (1, -1):
            p.prism("ramp_dark", [(y, z + 0.12) for y, z in prof[1:-1]] + [(3.0, 0.0), (-3.0, 0.0)], 0.14, loc=(s * 2.07, 0, 0))
    if lod == 0:
        for i in range(1, n):
            t = i / n
            y, z = -3 + 6 * t, 2 * t * t
            a = math.degrees(math.atan(4 * t * 2 / 6))
            p.box("ramp_dark", (4.0, 0.06, 0.03), loc=(0, y, z + 0.015), rot=(a, 0, 0))
    return p.finish("ramp_kicker")


def ramp_kicker_col():
    p = Part()
    p.prism("black", kicker_profile(5), 4.0)
    return p.finish("ramp_kicker_col")


def quarter_profile(n, R=5.0, deck=1.5):
    arc = curve(lambda t: (-R + R * math.cos(math.radians(-90 + 90 * t)), R + R * math.sin(math.radians(-90 + 90 * t))), n)
    return arc + [(deck, R), (deck, 0.0)]


def ramp_quarterpipe(lod):
    p = Part()
    n = seg_for(lod, 10, 6, 4)
    prof = quarter_profile(n)
    p.prism("ramp_orange", prof, 6.0)
    if lod < 2:
        for s in (1, -1):
            p.prism("wood_dark", prof, 0.15, loc=(s * 3.07, 0, 0))
        p.box("metal", (6.2, 0.15, 0.15), loc=(0, 0.05, 5.05))
    if lod == 0:
        for x in (-2.0, 0.0, 2.0):
            p.box("wood_dark", (0.15, 0.15, 5.0), loc=(x, 1.4, 2.5))
    return p.finish("ramp_quarterpipe")


def ramp_quarterpipe_col():
    p = Part()
    p.prism("black", quarter_profile(6), 6.0)
    return p.finish("ramp_quarterpipe_col")


def wave_profile(n, L=16.0, H=7.0):
    pts = [(-L / 2, 0.0)] + curve(lambda t: (-L / 2 + L * 0.8 * t, H * (t ** 2.2)), n)[1:]
    return pts + [(L / 2 - 1.5, H), (L / 2, H - 0.8), (L / 2, 0.0)]


def ramp_wave_big(lod):
    """Giant orange inflatable slide-ramp at the beach (ref 07). 10 m wide, 7 m high, 4 lanes."""
    p = Part()
    n = seg_for(lod, 10, 6, 4)
    prof = wave_profile(n)
    p.prism("ramp_orange", prof, 10.0)
    if lod < 2:
        ridge = [(y, z + 0.35) for y, z in prof[1:-1]]
        ridge = [(prof[0][0] + 0.6, 0.0)] + ridge + [(prof[-1][0], 0.0)]
        for x in (-5.0, -2.5, 0.0, 2.5, 5.0):
            p.prism("ramp_dark", ridge, 0.45, loc=(x, 0, 0))
    if lod == 0:
        p.cyl("ramp_dark", 0.6, 10.6, 8, loc=(0, 6.5, 7.0), rot=(0, 90, 0))
    return p.finish("ramp_wave_big")


def ramp_wave_big_col():
    p = Part()
    p.prism("black", wave_profile(6), 10.0)
    return p.finish("ramp_wave_big_col")


LOOP_R, LOOP_W, LOOP_SHIFT = 7.0, 4.5, 5.0


def loop_boards(p, n, color, thick=0.3, rails=True):
    for i in range(n):
        t = (i + 0.5) / n
        a = -90 + 360 * t
        ar = math.radians(a)
        x = -LOOP_SHIFT / 2 + LOOP_SHIFT * t
        y, z = LOOP_R * math.cos(ar), LOOP_R + 0.3 + LOOP_R * math.sin(ar)
        seg_len = 2 * math.pi * (LOOP_R + thick / 2) / n * 1.06
        p.box(color, (LOOP_W, seg_len, thick), loc=(x, y + math.cos(ar) * thick / 2, z + math.sin(ar) * thick / 2), rot=(a + 90, 0, 0))
        if rails:
            for s in (1, -1):
                p.box("wood_dark", (0.18, seg_len, 0.6), loc=(x + s * (LOOP_W / 2 + 0.09), y - math.cos(ar) * 0.2, z - math.sin(ar) * 0.2), rot=(a + 90, 0, 0))


def stunt_loop(lod):
    """Wooden loop-de-loop (refs 02/09): radius 7 m, track 4.5 m wide, entry and exit offset 5 m sideways."""
    p = Part()
    n = seg_for(lod, 28, 18, 12)
    loop_boards(p, n, "wood", rails=lod < 2)
    if lod < 2:
        for x in (-LOOP_SHIFT / 2 - 3.2, LOOP_SHIFT / 2 + 3.2):
            p.box("wood_dark", (0.4, 0.4, 2 * LOOP_R + 0.6), loc=(x, 0, LOOP_R + 0.3))
            p.box("wood_dark", (abs(x) - 2.6, 0.3, 0.3), loc=(x / 2 + (1.3 if x > 0 else -1.3), 0, 2 * LOOP_R - 0.4))
    if lod == 0:
        for s in (1, -1):
            p.box("wood_dark", (0.3, 0.3, 4.0), loc=(s * (LOOP_SHIFT / 2 + 3.2), 1.5, 1.8), rot=(30, 0, 0))
            p.box("wood_dark", (0.3, 0.3, 4.0), loc=(s * (LOOP_SHIFT / 2 + 3.2), -1.5, 1.8), rot=(-30, 0, 0))
    return p.finish("stunt_loop")


def stunt_loop_col():
    p = Part()
    loop_boards(p, 20, "black", rails=False)
    return p.finish("stunt_loop_col")


def gate_arch(lod):
    """Orange start/finish arch (refs 02/03/04): 10 m wide, 7 m tall."""
    p = Part()
    for s in (1, -1):
        p.box("ramp_orange", (0.9, 0.9, 7.0), loc=(s * 5.0, 0, 3.5), taper=(0.85, 0.85))
        p.box("ramp_dark", (1.3, 1.3, 0.6), loc=(s * 5.0, 0, 0.3))
    p.box("ramp_orange", (11.2, 1.0, 1.0), loc=(0, 0, 7.1))
    if lod < 2:
        n = 10 if lod == 0 else 5
        for i in range(n):
            p.box("black" if i % 2 else "white", (9.0 / n, 0.08, 0.7), loc=(-4.5 + 9.0 / n * (i + 0.5), -0.52, 6.3))
    if lod == 0:
        p.ico("flag_red", 0.3, 0, loc=(5.0, 0, 7.9))
        p.ico("flag_red", 0.3, 0, loc=(-5.0, 0, 7.9))
    return p.finish("gate_arch")


def gate_arch_col():
    p = Part()
    for s in (1, -1):
        p.box("black", (0.9, 0.9, 7.0), loc=(s * 5.0, 0, 3.5))
    p.box("black", (11.2, 1.0, 1.0), loc=(0, 0, 7.1))
    return p.finish("gate_arch_col")


BRIDGE_SPAN, BRIDGE_W, BRIDGE_SAG = 48.0, 5.0, 1.2


def sag(y, amount):
    t = y / (BRIDGE_SPAN / 2)
    return -amount * (1 - t * t)


def bridge_deck(p, n, color, thick=0.18, gaps=True):
    step = BRIDGE_SPAN / n
    for i in range(n):
        y = -BRIDGE_SPAN / 2 + step * (i + 0.5)
        slope = math.degrees(math.atan(2 * BRIDGE_SAG * y / (BRIDGE_SPAN / 2) ** 2))
        p.box(color if (i % 3 or not gaps) else "wood_dark", (BRIDGE_W, step * (0.85 if gaps else 1.02), thick),
              loc=(0, y, sag(y, BRIDGE_SAG) - thick / 2), rot=(slope, 0, 0))


def bridge_suspension(lod):
    """Wooden rope bridge across the canyon chasm (refs 02/04/05/09). 48 m span, 5 m wide, deck ends at z=0."""
    p = Part()
    bridge_deck(p, seg_for(lod, 44, 14, 6), "wood", gaps=lod == 0)
    for s in (1, -1):
        for e in (1, -1):
            p.cyl("wood_dark", 0.18, 3.4, seg_for(lod, 6, 5, 4), loc=(s * (BRIDGE_W / 2 + 0.2), e * (BRIDGE_SPAN / 2 + 0.2), 1.2))
    rope_n = seg_for(lod, 12, 6, 3)
    for s in (1, -1):
        for k in range(rope_n):
            y0 = -BRIDGE_SPAN / 2 + BRIDGE_SPAN * k / rope_n
            y1 = y0 + BRIDGE_SPAN / rope_n
            z0, z1 = 2.8 + sag(y0, 1.6), 2.8 + sag(y1, 1.6)
            length = math.hypot(y1 - y0, z1 - z0)
            p.box("rope", (0.08, length, 0.08), loc=(s * (BRIDGE_W / 2 + 0.2), (y0 + y1) / 2, (z0 + z1) / 2),
                  rot=(math.degrees(math.atan2(z1 - z0, y1 - y0)), 0, 0))
            if lod == 0 and k:
                h = z0 - sag(y0, BRIDGE_SAG)
                p.box("rope", (0.05, 0.05, h), loc=(s * (BRIDGE_W / 2 + 0.15), y0, sag(y0, BRIDGE_SAG) + h / 2))
    return p.finish("bridge_suspension")


def bridge_suspension_col():
    p = Part()
    bridge_deck(p, 12, "black", thick=0.3, gaps=False)
    for s in (1, -1):
        p.box("black", (0.2, BRIDGE_SPAN, 1.2), loc=(s * (BRIDGE_W / 2 + 0.1), 0, 0.2))
    return p.finish("bridge_suspension_col")


def bridge_plank_small(lod):
    """Short log/plank bridge over forest creeks and trail gaps (refs 02/03). 10 m x 4 m."""
    p = Part()
    n = seg_for(lod, 12, 4, 1)
    for i in range(n):
        y = -5 + 10 / n * (i + 0.5)
        p.box("wood" if i % 2 else "wood_light", (4.0, 10 / n * 0.92 if n > 1 else 10, 0.25), loc=(0, y, -0.125))
    if lod < 2:
        for s in (1, -1):
            p.cyl("trunk", 0.18, 10.4, 6, loc=(s * 2.1, 0, 0.6), rot=(90, 0, 0))
            for y in (-5, 0, 5):
                p.cyl("trunk", 0.15, 1.0, 5, loc=(s * 2.1, y, 0.25))
    return p.finish("bridge_plank_small")


def bridge_plank_small_col():
    p = Part()
    p.box("black", (4.0, 10.0, 0.3), loc=(0, 0, -0.15))
    return p.finish("bridge_plank_small_col")


def tunnel_portal(lod):
    """Mine-tunnel entrance set into a cliff (refs 02/03). Opening 6 m wide x 5 m tall, faces +Y."""
    p = Part()
    p.box("black", (6.0, 8.0, 5.0), loc=(0, -4.2, 2.5))
    for s in (1, -1):
        p.box("wood_dark", (0.6, 0.6, 5.4), loc=(s * 3.3, 0, 2.7))
    p.box("wood_dark", (7.6, 0.7, 0.7), loc=(0, 0, 5.6))
    if lod < 2:
        rocks = [(-4.8, 2.0, 2.2), (4.8, 1.8, 2.0), (-2.5, 6.6, 1.8), (2.6, 6.8, 1.9), (0, 7.2, 1.6)]
        for i, (x, z, r) in enumerate(rocks):
            p.ico("red_rock" if i % 2 else "red_rock_dark", r, 1 if lod == 0 else 0, loc=(x, -0.6, z), scale=(1.2, 0.8, 1), jitter=0.2, seed=30 + i)
    if lod == 0:
        p.box("lamp_glow", (0.3, 0.3, 0.4), loc=(3.3, 0.35, 4.5))
        p.box("wood", (1.6, 0.1, 0.5), loc=(0, 0.4, 6.4))
    return p.finish("tunnel_portal")


def fence_wood(lod):
    """4 m fence segment (refs 04/05/08), origin at the left post base, runs along +X."""
    p = Part()
    for x in (0.0, 4.0):
        p.box("wood_dark", (0.2, 0.2, 1.3), loc=(x, 0, 0.65))
    for z in (0.5, 1.0):
        p.box("wood", (4.1, 0.1, 0.18), loc=(2.0, 0.1, z))
    return p.finish("fence_wood")


def dock_pier(lod):
    """Wooden pier into the sea (refs 06/07/09). 3 m x 14 m deck at z=0.8, runs +Y into the water."""
    p = Part()
    n = seg_for(lod, 14, 5, 1)
    for i in range(n):
        y = 14 / n * (i + 0.5)
        p.box("wood" if i % 2 else "wood_light", (3.0, 14 / n * 0.92 if n > 1 else 14, 0.2), loc=(0, y, 0.8))
    posts = [(s * 1.4, y) for s in (1, -1) for y in (0.3, 4.7, 9.3, 13.7)]
    for x, y in posts if lod < 2 else posts[::2]:
        p.cyl("wood_dark", 0.15, 3.0, 5, loc=(x, y, -0.6))
    if lod == 0:
        p.cyl("wood_dark", 0.12, 0.6, 5, loc=(1.4, 13.7, 1.2))
        p.cyl("wood_dark", 0.12, 0.6, 5, loc=(-1.4, 13.7, 1.2))
    return p.finish("dock_pier")


def dock_pier_col():
    p = Part()
    p.box("black", (3.0, 14.0, 0.3), loc=(0, 7.0, 0.75))
    return p.finish("dock_pier_col")


def ski_lift_tower(lod):
    """Cable-lift pylon (refs 05/08/09). 12 m tall."""
    p = Part()
    p.cyl("metal_dark", 0.3, 12.0, seg_for(lod, 6, 5, 4), loc=(0, 0, 6.0), r2=0.2)
    p.box("metal_dark", (4.0, 0.3, 0.3), loc=(0, 0, 11.6))
    if lod < 2:
        p.box("metal", (1.2, 1.2, 0.4), loc=(0, 0, 0.2))
        for s in (1, -1):
            p.cyl("black", 0.25, 0.2, 6, loc=(s * 1.8, 0, 11.3), rot=(90, 0, 0))
    return p.finish("ski_lift_tower")


def gondola_cabin(lod):
    """Small red lift cabin hanging from the cable (refs 08/09). Origin at the cable grip."""
    p = Part()
    p.box("metal_dark", (0.12, 0.12, 1.6), loc=(0, 0, -0.8))
    p.box("gondola_red", (1.4, 1.2, 1.3), loc=(0, 0, -2.2), taper=(0.9, 0.9))
    if lod < 2:
        p.box("glass_blue", (1.42, 0.8, 0.5), loc=(0, 0, -2.0))
        p.box("glass_blue", (0.9, 1.22, 0.5), loc=(0, 0, -2.0))
    return p.finish("gondola_cabin")


STRUCTURES = [
    ("stunts", "ramp_kicker", ramp_kicker, (0, 1, 2), ramp_kicker_col),
    ("stunts", "ramp_quarterpipe", ramp_quarterpipe, (0, 1, 2), ramp_quarterpipe_col),
    ("stunts", "ramp_wave_big", ramp_wave_big, (0, 1, 2), ramp_wave_big_col),
    ("stunts", "stunt_loop", stunt_loop, (0, 1, 2), stunt_loop_col),
    ("stunts", "gate_arch", gate_arch, (0, 1, 2), gate_arch_col),
    ("structures", "bridge_suspension", bridge_suspension, (0, 1, 2), bridge_suspension_col),
    ("structures", "bridge_plank_small", bridge_plank_small, (0, 1, 2), bridge_plank_small_col),
    ("structures", "tunnel_portal", tunnel_portal, (0, 1, 2), None),
    ("structures", "fence_wood", fence_wood, (0,), None),
    ("structures", "dock_pier", dock_pier, (0, 1, 2), dock_pier_col),
    ("structures", "ski_lift_tower", ski_lift_tower, (0, 1, 2), None),
    ("structures", "gondola_cabin", gondola_cabin, (0, 1), None),
]

if globals().get("MODE") == "preview":
    preview([s[2] for s in STRUCTURES], globals().get("PREVIEW_PATH"), lod=int(globals().get("LOD", "0")), cols=4)
    result = {"preview": "written"}
elif globals().get("MODE") == "library":   # only define the builders (island_chunks.py places them)
    pass
else:
    for category, name, build, lods, col in STRUCTURES:
        make_asset(category, name, build, lods=lods, col=col)
    result = {"report": REPORT}
