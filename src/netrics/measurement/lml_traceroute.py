"""Measure latency to the "last mile" host via traceroute & ping."""
import random
import re
import shutil
import subprocess
import typing
from ipaddress import ip_address

from schema import Optional

from netrics import task

from .common import output, require_net


#
# params schema
#
PARAMS = task.schema.extend('last_mile_rtt', {
    # destinations: (traceroute): list of hosts
    #                             OR mapping of hosts to their labels (for results)
    #                             (Note: will select ONE)
    Optional('destinations',
             default={'8.8.8.8': 'Google_DNS',
                      '1.1.1.1': 'Cloudflare_DNS'}): task.schema.DestinationCollection(),

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
@require_net
def main(params):
    """Measure latency to the "last mile" host via traceroute and ping.

    The local network, and then internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    Traceroute is then executed against a configured internet host.

    Multiple host targets *may* be specified, in which case the target
    to trace is randomly selected; and, in the case of failure,
    additional targets will be selected, sequentially.

    The "last mile" host -- *i.e.* the first "hop" outside of the
    client's private network -- is identified from traceroute results,
    and this host's "round-trip time" (RTT) to respond is
    parsed and written out according to configuration.

    The last-mile host is also ping'd and these results are parsed and
    written as well.

    """
    # ensure traceroute on PATH
    # (ping is used by require_net)
    traceroute_path = shutil.which('traceroute')
    if traceroute_path is None:
        task.log.critical("traceroute executable not found")
        return task.status.file_missing

    # randomize target from configured destination(s)
    target_hosts = list(params.destinations)
    random.shuffle(target_hosts)

    # try target(s) falling back sequentially
    for target_host in target_hosts:
        # trace target
        try:
            traceroute = subprocess.run(
                (
                    traceroute_path,
                    target_host,
                ),
                capture_output=True,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            task.log.error(
                dest=target_host,
                status=f'Error ({exc.returncode})',
                stdout=exc.stdout,
                stderr=exc.stderr,
                msg='traceroute failed',
            )
            continue  # fall back to next (if any)

        # extract "last mile" host from trace
        try:
            last_mile = LastMileResult.extract(target_host,
                                               traceroute.stdout,
                                               traceroute.stderr)
        except TracerouteAddressError as exc:
            task.log.error(
                dest=target_host,
                stdout=traceroute.stdout,
                stderr=traceroute.stderr,
                line=exc.line,
                msg='failed to parse traceroute hop ip address from output line',
            )
            continue
        except TracerouteParseError as exc:
            task.log.error(
                dest=target_host,
                stdout=traceroute.stdout,
                stderr=traceroute.stderr,
                line=exc.line,
                msg='unexpected traceroute output line or parse failure',
            )
            continue
        except TracerouteOutputError:
            task.log.error(
                dest=target_host,
                stdout=traceroute.stdout,
                stderr=traceroute.stderr,
                msg='failed to extract last mile ip from traceroute output',
            )
            continue

        # ping last mile host
        ping = subprocess.run(
            (
                'ping',
                '-c', params.count,
                '-i', params.interval,
                '-w', params.deadline,
                last_mile.ip_address,
            ),
            capture_output=True,
            text=True,
        )

        if ping.returncode > 1:
            task.log.critical(
                dest=last_mile.ip_address,
                status=f'Error ({ping.returncode})',
                stdout=ping.stdout,
                stderr=ping.stderr,
                msg='last mile ping failure',
            )
            return task.status.no_host

        # parse ping results
        ping_stats = output.parse_ping(ping.stdout)

        break  # we're done!
    else:
        # no queries succeeded!
        task.log.critical(
            dests=target_hosts,
            status='Error',
            msg='all queries failed',
        )
        return task.status.no_host

    # write results
    traceroute_results = {
        f'last_mile_tr_{key}': value
        for (key, value) in last_mile.stats.items()
    }

    ping_results = {
        f'last_mile_ping_{key}': value
        for (key, value) in ping_stats.items()
    }

    results = {**ping_results, **traceroute_results}

    if isinstance(params.destinations, dict):
        target_label = params.destinations[last_mile.endpoint]
    else:
        target_label = last_mile.endpoint

    if params.result.flat:
        results = {
            f'{target_label}_{key}': value
            for (key, value) in results.items()
        }
    else:
        results = {target_label: results}

    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)

    return task.status.success


TRACEROUTE_HOP_PATTERN = re.compile(
    # arbitrary initial space
    r'\s*'
    # hop number
    r'(?P<hop_number>\d+)\s+'
    # first hostname (and conditionally-resolved ip address)
    r'(?P<addr0>\S+)\s+(\((?P<addr0_resolved>[.\d]+)\)\s+)?'
    # first rtt
    r'(?P<rtt0>[.\d]+)\s*ms\s+'
    # second hostname (conditional) (and conditionally-resolved ip address)
    r'((?P<addr1>\S+)\s+(\((?P<addr1_resolved>[.\d]+)\)\s+)?)?'
    # second rtt
    r'(?P<rtt1>[.\d]+)\s*ms\s+'
    # third hostname (conditional) (and conditionally-resolved ip address)
    r'((?P<addr2>\S+)\s+(\((?P<addr2_resolved>[.\d]+)\)\s+)?)?'
    # third rtt (with arbitrary ending space)
    r'(?P<rtt2>[.\d]+)\s*ms\s*'
)

TRACEROUTE_OTHER_PATTERN = re.compile(
    # title line
    r'(traceroute to .+)'
    # ...OR non-response asterisks
    r'|(\s*\d+\s+\*\s+\*\s+\*\s*)'
)


def parse_traceroute(output):
    return [(line, TRACEROUTE_HOP_PATTERN.fullmatch(line))
            for line in output.splitlines()]


def match_traceroute_other(line):
    return TRACEROUTE_OTHER_PATTERN.fullmatch(line)


class TracerouteOutputError(ValueError):
    pass


class TracerouteParseError(TracerouteOutputError):

    def __init__(self, line, *args):
        super().__init__(line, *args)

    @property
    def line(self):
        return self.args[0]


class TracerouteAddressError(TracerouteParseError):

    def __init__(self, line, hop_ip, *args):
        super().__init__(line, hop_ip, *args)

    @property
    def hop_ip(self):
        return self.args[1]


class RttStats(typing.NamedTuple):
    """Round-Trip Time statistics typical of traceroute results."""

    rtt_min_ms: float
    rtt_median_ms: float
    rtt_max_ms: float

    def _aszip(self):
        return zip(self._fields, self)

    items = _aszip


class LastMileResult(typing.NamedTuple):
    """Traceroute results for the "hop" corresponding to the "last mile"
    host.

    """
    endpoint: str
    ip_address: str
    stats: RttStats

    @classmethod
    def extract(cls, endpoint, stdout, stderr):
        """Construct results from traceroute outputs.

        The "last mile" IP address and response statistics are
        determined from the first "hop" presenting a public IP address.

        """
        for (line, hop) in parse_traceroute(stdout):
            if hop:
                hop_ip = hop['addr0_resolved'] or hop['addr0']

                try:
                    hop_ip_address = ip_address(hop_ip)
                except ValueError:
                    raise TracerouteAddressError(line, hop_ip)

                if not hop_ip_address.is_private:
                    # the first non-private "hop" is the "last mile"
                    hop_values = (hop['rtt0'], hop['rtt1'], hop['rtt2'])

                    try:
                        hop_stats = sorted(float(hop_value) for hop_value in hop_values)
                    except ValueError:
                        raise TracerouteParseError(line)

                    return cls(endpoint, hop_ip, RttStats._make(hop_stats))

            elif not match_traceroute_other(line):
                # in consideration of match limits...
                task.log.warning(
                    dest=endpoint,
                    stdout=stdout,
                    stderr=stderr,
                    line=line,
                    msg='unexpected traceroute output line',
                )

        raise TracerouteOutputError(endpoint, stdout, stderr)
