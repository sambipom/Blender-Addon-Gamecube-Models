from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Provide stub modules for Blender-specific imports used in package init.
# These stubs are intentionally lightweight – the tests only need the
# modules to exist so imports succeed. When running inside Blender these
# branches will be skipped and the real modules will be used instead.
if 'bpy' not in sys.modules:
    bpy_module = types.ModuleType('bpy')

    class _Menu:
        def append(self, *_args, **_kwargs):
            return None

        def remove(self, *_args, **_kwargs):
            return None

    bpy_module.types = types.SimpleNamespace(
        Operator=type('Operator', (), {}),
        OperatorFileListElement=type('OperatorFileListElement', (), {}),
        TOPBAR_MT_file_import=_Menu(),
        TOPBAR_MT_file_export=_Menu(),
    )
    bpy_module.props = types.SimpleNamespace(
        CollectionProperty=lambda *args, **kwargs: None,
        StringProperty=lambda *args, **kwargs: None,
        BoolProperty=lambda *args, **kwargs: None,
        IntProperty=lambda *args, **kwargs: None,
    )
    bpy_module.utils = types.SimpleNamespace(
        register_class=lambda *args, **kwargs: None,
        unregister_class=lambda *args, **kwargs: None,
    )

    sys.modules['bpy'] = bpy_module

bpy_extras = types.ModuleType('bpy_extras')
io_utils = types.ModuleType('io_utils')
io_utils.ImportHelper = object
io_utils.ExportHelper = object
io_utils.axis_conversion = lambda *args, **kwargs: None
bpy_extras.io_utils = io_utils
sys.modules.setdefault('bpy_extras', bpy_extras)
sys.modules.setdefault('bpy_extras.io_utils', io_utils)


# Minimal mathutils stub so modules that depend on Blender's math classes can
# be imported in the test environment.
if 'mathutils' not in sys.modules:
    mathutils = types.ModuleType('mathutils')

    class _Matrix:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def Translation(*args, **kwargs):
            return _Matrix()

        @staticmethod
        def Rotation(*args, **kwargs):
            return _Matrix()

        @staticmethod
        def Scale(*args, **kwargs):
            return _Matrix()

        def to_3x3(self):
            return self

        def to_4x4(self):
            return self

        def invert(self):
            return self

        def transpose(self):
            return self

        def inverted(self):
            return self

        def transposed(self):
            return self

        def identity(self):
            return self

        def __matmul__(self, other):
            return self

        def __rmatmul__(self, other):
            return self

        def __imatmul__(self, other):
            return self

        def __mul__(self, other):
            return self

        def __rmul__(self, other):
            return self

    class _Vector:
        def __init__(self, values=None):
            self.values = tuple(values) if values is not None else tuple()

        def normalized(self):
            return self

    class _Euler:
        def __init__(self, values=None):
            self.values = tuple(values) if values is not None else tuple()

    mathutils.Matrix = _Matrix
    mathutils.Vector = _Vector
    mathutils.Euler = _Euler
    sys.modules['mathutils'] = mathutils
