import json
import subprocess as sp
import re
import sys
import time

def exec(cmd):
    """
    Run ping on command line

    """
    
    pipe = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)

   # Wait for process to finish to collect exit code 
    while pipe.poll() is None:
        time.sleep(0.1)

    stdout = pipe.stdout.read().decode('utf-8')
    stderr = pipe.stderr.read().decode('utf-8')
    exit_code = pipe.returncode

    return exit_code, stdout, stderr

def error_handler(exit_code, err_msg):
    """
    Returns error message and error code

    """
    res = {}

    res['exit_code'] = exit_code
    if exit_code == 0:
        res['msg'] = "Transmission successful"
    if exit_code == 1:
        res['msg'] = "Transmission successful, some packet loss"
    else:
        res['msg'] = err_msg

    return res

def parse_ping_output(exit_code, ping_res):
    """
    Parses ping output and returns dict with results

    """

    if exit_code == 2:
        return None

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

    res = {}

    for dst in params['targets']:
        res[dst] = {}
        ping_cmd = "ping -i {:.2f} -c {:d} -w {:d} {:s} -q".format(
                0.25, 10, 5, dst)

        # Execute ping command
        exit_code, stdout, stderr = exec(ping_cmd)

        # Handle error message
        res[dst]['err'] = error_handler(exit_code, stderr)

        # Extract results from ping output
        res[dst]['results'] = parse_ping_output(exit_code, stdout)

    json.dump(res, sys.stdout)
    print(params)


if __name__ == '__main__':
    main()
