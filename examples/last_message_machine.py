""" This example demonstrates WSSTT's ability to propagate messages.
Each client prints a message when it's received, so many clients can be visually inspected to observe synchrony.

Start many instances with different ports incrementing from 12000. They'll connect and talk to each other and maintain
contact.
"""

import sys
import time
import random
import threading
import traceback

from encodium import Encodium, String

from WSSTT import Network, utils

seeds = (('127.0.0.1', 12000), ('xk.io', 12000))
import logging
logger = logging.getLogger('websockets.server')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

class Message(Encodium):
    name = String.Definition()
    content = String.Definition()


class LMM:
    """ Last message machine, connect to p2p network and display the last broadcast message.
    """

    def __init__(self, port, id: str, beyond_localhost=False):
        host = '0.0.0.0' if beyond_localhost else '127.0.0.1'
        self.network = Network(seeds=seeds, address=(host, port), debug=True)
        self.id = id
        self._shutdown = False

        self.previous_messages = set()

        @self.network.method(Message)
        def message(peer, payload):
            if payload.content in self.previous_messages:
                return
            self.previous_messages.add(payload.content)
            print("<<%s %10s: %s" % (peer.host + ':' + str(peer.port), payload.name, payload.content))
            self.network.broadcast('message', payload)

    def noise_loop(self):
        print("Starting noise")
        while not self._shutdown and not self.network._shutdown:
            random_number = random.randint(100,100000)
            self.network.broadcast('message', Message(name=self.id, content=str(random_number)))
            print("%20s: %s" % ("created", random_number))
            utils.nice_sleep(self, random.randint(4,20))

    def start_noise_thread(self):
        self.noise_thread = threading.Thread(target=self.noise_loop)
        self.noise_thread.start()

    #def join_threads

    def run(self):
        self.start_noise_thread()
        try:
            self.network.run()
        except Exception as e:
            print(e)
            traceback.print_exc()
        finally:
            self.shutdown()
            self.noise_thread.join()

    def shutdown(self):
        self._shutdown = True
        self.network.shutdown()

try:
    port = int(sys.argv[1])
except:
    print('Usage: ./last_message_machine.py PORT\nThe seed is set to 127.0.0.1:12000\n')
    sys.exit()

if len(sys.argv) > 2:
    beyond_localhost = sys.argv[2] == "TRUE"
else:
    beyond_localhost = False

lmm = LMM(port, "BOT" + str(port), beyond_localhost=beyond_localhost)

def main():
    try:
        lmm.run()
    except:
        traceback.print_exc()
    finally:
        lmm.shutdown()

if __name__ == '__main__':
    main()
