# WSSTT constants

# version numbers: major, minor, update
VERSION_NUMBERS = (0, 0, 2)  # authoritative
VERSION_INTEGER = sum([n * 10**i for i, n in enumerate(VERSION_NUMBERS[::-1])])

MESSAGE = 'message'
PAYLOAD = 'payload'
GET_PEER_INFO = 'get_peer_info'
PUT_PEER_INFO = 'put_peer_info'