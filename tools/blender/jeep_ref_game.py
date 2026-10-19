# Game export of the jeep built by jeep_ref.py: < 5k triangles, Draco-compressed GLB.
# Run after hero_car.py + jeep_ref.py in LOW mode:
#   node tools/blender/headless.mjs tools/blender/hero_car.py tools/blender/jeep_ref.py tools/blender/jeep_ref_game.py STEP=setup LOW=1 NO_RENDER=1
# Output nodes: car_body (origin 0,0,0 = ground under the car centre) + wheel_FL/FR/RL/RR (origin at each hub),
# so the game can spin/steer wheels. Blender +Y forward -> glTF/three.js -Z forward.
import os

GLB_PATH = globals().get("GLB_PATH", r"C:/project/New Game/models/red_jeep/red_jeep_game.glb")
MAX_TRIS = int(globals().get("MAX_TRIS", "4900"))
WHEEL_TRIS = int(globals().get("WHEEL_TRIS", "450"))


def eval_tris(o):
    dg = depsgraph()
    me = o.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    o.evaluated_get(dg).to_mesh_clear()
    return n


def decimate_to(o, target):
    n = eval_tris(o)
    if n > target:
        d = o.modifiers.new("GameDecimate", "DECIMATE")
        d.ratio = target / n
        d.use_collapse_triangulate = True
    return eval_tris(o)


def spin_profile(bm, prof, steps):
    """Lathe a [(x_axial, radius), ...] profile around the X axis into bm."""
    vs = [bm.verts.new((x, 0.0, rr)) for x, rr in prof]
    es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(1, 0, 0), angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)


def game_tire(name, loc, outward, parent, R=TIRE_R, W=TIRE_W, steps=14, lugs=12):
    """Game tyre (~430 tris): rounded tread + bulging sidewalls, staggered tread blocks, deep-dish rim, hub.
    Built with +X outward; left-side wheels are turned 180 degrees."""
    hw, ri = W / 2, R * 0.6
    half = [(hw - 0.04, R - 0.012), (hw + 0.018, R - 0.09), (hw + 0.03, R * 0.79), (hw - 0.015, ri)]
    bm = bmesh.new()
    spin_profile(bm, [(-x, rr) for x, rr in reversed(half)] + half, steps)
    for i in range(lugs):   # staggered blocks angled like a chevron mud-terrain tread
        side = 1 if i % 2 else -1
        v = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.transform(bm, matrix=M((side * 0.105, 0, R + 0.01), (0, 0, side * 24), (0.22, 0.12, 0.05)), verts=v)
        bmesh.ops.rotate(bm, verts=v, cent=(0, 0, 0), matrix=Matrix.Rotation(2 * math.pi * i / lugs, 3, "X"))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    tire = finish_mesh(name, bm, "tire_rubber", "Car", parent, 0, weighted=True)
    tire.location = loc
    tire.rotation_euler = (0, 0, 0 if outward > 0 else math.pi)
    rb = bmesh.new()   # deep dish: outer lip, recess, flat face
    spin_profile(rb, [(hw + 0.012, ri - 0.012), (hw - 0.03, ri - 0.05), (0.1, ri * 0.62), (0.115, 0.001)], 12)
    bmesh.ops.recalc_face_normals(rb, faces=rb.faces)
    rim = finish_mesh(name + "_rim", rb, "rim_white", "Car", tire, 0, weighted=False)
    hb = bmesh.new()
    bmesh.ops.create_cone(hb, cap_ends=True, cap_tris=False, segments=8, radius1=0.085, radius2=0.06, depth=0.07, matrix=M((0.145, 0, 0), (0, 90, 0)))
    finish_mesh(name + "_hub", hb, "maroon", "Car", tire, 0, weighted=False)
    return tire


# realistic matte rubber + slightly metallic rims for the game build
for _n, _rough, _metal in (("tire_rubber", 0.88, 0.0), ("rim_white", 0.35, 0.35)):
    _b = material(_n).node_tree.nodes["Principled BSDF"]
    _b.inputs["Roughness"].default_value, _b.inputs["Metallic"].default_value = _rough, _metal
material("tire_rubber").node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = lin("#1F1F21")

r = root()
# swap the LOW lathe wheels for the game tyres
for w in [o for o in r.children if o.name.startswith("car_hero_wheel_")]:
    for o in reversed(descend(w)):
        bpy.data.objects.remove(o, do_unlink=True)
for tag, sx, sy in (("FL", 1, 1), ("FR", -1, 1), ("RL", 1, -1), ("RR", -1, -1)):
    game_tire(f"car_hero_wheel_{tag}", (sx * TRACK, sy * BASE, WHEEL_Z), sx, r)

# small parts nobody sees at game distance; the 3D-text "0" alone is ~3k tris -> flat ring instead
for o in list(collection("Car").objects):
    if o.name.startswith(("eye_glint", "spring_seat", "spring_cap", "spring_arm", "winch_hook", "winch_coil", "tow_hook", "rack_leg",
                          "rack_post", "rack_rail_top", "crate_plank")):
        bpy.data.objects.remove(o, do_unlink=True)
    elif o.name.startswith("decal_zero_"):
        loc, sx = o.location.copy(), 1 if o.name.endswith("_1") else -1
        bpy.data.objects.remove(o, do_unlink=True)
        z = torus(f"decal_zero_{sx}", 0.11, 0.026, loc, "pupil", rot=(0, 90, 0), seg=12, sides=4, parent=r)
        z.scale = (1.4, 1, 1)

# coil springs: 3 turns instead of 6 still reads as a spring at game distance, for half the triangles
for o in [o for o in collection("Car").objects if o.type == "CURVE" and o.name.startswith("spring_")]:
    name, loc = o.name, o.location.copy()
    bpy.data.objects.remove(o, do_unlink=True)
    helix(name, 0.12, 0.42, 3, 0.035, loc, "metal_coil", parent=r)

wheels = [o for o in r.children if o.name.startswith("car_hero_wheel_")]
wheel_parts = set(x for w in wheels for x in descend(w))
body_parts = [o for o in descend(r)[1:] if o not in wheel_parts]

# Only the remeshed clay shell is decimated: it gets whatever budget the tyres and small parts leave.
# (Decimating the merged body collapses thin parts - glass, mirrors - so small parts stay untouched.)
shell = bpy.data.objects["car_hero_body"]
renderable = lambda o: o.type in ("MESH", "CURVE", "FONT") and not o.hide_render
wheel_tris = sum(eval_tris(o) for o in wheel_parts if renderable(o))
small_tris = sum(eval_tris(o) for o in body_parts if o is not shell and renderable(o))
shell_tris = decimate_to(shell, MAX_TRIS - wheel_tris - small_tris)
print(f"vehicles: wheels={wheel_tris} small_parts={small_tris} shell={shell_tris}", flush=True)
_groups = {}
for _o in body_parts:
    if _o is not shell and renderable(_o):
        _k = _o.name.rstrip("-0123456789._").rsplit("_", 1)[0] if _o.name[-1].isdigit() else _o.name
        _groups[_k] = _groups.get(_k, 0) + eval_tris(_o)
print("vehicles: parts", sorted(_groups.items(), key=lambda kv: -kv[1]), flush=True)
for o in body_parts + list(wheel_parts):
    o.name = o.name + "_src"
body = merged("car_body", body_parts, (0, 0, 0), "GameExport")
parts = [body]
for w in wheels:
    tag = w.name.replace("_src", "").split("_")[-1]
    wo = merged(f"wheel_{tag}", descend(w), tuple(w.matrix_world.translation), "GameExport")
    parts.append(wo)

counts = {o.name: decimate_to(o, WHEEL_TRIS) for o in parts[1:]}
counts["car_body"] = eval_tris(body)

sc = bpy.context.scene
for o in parts:
    if o.name not in sc.collection.objects:
        sc.collection.objects.link(o)
for o in bpy.context.view_layer.objects:
    o.select_set(False)
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = body
os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
kw = dict(filepath=GLB_PATH, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
          export_normals=True, export_texcoords=False, export_tangents=False, export_cameras=False, export_lights=False,
          export_animations=False, export_materials="EXPORT",
          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
          export_draco_position_quantization=14, export_draco_normal_quantization=10)
bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})
result["game_export"] = {"glb": GLB_PATH, "tris": counts, "total": sum(counts.values()), "bytes": os.path.getsize(GLB_PATH)}
