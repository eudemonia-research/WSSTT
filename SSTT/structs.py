import jsonrpc_requests
from encodium import Encodium, Integer, String, List

from SSTT.constants import *


MESSAGE = 'message'
PAYLOAD = 'payload'
PEER_INFO = 'peer_info'

Port = Version = Integer
Payload = Message = String


class Peer(Encodium):
    host = String.Definition()
    port = Integer.Definition()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.server = jsonrpc_requests.Server("http://%s:%d/" % (self.host, int(self.port)), timeout=5.0, verify=False)
        self.is_bad = False

    def __hash__(self):
        return self.host.__hash__() + self.port.__hash__()

    def request(self, message, payload: Encodium, nonce=0):
        print(message)
        try:
            result = self.server.send_request(MESSAGE, False,
                                              [MessageBubble.from_message_payload(message, payload, nonce=nonce).to_json()])
            print(result)
            if result is None:
                # mark peer banned or bad
                # todo: figure out best policy here
                self.is_bad = True
            return MessageBubble.from_json(result)
        except Exception as e:
            # todo: bad peer, remove from subscribed
            print("Exception:", e)
            print("Occurred carrying", message, payload)

    @property
    def as_pair(self):
        return self.host, self.port

    @classmethod
    def from_pair(cls, pair):
        return Peer(host=pair[0], port=pair[1])


class PeerInfo(Encodium):
    peers = List.Definition(Peer.Definition(), default=[])


class MessageBubble(Encodium):
    version = Version.Definition()
    client = String.Definition()
    serving_from = Port.Definition()
    message = Message.Definition()
    payload = Payload.Definition()
    nonce = Integer.Definition()

    @classmethod
    def from_message_payload(cls, message, payload: Encodium, nonce=0):
        return MessageBubble(payload=payload.to_json(), version=settings['version'], client=settings['client'],
                             serving_from=settings['port'], message=message, nonce=nonce)