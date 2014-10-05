import traceback

import websockets

from encodium import Encodium, Integer, String, List

from .constants import *
from .settings import settings
from .utils import log

MESSAGE = 'message'
PAYLOAD = 'payload'
PEER_INFO = 'peer_info'

Port = Version = Integer
Payload = Message = String


class WebsocketAbsent(Exception):
    pass


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

    def mark_for_kick(self):
        self.should_kick = True

    def mark_for_ban(self):
        self.should_ban = True

    def close(self):
        self.websocket.close()

    def _send(self, message, payload: Encodium, nonce=0):
        if self.websocket is None:
            raise WebsocketAbsent(self.websocket)
        self.should_kick = False
        self.should_ban = False

        if self._error_count >= 5:
            self.should_ban = True  # todo : bans should have a time associated..
            return None

        if not self.websocket.open:
            self.should_kick = True
            return

        try:
            yield from self.websocket.send(MessageBubble.from_message_payload(message, payload, nonce=nonce).to_json())
        except websockets.exceptions.InvalidState as e:
            self.should_kick = True
            raise
        log('Sent: %s\n' % ((message, payload.to_json()[:144]),))

    def shutdown(self):
        # If there's a websocket to terminate, do it
        if isinstance(self.websocket, websockets.WebSocketCommonProtocol):
            self.websocket.close()

    @property
    def as_pair(self):
        return self.host, self.port

    @classmethod
    def from_pair(cls, pair):
        return Peer(host=pair[0], port=pair[1])

class GetPeerInfo(Encodium):
    pass

class PutPeerInfo(Encodium):
    peers = List.Definition(Peer.Definition(), default=[])

class MessageBubble(Encodium):
    version = Version.Definition(default=settings.version)
    client = String.Definition(default=settings.client)
    serving_from = Port.Definition()
    message = Message.Definition()
    payload = Payload.Definition()
    nonce = Integer.Definition()

    @classmethod
    def from_message_payload(cls, message, payload: Encodium, nonce=0):
        return MessageBubble(payload=payload.to_json(), message=message, nonce=nonce, serving_from=settings.port)