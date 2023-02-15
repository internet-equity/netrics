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
        #
        # entry_points: currently only used for configuring shell completion
        #
        # fate defaults to LIB, LIBs & LIBd (like its fate, fates & fated)
        #
        # we have those, but those names would look weird, so we're
        # using the following instead.
        #
        entry_points=(
            'netrics',
            'netrics.s',
            'netrics.d',
        ),
    )


main = partial(entrypoint, fate.main)

daemon = partial(entrypoint, fate.daemon)

serve = partial(entrypoint, fate.serve)


if __name__ == '__main__':
    main()
