# Shoe-strings and Thumb-tacks (SSTT)

A light pseudo-p2p network using JSON-RPC over HTTP.

Suitable for frequently communicating p2p networks using a best-effort relay policy.
SSTT handles peer management, and provides a messaging layer on top for nodes to communicate with.

Inspired somewhat by [Spore](https://github.com/encodium-research/Spore)

## Requirements

* Python 3.4+
* [Encodium](https://github.com/eudemonia-research/encoidum)
* jsonrpc-requests
* Flask
* Flask-JSONRPC

## Code Example:

```
from SSTT import Network

network = Network(seeds, addr, debug, etc...)

@network.method(Ping)                  # optional encodium object to deserialize to
def ping(payload):                     # function name is the method name (rpc)
    return Pong(nonce=payload.nonce)   # return an encodium object, will be serialized to json

network.run()
```

