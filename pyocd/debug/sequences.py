# pyOCD debugger
# Copyright (c) 2020 Arm Limited
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

import lark.lark
import lark.exceptions
import lark.visitors
import six
import logging

from ..core import exceptions
from ..utility.graph import GraphNode

LOG = logging.getLogger(__name__)

class Parser(object):
    """! @brief Debug sequence statement parser."""
    
    class ConvertLiterals(lark.visitors.Transformer):
        def INTLIT(self, tok):
            """! @brief Convert integer literal tokens to integers."""
            return tok.update(value=int(tok.value, base=0))
    
    ## Shared parser object.
    _parser = lark.lark.Lark.open("sequences.lark",
                        rel_to=__file__,
                        parser="lalr",
                        maybe_placeholders=True,
                        propagate_positions=True,
                        transformer=ConvertLiterals())
    
    def __init__(self):
        pass

    def parse(self, data):
        try:
            return self._parser.parse(data)
        except lark.exceptions.UnexpectedInput as e:
            message = str(e) + "\n\nContext: " + e.get_context(data, 40)
            six.raise_from(exceptions.Error(message), e)

class DebugSequenceNode(GraphNode):
    """! @brief Common base class for debug sequence nodes."""
    
    def __init__(self, info=""):
        super(DebugSequenceNode, self).__init__()
        self._info = info
    
    @property
    def info(self):
        return self._info

class DebugSequence(DebugSequenceNode):
    """! @brief Named debug sequence."""
    
    def __init__(self, name, is_enabled=True, pname=None, info=""):
        super(DebugSequence, self).__init__(info)
        self._name = name
        self._is_enabled = is_enabled
        self._pname = pname
    
    @property
    def name(self):
        return self._name
    
    @property
    def pname(self):
        return self._pname
    
    @property
    def is_enabled(self):
        return self._is_enabled
    
    def __repr__(self):
        return "<{}:{:x} {}>".format(self.__class__.__name__, id(self), self.name)

class Control(DebugSequenceNode):
    """! @brief Base class for control nodes of debug sequences."""

    def __init__(self, predicate, info=""):
        super(Control, self).__init__(info)
        self._predicate = predicate
        self._ast = Parser().parse(predicate)
    
    def __repr__(self):
        return "<{}:{:x} {}>".format(self.__class__.__name__, id(self),
            self._ast.pretty())

class WhileControl(Control):
    """! @brief Looping debug sequence node."""

    def __init__(self, predicate, info=""):
        super(WhileControl, self).__init__(predicate, info)

class IfControl(Control):
    """! @brief Conditional debug sequence node."""

    def __init__(self, predicate, info=""):
        super(IfControl, self).__init__(predicate, info)

class Block(DebugSequenceNode):
    """! @brief Block of debug sequence statements."""

    def __init__(self, code, info=""):
        super(Block, self).__init__(info)
        self._code = code
        self._ast = Parser().parse(code)
    
    def __repr__(self):
        return "<{}:{:x} {}>".format(self.__class__.__name__, id(self),
            self._ast.pretty())

