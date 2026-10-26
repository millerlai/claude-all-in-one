"""answers.py: a per-project file of the answers a person gave to questions the
evidence could not settle, so a later track does not ask the same thing again.
Real git worktrees, as test_track_archive.py does, because the file must land
in the main checkout whichever worktree the track runs in."""
import os
import subprocess
import sys

import pytest

import answers

SCRIPTS = os.path.dirname(answers.__file__)
GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def rows(path):
    return open(path, encoding="utf-8").read().splitlines()


def test_a_row_has_date_track_first_line_of_the_question_and_answer(tmp_path):
    path = answers.append(str(tmp_path), "feat-x", "Which db?\n   Background: b", "Postgres")
    assert path == os.path.join(str(tmp_path), ".cai", "answers.md")
    cells = rows(path)[-1].split(" | ")
    assert cells[0].startswith("| 20") and len(cells[0]) == len("| 2026-10-25")
    assert cells[1:] == ["feat-x", "Which db?", "Postgres |"]


def test_the_file_sits_in_a_cai_dir_that_ignores_itself(tmp_path):
    answers.append(str(tmp_path), "t", "q", "a")
    assert (tmp_path / ".cai" / ".gitignore").read_text() == "*\n"


def test_pipes_become_escaped_and_newlines_a_space(tmp_path):
    path = answers.append(str(tmp_path), "t", "a|b", "x\r\ny|z\nw")
    assert rows(path)[-1].endswith("| a\\|b | x y\\|z w |")
    assert len(rows(path)) == 1


def test_question_and_answer_are_each_cut_to_1000_bytes_on_a_character(tmp_path):
    path = answers.append(str(tmp_path), "t", "題" * 600, "答" * 600 + "\nmore")
    _, _, question, answer = rows(path)[-1][2:-2].split(" | ")
    assert len(question.encode("utf-8")) == 999 and set(question) == {"題"}
    assert len(answer.encode("utf-8")) == 999 and set(answer) == {"答"}


def test_in_a_linked_worktree_the_file_is_the_main_checkouts(tmp_path):
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    git(main, "commit", "-q", "--allow-empty", "-m", "root")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "side", str(wt))
    path = answers.append(str(wt), "t", "q", "a")
    assert os.path.samefile(path, main / ".cai" / "answers.md")
    assert not (wt / ".cai" / "answers.md").exists()
    assert answers.path(str(wt)) == path


def test_a_write_failure_raises_oserror(tmp_path):
    (tmp_path / ".cai" / "answers.md").mkdir(parents=True)
    with pytest.raises(OSError):
        answers.append(str(tmp_path), "t", "q", "a")


def test_cli_path_prints_the_path(tmp_path):
    done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "answers.py"), "path",
                           "--project-dir", str(tmp_path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == os.path.join(str(tmp_path), ".cai", "answers.md")


def test_eight_processes_appending_fifty_rows_each_lose_none(tmp_path):
    # On Windows a plain O_APPEND lost rows in this exact shape (ledger.py's
    # _write_line explains); the test is what keeps append() on that helper.
    code = ("import sys; sys.path.insert(0, %r); import answers\n"
            "for i in range(50):\n"
            "    answers.append(sys.argv[1], 'p' + sys.argv[2], 'q', 'a%%s-%%d' %% (sys.argv[2], i))\n"
            % SCRIPTS)
    procs = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path), str(n)])
             for n in range(8)]
    assert [p.wait(timeout=120) for p in procs] == [0] * 8
    got = rows(tmp_path / ".cai" / "answers.md")
    assert len(got) == 400 and len(set(got)) == 400
