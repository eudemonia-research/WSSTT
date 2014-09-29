""" This example demonstrates SSTT's ability to propagate messages.
Each client prints a message when it's received, so many clients can be visually inspected to observe synchrony.

Start many instances with different ports incrementing from 12000. They'll connect and talk to each other and maintain
contact.
"""

import sys
import time
import random
import threading

from encodium import Encodium, String

from SSTT import Network

seeds = (('127.0.0.1', 12000),)


class Message(Encodium):
    name = String.Definition()
    content = String.Definition()


class LMM:
    """ Last message machine, connect to p2p network and display the last broadcast message.
    """

    def __init__(self, port, id: str):
        self.network = Network(seeds=seeds, address=('127.0.0.1', port))
        self.id = id
        self._shutdown = False

        self.previous_messages = set()

        @self.network.method(Message)
        def message(payload):
            if payload.content in self.previous_messages:
                return None
            self.previous_messages.add(payload.content)
            print("%020s: %s" % (payload.name, payload.content))
            self.network.broadcast('message', payload)

    def create_message_occasionally(self):
        print("Starting noise")
        while not self._shutdown:
            time.sleep(random.randint(20,30))
            self.network.broadcast('message', Message(name=self.id, content=str(random.randint(100,100000))))

    def run(self):
        noise_thread = threading.Thread(target=self.create_message_occasionally)
        noise_thread.start()
        try:
            self.network.run()
        except Exception as e:
            print(e)
        finally:
            self.network.shutdown()
            self._shutdown = True
            noise_thread.join()

    def shutdown(self):
        self._shutdown = True


if __name__ == '__main__':
    try:
        port = int(sys.argv[1])

        lmm = LMM(port, str(port))
        lmm.run()
    except:
        print('Usage: ./last_message_machine.py PORT')