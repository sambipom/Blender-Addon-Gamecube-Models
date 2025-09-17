from collections import deque

from .NodeTypes import get_type_length, markUpFieldType
from ..Constants.PrimitiveTypes import is_primitive_type
from ..Constants.RecursiveTypes import (
    getArraySubType,
    getArrayTypeBound,
    getBracketedSubType,
    getPointerSubType,
    getSubType,
    isBoundedArrayType,
    isBracketedType,
    isPointerType,
    isUnboundedArrayType,
)


def _identity_matrix():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


# Abstract node class
class Node(object):
    # The name of this type of Node
    class_name = "Node"

    # A list of the field names and field types for each field in this array
    fields = []

    # Most nodes can be cached but some need to skip the caching logic
    # Such as some which are sub structs which don't represent their own individual node.
    # If they are the first field of the containing node then that address would already be cached
    # as the container but we'd still need to read the sub struct at that address.
    is_cachable = True

    # Determines if the node should be in the main data section of the model. The header and section
    # info nodes are outside of this but for nodes within it we can make sure they're being read
    # from within the expected range. Attempting to read one from outside the data section tells us
    # something went wrong.
    is_in_data_section = True

    # When initialised in fromBinary(), blender_obj should be None. It will be filled in when the tree
    # is parsed to import into blender.
    # When initialised in fromBlender(), address should be None. It will be filled in when the tree
    # is parsed to write to the output file.
    def __init__(self, address, blender_obj):
        # The offset where the node starts in the binary file.
        # When writing the file this offset won't be known until the node is written.
        # At that time, this can be updated so it's clear if it still needs to be written or not
        self.address = address
        # Reference to corresponding blender object, should only be set to persistent objects (e.g not edit bones).
        # When reading the file this won't have been created yet but it can be updated later.
        self.blender_obj = blender_obj
        # Prevent reference cycles when traversing tree
        self.is_being_printed = False
        self.is_being_listed = False
        self.is_prepared_for_build = False

        self._initialize_field_defaults()

    def _initialize_field_defaults(self):
        for field_info in getattr(self, 'fields', []):
            field_name, field_type = field_info[0], field_info[1]
            if hasattr(self, field_name):
                continue
            default_value = self._default_value_for_field(field_type)
            setattr(self, field_name, default_value)

    @classmethod
    def _default_value_for_field(cls, field_type):
        if not field_type:
            return None

        clean_type = field_type.replace(' ', '')

        if cls._type_has_array(clean_type):
            element_type = cls._array_element_type(clean_type)
            bound = cls._array_bound(clean_type)
            if bound is None:
                return []
            return [cls._default_value_for_field(element_type) for _ in range(bound)]

        canonical_type = markUpFieldType(field_type)
        unwrapped_type = cls._strip_brackets(canonical_type)

        if isPointerType(unwrapped_type):
            pointer_target = getPointerSubType(unwrapped_type)

            if cls._canonical_type_is_array(pointer_target):
                array_sub_type = getArraySubType(pointer_target)
                bound = getArrayTypeBound(pointer_target)
                if bound is None:
                    return []
                return [cls._default_value_for_field(array_sub_type) for _ in range(bound)]

            base_type = getSubType(pointer_target)
            if base_type == 'string':
                return ""
            if base_type == 'matrix':
                return _identity_matrix()
            return None

        if cls._canonical_type_is_array(unwrapped_type):
            array_sub_type = getArraySubType(unwrapped_type)
            bound = getArrayTypeBound(unwrapped_type)
            if bound is None:
                return []
            return [cls._default_value_for_field(array_sub_type) for _ in range(bound)]

        base_type = getSubType(unwrapped_type)

        if is_primitive_type(base_type):
            return cls._primitive_default(base_type)

        if cls._field_is_embedded(clean_type):
            return cls._instantiate_node_class(base_type)

        return None

    @staticmethod
    def _strip_brackets(field_type):
        stripped = field_type
        while isBracketedType(stripped):
            stripped = getBracketedSubType(stripped)
        return stripped

    @staticmethod
    def _type_has_array(type_string):
        return ('[' in type_string) and (']' in type_string)

    @staticmethod
    def _canonical_type_is_array(type_string):
        return isBoundedArrayType(type_string) or isUnboundedArrayType(type_string)

    @staticmethod
    def _array_bound(type_string):
        start = type_string.find('[')
        end = type_string.find(']', start + 1)
        if start == -1 or end == -1:
            return None
        bound_string = type_string[start + 1:end]
        if bound_string.isdigit():
            return int(bound_string)
        return None

    @staticmethod
    def _array_element_type(type_string):
        start = type_string.find('[')
        if start == -1:
            return type_string
        end = type_string.find(']', start + 1)
        if end == -1:
            end = len(type_string)
        return type_string[:start] + type_string[end + 1:]

    @staticmethod
    def _primitive_default(primitive_type):
        if primitive_type == 'string':
            return ""
        if primitive_type in {'float', 'double'}:
            return 0.0
        if primitive_type == 'vec3':
            return (0.0, 0.0, 0.0)
        if primitive_type == 'matrix':
            return _identity_matrix()
        if primitive_type == 'void':
            return None
        return 0

    @staticmethod
    def _field_is_embedded(type_string):
        return '@' in type_string

    @staticmethod
    def _instantiate_node_class(class_name):
        try:
            from ..ClassLookup import get_class_from_name
            class_reference = get_class_from_name(class_name)
        except Exception:
            class_reference = None

        if class_reference is None:
            return None

        try:
            return class_reference(None, None)
        except Exception:
            return None

    # Parse struct from binary file.
    # Use the parser to read the binary for the fields and then do any conversions or calculations
    # required to update those values or set extra meta data
    def loadFromBinary(self, parser):
        parser.parseNode(self)

    # Do any set up required to convert the node into a suitable representation in blender
    def prepareForBlender(self, builder):
        if self.is_prepared_for_build:
            return
        self.is_prepared_for_build = True

        for field_info in self.fields:
            field_name = field_info[0]
            field = getattr(self, field_name)
            if isinstance(field, Node):
                field.prepareForBlender(builder)
            elif isinstance(field, list) and len(field) > 0:
                first_sub_field = field[0]
                if isinstance(first_sub_field, Node):
                    for sub_field in field:
                        sub_field.prepareForBlender(builder)

    # For any fields which are a pointer where the underlying sub type is a primitive type (but not a string),
    # write them to the builder's output and replace the field with the address it was written to
    def writePrimitivePointers(self, builder):
        pass

    # For any fields which are a pointer to a string, write the string to the builder and replace
    # the property's value with the address it was written to
    def writeStringPointers(self, builder):
        pass

    # Tells the builder how many bytes to reserve for this node.
    def allocationSize(self):
        size = 0
        for field in self.fields:
            size += get_type_length(field)
        return size

    # Tells the builder how far into the reserved region the node itself should start.
    # Some nodes may need to output some data within that region so pointers to the node need to
    # be offset to the point in the allocated region where the node's own data starts.
    def allocationOffset(self):
        return 0

    # Tells the builder how to write this node's data to the binary file.
    # The node should have had its write address allocated by the builder by the time this is called.
    def writeBinary(self, builder):
        if self.address == None:
            return
        builder.writeNode(self, relative_to_header=True)

    # Official DAT files write nodes in breadth-first order. Generate a list of
    # all nodes in the tree using a breadth-first traversal so the write order
    # matches this convention.
    def toList(self):
        # Prevent infinite cycles
        if self.is_being_listed:
            return []

        self.is_being_listed = True

        node_list = []
        queue = deque([self])
        visited = set()

        while queue:
            node = queue.popleft()
            key = node.address if node.address is not None else id(node)
            if key in visited:
                continue
            visited.add(key)
            node_list.append(node)

            # Enqueue any child nodes. If a field is a list then enqueue each
            # node in that list.
            for field in node.fields:
                field_name = field[0]
                value = getattr(node, field_name)

                if isinstance(value, Node):
                    queue.append(value)

                elif isinstance(value, list):
                    for element in value:
                        if isinstance(element, Node):
                            queue.append(element)

                        elif isinstance(element, list):
                            # We should never have deeper than a 2-dimensional list
                            for sub_element in element:
                                if isinstance(sub_element, Node):
                                    queue.append(sub_element)

        self.is_being_listed = False

        return node_list

    # Get a simple representation of just this node
    def stringRepresentation(self):

        def fieldWeight(field):
            field_name = field[0]
            attr = getattr(self, field_name)
            if isinstance(attr, list):
                if len(attr) > 0:
                    if isinstance(attr[0], Node):
                        return 4
                return 2
            elif isinstance(attr, Node):
                return 3
            else:
                return 1

        def stringRep(value):
            if isinstance(value, Node) and value.is_cachable:
                return "-> " + value.class_name + " @" + hex(value.address) + " (" + str(value.length) + " bytes)"
            else:
                return str(value)

        text = stringRep(self).replace("-> ", "*") + "\n"

        sorted_fields = sorted(self.fields, key=fieldWeight)
        for (field_name, field_type) in sorted_fields:
            attr = getattr(self, field_name)

            if isinstance(attr, list):
                text += "  " + field_name.replace("_", " ") + ": \n"
                for index, sub_attr in enumerate(attr):
                    substring = stringRep(sub_attr)
                    sublines = substring.split("\n")
                    
                    field_name_prefix = "    " + str(index + 1) + " "
                    if field_type == 'matrix':
                        field_name_prefix = "    "
                    spacing = "    "

                    for i, line in enumerate(sublines):
                        if len(line) > 0:
                            if i == 0:
                                text += field_name_prefix
                            else:
                                text += spacing
                            text += line + "\n"
            else:
                substring = stringRep(attr)
                sublines = substring.split("\n")
                
                field_name_prefix = "  " + field_name.replace("_", " ") + ": "
                spacing = "    "

                for i, line in enumerate(sublines):
                    if len(line) > 0:
                        if i == 0:
                            text += field_name_prefix
                        else:
                            text += spacing
                        text += line + "\n"

        return text

    # Converts node tree to list format and print each node in order
    def printListRepresentation(self):
        for node in self.toList():
            print(node.stringRepresentation())

    # This recursively creates a textual representation of the tree starting at this node.
    def __str__(self):

        # Prevent infinite cycles
        if self.is_being_printed:
            return "-> " + self.class_name + " @" + hex(self.address) + " (already printed)\n"

        self.is_being_printed = True

        def fieldWeight(field):
            field_name = field[0]
            attr = getattr(self, field_name)
            if isinstance(attr, Node):
                return 3
            elif isinstance(attr, list):
                return 2
            else:
                return 1

        text = "-> " + self.class_name + " @" + hex(self.address) + " (" + str(self.length) + " bytes)\n"

        sorted_fields = sorted(self.fields, key=fieldWeight)
        for (field_name, field_type) in sorted_fields:
            attr = getattr(self, field_name)

            if isinstance(attr, list):
                text += "  " + field_name.replace("_", " ") + ": \n"
                for index, sub_attr in enumerate(attr):
                    substring = str(sub_attr)
                    sublines = substring.split("\n")
                    
                    field_name_prefix = "    " + str(index + 1) + " "
                    if field_type == 'matrix':
                        field_name_prefix = "    "
                    spacing = "    "

                    for i, line in enumerate(sublines):
                        if len(line) > 0:
                            if i == 0:
                                text += field_name_prefix
                            else:
                                text += spacing
                            text += line + "\n"
            else:
                substring = str(attr)
                sublines = substring.split("\n")
                
                field_name_prefix = "  " + field_name.replace("_", " ") + ": "
                spacing = "    "

                for i, line in enumerate(sublines):
                    if len(line) > 0:
                        if i == 0:
                            text += field_name_prefix
                        else:
                            text += spacing
                        text += line + "\n"

        self.is_being_printed = False

        return text










