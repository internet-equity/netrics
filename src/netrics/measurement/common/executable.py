"""Common helpers requiring system executables"""
import functools
import shutil

import netrics.task


class ExecTask:
    """Wrapped callable requiring a named system executable."""

    def __init__(self, name, func):
        self._executable_name_ = name

        # assign func's __module__, __name__, etc.
        # (but DON'T update __dict__)
        #
        # (also assigns __wrapped__)
        functools.update_wrapper(self, func, updated=())

    def __repr__(self):
        return repr(self.__wrapped__)

    def __call__(self, *args, **kwargs):
        # ensure executable on PATH
        executable_path = shutil.which(self._executable_name_)

        if executable_path is None:
            netrics.task.log.critical(f"{self._executable_name_} executable not found")
            return netrics.task.status.file_missing

        return self.__wrapped__(executable_path, *args, **kwargs)


class require_exec:
    """Decorator constructor to wrap a callable such that it first
    checks that the named system executable is accessible via `PATH`.

    """
    def __init__(self, name):
        self.executable_name = name

    def __call__(self, func):
        return ExecTask(self.executable_name, func)
