# pyOCD debugger
# Copyright (c) 2022 Chris Reed
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

from ..utility.register import (Bitfield, Constant, RegisterDefinition)


# Debug Halting Control and Status Register
class DHCSR(RegisterDefinition, address=0xE000EDF0):
    S_RESET_ST  = 25
    S_RETIRE_ST = 24
    S_LOCKUP    = 19
    S_SLEEP     = 18
    S_HALT      = 17
    S_REGRDY    = 16
    DBGKEY      = Bitfield[31:16] # On write only
    DBGKEY__KEY = Constant(0xA05F << 16)
    C_PMOV      = 6
    C_SNAPSTALL = 5
    C_MASKINTS  = 3
    C_STEP      = 2
    C_HALT      = 1
    C_DEBUGEN   = 0

    # DHCSR.DBGKEY.KEY

# Debug Fault Status Register
class DFSR(RegisterDefinition, address=0xE000ED30):
    EXTERNAL = 4
    VCATCH = 3
    DWTTRAP = 2
    BKPT = 1
    HALTED = 0

# Debug Exception and Monitor Control Register
class DEMCR(RegisterDefinition, address=0xE000EDFC):
    TRCENA = 24 # DWTENA in armv6 architecture reference manual
    MONPRKEY = 23
    UMON_EN = 21
    SDME = 20
    MON_REQ = 19
    MON_STEP = 18
    MON_PEND = 17
    MON_EN = 16
    VC_SFERR = 11
    VC_HARDERR = 10
    VC_INTERR = 9
    VC_BUSERR = 8
    VC_STATERR = 7
    VC_CHKERR = 6
    VC_NOCPERR = 5
    VC_MMERR = 4
    VC_CORERESET = 0

# CPUID Register
class CPUID(RegisterDefinition, address=0xE000ED00):
    IMPLEMENTER = (31, 24)
    VARIANT = (23, 20)
    ARCHITECTURE = (19, 16)
    PARTNO = (15, 4)
    REVISION_POS = (3, 0)

# Debug Core Register Selector Register
class DCRSR(RegisterDefinition, address=0xE000EDF4):
    REGWnR = 16
    REGSEL = (7, 0)

# Debug Core Register Data Register
class DCRDR(RegisterDefinition, address=0xE000EDF8):
    pass

# Coprocessor Access Control Register
class CPACR(RegisterDefinition, address=0xE000ED88):
    CP10_CP11 = (23, 20)

# Interrupt Control and State Register
class ICSR(RegisterDefinition, address=0xE000ED04):
    PENDSVCLR = 27
    PENDSTCLR = 25

VTOR = 0xE000ED08
SCR = 0xE000ED10
SHPR1 = 0xE000ED18
SHPR2 = 0xE000ED1C
SHPR3 = 0xE000ED20
SHCSR = 0xE000ED24
FPCCR = 0xE000EF34
FPCAR = 0xE000EF38
FPDSCR = 0xE000EF3C
ICTR = 0xE000E004

class AIRCR(RegisterDefinition, address=0xE000ED0C):
    VECTKEY         = Bitfield[31:16]
    VECTKEY__KEY    = Constant(0x05FA << 16)
    ENDIANNESS      = 15
    PRIS            = 14
    BFHFNMINS       = 13
    PRIGROUP        = Bitfield[10:8]
    IESB            = 5
    DIT             = 4
    SYSRESETREQS    = 3
    SYSRESETREQ     = 2
    VECTCLRACTIVE   = 1
    VECTRESET       = 0

AIRCR_VECTKEY = 0x05FA

NVIC_ICER0 = 0xE000E180 # NVIC Clear-Enable Register 0
NVIC_ICPR0 = 0xE000E280 # NVIC Clear-Pending Register 0
NVIC_IPR0 = 0xE000E400 # NVIC Interrupt Priority Register 0

SYSTICK_CSR = 0xE000E010

# Media and FP Feature Register 0
class MVFR0(RegisterDefinition, address=0xE000EF40):
    SINGLE_PRECISION = Bitfield[7:4]
    SINGLE_PRECISION__SUPPORTED = Constant(2)
    DOUBLE_PRECISION = Bitfield[11:8]
    DOUBLE_PRECISION__SUPPORTED = Constant(2)

MVFR0_SINGLE_PRECISION_SUPPORTED = 2
MVFR0_DOUBLE_PRECISION_SUPPORTED = 2

# Media and FP Feature Register 2
class MVFR2(RegisterDefinition, address=0xE000EF48):
    MVFR2_VFP_MISC = Bitfield[7:4]

MVFR2_VFP_MISC_SUPPORTED = 4
