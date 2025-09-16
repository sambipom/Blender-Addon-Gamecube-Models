# Entry point to the script when loaded via Blender

# metadata about the addon which blender requires
# https://wiki.blender.org/wiki/Process/Addons/Guidelines/metainfo
bl_info = {
    "name": "Gamecube Dat Model",
    "author": "Made, StarsMmd, MikeyX",
    "blender": (3, 1, 0),
    "location": "File > Import-Export",
    "description": "Import-Export Gamecube .dat models",
    "warning": "",
    "category": "Import-Export"}


if "bpy" in locals():
    pass

import bpy
import os
from bpy_extras.io_utils import ImportHelper, ExportHelper, axis_conversion

IN_BLENDER = hasattr(bpy, "app")

if IN_BLENDER:
    if __package__:
        from .exporter import exporter
        from .importer import importer
    else:  # pragma: no cover - fallback for running outside Blender package context
        from exporter import exporter  # type: ignore
        from importer import importer  # type: ignore
else:  # pragma: no cover - skip heavy imports when running tests without Blender
    exporter = None  # type: ignore
    importer = None  # type: ignore


# This class declares global properties which blender uses to add toggles and fields to the file open browser
# allowing more options to be selected along with the filepath being opened.
# When a file is selected the execute() function runs.
class ImportHSD(bpy.types.Operator, ImportHelper):
    """Load a DAT model"""
    bl_idname = "import_model.dat"
    bl_label = "Import DAT"
    bl_options = {'UNDO'}

    files: bpy.props.CollectionProperty(name="File Path",
                          description="File path used for importing "
                                      "the HSD file",
                          type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype="DIR_PATH")
    section: bpy.props.StringProperty(default = '', name = 'Section Name', description = 'Name of the section that should be imported. Leave blank to import all.')
    ik_hack: bpy.props.BoolProperty(default = True, name = 'IK Hack', description = 'Shrinks Bones down to 1e-3 to make IK work properly.')
    max_frame: bpy.props.IntProperty(default = 1000, name = 'Max Anim Frame', description = 'Cutoff frame after which animations aren\'t sampled. Use 0 For no limit.')

    filename_ext = ".dat"
    filter_glob = bpy.props.StringProperty(default="*.fdat;*.dat;*.rdat;*.pkx", options={'HIDDEN'})

    def execute(self, context):
        if self.files and self.directory:
            paths = [os.path.join(self.directory, file.name) for file in self.files]
        else:
            paths = [self.filepath]

        for path in paths:
            status = Importer.parseDAT(context, path, self.section, self.ik_hack, self.max_frame, False)
            if not 'FINISHED' in status:
                return status

        return {'FINISHED'}


class ExportHSD(bpy.types.Operator, ExportHelper):
    """Export current scene to Gamecube .dat format"""
    bl_idname = "export_scene.hsd"
    bl_label = "Export HSD (.dat)"

    filename_ext = ".dat"
    filter_glob: bpy.props.StringProperty(default="*.dat", options={'HIDDEN'})

    source_dat: bpy.props.StringProperty(
        name="Base DAT",
        description="Optional base .dat to patch instead of rebuilding",
        default="",
        subtype='FILE_PATH'
    )

    @classmethod
    def poll(cls, context):
        # Allow export even if no object is selected (e.g. patch materials only)
        return True

    def execute(self, context):
        try:
            exporter.Exporter.writeDAT(context, self.filepath, source_dat=self.source_dat)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}

def menu_func_import(self, context):
    self.layout.operator(ImportHSD.bl_idname, text="Gamecube Dat Model (.dat)")


def menu_func_export(self, context):
    self.layout.operator(ExportHSD.bl_idname, text="Gamecube Dat Model (.dat)")


classes = (
    ImportHSD,
    ExportHSD,
)

# This function is called when the addon is installed by the user. The classes are registered and added to the blender menus.
def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

# This function is called when the addon is uninstalled by the user. The classes are unregistered and removed from the blender menus.
def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

# This function is called when the addon is run as a script from within blender's scripting window
if __name__ == "__main__":
    register()


