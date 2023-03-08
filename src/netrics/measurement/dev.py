"""Count devices connected to the local network."""
import ipaddress
import subprocess
import time
import typing
from datetime import datetime, timedelta

import netifaces
from descriptors import classonlymethod
from schema import Optional

from netrics import task

from .common import require_exec, require_lan


PARAMS = task.schema.extend('connected_devices_arp', {
    Optional('iface', default='eth0'): task.schema.Text,
})


@task.param.require(PARAMS)
@require_exec('nmap', 'arp')
@require_lan
def main(nmap, arp, params):
    """Count devices connected to the local network.

    The local network is queried first to ensure operation.
    (See: `require_lan`.)

    nmap and arp are then executed to detect devices connected to the
    local network. The network interface to query may be configured
    (`iface`).

    Devices are recorded by MAC address, their most recent timestamp of
    detection persisted to task state.

    Written results consist of the aggregate count of connected devices:

    * currently
    * for all time
    * over 24 hours
    * over 7 days

    The structure of written results is configurable (`result`).

    """
    # determine device subnet
    try:
        iface_addrs = netifaces.ifaddresses(params.iface)
    except ValueError as exc:
        # invalid interface name
        task.log.critical(iface=params.iface,
                          error=str(exc))
        return task.status.os_error

    try:
        ip_info = iface_addrs[netifaces.AF_INET][0]
    except (KeyError, IndexError):
        # bizarre interface
        task.log.critical(iface=params.iface,
                          msg='could not locate internet address set')
        return task.status.os_error

    ip_iface = ipaddress.ip_interface('{addr}/{netmask}'.format_map(ip_info))

    subnet = str(ip_iface.network)

    try:
        subprocess.run(
            (
                nmap,
                '-sn',  # no port scan
                subnet,
            ),
            # note: we don't actually want output -- unless there's an error
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # nmap shouldn't really error this way: this is serious
        task.log.critical(
            dest=subnet,
            status=f'Error ({exc.returncode})',
            args=exc.cmd,
            stdout=exc.stdout,
            stderr=exc.stderr,
        )
        return task.status.software_error

    try:
        process = subprocess.run(
            (
                arp,
                '-e',  # attempt to ensure Linux format
                '--numeric',
                '--device', params.iface,
            ),
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # arp shouldn't really error this way: this is serious
        task.log.critical(
            iface=params.iface,
            status=f'Error ({exc.returncode})',
            args=exc.cmd,
            stdout=exc.stdout,
            stderr=exc.stderr,
        )
        return task.status.software_error

    arp_results = ArpResult.parse(process.stdout)

    devices = {arp_result.hwaddress for arp_result in arp_results
               if arp_result.address != '_gateway' and arp_result.hwaddress != params.iface}

    task.log.info(count=len(devices))

    # persist state
    store = DeviceStore.read()

    task.log.debug(state0=store)

    store.record(*devices)

    task.log.debug(state1=store)

    store.write()

    # write results
    results = {
        'active': len(devices),
        'total': len(store),
        '1day': store.count(timedelta(days=1)),
        '1week': store.count(timedelta(days=7)),
    }

    if params.result.flat:
        results = {f'devices_{feature}': value for (feature, value) in results.items()}
    else:
        results = {'devices': results}

    task.result.write(results,
                      label=params.result.label,
                      annotate=params.result.annotate)

    return task.status.success


class ArpResult(typing.NamedTuple):
    """Connect device record retrieved from ARP results."""

    address: str
    hwtype: str
    hwaddress: str

    @classonlymethod
    def parse(cls, output):
        """Construct instances of ArpResult from ARP results text."""
        lines = output.splitlines()

        if lines[0].lower().startswith('address'):
            del lines[0]

        return [cls.extract(line) for line in lines]

    @classonlymethod
    def extract(cls, line):
        """Construct an instance of ArpResult from a single line of
        ARP results text.

        """
        items = line.split()
        return cls._make(items[:3])


class DeviceStore(dict):
    """Mapping of device MAC addresses to the timestamps of their most
    recent detection.

    Historical data are read from, updated and written to the task
    framework's state record.

    """
    @classonlymethod
    def read(cls):
        return cls(task.state.read() or {})

    def write(self):
        task.state.write(self)

    def record(self, *devices, ts=None):
        if ts is None:
            ts = time.time()
        elif isinstance(ts, datetime):
            ts = ts.timestamp()

        if isinstance(ts, float):
            ts = int(ts)

        if not isinstance(ts, int):
            raise TypeError(f"timestamp argument 'ts' must be datetime or numeric, not "
                            f"'{ts.__class__.__name__}'")

        for device in devices:
            self[device] = ts

    def query(self, span, before=None):
        if isinstance(span, timedelta):
            span = span.total_seconds()

        if not isinstance(span, (int, float)):
            raise TypeError(f"time span argument 'span' must be timedelta or numeric, "
                            f"not '{span.__class__.__name__}'")

        if before is None:
            before = time.time()
        elif isinstance(before, datetime):
            before = before.timestamp()

        if not isinstance(before, (int, float)):
            raise TypeError(f"timestamp argument 'before' must be datetime or numeric, "
                            f"not '{before.__class__.__name__}'")

        since = before - span

        for (device, last_seen) in self.items():
            if before >= last_seen > since:
                yield device

    def count(self, span, before=None):
        return sum(1 for _device in self.query(span, before))
