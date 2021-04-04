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

import argparse
import logging
from typing import List

from .base import SubcommandBase
from ..target import TARGET
from ..target.pack import pack_target
from ..core.session import Session
from ..core import exceptions
from ..utility.cmdline import (
    convert_session_options,
    )

class TargetInfoSubcommand(SubcommandBase):
    """! @brief `pyocd target` subcommand."""
    
    NAMES = ['info']
    HELP = "Access target information."
    DEFAULT_LOG_LEVEL = logging.WARNING

    @classmethod
    def get_args(cls) -> List[argparse.ArgumentParser]:
        """! @brief Add this subcommand to the subparsers object."""
        parser = argparse.ArgumentParser(description=cls.HELP, add_help=False)

        group = parser.add_argument_group("target options")
        group.add_argument('-H', '--no-header', action='store_true',
            help="Don't print table headers.")
        group.add_argument("target_type",
            help="The target type to examine.")
        
        return [cls.CommonOptions.COMMON, parser]
    
    def invoke(self) -> int:
        """! @brief Handle 'target info' subcommand."""
        # Create a probe-less session.
        session_options = convert_session_options(self._args.options)
        session = Session(probe=None,
                target_override=self._args.target_type,
                options=session_options)

        target_type = self._args.target_type.lower()

        # Create targets from provided CMSIS pack.
        if session.options['pack'] is not None:
            pack_target.PackTargets.populate_targets_from_pack(session.options['pack'])

        # Create targets from the cmsis-pack-manager cache.
        if target_type not in TARGET:
            pack_target.ManagedPacks.populate_target(target_type)

        # Look up the target class.
        try:
            target = TARGET[target_type](session)
        except KeyError as exc:
            raise exceptions.TargetSupportError(
                "Target type '%s' not recognized. Use 'pyocd list --targets' to see currently "
                "available target types. "
                "See <https://github.com/pyocd/pyOCD/blob/master/docs/target_support.md> "
                "for how to install additional target support." % target_type) from None
        
        print("Target:     ", target_type)
        print("Vendor:     ", target.vendor)
        print("Part number:", target.part_number)
        print("Memory map:")
        
        # Print memory map.
        pt = self._get_pretty_table(["Region", "Type", "Start", "End", "Size", "Access", "Sector", "Page"])
        for region in target.memory_map:
            pt.add_row([
                region.name,
                region.type.name.capitalize(),
                "0x%08x" % region.start,
                "0x%08x" % region.end,
                "0x%08x" % region.length,
                region.access,
                ("0x%08x" % region.sector_size) if region.is_flash else '-',
                ("0x%08x" % region.page_size) if region.is_flash else '-',
                ])
        print(pt)
        
        return 0

class TargetSubcommand(SubcommandBase):
    """! @brief `pyocd target` subcommand."""
    
    NAMES = ['target']
    HELP = "Target related commands."
    SUBCOMMANDS = [
        TargetInfoSubcommand,
        ]

    @classmethod
    def get_args(cls) -> List[argparse.ArgumentParser]:
        """! @brief Add this subcommand to the subparsers object."""
        parser = argparse.ArgumentParser(description=cls.HELP, add_help=False)
        cls.add_subcommands(parser)
        
        return [parser] #cls.CommonOptions.COMMON, cls.CommonOptions.CONNECT, parser]

