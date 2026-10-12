"""AC13: a query returns hits that each carry path:line, in a fixed order."""
import os

import codemap_cli
import codemap_index as idx
import codemap_query as q
import codemap_store as store
from codemap_repo import git, make_repo, write

FILES = {
    "src/loader.py": "class ConfigLoader:\n    def load_file(self):\n        pass\n\n\n"
                     "def parse_config(text):\n    return text\n",
    "config/settings.py": "DEBUG = True\n",
    "notes/timeouts.txt": "intro\nthe retry timeout is five seconds\nand timeout again\n",
}


def _index(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return str(tmp_path), store.load(str(tmp_path))


def test_terms_split_on_punctuation_and_camel_case_and_dedupe():
    assert q.terms("getUserName user_name") == ["get", "user", "name"]
    assert q.terms("parse-config.py") == ["parse", "config", "py"]
    assert q.terms("HTTPServer") == ["http", "server"]
    assert q.terms("   ") == []


def test_symbol_name_query_points_at_the_declaration_line(tmp_path):
    top, index = _index(tmp_path)
    hits = q.query(top, index, "parse_config", 10)
    first = hits[0]
    assert (first.path, first.line, first.kind, first.name) == \
        ("src/loader.py", 6, "function", "parse_config")
    assert first.score >= 100


def test_path_fragment_query_gives_a_path_hit_at_line_one(tmp_path):
    top, index = _index(tmp_path)
    hits = q.query(top, index, "settings", 10)
    assert [(h.path, h.line, h.kind) for h in hits
            if h.kind == "path"] == [("config/settings.py", 1, "path")]


def test_plain_text_query_finds_the_first_matching_line(tmp_path):
    top, index = _index(tmp_path)
    hits = q.query(top, index, "timeout", 10)
    text = [h for h in hits if h.kind == "text"]
    assert [(h.path, h.line) for h in text] == [("notes/timeouts.txt", 2)]
    assert text[0].score == 2          # one point per matching line


def test_results_are_sorted_and_repeatable(tmp_path):
    top, index = _index(tmp_path)
    one = q.query(top, index, "config load", 10)
    two = q.query(top, index, "config load", 10)
    assert one == two
    assert one == sorted(one, key=lambda h: (-h.score, h.path, h.line))
    assert all(h.line >= 1 and h.path for h in one)


def test_an_exact_name_outranks_a_longer_name_that_contains_it(tmp_path):
    # Without the equal-name bonus both tie at 50 and the path order puts a.py
    # first: only the bonus puts the declaration called exactly `run` ahead.
    make_repo(tmp_path, {"a.py": "def run_all_tasks():\n    pass\n",
                         "b.py": "def run():\n    pass\n"})
    idx.build(str(tmp_path))
    hits = q.query(str(tmp_path), store.load(str(tmp_path)), "run", 10)
    declared = [(h.path, h.score) for h in hits if h.kind == "function"]
    assert declared == [("b.py", 150), ("a.py", 50)]


def test_text_hits_are_capped_at_five_points(tmp_path):
    make_repo(tmp_path, {"log.txt": "needle\n" * 8})
    idx.build(str(tmp_path))
    hits = q.query(str(tmp_path), store.load(str(tmp_path)), "needle", 10)
    assert [(h.kind, h.score) for h in hits] == [("text", 5)]


def test_files_that_cannot_be_scanned_are_skipped_not_fatal(tmp_path):
    make_repo(tmp_path, {"a.py": "def needle():\n    pass\n", "gone.txt": "needle\n"})
    write(tmp_path, "blob.dat", b"needle\0\n", binary=True)
    write(tmp_path, "big.txt", "needle\n" + "x" * 1048577)
    git(tmp_path, "add", "-A")
    idx.build(str(tmp_path))
    os.remove(str(tmp_path / "gone.txt"))        # tracked, deleted, not `git rm`ed

    hits = q.query(str(tmp_path), store.load(str(tmp_path)), "needle", 10)

    assert [h.path for h in hits if h.kind == "text"] == ["a.py"]


def test_limit_caps_the_list(tmp_path):
    top, index = _index(tmp_path)
    assert len(q.query(top, index, "config", 2)) == 2


def test_cli_query_prints_state_line_then_one_line_per_hit(tmp_path, capsys):
    _index(tmp_path)
    assert codemap_cli.main(["query", "--project-dir", str(tmp_path), "parse_config"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("codemap: fresh")
    assert lines[1].endswith(" src/loader.py:6 function parse_config")


def test_cli_query_with_no_hit_says_so(tmp_path, capsys):
    _index(tmp_path)
    assert codemap_cli.main(["query", "--project-dir", str(tmp_path), "zzzqqq"]) == 0
    assert capsys.readouterr().out.splitlines()[1:] == ["no hit"]


def test_cli_query_without_an_index_prints_absent(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    assert codemap_cli.main(["query", "--project-dir", str(tmp_path), "config"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "codemap: absent"
