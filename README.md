# Websockets, Shoe-strings and Thumb-tacks (WSSTT)

A light p2p network using WebSockets and TLS.

Suitable for frequently communicating p2p networks using a best-effort relay policy.
WSSTT handles peer management, and provides a messaging layer on top for nodes to communicate with.

Inspired by [Spore](https://github.com/encodium-research/Spore)

## Requirements

* Python 3.4+
* [Encodium](https://github.com/eudemonia-research/encoidum)
* Websockets

## Code Example:

```
from WSSTT import Network

PING = 'ping'
PONG = 'pong'

network = Network(seeds, addr, debug, etc...)

@network.method(incoming_type=Ping,         # Encodium type to deserialize to.
                method=PING,                # If not provided the function's name is used.
                return_method=PONG)         # If anything returned it will be sent to the peer under this method.
def ping(peer: Peer, payload: Encoidum)
    return Pong(nonce=payload.nonce)        # An encodium object should be returned.
                                            # todo: automatically cast Integers, Strings, etc

network.run()
```

