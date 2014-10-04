""" WSSTT - a light pseudo-p2p network using JSON-RPC over HTTP.
Suitable for frequently communicating p2p networks using a best-effort relay policy.
WSSTT handles peer management, and provides a messaging layer on top for nodes to communicate with.

Inspired somewhat by Spore

Example:

from WSSTT import Network

network = Network(seeds, addr, debug, etc...)

@network.method(Ping)                  # optional encodium object to deserialize to
def ping(payload):                     # function name is the method name (rpc)
    return Pong(nonce=payload.nonce)   # return an encodium object, will be serialized to json

network.run()
"""
import asyncio

import threading, random
from queue import PriorityQueue
from queue import Empty

import websockets
from encodium import Encodium, List, String, Integer
import time

from .constants import *
from .structs import *
from .utils import *


class Network:
    """ Network is a class to manage P2P relationships.

    To add a message (and associated response) use an @network.method(DeserializeType) decorator. DeserializeType
    is optional, and must inherit the Encodium class.
    """

    def __init__(self, seeds=(('127.0.0.1', 54321),), address=('127.0.0.1', 54321), debug=True):
        if debug:
            import logging
            logger = logging.getLogger('websockets.server')
            logger.setLevel(logging.DEBUG)
            logger.addHandler(logging.StreamHandler())

        self._shutdown = False

        self.seeds = seeds
        self.address = address
        settings['port'] = address[1]
        self.debug = debug

        self.active_peers = set()  # contains ('host', int(port)) tuples
        self.active_peers_lock = threading.Lock()  # use MyLock() to test
        self.peer_objects = {}  # map host-port tuples to Peer objects
        self.banned = set()  # contains host-pair tuples.
        self.my_nonces = set()

        self.methods = {}

        self.to_broadcast = PriorityQueue()

        @self.method(name=PEER_INFO)
        def _peer_info(_):
            with self.active_peers_lock:
                return PeerInfo(peers=[self.get_peer(i) for i in self.active_peers])



    def method(self, encodium_class: Encodium=Encodium, name=None):  # decorator
        ''' Decorate a function to turn it into a message on the p2p network. Messages with the **same name as the
        function** will be passed through to it unless the name argument is specified.
        Functions therefore **must** be named identically to the message, or specify the name argument.
        :param encodium_class: The class to deserialize to
        :param name: an optional name to use instead of the function name
        :return: a function - .method() is a decorator
        '''
        def inner_method(func):
            method = func.__name__ if name is None else name
            def deserialize_and_pass_to_func(serialized_payload):
                returned_object = func(encodium_class.from_json(serialized_payload))
                if returned_object is None:
                    returned_object = Encodium()
                if not isinstance(returned_object, Encodium):  # sanity check, users can be silly
                    raise Exception('Bad return value, not an encodium object, %s' % str(returned_object))
                nonce = self.get_new_nonce()
                return MessageBubble.from_message_payload(method, returned_object, nonce=nonce).to_json()

            self.methods[method] = deserialize_and_pass_to_func
        return inner_method


    def get_peer(self, host_port):
        pair = host_port
        host, port = host_port
        if pair in self.peer_objects:
            return self.peer_objects[pair]
        self.peer_objects[pair] = Peer(host=host, port=port)
        return self.peer_objects[pair]


    def all_peers(self):
        return [self.peer_objects[pair] for pair in self.active_peers]


    def should_add_peer(self, peer: Peer):
        '''
        :param peer: Peer object to check if we should add
        :return: boolean
        '''
        if peer.as_pair in self.banned:
            return False
        if len(self.active_peers) > settings['max_peers']:
            return False
        return True


    def add_subscriber(self, peer: Peer, websocket: websockets.WebSocketCommonProtocol=None):
        '''
        Add a peer as a subscriber.
        :param peer: the Peer object to add
        :return: None
        '''
        if not self.should_add_peer(peer):
            return
        print('Add sub', peer.to_json())
        with self.active_peers_lock:
            self.active_peers.add(peer.as_pair)
        if websocket is None:
            print('No websocket')
        else:
            print('have websocket')
            print(websocket)
            peer.websocket = websocket


    def remove_all_subscribers(self):
        with self.active_peers_lock:
            for pair in self.active_peers:
                del self.peer_objects[pair]
            self.active_peers.clear()


    def broadcast(self, message, payload):
        self.to_broadcast.put((time.time(), message, payload))


    def broadcast_with_response(self, encodium_class_to_receive: Encodium, message, payload: Encodium=Encodium()):
        with self.active_peers_lock:
            responses = yield from [(yield from self.request_an_obj_from_peer(encodium_class_to_receive, self.get_peer(pair), message, payload)) for pair in self.active_peers]
            print(responses)
        return responses


    @asyncio.coroutine
    def request_an_obj_from_peer(self, encodium_class: Encodium, peer: Peer, method, payload: Encodium=Encodium(), nonce=None):
        '''
        Seek an `encodium_object` from a randomly chosen peer. Send a `method` and `payload`. Optionally specify a nonce.
        :param encodium_class: The class to seek (not an instance)
        :param peer: A Peer object - will seek from this peer
        :param method: The method as a string
        :param payload: Payload as an encodium object
        :param nonce: an integer or None
        :return: The object sought; None if the call fails
        '''
        if nonce is None:
            nonce = self.get_new_nonce()
        try:
            result = yield from peer.request(method, payload, nonce)
        except Exception as e:
            result = None  # peer was probably uninitialized
            print("WARNING", e)
            traceback.print_exc()
        if result is None:
            print('None result', method, payload.to_json())
            #self.ban(peer)
            if peer.should_ban:
                # ban
                print('told to ban')
                self.ban(peer)
            elif peer.should_kick:
                self.kick(peer)
        else:
            print(result.payload)
            return encodium_class.from_json(result.payload)


    def request_an_obj_from_hive(self, encodium_class: Encodium, method, payload: Encodium=Encodium(), nonce=None):
        '''
        Seek an `encodium_object` from a randomly chosen peer. Send a `method` and `payload`. Optionally specify a nonce.
        :param encodium_class: The class to seek (not an instance)
        :param method: The method as a string
        :param payload: Payload as an encodium object
        :param nonce: an integer or None
        :return: The object sought; we call this function recursively if the call to a specific peer fails.
        '''
        with self.active_peers_lock:
            peer = self.peer_objects[random.sample(self.active_peers, 1)[0]]
        result = self.request_an_obj_from_peer(encodium_class, peer, method, payload, nonce)
        if result is None:
            return self.request_an_obj_from_hive(encodium_class, method, payload, nonce)
        else:
            return result


    def get_new_nonce(self):
        nonce = random.randint(0,2**32)
        self.my_nonces.add(nonce)
        return nonce


    def run(self):
        @asyncio.coroutine
        def on_start():
            print('On_start')
            # init
            for seed in self.seeds:
                print(seed)
                if seed != self.address:
                    print('adding', self.get_peer(seed).to_json())
                    socket = yield from websockets.connect("ws://%s:%d" % seed)
                    print(socket)
                    self.add_subscriber(self.get_peer(seed), socket) # need to do this to populate peer_objects

        def broadcaster():
            try:
                _, message, payload = self.to_broadcast.get(block=False)
                print("Broadcast loop got (%s, %s)" % (message, payload.to_json()))
                with self.active_peers_lock:
                    for pair in self.active_peers:
                        asyncio.async(self.request_an_obj_from_peer(Encodium, self.get_peer(pair), message, payload))
            except Empty:
                pass
            if not self._shutdown:
                asyncio.get_event_loop().call_later(0.2, broadcaster)
        broadcaster()



        def random_peers():
            '''
            :return: A completely fresh set of subscribers
            '''
            peerlists = yield from self.broadcast_with_response(PeerInfo, PEER_INFO)

            print('Random peers', peerlists)

            with self.active_peers_lock:
                peerlists += [PeerInfo(peers=[self.get_peer(i) for i in self.active_peers])]

            peerlists = [pl for pl in peerlists if pl is not None and len(pl.peers) > 0]

            if len(peerlists) == 0:
                return set()
            new_peers = set()
            for i in range(10): new_peers.add(random.choice(random.choice(peerlists).peers))
            return new_peers


        def make_peers_random():
            '''
            :return: set of fresh Peer objects
            '''
            print('make_peers_random')
            new_peers = yield from random_peers()
            #self.remove_all_subscribers()
            for peer in new_peers:
                if self.should_add_peer(peer):
                    socket = yield from websockets.connect("ws://%s:%d" % peer.as_pair)
                    self.add_subscriber(peer, socket)

        @asyncio.coroutine
        def crawler():
            ''' This loop crawls for peers.
            First there is some warmup time, then functions are defined.
            Then the main logic takes places which is basically shuffle peers every so often.
            '''

            yield from asyncio.sleep(3)

            while not self._shutdown:
                yield from make_peers_random()
                print('tick', self.active_peers, self.peer_objects, self.banned)
                yield from asyncio.sleep(15)  # mix things up every 15 seconds.


        @asyncio.coroutine
        def handler(websocket: websockets.WebSocketServerProtocol, path):
            print("Starting")
            peer = self.get_peer((websocket.host, websocket.port))
            self.add_subscriber(peer, websocket)
            while not self._shutdown:
                raw_message = yield from websocket.recv()
                if raw_message is None:
                    return
                bubble = MessageBubble.from_json(raw_message)

                print('Main handler got', raw_message)
                peer_pair = (websocket.host, websocket.port)

                if bubble.nonce in self.my_nonces:
                    print('banning, detected self')
                    self.ban(self.peer_objects[peer_pair])
                    return

                peer = self.get_peer(peer_pair)
                if self.should_add_peer(peer):
                    if peer.websocket is None:
                        socket = yield from websockets.connect("ws://%s:%d" % peer.as_pair)
                    else:
                        socket = peer.websocket
                    self.add_subscriber(peer, socket)

                yield from websocket.send(self.methods[bubble.message](bubble.payload))
            print("Ending")

        start_server = websockets.serve(handler, self.address[0], settings['port'])

        asyncio.get_event_loop().run_until_complete(start_server)
        #asyncio.async(crawl_loop())
        print(0)
        asyncio.async(on_start())
        print(1)
        asyncio.async(crawler())
        print(2)
        asyncio.get_event_loop().run_forever()


    def shutdown(self):
        self._shutdown = True


    def ban(self, peer: Peer):
        self.kick(peer)
        self.banned.add(peer.as_pair)


    def kick(self, peer: Peer):
        print('kick', peer.to_json())
        with self.active_peers_lock:
            if peer.as_pair in self.active_peers:
                self.active_peers.remove(peer.as_pair)
            if peer.as_pair in self.peer_objects:
                del self.peer_objects[peer.as_pair]
        peer.shutdown()


