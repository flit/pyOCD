# pyOCD debugger
# Copyright (c) 2015-2020 Arm Limited
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
import os
from pathlib import Path
import traceback
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from prompt_toolkit.history import FileHistory

from ..core import (session, exceptions)

if TYPE_CHECKING:
    from .execution_context import CommandExecutionContext

LOG = logging.getLogger(__name__)

class ToolExitException(Exception):
    """@brief Special exception indicating the tool should exit.

    This exception is only raised by the `exit` command.
    """
    pass


class PyocdReplBase:
    """@brief Base Read-Eval-Print-Loop class for pyOCD commander."""

    PYOCD_HISTORY_ENV_VAR = 'PYOCD_HISTORY'
    DEFAULT_HISTORY_FILE = ".pyocd_history"

    def __init__(self, command_context: "CommandExecutionContext") -> None:
        self.context = command_context

        # Get path to history file.
        self._history_path = Path(os.environ.get(self.PYOCD_HISTORY_ENV_VAR,
               Path("~") / self.DEFAULT_HISTORY_FILE)).expanduser()

    def run(self) -> None:
        """@brief Runs the REPL loop until EOF is encountered."""
        raise NotImplementedError()

    def run_one_command(self, line: str) -> None:
        """@brief Execute a single command line and handle exceptions."""
        try:
            line = line.strip()
            if line:
                self.context.process_command_line(line)
        except KeyboardInterrupt:
            print()
        except ValueError:
            print("Error: invalid argument")
            if session.Session.get_current().log_tracebacks:
                traceback.print_exc()
        except exceptions.TransferError as e:
            print("Transfer failed:", e)
            if session.Session.get_current().log_tracebacks:
                traceback.print_exc()
        except exceptions.CommandError as e:
            print("Error:", e)
        except ToolExitException:
            # Catch and reraise this exception so it isn't caught by the catchall below.
            raise
        except Exception as e:
            # Catch most other exceptions so they don't cause the REPL to exit.
            print("Error:", e)
            if session.Session.get_current().log_tracebacks:
                traceback.print_exc()


class PromptToolkitRepl(PyocdReplBase):
    """@brief REPL using the prompt_toolkit package."""

    PROMPT = FormattedText([
            ('class:a', "pyocd"),
            ('class:b', "> ")
            ])

    PROMPT_STYLE = Style.from_dict({
            'a': '#2080e0',
            'b': '#44ff00',
            })

    def __init__(self, command_context: "CommandExecutionContext") -> None:
        super().__init__(command_context)

        # Create prompt session.
        history = FileHistory(str(self._history_path))
        self._prompt_session = PromptSession(
                message=self.PROMPT,
                style=self.PROMPT_STYLE,
                history=history)

    def run(self) -> None:
        """@brief Runs the REPL loop until EOF is encountered."""
        try:
            while True:
                try:
                    line = self._prompt_session.prompt()
                    self.run_one_command(line)
                except KeyboardInterrupt:
                    # Ignore Ctrl-C and continue the loop.
                    pass
        except EOFError:
            # Just exit the REPL on Ctrl-D.
            pass


PyocdRepl = PromptToolkitRepl

