# Copyright (C) 2004-2014,2016 Nominum, Inc.
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

"""Lower-level Nominum Command Channel connection management.

Do not use Connections directly, use a Session instead.
"""

import random
import socket
import struct
import threading
import time

import nomcc.channel
import nomcc.channelconf
import nomcc.encryption
import nomcc.exceptions
import nomcc.message
import nomcc.wire

from nomcc._compat import *

MAX_WIRE_SIZE = 4 * 1024 * 1024
_U63_MAX = 2 ** 63 - 1

def _generate_nonce():
    try:
        randomness = file('/dev/urandom', 'rb')
        bytes = randomness.read(8)
        randomness.close()
        value = 0
        for b in bytes:
            value *= 256
            value += ord(b)
        value &= _U63_MAX
    except Exception:
        value = int(random.random() * _U63_MAX)
    return value

def _get_nonce_field(_ctrl, field, zero_ok=False):
    if not field in _ctrl:
        raise nomcc.exceptions.BadNoncing('no %s in _ctrl' % field)
    try:
        value = int(_ctrl[field])
    except Exception:
        raise nomcc.exceptions.BadNoncing('%s not an integer' % field)
    if value < 0 or value > _U63_MAX:
        raise nomcc.exceptions.BadNoncing(
              '%s is not a 63-bit unsigned integer' % field)
    if value == 0 and not zero_ok:
        raise nomcc.exceptions.BadNoncing('%s is zero' % field)

    return value

class Connection(object):
    """A command channel connection.

    See the documentation for nomcc.session.connect() for information
    about this class.
    """

    def __init__(self, sock, secret, want_read=False,
                 encryption_policy=nomcc.encryption.DESIRED, tracer=None):
        self.closed = False
        self.sock = sock
        self.secret = secret
        if self.secret is None and \
                encryption_policy == nomcc.encryption.DESIRED:
            # We cannot meet this desire because there's no shared secret,
            # but encryption isn't required so we don't need to cause an
            # error.  We'll simply convert the policy to unencrypted.
            encryption_policy = nomcc.encryption.UNENCRYPTED
        self.self_nonce = _generate_nonce()
        self.self_next = 1
        self.self_first = 1
        self.encryption_policy = encryption_policy
        self.encrypted = False
        self.compressed = False
        self.tracer = tracer
        if want_read:
            request = self._read()
            _ctrl = request['_ctrl']
            if '_rpl' in _ctrl:
                raise nomcc.exceptions.BadNoncing(
                      'cannot initialize nonce state from a reply')
            if '_evt' in _ctrl:
                raise nomcc.exceptions.BadNoncing(
                      'cannot initialize nonce state from an event')
            if _get_nonce_field(_ctrl, '_pnon', True) != 0:
                raise nomcc.exceptions.BadNoncing(
                      '_pnon not zero in initial noncing request')
            self.peer_nonce = _get_nonce_field(_ctrl, '_snon')
            self.peer_next = _get_nonce_field(_ctrl, '_sseq') + 1
        else:
            self.peer_nonce = 0
            self.peer_next = 0
            request = None
        self.lock = threading.Lock() # covers "outstanding"
        self.outstanding = {}
        self._start_noncing(request)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if not self.closed:
            self.close()
        return False

    def _add_outstanding(self, seqno, state):
        with self.lock:
            self.outstanding[seqno] = state

    def _delete_outstanding(self, seqno):
        try:
            with self.lock:
                state = self.outstanding[seqno]
                del self.outstanding[seqno]
            return (True, state)
        except KeyError:
            return (False, None)

    def take_outstanding(self):
        with self.lock:
            outstanding = self.outstanding
            self.outstanding = {}
        return outstanding

    def _noncify(self, message, state=None):
        try:
            _ctrl = message['_ctrl']
        except KeyError:
            _ctrl = {}
            message['_ctrl'] = _ctrl
        _ctrl['_snon'] = maybe_encode(str(self.self_nonce))
        _ctrl['_sseq'] = maybe_encode(str(self.self_next))
        _ctrl['_pnon'] = maybe_encode(str(self.peer_nonce))

        if not ('_rpl' in _ctrl or '_evt' in _ctrl):
            # It's a request; remember its sequence number and state.
            self._add_outstanding(self.self_next, state)

        self.self_next += 1

        if self.encrypted:
            _ctrl['_enc'] = b'1'
        else:
            _ctrl.pop('_enc', None)

        if self.compressed:
            _ctrl['_comp'] = b'1'
        else:
            _ctrl.pop('_comp', None)

    def _check(self, message):
        _ctrl = message['_ctrl']

        if self.encrypted and not '_enc' in _ctrl:
            raise nomcc.exceptions.BadNoncing(
                'got an unencrypted message on an encrypted connection')

        _pnon = _get_nonce_field(_ctrl, '_pnon')
        if _pnon != self.self_nonce:
            raise nomcc.exceptions.BadNoncing(
                '_pnon does not match (%s != %s)' %
                (str(_pnon), str(self.self_nonce)))

        _snon = _get_nonce_field(_ctrl, '_snon')
        if self.peer_nonce == 0:
            self.peer_nonce = _snon
        elif _snon != self.peer_nonce:
            raise nomcc.exceptions.BadNoncing(
                '_snon does not match (%s != %s)' %
                (str(_snon), str(self.peer_nonce)))

        _sseq = _get_nonce_field(_ctrl, '_sseq')
        if self.peer_next == 0:
            self.peer_next = _sseq
        elif _sseq != self.peer_next:
            raise nomcc.exceptions.BadNoncing(
                '_sseq does not match (%s != %s)' %
                (str(_sseq), str(self.peer_next)))

        self.peer_next += 1

        if '_rpl' in _ctrl:
            _rseq = int(_ctrl['_rseq'])
            (found, state) = self._delete_outstanding(_rseq)
            if not found:
                raise nomcc.exceptions.BadNoncing(
                    '_rseq %s is not outstanding' % str(_rseq))
            return state
        else:
            return None

    def _start_noncing(self, request):
        encrypted = False
        compressed = False
        if request is None:
            message = {'_ctrl' : {}, '_data' : {'type' : b'version'}}
            if self.encryption_policy != nomcc.encryption.UNENCRYPTED:
                message['_ctrl']['_initenc'] = [b'aes256z', b'aes256']
        else:
            message = nomcc.message.reply_to(request)
            if self.encryption_policy != nomcc.encryption.UNENCRYPTED:
                _initenc = request['_ctrl'].get('_initenc', [])
                if b'aes256z' in _initenc:
                    message['_ctrl']['_encalg'] = b'aes256z'
                    encrypted = True
                    compressed = True
                elif b'aes256' in _initenc:
                    message['_ctrl']['_encalg'] = b'aes256'
                    encrypted = True
                elif self.encryption_policy == nomcc.encryption.REQUIRED:
                    raise nomcc.exceptions.NotSecure(
                        'encryption is required but not available')
        self.write(message, request)
        if request is None:
            response = self._read_response(message)
            _encalg = response['_ctrl'].get('_encalg')
            if _encalg is not None:
                if self.encryption_policy == nomcc.encryption.UNENCRYPTED:
                    raise nomcc.exceptions.BadNoncing(
                        'encryption not requested but peer specified _encalg')
                elif _encalg == b'aes256z':
                    encrypted = True
                    compressed = True
                elif _encalg == b'aes256':
                    encrypted = True
                else:
                    raise nomcc.exceptions.BadNoncing(
                        'peer specified an invalid _encalg')
            elif self.encryption_policy == nomcc.encryption.REQUIRED:
                raise nomcc.exceptions.NotSecure(
                    'encryption is required but not available')
        self.encrypted = encrypted
        self.compressed = compressed

    def close(self):
        if not self.closed:
            self.sock.close()
            self.closed = True

    def shutdown(self, how=socket.SHUT_RDWR):
        self.sock.shutdown(how)

    def _read_all(self, count):
        """Read the specified number of bytes from sock.  Keep trying until we
        either get the desired amount, or we hit EOF.
        """
        s = b''
        while count > 0:
            n = self.sock.recv(count)
            if n == b'':
                raise EOFError
            count = count - len(n)
            s = s + n
        return s

    def trace(self, obj, message):
        if self.tracer is not None:
            self.tracer(self, obj, message)

    def _read(self):
        ldata = self._read_all(4)
        (l,) = struct.unpack("!I", ldata)
        if l > MAX_WIRE_SIZE:
            raise nomcc.exceptions.MessageTooBig
        wire = self._read_all(l)
        message = nomcc.wire.from_wire(wire, self.secret)
        self.trace('read', message)
        return message

    def read(self):
        """Read a Nominum command channel message from 'sock'.
        """
        message = self._read()
        state = self._check(message)
        return (message, state)

    def _read_response(self, request):
        (response, state) = self.read()
        _ctrl = response['_ctrl']
        if not '_rpl' in _ctrl:
            raise nomcc.exceptions.NotResponse
        if _ctrl['_rseq'] != request['_ctrl']['_sseq']:
            raise nomcc.exceptions.BadResponse
        return response

    def write(self, message, state=None):
        self._noncify(message, state)
        self.trace('write', message)
        wire = nomcc.wire.to_wire(message, self.secret)
        self.sock.sendall(wire)

    def getpeername(self):
        return self.sock.getpeername()

def new(*args, **kwargs):
    return Connection(*args, **kwargs)

def channelify(where):
    if isinstance(where, nomcc.channel.Channel):
        channel = where
    elif isinstance(where, string_types):
        if where.find('#') >= 0:
            parts = where.split('#')
            address = parts[0]
            if len(parts) > 1:
                port = parts[1]
            else:
                port = 0
            if len(parts) > 2:
                secret = parts[2]
            else:
                secret = None
            channel = nomcc.channel.new('<literal>', address + '#' + port,
                                        secret)
        else:
            channel = nomcc.channelconf.find(where)
    else:
        raise nomcc.exceptions.BadChannelValue(where)
    return channel

def connect(where, timeout=None, encryption_policy=nomcc.encryption.DESIRED,
            source=None, tracer=None):
    """Create a command channel connection.

    Applications should not call this method directly; they should create
    a Session object instead.

    'where' is a string or a channel object.  If a string, it can be the
    name of a channel to be retrieved from /etc/channel.conf, or a channel
    literal of the form address[#port[#secret]].

    'timeout' is the timeout for the initial socket.connect().  The
    default is None.

    'encryption_policy' specifies the encryption policy to use for the
    connection, the default is nomcc.encryption.DESIRED, which
    attempts to use encryption but will permit communication if the
    remote server does not allow encryption.

    'source' is the source address and port to use in standard Python
    tuple form.  The default is (0.0.0.0, 0) or (::0, 0, 0, 0) as
    appropriate.

    'tracer' is a method taking a connection object, an operation string, and
    a message string.  The method is invoked at various points of the
    during the connection and can be used for debugging.

    Returns the connection.

    """
    channel = channelify(where)
    if channel.options.get('encrypt-only', False):
        encryption_policy = nomcc.encryption.REQUIRED
    sock = socket.socket(channel.addrport.af)
    sock.settimeout(timeout)
    if source is not None:
        if isinstance(source, str):
            # source is just an address, not a sockaddr; make a
            # sockaddr with a 0 port
            if channel.addrport.af == socket.AF_INET:
                source=(source, 0)
            elif channel.addrport.af == socket.AF_INET6:
                source=(source, 0, 0, 0)
            else:
                raise nomcc.exceptions.UnsupportedAddressFamily
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(source)
    sock.connect(channel.addrport.sending_sockaddr())
    sock.settimeout(None)
    return Connection(sock, channel.secret, None, encryption_policy, tracer)
