"""Measure ping latency to configured hosts."""
import re
import subprocess
from collections import defaultdict
from numbers import Real

from schema import (
    And,
    Or,
    Optional,
    Use,
    SchemaError,
)

from netrics import task

from .common import require_lan


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
# params
#
# input -- a (deserialized) mapping -- is entirely optional.
#
# a dict, of the optional param keys, their defaults, and validations of
# their values, is given below.
#

Text = And(str, len)  # non-empty str

PARAM_SCHEMA = {
    # destinations: (ping): list of hosts
    #                       OR mapping of hosts to their labels (for results)
    Optional('destinations',
             default=('google.com',
                      'facebook.com',
                      'nytimes.com')): Or({Text: Text},
                                          And([Text],
                                              lambda dests: len(dests) == len(set(dests))),
                                          error="destinations: must be non-repeating list "
                                                "of network locators or mapping of these "
                                                "to their result labels"),

    # count: (ping): natural number
    Optional('count', default='10'): And(int,
                                         lambda count: count > 0,
                                         Use(str),
                                         error="count: int must be greater than 0"),

    # interval: (ping): int/decimal seconds no less than 2ms
    Optional('interval', default='0.25'): And(Real,
                                              lambda interval: interval >= 0.002,
                                              Use(str),
                                              error="interval: seconds must not be less than 2ms"),

    # deadline: (ping): positive integer seconds
    Optional('deadline', default='5'): And(int,
                                           lambda deadline: deadline >= 0,
                                           Use(str),
                                           error="deadline: int seconds must not be less than 0"),

    # result: mappping
    Optional('result', default={'flat': True,
                                'label': 'ping_latency',
                                'meta': True}): {
        # flat: flatten ping destination results dict to one level
        Optional('flat', default=True): bool,

        # wrap: wrap the above (whether flat or not) in a measurement label
        Optional('label', default='ping_latency'): Or(False, None, Text),

        # meta: wrap all of the above (whatever it is) with metadata (time, etc.)
        Optional('meta', default=True): bool,
    },
}


@require_lan
def main():
    """Measure ping latency to configured hosts.

    The local network is queried first to ensure operation.
    (See: `require_lan`.)

    Ping queries are then executed, in parallel, to each configured host
    (`destinations`) according to configured ping command arguments:
    `count`, `interval` and `deadline`.

    Ping outputs are parsed into structured results and written out
    according to configuration (`result`).

    """
    # read input params
    try:
        params = task.param.read(schema=PARAM_SCHEMA)
    except SchemaError as exc:
        task.log.critical(error=str(exc), msg="input error")
        return task.status.conf_error

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
        destination: parse_output(stdout)
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
                      meta=params.result.meta)

    return task.status.success


def parse_output(output):
    """Parse ping output and return dict of results."""

    # Extract RTT stats
    rtt_match = re.search(
        r'rtt [a-z/]* = ([0-9.]*)/([0-9.]*)/([0-9.]*)/([0-9.]*) ms',
        output
    )

    rtt_values = [float(value) for value in rtt_match.groups()] if rtt_match else [-1.0] * 4

    rtt_keys = ('rtt_min_ms', 'rtt_avg_ms', 'rtt_max_ms', 'rtt_mdev_ms')

    rtt_stats = zip(rtt_keys, rtt_values)

    # Extract packet loss stats
    pkt_loss_match = re.search(r', ([0-9.]*)% packet loss', output, re.MULTILINE)

    pkt_loss = float(pkt_loss_match.group(1)) if pkt_loss_match else -1.0

    # Return combined dict
    return dict(rtt_stats, packet_loss_pct=pkt_loss)
