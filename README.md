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

## Example

Here's an example of how to use nomcc to print the answer to a simple
version query, update a resolver, and to iterate the list of resolvers.

```python
import nomcc

with nomcc.connect('cacheserve') as session:
     print session.tell('version')
     print session.tell({'type': 'resolver.update',
                     'name': 'world',
             'dnssec-aware': True})
     for r in session.sequence('resolver.mget'):
         print r
```

## Bug reports

Bug reports may be filed at https://github.com/akamai/nomcc.
