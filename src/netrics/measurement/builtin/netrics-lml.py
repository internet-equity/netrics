from json.decoder import JSONDecodeError
import subprocess as sp
import json
import sys
import types
import ipaddress
from shutil import which

# Global error codes
SUCCESS = 0
CONFIG_ERROR = 20
BIN_ERROR = 21

# Dig error codes
USAGE_ERROR = 1
BATCH_FILE = 8
NO_REPLY = 9
INTERNAL_ERROR = 10

# Scamper error codes
SCAMPER_CONFIG_ERROR = 255

# Default input parameters
PARAM_DEFAULTS = {'target': '8.8.8.8',
                  'attempts': 3,
                  'timeout': 5,
                  'verbose': 0}

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

    Returns:
        params: A dict containing the input parameters.
        exit_code: Exit code, 20 if unexpected type
    """

    # Read config from stdin and fill omitted params with default
    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))
    exit_code = SUCCESS

    # Check type of parameter
    try:
        params['attempts'] = str(int(params['attempts']))
        params['timeout'] = str(int(params['timeout']))
    except ValueError:
        exit_code = CONFIG_ERROR
    if str(params['verbose']).lower() in ['true', '1']:
        params['verbose'] = True
    elif str(params['verbose']).lower() in ['false', '0']:
        params['verbose'] = False
    else:
        exit_code = CONFIG_ERROR

    return params, exit_code


def parse_lml(out):
    """
    Parses traceroute output and returns last mile info
    """

    res = {}

    for line in out:
        try:
            record = json.loads(line)
            if record['type'] != 'trace':
                continue
        except json.decoder.JSONDecodeError:
            continue

        res['src'] = record['src']
        res['dst'] = record['dst']
        res['attempts'] = record['attempts']

        for i in range(record['probe_count']):
            hop = record['hops'][i]

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


def parse_scamper_stderr(exit_code, verbose, stderr):
    """
    Handles exit code and returns correct error message
    """

    if exit_code == SUCCESS:
        return {'retcode': exit_code,
                'message': 'Success'} if verbose else None
    elif exit_code == SCAMPER_CONFIG_ERROR:
        return {'retcode': exit_code, 'message': 'Scamper misconfigured'}
    elif exit_code > 0:
        return {'retcode': exit_code, 'message': stderr}

    else:
        return None


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

    # Initialized stored structs
    stdout_res = {}
    stderr_res = {}
    exit_code = SUCCESS

    # Check that scamper is executable and on PATH
    exit_code = is_executable(SCAMPER_BIN)
    if exit_code != SUCCESS:
        stderr_res['bin'] = {'retcode': exit_code,
                             'message': 'Scamper either not on PATH or not executable'}
        json.dump(stderr_res, sys.stderr)
        sys.exit(exit_code)

    # Parse stdin
    params, exit_code = stdin_parser()
    if exit_code != SUCCESS:
        stderr_res['stdin'] = {'retcode': exit_code,
                               'message': 'Config param types error'}
        json.dump(stderr_res, sys.stderr)
        sys.exit(exit_code)

    # Resolve target if given as hostname
    try:
        _ = ipaddress.ip_address(params['target'])
        target_ip = params['target']
    except ValueError:
        recode, target_ip = get_ip(params['target'])
        if stderr_dst := parse_dig_stderr(recode, params['verbose'], target_ip):
            if "dig" not in stderr_res:
                stderr_res['dig'] = {}
            stderr_res['dig'][params['target']] = stderr_dst

    cmd = f'{SCAMPER_BIN} -O json -i {target_ip} -c "trace -P icmp-paris -q {params["attempts"]} -w {params["timeout"]} -Q"'

    # Run scamper traceroute
    try:
        lml_res = sp.run(cmd, capture_output=True, shell=True, check=True)
        output = lml_res.stdout.decode('utf-8').split('\n')
        stdout_res = parse_lml(output)
        if error := parse_scamper_stderr(lml_res.returncode,
                                         params['verbose'],
                                         lml_res.stderr.decode('utf-8')):
            stderr_res['trace'] = error
    except sp.CalledProcessError as err:
        stderr_res['trace'] = parse_scamper_stderr(err.returncode,
                                                   params['verbose'],
                                                   err.stderr.decode('utf-8'))
        exit_code = err.returncode

    # Communicate stdout, stderr, exit code
    if stdout_res:
        json.dump(stdout_res, sys.stdout)
    if stderr_res:
        json.dump(stderr_res, sys.stderr)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
