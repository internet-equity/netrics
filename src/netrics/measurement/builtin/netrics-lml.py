import subprocess as sp
import json
import sys
import ipaddress

# Default input parameters
PARAM_DEFAULTS = {'target': '8.8.8.8'}

def output_parser(out):
    """
    Parses traceroute output and returns last mile info
    """

    res = {}

    res['src'] = out['src']
    res['dst'] = out['dst']
    res['attempts'] = out['attempts']

    for i in range(out['probe_count']):
        hop = out['hops'][i]

        # Check to see if we have ID'ed last mile hop IP addr
        if 'last_mile_ip' in res:
            if hop['addr'] != res['last_mile_ip']:
                break 
            else:
                res['rtts'].append(hop['rtt'])
        
        # Otherwise, see if this is last mile hop
        elif not ipaddress.ip_address(hop['addr']).is_private:
            res['last_mile_ip'] = hop['addr']
            res['rtts'] = [hop['rtt']]

    return res

def error_parser(exit_code, err_msg):
    """
    Handles exit code and returns correct error message

    """
    res = {}

    res['exit_code'] = exit_code
    if exit_code == 0:
        res['msg'] = "Traceroute successful"
    if exit_code == 1:
        res['msg'] = "Network error"
    else:
        res['msg'] = err_msg

    return res

def main():

    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))

    cmd = f'scamper -O json -I "trace -P icmp-paris -q 3 -Q {params["target"]}"'

    # Run scamper traceroute
    try:
        lml_res = sp.run(cmd, capture_output=True, shell=True, check=True)
    except sp.CalledProcessError as err:
        stderr_res = {"exit_code": err.returncode, 
                "msg": err.stderr.decode('utf-8')}
        json.dump(stderr_res, sys.stderr)
        sys.exit(err.returncode)

    output = lml_res.stdout.decode('utf-8').split('\n')[1]
    error = lml_res.stderr.decode('utf-8')

    # Run error parser
    stderr_res = error_parser(lml_res.returncode, error)

    # Process test results
    stdout_res = output_parser(json.loads(output))

    # Communicate stdout, stderr, exit code
    json.dump(stdout_res, sys.stdout)
    json.dump(stderr_res, sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()
