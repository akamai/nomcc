# nomcc

## Introduction

The "nomcc" Python library allows easy communication with services that use
the Nominum Command Channel protocol.  It works with Python 2.7, and
with Python 3.3 and later.

## Installation

Either download the source file and unzip it, or clone the repository,
and then run:
`pip install .`

> Note: if you intend to install directly on a machine instead of
> into a Python virtualenv, you may need to run the command as root.

If you do not have pip, you may install it by fetching and running the
appropriate `get-pip.py` script:

```
# Set $PYTHON to be the path to the Python you are using.
pyver=`$PYTHON -c 'import sys; print(".".join(map(str, sys.version_info[:2])))'`
curl -OL https://bootstrap.pypa.io/pip/${pyver}/get-pip.py
$PYTHON get-pip.py
```

## Examples

Here is an example of how to use nomcc to communicate with an engine.

```python
import nomcc

# Connect to the engine named "engine".
with nomcc.connect('engine') as session:
    # The "version" command takes no parameters, so can be passed as a string.
    # The response will be a table.
    print(session.tell('version'))

    # The "room" object has a color and a list of furniture.  This updates
    # an existing room, using the "room.update" command.
    print(session.tell({'type': 'room.update',
                        'name': 'kitchen',
                        'color' : 'white',
                        'furniture' : ('table', 'chairs')})

    # This sends a command which does not exist, and will raise an exception.
    # To get a response containing the error, add `raise_error=False` to the
    # call, and the response will contain an "err" field with the error.
    try:
        print(session.tell('bogus'))
    except nomcc.exceptions.Error as e:
        print(f'error: {str(e)}')

    # This retrieves the configuration of each room, with a separate response
    # message for each room.
    for r in session.sequence('room.mget'):
        print(r)
```

And another example, which requests and prints events.

```python
import queue

import nomcc

q = queue.SimpleQueue()

def handle_event(session, message, state):
    q.put(message)

with nomcc.connect('engine', dispatch=handle_event) as session:
    session.tell('request-events')
    while True:
        message = q.get()
        if nomcc.message.kind(message) != 'event':
            print('received a message that is not an event')
        else:
            print(f'received event: {message["_data"]}')

```

## Format

Field values may be strings (`str`), lists (`list`), and tables (`dict`).  The
message is a table.  When sending a message, `tuple`s are converted into lists,
and other types are converted into strings.

## Bug reports

Bug reports may be filed at https://github.com/akamai/nomcc.
