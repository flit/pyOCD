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

import pytest
import threading

from pyocd.utility.concurrency import RWValueLock

def run_in_parallel(function, args_list):
    """! @brief Create and run a thread in parallel for each element in args_list

    Wait until all threads finish executing. Throw an exception if an exception
    occurred on any of the threads.
    """
    def _thread_helper(idx, func, args):
        func(*args)
        result_list[idx] = True

    result_list = [False] * len(args_list)
    thread_list = []
    for idx, args in enumerate(args_list):
        thread = threading.Thread(target=_thread_helper,
                                  args=(idx, function, args))
        thread_list.append(thread)

    for thread in thread_list:
        thread.start()
    for thread in thread_list:
        thread.join()
    if not all(result_list):
        raise RuntimeError("Running in thread failed")

class TestRWValueLock:
    def test_no_init_val(self):
        lck = RWValueLock()
        assert lck.value is None

    def test_1_reader(self):
        lck = RWValueLock(initial_value=100)
        assert lck.value is 100
        with lck.lock_for_value(100):
            pass
        assert lck.value == 100

    def test_1_writer(self):
        lck = RWValueLock(initial_value=100)
        assert lck.value is 100
        with lck.lock_for_value(200):
            assert lck.value == 200
        assert lck.value == 200
        
    TEST_REPEAT = 100
    TEST_CASES = [
            [(100,), (100,), (100,)], # 3 readers
            [(100,), (100,), (200,)], # 2 readers, 1 writer
            [(200,), (200,), (200,)], # 3 writers, all same
            [(1,), (2,), (3,)], # 3 writers, all different
            [(128,), (128,), (128,), (256,), (128,), (128,), (512,), (512,), (128,)], # big combo
        ]
    
    @pytest.mark.parametrize(("parms"), TEST_CASES)
    def test_combos(self, parms):
        lck = RWValueLock(initial_value=100)
        assert lck.value is 100
        
        def _test(v):
            with lck.lock_for_value(v):
                assert lck.value == v
        
        for i in range(self.TEST_REPEAT):
            run_in_parallel(_test, parms)
    
    @pytest.mark.parametrize(("parms"), TEST_CASES)
    def test_combos_with_setter(self, parms):
        lck = RWValueLock(initial_value=100)
        assert lck.value is 100
        
        shared_value = [100]
        
        def my_setter(v):
            shared_value[0] = v
        
        def _test(v):
            with lck.lock_for_value(v, my_setter):
                assert lck.value == v
                assert shared_value[0] == v
        
        for i in range(self.TEST_REPEAT):
            run_in_parallel(_test, parms)

