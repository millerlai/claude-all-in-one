"""The command line as a person's shell meets it: a real process whose pipe is
not UTF-8, a subdirectory as --project-dir, and a failure nobody foresaw.

The other codemap tests call main() in-process under capsys, which swaps stdout
for a str buffer and so cannot see what a Windows pipe does to a non-ASCII name.
"""
import os
import subprocess
import sys

import codemap_cli
import codemap_index as idx
import codemap_store as store
from codemap_repo import make_repo, write

CJK = chr(0x8aaa)       # keeps this file ASCII
ASCII_PIPE = dict(os.environ, PYTHONIOENCODING="ascii:strict")


def _cli(*args):
    return subprocess.run([sys.executable, codemap_cli.__file__, *args],
                          capture_output=True, env=ASCII_PIPE)


def test_status_names_a_non_ascii_file_under_an_ascii_pipe(tmp_path):
    name = "docs/%s.md" % CJK
    make_repo(tmp_path, {"a.py": "x = 1\n", name: "# one\n"})
    idx.build(str(tmp_path))
    write(tmp_path, name, "# two\n")

    proc = _cli("status", "--project-dir", str(tmp_path))

    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.decode("utf-8")
    assert out.splitlines()[0].startswith("codemap: stale (1 file changed")
    assert CJK in out


def test_query_prints_a_non_ascii_text_hit_under_an_ascii_pipe(tmp_path):
    make_repo(tmp_path, {"a.py": "x = 1\n", "notes.txt": "needle %s\n" % CJK})
    idx.build(str(tmp_path))

    proc = _cli("query", "--project-dir", str(tmp_path), "needle")

    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.decode("utf-8")
    assert out.splitlines()[0].startswith("codemap: fresh")
    assert "notes.txt:1 text needle %s" % CJK in out


def test_unexpected_exception_is_one_state_line_and_exit_2(tmp_path, monkeypatch, capsys):
    make_repo(tmp_path, {"a.py": "x = 1\n"})

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store, "write_atomic", boom)
    assert codemap_cli.main(["build", "--project-dir", str(tmp_path)]) == 2
    out = capsys.readouterr()
    assert out.out.splitlines() == ["codemap: unsupported (OSError: disk full)"]
    assert "Traceback" not in out.out + out.err


def test_project_dir_inside_the_repository_resolves_to_its_top(tmp_path, capsys):
    make_repo(tmp_path, {"sub/a.py": "x = 1\n", "b.py": "y = 2\n"})

    assert codemap_cli.main(["build", "--project-dir", str(tmp_path / "sub")]) == 0

    assert capsys.readouterr().out.splitlines()[0] == "codemap: fresh (2 files)"
    assert (tmp_path / ".cai" / "codemap" / "state.json").exists()
    assert not (tmp_path / "sub" / ".cai").exists()
