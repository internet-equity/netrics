"""Retrieve public IP address from configured service."""
import ipaddress
import urllib

from schema import Optional

from netrics import task

from .common import require_lan


PARAMS = task.schema.extend('ipquery', {
    Optional('service', default='https://api.ipify.org/'): task.schema.Text,
})


@task.param.require(PARAMS)
@require_lan
def main(params):
    """Retrieve public IP address from configured service.

    The local network is queried first to ensure operation.
    (See: `require_lan`.)

    An HTTP request is then made of the configured IP address service
    (`service`).

    This configured service is expected to return a response with status
    `200` and body of the IP address (without additional content).

    The IP address is written out as a structured result according to
    configuration (`result`).

    """
    # initiate HTTP request
    try:
        response = urllib.request.urlopen(params.service)
    except OSError as exc:
        task.log.critical(
            url=params.service,
            error=str(exc),
            msg='urlopen error',
        )
        return task.status.no_host

    # check OK
    if response.status != 200:
        content = response.read()

        if len(content) > 75:
            content = content[:72] + '...'

        task.log.critical(
            url=params.service,
            status=f'Error ({response.status})',
            msg=content,
        )

        return task.status.no_host

    # retrieve response
    ip_addr = response.read().decode()

    # validate response
    try:
        ipaddress.ip_address(ip_addr)
    except ValueError as exc:
        task.log.critical(
            url=params.service,
            response=ip_addr,
            error=str(exc),
            msg='service response error',
        )
        return task.status.software_error

    # write result
    task.result.write({'ipv4': ip_addr},
                      label=params.result.label,
                      annotate=params.result.annotate)
