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

from ..core import exceptions
from .image_base import (
    ImageChunk,
    ImageFileBase,
    )

LOG = logging.getLogger(__name__)


class ElfImageFile(ImageFileBase):
    """@brief Base class for loadable image file formats.
    """
    def __init__(self, image_file, session):
        """@brief Constructor.

        @param self This object.
        @param image_file File-like object.
        @param session The session object.
        """
        self._file = image_file
        self._session = session
        self._chunks = []

    def iter_chunks(self):
        """@brief Iterator for ImageChunk objects."""
        raise NotImplementedError()


