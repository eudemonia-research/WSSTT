import asyncio
import traceback

import websockets

from encodium import Encodium, Integer, String, List

from SSTT.constants import *


MESSAGE = 'message'
PAYLOAD = 'payload'
PEER_INFO = 'peer_info'

Port = Version = Integer
Payload = Message = String


WebsocketAbsent = Exception


class Peer(Encodium):
    host = String.Definition()
    port = Integer.Definition()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.websocket = None
        self.should_ban = False
        self.should_kick = False
        self._error_count = 0  # this resets on a successful request

    def __hash__(self):
        return self.host.__hash__() + self.port.__hash__()

    def request(self, message, payload: Encodium, nonce=0):
        if self.websocket is None:
            raise WebsocketAbsent(self.websocket)
        self.should_kick = False
        self.should_ban = False

        if self._error_count >= 5:
            self.should_ban = True  # todo : bans should have a time associated..
            return None

        yield from self.websocket.send(MessageBubble.from_message_payload(message, payload, nonce=nonce).to_json())
        result = yield from self.websocket.recv()
        print('Request: %s\nResponse: %s' % ((message, payload.to_json()[:144]), result[:144] if result is not None else result))
        if result is None:
            # mark peer banned or bad
            # todo: figure out best policy here
            #self.should_ban = True
            return
        else:
            bubble = MessageBubble.from_json(result)
            self._error_count = 0
            return bubble

    def shutdown(self):
        # If there's a websocket to terminate, do it
        if isinstance(self.websocket, websockets.WebSocketCommonProtocol):
            asyncio.async(self.websocket.close())

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