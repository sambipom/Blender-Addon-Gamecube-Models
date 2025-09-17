import os
import pathlib
import tempfile
import importlib.util
import types
import sys


# Import file_io without executing shared.IO.__init__ (which pulls in bpy)
repo_root = pathlib.Path(__file__).resolve().parents[1]
shared_path = repo_root / "shared"
io_path = shared_path / "IO"

# Create package stubs for shared and shared.IO to satisfy relative imports
shared_pkg = types.ModuleType("shared")
shared_pkg.__path__ = [str(shared_path)]
sys.modules.setdefault("shared", shared_pkg)

io_pkg = types.ModuleType("shared.IO")
io_pkg.__path__ = [str(io_path)]
sys.modules.setdefault("shared.IO", io_pkg)

FILE_IO_PATH = io_path / "file_io.py"
spec = importlib.util.spec_from_file_location("shared.IO.file_io", FILE_IO_PATH)
file_io = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = file_io
spec.loader.exec_module(file_io)
BinaryReader = file_io.BinaryReader
BinaryWriter = file_io.BinaryWriter


def test_string_roundtrip():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        path = tmp.name
        tmp.close()

        writer = BinaryWriter(path)
        writer.write('string', 'hello')
        writer.close()

        with open(path, 'rb') as f:
            data = f.read()
        assert data == b'hello\x00'

        reader = BinaryReader(path)
        result = reader.read('string', 0)
        reader.close()
        assert result == 'hello'
    finally:
        os.remove(path)


if __name__ == "__main__":
    test_string_roundtrip()
    print("test_string_roundtrip passed")
