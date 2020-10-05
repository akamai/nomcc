# Copyright (C) 2019 Akamai Technologies, Inc.
# Copyright (C) 2001-2014,2016 Nominum, Inc.
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

"""Nominum command channel

Encode and decode messages using the Nominum command channel format (V1).
"""

import base64
import hmac
import string
import struct
import hashlib
import random

import zlib

import Crypto.Cipher.AES

from nomcc._compat import *
from nomcc.exceptions import BadVersion, BadAuth, UnexpectedEnd, BadSyntax, \
     BadForm, NeedSecret

__all__ = ["to_wire", "from_wire"]

cc_version = 0x01

cc_vtype_binarydata = 0x01
cc_vtype_table = 0x02
cc_vtype_list = 0x03

cc_auth_fixed = (b'\x05\x5f\x61\x75\x74\x68\x02\x00' +
                 b'\x00\x00\x20\x04\x68\x6d\x64\x35' +
                 b'\x01\x00\x00\x00\x16')

# cipher data block size in octets
cc_aes256_blocksize = 16
# Padding must be as long as blocksize
cc_aes256_padding = b'\xde\xad\xbe\xef' * 4


def _key_from_secret(secret):
    """Convert an arbitrary string into a 32 octet key appropriate for
    use in encrypting a message.
    """
    m = hashlib.sha256()
    m.update(maybe_encode(secret))
    return m.digest()


def _encrypt_message(key, message):
    # Generate a random IV
    iv = [random.randint(0, 0xff) for x in range(cc_aes256_blocksize)]
    iv = struct.pack('%dB' % len(iv), *iv)
    # Pad message to AES blocksize
    msglen = len(message)
    padlen = ((msglen + 0xF) & ~0xF) - msglen
    message += b'\0' * padlen
    # Encrypt
    cipher = Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, IV=iv)
    payload = iv + cipher.encrypt(message)
    return payload


def _decrypt_message(key, message):
    # Fetch IV
    iv = message[0:cc_aes256_blocksize]
    message = message[cc_aes256_blocksize:]
    # Decrypt
    cipher = Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, IV=iv)
    plain = cipher.decrypt(message)
    return plain


def _compress_message(message):
    compress = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
    return compress.compress(message) + compress.flush(zlib.Z_FINISH)


def _decompress_message(message):
    decompress = zlib.decompressobj(-15)
    return decompress.decompress(message) + decompress.flush()


def to_wire(message, secret=None):
    """Convert a message from dictionary format to wire format

    If the secret is not None, it will be used to sign the message.
    """
    # Ensure there's no _auth section in the message
    message.pop('_auth', None)

    # See if we want compression.
    want_compress = message['_ctrl'].pop('_comp', None)

    unsigned = _encode_table(message)
    version = struct.pack('!I', cc_version)

    if '_enc' in message['_ctrl']:
        if secret is None:
            raise NeedSecret

        # Since we're using a block cipher, the message may be padded,
        # so we need to prefix it with its length.
        if want_compress:
            unsigned = struct.pack('!I', len(unsigned)) + \
                    _compress_message(unsigned)
            field_name = '_aes256z'
        else:
            unsigned = struct.pack('!I', len(unsigned)) + unsigned
            field_name = '_aes256'

        key = _key_from_secret(secret)
        payload = _encrypt_message(key, unsigned)
        unsigned = _encode_table({field_name: payload})

    if secret is not None:
        h = hmac.new(maybe_encode(secret), digestmod=hashlib.md5)
        h.update(unsigned)
        sig = base64.b64encode(h.digest())[:-2]              # strip '=='
        res = version + _encode_table({'_auth': {'hmd5': sig}}) + unsigned
    else:
        res = version + unsigned

    l = len(res)

    return struct.pack('!I', l) + res


def _encode_table(item):
    s = b''
    for k in item.keys():
        l = len(k)
        assert(l < 256)
        s += struct.pack('B', l) + maybe_encode(k) + _encode(item[k])
    return (s)


def _encode(item):
    if isinstance(item, dict):
        s = _encode_table(item)
        l = len(s)
        t = cc_vtype_table
    elif isinstance(item, list) or isinstance(item, tuple):
        s = b''.join(map(_encode, item))
        l = len(s)
        t = cc_vtype_list
    else:
        if isinstance(item, bytes):
            s = item
        elif isinstance(item, string_types):
            s = maybe_encode(item)
        else:
            s = maybe_encode(str(item))
        l = len(s)
        t = cc_vtype_binarydata
    return struct.pack('!BI', t, l) + s


def _decode_table(item, top_level=False, want_stringify=None):
    t = {}
    while item != b'':
        l = struct.unpack('B', item[:1])[0] + 1
        if len(item) < l:
            raise UnexpectedEnd('table too short')
        key = decode(item[1:l])
        if top_level and key == '_data' and want_stringify is None:
            # We don't already have a stringify setting, and this is
            # the top-level _data section, which we want stringified.
            sub_want_stringify = True
        else:
            # use whatever stringify setting we had
            sub_want_stringify = want_stringify
        rest = item[l:]
        (value, l) = _decode(rest, sub_want_stringify)
        t[key] = value
        item = rest[l:]
    return t


def _decode_list(item, want_stringify=False):
    li = []
    while item != b'':
        (value, l) = _decode(item, want_stringify)
        li.append(value)
        item = item[l:]
    return li


def _decode(item, want_stringify=False):
    if len(item) < 5:
        raise UnexpectedEnd('value header too short')
    rest = item[5:]
    (type, l) = struct.unpack("!BI", item[:5])
    if len(rest) < l:
        raise UnexpectedEnd('value data too short')
    if type == cc_vtype_binarydata:
        value = rest[:l]
        if want_stringify:
            value = maybe_decode(value)
    elif type == cc_vtype_table:
        value = _decode_table(
            rest[:l], top_level=False, want_stringify=want_stringify
        )
    elif type == cc_vtype_list:
        value = _decode_list(rest[:l], want_stringify)
    else:
        raise BadForm('unknown value type')
    return (value, l + 5)


def _basic_syntax_checks(message, maybe_encrypted):
    if maybe_encrypted and (message.get('_aes256') or message.get('_aes256z')):
        encrypted = True
    else:
        encrypted = False

    if not encrypted:
        _ctrl = message.get('_ctrl')
        if _ctrl is None:
            raise BadForm('_ctrl must be present')
        if not isinstance(_ctrl, dict):
            raise BadForm('_ctrl must be a table')

        _data = message.get('_data')
        if _data is None:
            raise BadForm('_data must be present')
        if not isinstance(_data, dict):
            raise BadForm('_data must be a table')

        type = _data.get('type')
        if type is None:
            raise BadForm('type must be present in _data')
        if not isinstance(type, str):
            raise BadForm('type must be a string')

        err = _data.get('err')
        if err and not isinstance(err, str):
            raise BadForm('err must be a string')

    _auth = message.get('_auth')
    if _auth is not None and not isinstance(_auth, dict):
        raise BadForm('_auth must be a table')


def from_wire(message, secret=None):
    """Convert a message from wire format to dictionary format

    If the secret is not None, it will be used to verify the message.
    """

    if len(message) < 4:
        raise UnexpectedEnd('message version too short')
    version = struct.unpack('!I', message[:4])
    if version[0] != cc_version:
        raise BadVersion('unknown version %u' % version[0])
    rest = message[4:]
    table = _decode_table(rest, top_level=True)
    _basic_syntax_checks(table, True)
    has_auth = '_auth' in table

    if secret is not None or has_auth:
        if secret is None or not has_auth:
            raise BadAuth('signature mismatch')
        if len(message) < 43:
            raise UnexpectedEnd('encrypted message too short')
        auth = rest[:21]
        msig = rest[21:43]
        payload = rest[43:]
        h = hmac.new(maybe_encode(secret), digestmod=hashlib.md5)
        h.update(payload)
        sig = base64.b64encode(h.digest())[:-2]    # strip '=='
        if auth != cc_auth_fixed:
            raise BadAuth('unknown auth mechanism')
        if sig != msig:
            raise BadAuth('signature mismatch')

    _aes256z = table.get('_aes256z')
    _aes256 = table.get('_aes256')
    if _aes256z is None and _aes256 is None:
        _ctrl = table.get('_ctrl')
        _ctrl.pop('_enc', None)
        return table
    else:
        if _aes256z is not None:
            encrypted_data = _aes256z
            compressed = True
        else:
            encrypted_data = _aes256
            compressed = False
        if not isinstance(encrypted_data, binary_type):
            raise BadForm('encrypted input is not a string')

    if secret is None:
        raise NeedSecret

    if len(encrypted_data) % cc_aes256_blocksize != 0:
        raise BadForm('encrypted input is not a multiple of AES block size')

    key = _key_from_secret(secret)
    wire = _decrypt_message(key, encrypted_data)
    (wirelen,) = struct.unpack('!I', wire[0:4])

    if compressed:
        wire = _decompress_message(wire[4:])
    else:
        wire = wire[4:]

    if wirelen > len(wire):
        raise UnexpectedEnd('inner message too short')
    table = _decode_table(wire[0:wirelen], top_level=True)
    _basic_syntax_checks(table, False)

    _ctrl = table.get('_ctrl')
    _ctrl['_enc'] = '1'

    return table
