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

from flask import Flask, request
from flask_jsonrpc import JSONRPC

from encodium import Encodium, List, String, Integer
import time

from SSTT.constants import *
from SSTT.structs import *
from SSTT.utils import *

class MyLock:
    def __init__(self):
        self.lock = threading.Lock()

    def __enter__(self):
        print('lock start', time.time())
        self.lock.__enter__()

    def __exit__(self, type, value, tb):
        print('lock end  ', time.time())
        self.lock.__exit__(type, value, tb)


class Network:

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
            print(bubble.payload)
            peer_pair = (request.remote_addr, bubble.serving_from)

            if bubble.nonce in self.my_nonces:
                print('banning, detected self')
                self.ban(self.peer_objects[peer_pair])
                return

            peer = Peer(host=request.remote_addr, port=bubble.serving_from)
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

    def method(self, encodium_object: Encodium=Encodium):  # decorator
        def inner_method(func):
            def deserialize_and_pass_to_func(serialized_payload):
                returned_object = func(encodium_object.from_json(serialized_payload))
                if returned_object is None:
                    returned_object = Encodium()
                if not isinstance(returned_object, Encodium):  # sanity check, users can be silly
                    raise Exception('Bad return value, not an encodium object, %s' % str(returned_object))
                nonce = self.get_new_nonce()
                return MessageBubble.from_message_payload(func.__name__, returned_object, nonce=nonce).to_json()

            self.methods[func.__name__] = deserialize_and_pass_to_func
        return inner_method

    def should_add_peer(self, peer: Peer):
        if peer.as_pair in self.banned:
            return False
        if len(self.active_peers) > settings['max_peers']:
            return False
        return True

    def add_subscriber(self, peer: Peer):
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

    def run(self):
        self.crawler_thread = fire(target=self.crawl_loop, args=())
        self.broadcast_thread = fire(target=self.broadcast_loop)

        from tornado.wsgi import WSGIContainer
        from tornado.httpserver import HTTPServer
        from tornado.ioloop import IOLoop

        http_server = HTTPServer(WSGIContainer(self.app))
        http_server.listen(settings['port'])
        IOLoop.instance().start()

    def get_app(self):
        self.crawler_thread = fire(target=self.crawl_loop, args=())
        self.broadcast_thread = fire(target=self.broadcast_loop)
        return self.app

    def shutdown(self):
        self._shutdown = True

    def get_peer(self, pair):
        return self.peer_objects[pair]

    def ban(self, peer: Peer):
        self.kick(peer)
        self.banned.add(peer.as_pair)

    def kick(self, peer: Peer):
        with self.active_peers_lock:
            if peer.as_pair in self.active_peers:
                self.active_peers.remove(peer.as_pair)
            if peer.as_pair in self.peer_objects:
                del self.peer_objects[peer.as_pair]

    def broadcast(self, message, payload):
        self.to_broadcast.put((time.time(), message, payload))

    def broadcast_loop(self):
        loop_break_on_shutdown(self, 3)  # warm up time

        while not self._shutdown:
            try:
                _, message, payload = self.to_broadcast.get(block=True, timeout=0.2)
                with self.active_peers_lock:
                    for pair in self.active_peers:
                        fire(target=self.request_an_obj_from_peer, args=(Encodium, self.peer_objects[pair], message, payload))
            except Empty:
                pass
        print('shutdown')

    def broadcast_with_response(self, encodium_object_to_receive: Encodium, message, payload: Encodium):
        responses = []
        threads = []
        f = lambda : responses.append(self.request_an_obj_from_peer(encodium_object_to_receive, self.get_peer(pair), message, payload))

        with self.active_peers_lock:
            for pair in self.active_peers:
                threads.append(threading.Thread(target=f))
        for t in threads: t.join()
        return [r for r in responses if r is not None]

    def request_an_obj_from_peer(self, encodium_object: Encodium, peer: Peer, method, payload: Encodium=Encodium(), nonce=None):
        if nonce is None:
            nonce = self.get_new_nonce()
        result = peer.request(method, payload, nonce)
        if result is None:
            print('None result', method, payload.to_json())
            #self.ban(peer)
            return result
        else:
            return encodium_object.from_json(result.payload)

    def request_an_obj_from_hive(self, encodium_object: Encodium, method, payload: Encodium=Encodium(), nonce=None):
        with self.active_peers_lock:
            peer = self.peer_objects[random.choice(self.active_peers)]
        result = self.request_an_obj_from_peer(encodium_object, method, payload, nonce)
        if result is None:
            return self.request_an_obj_from_hive(encodium_object, method, payload, nonce)
        else:
            return encodium_object.from_json(result.payload)

    def crawl_loop(self):
        loop_break_on_shutdown(self, 3)  # warm up time

        def get_peer_list(peer: Peer):
            result = self.request_an_obj_from_peer(PeerInfo, peer, PEER_INFO)
            if result is not None:
                return result
            if peer.should_ban:
                # ban
                print('told to ban')
                self.ban(peer)
            elif peer.should_kick:
                self.kick(peer)

        def random_peers():
            # get a completely fresh set of subscribers
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
            new_peers = random_peers()
            self.remove_all_subscribers()
            for peer in new_peers:
                if self.should_add_peer(peer):
                    self.add_subscriber(peer)

        for _ in range(2):
            make_peers_random()

        while not self._shutdown:
            make_peers_random()
            print('tick', self.active_peers, self.peer_objects, self.banned)
            loop_break_on_shutdown(self, 5)
