"""#450 item 1: the query's text scan holds one file at a time.

tracked_texts used to read every tracked file under the cap into one list
before the first line was matched, so a query held the whole tree in memory.
It now yields file by file; what a query returns is unchanged."""
import collections.abc

import codemap_cli
import codemap_index as idx
import codemap_inventory as inventory
import codemap_query
from codemap_repo import make_repo

FILES = {"a.py": "def alpha():\n    return 'Needle'\n", "b.md": "# needle\nno\nNEEDLE\n",
         "c.txt": "nothing here\n"}


def test_tracked_texts_reads_one_file_per_step(tmp_path, monkeypatch):
    make_repo(tmp_path, FILES)
    reads = []
    real = inventory.read_tracked

    def counting(*args, **kwargs):
        reads.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(inventory, "read_tracked", counting)
    texts = codemap_query.tracked_texts(str(tmp_path))
    assert isinstance(texts, collections.abc.Iterator)
    assert reads == []
    first = next(texts)
    assert reads == [first[0]] == ["a.py"]
    assert [p for p, _ in texts] == ["b.md", "c.txt"]


def test_a_query_finds_the_same_text_lines(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    assert codemap_cli.main(["query", "--project-dir", str(tmp_path), "--", "needle"]) == 0
    hits = [ln for ln in capsys.readouterr().out.splitlines() if " text " in ln or "text" in ln]
    assert any("b.md" in ln for ln in hits) and any("a.py" in ln for ln in hits)
    assert codemap_query.matching_lines("# needle\nno\nNEEDLE\n", ["needle"]) == [
        (1, "# needle"), (3, "NEEDLE")]
