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
from os import PathLike
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


class BinaryImageFile(ImageFileBase):
    """@brief Image file class for simple binary files.
    """
    def __init__(self, image_file: FileOrPath):
        """@brief Constructor.

        @param self This object.
        @param image_file File-like object or path.
        """
        super().__init__(image_file)

        # Read the binary file's contents.
        if isinstance(image_file, str):
            with open(image_file, 'rb') as file_obj:
                data = file_obj.read()
        else:
            data = image_file.read()

        self._data: bytes = data

    def iter_chunks(self) -> Iterator[ImageChunk]:
        """@brief Iterator for ImageChunk objects."""
        yield ImageChunk(self, self._data)

