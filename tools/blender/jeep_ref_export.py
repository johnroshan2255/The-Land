# Export the jeep built by jeep_ref.py to GLB. Run after hero_car.py + jeep_ref.py (NO_RENDER=1):
#   node tools/blender/headless.mjs tools/blender/hero_car.py tools/blender/jeep_ref.py tools/blender/jeep_ref_export.py STEP=setup NO_RENDER=1
# Writes red_jeep.glb (car only) and red_jeep_diorama.glb (car + base, trees, rock). Curves, text and modifiers are
# baked to plain meshes with hero_car.merged() (to_mesh; new_from_object on curves crashes Blender).
import os

GLB_DIR = globals().get("GLB_DIR", r"C:/project/New Game/models/red_jeep")
BODY_RATIO = float(globals().get("BODY_RATIO", "0.25"))   # decimate the dense remeshed body shell


def baked(src_coll, coll_name):
    body = bpy.data.objects.get("car_hero_body")
    if src_coll == "Car" and body and BODY_RATIO < 1:
        d = body.modifiers.new("ExportDecimate", "DECIMATE")
        d.ratio = BODY_RATIO
    out = []
    for o in list(collection(src_coll).objects):
        if o.type in ("MESH", "CURVE", "FONT") and not o.hide_render:
            out.append(merged(o.name + "_x", [o], (0, 0, 0), coll_name))
    for o in out:
        o.name = o.name[:-2] if o.name.endswith("_x") else o.name
    return out


def tri_count(objs):
    n = 0
    for o in objs:
        o.data.calc_loop_triangles()
        n += len(o.data.loop_triangles)
    return n


def export(objs, path):
    # export from the default context scene (temp_override into HeroCar crashes the glTF exporter)
    sc = bpy.context.scene
    for o in objs:
        if o.name not in sc.collection.objects:
            sc.collection.objects.link(o)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_normals=True, export_texcoords=False, export_tangents=False, export_cameras=False,
              export_lights=False, export_animations=False, export_materials="EXPORT")
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})


os.makedirs(GLB_DIR, exist_ok=True)
car = baked("Car", "Export_Car")
ground = baked("Studio_ground", "Export_Ground")
p_car, p_dio = f"{GLB_DIR}/red_jeep.glb", f"{GLB_DIR}/red_jeep_diorama.glb"
print("vehicles: export car", flush=True)
export(car, p_car)
print("vehicles: export diorama", flush=True)
export(car + ground, p_dio)
result["export"] = {"car": p_car, "car_tris": tri_count(car), "diorama": p_dio, "diorama_tris": tri_count(car + ground)}
