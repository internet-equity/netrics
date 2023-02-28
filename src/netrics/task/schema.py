"""Support for construction of schema to validate and to provide
defaults to task input parameters.

"""
import collections.abc
from numbers import Real

from schema import (
    And,
    Optional,
    Or,
    Schema,
    Use,
)

import netrics
from netrics.util import lazy


#
# Schema composite "primitives"
#

Text = And(str, len)  # non-empty str


def DestinationList(name='destinations'):
    return And(
        [Text],
        lambda dests: len(dests) == len(set(dests)),
        error=f"{name}: must be a non-repeating list of network locators",
    )


def DestinationCollection(name='destinations'):
    return Or(
        {Text: Text},
        DestinationList(name),
        error=f"{name}: must be non-repeating list "
              "of network locators or mapping of these "
              "to their result labels",
    )


def NaturalNumber(name):
    return And(int,
               lambda value: value > 0,
               error=f"{name}: int must be greater than 0")


def NaturalStr(name):
    return And(NaturalNumber(name),
               Use(str))


def PositiveInt(name, unit):
    return And(int,
               lambda value: value >= 0,
               error=f"{name}: int {unit} must not be less than 0")


def PositiveIntStr(name, unit):
    return And(PositiveInt(name, unit),
               Use(str))


def BoundedReal(name, message, boundary):
    return And(Real,
               boundary,
               error=f"{name}: {message}")


def BoundedRealStr(*args, **kwargs):
    return And(BoundedReal(*args, **kwargs),
               Use(str))


#
# Schema of result meta params' global defaults configuration
#
# Values provided by defaults configuration file under key `ext.result`.
#
RESULT_META_DEFAULTS = Schema({
    #
    # flat: flatten results dict to one level
    #
    Optional('flat', default=True): bool,

    #
    # label: wrap the above (whether flat or not) in a measurement label
    #
    # (actual *text* of label provided by measurement and overridden by measurement params)
    #
    Optional('label', default=True): bool,

    #
    # annotate: wrap all of the above (whatever it is) with metadata (time, etc.)
    #
    Optional('annotate', default=True): bool,
})


def get_default(label):
    """Construct schema for globally-supported task parameters.

    Default values are populated from those given by any mapping at key
    `ext.result` in the defaults configuration. Note that these values
    are themselves validated, but lazily, such that validation errors
    are raised only during use of the schema returned by this function.
    (See `RESULT_META_DEFAULTS`.)

    As these global parameters concern the handling of task results, the
    text `label` of the measurement is required. This label is applied
    to the results, unless overridden or disabled by task-level
    parameter configuration, or disabled by global default. (See
    `ext.result.label`.)

    """
    # our global defaults specified via mapping at `ext`
    conf_ext = netrics.conf.default.get('ext')

    # configuration may be empty or null ... that's ok
    try:
        default_values = conf_ext['result']
    except (KeyError, TypeError):
        default_conf = {}
    else:
        #
        # Note: This is an issue with schema-validating configuration
        # mappings, which are currently *not* simple instances of dict
        # (and not "registered" as such).
        #
        # This may now be handled using `fate.conf.schema.ConfSchema` in
        # lieu of `schema.Schema`!
        #
        # However, so long as this configuration is so simple as it is
        # -- a single-level of booleans -- and passed off to another
        # layer which treats it as a simple dict, there's little to gain
        # from switching this over.
        #
        # *Should* this be desired, the below conditional cast may be
        # nixed, in lieu of `ConfSchema` above.
        #
        default_conf = (dict(default_values)
                        if isinstance(default_values, collections.abc.Mapping)
                        else default_values)

    #
    # we *do* want to validate -- and provide software defaults for --
    # any configuration that's specified
    #
    # however, we *do not* want to raise validation errors before
    # they're expected (e.g. not at the module-level)
    #
    # luckily, Schema supports *lazy* defaults, retrieved via callable.
    #
    # the below allows us to retrieve callable *promises* for values in
    # the validated defaults configuration.
    #
    # during validation of the measurement's *actual parameterized input*,
    # Schema will invoke these promised defaults, and thereby trigger
    # their own schema validations.
    #
    defaults = lazy.LazyValidator(RESULT_META_DEFAULTS, default_conf)

    # the below are all *callable promises* for our defaults
    default_flat = defaults['flat']
    default_annotate = defaults['annotate']
    default_label = lambda: label if defaults['label']() else None  # noqa: E731

    default_result = lambda: {'annotate': default_annotate(),  # noqa: E731
                              'label': default_label(),
                              'flat': default_flat()}

    return {
        # result: mappping
        Optional('result', default=default_result): {
            # flat: flatten results dict to one level
            Optional('flat', default=default_flat): bool,

            # label: wrap the above (whether flat or not) in a measurement label
            Optional('label', default=default_label): Or(False, None, Text),

            # annotate: wrap all of the above (whatever it is) with metadata (time, etc.)
            Optional('annotate', default=default_annotate): bool,
        },
    }


def extend(label, schema):
    """Construct a task parameter schema extending the globally-
    supported task parameter schema.

    The resulting `dict` will contain both schema for validating
    globally-supported task parameters *and* task-specific parameters
    specified by `schema`.

    See: `get_default`.

    """
    return {**get_default(label), **schema}
