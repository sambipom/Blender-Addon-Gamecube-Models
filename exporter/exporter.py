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
        else:
            print("No base .dat provided, starting from scratch.")
            root_nodes = []

        # Collect new nodes
        material_nodes = Exporter._collect_material_nodes()
        texture_nodes = Exporter._collect_texture_nodes()
        mesh_nodes = Exporter._collect_mesh_nodes()
        joint_nodes = Exporter._collect_armature_nodes()
        anim_nodes = Exporter._collect_animation_nodes()

        # Replace nodes of these types in root_nodes
        root_nodes = Exporter._replace_nodes(
            root_nodes,
            material_nodes + texture_nodes + mesh_nodes + joint_nodes + anim_nodes
        )

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
        For now, filter out known node types and append the replacements.
        """
        filtered = []
        for node in root_nodes:
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
