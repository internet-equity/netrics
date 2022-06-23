import argparse
import enum
import functools
import sys
import textwrap

import argcmdr
import plumbum.commands.base


class Executor(argcmdr.Local):
    """Base class for commands that execute measurements.

    Subclasses must define `get_command` to specify the measurement name
    (if any) and command to execute.

    """
    redirection_command_types = (
        plumbum.commands.base.StdinRedirection,
        plumbum.commands.base.StdinDataRedirection,
    )

    class CommandStatus(enum.Enum):
        """Status categories of measurement command return codes."""

        OK = 0
        Retry = 42
        Error = -1  # any other

        @classmethod
        def status(cls, code):
            """Retrieve appropriate status for given return code."""
            value = int(code)

            try:
                return cls(value)
            except ValueError:
                if value > 0:
                    return cls.Error

                raise

        def __str__(self):
            return self.name

    @staticmethod
    def print_output(name, text):
        """Print report value text formatted appropriately for its
        length (number of lines).

        """
        if '\n' in text:
            print(f'{name}:', textwrap.indent(text, '  '), sep='\n\n')
        else:
            print(f'{name}:', text)

    @classmethod
    def print_report(cls, name, command, retcode, stdout, stderr):
        """Print a report of measurement command execution outcomes."""
        print('Name:', '-' if name is None else name)

        # If we're composing the command with "echo" or otherwise providing
        # stdin then let's not include that in the report:
        cmd = command.cmd if isinstance(command, cls.redirection_command_types) else command

        print('Command:', cmd)

        print()

        if retcode is None:
            print('Status: Dry Run')
            return

        print('Status:', cls.CommandStatus.status(retcode), f'(Exit code {retcode})')

        print()

        cls.print_output('Result', stdout if stdout else '-')

        if stderr:
            print()
            cls.print_output('Standard error', stderr)

    def __init__(self, parser):
        super().__init__(parser)

        # argcmdr built-in arguments (@)
        # netrics added-in arguments (%)

        # (@) never print commands to be executed
        #     (we handle this in the report):
        parser.set_defaults(
            show_commands=False,
        )

        # (@) look up but do not actually execute commands during dry run:
        parser.add_argument(
            '-d', '--dry-run',
            action='store_false',
            dest='execute_commands',
            help="do not execute command",
        )

        # (%) copy stdout results to given path:
        parser.add_argument(
            '-o', '--stdout',
            metavar='path',
            type=argparse.FileType('w'),
            help="write command result to path",
        )

        # (%) copy stderr output to given path:
        parser.add_argument(
            '-e', '--stderr',
            metavar='path',
            type=argparse.FileType('w'),
            help="write command standard error to path",
        )

        # (@) pass command output (stdout and stderr) through (to terminal):
        parser.add_argument(
            '-p', '--print-output',
            action='store_true',
            default=False,
            dest='foreground',
            help="print command output (in addition to report)",
        )

        # (%) silence netrics command execution report:
        parser.add_argument(
            '--no-report',
            action='store_false',
            dest='report',
            help="do not print command report",
        )

    def get_command(self, args):
        """Determine measurement name (if any) and command to execute
        from CLI argumentation.

        Returns either just a command to execute -- plumbum
        `BaseCommand` -- or a tuple of the measurement name and the
        command -- `(str, BaseCommand)`.

        """
        super(argcmdr.Local, self).__call__(args)

    def prepare(self, args):
        """Execute and report on measurement command execution."""
        command_args = self.call(args, 'get_command')

        if command_args is None:
            return

        if isinstance(command_args, (list, tuple)):
            (measurement_name, command) = command_args
        else:
            (measurement_name, command) = (None, command_args)

        (retcode, stdout, stderr) = yield command

        if args.stdout and stdout is not None:
            print(stdout, end='', file=args.stdout)
            stdout = f'[See {args.stdout.name}]'

        if args.stderr and stderr is not None:
            print(stderr, end='', file=args.stderr)
            stderr = f'[See {args.stderr.name}]'

        if args.report:
            self.print_report(measurement_name, command, retcode, stdout, stderr)

    # Raise no exceptions for command return codes:
    prepare.retcode = None


"""Decorator to manufacture Executor commands from a simple function
defining method `get_command`.

"""
runcmd = functools.partial(argcmdr.cmd, base=Executor, method_name='get_command')
