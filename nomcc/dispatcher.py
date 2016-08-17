# Copyright (C) 2006-2014,2016 Nominum, Inc.
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

"""The dispatcher class provides a more sophisticated mechanism for
passing messages to handler functions.  Dispatchers are callable
objects: to use one, instantiate it and pass it as the 'dispatch'
parameter when creating a Session.
"""

import sys
import traceback

import nomcc.handler
import nomcc.message
import nomcc.sequence

class Dispatcher(object):
    def __init__(self):
        self._handlers = []
        self._handler_map = {}
        self._classes = set()
        self._fallback = None
        self._fallback_by_type = {}
        self.handle(self._handle_next, 'next')

    def __call__(self, session, message, state):
        """A Dispatcher is a callable object suitable for
        use as Manager dispatch functions.  The dispatcher will
        reroute any invocations to the appropriate handler function.
        """
        # we compute 'kind' and pass it to handlers for convenience and
        # efficiency
        kind = nomcc.message.kind(message)
        _data = message['_data']
        handled = False
        for handler in self._handlers:
            if handler(session, message, kind):
                handled = True
        mtype = _data.get('type')
        if mtype is not None:
            for handler in self._handler_map.get((kind, mtype), []):
                if handler(session, message, kind):
                    handled = True
            if not handled and kind == 'request':
                # If this is an object.method type command and we didn't
                # handle it, generate an error.
                parts = mtype.split('.', 1)
                if len(parts) > 1:
                    if parts[0] in self._classes:
                        err = "unknown command '%s' on object '%s'" % \
                              (parts[1], parts[0])
                    else:
                        err = "unknown object '%s'" % parts[0]
                    response = nomcc.message.error(message, err)
                    session.write(response)
                    handled = True
        if not handled:
            if self._fallback_by_type.get(kind):
                self._fallback_by_type[kind](session, message)
            elif self._fallback:
                self._fallback(session, message)
            else:
                return False
        return True

    def prepend_handler(self, handler):
        self._handlers.insert(0, handler)

    def _maybe_remember_class(self, key):
        if key[0] != 'request':
            return
        parts = key[1].split('.', 1)
        if len(parts) > 1:
            # remember object classes seen
            self._classes.add(parts[0])

    def add_handler(self, handler):
        map = None
        if isinstance(handler, nomcc.handler.MappedHandler):
            map = handler.handler_map
        if map is not None:
            for key, handlers_to_add in map.items():
                self._maybe_remember_class(key)
                handlers = self._handler_map.get(key)
                if handlers is None:
                    handlers = []
                    self._handler_map[key] = handlers
                handlers.extend(handlers_to_add)
        else:
            self._handlers.append(handler)

    def add_mapped_handler(self, key, handler):
        self._maybe_remember_class(key)
        handlers = self._handler_map.get(key)
        if handlers is None:
            handlers = []
            self._handler_map[key] = handlers
        handlers.append(handler)

    def handle(self, action, selector=None, kind='request'):
        """D.handle(action, selector)

        Construct and install a new handler object.

        'action' is a callable object to invoke when the handler
        triggers; actions will be called with a Session and message
        as arguments.

        'selector' determines what messages will be passed to this
        handler.

        If 'selector' is a string, it indicates the type of message
        this handler applies to.

        If 'selector' is a callable object, it will be called for
        each message received with the Message as an argument.
        The selector should return True for messages that this handler
        applies to.

        If 'selector' is a dictionary, the dictionary keys should be
        field names and the values selection criteria.  If a value
        is a string, the corresponding field must exactly match it.
        If a value is a callable object, it will be called with the
        value of the field and should return True for messages that
        this handler applies to.

        If 'selector' is None, the handler will be called for all
        messages.

        If 'kind' is a string (either "request", "response", or "event"),
        the handler will only be called for messages of that type.  If
        'kind' is None, then the message type is not considered when
        determining if the handler matches.  The default is "request".

        All criteria specified in a selector must match a message
        in order for a handler to receive that message.

        All applicable handlers that match a message will receive
        that message.  Order is not guaranteed.

            # Handle request messages of type 'foo'.
            d.handle(func, 'foo')

            # Handle request messages where 'x' is greater than 'y'.
            d.handle(func, lambda m: int(m['x']) > int(m['y']))

            # Handle request messages where 'one' is equal to '1' and
            # 'two' is equal to '2'.
            d.handle(func, { 'one' : '1', 'two' : '2' })

            # Handle request messages where 'n' is greater than 5.
            d.handle(func, { 'n' : lambda x: int(x) > 5 })
        """

        if not callable(action):
            raise TypeError('invalid callable object: %s' % action)

        if not (kind in nomcc.message.kinds or kind is None):
            raise TypeError('kind must be %s, or None: %s' %
                            ', '.join(['"%s"' for m in nomcc.message.kinds]))

        if isinstance(selector, str) and kind is None:
            # We have a simple type selector for just one kind; use a
            # mapped handler for greater efficiency.
            key = (kind, selector)
            handler = nomcc.handler.ActionHandler(action)
            self.add_mapped_handler(key, handler)
        else:
            if isinstance(selector, str):
                filter = nomcc.handler.DataFilter({'type' : selector})
            elif callable(selector):
                filter = selector
            elif isinstance(selector, dict):
                filter = nomcc.handler.DataFilter(selector.copy())
            elif selector is None:
                filter = None
            else:
                raise TypeError(
                    'selector must be str, callable, dict or None: %s' % \
                    selector)
            handler = nomcc.handler.BasicHandler(action, filter, kind)
            self.add_handler(handler)

    def handle_sequence(self, factory, selector):
        def _(session, message):
            session.write(nomcc.sequence.start(session, message, factory))
            return True
        self.handle(_, selector)

    def _handle_next(self, session, request):
        _seq = request['_ctrl'].get('_seq')
        if _seq is None:
            # We don't bother with more specific exception types because
            # the session will only be looking at the detail when converting
            # the exception into an error response
            raise Exception('_seq missing')
        sequence = session.get_sequence(_seq)
        if sequence is None:
            raise Exception('unknown sequence id: ' + _seq)
        (response, done) = sequence.next_message(request)
        if done:
            session.delete_sequence(_seq)
        session.write(response)
        return True

    def handle_standard(self, *args, **kwargs):
        self.add_handler(nomcc.handler.StandardHandler(*args, **kwargs))

    def fallback(self, action, kind='request'):
        """D.fallback(action)

        Install a fallback handler which will be called if no other
        handlers match a message.

        If 'kind' is a string (either "request", "response", or "event"),
        the fallback handler will only be called for messages of that type.
        """
        if not callable(action):
            raise TypeError('invalid callable object: %s' % action)
        if isinstance(kind, str) and kind in nomcc.message.kinds:
            self._fallback_by_type[kind] = action
        elif kind is None:
            self._fallback = action
        else:
            raise TypeError('kind must be %s, or None: %s'
                            ', '.join(['"%s"' for m in nomcc.message.kinds]))

def new(*args, **kwargs):
    return Dispatcher(*args, **kwargs)
