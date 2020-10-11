# pyOCD debugger
# Copyright (c) 2021-2022 Chris Reed
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
from intelhex import IntelHex
import itertools
from typing import (Iterator, List, Tuple)

from ..core import (
    exceptions,
    memory_map,
    )
from .image_base import (
    ImageChunk,
    ImageFileBase,
    )
from ..utility.types import (
    BinaryData,
    FileOrPath,
    )

LOG = logging.getLogger(__name__)


def ranges(i: List[int]) -> List[Tuple[int, int]]:
    """
    Accepts a sorted list of byte addresses. Breaks the addresses into contiguous ranges.
    Yields 2-tuples of the start and end address for each contiguous range.

    For instance, the input [0, 1, 2, 3, 32, 33, 34, 35] will yield the following 2-tuples:
    (0, 3) and (32, 35).
    """
    for a, b in itertools.groupby(enumerate(i), lambda x: x[1] - x[0]):
        b = list(b)
        yield b[0][1], b[-1][1]


class IntelHexImageFile(ImageFileBase):
    """@brief Image file class for Intel Hex format.
    """
    def __init__(self, image_file: FileOrPath):
        """@brief Constructor.

        @param self This object.
        @param image_file File-like object.
        @param session The session object.
        """
        super().__init__(image_file)
        self._hexfile = IntelHex(image_file)

        # Get list of address range pairs.
        addresses = self._hexfile.addresses()
        addresses.sort()
        self._range_list = list(ranges(addresses))

    def iter_chunks(self) -> Iterator[ImageChunk]:
        """@brief Iterator for ImageChunk objects."""
        for start, end in self._range_list:
            size = end - start + 1
            data_array = self._hexfile.tobinarray(start=start, size=size)
            data = ImageChunk(self, bytes(data_array))
            yield data

