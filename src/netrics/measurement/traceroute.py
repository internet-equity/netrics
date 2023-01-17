import subprocess as sp
import json
import sys
import ipaddress
from shutil import which

# Global error codes
CONFIG_ERROR = 20
BIN_ERROR = 21

# Dig error codes
SUCCESS = 0
USAGE_ERROR = 1
BATCH_FILE = 8
NO_REPLY = 9
INTERNAL_ERROR = 10

# Scamper error codes
SCAMPER_CONFIG_ERROR = 255

# Default input parameters
PARAM_DEFAULTS = {"targets": ["1.1.1.1"],
                  "attempts": 3,
                  "timeout": 5,
                  "verbose": False}

SCAMPER_BIN = "scamper"

def is_executable(name):
    """
    Checks whether `name` is on PATH and marked as executable
    """
    if which(name) is None:
        return BIN_ERROR
    return SUCCESS

def stdin_parser():
    """
    Verifies the type of the input parameters

    Return:
        params: A dict containing input parameters.
        exit_code: Exit code, 20 if unexpected type
    """

    # Read config from stdin and fill in omitted params with default
    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))
    exit_code = SUCCESS

    # Check type of paramters
    try:
        params['interval'] = str(int(params['attempts']))
        params['timeout'] = str(int(params['timeout']))
    except ValueError:
        exit_code = CONFIG_ERROR

    return params, exit_code

def parse_trace_stdout(out):
    """
    Parses scamper output and returns minimal results
    """
    res = {}

    for dst in out:
        try:
            dst_res = json.loads(dst)
            if dst_res['type'] != "trace":
                continue
        except json.decoder.JSONDecodeError:
            continue
        trace_res = {}
        trace_res['src'] = dst_res['src']
        trace_res['dst'] = dst_res['dst']
        trace_res['hop_count'] = dst_res['hop_count']
        trace_res['probe_count'] = len(dst_res['hops'])
        trace_res['attempts'] = dst_res['attempts']
        trace_res['hops'] = []

        for i in range(trace_res['probe_count']):
            hop = dst_res['hops'][i]
            resp = {'addr': hop['addr'], 'probe_id': hop['probe_id'], 
                    'rtt': hop['rtt'], 'ttl_id': hop['probe_ttl']}
            trace_res['hops'].append(resp)
        res[trace_res['dst']] = trace_res

    return res

def parse_dig_stderr(exit_code, verbose, stderr):
    """
    Parse dig exit code and return interpretable error. Error 
    messages based on Dig man page.

    Attributes:
        exit_code: The return code from the dig command.
        verbose: Module parameter to indicate verbose output.
        stderr: Stderr returned by dig.
    """

    if exit_code == SUCCESS:
        return {'retcode': exit_code,
                'message': 'Success'} if verbose else None
    
    elif exit_code == USAGE_ERROR:
        return {'retcode': exit_code, 'message': 'Usage Error'}
    elif exit_code == BATCH_FILE:
        return {'retcode': exit_code, 'message': "Couldn't open batch file"}
    elif exit_code == NO_REPLY:
        return {'retcode': exit_code, 'message': "No reply from server"}
    elif exit_code == INTERNAL_ERROR:
        return {'retcode': exit_code, 'message': "Internal error"}
    elif exit_code > 0:
        return {'retcode': exit_code, 'message': stderr}

    else:
        return None

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
    # Initialize stored structs
    stdout_res = {}
    stderr_res = {}
    exit_code = SUCCESS

    # Check that scamper is available
    exit_code = is_executable(SCAMPER_BIN)
    if exit_code != SUCCESS:
        stderr_res['bin'] = {'retcode': exit_code,
                'message': "Scamper either not on PATH or not executable"}
        json.dump(stderr_res, sys.stderr)
        sys.exit(exit_code)

    # Parse stdin
    params, exit_code = stdin_parser()
    if exit_code != SUCCESS:
        stderr_res['stdin'] = {'retcode': exit_code,
                               "message": "Config param  type error"}
        json.dump(stderr_res, sys.stderr)
        sys.exit(exit_code)

    # Execute traceroutes
    ips = []
    for dst in params['targets']:
        # Picks first IP addr returned by DNS lookup
        try:
            _ = ipaddress.ip_address(dst)
        except ValueError:
            recode, dst = get_ip(dst)
            if stderr_dst := parse_dig_stderr(recode, params['verbose'], dst):
                if "dig" not in stderr_res:
                    stderr_res['dig'] = {}
                stderr_res['dig'][dst] = stderr_dst

            if recode > SUCCESS:
                continue
        ips.append(dst)

    ip_list = " ".join(str(x) for x in ips)

    trace_cmd = f'{SCAMPER_BIN} -O json -i {ip_list} -c "trace -P icmp-paris -q {params["attempts"]} -w {params["timeout"]} -Q"'
    try:
        res = sp.run(trace_cmd, capture_output=True, check=True, shell=True)
    except sp.CalledProcessError as err:
        stderr_res['trace']['error'] = err.stderr
        exit_code = err.returncode
        if err.returncode == SCAMPER_CONFIG_ERROR:
            exit_code = CONFIG_ERROR
        stderr_res['trace']['retcode'] = exit_code
        json.dump(stderr_res, sys.stderr)
        sys.exit(exit_code)

    # Parse scamper output
    output = res.stdout.decode('utf-8').split('\n')
    stdout_res = parse_trace_stdout(output)
    if not stdout_res:
        print("error decoding")
        stderr_res['trace'] = {"exit_code": res.returncode,
                               "msg": res.stderr.decode('utf-8')}

    # Communicate results and errors
    if stdout_res:
        json.dump(stdout_res, sys.stdout)
    if stderr_res:
        json.dump(stderr_res, sys.stderr)
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
