# pyOCD debugger
# Copyright (c) 2018-2019 Arm Limited
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

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

# The background is set with 40 plus the number of the color, and the foreground with 30
# record.color = COLOR_SEQ % (30 + COLORS[levelname])

# These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

class ColoredLogger(logging.Logger):
    """! @brief Logger that uses ColorFormatter."""
    
    # Default log format.
    FORMAT = "%(msgcolor)s%(relativeCreated)07d$RESET %(lvlcolor)s%(levelname)s%(levelname_align)s$RESET %(msgcolor)s%(module)-8.8s %(message)s$RESET"
    
    use_color = True

    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)                

        console = logging.StreamHandler(sys.stdout)
        
        color_formatter = ColorFormatter(self.FORMAT, self.use_color)
        console.setFormatter(color_formatter)

        self.addHandler(console)

def decode_value(value):
    try:
        return str(value)
    except UnicodeDecodeError:  # pragma: no cover
        return bytes(value).decode('utf-8')

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
            'ERROR': RED,
            'WARNING': YELLOW,
            'DEBUG': DIM,
        }
    
    # Note: CRITICAL and WARNING are longer.
    MAX_LEVELNAME_WIDTH = len('DEBUG')

    def __init__(self, msg, use_color):
        super(ColorFormatter, self).__init__(msg)
        self._use_color = use_color
    
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
        
        # Add levelname alignment to record.
        record.levelname_align = " " * max(self.MAX_LEVELNAME_WIDTH - len(record.levelname), 0)
        
        # Let superclass handle formatting.
        log_msg = super(ColorFormatter, self).format(record)
        
        if self._use_color:
            log_msg = log_msg.replace("$RESET", colorama.Style.RESET_ALL)
        else:
            log_msg = log_msg.replace("$RESET", "")

        # Append uncolored exception/stack info.
        if exc_info:
            log_msg += "\n" + self.formatException(exc_info)
        if stack_info:
            log_msg += "\n" + self.formatStack(stack_info)

        return log_msg
