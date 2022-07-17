# pyOCD debugger
# Copyright (c) 2018-2019 Arm Limited
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

from __future__ import annotations

from typing import (TYPE_CHECKING, Optional, cast)

from ..utility.graph import GraphNode

if TYPE_CHECKING:
    from ..core.memory_interface import MemoryInterface
    from .rom_table import CoreSightComponentID

class CoreSightComponent(GraphNode):
    """@brief CoreSight component base class."""

    @classmethod
    def factory(cls, ap: MemoryInterface, cmpid: CoreSightComponentID, address: Optional[int]):
        """@brief Common CoreSightComponent factory."""
        cmp = cls(ap, cmpid, address)
        if hasattr(ap, 'core') and ap.core: # type:ignore
            ap.core.add_child(cmp) # type:ignore
        return cmp

    def __init__(
            self,
            ap: MemoryInterface,
            cmpid: Optional[CoreSightComponentID] = None,
            addr: Optional[int]=None
            ) -> None:
        """@brief Constructor."""
        super().__init__()
        self._ap = ap
        self._cmpid = cmpid
        address = addr if (addr is not None) else (cast(int, cmpid.address) if cmpid else None)
        assert address is not None
        self._address = address

    @property
    def ap(self) -> MemoryInterface:
        return self._ap

    @property
    def cmpid(self) -> Optional[CoreSightComponentID]:
        return self._cmpid

    @cmpid.setter
    def cmpid(self, newCmpid: CoreSightComponentID) -> None:
        self._cmpid = newCmpid

    @property
    def address(self) -> int:
        return self._address

    @address.setter
    def address(self, newAddr: int) -> None:
        self._address = newAddr

class CoreSightCoreComponent(CoreSightComponent):
    """@brief CoreSight component for a CPU core.

    This class serves only as a superclass for identifying core-type components.
    """
    pass
