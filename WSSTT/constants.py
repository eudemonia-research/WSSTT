# WSSTT constants

# version numbers: major, minor, update
version_numbers = (0, 0, 2)  # authoritative
version_integer = sum([n * 10**i for i, n in enumerate(version_numbers[::-1])])

MESSAGE = 'message'
PAYLOAD = 'payload'
GET_PEER_INFO = 'get_peer_info'
PUT_PEER_INFO = 'put_peer_info'