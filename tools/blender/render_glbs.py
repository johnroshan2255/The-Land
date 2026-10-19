# Headless check render (separate Blender process, never the live MCP session):
#   blender -b --factory-startup -P render_glbs.py -- out.png a.glb b.glb ...
# Lays the models out in a row under the clay studio lighting (warm key sun 45 deg, cool fill).
import bpy, sys, math
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
out, files = args[0], [a for a in args[1:] if not a.startswith("--")]
sc = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
x = 0.0
for f in files:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.name not in sc.collection.objects and not o.visible_get():
            sc.collection.objects.link(o)
    roots = [o for o in new if o.parent is None]
    bpy.context.view_layer.update()
    xs = [(o.matrix_world @ Vector(c)).x for o in new if o.type == "MESH" for c in o.bound_box]
    w = max(xs) - min(xs)
    for r in roots:
        r.location.x += x - min(xs)
    x += w + 0.8
bpy.context.view_layer.update()
pts = [o.matrix_world @ Vector(c) for o in bpy.data.objects if o.type == "MESH" for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, (hi - lo).length
print("FRAME", tuple(lo), tuple(hi), size)

bpy.ops.mesh.primitive_plane_add(size=size * 4, location=(center.x, center.y, lo.z))
ground = bpy.context.object
gm = bpy.data.materials.new("ground")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.55, 0.25, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.55
ground.data.materials.append(gm)

for name, color, energy, rot, shadow in (("key", (1.0, 0.9, 0.78), 3.2, (45, 0, -40), True), ("fill", (0.72, 0.82, 1.0), 0.9, (60, 0, 150), False)):
    L = bpy.data.lights.new(name, "SUN")
    L.color, L.energy, L.angle, L.use_shadow = color, energy, math.radians(12), shadow
    o = bpy.data.objects.new(name, L)
    sc.collection.objects.link(o)
    o.rotation_euler = [math.radians(a) for a in rot]
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.78, 0.8, 0.84, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
sc.world = world

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
d = Vector((-0.45, 1.0, 0.55)).normalized()
cam.location = center + d * size * 1.25
cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = 45
engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = globals().get("ENGINE_OVERRIDE") or ("BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT")
if "--workbench" in sys.argv:
    sc.render.engine = "BLENDER_WORKBENCH"
sc.view_settings.view_transform = "AgX"
sc.render.resolution_x, sc.render.resolution_y = 1600, 700
sc.render.filepath = out
print("CAM", tuple(cam.location), tuple(cam.rotation_euler), [o.name for o in sc.objects][:12])
bpy.ops.render.render(write_still=True)
