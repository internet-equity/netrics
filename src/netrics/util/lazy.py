import abc
import collections.abc
import typing
from dataclasses import dataclass

import schema
from descriptors import cachedproperty


class LazilyValidated(abc.ABC):
    """Abstract base class of lazy-validation data wrappers.

    Concrete subclasses must implement internal method `_get_value_` to
    trigger validation and realization of wrapped data.

    Validated data are accessible via public (caching) property `value`
    *and* via invocation of the instance.

    Lazily-evaluated promises for items contained within the data may be
    retrieved (recursively) via subscription.

    See `LazyValidator` and `LazyItem`.

    """
    @abc.abstractmethod
    def _get_value_(self):
        return None

    @cachedproperty
    def value(self):
        return self._get_value_()

    def __call__(self):
        return self.value

    def __getitem__(self, key):
        return LazyItem(self, key)


@dataclass
class LazyValidator(LazilyValidated):
    """Entrypoint for lazy validation of `data` by the given `schema`.

    See `LazilyValidated`.

    """
    schema: schema.Schema
    data: collections.abc.Collection

    def _get_value_(self):
        return self.schema.validate(self.data)

    def __repr__(self):
        value = repr(self.value) if 'value' in self.__dict__ else 'unknown'
        return f'<{self.__class__.__name__}: {value}>'


@dataclass
class LazyItem(LazilyValidated):
    """Lazily-evaluated promise for an item contained within lazily-
    validated data.

    See `LazilyValidated` and `LazyValidator`.

    """
    src: LazilyValidated
    key: typing.Any

    def _get_value_(self):
        return self.src()[self.key]

    def __repr__(self):
        value = repr(self.value) if 'value' in self.__dict__ else 'unknown'
        return f'<{self.__class__.__name__}[{self.key!r}]: {value}>'
