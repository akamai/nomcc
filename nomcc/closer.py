# Copyright (C) 2011-2016 Nominum, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Nominum Command Channel ThreadedCloser

A ThreadedCloser is a base class used for objects that want to be
automatically closed on command, when an idle timeout occurs, or after
a maximum lifetime.

Additionally, callbacks to run at close time can be specified with
at_close().

To use, simply subclass and override _close().
"""

import threading
import time

DEFAULT_TIMEOUT = 300

def _closer(tcloser):
    with tcloser._closer_lock:
        while not tcloser._closing:
            timeout = None
            now = time.time()
            if tcloser._idle_timeout is not None:
                if now >= tcloser._idle_timeout:
                    tcloser._closing = True
                    continue
                timeout = tcloser._idle_timeout
            if tcloser._life_timeout is not None:
                if now >= tcloser._life_timeout:
                    tcloser._closing = True
                    continue
                if timeout is None:
                    # no idle timeout, so just use the life timeout
                    timeout = tcloser._life_timeout
                elif tcloser._life_timeout < timeout:
                    # sleep until the earlier timeout
                    timeout = tcloser._life_timeout
            tcloser._closer_timeout = timeout
            if timeout is not None:
                sleep = timeout - now
                if sleep < 0:
                    sleep = 0
            else:
                sleep = None
            tcloser._wake_closer.wait(sleep)
    tcloser._do_close()

class ThreadedCloser(object):
    def __init__(self):
        self._at_close = []
        self._closer_lock = threading.Lock()    # covers 'closing',
        self._closing = False                   # 'wake_closer', and timeouts
        self._wake_closer = threading.Condition(self._closer_lock)
        self._idletime = None
        self._idle_timeout = None
        self._life_timeout = None
        self._closer = threading.Thread(target=_closer, args=[self],
                                        name="cc-closer")
        self._closer_timeout = None
        self._closer.daemon = True
        self.closed = threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if not self.closed.is_set():
            self.close()
        return False

    def _do_close(self):
        self._close()
        self.closed.set()
        for callback in reversed(self._at_close):
            callback(self)

    def at_close(self, callback):
        """Call 'callback' when the object is closed."""
        self._at_close.append(callback)

    def request_close(self):
        """Request that the object close.

        Note this method does not wait until the close is complete.  It
        merely starts the closing process if it isn't already underway.
        """
        with self._closer_lock:
            if self._closing:
                return
            self._closing = True
            self._wake_closer.notify()

    def close(self, timeout=DEFAULT_TIMEOUT):
        """Request that the object be closed and wait for it to occur."""
        self.request_close()
        self.closed.wait(timeout)

    def is_closing(self):
        with self._closer_lock:
            return self._closing

    def _maybe_wake_closer(self, timeout):
        # closer lock must be held
        if timeout is None:
            return
        if self._closer_timeout is None or \
           timeout < self._closer_timeout:
            self._wake_closer.notify()

    def set_lifetime(self, lifetime):
        """Set the maximum lifetime before closing."""
        with self._closer_lock:
            if lifetime is not None:
                self._life_timeout = time.time() + lifetime
            else:
                self._life_timeout = None
            self._maybe_wake_closer(self._life_timeout)

    def _not_idle(self):
        # closer lock must be held
        if self._idletime is not None:
            self._idle_timeout = time.time() + self._idletime
        else:
            self._idle_timeout = None
        self._maybe_wake_closer(self._idle_timeout)

    def not_idle(self):
        """Mark the object as not idle.

        This resets the idle time counter to start from now.
        """
        with self._closer_lock:
            self._not_idle()

    def set_idletime(self, idletime):
        """Set the amount of idle time which may elapse before closing.

        The currently elapsed idle time is reset every time the not_idle()
        method is called.
        """
        with self._closer_lock:
            self._idletime = idletime
            self._not_idle()

    def _start_closer(self):
        self._closer.start()

    def _close(self):
        # subclasser implements this
        pass
