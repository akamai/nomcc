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


def reply_to(request, request_type=None):
    _ctrl = {}
    _data = {}
    response = {'_ctrl': _ctrl, '_data': _data}
    if request_type is not None:
        t = request_type
    else:
        t = request['_data'].get('type')
    if t is not None:
        _data['type'] = t
    _ctrl['_rpl'] = b'1'
    _ctrl['_rseq'] = request['_ctrl']['_sseq']
    s = request['_ctrl'].get('_seq')
    if s is not None:
        _ctrl['_seq'] = s
    return response


def error(request, detail, request_type=None):
    response = reply_to(request, request_type)
    response['_data']['err'] = detail
    return response


def request(content):
    message = {'_ctrl': {},
               '_data': content}
    return message


def event(content):
    message = {'_ctrl': {'_evt': b'1'},
               '_data': content}
    return message


def is_reply(message):
    return '_rpl' in message['_ctrl']


def is_event(message):
    return '_evt' in message['_ctrl']


def is_request(message):
    _ctrl = message['_ctrl']
    return not ('_rpl' in _ctrl or '_evt' in _ctrl)


def kind(message):
    _ctrl = message['_ctrl']
    if '_rpl' in _ctrl:
        return 'response'
    elif '_evt' in _ctrl:
        return 'event'
    else:
        return 'request'


kinds = frozenset(('request', 'response', 'event'))
