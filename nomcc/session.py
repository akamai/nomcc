# Copyright (C) 2019 Akamai Technologies, Inc.
# Copyright (C) 2011-2017 Nominum, Inc.
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

"""Nominum Command Channel Sessions"""

import socket
import sys
import threading

import nomcc.closer
import nomcc.connection
import nomcc.encryption
import nomcc.exceptions
import nomcc.message
import nomcc.sequence


class RequestState(object):
    """RequestState represents a request "in flight".

    When ready to wait for the response, call get_response() and the
    thread will block until the answer is available or a timeout occurs.

    The 'request' field is the request that was sent.

    The 'response' field is the response received, but is not valid
    until 'done' is set.  Typically you call get_response() instead of
    reading 'response' directly.
    """
    def __init__(self, session, request, return_data, raise_error,
                 sequence_ok):
        """Create a RequestState for 'request' on 'session'.

        If 'return_data' is true, then get_response() will return the
        _data section of the response.

        If 'raise_error' is true, then get_response() will raise a
        nomcc.exceptions.Error exception if the response has an 'err' field.
        """
        self.done = threading.Event()
        self.request = request
        self.return_data = return_data
        self.raise_error = raise_error
        self.sequence_ok = sequence_ok
        self.response = None
        self.exception = None

    def wait(self, timeout=nomcc.closer.DEFAULT_TIMEOUT):
        """Wait for the request to complete, or the specified timeout
        to occur.
        """
        self.done.wait(timeout)

    def get_response(self, timeout=nomcc.closer.DEFAULT_TIMEOUT):
        """Get the response to the request.

        Waits until the request completes or the specified timeout occurs.
        """
        if not self.done.wait(timeout):
            raise nomcc.exceptions.Timeout
        if self.exception is not None:
            raise self.exception
        if not self.sequence_ok:
            _ctrl = self.response['_ctrl']
            if '_seq' in _ctrl:
                raise nomcc.exceptions.UnexpectedSequence
        _data = self.response['_data']
        if self.raise_error and 'err' in _data:
            raise nomcc.exceptions.Error(_data['err'])
        if self.return_data:
            return self.response['_data']
        else:
            return self.response

    def __call__(self, session, message):
        """Handle 'message' by binding it to the response attribute and
        waking up any waiters.
        """
        self.response = message
        self.done.set()
        return True

    def return_exception(self, exception):
        self.exception = exception
        self.done.set()


def _reader(session):
    """Reader thread."""
    try:
        while True:
            (message, state) = session.connection.read()
            session.not_idle()
            handled = False
            # try to handle the message ...
            try:
                if callable(state):
                    handled = state(session, message)
                if not handled and session.dispatch is not None:
                    handled = session.dispatch(session, message, state)
            except (SystemExit, KeyboardInterrupt,
                    nomcc.exceptions.Closing):
                # ... passing a few exceptions on ...
                raise
            except Exception as e:
                # ... but turning most into error responses
                if nomcc.message.is_request(message):
                    response = nomcc.message.error(message, str(e))
                    session.write(response)
                    handled = True
                session.connection.trace("session reader thread",
                                         "handling error: %s" % str(e))
            if not handled:
                if nomcc.message.is_request(message):
                    response = nomcc.message.error(message,
                                                   "unknown request")
                    session.write(response)
                # otherwise we just drop the message
    except EOFError:
        session.connection.trace("session reader thread",
                                 "end-of-input")
    except Exception:
        (ty, va) = sys.exc_info()[:2]
        session.connection.trace("session reader thread",
                                 "exiting due to exception %s: %s" %
                                 (str(ty), str(va)))
    finally:
        session.request_close()


def _writer(session):
    """Writer thread."""
    try:
        while True:
            with session.write_lock:
                while len(session.write_queue) == 0:
                    session.wake_writer.wait()
                (message, state) = session.write_queue.pop(0)
                if message is None:
                    # request to exit
                    break
            session.not_idle()
            try:
                session.connection.write(message, state)
            except (socket.error, socket.timeout):
                # socket problems are not something we can continue from
                # so reraise
                raise
            except Exception as e:
                # Something went wrong in rendering, but nothing was sent,
                # so the connection is still ok.  Try to inform the
                # originator.
                if state is not None:
                    try:
                        state.return_exception(e)
                    except Exception:
                        # We don't expect this path to happen very
                        # often, so we just trace it for now as
                        # opposed to trying to notify the session
                        # about the bad message some other way.
                        (ty, va) = sys.exc_info()[:2]
                        session.connection.trace("session writer thread",
                                                 "sending message threw " +
                                                 "exception %s: %s" %
                                                 (str(ty), str(va)))
    except Exception:
        (ty, va) = sys.exc_info()[:2]
        session.connection.trace("session writer thread",
                                 "exiting due to exception %s: %s" %
                                 (str(ty), str(va)))
        # We can't continue, so ask for shutdown.
        session.request_close()


class Session(nomcc.closer.ThreadedCloser):
    """A command channel session.

    Run a command channel session on 'connection'.  A session has
    independent reader and writer threads.  Writes are queued and then
    sent by the writer thread.

    Sessions support the context manager protocol.
    """
    def __init__(self, connection, dispatch=None, want_start=True):
        """Initialize a session.

        If 'dispatch' is not None, then it will be used to handle messages
        that don't have an associated RequestState.

        If 'want_start' is True, then the Session's service threads will
        be started.
        """

        super(Session, self).__init__()
        self.connection = connection
        self.dispatch = dispatch
        # sequence_loc covers sequences and next_id
        self.sequence_lock = threading.Lock()
        self.sequences = {}
        self.next_id = 1
        # write_lock covers write_queue and wake_writer
        self.write_lock = threading.Lock()
        self.write_queue = []
        self.wake_writer = threading.Condition(self.write_lock)
        self.reader = threading.Thread(target=_reader, args=[self],
                                       name="cc-reader")
        self.reader.daemon = True
        self.writer = threading.Thread(target=_writer, args=[self],
                                       name="cc-writer")
        self.writer.daemon = True
        self.started = False
        if want_start:
            self.start()

    def start(self):
        """Start the session (if not already started)."""
        if not self.started:
            self._start_closer()
            self.reader.start()
            self.writer.start()
            self.started = True

    def _close(self):
        # We seem to need to do the following shutdown on at
        # least OS X, Linux, and Solaris.
        #
        # If we don't do it, then the close() does nothing if there's
        # a recv() outstanding in another thread until either:
        #
        #       the recv() reads some data (assuming more ever gets sent)
        # or
        #
        #       the other side closes
        #
        try:
            self.connection.shutdown()
        except socket.error:
            # This can happen e.g. if the socket is not connected any
            # more.  We don't care since we're closing, so just eat
            # the exception.
            pass
        self.reader.join()
        # Take possession of the reader's outstanding state and end any
        # requests
        outstanding = self.connection.take_outstanding()
        for state in outstanding.values():
            if state is not None:
                state.exception = nomcc.exceptions.Closing()
                state.done.set()
        with self.write_lock:
            # Tell writer to exit.
            self.write_queue.insert(0, (None, None))
            self.wake_writer.notify()
        self.writer.join()
        with self.write_lock:
            # take possession of the queue remnants
            wq = self.write_queue
            # prevent further write attempts
            self.write_queue = None
        for (message, state) in wq:
            if state is not None:
                state.exception = nomcc.exceptions.Closing()
                state.done.set()
        # Take possession of sequences and close them
        with self.sequence_lock:
            sequences = self.sequences
            self.sequences = None
        for sequence in sequences.values():
            sequence.close()
        self.connection.close()

    def write(self, message, state=None):
        """Add 'message' to the write queue.

        Arbitrary state 'state' is associated with the message.

        Clients should NOT need to call this method directly.
        """
        with self.write_lock:
            if self.write_queue is None:
                raise nomcc.exceptions.Closing
            self.write_queue.append((message, state))
            if len(self.write_queue) == 1:
                self.wake_writer.notify()

    def ask(self, request, raise_error=True, sequence_ok=False):
        """Send a request.

        Note that 'tell()' is usually the more appropriate method to call
        if you want to wait for the answer.

        'request' may be a string, a _data section dictionary, or a
        complete CC message dictionary.  If the request is a string,
        then its value will be treated as the desired CC 'type' and
        only the _data section will be returned.  If the request is
        just a _data section, then only a _data section will be
        returned in the response.

        If 'raise_error' is true, then get_response() will raise a
        nomcc.exceptions.Error exception if the response has an 'err' field.

        If 'sequence_ok' is true, then sequence responses are allowed,
        and the caller is expected to deal with the sequence protocol.
        Normally you should use sequence() to get a sequence.

        Returns a RequestState object that may be used later to retreive
        the response.

        """
        if isinstance(request, str):
            request = {'_data': {'type': request}}
            return_data = True
        elif '_data' not in request:
            # Request is not a full message; caller prefers to deal
            # just with _data.  Wrap into a proper message, and
            # remember to unwrap later.
            request = {'_data': request}
            return_data = True
        else:
            return_data = False
        rstate = RequestState(self, request, return_data, raise_error,
                              sequence_ok)
        self.write(request, rstate)
        return rstate

    def tell(self, request, timeout=nomcc.closer.DEFAULT_TIMEOUT,
             raise_error=True, sequence_ok=False):
        """Send a request and wait for a response.

        'request' may be a string, a _data section dictionary, or a
        complete CC message dictionary.  If the request is a string,
        then its value will be treated as the desired CC 'type' and
        only the _data section will be returned.  If the request is
        just a _data section, then only a _data section will be
        returned in the response.

        The request will timeout and raise an exception if not answered
        within 'timeout' seconds.

        If 'raise_error' is true, then get_response() will raise a
        nomcc.exceptions.Error exception if the response has an 'err' field.

        If 'sequence_ok' is true, then sequence responses are allowed,
        and the caller is expected to deal with the sequence protocol.
        Normally you should use sequence() to get a sequence.

        Returns the response.
        """
        return self.ask(
            request, raise_error, sequence_ok
        ).get_response(timeout)

    def sequence(self, data, timeout=nomcc.closer.DEFAULT_TIMEOUT,
                 num=nomcc.sequence.DEFAULT_BATCHING,
                 raise_error=True):
        """Send a request for a multi-response question, returning a
        a nomcc.sequence.Reader object which may be used to iterate the
        responses.

        'data' is the _data section of the request to send, or a string.
        If 'data' is s a string, then its value will be treated as the
        desired CC type.

        The request will timeout and raise an exception if the next response
        isn't answered within 'timeout' seconds.

        'num' is a hint about the number of responses to return per
        network round-trip.  The default is
        nomcc.sequence.DEFAULT_BATCHING.

        If 'raise_error' is true, then get_response() will raise a
        nomcc.exceptions.Error exception if the response has an 'err' field.

        Returns a nomcc.sequence.Reader object.
        """
        return nomcc.sequence.Reader(self, data, timeout, num, raise_error)

    def add_sequence(self, sequence):
        """Add the specified sequence object to the set of known sequences.

        Returns the sequence id.
        """
        with self.sequence_lock:
            id = str(self.next_id)
            self.next_id += 1
            self.sequences[id] = sequence
        return id

    def delete_sequence(self, id):
        """Delete the sequence object for the specified id.

        A KeyError exception will be raised if the specified sequence does
        not exist.
        """
        with self.sequence_lock:
            sequence = self.sequences[id]
            del self.sequences[id]
        sequence.close()

    def get_sequence(self, id):
        """Get sequence object for the specified id."""
        with self.sequence_lock:
            return self.sequences.get(id)

    def getpeername(self):
        """Get the peername of the other half of the connection.

        Returns an address tuple appropriate to the address family of the
        connection.
        """
        return self.connection.getpeername()

    def set_dispatch(self, dispatch):
        """Set the dispatch function for this session.
        """
        self.dispatch = dispatch


def new(*args, **kwargs):
    """Create a new session.

    All arguments are passed directly to the Session constructor.
    """
    return Session(*args, **kwargs)


def connect(*args, dispatch=None, **kwargs):
    """Establish a command channel session with a server.

    All arguments are passed directly to nomcc.connection.connect(), whose
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
    return Session(nomcc.connection.connect(*args, **kwargs),
                   dispatch=dispatch)
