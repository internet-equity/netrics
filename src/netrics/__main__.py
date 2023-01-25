from functools import partial

import fate


#
# load configuration (customized with vanity tweaks, etc.)
#
conf = fate.conf.get(
    # override default configuration file settings
    fate.conf.spec.default,                                 # no change
    fate.conf.spec.task._replace(filename='measurements'),  # measurements rather than tasks

    # use own distro name
    lib='netrics',

    # use own default files
    # and allow fallback to these if configuration is missing
    builtin_path='netrics.conf.include',
    builtin_fallback=True,
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
