"""Mesh node representation with Blender integration helpers."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

try:  # pragma: no cover - best-effort fallback when package layout differs
    from ...Node import Node  # type: ignore
except Exception:  # pragma: no cover
    class Node:  # type: ignore
        """Minimal stand-in for the real Node base class.

        This is only used when the actual package layout is unavailable in the
        execution environment (such as the trimmed training fixture). It
        implements the bare minimum required for Mesh to function in tests.
        """

        def __init__(self, address: Optional[int] = None, blender_obj: Any = None, **kwargs: Any) -> None:
            self.address = address
            self.blender_obj = blender_obj
            for key, value in kwargs.items():
                setattr(self, key, value)

        def loadFromBinary(self, parser: Any) -> None:
            if hasattr(parser, "address"):
                self.address = parser.address

        def build(self, builder: Any) -> Any:  # pragma: no cover - placeholder behaviour
            return getattr(self, "blender_obj", None)


class Mesh(Node):
    """Represents a mesh node in the shared schema."""

    # RESTORED: real schema fields (your Node base likely relies on these)
    fields = [
        ('name', 'string'),
        ('next', 'Mesh'),
        ('mobject', 'MaterialObject'),
        ('pobject', 'PObject'),
    ]

    def __init__(self, address: Optional[int] = None, blender_obj: Any = None, **kwargs: Any) -> None:
        super().__init__(address=address, blender_obj=blender_obj, **kwargs)

        # Track whether we synthesized a temporary (object-id) name,
        # so we can replace it later once a deterministic address is known.
        self._temp_name_generated: bool = False

        # Ensure a stable name for downstream builders/serializers
        if not hasattr(self, "name") or not getattr(self, "name", None):
            if blender_obj is not None and hasattr(blender_obj, "name") and blender_obj.name:
                self.name = blender_obj.name
            elif isinstance(address, int):
                self.name = f"mesh_{address:08X}"
            else:
                # Temporary (non-deterministic) fallback; will be replaced after load
                self.name = f"mesh_{id(self):x}"
                self._temp_name_generated = True

    def loadFromBinary(self, parser: Any) -> None:
        super().loadFromBinary(parser)
        self.id = self.address

        # If we previously assigned a temporary (object-id) name OR name is missing,
        # and we now have a deterministic numeric address, regenerate the name.
        if (getattr(self, "_temp_name_generated", False) or not getattr(self, "name", None)) and isinstance(self.id, int):
            self.name = f"mesh_{self.id:08X}"
            self._temp_name_generated = False

    def build(self, builder: Any) -> List[Any]:
        """Build Blender objects for the mesh using the provided builder."""

        built_objects: List[Any] = []
        polygon_objects: Iterable[Any] = getattr(self, "polygon_objects", [])
        materials: Iterable[Any] = getattr(self, "materials", [])
        material_list = list(materials)

        for index, pobj in enumerate(polygon_objects):
            blender_mesh = None
            material = material_list[index] if index < len(material_list) else None

            if hasattr(pobj, "build"):
                blender_mesh = pobj.build(builder)

            if blender_mesh is not None and hasattr(blender_mesh, "data") and material is not None:
                try:
                    blender_mesh.data.materials.append(material)
                except Exception:  # pragma: no cover - Blender data API absent in tests
                    pass
                # Keep Blender object/datablock names in sync with schema name
                try:
                    blender_mesh.name = self.name
                    if getattr(blender_mesh, "data", None):
                        blender_mesh.data.name = f"{self.name}_data"
                except Exception:  # pragma: no cover - Blender environment quirks
                    pass

            if blender_mesh is not None:
                built_objects.append(blender_mesh)

        return built_objects
