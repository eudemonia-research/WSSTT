""" This example demonstrates SSTT's ability to propagate messages.
Each client prints a message when it's received, so many clients can be visually inspected to observe synchrony.

Start many instances with different ports incrementing from 12000. They'll connect and talk to each other and maintain
contact.
"""

import sys
import time
import random
import threading
import traceback

from redis import Redis

from encodium import Encodium, String

from SSTT import Network, utils

seeds = (('127.0.0.1', 12000),)


class Message(Encodium):
    name = String.Definition()
    content = String.Definition()


class Database:

    def __init__(self):
        self.redis = Redis()




class LMM:
    """ Last message machine, connect to p2p network and display the last broadcast message.
    """

    def __init__(self, port, id: str):
        self.network = Network(seeds=seeds, address=('127.0.0.1', port))
        self.id = id
        self._shutdown = False

        self.db = Database()

        self.previous_messages = set()

        @self.network.method(Message)
        def message(payload):
            if payload.content in self.previous_messages:
                return Encodium()
            self.previous_messages.add(payload.content)
            print("%20s: %s" % (payload.name, payload.content))
            self.network.broadcast(message.__name__, payload)
            return Encodium()

    def create_message_occasionally(self):
        print("Starting noise")
        while not self._shutdown:
            random_number = random.randint(100,100000)
            self.network.broadcast('message', Message(name=self.id, content=str(random_number)))
            print("%20s: %s" % ("created", random_number))
            utils.loop_break_on_shutdown(self, random.randint(4,6))

    def start_noise_thread(self):
        self.noise_thread = threading.Thread(target=self.create_message_occasionally)
        self.noise_thread.start()


    def run(self):
        self.start_noise_thread()
        try:
            self.network.run()
        except Exception as e:
            print(e)
        finally:
            self.network.shutdown()
            self._shutdown = True
            self.noise_thread.join()

    def shutdown(self):
        self._shutdown = True
        self.network.shutdown()

try:
    port = int(sys.argv[1])
except:
    port = 1522
print(port, sys.argv, int(sys.argv[1]))

lmm = LMM(port, str(port))

def main():
    try:
        lmm.run()
    except:
        print('Usage: ./last_message_machine.py PORT')
        traceback.print_exc()
    finally:
        lmm.shutdown()

if __name__ == '__main__':
    main()
