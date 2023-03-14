import itertools


def partition(predicate, iterable):
    """Split `iterable` into two disjoint iterables according
    to the Boolean return value of `predicate(item)` (where `item`
    corresponds to each item of `iterable`).

    This is identical to the composition of
    `filter(predicate, iterable)` and
    `itertools.filterfalse(predicate, iterable)`, with the distinction
    that `iterable` may be an exhaustable generator or iterator, but it
    will not be prematurely exhausted, (thanks to `itertools.tee`).

    """
    (t1, t2) = itertools.tee(iterable)

    return (
        filter(predicate, t1),
        itertools.filterfalse(predicate, t2),
    )


def sequence(predicate, iterable):
    """Split `iterable` into two disjoint sequences.

    This function is identical to `partition`, except that sequences of
    type `tuple` are returned, (in lieu of exhaustable iterators).

    See: `partition`.

    """
    return tuple(map(tuple, partition(predicate, iterable)))
