"""Measure Internet bandwidth, *etc*., via the Ookla speedtest CLI."""
import json
import os
import re
import subprocess
import tempfile

from schema import Optional, Or, Schema

from netrics import task

from .common import require_net


PARAMS = task.schema.extend('ookla', {
    # exec: speedtest executable name or path
    Optional('exec', default='speedtest'): task.schema.Command(
        error='exec: must be an executable on PATH or file system absolute path to executable'
    ),

    # timeout: seconds after which test is canceled
    # (0, None, False, etc. to disable timeout)
    Optional('timeout', default=45): Or(task.schema.GTZero(),
                                        task.schema.falsey,
                                        error='timeout: seconds greater than zero or '
                                              'falsey to disable'),

    # accept_license: (ookla): True (required)
    'accept_license': Schema(True, error="accept_license: Ookla CLI license must be "
                                         "explicitly accepted by specifying the value True"),
})


LICENSE_PATTERN = re.compile(
    r'=+\n+You may only use this Speedtest software.+'
    r'\n+License acceptance recorded.\s+Continuing.\s*',
    re.DOTALL | re.I
)


@task.param.require(PARAMS)
@require_net
def main(params):
    """Measure Internet bandwidth, *etc*., via the Ookla speedtest CLI.

    The local network, and then Internet hosts (as configured in global
    defaults), are queried first, to ensure network operation and
    internet accessibility. (See: `require_net`.)

    The Ookla speedtest binary is then executed.

    This binary is presumed to be accessible via PATH at `speedtest`.
    This PATH look-up name is configurable, and may be replaced with the
    absolute file system path, instead (`exec`).

    Should the speedtest not return within `timeout` seconds, an error
    is returned. (This may be disabled by setting a "falsey" timeout
    value.)

    Note: the configuration parameter `accept_license` **must** be
    specified with the value of `True`. This indicates that the terms of
    the Ookla speedtest CLI license has been reviewed and accepted.

    In addition to Ookla speedtest metrics such as download bandwidth
    (`download`), upload bandwidth (`upload`) and ping jitter
    (`jitter`), measurement results are written to include the key
    `test_bytes_consumed`. This item is *not* included under the test's
    `label`, (regardless of `result` configuration).

    """
    with tempfile.TemporaryDirectory() as tmphome:
        try:
            proc = subprocess.run(
                (
                    params.exec,
                    '--accept-license',
                    '--format', 'json',
                    '--progress', 'no',
                ),
                timeout=(params.timeout or None),
                capture_output=True,
                text=True,
                #
                # Ookla speedtest fails if HOME variable completely
                # unset -- as it _may_ be, _e.g._ under Systemd
                # (see #48).
                #
                # All it wants to do is record license-acceptance. This
                # is inconsequential; however, it cannot be disabled.
                #
                # As we can't (or don't want to) ensure a real HOME, and
                # don't need this record, we'll allow it to fall back to
                # a temporary directory.
                #
                env={'HOME': tmphome, **os.environ},
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

    if proc.stderr and not LICENSE_PATTERN.fullmatch(proc.stderr):
        task.log.error(
            status=f'Error ({proc.returncode})',
            stdout=proc.stdout,
            stderr=proc.stderr,
            msg="results despite errors",
        )

    task.log.info(
        download=parsed['download'],
        upload=parsed['upload'],
        bytes_consumed=parsed['meta'].get('total_bytes_consumed'),
        url=parsed['meta']['url'],
    )

    # flatten results
    data = {key: value for (key, value) in parsed.items() if key != 'meta'}

    if params.result.flat:
        results = {f'speedtest_ookla_{feature}': value
                   for (feature, value) in data.items()}

    else:
        results = {'speedtest_ookla': data}

    # extend results with non-measurement data
    if 'total_bytes_consumed' in parsed['meta']:
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
    """Parse output from the Ookla `speedtest` command.

    Returns a `dict` of the following form:

        {
            'download': float,
            'upload': float,
            'jitter': float,
            'latency': float,
            ...
            'meta': {
                'total_bytes_consumed': float,
                'url': str,
            },
        }

    Note: Should output not conform to expectations, `None` may be
    returned.

    """
    if not output:
        return None

    try:
        response = json.loads(output)

        result = {
            'download': response['download']['bandwidth'] * 8 / 1e6,
            'upload': response['upload']['bandwidth'] * 8 / 1e6,
            'jitter': response['ping']['jitter'],
            'latency': response['ping']['latency'],
            'server_host': response['server']['host'],
            'server_name': response['server']['name'],
            'server_id': response['server']['id'],
            'meta': {
                'total_bytes_consumed': (response['upload']['bytes'] +
                                         response['download']['bytes']),
                'url': response['result']['url'],
            },
        }

        if 'packetLoss' in response:
            result['pktloss2'] = response['packetLoss']
    except (KeyError, ValueError, TypeError) as exc:
        task.log.error(
            error=str(exc),
            msg="output parsing error",
        )
        return None
    else:
        return result
