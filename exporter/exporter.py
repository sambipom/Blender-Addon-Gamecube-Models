try:
    from ..shared.IO import DAT_io, ModelBuilder, DATBuilder
    from ..shared.Nodes.Classes.Material.Material import Material
    from ..shared.Nodes.Classes.Material.MaterialObject import MaterialObject
    from ..shared.Nodes.Classes.Colors.RGBAColor import RGBAColor
    from ..shared.Nodes.Classes.Texture.Texture import Texture
    from ..shared.Nodes.Classes.Mesh.Mesh import Mesh
    from ..shared.Nodes.Classes.Joints.Joint import Joint
    from ..shared.Nodes.Classes.Animation.Animation import Animation
    from ..shared.Nodes.Classes.RootNodes.SectionInfo import SectionInfo
except ImportError:
    from shared.IO import DAT_io, ModelBuilder, DATBuilder
    from shared.Nodes.Classes.Material.Material import Material
    from shared.Nodes.Classes.Material.MaterialObject import MaterialObject
    from shared.Nodes.Classes.Colors.RGBAColor import RGBAColor
    from shared.Nodes.Classes.Texture.Texture import Texture
    from shared.Nodes.Classes.Mesh.Mesh import Mesh
    from shared.Nodes.Classes.Joints.Joint import Joint
    from shared.Nodes.Classes.Animation.Animation import Animation
    from shared.Nodes.Classes.RootNodes.SectionInfo import SectionInfo

import bpy
import os

# --- Link repair helpers: turn integer offsets/ids back into node references ---

_PRIMITIVES = {
    # integers (signed/unsigned)
    "int","short","long","s8","s16","s32","s64",
    "uint","ushort","ulong","u8","u16","u32","u64",
    # floats
    "float","f16","f32","f64",
    # bool/byte/char
    "bool","byte","bytes","char","uchar",
    # strings
    "string","cstring",
    # aggregates we treat as primitive payloads during validation
    "vec2","vec3","vec4","quat","mat3","mat4",
    # common aliases
    "color","rgba","rgb","uv","bbox",
}

def _is_node_like(x):
    return hasattr(x, "fields") or (hasattr(x, "__class__") and hasattr(x.__class__, "fields"))

def _safe_fields(klass_or_obj):
    if hasattr(klass_or_obj, "fields"):
        return getattr(klass_or_obj, "fields") or []
    if hasattr(klass_or_obj, "__class__") and hasattr(klass_or_obj.__class__, "fields"):
        return getattr(klass_or_obj.__class__, "fields") or []
    return []

def _collect_address_index(nodes):
    idx = {}
    visited = set()

    key_attrs = ("address", "id", "addr", "offset", "ofs", "pointer", "ptr")

    def visit(n):
        nid = id(n)
        if nid in visited:
            return
        visited.add(nid)

        # index by any integer-ish identity
        for attr in key_attrs:
            v = getattr(n, attr, None)
            if isinstance(v, int):
                idx[v] = n

        # recurse children via schema fields
        for fld in _safe_fields(n):
            if not isinstance(fld, (list, tuple)) or len(fld) < 2:
                continue
            fname, ftype = fld[0], fld[1]
            try:
                val = getattr(n, fname)
            except Exception:
                continue
            if isinstance(ftype, str) and ftype.lower() in _PRIMITIVES:
                continue
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                for item in val:
                    if _is_node_like(item):
                        visit(item)
            else:
                if _is_node_like(val):
                    visit(val)

    for n in nodes:
        if _is_node_like(n):
            visit(n)
    return idx


def _repair_integer_links(nodes, index, verbose=True):
    """Replace ints found in node-typed fields with actual node refs (by address/id)."""
    repaired = 0
    nulled = 0
    visited = set()

    def fix_in_parent(parent, fname, ftype, val):
        nonlocal repaired, nulled
        # Only repair when schema says this should be another node type (string not primitive)
        if not (isinstance(ftype, str) and ftype.lower() not in _PRIMITIVES):
            return False
        if isinstance(val, int):
            ref = index.get(val)
            if ref is not None:
                setattr(parent, fname, ref)
                repaired += 1
                if verbose:
                    print(f"[link-fix] {type(parent).__name__}.{fname}: int({val}) -> {type(ref).__name__}")
                return True
            else:
                # No target found; safer to null than crash
                setattr(parent, fname, None)
                nulled += 1
                if verbose:
                    print(f"[link-fix] {type(parent).__name__}.{fname}: int({val}) -> None (unresolved)")
                return True
        return False

    def fix_list(parent, fname, ftype, seq):
        nonlocal repaired, nulled
        changed = False
        new_list = list(seq)
        for i, item in enumerate(new_list):
            if isinstance(item, int) and isinstance(ftype, str) and ftype.lower() not in _PRIMITIVES:
                ref = index.get(item)
                if ref is not None:
                    new_list[i] = ref
                    repaired += 1
                    changed = True
                    if verbose:
                        print(f"[link-fix] {type(parent).__name__}.{fname}[{i}]: int({item}) -> {type(ref).__name__}")
                else:
                    new_list[i] = None
                    nulled += 1
                    changed = True
                    if verbose:
                        print(f"[link-fix] {type(parent).__name__}.{fname}[{i}]: int({item}) -> None (unresolved)")
        if changed:
            setattr(parent, fname, new_list)

    def walk(n):
        nid = id(n)
        if nid in visited: return
        visited.add(nid)
        for fld in _safe_fields(n):
            if not isinstance(fld, (list, tuple)) or len(fld) < 2:
                continue
            fname, ftype = fld[0], fld[1]
            try:
                val = getattr(n, fname)
            except Exception:
                continue
            if val is None:
                continue
            # attempt repair on scalar
            if fix_in_parent(n, fname, ftype, val):
                val = getattr(n, fname)  # refresh after repair
            # attempt repair on list/tuple
            if isinstance(val, (list, tuple)):
                fix_list(n, fname, ftype, val)
                # refresh
                val = getattr(n, fname)
                # recurse into children
                for item in val:
                    if _is_node_like(item):
                        walk(item)
            else:
                if _is_node_like(val):
                    walk(val)

    for root in nodes:
        if _is_node_like(root):
            walk(root)

    if verbose:
        print(f"[link-fix] repaired={repaired}, nulled={nulled}")
    return repaired, nulled

def _repair_linked_list(nodes, node_type_name: str, next_field: str, index: dict, verbose=True):
    """Resolve int pointers in singly-linked lists like Frame.next."""
    repaired = 0
    nulled = 0
    visited = set()

    def is_target_type(x):
        return type(x).__name__ == node_type_name

    def fix_node(n):
        nonlocal repaired, nulled
        if id(n) in visited:
            return
        visited.add(id(n))
        if not is_target_type(n) or not hasattr(n, next_field):
            return
        nxt = getattr(n, next_field)
        if isinstance(nxt, int):
            ref = index.get(nxt)
            if ref is not None:
                setattr(n, next_field, ref)
                repaired += 1
                if verbose:
                    print(f"[link-fix:list] {node_type_name}.{next_field}: int({nxt}) -> {type(ref).__name__}")
                fix_node(ref)
            else:
                setattr(n, next_field, None)
                nulled += 1
                if verbose:
                    print(f"[link-fix:list] {node_type_name}.{next_field}: int({nxt}) -> None (unresolved)")
        elif _is_node_like(nxt):
            fix_node(nxt)

        # Also walk other node-typed fields to find chain heads
        for fld in _safe_fields(n):
            if not isinstance(fld, (list, tuple)) or len(fld) < 2:
                continue
            fname, ftype = fld[0], fld[1]
            if fname == next_field:
                continue
            try:
                val = getattr(n, fname)
            except Exception:
                continue
            if isinstance(ftype, str) and ftype.lower() in _PRIMITIVES:
                continue
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                for item in val:
                    if _is_node_like(item):
                        fix_node(item)
            elif _is_node_like(val):
                fix_node(val)

    for root in nodes:
        if _is_node_like(root):
            fix_node(root)

    if verbose:
        print(f"[link-fix:list] repaired={repaired}, nulled={nulled} for {node_type_name}.{next_field}")
    return repaired, nulled

def _force_nullify_linked_ints(nodes, node_type_name: str, next_field: str, verbose=True):
    """Set <node>.<next_field> = None whenever it is an int."""
    nulled = 0
    visited = set()

    def is_target(x): return type(x).__name__ == node_type_name

    def walk(n):
        nonlocal nulled
        nid = id(n)
        if nid in visited: return
        visited.add(nid)

        if is_target(n) and hasattr(n, next_field):
            nxt = getattr(n, next_field)
            if isinstance(nxt, int):
                if verbose:
                    print(f"[force-null] {node_type_name}.{next_field}: int({nxt}) -> None")
                setattr(n, next_field, None)
                nulled += 1
            elif _is_node_like(nxt):
                walk(nxt)

        # keep walking other node-typed fields to reach all frames
        for fld in _safe_fields(n):
            if not isinstance(fld, (list, tuple)) or len(fld) < 2: continue
            fname, ftype = fld[0], fld[1]
            if isinstance(ftype, str) and ftype.lower() in _PRIMITIVES: continue
            try:
                val = getattr(n, fname)
            except Exception:
                continue
            if val is None: continue
            if isinstance(val, (list, tuple)):
                for item in val:
                    if _is_node_like(item): walk(item)
            elif _is_node_like(val):
                walk(val)

    for root in nodes:
        if _is_node_like(root):
            walk(root)
    if verbose:
        print(f"[force-null] nulled={nulled} for {node_type_name}.{next_field}")
    return nulled

def _nullify_all_frame_next_ints(nodes, verbose=True):
    """Walk the graph and set Frame.next = None whenever it's an int, no exceptions."""
    from collections import deque
    nulled = 0
    seen = set()
    q = deque(nodes if isinstance(nodes, (list, tuple)) else [nodes])

    def is_node_like(x):
        return hasattr(x, "fields") or (hasattr(x, "__class__") and hasattr(x.__class__, "fields"))

    while q:
        n = q.popleft()
        if not is_node_like(n):
            continue
        if id(n) in seen:
            continue
        seen.add(id(n))

        # Force-null Frame.next if it's an int
        if type(n).__name__ == "Frame" and hasattr(n, "next") and isinstance(getattr(n, "next"), int):
            if verbose:
                print(f"[force-null] Frame.next: int({getattr(n, 'next')}) -> None")
            setattr(n, "next", None)
            nulled += 1

        # Traverse children by schema
        for fld in getattr(n, "fields", []) or getattr(n.__class__, "fields", []) or []:
            if not isinstance(fld, (list, tuple)) or len(fld) < 2:
                continue
            fname, ftype = fld[0], fld[1]
            try:
                val = getattr(n, fname)
            except Exception:
                continue
            if val is None:
                continue
            if isinstance(val, (list, tuple)):
                for item in val:
                    if is_node_like(item):
                        q.append(item)
            else:
                if is_node_like(val):
                    q.append(val)

    if verbose:
        print(f"[force-null] total Frame.next nulled = {nulled}")
    return nulled



class Exporter:

    @staticmethod
    def writeDAT(context, path, source_dat=None):
        """
        Export function for GameCube .dat models.

        If source_dat is provided, we load it and patch only selected sections.
        Otherwise, we build new nodes entirely.
        """

        if source_dat and os.path.exists(source_dat):
            print(f"Loading base .dat: {source_dat}")
            root_nodes = ModelBuilder.build_from_file(source_dat)
            # Normalize root_nodes into a flat list of node-like objects
            if isinstance(root_nodes, tuple) and len(root_nodes) == 2:
                # e.g., (nodes, section_info)
                maybe_nodes, _maybe_section_info = root_nodes
                root_nodes = maybe_nodes
            elif hasattr(root_nodes, "nodes"):
                # e.g., a container with .nodes
                root_nodes = root_nodes.nodes
        else:
            print("No base .dat provided, starting from scratch.")
            root_nodes = []

        def _is_node_like(x):
            # Node classes in your schema expose a class-level 'fields' list/tuple
            # and instances will have a .__class__.fields
            return hasattr(x, "fields") or (hasattr(x, "__class__") and hasattr(x.__class__, "fields"))

        if not isinstance(root_nodes, (list, tuple)):
            # Some loaders return a container/dict; keep only node-like values
            try:
                root_nodes = list(root_nodes)
            except Exception:
                try:
                    root_nodes = list(getattr(root_nodes, "values", lambda: [])())
                except Exception:
                    root_nodes = []

        # Keep only node-like entries
        root_nodes = [n for n in root_nodes if _is_node_like(n)]

        # Collect new nodes
        material_nodes = Exporter._collect_material_nodes()
        texture_nodes = Exporter._collect_texture_nodes()
        mesh_nodes = Exporter._collect_mesh_nodes()
        joint_nodes = Exporter._collect_armature_nodes()
        anim_nodes = Exporter._collect_animation_nodes()


        addr_index = _collect_address_index(root_nodes)
        # General repair pass (fix any node-typed fields that are ints)
        total_rep = total_null = 0
        # for _ in range(5):  # a few passes so deeper chains get reachable after earlier fixes
        #     rep, nul = _repair_integer_links(root_nodes, addr_index, verbose=True)
        #     total_rep += rep; total_null += nul
        #     if rep == 0 and nul == 0:
        #         break

        root_nodes = Exporter._replace_nodes(
            root_nodes,
            material_nodes + texture_nodes + mesh_nodes + joint_nodes + anim_nodes
        )

        # --- FINAL SAFETY PASS: kill any raw int in Frame.next to prevent writer crash ---
        _nullify_all_frame_next_ints(root_nodes, verbose=True)

        # Sanity assert so we fail early (clear message) if anything slipped through
        def _assert_no_frame_next_int(nodes):
            from collections import deque
            q = deque(nodes if isinstance(nodes, (list, tuple)) else [nodes])
            seen = set()
            while q:
                n = q.popleft()
                if not hasattr(n, "__class__"):
                    continue
                if id(n) in seen:
                    continue
                seen.add(id(n))
                if type(n).__name__ == "Frame" and isinstance(getattr(n, "next", None), int):
                    raise RuntimeError(f"Unresolved Frame.next int: {getattr(n, 'next')!r}")
                for fld in getattr(n, "fields", []) or getattr(n.__class__, "fields", []) or []:
                    if not isinstance(fld, (list, tuple)) or len(fld) < 2:
                        continue
                    fname, ftype = fld[0], fld[1]
                    val = getattr(n, fname, None)
                    if val is None:
                        continue
                    if isinstance(val, (list, tuple)):
                        for item in val:
                            if hasattr(item, "__class__"):
                                q.append(item)
                    elif hasattr(val, "__class__"):
                        q.append(val)

        _assert_no_frame_next_int(root_nodes)


        # --- pointer repair AFTER replacement so new nodes (e.g., Frames) get fixed ---
        addr_index = _collect_address_index(root_nodes)

        # 2) Try to resolve Frame.next ints -> Frame nodes
        rep, nul = _repair_linked_list(
            root_nodes, node_type_name="Frame", next_field="next", index=addr_index, verbose=True
        )
        print(f"Frame.next link repair (post-replace): repaired={rep}, nulled={nul}")

        # 3) If anything still an int, force-null it so we don't crash
        nul_forced = _force_nullify_linked_ints(root_nodes, "Frame", "next", verbose=True)
        print(f"Frame.next force-null: nulled={nul_forced}")

        if rep2 == 0:  # nothing resolved; avoid crashing on raw ints
            _force_nullify_linked_ints(root_nodes, "Frame", "next", verbose=True)

        # (Optional) other known singly-linked lists:
        # _repair_linked_list(root_nodes, "Material", "next", addr_index, verbose=True)
        # _repair_linked_list(root_nodes, "Mesh",     "next", addr_index, verbose=True)

        # Sanity: ensure Frame.next is not an int anymore
        def _assert_no_int_next(nodes):
            from collections import deque
            q = deque(nodes)
            while q:
                n = q.popleft()
                if not _is_node_like(n):
                    continue
                if type(n).__name__ == "Frame" and isinstance(getattr(n, "next", None), int):
                    raise RuntimeError(f"Unresolved Frame.next int: {getattr(n, 'next')!r}")
                for fname, ftype in _safe_fields(n):
                    if isinstance(ftype, str) and ftype.lower() in _PRIMITIVES:
                        continue
                    v = getattr(n, fname, None)
                    if v is None:
                        continue
                    if isinstance(v, (list, tuple)):
                        q.extend(x for x in v if _is_node_like(x))
                    elif _is_node_like(v):
                        q.append(v)

        _assert_no_int_next(root_nodes)

        # Write output file
        builder = DATBuilder(path, root_nodes)
        builder.build()
        print(f"Export complete: {path}")
        return {'FINISHED'}

    # ---------- MATERIALS ----------
    @staticmethod
    def _collect_material_nodes():
        """Convert Blender materials to MaterialNode objects."""
        material_nodes = []
        data = getattr(bpy, "data", None)
        materials = getattr(data, "materials", []) if data is not None else []

        for mat in materials or []:
            mat_node = MaterialObject(address=None, blender_obj=mat)

            class_type_value = getattr(mat, "gc_class_type", None)
            if class_type_value is None:
                class_type_value = getattr(mat, "name", "")
            mat_node.class_type = str(class_type_value) if class_type_value is not None else ""

            render_mode_value = getattr(mat, "gc_render_mode", 0)
            try:
                mat_node.render_mode = int(render_mode_value)
            except (TypeError, ValueError):
                mat_node.render_mode = 0

            diffuse_rgb = Exporter._color_components(mat, "diffuse_color", (1.0, 1.0, 1.0))
            specular_rgb = Exporter._color_components(mat, "specular_color", (1.0, 1.0, 1.0))
            alpha_value = Exporter._material_alpha(mat)

            mat_node.material = Exporter._build_material_struct(
                mat, diffuse_rgb, specular_rgb, alpha_value
            )

            mat_node.texture = None
            mat_node.render_data = None
            mat_node.pixel_engine_data = None

            material_nodes.append(mat_node)
        return material_nodes

    # ---------- TEXTURES ----------
    @staticmethod
    def _collect_texture_nodes():
        """Convert Blender textures/images to TextureNode objects."""
        texture_nodes = []
        data = getattr(bpy, "data", None)
        images = getattr(data, "images", []) if data is not None else []

        for index, img in enumerate(images or []):
            tex_node = Texture(address=None, blender_obj=img)
            tex_node.name = getattr(img, "name", f"texture_{index}") or f"texture_{index}"
            tex_node.texture_id = index
            try:
                tex_node.path = img.filepath_from_user() if hasattr(img, "filepath_from_user") else getattr(img, "filepath", "")
            except Exception:
                tex_node.path = getattr(img, "filepath", "")

            size = getattr(img, "size", (0, 0))
            try:
                tex_node.width, tex_node.height = int(size[0]), int(size[1])
            except Exception:
                tex_node.width, tex_node.height = 0, 0

            tex_node.format = Exporter._deduce_image_format(img)
            texture_nodes.append(tex_node)

        for idx in range(len(texture_nodes) - 1):
            texture_nodes[idx].next = texture_nodes[idx + 1]
        return texture_nodes

    # ---------- MESHES ----------
    @staticmethod
    def _collect_mesh_nodes():
        """Convert Blender mesh objects to MeshNode objects."""
        mesh_nodes = []
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                mesh_node = Mesh(address=None, blender_obj=obj)
                try:
                    mesh_node.vertices = Exporter._extract_vertices(obj)
                    mesh_node.normals = Exporter._extract_normals(obj)
                    mesh_node.uvs = Exporter._extract_uvs(obj)
                except Exception:
                    mesh_node.vertices = []
                    mesh_node.normals = []
                    mesh_node.uvs = []
                mesh_nodes.append(mesh_node)
        return mesh_nodes

    # ---------- ARMATURES / BONES ----------
    @staticmethod
    def _collect_armature_nodes():
        """Convert Blender armatures to JointNode objects."""
        joint_nodes = []
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE':
                for bone in obj.data.bones:
                    joint_node = Joint(address=None, blender_obj=bone)
                    try:
                        joint_node.name = bone.name
                        joint_node.head = tuple(bone.head_local)
                        joint_node.tail = tuple(bone.tail_local)
                    except Exception:
                        joint_node.name = getattr(bone, "name", "")
                        joint_node.head = (0.0, 0.0, 0.0)
                        joint_node.tail = (0.0, 0.0, 0.0)
                    joint_nodes.append(joint_node)
        return joint_nodes

    # ---------- ANIMATIONS ----------
    @staticmethod
    def _collect_animation_nodes():
        """Convert Blender actions/shape keys to AnimationNode objects."""
        anim_nodes = []
        for action in bpy.data.actions:
            anim_node = Animation(address=None, blender_obj=action)
            try:
                anim_node.name = action.name
            except Exception:
                anim_node.name = getattr(action, "name", "")
            anim_nodes.append(anim_node)
        return anim_nodes

    # ---------- UTILS ----------
    @staticmethod
    def _replace_nodes(root_nodes, new_nodes):
        """
        Replace nodes of matching type in root_nodes with new ones.
        Filters out non-node values (e.g., ints/offsets) and previously existing
        nodes of the same types, then appends replacements.
        """
        def is_node_like(x):
            return hasattr(x, "__class__") and hasattr(x.__class__, "fields")

        filtered = []
        for node in root_nodes or []:
            if not is_node_like(node):
                continue
            if not isinstance(node, (MaterialObject, Texture, Mesh, Joint, Animation)):
                filtered.append(node)
        return filtered + new_nodes

    @staticmethod
    def _deduce_image_format(img):
        """Simple helper to guess image format from file extension."""
        ext = os.path.splitext(img.filepath)[-1].lower()
        if ext in (".png", ".tga"):
            return "RGBA8"
        if ext in (".jpg", ".jpeg"):
            return "RGB8"
        return "UNKNOWN"

    @staticmethod
    def _extract_vertices(obj):
        return [v.co[:] for v in obj.data.vertices]

    @staticmethod
    def _extract_normals(obj):
        return [v.normal[:] for v in obj.data.vertices]

    @staticmethod
    def _extract_uvs(obj):
        if obj.data.uv_layers.active:
            return [loop.uv[:] for loop in obj.data.uv_layers.active.data]
        return []

    @staticmethod
    def _color_components(material, attribute, fallback):
        values = getattr(material, attribute, fallback)
        components = []
        for index in range(3):
            try:
                component = float(values[index])
            except (TypeError, ValueError, IndexError):
                component = fallback[index]
            components.append(component)
        return tuple(components)

    @staticmethod
    def _material_alpha(material):
        blend_method = getattr(material, "blend_method", "OPAQUE")
        alpha_source = None

        if blend_method == "OPAQUE":
            alpha_source = getattr(material, "alpha", None)
            if alpha_source is None:
                try:
                    alpha_source = float(getattr(material, "diffuse_color")[3])
                except (TypeError, ValueError, IndexError, AttributeError):
                    alpha_source = None
            if alpha_source is None:
                alpha_source = 1.0
        else:
            alpha_source = getattr(material, "alpha_threshold", None)
            if alpha_source is None:
                alpha_source = getattr(material, "alpha", None)
            if alpha_source is None:
                alpha_source = 1.0

        return Exporter._clamp_float(alpha_source)

    @staticmethod
    def _build_material_struct(material, diffuse_rgb, specular_rgb, alpha_value):
        material_struct = Material(address=None, blender_obj=material)
        material_struct.ambient = Exporter._color_to_rgba_node(diffuse_rgb, 1.0)
        material_struct.diffuse = Exporter._color_to_rgba_node(diffuse_rgb, alpha_value)
        material_struct.specular = Exporter._color_to_rgba_node(specular_rgb, 1.0)
        material_struct.alpha = Exporter._clamp_float(alpha_value)

        shininess_source = getattr(material, "specular_intensity", 0.0)
        try:
            material_struct.shininess = float(shininess_source)
        except (TypeError, ValueError):
            material_struct.shininess = 0.0

        return material_struct

    @staticmethod
    def _color_to_rgba_node(rgb_values, alpha_value):
        rgba_node = RGBAColor(address=None, blender_obj=None)
        components = list(rgb_values[:3])
        while len(components) < 3:
            components.append(1.0)
        rgba_floats = components + [alpha_value]
        rgba_bytes = [Exporter._color_component_to_byte(component) for component in rgba_floats]
        rgba_node.red, rgba_node.green, rgba_node.blue, rgba_node.alpha = rgba_bytes
        return rgba_node

    @staticmethod
    def _color_component_to_byte(value):
        try:
            component = float(value)
        except (TypeError, ValueError):
            component = 0.0

        if component > 1.0:
            component = max(0.0, min(component, 255.0))
            return int(round(component))

        component = max(0.0, min(component, 1.0))
        return int(round(component * 255))

    @staticmethod
    def _clamp_float(value, minimum=0.0, maximum=1.0):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return minimum
        return max(minimum, min(maximum, numeric))
