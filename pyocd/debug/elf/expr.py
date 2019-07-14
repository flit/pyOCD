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

import logging
from elftools.dwarf import constants
from elftools.dwarf.dwarf_expr import GenericExprVisitor

from ...core import exceptions
from ...utility.compatibility import to_str_safe

LOG = logging.getLogger(__name__)

class DwarfExpr(object):
    """! @brief Wrapper around the underlying machinery for DWARF expr evaluation."""

    def __init__(self, expr, structs):
        super(DwarfExpr, self).__init__()
        self._expr = expr
        self._structs = structs

    def evaluate(self, delegate=None):
        visitor = self._get_visitor()
        visitor.delegate = delegate
        visitor.process_expr(self._expr)
        return visitor.result
    
    def _get_visitor(self):
        return _DwarfExprEvaluatorVisitor(self._structs)
    
    def __repr__(self):
        return "<{}@{:#x} [{}]>".format(self.__class__.__name__, id(self),
            " ".join("{:02x}".format(b) for b in self._expr))

class _DwarfExprEvaluatorVisitor(GenericExprVisitor):
    """! @brief Virtual machine to evaluate DWARF expressions.
    """

    def __init__(self, structs):
        super(_DwarfExprEvaluatorVisitor, self).__init__(structs)
        self._stack = []
        self._delegate = None
    
    @property
    def result(self):
        try:
            return self._stack.pop()
        except IndexError:
            return 0 # None
    
    @property
    def delegate(self):
        return self._delegate
    
    @delegate.setter
    def delegate(self, new_delegate):
        self._delegate = new_delegate

    def _after_visit(self, opcode, opcode_name, args):
        print(opcode_name, args)
        
        if opcode_name in ('DW_OP_addr', 'DW_OP_const1u', 'DW_OP_const1s', 'DW_OP_const2u',
                            'DW_OP_const2s', 'DW_OP_const4u', 'DW_OP_const4s', 'DW_OP_const8u',
                            'DW_OP_const8s', 'DW_OP_constu', 'DW_OP_consts'):
            self._push(args[0])
        elif opcode_name.startswith('DW_OP_lit'):
            self._push(opcode - 0x30)

    def _push(self, value):
        self._stack.append(value)
    
    def _pop(self):
        return self._stack.pop()
