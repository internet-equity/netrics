"""Common helpers requiring system executables"""
import functools
import shutil

import netrics.task


class ExecTask:
    """Wrapped callable requiring named system executable(s)."""

    def __init__(self, func, names):
        self._executable_names_ = names

        # assign func's __module__, __name__, etc.
        # (but DON'T update __dict__)
        #
        # (also assigns __wrapped__)
        functools.update_wrapper(self, func, updated=())

    def __repr__(self):
        return repr(self.__wrapped__)

    def __call__(self, *args, **kwargs):
        # ensure executables on PATH
        executable_paths = [shutil.which(name) for name in self._executable_names_]

        for (executable_name, executable_path) in zip(self._executable_names_, executable_paths):
            if executable_path is None:
                netrics.task.log.critical(f"{executable_name} executable not found")
                return netrics.task.status.file_missing

        return self.__wrapped__(*executable_paths, *args, **kwargs)


class require_exec:
    """Decorator constructor to wrap a callable such that it first
    checks that the named system executable(s) are accessible on `PATH`.

    """
    def __init__(self, *names):
        self.executable_names = names

    def __call__(self, func):
        return ExecTask(func, self.executable_names)
