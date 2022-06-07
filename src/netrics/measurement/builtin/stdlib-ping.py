import subprocess as sp
import json
import re
import sys

# Global error codes
CONFIG_ERROR = 20

# Local error codes
SUCCESS = 0
NO_REPLY = 1
LAN_ERROR = 2

# Default parameters
PARAM_DEFAULTS = {"targets": ["google.com", "facebook.com", "nytimes.com"],
                  "interval": 0.25,
                  "count": 10,
                  "timeout": 5}


def stdin_parser():
    """
    Verifies the type of the input parameters.

    Returns
    -------
    params: A dict containing input parameters
    err: Exit code, 20 if unexpected type
    """

    # Read config from stdin, use default params otherwise
    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))
    err = None

    # Check type of parameters (count and timeout must be int)
    try:
        params['interval'] = str(float(params['interval']))
        params['count'] = str(int(params['count']))
        params['timeout'] = str(int(params['timeout']))
    except ValueError:
        err = CONFIG_ERROR

    return params, err

def stderr_parser(exit_code):
    """
    Parses error message and error code

    """
    res = {}

    res['exit_code'] = exit_code
    if exit_code == SUCCESS:
        res['msg'] = "Transmission successful"
    if exit_code == NO_REPLY:
        res['msg'] = "Transmission successful, some packet loss"

    return res


def stdout_parser(res):
    """
    Parses ping output and returns dict with results

    """

    stats = {}
    # Extract packet loss stats from output
    stats['pkt_loss'] = float(re.findall(', ([0-9.]*)% packet loss',
                                         res, re.MULTILINE)[0])

    # Extract RTT stats from output
    try:
        rtt_stats = re.findall(
            'rtt [a-z/]* = ([0-9.]*)/([0-9.]*)/([0-9.]*)/([0-9.]*) ms',
            res)[0]
    except IndexError:
        rtt_stats = [-1] * 4

    rtt_stats = [float(v) for v in rtt_stats]

    stats['rtt_min'] = rtt_stats[0]
    stats['rtt_avg'] = rtt_stats[1]
    stats['rtt_max'] = rtt_stats[2]
    stats['rtt_stddev'] = rtt_stats[3]

    return stats


def main():
    # Dict for outputs
    stdout_res = {}
    stderr_res = {}

    # Parse stdin
    params, err = stdin_parser()
    if err:
        stderr_res['error'] = {"exit_code": err,
                               "msg": """Config param type error (count and
                               timeout must be of type int"""}
        json.dump(stderr_res, sys.stderr)
        sys.exit(err)

    # Execute ping
    for dst in params['targets']:
        stdout_res[dst] = {}
        stderr_res[dst] = {}
        cmd = ['ping', '-i', params['interval'],
               '-c', params['count'], '-w', params['timeout'], dst]

        try:
            ping_res = sp.run(cmd, capture_output=True, check=True)
        except sp.CalledProcessError as err:
            # Check for client-side error
            if err.returncode == LAN_ERROR:
                stderr_res[dst] = {"exit_code": err.returncode,
                                   "msg": err.stderr}
                json.dump(stderr_res, sys.stderr)
                sys.exit(err.returncode)
            else:
                ping_res = err

        output = ping_res.stdout.decode('utf-8')

        # Handle error message
        stderr_res[dst] = stderr_parser(ping_res.returncode)

        # Extract results from ping output
        stdout_res[dst] = stdout_parser(output)

    # Communicate results and errors
    json.dump(stdout_res, sys.stdout)
    json.dump(stderr_res, sys.stderr)
    sys.exit(SUCCESS)


if __name__ == '__main__':
    main()
