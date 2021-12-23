# pyOCD debugger
# Copyright (c) 2020 NXP
# Copyright (c) 2006-2018 Arm Limited
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

import logging
from time import sleep
from typing import (Callable, TYPE_CHECKING, cast)

from ...coresight import ap
from ...coresight.cortex_m import CortexM
from ...core import exceptions
from ...core.memory_map import (MemoryType, RamRegion)
from ...core.target import Target
from ...coresight.coresight_target import CoreSightTarget
from ...utility.timeout import Timeout
from ..pack.flash_algo import PackFlashAlgo

if TYPE_CHECKING:
    from ...coresight.rom_table import CoreSightComponentID
    from ...coresight.ap import AccessPort

MDM_STATUS = 0x00000000
MDM_CTRL = 0x00000004
MDM_IDR = 0x000000fc

MDM_STATUS_FLASH_MASS_ERASE_ACKNOWLEDGE = (1 << 0)
MDM_STATUS_FLASH_READY = (1 << 1)
MDM_STATUS_SYSTEM_SECURITY = (1 << 2)
MDM_STATUS_MASS_ERASE_ENABLE = (1 << 5)
MDM_STATUS_CORE_HALTED = (1 << 16)

MDM_CTRL_FLASH_MASS_ERASE_IN_PROGRESS = (1 << 0)
MDM_CTRL_DEBUG_REQUEST = (1 << 2)
MDM_CTRL_SYSTEM_RESET_REQUEST = (1 << 3)
MDM_CTRL_CORE_HOLD_RESET = (1 << 4)

MDM_IDR_EXPECTED = 0x001c0000
MDM_IDR_VERSION_MASK = 0xf0
MDM_IDR_VERSION_SHIFT = 4

HALT_TIMEOUT = 2.0
MASS_ERASE_TIMEOUT = 10.0
FLASH_INIT_TIMEOUT = 1.0

ACCESS_TEST_ATTEMPTS = 10

LOG = logging.getLogger(__name__)

class Kinetis(CoreSightTarget):
    """@brief Family class for NXP Kinetis devices.

    This family class serves several functions:

    - Support unlocking of protected devices via mass erase.
    - For DFP based targets, ensure that FlexRAM is not selected as the memory to be used for running
      flash algorithms.
    - Workarounds for the issues described below.

    The Kinetis devices have a peculiar design attribute that causes some trouble. When the core enters
    lockup, the reset controller is hard-wired to automatically reset, similar to a watchdog. That may
    be fine for production applications, but when flash is empty and the device doesn't have a boot ROM,
    it causes difficult to control behaviour. Basically, the chip tries to boot, immediately enters lockup,
    this triggers a reset, and it starts over.

    Immediately after reset asserts, the flash controller (itself a small 16-bit proprietary RISC CPU) begins
    to initialise. During this brief time, device security is forcibly enabled, the device reads as locks,
    and the CPU's debug interface cannot be accessed. It is only disabled once the flash controller
    completes its boot and initialisation process and can read the flash configuration field (FCF, located
    at address 0x400) that contains the security control flag.

    Depending on exactly when the debugger reads the MDM-AP status register to check whether security is
    enabled, a blank, unlocked device may be detected as locked. There is also the possibility that the
    device will be (correctly) detected as unlocked, but it resets again before the core can be halted, thus
    causing connect to fail.
    """

    VENDOR = "NXP"

    mdm_ap: "AccessPort"

    def __init__(self, session, memory_map=None):
        super().__init__(session, memory_map)
        self._force_connect_under_reset = False

    def create_init_sequence(self):
        seq = super().create_init_sequence()

        seq.wrap_task('discovery',  lambda seq: \
                                        seq.insert_before('find_components',
                                            ('check_mdm_ap_idr',        self.check_mdm_ap_idr),
                                            ('check_flash_security',    self.check_flash_security),
                                            ))

        return seq

    def check_mdm_ap_idr(self):
        if not self.dp.aps:
            LOG.debug('Not found valid aps, skip MDM-AP check.')
            return

        self.mdm_ap = self.dp.aps[1]

        # Check MDM-AP ID.
        assert self.mdm_ap.idr is not None
        if (self.mdm_ap.idr & ~MDM_IDR_VERSION_MASK) != MDM_IDR_EXPECTED:
            LOG.error("%s: bad MDM-AP IDR (is 0x%08x)", self.part_number, self.mdm_ap.idr)

        self.mdm_ap_version = (self.mdm_ap.idr & MDM_IDR_VERSION_MASK) >> MDM_IDR_VERSION_SHIFT
        LOG.debug("MDM-AP version %d", self.mdm_ap_version)

    def check_flash_security(self):
        """@brief Check security and unlock device.

        This init task determines whether the device is locked (flash security enabled). If it is,
        and if auto unlock is enabled, it then perform a mass erase to unlock the device. This whole
        sequence is greatly complicated by the behaviour described in the class documentation.

        This init task runs *before* cores are created.
        """
        if not self.dp.aps:
            return

        # check for flash security
        isLocked = self.is_locked()

        # No need to do any of these extra tests if we're already connecting under reset.
        if self.session.options.get('connect_mode') != 'under-reset':
            # Test whether we can reliably access the memory and the core. This test can fail if flash
            # is blank and the device is auto-resetting.
            if isLocked:
                canAccess = False
            else:
                try:
                    # Ensure to use AP#0 as a MEM_AP
                    if isinstance(self.aps[0], ap.MEM_AP):
                        for attempt in range(ACCESS_TEST_ATTEMPTS):
                            self.aps[0].read32(CortexM.DHCSR)
                except exceptions.TransferError:
                    LOG.debug("Access test failed with fault")
                    canAccess = False
                else:
                    canAccess = True

            # Verify locked status under reset. We only want to assert reset if the device looks locked
            # or accesses fail, otherwise we could not support attach mode debugging.
            if not canAccess:
                LOG.warning("Forcing connect under reset in order to gain control of device")
                self._force_connect_under_reset = True
                self.session.options.set('connect_mode', 'under-reset')

                # Keep the target in reset until is had been erased and halted. It will be deasserted
                # later, in perform_halt_on_connect().
                #
                # Ideally we would use the MDM-AP to hold the device in reset, but SYSTEM_RESET_REQUEST
                # cannot be written in MDM_CTRL when the device is locked in MDM-AP version 0.
                self.dp.assert_reset(True)

                # Re-read locked status under reset.
                isLocked = self.is_locked()

        # Only do a mass erase if the device is actually locked.
        if isLocked:
            if self.session.options.get('auto_unlock'):
                LOG.warning("%s in secure state: will try to unlock via mass erase", self.part_number)

                # Do the mass erase.
                if not self.mass_erase():
                    self.dp.assert_reset(False)
                    self.mdm_ap.write_reg(MDM_CTRL, 0)
                    LOG.error("%s: mass erase failed", self.part_number)
                    raise exceptions.TargetError("unable to unlock device")
            else:
                LOG.warning("%s in secure state: not automatically unlocking", self.part_number)
        else:
            LOG.info("%s not in secure state", self.part_number)

    def _enable_mdm_halt(self):
        LOG.info("Configuring MDM-AP to halt when coming out of reset")

        # Prevent the target from resetting if it has invalid code
        with Timeout(HALT_TIMEOUT) as to:
            while to.check():
                self.mdm_ap.write_reg(MDM_CTRL, MDM_CTRL_DEBUG_REQUEST | MDM_CTRL_CORE_HOLD_RESET)
                if ((self.mdm_ap.read_reg(MDM_CTRL) & (MDM_CTRL_DEBUG_REQUEST | MDM_CTRL_CORE_HOLD_RESET))
                        == (MDM_CTRL_DEBUG_REQUEST | MDM_CTRL_CORE_HOLD_RESET)):
                    break
            else:
                raise exceptions.TimeoutError("Timed out attempting to set DEBUG_REQUEST and CORE_HOLD_RESET in MDM-AP")

    def _disable_mdm_halt(self):
        # Disable holding the core in reset, leave MDM halt on
        self.mdm_ap.write_reg(MDM_CTRL, MDM_CTRL_DEBUG_REQUEST)

        # Wait until the target is halted
        LOG.debug("Waiting for mdm halt")
        with Timeout(HALT_TIMEOUT) as to:
            while to.check():
                if self.mdm_ap.read_reg(MDM_STATUS) & MDM_STATUS_CORE_HALTED == MDM_STATUS_CORE_HALTED:
                    LOG.debug("MDM halt completed")
                    break
                sleep(0.01)
            else:
                raise exceptions.TimeoutError("Timed out waiting for core to halt")

        # release MDM halt once it has taken effect in the DHCSR
        self.mdm_ap.write_reg(MDM_CTRL, 0)

    # def perform_halt_on_connect(self):
    #     """This init task runs *after* cores are created."""
    #     if not self.mdm_ap:
    #         super().perform_halt_on_connect()
    #         return

    #     if self.session.options.get('connect_mode') == 'under-reset' or self._force_connect_under_reset:
    #         # Configure the MDM-AP to hold the core in reset and halt.
    #         self._enable_mdm_halt()

    #         # Enable debug
    #         # self.aps[0].write_memory(CortexM.DHCSR, CortexM.DBGKEY | CortexM.C_DEBUGEN)

    #     else:
    #         super().perform_halt_on_connect()

    # def post_connect(self):
    #     if not self.mdm_ap:
    #         super().perform_halt_on_connect()
    #         return

    #     if self.session.options.get('connect_mode') == 'under-reset' or self._force_connect_under_reset:
    #         # We can now deassert reset.
    #         LOG.info("Deasserting reset post connect")
    #         self.dp.assert_reset(False)

    #         # Disable using the MDM-AP to halt the core.
    #         self._disable_mdm_halt()

    #         # sanity check that the target is still halted
    #         if self.get_state() == Target.State.RUNNING:
    #             raise exceptions.DebugError("Target failed to stay halted during init sequence")

    def is_locked(self) -> bool:
        if not self.mdm_ap:
            return False

        self._wait_for_flash_init()

        val = self.mdm_ap.read_reg(MDM_STATUS)
        return (val & MDM_STATUS_SYSTEM_SECURITY) != 0

    def _wait_for_flash_init(self) -> bool:
        # Wait until flash is inited.
        with Timeout(FLASH_INIT_TIMEOUT) as to:
            while to.check():
                status = self.mdm_ap.read_reg(MDM_STATUS)
                if status & MDM_STATUS_FLASH_READY:
                    break
                sleep(0.01)
        return not to.did_time_out

    def mass_erase(self):
        """@brief Perform a mass erase operation.
        @note Reset is held for the duration of this function.
        @return True Mass erase succeeded.
        @return False Mass erase failed or is disabled.
        """
        # Read current reset state so we can restore it, then assert reset if needed.
        wasResetAsserted = self.dp.is_reset_asserted()
        if not wasResetAsserted:
            self.dp.assert_reset(True)

        # Set vector catch to ensure the core stays halted after the erase to prevent it from
        # entering the lockup reset loop.
        # self.set_vector_catch(Target.VectorCatch.CORE_RESET)
        self._wait_for_flash_init()
        self._enable_mdm_halt()

        # Perform the erase.
        result = self._mass_erase()

        # Restore previous reset state.
        if not wasResetAsserted:
            self.dp.assert_reset(False)

        self._disable_mdm_halt()

        return result

    def _mass_erase(self):
        """@brief Private mass erase routine."""
        # Flash must finish initing before we can mass erase.
        if not self._wait_for_flash_init():
            LOG.error("Mass erase timeout waiting for flash to finish init")
            return False

        # Check if mass erase is enabled.
        status = self.mdm_ap.read_reg(MDM_STATUS)
        if not (status & MDM_STATUS_MASS_ERASE_ENABLE):
            LOG.error("Mass erase disabled. MDM status: 0x%x", status)
            return False

        # Set Flash Mass Erase in Progress bit to start erase.
        self.mdm_ap.write_reg(MDM_CTRL, MDM_CTRL_FLASH_MASS_ERASE_IN_PROGRESS)

        # Wait for Flash Mass Erase Acknowledge to be set.
        with Timeout(MASS_ERASE_TIMEOUT) as to:
            while to.check():
                val = self.mdm_ap.read_reg(MDM_STATUS)
                if val & MDM_STATUS_FLASH_MASS_ERASE_ACKNOWLEDGE:
                    break
                sleep(0.1)
            else:
                LOG.error("Mass erase timeout waiting for Flash Mass Erase Ack to set")
                return False

        # Wait for Flash Mass Erase in Progress bit to clear when erase is completed.
        with Timeout(MASS_ERASE_TIMEOUT) as to:
            while to.check():
                val = self.mdm_ap.read_reg(MDM_CTRL)
                if ((val & MDM_CTRL_FLASH_MASS_ERASE_IN_PROGRESS) == 0):
                    break
                sleep(0.1)
            else:
                LOG.error("Mass erase timeout waiting for Flash Mass Erase in Progress to clear")
                return False

        # Confirm the part was unlocked
        val = self.mdm_ap.read_reg(MDM_STATUS)
        if (val & MDM_STATUS_SYSTEM_SECURITY) == 0:
            LOG.warning("%s secure state: unlocked successfully", self.part_number)
            return True
        else:
            LOG.error("Failed to unlock. MDM status: 0x%x", val)
            return False

    def _get_create_flash_ram_region(self, pack_algo: PackFlashAlgo, page_size: int) -> RamRegion:
        """@brief Returns the memory region that will be used for flash programming.

        This overrides the default implementation to ensure that RAM from the system space is
        selected. This also ensures that FlexRAM (at 0x14000000) is not used, since it cannot be accessed
        simultaneously with flash, thus making it impossible to use for flash algo code and buffers.

        @return RamRegion instance that will be used for flash programming.
        @exception TargetSupportError Raised if no appropriate RAM region can be found.
        """
        min_ram = pack_algo.get_required_ram(page_size)
        region = self.memory_map.get_first_matching_region(
                type=MemoryType.RAM,
                is_default=True,
                start=lambda x: x >= 0x2000_0000,
                length=lambda x: x >= min_ram)
        if not region:
            raise exceptions.TargetSupportError("no suitable RAM region found for flash algorithm")
        return cast(RamRegion, region)

    def get_component_factory(self, cmpid: "CoreSightComponentID") -> Callable:
        """@brief Simple hook to allow overriding the factory for a CoreSight component.

        @note Use this facility only if strictly necessary. The intention is to quickly define
            a more flexible solution and deprecate this hook.
        """
        assert cmpid.factory
        if cmpid.factory in (CortexM.factory,):
            LOG.info("creating KinetisCortexM core for component %s", cmpid)
            return KinetisCortexM.factory
        else:
            return cmpid.factory

    def _has_valid_boot_vectors(self) -> bool:
        """@brief Test whether the vector table is erased.

        The vector table is "valid" as long as the first two vectors are not erased.
        """
        # Read the initial SP and ResetHandler vectors.
        vectors = self.read_memory_block32(0, 2)
        return (vectors[0] != 0xffffffff) and (vectors[1] != 0xffffffff)

    def disconnect(self, resume: bool = True) -> None:
        """
        Override disconnect to prevent resuming a device that will just enter the lockup reset loop.
        """
        if not self._has_valid_boot_vectors():
            resume = False
        return super().disconnect(resume=resume)

class KinetisCortexM(CortexM):
    """@brief Kinetis subclass of the standard Cortex-M class."""

    # def set_reset_catch(self, reset_type=None):
    #     LOG.debug("KinetisCortexM set reset catch, core %d, type %s", self.core_number, reset_type.name)

    #     self._reset_catch_delegate_result = self.call_delegate('set_reset_catch', core=self, reset_type=reset_type)

    #     # Default behaviour if the delegate didn't handle it.
    #     if not self._reset_catch_delegate_result:
    #         # Use the MDM-AP to force the core to halt across the reset.
    #         with Timeout(HALT_TIMEOUT) as to:
    #             while to.check():
    #                 cast(Kinetis, self.parent).mdm_ap.write_reg(MDM_CTRL, MDM_CTRL_DEBUG_REQUEST)
    #                 if ((cast(Kinetis, self.parent).mdm_ap.read_reg(MDM_CTRL) & MDM_CTRL_DEBUG_REQUEST) == MDM_CTRL_DEBUG_REQUEST):
    #                     break
    #             else:
    #                 raise exceptions.TimeoutError("Timed out attempting to set DEBUG_REQUEST and CORE_HOLD_RESET in MDM-AP")

    # def clear_reset_catch(self, reset_type=None):
    #     LOG.debug("KinetisCortexM clear reset catch, core %d, type %s", self.core_number, reset_type.name)

    #     self.call_delegate('clear_reset_catch', core=self, reset_type=reset_type)

    #     if not self._reset_catch_delegate_result:
    #         cast(Kinetis, self.parent)._disable_mdm_halt()

