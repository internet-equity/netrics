"""Trace number of "hops" to target destination(s)"""
import operator
import subprocess
import typing

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
# params schema
#
PARAMS = task.schema.extend('hops_to_target', {
    # destinations: (traceroute): list of hosts
    #                             OR mapping of hosts to their labels (for results)
    Optional('destinations',
             default=default.DESTINATIONS): task.schema.DestinationCollection(),

    # max_hop: (traceroute): natural number
    Optional('max_hop', default='64'): task.schema.NaturalStr('max_hop'),

    # tries: (traceroute): natural number
    Optional('tries', default='5'): task.schema.NaturalStr('tries'),

    # wait: (traceroute): natural number
    Optional('wait', default='2'): task.schema.NaturalStr('wait'),
})


@task.param.require(PARAMS)
@require_exec('traceroute')
@require_net
def main(traceroute, params):
    """Trace the number of "hops" -- *i.e.* intermediary hosts --
    between the client and target destination(s).

    The local network, and then internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    Traceroute is then executed against all configured internet hosts
    (`destinations`) in parallel, according to configured traceroute
    command arguments: `max_hop`, `tries` and `wait`.

    Traceroute outputs are parsed to retrieve the hop number of each
    destination, and structured results are written out according to
    configuration (`result`).

    """
    # parallelize traceroutes
    pool = [
        subprocess.Popen(
            (
                #
                # versions of traceroute differ on their long options and how
                # they like them to be specified.
                #
                # we'll stick to short options which are consistent across
                # versions and which may be specified as below.
                #
                traceroute,
                '-m', params.max_hop,
                '-q', params.tries,
                '-w', params.wait,
                destination,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) for destination in params.destinations
    ]

    # wait and map to completed processes
    processes = {
        destination: procutils.complete(process)
        for (destination, process) in zip(params.destinations, pool)
    }

    # parse results
    hop_results = [
        HopResult.extract(
            destination,
            process,
        )
        for (destination, process) in processes.items()
    ]

    # check for exceptions
    (successes, failures) = iterutils.sequence(operator.attrgetter('hops'), hop_results)

    fail_total = len(failures)

    for (fail_count, hop_result) in enumerate(failures, 1):
        process = processes[hop_result.dest]

        task.log.error(
            dest=hop_result.dest,
            status=f'Error ({process.returncode})',
            failure=f"({fail_count}/{fail_total})",
            stdout=process.stdout,
            stderr=process.stderr,
        )

    if not successes:
        task.log.critical("no destinations succeeded")
        return task.status.no_host

    # prepare results
    results = {hop_result.dest: hop_result.hops for hop_result in hop_results}

    # label results
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


class HopResult(typing.NamedTuple):
    """Hop number parsed from traceroute outputs for a destination host.

    """
    dest: str
    hops: typing.Optional[int]

    @classmethod
    def extract(cls, destination, process):
        """Construct object from traceroute result."""
        if process.returncode == 0:
            try:
                (*_earlier_lines, last_line) = process.stdout.splitlines()

                (hop_count, _line_remainder) = last_line.strip().split(' ', 1)

                hop_int = int(hop_count)
            except ValueError:
                #
                # we have a problem!
                #
                # e.g.:
                #
                # *) stdout was empty
                # *) last line did not contain spaces to split
                # *) the first column value was non-numeric
                #
                pass
            else:
                return cls(destination, hop_int)

        return cls(destination, None)
