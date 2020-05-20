# Copyright (C) 2019 Akamai Technologies, Inc.
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

"""Information associated with a channel"""

import nomcc.addrport


class Channel(object):
    def __init__(self, name, addrport, secret=None, options=None):
        self.name = name
        if isinstance(addrport, nomcc.addrport.Addrport):
            self.addrport = addrport
        else:
            if addrport.isdigit():
                addrport = '127.0.0.1#' + addrport
            self.addrport = nomcc.addrport.new(addrport)
        if secret == '*':
            # secret "*" means "no secret"
            secret = None
        self.secret = secret
        if options is None:
            options = {}
        self.options = options


def new(*args, **kwargs):
    return Channel(*args, **kwargs)
