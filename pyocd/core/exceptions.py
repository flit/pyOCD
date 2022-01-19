# pyOCD debugger
# Copyright (c) 2018-2020 Arm Limited
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

from typing import (Any, Optional)

class Error(RuntimeError):
    """@brief Parent of all errors pyOCD can raise"""
    pass

class InternalError(Error):
    """@brief Internal consistency or logic error.

    This error indicates that something has happened that shouldn't be possible.
    """
    pass

class TimeoutError(Error):
    """@brief Any sort of timeout"""
    pass

class TargetSupportError(Error):
    """@brief Error related to target support"""
    pass

class ProbeError(Error):
    """@brief Error communicating with the debug probe"""
    pass

class ProbeDisconnected(ProbeError):
    """@brief The connection to the debug probe was lost"""
    pass

class TargetError(Error):
    """@brief An error that happens on the target"""
    pass

class DebugError(TargetError):
    """@brief Error controlling target debug resources"""
    pass

class CoreRegisterAccessError(DebugError):
    """@brief Failure to read or write a core register."""
    pass

class TransferError(DebugError):
    """@brief Error ocurred with a transfer over SWD or JTAG"""
    pass

class TransferTimeoutError(TransferError):
    """@brief An SWD or JTAG timeout occurred"""
    pass

class TransferFaultError(TransferError):
    """@brief A transfer fault occurred.

    This exception class is extended to optionally record the destination resource (memory/AP), start address,
    optional length, and operation (read/write) of the attempted transfer that caused the fault. The metadata,
    if available, will be included in the description of the exception when it is converted to a string.

    Positional arguments passed to the constructor are passed through to the superclass' constructor, and thus
    operate like any other standard exception class. Keyword arguments of 'resource', 'fault_address', 'length',
    and 'operation' can optionally be passed to the constructor to initialize the fault start address and length.
    Alternatively, the corresponding property setters can be used after the exception is created.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """@brief Constructor.

        Accepts these keyword arguments to set transfer metadata:
        - `resource`
        - `fault_address`
        - `length`
        - `operation`
        """
        super().__init__(*args)
        self._resource: Optional[str] = kwargs.get('resource', None)
        self._operation: Optional[str] = kwargs.get('operation', None)
        self._address: Optional[int] = kwargs.get('fault_address', None)
        self._length: Optional[int] = kwargs.get('length', None)

    @property
    def resource(self) -> Optional[str]:
        return self._resource

    @resource.setter
    def resource(self, value: str) -> None:
        self._resource = value

    @property
    def operation(self) -> Optional[str]:
        return self._operation

    @operation.setter
    def operation(self, value: str) -> None:
        self._operation = value

    @property
    def fault_address(self) -> Optional[int]:
        return self._address

    @fault_address.setter
    def fault_address(self, addr: int) -> None:
        self._address = addr

    @property
    def fault_end_address(self) -> Optional[int]:
        if (self._address is not None) and (self._length is not None):
            return self._address + self._length - 1
        else:
            return self._address

    @property
    def fault_length(self) -> Optional[int]:
        return self._length

    @fault_length.setter
    def fault_length(self, length: int) -> None:
        self._length = length

    def __str__(self) -> str:
        if self.operation is not None:
            if self.resource is not None:
                desc = f"{self.resource.capitalize()} {self.operation} fault"
            else:
                desc = f"{self.operation.capitalize()} fault"
        else:
            if self.resource is not None:
                desc = f"{self.resource.capitalize()} fault"
            else:
                desc = "Transfer fault"
        if self.args:
            if len(self.args) == 1:
                desc += f" ({self.args[0]})"
            else:
                desc += f" {self.args}"
        if self._address is not None:
            desc += f" @ {self.fault_address:#010x}"
            if self._length is not None:
                desc += f"-{self.fault_end_address:#010x}"
        return desc

class FlashFailure(TargetError):
    """@brief Exception raised when flashing fails for some reason.

    Positional arguments passed to the constructor are passed through to the superclass'
    constructor, and thus operate like any other standard exception class. The flash address that
    failed and/or result code from the algorithm can optionally be recorded in the exception, if
    passed to the constructor as 'address' and 'result_code' keyword arguments.
    """
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args)
        self._address: Optional[int] = kwargs.get('address', None)
        self._result_code: Optional[int] = kwargs.get('result_code', None)
        self._operation: Optional[str] = kwargs.get('operation', None)

    @property
    def address(self) -> Optional[int]:
        return self._address

    @property
    def result_code(self) -> Optional[int]:
        return self._result_code

    @property
    def operation(self) -> Optional[str]:
        return self._operation

    def __str__(self) -> str:
        desc = super().__str__()
        parts = []
        if self.operation is not None:
            parts.append(f"{self.operation} operation")
        if self.address is not None:
            parts.append(f"address {self.address:#010x}")
        if self.result_code is not None:
            parts.append(f"result code {self.result_code:#x}")
        if parts:
            if desc:
                desc += " "
            desc += "(%s)" % ("; ".join(parts))
        return desc

class FlashEraseFailure(FlashFailure):
    """@brief An attempt to erase flash failed. """
    pass

class FlashProgramFailure(FlashFailure):
    """@brief An attempt to program flash failed. """
    pass

class CommandError(Error):
    """@brief Raised when a command encounters an error."""
    pass

class RTTError(Error):
    """@brief Error encountered when transfering data through RTT."""
    pass

