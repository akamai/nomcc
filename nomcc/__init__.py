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

import nomcc.session
from nomcc.version import version


def connect(*args, **kwargs):
    """Establish a command channel session with a server.

    All arguments are passed directly to nomcc.session.connect(), whose
    documentation is reproduced here for convenience.

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

    'dispatch' is a method taking a session object, a message object, and
    a state object.  The method is invoked for each received message that is
    not a response to an in-flight query.  The nomcc.method.kind() method
    can be used to determine the kind of message, which is either "request",
    "response", or "event".

    Returns a Session object.

    """
    return nomcc.session.connect(*args, **kwargs)
