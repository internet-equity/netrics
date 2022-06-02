from argparse import REMAINDER

from .. import Netrics, runcmd


@Netrics.register
@runcmd('arguments', metavar='command-arguments', nargs=REMAINDER, help="command arguments (optional)")
@runcmd('command', help="program to execute")
def execute(context, args):
    """execute an arbitrary program as an ad-hoc measurement"""
    return context.local[args.command][args.arguments]
