import subprocess as sp

# Default input parameters
PARAM_DEFAULTS = {'targets': ['google.com', 'facebook.com', 'nytimes.com']}

def main():

    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))

    for dst in params['target']:
        stdout_res[dst] = {}
        stderr_res[dst] = {}

        cmd = ['dig', 
if __name__ == '__main__':
    main()
