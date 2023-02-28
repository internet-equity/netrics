"""Measure latency to the "last mile" host via scamper."""
import json
import random
import shutil
import statistics
import subprocess
from ipaddress import ip_address
from itertools import groupby

from schema import Optional

from netrics import task

from .common import AddressLookups, require_net


#
# params schema
#
PARAMS = task.schema.extend('last_mile_rtt', {
    # destinations: (scamper): list of hosts (IP address preferred!)
    #                          OR mapping of hosts to their labels (for results)
    #                          (Note: will select ONE)
    Optional('destinations',
             default={'8.8.8.8': 'Google_DNS',
                      '1.1.1.1': 'Cloudflare_DNS'}): task.schema.DestinationCollection(),

    # attempts: (scamper): natural number
    Optional('attempts', default='3'): task.schema.NaturalStr('attempts'),

    # timeout: (scamper): positive integer seconds
    Optional('timeout', default='5'): task.schema.PositiveIntStr('timeout', 'seconds'),

    # include: mapping
    Optional('include',
             default={'last_mile_ip': False,
                      'source_ip': False}): {
        # last_mile_ip: include detected IP address of last mile host in results
        Optional('last_mile_ip', default=False): bool,

        # source_ip: include device LAN IP address in results
        Optional('source_ip', default=False): bool,
    },
})


@task.param.require(PARAMS)
@require_net
def main(params):
    """Measure latency to the "last mile" host via scamper.

    The local network, and then internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    A scamper trace is then executed against a configured internet host.
    (A domain name *may* be configured in lieu of an IP address; the
    name will first be resolved to its IP.)

    Multiple host targets *may* be specified, in which case the target
    to trace is randomly selected; and, in the case of failure,
    additional targets will be selected, sequentially.

    The "last mile" host -- *i.e.* the first "hop" outside of the
    client's private network -- is identified from scamper trace
    results, and this host's "round-trip time" (RTT) to respond is
    parsed and written out according to configuration.

    """
    # ensure scamper on PATH
    scamper_path = shutil.which('scamper')
    if scamper_path is None:
        task.log.critical("scamper executable not found")
        return task.status.file_missing

    # resolve destination(s) given by domain to IP
    address_lookups = AddressLookups(params.destinations)

    for hostname in address_lookups.unresolved:
        task.log.error(host=hostname,
                       status=address_lookups.queries[hostname].returncode,
                       msg='domain look-up failure')

    if not address_lookups.resolved:
        task.log.critical(errors=len(address_lookups.unresolved),
                          msg='no addresses to query')
        return task.status.no_host

    # randomize target from resolved destination(s)
    target_ips = list(address_lookups.resolved)
    random.shuffle(target_ips)

    # try target(s) falling back sequentially
    trace_cmd = f'trace -Q -P icmp-paris -q {params.attempts} -w {params.timeout}'

    for target_ip in target_ips:
        try:
            process = subprocess.run(
                (
                    scamper_path,
                    '-O', 'json',
                    '-c', trace_cmd,
                    '-i', target_ip,
                ),
                capture_output=True,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            # scamper shouldn't really error this way: this is serious
            task.log.critical(
                dest=target_ip,
                status=f'Error ({exc.returncode})',
                args=exc.cmd,
                stdout=exc.stdout,
                stderr=exc.stderr,
            )
            return task.status.software_error

        #
        # retrieve any returned results
        #
        # scamper returns results for each target given; we've given
        # one target and expect to receive one results set.
        #
        # however, scamper *could* fail to return proper and/or desired
        # results: here, evaluating either to *no* results set (length
        # zero) OR to a results set equal to None. we'll treat either
        # case the same.
        #
        try:
            (results,) = parse_output(process.stdout)
        except ValueError:
            results = None

        if results is not None:
            # we got what we wanted! we're done.
            break

        #
        # query against this target failed...
        #
        # log and continue to next target (if any)
        #
        task.log.error(
            dest=target_ip,
            stdout=process.stdout,
            stderr=process.stderr,
            msg='no result identified',
        )
    else:
        # no queries succeeded!
        task.log.critical(
            dests=target_ips,
            status='Error',
            msg='all queries failed',
        )
        return task.status.no_host

    # write results
    if not params.include.last_mile_ip:
        del results['last_mile_tr_addr']

    if not params.include.source_ip:
        del results['last_mile_tr_src']

    target_ip = results.pop('last_mile_tr_dst')  # preserved from loop but for clarity

    (target_host, *extra_names) = address_lookups.getkeys(target_ip)

    if extra_names:
        task.log.warning(dest=target_ip,
                         msg='destination given by multiple hostnames')

    if isinstance(params.destinations, dict):
        target_label = params.destinations[target_host]
    else:
        target_label = target_host

    if params.result.flat:
        del results['last_mile_tr_rtt_ms']

        results = {f'{target_label}_{key}': value
                   for (key, value) in results.items()}
    else:
        results = {target_label: results}

    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)

    return task.status.success


def parse_output(output):
    """Parse scamper output to return last mile info."""
    records = (json.loads(line) for line in output.splitlines())

    return [
        prepare_result(record)
        for record in records
        if record['type'] == 'trace'
    ]


def prepare_result(record):
    """Construct last mile result from scamper trace record."""
    if record['stop_reason'] != 'COMPLETED':
        task.log.warning(dest=record['dst'],
                         count=record['probe_count'],
                         stop_reason=record['stop_reason'])

    hop_groups = groupby(record['hops'], lambda hop: hop['addr'])

    for (addr, trials) in hop_groups:
        if not ip_address(addr).is_private:
            # the first non-private "hop" is the "last mile"
            rtts = [trial['rtt'] for trial in trials]

            return {
                'last_mile_tr_dst': record['dst'],
                'last_mile_tr_src': record['src'],
                'last_mile_tr_addr': addr,
                'last_mile_tr_rtt_ms': rtts,
                'last_mile_tr_rtt_max_ms': max(rtts),
                'last_mile_tr_rtt_min_ms': min(rtts),
                'last_mile_tr_rtt_median_ms': statistics.median(rtts),
                'last_mile_tr_rtt_mdev_ms': round(statistics.stdev(rtts), 3),
            }

    # no last-mile/WAN data found
    return None
