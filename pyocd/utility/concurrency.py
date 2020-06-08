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

from functools import wraps
from threading import (Lock, Semaphore)
from contextlib import contextmanager
import logging

# Import low-level thread module for either Python 3 or 2.
try
    import _thread as thread
except ImportError:
    import thread

LOG = logging.getLogger(__name__)

def locked(func):
    """! @brief Decorator to automatically lock a method of a class.
    
    The class is required to have `lock()` and `unlock()` methods.
    """
    @wraps(func)
    def _locking(self, *args, **kwargs):
        try:
            self.lock()
            return func(self, *args, **kwargs)
        finally:
            self.unlock()
    return _locking

class RWValueLock(object):
    """! @brief Variant of a read-write lock that takes value into account.
    
    The general idea is that an instance of this lock protects some resource. That resource has
    a control field of some sort. The resource needs to be locked to allow safe concurrent access 
    while the control field as a given value. That is, multiple threads may use the resource
    simultaneously as long as all threads use the same control field value. This is a read lock.
    If a thread needs to access the resource using a different control field value, then a write
    lock must be acquired, waiting for all open read locks to be released.
    
    This lock implementation is fair, in the sense that it does not favour either readers or
    writers. A queue is maintained, and access is given in the order it was requested.
    
    Based on code from the third readers-writers problem on
    https://en.wikipedia.org/wiki/Readers-writers_problem.
    """
    
    def __init__(self, initial_value=None):
        """! @brief Constructor."""
        self._current_value = initial_value
        self._current_value_lock = Lock()
        self._reader_count = 0
        self._resource_sem = Semaphore()
        self._reader_count_sem = Semaphore()
        self._order_sem = Semaphore()
    
    @property
    def value(self):
        """! @brief Safely returns the current value.
        
        A separate lock is used to guarantee atomicity of the internal copy of the value without
        interacting with the reader-writer lock.
        """
        with self._current_value_lock:
            return self._current_value
    
    @contextmanager
    def lock_for_value(self, value, value_setter=None):
        """! @brief Context manager that locks for reading or writing based on a value.
        
        The value passed in is the desired control field value that needs to be used with the
        resource. If this value is the same as the current value, then a read lock is acquired.
        Otherwise, a write lock is temporarily acquired and the current value updated to the new
        value by invoking the `value_setter` with the new value, then returning to a read lock.
        
        The current implementation is naive and inefficient.
        
        @param self The lock instance.
        @param value The required value of the control field the caller needs to use.
        @param value_setter Callable taking the new value and applying it to the control field. Only
            called if the value needs to change. This parameter is optional. If not provided, then
            the `value` property can be used.
        """
        self.acquire_for_value(value, value_setter)
        yield self._current_value
        self.release_for_value()
        
    def acquire_for_value(self, value, value_setter=None):
        """! @brief Acquire a read or write lock based on a value.
        
        The value passed in is the desired control field value that needs to be used with the
        resource. If this value is the same as the current value, then a read lock is acquired.
        Otherwise, a write lock is temporarily acquired and the current value updated to the new
        value by invoking the `value_setter` with the new value, then returning to a read lock.
        
        The current implementation is naive and inefficient.
        
        @param self The lock instance.
        @param value The required value of the control field the caller needs to use.
        @param value_setter Callable taking the new value and applying it to the control field. Only
            called if the value needs to change. This parameter is optional. If not provided, then
            the `value` property can be used.
        """
        LOG.debug("[t:%s] acquire_for_value(%#010x)", thread.get_native_id(), value)
        self.acquire_read()
        if value != self._current_value:
            # The value needs to change, so switch from reader to writer.
            LOG.debug("[t:%s] acquire_for_value(%#010x): value needs to change", thread.get_native_id(), value)
            self.release_read()
            self.acquire_write()
            
            try:
                # Update our own copy of the value.
                with self._current_value_lock:
                    self._current_value = value
                # Invoke the setter to update the value externally.
                if value_setter is not None:
                    value_setter(value)
            finally:
                # Release write lock on any exit from this block.
                self.release_write()

            # Revert back to reader.
            LOG.debug("[t:%s] acquire_for_value(%#010x): revert to reader", thread.get_native_id(), value)
            self.acquire_read()
        return self._current_value
        
    def release_for_value(self):
        """! @brief Release the lock obtained with acquire_for_value()."""
        LOG.debug("[t:%s] release_for_value", thread.get_native_id())
        self.release_read()
    
    def clear(self):
        """! @brief Set the current value to None."""
        LOG.debug("[t:%s] clear", thread.get_native_id())
        with self.lock_for_value(None):
            pass
    
    def acquire_read(self):
        """! @brief Acquire a read lock."""
        LOG.debug("[t:%s] acquire_read", thread.get_native_id())
        self._order_sem.acquire()
        self._reader_count_sem.acquire()
        if self._reader_count == 0:
            self._resource_sem.acquire()
        self._reader_count += 1
        LOG.debug("[t:%s]     reader_count <- %i", thread.get_native_id(), self._reader_count)
        self._order_sem.release()
        self._reader_count_sem.release()
        
    def release_read(self):
        """! @brief Release a previously acquired read lock."""
        LOG.debug("[t:%s] release_read", thread.get_native_id())
        self._reader_count_sem.acquire()
        self._reader_count -= 1
        LOG.debug("[t:%s]     reader_count <- %i", thread.get_native_id(), self._reader_count)
        if self._reader_count == 0:
            self._resource_sem.release()
        self._reader_count_sem.release()
    
    def acquire_write(self):
        """! @brief Acquire a write lock."""
        LOG.debug("[t:%s] acquire_write", thread.get_native_id())
        self._order_sem.acquire()
        self._resource_sem.acquire()
        self._order_sem.release()
        
    def release_write(self):
        """! @brief Release a previously acquired write lock."""
        LOG.debug("[t:%s] release_write", thread.get_native_id())
        self._resource_sem.release()

