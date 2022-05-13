import json
import subprocess
import re
import sys

def exec(cmd):
    """
    Run ping on command line

    """

    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exec_err:
        return exec_err.returncode, exec_err.output.decode('utf-8')

    return None, out.decode('utf-8')

def main():

    # Read config from stdin
    params = json.load(sys.stdin)

    res = {}

    for dst in params['targets']:
        res[dst] = {}
        ping_cmd = "ping -i {:.2f} -c {:d} -w {:d} {:s} -q".format(
                0.25, 10, 5, dst)

        err, output = exec(ping_cmd)
        if err:
            res[dst]['err'] = True
            res[dst]['err_output'] = output
            res[dst]['err_returncode'] = err
            continue

        res[dst]['err'] = False

        # Extracting packet loss from the output
        res[dst]['pkt_loss'] = float(re.findall(', ([0-9.]*)% packet loss',
                                                output, re.MULTILINE)[0])

        # Extracting other stats from the output
        rtt_stats = re.findall(
                'rtt [a-z/]* = ([0-9.]*)/([0-9.]*)/([0-9.]*)/([0-9.]*) ms', 
                output)[0]

        rtt_stats = [float(v) for v in rtt_stats]

        res[dst]['rtt_min'] = rtt_stats[0]
        res[dst]['rtt_avg'] = rtt_stats[1]
        res[dst]['rtt_max'] = rtt_stats[2]
        res[dst]['rtt_stddev'] = rtt_stats[3]

    json.dump(res, sys.stdout)
    print(params)


if __name__ == '__main__':
    main()
