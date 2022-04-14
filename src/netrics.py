from subprocess import PIPE, Popen
import argparse
import yaml

# Local imports
from cmds.run import run

SUPPORTED_CMDS = ["run"]

def parse_args():
    """
    Parse command and command options

    Parameters
    ----------
    None

    Returns
    -------
    args : argparse.Namespace()
        Namespace of the arguments passed to netrics via command line
    """

    parser = argparse.ArgumentParser(description="Command line arg parser")

    parser.add_argument(
            'command',
            help="Netrics command. Currently supports: [run]")

    parser.add_argument(
            'utility',
            help="Utility to run. Currently supports: [ping]")

    args = parser.parse_args()

    return args
        
        
def execute():
    """ Entry-point for the netrics framework """

    # Parse command line args
    args = parse_args()

    # Read in netrics config
    with open("netrics-config.yaml", "r") as f:
                config = yaml.safe_load(f)

    if args.command == "run":
        run(args.utility, config[args.utility])
    else:
        print(f'Unrecognized command {args.command}')
        print(f'Please select from {*SUPPORTED_CMDS}')

    
if __name__ == '__main__':
    execute()
