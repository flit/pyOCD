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
from lark.lexer import Token as LarkToken
from lark.tree import Tree as LarkTree
import six
import logging
from enum import Enum

from ..core import exceptions
from ..utility.graph import GraphNode
from ..utility.mask import bit_invert

LOG = logging.getLogger(__name__)

class Parser(object):
    """! @brief Debug sequence statement parser."""
    
    class ConvertLiterals(lark.visitors.Transformer):
        """! @brief Transformer to convert integer literal tokens to integers.
        
        Running this transformer during the parse is more efficient than handling it post-parse
        such as during optimization.
        """
        def INTLIT(self, tok):
            return tok.update(value=int(tok.value, base=0))
    
    ## Shared parser object.
    _parser = lark.lark.Lark.open("sequences.lark",
                        rel_to=__file__,
                        parser="lalr",
                        maybe_placeholders=True,
                        propagate_positions=True,
                        transformer=ConvertLiterals())
    
    @classmethod
    def parse(cls, data):
        try:
            # Parse the input.
            tree = cls._parser.parse(data)
            
            # Do some optimization.
            optimized_tree = ConstantFolder().transform(tree)
            
            # Return the resulting tree.
            return optimized_tree
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

    def execute(self, session, delegate):
        pass

class DebugSequenceDelegate(object):
    """! @brief Delegate interface for handling sequence operations."""
    
    def get_sequence_by_name(self, name):
        pass
    
    def get_default_ap(self):
        pass
    
    def get_connection_type(self):
        pass

class DebugSequence(DebugSequenceNode):
    """! @brief Named debug sequence.
    
    Variable scoping:
    - Sequences and control elements create new scopes.
    - Scope extends to child control elements.
    - Block elements do not create a new scope.
    - Variables in a parent scope can be modified.
    - Leaving a scope destroys contained variables.
    
    Special read-write variables:
    - __dp, __ap, __errorcontrol
        - Not affected by scoping
        - Pushed on stack when another sequence is called via Sequence() function.
    - __Result
        - Not pushed when calling another sequence.
        - 0=success
        
    Special read-only variables:
    - __protocol
        - [15:0] 0=error, 1=JTAG, 2=SWD, 3=cJTAG
        - [16] SWJ-DP present?
        - [17] switch through dormant state?
    - __connection
        - [7:0] connection type: 0=error/disconnected, 1=for debug, 2=for flashing
        - [15:8] reset type: 0=error, 1=hw, 2=SYSRESETREQ, 3=VECTRESET
        - [16] connect under reset?
        - [17] pre-connect reset?
    - __traceout
        - [0] SWO enabled?
        - [1] parallel trace enabled?
        - [2] trace buffer enabled?
        - [21:16] selected parallel trace port size
    - __FlashOp
        - 0=no op, 1=erase full chip, 2=erase sector, 3=program 
    - __FlashAddr
    - __FlashLen
    - __FlashArg
    """
    
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
    
    def _create_scope(self, session, delegate):
        scope = Scope()
        scope.set('__dp', 0) # We only support one DP.
        scope.set('__ap', 0)
        scope.set('__errorcontrol', 0)
        scope.set('__Result', 0)
        
        # Generate __protocol value.
        protocol = session.probe.wire_protocol.value
        if True: #session.target.dp.is_swj:
            protocol |= 1 << 16
        if False:
            protocol |= 1 << 17
        scope.set('__protocol', protocol, True)
        
        # Generate __connection value.
        connection = delegate.get_connection_type()
        connection |= 1 << 8 # HW reset
        if session.options.get('connect_mode') == 'under-reset':
            connection |= 1 << 16
        scope.set('__connection', connection, True)
        
        scope.set('__traceout', 0, True)
        scope.set('__FlashOp', 0, True)
        scope.set('__FlashAddr', 0, True)
        scope.set('__FlashLen', 0, True)
        scope.set('__FlashArg', 0, True)
        return scope
    
    def execute(self, session, delegate):
        """! @brief Run the sequence."""
        scope = self._create_scope(session, delegate)
        for node in self.children:
            node.execute(session, delegate, scope)
    
    def __repr__(self):
        return "<{}:{:x} {}>".format(self.__class__.__name__, id(self), self.name)

class Control(DebugSequenceNode):
    """! @brief Base class for control nodes of debug sequences."""
    
    class ControlType(Enum):
        IF = 1
        WHILE = 2

    def __init__(self, control_type, predicate, info=""):
        super(Control, self).__init__(info)
        self._type = control_type
        self._predicate = predicate
        self._ast = Parser.parse(predicate)
    
    def execute(self, session, delegate, parent_scope):
        """! @brief Run the sequence."""
        scope = Scope(parent_scope)
        interp = Interpreter(scope, delegate)
        interp.start(self._ast)
        for node in self.children:
            node.execute(session, delegate, scope)
    
    def __repr__(self):
        return "<{}:{:x} {}>".format(self.__class__.__name__, id(self),
            self._ast.pretty())

class WhileControl(Control):
    """! @brief Looping debug sequence node."""

    def __init__(self, predicate, info=""):
        super(WhileControl, self).__init__(self.ControlType.WHILE, predicate, info)

class IfControl(Control):
    """! @brief Conditional debug sequence node."""

    def __init__(self, predicate, info=""):
        super(IfControl, self).__init__(self.ControlType.IF, predicate, info)

class Block(DebugSequenceNode):
    """! @brief Block of debug sequence statements."""

    def __init__(self, code, info=""):
        super(Block, self).__init__(info)
        self._code = code
        self._ast = Parser.parse(code)
    
    def execute(self, session, delegate, scope):
        """! @brief Run the sequence."""
        interp = Interpreter(scope, delegate)
        interp.start(self._ast)
    
    def __repr__(self):
        return "<{}:{:x} {}>".format(self.__class__.__name__, id(self),
            self._ast.pretty())

class ConstantFolder(lark.visitors.Transformer):
    """! @brief Performs basic constant folding on expressions."""
    
    def _is_intlit(self, node):
        return isinstance(node, LarkToken) and (node.type == 'INTLIT')
    
    def binary_expr(self, children):
        left = children[0]
        op = children[1].value
        right = children[2]
        
        if self._is_intlit(left) and self._is_intlit(right):
            result = _BINARY_OPS[op](left.value, right.value)
            LOG.info("opt: 0x%x %s 0x%x -> 0x%x", left.value, op, right.value, result)
            return LarkToken('INTLIT', result)

        return LarkTree('binary_expr', children)

    def unary_expr(self, children):
        op = children[0].value
        arg = children[1]
        
        if self._is_intlit(arg):
            result = _UNARY_OPS[op](arg.value)
            LOG.info("opt: %s 0x%x -> 0x%x", op, arg.value, result)
            return LarkToken('INTLIT', result)

        return LarkTree('unary_expr', children)

class Scope(object):
    """! @brief Debug sequence execution scope."""
    
    def __init__(self, parent=None):
        self._parent = parent
        self._variables = {} # Map from name: value.
        self._ro_variables = set() # A variable is read-only if its name is in this set.
    
    @property
    def parent(self):
        return self._parent
    
    def get(self, name):
        try:
            value = self._variables[name]
        except KeyError:
            if self._parent is not None:
                value = self._parent.get(name)
            else:
                raise
        LOG.info("get '%s' -> 0x%016x", name, value)
        return value
    
    def set(self, name, value, is_ro=False):
        LOG.info("set '%s' <- 0x%016x", name, value)
        # Catch attempt to rewrite a read-only variable.
        if (name in self._variables) and (name in self._ro_variables):
            raise RuntimeError("attempt to modify read-only variable '%s'" % name)
        self._variables[name] = value
        if is_ro:
            self._ro_variables.add(name)

## Lambdas for evaluating binary operators.
_BINARY_OPS = {
    '+':    lambda l, r: l + r,
    '-':    lambda l, r: l - r,
    '*':    lambda l, r: l * r,
    '/':    lambda l, r: l / r,
    '%':    lambda l, r: l % r,
    '&':    lambda l, r: l & r,
    '|':    lambda l, r: l | r,
    '^':    lambda l, r: l ^ r,
    '<<':   lambda l, r: l << r,
    '>>':   lambda l, r: l >> r,
    '&&':   lambda l, r: int(l and r),
    '||':   lambda l, r: int(l or r),
    '==':   lambda l, r: int(l == r),
    '!=':   lambda l, r: int(l != r),
    '>':    lambda l, r: int(l > r),
    '>=':   lambda l, r: int(l >= r),
    '<':    lambda l, r: int(l < r),
    '<=':   lambda l, r: int(l <= r),
    }

## Lambdas for evaluating unary operators.
_UNARY_OPS = {
    '~':    lambda v: bit_invert(v, width=64),
    '!':    lambda v: int(not v),
    '+':    lambda v: v,
    '-':    lambda v: -v,
    }

class Interpreter(lark.visitors.Interpreter):
    """! @brief Visitor for interpreting sequence trees.
    
    This class interprets the AST from only a single block or control node. The user of this class
    is required to handle crossing block/control boundaries.
    """

    def __init__(self, scope, delegate):
        super(Interpreter, self).__init__()
        self._scope = scope
        self._delegate = delegate
    
    def start(self, tree):
        self.visit_children(tree)
        
    def _log_children(self, name, children):
        LOG.info('%s: %s', name, [(("Node: %s" % c.data) if hasattr(c, 'data') else ("%s=%s" % (c.type, c.value))) for c in children])
    
    def decl_stmt(self, tree):
        self._log_children(tree.data + ' before visit', tree.children)
        values = self.visit_children(tree)
        LOG.info("%s values=%s", tree.data, values)
#         self._log_children(tree.data + ' after visit', tree.children)
        
        assert isinstance(values[0], LarkToken) and values[0].type == 'IDENT'
        name = values[0].value
        value = self._get_atom(values[1])
        
        self._scope.set(name, value)
    
    def assign_stmt(self, tree):
        self._log_children(tree.data, tree.children)
        values = self.visit_children(tree)
        LOG.info("%s values=%s", tree.data, values)
        
        name = values[0].value
        op = values[1].value
        value = self._get_atom(values[2])
        
        # Handle compound assignment operators.
        if op != '=':
            left = self._scope.get(name)
            op = op.rstrip('=')
            value = self._BINARY_OPS[op](left, value)

        self._scope.set(name, value)
    
    def expr_stmt(self, tree):
        self._log_children(tree.data, tree.children)
        self.visit_children(tree)
    
    def binary_expr(self, tree):
        self._log_children(tree.data + ' before visit', tree.children)
        values = self.visit_children(tree)
        LOG.info("%s values=%s", tree.data, values)
        
        left = self._get_atom(values[0])
        op = values[1].value
        right = self._get_atom(values[2])
        
        return _BINARY_OPS[op](left, right)
    
    def unary_expr(self, tree):
        values = self.visit_children(tree)
        LOG.info("%s values=%s", tree.data, values)
        
        op = values[0].value
        value = self._get_atom(values[1])
        
        return _UNARY_OPS[op](value)
    
    def fncall(self, tree):
        values = self.visit_children(tree)
        LOG.info("%s values=%s", tree.data, values)
        
        return 0
    
    def _get_atom(self, node):
        if isinstance(node, LarkTree):
            pass
        elif isinstance(node, LarkToken):
            if node.type == 'IDENT':
                return self._scope.get(node.value)
            elif node.type == 'INTLIT':
                return node.value
        elif isinstance(node, six.integer_types):
            return node
        
