from functools import partial

import fate


conf = fate.conf.get(
    fate.conf.spec.default,
    fate.conf.spec.task._replace(filename='measurements'),
    lib='netrics',
)


def entrypoint(hook):
    hook(
        conf=conf,
        banner_path='netrics.cli.include.banner',
    )


main = partial(entrypoint, fate.main)

daemon = partial(entrypoint, fate.daemon)

serve = partial(entrypoint, fate.serve)


if __name__ == '__main__':
    main()
