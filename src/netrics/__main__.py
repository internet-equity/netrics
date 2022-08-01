import fate


confspec = (
    (
        fate.conf.spec.default,
        fate.conf.spec.task._replace(filename='measurements'),
    ),
    {'lib': 'netrics'},
)


def main():
    fate.main(confspec=confspec)


if __name__ == '__main__':
    main()
