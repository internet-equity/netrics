import subprocess


def complete(process: subprocess.Popen) -> subprocess.CompletedProcess:
    """Allow a subprocess to complete and return a `CompletedProcess`.

    `CompletedProcess` is otherwise returned only by the high-level
    function `subprocess.run`. Here, `run`-style functionality is
    recreated for a given `Popen` object:

    * the process is allowed to complete (and the invoking thread is stalled)
    * standard output and error are collected (via `communicate()`)
    * a `CompletedProcess` is returned reflecting the process's command
      argumentation, returncode, standard output and error

    This is of primary use to subprocesses launched via `Popen` for the
    purpose of parallelization. (Otherwise, higher-level interfaces may
    be used.)

    """
    (stdout, stderr) = process.communicate()

    return subprocess.CompletedProcess(
        process.args,
        process.returncode,
        stdout,
        stderr,
    )
