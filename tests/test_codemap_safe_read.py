"""The three readers of a tracked file (inventory, parse, text scan) go through
one function that refuses anything but a regular file inside the repository,
and never reads past the cap it was given."""
import errno
import hashlib
import os
import subprocess
import sys

import pytest

import codemap_cli
import codemap_index as idx
import codemap_inventory as inv
import codemap_query
import codemap_store as store
from codemap_repo import make_repo, write


def _top(tmp_path):
    return os.path.realpath(str(tmp_path))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _link(target, link, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need privileges here")


def test_read_to_the_end_keeps_the_hash_and_not_the_bytes(tmp_path):
    body = b"x = 1\n" * 20000   # more than one CHUNK
    write(tmp_path, "a.py", body, binary=True)
    got = inv.read_tracked(_top(tmp_path), "a.py")
    mtime = os.stat(os.path.join(str(tmp_path), "a.py")).st_mtime_ns
    assert got == inv.TrackedRead(None, len(body), _sha(body), None, mtime)


def test_bytes_come_back_untranslated(tmp_path):
    # Windows' text mode would turn CRLF into LF and stop at 0x1A.
    body = b"a\r\nb\x1a c\r\n"
    write(tmp_path, "a.txt", body, binary=True)
    top = _top(tmp_path)
    mtime = os.stat(os.path.join(str(tmp_path), "a.txt")).st_mtime_ns
    assert inv.read_tracked(top, "a.txt") == inv.TrackedRead(None, len(body), _sha(body), None,
                                                             mtime)
    assert inv.read_tracked(top, "a.txt", 100).data == body


def test_a_limit_reads_at_most_limit_plus_one_byte(tmp_path, monkeypatch):
    body = b"y" * 200000
    write(tmp_path, "big.txt", body, binary=True)
    seen = []
    real = os.read
    monkeypatch.setattr(os, "read", lambda fd, n: seen.append(real(fd, n)) or seen[-1])
    got = inv.read_tracked(_top(tmp_path), "big.txt", 70000)
    assert got.reason is None
    assert len(got.data) == 70001 and got.size == 70001
    assert got.sha256 == _sha(body[:70001])
    assert sum(len(c) for c in seen) == 70001


def test_a_file_of_exactly_the_limit_is_returned_whole(tmp_path):
    body = b"z" * 10
    write(tmp_path, "a.txt", body, binary=True)
    got = inv.read_tracked(_top(tmp_path), "a.txt", 10)
    assert got.data == body and got.size == 10 and got.sha256 == _sha(body)


def test_a_directory_is_not_regular_and_is_not_opened(tmp_path, monkeypatch):
    os.makedirs(str(tmp_path / "d.py"))
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("opened"))
    got = inv.read_tracked(_top(tmp_path), "d.py")
    assert got == inv.TrackedRead("not-regular", None, None, None)


def test_a_symlink_is_not_regular_and_its_target_is_not_opened(tmp_path, monkeypatch):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    write(outside, "secret.py", "TOKEN = 1\n")
    _link(str(outside / "secret.py"), str(repo / "a.py"))
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("opened"))
    assert inv.read_tracked(_top(repo), "a.py", 100).reason == "not-regular"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_fifo_is_not_regular_and_does_not_block(tmp_path):
    os.mkfifo(str(tmp_path / "a.py"))
    assert inv.read_tracked(_top(tmp_path), "a.py").reason == "not-regular"


def test_a_parent_directory_linked_outside_the_repository_is_refused(tmp_path, monkeypatch):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    write(outside, "pkg/m.py", "TOKEN = 1\n")
    _link(str(outside / "pkg"), str(repo / "pkg"), directory=True)
    monkeypatch.setattr(os, "open", lambda *a, **k: pytest.fail("opened"))
    got = inv.read_tracked(_top(repo), "pkg/m.py", 100)
    assert got == inv.TrackedRead("outside-repository", None, None, None)


def test_a_parent_directory_linked_inside_the_repository_is_read(tmp_path):
    write(tmp_path, "real/m.py", "x = 1\n")
    _link(str(tmp_path / "real"), str(tmp_path / "alias"), directory=True)
    got = inv.read_tracked(_top(tmp_path), "alias/m.py", 100)
    assert got.reason is None and got.data == b"x = 1\n"


def test_a_deleted_file_and_a_file_used_as_a_directory_are_missing(tmp_path):
    write(tmp_path, "a.py", "x = 1\n")
    top = _top(tmp_path)
    assert inv.read_tracked(top, "gone.py").reason == "missing"
    assert inv.read_tracked(top, "a.py/inner.py").reason == "missing"


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses the name outright")
def test_a_name_windows_cannot_hold_is_missing_and_not_unopenable(tmp_path):
    # A repo written on Linux tracks `a?b.md`; the Windows checkout cannot create
    # it and os.lstat answers WinError 123, a plain OSError. The file is absent,
    # so it must not sit in `partial` on every update.
    assert inv.read_tracked(_top(tmp_path), "a?b.md").reason == "missing"


def test_a_name_too_long_for_the_filesystem_is_missing_and_not_unopenable(tmp_path, monkeypatch):
    def too_long(*a, **k):
        raise OSError(errno.ENAMETOOLONG, "File name too long")
    monkeypatch.setattr(os, "lstat", too_long)
    assert inv.read_tracked(_top(tmp_path), "a.py").reason == "missing"


def test_a_file_that_cannot_be_opened_names_the_exception(tmp_path, monkeypatch):
    write(tmp_path, "a.py", "x = 1\n")

    def refuse(*a, **k):
        raise PermissionError("no")
    monkeypatch.setattr(os, "open", refuse)
    got = inv.read_tracked(_top(tmp_path), "a.py")
    assert got.reason == "%s: PermissionError" % inv.CANNOT_OPEN
    assert (got.size, got.sha256, got.data) == (None, None, None)


def test_every_exit_is_reachable_where_the_platform_cannot_reach_it(tmp_path, monkeypatch):
    write(tmp_path, "a.py", "x = 1\n")
    top = _top(tmp_path)

    def raiser(exc):
        def fail(*a, **k):
            raise exc
        return fail

    with monkeypatch.context() as m:           # raced away between lstat and open
        m.setattr(os, "open", raiser(FileNotFoundError()))
        assert inv.read_tracked(top, "a.py").reason == "missing"
    with monkeypatch.context() as m:           # unreadable while being read
        m.setattr(os, "read", raiser(OSError("io")))
        assert inv.read_tracked(top, "a.py").reason == "cannot-open: OSError"
        assert inv.read_tracked(top, "a.py", 10).reason == "cannot-open: OSError"
    with monkeypatch.context() as m:           # another drive on Windows
        m.setattr(os.path, "commonpath", raiser(ValueError()))
        assert inv.read_tracked(top, "a.py").reason == "outside-repository"
    with monkeypatch.context() as m:           # lstat itself refused
        m.setattr(os, "lstat", raiser(PermissionError()))
        assert inv.read_tracked(top, "a.py").reason == "cannot-open: PermissionError"


def test_a_descriptor_is_closed_after_a_failed_read(tmp_path, monkeypatch):
    write(tmp_path, "a.py", "x = 1\n")
    opened, closed = [], []
    real_open, real_close = os.open, os.close
    monkeypatch.setattr(os, "open", lambda *a, **k: opened.append(real_open(*a, **k)) or opened[-1])
    monkeypatch.setattr(os, "close", lambda fd: closed.append(fd) or real_close(fd))

    def fail(*a, **k):
        raise OSError("io")
    monkeypatch.setattr(os, "read", fail)
    inv.read_tracked(_top(tmp_path), "a.py")
    assert opened and closed == opened


# --- inventory: git still says 100644, the working tree says otherwise ---------

def test_inventory_records_a_file_replaced_by_a_link_as_not_regular(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    write(outside, "secret.py", "TOKEN = 1\n")
    make_repo(repo, {"a.py": "x = 1\n"})
    os.remove(str(repo / "a.py"))
    _link(str(outside / "secret.py"), str(repo / "a.py"))

    by_path = {f.path: f for f in inv.inventory(str(repo))}

    assert by_path["a.py"].reason == "not-regular"
    assert by_path["a.py"].sha256 is None


def test_inventory_records_a_file_under_a_directory_linked_outside_as_outside(tmp_path):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    make_repo(repo, {"pkg/m.py": "x = 1\n"})
    os.rename(str(repo / "pkg"), str(outside))
    _link(str(outside), str(repo / "pkg"), directory=True)

    by_path = {f.path: f for f in inv.inventory(str(repo))}

    assert by_path["pkg/m.py"].reason == "outside-repository"
    assert by_path["pkg/m.py"].sha256 is None


# --- parse: the bytes parsed are the bytes the record's hash describes ---------

def _swapping_inventory(monkeypatch, name, text, after=None):
    """Makes the file change after inventory has listed it, which is the
    window between the two reads."""
    real = idx.inventory.inventory

    def swapped(top):
        listed = real(top)
        write(top, name, text)
        if after:
            after()
        return listed
    monkeypatch.setattr(idx.inventory, "inventory", swapped)


def test_a_record_hashes_the_bytes_it_was_parsed_from(tmp_path, monkeypatch):
    top = make_repo(tmp_path, {"a.py": "def old():\n    pass\n"})
    new = "def new():\n    pass\n"
    with monkeypatch.context() as m:
        _swapping_inventory(m, "a.py", new)
        idx.build(top)

    index = store.load(top)
    assert index.files["a.py"]["sha256"] == _sha(new.encode("utf-8"))
    assert index.files["a.py"]["bytes"] == len(new)
    assert [s["name"] for s in index.symbols] == ["new"]
    assert idx.status(top).word == "fresh"
    write(top, "a.py", "def newer():\n    pass\n")
    assert idx.status(top).word == "stale"


def _reads_of(monkeypatch, name, armed=lambda: True):
    """Lengths of the os.read results on descriptors currently open on a file
    called `name`, while `armed()` is true. A descriptor leaves the set when it
    is closed: the OS hands its number to the next file or pipe, and on POSIX
    subprocess reads its error pipe and a child's output with os.read, so a
    set that kept the number would count those reads too."""
    reads, fds = [], set()
    real_open, real_read, real_close = os.open, os.read, os.close

    def opening(path, *a, **k):
        fd = real_open(path, *a, **k)
        if armed() and os.path.basename(str(path)) == name:
            fds.add(fd)
        return fd

    def reading(fd, n):
        data = real_read(fd, n)
        if fd in fds:
            reads.append(len(data))
        return data

    def closing(fd):
        fds.discard(fd)
        real_close(fd)
    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "read", reading)
    monkeypatch.setattr(os, "close", closing)
    return reads


def test_a_reused_descriptor_number_is_not_counted_as_the_file(tmp_path, monkeypatch):
    # What CI saw on Linux: after a.py is closed, git's pipes (subprocess reads
    # them with os.read) get the number it gave back. Forced here by hand.
    write(tmp_path, "a.py", b"x = 1\n", binary=True)
    reads = _reads_of(monkeypatch, "a.py")
    fd = os.open(str(tmp_path / "a.py"), os.O_RDONLY | getattr(os, "O_BINARY", 0))
    assert len(os.read(fd, 100)) == 6
    os.close(fd)
    r, w = os.pipe()
    try:
        if r != fd:
            pytest.skip("this platform did not hand the closed number out again")
        os.write(w, b"abcde")
        assert os.read(r, 5) == b"abcde"
    finally:
        os.close(r)
        os.close(w)
    assert reads == [6]


def test_parsing_reads_at_most_the_cap_plus_one_byte(tmp_path, monkeypatch):
    top = make_repo(tmp_path, {"a.py": "x = 1\n"})
    monkeypatch.setattr(idx, "MAX_PARSE_BYTES", 100)
    counting = [False]
    reads = _reads_of(monkeypatch, "a.py", armed=lambda: counting[0])
    # inventory still reports the old, small size; the file has grown since
    _swapping_inventory(monkeypatch, "a.py", "y" * 5000, after=lambda: counting.__setitem__(0, True))

    idx.build(top)

    assert sum(reads) == 101
    record = store.load(top).files["a.py"]
    assert record["reason"] == "too-large"
    assert record["bytes"] == 6                      # inventory's figure, as before


# --- query: the text scan goes through the same read ----------------------------

def _opened_names(monkeypatch):
    seen, real = [], os.open

    def opening(path, *a, **k):
        seen.append(os.path.basename(str(path)))
        return real(path, *a, **k)
    monkeypatch.setattr(os, "open", opening)
    return seen


def test_the_text_scan_reads_at_most_the_cap_plus_one_byte(tmp_path, monkeypatch):
    make_repo(tmp_path, {"a.py": "needle\n" * 1000})
    monkeypatch.setattr(codemap_query, "MAX_TEXT_BYTES", 100)
    fds, reads = set(), []
    real_open, real_read = os.open, os.read

    def opening(path, *a, **k):
        fd = real_open(path, *a, **k)
        if os.path.basename(str(path)) == "a.py":
            fds.add(fd)
        return fd

    def reading(fd, n):
        data = real_read(fd, n)
        if fd in fds:
            reads.append(len(data))
        return data
    monkeypatch.setattr(os, "open", opening)
    monkeypatch.setattr(os, "read", reading)

    assert codemap_query.tracked_texts(str(tmp_path)) == []
    assert sum(reads) == 101


def test_a_text_scan_does_not_follow_a_file_replaced_by_a_link(tmp_path, monkeypatch, capsys):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    write(outside, "secret.py", "TOKEN = 'hunter2'\n")
    top = make_repo(repo, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    idx.build(top)
    os.remove(str(repo / "a.py"))
    _link(str(outside / "secret.py"), str(repo / "a.py"))
    opened = _opened_names(monkeypatch)

    assert codemap_cli.main(["query", "--project-dir", top, "hunter2"]) == 0

    out = capsys.readouterr().out
    assert "hunter2" not in out
    assert "secret.py" not in opened
    assert inv.inventory(top)[0].reason == "not-regular"


def test_a_text_scan_does_not_read_under_a_directory_linked_outside(tmp_path, monkeypatch, capsys):
    repo, outside = tmp_path / "repo", tmp_path / "outside"
    repo.mkdir()
    top = make_repo(repo, {"pkg/m.py": "TOKEN = 'hunter2'\n", "b.py": "y = 2\n"})
    idx.build(top)
    os.rename(str(repo / "pkg"), str(outside))
    _link(str(outside), str(repo / "pkg"), directory=True)
    opened = _opened_names(monkeypatch)

    assert codemap_cli.main(["query", "--project-dir", top, "hunter2"]) == 0

    assert "hunter2" not in capsys.readouterr().out
    assert "m.py" not in opened
    assert "pkg/m.py" not in [p for p, _ in codemap_query.tracked_texts(top)]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_file_replaced_by_a_fifo_does_not_hang_status_update_or_query(tmp_path):
    top = make_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    idx.build(top)
    os.remove(os.path.join(top, "a.py"))
    os.mkfifo(os.path.join(top, "a.py"))

    for command in (["status"], ["update"], ["query", "x"]):
        # A blocked open would never return; the timeout turns it into a failure.
        done = subprocess.run([sys.executable, codemap_cli.__file__, command[0],
                               "--project-dir", top, *command[1:]],
                              capture_output=True, timeout=30)
        assert done.returncode == 0, (command, done.stderr)

    assert store.load(top).files["a.py"]["reason"] == "not-regular"
