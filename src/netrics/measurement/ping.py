"""Measure ping latency to configured hosts."""
import subprocess
from collections import defaultdict

from schema import Optional

from netrics import task

from .common import default, output, require_lan


#
# ping exit codes
#
# if ping returns any code other than the below something is *very* wrong
#
# (the error code 2 is included -- unclear if ping *can* return anything higher than that.)
#
PING_CODES = {
    0,  # success
    1,  # no reply
    2,  # error (e.g. dns)
}


#
# params schema
#
# input -- a (deserialized) mapping -- is entirely optional.
#
# a dict, of the optional param keys, their defaults, and validations of
# their values, is given below, (extending the globally-supported input
# parameter schema given by `task.schema`).
#
PARAMS = task.schema.extend('ping_latency', {
    # destinations: (ping): list of hosts
    #                       OR mapping of hosts to their labels (for results)
    Optional('destinations',
             default=default.PING_DESTINATIONS): task.schema.DestinationCollection(),

    # count: (ping): natural number
    Optional('count', default='10'): task.schema.NaturalStr('count'),

    # interval: (ping): int/decimal seconds no less than 2ms
    Optional('interval',
             default='0.25'): task.schema.BoundedRealStr('interval',
                                                         'seconds may be no less than 0.002 (2ms)',
                                                         lambda interval: interval >= 0.002),

    # deadline: (ping): positive integer seconds
    Optional('deadline', default='5'): task.schema.PositiveIntStr('deadline', 'seconds'),
})


@task.param.require(PARAMS)
@require_lan
def main(params):
    """Measure ping latency to configured hosts.

    The local network is queried first to ensure operation.
    (See: `require_lan`.)

    Ping queries are then executed, in parallel, to each configured host
    (`destinations`) according to configured ping command arguments:
    `count`, `interval` and `deadline`.

    Ping outputs are parsed into structured results and written out
    according to configuration (`result`).

    """
    # parallelize pings
    processes = {
        destination: subprocess.Popen(
            (
                'ping',
                '-c', params.count,
                '-i', params.interval,
                '-w', params.deadline,
                destination,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) for destination in params.destinations
    }

    # wait and collect outputs
    outputs = {destination: process.communicate() for (destination, process) in processes.items()}

    # check for exceptions
    failures = [
        (destination, process, outputs[destination])
        for (destination, process) in processes.items()
        if process.returncode not in PING_CODES
    ]

    if failures:
        total_failures = len(failures)

        # directly log first 3 failures
        for (fail_count, (destination, process, (stdout, stderr))) in enumerate(failures[:3], 1):
            task.log.critical(
                dest=destination,
                status=f'Error ({process.returncode})',
                failure=f"({fail_count}/{total_failures})",
                args=process.args[:-1],
                stdout=stdout,
                stderr=stderr,
            )

        if fail_count < total_failures:
            task.log.critical(
                dest='...',
                status='Error (...)',
                failure=f"(.../{total_failures})",
                args='...',
                stdout='...',
                stderr='...',
            )

        return task.status.software_error

    # log summary/general results
    statuses = defaultdict(int)
    for process in processes.values():
        statuses[process.returncode] += 1

    task.log.info({'dest-status': statuses})

    # parse detailed results
    results = {
        destination: output.parse_ping(stdout)
        for (destination, (stdout, _stderr)) in outputs.items()
    }

    # label results
    if isinstance(params.destinations, dict):
        results = {
            params.destinations[destination]: result
            for (destination, result) in results.items()
        }

    # flatten results
    if params.result.flat:
        results = {f'{label}_{feature}': value
                   for (label, data) in results.items()
                   for (feature, value) in data.items()}

    # write results
    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)

    return task.status.success
