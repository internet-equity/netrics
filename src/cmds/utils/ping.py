from subprocess import Popen, PIPE

def exec(cmd):

    res = Popen(cmd)


def ping(config):
    """
    Parses ping config

    Parameters
    ----------
    config : dict
        Dictionary containing config parameters

    Returns
    -------
    cmd : dict
        Results of the ping test
    """

    destinations = config['destinations']




    
