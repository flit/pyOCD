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

import logging
import colorama

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

#The background is set with 40 plus the number of the color, and the foreground with 30

#These are the sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[1;%dm"
BOLD_SEQ = "\033[1m"

def formatter_message(message, use_color = True):
    if use_color:
        message = message.replace("$RESET", RESET_SEQ).replace("$BOLD", BOLD_SEQ)
    else:
        message = message.replace("$RESET", "").replace("$BOLD", "")
    return message

COLORS = {
    'WARNING': YELLOW,
    'INFO': WHITE,
    'DEBUG': BLUE,
    'CRITICAL': YELLOW,
    'ERROR': RED
}

class ColoredFormatter(logging.Formatter):
    def __init__(self, msg, use_color = True):
        logging.Formatter.__init__(self, msg)
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in COLORS:
            record.color = COLOR_SEQ % (30 + COLORS[levelname])
            record.reset = RESET_SEQ
        else:
            record.color = record.reset = ""
        return logging.Formatter.format(self, record)

# Custom logger class with multiple destinations
class ColoredLogger(logging.Logger):
    FORMAT = "$BOLD%(color)s%(levelname)s$RESET %(message)s"
    COLOR_FORMAT = formatter_message(FORMAT, True)
    def __init__(self, name):
        logging.Logger.__init__(self, name, logging.DEBUG)                

        color_formatter = ColoredFormatter(self.COLOR_FORMAT)

        console = logging.StreamHandler()
        console.setFormatter(color_formatter)

        self.addHandler(console)
        return

def decode_value(value):
    try:
        return str(value)
    except UnicodeDecodeError:  # pragma: no cover
        return bytes(value).decode('utf-8')

class ColorFormatter(logging.Formatter):
    """! @brief Simple log formatter that colorises each line."""
    
    RESET_ALL = colorama.Style.RESET_ALL
    BRIGHT = colorama.Style.BRIGHT
    DIM = colorama.Style.DIM
    CYAN = colorama.Fore.CYAN
    MAGENTA = colorama.Fore.MAGENTA
    YELLOW = colorama.Fore.YELLOW
    RED = colorama.Fore.RED

    LEVEL_COLORS = {
            'CRITICAL': BRIGHT + MAGENTA,
            'ERROR': RED,
            'WARNING': YELLOW,
            'INFO': '',
            'DEBUG': DIM,
        }
    
    def format(self, record):
        # Capture and remove exc_info and stack_info so the superclass format() doesn't
        # print it and we can control the formatting.
        exc_info = record.exc_info
        record.exc_info = None
        stack_info = record.stack_info
        record.stack_info = None
        
        # Let superclass handle formatting.
        msg = super(ColorFormatter, self).format(record)

        # Colorise the line.
        level_color = self.LEVEL_COLORS.get(record.levelname, '')
        log_msg = level_color + msg + self.RESET_ALL

        # Append uncolored exception/stack info.
        if exc_info:
            log_msg += "\n" + self.formatException(exc_info)
        if stack_info:
            log_msg += "\n" + self.formatStack(stack_info)

        return log_msg
