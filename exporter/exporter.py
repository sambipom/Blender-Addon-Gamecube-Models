try:
    from ..shared.IO import DAT_io, ModelBuilder, DATBuilder
    from ..shared.Nodes.Classes.Material.MaterialObject import MaterialObject
    from ..shared.Nodes.Classes.Texture.Texture import Texture
    from ..shared.Nodes.Classes.Mesh.Mesh import Mesh
    from ..shared.Nodes.Classes.Joints.Joint import Joint
    from ..shared.Nodes.Classes.Animation.Animation import Animation
    from ..shared.Nodes.Classes.RootNodes.SectionInfo import SectionInfo
except ImportError:
    from shared.IO import DAT_io, ModelBuilder, DATBuilder
    from shared.Nodes.Classes.Material.MaterialObject import MaterialObject
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
        for mat in bpy.data.materials:
            mat_node = MaterialObject(address=None, blender_obj=mat)
            # Populate fields from Blender material properties with fallbacks
            try:
                mat_node.diffuse_color = tuple(getattr(mat, "diffuse_color", (1.0, 1.0, 1.0))[:3])
            except Exception:
                mat_node.diffuse_color = (1.0, 1.0, 1.0)

            try:
                mat_node.specular_color = tuple(getattr(mat, "specular_color", (1.0, 1.0, 1.0))[:3])
            except Exception:
                mat_node.specular_color = (1.0, 1.0, 1.0)

            blend = getattr(mat, "blend_method", "OPAQUE")
            if blend == "OPAQUE":
                mat_node.alpha = 1.0
            else:
                mat_node.alpha = getattr(mat, "alpha_threshold", 1.0)
            material_nodes.append(mat_node)
        return material_nodes

    # ---------- TEXTURES ----------
    @staticmethod
    def _collect_texture_nodes():
        """Convert Blender textures/images to TextureNode objects."""
        texture_nodes = []
        for img in bpy.data.images:
            tex_node = Texture(address=None, blender_obj=img)
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
