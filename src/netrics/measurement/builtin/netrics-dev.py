import subprocess as sp
import json
import sys
import time

PARAM_DEFAULTS = {"iface": "eth0"}

def parse_arp_output(out):
    """
    Parses arp output and returns results
    """
    res = {}

    ts = int(time.time()) 
    devices = set(out.decode('utf-8').strip().split('\n'))

    # Parsing 
    res['n_devs'] = len(devices)
    res['devs'] = []
    for dev in devices:
        res['devs'].append({'name': dev, 'ts': ts})

    return res

def main():

    params = dict(PARAM_DEFAULTS, **json.load(sys.stdin))

    stdout_res = {}

    # Get local subnet
    route_cmd = f"ip r | grep -v default | grep src | grep {params['iface']} | head -n 1 | awk '{{print $1;}}'"

    try:
        subnet_res = sp.run(route_cmd, capture_output=True, shell=True, check=True)
    except sp.CalledProcessError as err:
        stderr_res = {"exit_code": err.returncode, 
                "msg": err.stderr.decode('utf-8')}
        json.dump(stderr_res, sys.stderr)
        sys.exit(err.returncode)

    subnet = subnet_res.stdout.decode('utf-8').strip('\n')

    nmap_cmd = ['nmap', '-sn', subnet]

    try:
        sp.run(nmap_cmd, capture_output=True, check=True)
    except sp.CalledProcessError as err:
        stderr_res = {"exit_code": err.returncode,
                "msg": err.stderr.decode('utf-8')}
        json.dump(stderr_res, sys.stderr)
        sys.exit(err.returncode)

    arp_cmd =  (f"/usr/sbin/arp -i {params['iface']} -n | grep : |"
                "grep -v '_gateway' | tr -s ' ' | "
                "cut -f3 -d' ' | sort | uniq")

    # Run ARP to count devices
    try:
        arp_res = sp.run(arp_cmd, capture_output=True, check=True)
    except sp.CalledProcessError as err:
        stderr_res = {"exit_code": err.returncode, 
                "msg": err.stderr.decode('utf-8')}
        json.dump(stderr_res, sys.stderr)
        sys.exit(err.returncode)

    # Parse arp output
    stdout_res = parse_arp_output(arp_res)
    stderr_res = {"exit_code": arp_res.returncode, 
            "msg": arp_res.stderr.decode('utf-8')}

    json.dump(stdout_res, sys.stdout)
    json.dump(stderr_res, sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()
