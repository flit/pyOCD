#!/usr/bin/env python3

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

import argparse
from importlib import import_module
from pathlib import Path
from typing import (Any, Dict, Iterator, List)

import pyocd
from pyocd.core.memory_map import MemoryRange

class FlashAlgoVerifyFailure(Exception):
    pass

FlashAlgoDict = Dict[str, Any]

def range_str(range: MemoryRange) -> str:
    return f"[{range.start:#010x}..{range.end:#010x}]"

class FlashAlgoVerifier:

    REQUIRED_ENTRY_POINTS = (
        'pc_init',
        'pc_program_page',
        'pc_erase_sector',
    )

    MINIMUM_STACK_SIZE = 256

    def __init__(self, module_name: str, name: str, algo: FlashAlgoDict) -> None:
        # print(f"Examining: {module_name}.{name}")
        self.module_name = module_name
        self.name = name
        self.algo = algo

        # Get layout values.
        try:
            self.load_addr = algo['load_address']
            self.instr_size = len(algo['instructions']) * 4
            self.instr_top = self.load_addr + self.instr_size
            self.instr_range = MemoryRange(start=self.load_addr, length=self.instr_size)
            self.static_base = algo['static_base']
            self.stack_top = algo['begin_stack']
            self.page_buffers = sorted(algo.get('page_buffers', [algo['begin_data']]))
        except KeyError as err:
            raise FlashAlgoVerifyFailure(f"flash algo dict missing required key: {err}") from None

        # Compute page size
        try:
            self.page_size = algo['page_size']
        except KeyError as err:
            if len(self.page_buffers) > 1:
                self.page_size = self.page_buffers[1] - self.page_buffers[0]
            else:
                print(f"Warning: page_size key is not available and unable to compute page size for {self.module_name}.{self.name}")
                self.page_size = 128

        # Collect entry points.
        self.entry_points = {
            k: v
            for k, v in algo.items()
            if k.startswith('pc_')
        }
        if not all((n in self.entry_points) for n in self.REQUIRED_ENTRY_POINTS):
            raise FlashAlgoVerifyFailure("flash algo dict missing required entry point")

    def verify(self) -> None:
        # Entry points must be within instructions.
        for name, addr in self.entry_points.items():
            is_disabled = (addr in (0, None))

            # Make sure required entry points are not disabled.
            if (name in self.REQUIRED_ENTRY_POINTS) and is_disabled:
                raise FlashAlgoVerifyFailure("required entry point '{name}' is disabled (value {addr})")

            # Verify entry points are either disabled or reside within the loaded address range.
            if not (is_disabled or self.instr_range.contains_address(addr)):
                raise FlashAlgoVerifyFailure(f"entry point '{name}' not within instructions {range_str(self.instr_range)}")

        # Static base should be within the instructions, since the instructions are supposed to contain
        # both rw and zi ready for loading.
        if not self.instr_range.contains_address(self.static_base):
            raise FlashAlgoVerifyFailure(f"static base {self.static_base:#010x} not within instructions {range_str(self.instr_range)}")

        # Verify stack basics.
        if self.instr_range.contains_address(self.stack_top):
            raise FlashAlgoVerifyFailure(f"stack top {self.stack_top:#010x} is within instructions {range_str(self.instr_range)}")

        buffers_top = self.page_buffers[-1] + self.page_size

        # Compute max stack size.
        if self.stack_top > self.instr_top and self.stack_top <= self.page_buffers[0]:
            stack_size = self.stack_top - self.instr_top
        elif self.stack_top > buffers_top:
            stack_size = self.stack_top - buffers_top
        else:
            stack_size = 0
            print(f"Warning: unable to compute stack size for {self.module_name}.{self.name}")

        stack_range = MemoryRange(start=(self.stack_top - stack_size), length=stack_size)

        # Minimum stack size.
        if (stack_size != 0) and (stack_size < self.MINIMUM_STACK_SIZE):
            raise FlashAlgoVerifyFailure(f"stack size {stack_size} is below minimum {self.MINIMUM_STACK_SIZE}")

        # Page buffers.
        for base_addr in self.page_buffers:
            buffer_range = MemoryRange(start=base_addr, length=self.page_size)

            if buffer_range.intersects_range(self.instr_range):
                raise FlashAlgoVerifyFailure(f"buffer {base_addr:#010x} overlaps instructsion {range_str(self.instr_range)}")
            if buffer_range.intersects_range(stack_range):
                raise FlashAlgoVerifyFailure(f"buffer {range_str(buffer_range)} overlaps stack {range_str(stack_range)}")


def collect_modules(dotted_path: str, dir_path: Path) -> Iterator[str]:
    """@brief Yield dotted names of all modules contained within the given package."""
    for entry in sorted(dir_path.iterdir(), key=lambda v: v.name):
        # Primitive tests for modules and packages.
        is_subpackage = (entry.is_dir() and (entry / "__init__.py").exists())
        is_module = entry.suffix == ".py"
        module_name = dotted_path + '.' + entry.stem

        # Yield this module's name.
        if is_module:
            yield module_name
        # Recursively yield modules from valid sub-packages.
        elif is_subpackage:
            for name in collect_modules(module_name, entry):
                yield name


def is_algo_dict(n: str, o: Any) -> bool:
    """@brief Test whether a dict contains a flash algo."""
    return (isinstance(o, Dict)
            and (n != '__builtins__')
            and 'instructions' in o
            and 'pc_program_page' in o)


def main() -> None:
    parser = argparse.ArgumentParser(description="Flash algo verifier")
    parser.add_argument("module", nargs='*', help="pyOCD module name containing flash algos to verify")
    args = parser.parse_args()

    pyocd_path = Path(pyocd.__file__).parent.resolve()
    # print(f"pyocd package path: {pyocd_path}")

    if not args.module:
        target_module_names = collect_modules('pyocd.target.builtin', pyocd_path / 'target' / 'builtin')
    else:
        target_module_names = args.module

    for module_name in target_module_names:
        # print(f"Importing: {module_name}")
        module = import_module(module_name)

        # Scan for algo dictionaries in the module. This assumes they are defined at the module level,
        # which is the case for all current targets.
        algos_iter = ((n, v) for n, v in module.__dict__.items() if is_algo_dict(n, v))

        for name, algo in algos_iter:
            try:
                FlashAlgoVerifier(module_name, name, algo).verify()
            except FlashAlgoVerifyFailure as err:
                print(f"Error: {module_name}.{name}: {err}")


if __name__ == "__main__":
    main()
