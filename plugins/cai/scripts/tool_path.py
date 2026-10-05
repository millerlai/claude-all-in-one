#!/usr/bin/env python3
"""Find an external tool (git, gh, an interpreter) by its full path, looking
only in trusted PATH entries.

A bare name handed to subprocess lets Windows run a same-named program from
the calling process's current directory before PATH, and an empty or relative
PATH entry means "the current directory" on every platform. shutil.which does
not help on its own: before Python 3.12 it searches the current directory on
Windows whatever NoDefaultCurrentDirectoryInExePath says. So the lookup is done
here, in absolute PATH entries only, skipping the current directory, the
directory the call runs in and any directory holding either (the project root
above a subdirectory), and the tool is started by the path found (#294).

statusline.py and resolve_test_command.py keep their own copy of resolve(),
since one is copied out of the plugin and the other imports no sibling;
tests/test_tool_path.py runs the same cases against all three.
"""
import os


def resolve(name, cwd=None):
    """The full path of `name` in a trusted PATH entry; FileNotFoundError if none."""
    here = [os.path.join(os.path.normcase(os.path.realpath(d)), "")
            for d in (os.getcwd(), cwd) if d]
    if os.name == "nt" and not os.path.splitext(name)[1]:
        names = [name + ext for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if ext]
    else:
        names = [name]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        entry = entry.strip('"')
        if not os.path.isabs(entry):
            continue
        real = os.path.join(os.path.normcase(os.path.realpath(entry)), "")
        if any(h.startswith(real) for h in here):
            continue
        for candidate in names:
            path = os.path.join(entry, candidate)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    raise FileNotFoundError(2, "not found in a trusted PATH entry", name)


def resolve_argv(argv, cwd=None):
    """`argv` with a bare argv[0] replaced by its full path. A path the person
    gave (an override such as CAI_TICKET_CLI) is their choice and kept as is."""
    if os.path.dirname(argv[0]):
        return list(argv)
    return [resolve(argv[0], cwd)] + list(argv[1:])
