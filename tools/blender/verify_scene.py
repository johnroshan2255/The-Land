# Assemble exported chunks + props.json around a point and render a chase-camera view to compare with references.
# Globals: CENTER="x,y" (Blender coords), RADIUS, CAM="x,y,z", TARGET="x,y,z", PREVIEW_PATH, LOD_SUFFIX
import bpy, json, math, os
from mathutils import Vector

ROOT = r"C:/project/New Game"
cx, cy = [float(v) for v in CENTER.split(",")]
R = float(globals().get("RADIUS", "220"))

sc = bpy.data.scenes.get("Verify") or bpy.data.scenes.new("Verify")
for o in list(sc.collection.objects):
    bpy.data.objects.remove(o, do_unlink=True)


def import_glb(path):
    before = set(bpy.data.objects)
    with bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0]):
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        sc.collection.objects.link(o)
    return new


# chunks touching the area
for i in range(12):
    for j in range(12):
        x0, y0 = -1200 + 200 * i, -1200 + 200 * j
        if x0 + 200 < cx - R or x0 > cx + R or y0 + 200 < cy - R or y0 > cy + R:
            continue
        import_glb(f"{ROOT}/models/terrain/chunks/terrain_chunk_{i}_{j}.glb")
import_glb(f"{ROOT}/models/terrain/world_backdrop_lod.glb")
for o in import_glb(f"{ROOT}/models/env/ocean_plane_lod0.glb"):
    pass

CATEGORY = {}
for cat in ("nature", "props", "stunts", "structures", "env", "vehicles"):
    d = f"{ROOT}/models/{cat}"
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith("_lod0.glb"):
                CATEGORY[f[:-9]] = f"{d}/{f}"

templates = {}
props = json.load(open(f"{ROOT}/data/props.json"))["props"]
placed = 0
for p in props:
    x, h, z = p["position"]
    bx, by = x, -z
    if math.hypot(bx - cx, by - cy) > R:
        continue
    t = p["type"]
    if t not in templates:
        objs = import_glb(CATEGORY[t])
        roots = [o for o in objs if o.parent is None]
        for o in objs:
            o.hide_render = True
        templates[t] = roots
    holder = bpy.data.objects.new(f"place_{placed}", None)
    sc.collection.objects.link(holder)
    holder.location = (bx, by, h)
    holder.rotation_euler = (0, 0, math.radians(p["rotation"][1]))
    holder.scale = [p["scale"][0]] * 3
    for root in templates[t]:
        stack = [(root, holder)]
        while stack:
            src, parent = stack.pop()
            dup = src.copy()
            sc.collection.objects.link(dup)
            dup.hide_render = False
            dup.parent = parent
            if parent is holder:
                dup.matrix_parent_inverse.identity()
            stack += [(ch, dup) for ch in src.children]
    placed += 1

# hero car at the camera target
if "TARGET" in globals():
    tx, ty, tz = [float(v) for v in TARGET.split(",")]
    for o in import_glb(f"{ROOT}/models/vehicles/car_hero_lod0.glb"):
        if o.parent is None:
            o.location = (tx, ty, tz)
            o.rotation_mode = "XYZ"
            o.rotation_euler = (0, 0, math.radians(float(globals().get("CAR_YAW", "0"))))

cam_data = bpy.data.cameras.get("VerifyCam") or bpy.data.cameras.new("VerifyCam")
cam = bpy.data.objects.new("VerifyCam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
cam.location = Vector([float(v) for v in CAM.split(",")])
look = Vector([float(v) for v in globals().get("LOOK", TARGET).split(",")])
cam.rotation_euler = (look - cam.location).to_track_quat("-Z", "Y").to_euler()
cam_data.lens = float(globals().get("LENS", "28"))
cam_data.clip_end = 5000

for lname, color, energy, rot, shadow in (("VerifySun", (1.0, 0.9, 0.78), 3.5, (45, 0, float(globals().get("SUN_AZ", "-60"))), True), ("VerifyFill", (0.72, 0.82, 1.0), 1.0, (60, 0, 150), False)):
    L = bpy.data.lights.new(lname, "SUN")
    L.color, L.energy, L.angle, L.use_shadow = color, energy, math.radians(10), shadow
    lo = bpy.data.objects.new(lname, L)
    sc.collection.objects.link(lo)
    lo.rotation_euler = [math.radians(a) for a in rot]
if sc.world is None:
    sc.world = bpy.data.worlds.new("VerifyWorld")
sc.world.use_nodes = True
bg = sc.world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.55, 0.75, 1.0, 1)
bg.inputs[1].default_value = 0.8
sc.view_settings.view_transform = "AgX"
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 1280, 800
sc.render.filepath = PREVIEW_PATH
with bpy.context.temp_override(scene=sc):
    bpy.ops.render.render(write_still=True, scene=sc.name)

# clean up everything this script created
for o in list(sc.collection.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for me in list(bpy.data.meshes):
    if me.users == 0:
        bpy.data.meshes.remove(me)
result = {"placed_props": placed, "templates": len(templates)}
