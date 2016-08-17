## Introduction

The "nomcc" Python library allows easy communication with services that use
the Nominum Command Channel protocol.  It works with Python 2.6 and 2.7,
and with Python 3.3 and later.

## Installation

- If you have pip installed, you can simply run
`pip install nomcc`
- If not, download the source file, unzip it, and then run
`sudo python setup.py install`

## About this release

This is nomcc 1.0.0.

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

Bug reports may be filed on github.

