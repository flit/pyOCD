# pyOCD debugger
# Copyright (c) 2018-2020 Arm Limited
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

from ..utility import conversion

class MemoryInterface(object):
    """! @brief Interface for memory access."""

    def write_memory(self, addr, data, transfer_size=32, **kwargs):
        """! @brief Write a single memory location.
        
        By default the transfer size is a word."""
        raise NotImplementedError()
        
    def read_memory(self, addr, transfer_size=32, now=True, **kwargs):
        """! @brief Read a memory location.
        
        By default, a word will be read."""
        raise NotImplementedError()

    def write_memory_block32(self, addr, data, **kwargs):
        """! @brief Write an aligned block of 32-bit words."""
        raise NotImplementedError()

    def read_memory_block32(self, addr, size, **kwargs):
        """! @brief Read an aligned block of 32-bit words."""
        raise NotImplementedError()
  
    def write64(self, addr, value, **kwargs):
        """! @brief Shorthand to write a 64-bit word."""
        self.write_memory(addr, value, 64, **kwargs)
  
    def write32(self, addr, value, **kwargs):
        """! @brief Shorthand to write a 32-bit word."""
        self.write_memory(addr, value, 32, **kwargs)

    def write16(self, addr, value, **kwargs):
        """! @brief Shorthand to write a 16-bit halfword."""
        self.write_memory(addr, value, 16, **kwargs)

    def write8(self, addr, value, **kwargs):
        """! @brief Shorthand to write a byte."""
        self.write_memory(addr, value, 8, **kwargs)

    def read64(self, addr, now=True, **kwargs):
        """! @brief Shorthand to read a 64-bit word."""
        return self.read_memory(addr, 64, now, **kwargs)

    def read32(self, addr, now=True, **kwargs):
        """! @brief Shorthand to read a 32-bit word."""
        return self.read_memory(addr, 32, now, **kwargs)

    def read16(self, addr, now=True, **kwargs):
        """! @brief Shorthand to read a 16-bit halfword."""
        return self.read_memory(addr, 16, now, **kwargs)

    def read8(self, addr, now=True, **kwargs):
        """! @brief Shorthand to read a byte."""
        return self.read_memory(addr, 8, now, **kwargs)

    def read_memory_block8(self, addr, size, **kwargs):
        """! @brief Read a block of unaligned bytes in memory.
        @return an array of byte values
        """
        res = []

        # try to read 8bits data
        if (size > 0) and (addr & 0x01):
            mem = self.read8(addr, **kwargs)
            res.append(mem)
            size -= 1
            addr += 1

        # try to read 16bits data
        if (size > 1) and (addr & 0x02):
            mem = self.read16(addr, **kwargs)
            res.append(mem & 0xff)
            res.append((mem >> 8) & 0xff)
            size -= 2
            addr += 2

        # try to read aligned block of 32bits
        if (size >= 4):
            mem = self.read_memory_block32(addr, size // 4, **kwargs)
            res += conversion.u32le_list_to_byte_list(mem)
            size -= 4*len(mem)
            addr += 4*len(mem)

        if (size > 1):
            mem = self.read16(addr, **kwargs)
            res.append(mem & 0xff)
            res.append((mem >> 8) & 0xff)
            size -= 2
            addr += 2

        if (size > 0):
            mem = self.read8(addr, **kwargs)
            res.append(mem)

        return res

    def write_memory_block8(self, addr, data, **kwargs):
        """! @brief Write a block of unaligned bytes in memory."""
        size = len(data)
        idx = 0

        #try to write 8 bits data
        if (size > 0) and (addr & 0x01):
            self.write8(addr, data[idx], **kwargs)
            size -= 1
            addr += 1
            idx += 1

        # try to write 16 bits data
        if (size > 1) and (addr & 0x02):
            self.write16(addr, data[idx] | (data[idx+1] << 8), **kwargs)
            size -= 2
            addr += 2
            idx += 2

        # write aligned block of 32 bits
        if (size >= 4):
            data32 = conversion.byte_list_to_u32le_list(data[idx:idx + (size & ~0x03)])
            self.write_memory_block32(addr, data32, **kwargs)
            addr += size & ~0x03
            idx += size & ~0x03
            size -= size & ~0x03

        # try to write 16 bits data
        if (size > 1):
            self.write16(addr, data[idx] | (data[idx+1] << 8), **kwargs)
            size -= 2
            addr += 2
            idx += 2

        #try to write 8 bits data
        if (size > 0):
            self.write8(addr, data[idx], **kwargs)

