# Copyright (C) 2016 Nominum, Inc.
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

"""Compatibility support for python 2 and 3 unified source
"""

import sys

if sys.version_info > (3,):
    long = int
    xrange = range
else:
    long = long
    xrange = xrange

if sys.version_info > (3,):
    import io
    StringIO = io.StringIO
    binary_type = bytes
    string_types = (str,)
    def maybe_decode(x):
        return x.decode()
    def maybe_encode(x):
        return x.encode()
else:
    import StringIO
    StringIO = StringIO.StringIO
    binary_type = str
    string_types = (basestring,)
    def maybe_decode(x):
        return x
    def maybe_encode(x):
        return x
