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

import os
from intervaltree import IntervalTree
from collections import (namedtuple, OrderedDict)
import logging
from enum import IntEnum
from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarfinfo import DWARFInfo
from elftools.dwarf import constants

from ..data_types import (
    InvalidTypeDefinition,
    SourceLocation,
    DataType,
    VOID_TYPE,
    ScalarType,
    PointerType,
    ArrayType,
    StructType,
    UnionType,
    EnumerationType,
    FunctionType,
    Variable,
    )
from ...core import exceptions
from ...utility.compatibility import to_str_safe

LOG = logging.getLogger(__name__)

## @brief Map from DWARF scalar types to struct module format strings used by ScalarType.
SCALAR_FORMAT_MAP = {
    constants.DW_ATE_address : {
        4 : 'L',
        },
    constants.DW_ATE_boolean : {
        1 : '?',
        },
    constants.DW_ATE_float : {
        4 : 'f',
        8 : 'd',
        },
    constants.DW_ATE_signed : {
        1 : 'b',
        2 : 'h',
        4 : 'l',
        8 : 'q',
        },
    constants.DW_ATE_signed_char : {
        1 : 'b',
        },
    constants.DW_ATE_unsigned : {
        1 : 'B',
        2 : 'H',
        4 : 'L',
        8 : 'Q',
        },
    constants.DW_ATE_unsigned_char : {
        1 : 'B',
        },
    }

class DwarfDieDecoder(object):
    """! @brief Extracts definitions from DWARF debug info."""
    
    def __init__(self, elf, dwarfinfo):
        assert isinstance(elf, ELFFile)
        assert isinstance(dwarfinfo, DWARFInfo)
        self._elffile = elf
        self._dwarfinfo = dwarfinfo
        self._anon_count = 0
        self._current_cu = None
        self._current_lineprog = None
        self._dies_by_offset = {}
        self._defs_by_offset = {}
        self._global_decls_by_offset = {}
        self._types = {}
        self._types_by_offset = {}
        self._globals = {}
        self._subprograms = {}
        
        self._process_cus()
    
    @property
    def types(self):
        return self._types
    
    @property
    def globals(self):
        return self._globals
    
    @property
    def subprograms(self):
        return self._subprograms

    def _process_cus(self):
        for cu in self._dwarfinfo.iter_CUs():
            self._current_cu = cu

            # The top DIE should be a DW_TAG_compile_unit or DW_TAG_partial_unit.
            top_die = cu.get_top_DIE()
            assert top_die.tag in ('DW_TAG_compile_unit', 'DW_TAG_partial_unit')
            
            self._current_lineprog = self._dwarfinfo.line_program_for_CU(cu)
            
            name = os.path.basename(to_str_safe(top_die.attributes['DW_AT_name'].value))
            LOG.debug("---- CU: %s", name)

            # Add all the DIEs for this CU so we can access them by offset.
            for die in top_die.iter_children():
                self._dies_by_offset[die.offset] = die
            
            for die in top_die.iter_children():
                try:
                    # Skip this DIE if we've already processed it out of order.
                    if die.offset in self._defs_by_offset:
                        continue
                    
                    new_def = self._handle_die(die)
                except (KeyError, InvalidTypeDefinition) as err:
                    LOG.debug("Error parsing DWARF types: %s ; die=%s", err, die, exc_info=True)

        # Clean up references to CU and DIEs.
        self._current_cu = None
        self._current_lineprog = None
        self._dies_by_offset = {}
        self._defs_by_offset = {}
        self._global_decls_by_offset = {}
    
    def _add_type(self, new_type, offset):
        self._defs_by_offset[offset] = new_type
        self._types[new_type.name] = new_type
        self._types_by_offset[offset] = new_type

    def _handle_die(self, die):
        # Find a handler method matching the DIE's tag.
        tag_handler_name = '_handle_' + die.tag
        if hasattr(self, tag_handler_name):
            getattr(self, tag_handler_name)(die)
            
    def _get_source_loc(self, die):
        if 'DW_AT_decl_file' not in die.attributes:
            return None
        filenum = die.attributes['DW_AT_decl_file'].value
        # A value of 0 indicates no file.
        if filenum == 0:
            return None
        try:
            # The file and dir indices are base-1, with 0 meaning invalid.
            file_entry = self._current_lineprog.header['file_entry'][filenum - 1]
            dirnum = file_entry['dir_index']
            if dirnum != 0:
                dirname = to_str_safe(self._current_lineprog.header['include_directory'][dirnum - 1])
            else:
                dirname = ""
        except IndexError:
            LOG.debug("invalid DW_AT_decl_file (%d)", filenum)
            return None
        if 'DW_AT_decl_line' in die.attributes:
            line = die.attributes['DW_AT_decl_line'].value
        else:
            line = 0
        
        return SourceLocation(to_str_safe(file_entry['name']), dirname, line)

    def _get_referenced_type(self, die, die_to_pend=None):
        if die_to_pend is None:
            die_to_pend = die
        type_ref = die.attributes['DW_AT_type'].value + self._current_cu.cu_offset
        if type_ref not in self._types_by_offset:
            referenced_die = self._dies_by_offset[type_ref]
            self._handle_die(referenced_die)
        return self._types_by_offset[type_ref]

    def _get_optional_name(self, die):
        if 'DW_AT_name' in die.attributes:
            name = to_str_safe(die.attributes['DW_AT_name'].value)
        else:
            name = "__anonymous${}".format(self._anon_count)
            self._anon_count += 1
        return name
    
    # --- types ---
    def _handle_DW_TAG_base_type(self, die):
        name = to_str_safe(die.attributes['DW_AT_name'].value)
        encoding = die.attributes['DW_AT_encoding'].value
        if 'DW_AT_byte_size' in die.attributes:
            byte_size = die.attributes['DW_AT_byte_size'].value
            try:
                fmt = SCALAR_FORMAT_MAP[encoding][byte_size]
            except KeyError:
                raise InvalidTypeDefinition("unsupported base type: {}, {} bytes".format(encoding, byte_size))
            self._add_type(ScalarType(name, fmt, byte_size), die.offset)
        else:
            LOG.debug("Unhandled base type: %s", die)
    
    def _handle_DW_TAG_typedef(self, die):
        name = to_str_safe(die.attributes['DW_AT_name'].value)
        # DW_AT_type may not be present according to the spec.
        if 'DW_AT_type' in die.attributes:
            self._add_type(self._get_referenced_type(die).make_typedef(
                name,
                loc=self._get_source_loc(die)),
                die.offset)
    
    def _handle_DW_TAG_volatile_type(self, die):
        parent_type = self._get_referenced_type(die)
        self._add_type(parent_type.make_typedef(
            parent_type.name + ' volatile',
            DataType.Qualifiers.VOLATILE,
            loc=self._get_source_loc(die)),
            die.offset)
    
    def _handle_DW_TAG_const_type(self, die):
        parent_type = self._get_referenced_type(die)
        self._add_type(parent_type.make_typedef(
            parent_type.name + ' const',
            DataType.Qualifiers.CONST,
            loc=self._get_source_loc(die)),
            die.offset)
    
    def _handle_DW_TAG_restrict_type(self, die):
        parent_type = self._get_referenced_type(die)
        self._add_type(parent_type.make_typedef(
            parent_type.name + ' restrict',
            DataType.Qualifiers.RESTRICT,
            loc=self._get_source_loc(die)),
            die.offset)
    
    def _handle_DW_TAG_pointer_type(self, die):
        if 'DW_AT_type' not in die.attributes:
            parent_type = VOID_TYPE
        else:
            parent_type = self._get_referenced_type(die)
        if parent_type.name.endswith('*'):
            name_star = '*'
        else:
            name_star = ' *'
        self._add_type(PointerType(
            parent_type.name + name_star,
            parent_type,
            loc=self._get_source_loc(die)),
            die.offset)

    # --- global variables
    def _handle_DW_TAG_variable(self, die):
        if 'DW_AT_declaration' in die.attributes:
            # Ignore declarations.
            pass
        else:
            if 'DW_AT_specification' in die.attributes:
                offset = die.attributes['DW_AT_specification'].value + self._current_cu.cu_offset
                decl = self._dies_by_offset[offset]
                assert (decl.tag == 'DW_TAG_variable') and ('DW_AT_declaration' in decl.attributes)
                name = to_str_safe(decl.attributes['DW_AT_name'].value)
                var_type = self._get_referenced_type(decl)
            else:
                name = to_str_safe(die.attributes['DW_AT_name'].value)
                var_type = self._get_referenced_type(die)
            addr = die.attributes['DW_AT_location'].value
            loc = self._get_source_loc(die)
            new_var = Variable(name, var_type, addr, loc)
            self._defs_by_offset[die.offset] = new_var
            self._globals[name] = new_var
    
    # --- subprograms
    def _handle_DW_TAG_subprogram(self, die):
        pass
    
    def _handle_DW_TAG_structure_type(self, die):
        self._handle_struct_type(die, False)

    def _handle_DW_TAG_union_type(self, die):
        self._handle_struct_type(die, True)

    def _handle_struct_type(self, die, is_union):
        # If DW_AT_declaration is set, then this is just a forward declaration that we can ignore.
        if 'DW_AT_declaration' in die.attributes:
            name = self._get_optional_name(die)
            self._add_type(StructType(name, byte_size=0, undefined=True), die.offset)
            return
        # The struct may be anonymous.
        name = self._get_optional_name(die)
        byte_size = die.attributes['DW_AT_byte_size'].value
        if is_union:
            klass = UnionType
        else:
            klass = StructType
        struct_type = klass(name, byte_size, loc=self._get_source_loc(die))
        self._add_type(struct_type, die.offset)
        for child in die.iter_children():
            if child.tag == 'DW_TAG_member':
                member_type = self._get_referenced_type(child, die)
                name = self._get_optional_name(child)
                if is_union:
                    struct_type.add_member(name, member_type)
                else:
                    offset = child.attributes['DW_AT_data_member_location'].value
                    struct_type.add_member(name, offset, member_type)
        return struct_type

    def _handle_DW_TAG_array_type(self, die):
        element_type = self._get_referenced_type(die)
        count = None
        # The children represent dimensions. We only support 1 for now.
        for child in die.iter_children():
            if child.tag == 'DW_TAG_subrange_type':
                if 'DW_AT_upper_bound' in child.attributes:
                    # The upper bound is inclusive.
                    count = child.attributes['DW_AT_upper_bound'].value + 1
                elif 'DW_TAG_count' in child.attributes:
                    count = child.attributes['DW_TAG_count'].value
                break
        self._add_type(ArrayType(element_type.name + '[]', element_type, count, loc=self._get_source_loc(die)), die.offset)
    
    def _handle_DW_TAG_enumeration_type(self, die):
        name = self._get_optional_name(die)
        byte_size = die.attributes['DW_AT_byte_size'].value
        enum_type = self._get_referenced_type(die)
        enum = EnumerationType(name, byte_size, enum_type, loc=self._get_source_loc(die))
        self._add_type(enum, die.offset)
        for child in die.iter_children():
            name = to_str_safe(child.attributes['DW_AT_name'].value)
            value = child.attributes['DW_AT_const_value'].value
            enum.add_enumerator(name, value)
        return enum

    def _handle_DW_TAG_subroutine_type(self, die):
        name = self._get_optional_name(die)
        if 'DW_AT_type' in die.attributes:
            return_type = self._get_referenced_type(die)
        else:
            return_type = None
        fn_type = FunctionType(name, return_type, loc=self._get_source_loc(die))
        self._add_type(fn_type, die.offset)
        for child in die.iter_children():
            if child.tag == 'DW_TAG_formal_parameter':
                if 'DW_AT_name' in child.attributes:
                    name = self._get_optional_name(die)
                else:
                    name = None
                param_type = self._get_referenced_type(child)
                fn_type.add_parameter(name, param_type)
        

