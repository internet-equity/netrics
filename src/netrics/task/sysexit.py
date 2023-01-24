"""Common exit codes"""
import enum


class status(enum.IntEnum):

    success = 0
    no_host = 68
    software_error = 70
    os_error = 71
    file_missing = 72
    conf_error = 78
