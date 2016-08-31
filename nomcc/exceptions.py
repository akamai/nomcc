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

"""Nominum Command Channel Exceptions"""

class CCException(Exception):
    _default_msg = ''
    _always_use_default_msg = True

    def __str__(self):
        s = super(CCException, self).__str__()
        if s:
            if self._always_use_default_msg:
                return self._default_msg + ': ' + s
            else:
                return s
        else:
            return self._default_msg

class MessageTooBig(CCException):
    """The message is too large."""
    _default_msg = 'message too big'

class BadResponse(CCException):
    """The response does not correspond to the request."""
    _default_msg = 'bad response'

class BadNoncing(CCException):
    """The message did not pass nonce checks."""
    _default_msg = 'bad noncing'

class NotResponse(CCException):
    """The message is not a response."""
    _default_msg = 'expected response'

class NotSupported(CCException):
    """The operation is not supported"""
    _default_msg = 'not supported'

class BadVersion(CCException):
    """The version of the encoding is not known
    """
    _default_msg = 'unknown CC version'

class BadAuth(CCException):
    """Authentication failed
    """
    _default_msg = 'bad CC auth'

class UnexpectedEnd(CCException):
    """Input ended prematurely
    """
    _default_msg = 'unexpected end'

class BadSyntax(CCException):
    """The message was encoded incorrectly
    """
    _default_msg = 'message syntax error'

class BadForm(CCException):
    """The message was missing required protocol elements, e.g. _ctrl
    """
    _default_msg = 'message format error'

class NotSecure(CCException):
    """Encryption was not available, and encryption policy was set to required
    """
    _default_msg = 'not secure'

class NeedSecret(CCException):
    """A secret is required in order to use encryption
    """
    _default_msg = 'cannot encrypt without a secret'

class Closing(CCException):
    """The session is closing
    """
    _default_msg = 'session closing'

class BadSequence(CCException):
    """The message does not implement the sequence protocol correctly
    """
    _default_msg = 'sequence format error'

class UnexpectedSequence(CCException):
    """The caller said not to expect a sequence, but sequence was received
    """
    _default_msg = 'unexpected sequence'

class BadChannelConf(CCException):
    """The channel.conf file is malformed.
    """
    _default_msg = 'channel.conf format error'

class BadChannelValue(CCException):
    """The parameter is not a valid channel specification
    """
    _default_msg = 'bad channel value'

class UnsupportedAddressFamily(CCException):
    """The address family of the socket is not supported.
    """
    _default_msg = 'unsupported address family'

class Error(CCException):
    """A generic exception used when a request handler wants to
    return a response with an 'err' tag.
    """
    _default_msg = 'unknown error'
    _always_use_default_msg = False

class Timeout(CCException):
    """The operation timed out.
    """
    _default_msg = 'timeout'
