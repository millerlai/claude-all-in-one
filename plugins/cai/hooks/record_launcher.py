"""Writes the launcher record that run-guard.cmd reads on every hook call.

Run by the interpreter being probed, as `<candidate> record_launcher.py <form>
<candidate-name>`, with the record's absolute path in CAI_GUARD_RECORD. It
records the interpreter's own `sys.executable` when that is a plain ASCII
absolute path to an existing file, and the candidate's name otherwise.

Exit 0: written. 73: the directory, the temp file or the replace failed (the
interpreter works, the record does not). 1: bad arguments or environment, or
any other failure -- the dispatcher treats that as a failed probe.

Standard library only and no import of the plugin's other modules: it runs
under whatever interpreter step 1 just proved can run the guard.
"""
import os
import sys
import tempfile

# The 73 characters a record may hold. `% ^ ! & | < > "` are left out: CMD
# reads them again in `call`, `if` and `echo`.
SAFE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                 " _.-\\/:()~+")
CANDIDATES = ("py -3", "python", "python3")
CANNOT_WRITE = 73


def record_line(executable, candidate):
    if (os.path.isabs(executable) and os.path.isfile(executable)
            and all(char in SAFE for char in executable)):
        return "cai-launcher 1 path " + executable + " end"
    return "cai-launcher 1 name " + candidate + " end"


def write_record(path, line, newline):
    """Raises OSError. Same-directory temp file then os.replace, so a reader sees
    the old record or the new one and never half a line."""
    dirname = os.path.dirname(path)
    os.makedirs(dirname, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dirname, prefix=os.path.basename(path) + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write((line + newline).encode("ascii"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv, environ):
    if len(argv) != 2 or argv[0] not in ("cmd", "sh") or argv[1] not in CANDIDATES:
        return 1
    path = environ.get("CAI_GUARD_RECORD")
    if not path or not os.path.isabs(path):
        return 1
    newline = "\r\n" if argv[0] == "cmd" else "\n"
    try:
        write_record(path, record_line(sys.executable, argv[1]), newline)
    except OSError:
        return CANNOT_WRITE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
