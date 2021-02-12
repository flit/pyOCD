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

from ..probe.debug_probe import DebugProbe

LOG = logging.getLogger(__name__)

class SWJSequenceSender(object):
    """! @brief Class to send canned SWJ sequences.
    
    The primary usage of this class is for sending the SWJ sequences to switch between JTAG and SWD protocols
    in the Arm ADI SWJ-DP. The select_protocol() method is used for this purpose.
    
    In addition, there are methods available to send fragments of the various selection sequences. These can be
    used to put a target is whatever state is required.
    """

    def __init__(self, probe, use_dormant):
        self._probe = probe
        self._use_dormant = use_dormant
    
    @property
    def use_dormant(self):
        return self._use_dormant
    
    @use_dormant.setter
    def use_dormant(self, flag):
        self._use_dormant = flag

    def select_protocol(self, protocol):
        """! @brief Send SWJ sequence to select chosen wire protocol.
        
        The `use_dormant` property determines whether dormant mode will be used for the protocol selection, or
        if the deprecated ADIv5.0 SWJ sequences will be used.
        
        @param self This object.
        @param protocol One of the @ref pyocd.probe.debug_probe.DebugProbe.Protocol DebugProbe.Protocol enums, except
            that `DEFAULT` is not acceptable and will cause a ValueError exception to be raised.
        
        @exception ValueError Request to select the `DEFAULT` protocol.
        """
        # Not all probes support sending SWJ sequences.
        assert isinstance(protocol, DebugProbe.Protocol)
        if protocol == DebugProbe.Protocol.SWD:
            self.switch_to_swd()
        elif protocol == DebugProbe.Protocol.JTAG:
            self.switch_to_jtag()
        elif protocol == DebugProbe.Protocol.DEFAULT:
            raise ValueError("cannot send SWJ sequence for default protocol")
        else:
            assert False, "unhandled protocol %s in SWJSequenceSender" % protocol
    
    def jtag_enter_test_logic_reset(self):
        """! @brief Execute at least >5 TCK cycles with TMS high to enter the Test-Logic-Reset state.
        
        The line_reset() method can be used instead of this method, but takes a little longer to send.
        """
        self._probe.swj_sequence(8, 0xff)
    
    def line_reset(self):
        """! @brief Execute a line reset for both SWD and JTAG.
        
        For JTAG, >=5 TCK cycles with TMS high enters the Test-Logic-Reset state.<br/>
        For SWD, >=50 cycles with SWDIO high performs a line reset.
        """
        self._probe.swj_sequence(51, 0xffffffffffffff)
    
    def selection_alert(self):
        """! @brief Send the dormant selection alert sequence.
        
        The 128-bit selection alert is prefixed with 8 cycles of SWDIOTMS high.
        """
        self._probe.swj_sequence(136, 0x19bc0ea2e3ddafe986852d956209f392ff)
    
    def jtag_to_dormant_select(self):
        """! @brief Send the JTAG to DS select sequence.
        
        Sends the recommended 31-bit JTAG-to-DS select sequence of 0x33bbbbba (LSB-first) on SWDIOTMS. See ADIv6
        section B5.3.2.
        
        Note that this should be prefixed with at least 5 cycles to put the JTAG TAP in Test-Logic-Reset; see
        jtag_enter_test_logic_reset().
        """
        self._probe.swj_sequence(39, 0x33bbbbba)
    
    def swd_to_dormant_select(self):
        """! @brief Send the SWD to DS sequence.
        
        Sends the 16-bit SWD-to-DS select sequence of 0xe3bc (LSB-first) on SWDIOTMS. See ADIv6 section B5.3.3.
        
        Note that an SWD line reset should prefix this sequence. See line_reset().
        """
        self._probe.swj_sequence(16, 0xe3bc)
    
    def jtag_activation_code(self):
        """! @brief 4-bit SWDIOTMS cycles low + 8-bit JTAG activation code."""
        self._probe.swj_sequence(12, 0x00a0)
    
    def swd_activation_code(self):
        """! @brief 4-bit SWDIOTMS cycles low + 8-bit SWD activation code."""
        self._probe.swj_sequence(12, 0x01a0)
    
    def idle_cycles(self, cycles):
        """! @brief Send SWD idle cycles with SWDIOTMS low."""
        self._probe.swj_sequence(cycles, 0)
    
    def dormant_to_swd(self):
        """! @brief Perform the dormant mode to SWD transition sequence."""
        # 8 SWDIOTMS cycles high + 128-bit selection alert sequence.
        self.selection_alert()
        
        # 4-bit SWDIOTMS cycles low + 8-bit SWD activation code.
        self.swd_activation_code()
        
        # SWD line reset (>50 SWDIOTMS cycles high).
        self.line_reset()
        
        # >=2 SWDIOTMS cycles low.
        self.idle_cycles(2)
    
    def dormant_to_jtag(self):
        """! @brief Perform the dormant mode to JTAG transition sequence."""
        # 8 SWDIOTMS cycles high + 128-bit selection alert sequence.
        self.selection_alert()
        
        self.jtag_activation_code()
        
        self.jtag_enter_test_logic_reset()

    def switch_to_swd(self):
        """! @brief Send SWJ sequence to select SWD."""
        if self._use_dormant:
            LOG.debug("Sending SWJ sequence to select SWD; using dormant state")
            
            # Ensure current debug interface is in reset state
            self.line_reset()
            
            # Send all this in one transfer:
            # Select Dormant State (from JTAG), 0xb3bbbbbaff
            # 8 cycles SWDIO/TMS HIGH, 0xff
            # Alert Sequence, 0x19bc0ea2e3ddafe986852d956209f392
            # 4 cycles SWDIO/TMS LOW + 8-Bit SWD Activation Code (0x1A), 0x01a0
#             self._probe.swj_sequence(188, 0x01a019bc0ea2e3ddafe986852d956209f392ffb3bbbbbaff)
            self.jtag_to_dormant_select()
            self.selection_alert()
            self.swd_activation_code()
           
            # Enter SWD Line Reset State
            self.line_reset()                   # > 50 cycles SWDIO/TMS High
            self._probe.swj_sequence(8,  0x00)  # At least 2 idle cycles (SWDIO/TMS Low)
        else:
            LOG.debug("Sending deprecated SWJ sequence to select SWD")
            
            # Ensure current debug interface is in reset state
            self.line_reset()
            
            # Execute SWJ-DP Switch Sequence JTAG to SWD (0xE79E)
            # Change if SWJ-DP uses deprecated switch code (0xEDB6)
            self._probe.swj_sequence(16, 0xe79e)
            
            # Enter SWD Line Reset State
            self.line_reset()                   # > 50 cycles SWDIO/TMS High
            self._probe.swj_sequence(8,  0x00)  # At least 2 idle cycles (SWDIO/TMS Low)
    
    def switch_to_jtag(self):
        """! @brief Send SWJ sequence to select JTAG."""
        if self._use_dormant:
            LOG.debug("Sending SWJ sequence to select JTAG ; using dormant state")
            
            # Ensure current debug interface is in reset state
            self.line_reset()
            
            # Select Dormant State (from SWD)
            # At least 8 cycles SWDIO/TMS HIGH, 0xE3BC
            # Alert Sequence, 0x19bc0ea2e3ddafe986852d956209f392
            # 4 cycles SWDIO/TMS LOW + 8-Bit JTAG Activation Code (0x0A), 0x00a0
            self._probe.swj_sequence(188, 0x00a019bc0ea2e3ddafe986852d956209f392ffe3bc)
           
            # Ensure JTAG interface is reset
            self.jtag_enter_test_logic_reset()
        else:
            LOG.debug("Sending deprecated SWJ sequence to select JTAG")
            
            # Ensure current debug interface is in reset state
            self.line_reset()
            
            # Execute SWJ-DP Switch Sequence SWD to JTAG (0xE73C)
            # Change if SWJ-DP uses deprecated switch code (0xAEAE)
            self._probe.swj_sequence(16, 0xe73c)
            
            # Ensure JTAG interface is reset
            self.jtag_enter_test_logic_reset()
    
