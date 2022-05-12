import argcmdr

import netrics.interface


class Netrics(argcmdr.RootCommand):
    """manage the periodic execution of measurements"""

    @classmethod
    def base_parser(cls):
        parser = super().base_parser()

        # enforce program name when invoked via "python -m netrics"
        if parser.prog == '__main__.py':
            parser.prog = 'netrics'

        return parser


def main():
    # auto-discover nested commands
    argcmdr.init_package(
        netrics.interface.__path__,
        netrics.interface.__name__,
    )

    argcmdr.main(Netrics)
