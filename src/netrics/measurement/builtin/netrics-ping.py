import subprocess as sp
import json
import re
import sys
import time

def stderr_parser(exit_code, err_msg):
    """
    Parses error message and error code

    """
    res = {}

    res['exit_code'] = exit_code
    if exit_code == 0:
        res['msg'] = "Transmission successful"
    if exit_code == 1:
        res['msg'] = "Transmission successful, some packet loss"

    return res

def stdout_parser(exit_code, ping_res):
    """
    Parses ping output and returns dict with results

    """

    stats = {}
    # Extract packet loss stats from output
    stats['pkt_loss'] = float(re.findall(', ([0-9.]*)% packet loss', 
                                        ping_res, re.MULTILINE)[0])

    # Extract RTT stats from output
    try:
        rtt_stats = re.findall(
                'rtt [a-z/]* = ([0-9.]*)/([0-9.]*)/([0-9.]*)/([0-9.]*) ms', 
                ping_res)[0]
    except IndexError:
        rtt_stats = [-1] * 4

    rtt_stats = [float(v) for v in rtt_stats]

    stats['rtt_min'] = rtt_stats[0]
    stats['rtt_avg'] = rtt_stats[1]
    stats['rtt_max'] = rtt_stats[2]
    stats['rtt_stddev'] = rtt_stats[3]

    return stats

def main():

    # Read config from stdin
    params = json.load(sys.stdin)

    stdout_res = {}
    stderr_res = {}

    for dst in params['targets']:
        stdout_res[dst] = {}
        stderr_res[dst] = {}
        cmd = ['ping', '-i', '0.25', '-c', '10', '-w', '5', dst]

        try:
            ping_res = sp.run(cmd, capture_output=True, check=True)
        except sp.CalledProcessError as err:
            # Check for client-side error
            if err.returncode == 2:
                print("command 'ping' failed with exit code 2 and stderr <",
                        err.stderr, ">", file=sys.stderr)
          
                sys.exit(err.returncode)
            else:
                ping_res = err

        output = ping_res.stdout.decode('utf-8')
        error_msg = ping_res.stderr.decode('utf-8')

        # Handle error message
        stderr_res[dst] = stderr_parser(ping_res.returncode, error_msg)

        # Extract results from ping output
        stdout_res[dst] = stdout_parser(ping_res.returncode, output)

    # Communicate results and errors
    json.dump(stdout_res, sys.stdout)
    json.dump(stderr_res, sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()
