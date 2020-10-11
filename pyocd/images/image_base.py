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
from enum import IntFlag
from typing import (Iterator, Optional)

from ..core import (
    exceptions,
    memory_map,
    )
from ..utility.types import (
    BinaryData,
    FileOrPath,
    )

LOG = logging.getLogger(__name__)


class ImageChunk:
    """@brief Base class for a contiguous piece of data from a loadable image file.
    """

    class ImageChunkFlag(IntFlag):
        READ = 1
        WRITE = 2
        EXEC = 4

    def __init__(self, image: "ImageFileBase", data: BinaryData):
        self._image = image
        self._data = data
        self._flags: "ImageChunk.ImageChunkFlag" = self.ImageChunkFlag(0)

    @property
    def has_base_address(self) -> bool:
        return False

    @property
    def image(self) -> "ImageFileBase":
        """@brief The parent image file."""
        return self._image

    @property
    def data(self) -> BinaryData:
        """@brief Bytes-like object holding the data from this chunk ."""
        return self._data


class BasedImageChunk(ImageChunk, memory_map.MemoryRangeBase):
    """@brief Base class for a contiguous piece of data from a loadable image file.
    """

    def __init__(self, image: "ImageFileBase", data: BinaryData):
        self._image = image
        self._data = data


class ImageFileBase:
    """@brief Base class for loadable image file formats.
    """
    def __init__(self, image_file: FileOrPath):#, session: Session):
        """@brief Constructor.

        @param self This object.
        @param image_file File-like object.
        @param session The session object.
        """
        self._file = image_file
#         self._session = session
        self._chunks = []

    def iter_chunks(self) -> Iterator[ImageChunk]:
        """@brief Iterator for ImageChunk objects."""
        raise NotImplementedError()




