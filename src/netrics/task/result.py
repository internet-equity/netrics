"""Task result recording compatible with the Fate scheduler."""
import time

import fate.task.result


def write(results, /, label=None, meta=True, **kwargs):
    """Write task results.

    Wraps results in metadata, by default, according to `meta=True`;
    and, places results under the key `label`, if provided.

    See `fate.task.result.write` for further details.

    """
    if label:
        results = {label: results}

    if meta:
        results = {
            'Measurements': results,
            'Meta': {
                'Time': time.time(),
            },
        }

    return fate.task.result.write(results, **kwargs)
