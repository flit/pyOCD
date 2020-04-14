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

import logging
import pytest

# unittest.mock is available from Python 3.3.
try:
    from unittest import mock
except ImportError:
    import mock

from pyocd.debug.sequences import *
from pyocd.core.session import Session
from pyocd.probe.debug_probe import DebugProbe

MockSequenceDelegate = mock.Mock(spec=DebugSequenceDelegate)

class MockProbe(object):
    def __init__(self):
        self.wire_protocol = DebugProbe.Protocol.SWD

@pytest.fixture(scope='function')
def session():
    s = Session(None)
    setattr(s, '_probe', MockProbe())
    return s

@pytest.fixture(scope='function')
def delegate():
    return MockSequenceDelegate()

@pytest.fixture(scope='function')
def scope():
    s = Scope()
    s.set("a", 0)
    s.set("b", 128)
    return s

class TestDebugSequences:
    def test_a(self, session, delegate, scope):
        s = Block("a == 0")
        s.execute(session, delegate, scope)

    def test_set_var(self, session, delegate, scope):
        s = Block("__var x = 100;")
        s.execute(session, delegate, scope)
        assert scope.get("x") == 100

    @pytest.mark.parametrize(("expr", "result"), [
            ("1 + 1", 2),
            ("2 - 1", 1),
            ("2 * 4", 8),
            ("4 / 2", 2),
            ("5 % 4", 1),
            ("1 << 12", 4096),
            ("0x80 >> 4", 0x8),
            ("0b1000 | 0x2", 0b1010),
            ("0b1100 & 0b0100", 0b0100),
        ])
    def test_int_expr(self, session, delegate, scope, expr, result):
        s = Block("__var x = %s;" % expr)
        s.execute(session, delegate, scope)
        assert scope.get("x") == result

    @pytest.mark.parametrize(("expr", "result"), [
            ("1 == 1", 1),
            ("1 == 0", 0),
            ("0 == 1", 0),
            ("1 != 1", 0),
            ("1 != 0", 1),
            ("0 != 1", 1),
            ("20 > 10", 1),
            ("20 > 20", 0),
            ("20 > 100", 0),
            ("5 >= 2", 1),
            ("5 >= 5", 1),
            ("5 >= 100", 0),
            ("10 < 20", 1),
            ("10 < 10", 0),
            ("10 < 4", 0),
            ("10 <= 20", 1),
            ("10 <= 10", 1),
            ("10 <= 5", 0),
        ])
    def test_bool_cmp_expr(self, session, delegate, scope, expr, result):
        s = Block("__var x = %s;" % expr)
        s.execute(session, delegate, scope)
        assert scope.get("x") == result

    # Aside from the obvious, verify that && and || are evaluated as in C rather than Python.
    # That is, they must produce a 1 or 0 and not the value of either operand.
    @pytest.mark.parametrize(("expr", "result"), [
            ("1 && 1", 1),
            ("1 && 0", 0),
            ("0 && 1", 0),
            ("0 && 0", 0),
            ("1 || 1", 1),
            ("1 || 0", 1),
            ("0 || 1", 1),
            ("0 || 0", 0),
            ("5 && 1000", 1),
            ("432 && 0", 0),
            ("0 && 2", 0),
            ("0 && 0", 0),
            ("348 || 4536", 1),
            ("5 || 0", 1),
            ("0 || 199", 1),
            ("0 || 0", 0),
        ])
    def test_bool_and_or_expr(self, session, delegate, scope, expr, result):
        s = Block("__var x = %s;" % expr)
        s.execute(session, delegate, scope)
        assert scope.get("x") == result

    @pytest.mark.parametrize(("expr", "result"), [
            ("1 + 2 * 5", 11),
            ("7 * 12 + 5", 89),
            ("1 + 5 - 3", 3),
            ("(1 + 2) * 5", 15),
            ("1 + (2 * 5)", 11),
            ("2 + 16 / 2", 10),
            ("1 + 17 % 3", 3),
            ("2 * 3 * 4", 24),
            ("0 || 1 && 1", 1),
            ("1 == 6 > 5", 1),
            ("1 == 6 < 12", 0),
            ("1 << 4 > 1 << 2", 1),
            ("1 << (4 > 1) << 2", 8),
            ("!1 == 0", 1),
        ])
    def test_precedence(self, session, delegate, scope, expr, result):
        s = Block("__var x = %s;" % expr)
        s.execute(session, delegate, scope)
        assert scope.get("x") == result

    @pytest.mark.parametrize(("expr", "result"), [
            ("(7 * (1 << 3) + 1) >> 1", 28),
        ])
    def test_longer_expr(self, session, delegate, scope, expr, result):
        s = Block("__var x = %s;" % expr)
        logging.info("%s", s._ast.pretty())
        s.execute(session, delegate, scope)
        assert scope.get("x") == result
        
