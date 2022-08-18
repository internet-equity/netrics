import subprocess
import json
import re
import sys
import types

from netrics import errno


# Local error codes
SUCCESS = 0
NO_REPLY = 1
LAN_ERROR = 2

# Default parameters
PARAM_DEFAULTS = {
    "targets": [
        "google.com",
        "facebook.com",
        "nytimes.com",
    ],
    "count": 10,
    "interval": 0.25,
    "timeout": 5,
    "verbose": False,
}

CONFIG_MESSAGE = "Parameter type error (count and timeout must be of type int)"


def get_params():
    """Ensure the type of the input parameters.

    Returns
    -------
    params: A dict containing input parameters

    Raises
    ------
    ValueError

    """
    # Read params from stdin with defaults
    params = PARAM_DEFAULTS.copy()
    if input_ := sys.stdin.read():
        params.update(json.loads(input_))

    # Check type of parameters (count and timeout must be int)
    params['interval'] = str(float(params['interval']))
    params['count'] = str(int(params['count']))
    params['timeout'] = str(int(params['timeout']))

    return types.SimpleNamespace(**params)


def result_log(returncode, stderr, verbose):
    """Construct log message for given result.

    Arguments
    ---------
    returncode: The return code from the ping command.
    stderr: Stderr returned by ping.
    verbose: Module parameter to indicate verbose output.

    """
    if returncode == SUCCESS:
        return {'retcode': returncode, 'message': "Success"} if verbose else None

    if returncode == NO_REPLY:
        return {'retcode': returncode,
                'message': "Transmission successful, some packet loss"} if verbose else None

    if returncode == LAN_ERROR:
        return {'retcode': returncode, "message": "Local network error"}

    return {'retcode': returncode, 'message': stderr}


def parse_result(output):
    """Parse ping output and returns dict with results."""

    # Extract packet loss stats
    pkt_loss_match = re.search(r', ([0-9.]*)% packet loss', output, re.MULTILINE)

    if pkt_loss_match:
        pkt_loss = float(pkt_loss_match.group(1))
    else:
        pkt_loss = -1.0

    # Extract RTT stats
    rtt_match = re.search(
        r'rtt [a-z/]* = ([0-9.]*)/([0-9.]*)/([0-9.]*)/([0-9.]*) ms',
        output
    )

    if rtt_match:
        rtt_values = [float(value) for value in rtt_match.groups()]
    else:
        rtt_values = [-1.0] * 4

    rtt_keys = ('rtt_min', 'rtt_avg', 'rtt_max', 'rtt_stddev')

    rtt_stats = dict(zip(rtt_keys, rtt_values))

    return dict(rtt_stats, pkt_loss=pkt_loss)


def main():
    # Parse stdin params
    try:
        params = get_params()
    except ValueError:
        json.dump({'error': CONFIG_MESSAGE}, sys.stderr)
        sys.exit(errno.CONFIG_ERROR)

    # Launch pings
    procs = []
    for dst in params.targets:
        args = (
            'ping',
            '-i', params.interval,
            '-c', params.count,
            '-w', params.timeout,
            dst,
        )

        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        procs.append((dst, proc))

    # Process results
    dst_code = SUCCESS
    log = {}
    result = {}

    for (dst, proc) in procs:
        proc.wait()

        # We'll report the "worst" exit code as our own
        dst_code = max(dst_code, proc.returncode)

        # Parse ping exit code and write to log if message or error
        if dst_log := result_log(proc.returncode, proc.stderr.read(), params.verbose):
            log[dst] = dst_log

        # If LAN error, don't expect a result
        if proc.returncode >= LAN_ERROR:
            continue

        result[dst] = parse_result(proc.stdout.read())

    exit_code = dst_code if dst_code > NO_REPLY else 0

    # Write out logs and results
    if exit_code == 0:
        json.dump(result, sys.stdout)

    if log:
        json.dump(log, sys.stderr)

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
