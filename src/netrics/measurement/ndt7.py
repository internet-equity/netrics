"""Measure Internet bandwidth, *etc*., via Measurement Lab's NDT7 client."""
import json
import subprocess

from schema import Optional, Or

from netrics import task

from .common import require_net


PARAMS = task.schema.extend('ndt7', {
    # exec: ndt7-client executable name or path
    Optional('exec', default='ndt7-client'): task.schema.Command(
        error='exec: must be an executable on PATH or file system absolute path to executable'
    ),

    # timeout: seconds after which test is canceled
    # (0, None, False, etc. to disable timeout)
    Optional('timeout', default=45): Or(task.schema.GTZero(),
                                        task.schema.falsey,
                                        error='timeout: seconds greater than zero or '
                                              'falsey to disable'),
})


@task.param.require(PARAMS)
@require_net
def main(params):
    """Measure Internet bandwidth, *etc*., via M-Lab's NDT7 client.

    The local network, and then Internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    The ndt7-client binary is then executed.

    This binary is presumed to be accessible via PATH at `ndt7-client`.
    This PATH look-up name is configurable, and may be replaced with the
    absolute file system path, instead (`exec`).

    Should the speedtest not return within `timeout` seconds, an error
    is returned. (This may be disabled by setting a "falsey" timeout
    value.)

    In addition to NDT metrics such as download bandwidth
    (`download`) and upload bandwidth (`upload`), measurement results
    are written to include the key `test_bytes_consumed`. This item is
    *not* included under the test's `label`, (regardless of `result`
    configuration).

    """
    try:
        proc = subprocess.run(
            (
                params.exec,
                '-format', 'json',
            ),
            timeout=(params.timeout or None),
            capture_output=True,
            text=True
        )
    except subprocess.TimeoutExpired as exc:
        task.log.critical(
            cmd=exc.cmd,
            elapsed=exc.timeout,
            stdout=exc.stdout,
            stderr=exc.stderr,
            status='timeout',
        )
        return task.status.timeout

    parsed = parse_output(proc.stdout)

    if not parsed:
        task.log.critical(
            status=f'Error ({proc.returncode})',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg="no results",
        )
        return task.status.no_host

    if proc.stderr:
        task.log.error(
            status=f'Error ({proc.returncode})',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg="results despite errors",
        )

    task.log.info(
        download=parsed['download'],
        upload=parsed['upload'],
        bytes_consumed=parsed['meta']['total_bytes_consumed'],
        uuid_download=parsed['meta']['downloaduuid'],
    )

    # flatten results
    data = {key: value for (key, value) in parsed.items() if key != 'meta'}

    if params.result.flat:
        results = {f'speedtest_ndt7_{feature}': value
                   for (feature, value) in data.items()}

    else:
        results = {'speedtest_ndt7': data}

    # extend results with non-measurement data
    if parsed['meta']['total_bytes_consumed']:
        extended = {'test_bytes_consumed': parsed['meta']['total_bytes_consumed']}
    else:
        extended = None

    # write results
    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate,
                      extend=extended)

    return task.status.success


def parse_output(output):
    """Parse output from M-Lab NDT7 client.

    Note: Should output not conform to expectations, `None` may be
    returned.

    """
    try:
        #
        # output consists of one or more lines of JSON objects
        #
        # this should entail arbitrary status lines (without -quiet flag)
        # followed by a single summary line
        #
        (*statuses, summary) = (json.loads(line) for line in output.splitlines())

        #
        # bytes consumed by the tests may only be retrieved from the status
        # lines under the measurement key
        #
        # we may retrieve the total bytes consumed by each test via the
        # *last* status line
        #
        (bytes_dl, bytes_ul) = (
            #
            # retrieve the *last* matching element by iterating statuses in *reverse*
            #
            # (if no matching element evaluate 0)
            #
            next(
                (
                    status['Value']['AppInfo']['NumBytes']
                    for status in reversed(statuses)
                    if (
                        status['Key'] == 'measurement' and
                        status['Value']['Origin'] == 'client' and
                        status['Value']['Test'] == test_name
                    )
                ),
                0,
            )
            for test_name in ('download', 'upload')
        )

        #
        # all other results are presented by the summary
        #
        return {
            'download': summary['Download']['Throughput']['Value'],
            'upload': summary['Upload']['Throughput']['Value'],

            'downloadretrans': summary['Download']['Retransmission']['Value'],
            'downloadlatency': summary['Download']['Latency']['Value'],

            'server': summary['ServerFQDN'],
            'server_ip': summary['ServerIP'],

            'meta': {
                'downloaduuid': summary['Download']['UUID'],
                'total_bytes_consumed': bytes_dl + bytes_ul,
            }
        }
    except (KeyError, TypeError, ValueError) as exc:
        task.log.error(
            error=str(exc),
            msg="output parsing error",
        )
        return None
