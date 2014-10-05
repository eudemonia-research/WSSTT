

# version numbers: major, minor, update
_version_numbers = (0, 0, 2)  # authoritative
_version_integer = sum([n * 10**i for i, n in enumerate(_version_numbers[::-1])])

settings = {
    "version": _version_integer,
    "client": "WSSTT ALPHA %d.%d.%d" % _version_numbers,
    "port": 12345,
    "max_peers": 20,
    "network_id": "WSSTT - UNSET"
}


MESSAGE = 'message'
PAYLOAD = 'payload'
PEER_INFO = 'peer_info'