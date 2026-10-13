"""Tests for plugins/cai/scripts/scratch.py.

The script owns one root, `<temp>/cai-scratch/`, and deletes only from it. Each
test points the temp directory at tmp_path, so nothing here touches the real
one, and a directory the test makes next to the root stands for a person's own
folder that must survive.
"""
import os
import stat
import subprocess
import sys
import tempfile
import time

import pytest

import scratch

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "plugins", "cai", "scripts", "scratch.py")
HOURS = 60 * 60


@pytest.fixture
def temp(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def age(path, seconds):
    then = time.time() - seconds
    os.utime(path, (then, then))


def test_dir_is_new_and_empty_under_the_root(temp):
    first = scratch.new_dir("fix")
    second = scratch.new_dir("fix")
    assert first != second
    for made in (first, second):
        assert os.path.isdir(made) and os.listdir(made) == []
        assert os.path.dirname(made) == str(temp / scratch.ROOT_NAME)
        assert os.path.basename(made).startswith("fix-")


def test_dir_removes_what_an_earlier_run_left(temp):
    stale = scratch.new_dir("old")
    open(os.path.join(stale, "msg.txt"), "w").close()
    age(stale, scratch.STALE_AFTER_S + HOURS)
    fresh = scratch.new_dir("live")
    age(fresh, scratch.STALE_AFTER_S - HOURS)

    kept = scratch.new_dir("next")

    assert not os.path.exists(stale)
    assert os.path.isdir(fresh) and os.path.isdir(kept)


def test_sweep_does_not_reach_outside_the_root(temp):
    # What a person keeps beside the root, whatever it is called and however old.
    theirs = temp / "cai-my-own-notes"
    theirs.mkdir()
    (theirs / "a.txt").write_text("keep")
    age(str(theirs), 30 * 24 * HOURS)
    stale = scratch.new_dir("old")
    age(stale, scratch.STALE_AFTER_S + HOURS)

    scratch.new_dir("next")

    assert (theirs / "a.txt").read_text() == "keep"


def test_sweep_unlinks_a_stale_link_and_leaves_its_target(temp):
    target = temp / "elsewhere"
    target.mkdir()
    (target / "a.txt").write_text("keep")
    base = scratch.root()
    os.makedirs(base)
    link = os.path.join(base, "link")
    try:
        os.symlink(str(target), link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symbolic links")

    # `now` is the seam: utime cannot age a link itself on Windows.
    scratch.sweep(base, time.time() + scratch.STALE_AFTER_S + HOURS)

    assert not os.path.lexists(link)
    assert (target / "a.txt").read_text() == "keep"


def test_clean_removes_the_directory_with_a_read_only_file(temp):
    made = scratch.new_dir("fix")
    held = os.path.join(made, "sub", "object")
    os.makedirs(os.path.dirname(held))
    with open(held, "w") as fh:
        fh.write("x")
    os.chmod(held, stat.S_IREAD)

    assert scratch.main(["clean", made]) == 0

    assert not os.path.exists(made)


def test_a_read_only_file_is_made_writable_and_the_removal_retried(tmp_path):
    # Linux deletes a read-only file without complaint, so rmtree never calls
    # the retry there; this is the one place that runs it on every platform.
    held = tmp_path / "object"
    held.write_text("x")
    os.chmod(held, stat.S_IREAD)

    scratch._make_writable_then(os.unlink, str(held), None)

    assert not held.exists()


def test_the_pre_3_12_rmtree_keyword_removes_a_directory_too(tmp_path, monkeypatch):
    monkeypatch.setattr(scratch, "_HAS_ONEXC", False)
    target = tmp_path / "gone"
    (target / "sub").mkdir(parents=True)
    (target / "sub" / "a.txt").write_text("x")

    scratch._rmtree(str(target))

    assert not target.exists()


def test_sweep_of_a_missing_root_is_not_an_error(tmp_path):
    scratch.sweep(str(tmp_path / "never-made"), time.time())


def test_sweep_goes_on_past_a_child_it_cannot_remove(temp, monkeypatch):
    first, second = scratch.new_dir("a"), scratch.new_dir("b")
    real = scratch._remove

    def refuse_the_first(path):
        if path == first:
            raise PermissionError(path)
        real(path)

    monkeypatch.setattr(scratch, "_remove", refuse_the_first)
    scratch.sweep(scratch.root(), time.time() + scratch.STALE_AFTER_S + HOURS)

    assert os.path.isdir(first) and not os.path.exists(second)


def test_clean_of_a_missing_directory_is_not_an_error(temp):
    made = scratch.new_dir("fix")
    assert scratch.main(["clean", made]) == 0
    assert scratch.main(["clean", made]) == 0


@pytest.mark.parametrize("where", ["beside", "root", "dotdot", "nested"])
def test_clean_refuses_what_is_not_a_child_of_the_root(temp, where, capsys):
    made = scratch.new_dir("fix")
    other = temp / "project"
    other.mkdir()
    (other / "a.txt").write_text("keep")
    path = {"beside": str(other),
            "root": scratch.root(),
            "dotdot": os.path.join(made, "..", ".."),
            "nested": os.path.join(made, "inner")}[where]
    os.makedirs(os.path.join(made, "inner"), exist_ok=True)

    assert scratch.main(["clean", path]) == 2

    assert "refused" in capsys.readouterr().out
    assert (other / "a.txt").read_text() == "keep"
    assert os.path.isdir(os.path.join(made, "inner"))


@pytest.mark.parametrize("label", ["", "a/b", "..", "a b", "_x", "x" * 33, "a\\b"])
def test_dir_refuses_a_label_that_is_not_one_plain_word(temp, label, capsys):
    assert scratch.main(["dir", label]) == 2
    assert "refused" in capsys.readouterr().out
    assert not os.path.exists(scratch.root())


def test_the_command_line_prints_a_path_and_cleans_it(tmp_path):
    env = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path), TMPDIR=str(tmp_path))
    made = subprocess.run([sys.executable, SCRIPT, "dir", "fix"], env=env,
                          capture_output=True, text=True, check=True).stdout.strip()
    assert os.path.isdir(made)
    assert os.path.normcase(os.path.realpath(os.path.dirname(made))) == \
        os.path.normcase(os.path.realpath(str(tmp_path / scratch.ROOT_NAME)))

    done = subprocess.run([sys.executable, SCRIPT, "clean", made], env=env)

    assert done.returncode == 0
    assert not os.path.exists(made)
