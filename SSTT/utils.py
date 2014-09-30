import threading
import time

# todo : `import threading.Thread as fire` does what this does without the fuss
def fire(target, args=()):
    t = threading.Thread(target=target, args=args)
    t.start()
    return t


def loop_break_on_shutdown(object, seconds):
    for i in range(int(seconds * 10)):
        time.sleep(0.1)
        if object._shutdown:
            break