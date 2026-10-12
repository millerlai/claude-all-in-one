"""AC14: Recall@5 and Recall@10, for the index and for the plain-Grep baseline,
match hand-computed values on a three-task fixture."""
import importlib.util
import json
import os

import codemap_index as idx
from codemap_repo import make_repo

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "codemap_recall", os.path.join(REPO_ROOT, "scripts", "codemap_recall.py"))
recall_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recall_mod)

# Eight files each holding the word "gamma" once, so the baseline ranks them by
# path; the index's symbol hits push the real target to the front.
FILES = {"f%d.py" % i: "# gamma\nx = %d\n" % i for i in range(8)}
FILES["target.py"] = "def gamma_handler():\n    pass\n"
FILES["other.py"] = "def delta_thing():\n    pass\n"


def _tasks(tmp_path, rows):
    path = tmp_path / "tasks.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(path)


def test_recall_is_the_found_share_of_the_expected_files():
    assert recall_mod.recall(["a", "b", "c"], ["a", "c"], 2) == 0.5
    assert recall_mod.recall(["a", "b", "c"], ["a", "c"], 3) == 1.0
    assert recall_mod.recall([], ["a"], 5) == 0.0


def test_baseline_ranks_by_matching_lines_then_path(tmp_path):
    make_repo(tmp_path, {"b.py": "gamma\ngamma\n", "a.py": "gamma\n", "c.py": "none\n"})
    assert recall_mod.grep_baseline(str(tmp_path), "Gamma") == ["b.py", "a.py"]


def test_tool_prints_both_sets_with_hand_computed_values(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    tasks = _tasks(tmp_path, [
        {"query": "gamma_handler", "expected_files": ["target.py"]},
        {"query": "delta_thing", "expected_files": ["other.py"]},
        {"query": "gamma", "expected_files": ["f7.py", "target.py"]},
    ])
    rc = recall_mod.main(["--project-dir", str(tmp_path), "--tasks", tasks])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0].startswith("codemap: fresh")
    values = dict(line.rsplit(" ", 1) for line in out[1:] if line.startswith(("index", "grep")))
    # Task 1: index finds target.py first (1.0); grep finds it too (the only
    # file holding the word "handler"... via the term "gamma", position 9).
    assert set(values) == {"index recall@5", "index recall@10", "grep recall@5",
                           "grep recall@10"}
    assert any(line == "tasks 3" for line in out)
    assert float(values["index recall@5"]) >= float(values["grep recall@5"])
    # index: task1 1.0, task2 1.0, task3 -> hits for "gamma": target.py first
    # (name contains gamma), then f0..f7 by path; top 5 = target,f0,f1,f2,f3 ->
    # 1/2; top 10 holds target and f7 -> 1.0.
    assert values["index recall@5"] == "0.83"       # (1 + 1 + 0.5) / 3
    assert values["index recall@10"] == "1.00"      # (1 + 1 + 1) / 3
    # grep: gamma_handler -> terms gamma, handler: files with a "gamma" line are
    # f0..f7 and target.py (path order: f0..f7, target.py) -> target is 9th.
    # task2 delta_thing: other.py is the only file with "delta" -> 1.0.
    # task3: expected f7 (8th) and target (9th): @5 0, @10 1.0
    assert values["grep recall@5"] == "0.33"        # (0 + 1 + 0) / 3
    assert values["grep recall@10"] == "1.00"


def test_index_ranking_counts_each_file_once(tmp_path, capsys):
    # Six symbol hits in many.py come before goal.py's one text hit. Counting
    # hits instead of files would push goal.py to rank 8 and report recall@5 0.
    many = "".join("def alpha_%d():\n    pass\n" % i for i in range(6))
    make_repo(tmp_path, {"many.py": many, "goal.py": "# ALPHA\n"})
    idx.build(str(tmp_path))
    tasks = _tasks(tmp_path, [{"query": "alpha", "expected_files": ["goal.py"]}])

    assert recall_mod.main(["--project-dir", str(tmp_path), "--tasks", tasks]) == 0

    values = dict(line.rsplit(" ", 1) for line in capsys.readouterr().out.splitlines()
                  if line.startswith(("index", "grep")))
    assert values["index recall@5"] == "1.00"
    assert values["grep recall@5"] == "1.00"       # `ALPHA` found case-insensitively


def test_malformed_task_line_names_the_line_number(tmp_path, capsys):
    make_repo(tmp_path, FILES)
    path = tmp_path / "tasks.jsonl"
    path.write_text('{"query": "a", "expected_files": ["x.py"]}\nnot json\n', encoding="utf-8")
    rc = recall_mod.main(["--project-dir", str(tmp_path), "--tasks", str(path)])
    assert rc == 1
    assert "line 2" in capsys.readouterr().err
