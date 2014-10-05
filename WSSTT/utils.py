import threading
import time
import logging

from .constants import *
from .settings import settings

class MyLock:
    def __init__(self):
        self.lock = threading.Lock()

    def __enter__(self):
        log('lock start', time.time())
        self.lock.__enter__()

    def __exit__(self, type, value, tb):
        log('lock end  ', time.time())
        self.lock.__exit__(type, value, tb)



def wait_for_all_threads_to_finish(threads):
    for t in threads:
        t.join()

def fire(target, args=(), kwargs={}):
    t = threading.Thread(target=target, args=args, kwargs=kwargs)
    t.start()
    return t


def nice_sleep(object, seconds):
    '''
    This sleep is nice because it pays attention to an object's ._shutdown variable.
    :param object: some object with a _shutdown variable
    :param seconds: seconds in float, int, w/e
    :return: none
    '''
    for i in range(int(seconds * 10)):
        time.sleep(0.1)
        if object._shutdown:
            break

logger = logging.getLogger(settings.short_name)
logging.basicConfig(filename=settings.short_name + ".log", level=logging.DEBUG)
logging.getLogger('asyncio').setLevel(logging.WARNING)

def log(*args):
    logger.debug('DEBUG: ' + ' '.join([str(a) for a in args]))