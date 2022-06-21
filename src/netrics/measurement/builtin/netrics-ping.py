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
                  "timeout": 5,
                  "verbose": False}


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


def stderr_parser(exit_code, verbose, stderr):
    """
    Parses error message and error code

    Attributes:
        exit_code: The return code from the ping command.
        verbose: Module parameter to indicate verbose output.
        stderr: Stderr returned by ping.
    """


    if exit_code == SUCCESS:
        return {'retcode': exit_code, 'message': "Success"} if verbose else None

    elif exit_code == NO_REPLY:
        return {'retcode': exit_code,
                'message': "Transmission successful, some packet loss"} if verbose else None

    elif exit_code == LAN_ERROR:
        return {'retcode': exit_code, "message": "Local network error"}

    elif exit_code > 0:
        return {'retcode': exit_code, 'message': stderr}

    else:
        return None


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

    # Initializing module contract structures
    stdout_res = {}
    stderr_res = {}
    exit_code_dst = SUCCESS

    # Parse stdin
    params, err = stdin_parser()
    if err:
        stderr_res['error'] = {"exit_code": err,
                               "msg": """Config param type error (count and
                               timeout must be of type int"""}
        json.dump(stderr_res, sys.stderr)
        sys.exit(err)

    # Execute ping
    procs = []
    for dst in params['targets']:
        cmd = ['ping', '-i', params['interval'],
               '-c', params['count'], '-w', params['timeout'], dst]

        p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        procs.append((dst, p))

    # Process results
    for (dst, p) in procs:
        p.wait()

        # Parse ping exit code and write to output if message or error
        if stderr_dst := stderr_parser(p.returncode, params['verbose'],
                                        p.stderr.read()):
            stderr_res[dst] = stderr_dst

        exit_code_dst = max(exit_code_dst, p.returncode)

        # If LAN error, don't write stdout 
        if p.returncode > NO_REPLY:
            continue

        output = p.stdout.read()
        stdout_res[dst] = stdout_parser(output)


    exit_code = exit_code_dst if exit_code_dst > 1 else 0
    # Communicate results and errors
    if exit_code == SUCCESS:
        json.dump(stdout_res, sys.stdout)
    if stderr_res:
        json.dump(stderr_res, sys.stderr)
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
