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
            # TODO: populate mat_node fields from Blender material properties
            # mat_node.diffuse_color = mat.diffuse_color[:3]
            # mat_node.specular_color = mat.specular_color[:3]
            # mat_node.alpha = 1.0 if mat.blend_method == 'OPAQUE' else mat.alpha_threshold
            material_nodes.append(mat_node)
        return material_nodes

    # ---------- TEXTURES ----------
    @staticmethod
    def _collect_texture_nodes():
        """Convert Blender textures/images to TextureNode objects."""
        texture_nodes = []
        for img in bpy.data.images:
            tex_node = Texture(address=None, blender_obj=img)
            # TODO: populate tex_node fields
            # tex_node.path = img.filepath_from_user()
            # tex_node.width, tex_node.height = img.size
            # tex_node.format = Exporter._deduce_image_format(img)
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
                # TODO: populate mesh_node fields
                # mesh_node.vertices = Exporter._extract_vertices(obj)
                # mesh_node.normals = Exporter._extract_normals(obj)
                # mesh_node.uvs = Exporter._extract_uvs(obj)
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
                    # TODO: populate joint_node fields
                    # joint_node.name = bone.name
                    # joint_node.head = bone.head_local
                    # joint_node.tail = bone.tail_local
                    joint_nodes.append(joint_node)
        return joint_nodes

    # ---------- ANIMATIONS ----------
    @staticmethod
    def _collect_animation_nodes():
        """Convert Blender actions/shape keys to AnimationNode objects."""
        anim_nodes = []
        for action in bpy.data.actions:
            anim_node = Animation(address=None, blender_obj=action)
            # TODO: populate anim_node fields
            # anim_node.name = action.name
            # anim_node.keyframes = Exporter._extract_keyframes(action)
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
