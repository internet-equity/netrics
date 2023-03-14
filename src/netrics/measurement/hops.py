"""Trace number of "hops" to target destination(s)"""
import json
import operator
import subprocess

from schema import Optional

from netrics import task
from netrics.util.iterutils import sequence

from .common import (
    AddressLookups,
    default,
    require_exec,
    require_net,
)


#
# params schema
#
PARAMS = task.schema.extend('hops_to_target', {
    # destinations: (scamper): list of hosts (IP address preferred!)
    #                          OR mapping of hosts to their labels (for results)
    Optional('destinations',
             default=default.DESTINATIONS): task.schema.DestinationCollection(),

    # attempts: (scamper): natural number
    Optional('attempts', default='1'): task.schema.NaturalStr('attempts'),

    # timeout: (scamper): positive integer seconds
    Optional('timeout', default='5'): task.schema.PositiveIntStr('timeout', 'seconds'),
})


@task.param.require(PARAMS)
@require_exec('scamper')
@require_net
def main(scamper, params):
    """Trace the number of "hops" -- *i.e.* intermediary hosts --
    between the client and target destination(s).

    The local network, and then internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    Scamper trace -- using the Paris implementation -- is then executed
    against *all* configured internet hosts (`destinations`), according
    to configured scamper command arguments: `attempts` and `timeout`.

    (Domain name `destinations` *may* be configured in lieu IP
    addresses; names will first be resolved to IPs.)

    The hop number of each destination is retrieved from scamper
    outputs, and written as structured results according to
    configuration (`result`).

    """
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

    # trace target(s)
    target_ips = address_lookups.resolved

    target_args = [arg for target in target_ips for arg in ('-i', target)]

    trace_cmd = f'trace -Q -P icmp-paris -q {params.attempts} -w {params.timeout}'

    try:
        process = subprocess.run(
            (
                scamper,
                '-O', 'json',
                '-c', trace_cmd,
                *target_args,
            ),
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # scamper shouldn't really error this way: this is serious
        task.log.critical(
            dests=target_ips,
            status=f'Error ({exc.returncode})',
            args=exc.cmd,
            stdout=exc.stdout,
            stderr=exc.stderr,
        )
        return task.status.software_error

    # parse results
    hop_results = parse_output(process.stdout)

    # check for exceptions
    unaccounted_ips = target_ips - {result['dst'] for result in hop_results}

    if unaccounted_ips:
        # we/scamper shouldn't error this way: this is serious
        task.log.critical(
            dests=unaccounted_ips,
            msg='could not account for destinations in results',
        )
        return task.status.software_error

    (successes, failures) = sequence(operator.itemgetter('completed'), hop_results)

    fail_total = len(failures)

    for (fail_count, failure) in enumerate(failures, 1):
        task.log.error(
            dest=failure['dst'],
            failure=f"({fail_count}/{fail_total})",
            hop_count=failure['hop_count'],
            stop_reason=failure['stop_reason'],
        )

    if not successes:
        task.log.critical("no destinations succeeded")
        return task.status.no_host

    # label results
    results = {result['dst']: result['hop_count'] for result in successes}

    for target_ip in tuple(results):
        (target_host, *extra_names) = address_lookups.getkeys(target_ip)

        if extra_names:
            task.log.warning(dest=target_ip,
                             msg='destination given by multiple hostnames')

        if target_ip != target_host:
            results[target_host] = results.pop(target_ip)

    if isinstance(params.destinations, dict):
        results = {
            params.destinations[destination]: result
            for (destination, result) in results.items()
        }

    # flatten results
    if params.result.flat:
        results = {
            f'hops_to_{destination}': result
            for (destination, result) in results.items()
        }
    else:
        results = {
            destination: {'hops': result}
            for (destination, result) in results.items()
        }

    # write results
    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)

    return task.status.success


def parse_output(output):
    """Parse scamper output to return hop info."""
    records = (json.loads(line) for line in output.splitlines())

    return [
        prepare_result(record)
        for record in records
        if record['type'] == 'trace'
    ]


def prepare_result(record):
    """Construct final hop result from scamper trace record."""
    try:
        last_hop = record['hops'][-1]
    except (KeyError, IndexError):
        # no data found
        pass
    else:
        if (
            record['stop_reason'] == 'COMPLETED' and
            last_hop['addr'] == record['dst'] and
            last_hop['probe_ttl'] == record['hop_count']
        ):
            return {
                'completed': True,
                'dst': record['dst'],
                'hop_count': record['hop_count'],
                'stop_reason': record['stop_reason'],
            }

    # data exceptional
    return {
        'completed': False,
        'dst': record.get('dst'),
        'hop_count': record.get('hop_count'),
        'stop_reason': record.get('stop_reason'),
    }
