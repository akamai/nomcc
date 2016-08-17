# Copyright (C) 2011-2014,2016 Nominum, Inc.
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

# Adapted from dnspython query.py
#
# Copyright (C) 2003-2007, 2009-2011 Nominum, Inc.
#
# Permission to use, copy, modify, and distribute this software and its
# documentation for any purpose with or without fee is hereby granted,
# provided that the above copyright notice and this permission notice
# appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND NOMINUM DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL NOMINUM BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT
# OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""I/O helpers"""

import errno
import select
import socket
import time

import nomcc.exceptions
from nomcc._compat import *

def get_expiration(timeout):
    if timeout is None:
        return None
    else:
        return time.time() + timeout

def _poll_for(fd, readable, writable, error, timeout):
    """
    @param fd: File descriptor (int).
    @param readable: Whether to wait for readability (bool).
    @param writable: Whether to wait for writability (bool).
    @param expiration: Deadline timeout (expiration time, in seconds (float)).

    @return True on success, False on timeout
    """
    event_mask = 0
    if readable:
        event_mask |= select.POLLIN
    if writable:
        event_mask |= select.POLLOUT
    if error:
        event_mask |= select.POLLERR

    pollable = select.poll()
    pollable.register(fd, event_mask)

    if timeout:
        event_list = pollable.poll(long(timeout * 1000))
    else:
        event_list = pollable.poll()

    return bool(event_list)

def _select_for(fd, readable, writable, error, timeout):
    """
    @param fd: File descriptor (int).
    @param readable: Whether to wait for readability (bool).
    @param writable: Whether to wait for writability (bool).
    @param expiration: Deadline timeout (expiration time, in seconds (float)).

    @return True on success, False on timeout
    """
    rset, wset, xset = [], [], []

    if readable:
        rset = [fd]
    if writable:
        wset = [fd]
    if error:
        xset = [fd]

    if timeout is None:
        (rcount, wcount, xcount) = select.select(rset, wset, xset)
    else:
        (rcount, wcount, xcount) = select.select(rset, wset, xset, timeout)

    return bool((rcount or wcount or xcount))

def _wait_for(fd, readable, writable, error, expiration):
    done = False
    while not done:
        if expiration is None:
            timeout = None
        else:
            timeout = expiration - time.time()
            if timeout <= 0.0:
                raise nomcc.exceptions.Timeout
        try:
            if not _polling_backend(fd, readable, writable, error, timeout):
                raise nomcc.exceptions.Timeout
        except select.error as e:
            if e.args[0] != errno.EINTR:
                raise e
        done = True

def _set_polling_backend(fn):
    """
    Internal API. Do not use.
    """
    global _polling_backend

    _polling_backend = fn

if hasattr(select, 'poll'):
    # Prefer poll() on platforms that support it because it has no
    # limits on the maximum value of a file descriptor (plus it will
    # be more efficient for high values).
    _polling_backend = _poll_for
else:
    _polling_backend = _select_for

def wait_for_readable(s, expiration):
    _wait_for(s, True, False, True, expiration)

def wait_for_writable(s, expiration):
    _wait_for(s, False, True, True, expiration)
