# pyOCD debugger
# Copyright (c) 2021-2022 Chris Reed
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

from __future__ import annotations

import collections.abc
import threading
from contextlib import contextmanager
from functools import total_ordering
from types import MethodType
from typing import (Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Type, Union, TYPE_CHECKING, overload)
from typing_extensions import Self

from ..core.memory_interface import MemoryInterface
from .mask import (bitmask, bit_invert)

if TYPE_CHECKING:
    pass

class Constant(int):
    """@brief Used to define bitfield value constants in a register definition."""
    pass

@total_ordering
class Bitfield:
    """@brief Bitfield descriptor.

    Represents one bitfield of a register. Primarily intended to be used as a descriptor for bitfields
    within a RegisterDescription subclass. It can also be used on its own for simple uses.

    Bitfields support binary AND, OR, and XOR operations with ints and other Bitfields. The result
    is an int, and a Bitfield object's value in the expression is its `.mask` property.

    Left and right shifts of an int accept a Bitfield on the right-hand side, in which case the
    shift amount is the Bitfield's `.shift` property. This can be used to shift a value into the bitfield's
    position. Other shifts are not supported, as they don't have a practical use. (R-shift a bitfield by a
    bitfield??)

    The binary NOT, aka invert, operation is supported, and returns the inverted `.mask` property as an int.
    The inverted value is
    """
    __slots__ = ('_msb', '_lsb', '_name', '_register_width', '_mask')

    def __init__(
                self,
                msb: int,
                lsb: Optional[int] = None,
                name: Optional[str] = None,
                register_width: int = 32
            ) -> None:
        """@brief Constructor.
        @param self
        @param msb Most significant bit.
        @param lsb Least significant bit.
        @param name Optional name for the bitfield.
        @param register_width Width in bits of the containing register. Defaults to 32 if not specified.
        """
        assert msb >= (lsb or msb)
        assert msb < register_width
        self._msb = msb
        self._lsb = lsb if (lsb is not None) else msb
        self._name = name or "(unnamed)"
        self._register_width = register_width
        self._mask = bitmask((self._msb, self._lsb))

    @property
    def width(self) -> int:
        """@brief Width of the bitfield."""
        return self._msb - self._lsb + 1

    @property
    def mask(self) -> int:
        """@brief Pre-shifted mask of the bitfield."""
        return self._mask

    @property
    def shift(self) -> int:
        """@brief Value of the least-significant bit of the bitfield."""
        return self._lsb

    @property
    def lsb(self) -> int:
        """@brief Lowest bit position of the bitfield, same as `.shift`."""
        return self._lsb

    @property
    def msb(self) -> int:
        """@brief Highest bit position of the bitfield."""
        return self._msb

    @property
    def name(self) -> str:
        """@brief The bitfield's name."""
        return self._name

    def __index__(self) -> int:
        """@brief Get the bitfield's mask."""
        return self.mask

    def __and__(self, other):
        """@brief Binary AND operator."""
        if isinstance(other, int):
            return self.mask & other
        elif isinstance(other, Bitfield):
            return self.mask & other.mask
        else:
            return NotImplemented

    def __or__(self, other):
        """@brief Binary OR operator."""
        if isinstance(other, int):
            return self.mask | other
        elif isinstance(other, Bitfield):
            return self.mask | other.mask
        else:
            return NotImplemented

    def __xor__(self, other):
        """@brief Binary XOR operator."""
        if isinstance(other, int):
            return self.mask ^ other
        elif isinstance(other, Bitfield):
            return self.mask ^ other.mask
        else:
            return NotImplemented

    def __rand__(self, other):
        """@brief Right-handed binary AND operator."""
        if isinstance(other, int):
            return self.mask & other
        elif isinstance(other, Bitfield):
            return self.mask & other.mask
        else:
            return NotImplemented

    def __ror__(self, other):
        """@brief Right-handed binary OR operator."""
        if isinstance(other, int):
            return self.mask | other
        elif isinstance(other, Bitfield):
            return self.mask | other.mask
        else:
            return NotImplemented

    def __rxor__(self, other):
        """@brief Right-handed binary XOR operator."""
        if isinstance(other, int):
            return self.mask ^ other
        elif isinstance(other, Bitfield):
            return self.mask ^ other.mask
        else:
            return NotImplemented

    def __invert__(self) -> int:
        """@brief Binary NOT operator."""
        return bit_invert(self.mask, self._register_width)

    def __rlshift__(self, other):
        """@brief Right-handed left-shift operator."""
        if isinstance(other, int):
            return other << self.shift
        else:
            return NotImplemented

    def __rrshift__(self, other):
        """@brief Right-handed right-shift operator."""
        if isinstance(other, int):
            return other >> self.shift
        else:
            return NotImplemented

    def __eq__(self, o: object) -> bool:
        """@brief Equality operator."""
        return isinstance(o, Bitfield) and (self.mask == o.mask) and (self.width == o.width)

    def __gt__(self, o: object) -> bool:
        """@brief Greater-than operator."""
        return isinstance(o, Bitfield) and (self._lsb > o._lsb)

    def get(self, register_value: int) -> int:
        """@brief Extract the bitfield value from a register value.
        @param self The Bitfield object.
        @param register_value Integer register value.
        @return Integer value of the bitfield extracted from `value`.
        """
        return (register_value & self._mask) >> self._lsb

    def set(self, field_value: int, register_value: int) -> int:
        """@brief Modified the bitfield in a register value.
        @param self The Bitfield object.
        @param field_value New value for the bitfield. Must _not_ be shifted into place already.
        @param register_value Integer register value.
        @return Integer register value with the bitfield updated to `field_value`.
        """
        return (register_value & ~self) | ((field_value << self._lsb) & self._mask)

    def __get__(self, obj: Optional[object], objtype: Optional[type] = None) -> Union[Self, int]:
        """@brief Descriptor get operation."""
        # When called on the class, return ourself.
        if obj is None:
            return self
        else:
            return self.get(obj.value) # type:ignore

    def __set__(self, obj: object, value: Any) -> None:
        """@brief Descriptor set operation."""
        if obj is None:
            raise AttributeError("cannot set bitfields of a register class")
        obj._value = self.set(int(value), obj._value) # type:ignore

    def __class_getitem__(cls, key: slice) -> slice:
        """@brief Simply returns the passed in slice for use by _RegisterDefinitionMeta."""
        return key

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._name} {self._msb}:{self._lsb}>"


class MultiBitfield(Bitfield):
    """@brief Bitfield with more than one discontiguous bit range.

    Most of the same operations as a simple Bitfield are supported, but some do not make sense.
    """
    __slots__ = ('_fields', '_width')

    def __init__(
                self,
                fields: Iterable[Bitfield],
                name: Optional[str] = None,
                register_width: int = 32
            ) -> None:
        """@brief Constructor.
        @param self
        @param fields Iterable of Bitfield objects.
        @param name Optional name for the bitfield.
        @param register_width Width in bits of the containing register. Defaults to 32 if not specified.
        """
        self._fields = tuple(sorted(fields, key=lambda f: f.lsb))
        if len(self._fields) < 2:
            raise ValueError("MultiBitfield must have at least two sub-bitfields")

        super().__init__(
            msb=self._fields[-1].msb,
            lsb=self._fields[0].lsb,
            name=name,
            register_width=register_width
            )

        self._width = sum(f.width for f in self._fields)
        self._mask = sum(f.mask for f in self._fields)

    @property
    def width(self) -> int:
        """@brief Width of the merged field when extracted from a register."""
        return self._width

    @property
    def ranges(self) -> Tuple[Bitfield]:
        """@brief Tuple of discontiguous Bitfield objects comprising the multi-bitfield."""
        return self._fields

    def __and__(self, other):
        """@brief Binary AND operator."""
        if isinstance(other, int):
            return self.mask & other
        elif isinstance(other, Bitfield):
            return self.mask & other.mask
        else:
            return NotImplemented

    def __or__(self, other):
        """@brief Binary OR operator."""
        if isinstance(other, int):
            return self.mask | other
        elif isinstance(other, Bitfield):
            return self.mask | other.mask
        else:
            return NotImplemented

    def __xor__(self, other):
        """@brief Binary XOR operator."""
        if isinstance(other, int):
            return self.mask ^ other
        elif isinstance(other, Bitfield):
            return self.mask ^ other.mask
        else:
            return NotImplemented

    def __rand__(self, other):
        """@brief Right-handed binary AND operator."""
        if isinstance(other, int):
            return self.mask & other
        elif isinstance(other, Bitfield):
            return self.mask & other.mask
        else:
            return NotImplemented

    def __ror__(self, other):
        """@brief Right-handed binary OR operator."""
        if isinstance(other, int):
            return self.mask | other
        elif isinstance(other, Bitfield):
            return self.mask | other.mask
        else:
            return NotImplemented

    def __rxor__(self, other):
        """@brief Right-handed binary XOR operator."""
        if isinstance(other, int):
            return self.mask ^ other
        elif isinstance(other, Bitfield):
            return self.mask ^ other.mask
        else:
            return NotImplemented

    def __invert__(self) -> int:
        """@brief Binary NOT operator."""
        return bit_invert(self.mask, self._register_width)

    def __rlshift__(self, other):
        """@brief Right-handed left-shift operator."""
        return NotImplemented

    def __rrshift__(self, other):
        """@brief Right-handed right-shift operator."""
        return NotImplemented

    def __eq__(self, o: object) -> bool:
        """@brief Equality operator."""
        return isinstance(o, MultiBitfield) and (self.mask == o.mask) and (self.width == o.width)

    def __gt__(self, o: object) -> bool:
        """@brief Greater-than operator."""
        return isinstance(o, Bitfield) and (self._lsb > o._lsb)

    def get(self, register_value: int) -> int:
        """@brief Extract the multi-bitfield value from a register value.
        @param self
        @param register_value Integer register value.
        @return Integer value of the bitfield extracted from `value`.
        """
        result = 0
        offset = 0
        for field in self._fields:
            result |= field.get(register_value) << offset
            offset += field.width
        return result

    def set(self, field_value: int, register_value: int) -> int:
        """@brief Modified the multi-bitfield in a register value.
        @param self
        @param field_value New value for the bitfield. Must _not_ be shifted into place already.
        @param register_value Integer register value.
        @return Integer register value with the bitfield updated to `field_value`.
        """
        result = register_value
        for field in self._fields:
            result = field.set(field_value, register_value)
            field_value >>= field.width
        return result

    def __repr__(self) -> str:
        bits = ",".join(f"{f.msb}:{f.lsb}" for f in self._fields)
        return f"<{type(self).__name__} {self._name} {bits}>"


class _ClassAndInstanceMethod:
    """@brief Descriptor for having separate class and instance method implementations."""

    def __init__(self, c: Callable, i: Callable) -> None:
        self._classmethod = c
        self._instancemethod = i

    def __set_name__(self, owner: object, name: str) -> None:
        pass

    def __get__(self, obj: Optional[object], objtype: Optional[type] = None) -> MethodType:
        # Class
        if obj is None:
            return MethodType(self._classmethod, objtype)
        else:
            return MethodType(self._instancemethod, obj)


class _RegisterDefinitionMeta(type):
    """@brief Metaclass for register definitions.

    The role of this metaclass is to convert bitfield declarations in the class definition to Bitfield
    descriptor instances.
    """
    def __new__(
                mcs: Type, # type:ignore
                name: str,
                bases: Tuple[type, ...],
                objdict: Dict[str, Any],
                **kwds: Any
            ) -> _RegisterDefinitionMeta:
        # print(f"RegisterDefinitionMeta.__new__(mcs={mcs}, name={name}, bases={bases}, objdict={objdict}, kwds={kwds})")

        # Don't process the RegisterDefinition class that is used as the actual base of register definitions.
        if name == 'RegisterDefinition':
            return super().__new__(mcs, name, bases, objdict, **kwds)

        if 'address' in kwds and 'offset' in kwds:
            raise TypeError("register definitions must not have both address and offset parameters")

        classdict: Dict[str, Any] = {}
        classdict['_address'] = kwds.get('address', None)
        classdict['_offset'] = kwds.get('offset', None)
        classdict['_name'] = name

        width = kwds.get('width', 32)
        assert width in {8, 16, 32, 64}
        classdict['_width'] = width

        classdict['_elements'] = kwds.get('elements', 1)
        classdict['_stride'] = kwds.get('stride', width // 8)

        fields: List[Bitfield] = []
        classdict['_fields'] = fields

        # Create bitfield descriptors.
        for k, v in objdict.items():
            # Copy special attributes.
            if k.startswith('__'):
                classdict[k] = v
                continue
            # Handle constant definitions. This check must come before bitfields.
            elif isinstance(v, Constant):
                # Turn into a plain int.
                classdict[k] = int(v)
                continue
            # Single slice object.
            elif isinstance(v, slice):
                # start and stop are reverse of normal python usage to look like verilog
                msb, lsb = v.start, v.stop
            # Single-bit bitfield.
            elif isinstance(v, int):
                msb = lsb = v
            # Multi-bit bitfield.
            elif isinstance(v, collections.abc.Sequence):
                # If the sequence contains all slices, then create a regular bitfield for a single slice,
                # but create a multi-bitfield for multiple slices.
                if all(isinstance(e, slice) for e in v):
                    if len(v) == 1:
                        msb, lsb = v[0].start, v[0].stop
                    else:
                        bf = MultiBitfield(
                            fields=(
                                # start and stop are reverse of normal python usage to look like verilog
                                Bitfield(msb=s.start, lsb=s.stop, name=k, register_width=width)
                                for s in v
                            ),
                            name=k,
                            register_width=width,
                        )
                        fields.append(bf)
                        classdict[k] = bf
                        continue
                elif not all(isinstance(e, int) for e in v):# or all(isinstance(e, int) for e in v)):
                    raise TypeError(f"invalid bitfield definition '{v}'; sequence elements must be all "
                                     "int or all Bitfield slices")

                if len(v) == 1:
                    msb = lsb = v[0]
                elif len(v) == 2:
                    msb, lsb = v
                else:
                    raise TypeError(f"invalid bitfield definition '{v}'; sequence must be 1 or 2 elements")
            # Copy any other attributes
            else:
                classdict[k] = v
                continue

            # Define the bitfield descriptor.
            bf = Bitfield(msb, lsb, name=k, register_width=width)
            fields.append(bf)
            classdict[k] = bf

        fields.sort()

        # Build the reserved bits mask.
        reserved_mask = bit_invert(sum(f.mask for f in fields), width)
        classdict['_reserved_mask'] = reserved_mask

        # print(f"    new {classdict=}")

        # Create the new type.
        new_type = type.__new__(mcs, name, bases, classdict)
        # print(f"    new_type={new_type}")

        return new_type


# TODO: if obj in the __get__() and __set__() methods is a CoreSightComponent, then we could
#   automatically pick up the memif to use.
class _RegisterTargetProxy:
    """@brief"""
    __slots__ = ('_register', '_memif', '_base')

    def __init__(self, register: Type[RegisterDefinition], memif: MemoryInterface, base: Optional[int] = None) -> None:
        self._register = register
        self._memif = memif
        self._base = base

    def __get__(self, obj: Optional[object], objtype: Optional[type] = None) -> Union[Self, "RegisterDefinition"]:
        """@brief Descriptor get operation."""
        print(f"proxy get called for {self._register.name}; {obj=}")
        # When called on the class, return ourself.
        if obj is None:
            return self
        else:
            return self._register.read(self._memif, base=self._base)

    def __set__(self, obj: object, value: Any) -> None:
        """@brief Descriptor set operation."""
        print(f"proxy get called for {self._register.name}; {obj=} {value=}")
        if obj is None:
            raise AttributeError("cannot set bitfields of a register class")
        self._register.write(self._memif, value, base=self._base)


class RegisterDefinition(metaclass=_RegisterDefinitionMeta):
    """@brief Superclass for register definitions.

    Bitfields of the register are declared as class attributes whose value indicates the bit position
    or range. Values can be either a single int to declare a single-bit field, or a bi-tuple (or list)
    containing the MSB and LSB, respectively, of the bitfield.

    The bitfields listed in the class definition are converted to Bitfield instances.

    Several class definition parameters are accepted:
    - _address_: Sets the register's address. Register definitions do not require an address. If not
        specified, the read() and write() methods will have to be provided with the address.
    - _offset_: An alternative to _address_ is to set the offset from some base address. The base isn't
        set in the register definition; it is passed in to the read() and write() methods, or the final
        address can be computed by the caller.
    - _width_: Width of the register in bits. Defaults to 32 if not specified.

    Passing both _address_ and _offset_ is disallowed.

    Simple example of the Arm M-profile DCRSR register definition with two bitfields:

    ```py
    class DCRSR(RegisterDefinition, address=0xE000EDF4):
        REGSEL = (7, 0)
        REGWnR = 16
    ```

    ### Usage

    Bitfield access on the register definition:

    ```py
    >>> DCRSR.REGSEL.msb
    7
    >>> DCRSR.REGSEL.mask
    255
    >>> DCRSR.REGWnR.shift
    16
    >>> hex(DCRSR.REGSEL | DCRSR.REGWnR)
    '0x100ff'
    >>> 1 << DCRSR.REGWnR
    16
    ```

    Read and write bitfields from register instances:

    ```py
    >>> r = DCRSR(0x10003)
    >>> r.REGSEL
    3
    >>> r.REGWnR
    1
    >>> r.REGSEL = 14
    >>> hex(r.value)
    '0x1000e'
    ```

    Read and write the register instance to/from memory:

    ```py
    >>> DCRSR.read(target)
    <DHRSR @e000edf4 =0001000a>
    >>> r.write(target)
    ```

    Register definition with offset instead of fixed address. The offset is added to the address
    passed into the `.read()` or `.write()` methods.

    ```py
    >>> class CTRL(RegisterDefinition, offset=0x10): pass
    >>> CTRL.read(target, address=0x40013000)
    ```
    """
    __slots__ = ('_value', '_base')

    # @overload
    # def __new__(cls, value: "MemoryInterface", base: Optional[int] = None) -> _RegisterTargetProxy:
    #     ...

    # @overload
    # def __new__(cls, value: int) -> "_RegisterTargetProxy":
    #     ...

    # def __new__(cls, value, base=None):
    #     """@brief Constructs a register instance with a value."""
    #     if isinstance(value, MemoryInterface):
    #         print(f"creating target proxy for {cls.name}")
    #         proxy = _RegisterTargetProxy.__new__(_RegisterTargetProxy)
    #         proxy.__init__(cls, value, base)
    #         print(f"{proxy=}")
    #         return proxy
    #     else:
    #         # Construct value instance of this register. __init__() will automatically be called
    #         # after returning an instance of cls.
    #         return super().__new__(cls)

    def __init__(self, value: Optional[int], base: Optional[int] = None):
        """@brief Constructs a register instance with a value.

        @note Current the _base_ argument is ignored.
        """
        self._value = value
        self._base = base

    @classmethod
    @property
    def name(cls) -> str:
        """@brief Name of the register."""
        return cls._name # type:ignore

    @classmethod
    @property
    def fields(cls) -> List[Bitfield]:
        """@brief List of the register fields sorted by LSB."""
        return cls._fields # type:ignore

    @classmethod
    @property
    def reserved_mask(cls) -> int:
        """@brief Mask with 1s for all the undefined, reserved bits in the register."""
        return cls._reserved_mask # type:ignore

    @classmethod
    @property
    def address(cls) -> Optional[int]:
        """@brief The register's address, if supplied with one at class definition time."""
        return cls._address # type:ignore

    @classmethod
    @property
    def offset(cls) -> Optional[int]:
        """@brief The register's offset from a base address, if supplied with one at class definition time."""
        return cls._offset # type:ignore

    @classmethod
    @property
    def width(cls) -> int:
        """@brief Width of the register in bits."""
        return cls._width # type:ignore

    @classmethod
    @property
    def elements(cls) -> int:
        """@brief Number of array elements."""
        return cls._elements # type:ignore

    @classmethod
    @property
    def stride(cls) -> int:
        """@brief Offset in bytes between array elements."""
        return cls._stride # type:ignore

    @property
    def value(self) -> int:
        """@brief Get the register instance's value."""
        return self._value

    @value.setter
    def value(self, new_value: int) -> None:
        """@brief Set the register instance's value."""
        self._value = new_value

    def __index__(self) -> int:
        """@brief Convert a register instance to int."""
        return self._value

    # TODO: handle _base instance attribute
    @classmethod
    def _get_target_address(
                cls,
                address: Optional[int] = None,
                base: Optional[int] = None,
                index: Optional[int] = None,
            ) -> int:
        """@brief Return the actual address of the register, given various optional parameters.

        @exception IndexError The _index_ argument is out of range.
        @exception ValueError Missing a value required to determine the register address.
        """
        # Compute offset if the register is accessed as an array.
        if index is not None:
            if index < 0 or index >= cls.elements:
                raise IndexError(
                        f"index {index} out of range for register {cls.name} ({cls.elements} elements)")
            element_offset = cls.stride * index
        else:
            element_offset = 0

        # Get final address, taking into account explicit address, offset + base, and array offset.
        if address is not None:
            return address + element_offset
        elif base is not None:
            if cls.offset is not None:
                return base + cls.offset + element_offset
            else:
                raise ValueError(f"register {cls.name} cannot be used with a base address because it "
                                 "does not have a specified offset")
        elif cls.address is not None:
            return cls.address + element_offset
        elif cls.offset is not None:
            raise ValueError(f"base address of register {cls.name} must be specified to read or write")
        else:
            raise ValueError(f"address of register {cls.name} must be specified to read or write")

    @classmethod
    def read(
                cls,
                memif: MemoryInterface,
                address: Optional[int] = None,
                base: Optional[int] = None,
                index: Optional[int] = None,
            ) -> Self:
        """@brief Create a new register instance by reading the value from a target memory interface.

        @param self
        @param memif `MemoryInterface` used to read the register.
        @param address Address (int) of the register. If specified, this takes precedence over other
            parameters and over an address passed into the class definition.
        @param base Base address (int) of the register's peripheral/component. If specified, this is added
            to the _offset_ passed into the class definition. If no _offset_ was specified, then a
            `TypeError` is raised. Ignored if _address_ is passed.
        @param index Base-0 register array element index (int). The read address is adjusted based on this
            value multiplied by the array element _stride_ passed into the class definition (which defaults
            to the register width in bytes if not provided). An index of 0 is always valid. Otherwise, if
            the index is negative or greater than the specified number of elements (also passed into the
            class definition) then an `IndexError` is raised.

        @return New instance of the register with the value read from _memif_.
        """
        addr = cls._get_target_address(address, base, index)
        return cls(memif.read_memory(addr, transfer_size=cls.width))

    def _class_write(
                cls, # type:ignore # pyright doesn't like this since the method doesn't have @classmethod
                memif: MemoryInterface,
                value: int,
                address: Optional[int] = None,
                base: Optional[int] = None,
                index: Optional[int] = None,
            ) -> None:
        """@brief Write a register value to a target.

        @param self
        @param memif `MemoryInterface` used to write the register.
        @param value Integer value to write to the register.
        @param address Address (int) of the register. If specified, this takes precedence over other
            parameters and over an address passed into the class definition.
        @param base Base address (int) of the register's peripheral/component. If specified, this is added
            to the _offset_ passed into the class definition. If no _offset_ was specified, then a
            `TypeError` is raised. Ignored if _address_ is passed.
        @param index Base-0 register array element index (int). The write address is adjusted based on this
            value multiplied by the array element _stride_ passed into the class definition (which defaults
            to the register width in bytes if not provided). An index of 0 is always valid. Otherwise, if
            the index is negative or greater than the specified number of elements (also passed into the
            class definition) then an `IndexError` is raised.
        """
        addr = cls._get_target_address(address, base, index)
        memif.write_memory(addr, value, transfer_size=cls.width)

    def _instance_write(
                self,
                memif: MemoryInterface,
                value: Optional[int] = None,
                address: Optional[int] = None,
                base: Optional[int] = None,
                index: Optional[int] = None,
            ) -> None:
        """@brief Write the register instance's value to a target.

        @param self
        @param memif `MemoryInterface` used to write the register.
        @param value Optional new int value for the register. If provided, the register instance's value is
            first updated, then the register is written to the new value through _memif_. If not provided,
            the register is written to it's current value.
        @param address Address (int) of the register. If specified, this takes precedence over other
            parameters and over an address passed into the class definition.
        @param base Base address (int) of the register's peripheral/component. If specified, this is added
            to the _offset_ passed into the class definition. If no _offset_ was specified, then a
            `TypeError` is raised. Ignored if _address_ is passed.
        @param index Base-0 register array element index (int). The write address is adjusted based on this
            value multiplied by the array element _stride_ passed into the class definition (which defaults
            to the register width in bytes if not provided). An index of 0 is always valid. Otherwise, if
            the index is negative or greater than the specified number of elements (also passed into the
            class definition) then an `IndexError` is raised.
        """
        if value is not None:
            self.value = value
        addr = self._get_target_address(address, (base or self._base), index)
        memif.write_memory(addr, self.value, transfer_size=self.width)

    # Use different implementations of write() for the class and instance.
    write = _ClassAndInstanceMethod(_class_write, _instance_write)

    def __get__(self, obj: Optional[object], objtype: Optional[type] = None) -> Union[Self, RegisterDefinition]:
        """@brief Descriptor get operation."""
        print(f"reg get called for {self.name}; {obj=}; {_register_thread_locals.memif_stack=}")
        # When called on the class, return ourself.
        if obj is None:
            return self
        else:
            return self.read(_register_thread_locals.memif_stack[-1], base=self._base)

    def __set__(self, obj: object, value: Any) -> None:
        """@brief Descriptor set operation."""
        print(f"reg get called for {self.name}; {obj=} {value=}; {_register_thread_locals.memif_stack=}")
        if obj is None:
            raise AttributeError("cannot set bitfields of a register class")
        self.write(_register_thread_locals.memif_stack[-1], value, base=self._base)

    def __repr__(self) -> str:
        val = -1 if self._value is None else self._value
        at_addr = f"@{self.address:0{self.width // 4}x}" if (self.address is not None) else ""
        return f"<{self.name} {at_addr} ={val:0{self.width // 4}x}>"

_register_thread_locals = threading.local()
_register_thread_locals.memif_stack = []

@contextmanager
def register_memif(memif: MemoryInterface):
    try:
        _register_thread_locals.memif_stack.append(memif)
        yield
    finally:
        _register_thread_locals.memif_stack.pop()

# class Foo:
#     def __init__(self, target) -> None:
#         self.DHCSR = DHCSR(target)
#         # -> RegisterTargetProxy(DHCSR, target)
#
#         self.CTRL = FPB.CTRL(target, base=0xe000e000)
#         # -> RegisterTargetProxy(FPB.CTRL, target, base=0xe000e000)
#
#     def foo(self):
#         self.DHCSR.C_HALT = 1
#         # a = self.DHCSR.__get__(self, Foo) ----> RegisterTargetProxy.__get__()
#         # b = a.C_HALT.__get__(a, DHCSR)

#
# class CSW(RegisterDefinition):
#     SIZE        = Bitfield[2:0](
#         SIZE8   = 0,
#         SIZE16  = 1,
#         SIZE32  = 2,
#         SIZE64  = 3,
#         SIZE128 = 4,
#         SIZE256 = 5,
#     )
#     ADDRINC     = Bitfield[5:4](
#         NADDRINC=0,
#         SADDRINC=1
#         PADDRINC=2,
#     )
#     DEVICEEN    = Bitfield[6]
#     TINPROG     = Bitfield[7]
#     ERRNPASS    = Bitfield[16]
#     ERRSTOP     = Bitfield[17]
#     SDEVICEEN   = Bitfield[23]
#     HPROT       = Bitfield[27:24]
#     MSTRTYPE    = Bitfield[29](
#         MSTRCORE=0,
#         MSTRDBG=1,
#     )
#     DBGSWEN     = Bitfield[31]


