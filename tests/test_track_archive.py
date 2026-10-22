"""#468: a track archived inside a linked worktree is copied to the main
checkout, glossary terms included, before removing the worktree deletes the
ignored .cai/ with it. Real git repositories and worktrees, as
test_track_start.py does."""
import os
import subprocess

import pytest

import track_archive

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t"]
TEMPLATE = "# Glossary\n\n## Domain\n\n## Process\n"


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo)] + GIT_ID + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", "main", str(main)], check=True)
    git(main, "commit", "-q", "--allow-empty", "-m", "root")
    wt = main / ".claude" / "worktrees" / "feat"
    git(main, "worktree", "add", "-q", "-b", "worktree-feat", str(wt))
    done = wt / ".cai" / "track" / "done" / "feat"
    done.mkdir(parents=True)
    (done / "state.md").write_text("| stage | status |\n", encoding="utf-8")
    (done / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
    return main, wt, done


def run(wt, done):
    return track_archive.archive(str(done), str(wt))


def test_the_archive_is_copied_to_the_main_checkout(repo):
    main, wt, done = repo
    code, out = run(wt, done)
    assert code == 0
    copied = main / ".cai" / "track" / "done" / "feat"
    assert sorted(os.listdir(copied)) == ["ledger.jsonl", "state.md"]
    assert (copied / "state.md").read_text(encoding="utf-8") == "| stage | status |\n"
    assert out[0] == "copied %s to %s" % (done, os.path.realpath(copied))
    assert (main / ".cai" / ".gitignore").read_text() == "*\n"


def test_an_existing_archive_of_that_name_is_never_overwritten(repo):
    main, wt, done = repo
    old = main / ".cai" / "track" / "done" / "feat"
    old.mkdir(parents=True)
    (old / "state.md").write_text("older\n", encoding="utf-8")
    assert run(wt, done)[0] == 0
    assert (old / "state.md").read_text(encoding="utf-8") == "older\n"
    assert (main / ".cai" / "track" / "done" / "feat-1" / "state.md").is_file()
    assert run(wt, done)[0] == 0
    assert (main / ".cai" / "track" / "done" / "feat-2").is_dir()


def test_outside_a_linked_worktree_nothing_is_copied(repo, tmp_path):
    main, _, _ = repo
    here = main / ".cai" / "track" / "done" / "x"
    here.mkdir(parents=True)
    assert run(main, here) == (0, ["not a linked worktree -- the archive stays where it is"])
    plain = tmp_path / "plain"
    plain.mkdir()
    assert run(plain, here) == (0, ["not a git work tree -- nothing to copy"])


def test_glossary_terms_the_main_checkout_lacks_are_added_under_their_heading(repo):
    main, wt, done = repo
    (main / ".cai").mkdir()
    (main / ".cai" / "cai-context.md").write_text(
        TEMPLATE.replace("## Domain\n", "## Domain\n\n**Order**: what a buyer places.\n"),
        encoding="utf-8")
    (wt / ".cai" / "cai-context.md").write_text(
        TEMPLATE.replace("## Domain\n", "## Domain\n\n**Order**: what a buyer places.\n"
                         "**Refund**: money sent back.\n")
        .replace("## Process\n", "## Process\n\n**Triage**: sorting new reports.\n"),
        encoding="utf-8")
    code, out = run(wt, done)
    assert code == 0 and out[-1].startswith("glossary: 2 added")
    text = (main / ".cai" / "cai-context.md").read_text(encoding="utf-8")
    assert text == ("# Glossary\n\n## Domain\n\n**Order**: what a buyer places.\n"
                    "**Refund**: money sent back.\n\n## Process\n**Triage**: sorting new reports.\n")
    # A second run adds nothing twice.
    assert run(wt, done)[1][-1].startswith("glossary: 0 added")
    assert (main / ".cai" / "cai-context.md").read_text(encoding="utf-8") == text


def test_a_term_defined_differently_keeps_the_main_definition_and_is_named(repo):
    main, wt, done = repo
    (main / ".cai").mkdir()
    (main / ".cai" / "cai-context.md").write_text(
        "## Domain\n**Order**: what a buyer places.\n", encoding="utf-8")
    (wt / ".cai" / "cai-context.md").write_text(
        "## Domain\n**order**: a sorted list.\n", encoding="utf-8")
    code, out = run(wt, done)
    assert code == 0
    target = os.path.realpath(main / ".cai" / "cai-context.md")
    assert out[-2:] == ["glossary: 0 added to %s, 1 conflicting" % target,
                        "conflict order: kept the main checkout's definition"]
    assert (main / ".cai" / "cai-context.md").read_text(encoding="utf-8") == (
        "## Domain\n**Order**: what a buyer places.\n")


def test_no_main_glossary_takes_the_worktree_file_whole(repo):
    main, wt, done = repo
    (wt / ".cai" / "cai-context.md").write_text(TEMPLATE + "**X**: y.\n", encoding="utf-8")
    assert run(wt, done)[0] == 0
    assert (main / ".cai" / "cai-context.md").read_text(encoding="utf-8") == TEMPLATE + "**X**: y.\n"


def test_a_failed_copy_exits_2_and_says_why(repo, monkeypatch):
    main, wt, done = repo

    def refuse(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(track_archive.shutil, "copytree", refuse)
    code, out = run(wt, done)
    assert code == 2 and out[-1] == "could not copy into the main checkout: disk full"


def test_main_reports_a_missing_track_dir(tmp_path, capsys):
    assert track_archive.main(["--track-dir", str(tmp_path / "none")]) == 2
    assert "no such track directory" in capsys.readouterr().out


def test_a_heading_the_main_glossary_lacks_is_added_with_its_term(repo):
    main, wt, done = repo
    (main / ".cai").mkdir()
    (main / ".cai" / "cai-context.md").write_text("## Domain\n**A**: b.\n", encoding="utf-8")
    (wt / ".cai" / "cai-context.md").write_text("## Process\n**Triage**: sorting.\n", encoding="utf-8")
    assert run(wt, done)[0] == 0
    assert (main / ".cai" / "cai-context.md").read_text(encoding="utf-8") == (
        "## Domain\n**A**: b.\n\n## Process\n**Triage**: sorting.\n")


def test_a_worktree_of_a_bare_repository_has_no_checkout_to_copy_into(tmp_path):
    bare = tmp_path / "repo.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], capture_output=True)
    git(seed, "commit", "-q", "--allow-empty", "-m", "root")
    git(seed, "push", "-q", "origin", "HEAD:main")
    wt = tmp_path / "wt"
    git(bare, "worktree", "add", "-q", str(wt), "main")
    done = wt / ".cai" / "track" / "done" / "feat"
    done.mkdir(parents=True)
    assert run(wt, done) == (0, ["the main repository is bare -- no checkout to copy into"])


def test_main_prints_each_line_and_exits_0(repo, capsys, monkeypatch):
    main, wt, done = repo
    monkeypatch.chdir(wt)
    assert track_archive.main(["--track-dir", os.path.join(".cai", "track", "done", "feat"),
                               "--project-dir", str(wt)]) == 0
    assert capsys.readouterr().out.startswith("copied ")
    assert (main / ".cai" / "track" / "done" / "feat" / "state.md").is_file()


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_the_glossary_keeps_an_ordinary_file_mode(repo):
    main, wt, done = repo
    (wt / ".cai" / "cai-context.md").write_text("## Domain\n**X**: y.\n", encoding="utf-8")
    assert run(wt, done)[0] == 0
    mode = os.stat(main / ".cai" / "cai-context.md").st_mode & 0o777
    assert mode == os.stat(wt / ".cai" / "cai-context.md").st_mode & 0o777
