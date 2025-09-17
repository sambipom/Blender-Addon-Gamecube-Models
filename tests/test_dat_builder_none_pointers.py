from pathlib import Path

from shared.IO.DAT_io import DATBuilder
from shared.Nodes.Classes.Material.MaterialObject import MaterialObject


def test_write_node_handles_none_children(tmp_path: Path) -> None:
    material = MaterialObject(0, None)

    output_path = tmp_path / "material.dat"
    builder = DATBuilder(str(output_path), [])

    try:
        builder.writeNode(material, relative_to_header=True)
    finally:
        builder.close()

    assert material.texture == 0
    assert material.material == 0
    assert material.render_data == 0
    assert material.pixel_engine_data == 0

    data = output_path.read_bytes()
    base_offset = DATBuilder.DAT_header_length
    pointer_offsets = [base_offset + 8, base_offset + 12, base_offset + 16, base_offset + 20]

    for offset in pointer_offsets:
        pointer_value = int.from_bytes(data[offset:offset + 4], byteorder="big")
        assert pointer_value == 0
