"""
Generate LOD1 / LOD2 / collision meshes for selected objects and export each level as .glb.

Run one of:
  - Blender MCP: ask Claude to execute this file's contents (set CONFIG first).
  - Blender Text Editor: open, select objects in the viewport, press Run Script.
  - Headless:  blender -b scene.blend -P blender_generate_lods.py -- --all [--out C:/path/to/dir]

For each source mesh object NAME it creates (in a "LODs" collection):
  NAME_lod1, NAME_lod2  - Decimate (Collapse) copies
  NAME_col              - Planar dissolve + heavy collapse copy (Rapier collision proxy)
and exports NAME_lod0.glb, NAME_lod1.glb, NAME_lod2.glb, NAME_col.glb to EXPORT_DIR.

Tested against the Blender 4.x Python API; export options are filtered to the ones the
installed glTF exporter actually has, so it also runs on 3.6+.
"""

import math
import os
import sys

import bpy

# ---------------------------------------------------------------- CONFIG
CONFIG = {
    "EXPORT_DIR": "//lod_export",   # '//' = next to the .blend file
    "LOD_RATIOS": [0.35, 0.12],     # LOD1, LOD2 as fraction of LOD0 triangles
    "MIN_TRIS_FOR_LOD": 200,        # skip LODs for meshes already this small
    "MAKE_COLLISION": True,
    "COL_PLANAR_ANGLE_DEG": 8.0,    # planar dissolve angle for the collision proxy
    "COL_RATIO": 0.05,              # extra collapse after planar dissolve
    "COL_MAX_TRIS": 300,
    "EXPORT": True,
    "EXPORT_NORMALS": False,        # False for flat-shaded vertex-color meshes (three.js flatShading)
    "COLLECTION": "LODs",
}
# -----------------------------------------------------------------------


def tri_count(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def ensure_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def evaluated_copy(src, new_name, modifiers, coll):
    """Duplicate src, apply the given modifier specs through the depsgraph, return the new object."""
    tmp = src.copy()
    tmp.data = src.data.copy()
    coll.objects.link(tmp)
    for spec in modifiers:
        mod = tmp.modifiers.new(name=spec["name"], type="DECIMATE")
        for key, value in spec["props"].items():
            setattr(mod, key, value)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked = bpy.data.meshes.new_from_object(tmp.evaluated_get(depsgraph))
    old_mesh = tmp.data
    tmp.modifiers.clear()
    tmp.data = baked
    bpy.data.meshes.remove(old_mesh)

    existing = bpy.data.objects.get(new_name)
    if existing is not None and existing is not tmp:
        bpy.data.objects.remove(existing, do_unlink=True)
    tmp.name = new_name
    tmp.data.name = new_name
    return tmp


def gltf_export(objs, filepath):
    op_props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    wanted = {
        "filepath": filepath,
        "export_format": "GLB",
        "use_selection": True,
        "export_apply": True,
        "export_normals": CONFIG["EXPORT_NORMALS"],
        "export_texcoords": False,
        "export_tangents": False,
        "export_materials": "EXPORT",
        "export_cameras": False,
        "export_lights": False,
        "export_extras": True,
        # Vertex colors: Blender 4.2+ uses export_vertex_color, older uses export_colors
        "export_vertex_color": "ACTIVE",
        "export_colors": True,
        "export_draco_mesh_compression_enable": False,  # compress later with meshopt
    }
    kwargs = {k: v for k, v in wanted.items() if k in op_props}

    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(**kwargs)


def process(src, coll, export_dir):
    base = tri_count(src.data)
    made = {"lod0": src}
    report = [f"{src.name}: lod0={base}"]

    if base >= CONFIG["MIN_TRIS_FOR_LOD"]:
        for i, ratio in enumerate(CONFIG["LOD_RATIOS"], start=1):
            obj = evaluated_copy(
                src,
                f"{src.name}_lod{i}",
                [{"name": "LOD", "props": {"decimate_type": "COLLAPSE", "ratio": ratio, "use_collapse_triangulate": True}}],
                coll,
            )
            made[f"lod{i}"] = obj
            report.append(f"lod{i}={tri_count(obj.data)}")

    if CONFIG["MAKE_COLLISION"]:
        col = evaluated_copy(
            src,
            f"{src.name}_col",
            [
                {"name": "Planar", "props": {"decimate_type": "DISSOLVE", "angle_limit": math.radians(CONFIG["COL_PLANAR_ANGLE_DEG"])}},
                {"name": "Collapse", "props": {"decimate_type": "COLLAPSE", "ratio": CONFIG["COL_RATIO"], "use_collapse_triangulate": True}},
            ],
            coll,
        )
        if tri_count(col.data) > CONFIG["COL_MAX_TRIS"]:
            report.append(f"WARNING col over budget ({tri_count(col.data)} tris)")
        col.display_type = "WIRE"
        made["col"] = col
        report.append(f"col={tri_count(col.data)}")

    if CONFIG["EXPORT"]:
        os.makedirs(export_dir, exist_ok=True)
        for level, obj in made.items():
            gltf_export([obj], os.path.join(export_dir, f"{src.name}_{level}.glb"))

    # LOD copies stay hidden in the viewport so the scene still looks like LOD0
    for level, obj in made.items():
        if level != "lod0":
            obj.hide_set(True)
    print("  ".join(report))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--out" in argv:
        CONFIG["EXPORT_DIR"] = argv[argv.index("--out") + 1]

    if "--all" in argv:
        sources = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    else:
        sources = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    skip = ("_lod", "_col")
    sources = [o for o in sources if not any(s in o.name for s in skip)]
    if not sources:
        print("No mesh objects selected (or use -- --all).")
        return

    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    coll = ensure_collection(CONFIG["COLLECTION"])
    export_dir = bpy.path.abspath(CONFIG["EXPORT_DIR"])
    for src in sources:
        process(src, coll, export_dir)
    print(f"Done: {len(sources)} object(s) -> {export_dir}")


main()
