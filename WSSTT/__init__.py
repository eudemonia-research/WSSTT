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
import threading, random, os, sys, subprocess
from queue import PriorityQueue
from queue import Empty
import time
import asyncio

import websockets
from encodium import Encodium, List, String, Integer

from .constants import *
from .structs import *
from .utils import *
from . import autoreload



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
        def _peer_info(peer: Peer, _):
            with self.active_peers_lock:
                peer_info = PeerInfo(peers=[self.get_peer(i) for i in self.active_peers])
            peer.send(PEER_INFO, peer_info)



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
            def deserialize_and_pass_to_func(peer, serialized_payload):
                returned_object = func(peer, encodium_class.from_json(serialized_payload))

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


    def is_peer_active(self, peer: Peer):
        return peer.as_pair in self.active_peers


    def should_add_peer(self, peer: Peer):
        '''
        :param peer: Peer object to check if we should add
        :return: boolean
        '''
        if peer.as_pair in self.banned or peer.as_pair in self.active_peers:
            return False
        if len(self.active_peers) > settings['max_peers']:
            return False
        return True


    def add_subscriber(self, peer: Peer, websocket: websockets.WebSocketCommonProtocol):
        '''
        Add a peer as a subscriber.
        :param peer: the Peer object to add
        :return: None
        '''
        if not self.should_add_peer(peer):
            return
        print('Add subscriber', peer.to_json())
        if websocket is None:
            print('No websocket')
        else:
            peer.websocket = websocket
        with self.active_peers_lock:
            self.active_peers.add(peer.as_pair)
        asyncio.async(self.listen_loop(peer.host, peer.websocket))


    def remove_all_subscribers(self):
        with self.active_peers_lock:
            for pair in self.active_peers:
                del self.peer_objects[pair]
            self.active_peers.clear()


    def broadcast(self, message, payload):
        self.to_broadcast.put((time.time(), message, payload))


    def broadcast_with_response(self, encodium_class_to_receive: Encodium, message, payload: Encodium=Encodium()):
        with self.active_peers_lock:
            responses = yield from [(yield from self.send_to_peer(self.get_peer(pair), message, payload)) for pair in self.active_peers]
            print(responses)
        return responses


    def send_to_peer(self, peer: Peer, method, payload: Encodium=Encodium(), nonce=None):
        '''
        Seek an `encodium_object` from a randomly chosen peer. Send a `method` and `payload`. Optionally specify a nonce.
        :param peer: A Peer object - will seek from this peer
        :param method: The method as a string
        :param payload: Payload as an encodium object
        :param nonce: an integer or None
        :return: The object sought; None if the call fails
        '''
        if nonce is None:
            nonce = self.get_new_nonce()
        try:
            yield from peer.send(method, payload, nonce)
        except Exception as e:
            print("WARNING", e)
            traceback.print_exc()


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
        result = self.send_to_peer(peer, method, payload, nonce)
        if result is None:
            return self.request_an_obj_from_hive(encodium_class, method, payload, nonce)
        else:
            return result


    def get_new_nonce(self):
        nonce = random.randint(0,2**32)
        self.my_nonces.add(nonce)
        return nonce

    #
    #  Peer and Message stuff
    #


    @asyncio.coroutine
    def listen_loop(self, remote_ip: str, websocket):
        print("Starting listner loop for remote", remote_ip)
        peer = None
        while not self._shutdown and (peer is None or self.is_peer_active(peer)):
            raw_message = yield from websocket.recv()
            if raw_message is None:
                return
            bubble = MessageBubble.from_json(raw_message)
            if peer is None:
                peer = self.get_peer((remote_ip, bubble.serving_from))
                self.add_subscriber(peer, websocket)

            print('Listner loop got', raw_message)
            peer_pair = (websocket.host, websocket.port)

            if bubble.nonce in self.my_nonces:
                print('banning, detected self')
                self.ban(peer)
                return

            yield self.methods[bubble.message](peer, bubble.payload)


    def run(self):
        self._run()

    def _run(self):

        def get_new_websocket(pair):
            try:
                return (yield from websockets.connect("ws://%s:%d" % pair))
            except ConnectionRefusedError:
                self.kick(self.get_peer(pair))

        @asyncio.coroutine
        def on_start():
            print('On_start')
            # init
            yield from asyncio.sleep(0.5)  # warmup
            for seed in self.seeds:
                print(seed)
                if seed != self.address:
                    print('adding', self.get_peer(seed).as_pair)
                    socket = yield from get_new_websocket(seed)
                    if socket is not None:
                        self.add_subscriber(self.get_peer(seed), socket) # need to do this to populate peer_objects

        def broadcaster():
            try:
                _, message, payload = self.to_broadcast.get(block=False)
                print("Broadcast loop got (%s, %s)" % (message, payload.to_json()))
                with self.active_peers_lock:
                    for pair in self.active_peers:
                        asyncio.async(self.send_to_peer(self.get_peer(pair), message, payload))
            except Empty:
                pass
            if not self._shutdown:
                asyncio.get_event_loop().call_later(0.2, broadcaster)


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
                    socket = yield from get_new_websocket(peer.as_pair)
                    self.add_subscriber(peer, socket)

        @asyncio.coroutine
        def crawler():
            ''' This loop crawls for peers.
            First there is some warmup time, then functions are defined.
            Then the main logic takes places which is basically shuffle peers every so often.
            '''

            yield from asyncio.sleep(300)

            while not self._shutdown:
                yield from make_peers_random()
                print('tick', self.active_peers, self.peer_objects, self.banned)
                yield from asyncio.sleep(60)  # mix things up every 15 seconds.


        @asyncio.coroutine
        def handler(websocket: websockets.WebSocketServerProtocol, path):
            print("Starting")
            remote_ip = websocket._stream_reader._transport._sock.getpeername()[0]
            yield from self.listen_loop(remote_ip, websocket)
            print("Ending")


        @asyncio.coroutine
        def reloader(start_server_future):
            while True:
                if autoreload.code_changed():
                    self.shutdown()

                    print('info', 'Detected file change..')

                    while not start_server_future.done():
                        yield from asyncio.sleep(0.1)
                    start_server_future.result().close()
                    print(start_server_future)

                    import signal
                    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))

                    print('info', ' * Restarting')
                    args = [sys.executable] + sys.argv
                    new_environ = os.environ.copy()

                    fire(subprocess.call, (args,), {'env':new_environ})
                    break
                yield from asyncio.sleep(0.2)


        server_future = asyncio.async(websockets.serve(handler, self.address[0], settings['port']))
        asyncio.async(on_start())
        asyncio.async(crawler())
        if self.debug: asyncio.async(reloader(server_future))
        broadcaster()
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


