"""Common DNS helpers."""
import collections.abc
import ipaddress
import shutil
import subprocess


class AddressLookups(collections.abc.Mapping):
    """Mapping enabling parallelized domain name resolution."""

    _dig_path_ = shutil.which('dig')

    def __init__(self, destinations):
        self._results_ = dict.fromkeys(destinations)

        self.queries = {}

        self._resolve_()

        self.resolved = frozenset(address for address in self._results_.values()
                                  if address is not None)

        self.unresolved = tuple(host for (host, address) in self._results_.items()
                                if address is None)

    def _resolve_(self):
        for host in self._results_:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                if self._dig_path_ is None:
                    raise FileNotFoundError("dig executable not found")

                self.queries[host] = subprocess.Popen(
                    (self._dig_path_, '+short', host),
                    stdout=subprocess.PIPE,
                    text=True,
                )
            else:
                self._results_[host] = host

        for (host, process) in self.queries.items():
            (stdout, _stderr) = process.communicate()

            if process.returncode == 0:
                try:
                    self._results_[host] = stdout.splitlines()[0]
                except IndexError:
                    pass

    def __getitem__(self, item):
        return self._results_[item]

    def __len__(self):
        return len(self._results_)

    def __iter__(self):
        yield from self._results_

    def __repr__(self):
        map_ = ', '.join(f'{key} => {value}'
                         for (key, value) in self._results_.items())

        return f'<{self.__class__.__name__}: [{map_}]>'

    def getkeys(self, value):
        return {host for (host, address) in self._results_.items() if address == value}
