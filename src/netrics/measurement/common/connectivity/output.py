"""Helpers for processing command outputs."""
import re


def parse_ping(output):
    """Parse output from the `ping` command.

    Returns a `dict` of the following form:

        {
            'rtt_min_ms': float,
            'rtt_avg_ms': float,
            'rtt_max_ms': float,
            'rtt_mdev_ms': float,
            'packet_loss_pct': float,
        }

    Note: Where values could not be determined from `output`, the float
    `-1.0` is returned.

    """
    # Extract RTT stats
    rtt_match = re.search(
        r'rtt [a-z/]* = ([0-9.]*)/([0-9.]*)/([0-9.]*)/([0-9.]*) ms',
        output
    )

    rtt_values = [float(value) for value in rtt_match.groups()] if rtt_match else [-1.0] * 4

    rtt_keys = ('rtt_min_ms', 'rtt_avg_ms', 'rtt_max_ms', 'rtt_mdev_ms')

    rtt_stats = zip(rtt_keys, rtt_values)

    # Extract packet loss stats
    pkt_loss_match = re.search(r', ([0-9.]*)% packet loss', output, re.MULTILINE)

    pkt_loss = float(pkt_loss_match.group(1)) if pkt_loss_match else -1.0

    # Return combined dict
    return dict(rtt_stats, packet_loss_pct=pkt_loss)
