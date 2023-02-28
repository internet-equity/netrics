import functools

from schema import SchemaError

from fate.task.param import read

import netrics.task


class ParamTask:
    """Callable wrapper to first read and validate task input parameters
    as specified by `schema`.

    This wrapper is deployed by the decorator `require`.

    See: `require`.

    """
    def __init__(self, schema, func):
        self.schema = schema

        # assign func's __module__, __name__, etc.
        # (but DON'T update __dict__)
        #
        # (also assigns __wrapped__)
        functools.update_wrapper(self, func, updated=())

    def __repr__(self):
        return repr(self.__wrapped__)

    def __call__(self, *args, **kwargs):
        # read input params
        try:
            params = read(schema=self.schema)
        except SchemaError as exc:
            netrics.task.log.critical(error=str(exc), msg="input error")
            return netrics.task.status.conf_error

        return self.__wrapped__(params, *args, **kwargs)


class require:
    """Wrap the decorated callable to first read and schema-validate
    task input parameters.

    Having validated input, the wrapped callable is invoked with the
    cleaned parameters as its first argument.

    Upon validation error, the wrapped callable is *not* invoked. The
    error is logged and the appropriate status code returned.

    See: `ParamTask`.

    """
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, func):
        return ParamTask(self.schema, func)
