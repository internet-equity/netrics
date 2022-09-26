import subprocess as sp
import json
import sys

PARAM_DEFAULTS = {
    'exec': 'speedtest',
    'params': {
        'accept-license': True,
        'f': 'json',
        'u': 'Mbps',
        'p': 'no'
    }
}

def parse_result(output):

    ret_json = {}

    try:
        res_json = json.loads(output)
    except json.JSONDecodeError as e:
        res_json = {
            'ookla_error': f'{e}'
        }
        json.dump(res_json, sys.stderr)
        
        sys.exit(1)

    download_ookla = res_json["download"]['bandwidth'] * 8 / 1e6
    upload_ookla = res_json["upload"]['bandwidth'] * 8 / 1e6
    jitter_ookla = res_json['ping']['jitter']
    latency_ookla = res_json['ping']['latency']

    # Calculating data transferred 
    ul_bw_used = int(res_json['upload']['bytes']) 
    dl_bw_used = int(res_json['download']['bytes']) 

    pktloss_ookla = None
    if 'packetLoss' in res_json.keys():
        pktloss_ookla = res_json['packetLoss']

    ret_json['total_bytes_consumed'] = ul_bw_used + dl_bw_used
    ret_json["speedtest_ookla_download"] = float(download_ookla)
    ret_json["speedtest_ookla_upload"] = float(upload_ookla)
    ret_json["speedtest_ookla_jitter"] = float(jitter_ookla)
    ret_json["speedtest_ookla_latency"] = float(latency_ookla)
    ret_json["speedtest_ookla_server_host"] = res_json["server"]["host"]
    ret_json["speedtest_ookla_server_name"] = res_json["server"]["name"]
    ret_json["speedtest_ookla_server_id"]   = res_json["server"]["id"] 
    if pktloss_ookla is not None:
        ret_json["speedtest_ookla_pktloss2"] = float(pktloss_ookla)

    return ret_json


def main():

    # Read config from stdin
    params = PARAM_DEFAULTS.copy()
    if input_ := sys.stdin.read():
        params['params'].update(json.loads(input_))
    
    args = (params['exec'],)
    for k, v in params['params'].items():
        args += (f'--{k}' if v is True else f'-{k}',)
        args += (f'{v}'  if v is not True else '',)

    proc = sp.Popen(
        args,
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        text=True,
    )

    proc.wait()

    dst_code = proc.returncode

    if dst_code > 0:
        log = {"ookla_error": f'{proc.stderr.read()}'}
        json.dump(log, sys.stderr)
        sys.exit(dst_code)
    else:
        result = parse_result(proc.stdout.read())
        json.dump(result, sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
