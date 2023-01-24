"""Measurement utilities to ensure network connectivity."""

from .command import ping_dest_once, ping_dest_succeed_once  # noqa: F401

from .decorator import require_lan  # noqa: F401
