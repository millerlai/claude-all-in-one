"""The index directory is written only by one build at a time, and only through
names this tool made: planted links, FIFOs and hardlinks are refused or left
alone, a failed write keeps the previous index, and a busy target is retried.
Every test asserts what a caller sees -- result lines, exit codes, file bytes,
status words -- never a file-descriptor number."""
import errno
import json
import os
import stat
import subprocess
import sys
import types

import pytest

import codemap_cli
import codemap_index as idx
import codemap_store as store
from codemap_repo import make_repo

SCRIPTS = os.path.dirname(os.path.abspath(codemap_cli.__file__))
BUSY = "codemap: unsupported (another build or update is running)"


def _cli(capsys, command, repo):
    code = codemap_cli.main([command, "--project-dir", str(repo)])
    lines = capsys.readouterr().out.splitlines()
    return code, (lines[0] if lines else "")


def _sharded_files():
    # Copied from tests/test_codemap_incremental.py so this file stands alone.
    return {"pkg%d/m%d.py" % (d, m): "".join(
                "def f%d_%d_%d(a, b):\n    return a\n\n" % (d, m, i) for i in range(8))
            for d in range(4) for m in range(5)}


def _setup(tmp_path, files):
    """A repo, a directory outside it, and the (empty) index directory."""
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    make_repo(repo, files)
    index = repo / ".cai" / "codemap"
    index.mkdir(parents=True)
    return repo, outside, index


def _link(kind, target, link):
    if kind == "junction":
        if os.name != "nt":
            pytest.skip("junctions exist only on Windows")
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    elif kind == "hardlink":
        os.link(str(target), str(link))
    else:
        try:
            os.symlink(str(target), str(link),
                       target_is_directory=os.path.isdir(str(target)))
        except (OSError, NotImplementedError):
            # Only Windows withholds symlinks for lack of a privilege; on POSIX
            # the failure must fail the test so a green Linux run means it ran.
            if os.name == "nt":
                pytest.skip("symlinks need privileges here")
            raise


# A second process that takes the write lock and keeps it until its stdin closes.
HOLDER = """
import sys
sys.path.insert(0, sys.argv[1])
import codemap_store as s
fd = s.acquire_write_lock(sys.argv[2])
print("held", flush=True)
sys.stdin.read()
s.release_write_lock(fd)
"""


def _lock_function():
    """The OS call acquire_write_lock makes, as (module, attribute name, is-unlock)."""
    if os.name == "nt":
        import msvcrt
        return msvcrt, "locking", lambda args: args[1] == msvcrt.LK_UNLCK
    import fcntl
    return fcntl, "flock", lambda args: args[1] == fcntl.LOCK_UN


def test_entry_kind_reads_the_name_surrogate_bit():
    # Literal tags: stat.IO_REPARSE_TAG_* exist only on Windows, and this must
    # reach the Windows branch on Linux too.
    reparse = stat.FILE_ATTRIBUTE_REPARSE_POINT

    def info(mode, attributes=0, tag=0):
        return types.SimpleNamespace(st_mode=mode, st_file_attributes=attributes,
                                     st_reparse_tag=tag)

    assert store._entry_kind(info(stat.S_IFLNK)) == "link"
    assert store._entry_kind(info(stat.S_IFDIR, reparse, 0xA0000003)) == "link"       # junction
    assert store._entry_kind(info(stat.S_IFDIR, reparse, 0x9000001A)) == "directory"  # cloud
    assert store._entry_kind(info(stat.S_IFDIR)) == "directory"
    assert store._entry_kind(info(stat.S_IFREG)) == "file"
    assert store._entry_kind(info(stat.S_IFIFO)) == "other"


def test_lstat_or_none_only_forgives_a_missing_name(tmp_path):
    assert store._lstat_or_none(str(tmp_path / "missing")) is None
    (tmp_path / "plain").write_bytes(b"x")
    assert store._lstat_or_none(str(tmp_path / "plain" / "below")) is None
    assert store._lstat_or_none(str(tmp_path / "plain")) is not None


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_ac1_a_planted_packages_link(tmp_path, capsys, kind):
    repo, outside, index = _setup(tmp_path, _sharded_files())
    _link(kind, outside, index / "packages")
    reason = ".cai/codemap/packages is not a directory inside the repository"
    build = _cli(capsys, "build", repo)
    after_build = sorted(os.listdir(str(outside)))
    update = _cli(capsys, "update", repo)
    status = idx.status(str(repo))
    assert (build, update, after_build, status.word, status.detail) == (
        (2, "codemap: unsupported (%s)" % reason),
        (2, "codemap: unsupported (%s)" % reason), [], "unsupported", reason)


def test_a_real_packages_directory_is_not_refused(tmp_path, capsys):
    repo, _, _ = _setup(tmp_path, _sharded_files())
    assert _cli(capsys, "build", repo)[0] == 0
    assert _cli(capsys, "build", repo)[0] == 0
    assert idx.status(str(repo)).word == "fresh"


@pytest.mark.parametrize("failure", [PermissionError, OSError])
def test_ac7_replace_retrying_alone(tmp_path, monkeypatch, failure):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    real, sleeps, tries = os.replace, [], []

    def flaky(a, b):
        tries.append(1)
        if len(tries) <= 2:
            raise failure("busy")
        return real(a, b)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(store, "time", types.SimpleNamespace(sleep=sleeps.append))
    if failure is OSError:
        with pytest.raises(OSError):
            store._replace_retrying(str(src), str(dst))
        assert (len(tries), sleeps, dst.read_bytes()) == (1, [], b"old")
    else:
        store._replace_retrying(str(src), str(dst))
        assert (len(sleeps), dst.read_bytes(), src.exists()) == (2, b"new", False)


def test_ac7_replace_retrying_gives_up_with_the_last_error(tmp_path, monkeypatch):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.write_bytes(b"new")
    sleeps = []

    def busy(a, b):
        raise PermissionError("busy")

    monkeypatch.setattr(os, "replace", busy)
    monkeypatch.setattr(store, "time", types.SimpleNamespace(sleep=sleeps.append))
    with pytest.raises(PermissionError):
        store._replace_retrying(str(src), str(dst))
    assert len(sleeps) == store.REPLACE_ATTEMPTS - 1


def test_a_new_temp_is_exclusive_and_unlinks_quietly(tmp_path):
    fd, first = store._new_temp(str(tmp_path), "files.jsonl")
    os.close(fd)
    fd, second = store._new_temp(str(tmp_path), "files.jsonl")
    os.close(fd)
    assert first != second
    assert os.path.basename(first).startswith("files.jsonl.")
    assert first.endswith(store.TEMP_SUFFIX)
    store._unlink_quietly(first)
    store._unlink_quietly(first)        # already gone: no error
    assert not os.path.exists(first) and os.path.exists(second)


ENTRY = "codemap: unsupported (.cai/codemap holds an entry that is not a regular file or directory)"


@pytest.mark.parametrize("kind", ["hardlink", "symlink"])
def test_ac2_a_link_at_the_old_temp_name(tmp_path, capsys, kind):
    repo, outside, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    victim = outside / "victim.txt"
    victim.write_bytes(b"keep me\n")
    old_name = index / ("files.jsonl.%d.tmp" % os.getpid())
    _link(kind, victim, old_name)
    code, line = _cli(capsys, "build", repo)
    assert victim.read_bytes() == b"keep me\n"
    if kind == "symlink":
        assert (code, line) == (2, ENTRY)
    else:
        # A hardlink is a regular file: the build goes ahead under new names and
        # the sweep removes only that name, never the file it shares.
        assert code == 0 and line.startswith("codemap: fresh")
        assert not old_name.exists() and victim.exists()


def test_ac2_temp_names_are_new_each_time(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    directory = store.ensure_dir(top)
    first = store.write_atomic(top, "files.jsonl", b"x")
    second = store.write_atomic(top, "files.jsonl", b"x")
    old_name = os.path.join(directory, "files.jsonl.%d.tmp" % os.getpid())
    try:
        assert first.tmp != second.tmp
        for staged in (first, second):
            assert staged.tmp.startswith(os.path.join(directory, "files.jsonl."))
            assert staged.tmp.endswith(".tmp") and staged.tmp != old_name
            assert staged.target == os.path.join(directory, "files.jsonl")
    finally:
        store.discard([first, second])
    assert not os.path.exists(first.tmp) and not os.path.exists(second.tmp)


def _index_tmp(repo):
    found = []
    for _, _, names in os.walk(os.path.join(str(repo), ".cai", "codemap")):
        found.extend(n for n in names if n.endswith(".tmp"))
    return found


def _index_bytes(repo):
    """Every data file and state.json, by relative name."""
    root, seen = os.path.join(str(repo), ".cai", "codemap"), {}
    for dirpath, _, names in os.walk(root):
        for name in names:
            if name in (store.LOCK_NAME, ".gitignore"):
                continue
            with open(os.path.join(dirpath, name), "rb") as fh:
                seen[os.path.relpath(os.path.join(dirpath, name), root)] = fh.read()
    return seen


def test_ac7_replace_retries_a_busy_target(tmp_path, capsys, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    real, busy, sleeps = os.replace, [], []

    def busy_twice(src, dst):
        if os.path.basename(dst) == "files.jsonl" and len(busy) < 2:
            busy.append(dst)
            raise PermissionError("busy")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", busy_twice)
    monkeypatch.setattr(store, "time", types.SimpleNamespace(sleep=sleeps.append))
    code, line = _cli(capsys, "build", tmp_path)
    monkeypatch.undo()
    assert code == 0 and line.startswith("codemap: fresh")
    assert idx.status(str(tmp_path)).word == "fresh"
    assert len(sleeps) == 2


def test_ac7_replace_gives_up_after_the_last_attempt(tmp_path, capsys, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    real, sleeps = os.replace, []

    def always_busy(src, dst):
        if os.path.basename(dst) == "files.jsonl":
            raise PermissionError("busy")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", always_busy)
    monkeypatch.setattr(store, "time", types.SimpleNamespace(sleep=sleeps.append))
    code = codemap_cli.main(["build", "--project-dir", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()
    monkeypatch.undo()
    assert code == 2 and len(lines) == 1
    assert lines[0].startswith("codemap: unsupported (PermissionError")
    assert len(sleeps) == store.REPLACE_ATTEMPTS - 1
    assert _index_tmp(tmp_path) == []


@pytest.mark.parametrize("where", ["second_write_atomic", "inside_write_atomic"])
def test_ac8_a_failed_temp_write_keeps_the_previous_index(tmp_path, monkeypatch, where):
    top = make_repo(tmp_path, {"a.py": "def a():\n    return 1\n"})
    assert idx.build(top).word == "fresh"
    before = _index_bytes(tmp_path)
    calls, inside = [], []
    real_write, real_fdopen = store.write_atomic, os.fdopen

    class Failing:
        def __init__(self, fh):
            self.fh = fh

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.fh.close()

        def write(self, data):
            raise OSError("disk full")

    def write_atomic(top_, name, data):
        calls.append(name)
        if len(calls) == 2 and where == "second_write_atomic":
            raise OSError("disk full")
        inside[:] = [len(calls) == 2]
        try:
            return real_write(top_, name, data)
        finally:
            inside[:] = [False]

    def fdopen(*args, **kwargs):
        fh = real_fdopen(*args, **kwargs)
        # Only the fdopen issued inside the second write_atomic: with an index
        # already there, the first fdopen of a build is the .gitignore read.
        return Failing(fh) if inside and inside[0] else fh

    monkeypatch.setattr(store, "write_atomic", write_atomic)
    if where == "inside_write_atomic":
        monkeypatch.setattr(os, "fdopen", fdopen)
    with pytest.raises(OSError):
        idx.build(top)
    monkeypatch.undo()
    assert idx.status(top).word == "fresh"
    assert _index_bytes(tmp_path) == before
    assert _index_tmp(tmp_path) == []
    assert idx.build(top).word == "fresh"
    assert _index_tmp(tmp_path) == []


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_ac3_sweep_and_a_planted_directory_link(tmp_path, capsys, kind):
    repo, outside, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    (outside / "precious.txt").write_bytes(b"mine\n")
    _link(kind, outside, index / "stash")
    code, line = _cli(capsys, "build", repo)
    assert (code, line, sorted(os.listdir(str(outside))), os.path.lexists(str(index / "stash"))) \
        == (2, ENTRY, ["precious.txt"], True)


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_sweep_never_enters_or_removes_a_link(tmp_path, kind):
    # Straight at sweep, so the proof is sweep's own and not check_entries'.
    repo, outside, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    top = str(repo)
    assert idx.build(top).word == "fresh"
    (outside / "precious.txt").write_bytes(b"mine\n")
    _link(kind, outside, index / "stash")
    artifacts = json.loads((index / "state.json").read_text(encoding="utf-8"))["artifacts"]
    store.sweep(top, set(artifacts))
    assert sorted(os.listdir(str(outside))) == ["precious.txt"]
    assert os.path.lexists(str(index / "stash"))
    assert all((index / name).is_file() for name in artifacts)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFO on this platform")
def test_sweep_leaves_a_fifo_where_it_is(tmp_path):
    repo, _, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    top = str(repo)
    assert idx.build(top).word == "fresh"
    os.mkfifo(str(index / "pipe"))
    store.sweep(top, set())
    assert os.path.lexists(str(index / "pipe"))
    assert (index / store.LOCK_NAME).is_file() and (index / "state.json").is_file()
    assert not (index / "files.jsonl").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFO on this platform")
def test_ac5_a_planted_fifo_inside_packages(tmp_path):
    repo, _, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    (index / "packages").mkdir()
    os.mkfifo(str(index / "packages" / "pkg0.md"))
    try:
        done = subprocess.run([sys.executable, codemap_cli.__file__, "build",
                               "--project-dir", str(repo)],
                              capture_output=True, encoding="utf-8", timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("build still running after 30 s")
    assert (done.returncode, done.stdout.splitlines()[:1]) == (2, [ENTRY])


@pytest.mark.parametrize("variant", ["a_wrong_body_replace_fails", "b_right_body"])
def test_ac4_a_planted_gitignore_symlink(tmp_path, capsys, monkeypatch, variant):
    repo, outside, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    body = b"keep\n" if variant.startswith("a") else b"*\n"
    victim = outside / "ignore.txt"
    victim.write_bytes(body)
    _link("symlink", victim, index / ".gitignore")
    if variant.startswith("a"):
        def refuse(src, dst):
            raise OSError("replace refused")
        monkeypatch.setattr(os, "replace", refuse)
    code, line = _cli(capsys, "build", repo)
    monkeypatch.undo()
    left = sorted(n for n in os.listdir(str(index)) if n != ".gitignore")
    assert (code, line, victim.read_bytes(), left) == (
        2, "codemap: unsupported (.cai/codemap/.gitignore is not a regular file)", body, [])


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFO on this platform")
@pytest.mark.parametrize("name, reason", [
    (".gitignore", ".cai/codemap/.gitignore is not a regular file"),
    ("write.lock", ".cai/codemap/write.lock is not a regular file"),
])
def test_ac5_a_planted_fifo(tmp_path, name, reason):
    repo, _, index = _setup(tmp_path, {"a.py": "x = 1\n"})
    os.mkfifo(str(index / name))
    try:
        done = subprocess.run([sys.executable, codemap_cli.__file__, "build",
                               "--project-dir", str(repo)],
                              capture_output=True, encoding="utf-8", timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("build still running after 30 s")
    assert (done.returncode, done.stdout.splitlines()[:1]) == (
        2, ["codemap: unsupported (%s)" % reason])


def test_ac6_two_interleaved_writers(tmp_path, capsys, monkeypatch):
    make_repo(tmp_path, {"a.py": "def a():\n    return 1\n"})
    top = str(tmp_path)
    real = store.write_atomic
    second = []

    def first_write_runs_a_whole_second_build(top_, name, data):
        got = real(top_, name, data)
        if not second:
            second.append("running")
            second[0] = _cli(capsys, "build", tmp_path)
        return got

    monkeypatch.setattr(store, "write_atomic", first_write_runs_a_whole_second_build)
    first = idx.build(top)
    monkeypatch.undo()
    final = idx.status(top)
    seen = (first.word, second, final.word, final.detail)
    assert (first.word, second, final.word) == ("fresh", [(2, BUSY)], "fresh"), seen


def test_ac6_a_second_process_holding_the_lock_is_refused(tmp_path, capsys):
    make_repo(tmp_path, {"a.py": "def a():\n    return 1\n"})
    top = str(tmp_path)
    assert _cli(capsys, "build", tmp_path)[0] == 0
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, SCRIPTS, top],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        refused = _cli(capsys, "build", tmp_path)
        holder.stdin.close()
        holder.wait(timeout=30)
    finally:
        if holder.poll() is None:
            holder.kill()
    assert refused == (2, BUSY)
    assert _cli(capsys, "build", tmp_path)[0] == 0
    assert idx.status(top).word == "fresh"


def test_ac6_the_next_build_succeeds_after_the_holder_raised(tmp_path, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})

    def boom(*args, **kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(store, "write_atomic", boom)
    with pytest.raises(OSError):
        idx.build(str(tmp_path))
    monkeypatch.undo()
    assert idx.build(str(tmp_path)).word == "fresh"
    assert idx.status(str(tmp_path)).word == "fresh"


def test_ac6_the_lock_file_survives_the_sweep(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    idx.build(str(tmp_path))
    idx.build(str(tmp_path))
    assert os.path.isfile(os.path.join(str(tmp_path), ".cai", "codemap", store.LOCK_NAME))


def test_a_lock_error_that_is_not_busy_travels_as_itself(tmp_path, capsys, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    module, attr, _ = _lock_function()

    def no_locks(*args, **kwargs):
        raise OSError(errno.ENOLCK, "no locks")

    monkeypatch.setattr(module, attr, no_locks)
    code, line = _cli(capsys, "build", tmp_path)
    assert code == 2
    assert line.startswith("codemap: unsupported (OSError: ")


def test_the_windows_lock_branch_with_a_stand_in_msvcrt(tmp_path, monkeypatch):
    # Runs everywhere so the Windows branch is reached on Linux too.
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    store.ensure_dir(top)
    calls = []

    def locking(fd, mode, nbytes):
        calls.append(mode)
        if mode == 1 and calls.count(1) > 1:    # LK_NBLCK: only the first lock succeeds
            raise OSError(errno.EACCES, "locked")

    stand_in = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=0, locking=locking)
    monkeypatch.setattr(store.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "msvcrt", stand_in)
    fd = store.acquire_write_lock(top)
    with pytest.raises(store.IndexUnreadable) as busy:
        store.acquire_write_lock(top)
    store.release_write_lock(fd)
    assert busy.value.args[0] == store.BUSY_REASON
    assert calls == [1, 1, 0]


def test_a_failing_unlock_does_not_change_the_result(tmp_path, capsys, monkeypatch):
    make_repo(tmp_path, {"a.py": "x = 1\n"})
    module, attr, is_unlock = _lock_function()
    real = getattr(module, attr)

    def lock_but_not_unlock(*args):
        if is_unlock(args):
            raise OSError(errno.EIO, "unlock failed")
        return real(*args)

    monkeypatch.setattr(module, attr, lock_but_not_unlock)
    code, line = _cli(capsys, "build", tmp_path)
    assert (code, line.startswith("codemap: fresh")) == (0, True), line
    if os.name != "nt":
        # Closing every descriptor releases a flock; Windows frees it on its own schedule.
        assert _cli(capsys, "build", tmp_path)[0] == 0
