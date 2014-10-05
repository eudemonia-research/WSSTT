from .constants import *
from collections import defaultdict

class Settings(defaultdict):
    __getattr__ = defaultdict.__getitem__
    __setattr__ = defaultdict.__setitem__

settings = Settings(lambda : 'UNSET')
settings.version = version_integer
settings.client = "WSSTT ALPHA %d.%d.%d" % version_numbers
settings.short_name = "WSSTT"
settings.port = 12345
settings.max_peers = 20
settings.network_id = "WSSTT - UNSET"