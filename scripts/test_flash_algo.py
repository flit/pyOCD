#!/usr/bin/env python3
# pyOCD debugger
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
from __future__ import annotations
import argparse
import logging
from random import randbytes
import sys
from typing import cast, Optional
from pyocd.core.memory_map import MemoryRegion, MemoryType
from pyocd.core.session import Session
from pyocd.core.helpers import ConnectHelper
from pyocd.utility.color_log import build_color_logger
from pyocd.utility.cmdline import convert_frequency
from pyocd.target.pack.flash_algo import PackFlashAlgo
from pyocd.flash.flash import Flash
from pyocd.utility.mask import same

LOG = logging.getLogger(__name__)

class FlashAlgoTestCase:
    NAME: str = "!base class!"

    def __init__(self, tester: FlashAlgoTester) -> None:
        self._tester = tester

    @property
    def target(self):
        return self._tester.target

    @property
    def region(self):
        return self._tester.region

    @property
    def flash(self):
        return self._tester.flash

    @property
    def test_size(self):
        return self._tester.test_size

    @property
    def sector_size(self):
        return self._tester._sector_size

    @property
    def sector_count(self):
        return self._tester._sector_count

    @property
    def page_size(self):
        return self._tester._page_size

    @property
    def page_count(self):
        return self._tester._page_count

    def run(self) -> bool:
        raise NotImplementedError()

class ChipEraseTest(FlashAlgoTestCase):
    NAME = "chip erase"

    def run(self) -> bool:
        return True

class SectorEraseTest(FlashAlgoTestCase):
    NAME = "sector erase"

    def run(self) -> bool:
        did_pass = True

        # Fill all pages with random data.
        self._tester.prep_pages()

        for sector in range(self.sector_count):
            LOG.info("testing erase sector %d", sector)
            self.flash.init(address=self.region.start, operation=Flash.Operation.ERASE)
            self.flash.erase_sector(self._tester.sector_to_address(sector))

            actual_erased_sectors = self.find_erased_sectors()

            if actual_erased_sectors != [sector]:
                LOG.error("erroneously erased sector(s) %s instead of %d", actual_erased_sectors, sector)
                did_pass = False
            else:
                LOG.info("successfully erased sector %d", sector)

            for erased_sector in actual_erased_sectors:
                LOG.info("reprogrammed erased sector %d", erased_sector)
                self._tester.fill_sector(erased_sector)

        return did_pass

    def find_erased_sectors(self) -> list[int]:
        result: list[int] = []
        for sector in range(self.sector_count):
            if self._tester.is_sector_erased(sector):
                result.append(sector)
        return result

class FlashAlgoTester:
    """@brief Runs a series of flash programming algorithm tests over a memory region.

    Only one sector size is supported by a given instance of this class. (For now, at least.)

    Tests performed:
    - Chip erase.
    """

    TEST_CASE_CLASSES = [
        SectorEraseTest,
    ]

    QUICK_READ_LENGTH = 32

    def __init__(
            self,
            session: Session,
            algo: PackFlashAlgo,
            region: MemoryRegion,
            ram_region: MemoryRegion,
            debug_mode: bool,
        ) -> None:
        self._session = session
        target = session.target
        assert target
        self._target = target
        self._region = region
        self._algo = algo
        self._debug_mode = debug_mode

        if len(self._algo.sector_sizes) > 1:
            LOG.warning("flash algo specifies more than one section size, which is currently not supported by this tool; only the first size will be tested")
            self._test_size = cast(int, self._algo.sector_sizes[1][0])
        else:
            self._test_size = self._region.length
        self._sector_size = self._algo.sector_sizes[0][1]
        self._sector_count = self._test_size // self._sector_size
        self._page_size = self._algo.page_size
        self._page_count = self._test_size // self._page_size
        self._pages_per_sector = self._sector_size // self._page_size

        LOG.info("test memory size: %u KiB", self._test_size // 1024)
        LOG.info("sectors: %u bytes × %u sectors", self._sector_size, self._sector_count)
        LOG.info("pages: %u bytes × %u pages, %u pages per sector", self._page_size, self._page_count,
            self._pages_per_sector)

        LOG.info("algo data size: %u", len(self._algo.algo_data))
        LOG.info("loading algo to %s", ram_region)

        self._algo_dict = self._algo.get_pyocd_flash_algo(
                                    blocksize=self._sector_size,
                                    ram_region=ram_region)
        if self._algo_dict is None:
            raise RuntimeError("failed to create flash algo dict")
        self._flash = Flash(self._target, self._algo_dict)
        self._flash.region = self._region
        if debug_mode:
            self._flash.flash_algo_debug = True

        self._erased_page_data = b"\xff" * self.page_size
        self._current_page_data: dict[int, bytes] = {p: b"" for p in range(self.page_count)}

    @property
    def target(self):
        return self._target

    @property
    def region(self):
        return self._region

    @property
    def flash(self):
        return self._flash

    @property
    def test_size(self):
        return self._test_size

    @property
    def sector_size(self):
        return self._sector_size

    @property
    def sector_count(self):
        return self._sector_count

    @property
    def page_size(self):
        return self._page_size

    @property
    def page_count(self):
        return self._page_count

    def run_test(self) -> bool:
        results: dict[str, bool] = {}
        for case_class in self.TEST_CASE_CLASSES:
            case_name = case_class.NAME
            LOG.info("running test case '%s'", case_name)
            test_case = case_class(self)
            try:
                did_pass = test_case.run()
            except Exception as exc:
                LOG.error("exception running test case '%s': %s", case_name, exc, exc_info=True)
                did_pass = False
            results[case_name] = did_pass

        LOG.info("test results:")
        for case_name, did_pass in results.items():
            passed_str = ("failed", "passed")[did_pass]
            LOG.info("%s: %s", case_name, passed_str)
        return True

    def sector_to_address(self, sector: int) -> int:
        return self._region.start + sector * self.sector_size

    def page_to_address(self, page: int) -> int:
        return self._region.start + page * self.page_size

    def page_to_sector(self, page: int) -> int:
        return (page * self.page_size) // self.sector_size

    def sector_to_page(self, sector: int) -> int:
        return (sector * self.sector_size) // self.page_size

    def page_range_for_sector(self, sector: int):
        first_page = self.sector_to_page(sector)
        return range(first_page, first_page + (self.sector_size // self.page_size))

    def is_sector_erased(self, sector: int, quick: bool = False) -> bool:
        addr = self.sector_to_address(sector)
        read_length = min(self.QUICK_READ_LENGTH, self.sector_size) if quick else self.sector_size
        data = self.target.read_memory_block8(addr, read_length)
        is_erased = self.region.is_data_erased(data)
        if is_erased:
            for page in self.page_range_for_sector(sector):
                self._current_page_data[page] = self._erased_page_data
        return is_erased

    def check_page(self, page: int, quick: bool = False) -> bool:
        addr = self.page_to_address(page)
        read_length = min(self.QUICK_READ_LENGTH, self.page_size) if quick else self.page_size
        data = self.target.read_memory_block8(addr, read_length)
        return same(data, self._current_page_data[page][:read_length])

    def erase_all(self) -> None:
        LOG.info("erase all")

        self.flash.init(address=self.region.start, operation=Flash.Operation.ERASE)
        self.flash.erase_all()
        self.flash.uninit()

        LOG.info("completed erase all")

        self._current_page_data = {p: self._erased_page_data for p in range(self.page_count)}

        unerased_sectors: list[int] = []
        for sector in range(self.sector_count):
            if not self.is_sector_erased(sector, quick=True):
                unerased_sectors.append(sector)
        if unerased_sectors:
            LOG.error("erase all failed to erase sectors %s", unerased_sectors)

    def prep_pages(self) -> None:
        self.erase_all()

        LOG.info("filling %d pages", self.page_count)
        for page in range(self.page_count):
            self.fill_page(page)
        LOG.info("finished filling pages")

    def fill_page(self, page: int) -> None:
        self.flash.init(address=self.region.start, operation=Flash.Operation.PROGRAM)
        data = randbytes(self.page_size)
        self._current_page_data[page] = data
        self.flash.program_page(self.page_to_address(page), data)

        if not self.check_page(page, quick=True):
            LOG.error("failed to program page %d, read-back does not match", page)

    def fill_sector(self, sector: int) -> None:
        for page in self.page_range_for_sector(sector):
            self.fill_page(page)

class FlashAlgoTesterTool:
    def __init__(self) -> None:
        self._parser = self._build_args()
        self._args = self._parser.parse_args()

    def _build_args(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="Flash algo tester")
        parser.add_argument("algo_path", help="Elf, axf, or flm for the flash algo.")
        parser.add_argument("-u", "--probe", metavar="ID", help="Debug probe unique ID.")
        parser.add_argument("-t", "--target", metavar="TARGET",
            help="Set the target type.")
        parser.add_argument("-f", "--frequency", dest="frequency", default=None, type=convert_frequency,
            help="SWD/JTAG clock frequency in Hz. Accepts a float or int with optional case-"
                "insensitive K/M suffix and optional Hz. Examples: \"1000\", \"2.5khz\", \"10m\".")
        parser.add_argument("--debug-mode", action="store_true", help="Set flash algo debug mode.")
        parser.add_argument("-r", "--ram", metavar="ADDR", default=None, help="Use RAM region at this address to hold algo. Uses default RAM region if not specified.")
        return parser

    def run(self) -> int:
        build_color_logger(level=logging.INFO)

        algo = PackFlashAlgo(self._args.algo_path)
        LOG.info("%s", algo.flash_info)

        try:
            session = ConnectHelper.session_with_chosen_probe(
                                unique_id=self._args.probe,
                                target_override=self._args.target,
                                frequency=self._args.frequency,
                                blocking=False)
            if session is None:
                LOG.error("No target device available")
                return 1
            with session:
                target = session.target
                assert target

                # Look up the algo's memory region.
                region = target.memory_map.get_region_for_address(algo.flash_start)
                if region is None:
                    raise RuntimeError(f"no memory region found for flash algo start address {algo.flash_start:#010x}")

                # Use either default RAM or the one specified by the region address arg.
                if self._args.ram is None:
                    ram_region = target.memory_map.get_default_region_of_type(MemoryType.RAM)
                    if not ram_region:
                        raise RuntimeError("target has no default RAM region")
                else:
                    ram_region_addr = int(self._args.ram, base=0)
                    ram_region = target.memory_map.get_region_for_address(ram_region_addr)
                    if not ram_region:
                        raise RuntimeError(f"no RAM region at address {ram_region_addr:#010x}")
                    if ram_region.type != MemoryType.RAM:
                        raise RuntimeError(f"memory region at address {ram_region_addr:#010x} is not RAM (it's {ram_region.type.name})")

                tester = FlashAlgoTester(session, algo, region, ram_region, self._args.debug_mode)
                did_pass = tester.run_test()
                if not did_pass:
                    return 1
        except RuntimeError as err:
            LOG.error("Error: %s", err)
            return 2

        return 0

if __name__ == "__main__":
    sys.exit(FlashAlgoTesterTool().run())

