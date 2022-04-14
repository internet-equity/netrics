
# Local imports
from utils.ping import ping

SUPPORTED_UTILS = ["ping"]

def run(util, config):

    if util == "ping":
        ping(config)
    else:
        print(f'Unrecognized utility: {util}')
        print(f'Please select from {*SUPPORTED_UTILS}')

