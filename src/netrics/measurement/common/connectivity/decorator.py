"""Measurement decorators to ensure network connectivity."""
import functools
import shutil
import subprocess

import netifaces

from netrics import task

from . import command


class RequirementError(Exception):

    def __init__(self, returncode):
        super().__init__(returncode)
        self.returncode = returncode


class require_lan:
    """Decorator to extend a network measurement function with
    preliminary network checks.

    `require_lan` wraps the decorated function such that it will first
    ping the host (`localhost`), and then the default gateway, prior to
    proceeding with its own functionality. For example:

        @require_lan
        def main():
            # Now we know at least that the LAN is operational.
            #
            # For example, let's now attempt to access the Google DNS servers:
            #
            result = subprocess.run(
                ['ping', '-c', '1', '8.8.8.8'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode

    """
    RequirementError = RequirementError

    def __init__(self, func):
        # assign func's __module__, __name__, etc.
        # (but DON'T update __dict__)
        #
        # (also assigns __wrapped__)
        functools.update_wrapper(self, func, updated=())

    def __call__(self, *args, **kwargs):
        try:
            self.check_requirements()
        except self.RequirementError as exc:
            return exc.returncode

        return self.__wrapped__(*args, **kwargs)

    def check_requirements(self):
        """Check for ping executable, localhost and gateway."""

        # ensure ping on PATH
        ping_path = shutil.which('ping')
        if ping_path is None:
            task.log.critical("ping executable not found")
            raise self.RequirementError(task.status.file_missing)

        # check network interface up
        try:
            command.ping_dest_once('localhost')
        except subprocess.CalledProcessError:
            task.log.critical(
                dest='localhost',
                status='Error',
                msg="host network interface down",
            )
            raise self.RequirementError(task.status.os_error)
        else:
            task.log.debug(dest='localhost', status='OK')

        # check route to gateway
        gateways = netifaces.gateways()

        try:
            (gateway_addr, _iface) = gateways['default'][netifaces.AF_INET]
        except KeyError:
            task.log.critical("default gateway not found")
            raise self.RequirementError(task.status.os_error)

        gateway_up = command.ping_dest_succeed_once(gateway_addr)

        if gateway_up:
            task.log.log(
                'DEBUG' if gateway_up.attempts == 1 else 'WARNING',
                dest='gateway',
                addr=gateway_addr,
                tries=gateway_up.attempts,
                status='OK',
            )
        else:
            task.log.critical(
                dest='gateway',
                addr=gateway_addr,
                tries=gateway_up.attempts,
                status=f'Error ({gateway_up.returncode})',
                msg="network gateway inaccessible",
            )
            raise self.RequirementError(task.status.no_host)
