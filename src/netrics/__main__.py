import fate


conf = fate.conf.get(
    fate.conf.spec.default,
    fate.conf.spec.task._replace(filename='measurements'),
    lib='netrics',
)


def main():
    fate.main(conf=conf)


if __name__ == '__main__':
    main()
