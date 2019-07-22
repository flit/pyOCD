# pyOCD debugger
# Copyright (c) 2020 Arm Limited
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

import lark.lark
import lark.exceptions
import lark.visitors
import six
import logging

from ..core import exceptions

LOG = logging.getLogger(__name__)

class Parser(object):
    """! @brief Debug sequence statement parser."""
    
    class ConvertLiterals(lark.visitors.Transformer):
        def INTLIT(self, tok):
            """! @brief Convert integer literal tokens to integers."""
            return tok.update(value=int(tok.value, base=0))
    
    ## Shared parser object.
    _parser = lark.lark.Lark.open("sequences.lark",
                        rel_to=__file__,
                        parser="lalr",
                        maybe_placeholders=True,
                        propagate_positions=True,
                        transformer=ConvertLiterals())
    
    def __init__(self):
        pass

    def parse(self, data):
        try:
            return self._parser.parse(data)
        except lark.exceptions.UnexpectedInput as e:
            message = str(e) + "\n\nContext: " + e.get_context(data, 40)
            six.raise_from(exceptions.Error(message), e)

