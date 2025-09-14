import sys
import types

# Provide stub modules for Blender-specific imports used in package init
sys.modules.setdefault('bpy', types.ModuleType('bpy'))

bpy_extras = types.ModuleType('bpy_extras')
io_utils = types.ModuleType('io_utils')
io_utils.ImportHelper = object
io_utils.ExportHelper = object
io_utils.axis_conversion = lambda *args, **kwargs: None
bpy_extras.io_utils = io_utils
sys.modules.setdefault('bpy_extras', bpy_extras)
sys.modules.setdefault('bpy_extras.io_utils', io_utils)
