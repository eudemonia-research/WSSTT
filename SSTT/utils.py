import threading

# todo : `import threading.Thread as fire` does what this does without the fuss
def fire(target, args=()):
    t = threading.Thread(target=target, args=args)
    t.start()
    return t