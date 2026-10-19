# Shared helpers for building low-poly, flat-shaded, vertex-colored game assets in Blender.
# Sent ahead of each asset script by bl.mjs; everything lands in the "AssetBuild" collection.
import bpy, bmesh, math, os, json, random
from mathutils import Matrix, Vector, Euler, noise

OUT_ROOT = globals().get("OUT_ROOT", r"C:/project/New Game/models")
REPORT = []
# Clay style (reference 01): rounded bevels, smooth normals, satin vertex-color material.
CLAY = globals().get("CLAY", "1") == "1"
BEVEL_SEGMENTS = {0: 2, 1: 1, 2: 0}   # per LOD
CURRENT_LOD = [0]


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexcol(h):
    h = h.lstrip("#")
    return tuple(_lin(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


# Colors sampled from the reference images (sRGB hex)
PAL_HEX = {
    # vehicles
    "car_red": "#D8392B", "car_red_dark": "#A92B22", "maroon": "#5C2C25", "chassis": "#3B2B27",
    "tire": "#2A2A2D", "tire_side": "#38383C", "rim": "#D6D8DE", "window": "#5E3A37", "glass_blue": "#5C7A8C",
    "eye_white": "#F4F4F2", "pupil": "#1E1E22", "spring": "#B9BCC2", "copper": "#B8743A",
    "yellow": "#F2B533", "blue": "#3F63B8", "purple": "#7B5BB5", "pink": "#E06AA8", "green_car": "#7CC243",
    "teal": "#83C6C8", "cream": "#F1ECDF", "orange_car": "#EE7D2E",
    # nature
    "pine": "#5F9F3B", "pine_dark": "#457F2F", "trunk": "#6B4528", "snow": "#F4F7FA", "snow_shade": "#D9E4EE",
    "rock": "#9C928A", "rock_dark": "#7A706A", "sand": "#EBBE73", "sand_dark": "#D9A25A", "desert": "#E39A4D",
    "desert_dark": "#C98340", "red_rock": "#B5613B", "red_rock_dark": "#8C462C", "grass": "#8CC44C",
    "grass_dark": "#6DA43A", "forest_floor": "#5E9A36", "dirt": "#8A5E38", "dirt_dark": "#6E4A2C",
    "asphalt": "#3D4148", "road_line": "#EDEDED", "ice": "#A9D9EC", "ice_dark": "#86C2DC", "water": "#3E8FCB",
    "water_deep": "#2C6FA8", "cactus": "#5E9E3A", "cactus_dark": "#4A8530", "palm_trunk": "#9C6B3D",
    "palm_leaf": "#4FA03A", "bush": "#5C9A35",
    # camp / props
    "tent_orange": "#F08A2C", "tent_red": "#D8452B", "tent_blue": "#3C6FB5", "tent_yellow": "#F2C230",
    "white": "#F2EFE8", "trailer_stripe": "#C9A15A", "wood": "#9E6C3E", "wood_dark": "#6C4829",
    "wood_light": "#C08A55", "fire_orange": "#FF8A24", "fire_yellow": "#FFD24A", "ember": "#E0451F",
    "ramp_orange": "#F2A13A", "ramp_dark": "#D9822B", "rope": "#C7A46A", "metal": "#8A9099", "metal_dark": "#5C6168",
    "lamp_glow": "#FFE6A0", "flag_red": "#E0453A", "flag_orange": "#F29A33", "flag_yellow": "#F5D24A",
    "flag_green": "#5DB55A", "flag_blue": "#3C7CC8", "flag_purple": "#8A5BB5", "black": "#1E1E22",
    "canvas": "#E8DCC0", "boat_red": "#D9473A", "smoke": "#F2F2F2", "olive": "#6E7F3A", "crate": "#B47C4A",
    "umbrella_a": "#E5534B", "umbrella_b": "#F5E6C8", "towel": "#4FA3D8", "chair_blue": "#4B8BD1",
    "gondola_red": "#D9443A", "ball_white": "#F4F4F4", "ball_black": "#222226",
}
C = {k: hexcol(v) for k, v in PAL_HEX.items()}


def M(loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    if not hasattr(scale, "__len__"):
        scale = (scale, scale, scale)
    return Matrix.LocRotScale(Vector(loc), Euler([math.radians(a) for a in rot], "XYZ"), Vector(scale))


class Part:
    """A bmesh being assembled from colored primitives. finish() turns it into an object."""

    def __init__(self):
        self.bm = bmesh.new()
        self.col = self.bm.loops.layers.float_color.new("Col")

    def _paint(self, verts, color):
        c = C[color] if isinstance(color, str) else color
        for f in {f for v in verts for f in v.link_faces}:
            for loop in f.loops:
                loop[self.col] = c
        return verts

    def transform(self, verts, matrix):
        bmesh.ops.transform(self.bm, matrix=matrix, verts=verts)

    def box(self, color, size=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0), taper=None):
        """Axis box; taper=(sx, sy) scales the top face (for wedge-ish cabins/roofs)."""
        verts = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        if taper:
            for v in verts:
                if v.co.z > 0:
                    v.co.x *= taper[0]
                    v.co.y *= taper[1]
        self.transform(verts, M(loc, rot, size))
        return self._paint(verts, color)

    def cyl(self, color, r=0.5, depth=1.0, seg=8, loc=(0, 0, 0), rot=(0, 0, 0), r2=None, caps=True, scale=1.0):
        verts = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r,
                                      radius2=r if r2 is None else r2, depth=depth, matrix=M(loc, rot, scale))["verts"]
        return self._paint(verts, color)

    def cone(self, color, r=0.5, depth=1.0, seg=6, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
        return self.cyl(color, r, depth, seg, loc, rot, r2=0.0, scale=scale)

    def ico(self, color, r=0.5, sub=1, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, jitter=0.0, seed=0):
        if CLAY and CURRENT_LOD[0] < 2:
            sub += 1
        verts = bmesh.ops.create_icosphere(self.bm, subdivisions=sub, radius=r, matrix=M(loc, rot, scale))["verts"]
        if jitter:
            rnd = random.Random(seed)
            for v in verts:
                v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * jitter
        return self._paint(verts, color)

    def poly(self, color, points, faces):
        verts = [self.bm.verts.new(p) for p in points]
        for f in faces:
            self.bm.faces.new([verts[i] for i in f])
        return self._paint(verts, color)

    def prism(self, color, profile, width, loc=(0, 0, 0), rot=(0, 0, 0)):
        """Extrude a closed 2D profile [(y, z), ...] along X by `width`, centered."""
        n = len(profile)
        pts = [(-width / 2, y, z) for y, z in profile] + [(width / 2, y, z) for y, z in profile]
        faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
        faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
        verts = self.poly(color, pts, faces)
        self.transform(verts, M(loc, rot))
        return verts

    def ring(self, color, R=1.0, r=0.1, seg=12, sides=4, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
        """Low-poly torus around Z."""
        pts, faces = [], []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            for j in range(sides):
                b = 2 * math.pi * j / sides + math.pi / sides
                d = R + r * math.cos(b)
                pts.append((d * math.cos(a), d * math.sin(a), r * math.sin(b)))
        for i in range(seg):
            for j in range(sides):
                a, b = i * sides + j, i * sides + (j + 1) % sides
                c, d = ((i + 1) % seg) * sides + (j + 1) % sides, ((i + 1) % seg) * sides + j
                faces.append([a, b, c, d])
        verts = self.poly(color, pts, faces)
        self.transform(verts, M(loc, rot, scale))
        return verts

    def finish(self, name, parent=None, origin=None):
        bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        me.polygons.foreach_set("use_smooth", [CLAY] * len(me.polygons))
        attr = me.color_attributes.get("Col")
        if attr:
            me.color_attributes.active_color = attr
            me.color_attributes.render_color_index = me.color_attributes.active_color_index
        obj = bpy.data.objects.new(name, me)
        work_collection().objects.link(obj)
        obj.data.materials.append(vc_material())
        segs = BEVEL_SEGMENTS.get(CURRENT_LOD[0], 0)
        if CLAY and segs and len(me.vertices) > 3:
            xs, ys, zs = zip(*[v.co[:] for v in me.vertices])
            dims = sorted(max(a) - min(a) for a in (xs, ys, zs))
            ref = dims[1] if dims[0] < 0.03 else dims[0]
            bv = obj.modifiers.new("Bevel", "BEVEL")
            bv.width = max(0.006, min(0.3, ref * 0.12))
            bv.segments = segs
            bv.limit_method = "ANGLE"
            bv.angle_limit = math.radians(35)
            bv.use_clamp_overlap = True
        if CLAY:
            wn = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
            wn.keep_sharp = False
        if parent is not None:
            obj.parent = parent
        if origin is not None:
            obj.location = origin
        return obj


def work_collection():
    coll = bpy.data.collections.get("AssetBuild")
    if coll is None:
        coll = bpy.data.collections.new("AssetBuild")
        bpy.context.scene.collection.children.link(coll)
    return coll


def vc_material():
    mat = bpy.data.materials.get("VertexColor")
    if mat is None:
        mat = bpy.data.materials.new("VertexColor")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.5 if CLAY else 0.9
    return mat


def tris(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    total = 0
    for o in objs:
        if o.type != "MESH":
            continue
        me = o.evaluated_get(dg).to_mesh()
        me.calc_loop_triangles()
        total += len(me.loop_triangles)
        o.evaluated_get(dg).to_mesh_clear()
    return total


def descendants(obj):
    out = [obj]
    for ch in obj.children:
        out += descendants(ch)
    return out


def export_objs(objs, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    objs = [o for o in objs if o is not None]
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_normals=CLAY, export_texcoords=False, export_tangents=False, export_cameras=False,
              export_lights=False, export_extras=True, export_animations=False, export_materials="EXPORT",
              export_vertex_color="ACTIVE", export_colors=True, export_draco_mesh_compression_enable=False)
    bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})


def remove(objs):
    for o in objs:
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me and me.users == 0:
            bpy.data.meshes.remove(me)


def make_asset(category, name, build, lods=(0, 1, 2), col=None, keep=False):
    """build(lod) -> root object (children = extra nodes). col() -> collision root object."""
    counts = []
    for index, lod in enumerate(lods):
        CURRENT_LOD[0] = lod
        root = build(lod)
        objs = descendants(root)
        counts.append(tris(objs))
        export_objs(objs, f"{OUT_ROOT}/{category}/{name}_lod{index}.glb")
        if not (keep and lod == lods[0]):
            remove(objs)
    line = f"{category}/{name}: " + " / ".join(f"lod{i}={c}" for i, c in enumerate(counts))
    CURRENT_LOD[0] = 2
    if col:
        root = col()
        objs = descendants(root)
        line += f" col={tris(objs)}"
        export_objs(objs, f"{OUT_ROOT}/{category}/{name}_col.glb")
        remove(objs)
    REPORT.append(line)
    print(line)


def preview(builders, path, lod=0, cols=6, elev=30, azim=220, res=(1600, 1000)):
    """Build each builder(lod), lay them out in a grid and render a Workbench contact sheet."""
    sc = bpy.data.scenes.get("Preview") or bpy.data.scenes.new("Preview")
    for o in list(sc.collection.objects):
        sc.collection.objects.unlink(o)
    roots, x, y, row_h = [], 0.0, 0.0, 0.0
    CURRENT_LOD[0] = lod
    for i, b in enumerate(builders):
        root = b(lod)
        objs = descendants(root)
        for o in objs:
            sc.collection.objects.link(o)
        bpy.context.view_layer.update()
        xs = [(o.matrix_world @ Vector(c)).x for o in objs for c in o.bound_box]
        ys = [(o.matrix_world @ Vector(c)).y for o in objs for c in o.bound_box]
        w, d = max(xs) - min(xs), max(ys) - min(ys)
        if i and i % cols == 0:
            x, y, row_h = 0.0, y - row_h - 2, 0.0
        root.location.x += x - min(xs)
        root.location.y += y - max(ys)
        x += w + 2
        row_h = max(row_h, d)
        roots.append(root)
    bpy.context.view_layer.update()
    cam_data = bpy.data.cameras.get("PreviewCam") or bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.get("PreviewCam") or bpy.data.objects.new("PreviewCam", cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    allobjs = [o for r in roots for o in descendants(r)]
    pts = [o.matrix_world @ Vector(c) for o in allobjs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center, size = (lo + hi) / 2, (hi - lo).length
    e, a = math.radians(elev), math.radians(azim)
    direction = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = center + direction * size * 2
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = size * 0.95
    cam_data.clip_end = size * 10
    if sc.world is None:
        sc.world = bpy.data.worlds.new("PreviewWorld")
    sc.world.color = (0.55, 0.6, 0.65)
    sc.view_settings.view_transform = "Standard"
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "VERTEX"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = False
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True, scene=sc.name)
    remove(allobjs)
    return path


def seg_for(lod, hi, mid, lo):
    return (hi, mid, lo)[min(lod, 2)]

