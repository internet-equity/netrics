import subprocess as sp
import json
import sys
import time

# Default input parameters
PARAM_DEFAULTS = {'targets': ['google.com']}

def parse_trace_stdout(out):
    """
    Parses scamper output and returns minimal results
    """
    res = {}

    res['src'] = out['src']
    res['dst'] = out['dst']
    res['hop_count'] = out['hop_count']
    res['probe_count'] = out['probe_count']
    res['attempts'] = out['attempts']
    res['hops'] = {}

    for i in range(res['probe_count']):
       hop = out['hops'][i]
       resp = {'addr': hop['addr'], 'probe_id': hop['probe_id'], 
               'rtt': hop['rtt']}
       if hop['probe_ttl'] in res['hops']:
           res['hops'][hop['probe_ttl']].append(resp)
       else:
           res['hops'][hop['probe_ttl']] = [resp]

    return res

def dig_stderr_parser(exit_code):
    """
    Parse dig exit code and return interpretable error. Error 
    messages based on Dig man page.
    """

    res = {}
    res['exit_code'] = exit_code
    if exit_code == 1:
        res['msg'] = "Usage error"
    elif exit_code == 8:
        res['msg'] = "Couldn't open batch file"
    elif exit_code == 9:
        res['msg'] = "No reply from server"
    elif exit_code == 10:
        res['msg'] = "Internal error"

    return res

def get_ip(hostname):
    """
    Perform DNS query on hostname, return first IP
    """

    cmd = ['dig', '+short', hostname]

    try:
        res = sp.run(cmd, capture_output=True, check=True)
    except sp.CalledProcessError as err:
        return err.returncode, err.stderr

    ipaddr = res.stdout.decode('utf-8').split('\n')[0]
    return res.returncode, ipaddr

def main():

    # Read config from stdin
    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))

    stdout_res = {}
    stderr_res = {}

    for dst in params['targets']:
        stdout_res[dst] = {}
        stderr_res[dst] = {}

        # Picks first IP addr returned by DNS lookup
        recode, out = get_ip(dst)
        if recode != 0:
            stderr_res[dst]['dig'] = dig_stderr_parser(recode)
            continue
        
        trace_cmd = f'scamper -O json -I "trace -P icmp-paris -q 3 -Q {out}"'

        # Performs traceroute using scamper
        try:
            trace_res = sp.run(trace_cmd, capture_output=True, shell=True, 
                    check=True, timeout=15)
        except sp.TimeoutExpired:
            stderr_res[dst]['traceroute'] = {"exit_code": 3, "msg": "Timeout"}
            continue
        except sp.CalledProcessError as err:
            stderr_res[dst]['traceroute'] = {'exit_code': err.returncode, 
                    "msg": err.stderr.decode('utf-8')}
            continue

        # Parses scamper output
        output = trace_res.stdout.decode('utf-8').split('\n')[1]
        stdout_res[dst] = parse_trace_stdout(json.loads(output))
        stderr_res[dst] = {"exit_code": trace_res.returncode,
                "msg":trace_res.stderr.decode('utf-8')}


    # Communicate results and errors
    json.dump(stdout_res, sys.stdout)
    json.dump(stderr_res, sys.stderr)

    sys.exit(0)
 

if __name__ == '__main__':
    main()
