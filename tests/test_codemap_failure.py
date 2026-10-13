"""AC9: every failure becomes a state line, never a traceback."""
import codemap_cli
import codemap_index as idx
from codemap_repo import make_repo

FILES = {"a.py": "x = 1\n", "b.py": "y = 2\n"}


def _built(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return tmp_path


def _no_traceback(capsys):
    out = capsys.readouterr()
    assert "Traceback" not in out.out + out.err
    return out.out


def test_non_git_directory_status_is_unsupported(tmp_path, capsys):
    assert codemap_cli.main(["status", "--project-dir", str(tmp_path)]) == 0
    assert _no_traceback(capsys).splitlines()[0] == \
        "codemap: unsupported (not a git repository)"


def test_non_git_directory_build_exits_2_and_writes_nothing(tmp_path, capsys):
    assert codemap_cli.main(["build", "--project-dir", str(tmp_path)]) == 2
    assert _no_traceback(capsys).splitlines()[0] == \
        "codemap: unsupported (not a git repository)"
    assert not (tmp_path / ".cai").exists()


def test_garbage_state_json_is_unsupported(tmp_path, capsys):
    top = _built(tmp_path)
    (top / ".cai" / "codemap" / "state.json").write_text("{not json", encoding="utf-8")
    assert codemap_cli.main(["status", "--project-dir", str(top)]) == 0
    first = _no_traceback(capsys).splitlines()[0]
    assert first.startswith("codemap: unsupported (index unreadable: ")
    assert first.endswith("; run build)")


def test_one_byte_changed_data_file_is_unsupported(tmp_path, capsys):
    top = _built(tmp_path)
    path = top / ".cai" / "codemap" / "files.jsonl"
    data = bytearray(path.read_bytes())
    data[-2] = ord("X") if data[-2] != ord("X") else ord("Y")
    path.write_bytes(bytes(data))
    assert codemap_cli.main(["status", "--project-dir", str(top)]) == 0
    assert "index files disagree" in _no_traceback(capsys).splitlines()[0]


def test_missing_data_file_is_unsupported(tmp_path):
    top = _built(tmp_path)
    (top / ".cai" / "codemap" / "symbols.jsonl").unlink()
    st = idx.status(str(top))
    assert st.word == "unsupported"
    assert "symbols.jsonl is missing" in st.detail


def test_adapter_crash_makes_the_file_partial_not_the_build_fail(tmp_path, monkeypatch, capsys):
    import codemap_symbols
    make_repo(tmp_path, FILES)
    real = codemap_symbols.extract

    def crashing(path, language, data):
        if path == "b.py":
            raise RuntimeError("boom")
        return real(path, language, data)

    monkeypatch.setattr(codemap_symbols, "extract", crashing)
    assert codemap_cli.main(["build", "--project-dir", str(tmp_path)]) == 0
    assert "Traceback" not in capsys.readouterr().out
    st = idx.status(str(tmp_path))
    assert idx.state_line(st) == "codemap: partial (1 file not parsed: b.py)"
    assert st.paths == ["b.py"]

    monkeypatch.setattr(codemap_symbols, "extract", real)
    res = idx.update(str(tmp_path))
    assert res.reparsed == 1                       # the partial file is retried
    assert idx.status(str(tmp_path)).word == "fresh"


def test_stale_wins_over_partial(tmp_path, monkeypatch):
    import codemap_symbols
    make_repo(tmp_path, FILES)

    def crashing(path, language, data):
        raise RuntimeError("boom")

    monkeypatch.setattr(codemap_symbols, "extract", crashing)
    idx.build(str(tmp_path))
    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert idx.status(str(tmp_path)).word == "stale"


def test_build_replaces_a_damaged_index(tmp_path, capsys):
    top = _built(tmp_path)
    (top / ".cai" / "codemap" / "state.json").write_text("[]", encoding="utf-8")
    assert codemap_cli.main(["build", "--project-dir", str(top)]) == 0
    _no_traceback(capsys)
    assert idx.status(str(top)).word == "fresh"
