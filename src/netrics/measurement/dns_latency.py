"""Measure query latency statistics to resolve a set of domain names."""
import operator
import statistics
import subprocess
from types import SimpleNamespace as ns

import yaml
from schema import Optional

from netrics import task
from netrics.util import (
    iterutils,
    procutils,
)

from .common import (
    default,
    require_exec,
    require_net,
)


#
# dig exit codes
#
DIG_CODES = {
    0: "success",
    1: "usage error",
    8: "couldn't open batch file",
    9: "no reply from server",
    10: "internal error",
}


#
# params schema
#
PARAMS = task.schema.extend('dns_latency', {
    # destinations: (dig): list of domain names
    Optional('destinations',
             default=default.DESTINATIONS): task.schema.HostnameList(),

    # server: (dig): DNS server to query
    Optional('server', default='8.8.8.8'): task.schema.IPAddress('server'),
})


@task.param.require(PARAMS)
@require_exec('dig')
@require_net
def main(dig, params):
    """Measure query latency statistics to resolve a set of domain names.

    The local network, and then internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    The `dig` command is then executed, concurrently, for each
    configured domain name (`destinations`), against the configured DNS
    server (`server`).

    The mean and maximum values of the query time, reported by `dig`,
    over these invocations, is written out according to configuration
    (`result`).

    """
    # parallelize look-ups
    pool = [
        subprocess.Popen(
            (
                dig,
                f'@{params.server}',
                destination,
                '+yaml',
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for destination in params.destinations
    ]

    # wait and map to completed processes
    processes = [procutils.complete(process) for process in pool]

    # wrap completed processes with annotative encapsulation
    trials = [
        ns(
            dest=destination,
            proc=process,
        )
        for (destination, process) in zip(params.destinations, processes)
    ]

    # check for exceptions
    (failures, successes) = iterutils.sequence(operator.attrgetter('proc.returncode'), trials)

    fail_total = len(failures)

    for (fail_count, failure) in enumerate(failures, 1):
        task.log.error(
            dest=failure.dest,
            status=f'Error ({failure.proc.returncode})',
            error=DIG_CODES.get(failure.proc.returncode, "<unidentified>"),
            failure=f"({fail_count}/{fail_total})",
            stdout=failure.proc.stdout,
            stderr=failure.proc.stderr,
        )

    if not successes:
        task.log.critical("no destinations succeeded")
        return task.status.no_host

    # prepare results
    try:
        times_label = {success.dest: extract_time_ms(success.proc.stdout) for success in successes}
    except ExtractionError as exc:
        task.log.critical(
            error=exc.msg,
            stdout=exc.stdout,
            msg='latency extraction error',
        )
        return task.status.software_error

    times = times_label.values()

    results = {'avg_ms': statistics.mean(times),
               'max_ms': max(times)}

    # add'l detail
    times_sort = sorted(times_label.items(), key=operator.itemgetter(1))

    task.log.info(
        min_label=dict(times_sort[:1]),
        mean=round(statistics.mean(times), 1),
        stdev=round(statistics.stdev(times), 1),
        max_label=dict(times_sort[-1:]),
    )

    # flatten results
    if params.result.flat:
        results = {f'dns_query_{feature}': value for (feature, value) in results.items()}
    else:
        results = {'dns_query': results}

    # write results
    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)

    return task.status.success


class ExtractionError(ValueError):
    """Unexpected dig output"""

    def __init__(self, msg, stdout):
        super().__init__(msg, stdout)

    def __str__(self):
        return self.msg

    @property
    def msg(self):
        return self.args[0]

    @property
    def stdout(self):
        return self.args[1]


def extract_time_ms(stdout_yaml):
    """Extract query latency in miliseconds from dig's YAML output."""
    try:
        (data,) = yaml.safe_load(stdout_yaml)
    except ValueError:
        raise ExtractionError('unexpected output', stdout_yaml)

    try:
        message = data['message']
        delta = message['response_time'] - message['query_time']
    except (KeyError, TypeError):
        raise ExtractionError('unexpected structure', stdout_yaml)

    seconds = delta.total_seconds()

    return seconds * 1e3
