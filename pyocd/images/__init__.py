# pyOCD debugger
# Copyright (c) 2021 Chris Reed
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

from .binary_image import BinaryImageFile
from .elf_image import ElfImageFile
from .ihex_image import IntelHexImageFile

FORMAT_HANDLERS = {
    'axf': ElfImageFile,
    'bin': BinaryImageFile,
    'elf': ElfImageFile,
    'hex': IntelHexImageFile,
    }

#def open_image(path):
