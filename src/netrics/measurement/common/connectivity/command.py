"""Common measurement commands to ensure network connectivity."""
import abc
import subprocess

from fate.util.abstract import abstractmember


DEFAULT_DEADLINE = 5
DEFAULT_ATTEMPTS = 3


def ping_dest_once(dest, deadline=DEFAULT_DEADLINE):
    """ping `dest` once (`-c 1`) with given `deadline` (`-w DEADLINE`).

    `deadline` defaults to `{DEFAULT_DEADLINE}`.

    Raises `subprocess.CalledProcessError` if a response packet is not
    received after `deadline` or on any other network or ping error.

    """
    subprocess.run(
        (
            'ping',
            '-c', '1',
            '-w', str(deadline),
            dest,
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


ping_dest_once.__doc__ = ping_dest_once.__doc__.format_map(globals())


class PingResult(abc.ABC):

    _success_ = abstractmember()

    def __init__(self, returncode, attempts):
        self.returncode = returncode
        self.attempts = attempts

    def __bool__(self):
        return self._success_


class PingSuccess(PingResult):

    _success_ = True


class PingFailure(PingResult):

    _success_ = False


def ping_dest_succeed_once(dest, attempts=DEFAULT_ATTEMPTS, **kwargs):
    """ping `dest` *until* a single response is received.

    Returns an instance of a subclass of `PingResult` with the attribute
    `attempts` reflecting the number of attempts made – `PingSuccess` if
    a response is received within `attempts` requests, or `PingFailure`
    if not. `PingSuccess` will evalute to `True` and `PingFailure` to
    `False`.

    `attempts` defaults to `{DEFAULT_ATTEMPTS}`.

    See also: `ping_dest_once`.

    """
    # note: this functionality was apparently in BSD ping (or something)
    # but never in GNU...

    if not isinstance(attempts, int):
        raise TypeError(f'attempts expected int not {attempts.__class__.__name__}')

    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for count in range(1, attempts + 1):
        try:
            ping_dest_once(dest, **kwargs)
        except subprocess.CalledProcessError as exc:
            failure_returncode = exc.returncode

            if failure_returncode > 1:
                # this is more than a response failure: quit and fail
                break
        else:
            # received a response: success
            return PingSuccess(0, count)

    # returned 1 more than `attempts` times
    # or returned a worse code once: fail
    return PingFailure(failure_returncode, count)


ping_dest_succeed_once.__doc__ = ping_dest_succeed_once.__doc__.format_map(globals())
