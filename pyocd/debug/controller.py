# pyOCD debugger
# Copyright (c) 2019-2020 Arm Limited
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
import threading
import sys
from time import sleep

from ..core import exceptions
from ..core.target import Target
from ..utility.cmdline import convert_vector_catch
from ..utility.conversion import (hex_to_byte_list, hex_encode, hex_decode, hex8_to_u32le)
from ..utility.progress import print_progress
from ..utility.server import StreamServer
from ..trace.swv import SWVReader
from . import semihost
from .cache import MemoryAccessError
from ..rtos import RTOS

LOG = logging.getLogger(__name__)

class DebugController:
    """@brief Controller class that provides high level debug functionality.

    This class is used by the gdbserver to perform actions on behalf of gdb.

    This class' responsibilities are:
    - Continually watch the target for state changes.
    - Send notifications when the target state does change.
    - Enact state changes upon request from other objects.
    - Construct the common IO infrastructure for things like semihosting and SWV.
    - Handle RTOS thread providers.
    """

    def __init__(self, session, core_number=0):
        """@brief Constructor.
        @param self
        @param session The session being managed by the controller.
        """
        self._session = session
        self._core_number = core_number
        self._core = None
        self._delegate = None
        self._swv_reader = None
        self._thread_provider = None
        self._did_init_thread_providers = False
        self._current_thread_id = 0
        self._first_run_after_reset_or_flash = True
        self._is_target_running = False
        self._target_context = None
        self.semihost_console_type = None
        self._telnet_server = None
        self._semihost_agent = None

    def init(self):
        self._core = session.target.cores[self._core_number]
        self._target_context = self._core.get_target_context()
        self._is_target_running = (self._core.get_state() == Target.TARGET_RUNNING)

        # Subscribe to events we're interested in.
        self.session.subscribe(self._event_handler, [
                Target.Event.PRE_RUN,
                Target.Event.POST_RUN,
                Target.Event.PRE_HALT,
                Target.Event.POST_HALT,
                Target.Event.PRE_RESET,
                Target.Event.POST_RESET,
                ], self._core)

        self._init_options()
        self._init_semihosting()
        self._init_swv()

    def _init_options(self):
        self.vector_catch = session.options.get('vector_catch')
        self._core.set_vector_catch(convert_vector_catch(self.vector_catch))
        self.step_into_interrupt = session.options.get('step_into_interrupt')
        self.enable_semihosting = session.options.get('enable_semihosting')

    def _init_semihosting(self):
        # Init semihosting and telnet console.
        if self.semihost_use_syscalls:
            semihost_io_handler = None # TODO GDBSyscallIOHandler(self)
        else:
            # Use internal IO handler.
            semihost_io_handler = semihost.InternalSemihostIOHandler()

        telnet_port = session.options.get('telnet_port')
        if telnet_port != 0:
            telnet_port += self.core

        serve_local_only = session.options.get('serve_local_only')
        semihost_console_type = session.options.get('semihost_console_type')
        semihost_use_syscalls = session.options.get('semihost_use_syscalls')

        if self.semihost_console_type == 'telnet':
            self._telnet_server = StreamServer(telnet_port, serve_local_only, "Semihost", False)
            console_file = self._telnet_server
            semihost_console = semihost.ConsoleIOHandler(self._telnet_server)
        else:
            LOG.info("Semihosting will be output to console")
            console_file = sys.stdout
            self._telnet_server = None
            semihost_console = semihost_io_handler
        self._semihost_agent = semihost.SemihostAgent(self._target_context, io_handler=semihost_io_handler, console=semihost_console)

    def _init_swv(self):
        if session.options.get("enable_swv", False):
            if "swv_system_clock" not in session.options:
                LOG.warning("Cannot enable SWV due to missing swv_system_clock option")
            else:
                sys_clock = int(session.options.get("swv_system_clock"))
                swo_clock = int(session.options.get("swv_clock", 1000000))
                self._swv_reader = SWVReader(session, self.core)
                self._swv_reader.init(sys_clock, swo_clock, console_file)

#         self.daemon = True
#         self.start()

    def cleanup(self):
        if self._semihost_agent:
            self._semihost_agent.cleanup()
            self._semihost_agent = None
        if self._telnet_server:
            self._telnet_server.stop()
            self._telnet_server = None
        if self._swv_reader:
            self._swv_reader.stop()
            self._swv_reader = None

    @property
    def session(self):
        return self._session

    @property
    def delegate(self):
        return self._delegate

    @delegate.setter
    def delegate(self, new_delegate):
        self._delegate = new_delegate

    @property
    def core(self):
        return self._core

    @property
    def is_target_running(self):
        return self._is_target_running

    def receive(self, event):
        """@brief Handle an SWV trace event.
        @param self
        @param event An instance of TraceITMEvent. If the event is not this class, or isn't
            for ITM port 0, then it will be ignored.
        """
        pass

    def run(self):
        pass

    def resume(self):
        self._core.resume()

        if self._first_run_after_reset_or_flash:
            self._first_run_after_reset_or_flash = False
            if self._thread_provider is not None:
                self._thread_provider.read_from_target = True

        while True:
            if self.shutdown_event.isSet():
                self.packet_io.interrupt_event.clear()
                return self.create_rsp_packet(val)

            # Wait for a ctrl-c to be received.
            if self.packet_io.interrupt_event.wait(0.01):
                LOG.debug("receive CTRL-C")
                self.packet_io.interrupt_event.clear()
                self._core.halt()
                val = self.get_t_response(forceSignal=signals.SIGINT)
                break

            try:
                if self._core.get_state() == Target.TARGET_HALTED:
                    # Handle semihosting
                    if self.enable_semihosting:
                        was_semihost = self._semihost_agent.check_and_handle_semihost_request()

                        if was_semihost:
                            self._core.resume()
                            continue

                    val = self.get_t_response()
                    break
            except exceptions.Error as err:
                try:
                    self._core.halt()
                except:
                    pass
                break

    def step(self):
        self._core.step(not self.step_into_interrupt)

    def halt(self):
        self._core.halt()

    def init_thread_providers(self, symbol_provider):
        for rtosName, rtosClass in RTOS.items():
            try:
                LOG.info("Attempting to load %s", rtosName)
                rtos = rtosClass(self.session.target)
                if rtos.init(symbol_provider):
                    LOG.info("%s loaded successfully", rtosName)
                    self._thread_provider = rtos
                    break
            except exceptions.Error as err:
                LOG.error("Error during symbol lookup: %s", err, exc_info=self.session.log_tracebacks)

        self._did_init_thread_providers = True

    def is_threading_enabled(self):
        return (self._thread_provider is not None) and self._thread_provider.is_enabled \
            and (self._thread_provider.current_thread is not None)

    def is_target_in_reset(self):
        return self._core.get_state() == Target.TARGET_RESET

    def _event_handler(self, notification):
        """@brief Notification handler."""
        if notification.event == Target.Event.PRE_RUN:
            self._is_target_running = True
        elif notification.event == Target.Event.PRE_HALT:
            self._is_target_running = False
        elif notification.event == Target.Event.POST_RESET:
            # Invalidate threads list if flash is reprogrammed.
            LOG.debug("Received POST_RESET event")
            self._first_run_after_reset_or_flash = True
            if self._thread_provider is not None:
                self._thread_provider.read_from_target = False

