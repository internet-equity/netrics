import argparse
import os.path

from .. import Netrics, runcmd


READABLE = argparse.FileType('r')


def path_or_text(value):
    """Guess whether to use given value as-is or to treat as a
    filesystem path (from which to read a value).

    Returns either the given value OR an `open()` file descriptor (via
    `FileType`).

    """
    if value.startswith('{') or '\n' in value:
        return value

    if value == '-' or os.path.sep in value or os.path.exists(value):
        return READABLE(value)

    return value


@Netrics.register
@runcmd('arguments', metavar='command-arguments', nargs=argparse.REMAINDER,
        help="command arguments (optional)")
@runcmd('command', help="program to execute")
@runcmd('-i', '--stdin', metavar='path|text', type=path_or_text,
        help="set standard input (parameterization) for command to given path "
             "or text (specify '-' to pass through stdin)")
def execute(context, args):
    """execute an arbitrary program as an ad-hoc measurement"""
    cmd = context.local[args.command][args.arguments]

    if hasattr(args.stdin, 'read'):
        return cmd < args.stdin

    if args.stdin is not None:
        return cmd << args.stdin

    return cmd
