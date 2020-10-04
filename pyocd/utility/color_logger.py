# pyOCD debugger
# Copyright (c) 2018-2020 Arm Limited
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

import sys
import logging
import colorama

from .compatibility import get_terminal_size

class ColorLogger(logging.Logger):
    """! @brief Logger that uses ColorFormatter."""
    
    # Default log format.
#     FORMAT = "%(msgcolor)s%(relativeCreated)07d$RESET %(lvlcolor)s%(levelname)s%(levelname_align)s$RESET %(msgcolor)s%(module)-8.8s %(message)s$RESET"
    FORMAT = "{relativeCreated:07.0f} {lvlcolor:s}{levelname:<{levelnamewidth}.{levelnamewidth}s}{_reset} {msgcolor}{msg_1: <{msgwidth}s}{_reset} {_dim}[{module:s}]{_reset}{msg_2}"
    
    use_color = True

    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)                

        console = logging.StreamHandler(sys.stdout)
        
        color_formatter = ColorFormatter(self.FORMAT, self.use_color)
        console.setFormatter(color_formatter)

        self.addHandler(console)

class ColorFormatter(logging.Formatter):
    """! @brief Log formatter that applies colours based on the record level."""
    
    RESET_ALL = colorama.Style.RESET_ALL
    BRIGHT = colorama.Style.BRIGHT
    DIM = colorama.Style.DIM
    BLACK = colorama.Fore.BLACK
    RED = colorama.Fore.RED
    GREEN = colorama.Fore.GREEN
    YELLOW = colorama.Fore.YELLOW
    BLUE = colorama.Fore.BLUE
    MAGENTA = colorama.Fore.MAGENTA
    CYAN = colorama.Fore.CYAN
    WHITE = colorama.Fore.WHITE

    ## Colors for the log level name.
    LEVEL_COLORS = {
            'CRITICAL': BRIGHT + RED,
            'ERROR': RED,
            'WARNING': YELLOW,
            'INFO': '',
            'DEBUG': DIM,
        }

    ## Colors for the rest of the log message.
    MESSAGE_COLORS = {
            'ERROR': colorama.Fore.LIGHTRED_EX,
            'WARNING': colorama.Fore.LIGHTYELLOW_EX,
        }
    
    # Note: CRITICAL and WARNING are longer.
    MAX_LEVELNAME_WIDTH = 4 #len('DEBUG')

    def __init__(self, msg, use_color):
        super(ColorFormatter, self).__init__(msg, style='{')
        self._use_color = use_color
        self._term_width = get_terminal_size()[0] # TODO: Handle resizing of terminal
    
    def format(self, record):
        # Capture and remove exc_info and stack_info so the superclass format() doesn't
        # print it and we can control the formatting.
        exc_info = record.exc_info
        record.exc_info = None
        stack_info = record.stack_info
        record.stack_info = None

        # Add level and message colors to the record.
        if self._use_color and (record.levelname in self.LEVEL_COLORS):
            record.lvlcolor = self.LEVEL_COLORS[record.levelname]
        else:
            record.lvlcolor = ""

        if self._use_color and (record.levelname in self.MESSAGE_COLORS):
            record.msgcolor = self.MESSAGE_COLORS[record.levelname]
        else:
            record.msgcolor = ""
        
        if self._use_color:
            record._reset = colorama.Style.RESET_ALL
        else:
            record._reset = ""
        record._dim = self.DIM
        
        record.message = record.getMessage()
        
        record.msgwidth = self._term_width - (7 + 1 + 4 + 1 + len(record.module) + 3)
        if len(record.message) > record.msgwidth:
            record.msg_1 = record.message[:record.msgwidth - 3] + "..."
            record.msg_2 = "..." + record.message[record.msgwidth - 3:]
        else:
            record.msg_1 = record.message
            record.msg_2 = ""
        
        # Add levelname alignment to record.
        record.levelname_align = " " * max(self.MAX_LEVELNAME_WIDTH - len(record.levelname), 0)
        record.levelnamewidth = self.MAX_LEVELNAME_WIDTH
        
        # Let superclass handle formatting.
        log_msg = super(ColorFormatter, self).format(record)

        # Append uncolored exception/stack info.
        if exc_info:
            log_msg += "\n" + self.formatException(exc_info)
        if stack_info:
            log_msg += "\n" + self.formatStack(stack_info)

        return log_msg
