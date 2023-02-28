"""Task result recording compatible with the Fate scheduler."""
import time

import fate.task.result


def write(results, /, label=None, annotate=True, **kwargs):
    """Write task results.

    Wraps results in metadata, by default, according to `annotate=True`;
    and, places results under the key `label`, if provided.

    See `fate.task.result.write` for further details.

    """
    if label:
        results = {label: results}

    if annotate:
        results = {
            'Measurements': results,
            'Meta': {
                'Time': time.time(),
            },
        }

    return fate.task.result.write(results, **kwargs)
