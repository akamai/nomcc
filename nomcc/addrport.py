# Copyright (C) 2019 Akamai Technologies, Inc.
# Copyright (C) 2003-2014,2016 Nominum, Inc.
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

"""Network Address/Port Support

An 'addrport' is a network address and port pair, corresponding to a
'struct sockaddr' in C.
"""

import socket


class Addrport(object):
    """Virtual base clase for addrports

    The 'af' attribute of an addrport is suitable for use as the
    address family argument to socket.socket().

    The 'sockaddr' attribute of an addrport is suitable for use as an
    address in python socket operations, e.g. socket.connect().
    """
    pass


class Addrport4(Addrport):
    """An IPv4 addrport

    The texual form of an IPv4 addrport is

        <address>[#<port>]

    E.g.:

        127.0.0.1#6000

    If not specified, the port defaults to zero.
    """

    def __init__(self, ap=None):
        self.af = socket.AF_INET
        port_start = ap.find('#')
        if port_start >= 0:
            addr = ap[: port_start]
            port = ap[port_start + 1:]
        else:
            addr = ap
            port = '0'
        port = int(port)
        self.sockaddr = (addr, port)

    def __str__(self):
        return "%s#%d" % (self.sockaddr[0], self.sockaddr[1])

    def __repr__(self):
        return "<IPv4 addrport %s>" % (str(self))

    def sending_sockaddr(self):
        """The sockaddr that should be used to send to the service."""
        if self.sockaddr[0] == '0.0.0.0':
            return ('127.0.0.1', self.sockaddr[1])
        else:
            return self.sockaddr


class Addrport6(Addrport):
    """An IPv6 addrport

    The texual form of an IPv6 addrport is

        <address>[%scopeid][#<port>]

    E.g.:

        ::1#6000

    If not specified, the port defaults to zero.
    """

    def __init__(self, ap=None):
        self.af = socket.AF_INET6
        port_start = ap.find('#')
        if port_start >= 0:
            addrscope = ap[: port_start]
            port = int(ap[port_start + 1:])
        else:
            addrscope = ap
            port = '0'
        scope_start = ap.find('%')
        if scope_start >= 0:
            addr = addrscope[: scope_start]
            scope = addrscope[scope_start + 1:]
        else:
            addr = addrscope
            scope = 0
        port = int(port)
        scope = int(scope)
        self.sockaddr = (addr, port, 0, scope)

    def __str__(self):
        if self.sockaddr[3] != 0:
            return "%s%%%d#%d" % (self.sockaddr[0], self.sockaddr[3],
                                  self.sockaddr[1])
        else:
            return "%s#%d" % (self.sockaddr[0], self.sockaddr[1])

    def __repr__(self):
        return "<IPv6 Addrport %s>" % (str(self))

    def sending_sockaddr(self):
        """The address that should be used to send to the service.
        """
        if self.sockaddr[0] == '::':
            return (
                '::1', self.sockaddr[1], self.sockaddr[2], self.sockaddr[3]
            )
        else:
            return self.sockaddr


def new(text):
    """
    Create a new IPv4 or IPv6 Addrport object (as appropriate) based
    on the textual addrport representation 'text'.
    """

    if text.find(':') >= 0:
        return Addrport6(text)
    else:
        return Addrport4(text)
