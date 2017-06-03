# pyOCD debugger
# Copyright (c) 2017-2019 Arm Limited
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
from elftools.dwarf.callframe import (CIE, FDE, RegisterRule)
from elftools.dwarf import descriptions

from ..core import exceptions
from .context import DebugContext
from ..coresight.cortex_m import (
    register_name_to_index,
    )

class ConfigError(exceptions.Error):
    pass

class DwarfError(exceptions.Error):
    pass

def dump_cfi(e):
    print(e.__class__.__name__)
    print(e.header)
    decoded = e.get_decoded()
#     print decoded
    print(descriptions.describe_CFI_instructions(e))
    for ln in decoded.table:
        pc = ln['pc']
        cfa = ln['cfa']
        print("0x%x: cfa=%s" % (pc, cfa),)
        for k in ln.iterkeys():
            if k in ('pc', 'cfa'):
                continue
            print(" r%d=%s" % (k, ln[k]),)
        print()

class CallFrameContext(DebugContext):
    def __init__(self, parent):
        super(CallFrameContext, self).__init__(parent)
        pc = self._parent.read_core_register_raw(15)
        self._cfp = CallFrameProvider(self.core, pc)
        self._cfp.eval()

    def read_core_register_raw(self, reg):
        try:
            regIndex = register_name_to_index(reg)
            rule = self._cfp.get_reg_rule(regIndex)
        except KeyError:
            return self._parent.read_core_register_raw(reg)

        # This frame's PC is its parent's LR (with T-bit cleared).
        if regIndex == 15:
            return self._parent.read_core_register_raw(14) & ~1

        cfa = self._cfp.cfa
        if cfa.expr is not None:
            raise DwarfError("unsupported CFA rule DWARF expression")
        assert 0 <= cfa.reg <= 15

        if rule.type in (RegisterRule.UNDEFINED, RegisterRule.SAME_VALUE):
            return self._parent.read_core_register_raw(reg)
        elif rule.type == RegisterRule.OFFSET:
            addr = self._parent.read_core_register_raw(cfa.reg) + cfa.offset + rule.arg
            value = self.read32(addr)
            return value
        elif rule.type == RegisterRule.VAL_OFFSET:
            value = self._parent.read_core_register_raw(cfa.reg) + cfa.offset
            return value
        elif rule.type == RegisterRule.REGISTER:
            assert 0 <= rule.arg <= 15
            return self._parent.read_core_register_raw(rule.arg)
        elif rule.type in (RegisterRule.EXPRESSION, RegisterRule.VAL_EXPRESSION, RegisterRule.ARCHITECTURAL):
            raise DwarfError("unsupported register rule type %s" % rule.type)

    def write_core_register_raw(self, reg, value):
        self._parent.write_core_register_raw(reg, value)

#         try:
#             regIndex = register_name_to_index(reg)
#             rule = self._cfp.get_reg_rule(regIndex)
#         except KeyError:
#             self._parent.write_core_register_raw(reg, value)

    def read_core_registers_raw(self, reg_list):
        return [self.read_core_register_raw(r) for r in reg_list]

    def write_core_registers_raw(self, reg_list, data_list):
        for r, d in zip(reg_list, data_list):
            self.write_core_register_raw(r, d)

class CallFrameProvider(object):
    def __init__(self, core, addr):
        if core.elf is None:
            raise ConfigError("Cannot provide call frame information without ELF")
        self._core = core
        self._elf = core.elf
        self._cfi_decoder = self._elf.cfi_decoder
        self._address = addr
        self._fde = self._cfi_decoder.get_fde_for_address(addr)

        self._init_regs();

#         if self._fde:
#             dump_cfi(self._fde.cie)
#             dump_cfi(self._fde)

    def _init_regs(self):
        self._cfa = None
        self._regs = {n : RegisterRule(RegisterRule.SAME_VALUE) for n in list(range(4, 12)) + list(range(13, 16))}
        self._regs.update({n : RegisterRule(RegisterRule.UNDEFINED) for n in range(0, 4)})

    def eval(self):
        def apply_entry(regs, entry, max_pc=None):
            for row in entry.get_decoded().table:
#                 print row

                pc = row['pc']
#                 print hex(pc)
                if (max_pc is not None) and (pc > max_pc):
#                     print "done"
                    return

                self._cfa = row['cfa']

                for key, rule in [r for r in row.items() if isinstance(r[0], int)]:
                    self._regs[key] = rule

        # Apply defaults from CIE.
        apply_entry(self._regs, self._fde.cie)

        # Apply the FDE.
        apply_entry(self._regs, self._fde, self._address)

        self._dump_regs()

    @property
    def cfa(self):
        return self._cfa

    def get_reg_rule(self, reg):
        return self._regs[reg]

    def _dump_regs(self):
        print("CFA: %s" % (self._cfa))
        for reg, rule in self._regs.items():
            print("r%s: %s" % (reg, rule))




