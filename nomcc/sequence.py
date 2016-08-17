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

import nomcc.exceptions

DEFAULT_BATCHING = 20

class Reader(object):
    def __init__(self, session, data, timeout, num, raise_error):
        if isinstance(data, str):
            self.request = {'_data' : {'type': data}}
        else:
            self.request = {'_data' : data}
        self.session = session
        self.first = True
        self.done = False
        self._datas = []
        self.timeout = timeout
        self._num = num
        self.raise_error = raise_error
        self._seq = None
        self.batch = False

    def __iter__(self):
        return self

    def __next__(self):
        if len(self._datas) > 0:
            return self._datas.pop()
        elif self.done:
            raise StopIteration
        elif self.first:
            self.first = False
            response = self.session.tell(self.request, self.timeout, False,
                                         True)
            if '_batch' in response['_ctrl'] and self._num > 0:
                self.batch = True
            if '_more' in response['_ctrl']:
                try:
                    self._seq = response['_ctrl']['_seq']
                except KeyError:
                    raise nomcc.exceptions.BadSequence
            else:
                self.done = True
            _data = response['_data']
        else:
            request = {'_ctrl' : { '_seq' : self._seq },
                       '_data' : { 'type' : 'next' }}
            if self.batch:
                request['_ctrl']['_num'] = self._num
            response = self.session.tell(request, self.timeout, False, True)
            if not '_more' in response['_ctrl']:
                self.done = True
            if self.batch and 'list' in response['_data']:
                l = response['_data']['list']
                if not isinstance(l, list):
                    raise nomcc.exceptions.BadSequence
                self._datas = l
                self._datas.reverse()
                if len(self._datas) == 0:
                    raise StopIteration
                _data = self._datas.pop()
            else:
                _data = response['_data']
        if self.done and len(_data) == 1:
            raise StopIteration
        if self.raise_error and 'err' in _data:
            raise nomcc.exceptions.Error(_data['err'])
        return _data

    next = __next__

    def close(self):
        if not self.done:
            self.done = True
            if not self.first:
                request = {'_ctrl' : { '_seq' : self._seq, '_end' : '1' },
                           '_data' : { 'type' : 'next' }}
            response = self.session.tell(request, self.timeout)
