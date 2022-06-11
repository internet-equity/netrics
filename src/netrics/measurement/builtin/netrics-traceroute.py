import subprocess as sp
import json
import sys

# Local error codes
SUCCESS = 0
USAGE_ERROR = 1
BATCH_FILE = 8
NO_REPLY = 9
INTERNAL_ERROR = 10

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

def parse_dig_stderr(exit_code):
    """
    Parse dig exit code and return interpretable error. Error 
    messages based on Dig man page.
    """

    res = {}
    res['exit_code'] = exit_code
    if exit_code == USAGE_ERROR:
        res['msg'] = "Usage error"
    elif exit_code == BATCH_FILE:
        res['msg'] = "Couldn't open batch file"
    elif exit_code == NO_REPLY:
        res['msg'] = "No reply from server"
    elif exit_code == INTERNAL_ERROR:
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
    exit_code = SUCCESS

    # Execute traceroutes
    procs = []
    for dst in params['targets']:
        stdout_res[dst] = {}
        stderr_res[dst] = {}

        # Picks first IP addr returned by DNS lookup
        recode, out = get_ip(dst)
        if recode != SUCCESS:
            stderr_res[dst]['dig'] = parse_dig_stderr(recode)
            continue
        
        trace_cmd = f'scamper -O json -I "trace -P icmp-paris -q 3 -Q {out}"'
        p = sp.Popen(trace_cmd, stdout=sp.PIPE, stderr=sp.PIPE)
        procs.append((dst, p))

    for (dst, p) in procs:
        p.wait()

        # Parse scamper output
        output = p.stdout.read().decode('utf-8').split('\n')[1] 
        stdout_res[dst] = parse_trace_stdout(json.loads(output))
        stderr_res[dst] = {"exit_code": p.returncode, 
                "msg": p.stderr.read().decode('utf-8')}

    # Communicate results and errors
    json.dump(stdout_res, sys.stdout)
    json.dump(stderr_res, sys.stderr)
    sys.exit(exit_code)
 

if __name__ == '__main__':
    main()
