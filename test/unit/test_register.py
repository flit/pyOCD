# pyOCD debugger
# Copyright (c) 2019-2020 Arm Limited
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

import pytest
from unittest.mock import MagicMock

from .conftest import mockcore

from pyocd.core.memory_interface import MemoryInterface
from pyocd.utility.register import (
    Bitfield,
    Constant,
    RegisterDefinition,
    register_memif,
)

class DHCSR(RegisterDefinition, offset=0xDF0, width=32):
    # creates class attrs from field defs, each is a Bitfield
    C_DEBUGEN   = 0
    C_HALT      = 1
    C_STEP      = 2
    C_MASKINTS  = 3
    C_SNAPSTALL = 5
    C_PMOV      = 6
    STATUSES    = (19, 16)  # bit range as 2-tuple; can have duplicate bits within reg def
    S_REGRDY    = 16
    S_HALT      = 17
    S_SLEEP     = 18
    S_LOCKUP    = 19
    S_RETIRE_ST = 24
    S_RESET_ST  = 25

class CTRL(RegisterDefinition, offset=0):
    ENABLE      = Bitfield[0]
    KEY         = Bitfield[1]
    NUM_CODE    = Bitfield[14:12, 7:4]
    NUM_LIT     = Bitfield[11:8]
    REV         = Bitfield[31:28]

# register array, defined by elements and stride params
class COMP0(RegisterDefinition, offset=8, elements=8):
    pass

class COMPA(RegisterDefinition, offset=8, elements=8, stride=8):
    pass

class WADDR(RegisterDefinition, address=0x2800):
    FOO = Bitfield[13:4]
    BAR = 2

@pytest.fixture(scope='function')
def memif():
    return MagicMock(spec=MemoryInterface)

class TestBitfield:
    pass

class TestMultiBitfield:
    def test_1(self):
        pass

class TestRegisterDefinition:
    def test_1(self):
        assert CTRL.ENABLE.mask == 0x1
        assert CTRL.ENABLE.width == 1
        assert CTRL.ENABLE.lsb == 0 and CTRL.ENABLE.msb == 0
        assert CTRL.ENABLE._register_width == 32

    def test_2(self):
        assert DHCSR.STATUSES.mask == 0x000f0000

    def test_3(self):
        assert CTRL.REV.mask == 0xf0000000

    def test_reg_array_no_stride(self):
        assert COMP0.width == 32
        assert COMP0._get_target_address(base=0x1000) == 0x1008
        assert COMP0._get_target_address(base=0x1000, index=0) == 0x1008
        assert COMP0._get_target_address(base=0x1000, index=1) == 0x100C
        assert COMP0._get_target_address(base=0x1000, index=3) == 0x1014

    def test_reg_array_stride(self):
        assert COMPA.width == 32
        assert COMPA._get_target_address(base=0x1000) == 0x1008
        assert COMPA._get_target_address(base=0x1000, index=0) == 0x1008
        assert COMPA._get_target_address(base=0x1000, index=1) == 0x1010
        assert COMPA._get_target_address(base=0x1000, index=3) == 0x1020

    def test_reg_addr_override(self):
        assert WADDR._get_target_address(address=0x8000) == 0x8000

    def test_reg_with_base_addr_override(self):
        assert COMP0._get_target_address(address=0x8000, base=0x1000) == 0x8000

    def test_read(self, memif):
        r = COMP0.read(memif, base=0x1000)
        memif.read_memory.assert_called_with(0x1008, transfer_size=32)

    def test_write_class(self, memif):
        COMP0.write(memif, 0x1234, base=0x1000)
        memif.write_memory.assert_called_with(0x1008, 0x1234, transfer_size=32)

    def test_write_instance(self, memif):
        r = COMP0(0x5678)
        r.write(memif, base=0x2000)
        memif.write_memory.assert_called_with(0x2008, 0x5678, transfer_size=32)

class TestRegisterProxy:
    def test_a(self, memif):
        class Foo:
            DHCSR = DHCSR(None, base=0xe000e000) #(memif, base=0xe000e000)
            def __init__(self) -> None:
                rattr = self.__dict__.get('DHCSR', 'none')
                print(f"{rattr=} {type(self.DHCSR)=}")
        f = Foo()
        # x = f.DHCSR
        # memif.read_memory.assert_called_with(0xe000edf0, transfer_size=32)
        # f.DHCSR = 0x10301
        # memif.write_memory.assert_called_with(0xe000edf0, 0x10301, transfer_size=32)

        with register_memif(memif):
            x = f.DHCSR
            print(f"{x=}")
            memif.read_memory.assert_called_with(0xe000edf0, transfer_size=32)

            f.DHCSR = 0x10301
            memif.write_memory.assert_called_with(0xe000edf0, 0x10301, transfer_size=32)
