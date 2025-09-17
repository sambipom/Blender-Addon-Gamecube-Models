import importlib
import inspect
import pkgutil

import pytest

from shared.Nodes.Node import Node
import shared.Nodes.Classes as node_classes_module


def _iter_node_modules():
    yield node_classes_module

    package_path = getattr(node_classes_module, "__path__", None)
    if not package_path:
        return

    prefix = node_classes_module.__name__ + "."
    for _, module_name, _ in pkgutil.walk_packages(package_path, prefix):
        yield importlib.import_module(module_name)


def _gather_node_classes():
    discovered = {}

    for module in _iter_node_modules():
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, Node) and cls is not Node:
                discovered.setdefault(cls, cls)

    return tuple(sorted(discovered, key=lambda cls: (cls.__module__, cls.__name__)))


NODE_CLASSES = tuple(_gather_node_classes())
NODE_CLASS_NAMES = {cls.__name__ for cls in NODE_CLASSES}


ESSENTIAL_NODE_CLASS_NAMES = {
    "Mesh",
    "PObject",
    "Vertex",
    "VertexList",
    "Texture",
    "TextureAnimation",
    "TextureLOD",
    "TextureTEV",
    "Image",
    "Palette",
    "Material",
    "MaterialObject",
    "Render",
    "PixelEngine",
    "SceneData",
    "SectionInfo",
}


def test_expected_node_classes_present():
    missing = ESSENTIAL_NODE_CLASS_NAMES - NODE_CLASS_NAMES

    assert not missing, (
        "Node instantiation coverage is missing classes used by exporters: "
        + ", ".join(sorted(missing))
    )


def _expected_value(node_cls, field_type):
    return node_cls._default_value_for_field(field_type)


@pytest.mark.parametrize("node_cls", NODE_CLASSES, ids=lambda cls: cls.__name__)
def test_node_fields_have_default_values(node_cls):
    node = node_cls(None, None)

    for field in getattr(node_cls, "fields", []):
        if not field:
            continue

        field_name = field[0]
        field_type = field[1] if len(field) > 1 else None

        assert hasattr(node, field_name), f"{node_cls.__name__} missing attribute '{field_name}'"

        if not field_type:
            continue

        expected = _expected_value(node_cls, field_type)
        value = getattr(node, field_name)

        if isinstance(expected, Node):
            assert isinstance(value, expected.__class__), (
                f"{node_cls.__name__}.{field_name} expected instance of {expected.__class__.__name__}, "
                f"got {type(value).__name__}"
            )
        elif isinstance(expected, list):
            assert isinstance(value, list), (
                f"{node_cls.__name__}.{field_name} expected list default, got {type(value).__name__}"
            )
        elif isinstance(expected, tuple):
            assert isinstance(value, tuple), (
                f"{node_cls.__name__}.{field_name} expected tuple default, got {type(value).__name__}"
            )
        else:
            assert isinstance(value, type(expected)), (
                f"{node_cls.__name__}.{field_name} expected {type(expected).__name__} default, "
                f"got {type(value).__name__}"
            )
