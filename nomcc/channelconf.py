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

"""Nominum /etc/channel.conf Utilities"""

from __future__ import absolute_import

import errno
import os
import os.path
import re
import threading

import nomcc.channel

from nomcc.exceptions import BadChannelConf
from nomcc._compat import *

_lock = threading.Lock()

def _parse_options(options_list):
    options = {}
    for item in options_list:
        fields = item.split('=', 1)
        try:
            (key, value) = fields
        except ValueError:
            raise BadChannelConf('bad option: %s' % item)
        options[key] = value
    return options

def _split(s, delim, quoting_ok, bug_compatible=True):
    if isinstance(s, str):
        buf = StringIO(s)
    else:
        # Hopefully, whatever they passed in has a .read()...
        buf = s
    read = buf.read
    c = read(1)

    if not bug_compatible:
        while (c != '') and (c in delim):
            c = read(1)

    out = []
    while c != '':
        word = []
        if quoting_ok and (c in '\'"'):
            quote_char = c
            c = read(1)
            while (c != '') and (c != quote_char):
                if c == '\\':
                    c = read(1)
                    if c == '':
                        raise SyntaxError
                word.append(c)
                c = read(1)
            if c != quote_char:
                raise SyntaxError
            c = read(1)

            if (not bug_compatible) and (c != '') and (c not in delim):
                raise SyntaxError
        else:
            while (c != '') and (c not in delim):
                word.append(c)
                c = read(1)
        out.append(''.join(word))
        while (c != '') and (c in delim):
            c = read(1)

    return out

class ChannelConf(dict):
    """/etc/channel.conf container

    A ChannelConf object may be treated as a dictionary: The key is the
    channel name, and the value is a Channel.
    """

    def __init__(self, filename=None):
        """Read a Nominum channel.conf format file from 'filename'.

        If a filename is not specified, the contents of these files will
        be read and merged:
            /etc/channel.conf
            $HOME/.nom/channel.conf
            $NOM_CHANNEL_CONF
        """
        super(ChannelConf, self).__init__()

        if filename is None:
            paths = ['/etc/channel.conf']
            paths.append(os.path.expanduser('~/.nom/channel.conf'))
            env_path = os.environ.get('NOM_CHANNEL_CONF', None)
            if env_path:
                paths.append(env_path)

            for path in paths:
                try:
                    self.update(ChannelConf(path))
                except IOError as e:
                    if e.args[0] not in (errno.ENOENT, errno.EPERM,
                                         errno.EACCES):
                        raise

            return

        ignore_pattern = re.compile(r'(#.*|\s+)')
        with open(filename, 'r') as f:
            for l in f:
                if ignore_pattern.match(l):
                    pass
                else:
                    fields = _split(l.rstrip(), ' \t', True)
                    if len(fields) >= 3:
                        options = _parse_options(fields[3:])
                        channel = nomcc.channel.new(fields[0], fields[1],
                                                    fields[2], options)
                        self[channel.name] = channel
                    else:
                        raise BadChannelConf('too few fields')

default_channelconf = None

def new(*args, **kwargs):
    return ChannelConf(*args, **kwargs)

def find(name):
    global default_channelconf
    with _lock:
        if default_channelconf is None:
            default_channelconf = ChannelConf()
    try:
        return default_channelconf[name]
    except KeyError:
        raise nomcc.exceptions.UnknownChannel(name)
