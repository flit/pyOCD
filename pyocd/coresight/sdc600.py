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
from time import sleep
from enum import Enum

from .component import CoreSightComponent
from ..core import exceptions
from ..utility.timeout import Timeout
from ..utility.hex import dump_hex_data

LOG = logging.getLogger(__name__)

class UnexpectedFlagError(exceptions.Error):
    """! @brief Received an unexpected or out of order flag byte."""
    pass

class SDC600(CoreSightComponent):
    """! @brief SDC-600 component.
    """
    
    ## Timeout for each byte transfer.
    TRANSFER_TIMEOUT = 30.0
    
    class LinkPhase(Enum):
        """! @brief COM Port link phases."""
        ## Hardware-defined link phase.
        PHASE1 = 1
        ## Software-defiend link phase.
        PHASE2 = 2
    
    class Register:
        """! @brief Namespace for register offset constants."""
        # Register offsets.
        VIDR        = 0xD00
        FIDTXR      = 0xD08
        FIDRXR      = 0xD0C
        ICSR        = 0xD10
        DR          = 0xD20
        SR          = 0xD2C
        DBR         = 0xD30
        SR_ALIAS    = 0xD3C

        # FIDTXR and FIDRXR bit definitions.
        FIDxXR_xXI_MASK     = (0x00000001)
        FIDxXR_xXI_SHIFT    = (0)
        FIDxXR_xXINT_MASK   = (0x00000002)
        FIDxXR_xXINT_SHIFT  = (1)
        FIDxXR_xXW_MASK     = (0x000000f0)
        FIDxXR_xXW_SHIFT    = (4)
        FIDxXR_xXSZ8_MASK   = (0x00000100)
        FIDxXR_xXSZ8_SHIFT  = (8)
        FIDxXR_xXSZ16_MASK  = (0x00000200)
        FIDxXR_xXSZ16_SHIFT = (9)
        FIDxXR_xXSZ32_MASK  = (0x00000400)
        FIDxXR_xXSZ32_SHIFT = (10)
        FIDxXR_xXFD_MASK    = (0x000f0000)
        FIDxXR_xXFD_SHIFT   = (16)
        
        # SR bit definitions.
        SR_TXS_MASK         = (0x000000ff)
        SR_TXS_SHIFT        = (0)
        SR_RRDIS_MASK       = (0x00001000)
        SR_RRDIS_SHIFT      = (12)
        SR_TXOE_MASK        = (0x00002000)
        SR_TXOE_SHIFT       = (13)
        SR_TXLE_MASK        = (0x00004000)
        SR_TXLE_SHIFT       = (14)
        SR_TRINPROG_MASK    = (0x00008000)
        SR_TRINPROG_SHIFT   = (18)
        SR_RXF_MASK         = (0x00ff0000)
        SR_RXF_SHIFT        = (16)
        SR_RXLE_MASK        = (0x40000000)
        SR_RXLE_SHIFT       = (30)
        SR_PEN_MASK         = (0x80000000)
        SR_PEN_SHIFT        = (31)
    
    class Flag:
        """! @brief Namespace with flag byte value constants."""
        IDR     = 0xA0
        IDA     = 0xA1
        LPH1RA  = 0xA6
        LPH1RL  = 0xA7
        LPH2RA  = 0xA8
        LPH2RL  = 0xA9
        LPH2RR  = 0xAA
        LERR    = 0xAB
        START   = 0xAC
        END     = 0xAD
        ESC     = 0xAE
        NULL    = 0xAF
        
        # All bytes with 0b101 in bits [7:5] are flag bytes.
        MASK = 0xE0
        IDENTIFIER = 0b10100000
        
        ## Map from flag value to name.
        NAME = {
            IDR     : "IDR",
            IDA     : "IDA",
            LPH1RA  : "LPH1RA",
            LPH1RL  : "LPH1RL",
            LPH2RA  : "LPH2RA",
            LPH2RL  : "LPH2RL",
            LPH2RR  : "LPH2RR",
            LERR    : "LERR",
            START   : "START",
            END     : "END",
            ESC     : "ESC",
            NULL    : "NULL",
            }
    
    ## NULL bytes must be written to the upper bytes, and will be present in the upper bytes
    # when read.
    NULL_FILL = 0xAFAFAF00
    
    def __init__(self, ap, cmpid=None, addr=None):
        super(SDC600, self).__init__(ap, cmpid, addr)
        self._tx_width = 0
        self._rx_width = 0

    def init(self):
        """! @brief Inits the component.
        
        Reads the RX and TX widths and whether the SDC-600 is enabled. All error flags are cleared.
        """
        fidtx = self.ap.read32(self.Register.FIDTXR)
        LOG.info("fidtx=0x%08x", fidtx)
        fidrx = self.ap.read32(self.Register.FIDRXR)
        LOG.info("fidrx=0x%08x", fidrx)
        
        self._tx_width = (fidtx & self.Register.FIDxXR_xXW_MASK) >> self.Register.FIDxXR_xXW_SHIFT
        
        self._rx_width = (fidrx & self.Register.FIDxXR_xXW_MASK) >> self.Register.FIDxXR_xXW_SHIFT
        
        status = self.ap.read32(self.Register.SR)
        LOG.info("status=0x%08x", status)
        self._is_enabled = (status & self.Register.SR_PEN_MASK) != 0
        
        # Clear any error flags.
        error_flags = status & (self.Register.SR_TXOE_MASK | self.Register.SR_TXLE_MASK)
        if error_flags:
            self.ap.write32(self.Register.SR, error_flags)
    
    @property
    def is_reboot_request_enabled(self):
        return (self.ap.read32(self.Register.SR) & self.Register.SR_RRDIS_MASK) == 0

    def _read1(self):
        """! @brief Read a single byte.
        
        If a NULL byte is received, it is ignored and another byte is read.
        """
        while True:
            # Wait until a byte is ready in the receive FIFO.
            with Timeout(self.TRANSFER_TIMEOUT) as to_:
                while to_.check():
                    if (self.ap.read32(self.Register.SR) & self.Register.SR_RXF_MASK) != 0:
                        break
                    sleep(0.01)
                else:
                    raise exceptions.TimeoutError("timeout while reading from SDC-600")

            # Read the data register and strip off NULL bytes in high bytes.
            value = self.ap.read32(self.Register.DR) & 0xFF

            # Ignore NULL flag bytes.
            if value == self.Flag.NULL:
                continue
            
            return value
        
    def _write1(self, value):
        """! @brief Write one or more bytes."""
        # Wait until room is available in the transmit FIFO.
        with Timeout(self.TRANSFER_TIMEOUT) as to_:
            while to_.check():
                if (self.ap.read32(self.Register.SR) & self.Register.SR_TXS_MASK) != 0:
                    break
                sleep(0.01)
            else:
                raise exceptions.TimeoutError("timeout while writing to from SDC-600")

        # Write this byte to the transmit FIFO.
        dbr_value = self.NULL_FILL | (value & 0xFF)
        self.ap.write32(self.Register.DR, dbr_value)

    def _expect_flag(self, flag):
        value = self._read1()
        LOG.info("received: 0x%02x", value)
        if value != flag:
            raise UnexpectedFlagError("got {:#04x} instead of expected {} ({:#04x})".format(
                value, self.Flag.NAME[flag], flag))
        else:
            LOG.info("got expected %s", self.Flag.NAME[value])

    def _stuff(self, data):
        """! @brief Perform COM Encapsulation byte stuffing."""
        result = []
        for value in data:
            # Values matching flag bytes just get copied to output.
            if (value & self.Flag.MASK) == self.Flag.IDENTIFIER:
                # Insert escape flag.
                result.append(self.Flag.ESC)
                
                # Invert high bit.
                value ^= 0x80
            
            result.append(value)
        return result

    def _destuff(self, data):
        """! @brief Remove COM Encapsulation byte stuffing."""
        result = []
        i = 0
        while i < len(data):
            value = data[i]
            
            # Check for escaped bytes.
            if value == self.Flag.ESC:
                # Skip over escape.
                i += 1
                
                # Get escaped byte and invert high bit to destuff it.
                value = data[i] ^ 0x80
            
            result.append(value)
            
            i += 1
        return result

    def _read_packet_data_to_end(self):
        """! @brief Read an escaped packet from the first message byte to the end.
        @exception UnexpectedFlagError
        @exception TimeoutError
        """
        result = []
        while True:
            value = self._read1()
            
            # Check for the packet end marker flag.
            if value == self.Flag.END:
                break
            elif value == self.Flag.LPH2RL:
                # Target killed the connection in the middle of a packet. At least reply.
                self._write1(self.Flag.LPH2RL)
                return []
            elif value == self.Flag.LERR:
                # Received a link error flag.
                return []
            else:
                result.append(value)
            
        return self._destuff(result)

    def receive_packet(self):
        """! @brief Read an escaped packet.
        @exception UnexpectedFlagError
        @exception TimeoutError
        """
        self._expect_flag(self.Flag.START)
        return self._read_packet_data_to_end()
    
    def send_packet(self, data):
        """! @brief Send an escaped packet.
        @exception UnexpectedFlagError
        @exception TimeoutError
        """
        self._write1(self.Flag.START)
        for value in self._stuff(data):
            self._write1(value)
        self._write1(self.Flag.END)
    
    def open_link(self, phase):
        """! @brief Send the LPH1RA or LPH2RA flag.
        @exception UnexpectedFlagError
        @exception TimeoutError
        """
        if phase == self.LinkPhase.PHASE1:
            # Close link phase 1 first, to put it in a known state.
            self.close_link(self.LinkPhase.PHASE1)
        
            LOG.info("sending LPH1RA")
            self._write1(self.Flag.LPH1RA)
            self._expect_flag(self.Flag.LPH1RA)
        elif phase == self.LinkPhase.PHASE2:
            LOG.info("sending LPH2RA")
            self._write1(self.Flag.LPH2RA)
            self._expect_flag(self.Flag.LPH2RA)

    def close_link(self, phase):
        """! @brief Send the LPH1RL or LPH2RL flag.
        @exception UnexpectedFlagError
        @exception TimeoutError
        """
        if phase == self.LinkPhase.PHASE1:
            LOG.info("sending LPH1RL")
            self._write1(self.Flag.LPH1RL)
            self._expect_flag(self.Flag.LPH1RL)
        elif phase == self.LinkPhase.PHASE2:
            LOG.info("sending LPH2RL")
            self._write1(self.Flag.LPH2RL)
            self._expect_flag(self.Flag.LPH2RL)

    def _log_status(self):
        status = self.ap.read32(self.Register.SR)
        LOG.info("status=0x%08x", status)

    def read_protocol_id(self):
        """! @brief Read and return the 6-byte protocol ID.
        @exception UnexpectedFlagError
        @exception TimeoutError
        """
        self._write1(self.Flag.IDR)
        self._expect_flag(self.Flag.IDA)
        return self._read_packet_data_to_end()
    
    def send_reboot_request(self):
        """! @brief Send remote reboot request."""
        self._write1(self.Flag.LPH2RR)
    
    def __repr__(self):
        return "<SDC-600@{:x}: en={} txw={} rxw={}>".format(id(self),
            self._is_enabled, self._tx_width, self._rx_width)
        


