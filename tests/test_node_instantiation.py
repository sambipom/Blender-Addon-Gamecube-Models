"""Validation tests for node class definitions.

These tests ensure that every node class can be instantiated with the
arguments used by the binary parser and that each field definition points to a
known primitive type or another registered node class. This guards against
regressions where refactors leave a class with mismatched constructor
signatures or dangling type names in the ``fields`` metadata used by the
parser.
"""

from shared.ClassLookup.get_class_from_name import get_class_from_name
from shared.Constants.PrimitiveTypes import is_primitive_type
from shared.Constants.RecursiveTypes import getSubType
from shared.Nodes import Node
from shared.Nodes.NodeTypes import markUpFieldType


def _iter_node_classes():
    """Yield every concrete subclass of :class:`Node`."""

    seen = set()
    stack = list(Node.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        yield cls
        stack.extend(cls.__subclasses__())


def test_node_classes_have_valid_field_definitions():
    """All node classes should instantiate and reference known field types."""

    for cls in _iter_node_classes():
        instance = cls(0, None)

        assert hasattr(instance, "fields"), f"{cls.__name__} missing fields attribute"
        assert isinstance(instance.fields, list), (
            f"{cls.__name__}.fields should be a list, got {type(instance.fields)!r}"
        )

        for field in instance.fields:
            assert isinstance(field, tuple) and len(field) == 2, (
                f"{cls.__name__}.fields entries must be (name, type) tuples"
            )
            field_name, field_type = field
            assert isinstance(field_name, str) and field_name, (
                f"{cls.__name__} has invalid field name {field_name!r}"
            )
            assert isinstance(field_type, str) and field_type, (
                f"{cls.__name__}.{field_name} must declare a type"
            )

            subtype = getSubType(markUpFieldType(field_type))
            if is_primitive_type(subtype):
                continue

            resolved = get_class_from_name(subtype)
            assert (
                resolved is not None
            ), f"{cls.__name__}.{field_name} references unknown node type {subtype!r}"
