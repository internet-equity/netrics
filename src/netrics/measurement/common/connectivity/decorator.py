"""Measurement decorators to ensure network connectivity."""
import concurrent.futures
import functools
import shutil
import subprocess

import netifaces
from fate.conf.schema import ConfSchema
from fate.util.datastructure import AttributeDict
from schema import Optional, SchemaError

from netrics import conf, task

from . import command, default


class RequirementError(Exception):

    def __init__(self, returncode):
        super().__init__(returncode)
        self.returncode = returncode


class require_lan:
    """Decorator to extend a network measurement function with
    preliminary network accessibility checks.

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

    def __repr__(self):
        return repr(self.__wrapped__)

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


class require_net(require_lan):
    """Decorator to extend a network measurement function with
    preliminary network and internet accessibility checks.

    `require_net` wraps the decorated function such that it will first
    execute the checks implemented by `require_lan`; then, it will ping
    internet hosts in parallel, prior to proceeding with the measurement
    function's own functionality.

    Should any internet host respond to a single ping after a configured
    number of attempts, measurement will proceed.

    Should no internet hosts respond, measurement will be aborted.

    For example:

        @require_net
        def main():
            # Now we know at least that the LAN is operational *and* the
            # Internet is accessible.
            #
            # For example, let's *now* attempt to access Google DNS:
            #
            result = subprocess.run(
                ['ping', '-c', '1', '8.8.8.8'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return result.returncode

    Configuration of internet hosts to ping, and the number of attempts
    to make, may be given in the "defaults" file under the extension key
    `ext.require_net`, for example:

        ext:
          require_net:
            attempts: 3
            destinations:
              - google.com
              - facebook.com
              - nytimes.com

    """
    schema = ConfSchema({
        Optional('destinations', default=default.PING_DESTINATIONS):
            task.schema.DestinationList(),

        Optional('attempts', default=command.DEFAULT_ATTEMPTS):
            task.schema.NaturalNumber('attempts'),
    })

    def check_requirements(self):
        super().check_requirements()

        try:
            conf_net = conf.default.ext.require_net
        except AttributeError:
            conf_net = True
        else:
            if conf_net is False:
                return  # disabled

        if conf_net is True:
            conf_net = AttributeDict()

        try:
            params = self.schema.validate(conf_net)
        except SchemaError as exc:
            task.log.critical(check=self.__class__.__name__,
                              error=str(exc),
                              msg="configuration error at 'ext.require_net'")
            raise self.RequirementError(task.status.conf_error)

        # We want to return as soon as we receive ONE ping success; so,
        # we needn't test *every* result.
        #
        # And, we take in easy on ourselves, and delegate to a thread pool.
        #
        # Note: we *could* monitor results synchronously (with sleeps), or use
        # a *nix feature like os.wait() to good effect; however,
        # concurrent.futures makes this *darn* easy, (and this is perhaps the
        # direction that this library is going for subprocess management
        # regardless). Plus, as attractive as *nix features may be, (and as
        # little as Windows is currently under consideration), *this* is likely
        # not the place to bind to platform-dependent features.

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(command.ping_dest_succeed_once,
                                       dest,
                                       params.attempts): dest
                       for dest in params.destinations}

            for future in concurrent.futures.as_completed(futures):
                success = future.result()

                if success:
                    task.log.log(
                        'DEBUG' if success.attempts == 1 else 'WARNING',
                        dest=futures[future],
                        tries=success.attempts,
                        status='OK',
                    )
                    return  # success!
            else:
                task.log.critical(
                    dest=(params.destinations if len(params.destinations) < 4
                          else params.destinations[:3] + ['...']),
                    tries=params.attempts,
                    status='Error',
                    msg="internet inaccessible",
                )
                raise self.RequirementError(task.status.no_host)
