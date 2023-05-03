#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request


APP_NAME = 'netrics'

# specify for use via pipe
PROG_NAME = 'install.py'

PROG_DESC = f'install {APP_NAME}'

INSTALL_PATHS = (
    pathlib.Path('/usr/local/bin/'),
    pathlib.Path.home() / '.local' / 'bin',
    pathlib.Path.home() / 'bin',
)

PYVERSION_RANGE = (8, 11)

RELEASES_URL = f'https://api.github.com/repos/internet-equity/{APP_NAME}/releases'

LATEST_RELEASE_URL = RELEASES_URL + '/latest'

LATEST_RELEASE_PRE_URL = RELEASES_URL + '?per_page=1'

DOWNLOAD_URL = (f'https://github.com/internet-equity/{APP_NAME}/releases/download'
                f'/{{APP_VERSION}}/{APP_NAME}-all-{{APP_VERSION}}-py{{PY_VERSION}}-{{ARCH}}.tar')


#
# support py38
#
def is_relative_to(path, root):
    """Return True if the path is relative to another path or False."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    else:
        return True


#
# see also! fate:src/fate/util/os.py
#
def system_path(path):
    """Whether the given Path `path` appears to be a non-user path.

    Returns bool – or None if called on an unsupported platform
    (_i.e._ implicitly False).

    """
    if sys.platform == 'linux':
        return not is_relative_to(path, '/home') and not is_relative_to(path, '/root')

    if sys.platform == 'darwin':
        return not is_relative_to(path, '/Users')


def dir_writable(path):
    """Whether given Path `path` is writable or createable directory.

    Returns whether the *extant portion* of the given path is a
    writable directory. If so, the directory is either extant and
    writable or its nearest extant parent is writable (and as such the
    path may be created in a writable form).

    """
    while not path.exists():
        parent = path.parent

        # reliably determine whether this is the root
        if parent == path:
            break

        path = parent

    return path.is_dir() and os.access(path, os.W_OK)


def path_env(path_var=os.getenv('PATH', ''), /):
    """The process environment PATH as a list of pathlib.Path."""
    paths = path_var.split(':') if path_var else []
    return [pathlib.Path(path) for path in paths]


class InstallPath(argparse._StoreAction):
    """Command line argument processor for the installation path."""

    def __init__(self,
                 option_strings,
                 dest,
                 default=None,
                 required=False,
                 help=None,
                 metavar=None):
        if default is None:
            default = self._install_path_default_()

        if help is None:
            help = "path to which to install executables"

            if default:
                help += " (default: %(default)s)"

        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs='?' if default else None,
            const=None,
            default=default,
            type=self._clean_install_path_,
            choices=None,
            required=required,
            help=help,
            metavar=metavar,
        )

    @staticmethod
    def _clean_install_path_(value):
        path = pathlib.Path(value).resolve()

        if not dir_writable(path):
            raise argparse.ArgumentTypeError('non-writable or non-createable directory')

        return path

    @staticmethod
    def _install_path_default_(options=INSTALL_PATHS):
        """Find an appropriate default for the installation path.

        The returned pathlib.Path must be either a writable or createable
        directory, and it must be on PATH.

        Otherwise, None is returned.

        """
        env_paths = set(path_env())

        for path in options:
            if dir_writable(path) and path in env_paths:
                return path


class ArgumentNamespace(argparse.Namespace):

    @property
    def _is_system_path_(self):
        return system_path(self.path)

    @property
    def _record_path_(self):
        return self._state_path_ / 'installer'

    @property
    def _state_path_(self):
        if self._is_system_path_:
            state_path = pathlib.Path('/var/lib')
        elif xdg_state_home := os.getenv('XDG_STATE_HOME', ''):
            state_path = pathlib.Path(xdg_state_home)
        else:
            state_path = pathlib.Path.home() / '.local' / 'state'

        return state_path / APP_NAME

    def _iter_installed_(self):
        try:
            with self._record_path_.open() as fd:
                for record in fd:
                    path = pathlib.Path(record.rstrip())
                    if path.exists():
                        yield path
        except FileNotFoundError:
            pass

    def _open_record_(self, mode='r'):
        self._record_path_.parent.mkdir(parents=True, exist_ok=True)

        return self._record_path_.open(mode)


def py_version(version_min=PYVERSION_RANGE[0],
               version_max=PYVERSION_RANGE[1]):
    if (3, version_max) >= (current_version := sys.version_info[:2]) >= (3, version_min):
        py_version = '.'.join(map(str, current_version))

        if shutil.which('python' + py_version):
            return py_version

    for minor in range(version_max, version_min - 1, -1):
        if shutil.which(f'python3.{minor}'):
            return f'3.{minor}'


def load_release_name(pre=False):
    url = LATEST_RELEASE_PRE_URL if pre else LATEST_RELEASE_URL

    try:
        with urllib.request.urlopen(url) as fd:
            result = json.load(fd)
    except urllib.request.HTTPError:
        return None

    if isinstance(result, list):
        (result,) = result

    return result['tag_name']


def open_release(app_version, python_version, arch):
    url = DOWNLOAD_URL.format(APP_VERSION=app_version,
                              PY_VERSION=python_version.replace('.', ''),
                              ARCH=arch)

    response = urllib.request.urlopen(url)

    content_length = response.getheader('content-length')

    if content_length is None:
        return response
    else:
        return ProgressBar(
            response,
            length=int(content_length),
            message=f'{APP_NAME}-{app_version}',
            ending='\n\n',
        )


class ProgressBar:

    _terminal_size_ = shutil.get_terminal_size((80, None))

    _bar_filler_ = '='
    _bar_ending_ = '=>'
    _bar_template_ = _message_template_ = '[{}]'

    _filler_length_ = _terminal_size_.columns - len(_bar_template_.format(''))

    def __init__(self, file, length, message='', ending='\n', output=sys.stdout):
        self._file_ = file
        self._length_ = length
        self._message_ = message
        self._message_content_ = message and (self._message_template_.format(message) + ' ')
        self._line_ending_ = ending
        self._output_ = output
        self._read_ = 0
        self._done_ = False

    def read(self, size):
        buffer = self._file_.read(size)

        self._read_ += len(buffer)
        self._update_bar_(self._read_ratio_ if buffer else 1)

        return buffer

    @property
    def _read_ratio_(self):
        return self._read_ / self._length_

    def _make_bar_(self, ratio):
        ratio_length = int(ratio * (self._filler_length_ - len(self._message_content_)))

        filler = self._bar_filler_ * (ratio_length - len(self._bar_ending_)) + self._bar_ending_

        return self._bar_template_.format(filler)

    def _update_bar_(self, ratio):
        if self._done_:
            return

        bar = self._make_bar_(ratio)

        self._output_.write('\r' + self._message_content_ + bar)

        if ratio >= 1:
            self._output_.write(self._line_ending_)
            self._done_ = True

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        return self._file_.__exit__(*args, **kwargs)


def style_title(string):
    return f"\033[36;1;4m{string}\033[0m"


def style_bold(string):
    return f"\033[1m{string}\033[0m"


def style_success(string):
    return f"\033[32;1m{string}\033[0m"


def style_trivia(string):
    return f"\033[2;4m{string}\033[0m"


def main(args=None):
    parser = argparse.ArgumentParser(prog=PROG_NAME,
                                     description=PROG_DESC)

    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help="override file overwrite checks",
    )
    parser.add_argument(
        '-U', '--upgrade',
        action='store_true',
        help="reinstall with latest version",
    )
    parser.add_argument(
        '--pre',
        action='store_true',
        help="allow pre-releases",
    )
    parser.add_argument(
        'path',
        action=InstallPath,
    )

    namespace = parser.parse_args(args, ArgumentNamespace())

    try:
        extant_members = set(namespace._iter_installed_())
    except PermissionError as exc:
        parser.error(f'access to installation record was not permitted: {exc.filename}')

    if extant_members and not namespace.upgrade:
        parser.error(
            'existing installation found: specify -U or --upgrade to '
            'replace with latest version'
            '\n\n'
            f'for more information see: {namespace._record_path_}'
        )

    if (python_version := py_version()) is None:
        parser.error('no suitable version of Python found on PATH: ' +
                     ' <= x <= '.join(f'3.{end}' for end in PYVERSION_RANGE))

    if (app_version := load_release_name(namespace.pre)) is None:
        parser.error('no releases available' + ('!' if namespace.pre else ' (try --pre)'))

    arch = platform.processor()

    print(style_title(f'{APP_NAME} installation'), end='\n\n')

    with tempfile.TemporaryDirectory() as staging:
        try:
            with open_release(app_version, python_version, arch) as fd:
                with tarfile.open(fileobj=fd, mode='r|') as package:
                    package.extractall(staging)
        except urllib.request.HTTPError:
            parser.error(f'latest {APP_NAME} release {app_version} has no pre-built '
                         f'packages for your platform: Python v{python_version} on {arch}')

        install_paths = {
            member_path: namespace.path / member_path.name
            for member_path in pathlib.Path(staging).iterdir()
        }

        # check for untracked file conflicts
        if not namespace.force:
            path_conflicts = {target_path for target_path in install_paths.values()
                              if target_path.exists()}
            if would_overwrite := path_conflicts - extant_members:
                parser.error('will not overwrite untracked conflicting files '
                             '(specify -f or --force to override)\n\n' +
                             '\n'.join(map(str, would_overwrite)))

        # perform upgrade (if it is): remove old files
        for extant_member in extant_members:
            extant_member.unlink()

        # install new files
        namespace.path.mkdir(parents=True, exist_ok=True)

        for (member_path, target_path) in install_paths.items():
            member_path.replace(target_path)

        file_count = len(install_paths)

        print(
            style_success('☑'),
            style_bold('★'),
            (
                style_trivia(namespace.path / f'{APP_NAME}*') +
                f': {file_count} executables installed'
            ),
            sep='  ',
            end='\n\n',
        )

    # write installation record
    with namespace._open_record_('w') as fd:
        for target_path in install_paths.values():
            fd.write(f'{target_path}\n')

    # initialize
    proc = subprocess.run(
        (
            namespace.path / APP_NAME,
            'init',
        )
    )

    return proc.returncode


if __name__ == '__main__':
    sys.exit(main())
