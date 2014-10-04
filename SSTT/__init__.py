""" Shoe-strings and Thumb-tacks (SSTT) - a light pseudo-p2p network using JSON-RPC over HTTP.
Suitable for frequently communicating p2p networks using a best-effort relay policy.
SSTT handles peer management, and provides a messaging layer on top for nodes to communicate with.

Inspired somewhat by Spore

Example:

import SSTT

network = Network(seeds, addr, debug, etc...)

@network.method(Ping)                  # optional encodium object to deserialize to
def ping(payload):                     # function name is the method name (rpc)
    return Pong(nonce=payload.nonce)   # return an encodium object, will be serialized to json

network.run()
"""

import threading, random
from queue import PriorityQueue
from queue import Empty

from flask import Flask
from flask import request as incoming_request
from flask_jsonrpc import JSONRPC

from encodium import Encodium, List, String, Integer
import time

from .constants import *
from .structs import *
from .utils import *


class Network:
    """ Network is a class to manage P2P relationships.

    To add a message (and associated response) use an @network.method(DeserializeClass) decorator. DeserializeClass
    is optional, and must inherit the Encodium class.
    """

    def __init__(self, seeds=(('127.0.0.1', 54321),), address=('127.0.0.1', 54321), debug=True):
        self.app = Flask(__name__)
        self.app.debug = True
        self.jsonrpc = JSONRPC(self.app, '/', enable_web_browsable_api=True)

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

        @self.jsonrpc.method(MESSAGE)
        def message(serialized_bubble):
            bubble = MessageBubble.from_json(serialized_bubble)
            print(serialized_bubble)
            peer_pair = (incoming_request.remote_addr, bubble.serving_from)

            if bubble.nonce in self.my_nonces:
                print('banning, detected self')
                self.ban(self.peer_objects[peer_pair])
                return

            peer = Peer(host=incoming_request.remote_addr, port=bubble.serving_from)
            if self.should_add_peer(peer):
                self.add_subscriber(peer)

            # these methods should return serialized objects
            return self.methods[bubble.message](bubble.payload)

        @self.method()
        def peer_info(_):
            with self.active_peers_lock:
                return PeerInfo(peers=[self.get_peer(i) for i in self.active_peers])

        # init
        for seed in self.seeds:
            if seed != self.address:
                self.add_subscriber(Peer.from_pair(seed))  # need to do this to populate peer_objects


    def method(self, encodium_class: Encodium=Encodium, name=None):  # decorator
        ''' Decorate a function to turn it into a message on the p2p network. Messages with the **same name as the
        function** will be passed through to it unless the name argument is specified.
        Functions therefore **must** be named identically to the message, or specify the name argument.
        :param encodium_class: The class to deserialize to
        :param name: an optional name to use instead of the function name
        :return: a function - .method() is a decorator
        '''
        def inner_method(func):
            def deserialize_and_pass_to_func(serialized_payload):
                returned_object = func(encodium_class.from_json(serialized_payload))
                if returned_object is None:
                    returned_object = Encodium()
                if not isinstance(returned_object, Encodium):  # sanity check, users can be silly
                    raise Exception('Bad return value, not an encodium object, %s' % str(returned_object))
                nonce = self.get_new_nonce()
                return MessageBubble.from_message_payload(func.__name__, returned_object, nonce=nonce).to_json()

            self.methods[func.__name__ if name is None else name] = deserialize_and_pass_to_func
        return inner_method


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


    def add_subscriber(self, peer: Peer):
        '''
        Add a peer as a subscriber.
        :param peer: the Peer object to add
        :return: None
        '''
        with self.active_peers_lock:
            self.active_peers.add(peer.as_pair)
        self.peer_objects[peer.as_pair] = peer


    def remove_all_subscribers(self):
        with self.active_peers_lock:
            for pair in self.active_peers:
                del self.peer_objects[pair]
            self.active_peers.clear()


    def get_new_nonce(self):
        nonce = random.randint(0,2**32)
        self.my_nonces.add(nonce)
        return nonce


    def start_threads(self):
        self.crawler_thread = fire(target=self.crawl_loop, args=())
        self.broadcast_thread = fire(target=self.broadcast_loop)


    def run(self):
        self.start_threads()

        from tornado.wsgi import WSGIContainer
        from tornado.httpserver import HTTPServer
        from tornado.ioloop import IOLoop

        http_server = HTTPServer(WSGIContainer(self.app))
        http_server.listen(settings['port'])
        IOLoop.instance().start()


    def get_app(self):
        self.start_threads()
        return self.app


    def shutdown(self):
        self._shutdown = True


    def get_peer(self, pair):
        return self.peer_objects[pair]


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


    def broadcast(self, message, payload):
        self.to_broadcast.put((time.time(), message, payload))


    def broadcast_loop(self):
        nice_sleep(self, 3)  # warm up time

        while not self._shutdown:
            try:
                _, message, payload = self.to_broadcast.get(block=True, timeout=0.2)
                print("Broadcast loop got (%s, %s)" % (message, payload))
                with self.active_peers_lock:
                    for pair in self.active_peers:
                        fire(target=self.request_an_obj_from_peer, args=(Encodium, self.peer_objects[pair], message, payload))
            except Empty:
                pass
        print('shutdown')


    def broadcast_with_response(self, encodium_class_to_receive: Encodium, message, payload: Encodium=Encodium()):
        responses = []
        threads = []

        f = lambda host_port : responses.append(self.request_an_obj_from_peer(encodium_class_to_receive, self.get_peer(host_port), message, payload))

        with self.active_peers_lock:
            for pair in self.active_peers:
                threads.append(fire(target=f, args=(pair,)))
        for t in threads: t.join()
        return [r for r in responses if r is not None]


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
        result = peer.request(method, payload, nonce)
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


    def crawl_loop(self):
        ''' This loop crawls for peers.
        First there is some warmup time, then functions are defined.
        Then the main logic takes places which is basically shuffle peers every so often.
        '''
        nice_sleep(self, 3)  # warm up time

        def get_peer_list(peer: Peer):
            '''
            :param peer
            :return: the peerlist of peer, or None on error
            '''
            result = self.request_an_obj_from_peer(PeerInfo, peer, PEER_INFO)
            if result is not None:
                return result


        def random_peers():
            '''
            :return: A completely fresh set of subscribers
            '''
            populate_peerlist = lambda i : peerlists.append(get_peer_list(self.get_peer(i)))
            with self.active_peers_lock:
                peerlists = [PeerInfo(peers=[self.get_peer(i) for i in self.active_peers])]
                threads = [fire(populate_peerlist, args=(i,)) for i in self.active_peers]
            for t in threads: t.join()
            peerlists = [i for i in peerlists if i is not None and len(i.peers) > 0]
            if len(peerlists) == 0:
                return set()
            new_peers = set()
            for i in range(10): new_peers.add(random.choice(random.choice(peerlists).peers))
            return new_peers


        def make_peers_random():
            '''
            :return: set of fresh Peer objects
            '''
            new_peers = random_peers()
            self.remove_all_subscribers()
            for peer in new_peers:
                if self.should_add_peer(peer):
                    self.add_subscriber(peer)


        for _ in range(2):
            make_peers_random()  # shake things up to begin with

        while not self._shutdown:
            make_peers_random()
            print('tick', self.active_peers, self.peer_objects, self.banned)
            nice_sleep(self, 60*15)  # mix things up every 15 minutes.
