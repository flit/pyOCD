# pyOCD debugger
# Copyright (c) 2019 Arm Limited
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import struct
import copy
from collections import (namedtuple, OrderedDict)
import logging
from enum import (Enum, IntEnum)

from ..core import exceptions

LOG = logging.getLogger(__name__)

class InvalidTypeDefinition(exceptions.Error):
    """! @brief Could not parse a type definitions."""
    pass

SourceLocation = namedtuple("SourceLocation", ["filename", "dirname", "line"])

class DataType(object):
    """! @brief Abstract data type.
    
    Base class for the data type class hierarchy. All data types have a name, byte/bit size,
    and set of qualifier flags. The qualifiers are those from C/C++: const, volatile, and restrict.
    They are represented by the @ref pyocd.debug.types.DataType.Qualifiers "DataType.Qualifiers"
    class attributes. Optionally, a type may have a reference to the source file and line where it
    was defined.
    
    Type aliases, aka typedefs, can be created from a parent type with the make_typedef() method.
    It can change the new type's name and _add_ qualifiers. Qualifiers cannot be removed in a
    typedef.
    """
    class Qualifiers:
        """! @brief Type qualifier flags.
        
        These flags are intended to be OR'd together.
        """
        CONST = 0x01
        VOLATILE = 0x02
        RESTRICT = 0x04
    
    def __init__(self, name, byte_size=0, bit_size=0, bit_offset=0, loc=None, undefined=False):
        """! @brief Constructor."""
        self._name = name
        self._byte_size = byte_size
        self._bit_size = bit_size
        self._bit_offset = bit_offset
        self._parent = None
        self._qualifiers = 0
        self._is_undefined = undefined
        self._source_loc = loc
    
    @property
    def name(self):
        return self._name
    
    @property
    def byte_size(self):
        return self._byte_size
    
    @property
    def bit_size(self):
        return self._bit_size
    
    @property
    def bit_offset(self):
        return self._bit_offset
    
    @property
    def parent(self):
        return self._parent
    
    @property
    def qualifiers(self):
        return self._qualifiers
    
    @property
    def is_undefined(self):
        return self._is_undefined
    
    @property
    def is_const(self):
        return (self._qualifiers & self.Qualifiers.CONST) != 0
    
    @property
    def is_volatile(self):
        return (self._qualifiers & self.Qualifiers.VOLATILE) != 0
    
    @property
    def is_restrict(self):
        return (self._qualifiers & self.Qualifiers.RESTRICT) != 0
    
    @property
    def source_location(self):
        """! @brief Returns a @ref pyocd.debug.types.SourceLocation "SourceLocation" object."""
        return self._source_loc
    
    def make_typedef(self, new_name, add_qualifiers=None, loc=None):
        """! @brief Create a child type.
        
        Qualifiers can be added, but not removed. The returned type has its parent set to the
        invoked object.
        
        @param self
        @param new_name Name of the new type.
        @param add_qualifiers Integer that is bit-OR'd into the new type's qualifier flags. If not
            provided, the qualifiers remain unchanged from those of the receiving object.
        @param loc Optional source code location. If not provided, the location is set to None.
        @return New instance of the receiving object's class.
        """
        child = copy.copy(self)
        child._name = new_name
        child._parent = self
        child._source_loc = loc
        if add_qualifiers is not None:
            child._qualifiers |= add_qualifiers
        return child
    
    def decode(self, data):
        """! @brief Decode bytes into a Python representation of the data type."""
        raise NotImplementedException()
    
    def encode(self, value):
        """! @brief Convert a Python representation of the data type into bytes."""
        raise NotImplementedException()
    
    def _get_repr(self, extra=""):
        q = ""
        if self.is_const:
            q += "c"
        if self.is_volatile:
            q += "v"
        if self.is_restrict:
            q += "r"
        if q == "":
            q = "-"
        if extra:
            extra = " " + extra
        return "<{}@{:#10x} name={} Bsz={} q={}{}>".format(
            self.__class__.__name__, id(self), self.name, self.byte_size, q, extra)
    
    def __repr__(self):
        return self._get_repr()

class VoidType(DataType):
    """! @brief The void type in C."""
    def __init__(self):
        super(VoidType, self).__init__("void")

## Singleton for the 'void' type.
VOID_TYPE = VoidType()

class ScalarType(DataType):
    """! @brief Base scalar data type.
    
    A scalar type can be one of these:
    - boolean
    - float or double
    - signed byte (char), halfword, or word
    - unsigned byte (char), halfword, or word
    
    This is represented by the combination of the _form_, _is_signed_, and _byte_size_ properties.
    """
    
    class Form(Enum):
        """! @brief Class of scalar."""
        BOOL = 1
        INT = 2
        FLOAT = 3
    
    def __init__(self, name, fmt, byte_size, **kwargs):
        super(ScalarType, self).__init__(name, byte_size=byte_size, **kwargs)
        self._format = "<" + fmt # Force little-endian (for now, at least).
        if fmt == '?':
            self._form = self.Form.BOOL
        elif fmt.lower() in ('b', 'h', 'l', 'q'):
            self._form = self.Form.INT
        elif fmt in ('f', 'd'):
            self._form = self.Form.FLOAT
        else:
            raise InvalidTypeDefinition("unsupported scalar format '{}'".format(fmt))
        self._is_signed = fmt in ('b', 'h', 'l', 'q')
    
    @property
    def form(self):
        return self._form
    
    @property
    def is_signed(self):
        return self._is_signed
    
    def decode(self, data):
        value, = struct.unpack_from(self._format, data)
        return value
    
    def encode(self, value):
        return struct.pack(self._format, value)
    
    def __repr__(self):
        return self._get_repr("{}{}{}".format(
            ('s' if self.is_signed else 'u'),
            self.form.name,
            self.byte_size,
            ))

class PointerType(DataType):
    """! @brief Pointer to another type.
    
    We assume a pointer is always 32-bit (and little-endian). If we ever support v8-A/R
    or later, we'll have to correct this assumption.
    """
    
    def __init__(self, name, object_type, **kwargs):
        super(PointerType, self).__init__(name, byte_size=4, **kwargs)
        self._object_type = object_type
    
    @property
    def object_type(self):
        return self._object_type
    
    def decode(self, data):
        value, = struct.unpack_from("<L", data)
        return value
    
    def encode(self, value):
        return struct.pack("<L", value)
    
    def __repr__(self):
        return self._get_repr("obj={}".format(repr(self._object_type)))

class ArrayType(DataType):
    """! @brief Array of another type.
    
    An array may have a fixed number of elements or be unsized. Currently only one dimension
    is supported.
    
    If the array is unsized, it will have a _length_ property of None and a byte size of a single
    object of the underlying type.
    """

    def __init__(self, name, element_type, length, **kwargs):
        super(ArrayType, self).__init__(name, byte_size=element_type.byte_size * (length or 1), **kwargs)
        self._element_type = element_type
        self._length = length
    
    @property
    def length(self):
        """! @brief Number of elements, or None for an unsized array."""
        return self._length
    
    @property
    def element_type(self):
        return self._element_type
    
    def decode(self, data, count=None):
        value = []
        l = self._length or count or 1
        offset = 0
        for i in range(l):
            sz = self._element_type.byte_size
            value.append(self._element_type.decode(data[offset:offset + sz]))
            offset += sz
        return value
    
    def encode(self, value):
        l = self._length or len(value)
        assert len(value) == l, "array value is incorrect size"
        data = bytestring()
        for v in value:
           data += self._element_type.encode(v)
        return data
    
    def __repr__(self):
        return self._get_repr("n={} elem={}".format(self.length, repr(self._element_type)))

StructMember = namedtuple("StructMember", ["name", "offset", "type"])

class StructType(DataType):
    """! @brief Structure type containing named members."""
    
    def __init__(self, name, byte_size, **kwargs):
        super(StructType, self).__init__(name, byte_size=byte_size, **kwargs)
        self._members = OrderedDict()
        self._members_by_offset = OrderedDict()
    
    @property
    def members(self):
        """! @brief OrderedDict of the struct member types with member names as keys."""
        return self._members
    
    @property
    def members_by_offset(self):
        """! @brief OrderedDict of the struct member types with member offsets as keys."""
        return self._members_by_offset
    
    def add_member(self, name, offset, member_type):
        """! @brief Add a new member to the struct.
        
        Members must be added in offset order, and retain the order with which they were added.
        """
        member = StructMember(name, offset, member_type)
        self._members[name] = member
        self._members_by_offset[offset] = member
    
    def decode(self, data):
        """! @brief Decode a struct instance by bytes.
        
        Returns an OrderedDict containing key/value pairs of member names and values, in their
        declaration (and offset) order.
        """
        result = OrderedDict()
        offset = 0
        for member in self.members_by_offset.values():
            sz = member.type.byte_size
            result[member.name] = member.type.decode(data[offset:offset + sz])
            offset += sz
        return result
    
    def encode(self, value):
        """! @brief Encode a struct instance as bytes.
        
        The _value_ parameter must be either a tuple, list, or dict. If it's a dict, then the
        struct member values are accessed by member name. For tuples or lists, the member values
        must be in offset order. Note that it is not possible to use a dict for a struct that has
        anonymous members.
        """
        data = bytestring()
        if isinstance(value, (tuple, list)):
            for i, member in enumerate(self.members_by_offset.values()):
               data += member.type.encode(value[i])
        else:
            for member in self.members_by_offset.values():
               data += member.type.encode(value[member.name])
        return data
    
    def __repr__(self):
        members_info = ""
        for _, info in self.members.items():
            members_info += "{}@{:#x}: {}\n".format(info.name, info.offset, repr(info.type))
        return self._get_repr("members=[" + members_info + "]")

class UnionType(StructType):
    """! @brief Union type containing named members.
    
    Unlike the other types (except VoidType), unions cannot be encoded or decoded because there
    is no (easy) way to know which member is active at any one point in time.
    """
    
    def __init__(self, name, byte_size, **kwargs):
        super(UnionType, self).__init__(name, byte_size=byte_size, **kwargs)
    
    def add_member(self, name, member_type):
        """! @brief Add a new member to the union."""
        member = StructMember(name, 0, member_type)
        self._members[name] = member
    
    def decode(self, data):
        """! @brief Decoding a union is not supported."""
        raise NotImplementedException()
    
    def encode(self, value):
        """! @brief Encoding a union is not supported."""
        raise NotImplementedException()
    
    def __repr__(self):
        members_info = ""
        for _, info in self.members.items():
            members_info += "{}: {}\n".format(info.name, repr(info.type))
        return self._get_repr("members=[" + members_info + "]")
    
EnumMember = namedtuple("EnumMember", ["name", "value"])
    
class EnumerationType(DataType):
    """! @brief Enumeration type."""

    def __init__(self, name, byte_size, enum_type, **kwargs):
        super(EnumerationType, self).__init__(name, byte_size=byte_size, **kwargs)
        self._enum_type = enum_type
        self._enumerators = OrderedDict()
        self._enumerators_by_value = OrderedDict()
    
    @property
    def enum_type(self):
        """! @brief The type used to hold an enumerator."""
        return self._enum_type
    
    @property
    def enumerators(self):
        """! @brief OrderedDict of the enumerators, with enumerator names for the keys."""
        return self._enumerators
    
    @property
    def enumerators_by_value(self):
        """! @brief OrderedDict of the enumerators, with enumerator values for the keys."""
        return self._enumerators_by_value
    
    def add_enumerator(self, name, value):
        """! @brief Add a new enumerator to the enum.
        
        Enumerators retain their declaration order.
        """
        member = EnumMember(name, value)
        self._enumerators[name] = member
        self._enumerators_by_value[value] = member
    
    def decode(self, data):
        return self.enum_type.decode(data)
    
    def encode(self, value):
        return self.enum_type.encode(value)
    
    def __repr__(self):
        members_info = ""
        for _, info in self.enumerators.items():
            members_info += "{}={}, ".format(info.name, info.value)
        return self._get_repr("type=" + repr(self.enum_type) + " members=[" + members_info + "]")

FormalParameter = namedtuple("FormalParameter", ["name", "type", "is_artificial"])
    
class FunctionType(DataType):
    """! @brief Function or method type."""

    def __init__(self, name, return_type, **kwargs):
        super(FunctionType, self).__init__(name, **kwargs)
        self._return_type = return_type
        self._parameters = []

    @property
    def return_type(self):
        return self._return_type
    
    @property
    def parameters(self):
        return self._parameters
    
    def add_parameter(self, name, type, is_artificial=False):
        self._parameters.append(FormalParameter(name, type, is_artificial))
    
    def __repr__(self):
        params_info = ""
        for _, info in self.parameters.items():
            params_info += "{}={}, ".format(info.name, info.type)
        return self._get_repr("return=" + repr(self.return_type) + " params=[" + params_info + "]")

class Variable(object):
    """! @brief Information about a program variable."""
    
    def __init__(self, name, data_type, addr, loc=None):
        self._name = name
        self._type = data_type
        self._addr = addr
        self._source_loc = loc
    
    @property
    def name(self):
        return self._name
    
    @property
    def data_type(self):
        return self._type
    
    @property
    def addr(self):
        return self._addr
    
    @property
    def source_location(self):
        """! @brief Returns a @ref pyocd.debug.types.SourceLocation "SourceLocation" object."""
        return self._source_loc
    
    def __repr__(self):
        return "<{}@{:#10x} name={} typename={} addr={}>".format(
            self.__class__.__name__, id(self), self.name, self.data_type.name, self.addr)
    


